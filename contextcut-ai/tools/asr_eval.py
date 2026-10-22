# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
"""Đo ASR so với mốc gõ tay (định dạng `lyric-calibration/1` của Lyric Calibrator, D:\\SongMV): WER, lệch đầu/cuối
từ và đầu/cuối câu, thời gian chạy, VRAM đỉnh — mỗi model một tiến trình (VRAM đo sạch), có/không tinh chỉnh ranh giới.

    uv run --directory contextcut-ai --no-sync python tools/asr_eval.py --calibration <file.json> --audio <wav|mkv>
        [--index 0] [--models large-v3 phowhisper-large parakeet-ctc-vi] [--ends] [--out kết-quả.json]

`--ends`: mốc có cả cuối từ thật (gõ ở chế độ "Giữ phím = độ dài chữ"); không có thì chỉ đo đầu từ/đầu câu.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import subprocess
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any

import numpy as np


def normalize(text: str) -> list[str]:
    """Chữ thường, bỏ dấu câu, giữ dấu thanh (NFC)."""
    text = unicodedata.normalize("NFC", text.lower())
    return re.sub(r"[^\w\s]", " ", text).split()


def _tokens(words: list[dict[str, Any]]) -> tuple[list[str], list[int]]:
    """Token đã chuẩn hoá + chỉ số từ gốc của từng token (một "từ" ASR có thể ra 0 hoặc 2 token)."""
    toks, owner = [], []
    for i, w in enumerate(words):
        for t in normalize(w["w"]):
            toks.append(t)
            owner.append(i)
    return toks, owner


def _levenshtein(ref: list[str], hyp: list[str]) -> list[list[int]]:
    d = [[0] * (len(hyp) + 1) for _ in range(len(ref) + 1)]
    for i in range(len(ref) + 1):
        d[i][0] = i
    for j in range(len(hyp) + 1):
        d[0][j] = j
    for i in range(1, len(ref) + 1):
        for j in range(1, len(hyp) + 1):
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (ref[i - 1] != hyp[j - 1]))
    return d


def wer(ref: str | list[str], hyp: str | list[str]) -> float:
    r = normalize(ref) if isinstance(ref, str) else ref
    h = normalize(hyp) if isinstance(hyp, str) else hyp
    if not r:
        return 0.0 if not h else 1.0
    return round(_levenshtein(r, h)[len(r)][len(h)] / len(r), 4)


def align_words(ref: list[str], hyp: list[str]) -> list[tuple[int, int]]:
    """Cặp (i, j) có token bằng nhau trên một đường Levenshtein tối ưu."""
    d = _levenshtein(ref, hyp)
    i, j, pairs = len(ref), len(hyp), []
    while i > 0 and j > 0:
        if ref[i - 1] == hyp[j - 1] and d[i][j] == d[i - 1][j - 1]:
            pairs.append((i - 1, j - 1))
            i, j = i - 1, j - 1
        elif d[i][j] == d[i - 1][j - 1] + 1:
            i, j = i - 1, j - 1
        elif d[i][j] == d[i - 1][j] + 1:
            i -= 1
        else:
            j -= 1
    return pairs[::-1]


def _word_pairs(ref_words: list[dict[str, Any]], hyp_words: list[dict[str, Any]]) -> list[tuple[int, int]]:
    rt, ro = _tokens(ref_words)
    ht, ho = _tokens(hyp_words)
    pairs, seen = [], set()
    for i, j in align_words(rt, ht):
        key = (ro[i], ho[j])
        if key not in seen and ro[i] not in {p[0] for p in pairs} and ho[j] not in {p[1] for p in pairs}:
            seen.add(key)
            pairs.append(key)
    return pairs


def ms(a: float, b: float) -> int:
    return int(round(abs(a - b) * 1000))


def timing_errors(ref_words: list[dict[str, Any]], hyp_words: list[dict[str, Any]]) -> dict[str, Any]:
    pairs = _word_pairs(ref_words, hyp_words)
    return {"matched": len(pairs),
            "word_start_ms": [ms(hyp_words[j]["start"], ref_words[i]["start"]) for i, j in pairs],
            "word_end_ms": [ms(hyp_words[j]["end"], ref_words[i]["end"]) for i, j in pairs]}


def line_errors(lines: list[dict[str, Any]], hyp_words: list[dict[str, Any]]) -> dict[str, list[int]]:
    """Đầu câu mốc ↔ đầu từ ASR khớp với từ đầu câu; cuối câu ↔ cuối từ ASR khớp với từ cuối câu."""
    ref_words, first, last = [], [], []
    for line in lines:
        first.append(len(ref_words))
        ref_words += line["words"]
        last.append(len(ref_words) - 1)
    match = dict(_word_pairs(ref_words, hyp_words))
    starts = [ms(hyp_words[match[f]]["start"], lines[k]["start"]) for k, f in enumerate(first) if f in match]
    ends = [ms(hyp_words[match[e]]["end"], lines[k]["end"]) for k, e in enumerate(last) if e in match]
    return {"line_start_ms": starts, "line_end_ms": ends}


def summarize(values: list[int]) -> dict[str, Any]:
    if not values:
        return {"n": 0, "median": None, "p90": None, "mean": None}
    a = np.array(values, dtype=float)
    return {"n": len(values), "median": int(round(np.median(a))), "p90": int(round(np.percentile(a, 90))),
            "mean": int(round(a.mean()))}


def reference(cal: dict[str, Any], tapped_only: bool = True) -> dict[str, Any]:
    if cal.get("format") != "lyric-calibration/1":
        raise ValueError("cần file định dạng lyric-calibration/1 (Lyric Calibrator)")
    lines = []
    for line in cal["lines"]:
        words = [w for w in line["words"] if w.get("start") is not None]
        if not words or (tapped_only and any(w.get("source", "tap") != "tap" for w in words)):
            continue
        lines.append({"text": line.get("text", ""), "start": line.get("start", words[0]["start"]),
                      "end": line.get("end") or words[-1]["end"], "words": words})
    words = [w for line in lines for w in line["words"]]
    if not words:
        raise ValueError("file mốc không có từ nào được gõ tay")
    return {"lines": lines, "words": words, "window": (words[0]["start"], lines[-1]["end"])}


def run_one(args: argparse.Namespace) -> dict[str, Any]:
    """Một model, trong tiến trình riêng: phiên âm đoạn có mốc như job transcribe rồi chấm."""
    from contextcut_ai import media
    from contextcut_ai.analysis import asr, gpu, refine, transcribe, vad

    cal = json.loads(Path(args.calibration).read_text(encoding="utf-8"))
    ref = reference(cal, tapped_only=not args.all_words)
    w0, w1 = ref["window"]
    a0 = max(0.0, w0 - args.pad)
    tmp = Path(args.workdir) / f"eval-{args.one}.wav"
    media.extract_audio(args.audio, args.index, tmp, start_s=a0, end_s=w1 + args.pad)
    audio = transcribe.read_wav(tmp)
    with gpu.VramMonitor() as vram:
        t0 = time.monotonic()
        backend = asr.load(args.one, device=args.device)
        load_s = time.monotonic() - t0
        t1 = time.monotonic()
        chunks = vad.plan_chunks(vad.speech_regions(audio, 16000, args.vad), max_chunk_s=backend.max_chunk_s)
        segs = []
        for a, b in chunks:
            segs += [transcribe.segment_dict(s, a) for s in backend.transcribe(audio[int(a * 16000):int(b * 16000)],
                                                                               args.language, args.prompt)]
        asr_s = time.monotonic() - t1
        backend.close()
    kept = [s for s in segs if not transcribe.is_hallucination(s)]
    refined = copy.deepcopy(kept)
    transcribe.refine_track(refined, refine.envelope(audio, 16000))
    out: dict[str, Any] = {"model": args.one, "device": backend.device, "load_s": round(load_s, 1),
                           "asr_s": round(asr_s, 1), "audio_s": round(len(audio) / 16000, 1), **vram.summary(),
                           "dropped": len(segs) - len(kept)}
    for mode, seg_list in (("raw", kept), ("refined", refined)):
        hyp = [w | {"start": w["start"] + a0, "end": w["end"] + a0} for s in seg_list for w in s["words"]]
        hyp = [w for w in hyp if w0 - 0.5 <= w["start"] <= w1 + 0.5]
        te = timing_errors(ref["words"], hyp)
        le = line_errors(ref["lines"], hyp)
        out[mode] = {"wer": wer([t for w in ref["words"] for t in normalize(w["w"])],
                                [t for w in hyp for t in normalize(w["w"])]),
                     "matched": te["matched"], "ref_words": len(ref["words"]),
                     "word_start": summarize(te["word_start_ms"]), "line_start": summarize(le["line_start_ms"])}
        if args.ends:
            out[mode] |= {"word_end": summarize(te["word_end_ms"]), "line_end": summarize(le["line_end_ms"])}
        out[mode]["text"] = " ".join(w["w"] for w in hyp)[:2000]
    tmp.unlink(missing_ok=True)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--calibration", required=True)
    parser.add_argument("--audio", required=True)
    parser.add_argument("--index", type=int, default=0, help="chỉ số stream audio (ffprobe); WAV = 0")
    parser.add_argument("--models", nargs="+", default=["large-v3", "phowhisper-large", "parakeet-ctc-vi"])
    parser.add_argument("--language", default="vi")
    parser.add_argument("--prompt", default=None)
    parser.add_argument("--vad", default="silero", choices=["silero", "energy"])
    parser.add_argument("--device", default="auto")
    parser.add_argument("--pad", type=float, default=2.0, help="giây audio thêm hai đầu đoạn có mốc")
    parser.add_argument("--ends", action="store_true", help="mốc có cuối từ thật (giữ phím)")
    parser.add_argument("--all-words", action="store_true", help="tính cả từ không phải gõ tay (auto/interp)")
    parser.add_argument("--out", default=None, help="ghi kết quả JSON")
    parser.add_argument("--workdir", default=None)
    parser.add_argument("--one", help=argparse.SUPPRESS)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    args.workdir = args.workdir or str(Path(args.out).parent if args.out else Path.cwd())
    if args.one:
        print("RESULT " + json.dumps(run_one(args), ensure_ascii=False))
        return 0
    results = []
    for model in args.models:
        cmd = [sys.executable, __file__, *sys.argv[1:], "--one", model]
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        line = next((l for l in proc.stdout.splitlines() if l.startswith("RESULT ")), None)
        if not line:
            print(f"{model}: lỗi\n{proc.stderr[-2000:]}")
            results.append({"model": model, "error": proc.stderr[-2000:]})
            continue
        results.append(json.loads(line[7:]))
    keys = ["word_start", "line_start"] + (["word_end", "line_end"] if args.ends else [])
    print("| model | chế độ | WER | khớp | " + " | ".join(f"{k} trung vị/p90 (ms)" for k in keys) + " | ASR s | VRAM đỉnh MiB |")
    print("|" + " --- |" * (6 + len(keys)))
    for r in results:
        if "error" in r:
            continue
        for mode in ("raw", "refined"):
            m = r[mode]
            cells = [f"{m[k]['median']}/{m[k]['p90']} (n={m[k]['n']})" for k in keys]
            print(f"| {r['model']} | {mode} | {m['wer']:.3f} | {m['matched']}/{m['ref_words']} | " + " | ".join(cells)
                  + f" | {r['asr_s']} | {r['vram_peak_mib']} |")
    if args.out:
        Path(args.out).write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
