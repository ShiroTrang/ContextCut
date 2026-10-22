# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
"""P2b (docs/plans/P2.md Task 15–16): get_scene và get_viewer_frame của app trả đúng khung hình.

Chạy trên project `p1-gate` (720p 25 fps) như test_live_ops.py: mỗi test nhập một video mã số frame 60 fps, đặt nó lên
V2 ở chỗ trống cuối timeline, kiểm, rồi hoàn tác cả hai bước (timeline y hệt lúc đầu).
"""

from __future__ import annotations

import asyncio
import base64
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from test_live_ops import app, apply, clean, expect_error, free_from, revision, timeline  # noqa: F401 — fixture dùng lại

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from p2_fixture import image_size, make_frame_code_video, read_frame_code  # noqa: E402

from contextcut_ai import paths  # noqa: E402
from contextcut_ai.bridge_client import BridgeClient  # noqa: E402

pytestmark = [pytest.mark.anyio, pytest.mark.live]

CLIP_LEN = 50  # frame timeline (25 fps) = 2 s của video 60 fps


def expected_code(k: int) -> int:
    """Frame nguồn 60 fps MLT hiện ở frame thứ k (25 fps) của clip: floor(k·60/25 + 0.5)."""
    return (k * 60 * 2 + 25) // 50


@pytest.fixture(scope="module")
def code_video(tmp_path_factory) -> Path:
    return make_frame_code_video(tmp_path_factory.mktemp("Mã frame") / "mã số frame 60.mp4", fps=60, seconds=3)


async def import_ready(c: BridgeClient, path: Path) -> dict[str, Any]:
    batch = await c.call("import_media", {"path": str(path)})
    c.batches.append(batch["batch_id"])
    source = batch["source"]
    for _ in range(100):
        if source["ready"]:
            return source
        await asyncio.sleep(0.1)
        page = await c.call("list_sources", {"limit": 500})
        source = next(s for s in page["sources"] if s["id"] == source["id"])
    raise AssertionError(f"clip chưa nạp xong: {source}")


@pytest.fixture
async def code_clip(app, clean, code_video):
    """Video mã số frame nằm trên V2 tại [at, at + 50): trả at."""
    source = await import_ready(app, code_video)
    at = free_from(await timeline(app))
    await apply(app, [{"type": "insert_clip", "source": source["id"], "in_f": 0, "out_f": CLIP_LEN, "track": "V2",
                       "at_f": at, "audio": False}], "AI: test mã frame")
    return at


def melt_frame(xml: str, frame: int, out: Path) -> Path:
    scene = out.with_suffix(".mlt")
    scene.write_text(xml, encoding="utf-8")
    env = os.environ | {"MLT_REPOSITORY_DENY": "libmltjackrack:libmltladspa"}
    subprocess.run([paths.find_tool("melt"), "-quiet", str(scene), f"in={frame}", f"out={frame}", "-consumer",
                    f"avformat:{out}", "vcodec=mjpeg", "an=1", "width=640", "height=360", "progressive=1"], check=True, env=env,
                   capture_output=True, timeout=120)
    return out


def save_jpeg(data: str, out: Path) -> Path:
    out.write_bytes(base64.b64decode(data))
    return out


async def test_get_scene_renders_with_melt(app, code_clip, tmp_path):
    scene = await app.call("get_scene", {})
    assert scene["revision"] == await revision(app)
    assert scene["profile"] == {"fps": {"num": 25, "den": 1}, "width": 1280, "height": 720}
    assert scene["duration_f"] == code_clip + CLIP_LEN
    assert scene["proxies"] is True  # p1-gate bật proxy (generateproxy = 1); clip 640×360 nhỏ nên không có proxy
    assert scene["xml"].lstrip().startswith("<?xml") and "<mlt" in scene["xml"]
    for k in (0, 2, 31):
        frame = melt_frame(scene["xml"], code_clip + k, tmp_path / f"scene-{k}.jpg")
        assert read_frame_code(frame) == expected_code(k), k


async def test_get_scene_originals_flag(app, code_clip):
    kept = await app.call("get_scene", {"originals": False})
    assert kept["proxies"] is True and "mã số frame 60.mp4" in kept["xml"]
    await expect_error(app.call("get_scene", {"originals": "có"}), "invalid_params")


async def test_viewer_frame_at_f(app, code_clip, tmp_path):
    for k in (5, 40):
        shot = await app.call("get_viewer_frame", {"monitor": "project", "at_f": code_clip + k, "width": 320})
        assert shot["monitor"] == "project" and shot["position_f"] == code_clip + k and shot["clip"] is None
        assert (shot["width"], shot["height"], shot["format"]) == (320, 180, "jpeg")
        image = save_jpeg(shot["data"], tmp_path / f"viewer-{k}.jpg")
        assert image_size(image) == (320, 180)
        assert read_frame_code(image) == expected_code(k), k
    again = await app.call("get_viewer_frame", {})
    assert again["monitor"] in {"project", "clip"}
    state = await app.call("get_editor_state")
    assert state["playhead_f"] == code_clip + 40


async def test_viewer_frame_bad_params(app, clean):
    duration = (await timeline(app))["sequence"]["duration_f"]
    await expect_error(app.call("get_viewer_frame", {"at_f": duration}), "invalid_params")
    await expect_error(app.call("get_viewer_frame", {"monitor": "clip", "at_f": 3}), "invalid_params")
    await expect_error(app.call("get_viewer_frame", {"monitor": "tivi"}), "invalid_params")
    await expect_error(app.call("get_viewer_frame", {"width": 4000}), "invalid_params")


@pytest.fixture
async def mcp_live(app, tmp_path, monkeypatch):
    from mcp import Client

    from contextcut_ai.mcp_server import build_server
    monkeypatch.setenv("CONTEXTCUT_DATA_DIR", str(tmp_path / "data"))  # job render của test không lẫn job thật
    async with Client(build_server(BridgeClient())) as client:
        yield client


def images_of(result, tmp_path: Path) -> list[Path]:
    assert not result.is_error, result.content[0].text
    out = []
    for i, image in enumerate(result.content[1:]):
        out.append(save_jpeg(image.data, tmp_path / f"mcp-{i}.jpg"))
    return out


async def test_render_frames_live(code_clip, mcp_live, tmp_path):
    result = await mcp_live.call_tool("render_frames", {"frames": [code_clip + 31, code_clip + 2], "width": 320})
    shots = images_of(result, tmp_path)
    assert [read_frame_code(s) for s in shots] == [expected_code(31), expected_code(2)]
    assert image_size(shots[0]) == (320, 180)


async def test_viewer_frame_tool_live(code_clip, mcp_live, tmp_path):
    result = await mcp_live.call_tool("get_viewer_frame", {"at_f": code_clip + 12, "width": 320})
    (shot,) = images_of(result, tmp_path)
    assert read_frame_code(shot) == expected_code(12)
