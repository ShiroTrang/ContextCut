# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
import json
import socket
import time

import pytest
from fake_bridge import EDITOR_STATE, FakeBridge, rpc_error

from contextcut_ai.bridge_client import BridgeClient
from contextcut_ai.errors import BridgeError, BridgeUnavailable, RpcError, agent_message

pytestmark = pytest.mark.anyio


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def test_missing_bridge_file(tmp_path):
    client = BridgeClient(tmp_path / "nope.json")
    with pytest.raises(BridgeUnavailable) as e:
        await client.call("get_editor_state")
    assert str(e.value).startswith("Mở ContextCut trước (")
    assert "nope.json" in str(e.value) and "màn hình chào" in str(e.value)


async def test_stale_bridge_file(tmp_path):
    path = tmp_path / "bridge.json"
    path.write_text(json.dumps({"protocol": 1, "host": "127.0.0.1", "port": free_port(), "token": "0" * 64,
                                "session": "x", "pid": 1}), encoding="utf-8")
    started = time.monotonic()
    with pytest.raises(BridgeUnavailable) as e:
        await BridgeClient(path).call("get_editor_state")
    assert time.monotonic() - started < 6
    assert str(e.value).startswith("Mở ContextCut trước (")


async def test_bridge_file_with_bom(tmp_path, bridge):
    bridge.path.write_text("﻿" + bridge.path.read_text(encoding="utf-8"), encoding="utf-8")
    assert await BridgeClient(bridge.path).call("get_editor_state") == EDITOR_STATE


async def test_wrong_protocol(tmp_path):
    async with FakeBridge(tmp_path / "bridge.json", protocol=2) as fake:
        with pytest.raises(BridgeError) as e:
            await BridgeClient(fake.path).call("get_editor_state")
    assert "giao thức 2" in str(e.value)
    assert not isinstance(e.value, BridgeUnavailable)


async def test_auth_and_call(bridge):
    client = BridgeClient()  # đường dẫn lấy từ CONTEXTCUT_BRIDGE_FILE
    assert await client.call("get_editor_state") == EDITOR_STATE
    assert bridge.auth_params == {"token": bridge.token, "client": "contextcut-ai/0.1.0"}
    assert client.auth_result["session"] == bridge.session
    await client.close()


async def test_params_passed(bridge):
    client = BridgeClient(bridge.path)
    await client.call("get_timeline", {"start_f": 10, "tracks": ["V1"]})
    await client.call("get_editor_state")
    assert bridge.calls == [("get_timeline", {"start_f": 10, "tracks": ["V1"]}), ("get_editor_state", None)]


async def test_single_connection(bridge):
    client = BridgeClient(bridge.path)
    for _ in range(3):
        await client.call("get_editor_state")
    assert bridge.connections == 1


async def test_wrong_token_in_file(bridge):
    bridge.write_file(token="f" * 64)
    with pytest.raises(BridgeUnavailable) as e:
        await BridgeClient(bridge.path).call("get_editor_state")
    assert "bridge.json" in str(e.value)


async def test_reconnects_after_app_restart(bridge):
    client = BridgeClient(bridge.path)
    await client.call("get_editor_state")
    await bridge.restart()
    assert await client.call("get_editor_state") == EDITOR_STATE
    assert bridge.connections == 2
    assert client.auth_result["session"] == bridge.session


@pytest.mark.parametrize("remove_file", [True, False], ids=["closed", "crashed"])
async def test_app_closed_after_connect(bridge, remove_file):
    client = BridgeClient(bridge.path)
    await client.call("get_editor_state")
    await bridge.stop(remove_file=remove_file)
    with pytest.raises(BridgeUnavailable) as e:
        await client.call("get_editor_state")
    assert str(e.value).startswith("Mở ContextCut trước (")


async def test_rpc_error_kind(bridge):
    bridge.responses["get_editor_state"] = rpc_error(-32002, "no_project", "no project open")
    with pytest.raises(RpcError) as e:
        await BridgeClient(bridge.path).call("get_editor_state")
    assert (e.value.code, e.value.kind) == (-32002, "no_project")


async def test_call_timeout(bridge):
    bridge.silent = True
    started = time.monotonic()
    with pytest.raises(BridgeError) as e:
        await BridgeClient(bridge.path, call_timeout=0.5).call("get_editor_state")
    assert time.monotonic() - started < 3
    assert "không trả lời" in str(e.value)


def test_agent_message_kinds():
    def err(kind, **data):
        return RpcError({"code": -1, "message": "m", "data": {"kind": kind, **data}})

    assert agent_message(err("no_project")).startswith("Mở ContextCut trước (")
    assert "màn hình chào" in agent_message(err("no_project"))
    assert agent_message(err("busy")).startswith("Mở ContextCut trước (")
    assert "1234" in agent_message(err("stale_cursor", current_revision=1234))
    assert "limit" in agent_message(err("invalid_params", field="limit"))
    assert "V99" in agent_message(err("not_found", id="V99"))
    assert agent_message(BridgeUnavailable("x")) == "Mở ContextCut trước (x)"
