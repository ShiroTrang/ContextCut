# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
"""Đọc file media bằng ffprobe/ffmpeg (chỉ đọc bản ghi, không bao giờ ghi cạnh nó)."""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .paths import find_tool

HASH_BLOCK = 1 << 20
# Cửa sổ console của ffmpeg không được bật lên khi MCP server/worker chạy nền
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


@dataclass(frozen=True)
class AudioStream:
    index: int  # chỉ số stream tuyệt đối (ffprobe = MLT, đếm cả stream hình)
    title: str | None
    channels: int
    sample_rate: int
    codec: str


@dataclass(frozen=True)
class Probe:
    duration_s: float
    has_video: bool
    streams: list[AudioStream]


def probe(path: str | Path) -> Probe:
    out = subprocess.run([find_tool("ffprobe"), "-v", "error", "-print_format", "json", "-show_format", "-show_streams",
                          str(path)], capture_output=True, check=True, creationflags=NO_WINDOW).stdout
    info = json.loads(out.decode("utf-8"))
    audio = []
    for s in info.get("streams", []):
        if s.get("codec_type") != "audio":
            continue
        tags = {k.lower(): v for k, v in (s.get("tags") or {}).items()}
        audio.append(AudioStream(index=int(s["index"]), title=tags.get("title") or tags.get("handler_name"),
                                 channels=int(s.get("channels") or 0), sample_rate=int(s.get("sample_rate") or 0),
                                 codec=s.get("codec_name") or ""))
    has_video = any(s.get("codec_type") == "video" and not (s.get("disposition") or {}).get("attached_pic")
                    for s in info.get("streams", []))
    return Probe(duration_s=float((info.get("format") or {}).get("duration") or 0), has_video=has_video, streams=audio)


def fast_hash(path: str | Path) -> str:
    """sha1 của kích thước + 1 MiB đầu + 1 MiB cuối: đủ phân biệt bản ghi, đọc nhanh cả file 20 GB."""
    p = Path(path)
    size = p.stat().st_size
    h = hashlib.sha1(str(size).encode())
    with p.open("rb") as f:
        h.update(f.read(HASH_BLOCK))
        if size > HASH_BLOCK:
            f.seek(max(HASH_BLOCK, size - HASH_BLOCK))
            h.update(f.read(HASH_BLOCK))
    return h.hexdigest()[:16]


def extract_audio(path: str | Path, index: int, out_wav: str | Path, start_s: float | None = None,
                  end_s: float | None = None) -> Path:
    """Stream audio `index` → WAV mono 16 kHz s16 (đầu vào của ASR)."""
    cmd = [find_tool("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-nostdin"]
    if start_s is not None:
        cmd += ["-ss", f"{start_s:.3f}"]
    if end_s is not None:
        cmd += ["-to", f"{end_s:.3f}"]
    cmd += ["-i", str(path), "-map", f"0:{index}", "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(out_wav)]
    subprocess.run(cmd, check=True, capture_output=True, creationflags=NO_WINDOW)
    return Path(out_wav)
