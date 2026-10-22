# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
"""Job `transcribe`: phiên âm từng track (Mic, Discord…) của một bản ghi thành `transcript.json` theo từng từ.

Mỗi track: tách audio mono 16 kHz → tìm đoạn có tiếng → chia chunk (≤ vài phút) → ASR từng chunk, mỗi chunk xong ghi
một file (chạy lại thì bỏ qua chunk đã có) → lọc câu "ảo giác" → tinh chỉnh đầu/cuối câu theo năng lượng → ghép mọi
track theo thời gian. Thời gian lưu là giây trên bản ghi gốc.
"""

from __future__ import annotations

import json
import os
import re
import time
import unicodedata
import wave
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np

from .. import media
from . import asr, gpu, refine, vad

SCHEMA = "contextcut-transcript/1"
SR = asr.SAMPLE_RATE
LOW_CONF = 0.4
EDGE_GAP_S = 0.3  # khoảng lặng giữa hai từ đủ dài để coi là ranh giới câu cần tinh chỉnh
# Câu Whisper tiếng Việt hay "nghe" ra trên đoạn im lặng/nhạc (học từ phụ đề YouTube)
HALLUCINATIONS = (
    "hay subscribe cho kenh ghien mi go",
    "de khong bo lo nhung video hap dan",
    "cam on cac ban da theo doi",
    "hen gap lai cac ban trong nhung video tiep theo",
    "dang ky kenh",
    "nhan chuong de nhan thong bao",
)
MAX_SYLLABLES_PER_S = 15
MIN_RATE_SYLLABLES = 6
UNK = re.compile(r"<?\bunk\b>?", re.IGNORECASE)


def plain(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower()).replace("đ", "d")
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return " ".join(re.sub(r"[^\w\s]", " ", text).split())


def is_hallucination(seg: dict[str, Any]) -> bool:
    text = plain(seg.get("text") or "")
    if not text:
        return True
    if any(h in text for h in HALLUCINATIONS):
        return True
    # Câu dài nhét vào chưa tới một giây (PhoWhisper trên tiếng lắt nhắt: 13 âm tiết trong 0,6 s, no_speech_prob ≈ 0):
    # người nói nhanh cũng chỉ ~8 âm tiết/giây
    syllables, dur = len(text.split()), seg["end"] - seg["start"]
    if syllables >= MIN_RATE_SYLLABLES and syllables > MAX_SYLLABLES_PER_S * max(dur, 0.01):
        return True
    nsp, lp = seg.get("no_speech_prob"), seg.get("avg_logprob")
    return nsp is not None and lp is not None and nsp > 0.6 and lp < -1.0


def strip_unk(seg: dict[str, Any]) -> dict[str, Any]:
    """Bỏ token `unk`/`<unk>` PhoWhisper lọt ra (từ tokenizer, không phải lời nói)."""
    words = [w for w in seg["words"] if not UNK.fullmatch(w["w"].strip())]
    return seg | {"text": " ".join(UNK.sub(" ", seg["text"]).split()), "words": words}


def read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path)) as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768


def write_json(path: Path, data: Any) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def segment_dict(seg: asr.Segment, offset: float) -> dict[str, Any]:
    d = asdict(seg)
    d["start"], d["end"] = round(seg.start + offset, 3), round(seg.end + offset, 3)
    d["words"] = [{"w": w.text, "start": round(w.start + offset, 3), "end": round(w.end + offset, 3), "p": w.prob}
                  for w in seg.words]
    return d


def refine_track(segments: list[dict[str, Any]], env: np.ndarray) -> None:
    """Tinh chỉnh từ đứng sau/trước một khoảng lặng ≥ EDGE_GAP_S (đầu và cuối câu); giữ `raw_start`/`raw_end`."""
    words = [w for s in segments for w in s["words"]]
    for i, w in enumerate(words):
        prev_end = words[i - 1]["end"] if i else None
        next_start = words[i + 1]["start"] if i + 1 < len(words) else None
        edge_start = prev_end is None or w["start"] - prev_end >= EDGE_GAP_S
        edge_end = next_start is None or next_start - w["end"] >= EDGE_GAP_S
        if not (edge_start or edge_end):
            continue
        start, end = refine.refine_edges(env, w["start"], w["end"])
        if edge_start and start != w["start"]:
            start = max(start, prev_end if prev_end is not None else 0.0)
            if start < w["end"]:
                w["raw_start"], w["start"] = w["start"], start
        if edge_end and end != w["end"]:
            end = min(end, next_start) if next_start is not None else end
            if end > w["start"]:
                w["raw_end"], w["end"] = w["end"], end
    for s in segments:
        if s["words"]:
            s["start"], s["end"] = s["words"][0]["start"], s["words"][-1]["end"]


