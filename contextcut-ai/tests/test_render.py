# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
"""P2b Task 16: render_frames dựng khung hình timeline bằng melt trên XML scene (một tiến trình cho nhiều frame)."""

import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from p2_fixture import image_size, make_frame_code_video, read_frame_code  # noqa: E402

from contextcut_ai import paths, render  # noqa: E402

PROFILE_25 = {"fps": {"num": 25, "den": 1}, "width": 1280, "height": 720}


def melt_scene(video: Path, out: Path) -> Path:
    """Scene MLT 720p 25 fps chỉ có video mã số frame (giống XML app trả về: melt đọc được trực tiếp)."""
    env = os.environ | {"MLT_REPOSITORY_DENY": render.MLT_DENY}
    subprocess.run([paths.find_tool("melt"), "-quiet", "-profile", "atsc_720p_25", str(video), "-consumer",
                    f"xml:{out}"], check=True, env=env, capture_output=True)
    return out


@pytest.fixture(scope="module")
def scene(tmp_path_factory) -> Path:
    try:
        paths.find_tool("melt")
    except paths.ToolMissing:
        pytest.skip("cần melt (MSYS2 của dự án)")
    d = tmp_path_factory.mktemp("scene")
    return melt_scene(make_frame_code_video(d / "code60.mp4", fps=60, seconds=4), d / "scene.mlt")


def test_wrapper_xml_sorted_unique(tmp_path):
    scene = tmp_path / "Bắt Nạt & <Hải Sản>" / "scene.mlt"
    root = ET.fromstring(render.wrapper_xml(scene, [90, 3, 40, 3], PROFILE_25))
    assert root.tag == "mlt" and root.get("producer") == "frames"
    profile = root.find("profile")
    assert (profile.get("width"), profile.get("height"), profile.get("frame_rate_num"), profile.get("frame_rate_den")) == \
        ("1280", "720", "25", "1")
    assert (profile.get("display_aspect_num"), profile.get("display_aspect_den")) == ("16", "9")
    producer = root.find("producer")
    props = {p.get("name"): p.text for p in producer.findall("property")}
    assert props == {"mlt_service": "xml", "resource": scene.as_posix()}
    entries = root.find("playlist").findall("entry")
    assert [(e.get("producer"), e.get("in"), e.get("out")) for e in entries] == \
        [("scene", "3", "3"), ("scene", "40", "40"), ("scene", "90", "90")]


def run(scene: Path, frames: list[int], out: Path, width: int = 320) -> dict:
    stages = []
    result = render.run_frames({"scene": str(scene), "frames": frames, "width": width, "height": width * 9 // 16,
                                "out_dir": str(out)}, lambda stage, progress=None, eta_s=None: stages.append(stage))
    assert stages
    return result


def test_run_frames_melt_exact(scene, tmp_path):
    result = run(scene, [90, 3, 40], tmp_path / "out")
    got = {item["f"]: Path(item["path"]) for item in result["frames"]}
    assert sorted(got) == [3, 40, 90]
    for f, code in ((3, 7), (40, 96), (90, 216)):  # floor(f·60/25 + 0.5)
        assert got[f].name == f"{f}-320.jpg" and image_size(got[f]) == (320, 180)
        assert read_frame_code(got[f]) == code, f
    assert result["elapsed_s"] >= 0
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == ["3-320.jpg", "40-320.jpg", "90-320.jpg"]


def test_run_frames_unicode_dir(scene, tmp_path):
    folder = tmp_path / "Bắt Nạt Hải Sản.contextcut" / "render" / "ảnh"
    folder.mkdir(parents=True)
    moved = folder / "scene.mlt"
    shutil.copyfile(scene, moved)
    result = run(moved, [12], folder)
    assert read_frame_code(Path(result["frames"][0]["path"])) == 29


def test_run_frames_reports_melt_failure(tmp_path):
    bad = tmp_path / "hỏng.mlt"
    bad.write_text("<mlt><producer id='x'><property name='resource'>khong-co.mp4</property></producer></mlt>",
                   encoding="utf-8")
    try:
        paths.find_tool("melt")
    except paths.ToolMissing:
        pytest.skip("cần melt")
    with pytest.raises(RuntimeError, match="melt"):
        run(bad, [0, 5], tmp_path / "out")
