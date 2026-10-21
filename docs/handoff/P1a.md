# Bàn giao P1a — Cầu nối C++ và tool đọc

22/10/2026 · kế hoạch: `docs/plans/P1.md` (phần P1a) · giao thức: `docs/protocol.md` · session P1a (Claude Opus 5.5)

## Đã xong

| Việc | Ở đâu |
| --- | --- |
| Kế hoạch cả P1, chia 3 session (P1a/P1b/P1c); P1b và P1c ở dạng phác thảo để session sau chi tiết hoá | `docs/plans/P1.md` |
| Hợp đồng giao thức v1: `bridge.json`, bảo mật, JSON-RPC, mã lỗi, frame/khoảng nửa mở, revision, phân trang, method P1a đầy đủ, method P1c dạng nháp | `docs/protocol.md` |
| `AiBridgeServer`: QWebSocketServer chỉ `127.0.0.1`, cổng do OS cấp, token 32 byte mỗi lần chạy, `auth` bắt buộc trong 5 s, từ chối `Origin` ở bước bắt tay, tối đa 8 socket, 4 MiB/thông điệp, hàng đợi tuần tự trên GUI thread, ghi `bridge.json` (QSaveFile) và chỉ xoá khi token trong file là của mình | `src/contextcut/bridge/aibridgeserver.*` |
| Khung JSON-RPC 2.0 + bảng mã lỗi, không dùng exception | `src/contextcut/bridge/jsonrpc.*` |
| `RevisionTracker`: tăng khi undo stack đổi chỉ số, khi timeline thêm/xoá/dời hàng hoặc reset, khi đổi project/sequence; giá trị đầu ngẫu nhiên 1…2³⁰ | `src/contextcut/bridge/revisiontracker.*` |
| `get_editor_state`, `get_timeline` (lọc khoảng/track, cursor), `list_recordings` (nhiều bản ghi mỗi project, id = `kdenlive:id`, hash file, stream audio, chỗ trống `track_map`/`day_start` cho P2/P7) | `src/contextcut/model/editorreader.*` |
| Hook một dòng trong `Core::initGUI` + include; CMake `add_subdirectory(contextcut)` + `Qt6::WebSockets` | `src/core.cpp`, `src/CMakeLists.txt`, `src/contextcut/CMakeLists.txt`, `patches.md` |
| Client thử (PEP 723, `websockets==16.0`): `check` (20 kiểm tra), `call`, `watch` | `contextcut-ai/tools/bridge_probe.py` |

## Bằng chứng cổng

Đo ngày 22/10/2026 trên máy Nhan, bản build cuối (`build.ps1 -SkipDeps`, exit 0). Project thử: bản sao `tests/dataset/clip-ids.kdenlive` (4 file `.mpg`, 16 clip trên V2/V1/A1/A2, 25 fps) mở bằng `contextcut.exe --no-welcome -i obs-2026-10-21.mkv clip-ids.kdenlive`; `obs-2026-10-21.mkv` là file giả OBS tạo bằng ffmpeg (640×360, 30 fps, 6 s, 3 stream audio). Không file nào trong repo bị sửa.

