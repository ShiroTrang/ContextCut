# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
import base64
import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest
from fake_bridge import EDITOR_STATE, RECORDINGS, rpc_error
from mcp import Client

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from p2_fixture import make_frame_code_video, make_obs_mkv, read_frame_code  # noqa: E402

from contextcut_ai import guide, paths, trackmap
from contextcut_ai.analysis import asr
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


READ_TOOLS = {"get_editor_state", "get_timeline", "list_recordings", "list_sources", "get_guide", "list_operations",
              "validate_operations", "get_job", "get_transcript", "get_source_frames", "get_contact_sheet"}
EDIT_TOOLS = {"apply_operations", "undo_batch", "add_markers", "import_media", "set_track_map", "cancel_job", "transcribe",
              "add_subtitles"}


async def test_lists_tools(mcp):
    tools = {t.name: t for t in (await mcp.list_tools()).tools}
    assert set(tools) == READ_TOOLS | EDIT_TOOLS
    for t in tools.values():
        assert t.annotations.read_only_hint is (t.name in READ_TOOLS), t.name
        assert t.output_schema is None, t.name
        assert t.description, t.name
    assert tools["apply_operations"].annotations.destructive_hint is True
    assert tools["undo_batch"].annotations.destructive_hint is True
    assert tools["add_markers"].annotations.destructive_hint is False
    assert tools["import_media"].annotations.destructive_hint is False
    assert set(tools["get_timeline"].input_schema["properties"]) == {"start_f", "end_f", "tracks", "limit", "cursor"}
    assert set(tools["list_recordings"].input_schema["properties"]) == {"limit", "cursor"}
    assert set(tools["apply_operations"].input_schema["properties"]) == {"ops", "base_revision", "label", "reason"}
    assert set(tools["apply_operations"].input_schema["required"]) == {"ops", "base_revision", "label"}
    for op in ["cut_range", "split", "trim", "move", "insert_clip", "add_music", "title_card", "caption"]:
        assert op in tools["apply_operations"].description, op
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
        ("get_editor_state", None),  # thư mục đi kèm project, để gắn track_map
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


async def test_apply_passthrough(mcp, bridge):
    ops = [{"type": "cut_range", "start_f": 11400, "end_f": 14520, "reason": "im lặng"}]
    result = await mcp.call_tool("apply_operations", {"ops": ops, "base_revision": 1873402, "label": "AI: cắt đoạn chết"})
    assert not result.is_error
    assert json.loads(text_of(result))["created"] == {"0": [87, 88]}
    assert bridge.calls == [("apply_operations", {"ops": ops, "base_revision": 1873402, "label": "AI: cắt đoạn chết"})]


async def test_other_edit_tools_passthrough(mcp, bridge):
    await mcp.call_tool("validate_operations", {"ops": [{"type": "split", "clip_id": 42, "at_f": 100}]})
    await mcp.call_tool("add_markers", {"markers": [{"f": 3600, "comment": "Hook"}], "base_revision": 7})
    await mcp.call_tool("undo_batch", {"batch_id": "b-1"})
    await mcp.call_tool("import_media", {"path": "D:/Nhạc/Can Can.mp3"})
    await mcp.call_tool("list_operations", {})
    await mcp.call_tool("list_sources", {})
    assert bridge.calls == [
        ("validate_operations", {"ops": [{"type": "split", "clip_id": 42, "at_f": 100}]}),
        ("add_markers", {"markers": [{"f": 3600, "comment": "Hook"}], "base_revision": 7}),
        ("undo_batch", {"batch_id": "b-1"}),
        ("import_media", {"path": "D:/Nhạc/Can Can.mp3"}),
        ("list_operations", None),
        ("list_sources", {}),
    ]


async def test_apply_rejects_empty_batch_before_bridge(mcp, bridge):
    result = await mcp.call_tool("apply_operations", {"ops": [], "base_revision": 1, "label": "AI: x"})
    assert result.is_error and bridge.calls == []


async def test_conflict_message(mcp, bridge):
    bridge.responses["apply_operations"] = rpc_error(-32003, "conflict", "stale", current_revision=1873999)
    result = await mcp.call_tool("apply_operations", {"ops": [{"type": "cut_range", "start_f": 0, "end_f": 5}],
                                                      "base_revision": 1873402, "label": "AI: x"})
    assert result.is_error
    assert "1873999" in text_of(result) and "Không có gì bị đổi" in text_of(result)


