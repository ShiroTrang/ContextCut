# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
"""Lỗi của cầu nối và câu báo lỗi tiếng Việt cho agent."""

from __future__ import annotations

from typing import Any


class BridgeError(Exception):
    """Cầu nối không dùng được: sai giao thức, app không trả lời…"""


class BridgeUnavailable(BridgeError):
    """App không chạy hoặc không nối được: `bridge.json` thiếu, cũ, hoặc kết nối bị đóng."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(f"Mở ContextCut trước ({reason})")


class RpcError(Exception):
    """Lỗi JSON-RPC app trả về (docs/protocol.md §4); `kind` là tên ổn định để code dựa vào."""

    def __init__(self, error: dict[str, Any]):
        self.code: int = error.get("code", 0)
        self.message: str = error.get("message") or ""
        self.data: dict[str, Any] = error.get("data") or {}
        self.kind: str | None = self.data.get("kind")
        super().__init__(f"{self.code} {self.kind}: {self.message}")


def agent_message(e: Exception) -> str:
    """Câu báo lỗi ngắn cho agent: chuyện gì xảy ra và làm gì tiếp."""
    if not isinstance(e, RpcError):
        return str(e)
    match e.kind:
        case "no_project":
            return ("Mở ContextCut trước (app đang chạy nhưng chưa mở project nào: còn ở màn hình chào hoặc hộp "
                    "File Recovery). Nhờ người dùng mở hoặc tạo project rồi gọi lại.")
        case "busy":
            return "Mở ContextCut trước (project đang nạp hoặc đang đóng). Đợi vài giây rồi gọi lại."
        case "stale_cursor":
            return (f"Timeline đã đổi sau khi lấy cursor (revision hiện tại {e.data.get('current_revision')}). "
                    "Đọc lại từ trang đầu, không truyền cursor.")
        case "invalid_params":
            return f"Tham số sai ({e.data.get('field')}): {e.message}"
        case "not_found":
            return (f"Không có {e.data.get('id')!r} ({e.message}). "
                    "Gọi get_editor_state/get_timeline để xem id hiện tại của track và clip.")
        case "conflict" if "undo step" in e.message:
            return (f"Đợt đó không còn là bước undo trên cùng nên không hoàn tác tự động ({e.message}). "
                    "Nếu vẫn cần, nhờ người dùng Ctrl+Z trong app (Undo History).")
        case "conflict":
            return (f"Timeline đã đổi từ lúc đọc: người dùng vừa sửa tay, undo, hoặc đợt khác đã áp dụng "
                    f"(revision hiện tại {e.data.get('current_revision')}). Không có gì bị đổi. "
                    "Đọc lại get_timeline rồi gửi lại đợt sửa với base_revision mới.")
        case "validation_failed":
            lines = []
            for err in e.data.get("errors") or []:
                where = f"op {err.get('op_index')}" if err.get("op_index", -1) >= 0 else ""
                field = err.get("field") or ""
                label = f"{where} ({field})" if where and field else (where or field)
                lines.append(f"- {label}: {err.get('message')}")
            body = "\n".join(lines or [f"- {e.message}"])
            return f"Đợt sửa không hợp lệ, chưa đổi gì:\n{body}\nSửa tham số (xem list_operations) rồi gửi lại."
        case "apply_failed":
            field = f" ({e.data['field']})" if e.data.get("field") else ""
            return (f"op {e.data.get('op_index')}{field} lỗi khi áp dụng: {e.data.get('reason')}. "
                    "Cả đợt đã hoàn tác, timeline như cũ. Đọc lại timeline nếu cần rồi gửi lại.")
        case _:
            return f"ContextCut báo lỗi {e.code} {e.kind}: {e.message}"
