# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
"""P2b (docs/plans/P2.md Task 17): op zoom = Transform có keyframe trên clip cắt ra đúng khoảng; undo về y hệt.

Chạy trên `p1-gate` như test_live_ops.py. Clip là video mã số frame (test_live_vision): zoom ×2 giữ góc trái trên
đứng yên thì nửa trái khung phóng ra cả khung, nên bit k của số frame hiện ở hai ô 2k, 2k+1 — đo được scale và focus.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import pytest
from test_live_ops import (  # noqa: F401 — fixture dùng lại
    app, apply, by_id, clean, expect_error, free_from, snapshot, timeline, track_id, undo)
from test_live_vision import CLIP_LEN, code_clip, code_video, expected_code, import_ready  # noqa: F401
from p2_fixture import read_frame_code

from contextcut_ai import render
from contextcut_ai.bridge_client import BridgeClient

pytestmark = [pytest.mark.anyio, pytest.mark.live]


def doubled_left_half(code: int) -> int:
    """Số đọc được khi nửa trái khung phóng ×2: bit k (k < 8) lặp ở bit 2k và 2k+1."""
    return sum(3 << (2 * k) for k in range(8) if code >> k & 1)


def clips_on(tl: dict[str, Any], tag: str, start: int, end: int) -> list[dict[str, Any]]:
    tid = track_id(tl, tag)
    return sorted((i for i in tl["items"] if i["kind"] == "clip" and i["track"] == tid and i["start_f"] < end
                   and i["end_f"] > start), key=lambda i: i["start_f"])


def qtblend_rects(xml: str) -> list[str]:
    root = ET.fromstring(xml)
    out = []
    for f in root.iter("filter"):
        props = {p.get("name"): p.text for p in f.findall("property")}
        if props.get("mlt_service") == "qtblend":
            out.append(props["rect"])
    return out


def keyframes(anim: str, fps: int = 25) -> list[tuple[int, list[float]]]:
    """Keyframe (frame, giá trị); vị trí là số frame hoặc đồng hồ hh:mm:ss.mmm (consumer xml của Kdenlive ghi
    `time_format=clock`, nên chuỗi đã được Kdenlive đọc lại thì ra dạng này)."""
    out = []
    for part in anim.split(";"):
        m = re.fullmatch(r"\s*(?:(\d+):(\d+):(\d+(?:\.\d+)?)|(-?\d+))[^=\d]*=\s*(.+)", part)
        assert m, anim
        h, mi, sec, frame, value = m.groups()
        f = int(frame) if frame is not None else round((int(h) * 3600 + int(mi) * 60 + float(sec)) * fps)
        out.append((f, [float(v) for v in value.split()]))
    return out


async def render_codes(c: BridgeClient, frames: list[int], tmp_path: Path) -> list[int]:
    scene = await c.call("get_scene", {})
    path = tmp_path / "scene.mlt"
    path.write_text(scene["xml"], encoding="utf-8")
    result = render.run_frames({"scene": str(path), "frames": frames, "width": 640, "height": 360,
                                "out_dir": str(tmp_path / f"r{len(list(tmp_path.iterdir()))}")}, lambda *a, **k: None)
    by_f = {item["f"]: Path(item["path"]) for item in result["frames"]}
    return [read_frame_code(by_f[f]) for f in frames]


async def test_list_operations_has_zoom(app):
    ops = {op["type"]: op for op in (await app.call("list_operations"))["ops"]}
    params = ops["zoom"]["params"]
    assert {"start_f", "end_f", "scale", "focus_x", "focus_y", "ramp_in_f", "ramp_out_f", "ease", "track"} <= set(params)
    assert params["scale"]["default"] == 1.2 and params["ease"]["values"] == ["out", "in", "linear", "smooth"]


async def test_zoom_roundtrip(app, code_clip):
    at = code_clip
    before = await snapshot(app)
    batch = await apply(app, [{"type": "zoom", "start_f": at + 10, "end_f": at + 30, "scale": 2, "focus_x": 0,
                               "focus_y": 0, "ramp_in_f": 4}], "AI: zoom thử")
    tl = await timeline(app)
    pieces = clips_on(tl, "V2", at, at + CLIP_LEN)
    assert [(p["start_f"], p["end_f"], p["src_in_f"]) for p in pieces] == [(at, at + 10, 0), (at + 10, at + 30, 10),
                                                                          (at + 30, at + CLIP_LEN, 30)]
    assert [p["effects"] for p in pieces] == [[], ["Transform"], []]
    assert batch["created"]["0"] == [pieces[1]["id"]]
    [rect] = qtblend_rects((await app.call("get_scene", {}))["xml"])
    # keyframe theo frame producer: in của clip giữa = 10; vào ×2 trong 4 frame rồi giữ
    assert keyframes(rect) == [(10, [0, 0, 1280, 720, 1]), (14, [0, 0, 2560, 1440, 1])]
    await undo(app, batch)
    assert await snapshot(app) == before


async def test_zoom_render(app, code_clip, tmp_path):
    at = code_clip
    await apply(app, [{"type": "zoom", "start_f": at + 10, "end_f": at + 30, "scale": 2, "focus_x": 0, "focus_y": 0,
                       "ramp_in_f": 0, "ramp_out_f": 6, "ease": "linear"}])
    got = await render_codes(app, [at + 5, at + 10, at + 20, at + 29, at + 35], tmp_path)
    assert got[0] == expected_code(5)  # trước khoảng: khung thường
    assert got[1] == doubled_left_half(expected_code(10))  # ramp_in_f 0: vào thẳng ×2
    assert got[2] == doubled_left_half(expected_code(20))  # giữ ×2
    assert got[3] == expected_code(29)  # cuối ramp_out: về 1
    assert got[4] == expected_code(35)  # sau khoảng: khung thường


async def test_zoom_rejects_cross_clip_and_double(app, code_clip):
    at = code_clip
    err = await expect_error(apply(app, [{"type": "zoom", "start_f": at + 40, "end_f": at + CLIP_LEN + 10}]),
                             "apply_failed")
    assert err.data["field"] == "end_f" and "one clip" in err.data["reason"]
    err = await expect_error(apply(app, [{"type": "zoom", "start_f": at + 5, "end_f": at + 9, "ramp_in_f": 3,
                                          "ramp_out_f": 3}]), "apply_failed")
    assert err.data["field"] == "ramp_out_f"
    await apply(app, [{"type": "zoom", "start_f": at + 10, "end_f": at + 30}])
    err = await expect_error(apply(app, [{"type": "zoom", "start_f": at + 15, "end_f": at + 20}]), "apply_failed")
    assert "Transform" in err.data["reason"]
    bad = await app.call("validate_operations", {"ops": [{"type": "zoom", "start_f": 0, "end_f": 10, "scale": 9,
                                                          "focus_x": 2, "ease": "bounce"}]})
    assert {e["field"] for e in bad["errors"]} >= {"scale", "focus_x", "ease"}


async def test_zoom_default_track_skips_titles(app, clean, code_video):
    source = await import_ready(app, code_video)
    at = free_from(await timeline(app))
    await apply(app, [{"type": "insert_clip", "source": source["id"], "in_f": 0, "out_f": CLIP_LEN, "track": "V1",
                       "at_f": at, "audio": False},
                      {"type": "caption", "text": "chữ đè", "start_f": at, "end_f": at + CLIP_LEN, "track": "V2"}])
    batch = await apply(app, [{"type": "zoom", "start_f": at + 10, "end_f": at + 20}])
    tl = await timeline(app)
    [zoomed] = [i for i in tl["items"] if i["id"] == batch["created"]["0"][0]]
    assert zoomed["track"] == track_id(tl, "V1") and zoomed["effects"] == ["Transform"]
    assert [c["effects"] for c in clips_on(tl, "V2", at, at + CLIP_LEN)] == [[]]


async def test_zoom_then_cut_range_undo(app, code_clip):
    at = code_clip
    before = await snapshot(app)
    zoom = await apply(app, [{"type": "zoom", "start_f": at + 10, "end_f": at + 30, "ramp_out_f": 4}])
    cut = await apply(app, [{"type": "cut_range", "start_f": at + 20, "end_f": at + 25}])
    tl = await timeline(app)
    assert [p["effects"] for p in clips_on(tl, "V2", at, at + CLIP_LEN - 5)] == [[], ["Transform"], ["Transform"], []]
    await undo(app, cut)
    await undo(app, zoom)
    assert await snapshot(app) == before
