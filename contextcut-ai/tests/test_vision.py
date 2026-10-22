# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
"""P2b Task 13: ảnh nguồn bằng ffmpeg đúng frame MLT sẽ hiện, contact sheet, chỗ cache."""

import os
import sys
import time
from fractions import Fraction
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from p2_fixture import image_size, make_frame_code_video, read_frame_code  # noqa: E402

from contextcut_ai import media, paths, vision  # noqa: E402


@pytest.fixture(scope="module")
def code60(tmp_path_factory) -> Path:
    """240 frame, 60 fps, 640×360."""
    try:
        paths.find_tool("ffmpeg")
    except paths.ToolMissing:
        pytest.skip("cần ffmpeg")
    return make_frame_code_video(tmp_path_factory.mktemp("code") / "code60.mp4", fps=60, seconds=4)


def test_source_index_matches_melt():
    # đo bằng melt 22/10: profile 25 fps, nguồn 60 fps → frame nguồn MLT hiện
    got = [vision.source_index(f, Fraction(25), Fraction(60)) for f in (0, 1, 2, 3, 4, 5, 50)]
    assert got == [0, 2, 5, 7, 10, 12, 120]
    assert vision.source_index(7, Fraction(30000, 1001), Fraction(30000, 1001)) == 7


def test_probe_video_fps(code60):
    video = media.probe(code60).video
    assert video is not None
    assert (video.index, video.fps, video.width, video.height) == (0, Fraction(60), 640, 360)


def test_extract_frames_exact(code60, tmp_path):
    wanted = [0, 1, 2, 59, 60, 61, 121, 200]
    got = vision.extract_frames(code60, wanted, Fraction(60), 512, tmp_path)
    assert sorted(got) == sorted(wanted)
    for s, path in got.items():
        assert isinstance(path, Path) and path.name == f"{s}-512.jpg"
        assert image_size(path) == (512, 288)
        assert read_frame_code(path) == s, s


def test_extract_frames_cached(code60, tmp_path):
    first = vision.extract_frames(code60, [30], Fraction(60), 256, tmp_path)[30]
    stamp = first.stat().st_mtime_ns
    time.sleep(0.05)
    again = vision.extract_frames(code60, [30], Fraction(60), 256, tmp_path)[30]
    assert again == first and again.stat().st_mtime_ns == stamp
    assert not list(tmp_path.glob("*.tmp*"))


def test_extract_frames_unicode_path(code60, tmp_path):
    folder = tmp_path / "Bắt Nạt Hải Sản"
    folder.mkdir()
    rec = folder / "ghi hình 01.mp4"
    rec.write_bytes(code60.read_bytes())
    out = tmp_path / "cache ảnh"
    got = vision.extract_frames(rec, [45], Fraction(60), 320, out)
    assert read_frame_code(got[45]) == 45


def test_extract_frame_past_end_is_error(code60, tmp_path):
    got = vision.extract_frames(code60, [10, 5000], Fraction(60), 256, tmp_path)
    assert isinstance(got[10], Path)
    assert isinstance(got[5000], vision.FrameError)
    assert "5000" in str(got[5000])


def test_even_frames():
    assert vision.even_frames(0, 120, 4) == [15, 45, 75, 105]
    assert vision.even_frames(100, 112, 12) == list(range(100, 112))
    assert vision.even_frames(10, 13, 6) == [10, 11, 12]


def test_contact_sheet_size_and_order(code60, tmp_path):
    frames = vision.even_frames(0, 240, 12)
    tiles = vision.extract_frames(code60, frames, Fraction(60), 256, tmp_path)
    sheet = vision.contact_sheet([(tiles[f], f"00:00.{f % 60:02d}") for f in frames], cols=4, tile_w=256,
                                 out=tmp_path / "sheet.jpg")
    assert image_size(sheet) == (1024, 432)
    # ô thứ 7 (hàng 2, cột 3) = frames[6]
    assert read_frame_code(sheet, crop=(512, 144, 256, 144)) == frames[6]
    assert read_frame_code(sheet, crop=(0, 0, 256, 144)) == frames[0]


def test_contact_sheet_fills_missing_tiles(code60, tmp_path):
    tile = vision.extract_frames(code60, [3], Fraction(60), 256, tmp_path)[3]
    sheet = vision.contact_sheet([(tile, "a"), (None, "lỗi"), (tile, "c")], cols=2, tile_w=256, out=tmp_path / "s.jpg")
    assert image_size(sheet) == (512, 288)
    assert read_frame_code(sheet, crop=(0, 144, 256, 144)) == 3


def test_frames_root_and_prune(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTEXTCUT_DATA_DIR", str(tmp_path / "data"))
    assert vision.frames_root(tmp_path / "p.contextcut") == tmp_path / "p.contextcut"
    assert vision.frames_root(None) == tmp_path / "data" / "frames"
    d = tmp_path / "render"
    d.mkdir()
    for i in range(5):
        (d / f"s{i}").mkdir()
        os.utime(d / f"s{i}", (1000 + i, 1000 + i))
    vision.prune(d, keep=2)
    assert sorted(p.name for p in d.iterdir()) == ["s3", "s4"]