| Kiểm | Kết quả |
| --- | --- |
| `bridge_probe.py check` (đầy đủ) | **20/20 PASS**, chạy trên hai bản build (trước và sau hai lần sửa nhỏ dưới đây) |
| `bridge.json` | `%LOCALAPPDATA%\contextcut\bridge.json`: `protocol 1`, `host 127.0.0.1`, `port` ngẫu nhiên (57743, 52299, 59636…), token 64 hex, `session`, `pid`, `started_at` có múi giờ |
| Xác thực / đọc | `auth` đúng → `session` khớp file; `get_editor_state` trả project, fps 25/1, 1280×720, playhead, zone, 4 track, `counts` (16 clip, 5 bản ghi); `get_timeline(limit=1)` đi 16 trang ghép ra đúng `get_timeline(limit=1000)`, sắp đúng; `list_recordings` trả 5 bản ghi, bản OBS có 3 stream audio, hash `8a0102e8…`, `on_timeline: false`; phân trang `limit=4` → trang 2 chỉ còn bản OBS, `next_cursor: null` |
| Token sai / thiếu / gọi trước `auth` | lỗi `-32001 unauthorized`, server đóng mã `4401`; không `auth` 6 s → đóng `4408` |
| Trang web (`Origin: http://example.com`) | bắt tay bị từ chối HTTP 403 |
| Chỉ loopback | `netstat -ano`: duy nhất `TCP 127.0.0.1:57743 0.0.0.0:0 LISTENING 16916`; nối `192.168.1.182:<port>` và `[::1]:<port>` đều bị từ chối |
| Lỗi khung | method lạ `-32601`, không phải JSON `-32700`, frame nhị phân `-32600`, `limit:"x"` / `end_f<start_f` `-32602`, track `V99` `-32008`, cursor revision cũ `-32004` |
| Revision (`watch` + nút thanh công cụ qua UI Automation) | dời playhead 0 → 35 (Project Monitor › Forward ×2): **không đổi**; Ctrl+A chọn 16 clip rồi Esc: **không đổi**; Extract Timeline Zone (clips 16 → 0), Undo (→ 16), Redo, Undo: **đổi mỗi lần** (…617 → 634 → 651 → 668 → 685); tạo project mới (Ctrl+N): đổi; tạo "Sequence 2": đổi; chọn tab "Sequence 1": đổi |
| App chưa có project | khi hộp "File Recovery" đang mở: `get_editor_state` → `-32002 no_project`, app không crash |
| Đóng app bình thường (nút đóng → "Do Not Save") | log `AI bridge: removed …bridge.json`, file không còn; `check` sau đó báo "không thấy … — Mở ContextCut trước" |
| App crash (`Stop-Process -Force`) | file còn lại; `check` báo ngay `WinError 10061 … — Mở ContextCut trước` (không treo); lần chạy sau ghi đè file (log "replacing … stale") |
| Hai instance | mở A rồi B → file mang pid của B; đóng A → file vẫn là của B, client vẫn nối được B; đóng B → file mất |

## Lệch so với thiết kế / kế hoạch

1. **`content` của clip chỉ là `video` hoặc `audio`**, không có `av`: Kdenlive luôn tách clip có tiếng thành hai clip (V và A) nối nhau qua nhóm AVSplit; trường `linked` trỏ sang clip cặp. Đã sửa `docs/protocol.md`.
2. **`hidden`/`muted` của track**: bit `hide` của MLT luôn có sẵn cho phần track không mang (track audio ẩn hình, track video tắt tiếng), lần chạy đầu báo sai `muted: true` cho V1/V2. Đã sửa theo `TimelineItemModel::IsDisabledRole`: `hidden` chỉ cho track video, `muted` chỉ cho track audio.
3. **Revision tăng nhiều đơn vị mỗi lần sửa** (Extract 16 clip: +17, vì mỗi hàng thêm/xoá là một tín hiệu). Giao thức chỉ hứa "khác là đã đổi", chỉ phép so bằng có nghĩa.
4. **Tên stream audio** là mô tả Kdenlive (`Mono 44100Hz aac`, đã bỏ tiền tố `1|`), không phải tên track OBS ghi trong file (Mic, Discord…). P2 đọc tên đó bằng ffprobe khi dựng `track_map`.
5. **`sequences`** chỉ liệt kê sequence đang mở trong tab (`KdenliveDoc::getTimelinesUuids()`); sequence chỉ nằm trong bin chưa mở thì không có.
6. **`selection.zone`** trả nguyên `zoneIn`/`zoneOut` của Kdenlive (project mẫu: 0–75). Chưa kiểm `zoneOut` của Kdenlive là mút mở hay đóng; P1c kiểm khi dùng zone cho op.
7. **Lần build đầu sau P1a biên dịch lại cả `kdenliveLib`** (thêm `Qt6::WebSockets` vào link PUBLIC đổi cờ biên dịch của mọi file): ~9,5 phút trên máy Nhan (8 phút 331 bước + 71 s); sau đó sửa một file của cầu nối ~30 s.
8. Track phụ đề không có trong `get_timeline` (để P2). `get_editor_state` chưa có `game_preset` (P3).
9. Chưa thử khi app khởi động có màn hình chào (mọi lần chạy đều `--no-welcome`). `main.cpp` gọi `initGUI` ngay sau `Core::build` (nơi dựng splash/màn hình chào), nên cầu nối nhiều khả năng đã mở trong lúc màn hình chào còn hiện, và method trả `no_project`/`busy` như lúc hộp "File Recovery" mở. P1b nên kiểm lại khi thử với agent.
10. Kế hoạch ghi `getFileHash()` cho `file_hash`: hàm đó `protected`, dùng `ProjectClip::hash()` (public, đọc `kdenlive:file_hash` hoặc tính nếu chưa có).

## Lệnh

