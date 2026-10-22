# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
"""P2a (docs/plans/P2.md Task 8): op phụ đề, list_subtitles, cut_range dời phụ đề, caption màu/in hoa.

Chạy trên project `p1-gate` như test_live_ops.py (sửa rồi hoàn tác; cuối mỗi test timeline y hệt lúc đầu).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from mcp import Client
from test_live_ops import apply, app, clean, expect_error, free_from, timeline, undo  # noqa: F401 — fixture dùng lại

from contextcut_ai import trackmap
from contextcut_ai.bridge_client import BridgeClient
from contextcut_ai.mcp_server import build_server

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


async def test_add_subtitles_tool_on_app(app, clean):
    """Chuỗi P2a trên app thật: bản ghi trên timeline + transcript (giả) → tool add_subtitles → track phụ đề."""
    state = await app.call("get_editor_state")
    fps = state["profile"]["fps"]["num"] / state["profile"]["fps"]["den"]
    rec = next(r for r in (await app.call("list_recordings"))["recordings"] if r["name"].startswith("Ông Sang"))
    at = free_from(await timeline(app))
    placed = await apply(app, [{"type": "insert_clip", "source": rec["id"], "in_f": 0, "out_f": int(4 * fps),
                                "track": "V1", "at_f": at}], "AI: test đặt bản ghi")
    companion = Path(state["project"]["companion_dir"])
    info = trackmap.RecordingStore(companion).ensure(rec["id"], rec["path"])
    folder = companion / "analysis" / info["file_hash"]
    folder.mkdir(parents=True, exist_ok=True)
    w = lambda t, a, b: {"w": t, "start": a, "end": b, "p": 0.9}  # noqa: E731
    (folder / "transcript.json").write_text(json.dumps({
        "schema": "contextcut-transcript/1", "language": "vi", "model": "test",
        "tracks": [{"index": 2, "model": "test", "language": "vi"}],
        "segments": [{"track": 2, "speaker": "Nhan", "start": 0.5, "end": 1.4, "text": "Ủa alo?", "flags": [],
                      "words": [w("Ủa", 0.5, 0.8), w("alo?", 0.8, 1.4)]},
                     {"track": 2, "speaker": "Nhan", "start": 2.0, "end": 3.0, "text": "Nghe nè.", "flags": [],
                      "words": [w("Nghe", 2.0, 2.4), w("nè.", 2.4, 3.0)]}]}, ensure_ascii=False), encoding="utf-8")
    async with Client(build_server(BridgeClient())) as mcp:
        result = await mcp.call_tool("add_subtitles", {"start_f": at, "end_f": at + int(4 * fps)})
    assert not result.is_error, result.content[0].text
    out = json.loads(result.content[0].text)
    app.batches.append(out["batch_id"])
    got = [(s["start_f"] - at, s["end_f"] - at, s["text"], s["speaker"]) for s in await subtitles(app)]
    assert got == [(round(0.5 * fps), round(1.4 * fps), "Ủa alo?", "Nhan"), (round(2.0 * fps), round(3.0 * fps), "Nghe nè.", "Nhan")]
    await undo(app, {"batch_id": out["batch_id"]})
    await undo(app, placed)
