# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
"""Cầu nối giả: server WebSocket thật trên 127.0.0.1, xác thực và trả lời như app (docs/protocol.md)."""

from __future__ import annotations

import copy
import json
import secrets
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from websockets.asyncio.server import Server, ServerConnection, serve
from websockets.exceptions import ConnectionClosed

Response = dict[str, Any] | Callable[[dict[str, Any] | None], dict[str, Any]]


def rpc_error(code: int, kind: str, message: str, **data: Any) -> dict[str, Any]:
    """Một trả lời lỗi để đặt vào `FakeBridge.responses`."""
    return {"error": {"code": code, "message": message, "data": {"kind": kind, **data}}}


TRACKS = [
    {"id": 3, "tag": "V2", "name": "Chữ", "kind": "video", "locked": False, "muted": False, "hidden": False, "items": 1},
    {"id": 5, "tag": "V1", "name": "Video", "kind": "video", "locked": False, "muted": False, "hidden": False, "items": 1},
    {"id": 7, "tag": "A1", "name": "Mic", "kind": "audio", "locked": False, "muted": False, "hidden": False, "items": 1},
]

EDITOR_STATE = {
    "session": "3b0c8f7e-0000-4000-8000-000000000001",
    "revision": 1873402,
    "project": {"path": "D:/Videos/Bắt Nạt Hải Sản.kdenlive", "name": "Bắt Nạt Hải Sản", "modified": False,
                "companion_dir": "D:/Videos/Bắt Nạt Hải Sản.contextcut"},
    "profile": {"fps": {"num": 60, "den": 1}, "width": 1920, "height": 1080},
    "sequence": {"uuid": "{8a1f}", "name": "Sequence 1", "duration_f": 216000},
    "sequences": [{"uuid": "{8a1f}", "name": "Sequence 1", "active": True}],
    "playhead_f": 43380,
    "selection": {"items": [], "zone": None},
    "tracks": TRACKS,
    "counts": {"clips": 2, "compositions": 0, "guides": 1, "subtitles": 0, "recordings": 1},
}

TIMELINE = {
    "revision": 1873402,
    "sequence": EDITOR_STATE["sequence"],
    "fps": {"num": 60, "den": 1},
    "range": {"start_f": 0, "end_f": 216000},
    "tracks": TRACKS,
    "items": [
        {"id": 42, "kind": "clip", "track": 5, "start_f": 0, "end_f": 300, "source": "4", "src_in_f": 120,
         "src_out_f": 420, "name": "Ông Sang câu con cá.mkv", "speed": 1.0, "enabled": True, "content": "video",
         "linked": 43, "effects": []},
        {"id": 43, "kind": "clip", "track": 7, "start_f": 0, "end_f": 300, "source": "4", "src_in_f": 120,
         "src_out_f": 420, "name": "Ông Sang câu con cá.mkv", "speed": 1.0, "enabled": True, "content": "audio",
         "linked": 42, "effects": []},
    ],
    "guides": [{"f": 3600, "comment": "Hook", "category": 0}],
    "sources": {"4": {"name": "Ông Sang câu con cá.mkv", "type": "av", "recording": True}},
    "next_cursor": None,
}

RECORDINGS = {
    "revision": 1873402,
    "recordings": [
        {"id": "4", "name": "Ông Sang câu con cá.mkv", "path": "D:/OBS/Ông Sang câu con cá.mkv",
         "file_hash": "5d41402abc4b2a76b9719d911017c592", "type": "av", "ready": True, "duration_f": 432000,
         "source_fps": 60.0, "width": 1920, "height": 1080,
         "audio_streams": [{"index": 1, "name": "Stereo 48kHz aac", "channels": 2}],
         "on_timeline": True, "track_map": None, "day_start": None},
    ],
    "next_cursor": None,
}


def default_responses() -> dict[str, Response]:
    return {
        "get_editor_state": copy.deepcopy(EDITOR_STATE),
        "get_timeline": copy.deepcopy(TIMELINE),
        "list_recordings": copy.deepcopy(RECORDINGS),
    }


class FakeBridge:
    """`async with FakeBridge(path) as b:` — nghe trên cổng do OS cấp và ghi `bridge.json` vào `path`."""

    def __init__(self, path: Path, responses: dict[str, Response] | None = None, *, protocol: int = 1):
        self.path = Path(path)
        self.responses: dict[str, Response] = default_responses() if responses is None else responses
        self.protocol = protocol
        self.silent = False  # True: nhận request nhưng không bao giờ trả lời (app treo)
        self.connections = 0
        self.calls: list[tuple[str, dict[str, Any] | None]] = []
        self.auth_params: dict[str, Any] | None = None
        self.token = ""
        self.session = ""
        self.port = 0
        self._server: Server | None = None

    async def __aenter__(self) -> FakeBridge:
        await self.start()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.stop()

    async def start(self) -> None:
        self.token = secrets.token_hex(32)
        self.session = str(uuid.uuid4())
        self._server = await serve(self._handle, "127.0.0.1", 0, compression=None)
        self.port = self._server.sockets[0].getsockname()[1]
        self.write_file()

    def write_file(self, **overrides: Any) -> None:
        info = {"protocol": self.protocol, "host": "127.0.0.1", "port": self.port, "token": self.token,
                "session": self.session, "pid": 4242, "app": "ContextCut", "app_version": "26.08.2",
                "started_at": "2026-10-22T10:00:00+07:00"} | overrides
        self.path.write_text(json.dumps(info), encoding="utf-8")

    async def stop(self, *, remove_file: bool = False) -> None:
        """Đóng server và mọi kết nối. `remove_file=False` giống app crash (file còn sót)."""
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        if remove_file:
            self.path.unlink(missing_ok=True)

    async def restart(self) -> None:
        """App khởi động lại: cổng, token, session mới."""
        await self.stop()
        await self.start()

    async def _handle(self, ws: ServerConnection) -> None:
        self.connections += 1
        authed = False
        try:
            async for raw in ws:
                msg = json.loads(raw)
                rid, method, params = msg.get("id"), msg.get("method"), msg.get("params")
                if method == "auth" or not authed:
                    if method == "auth" and (params or {}).get("token") == self.token:
                        authed = True
                        self.auth_params = params
                        await self._reply(ws, rid, {"result": {"protocol": self.protocol, "session": self.session,
                                                               "app": "ContextCut", "app_version": "26.08.2",
                                                               "revision": 1873402}})
                        continue
                    await self._reply(ws, rid, rpc_error(-32001, "unauthorized", "unauthorized"))
                    await ws.close(4401, "unauthorized")
                    return
                self.calls.append((method, params))
                if self.silent:
                    continue
                response = self.responses.get(method)
                if response is None:
                    response = rpc_error(-32601, "method_not_found", f"unknown method {method}", method=method)
                elif callable(response):
                    response = response(params)
                if "error" not in response:
                    response = {"result": response}
                await self._reply(ws, rid, response)
        except ConnectionClosed:
            pass

    @staticmethod
    async def _reply(ws: ServerConnection, rid: Any, body: dict[str, Any]) -> None:
        await ws.send(json.dumps({"jsonrpc": "2.0", "id": rid} | body, ensure_ascii=False))
