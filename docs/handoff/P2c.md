# Bàn giao P2c — Xuất file, mở project; review toàn P2

22/10/2026 · kế hoạch: `docs/plans/P2.md` (P2c = Task 20–26, Review Focus (P2c)) · giao thức: `docs/protocol.md` §8.12 (xác nhận trong app), §8.13 (`open_project`) · session P2c (Claude Opus 5.5). **Code xong, cổng đạt trên dữ liệu thật, đã review cả P2** (P2a + P2b + P2c, một lượt review trong session, có sửa). Cuối file: **tóm tắt cả P2**.

## Đã xong (commit trên `main` từ `56e0c78211`, chưa push)

| Việc | Ở đâu |
| --- | --- |
| Hộp xác nhận trong app: `request_confirmation` / `get_confirmation` / `cancel_confirmation`. Hộp không-modal trên cửa sổ chính, chữ do app soạn từ trường có cấu trúc (project, file, đoạn, preset, mã hoá, "GHI ĐÈ"); nút mặc định "Không xuất", "Xuất" tắt 1,5 s đầu; hết 15 phút tự đóng; project đóng/đổi thì hộp tự rút (`cancelled`); từ chối `output` trùng file clip bin (gốc hoặc proxy) hay file project | `src/contextcut/app/confirmations.{h,cpp}` |
| `open_project` / `get_open_status`: kiểm đường dẫn (`.kdenlive`, tuyệt đối, có thật, không qua link), xếp `ProjectManager::openFile` vào vòng sự kiện chính như File › Open (hộp Save changes?, File Recovery… của Kdenlive hỏi người dùng), báo hộp modal đang hiện; trong lúc mở cầu nối chỉ nhận `get_open_status`/xác nhận (`AiBridgeServer::setExclusive`) | `src/contextcut/app/projectopener.{h,cpp}`, `bridge/aibridgeserver.*` |
| Method sửa (`apply_operations`, `add_markers`, `undo_batch`, `import_media`, `open_project`) bị từ chối `busy` khi app đang có hộp thoại modal | `aibridgeserver.cpp` (`MethodKind::Edit`) |
| Job `export`: chờ người dùng bấm Xuất → kiểm lại project + sequence → `get_scene` (file gốc) → melt với `<consumer avformat>` trong XML (đường dẫn có dấu được) → NVENC (`h264_nvenc` p5 hq CQ 19, trần 24 Mbit/s) → hỏng thì x264 (CRF 18, cùng trần) → ffprobe → đổi tên `<tên>.<mã>.part.mp4` thành file đích. NVENC giữ khoá GPU, x264 thì không | `contextcut-ai/src/contextcut_ai/exporter.py`, `analysis/worker.py` |
| Tool `export(output, start_f?, end_f?, preset, encoder, overwrite, originals)`: kiểm preset (`youtube-1080p60` cần project 1920×1080 60/59,94 fps; `project` giữ cỡ/fps), đường dẫn, khoảng; hỏi app; tạo job; chờ ≤ 50 s qua bước xác nhận. Tool `open_project(path, wait_s)`: chờ, báo `dialog`, gọi lại cùng path thì chờ tiếp lần mở đó | `mcp_server.py`, `errors.py` |
| Guide: bước Xuất (người dùng bấm, agent không bấm thay/không lách, gọi `get_job` ngay, báo `checks`), Mở project, bảng tham số, lỗi mới; SKILL/AGENTS sinh lại; README | `contextcut-ai/guide/`, `skills/` |

Test: `uv run --directory contextcut-ai --no-sync pytest` → **246 xanh** khi app mở `p1-gate` (sống gồm `test_live_open.py` 5 mới + toàn bộ P1/P2a/P2b); không có app thì test sống tự bỏ qua. `test_exporter.py` dùng melt/ffmpeg thật (NVENC thật bỏ qua khi máy không có GPU NVIDIA).

## Bằng chứng cổng

Project thử `Xuất thử 1080p60.kdenlive` (fixture `p1-gate` đổi profile sang `atsc_1080p_60`, proxy tắt) mở bằng `open_project`, `import_media` `C:\Users\VuNhan\Videos\Gaming.mkv` (HEVC 1080p60, 5 track), `insert_clip` 20 s (nguồn 00:10–00:30) lên V1 ở 00:02. Xuất `[120, 1320)` = 20 s.

