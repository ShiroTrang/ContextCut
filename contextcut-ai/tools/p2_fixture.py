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


CODE_BITS = 16


def fonts_dir() -> Path | None:
    """Thư mục font Windows có arial.ttf: drawtext của ffmpeg chạy với cwd ở đó (khỏi thoát dấu `:` của ổ đĩa)."""
    d = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    return d if (d / "arial.ttf").exists() else None


def make_frame_code_video(path: Path, fps: int = 60, seconds: float = 4, size: tuple[int, int] = (640, 360),
                          ffmpeg: str | None = None) -> Path:
    """Video kiểm "đúng mốc": nửa trên 16 ô dọc, ô b trắng khi bit b của số frame là 1 (`read_frame_code` đọc lại, kể cả
    ảnh thu nhỏ); nửa dưới là số frame chữ to (để agent đọc bằng mắt). H.264 có B-frame, GOP 2 s như bản ghi OBS."""
    w, h = size
    fonts = fonts_dir()
    vf = (f"geq=lum='if(lt(Y,H/2),if(mod(floor(N/pow(2,floor(X*{CODE_BITS}/W))),2),235,16),16)':cb=128:cr=128")
    if fonts:
        vf += f",drawtext=fontfile=arial.ttf:text='%{{frame_num}}':fontsize={h // 4}:fontcolor=white:x=(w-text_w)/2:y=h*5/8"
    cmd = [ffmpeg or find_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
           "-i", f"color=c=black:s={w}x{h}:r={fps}:d={seconds}", "-vf", vf, "-c:v", "libx264", "-crf", "12",
           "-g", str(2 * fps), "-bf", "2", "-pix_fmt", "yuv420p", str(Path(path).resolve())]
    subprocess.run(cmd, check=True, cwd=fonts)
    return Path(path)


def image_size(image: Path, ffmpeg: str | None = None) -> tuple[int, int]:
    probe = (ffmpeg or find_ffmpeg()).replace("ffmpeg", "ffprobe")
    out = subprocess.run([probe, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                          "-of", "csv=p=0", str(image)], capture_output=True, text=True, check=True).stdout
    w, h = out.strip().split(",")[:2]
    return int(w), int(h)


def read_frame_code(image: Path, crop: tuple[int, int, int, int] | None = None, ffmpeg: str | None = None) -> int:
    """Số frame mã hoá trong ảnh (hoặc vùng `crop` = x, y, w, h của ảnh, vd. một ô contact sheet)."""
    x0, y0, w, h = crop or (0, 0, *image_size(image, ffmpeg))
    raw = subprocess.run([ffmpeg or find_ffmpeg(), "-v", "error", "-i", str(image), "-frames:v", "1",
                          "-vf", f"crop={w}:{h}:{x0}:{y0}", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                         capture_output=True, check=True).stdout
    y = h * 3 // 8  # giữa nửa trên, dưới nhãn của contact sheet
    n = 0
    for bit in range(CODE_BITS):
        if raw[y * w + int((bit + 0.5) * w / CODE_BITS)] > 128:
            n |= 1 << bit
    return n


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