async def test_validation_failed_message(mcp, bridge):
    bridge.responses["apply_operations"] = rpc_error(
        -32006, "validation_failed", "1 invalid", errors=[{"op_index": 0, "field": "end_f", "message": "must be > 5"}])
    result = await mcp.call_tool("apply_operations", {"ops": [{"type": "cut_range", "start_f": 5, "end_f": 5}],
                                                      "base_revision": 1, "label": "AI: x"})
    assert result.is_error and "op 0 (end_f): must be > 5" in text_of(result)


async def test_apply_failed_message(mcp, bridge):
    bridge.responses["apply_operations"] = rpc_error(-32007, "apply_failed", "op 1 failed", op_index=1, field="at_f",
                                                     reason="V1 already has item 12")
    result = await mcp.call_tool("apply_operations", {"ops": [{"type": "split", "clip_id": 1, "at_f": 2}] * 2,
                                                      "base_revision": 1, "label": "AI: x"})
    assert result.is_error
    assert "op 1" in text_of(result) and "V1 already has item 12" in text_of(result) and "hoàn tác" in text_of(result)


async def test_apply_not_resent_when_app_drops(mcp, bridge):
    await mcp.call_tool("get_editor_state", {})
    bridge.drop_once.add("apply_operations")
    result = await mcp.call_tool("apply_operations", {"ops": [{"type": "cut_range", "start_f": 0, "end_f": 5}],
                                                      "base_revision": 1, "label": "AI: x"})
    assert result.is_error and "có thể đã được áp dụng" in text_of(result)
    assert [m for m, _ in bridge.calls].count("apply_operations") == 1


def with_companion(bridge, companion: Path, rec_path: Path | None = None) -> None:
    state = copy.deepcopy(EDITOR_STATE)
    state["project"]["companion_dir"] = companion.as_posix()
    bridge.responses["get_editor_state"] = state
    if rec_path is not None:
        recs = copy.deepcopy(RECORDINGS)
        recs["recordings"][0]["path"] = rec_path.as_posix()
        bridge.responses["list_recordings"] = recs


@pytest.fixture(scope="module")
def obs_mkv(tmp_path_factory) -> Path:
    return make_obs_mkv(tmp_path_factory.mktemp("rec") / "Ông Sang câu con cá.mkv", seconds=3)


async def test_list_recordings_adds_known_track_map(mcp, bridge, tmp_path, obs_mkv):
    companion = tmp_path / "Bắt Nạt Hải Sản.contextcut"
    with_companion(bridge, companion, obs_mkv)
    out = json.loads(text_of(await mcp.call_tool("list_recordings", {})))
    assert out["recordings"][0]["track_map"] is None  # chưa probe: không tự chạy ffprobe khi liệt kê
    trackmap.RecordingStore(companion).ensure("4", obs_mkv)
    out = json.loads(text_of(await mcp.call_tool("list_recordings", {})))
    assert [e["role"] for e in out["recordings"][0]["track_map"]] == ["mix", "mic", "discord", "game", "desktop"]


async def test_set_track_map_tool(mcp, bridge, tmp_path, obs_mkv):
    companion = tmp_path / "P.contextcut"
    with_companion(bridge, companion, obs_mkv)
    result = await mcp.call_tool("set_track_map", {"recording": "4", "tracks": [
        {"index": 1, "role": "mix"}, {"index": 2, "role": "mic"}, {"index": 3, "role": "discord", "speaker": "Sang"}]})
    assert not result.is_error, text_of(result)
    out = json.loads(text_of(result))
    assert [(e["role"], e["speaker"]) for e in out["track_map"]] == [("mix", None), ("mic", "Nhan"), ("discord", "Sang")]
    assert trackmap.RecordingStore(companion).get("4")["track_map"] == out["track_map"]
    bad = await mcp.call_tool("set_track_map", {"recording": "4", "tracks": [{"index": 9, "role": "mic"}]})
    assert bad.is_error and "index 9" in text_of(bad)
    missing = await mcp.call_tool("set_track_map", {"recording": "77", "tracks": [{"index": 1, "role": "mix"}]})
    assert missing.is_error and "77" in text_of(missing)


