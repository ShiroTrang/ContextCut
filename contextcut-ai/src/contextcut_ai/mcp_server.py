# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
"""MCP server stdio `contextcut-ai`: tool đọc và sửa timeline qua cầu nối, guide qua instructions/prompt/resource/tool."""

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

from . import __version__, guide, jobs, paths, trackmap
from .bridge_client import BridgeClient
from .errors import BridgeError, RpcError, agent_message

READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
# Sửa được hoàn tác (Ctrl+Z) nhưng có thể xoá clip khỏi timeline
DESTRUCTIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False)
ADDITIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
# Ghi dữ liệu của ContextCut (thư mục .contextcut), không đụng timeline
PROJECT_DATA = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)

OPS_SUMMARY = (
    "Op (frame nguyên, khoảng nửa mở, mọi op nhận reason): "
    "cut_range{start_f,end_f} cắt bỏ khoảng trên mọi track không khoá và kéo phần sau lên; "
    "split{clip_id,at_f}; trim{clip_id,start_f?,end_f?} mép mới trên timeline; move{clip_id,at_f,track?}; "
    "insert_clip{source,in_f,out_f,track,at_f,audio_track?,audio_stream?,audio?} vào chỗ trống; "
    "add_music{source,at_f,in_f?,out_f?,track?,gain_db?}; "
    "title_card{text,start_f,end_f,track?,style=black|dim} thẻ chữ toàn màn hình; "
    "caption{text,start_f,end_f,speaker?,track?,style=bottom|top|pop}. "
    "Clip có tiếng đi cặp (linked) được cắt/dời cùng. Schema đầy đủ: list_operations."
)

# Ở mức module: `from __future__ import annotations` khiến pydantic tra chú thích kiểu trong globals
OpList = Annotated[list[dict[str, Any]], Field(min_length=1, max_length=200,
                                               description='Các op chạy theo thứ tự, vd. [{"type": "split", '
                                                           '"clip_id": 42, "at_f": 300, "reason": "…"}]')]


JOB_FIELDS = ("id", "kind", "status", "stage", "progress", "eta_s", "created_at", "started_at", "finished_at", "result",
              "error")