def run(params: dict[str, Any], report: Callable[..., None],
        load_backend: Callable[..., asr.Backend] = asr.load) -> dict[str, Any]:
    rec = params["recording"]
    model = params.get("model") or asr.default_model()
    lang = params.get("language") or "vi"
    base = Path(params["companion"]) / "analysis" / rec["file_hash"]
    tracks = params["tracks"]
    backend: asr.Backend | None = None
    new_segments: list[dict[str, Any]] = []
    track_info: list[dict[str, Any]] = []
    started = time.monotonic()

    def backend_ready() -> asr.Backend:
        nonlocal backend
        if backend is None:
            report(f"nạp model {model}")
            backend = load_backend(model, device=params.get("device", "auto"),
                                   allow_download=params.get("allow_download", False))
        return backend

    with gpu.VramMonitor() as vram:
        try:
            for ti, track in enumerate(tracks):
                t0 = time.monotonic()
                folder = base / "asr" / f"{track['index']}-{model}-{lang}"
                folder.mkdir(parents=True, exist_ok=True)
                wav = folder / "audio.wav"
                report(f"track {track['index']} ({track.get('role')}): tách audio", progress=ti / len(tracks))
                media.extract_audio(rec["path"], track["index"], wav)
                try:
                    audio = read_wav(wav)
                    plan_file = folder / "plan.json"
                    plan = json.loads(plan_file.read_text(encoding="utf-8")) if plan_file.exists() else None
                    if not plan or plan.get("samples") != len(audio):
                        report(f"track {track['index']}: tìm đoạn có tiếng", progress=ti / len(tracks))
                        regions = vad.speech_regions(audio, SR, params.get("vad", "silero"))
                        chunks = vad.plan_chunks(regions, max_chunk_s=backend_ready().max_chunk_s)
                        plan = {"samples": len(audio), "regions": regions, "chunks": chunks}
                        write_json(plan_file, plan)
                    chunks = [tuple(c) for c in plan["chunks"]]
                    total = sum(b - a for a, b in chunks) or 1.0
                    done = 0.0
                    segments: list[dict[str, Any]] = []
                    for ci, (a, b) in enumerate(chunks):
                        chunk_file = folder / f"chunk-{ci:04d}.json"
                        if not chunk_file.exists():
                            frac = (ti + done / total) / len(tracks)
                            report(f"track {track['index']}: phiên âm {ci + 1}/{len(chunks)}", progress=frac)
                            piece = audio[int(a * SR):int(b * SR)]
                            segs = backend_ready().transcribe(piece, lang, params.get("prompt"))
                            write_json(chunk_file, {"chunk": [a, b], "segments": [segment_dict(s, a) for s in segs]})
                        segments += json.loads(chunk_file.read_text(encoding="utf-8"))["segments"]
                        done += b - a
                    segments = [strip_unk(s) for s in segments]
                    kept = [s for s in segments if not is_hallucination(s)]
                    refine_track(kept, refine.envelope(audio, SR))
                    for s in kept:
                        s["flags"] = ["low_conf"] if any(w["p"] is not None and w["p"] < LOW_CONF for w in s["words"]) else []
                        new_segments.append({"track": track["index"], "speaker": track.get("speaker"), "start": s["start"],
                                             "end": s["end"], "text": s["text"], "words": s["words"],
                                             "avg_logprob": s.get("avg_logprob"), "flags": s["flags"]})
                    track_info.append({"index": track["index"], "role": track.get("role"), "speaker": track.get("speaker"),
                                       "model": model, "language": lang, "audio_s": round(len(audio) / SR, 2),
                                       "speech_s": round(sum(b - a for a, b in plan["regions"]), 2),
                                       "segments": len(kept), "dropped": len(segments) - len(kept),
                                       "elapsed_s": round(time.monotonic() - t0, 1)})
                finally:
                    wav.unlink(missing_ok=True)
        finally:
            if backend is not None:
                backend.close()

    out_file = base / "transcript.json"
    redone = {t["index"] for t in tracks}
    old = json.loads(out_file.read_text(encoding="utf-8")) if out_file.exists() else None
    if old and old.get("language") == lang:
        new_segments += [s for s in old["segments"] if s["track"] not in redone]
        track_info += [t for t in old["tracks"] if t["index"] not in redone]
    new_segments.sort(key=lambda s: (s["start"], s["track"]))
    track_info.sort(key=lambda t: t["index"])
    transcript = {"schema": SCHEMA, "recording": rec, "language": lang, "model": model,
                  "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "tracks": track_info, "segments": new_segments}
    write_json(out_file, transcript)
    words = sum(len(s["words"]) for s in new_segments)
    return {"transcript": str(out_file), "segments": len(new_segments), "words": words, "tracks": track_info,
            "model": model, "device": getattr(backend, "device", None), "elapsed_s": round(time.monotonic() - started, 1),
            **vram.summary()}
