# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
"""P2a (docs/plans/P2.md Task 8): op phụ đề, list_subtitles, cut_range dời phụ đề, caption màu/in hoa.

Chạy trên project `p1-gate` như test_live_ops.py (sửa rồi hoàn tác; cuối mỗi test timeline y hệt lúc đầu).
"""

from __future__ import annotations

from typing import Any

import pytest
from test_live_ops import apply, app, clean, expect_error, timeline, undo  # noqa: F401 — fixture dùng lại

from contextcut_ai.bridge_client import BridgeClient

pytestmark = [pytest.mark.anyio, pytest.mark.live]


async def subtitles(c: BridgeClient, **params: Any) -> list[dict[str, Any]]:
    page = await c.call("list_subtitles", {"limit": 1000} | params)
    assert page["next_cursor"] is None
    return page["items"]


def plain(items: list[dict[str, Any]]) -> list[tuple]:
    return [(s["layer"], s["start_f"], s["end_f"], s["text"], s["speaker"]) for s in items]


LINES = [{"start_f": 2, "end_f": 6, "text": "Ủa alo, nghe không?", "speaker": "Nhan"},
         {"start_f": 8, "end_f": 12, "text": "Nghe nè", "speaker": "bạn bè"},
         {"start_f": 14, "end_f": 20, "text": "Vào game đi\nnhanh lên"}]


async def test_list_operations_has_subtitle_ops(app):
    ops = {op["type"]: op for op in (await app.call("list_operations"))["ops"]}
    assert {"add_subtitles", "clear_subtitles"} <= set(ops)
    assert ops["add_subtitles"]["params"]["items"]["type"] == "items"
    assert ops["add_subtitles"]["params"]["items"]["max_items"] == 5000
    assert {"color", "uppercase", "label"} <= set(ops["caption"]["params"])


async def test_add_subtitles_roundtrip(app, clean):
    assert await subtitles(app) == []
    batch = await apply(app, [{"type": "add_subtitles", "items": LINES}], "AI: phụ đề thử")
    assert len(batch["created"]["0"]) == 3
    got = await subtitles(app)
    assert plain(got) == [(0, 2, 6, "Ủa alo, nghe không?", "Nhan"), (0, 8, 12, "Nghe nè", "bạn bè"),
                          (0, 14, 20, "Vào game đi\nnhanh lên", "")]
    assert plain(await subtitles(app, start_f=7, end_f=9)) == [(0, 8, 12, "Nghe nè", "bạn bè")]
    state = await app.call("get_editor_state")
    assert state["counts"]["subtitles"] == 3 and state["undo"]["next_undo"] == "AI: phụ đề thử"
    await undo(app, batch)
    assert await subtitles(app) == []


async def test_clear_then_add_is_one_undo(app, clean):
    first = await apply(app, [{"type": "add_subtitles", "items": LINES}])
    before = (await app.call("get_editor_state"))["undo"]["index"]
    second = await apply(app, [{"type": "clear_subtitles", "start_f": 0, "end_f": 10},
                               {"type": "add_subtitles", "items": [{"start_f": 3, "end_f": 9, "text": "Thay thế"}]}])
    assert (await app.call("get_editor_state"))["undo"]["index"] == before + 1
    assert [s["text"] for s in await subtitles(app)] == ["Thay thế", "Vào game đi\nnhanh lên"]
    await undo(app, second)
    assert plain(await subtitles(app))[0][3] == "Ủa alo, nghe không?" and len(await subtitles(app)) == 3
    await undo(app, first)


async def test_overlap_rejected(app, clean):
    bad = [{"start_f": 2, "end_f": 8, "text": "một"}, {"start_f": 6, "end_f": 10, "text": "hai"}]
    err = await expect_error(apply(app, [{"type": "add_subtitles", "items": bad}]), "validation_failed")
    assert err.data["errors"][0]["field"] == "items"
    first = await apply(app, [{"type": "add_subtitles", "items": LINES}])
    err = await expect_error(apply(app, [{"type": "add_subtitles", "items": [{"start_f": 5, "end_f": 7, "text": "x"}]}]),
                             "apply_failed")
    assert err.data["field"] == "items"
    await undo(app, first)


async def test_cut_range_moves_subtitles(app, clean):
    lines = [{"start_f": 1, "end_f": 4, "text": "trước"}, {"start_f": 6, "end_f": 9, "text": "cắt ngang đầu"},
             {"start_f": 11, "end_f": 13, "text": "nằm trong"}, {"start_f": 15, "end_f": 19, "text": "cắt ngang cuối"},
             {"start_f": 22, "end_f": 25, "text": "sau"}]
    first = await apply(app, [{"type": "add_subtitles", "items": lines}])
    cut = await apply(app, [{"type": "cut_range", "start_f": 8, "end_f": 17}])
    assert not any("subtitle" in w["message"] for w in cut["warnings"])
    assert [(s["start_f"], s["end_f"], s["text"]) for s in await subtitles(app)] == [
        (1, 4, "trước"), (6, 8, "cắt ngang đầu"), (8, 10, "cắt ngang cuối"), (13, 16, "sau")]
    await undo(app, cut)
    assert [(s["start_f"], s["end_f"]) for s in await subtitles(app)] == [(1, 4), (6, 9), (11, 13), (15, 19), (22, 25)]
    await undo(app, first)


async def test_caption_color_uppercase(app, clean):
    tl = await timeline(app)
    at = tl["sequence"]["duration_f"] + 5
    batch = await apply(app, [{"type": "caption", "text": "ủa alo được chưa", "speaker": "Sang", "start_f": at,
                               "end_f": at + 4, "track": "V2", "color": "#FFD400", "uppercase": True, "label": False}])
    [cid] = batch["created"]["0"]
    item = next(i for i in (await timeline(app))["items"] if i["id"] == cid)
    assert item["name"] == "ỦA ALO ĐƯỢC CHƯA"
    await undo(app, batch)
    err = await expect_error(apply(app, [{"type": "caption", "text": "x", "start_f": at, "end_f": at + 2,
                                          "color": "vàng"}]), "validation_failed")
    assert err.data["errors"][0]["field"] == "color"
