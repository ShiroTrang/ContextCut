# Bàn giao P2a — Phiên âm và phụ đề

22/10/2026 · kế hoạch: `docs/plans/P2.md` (P2a = Task 1–11) · giao thức: `docs/protocol.md` §8.5, §8.9 · số đo: `docs/measurements/P2a-asr.md` · session P2a (Claude Opus 5.5). **Code xong, cổng xong trừ phần cần dữ liệu thật của Nhan** (bản ghi OBS 5 track + mốc gõ tay) và review toàn nhánh.

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

## Bằng chứng cổng

Project thử: fixture `p1-gate` + đoạn 2 phút cắt (`-c copy`) từ bản ghi một track `C:\Users\VuNhan\Videos\2026-07-10 00-24-05.mkv` (230–350 s), **tắt proxy tự động** (`kdenlive:docproperties.generateproxy` = 0, xem Bẫy). Server MCP cho `claude -p` chạy bằng `uv run --no-sync` (`--mcp-config`).

| Kiểm | Kết quả |
| --- | --- |
| Claude Code phiên mới, transcript có sẵn: "Thêm phụ đề cho đoạn 00:10 đến 01:10…" | `get_editor_state` → tự đổi ra frame 250–1750 → `get_transcript` → `add_subtitles` preview → apply **một đợt** "AI: thêm phụ đề 00:10–01:10", 19 dòng, nhắc Ctrl+Z (7 lượt, 0,24 USD). Phụ đề hiện trên track phụ đề trong app (ảnh chụp) |
| Claude Code phiên mới, từ đầu: "Phiên âm lại … bằng model large-v3, đợi xong rồi thêm phụ đề cho cả đoạn đó" | `list_recordings` → `transcribe(model=large-v3, force)` → `get_job(wait_s=50)` một lần (xong sau 24 s) → `add_subtitles` 37 dòng **một đợt** → nhắc Ctrl+Z (10 lượt, 0,21 USD, 61 s) |
| Job sống qua client: lượt trước agent (chưa có `wait_s`) hẹn giờ rồi thoát | worker vẫn chạy xong: `parakeet-ctc-vi` CUDA 61,6 s, 182 từ, VRAM đỉnh 4236 MiB |
| Lưu (Ctrl+S) → `.kdenlive` + `p1-gate.kdenlive.ass` (37 dòng `Dialogue` tiếng Việt) | ✔ |
| `melt` dựng khung 70 từ file đã lưu | chữ "Là mày phải nhìn lên cái bảng đó," ở đáy khung, dấu đúng (style mặc định của Kdenlive, chữ nhỏ) |
| Đóng app, mở lại project | `list_subtitles` 37 dòng, `modified: false` |
| Test | unit 138 xanh; sống 38/38 trên `p1-gate` sạch, 3 lượt liền. Một lần app crash giữa lượt chạy cả bộ (quanh `test_undo_batch_only_top`), không tái hiện được trong 3 lượt sau (có log stderr) |
| VRAM | đỉnh toàn card 3,4–4,5 GB (< 6 GB) ở mọi model; job thật 34 phút audio `large-v3` 375 s |

**Còn chờ Nhan (cổng chính):** bản ghi OBS 5 track 10–20 phút + 3–5 phút mốc gõ tay. Cách chạy:

```powershell
# 1. Kiểm 5 stream + tên (Mic/Discord…): ffprobe -v error -show_entries stream=index,codec_type:stream_tags=title -of compact "<file>.mkv"
# 2. Đoạn để gõ mốc (index 2 = Mic; chọn 3–5 phút nói nhiều)
uv run --directory contextcut-ai --no-sync python tools/make_calibration.py --recording "<file>.mkv" --index 2 --start <s> --end <s>
# 3. Nhan sửa lyrics.txt, gõ mốc trong Lyric Calibrator (Đo trễ + "Giữ phím = độ dài chữ"), lưu bản
# 4. Đo 3 model, có cuối từ
uv run --directory contextcut-ai --no-sync python tools/asr_eval.py --calibration "D:/SongMV/tools/lyric_calibrator/songs/p2a-mic/versions/<bản>.json" --audio "D:/SongMV/tools/lyric_calibrator/songs/p2a-mic/audio.wav" --ends --out <kết quả>.json
```

Đạt khi trung vị lệch đầu **và** cuối câu (sau tinh chỉnh) < 100 ms; ghi WER 3 model vào `docs/measurements/P2a-asr.md`, sửa `asr.PREFERENCE` nếu cần. Rồi thử `transcribe` cả hai track Mic + Discord của bản ghi đó qua agent.

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
- **Kdenlive treo khi tạo proxy cho bản ghi HEVC của OBS** (gặp với file 34 phút và cả đoạn 2 phút): luồng giao diện quay CPU 100% mãi trong `ProxyTask::processLogInfo()` (gdb), kể cả khi không còn tiến trình ffmpeg con; cầu nối hết giờ, app "Not Responding". Nguyên nhân nghi: `src/jobs/proxytask.cpp` tạo `QProcess` trong luồng worker nhưng nối `readyReadStandardError` vào `ProxyTask` (sống ở luồng giao diện) → `processLogInfo` chạy ở luồng giao diện, đọc chéo luồng và nối `m_logDetails` liên tục. Tạm tránh: tắt proxy tự động của project (`generateproxy` = 0). **Phải sửa trước khi Nhan dùng bản ghi thật** (task riêng).
- Đừng `InvokePattern` nút Save bằng UIA khi có thể hiện hộp modal (gọi UIA kẹt trong hộp). Hộp KMessageBox không thấy qua UIA; `PostMessage` Enter không ăn khi app đang bận.
- Heredoc bash chứa Python có `\1`/`\s` dễ hỏng (thành ký tự điều khiển): ghi script bằng file.
- `claude -p` cần `--mcp-config` đường dẫn Windows (`cygpath -m`). Ở chế độ `-p` agent có thể "hẹn giờ quay lại" rồi thoát khi job chưa xong: `get_job(wait_s≤55)` để chờ trong một lần gọi.
- Lưu bằng SendKeys Ctrl+S sau `SetForegroundWindow`; hộp "Information" (lưu lần đầu project cũ) đóng bằng SendKeys Enter sau `SetForegroundWindow` vào hộp đó (`gate/save.ps1` trong scratchpad của session). Đóng app đã lưu: `PostMessage WM_CLOSE`.

## Việc tiếp

1. Nhan: bản ghi OBS 5 track + mốc gõ tay → chạy cổng (lệnh ở trên), chốt model mặc định.
2. Sửa treo proxy HEVC của Kdenlive (xem Bẫy) — task riêng, trước khi dùng bản ghi thật dài.
3. Nhắc Nhan chạy `uv run --directory contextcut-ai python scripts/register_clients.py` (skill đã cài vẫn là bản P1b: agent báo "Skill không load được") và đóng client trước `uv sync`.
4. Review toàn nhánh P2a (chưa làm) trước khi push; hỏi Nhan trước khi push.
5. P2b theo `docs/plans/P2.md`.
