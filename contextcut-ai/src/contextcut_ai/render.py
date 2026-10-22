# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
"""Khung hình timeline đã dựng, bằng melt trên XML scene của app (cùng engine, cùng hiệu ứng với file xuất).

Một tiến trình melt cho mọi frame: XML bọc nạp scene một lần (producer `xml`) rồi phát một playlist mỗi frame một
mục `in = out = f`. Chạy trong worker của job (`render_frames`), không cần khoá GPU (melt giải mã bằng CPU).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from collections.abc import Callable
from fractions import Fraction
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape, quoteattr

from .media import NO_WINDOW
from .paths import find_tool

# Plugin Waves trên máy Nhan làm MLT treo/crash khi nạp jackrack/ladspa (CLAUDE.md)
MLT_DENY = "libmltjackrack:libmltladspa"
TIMEOUT_S = 600


def wrapper_xml(scene: Path, frames: list[int], profile: dict[str, Any]) -> str:
    """XML MLT phát các frame (tăng dần, không trùng) của `scene`, mỗi frame một mục playlist dài 1 frame."""
    w, h = int(profile["width"]), int(profile["height"])
    dar = Fraction(w, h)
    fps = profile["fps"]
    entries = "\n".join(f'    <entry producer="scene" in="{f}" out="{f}"/>' for f in sorted(set(frames)))
    return (f'<?xml version="1.0" encoding="utf-8"?>\n'
            f'<mlt LC_NUMERIC="C" producer="frames">\n'
            f'  <profile width="{w}" height="{h}" frame_rate_num="{fps["num"]}" frame_rate_den="{fps["den"]}" '
            f'sample_aspect_num="1" sample_aspect_den="1" display_aspect_num="{dar.numerator}" '
            f'display_aspect_den="{dar.denominator}" progressive="1" colorspace="709"/>\n'
            f'  <producer id="scene">\n'
            f'    <property name="mlt_service">xml</property>\n'
            f'    <property name="resource">{escape(Path(scene).as_posix())}</property>\n'
            f'  </producer>\n'
            f'  <playlist id="frames">\n{entries}\n  </playlist>\n'
            f'</mlt>\n')


def _profile_of(scene: Path) -> dict[str, Any]:
    """Profile ghi trong scene (app luôn ghi `<profile>`; scene melt tự dựng cũng vậy)."""
    import xml.etree.ElementTree as ET
    node = ET.parse(scene).getroot().find("profile")
    if node is None:
        raise RuntimeError(f"scene {scene} không có <profile>")
    return {"width": node.get("width"), "height": node.get("height"),
            "fps": {"num": node.get("frame_rate_num"), "den": node.get("frame_rate_den")}}


def run_frames(params: dict[str, Any], report: Callable[..., None]) -> dict[str, Any]:
    """Job `render_frames`: params `{scene, frames, width, height, out_dir}` → ảnh `out_dir/<f>-<width>.jpg`."""
    scene, out_dir = Path(params["scene"]), Path(params["out_dir"])
    frames = sorted(set(int(f) for f in params["frames"]))
    width, height = int(params["width"]), int(params["height"])
    start = time.monotonic()
    report("chuẩn bị melt", progress=0.05)
    out_dir.mkdir(parents=True, exist_ok=True)
    work = out_dir / f"melt-{os.getpid()}"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir()
    (work / "frames.mlt").write_text(wrapper_xml(scene, frames, _profile_of(scene)), encoding="utf-8")
    # Đối số của melt chỉ ASCII (cwd = thư mục làm việc): argv của melt trên Windows không giữ được chữ có dấu.
    # melt dựng ở cỡ profile như khi xuất, ffmpeg thu nhỏ sau: consumer có width/height thì transition qtblend của
    # Kdenlive chừa viền đen khi nguồn lớn hơn profile, và thiếu progressive=1 thì melt crash (22/10).
    cmd = [find_tool("melt"), "-quiet", "frames.mlt", "-consumer", "avformat:%04d.jpg", "vcodec=mjpeg", "qscale=2",
           "an=1", "real_time=-1", "progressive=1"]
    report(f"melt dựng {len(frames)} khung hình", progress=0.1)
    run = subprocess.run(cmd, cwd=work, env=os.environ | {"MLT_REPOSITORY_DENY": MLT_DENY}, capture_output=True,
                         timeout=TIMEOUT_S, creationflags=NO_WINDOW)
    made = sorted(work.glob("[0-9][0-9][0-9][0-9].jpg"))
    if run.returncode != 0 or len(made) != len(frames):
        tail = run.stderr.decode("utf-8", "replace").strip().splitlines()[-3:]
        shutil.rmtree(work, ignore_errors=True)
        raise RuntimeError(f"melt dừng với mã {run.returncode}, ra {len(made)}/{len(frames)} ảnh: {' | '.join(tail)}")
    report("thu nhỏ ảnh", progress=0.9)
    subprocess.run([find_tool("ffmpeg"), "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-start_number", "1",
                    "-i", "%04d.jpg", "-vf", f"scale={width}:{height}", "-q:v", "3", "small-%04d.jpg"], cwd=work,
                   check=True, capture_output=True, creationflags=NO_WINDOW)
    made = sorted(work.glob("small-[0-9][0-9][0-9][0-9].jpg"))
    out = []
    for f, image in zip(frames, made):
        target = out_dir / f"{f}-{width}.jpg"
        os.replace(image, target)
        out.append({"f": f, "path": target.as_posix()})
    shutil.rmtree(work, ignore_errors=True)
    report("xong", progress=1.0)
    return {"frames": out, "elapsed_s": round(time.monotonic() - start, 2)}
