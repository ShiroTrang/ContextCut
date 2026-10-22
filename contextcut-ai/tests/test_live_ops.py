# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
"""Cổng P1 (docs/plans/P1.md Task 13–17): mỗi op apply rồi undo_batch → timeline y hệt; đợt lỗi hoàn tác cả đợt;
base_revision cũ → conflict. Sửa project đang mở nên chỉ chạy khi project tên `p1-gate`
(`uv run contextcut-ai/tools/p1_fixture.py --out <dir>` rồi mở bằng lệnh nó in ra).
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from contextcut_ai.bridge_client import BridgeClient
from contextcut_ai.errors import BridgeUnavailable, RpcError

pytestmark = [pytest.mark.anyio, pytest.mark.live]

OPS = {"cut_range", "split", "trim", "move", "insert_clip", "add_music", "title_card", "caption"}


@pytest.fixture
async def app():
    client = BridgeClient()
    try:
        state = await client.call("get_editor_state")
    except (BridgeUnavailable, RpcError) as e:
        await client.close()
        pytest.skip(f"cần ContextCut mở project p1-gate: {e}")
    if state["project"]["name"] != "p1-gate":
        await client.close()
        pytest.skip(f"project đang mở là {state['project']['name']!r}, không phải p1-gate: không sửa")
    client.batches = []  # đợt test đã áp dụng mà chưa hoàn tác: `clean` dọn khi một assert hỏng giữa chừng
    yield client
    await client.close()


async def timeline(c: BridgeClient) -> dict[str, Any]:
    page = await c.call("get_timeline", {"limit": 1000})
    assert page["next_cursor"] is None, "fixture nhỏ: một trang là đủ"
    return page


async def snapshot(c: BridgeClient) -> dict[str, Any]:
    """Toàn bộ timeline + trạng thái, bỏ các trường đổi mà timeline không đổi (revision, playhead, chọn)."""
    tl = copy.deepcopy(await timeline(c))
    del tl["revision"], tl["next_cursor"]
    st = copy.deepcopy(await c.call("get_editor_state"))
    for key in ("revision", "playhead_f", "selection"):
        del st[key]
    del st["project"]["modified"]
    st["undo"] = {"index": st["undo"]["index"]}
    return {"timeline": tl, "state": st}


@pytest.fixture
async def clean(app):
    """Mỗi test phải tự hoàn tác: cuối test timeline y hệt lúc đầu."""
    before = await snapshot(app)
    yield before
    for batch_id in reversed(app.batches):
        try:
            await app.call("undo_batch", {"batch_id": batch_id})
        except RpcError:
            pass
    assert await snapshot(app) == before


async def revision(c: BridgeClient) -> int:
    return (await c.call("get_editor_state"))["revision"]


async def apply(c: BridgeClient, ops: list[dict], label: str = "AI: test") -> dict[str, Any]:
    batch = await c.call("apply_operations", {"base_revision": await revision(c), "label": label, "ops": ops})
    c.batches.append(batch["batch_id"])
    return batch


async def undo(c: BridgeClient, batch: dict[str, Any]) -> dict[str, Any]:
    result = await c.call("undo_batch", {"batch_id": batch["batch_id"]})
    c.batches.remove(batch["batch_id"])
    return result


def by_id(tl: dict[str, Any]) -> dict[int, dict[str, Any]]:
    return {item["id"]: item for item in tl["items"]}


def track_id(tl: dict[str, Any], tag: str) -> int:
    return next(t["id"] for t in tl["tracks"] if t["tag"] == tag)


def linked_video_clip(tl: dict[str, Any], tag: str = "V1", min_len: int = 3) -> dict[str, Any]:
    tid = track_id(tl, tag)
    return next(i for i in tl["items"] if i["track"] == tid and i["linked"] is not None
                and i["end_f"] - i["start_f"] >= min_len)


def free_from(tl: dict[str, Any]) -> int:
    """Frame đầu tiên sau mọi clip: chỗ trống trên mọi track."""
    return tl["sequence"]["duration_f"] + 5


async def source_ids(c: BridgeClient) -> dict[str, dict[str, Any]]:
    return {s["name"]: s for s in (await c.call("list_sources", {"limit": 500}))["sources"]}


async def expect_error(coro, kind: str) -> RpcError:
    with pytest.raises(RpcError) as info:
        await coro
    assert info.value.kind == kind, info.value
    return info.value


async def test_list_operations_has_eight_ops(app):
    ops = {op["type"]: op for op in (await app.call("list_operations"))["ops"]}
    assert set(ops) == OPS
    for op in ops.values():
        assert op["summary"] and op["params"], op["type"]
        for name, spec in op["params"].items():
            assert spec["type"] and "required" in spec and spec["description"], (op["type"], name)
    assert ops["split"]["params"]["clip_id"]["required"] is True
    assert ops["title_card"]["params"]["style"]["values"] == ["black", "dim"]


async def test_list_sources_has_music_and_recordings(app):
    sources = await source_ids(app)
    flac = sources["stereo.flac"]
    assert flac["has_audio"] and not flac["has_video"] and not flac["recording"] and flac["duration_f"] > 0
    assert any(s["recording"] and s["has_audio"] for s in sources.values())


async def test_roundtrip_cut_range(app, clean):
    tl = await timeline(app)
    clip = linked_video_clip(tl)
    start, end = clip["start_f"], clip["end_f"]
    batch = await apply(app, [{"type": "cut_range", "start_f": start, "end_f": end, "reason": "thử"}])
    after = await timeline(app)
    assert after["sequence"]["duration_f"] == tl["sequence"]["duration_f"] - (end - start)
    items = by_id(after)
    assert clip["id"] not in items and clip["linked"] not in items
    for item in tl["items"]:
        if item["start_f"] >= end:
            assert items[item["id"]]["start_f"] == item["start_f"] - (end - start), item
        elif item["end_f"] <= start:
            assert items[item["id"]] == item
    await undo(app, batch)


async def test_roundtrip_split(app, clean):
    tl = await timeline(app)
    clip = linked_video_clip(tl)
    at = clip["start_f"] + 2
    batch = await apply(app, [{"type": "split", "clip_id": clip["id"], "at_f": at}])
    items = by_id(await timeline(app))
    assert items[clip["id"]]["end_f"] == at and items[clip["linked"]]["end_f"] == at
    created = batch["created"]["0"]
    assert len(created) == 2
    halves = [items[i] for i in created]
    assert {h["start_f"] for h in halves} == {at} and {h["end_f"] for h in halves} == {clip["end_f"]}
    assert halves[0]["linked"] == halves[1]["id"]
    await undo(app, batch)


async def test_roundtrip_trim(app, clean):
    tl = await timeline(app)
    clip = linked_video_clip(tl, min_len=4)
    batch = await apply(app, [{"type": "trim", "clip_id": clip["id"], "start_f": clip["start_f"] + 1,
                               "end_f": clip["end_f"] - 1}])
    items = by_id(await timeline(app))
    for cid in (clip["id"], clip["linked"]):
        assert (items[cid]["start_f"], items[cid]["end_f"]) == (clip["start_f"] + 1, clip["end_f"] - 1)
        assert items[cid]["src_in_f"] == clip["src_in_f"] + 1
    await undo(app, batch)


async def test_roundtrip_move(app, clean):
    tl = await timeline(app)
    clip = linked_video_clip(tl)
    partner = by_id(tl)[clip["linked"]]
    at = free_from(tl)
    batch = await apply(app, [{"type": "move", "clip_id": clip["id"], "at_f": at}])
    items = by_id(await timeline(app))
    assert items[clip["id"]]["start_f"] == at and items[clip["id"]]["track"] == clip["track"]
    assert items[partner["id"]]["start_f"] == at and items[partner["id"]]["track"] == partner["track"]
    await undo(app, batch)


async def test_roundtrip_insert_clip(app, clean):
    tl = await timeline(app)
    at = free_from(tl)
    source = by_id(tl)[linked_video_clip(tl)["id"]]["source"]
    batch = await apply(app, [{"type": "insert_clip", "source": source, "in_f": 1, "out_f": 4, "track": "V1",
                               "at_f": at}])
    created = batch["created"]["0"]
    assert len(created) == 2
    items = by_id(await timeline(app))
    video, audio = (items[i] for i in created)
    assert (video["track"], video["start_f"], video["end_f"], video["src_in_f"]) == (track_id(tl, "V1"), at, at + 3, 1)
    assert audio["track"] == track_id(tl, "A1") and audio["start_f"] == at and audio["linked"] == video["id"]
    await undo(app, batch)


async def test_insert_obs_recording_no_dialog(app, clean):
    tl = await timeline(app)
    recs = (await app.call("list_recordings"))["recordings"]
    obs = next(r for r in recs if len(r["audio_streams"]) == 3)
    stream = obs["audio_streams"][1]["index"]
    at = free_from(tl)
    batch = await apply(app, [{"type": "insert_clip", "source": obs["id"], "in_f": 0, "out_f": 25, "track": "V2",
                               "at_f": at, "audio_track": "A2", "audio_stream": stream}])
    items = by_id(await timeline(app))
    video, audio = (items[i] for i in batch["created"]["0"])
    assert video["track"] == track_id(tl, "V2") and audio["track"] == track_id(tl, "A2")
    assert audio["end_f"] - audio["start_f"] == 25
    await undo(app, batch)


async def test_roundtrip_add_music(app, clean):
    tl = await timeline(app)
    flac = (await source_ids(app))["stereo.flac"]
    at = free_from(tl)
    batch = await apply(app, [{"type": "add_music", "source": flac["id"], "at_f": at, "out_f": 20, "track": "A2",
                               "gain_db": -6}])
    (cid,) = batch["created"]["0"]
    music = by_id(await timeline(app))[cid]
    assert (music["track"], music["start_f"], music["end_f"]) == (track_id(tl, "A2"), at, at + 20)
    assert music["content"] == "audio" and music["effects"] == ["Volume"]
    await undo(app, batch)


async def test_add_music_needs_music_track(app, clean):
    flac = (await source_ids(app))["stereo.flac"]
    err = await expect_error(apply(app, [{"type": "add_music", "source": flac["id"], "at_f": 0}]), "apply_failed")
    assert err.data["op_index"] == 0 and err.data["field"] == "track"


async def test_roundtrip_title_card(app, clean):
    tl = await timeline(app)
    at = free_from(tl)
    batch = await apply(app, [{"type": "title_card", "text": "Trong lúc đó:", "start_f": at, "end_f": at + 50,
                               "track": "V2"}])
    (cid,) = batch["created"]["0"]
    after = await timeline(app)
    card = by_id(after)[cid]
    assert (card["track"], card["start_f"], card["end_f"]) == (track_id(tl, "V2"), at, at + 50)
    assert after["sources"][card["source"]]["type"] == "title"
    assert "Trong lúc đó" in card["name"]
    await undo(app, batch)


async def test_roundtrip_caption_default_track(app, clean):
    tl = await timeline(app)
    at = free_from(tl)
    batch = await apply(app, [{"type": "caption", "text": "Ủa alo???", "speaker": "Sang", "style": "pop",
                               "start_f": at, "end_f": at + 30}])
    (cid,) = batch["created"]["0"]
    assert by_id(await timeline(app))[cid]["track"] == tl["tracks"][0]["id"]  # không có track "Chữ": track trên cùng
    assert any(w["op_index"] == 0 for w in batch["warnings"])
    await undo(app, batch)


async def test_batch_is_one_undo_step(app, clean):
    tl = await timeline(app)
    clip = linked_video_clip(tl)
    at = free_from(tl)
    index = (await app.call("get_editor_state"))["undo"]["index"]
    batch = await apply(app, [
        {"type": "split", "clip_id": clip["id"], "at_f": clip["start_f"] + 2},
        {"type": "move", "clip_id": clip["id"], "at_f": at},
        {"type": "title_card", "text": "CÒN TIẾP", "start_f": at, "end_f": at + 25, "track": "V2", "style": "dim"},
    ], label="thử ba op")
    assert batch["label"] == "AI: thử ba op"
    st = await app.call("get_editor_state")
    assert st["undo"]["index"] == index + 1 and st["undo"]["next_undo"] == "AI: thử ba op"
    assert st["revision"] == batch["revision"]
    await undo(app, batch)


async def test_failed_op_rolls_back_whole_batch(app, clean):
    tl = await timeline(app)
    v1 = sorted((i for i in tl["items"] if i["track"] == track_id(tl, "V1")), key=lambda i: i["start_f"])
    first, second = v1[0], v1[1]
    err = await expect_error(apply(app, [
        {"type": "split", "clip_id": first["id"], "at_f": first["start_f"] + 2},
        {"type": "move", "clip_id": second["id"], "at_f": first["start_f"]},  # chỗ đã có clip
    ]), "apply_failed")
    assert err.data["op_index"] == 1 and err.data["field"] == "at_f" and err.data["reason"]


async def test_validation_errors_are_specific(app, clean):
    tl = await timeline(app)
    clip = linked_video_clip(tl)
    err = await expect_error(apply(app, [
        {"type": "nope"},
        {"type": "split", "clip_id": clip["id"]},
        {"type": "cut_range", "start_f": 10, "end_f": 5},
        {"type": "title_card", "text": "", "start_f": 0, "end_f": 10, "style": "neon"},
    ]), "validation_failed")
    fields = {(e["op_index"], e["field"]) for e in err.data["errors"]}
    assert {(0, "type"), (1, "at_f"), (2, "end_f"), (3, "text"), (3, "style")} <= fields
    assert all(e["message"] for e in err.data["errors"])


@pytest.mark.parametrize("op,field", [
    ({"type": "insert_clip", "in_f": 0, "out_f": 999, "track": "V1"}, "out_f"),
    ({"type": "insert_clip", "in_f": 0, "out_f": 3, "track": "V9"}, "track"),
    ({"type": "insert_clip", "in_f": 0, "out_f": 3, "track": "V1", "at_f": "occupied"}, "at_f"),
    ({"type": "add_music", "track": "V1"}, "track"),
    ({"type": "split", "at_f": "outside"}, "at_f"),
])
async def test_validate_state_errors(app, clean, op, field):
    tl = await timeline(app)
    clip = linked_video_clip(tl)
    op = dict(op)
    if op["type"] == "insert_clip":
        op["source"] = clip["source"]
        op["at_f"] = clip["start_f"] if op.get("at_f") == "occupied" else free_from(tl)
    elif op["type"] == "add_music":
        op |= {"source": (await source_ids(app))["stereo.flac"]["id"], "at_f": free_from(tl)}
    else:
        op |= {"clip_id": clip["id"], "at_f": clip["end_f"] + 1}
    rev = await revision(app)
    result = await app.call("validate_operations", {"ops": [op]})
    assert not result["ok"] and [(e["op_index"], e["field"]) for e in result["errors"]] == [(0, field)]
    assert await revision(app) == rev


async def test_validate_ok_does_not_change_revision(app, clean):
    tl = await timeline(app)
    clip = linked_video_clip(tl)
    rev = await revision(app)
    result = await app.call("validate_operations", {"ops": [
        {"type": "split", "clip_id": clip["id"], "at_f": clip["start_f"] + 1},
        {"type": "cut_range", "start_f": 0, "end_f": 2, "typo_field": 1},
    ]})
    assert result["ok"] and result["errors"] == []
    assert any(w["op_index"] == 1 and "typo_field" in w["message"] for w in result["warnings"])
    assert await revision(app) == rev


async def test_conflict_on_stale_revision(app, clean):
    rev = await revision(app)
    err = await expect_error(app.call("apply_operations", {"base_revision": rev + 1, "label": "AI: x",
                                                            "ops": [{"type": "cut_range", "start_f": 0, "end_f": 2}]}),
                             "conflict")
    assert err.data["current_revision"] == rev


async def test_conflict_after_other_edit(app, clean):
    tl = await timeline(app)
    rev = await revision(app)
    other = await app.call("add_markers", {"base_revision": rev, "markers": [{"f": 3, "comment": "sửa tay"}]})
    app.batches.append(other["batch_id"])
    assert other["revision"] != rev
    await expect_error(app.call("apply_operations", {"base_revision": rev, "label": "AI: x",
                                                      "ops": [{"type": "cut_range", "start_f": 0, "end_f": 2}]}),
                       "conflict")
    assert (await timeline(app))["items"] == tl["items"]
    await undo(app, other)


async def test_add_markers_roundtrip(app, clean):
    batch = await app.call("add_markers", {"base_revision": await revision(app), "label": "AI: chỗ cần xem",
                                           "markers": [{"f": 4, "comment": "phản ứng"},
                                                       {"f": 9, "comment": "Hook", "category": 2}]})
    app.batches.append(batch["batch_id"])
    assert batch["added"] == 2
    guides = {g["f"]: g for g in (await timeline(app))["guides"]}
    assert guides[4]["comment"] == "phản ứng" and guides[9]["category"] == 2
    assert (await app.call("get_editor_state"))["undo"]["next_undo"] == "AI: chỗ cần xem"
    await undo(app, batch)


async def test_add_markers_rejects_unknown_category(app, clean):
    await expect_error(app.call("add_markers", {"base_revision": await revision(app),
                                                "markers": [{"f": 4, "comment": "x", "category": 99}]}),
                       "validation_failed")


async def test_undo_batch_only_top(app, clean):
    tl = await timeline(app)
    at = free_from(tl)
    first = await apply(app, [{"type": "title_card", "text": "1", "start_f": at, "end_f": at + 10, "track": "V2"}])
    second = await apply(app, [{"type": "title_card", "text": "2", "start_f": at + 20, "end_f": at + 30,
                                "track": "V2"}])
    await expect_error(undo(app, first), "conflict")
    assert (await undo(app, second))["undone"] == "AI: test"
    await expect_error(undo(app, second), "conflict")
    await undo(app, first)
    await expect_error(app.call("undo_batch", {"batch_id": "khong-co"}), "not_found")


@pytest.mark.parametrize("path", ["stereo.flac", "C:/Windows/notepad.exe", "C:/khong-co/nhac.mp3", ""])
async def test_import_media_rejects_bad_paths(app, clean, path):
    err = await expect_error(app.call("import_media", {"path": path}), "invalid_params")
    assert err.data["field"] == "path"


async def test_import_media_audio(app, clean):
    sources = await source_ids(app)
    flac = sources["stereo.flac"]
    batch = await app.call("import_media", {"path": flac["path"]})
    app.batches.append(batch["batch_id"])
    source = batch["source"]
    assert source["id"] not in {s["id"] for s in sources.values()}
    assert source["ready"] and source["has_audio"] and source["duration_f"] == flac["duration_f"]
    assert (await app.call("get_editor_state"))["undo"]["next_undo"] == "AI: nhập stereo.flac"
    await undo(app, batch)
    assert len(await source_ids(app)) == len(sources)
