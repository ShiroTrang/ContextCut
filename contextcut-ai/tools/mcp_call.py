# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
"""Gọi một tool MCP của ContextCut trong tiến trình (cùng code server client chạy), in kết quả.

    uv run --directory contextcut-ai --no-sync python tools/mcp_call.py export '{"output": "D:/x.mp4"}'
"""
import asyncio
import json
import sys
import time

from mcp import Client

from contextcut_ai.bridge_client import BridgeClient
from contextcut_ai.mcp_server import build_server


async def main(tool: str, args: dict) -> None:
    async with Client(build_server(BridgeClient(call_timeout=60))) as client:
        start = time.monotonic()
        result = await client.call_tool(tool, args)
        for block in result.content:
            print(block.text if block.type == "text" else f"<{block.type}>")
        print(f"[{tool} {'ERROR' if result.is_error else 'ok'} {time.monotonic() - start:.1f} s]")

asyncio.run(main(sys.argv[1], json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}))
