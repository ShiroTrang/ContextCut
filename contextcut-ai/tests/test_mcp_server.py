# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
import json

import pytest
from fake_bridge import EDITOR_STATE, rpc_error
from mcp import Client

from contextcut_ai import guide
from contextcut_ai.bridge_client import BridgeClient
from contextcut_ai.mcp_server import build_server

pytestmark = pytest.mark.anyio


@pytest.fixture
async def mcp(bridge):
    async with Client(build_server(BridgeClient(bridge.path))) as client:
        yield client


def text_of(result) -> str:
    assert len(result.content) == 1
    return result.content[0].text


async def test_lists_four_read_only_tools(mcp):
    tools = {t.name: t for t in (await mcp.list_tools()).tools}
    assert set(tools) == {"get_editor_state", "get_timeline", "list_recordings", "get_guide"}
    for t in tools.values():
        assert t.annotations.read_only_hint is True, t.name
        assert t.output_schema is None, t.name
        assert t.description, t.name
    assert set(tools["get_timeline"].input_schema["properties"]) == {"start_f", "end_f", "tracks", "limit", "cursor"}
    assert set(tools["list_recordings"].input_schema["properties"]) == {"limit", "cursor"}
    assert "styles/gaming" in tools["get_guide"].description


async def test_get_editor_state_passthrough(mcp, bridge):
    result = await mcp.call_tool("get_editor_state", {})
    assert not result.is_error
    assert json.loads(text_of(result)) == EDITOR_STATE
    assert result.structured_content is None
    assert bridge.calls == [("get_editor_state", None)]


async def test_get_timeline_sends_only_given_params(mcp, bridge):
    await mcp.call_tool("get_timeline", {"start_f": 600, "tracks": ["V1", 7]})
    await mcp.call_tool("get_timeline", {"cursor": "5.100", "limit": 5})
    await mcp.call_tool("list_recordings", {})
    assert bridge.calls == [
        ("get_timeline", {"start_f": 600, "tracks": ["V1", 7], "limit": 100}),
        ("get_timeline", {"limit": 5, "cursor": "5.100"}),
        ("list_recordings", {}),
    ]


async def test_invalid_params_rejected_before_bridge(mcp, bridge):
    result = await mcp.call_tool("get_timeline", {"limit": 5000})
    assert result.is_error
    assert bridge.calls == []


async def test_compact_utf8_output(mcp):
    out = text_of(await mcp.call_tool("get_timeline", {}))
    assert "\n" not in out and ", " not in out and '": ' not in out
    assert "Ông Sang câu con cá" in out and "\\u" not in out


async def test_no_project_message(mcp, bridge):
    bridge.responses["get_editor_state"] = rpc_error(-32002, "no_project", "no project")
    result = await mcp.call_tool("get_editor_state", {})
    assert result.is_error
    assert "Mở ContextCut trước (" in text_of(result)
    assert "màn hình chào" in text_of(result)


async def test_stale_cursor_message(mcp, bridge):
    bridge.responses["get_timeline"] = rpc_error(-32004, "stale_cursor", "stale", current_revision=99)
    result = await mcp.call_tool("get_timeline", {"cursor": "1.5"})
    assert result.is_error and "Đọc lại từ trang đầu" in text_of(result)


async def test_app_not_running_message(tmp_path):
    async with Client(build_server(BridgeClient(tmp_path / "bridge.json"))) as client:
        result = await client.call_tool("get_timeline", {})
    assert result.is_error
    assert "Mở ContextCut trước (" in text_of(result) and "bridge.json" in text_of(result)


async def test_get_guide_index_and_topic(mcp):
    index = text_of(await mcp.call_tool("get_guide", {}))
    assert index == guide.index_text()
    body = text_of(await mcp.call_tool("get_guide", {"topic": "gaming"}))
    assert body == guide.find_topic("styles/gaming").body


async def test_get_guide_unknown_topic(mcp):
    result = await mcp.call_tool("get_guide", {"topic": "khong-co"})
    assert result.is_error
    assert "patterns/irony-cut" in text_of(result)


async def test_resources_cover_all_topics(mcp):
    resources = {str(r.uri): r for r in (await mcp.list_resources()).resources}
    expected = {f"contextcut://guide/{t.name}" for t in guide.load_topics()} | {"contextcut://guide/index"}
    assert set(resources) == expected
    assert resources["contextcut://guide/workflow"].mime_type == "text/markdown"
    [content] = (await mcp.read_resource("contextcut://guide/editing-rules")).contents
    assert content.text == guide.find_topic("editing-rules").body


async def test_prompt_open_session(mcp):
    prompts = {p.name: p for p in (await mcp.list_prompts()).prompts}
    assert set(prompts) == {"mo-phien-dung"}
    [message] = (await mcp.get_prompt("mo-phien-dung", {"goal": "funny moments 15 phút"})).messages
    for phrase in ["get_editor_state", 'get_guide("styles/gaming")', "funny moments 15 phút", "dàn ý"]:
        assert phrase in message.content.text, phrase


async def test_instructions_present(mcp):
    assert mcp.instructions == guide.instructions()


async def test_software_lists_registered_tools(mcp):
    body = guide.find_topic("software").body
    for tool in (await mcp.list_tools()).tools:
        assert f"`{tool.name}`" in body, tool.name
