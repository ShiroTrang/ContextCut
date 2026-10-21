# /// script
# requires-python = ">=3.11"
# ///
# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
"""Dựng project thử cho cổng P1 (tests/test_live_ops.py chỉ sửa project tên `p1-gate`).

    uv run contextcut-ai/tools/p1_fixture.py --out <thư mục trống>

Chép `tests/dataset/clip-ids.kdenlive` thành `p1-gate.kdenlive` (4 file .mpg, 16 clip trên V2/V1/A1/A2, 25 fps)
kèm `stereo.flac`, tạo bản ghi OBS giả 3 stream audio bằng ffmpeg của MSYS2, rồi in lệnh mở app.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DATASET = REPO / "tests" / "dataset"
OBS_NAME = "Ông Sang câu cá 2026-10-22.mkv"


def msys2_root() -> Path:
    return Path(os.environ.get("CONTEXTCUT_MSYS2") or REPO.parent / "env" / "msys64")


def make_obs(ffmpeg: Path, out: Path) -> None:
    """640×360, 30 fps, 6 s; stream audio 1 trộn chung, 2 mic, 3 Discord như sơ đồ OBS khuyến nghị."""
    cmd = [str(ffmpeg), "-hide_banner", "-loglevel", "error", "-y",
           "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30:duration=6",
           "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
           "-f", "lavfi", "-i", "sine=frequency=660:duration=6",
           "-f", "lavfi", "-i", "sine=frequency=880:duration=6",
           "-map", "0:v", "-map", "1:a", "-map", "2:a", "-map", "3:a",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(out)]
    subprocess.run(cmd, check=True)


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
    ffmpeg = msys2_root() / "ucrt64" / "bin" / "ffmpeg.exe"
    if not ffmpeg.exists():
        print(f"không thấy {ffmpeg} (đặt CONTEXTCUT_MSYS2)", file=sys.stderr)
        return 2
    shutil.copyfile(DATASET / "clip-ids.kdenlive", out / "p1-gate.kdenlive")
    for name in ("blue.mpg", "green.mpg", "red.mpg", "yellow.mpg", "stereo.flac"):
        shutil.copyfile(DATASET / name, out / name)
    make_obs(ffmpeg, out / OBS_NAME)
    exe = REPO / "stage" / "bin" / "contextcut.exe"
    dlls = msys2_root() / "ucrt64" / "bin"
    print("Mở app (PowerShell; ucrt64\\bin lên đầu PATH như packaging\\run.ps1):")
    # -i nhận một danh sách phân cách bằng dấu phẩy (lặp lại -i thì chỉ lần cuối có tác dụng)
    print(f'  $env:PATH = "{dlls};$env:PATH"; & "{exe}" --no-welcome -i "{out / OBS_NAME},{out / "stereo.flac"}" '
          f'"{out / "p1-gate.kdenlive"}"')
    return 0


if __name__ == "__main__":
    sys.exit(main())
