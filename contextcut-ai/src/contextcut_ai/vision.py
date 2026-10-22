# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
"""Ảnh cho agent xem: khung hình bản ghi gốc bằng ffmpeg (đúng frame MLT sẽ hiện), contact sheet, chỗ cache ảnh.

Chỉ cần ffmpeg, không thư viện ảnh: ghép lưới bằng `xstack`, nhãn bằng `drawtext`. Ảnh JPEG nhỏ để tốn ít token.
"""

from __future__ import annotations

import math
import os
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from fractions import Fraction
from pathlib import Path

from .media import NO_WINDOW
from .paths import data_dir, find_tool

PARALLEL = 4
JPEG_QUALITY = "3"  # -q:v của mjpeg: 2 đẹp nhất … 31; 3 ≈ 30–40 KB cho 512×288


class FrameError(Exception):
    """Không lấy được một frame (quá cuối bản ghi, file hỏng…); trả trong kết quả thay vì ném."""


def source_index(f: int, project_fps: Fraction | float, source_fps: Fraction | float) -> int:
    """Frame nguồn MLT hiện ở frame `f` (đếm theo fps project) của bản ghi: làm tròn như avformat của MLT."""
    return math.floor(Fraction(f) * Fraction(source_fps) / Fraction(project_fps) + Fraction(1, 2))


def even_frames(start_f: int, end_f: int, count: int) -> list[int]:
    """`count` frame rải đều trong [start_f, end_f), mỗi frame ở giữa một phần; khoảng ngắn thì ít frame hơn."""
    span = end_f - start_f
    picked = [start_f + int((i + 0.5) * span / count) for i in range(count)]
    return sorted(set(f for f in picked if start_f <= f < end_f))


def frames_root(companion: Path | None) -> Path:
    """Gốc cache ảnh: thư mục `<project>.contextcut/`, project chưa lưu thì `%LOCALAPPDATA%\\contextcut\\frames`."""
    return Path(companion) if companion else data_dir() / "frames"


def prune(directory: Path, keep: int) -> None:
    """Giữ `keep` mục mới nhất (file hoặc thư mục) trong `directory`, xoá phần còn lại."""
    if not directory.is_dir():
        return
    entries = sorted(directory.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in entries[keep:]:
        if old.is_dir():
            shutil.rmtree(old, ignore_errors=True)
        else:
            old.unlink(missing_ok=True)


def _extract_one(ffmpeg: str, path: Path, s: int, fps: Fraction, width: int, out: Path) -> Path | FrameError:
    if out.exists() and out.stat().st_size > 0:
        return out
    tmp = out.with_name(f"{out.stem}.tmp{os.getpid()}.jpg")
    # Seek tới nửa frame trước frame s: ffmpeg bỏ mọi frame có pts < mốc seek, frame đầu còn lại là s
    seek = max(Fraction(0), (s - Fraction(1, 2)) / fps)
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-ss", f"{float(seek):.6f}", "-i", str(path),
           "-map", "0:v:0", "-frames:v", "1", "-vf", f"scale={width}:-2", "-q:v", JPEG_QUALITY, str(tmp)]
    run = subprocess.run(cmd, capture_output=True, creationflags=NO_WINDOW)
    if run.returncode != 0 or not tmp.exists() or tmp.stat().st_size == 0:
        tmp.unlink(missing_ok=True)
        detail = run.stderr.decode("utf-8", "replace").strip().splitlines()[-1:] or ["không có frame nào"]
        return FrameError(f"không lấy được frame nguồn {s} ({float(s / fps):.2f} s): {detail[0]}")
    os.replace(tmp, out)
    return out


def extract_frames(path: str | Path, indices: list[int], source_fps: Fraction, width: int,
                   out: Path) -> dict[int, Path | FrameError]:
    """Frame nguồn `indices` (chỉ số frame của bản ghi) → `out/<s>-<width>.jpg` (rộng `width`, cao theo tỉ lệ).
    Ảnh đã có thì dùng lại; chạy song song tối đa 4 ffmpeg; frame lỗi trả `FrameError`."""
    out.mkdir(parents=True, exist_ok=True)
    ffmpeg = find_tool("ffmpeg")
    wanted = sorted(set(indices))
    with ThreadPoolExecutor(PARALLEL) as pool:
        results = pool.map(lambda s: _extract_one(ffmpeg, Path(path), s, Fraction(source_fps), width,
                                                  out / f"{s}-{width}.jpg"), wanted)
        return dict(zip(wanted, results))


def _drawtext_value(text: str) -> str:
    return text.replace("\\", "\\\\").replace("'", "").replace(":", "\\:").replace("%", "\\%")


def contact_sheet(tiles: list[tuple[Path | None, str]], cols: int, tile_w: int, out: Path) -> Path:
    """Ghép các ảnh thành lưới `cols` cột (hàng ngang trước), mỗi ô `tile_w` × `tile_w·9/16`, nhãn ở góc trái trên.
    Ô `None` (frame lỗi) là ô đen kèm nhãn."""
    tile_h = round(tile_w * 9 / 16 / 2) * 2
    rows = math.ceil(len(tiles) / cols)
    fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    label = (fonts / "arial.ttf").exists()
    cmd = [find_tool("ffmpeg"), "-hide_banner", "-loglevel", "error", "-nostdin", "-y"]
    graph, layout = [], []
    for i in range(rows * cols):
        path, text = tiles[i] if i < len(tiles) else (None, "")
        if path is None:
            cmd += ["-f", "lavfi", "-i", f"color=c=black:s={tile_w}x{tile_h}:d=1"]
        else:
            cmd += ["-i", str(Path(path).resolve())]
        chain = (f"[{i}:v]scale={tile_w}:{tile_h}:force_original_aspect_ratio=decrease,"
                 f"pad={tile_w}:{tile_h}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p")
        if label and text:
            chain += (f",drawtext=fontfile=arial.ttf:text='{_drawtext_value(text)}':x=4:y=4:fontsize={max(12, tile_h // 8)}"
                      ":fontcolor=white:box=1:boxcolor=black@0.6:boxborderw=3")
        graph.append(chain + f"[t{i}]")
        layout.append(f"{(i % cols) * tile_w}_{(i // cols) * tile_h}")
    graph.append("".join(f"[t{i}]" for i in range(rows * cols)) + f"xstack=inputs={rows * cols}:layout={'|'.join(layout)}")
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(f"{out.stem}.tmp{os.getpid()}.jpg")
    cmd += ["-filter_complex", ";".join(graph), "-frames:v", "1", "-q:v", JPEG_QUALITY, str(tmp.resolve())]
    subprocess.run(cmd, check=True, capture_output=True, creationflags=NO_WINDOW, cwd=fonts if label else None)
    os.replace(tmp, out)
    return out
