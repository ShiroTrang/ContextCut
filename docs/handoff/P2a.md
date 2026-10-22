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
- **Kdenlive treo khi tạo proxy cho bản ghi HEVC của OBS** (gặp với file 34 phút và cả đoạn 2 phút): luồng giao diện quay CPU 100% mãi trong `ProxyTask::processLogInfo()` (gdb), kể cả khi không còn tiến trình ffmpeg con; cầu nối hết giờ, app "Not Responding". Nguyên nhân nghi: `src/jobs/proxytask.cpp` tạo `QProcess` trong luồng worker nhưng nối `readyReadStandardError` vào `ProxyTask` (sống ở luồng giao diện) → `processLogInfo` chạy ở luồng giao diện, đọc chéo luồng và nối `m_logDetails` liên tục. Tạm tránh: tắt proxy tự động của project (`generateproxy` = 0). **Phải sửa trước khi Nhan dùng bản ghi thật** (task riêng). → **Đã sửa**, xem mục cuối.
- Đừng `InvokePattern` nút Save bằng UIA khi có thể hiện hộp modal (gọi UIA kẹt trong hộp). Hộp KMessageBox không thấy qua UIA; `PostMessage` Enter không ăn khi app đang bận.
- Heredoc bash chứa Python có `\1`/`\s` dễ hỏng (thành ký tự điều khiển): ghi script bằng file.
- `claude -p` cần `--mcp-config` đường dẫn Windows (`cygpath -m`). Ở chế độ `-p` agent có thể "hẹn giờ quay lại" rồi thoát khi job chưa xong: `get_job(wait_s≤55)` để chờ trong một lần gọi.
- Lưu bằng SendKeys Ctrl+S sau `SetForegroundWindow`; hộp "Information" (lưu lần đầu project cũ) đóng bằng SendKeys Enter sau `SetForegroundWindow` vào hộp đó (`gate/save.ps1` trong scratchpad của session). Đóng app đã lưu: `PostMessage WM_CLOSE`.

## Việc tiếp

1. Nhan: bản ghi OBS 5 track + mốc gõ tay → chạy cổng (lệnh ở trên), chốt model mặc định.
2. ~~Sửa treo proxy HEVC của Kdenlive~~ — xong. ~~Deadlock cầu nối khi clip đang nạp~~ — xong (hai mục cuối).
3. Nhắc Nhan chạy `uv run --directory contextcut-ai python scripts/register_clients.py` (skill đã cài vẫn là bản P1b: agent báo "Skill không load được") và đóng client trước `uv sync`.
4. Review toàn nhánh P2a (chưa làm) trước khi push; hỏi Nhan trước khi push.
5. P2b theo `docs/plans/P2.md`.

## Sửa treo proxy HEVC (22/10/2026, session riêng)

**Nguyên nhân (đã chứng minh):** `ProxyTask::run()` tạo `QProcess` và `waitForFinished()` trong luồng worker của `QThreadPool`, nhưng `ProxyTask` sống ở luồng giao diện, nên `connect(readyReadStandardError → processLogInfo)` (AutoConnection) thành queued: `processLogInfo` chạy ở luồng giao diện và gọi `readAllStandardError()` trong khi worker đang ghi vào cùng bộ đệm đọc của `QProcess` (`QRingBuffer`, không thread-safe). Bộ đệm hỏng → luồng giao diện kẹt trong `readAll` (vòng lặp/memmove trên dữ liệu rác) hoặc crash; worker sau đó chờ luồng giao diện (`BlockingQueuedConnection`) nên treo mãi kể cả khi ffmpeg đã thoát. Xác suất tỉ lệ với lượng stderr: bản ghi dài (nhiều dòng `-stats`) hay gặp, đoạn ngắn hiếm. Upstream `master` (fetch 22/10/2026) chưa sửa; commit `8e15db3eb9` "Fix proxy crash…" (có trong 26.08.2) chuyển sang `m_jobProcess` nhưng vẫn để kết nối queued.

**Sửa:** thêm `Qt::DirectConnection` vào hai `connect` đó trong `src/jobs/proxytask.cpp` (nhánh MLT và ffmpeg) → `processLogInfo` chạy trong worker, bên trong `waitForFinished`, không còn hai luồng chạm một `QProcess`; tiến độ vẫn gửi về giao diện bằng `invokeMethod` queued. Giống `TranscodeTask` (nhánh ffmpeg) của upstream. Ghi `patches.md`.

