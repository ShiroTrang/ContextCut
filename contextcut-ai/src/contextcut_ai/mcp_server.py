# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
"""MCP server stdio `contextcut-ai`: tool đọc timeline qua cầu nối, guide qua instructions/prompt/resource/tool."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Annotated, Any

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.mcpserver.resources import TextResource
from mcp.types import ToolAnnotations
from pydantic import Field

from . import __version__, guide
from .bridge_client import BridgeClient
from .errors import BridgeError, RpcError, agent_message

READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=False)


def compact(value: Any) -> str:
    """JSON một dòng, giữ nguyên chữ tiếng Việt: kết quả tool đi thẳng vào context của agent."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def build_server(bridge: BridgeClient | None = None) -> MCPServer:
    bridge = bridge or BridgeClient()
    topics = guide.load_topics()

    @asynccontextmanager
    async def lifespan(_: MCPServer) -> AsyncIterator[None]:
        try:
            yield
        finally:
            await bridge.close()

    server = MCPServer("contextcut", title="ContextCut", version=__version__, instructions=guide.instructions(),
                       log_level="WARNING", lifespan=lifespan)

    def read_tool(fn: Callable[..., Any]) -> Callable[..., Any]:
        # docstring gom về một dòng: mô tả tool nằm trong context của agent ở mọi lượt
        server.add_tool(fn, description=" ".join((fn.__doc__ or "").split()), structured_output=False,
                        annotations=READ_ONLY)
        return fn

    async def call(method: str, params: dict[str, Any] | None = None) -> str:
        try:
            return compact(await bridge.call(method, params))
        except (BridgeError, RpcError) as e:
            raise ToolError(agent_message(e)) from e

    @read_tool
    async def get_editor_state() -> str:
        """Trạng thái ContextCut: project, fps (phân số num/den), kích thước, sequence, playhead_f, vùng chọn,
        track (id, tag V1/A1, tên, loại, khoá/ẩn/tắt tiếng), số clip/marker/bản ghi, revision. Gọi đầu tiên.
        Chỉ có số lượng: tên và chi tiết bản ghi ở list_recordings, clip và marker ở get_timeline."""
        return await call("get_editor_state")

    @read_tool
    async def get_timeline(
        start_f: Annotated[int | None, Field(ge=0, description="Frame đầu, mặc định 0")] = None,
        end_f: Annotated[int | None, Field(ge=1, description="Frame cuối (không tính), mặc định hết timeline")] = None,
        tracks: Annotated[list[int | str] | None, Field(description="Chỉ lấy các track này: id số hoặc tag như \"V1\"")] = None,
        limit: Annotated[int, Field(ge=1, le=1000, description="Số item tối đa mỗi trang")] = 100,
        cursor: Annotated[str | None, Field(description="next_cursor của trang trước; giữ nguyên bộ lọc")] = None,
    ) -> str:
        """Clip, composition và marker (guides) của sequence đang mở, lấy các item giao với khoảng nửa mở
        [start_f, end_f), sắp theo start_f rồi thứ tự track. Thời gian là frame theo fps project.
        Còn trang thì next_cursor khác null."""
        params = {"start_f": start_f, "end_f": end_f, "tracks": tracks, "limit": limit, "cursor": cursor}
        return await call("get_timeline", {k: v for k, v in params.items() if v is not None})

    @read_tool
    async def list_recordings(
        limit: Annotated[int | None, Field(ge=1, le=500, description="Số bản ghi tối đa mỗi trang (mặc định 100)")] = None,
        cursor: Annotated[str | None, Field(description="next_cursor của trang trước")] = None,
    ) -> str:
        """Các bản ghi (video nguồn, thường là file OBS) của project: id ổn định, đường dẫn, hash, độ dài theo frame
        project, fps nguồn, kích thước, stream audio, đã lên timeline chưa."""
        params = {"limit": limit, "cursor": cursor}
        return await call("list_recordings", {k: v for k, v in params.items() if v is not None})

    def get_guide(
        topic: Annotated[str | None, Field(description="Ví dụ workflow, styles/gaming; bỏ trống để xem mục lục")] = None,
    ) -> str:
        if not topic:
            return guide.index_text()
        found = guide.find_topic(topic)
        if found is None:
            raise ToolError(f"Không có topic {topic!r}.\n{guide.index_text()}")
        return found.body

    server.add_tool(
        get_guide, structured_output=False, annotations=READ_ONLY,
        description="Hướng dẫn dựng video trong ContextCut (tiếng Việt). Bỏ trống topic để xem mục lục. Topic: "
                    + ", ".join(t.name for t in topics) + ".")

    for t in topics:
        server.add_resource(TextResource(uri=f"contextcut://guide/{t.name}", name=f"guide/{t.name}", title=t.title,
                                         description=t.summary, text=t.body, mime_type="text/markdown"))
    server.add_resource(TextResource(uri="contextcut://guide/index", name="guide/index", title="Mục lục guide",
                                     description="Danh sách topic hướng dẫn", text=guide.index_text(),
                                     mime_type="text/markdown"))

    styles = [t.name.removeprefix("styles/") for t in topics if t.name.startswith("styles/")]

    @server.prompt(name="mo-phien-dung", title="Mở phiên dựng ContextCut",
                   description="Đọc project đang mở và guide, tóm tắt, rồi đề xuất dàn ý để duyệt. "
                               f"style: {', '.join(styles)}; goal: video muốn làm.")
    def open_session(style: str = "gaming", goal: str = "") -> str:
        style_line = (f'get_guide("styles/{style}")' if style in styles
                      else f"(chưa có hướng dẫn phong cách {style!r}; dùng get_guide(\"styles/gaming\") và nói rõ)")
        return (
            f"Mở phiên dựng ContextCut, phong cách {style}.\n"
            "1. Gọi get_editor_state và list_recordings; cần thì get_timeline theo khoảng.\n"
            f'2. Đọc get_guide("workflow"), get_guide("editing-rules"), {style_line}.\n'
            "3. Tóm tắt project cho tôi: bản ghi, độ dài, track, marker, chỗ playhead/vùng chọn.\n"
            "4. Đề xuất dàn ý theo workflow: mỗi đoạn có vai trò, khoảng thời gian (frame + timecode), "
            "lý do một câu, kiểu dựng. Chỗ nào là đoán (chưa nghe, chưa xem) thì nói rõ.\n"
            "5. Dừng ở dàn ý, chờ tôi duyệt. Chưa có tool sửa thì không nói là đã dựng.\n"
            f"Video tôi muốn: {goal or '(chưa nói: hỏi tôi muốn video thế nào)'}"
        )

    return server


def main() -> None:
    build_server().run("stdio")


if __name__ == "__main__":
    main()
