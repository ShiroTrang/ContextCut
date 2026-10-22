# /// script
# requires-python = ">=3.11"
# ///
# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
"""Dữ liệu thử cho P2a: bản ghi OBS giả 5 stream audio có tên (sơ đồ track design §8.1).

    uv run contextcut-ai/tools/p2_fixture.py --out <thư mục trống>

`make_obs_mkv()` cũng được test dùng trực tiếp.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OBS_TITLES = ("Track1", "Track2", "Track3", "Track4", "Track5")


def find_ffmpeg() -> str:
    """ffmpeg của MSYS2 dự án nếu có, không thì trên PATH."""
    msys2 = Path(os.environ.get("CONTEXTCUT_MSYS2") or REPO.parent / "env" / "msys64")
    exe = msys2 / "ucrt64" / "bin" / "ffmpeg.exe"
    if exe.exists():
        return str(exe)
    found = shutil.which("ffmpeg")
    if not found:
        raise FileNotFoundError("không thấy ffmpeg (MSYS2 hoặc PATH)")
    return found


def make_obs_mkv(path: Path, seconds: float = 8, titles: Sequence[str] = OBS_TITLES, ffmpeg: str | None = None) -> Path:
    """MKV 320×180 30 fps + một stream audio mỗi tên trong `titles` (sine 300, 400… Hz; stream 1 stereo, còn lại mono)."""
    cmd = [ffmpeg or find_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
           "-f", "lavfi", "-i", f"testsrc2=size=320x180:rate=30:duration={seconds}"]
    for i, _ in enumerate(titles):
        cmd += ["-f", "lavfi", "-i", f"sine=frequency={300 + 100 * i}:duration={seconds}:sample_rate=48000"]
    cmd += ["-map", "0:v"]
    for i, title in enumerate(titles):
        cmd += ["-map", f"{i + 1}:a", f"-ac:a:{i}", "2" if i == 0 else "1", f"-metadata:s:a:{i}", f"title={title}"]
    cmd += ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", str(path)]
    subprocess.run(cmd, check=True)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", required=True, type=Path, help="thư mục đích (tạo nếu chưa có, phải trống)")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    out: Path = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if any(out.iterdir()):
        print(f"{out} không trống", file=sys.stderr)
        return 2
    mkv = make_obs_mkv(out / "Ông Sang câu cá 2026-10-22 21-00-00.mkv", titles=("Mix", "Mic", "Discord", "Game", "Desktop"))
    print(mkv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