| Kiểm | Kết quả |
| --- | --- |
| NVENC, Claude Code phiên mới (`claude -p`, sonnet): "Xuất đoạn 00:02–00:22 … cho YouTube" | `get_editor_state` → `export` (tool đứng chờ 20 s tới khi bấm Xuất) → `get_job(wait_s=50)` → báo bảng 6/6 kiểm đạt (7 lượt, 65 s, 0,18 USD). 1200/1200 frame, 1920×1080 60 fps, lệch đầu hình/tiếng 0 ms, tiếng dài hơn hình 10,7 ms (đệm AAC); mã hoá 18,6 s (1,08× thời gian thực), 23,5 Mbit/s, 59,4 MB. Khung giữa file trùng khung bản ghi gốc |
| Ép NVENC hỏng (`CONTEXTCUT_FORCE_NVENC_FAIL=1` → `gpu=99`), `encoder: auto` | `fallback_reason`: "melt dừng với mã 3221225477: [h264_nvenc] No capable devices found" → x264: 6/6 đạt, 60,8 s (0,33×), 24,2 Mbit/s, 61,2 MB; không còn file dở |
| Hộp xác nhận chặn | Job đứng ở "chờ người dùng bấm Xuất trong ContextCut" suốt thời gian giữ hộp (15–20 s mỗi lần); bấm "Xuất" trong 1,5 s đầu bị bỏ qua; "Không xuất" → job `cancelled` ("không xuất: người dùng bấm Không xuất"), không có file nào |
| `open_project` khi project hiện tại đã sửa, Claude Code phiên mới: "Mở giúp project …/p1-gate.kdenlive" | Lần 1: tool trả `pending` + `dialog` "The project "Xuất thử 1080p60.kdenlive" has been changed. Do you want to save your changes?"; agent báo nguyên câu và để Nhan chọn (4 lượt, 0,11 USD). Bấm Cancel → `cancelled`, project cũ còn nguyên (vẫn `modified`, marker còn). Lần 2 (phiên mới): bấm Save sau 15 s → `opened`, agent tóm tắt project mới (6 lượt, 0,16 USD); file cũ đã lưu marker |
| Mở project liên tiếp | 20 lần mở A↔B sát nhau không crash (trước khi sửa: crash ở lần 2, xem Bẫy) |

Lưu ý trung thực: "Nhan bấm" trong cổng là **giả lập** (PostMessage nhấp chuột vào nút của hộp theo toạ độ client), không phải Nhan bấm tay. Nhan nên tự thử một lần: nhờ agent xuất một đoạn ngắn và bấm "Xuất"/"Không xuất" trong hộp.

## Review toàn P2 (session này)

Đã sửa (có test hoặc kiểm lại):

1. **`undo_batch` so con trỏ lệnh undo đã bị Kdenlive giải phóng** (P1c, lộ ra ở P2c khi đổi project; cũng xảy ra khi vượt giới hạn undo): con trỏ treo có thể trùng địa chỉ lệnh mới → hoàn tác nhầm bước của người dùng. Nay lệnh của đợt là lớp con `BatchCommand` mang `batch_id`, kiểm bằng `dynamic_cast` lệnh trên cùng.
2. **Hộp xác nhận không gắn project**: đổi project rồi bấm Xuất ở hộp cũ sẽ xuất timeline project mới. Nay hộp ghi tên project, tự rút khi project đóng, job kiểm lại project + sequence. Lần sửa đầu làm app crash (đọc revision lúc document đang huỷ) — test sống bắt được, đã sửa.
3. **`Cancelled` khác lớp** khi worker chạy bằng `python -m` (`__main__.Cancelled` ≠ lớp module job import): từ chối xuất thành `failed` thay vì `cancelled`. Chuyển `Cancelled` vào `jobs.py`.
4. **File tạm `.part.mp4`** có thể trùng (và bị xoá) một file có sẵn của người dùng: nay có mã riêng mỗi job.
5. File ảnh tạm của `get_source_frames` cùng tên khi hai lời gọi song song trong một server (chỉ theo pid): thêm id luồng.
6. `auth` trong lúc đang mở project gọi `RevisionTracker::sync` đọc document/timeline đang dựng/huỷ: nay trả revision đã biết.
7. Method sửa chạy được bên trong vòng sự kiện của hộp modal Kdenlive (vd. "Save changes?" lúc Nhan đóng app): nay `busy`.

