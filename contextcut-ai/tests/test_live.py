# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
"""Test sống: MCP server thật qua stdio, nối vào app ContextCut đang chạy. Tự bỏ qua khi app không chạy."""

import json
import os
import shutil
from pathlib import Path

import pytest
from mcp import Client, StdioServerParameters

from contextcut_ai.bridge_client import BridgeClient
from contextcut_ai.errors import BridgeUnavailable, RpcError

pytestmark = [pytest.mark.anyio, pytest.mark.live]
PROJECT_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture
async def app_running():
    client = BridgeClient()
    try:
        await client.call("get_editor_state")
    except BridgeUnavailable as e:
        pytest.skip(str(e))
    except RpcError:
        pass  # app chạy nhưng chưa có project: vẫn thử được thông báo lỗi
    finally:
        await client.close()


async def test_read_tools_over_stdio(app_running):
    server = StdioServerParameters(command=shutil.which("uv"),
                                   args=["--directory", str(PROJECT_DIR), "run", "--no-sync", "contextcut-ai"],
                                   env=dict(os.environ))
    async with Client(server) as mcp:
        state = await mcp.call_tool("get_editor_state", {})
        text = state.content[0].text
        if state.is_error:
            assert "Mở ContextCut trước (" in text
            return
        st = json.loads(text)
        assert st["profile"]["fps"]["num"] > 0 and st["tracks"]
        page = json.loads((await mcp.call_tool("get_timeline", {"limit": 5})).content[0].text)
        assert page["revision"] == st["revision"] and len(page["items"]) <= 5
        recordings = json.loads((await mcp.call_tool("list_recordings", {})).content[0].text)
        assert all(isinstance(r["id"], str) for r in recordings["recordings"])
        guide = await mcp.call_tool("get_guide", {"topic": "workflow"})
        assert not guide.is_error
