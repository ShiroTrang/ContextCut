# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
"""Chuẩn bị một đoạn bản ghi để Nhan gõ mốc lời thoại trong Lyric Calibrator (D:\\SongMV) — dữ liệu cho cổng P2a.

    uv run --directory contextcut-ai --no-sync python tools/make_calibration.py --recording <mkv> --index 2
        --start 300 --end 540 [--slug p2a-mic] [--songs D:/SongMV/tools/lyric_calibrator/songs] [--model large-v3]

Cắt đoạn [start, end) của stream audio `index` thành WAV trong thư mục bài của Calibrator, chạy ASR làm bản nháp
`lyrics.txt` (mỗi dòng một câu ngắn) để Nhan sửa chữ trước khi gõ mốc. Thời gian trong file mốc tính từ đầu đoạn cắt;
đo bằng `asr_eval.py --audio <WAV đó> --index 0 --ends`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

SONGS = Path("D:/SongMV/tools/lyric_calibrator/songs")


def draft_lines(segments: list[dict[str, Any]], max_words: int = 12) -> list[str]:
    """Mỗi câu ASR một dòng; câu dài hơn `max_words` chia ở khoảng nghỉ lớn nhất (đệ quy)."""
    def split(words: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
        if len(words) <= max_words:
            return [words]
        gaps = [words[i + 1]["start"] - words[i]["end"] for i in range(len(words) - 1)]
        cut = max(range(len(gaps)), key=lambda i: (gaps[i], -abs(i + 1 - len(words) / 2))) + 1
        return split(words[:cut]) + split(words[cut:])

    lines = []
    for s in segments:
        if not s["words"]:
            continue
        parts = split(s["words"])
        if len(parts) == 1:
            lines.append(s["text"].strip())
        else:
            lines += [" ".join(w["w"] for w in p) for p in parts]
    return [line for line in lines if line]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--recording", required=True)
    parser.add_argument("--index", type=int, required=True, help="stream audio (ffprobe), vd. 2 = Mic của OBS")
    parser.add_argument("--start", type=float, required=True)
    parser.add_argument("--end", type=float, required=True)
    parser.add_argument("--slug", default="p2a-mic")
    parser.add_argument("--songs", type=Path, default=SONGS)
    parser.add_argument("--model", default=None)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    import subprocess

    from contextcut_ai import paths
    from contextcut_ai.analysis import asr, transcribe, vad

    folder = args.songs / args.slug
    (folder / "versions").mkdir(parents=True, exist_ok=True)
    wav = folder / "audio.wav"
    # 48 kHz để nghe rõ khi gõ; asr_eval tự đổi sang 16 kHz
    subprocess.run([paths.find_tool("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{args.start:.3f}",
                    "-to", f"{args.end:.3f}", "-i", args.recording, "-map", f"0:{args.index}", "-vn", "-ac", "1",
                    "-ar", "48000", "-c:a", "pcm_s16le", str(wav)], check=True)
    tmp16 = folder / "audio16k.wav"
    from contextcut_ai import media
    media.extract_audio(wav, 0, tmp16)
    audio = transcribe.read_wav(tmp16)
    tmp16.unlink()
    backend = asr.load(args.model)
    segs = []
    for a, b in vad.plan_chunks(vad.speech_regions(audio), max_chunk_s=backend.max_chunk_s):
        segs += [transcribe.segment_dict(s, a) for s in backend.transcribe(audio[int(a * 16000):int(b * 16000)], "vi", None)]
    backend.close()
    lines = draft_lines([s for s in segs if not transcribe.is_hallucination(s)])
    (folder / "lyrics.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (folder / "peaks.json").unlink(missing_ok=True)
    song = {"title": f"P2a {Path(args.recording).name} stream {args.index} {args.start:.0f}-{args.end:.0f}s",
            "artist": "ContextCut", "audio": str(wav.resolve()),
            "audio_sha256": hashlib.sha256(wav.read_bytes()).hexdigest(),
            "contextcut": {"recording": args.recording, "index": args.index, "start_s": args.start, "end_s": args.end,
                           "draft_model": backend.name}}
    (folder / "song.json").write_text(json.dumps(song, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Đã tạo bài '{args.slug}': {len(lines)} dòng nháp, {sum(len(l.split()) for l in lines)} từ\n"
          f"  audio  {wav}\n  lời    {folder / 'lyrics.txt'}\n\n"
          "Việc của Nhan:\n"
          "  1. Mở lyrics.txt, nghe đoạn audio và sửa chữ cho đúng lời thật (mỗi dòng một câu ngắn, ngắt ở chỗ nghỉ).\n"
          "  2. Mở D:\\SongMV\\Mo_Lyric_Calibrator.bat, chọn bài, bấm Đo trễ, bật 'Giữ phím = độ dài chữ'.\n"
          "  3. Enter để phát, giữ Space trong lúc mỗi chữ được nói, nhả khi hết chữ. Lưu bản (Ctrl+S).\n"
          f"  4. Báo lại tên bản đã lưu (songs/{args.slug}/versions/<tên>.json).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