Kiểm, không thấy lỗi: `get_scene` chỉ tuần tự hoá MLT (khoá `xmlMutex`, không đụng khoá producer clip → không dính bẫy `StatusWaiting`); khoá GPU (`msvcrt.locking` byte 0, hệ điều hành nhả khi tiến trình chết), VRAM trả khi worker thoát; ghi file job nguyên tử; op phụ đề/`cut_range`/`zoom` (thứ tự xoá → thu → dời, keyframe theo frame producer).

Biết trước, chưa sửa (nhỏ hoặc hiếm):

- `jobs.pid_alive` không chống tái dùng pid trên Windows (worker chết + pid bị cấp lại → job kẹt `running`); worker treo (không chết) giữ khoá GPU tới khi người dùng giết tiến trình Python — `cancel_job` chỉ dừng ở mốc `report` kế tiếp.
- Xuất HEVC 1080p60 chỉ ~1× thời gian thực: melt giải mã + ghép ở `real_time=-1` (một luồng xử lý). Kdenlive có "parallel processing" (`real_time=-N`) nhưng tắt mặc định vì vài hiệu ứng không an toàn; thử khi cần nhanh hơn.
- Worker xuất chết giữa chừng (BSOD, giết tiến trình) để lại `<tên>.<mã>.part.mp4` cạnh file đích; hộp xác nhận của job đó vẫn bấm được nhưng không làm gì.
- Từ P2b: `get_viewer_frame` có thể báo `position_f = at_f` khi Kdenlive bỏ qua seek; `zoom` chưa từ chối clip đổi tốc độ; XML bọc của `render_frames` giả định pixel vuông.

## Lệch thiết kế / kế hoạch

1. Thêm preset `project` (ngoài "YouTube 1080p60"): ContextCut không tự đổi cỡ/fps khi xuất (consumer đổi cỡ trên scene Kdenlive chừa viền đen, Bẫy P2b), nên project không phải 1080p60 xuất theo cỡ của nó.
2. Trần bitrate 24 Mbit/s cho cả NVENC và x264 (lần đầu NVENC CQ 19 trần 40 Mbit/s ra 38,5 Mbit/s, ~17 GB/giờ).
3. Xác nhận không khoá cầu nối (hộp không-modal + job hỏi `get_confirmation`) thay vì một request cầu nối chờ hộp modal: request chờ lâu sẽ chặn mọi client khác (cầu nối tuần tự).
4. Scene lấy **lúc người dùng bấm Xuất**, không phải lúc agent hỏi.
5. `open_project` không vá mã Kdenlive: đợi timer 250 ms của monitor (Bẫy) thay vì sửa `Monitor::updateTimelineProducer`.

## Bẫy mới

