# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
"""Client WebSocket tới cầu nối AI của app ContextCut (docs/protocol.md §1, §3).

Một kết nối, gửi tuần tự. Mỗi lần nối đọc lại `bridge.json` vì cổng và token đổi mỗi lần app chạy;
kết nối rớt (app khởi động lại) thì nối lại và gửi lại đúng một lần (lệnh sửa: chỉ khi app chắc chưa nhận).
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed, InvalidHandshake

from . import __version__
from .errors import BridgeError, BridgeUnavailable, RpcError

PROTOCOL = 1
MAX_MESSAGE = 16 * 1024 * 1024


def default_bridge_file() -> Path:
    if env := os.environ.get("CONTEXTCUT_BRIDGE_FILE"):
        return Path(env)
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "contextcut" / "bridge.json"


class BridgeClient:
    def __init__(self, bridge_file: str | Path | None = None, *, connect_timeout: float = 5,
                 call_timeout: float = 30):
        self._bridge_file = Path(bridge_file) if bridge_file else None
        self._connect_timeout = connect_timeout
        self._call_timeout = call_timeout
        self._ws: ClientConnection | None = None
        self._lock = asyncio.Lock()
        self._next_id = 0
        self.auth_result: dict[str, Any] | None = None

    @property
    def bridge_file(self) -> Path:
        return self._bridge_file or default_bridge_file()

    async def call(self, method: str, params: dict[str, Any] | None = None, *, resend: bool = True) -> dict[str, Any]:
        """Gửi một request, trả `result`; lỗi của app thành `RpcError`, lỗi kết nối thành `BridgeError`.

        Kết nối rớt thì nối lại và gửi lại một lần. Lệnh sửa (`resend=False`) chỉ gửi lại khi chắc app chưa nhận:
        rớt sau khi đã gửi thì báo "có thể đã được áp dụng" thay vì áp dụng hai lần.
        """
        async with self._lock:
            if not resend:
                await self._drop_if_dead()
            for attempt in range(2):
                if self._ws is None:
                    await self._connect()
                sent = [False]
                try:
                    return await self._request(method, params, sent)
                except (ConnectionClosed, OSError) as e:
                    await self.close()
                    if sent[0] and not resend:
                        raise BridgeError(
                            f"Kết nối tới ContextCut rớt sau khi đã gửi {method}: lệnh có thể đã được áp dụng. "
                            "Gọi get_editor_state (xem undo.next_undo) hoặc get_timeline để kiểm tra trước khi gửi lại."
                        ) from e
                    if attempt == 1:
                        raise BridgeUnavailable(f"kết nối tới app bị đóng: {e}") from e
        raise AssertionError("unreachable")

    async def _drop_if_dead(self) -> None:
        """Ping kết nối đang giữ (app có thể đã khởi động lại); chết thì bỏ để lệnh sửa đi trên kết nối mới."""
        if self._ws is None:
            return
        try:
            pong = await self._ws.ping()
            async with asyncio.timeout(2):
                await pong
        except (ConnectionClosed, OSError, TimeoutError):
            await self.close()

    async def close(self) -> None:
        ws, self._ws = self._ws, None
        if ws is not None:
            await ws.close()

    async def _connect(self) -> None:
        path = self.bridge_file
        try:
            info = json.loads(path.read_text(encoding="utf-8-sig"))
            port = int(info["port"])
            token = str(info["token"])
        except FileNotFoundError:
            # Ở màn hình chào app chưa dựng cửa sổ chính nên cầu nối chưa mở (đo ở P1b).
            raise BridgeUnavailable(f"không thấy {path}: app chưa chạy, hoặc còn ở màn hình chào") from None
        except (OSError, ValueError, KeyError, TypeError) as e:
            raise BridgeUnavailable(f"không đọc được {path}: {e}") from e
        if info.get("protocol") != PROTOCOL:
            raise BridgeError(f"app ContextCut dùng giao thức {info.get('protocol')}, contextcut-ai {__version__} "
                              f"chỉ hiểu giao thức {PROTOCOL}: cập nhật cả hai lên cùng phiên bản")
        # Giao thức chỉ nghe 127.0.0.1; không dùng "localhost" (có thể ra ::1).
        url = f"ws://127.0.0.1:{port}/"
        try:
            self._ws = await connect(url, open_timeout=self._connect_timeout, close_timeout=2,
                                     max_size=MAX_MESSAGE, compression=None)
        except (OSError, TimeoutError, InvalidHandshake) as e:
            raise BridgeUnavailable(f"không nối được {url}: app đã tắt hoặc crash, {path} còn sót lại") from e
        try:
            self.auth_result = await self._request("auth", {"token": token, "client": f"contextcut-ai/{__version__}"})
        except RpcError as e:
            await self.close()
            raise BridgeUnavailable(f"app từ chối token trong {path} (file cũ hoặc của app khác): {e.message}") from e
        except (ConnectionClosed, OSError) as e:
            await self.close()
            raise BridgeUnavailable(f"app đóng kết nối lúc xác thực: {e}") from e

    async def _request(self, method: str, params: dict[str, Any] | None, sent: list[bool] | None = None) -> dict[str, Any]:
        assert self._ws is not None
        self._next_id += 1
        rid = self._next_id
        msg: dict[str, Any] = {"jsonrpc": "2.0", "id": rid, "method": method}
        if params is not None:
            msg["params"] = params
        await self._ws.send(json.dumps(msg, ensure_ascii=False))
        if sent is not None:
            sent[0] = True
        try:
            async with asyncio.timeout(self._call_timeout):
                while True:
                    reply = json.loads(await self._ws.recv())
                    if reply.get("id") == rid:  # bỏ trả lời trễ của request đã hết giờ
                        break
        except TimeoutError:
            raise BridgeError(f"ContextCut không trả lời {method} sau {self._call_timeout:g} giây "
                              "(app đang bận, đang mở hộp thoại, hoặc bị treo)") from None
        if "error" in reply:
            raise RpcError(reply["error"])
        return reply["result"]