async def test_set_track_map_unsaved_project(mcp, bridge):
    state = copy.deepcopy(EDITOR_STATE)
    state["project"].update(path=None, companion_dir=None)
    bridge.responses["get_editor_state"] = state
    result = await mcp.call_tool("set_track_map", {"recording": "4", "tracks": [{"index": 1, "role": "mix"}]})
    assert result.is_error and "Lưu project trước" in text_of(result)


async def test_get_job_and_cancel_job_tools(mcp, tmp_path, monkeypatch):
    monkeypatch.setenv("CONTEXTCUT_DATA_DIR", str(tmp_path / "data"))
    from contextcut_ai import jobs
    job = jobs.submit("sleep", {"seconds": 30})
    out = json.loads(text_of(await mcp.call_tool("get_job", {"job_id": job["id"]})))
    assert out["id"] == job["id"] and out["status"] in {"queued", "running"}
    listing = json.loads(text_of(await mcp.call_tool("get_job", {})))
    assert [j["id"] for j in listing["jobs"]] == [job["id"]]
    out = json.loads(text_of(await mcp.call_tool("cancel_job", {"job_id": job["id"]})))
    assert out["status"] in {"queued", "running", "cancelled"}
    missing = await mcp.call_tool("get_job", {"job_id": "khong-co"})
    assert missing.is_error and "khong-co" in text_of(missing)


@pytest.fixture
def submitted(monkeypatch):
    """jobs.submit giả: ghi lại tham số thay vì chạy worker ASR thật."""
    from contextcut_ai import jobs
    calls = []

    def fake_submit(kind, params):
        calls.append((kind, params))
        return {"id": "transcribe-1", "kind": kind, "status": "queued", "stage": "đang khởi động worker"}

    monkeypatch.setattr(jobs, "submit", fake_submit)
    monkeypatch.setattr(jobs, "recent", lambda limit=10: [])
    return calls


async def test_transcribe_unsaved_project(mcp, bridge, submitted):
    state = copy.deepcopy(EDITOR_STATE)
    state["project"].update(path=None, companion_dir=None)
    bridge.responses["get_editor_state"] = state
    result = await mcp.call_tool("transcribe", {"recording": "4"})
    assert result.is_error and "Lưu project trước" in text_of(result) and submitted == []


async def test_transcribe_submits_voice_tracks(mcp, bridge, tmp_path, obs_mkv, submitted):
    companion = tmp_path / "P.contextcut"
    with_companion(bridge, companion, obs_mkv)
    out = json.loads(text_of(await mcp.call_tool("transcribe", {"recording": "4", "prompt": "Minecraft, creeper"})))
    assert out["job_id"] == "transcribe-1" and out["status"] == "queued"
    [(kind, params)] = submitted
    assert kind == "transcribe"
    assert [(t["index"], t["speaker"]) for t in params["tracks"]] == [(2, "Nhan"), (3, "bạn bè")]
    assert params["recording"]["id"] == "4" and params["recording"]["path"] == obs_mkv.as_posix()
    assert params["companion"] == companion.as_posix() and params["language"] == "vi"
    assert params["model"] == asr.default_model() and params["prompt"] == "Minecraft, creeper"
    one = await mcp.call_tool("transcribe", {"recording": "4", "tracks": [3]})
    assert [t["index"] for t in submitted[-1][1]["tracks"]] == [3], text_of(one)
    bad = await mcp.call_tool("transcribe", {"recording": "4", "tracks": [9]})
    assert bad.is_error and "9" in text_of(bad)


async def test_transcribe_cached(mcp, bridge, tmp_path, obs_mkv, submitted):
    companion = tmp_path / "P.contextcut"
    with_companion(bridge, companion, obs_mkv)
    rec = trackmap.RecordingStore(companion).ensure("4", obs_mkv)
    folder = companion / "analysis" / rec["file_hash"]
    folder.mkdir(parents=True)
    model = asr.default_model()
    (folder / "transcript.json").write_text(json.dumps({
        "schema": "contextcut-transcript/1", "language": "vi", "model": model,
        "tracks": [{"index": 2, "model": model, "language": "vi"}, {"index": 3, "model": model, "language": "vi"}],
        "segments": [{"track": 2, "speaker": "Nhan", "start": 1.0, "end": 2.0, "text": "ủa", "words": []}]}),
        encoding="utf-8")
    out = json.loads(text_of(await mcp.call_tool("transcribe", {"recording": "4"})))
    assert out["cached"] is True and out["segments"] == 1 and submitted == []
    await mcp.call_tool("transcribe", {"recording": "4", "force": True})
    assert len(submitted) == 1


