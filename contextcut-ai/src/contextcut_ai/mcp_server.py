# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
"""MCP server stdio `contextcut-ai`: tool đọc và sửa timeline qua cầu nối, guide qua instructions/prompt/resource/tool."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import importlib.util
import json
import os
import time
import shutil
import subprocess
from collections.abc import AsyncIterator, Callable
from fractions import Fraction
from pathlib import Path
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated, Any, Literal

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.mcpserver.resources import TextResource
from mcp.server.mcpserver.utilities.types import Image
from mcp.types import ToolAnnotations
from pydantic import Field

from . import __version__, captions, guide, jobs, media, paths, trackmap, transcript, vision
from .analysis import asr
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


MAX_IMAGES = 12  # ảnh mỗi lần gọi (design: 8–12)
TILE_W = 256  # ô contact sheet: lưới 4×3 = 1024×432
RENDER_WAIT_S = 45  # render_frames chờ job melt chừng này trước khi trả job_id

FrameList = Annotated[list[Annotated[int, Field(ge=0)]], Field(min_length=1, max_length=MAX_IMAGES,
                                                               description="tối đa 12 frame, vd. [43380, 43440]")]
ImageWidth = Annotated[int, Field(ge=160, le=1280, description="chiều rộng ảnh (px), cao theo tỉ lệ; 512 ≈ 200 token")]
FramesOn = Annotated[Literal["source", "timeline"], Field(
    description="source: frame trên bản ghi gốc (theo fps project); timeline: frame timeline, đổi qua clip của bản ghi")]

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

    async def all_recordings() -> list[dict[str, Any]]:
        out, cursor = [], None
        while True:
            page = await bridge_call("list_recordings", present(limit=500, cursor=cursor))
            out += page["recordings"]
            if not (cursor := page.get("next_cursor")):
                return out

    async def whole_timeline() -> dict[str, Any]:
        """Mọi item của sequence (gộp các trang) kèm revision của trang đầu."""
        first = await bridge_call("get_timeline", {"limit": 1000})
        items, cursor = list(first["items"]), first.get("next_cursor")
        while cursor:
            page = await bridge_call("get_timeline", {"limit": 1000, "cursor": cursor})
            items += page["items"]
            cursor = page.get("next_cursor")
        return first | {"items": items}

    async def timed_segments(recording: str | None, on: str) -> tuple[list[dict[str, Any]], dict[str, Any], Any]:
        """Câu của transcript đã đổi ra frame (timeline hoặc nguồn) + thông tin trang (revision, fps) + store."""
        comp = await companion()
        store = trackmap.RecordingStore(comp)
        recs = [await find_recording(recording)] if recording else await all_recordings()
        loaded = []
        for rec in recs:
            info = store.get(rec["id"])
            tr = transcript.load(comp, info["file_hash"]) if info and info["path"] == rec.get("path") else None
            if tr:
                loaded.append((rec["id"], tr))
        if not loaded:
            raise ToolError("Chưa có transcript cho " + (f"bản ghi {recording}" if recording else "bản ghi nào")
                            + ": gọi transcribe(recording) rồi đợi job xong (get_job).")
        if on == "timeline":
            tl = await whole_timeline()
            fps = tl["fps"]["num"] / tl["fps"]["den"]
            segs = []
            for rec_id, tr in loaded:
                segs += transcript.on_timeline(tr, transcript.placements(tl["items"], rec_id), fps, rec_id)
            meta = {"revision": tl["revision"], "fps": tl["fps"], "duration_f": tl["sequence"]["duration_f"]}
        else:
            state = await bridge_call("get_editor_state")
            fps = state["profile"]["fps"]["num"] / state["profile"]["fps"]["den"]
            segs = [s for rec_id, tr in loaded for s in transcript.on_source(tr, fps, rec_id)]
            meta = {"revision": "source", "fps": state["profile"]["fps"]}
        segs.sort(key=lambda s: (s["start_f"], s["track"]))
        return segs, meta | {"fps_value": fps}, store

    def segment_matcher(store: Any, wanted: int | str) -> Callable[[dict[str, Any]], bool]:
        """Lọc câu theo index stream (số), role của track_map (mic, discord…) hoặc tên người nói."""
        def match(seg: dict[str, Any]) -> bool:
            if isinstance(wanted, int):
                return seg["track"] == wanted
            name = str(wanted).strip().lower()
            info = store.get(seg["recording"]) or {}
            roles = {t["index"]: t["role"] for t in info.get("track_map", [])}
            return roles.get(seg["track"]) == name or (seg["speaker"] or "").lower() == name
        return match

    async def enrich_ops(ops: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Op `caption` có `speaker`: điền màu/in hoa/nhãn theo người nói (speakers.json) và bắt mép về đầu/cuối từ
        của transcript (`snap`, mặc định bật; trường này không gửi sang app)."""
        if not any(op.get("type") == "caption" for op in ops):
            return ops, []
        try:
            comp = paths.companion_dir(await bridge_call("get_editor_state"))
        except paths.ProjectNotSaved:
            comp = None
        words, fps = None, 0.0
        if comp and any(op.get("type") == "caption" and op.get("snap", True) for op in ops):
            try:
                segs, meta, _ = await timed_segments(None, "timeline")
                words = [w | {"speaker": s["speaker"]} for s in segs for w in s["words"]]
                fps = meta["fps_value"]
            except ToolError:
                words = None  # chưa có transcript: không bắt mép
        out, snapped = [], []
        for i, op in enumerate(ops):
            if op.get("type") != "caption":
                out.append(op)
                continue
            op = dict(op)
            snap = op.pop("snap", True)
            for key, value in captions.speaker_style(comp, op.get("speaker")).items():
                op.setdefault(key, value)
            if snap and words:
                op, info = captions.snap_caption(op, words, fps)
                if info:
                    snapped.append({"op_index": i} | info)
            out.append(op)
        return out, snapped

    async def find_recording(rec_id: str) -> dict[str, Any]:
        cursor = None
        while True:
            page = await bridge_call("list_recordings", present(limit=500, cursor=cursor))
            for rec in page["recordings"]:
                if rec["id"] == rec_id:
                    return rec
            if not (cursor := page.get("next_cursor")):
                raise ToolError(f"Không có bản ghi id {rec_id!r} trong project (xem list_recordings).")

    video_cache: dict[tuple[str, int, int], tuple[str, media.VideoInfo | None]] = {}

    async def recording_video(recording: str) -> tuple[Path, str, media.VideoInfo]:
        """File, hash nhanh, thông tin hình của một bản ghi (ffprobe + hash nhớ theo kích thước/giờ sửa file)."""
        rec = await find_recording(recording)
        if rec.get("ready") is False:
            raise ToolError(f"Bản ghi {recording} đang nạp trong app: đợi vài giây rồi gọi lại.")
        path = Path(rec.get("path") or "")
        try:
            st = path.stat()
            key = (str(path), st.st_size, st.st_mtime_ns)
            if key not in video_cache:
                probe, file_hash = await asyncio.to_thread(lambda: (media.probe(path), media.fast_hash(path)))
                video_cache[key] = (file_hash, probe.video)
        except (OSError, subprocess.CalledProcessError, paths.ToolMissing) as e:
            raise ToolError(f"Không đọc được file bản ghi {rec.get('path')}: {e}") from e
        file_hash, video = video_cache[key]
        if video is None:
            raise ToolError(f"Bản ghi {recording} không có hình (chỉ có tiếng): không có khung hình để xem.")
        return path, file_hash, video

    async def vision_context() -> tuple[Fraction, Path | None]:
        """fps project (phân số) và thư mục đi kèm project (None khi chưa lưu: ảnh vào %LOCALAPPDATA%)."""
        state = await bridge_call("get_editor_state")
        fps = Fraction(state["profile"]["fps"]["num"], state["profile"]["fps"]["den"])
        try:
            return fps, paths.companion_dir(state)
        except paths.ProjectNotSaved:
            return fps, None

    async def to_source(recording: str, frames: list[int], on: str) -> list[int | str]:
        """Frame nguồn (fps project) cho từng frame; frame timeline không có bản ghi → câu lỗi thay cho số."""
        if on == "source":
            return list(frames)
        places = transcript.placements((await whole_timeline())["items"], recording)
        out: list[int | str] = []
        for f in frames:
            hit = next((p for p in places if p.start_f <= f < p.start_f + p.src_out_f - p.src_in_f), None)
            out.append(hit.src_in_f + f - hit.start_f if hit else
                       f"frame {f} không có trên timeline (bản ghi {recording} không hiện ở đó)")
        return out

    async def source_images(recording: str, frames: list[int], on: str, width: int):
        """Ảnh nguồn cho các frame → (fps project, fps nguồn, thư mục đi kèm, [(f, src_f | lỗi, Path | lỗi)])."""
        fps, comp = await vision_context()
        path, file_hash, video = await recording_video(recording)
        sources = await to_source(recording, frames, on)
        index = {f: vision.source_index(src, fps, video.fps) for f, src in zip(frames, sources) if isinstance(src, int)}
        out_dir = vision.frames_root(comp) / "analysis" / file_hash / "frames"
        try:
            got = await asyncio.to_thread(vision.extract_frames, path, list(index.values()), video.fps, width, out_dir)
        except (OSError, paths.ToolMissing) as e:
            raise ToolError(f"Không trích được ảnh: {e}") from e
        rows = [(f, src, got[index[f]] if isinstance(src, int) else src) for f, src in zip(frames, sources)]
        return fps, video.fps, comp, rows

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
        ops, snapped = await enrich_ops(ops)
        result = await bridge_call("validate_operations", {"ops": ops})
        return compact(result | ({"snapped": snapped} if snapped else {}))

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
        Trả batch_id (cho undo_batch), revision mới, created (id clip mới theo op), warnings. Op caption có speaker được
        tự điền style theo người nói và bắt mép về đầu/cuối từ trong transcript (snapped cho biết đã dời gì)."""
        ops, snapped = await enrich_ops(ops)
        try:
            result = await bridge.call("apply_operations",
                                       present(ops=ops, base_revision=base_revision, label=label, reason=reason), resend=False)
        except (BridgeError, RpcError) as e:
            raise ToolError(agent_message(e)) from e
        return compact(result | ({"snapped": snapped} if snapped else {}))

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
        wait_s: Annotated[int, Field(ge=0, le=55, description="chờ tối đa bấy nhiêu giây cho tới khi job xong rồi mới trả")] = 0,
    ) -> Any:
        """Theo dõi job nền (phiên âm, dựng khung hình…): status queued | running | done | failed | cancelled, stage,
        progress 0…1, eta_s, result khi xong (job render_frames trả kèm ảnh), error khi lỗi. Đợi job: gọi với wait_s=50
        (tool tự chờ, trả ngay khi xong) thay vì gọi dồn; job dài thì gọi lại vài lần như vậy."""
        try:
            if job_id:
                job = jobs.get(job_id)
                deadline = time.monotonic() + wait_s
                while job["status"] in jobs.ACTIVE and time.monotonic() < deadline:
                    await asyncio.sleep(0.5)
                    job = jobs.get(job_id)
                if job["kind"] == "render_frames" and job["status"] == "done":
                    shots = [Path(f["path"]) for f in (job.get("result") or {}).get("frames", [])]
                    return [compact(job_view(job)), *[Image(path=shot) for shot in shots if shot.exists()]]
                return compact(job_view(job))
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

    @tool(PROJECT_DATA)
    async def transcribe(
        recording: Annotated[str, Field(min_length=1, description="id bản ghi (list_recordings)")],
        tracks: Annotated[list[int] | None, Field(description="index stream audio cần phiên âm; bỏ trống = các track "
                                                              "transcribe=true của track_map (Mic, Discord)")] = None,
        language: Annotated[str, Field(min_length=2, max_length=8, description="mã ngôn ngữ, vd. vi, en")] = "vi",
        model: Annotated[str | None, Field(description="large-v3 | phowhisper-large | parakeet-ctc-vi; bỏ trống = mặc định")] = None,
        prompt: Annotated[str | None, Field(max_length=500, description="tên riêng/thuật ngữ để nghe đúng chính tả, "
                                                                        "vd. \"Minecraft, creeper, Sang\"")] = None,
        force: Annotated[bool, Field(description="phiên âm lại dù đã có transcript")] = False,
        allow_download: Annotated[bool, Field(description="cho tải model còn thiếu; chỉ đặt true khi người dùng đã đồng ý")] = False,
    ) -> str:
        """Phiên âm lời thoại của một bản ghi theo từng từ (track Mic = Nhan, Discord = bạn bè). Chạy nền: trả job_id,
        theo dõi bằng get_job (vài phút cho một buổi dài), xong thì đọc bằng get_transcript. Đã có transcript cùng model
        thì trả ngay (cached). Thiếu model/thư viện thì báo dung lượng: hỏi người dùng trước khi cho tải."""
        comp = await companion()
        rec = await find_recording(recording)
        store = trackmap.RecordingStore(comp)
        try:
            info = store.ensure(recording, rec["path"])
        except OSError as e:
            raise ToolError(f"Không đọc được file bản ghi {rec.get('path')}: {e}") from e
        track_map = info["track_map"]
        if tracks:
            by_index = {t["index"]: t for t in track_map}
            unknown = [i for i in tracks if i not in by_index]
            if unknown:
                raise ToolError(f"Bản ghi {recording} không có stream audio {unknown} (có: {list(by_index)}).")
            chosen = [by_index[i] for i in tracks]
        else:
            chosen = [t for t in track_map if t["transcribe"]]
        if not chosen:
            raise ToolError("Không có track nào được đánh dấu phiên âm: dùng set_track_map hoặc truyền tracks.")
        model = model or asr.default_model()
        if model not in asr.MODELS:
            raise ToolError(f"Model {model!r} không có; chọn một trong: {', '.join(asr.MODELS)}.")
        base = comp / "analysis" / info["file_hash"]
        transcript_file = base / "transcript.json"
        if transcript_file.exists() and not force:
            done = json.loads(transcript_file.read_text(encoding="utf-8"))
            have = {(t["index"], t.get("model"), t.get("language")) for t in done.get("tracks", [])}
            if all((t["index"], model, language) in have for t in chosen):
                wanted = {t["index"] for t in chosen}
                return compact({"cached": True, "transcript": transcript_file.as_posix(), "model": model,
                                "tracks": [t for t in done["tracks"] if t["index"] in wanted],
                                "segments": sum(1 for s in done["segments"] if s["track"] in wanted)})
        engine = asr.MODELS[model].engine
        needed = "faster_whisper" if engine == "ctranslate2" else "nemo"
        if importlib.util.find_spec(needed) is None or importlib.util.find_spec("huggingface_hub") is None:
            extra = "analysis" if engine == "ctranslate2" else "parakeet"
            raise ToolError(f"Chưa cài thư viện phân tích cho {model}: uv sync --directory contextcut-ai --extra {extra} "
                            "(tải vài GB thư viện; hỏi người dùng trước).")
        try:
            asr.MODELS[model].locate(allow_download=False)
        except asr.ModelMissing as e:
            if not allow_download or asr.MODELS[model].local:
                raise ToolError(f"{e} Hỏi người dùng có đồng ý tải không trước khi gọi lại.") from e
        for job in jobs.recent(50):
            p = job.get("params") or {}
            if (job["kind"] == "transcribe" and job["status"] in jobs.ACTIVE and p.get("model") == model
                    and (p.get("recording") or {}).get("file_hash") == info["file_hash"]):
                return compact({"job_id": job["id"], "status": job["status"], "already_running": True})
        if force:
            for t in chosen:
                shutil.rmtree(base / "asr" / f"{t['index']}-{model}-{language}", ignore_errors=True)
        params = {"recording": {"id": recording, "path": info["path"], "file_hash": info["file_hash"]},
                  "companion": Path(comp).as_posix(), "tracks": chosen, "language": language, "model": model,
                  "prompt": prompt, "allow_download": allow_download}
        job = jobs.submit("transcribe", params)
        return compact({"job_id": job["id"], "status": job["status"], "model": model,
                        "tracks": [{"index": t["index"], "role": t["role"], "speaker": t["speaker"]} for t in chosen],
                        "next": "get_job(job_id) sau 30–60 s; xong thì get_transcript"})

    @read_tool
    async def get_transcript(
        recording: Annotated[str | None, Field(description="id bản ghi; bỏ trống = mọi bản ghi đã có transcript")] = None,
        start_f: Annotated[int | None, Field(ge=0, description="lấy câu giao [start_f, end_f)")] = None,
        end_f: Annotated[int | None, Field(ge=1, description="frame cuối (không tính)")] = None,
        track: Annotated[int | str | None, Field(description="index stream, role (mic, discord) hoặc tên người nói")] = None,
        on: Annotated[Literal["timeline", "source"], Field(description="timeline: frame trên timeline đang mở (chỉ "
                                                                         "phần bản ghi đang hiện); source: frame trên bản ghi gốc")] = "timeline",
        words: Annotated[bool, Field(description="kèm từng từ với frame (để đặt câu đắt chính xác)")] = False,
        limit: Annotated[int, Field(ge=1, le=500, description="số câu tối đa mỗi trang")] = 100,
        cursor: Annotated[str | None, Field(description="next_cursor của trang trước; giữ nguyên bộ lọc")] = None,
    ) -> str:
        """Lời thoại đã phiên âm theo câu: người nói (Nhan, bạn bè…), start_f/end_f, tc (mm:ss.ff), chữ; low_conf là
        từ máy nghe chưa chắc. Mặc định tính theo timeline đang mở: phần bị cắt khỏi timeline không có. Đọc theo
        khoảng (start_f/end_f) để không tràn context; words=true khi cần mốc từng từ."""
        segs, meta, store = await timed_segments(recording, on)
        if track is not None:
            segs = [s for s in segs if segment_matcher(store, track)(s)]
        if start_f is not None:
            segs = [s for s in segs if s["end_f"] > start_f]
        if end_f is not None:
            segs = [s for s in segs if s["start_f"] < end_f]
        offset = 0
        if cursor:
            rev, _, off = cursor.rpartition(":")
            if rev != str(meta["revision"]) or not off.isdigit():
                raise ToolError("Timeline đã đổi (hoặc cursor sai) từ trang trước: đọc lại từ trang đầu (bỏ cursor).")
            offset = int(off)
        page = segs[offset:offset + limit]
        out = []
        for s in page:
            item = {"recording": s["recording"], "track": s["track"], "speaker": s["speaker"], "start_f": s["start_f"],
                    "end_f": s["end_f"], "tc": transcript.timecode(s["start_f"], meta["fps_value"]), "text": s["text"]}
            if s["partial"]:
                item["partial"] = True
            if words:
                item["words"] = [{"w": w["w"], "start_f": w["start_f"], "end_f": w["end_f"], "p": w.get("p")}
                                 for w in s["words"]]
            else:
                low = [w["w"] for w in s["words"] if w.get("p") is not None and w["p"] < 0.4]
                if low:
                    item["low_conf"] = low
            out.append(item)
        more = offset + limit < len(segs)
        return compact({"on": on, "revision": meta["revision"], "fps": meta["fps"], "total": len(segs),
                        "segments": out, "next_cursor": f"{meta['revision']}:{offset + limit}" if more else None})

    @tool(DESTRUCTIVE)
    async def add_subtitles(
        start_f: Annotated[int | None, Field(ge=0, description="đầu khoảng trên timeline; mặc định 0")] = None,
        end_f: Annotated[int | None, Field(ge=1, description="cuối khoảng (không tính); mặc định hết timeline")] = None,
        recording: Annotated[str | None, Field(description="chỉ lời của bản ghi này; mặc định mọi bản ghi có transcript")] = None,
        speakers: Annotated[list[str] | None, Field(description="chỉ những người nói/track này (tên, role mic|discord)")] = None,
        replace: Annotated[bool, Field(description="xoá phụ đề cũ bắt đầu trong khoảng trước khi thêm")] = True,
        preview: Annotated[bool, Field(description="chỉ trả các dòng sẽ thêm, không sửa timeline")] = False,
        max_chars: Annotated[int, Field(ge=20, le=80, description="ký tự tối đa mỗi dòng (design: 32–42)")] = 42,
        label: Annotated[str | None, Field(min_length=1, max_length=200, description="nhãn bước undo")] = None,
    ) -> str:
        """Phụ đề đầy đủ: lấy lời thoại đã phiên âm trong khoảng (theo timeline đang mở), ngắt dòng ≤ max_chars ở
        chỗ nghỉ, mỗi dòng hiện từ đầu từ đầu tới cuối từ cuối, rồi đưa vào track phụ đề của Kdenlive trong MỘT bước undo
        (Ctrl+Z). preview=true để xem trước. Cần transcript (transcribe). Câu đắt chọn lọc thì dùng op caption."""
        segs, meta, store = await timed_segments(recording, "timeline")
        fps = meta["fps_value"]
        lo = start_f or 0
        hi = end_f if end_f is not None else meta["duration_f"]
        if hi <= lo:
            raise ToolError("end_f phải lớn hơn start_f.")
        if speakers:
            matchers = [segment_matcher(store, s) for s in speakers]
            segs = [s for s in segs if any(m(s) for m in matchers)]
        clipped = []
        for s in segs:
            words = [w | {"end_f": min(w["end_f"], hi)} for w in s["words"] if lo <= w["start_f"] < hi]
            if words:
                clipped.append(s | {"words": words})
        lines = captions.build_lines(clipped, fps, max_chars=max_chars, min_chars=min(32, max_chars - 10))
        for line in lines:
            line["end_f"] = max(line["start_f"] + 1, min(line["end_f"], hi))
        tc = transcript.timecode
        if preview:
            return compact({"preview": True, "count": len(lines), "range": [lo, hi],
                            "lines": [line | {"tc": tc(line["start_f"], fps)} for line in lines]})
        if not lines:
            raise ToolError(f"Không có lời thoại nào trong khoảng {tc(lo, fps)}–{tc(hi, fps)} (xem get_transcript).")
        ops: list[dict[str, Any]] = []
        if replace:
            ops.append({"type": "clear_subtitles", "start_f": lo, "end_f": hi, "reason": "thay phụ đề cũ trong khoảng"})
        items = [{k: v for k, v in line.items() if v is not None} for line in lines]
        for i in range(0, len(items), 5000):
            ops.append({"type": "add_subtitles", "items": items[i:i + 5000]})
        label = label or f"AI: phụ đề {tc(lo, fps)}–{tc(hi, fps)}"
        try:
            result = await bridge.call("apply_operations", {"base_revision": meta["revision"], "label": label, "ops": ops},
                                       resend=False)
        except (BridgeError, RpcError) as e:
            raise ToolError(agent_message(e)) from e
        return compact({"batch_id": result["batch_id"], "revision": result["revision"], "label": result.get("label", label),
                        "lines": len(lines), "range": [lo, hi],
                        "first": [line | {"tc": tc(line["start_f"], fps)} for line in lines[:3]],
                        "warnings": result.get("warnings", [])})

    @read_tool
    async def get_source_frames(
        recording: Annotated[str, Field(min_length=1, description="id bản ghi (list_recordings)")],
        frames: FrameList,
        on: FramesOn = "source",
        width: ImageWidth = 512,
    ) -> list[Any]:
        """Xem khung hình GỐC của bản ghi ở các frame (≤ 12 ảnh JPEG nhỏ): hiểu chuyện gì xảy ra trong game, chọn chỗ
        zoom. Không có hiệu ứng/chữ của timeline (cái đó: render_frames). Ảnh cũng lưu thành file, đường dẫn trong phần
        chữ (client không hiện ảnh thì mở file). Lướt đoạn dài thì dùng get_contact_sheet trước."""
        fps, source_fps, _, rows = await source_images(recording, frames, on, width)
        listed, images = [], []
        for f, src, image in rows:
            item: dict[str, Any] = {"f": f}
            if isinstance(src, int):
                item |= {"src_f": src, "tc": transcript.timecode(f, float(fps))}
            if isinstance(image, Path):
                item["path"] = image.as_posix()
                images.append(Image(path=image))
            else:
                item["error"] = str(image)
            listed.append(item)
        info = {"recording": recording, "on": on, "fps": {"num": fps.numerator, "den": fps.denominator},
                "source_fps": str(source_fps), "frames": listed, "images": len(images)}
        return [compact(info), *images]

    @read_tool
    async def get_contact_sheet(
        recording: Annotated[str, Field(min_length=1, description="id bản ghi (list_recordings)")],
        start_f: Annotated[int, Field(ge=0, description="đầu đoạn")],
        end_f: Annotated[int, Field(ge=1, description="cuối đoạn (không tính)")],
        on: FramesOn = "source",
        cols: Annotated[int, Field(ge=2, le=6, description="số cột")] = 4,
        rows: Annotated[int, Field(ge=1, le=4, description="số hàng")] = 3,
    ) -> list[Any]:
        """Lướt nhanh một đoạn dài của bản ghi gốc: MỘT ảnh lưới (mặc định 4×3 ô, ~600 token), các ô rải đều trong
        [start_f, end_f), mỗi ô có nhãn thời gian; phần chữ liệt kê ô → frame. Xem kỹ một mốc thì get_source_frames."""
        if end_f <= start_f:
            raise ToolError("end_f phải lớn hơn start_f.")
        frames = vision.even_frames(start_f, end_f, cols * rows)
        fps, source_fps, comp, found = await source_images(recording, frames, on, TILE_W)
        cells, tiles = [], []
        for i, (f, src, image) in enumerate(found):
            tc = transcript.timecode(f, float(fps))
            cell: dict[str, Any] = {"cell": i + 1, "row": i // cols + 1, "col": i % cols + 1, "f": f, "tc": tc}
            if isinstance(src, int):
                cell["src_f"] = src
            if not isinstance(image, Path):
                cell["error"] = str(image)
            cells.append(cell)
            tiles.append((image if isinstance(image, Path) else None, tc))
        sheets = vision.frames_root(comp) / "sheets"
        out = sheets / f"{recording}-{on}-{start_f}-{end_f}-{cols}x{rows}.jpg"
        try:
            await asyncio.to_thread(vision.contact_sheet, tiles, cols, TILE_W, out)
        except (OSError, subprocess.CalledProcessError, paths.ToolMissing) as e:
            raise ToolError(f"Không ghép được contact sheet: {e}") from e
        vision.prune(sheets, keep=30)
        used_rows = -(-len(tiles) // cols)
        info = {"recording": recording, "on": on, "range": [start_f, end_f], "source_fps": str(source_fps),
                "size": [cols * TILE_W, used_rows * (TILE_W * 9 // 16)], "path": out.as_posix(), "cells": cells}
        return [compact(info), Image(path=out)]

    @read_tool
    async def render_frames(
        frames: FrameList,
        width: ImageWidth = 512,
        originals: Annotated[bool, Field(description="file gốc thay proxy (đúng như xuất); false = proxy, nhanh hơn")] = True,
    ) -> list[Any]:
        """Xem timeline ĐÃ DỰNG ở các frame timeline (≤ 12 ảnh): cùng engine và hiệu ứng với file xuất (cắt, zoom, chữ,
        phụ đề). Dùng để tự kiểm sau khi sửa. melt chạy nền, thường vài giây; quá 45 s thì trả job_id, get_job trả ảnh
        khi xong. Ảnh lưu thành file, đường dẫn trong phần chữ."""
        scene = await bridge_call("get_scene", {"originals": originals})
        late = sorted({f for f in frames if f >= scene["duration_f"]})
        if late:
            raise ToolError(f"Frame {late} nằm sau cuối timeline ({scene['duration_f']} frame).")
        _, comp = await vision_context()
        renders = vision.frames_root(comp) / "render"
        # Cùng XML (cùng timeline, cùng lựa chọn proxy) thì dùng lại ảnh đã dựng
        folder = renders / hashlib.sha1(scene["xml"].encode("utf-8")).hexdigest()[:16]
        folder.mkdir(parents=True, exist_ok=True)
        scene_file = folder / "scene.mlt"
        if not scene_file.exists():
            scene_file.write_text(scene["xml"], encoding="utf-8")
        os.utime(folder)  # prune giữ các scene dùng gần đây
        profile = scene["profile"]
        height = max(2, round(width * profile["height"] / profile["width"] / 2) * 2)
        missing = sorted({f for f in frames if not (folder / f"{f}-{width}.jpg").exists()})
        job_id = None
        if missing:
            job = jobs.submit("render_frames", {"scene": scene_file.as_posix(), "frames": missing, "width": width,
                                                "height": height, "out_dir": folder.as_posix()})
            job_id = job["id"]
            deadline = time.monotonic() + RENDER_WAIT_S
            while job["status"] in jobs.ACTIVE and time.monotonic() < deadline:
                await asyncio.sleep(0.3)
                job = jobs.get(job_id)
            if job["status"] != "done":
                if job["status"] in jobs.ACTIVE:
                    return [compact({"job_id": job_id, "status": job["status"], "stage": job.get("stage"),
                                     "next": "get_job(job_id, wait_s=50): xong thì trả ảnh"})]
                raise ToolError(f"Dựng khung hình lỗi: {job.get('error')} (log: {job.get('log')}).")
        vision.prune(renders, keep=20)
        fps = profile["fps"]["num"] / profile["fps"]["den"]
        listed = [{"f": f, "tc": transcript.timecode(f, fps), "path": (folder / f"{f}-{width}.jpg").as_posix()}
                  for f in frames]
        info = {"revision": scene["revision"], "originals": originals, "cached": not missing, "job_id": job_id,
                "frames": listed}
        return [compact(info), *[Image(path=Path(item["path"])) for item in listed]]

    @read_tool
    async def get_viewer_frame(
        monitor: Annotated[Literal["active", "project", "clip"], Field(
            description="active: monitor người dùng đang dùng; project: timeline; clip: monitor clip")] = "active",
        at_f: Annotated[int | None, Field(ge=0, description="dời playhead monitor project tới frame này trước "
                                                            "(người dùng thấy playhead nhảy tới đó)")] = None,
        width: ImageWidth = 512,
    ) -> list[Any]:
        """Khung hình người dùng đang xem trong monitor ở playhead, đúng như app hiện (proxy, chất lượng preview): để bàn
        về "chỗ này" với người dùng. at_f dời playhead tới đó trước. Cần ảnh như file xuất thì dùng render_frames."""
        fps, comp = await vision_context()
        shot = await bridge_call("get_viewer_frame", present(monitor=monitor, at_f=at_f, width=width))
        folder = vision.frames_root(comp) / "viewer"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{datetime.now():%Y%m%d-%H%M%S-%f}-{shot['position_f']}.jpg"
        path.write_bytes(base64.b64decode(shot["data"]))
        vision.prune(folder, keep=30)
        info = {k: shot.get(k) for k in ("monitor", "position_f", "playing", "clip", "width", "height")}
        info |= {"tc": transcript.timecode(shot["position_f"], float(fps)), "path": path.as_posix()}
        return [compact(info), Image(path=path)]

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