**Bằng chứng** (build Release, máy Nhan, đoạn cắt `-c copy` từ `2026-07-10 00-24-05.mkv`, HEVC 1080p60; fixture `p1-gate` có `generateproxy` = 1):

| Kiểm | Trước sửa | Sau sửa |
| --- | --- | --- |
| Chương trình Qt độc lập mô phỏng `ProxyTask` (tiến trình con ghi 20 000 dòng stderr/vòng) | queued (như Kdenlive): 12/12 lần treo hoặc crash (heap corruption, access violation), thường ngay vòng 1–2; một vòng đọc ra 1 863 917 ký tự trong khi con chỉ ghi 1 860 000 | `DirectConnection`: 73 vòng (3 lần chạy) không treo; lượt cuối 30/30 vòng mỗi vòng đúng 1 860 000 ký tự |
| App, proxy mặc định, đoạn 2 phút / 3 đoạn 4 phút | không treo (race hiếm với ~2 dòng stderr/giây) | đoạn 4 phút: proxy 241,9 s hợp lệ, `bridge_probe check --quick` OK suốt |
| App, khuếch đại stderr (`-loglevel debug` trong `proxyparams`, ~1 500 dòng/giây) | **2/2 treo** sau 20–60 s: "Not Responding", cầu nối không bắt tay, CPU ~150 %, vẫn treo sau khi ffmpeg thoát; gdb thread 1: `ProxyTask::processLogInfo()` → Qt6Core | **2/2 chạy trơn**: proxy tạo xong và thay vào clip ("replace finished", 640×360, đủ độ dài), probe OK mỗi 15 s trong và sau khi proxy chạy |
| `uv run --directory contextcut-ai --no-sync pytest -m live` (p1-gate + bản ghi OBS giả + `stereo.flac` + đoạn HEVC, chạy **trong lúc** proxy khuếch đại đang tạo) | — | 38 xanh, 1 đỏ `test_read_tools_over_stdio` (môi trường như trên: `uv` không xoá được `contextcut-ai.exe` đang bị client MCP khoá) |

Tái hiện lại (khi merge bản KDE Gear mới, kiểm patch còn cần không): fixture `p1-gate`, sửa `kdenlive:docproperties.proxyparams` thêm ` -loglevel debug`, thêm `safeFFmpegParams=loglevel` vào nhóm `[env]` của `%LOCALAPPDATA%\contextcutrc` (không thì hộp cảnh báo tham số lạ khi mở project; gỡ dòng này sau khi thử), mở app với `-i "<đoạn HEVC chưa có proxy>"`. Proxy lưu ở `%LOCALAPPDATA%\contextcut\cache\proxy\<hash>.mov`; file đã có proxy thì không tạo lại — cắt đoạn mới (hash khác) cho mỗi lần thử.

**Phát hiện phụ (đã sửa ở mục sau):** cầu nối có thể **deadlock** luồng giao diện khi clip nạp lỗi. Gặp khi lỡ nhập cả thư mục repo (file `.a`, `.ico`…): luồng giao diện ở `EditorReader::sources` → `ProjectClip::frameDuration()` → `ClipController::getFramePlaytime()` chờ khoá producer, còn các `ClipLoadTask::abort()` trong worker chờ luồng giao diện qua `BlockingQueuedConnection`. Với dữ liệu thật có thể xảy ra khi agent gọi `list_sources` lúc một file hỏng/đang ghi dở đang nạp. Các job Kdenlive khác cùng kiểu kết nối với proxy ghi ở `patches.md` ("Biết trước").

Bẫy mới: `-i` của app với một mục rỗng (vd. `",a.mkv"`) nhập **cả thư mục hiện tại, đệ quy**; PowerShell 5.1 đọc `.ps1` UTF-8 không BOM như ANSI (tên có dấu trong script thành rác); chạy bản sao `stage` ở thư mục khác ghi `mltpath` của nó vào `contextcutrc` (sửa lại về `stage\share\mlt\profiles`).

## Sửa deadlock cầu nối khi clip đang nạp (22/10/2026, session riêng)