def job_view(job: dict[str, Any]) -> dict[str, Any]:
    view = {k: job.get(k) for k in JOB_FIELDS}
    if job.get("status") == "failed":
        view["log"] = job.get("log")
    return view


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

    def tool(annotations: ToolAnnotations, extra: str = "") -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def register(fn: Callable[..., Any]) -> Callable[..., Any]:
            # docstring gom về một dòng: mô tả tool nằm trong context của agent ở mọi lượt
            description = " ".join(((fn.__doc__ or "") + " " + extra).split())
            server.add_tool(fn, description=description, structured_output=False, annotations=annotations)
            return fn
        return register

    read_tool = tool(READ_ONLY)

    async def call(method: str, params: dict[str, Any] | None = None, *, resend: bool = True) -> str:
        try:
            return compact(await bridge.call(method, params, resend=resend))
        except (BridgeError, RpcError) as e:
            raise ToolError(agent_message(e)) from e

    def present(**params: Any) -> dict[str, Any]:
        return {k: v for k, v in params.items() if v is not None}

    async def bridge_call(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            return await bridge.call(method, params)
        except (BridgeError, RpcError) as e:
            raise ToolError(agent_message(e)) from e

    async def companion() -> Any:
        try:
            return paths.companion_dir(await bridge_call("get_editor_state"))
        except paths.ProjectNotSaved as e:
            raise ToolError(str(e)) from e

    async def find_recording(rec_id: str) -> dict[str, Any]:
        cursor = None
        while True:
            page = await bridge_call("list_recordings", present(limit=500, cursor=cursor))
            for rec in page["recordings"]:
                if rec["id"] == rec_id:
                    return rec
            if not (cursor := page.get("next_cursor")):
                raise ToolError(f"Không có bản ghi id {rec_id!r} trong project (xem list_recordings).")

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
        return await call("get_timeline",
                          present(start_f=start_f, end_f=end_f, tracks=tracks, limit=limit, cursor=cursor))

    @read_tool
    async def list_recordings(
        limit: Annotated[int | None, Field(ge=1, le=500, description="Số bản ghi tối đa mỗi trang (mặc định 100)")] = None,
        cursor: Annotated[str | None, Field(description="next_cursor của trang trước")] = None,
    ) -> str:
        """Các bản ghi (video nguồn, thường là file OBS) của project: id ổn định, đường dẫn, hash, độ dài theo frame
        project, fps nguồn, kích thước, stream audio, đã lên timeline chưa, track_map (stream nào là Mic/Discord/Game;
        null tới khi transcribe hoặc set_track_map lần đầu)."""
        result = await bridge_call("list_recordings", present(limit=limit, cursor=cursor))
        if result.get("recordings"):
            try:
                store = trackmap.RecordingStore(paths.companion_dir(await bridge_call("get_editor_state")))
            except paths.ProjectNotSaved:
                store = None
            for rec in result["recordings"]:
                known = store.get(rec["id"]) if store else None
                if known and known["path"] == rec.get("path"):
                    rec["track_map"] = known["track_map"]
        return compact(result)

    @read_tool
    async def list_sources(
        limit: Annotated[int | None, Field(ge=1, le=500, description="Số clip tối đa mỗi trang (mặc định 100)")] = None,
        cursor: Annotated[str | None, Field(description="next_cursor của trang trước")] = None,
    ) -> str:
        """Mọi clip trong bin (bản ghi, nhạc, SFX, ảnh, title…): id dùng làm source cho insert_clip/add_music, tên,
        loại, đường dẫn, độ dài theo frame project (null nếu không giới hạn), có hình/tiếng, đã nạp xong chưa."""
        return await call("list_sources", present(limit=limit, cursor=cursor))

    @read_tool
    async def list_operations() -> str:
        """Danh mục op sửa timeline và schema tham số (kiểu, bắt buộc, khoảng, mặc định). Đọc trước lần sửa đầu."""
        return await call("list_operations")

    @tool(READ_ONLY, OPS_SUMMARY)
    async def validate_operations(ops: OpList) -> str:
        """Kiểm một đợt op với timeline hiện tại, không đổi gì: ok, errors (op_index, field, message), warnings.
        Op đứng sau một op làm đổi timeline chỉ được kiểm gần đúng (apply kiểm lại đúng lúc)."""
        return await call("validate_operations", {"ops": ops})

    @tool(DESTRUCTIVE, OPS_SUMMARY)
    async def apply_operations(
        ops: OpList,
        base_revision: Annotated[int, Field(ge=0, description="revision vừa đọc từ get_editor_state/get_timeline")],
        label: Annotated[str, Field(min_length=1, max_length=200,
                                    description='Tên bước undo người dùng thấy, vd. "AI: cắt đoạn chết 03:10–04:02"')],
        reason: Annotated[str | None, Field(max_length=500, description="Lý do một câu cho cả đợt")] = None,
    ) -> str:
        """Sửa timeline đang mở: cả đợt là MỘT bước undo nhãn "AI: …" (Ctrl+Z hoàn tác cả đợt). Người dùng sửa chen
        ngang (revision khác base_revision) thì bị từ chối, không đổi gì. Op nào lỗi thì cả đợt tự hoàn tác.
        Trả batch_id (cho undo_batch), revision mới, created (id clip mới theo op), warnings."""
        return await call("apply_operations", present(ops=ops, base_revision=base_revision, label=label, reason=reason),
                          resend=False)

    @tool(ADDITIVE)
    async def add_markers(
        markers: Annotated[list[dict[str, Any]], Field(min_length=1, max_length=500,
                                                       description='[{"f": 43380, "comment": "phản ứng", "category": 2}]; '
                                                                   "category bỏ trống = loại mặc định")],
        base_revision: Annotated[int, Field(ge=0, description="revision vừa đọc")],
        label: Annotated[str | None, Field(min_length=1, max_length=200,
                                           description='Tên bước undo, mặc định "AI: thêm marker"')] = None,
    ) -> str:
        """Thêm guide (marker) trên timeline để chỉ chỗ cho người dùng xem: một bước undo. Không đổi clip."""
        return await call("add_markers", present(markers=markers, base_revision=base_revision, label=label),
                          resend=False)

    @tool(DESTRUCTIVE)
    async def undo_batch(
        batch_id: Annotated[str, Field(min_length=1, description="batch_id do apply_operations/add_markers trả")],
    ) -> str:
        """Hoàn tác đợt sửa của chính mình, chỉ khi nó còn là bước undo trên cùng (như Ctrl+Z một lần).
        Người dùng đã sửa thêm thì bị từ chối: nhờ người dùng tự hoàn tác."""
        return await call("undo_batch", {"batch_id": batch_id}, resend=False)

    @tool(ADDITIVE)
    async def import_media(
        path: Annotated[str, Field(min_length=1, description="Đường dẫn tuyệt đối tới file video/âm thanh/ảnh, vd. D:/Nhạc/Can Can.mp3")],
    ) -> str:
        """Nhập một file media (video, nhạc, SFX, ảnh) vào bin để dùng làm source; một bước undo. Chỉ nhận đuôi media,
        không nhận file qua symlink. Trả source (id, độ dài, ready); chưa ready thì đợi rồi xem list_sources."""
        return await call("import_media", {"path": path}, resend=False)

    @tool(PROJECT_DATA)
    async def set_track_map(
        recording: Annotated[str, Field(min_length=1, description="id bản ghi (list_recordings)")],
        tracks: Annotated[list[dict[str, Any]], Field(min_length=1, max_length=32, description=(
            '[{"index": 2, "role": "mic", "speaker": "Nhan", "transcribe": true}]; index = audio_streams[].index; '
            "role: mix | mic | discord | game | desktop | other; speaker mặc định mic → Nhan, discord → bạn bè"))],
    ) -> str:
        """Sửa sơ đồ track audio của một bản ghi (stream nào là Mic của Nhan, Discord của bạn bè, game…). Mặc định
        ContextCut đoán theo tên stream rồi theo thứ tự OBS (1 trộn chung, 2 Mic, 3 Discord, 4 game, 5 desktop).
        Chỉ track transcribe=true được phiên âm. Lưu vào <project>.contextcut/recordings.json."""
        store = trackmap.RecordingStore(await companion())
        rec = await find_recording(recording)
        try:
            store.ensure(recording, rec["path"])
            updated = store.set_track_map(recording, tracks)
        except (ValueError, OSError) as e:
            raise ToolError(str(e)) from e
        return compact({"recording": recording, "track_map": updated["track_map"]})

    @read_tool
    async def get_job(
        job_id: Annotated[str | None, Field(description="job_id do transcribe… trả; bỏ trống để xem các job gần đây")] = None,
    ) -> str:
        """Theo dõi job nền (phiên âm…): status queued | running | done | failed | cancelled, stage (đang làm gì),
        progress 0…1, eta_s, result khi xong, error khi lỗi. Job dài vài phút: hỏi lại thưa (30–60 s), đừng gọi dồn."""
        try:
            if job_id:
                return compact(job_view(jobs.get(job_id)))
            return compact({"jobs": [job_view(j) for j in jobs.recent()]})
        except KeyError as e:
            raise ToolError(f"Không có job {job_id!r} (xem get_job không tham số).") from e

    @tool(PROJECT_DATA)
    async def cancel_job(job_id: Annotated[str, Field(min_length=1, description="job_id cần huỷ")]) -> str:
        """Huỷ job nền: job đang chờ thì huỷ ngay, đang chạy thì dừng ở mốc kế tiếp (phần đã xong vẫn giữ để chạy tiếp)."""
        try:
            return compact(job_view(jobs.cancel(job_id)))
        except KeyError as e:
            raise ToolError(f"Không có job {job_id!r}.") from e

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
            "5. Dừng ở dàn ý, chờ tôi duyệt. Chỉ dựng (apply_operations, nhãn AI: …) phần tôi đã duyệt.\n"
            f"Video tôi muốn: {goal or '(chưa nói: hỏi tôi muốn video thế nào)'}"
        )

    return server


def main() -> None:
    build_server().run("stdio")


if __name__ == "__main__":
    main()
