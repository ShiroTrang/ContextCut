# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
"""P2c Task 21 (sống): hộp xác nhận xuất và open_project trên app thật, project `p1-gate`.

Không bấm hộp thoại thay người dùng: hộp xác nhận được huỷ bằng `cancel_confirmation`; test mở project khác chỉ chạy khi
`p1-gate` chưa có thay đổi chưa lưu (Kdenlive sẽ hỏi Save changes? — cái đó kiểm tay ở cổng P2c).
"""

from __future__ import annotations

import asyncio
import shutil
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from p2_fixture import make_frame_code_video  # noqa: E402

from contextcut_ai.bridge_client import BridgeClient  # noqa: E402
from contextcut_ai.errors import BridgeUnavailable, RpcError  # noqa: E402

pytestmark = [pytest.mark.anyio, pytest.mark.live]


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
        pytest.skip(f"project đang mở là {state['project']['name']!r}, không phải p1-gate")
    client.state = state
    yield client
    await client.close()


async def rpc_error(coro) -> RpcError:
    with pytest.raises(RpcError) as e:
        await coro
    return e.value


async def test_open_rejects_bad_paths(app, tmp_path):
    project = Path(app.state["project"]["path"])
    for path in ("p1-gate.kdenlive", str(project.with_suffix(".mp4")), str(tmp_path / "không có.kdenlive"), ""):
        e = await rpc_error(app.call("open_project", {"path": path}))
        assert e.kind == "invalid_params" and e.data["field"] == "path", (path, e)


async def test_open_same_project_is_noop(app):
    before = app.state["revision"]
    out = await app.call("open_project", {"path": app.state["project"]["path"]})
    assert out["state"] == "opened" and out["already_open"] is True and out["request_id"] is None
    assert (await app.call("get_editor_state"))["revision"] == before


async def test_confirmation_lifecycle(app, tmp_path):
    duration = app.state["sequence"]["duration_f"]
    ask = {"kind": "export", "output": (tmp_path / "Xuất thử.mp4").as_posix(), "start_f": 0, "end_f": min(50, duration),
           "preset": "project", "encoder": "auto", "overwrite": False}
    asked = await app.call("request_confirmation", ask)
    cid = asked["confirm_id"]
    assert asked["state"] == "pending" and cid.startswith("c-")
    assert (await app.call("get_confirmation", {"confirm_id": cid}))["state"] == "pending"
    # hộp không-modal: cầu nối vẫn đọc/sửa được trong lúc chờ
    assert (await app.call("get_editor_state"))["project"]["name"] == "p1-gate"
    cancelled = await app.call("cancel_confirmation", {"confirm_id": cid})
    assert cancelled["state"] == "cancelled" and cancelled["revision"] is not None
    assert (await app.call("get_confirmation", {"confirm_id": cid}))["state"] == "cancelled"
    assert (await rpc_error(app.call("get_confirmation", {"confirm_id": "c-khong-co"}))).kind == "not_found"
    for bad, field in ((ask | {"end_f": duration + 1}, "end_f"), (ask | {"preset": "4k"}, "preset"),
                       (ask | {"output": "Xuất thử.mp4"}, "output"), (ask | {"output": ask["output"][:-4] + ".mkv"}, "output"),
                       (ask | {"kind": "delete"}, "kind")):
        e = await rpc_error(app.call("request_confirmation", bad))
        assert e.kind == "invalid_params" and e.data["field"] == field, (bad, e)


async def test_confirmation_refuses_source_media(app, tmp_path):
    """output trùng file một clip trong bin → invalid_params: xuất không bao giờ ghi đè nguồn."""
    video = make_frame_code_video(tmp_path / "Nguồn thử.mp4", fps=25, seconds=1)
    imported = await app.call("import_media", {"path": str(video)})
    try:
        e = await rpc_error(app.call("request_confirmation", {
            "kind": "export", "output": str(video).upper(), "start_f": 0, "end_f": 10, "preset": "project",
            "encoder": "x264", "overwrite": True}))
        assert e.kind == "invalid_params" and "source media" in e.message
    finally:
        await app.call("undo_batch", {"batch_id": imported["batch_id"]})


async def wait_open(app: BridgeClient, request_id: str, timeout: float = 60) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = await app.call("get_open_status", {"request_id": request_id})
        if status["state"] != "pending":
            return status
        dialog = status["dialog"]
        assert dialog is None or dialog["title"] == "Loading Project", f"app đang hỏi: {dialog}"
        await asyncio.sleep(0.3)
    raise AssertionError("mở project quá lâu")


async def ready_state(app: BridgeClient, timeout: float = 30) -> dict:
    deadline = time.monotonic() + timeout
    while True:
        try:
            return await app.call("get_editor_state")
        except RpcError as e:
            if e.kind != "busy" or time.monotonic() > deadline:
                raise
            await asyncio.sleep(0.3)


async def test_open_other_project_and_back(app):
    if app.state["project"]["modified"]:
        pytest.skip("p1-gate có thay đổi chưa lưu: Kdenlive sẽ hỏi Save changes? (lưu bằng Ctrl+S rồi chạy lại)")
    home = Path(app.state["project"]["path"])
    other = home.with_name("p1-gate bản sao Tập 2.kdenlive")
    shutil.copyfile(home, other)
    try:
        # một hộp xác nhận xuất còn chờ: đổi project thì hộp tự rút (không để bấm Xuất cho project khác)
        asked = await app.call("request_confirmation", {
            "kind": "export", "output": str(home.with_name("không xuất.mp4")), "start_f": 0, "end_f": 10,
            "preset": "project", "encoder": "x264", "overwrite": False})
        started = await app.call("open_project", {"path": str(other)})
        assert started["state"] == "pending" and started["modified"] is False
        # trong lúc mở: method khác bị từ chối (busy) hoặc chạy sau khi mở xong — không bao giờ chen vào giữa
        try:
            await app.call("add_markers", {"markers": [{"f": 1, "comment": "x"}], "base_revision": app.state["revision"]})
            raise AssertionError("add_markers không được chạy được vào project cũ/mới khi base_revision là của p1-gate")
        except RpcError as e:
            assert e.kind in {"busy", "conflict"}, e
        status = await wait_open(app, started["request_id"])
        assert status["state"] == "opened", status
        assert (await app.call("get_confirmation", {"confirm_id": asked["confirm_id"]}))["state"] == "cancelled"
        state = await ready_state(app)
        assert state["project"]["name"] == other.stem and state["revision"] != app.state["revision"]
        # một đợt trong project mới, hoàn tác cho sạch rồi quay về
        marked = await app.call("add_markers", {"markers": [{"f": 3, "comment": "mốc thử"}], "base_revision": state["revision"]})
        await app.call("undo_batch", {"batch_id": marked["batch_id"]})
        assert (await app.call("get_editor_state"))["project"]["modified"] is False
        back = await app.call("open_project", {"path": str(home)})
        assert (await wait_open(app, back["request_id"]))["state"] == "opened"
        state = await ready_state(app)
        assert state["project"]["name"] == "p1-gate"
        # đợt của project kia không còn là bước undo nào ở đây
        e = await rpc_error(app.call("undo_batch", {"batch_id": marked["batch_id"]}))
        assert e.kind == "conflict", e
    finally:
        state = await ready_state(app)
        if state["project"]["name"] != "p1-gate":
            back = await app.call("open_project", {"path": str(home)})
            await wait_open(app, back["request_id"])
        other.unlink(missing_ok=True)
