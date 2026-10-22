# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
"""Pipeline phiên âm với backend giả: chunk, chạy tiếp, ghép track, lọc ảo giác, tinh chỉnh ranh giới."""
import json
import subprocess
import sys
import wave
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from p2_fixture import find_ffmpeg  # noqa: E402

from contextcut_ai.analysis import refine, transcribe, vad  # noqa: E402
from contextcut_ai.analysis.asr import Segment, Word  # noqa: E402

SR = 16000


def tone_track(bursts: list[tuple[float, float]], seconds: float, freq: float = 300.0) -> np.ndarray:
    rng = np.random.default_rng(1)
    audio = rng.normal(0, 0.001, int(seconds * SR)).astype(np.float32)
    for a, b in bursts:
        t = np.arange(int(a * SR), int(b * SR)) / SR
        audio[int(a * SR):int(a * SR) + len(t)] += 0.3 * np.sin(2 * np.pi * freq * t)
    return audio


def write_wav(path: Path, audio: np.ndarray) -> Path:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())
    return path


def mux(out: Path, *wavs: Path) -> Path:
    cmd = [find_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y"]
    for w in wavs:
        cmd += ["-i", str(w)]
    for i in range(len(wavs)):
        cmd += ["-map", f"{i}:a"]
    subprocess.run(cmd + ["-c:a", "pcm_s16le", str(out)], check=True)
    return out


class FakeBackend:
    """Mỗi chunk: một câu "xin chào bạn" phủ từng đoạn có tiếng (biết trước từ test), hoặc câu định sẵn."""

    name, device, max_chunk_s = "fake", "cpu", 300.0

    def __init__(self, script=None, fail_on_call: int | None = None):
        self.calls: list[int] = []  # số mẫu audio mỗi lần gọi
        self.script = script
        self.fail_on_call = fail_on_call

    def transcribe(self, audio, language, prompt):
        self.calls.append(len(audio))
        if self.fail_on_call is not None and len(self.calls) == self.fail_on_call:
            raise RuntimeError("giả lập worker chết")
        if self.script:
            return self.script(audio)
        regions = vad.energy_regions(audio, SR)
        out = []
        for a, b in regions:
            # Whisper hay kéo từ đầu sớm và từ cuối dài vào khoảng lặng: lệch 0,2 s để tinh chỉnh có việc làm
            a2, b2 = max(0.0, a - 0.2), b + 0.25
            mid = (a2 + b2) / 2
            out.append(Segment(a2, b2, "xin chào bạn", [Word("xin", a2, mid, 0.9), Word("chào", mid, b - 0.05, 0.3),
                                                         Word("bạn", b - 0.05, b2, 0.95)], -0.2, 0.01))
        return out

    def close(self):
        pass


def params(tmp_path: Path, rec: Path, tracks, model="fake"):
    return {"recording": {"id": "4", "path": rec.as_posix(), "file_hash": "abcd1234abcd1234"},
            "companion": (tmp_path / "P.contextcut").as_posix(), "tracks": tracks, "language": "vi",
            "model": model, "allow_download": False, "prompt": None, "vad": "energy"}  # Silero bỏ qua tiếng sine


def no_report(*a, **k):
    pass


def load_transcript(tmp_path: Path) -> dict:
    return json.loads((tmp_path / "P.contextcut" / "analysis" / "abcd1234abcd1234" / "transcript.json")
                      .read_text(encoding="utf-8"))


def test_plan_chunks_cuts_at_longest_silence():
    regions = [(0.0, 100.0), (110.0, 200.0), (260.0, 350.0), (355.0, 500.0)]
    chunks = vad.plan_chunks(regions, max_chunk_s=300, pad_s=0.4)
    assert chunks == [(0.0, 200.4), (259.6, 500.4)]


def test_plan_chunks_hard_splits_long_region():
    chunks = vad.plan_chunks([(10.0, 710.0)], max_chunk_s=300, pad_s=0.0)
    assert len(chunks) == 3 and chunks[0][0] == 10.0 and chunks[-1][1] == 710.0
    assert all(b - a <= 300 for a, b in chunks)


def test_refine_snaps_to_tone_onset():
    audio = tone_track([(1.0, 1.8)], 3.0)
    env = refine.envelope(audio, SR)
    start, end = refine.refine_edges(env, 0.75, 2.05)  # ASR lệch 250 ms mỗi đầu
    assert abs(start - 1.0) <= 0.02 and abs(end - 1.8) <= 0.02


def test_refine_keeps_raw_when_no_edge_nearby():
    audio = tone_track([(0.0, 3.0)], 3.0)  # tiếng liên tục: không có ranh giới trong cửa sổ
    env = refine.envelope(audio, SR)
    assert refine.refine_edges(env, 1.2, 2.0) == (1.2, 2.0)


def test_offsets_and_speakers_merged(tmp_path):
    mic = write_wav(tmp_path / "mic.wav", tone_track([(1.0, 2.0), (6.0, 7.5)], 10))
    discord = write_wav(tmp_path / "discord.wav", tone_track([(3.0, 4.5)], 10, freq=500))
    rec = mux(tmp_path / "Bắt Nạt Hải Sản.mkv", mic, discord)
    backend = FakeBackend()
    result = transcribe.run(params(tmp_path, rec, [{"index": 0, "role": "mic", "speaker": "Nhan"},
                                                   {"index": 1, "role": "discord", "speaker": "bạn bè"}]),
                            no_report, load_backend=lambda *a, **k: backend)
    tr = load_transcript(tmp_path)
    assert tr["schema"] == "contextcut-transcript/1" and tr["model"] == "fake" and tr["language"] == "vi"
    assert [(s["speaker"], s["track"]) for s in tr["segments"]] == [("Nhan", 0), ("bạn bè", 1), ("Nhan", 0)]
    starts = [s["start"] for s in tr["segments"]]
    assert starts == sorted(starts)
    first = tr["segments"][0]
    assert abs(first["start"] - 1.0) <= 0.03 and abs(first["end"] - 2.0) <= 0.03  # đã tinh chỉnh theo năng lượng
    assert first["words"][0]["raw_start"] == pytest.approx(0.8, abs=0.02)
    assert first["words"][1]["p"] == 0.3 and "low_conf" in first["flags"]
    assert [t["index"] for t in tr["tracks"]] == [0, 1]
    assert result["segments"] == 3 and result["transcript"].endswith("transcript.json")
    assert not list((tmp_path / "P.contextcut").rglob("*.wav"))  # WAV tạm đã xoá


def test_chunks_resume_after_crash(tmp_path):
    bursts = [(1.0, 2.0), (40.0, 41.0), (80.0, 81.0)]
    rec = write_wav(tmp_path / "mic.wav", tone_track(bursts, 90))
    p = params(tmp_path, rec, [{"index": 0, "role": "mic", "speaker": "Nhan"}])
    small = FakeBackend(fail_on_call=2)
    small.max_chunk_s = 30.0  # ba chunk
    with pytest.raises(RuntimeError):
        transcribe.run(p, no_report, load_backend=lambda *a, **k: small)
    chunk_files = sorted((tmp_path / "P.contextcut").rglob("chunk-*.json"))
    assert [f.name for f in chunk_files] == ["chunk-0000.json"]
    again = FakeBackend()
    again.max_chunk_s = 30.0
    transcribe.run(p, no_report, load_backend=lambda *a, **k: again)
    assert len(again.calls) == 2  # chỉ chunk 1 và 2
    assert len(load_transcript(tmp_path)["segments"]) == 3


def test_hallucination_dropped(tmp_path):
    rec = write_wav(tmp_path / "mic.wav", tone_track([(1.0, 2.0)], 6))

    def script(audio):
        return [Segment(0.9, 2.0, "Ủa alo", [Word("Ủa", 0.9, 1.4, 0.9), Word("alo", 1.4, 2.0, 0.9)], -0.3, 0.02),
                Segment(3.0, 5.5, "Hãy subscribe cho kênh Ghiền Mì Gõ Để không bỏ lỡ những video hấp dẫn",
                        [Word("Hãy", 3.0, 3.5, 0.5)], -0.4, 0.1),
                Segment(5.5, 5.9, "ừm", [Word("ừm", 5.5, 5.9, 0.2)], -1.5, 0.9)]

    transcribe.run(params(tmp_path, rec, [{"index": 0, "role": "mic", "speaker": "Nhan"}]), no_report,
                   load_backend=lambda *a, **k: FakeBackend(script=script))
    assert [s["text"] for s in load_transcript(tmp_path)["segments"]] == ["Ủa alo"]


def test_impossibly_fast_segment_dropped():
    # PhoWhisper trên tiếng Discord ngắt quãng (Gaming.mkv 17:27): 13 âm tiết trong 0,58 s, no_speech_prob ≈ 0
    words = "những thông tin tiếp theo sẽ được đăng tải trong phần tiếp theo".split()
    fake = {"start": 1047.124, "end": 1047.704, "text": " ".join(words) + ".", "avg_logprob": -0.39,
            "no_speech_prob": 2e-06, "words": [{"w": w, "start": 1047.124, "end": 1047.704, "p": 0.6} for w in words]}
    fast_talk = {"start": 10.0, "end": 11.0, "text": "ê mày ơi chạy đi nhanh lên", "avg_logprob": -0.3,
                 "no_speech_prob": 0.0, "words": []}
    assert transcribe.is_hallucination(fake)
    assert not transcribe.is_hallucination(fast_talk)  # 7 âm tiết/giây: nói nhanh thật vẫn giữ


def test_unk_token_removed():
    seg = {"start": 0.0, "end": 3.0, "text": "unk mà không vướng <unk> bận", "words": [
        {"w": "unk", "start": 0.0, "end": 0.2, "p": 0.1}, {"w": "mà", "start": 0.3, "end": 0.5, "p": 0.9},
        {"w": "không", "start": 0.5, "end": 0.8, "p": 0.9}, {"w": "vướng", "start": 0.8, "end": 1.1, "p": 0.9},
        {"w": "<unk>", "start": 1.1, "end": 1.2, "p": 0.1}, {"w": "bận", "start": 1.2, "end": 1.5, "p": 0.9}]}
    out = transcribe.strip_unk(seg)
    assert out["text"] == "mà không vướng bận"
    assert [w["w"] for w in out["words"]] == ["mà", "không", "vướng", "bận"]


def test_single_mix_track_speaker_null(tmp_path):
    rec = write_wav(tmp_path / "mix.wav", tone_track([(1.0, 2.0)], 4))
    transcribe.run(params(tmp_path, rec, [{"index": 0, "role": "mix", "speaker": None}]), no_report,
                   load_backend=lambda *a, **k: FakeBackend())
    [seg] = load_transcript(tmp_path)["segments"]
    assert seg["speaker"] is None and seg["track"] == 0


def test_rerun_one_track_keeps_other_tracks(tmp_path):
    mic = write_wav(tmp_path / "mic.wav", tone_track([(1.0, 2.0)], 5))
    discord = write_wav(tmp_path / "discord.wav", tone_track([(3.0, 4.0)], 5, freq=500))
    rec = mux(tmp_path / "rec.mkv", mic, discord)
    both = [{"index": 0, "role": "mic", "speaker": "Nhan"}, {"index": 1, "role": "discord", "speaker": "bạn bè"}]
    transcribe.run(params(tmp_path, rec, both), no_report, load_backend=lambda *a, **k: FakeBackend())
    transcribe.run(params(tmp_path, rec, [{"index": 1, "role": "discord", "speaker": "Sang"}]), no_report,
                   load_backend=lambda *a, **k: FakeBackend())
    assert [s["speaker"] for s in load_transcript(tmp_path)["segments"]] == ["Nhan", "Sang"]