async def test_transcribe_missing_model_asks_first(mcp, bridge, tmp_path, obs_mkv, submitted, monkeypatch):
    pytest.importorskip("huggingface_hub")
    monkeypatch.setenv("CONTEXTCUT_MODELS", str(tmp_path / "trống"))
    with_companion(bridge, tmp_path / "P.contextcut", obs_mkv)
    result = await mcp.call_tool("transcribe", {"recording": "4", "model": "phowhisper-large"})
    assert result.is_error and "3,1 GB" in text_of(result) and "hỏi" in text_of(result).lower()
    assert submitted == []


def write_transcript(companion: Path, obs_mkv: Path) -> None:
    rec = trackmap.RecordingStore(companion).ensure("4", obs_mkv)
    folder = companion / "analysis" / rec["file_hash"]
    folder.mkdir(parents=True, exist_ok=True)
    w = lambda t, a, b, p=0.9: {"w": t, "start": a, "end": b, "p": p}  # noqa: E731
    (folder / "transcript.json").write_text(json.dumps({
        "schema": "contextcut-transcript/1", "language": "vi", "model": "large-v3",
        "tracks": [{"index": 2, "model": "large-v3", "language": "vi"}, {"index": 3, "model": "large-v3", "language": "vi"}],
        "segments": [
            {"track": 2, "speaker": "Nhan", "start": 2.5, "end": 3.0, "text": "Ủa alo?", "flags": [],
             "words": [w("Ủa", 2.5, 2.7), w("alo?", 2.7, 3.0, 0.3)]},
            {"track": 3, "speaker": "bạn bè", "start": 4.0, "end": 4.5, "text": "Nghe nè.", "flags": [],
             "words": [w("Nghe", 4.0, 4.2), w("nè.", 4.2, 4.5)]},
            {"track": 2, "speaker": "Nhan", "start": 8.0, "end": 8.5, "text": "Ngoài clip", "flags": [],
             "words": [w("Ngoài", 8.0, 8.2), w("clip", 8.2, 8.5)]}]}, ensure_ascii=False), encoding="utf-8")


async def test_get_transcript_tool(mcp, bridge, tmp_path, obs_mkv):
    companion = tmp_path / "P.contextcut"
    with_companion(bridge, companion, obs_mkv)
    missing = await mcp.call_tool("get_transcript", {})
    assert missing.is_error and "transcribe" in text_of(missing)
    write_transcript(companion, obs_mkv)
    out = json.loads(text_of(await mcp.call_tool("get_transcript", {})))
    # clip 42/43: timeline 0–300 ← nguồn 120–420 (60 fps); 2,5 s = frame nguồn 150 → timeline 30
    assert [(s["speaker"], s["start_f"], s["end_f"], s["text"]) for s in out["segments"]] == [
        ("Nhan", 30, 60, "Ủa alo?"), ("bạn bè", 120, 150, "Nghe nè.")]
    assert out["segments"][0]["tc"] == "00:00.30" and out["segments"][0]["low_conf"] == ["alo?"]
    assert "words" not in out["segments"][0] and out["next_cursor"] is None and out["on"] == "timeline"
    src = json.loads(text_of(await mcp.call_tool("get_transcript", {"on": "source", "words": True})))
    assert [s["start_f"] for s in src["segments"]] == [150, 240, 480]
    assert src["segments"][0]["words"][1] == {"w": "alo?", "start_f": 162, "end_f": 180, "p": 0.3}
    disc = json.loads(text_of(await mcp.call_tool("get_transcript", {"track": "discord"})))
    assert [s["text"] for s in disc["segments"]] == ["Nghe nè."]
    nhan = json.loads(text_of(await mcp.call_tool("get_transcript", {"track": "Nhan", "on": "source"})))
    assert len(nhan["segments"]) == 2
    ranged = json.loads(text_of(await mcp.call_tool("get_transcript", {"start_f": 100, "end_f": 200})))
    assert [s["text"] for s in ranged["segments"]] == ["Nghe nè."]
    page1 = json.loads(text_of(await mcp.call_tool("get_transcript", {"limit": 1})))
    assert len(page1["segments"]) == 1 and page1["next_cursor"]
    page2 = json.loads(text_of(await mcp.call_tool("get_transcript", {"limit": 1, "cursor": page1["next_cursor"]})))
    assert page2["segments"][0]["text"] == "Nghe nè." and page2["next_cursor"] is None


