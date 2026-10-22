# Bàn giao P2a — Phiên âm và phụ đề

22/10/2026 · kế hoạch: `docs/plans/P2.md` (P2a = Task 1–11) · giao thức: `docs/protocol.md` §8.5, §8.9 · số đo: `docs/measurements/P2a-asr.md` · session P2a (Claude Opus 5.5). **Dừng giữa Task 11 vì hết hạn mức**: code xong, cổng làm một phần.

## Đã xong (commit trên `main`, chưa push)

| Việc | Ở đâu |
| --- | --- |
| `track_map` theo bản ghi (ffprobe, sơ đồ OBS §8.1, tên stream thắng thứ tự, file 1 track = `mix`), `recordings.json`, tool `set_track_map`, `list_recordings` gắn `track_map` | `contextcut-ai/src/contextcut_ai/{paths,media,trackmap}.py` |
| Job nền: file JSON `%LOCALAPPDATA%\contextcut\jobs`, worker tách rời (`python -m contextcut_ai.analysis.worker`), khoá GPU toàn máy `gpu.lock`, pid chết → `failed`, huỷ; tool `get_job`, `cancel_job` | `jobs.py`, `analysis/worker.py` |
| Extra `analysis` (faster-whisper 1.2.1, CT2 4.8.3, cuBLAS/cuDNN PyPI) và `parakeet` (NeMo 2.6.2 + torch 2.9.1 cu126); backend `large-v3`, `phowhisper-large` (chuyển tại máy: `tools/convert_phowhisper.py`), `parakeet-ctc-vi` | `pyproject.toml`, `analysis/{asr,gpu}.py` |
| `transcribe` (job): VAD → chunk cắt ở khoảng lặng dài nhất → ASR → chạy tiếp từ chunk đã xong → lọc ảo giác → tinh chỉnh đầu/cuối câu theo năng lượng → `transcript.json` (giây nguồn); tool `transcribe`, `get_transcript` (frame timeline qua clip, hoặc nguồn; phân trang) | `analysis/{vad,refine,transcribe}.py`, `transcript.py` |
| C++: kiểu tham số `items`, op `add_subtitles`/`clear_subtitles` (track phụ đề Kdenlive, một bước undo), `cut_range` dời/thu/xoá phụ đề, `caption` thêm `color`/`uppercase`/`label`, method `list_subtitles` | `src/contextcut/ops/*`, `model/editorreader.*` |
| Tool `add_subtitles` (≤ 42 ký tự, ngắt ở chỗ nghỉ / đầu câu ASR, chồng lời → cắt hoặc gộp hai hàng, ≥ 0,6 s), op `caption` có `speaker` tự điền style (`speakers.json`) và bắt mép về đầu/cuối từ | `captions.py`, `mcp_server.py` |
| Đo ASR: `tools/asr_eval.py`, `tools/make_calibration.py`; mặc định tạm `parakeet-ctc-vi` | `docs/measurements/P2a-asr.md` |
| Guide (`workflow`, `software`, `instructions`, `patterns/subtitles`), `SKILL.md`/`AGENTS-snippet.md` sinh lại, README | `contextcut-ai/guide/`, `skills/` |

Test: `uv run --directory contextcut-ai --no-sync pytest` → 174 xanh trừ `test_live.py::test_read_tools_over_stdio` (môi trường, xem Bẫy); sống trên `p1-gate`: 7/7 phụ đề + 31 op P1 xanh.

## Bằng chứng cổng (một phần)