- **Kdenlive crash khi mở project thứ hai trong vòng 250 ms sau project trước**: `TimelineTabs` bật `refreshMonitorTimer` (250 ms) khi tab timeline vừa kích hoạt; timer chạy trong `processEvents` của `doOpenFile` lúc chưa có document → `Monitor::updateTimelineProducer` → `currentDoc()->getSequenceProperty` null (gdb gắn vào app đang chạy). Agent mở liên tiếp là gặp. `open_project` đợi timer xong (`patches.md`, "Biết trước").
- gdb chạy app từ đầu (`gdb --args contextcut.exe`) kẹt ở màn hình splash; **gắn gdb vào app đang chạy** (`gdb -batch -ex "attach <pid>" -ex continue -ex "bt 40"`) thì được. Exe có bảng symbol (tên hàm, không có dòng).
- NVENC hỏng làm melt **segfault** (0xC0000005) sau dòng `[h264_nvenc] No capable devices found`, để lại file 48 byte không có `moov`: nhận biết bằng mã thoát + ffprobe.
- melt: đặt `<consumer mlt_service="avformat" target=… in= out=>` **trong XML** (như Kdenlive xuất) thì `target` có dấu chạy đúng; argv thì không.
- Worker job chạy bằng `python -m …worker` nên lớp exception khai báo trong `worker.py` là `__main__.X`: lớp dùng chung giữa worker và module job phải ở module khác (`jobs.Cancelled`).
- Tự động hoá hộp thoại ContextCut từ tiến trình nền: `SetForegroundWindow` + `SendKeys` thường **không** tới hộp (khoá foreground của Windows; phím đi lạc sang cửa sổ khác). Gửi `PostMessage` `WM_LBUTTONDOWN/UP` vào HWND của hộp theo toạ độ client (Qt dùng widget "alien"): hộp xác nhận xuất (client 500×197) "Xuất" ≈ (W−147, H−25), "Không xuất" ≈ (W−53, H−25); hộp "Save changes?" của Kdenlive (client 590×86) Save (360,63), Do Not Save (452,63), Cancel (537,63). `SetWindowPos(HWND_TOPMOST, SWP_NOACTIVATE)` để chụp hộp bị che. Script: `contextcut-ai/tools/ui/` (`launch.ps1` mở app có log, `save.ps1` Ctrl+S + hộp Information, `close.ps1` đóng bằng WM_CLOSE, `dialog.ps1` chụp/bấm hộp); `tools/mcp_call.py` gọi một tool MCP trong tiến trình; `tools/agent_run.sh` chạy `claude -p` phiên mới chỉ với server ContextCut.
- PowerShell: bắt stdout của một script có `Start-Process` app (`$p = powershell -File launch.ps1`) treo tới khi app thoát (app thừa hưởng pipe): ghi pid ra file / chạy nền.
- Agent `claude -p` kết thúc lượt khi tool trả "đang chờ người dùng" (lặp lại bẫy P2a): câu `next` của `export` nay bảo gọi `get_job` ngay, lần chạy sau agent tự chờ đúng.
- Hộp "Loading Project" (tiến độ) cũng là `activeModalWidget`: `get_open_status.dialog` báo nó khi đang nạp.

## Việc tiếp / dở

1. **Nhan**: tự bấm thử hộp xác nhận một lần (agent xuất một đoạn ngắn); tự thử `open_project` khi project đang sửa.
2. **Cổng timing phụ đề P2a vẫn chờ Nhan**: 3–5 phút mốc gõ tay trên track Mic của một bản ghi OBS 5 track (vd. `Gaming.mkv`) — lệnh ở `docs/handoff/P2a.md` ("Còn chờ Nhan"); đạt khi trung vị lệch đầu và cuối câu < 100 ms, rồi chốt `asr.PREFERENCE`.
3. Nhắc Nhan: chạy lại `uv run --directory contextcut-ai python scripts/register_clients.py` (skill đã cài còn bản cũ: agent báo "Skill không load được"); gỡ `D:\ContextCut` khỏi loại trừ Defender khi xong dự án.
4. P3 (dàn ý, `find_moments`, `detect_beats`, `beat_montage`) theo design §12.

## Tóm tắt P2 (P2a + P2b + P2c)

| Phần | Có gì | Cổng |
| --- | --- | --- |
| P2a | Job nền tách tiến trình + khoá GPU toàn máy; `track_map` theo bản ghi; `transcribe` (Parakeet/PhoWhisper/large-v3, chunk chạy tiếp, lọc ảo giác, tinh chỉnh ranh giới), `get_transcript`; `add_subtitles`, `caption` theo người nói; `cut_range` dời phụ đề | Agent chạy trọn transcribe → phụ đề, lưu/mở lại được, VRAM < 6 GB. **Đo timing < 100 ms chưa có** (chờ mốc tay của Nhan) |
| P2b | `get_source_frames`, `get_contact_sheet`, `render_frames` (melt), `get_viewer_frame`; op `zoom` | Ảnh đúng mốc; zoom → undo y hệt; agent xem → zoom → tự kiểm; Claude Code và Codex hiện ảnh từ tool |
| P2c | `export` (xác nhận trong app, NVENC → x264, ffprobe), `open_project` (hộp Kdenlive hỏi người dùng) | NVENC và x264 đạt ffprobe trên bản ghi thật; hộp chặn tới khi trả lời; `open_project` từ phiên mới kể cả khi project đang sửa |

Hai lỗi Kdenlive gốc đã vá trong P2 (session riêng): treo khi tạo proxy HEVC (`proxytask.cpp`), deadlock cầu nối khi clip đang nạp (né trong `editorreader.cpp`). Một lỗi gốc né ở P2c (crash mở project liên tiếp). Commit P2 từ `099033d` tới `50c7af6c7b` trên `main`, **chưa push**.