def applied_ops(bridge) -> list[dict]:
    [(_, params)] = [c for c in bridge.calls if c[0] == "apply_operations"]
    return params


async def test_add_subtitles_preview_and_apply(mcp, bridge, tmp_path, obs_mkv):
    companion = tmp_path / "P.contextcut"
    with_companion(bridge, companion, obs_mkv)
    write_transcript(companion, obs_mkv)
    preview = json.loads(text_of(await mcp.call_tool("add_subtitles", {"preview": True})))
    # 60 fps: câu 30 frame (0,5 s) kéo tới 0,6 s = 36 frame
    assert [(l["start_f"], l["end_f"], l["text"], l["speaker"]) for l in preview["lines"]] == [
        (30, 66, "Ủa alo?", "Nhan"), (120, 156, "Nghe nè.", "bạn bè")]
    assert preview["lines"][0]["tc"] == "00:00.30"
    assert not [c for c in bridge.calls if c[0] == "apply_operations"]
    out = json.loads(text_of(await mcp.call_tool("add_subtitles", {})))
    assert out["batch_id"] == "b-1" and out["lines"] == 2
    params = applied_ops(bridge)
    assert params["base_revision"] == 1873402 and params["label"].startswith("AI: phụ đề")
    clear, add = params["ops"]
    assert clear == {"type": "clear_subtitles", "start_f": 0, "end_f": 216000, "reason": "thay phụ đề cũ trong khoảng"}
    assert add["type"] == "add_subtitles"
    assert add["items"] == [{"start_f": 30, "end_f": 66, "text": "Ủa alo?", "speaker": "Nhan"},
                            {"start_f": 120, "end_f": 156, "text": "Nghe nè.", "speaker": "bạn bè"}]


async def test_add_subtitles_range_speakers_and_append(mcp, bridge, tmp_path, obs_mkv):
    companion = tmp_path / "P.contextcut"
    with_companion(bridge, companion, obs_mkv)
    write_transcript(companion, obs_mkv)
    await mcp.call_tool("add_subtitles", {"start_f": 100, "end_f": 200, "replace": False, "label": "AI: phụ đề đoạn 2"})
    params = applied_ops(bridge)
    assert params["label"] == "AI: phụ đề đoạn 2"
    [add] = params["ops"]
    assert [i["text"] for i in add["items"]] == ["Nghe nè."]
    bridge.calls.clear()
    await mcp.call_tool("add_subtitles", {"speakers": ["discord"]})
    assert [i["text"] for i in applied_ops(bridge)["ops"][1]["items"]] == ["Nghe nè."]
    empty = await mcp.call_tool("add_subtitles", {"start_f": 1000, "end_f": 2000})
    assert empty.is_error and "Không có lời thoại" in text_of(empty)


async def test_caption_enriched_with_speaker_style_and_snapped(mcp, bridge, tmp_path, obs_mkv):
    companion = tmp_path / "P.contextcut"
    with_companion(bridge, companion, obs_mkv)
    write_transcript(companion, obs_mkv)
    op = {"type": "caption", "text": "ủa alo", "speaker": "Nhan", "start_f": 27, "end_f": 63}
    result = await mcp.call_tool("apply_operations", {"ops": [op], "base_revision": 1873402, "label": "AI: câu đắt"})
    out = json.loads(text_of(result))
    [sent] = applied_ops(bridge)["ops"]
    assert sent == {"type": "caption", "text": "ủa alo", "speaker": "Nhan", "start_f": 30, "end_f": 60,
                    "color": "#FFFFFF", "uppercase": True, "label": False}
    assert out["snapped"] == [{"op_index": 0, "start_f": [27, 30], "end_f": [63, 60]}]
    bridge.calls.clear()
    keep = {"type": "caption", "text": "x", "speaker": "Sang", "start_f": 27, "end_f": 63, "snap": False, "color": "#00FF00"}
    await mcp.call_tool("validate_operations", {"ops": [keep]})
    [(_, params)] = [c for c in bridge.calls if c[0] == "validate_operations"]
    assert params["ops"] == [{"type": "caption", "text": "x", "speaker": "Sang", "start_f": 27, "end_f": 63,
                              "color": "#00FF00", "uppercase": True, "label": False}]