- **Claude Code phiên mới** (`claude -p`, `claude-sonnet-4-6`, server chạy `uv run --no-sync`): "Thêm phụ đề cho đoạn 00:10 đến 01:10…" → `get_editor_state` → tự đổi ra frame 250–1750 → `get_transcript` → `add_subtitles` preview → apply **một đợt** "AI: thêm phụ đề 00:10–01:10", 19 dòng, nhắc Ctrl+Z (7 lượt, 0,24 USD). Ảnh app: phụ đề hiện trên track phụ đề (đã chụp trong scratchpad của session).
- VRAM đỉnh toàn card: 3,4–4,5 GB (< 6 GB) ở mọi model; job thật 34 phút audio `large-v3` 375 s.
- **Chưa làm:** lưu `.kdenlive` rồi mở lại + dựng khung bằng `melt` (lần lưu đầu bị treo app, xem Bẫy); e2e có cả `transcribe` từ agent; **cổng chính chờ dữ liệu của Nhan**: bản ghi OBS 5 track 10–20 phút + 3–5 phút mốc gõ tay → `make_calibration.py` → Lyric Calibrator → `asr_eval.py --ends` (trung vị lệch đầu/cuối câu < 100 ms, WER 3 model), rồi chốt `asr.PREFERENCE`.

## Lệch thiết kế / kế hoạch

1. Thêm ứng viên thứ ba **Parakeet** (Nhan yêu cầu, đồng ý tải ~7 GB tổng cả thư viện).
2. Tinh chỉnh ranh giới chạy trong job (cần audio), lưu `raw_start/raw_end`; job có tham số `vad` (`silero`/`energy`).
3. Test sống phụ đề chạy trên `p1-gate` thay vì project `p2-gate` riêng.
4. Mặc định model theo thứ tự đo được và cái có trên máy (`asr.default_model()`), không cố định.
5. Validator §8.6 (cắt giữa từ) chưa làm → P3.

## Bẫy mới

- `uv sync`/`uv run` (không `--no-sync`) phải cài lại project sau khi `pyproject.toml` đổi; Windows khoá `contextcut-ai.exe` khi có client MCP đang chạy server từ repo → lỗi "failed to remove file". Đóng mọi client rồi `uv sync --directory contextcut-ai --extra analysis --extra parakeet` một lần; tạm thời `--no-install-project --inexact` và chạy test bằng `uv run --no-sync`.
- NeMo: `restore_from(map_location="cuda")` giữ hai bản trọng số (4,7 GB) → card 6 GB tràn RAM chung, chậm hàng trăm lần. Nạp CPU rồi `.to("cuda")`.
- PhoWhisper qua CT2 phải `without_timestamps=True` + `int8_float16` (không thì 63 s cho 60 s audio, 5,6 GB VRAM).
- **Kdenlive tạo proxy cho bản ghi HEVC dài** (`ProxyTask::processLogInfo` nối toàn bộ stderr ffmpeg) làm luồng giao diện quay CPU 100%; trong lúc có hộp thoại modal (lưu lần đầu → hộp "Information") app "Not Responding", cầu nối hết giờ. Gặp khi nhập file 34 phút. Cần xem lại với bản ghi 2 giờ của Nhan (tắt auto-proxy / proxy bằng NVENC) — P2c hoặc P5.
- Đừng `InvokePattern` nút Save bằng UIA khi có thể hiện hộp modal (gọi UIA kẹt trong hộp). Hộp KMessageBox không thấy qua UIA; `PostMessage` Enter không ăn khi app đang bận.
- Heredoc bash chứa Python có `\1`/`\s` dễ hỏng (thành ký tự điều khiển): ghi script bằng file.
- `claude -p` cần `--mcp-config` đường dẫn Windows (`cygpath -m`).

## Việc tiếp

1. Nhan: bản ghi OBS 5 track + mốc gõ tay → chạy cổng (lệnh ở `docs/measurements/P2a-asr.md`), chốt model mặc định.
2. Lưu/mở lại project có phụ đề + `melt` dựng khung (dùng project nhỏ, không file HEVC dài; lưu bằng SendKeys Ctrl+S, hộp "Information" → Enter).
3. Nhắc Nhan chạy `uv run --directory contextcut-ai python scripts/register_clients.py` (skill đã cài vẫn là bản P1b) và đóng client trước `uv sync`.
4. Review toàn nhánh P2a (chưa làm) trước khi push; hỏi Nhan trước khi push.
5. P2b theo `docs/plans/P2.md`.