```powershell
# build (lần đầu sau P1a biên dịch lại cả kdenliveLib vì thêm Qt6::WebSockets)
powershell -NoProfile -ExecutionPolicy Bypass -File packaging\build.ps1 -SkipDeps
# chạy app (cầu nối tự mở; bridge.json ở %LOCALAPPDATA%\contextcut\)
powershell -NoProfile -ExecutionPolicy Bypass -File packaging\run.ps1
# thử cầu nối khi app đang chạy
uv run contextcut-ai/tools/bridge_probe.py check
uv run contextcut-ai/tools/bridge_probe.py call get_timeline limit=5
uv run contextcut-ai/tools/bridge_probe.py call list_recordings cursor=<next_cursor>
uv run contextcut-ai/tools/bridge_probe.py watch --seconds 60
# log của cầu nối (category contextcut.bridge) ra stderr khi đặt QT_FORCE_STDERR_LOGGING=1
```

## Bẫy mới (đã chép phần cần thiết vào CLAUDE.md)

- **Tự động hoá UI của ContextCut:** computer-use không thấy `contextcut.exe` (không có trong Start menu). UI Automation (PowerShell `System.Windows.Automation`) bấm được nút thanh công cụ (`InvokePattern`: Undo, Redo, Extract Timeline Zone, Forward…), nút của hộp `KMessageBox` ("Do Not Save", "Do not recover") và tab sequence (`SelectionItemPattern`). **Menu Qt thì không** (Invoke hết giờ, lệnh không chạy). Chạy lệnh theo tên: SendKeys `^%i` (Find Action của KF6) + gõ tên lệnh + Enter. Hộp "Project Settings" không hiện trong cây UIA: chụp riêng cửa sổ (`GetWindowRect` + `CopyFromScreen`) để xem.
- Có hai nút "Forward"/"Rewind": cái đầu là Clip Monitor, cái thứ hai là Project Monitor (playhead timeline).
- Giết app (`Stop-Process`) thì lần mở sau hiện hộp "File Recovery" chặn việc nạp project; trong lúc đó cầu nối trả `no_project`.
- `-i <file>` thêm clip vào bin làm project thành "đã sửa" (`*`), nên đóng app sẽ hỏi lưu. File nhiều stream audio còn hiện thông báo trong bin "Your project needs more audio tracks…".
- File JSON do PowerShell 5.1 ghi bằng `>` có BOM UTF-8: đọc bằng `utf-8-sig`.
- Đóng gói P5 phải kèm `Qt6WebSockets.dll` (hiện `run.ps1` lấy từ `ucrt64\bin` qua PATH).

## P1b cần biết

- Cách tìm app và xác thực: protocol §1, §3; làm y như `bridge_probe.py` (`load_bridge_file`, `Bridge`). Nối `ws://127.0.0.1:<port>/`, không gửi `Origin`, tắt nén (`compression=None`), `max_size` ≥ 16 MiB. Lỗi kết nối → "Mở ContextCut trước"; đọc lại `bridge.json` mỗi lần nối lại vì cổng và token đổi mỗi lần app chạy.
- Lỗi trả về có `error.data.kind` ổn định (`no_project`, `busy`, `stale_cursor`…); MCP server nên chuyển thành thông báo tiếng Việt ngắn cho agent.
- Trên máy Nhan có sẵn **Codex** và **Antigravity** (thấy trong Start menu) ngoài Claude Code: cổng P1b/P1 thử được cả ba.
- `uv` 0.12 ở `C:\Users\VuNhan\.local\bin\uv.exe`; Python 3.11 có sẵn (`uv python list`).
- Fixture dùng ở P1a nằm ở scratchpad của session (không giữ); tạo lại: chép `tests/dataset/{clip-ids.kdenlive,*.mpg}` ra thư mục tạm, và file giả OBS bằng `ucrt64\bin\ffmpeg.exe -f lavfi -i testsrc2=size=640x360:rate=30:duration=6 -f lavfi -i sine=frequency=440:duration=6 … -map 0:v -map 1:a -map 2:a -map 3:a -c:v libx264 -c:a aac obs.mkv`.

## P1c cần biết

- Đăng ký method mới: `AiBridgeServer::instance()->registerMethod(name, handler)` (xem `EditorReader::registerReadOnlyMethods`, gọi từ `AiBridgeServer::start`). Handler chạy trên GUI thread, tuần tự; revision hiện tại: `revisions()->current()`.
- Sau `pushUndo` của một đợt, revision tăng (undo stack đổi chỉ số + tín hiệu hàng): trả `revisions()->current()` sau khi đẩy undo.
- `EditorReader::activeTimeline(error)` trả timeline đang mở hoặc lỗi `no_project`/`busy`; `tracks()` cho thứ tự hiển thị; nhận track theo id hoặc tag như `get_timeline`.