async def test_caption_without_transcript_still_styled(mcp, bridge, tmp_path):
    with_companion(bridge, tmp_path / "P.contextcut")
    op = {"type": "caption", "text": "ừ", "speaker": "bạn bè", "start_f": 5, "end_f": 50}
    result = await mcp.call_tool("apply_operations", {"ops": [op], "base_revision": 1, "label": "AI: x"})
    assert not result.is_error
    [sent] = applied_ops(bridge)["ops"]
    assert sent["color"] == "#FFD400" and (sent["start_f"], sent["end_f"]) == (5, 50)


async def test_get_job_wait_returns_when_done(mcp, tmp_path, monkeypatch):
    monkeypatch.setenv("CONTEXTCUT_DATA_DIR", str(tmp_path / "data"))
    import time
    from contextcut_ai import jobs
    job = jobs.submit("sleep", {"seconds": 1.0})
    quick = json.loads(text_of(await mcp.call_tool("get_job", {"job_id": job["id"]})))
    assert quick["status"] in {"queued", "running"}
    start = time.monotonic()
    done = json.loads(text_of(await mcp.call_tool("get_job", {"job_id": job["id"], "wait_s": 30})))
    assert done["status"] == "done" and time.monotonic() - start < 25
    bad = await mcp.call_tool("get_job", {"job_id": job["id"], "wait_s": 120})
    assert bad.is_error


# --- P2b: xem hình (Task 14) ---------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def code60(tmp_path_factory) -> Path:
    """Video mã số frame 60 fps, 240 frame (p2_fixture.read_frame_code đọc lại số frame từ ảnh)."""
    return make_frame_code_video(tmp_path_factory.mktemp("code") / "Mã frame 60.mp4", fps=60, seconds=4)


def vision_project(bridge, tmp_path, rec_path: Path, fps: int = 60, saved: bool = True) -> Path:
    state = copy.deepcopy(EDITOR_STATE)
    companion = tmp_path / "Bắt Nạt Hải Sản.contextcut"
    if saved:
        state["project"]["companion_dir"] = companion.as_posix()
    else:
        state["project"].update(path=None, companion_dir=None)
    state["profile"]["fps"] = {"num": fps, "den": 1}
    bridge.responses["get_editor_state"] = state
    recs = copy.deepcopy(RECORDINGS)
    recs["recordings"][0]["path"] = rec_path.as_posix()
    bridge.responses["list_recordings"] = recs
    return companion


def split_content(result) -> tuple[dict, list]:
    """Kết quả tool xem hình: một khối chữ JSON rồi các ảnh."""
    assert not result.is_error, result.content[0].text
    text, *images = result.content
    return json.loads(text.text), images


def image_frame_code(image, tmp_path: Path) -> int:
    assert image.type == "image" and image.mime_type == "image/jpeg"
    path = tmp_path / f"img-{len(list(tmp_path.glob('img-*')))}.jpg"
    path.write_bytes(base64.b64decode(image.data))
    return read_frame_code(path)


async def test_source_frames_returns_images_and_paths(mcp, bridge, tmp_path, code60):
    companion = vision_project(bridge, tmp_path, code60)
    out, images = split_content(await mcp.call_tool("get_source_frames", {"recording": "4", "frames": [200, 3, 61]}))
    assert out["on"] == "source" and out["source_fps"] == "60"
    assert [(f["f"], f["src_f"]) for f in out["frames"]] == [(200, 200), (3, 3), (61, 61)]
    assert [image_frame_code(img, tmp_path) for img in images] == [200, 3, 61]
    for f in out["frames"]:
        path = Path(f["path"])
        assert path.exists() and companion in path.parents and path.parent.name == "frames"
    assert out["frames"][1]["tc"] == "00:00.03"


async def test_source_frames_project_fps_differs(mcp, bridge, tmp_path, code60):
    vision_project(bridge, tmp_path, code60, fps=25)
    out, images = split_content(await mcp.call_tool("get_source_frames", {"recording": "4", "frames": [2, 50],
                                                                           "width": 256}))
    assert [image_frame_code(img, tmp_path) for img in images] == [5, 120]  # floor(f·60/25 + 0.5), như melt