**Nguyên nhân (đã chứng minh):** khi một clip vào bin (nhập file, mở project, `import_media`), `ProjectClip(id, description…)` dựng `ClipController` không kèm producer, và hàm dựng đó gọi `m_producerLock.lockForWrite()` (`clipcontroller.cpp:63`) **trên luồng giao diện**. Khoá chỉ nhả trong `addMasterProducer()` (qua `ProjectClip::setProducer`, nạp được) hoặc `ProjectClip::setInvalid()` (nạp hỏng). `ClipLoadTask` gọi cả hai bằng `BlockingQueuedConnection` về luồng giao diện. Trong khoảng đó clip ở `StatusWaiting`. Cầu nối chạy trên luồng giao diện: `list_sources` gọi `frameDuration()` → `getFramePlaytime()` → `QReadLocker`. Qt không cho luồng đang giữ khoá ghi lấy khoá đọc, kể cả ở chế độ `Recursive` (chương trình thử với Qt 6.11.2: `lockForWrite()` rồi `tryLockForRead(2000)` cùng luồng → `false`). Vì vậy luồng giao diện tự khoá chính nó, còn `ClipLoadTask` chờ luồng giao diện mãi. **Clip tốt cũng bị**, không riêng clip hỏng: chỉ cần gọi trong lúc clip đang nạp. Cũng dính: `getFrameSize()`, `getOriginalFps()` (`list_recordings`), `hasLimitedDuration()` của slideshow, và `import_media` khi nạp quá 20 s (trả `sourceObject` của clip còn đang nạp). Op sửa thì không dính, vì `checkSource` kiểm `statusReady()` trước. Kdenlive tự né bằng cách kiểm `StatusWaiting` (`ProjectClip::hash()`, `getThumbProducer()`), nên không vá mã gốc mà ghi vào `patches.md` ("Biết trước").

**Sửa** (`src/contextcut/model/editorreader.cpp`): thêm `stillLoading(clip)` (`clipStatus() == StatusWaiting`). Clip đang nạp thì `list_sources`/`import_media` trả `duration_f: null`; `list_recordings` trả `duration_f`, `source_fps`, `width`, `height` là `null` (`audio_streams` vốn rỗng lúc đó), không gọi getter nào có khoá. `ready: false` như trước. Đã cập nhật `docs/protocol.md` §8.4/§8.4b; `protocol` vẫn là 1, vì trước đây trường này không bao giờ trả về được (app treo). Phía Python chỉ đọc `id`/`path` của bản ghi nên không phải sửa.

**Bằng chứng** (build Release, fixture `p1-gate` mới mỗi lần; script gọi `list_sources` liên tục qua một kết nối `bridge_probe.Bridge`, hết giờ 8 s thì báo HANG; bản sao ở thư mục ghi chú session `local_da273b71…/hammer.py`):

| Kiểm | Trước sửa | Sau sửa |
| --- | --- | --- |
| Nhập 1 file nhị phân đổi đuôi `junk01.mkv` (4 MB ngẫu nhiên) | **2/2 treo**: lần gọi thứ 13, ~14–17 s sau khi mở app, "Not Responding"; gdb: thread 1 `EditorReader::sources` → `sourceObject` → `ProjectClip::frameDuration` → `ClipController::getFramePlaytime` → Qt6Core chờ; một luồng pool `ClipLoadTask::run` → `abort`; không luồng nào khác chạm `ClipController` | 105 923 lần gọi trong 45 s, không treo; thấy clip `ready: false` rồi bị gỡ; app phản hồi |
| Nhập 12 clip **tốt** (H.264 3 s) | **treo** ở lần gọi thứ 16 | `list_sources` + `list_recordings` song song: ~27 500 lần gọi mỗi method trong 45 s, không treo; 1–2 clip `ready: false` mỗi lúc rồi đủ 17 nguồn |
| Nhập 30 file hỏng + bản ghi fixture cắt còn 1/3 (`dang-ghi.mkv`) | — | hai method song song, ~61 300 lần gọi mỗi method trong 60 s, không treo; tới 13 clip cùng nạp; 30 file hỏng bị gỡ, bản ghi cắt cụt nạp được |
| `uv run --directory contextcut-ai --no-sync pytest -m live` (p1-gate + OBS giả + `stereo.flac`) | — | **39/39 xanh** (cả `test_read_tools_over_stdio`); `bridge_probe check --quick` OK |

Tái hiện lại (khi merge bản KDE Gear mới hay thêm code đọc clip bin): fixture `p1-gate`, mở app với `-i "<file nhị phân đổi đuôi .mkv>"` hoặc vài clip mới, và gọi `list_sources` liên tục ngay lúc app mở. Code ContextCut mới mà gọi getter của `ProjectClip`/`ClipController` có `QReadLocker` phải kiểm `stillLoading()` hoặc `statusReady()` trước.