async def test_source_frames_timeline_mapping(mcp, bridge, tmp_path, code60):
    vision_project(bridge, tmp_path, code60)  # clip 42: timeline 0…300 = nguồn 120…420
    out, images = split_content(await mcp.call_tool("get_source_frames", {"recording": "4", "frames": [10, 100],
                                                                           "on": "timeline"}))
    assert [(f["f"], f["src_f"]) for f in out["frames"]] == [(10, 130), (100, 220)]
    assert [image_frame_code(img, tmp_path) for img in images] == [130, 220]


async def test_source_frames_off_timeline_error_per_frame(mcp, bridge, tmp_path, code60):
    vision_project(bridge, tmp_path, code60)
    out, images = split_content(await mcp.call_tool("get_source_frames", {"recording": "4", "frames": [10, 400, 5000],
                                                                           "on": "timeline"}))
    assert len(images) == 1 and image_frame_code(images[0], tmp_path) == 130
    assert "không có trên timeline" in out["frames"][1]["error"]
    out, images = split_content(await mcp.call_tool("get_source_frames", {"recording": "4", "frames": [5000]}))
    assert images == [] and "5000" in out["frames"][0]["error"]


async def test_source_frames_limits(mcp, bridge, tmp_path, code60):
    vision_project(bridge, tmp_path, code60)
    bridge.calls.clear()
    too_many = await mcp.call_tool("get_source_frames", {"recording": "4", "frames": list(range(13))})
    assert too_many.is_error and bridge.calls == []
    too_wide = await mcp.call_tool("get_source_frames", {"recording": "4", "frames": [1], "width": 4000})
    assert too_wide.is_error


async def test_source_frames_rejects_loading_or_audio_only(mcp, bridge, tmp_path, code60):
    vision_project(bridge, tmp_path, code60)
    bridge.responses["list_recordings"]["recordings"][0]["ready"] = False
    loading = await mcp.call_tool("get_source_frames", {"recording": "4", "frames": [1]})
    assert loading.is_error and "đang nạp" in loading.content[0].text
    audio = tmp_path / "chỉ tiếng.wav"
    subprocess.run([paths.find_tool("ffmpeg"), "-v", "error", "-f", "lavfi", "-i", "sine=d=1", str(audio)], check=True)
    vision_project(bridge, tmp_path, audio)
    no_video = await mcp.call_tool("get_source_frames", {"recording": "4", "frames": [1]})
    assert no_video.is_error and "không có hình" in no_video.content[0].text


async def test_contact_sheet_tool(mcp, bridge, tmp_path, code60):
    vision_project(bridge, tmp_path, code60)
    out, images = split_content(await mcp.call_tool("get_contact_sheet", {"recording": "4", "start_f": 0, "end_f": 240}))
    assert len(images) == 1 and out["size"] == [1024, 432]
    assert [(c["cell"], c["row"], c["col"]) for c in out["cells"][:5]] == [(1, 1, 1), (2, 1, 2), (3, 1, 3), (4, 1, 4),
                                                                           (5, 2, 1)]
    sheet = tmp_path / "sheet.jpg"
    sheet.write_bytes(base64.b64decode(images[0].data))
    assert read_frame_code(sheet, crop=(512, 144, 256, 144)) == out["cells"][6]["src_f"]
    assert Path(out["path"]).exists()
    small = await mcp.call_tool("get_contact_sheet", {"recording": "4", "start_f": 0, "end_f": 240, "cols": 2, "rows": 1})
    assert split_content(small)[0]["size"] == [512, 144]


async def test_vision_unsaved_project_uses_data_dir(mcp, bridge, tmp_path, code60, monkeypatch):
    monkeypatch.setenv("CONTEXTCUT_DATA_DIR", str(tmp_path / "data"))
    vision_project(bridge, tmp_path, code60, saved=False)
    out, images = split_content(await mcp.call_tool("get_source_frames", {"recording": "4", "frames": [7]}))
    assert len(images) == 1
    assert (tmp_path / "data" / "frames") in Path(out["frames"][0]["path"]).parents
    assert not (tmp_path / "Bắt Nạt Hải Sản.contextcut").exists()
