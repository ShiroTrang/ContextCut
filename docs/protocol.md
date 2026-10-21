# Giao thức cầu nối ContextCut (AI Bridge) — v1

21/10/2026 · trạng thái: **hợp đồng cho P1** (P1a cài, P1b và P1c dựa vào) · nguồn: design v3.1 §9, Kiến trúc v3 mục "AI chỉnh trực tiếp và nhìn video", "Timeline và thao tác", "Bảo mật".

App ContextCut (C++) mở một server WebSocket cục bộ. Dịch vụ Python `contextcut-ai` (MCP server) là client duy nhất dự kiến; AI client (Claude, Codex, Antigravity) không nói chuyện thẳng với cầu nối. Tài liệu này là hợp đồng giữa hai bên: đổi thứ gì ở đây thì tăng `protocol` hoặc ghi rõ là trường mới không bắt buộc.

Ký hiệu: **[P1a]** đã cài ở P1a; **[P1c]** bản nháp, P1c được chỉnh chi tiết nhưng giữ các trường đã ghi.

## 1. Tìm app và kết nối

Mỗi lần khởi động, app ghi file **`bridge.json`** vào thư mục dữ liệu của người dùng (`QStandardPaths::AppLocalDataLocation`; trên Windows là `%LOCALAPPDATA%\contextcut\bridge.json`). Client cho phép đổi đường dẫn bằng biến môi trường `CONTEXTCUT_BRIDGE_FILE` (để test).

```json
{
  "protocol": 1,
  "host": "127.0.0.1",
  "port": 51234,
  "token": "9f2c…(64 ký tự hex)",
  "session": "3b0c8f7e-…",
  "pid": 12345,
  "app": "ContextCut",
  "app_version": "26.08.2",
  "started_at": "2026-10-21T22:30:00+07:00"
}
```

- `port` do hệ điều hành cấp (cổng 0 khi `listen`), đổi mỗi lần chạy. Client luôn nối tới `ws://127.0.0.1:<port>/`, không dùng `localhost` (có thể ra `::1`).
- `token`: 32 byte ngẫu nhiên (`QRandomGenerator::system()`), mã hex, đổi mỗi lần chạy.
- `session`: UUID của lần chạy này; cũng trả trong `auth` và `get_editor_state`.
- File ghi nguyên tử (`QSaveFile`). Thư mục `%LOCALAPPDATA%` vốn chỉ chủ tài khoản đọc được; token không bao giờ nằm trong URL hay log.
- App đóng bình thường thì xoá file, nhưng **chỉ khi file còn là của mình** (token trong file trùng token của tiến trình). Có hai bản ContextCut chạy cùng lúc thì bản mở sau ghi đè file và là bản AI nối vào.
- App crash thì file còn lại. Client gặp lỗi kết nối (bị từ chối hoặc hết giờ) phải báo **"Mở ContextCut trước"**, không thử lại liên tục.

## 2. Bảo mật

| Lớp | Cách làm |
| --- | --- |
| Mạng | Chỉ `listen(QHostAddress::LocalHost)` = `127.0.0.1`. Không nghe trên IPv6 hay card mạng khác. Socket có địa chỉ đầu kia không phải loopback bị đóng ngay. |
| Trình duyệt | Bắt tay có header `Origin` (mọi trang web đều gửi) bị từ chối ngay ở bước bắt tay (`QWebSocketServer::originAuthenticationRequired`). Client Python không gửi `Origin`. |
| Token | Thông điệp đầu tiên phải là `auth` với đúng token (so sánh thời gian hằng). Sai token, thiếu token, hoặc gọi method khác trước khi `auth` → lỗi `unauthorized` rồi đóng socket (mã đóng `4401`). Không `auth` trong **5 giây** → đóng (`4408`). |
| Giới hạn | Tối đa **8** socket cùng lúc (thừa → đóng `4429`). Thông điệp vào tối đa **4 MiB**. Không nhận frame nhị phân. |
| Phạm vi | Chỉ có các method trong registry dưới đây. Không method nào chạy shell, đọc file tùy ý hay ghi đè file gốc. `import_media` (sau P1) chỉ nhận đuôi file media, đường dẫn được resolve và kiểm symlink. |

## 3. Khung thông điệp (JSON-RPC 2.0)

Mỗi frame text là một object JSON-RPC 2.0. Không hỗ trợ batch (mảng).

```json
{"jsonrpc": "2.0", "id": 7, "method": "get_timeline", "params": {"start_f": 0, "end_f": 600}}
{"jsonrpc": "2.0", "id": 7, "result": {"revision": 1873402, "items": []}}
{"jsonrpc": "2.0", "id": 7, "error": {"code": -32602, "message": "limit must be an integer in 1..1000", "data": {"kind": "invalid_params", "field": "limit"}}}
```

- `id` là số hoặc chuỗi; app trả lại y nguyên. Thông điệp không có `id` (notification) bị bỏ qua, không trả lời.
- `params` là object hoặc bỏ trống. Trường không biết bị bỏ qua (để client mới nói chuyện được với app cũ).
- **Tuần tự:** app xử lý từng request một, theo thứ tự đến, trên luồng giao diện (GUI thread). Request đến lúc đang xử lý (kể cả khi handler chạy vòng lặp sự kiện lồng) được xếp hàng, không chạy chồng.
- Client nên giữ một kết nối và gửi tuần tự; gửi song song vẫn đúng nhưng chỉ xếp hàng.

## 4. Mã lỗi

`error.data.kind` là tên ổn định để code dựa vào; `message` là tiếng Anh ngắn cho người đọc log.

| code | `kind` | Khi nào | `data` thêm |
| --- | --- | --- | --- |
| -32700 | `parse_error` | Frame không phải JSON | |
| -32600 | `invalid_request` | Không phải object JSON-RPC 2.0, là batch, frame nhị phân | |
| -32601 | `method_not_found` | Method không có trong registry | `method` |
| -32602 | `invalid_params` | Tham số sai kiểu hoặc ngoài khoảng | `field` |
| -32603 | `internal_error` | Lỗi trong app | |
| -32001 | `unauthorized` | Chưa `auth` hoặc token sai | |
| -32002 | `no_project` | Chưa có project/timeline nào mở | |
| -32003 | `conflict` | `base_revision` khác revision hiện tại **[P1c]** | `current_revision` |
| -32004 | `stale_cursor` | `cursor` thuộc revision cũ hoặc sai dạng | `current_revision` |
| -32005 | `busy` | Project đang nạp hoặc đang đóng | |
| -32006 | `validation_failed` | Ops không hợp lệ, chưa đổi gì **[P1c]** | `errors[]` |
| -32007 | `apply_failed` | Một op lỗi giữa chừng, cả đợt đã hoàn tác **[P1c]** | `op_index`, `reason` |
| -32008 | `not_found` | Id clip/track/sequence không tồn tại | `id` |

Mã đóng WebSocket: `4401` sai/thiếu token, `4408` hết giờ `auth`, `4429` quá số kết nối.

## 5. Quy ước dữ liệu

- **Thời gian là frame nguyên** ở fps của project (timeline đang mở). `fps` luôn ghi dạng phân số `{"num": 60, "den": 1}`; `30000/1001` giữ nguyên, không làm tròn.
- **Mọi khoảng là nửa mở** `[start_f, end_f)`: `end_f` là frame đầu tiên *không* thuộc khoảng. Clip dài 300 frame đặt ở frame 100 có `start_f: 100, end_f: 400`. Khoảng nguồn của clip cũng vậy: `src_in_f` thuộc clip, `src_out_f` không thuộc.
- **Id:** id clip, composition, track là số nguyên của mô hình timeline Kdenlive, chỉ có giá trị trong một lần chạy app (`session`). Id nguồn (bin clip, bản ghi) là chuỗi `kdenlive:id`, lưu trong file `.kdenlive`, ổn định giữa các lần mở.
- **Track** được liệt kê theo thứ tự hiển thị từ trên xuống (V2, V1, A1, A2…); `tag` là nhãn Kdenlive hiện (`V1`, `A2`). Method nhận track bằng id (số) hoặc tag (chuỗi).
- Trường chưa có nguồn đáng tin thì là `null`, không bịa giá trị.

## 6. Revision

- `revision` là số nguyên app tăng mỗi khi timeline có thể đã đổi: mỗi lần undo stack đổi chỉ số (sửa tay, sửa của AI, undo, redo), mỗi lần mô hình timeline thêm/xoá/dời hàng hoặc reset, mỗi lần đổi project hoặc đổi sequence đang mở. Chọn clip, dời playhead, cuộn, zoom **không** tăng revision.
- Chỉ phép so sánh bằng là có nghĩa. Giá trị **bắt đầu ngẫu nhiên** mỗi lần chạy (1…2³⁰), nên revision đọc từ lần chạy trước gần như không thể trùng.
- Mọi kết quả đọc có `revision`. Lệnh sửa **[P1c]** bắt buộc `base_revision`; khác revision hiện tại → `conflict` kèm `current_revision`, timeline không đổi gì; AI đọc lại rồi gửi lại.
- Đợt sửa thành công trả revision mới sau đợt đó.

## 7. Phân trang

- Method trả danh sách dài nhận `limit` và `cursor`, trả `next_cursor` (chuỗi) hoặc `null` khi hết.
- `cursor` gắn với revision lúc phát hành. Timeline đổi giữa hai trang → `stale_cursor`; client đọc lại từ đầu. Hai trang liên tiếp phải gửi cùng bộ lọc (`start_f`, `end_f`, `tracks`) như trang đầu.
- Định dạng `cursor` là nội bộ của app; client không tự tạo.

## 8. Methods

| Method | Việc | GĐ |
| --- | --- | --- |
| `auth` | Xác thực kết nối | P1a |
| `get_editor_state` | Project, fps, playhead, chọn, revision, tóm tắt track | P1a |
| `get_timeline` | Track, clip, composition, guide trong một khoảng; phân trang | P1a |
| `list_recordings` | Các bản ghi (nguồn video) của project; phân trang | P1a |
| `list_operations` | Danh mục op + schema tham số | P1c |
| `validate_operations` | Kiểm một đợt op, không đổi gì | P1c |
| `apply_operations` | Một đợt op = một bước undo có nhãn | P1c |
| `add_markers` | Thêm guide/marker để Nhan xem | P1c |

### 8.1 `auth` [P1a]

```json
{"jsonrpc": "2.0", "id": 1, "method": "auth", "params": {"token": "9f2c…", "client": "contextcut-ai/0.1.0"}}
```

Kết quả:

```json
{"protocol": 1, "session": "3b0c8f7e-…", "app": "ContextCut", "app_version": "26.08.2", "revision": 1873402}
```

`client` không bắt buộc, chỉ để ghi log. Gọi `auth` lần hai trên cùng kết nối đã xác thực → trả kết quả như trên.

### 8.2 `get_editor_state` [P1a]

Không có tham số. Không có project → `no_project`; đang nạp/đóng → `busy`.

```json
{
  "session": "3b0c8f7e-…",
  "revision": 1873402,
  "project": {
    "path": "D:/Videos/MyVideo.kdenlive",
    "name": "MyVideo",
    "modified": false,
    "companion_dir": "D:/Videos/MyVideo.contextcut"
  },
  "profile": {"fps": {"num": 60, "den": 1}, "width": 1920, "height": 1080},
  "sequence": {"uuid": "{8a1f…}", "name": "Sequence 1", "duration_f": 216000},
  "sequences": [{"uuid": "{8a1f…}", "name": "Sequence 1", "active": true}],
  "playhead_f": 43380,
  "selection": {"items": [42, 43], "zone": {"start_f": 43000, "end_f": 43600}},
  "tracks": [
    {"id": 5, "tag": "V1", "name": "Video", "kind": "video", "locked": false, "muted": false, "hidden": false, "items": 12}
  ],
  "counts": {"clips": 24, "compositions": 0, "guides": 3, "subtitles": 0, "recordings": 2}
}
```

- `project.path` là `null` khi project chưa lưu lần nào; khi đó `companion_dir` cũng `null`. `companion_dir` là chỗ dữ liệu AI sẽ nằm (`MyVideo.contextcut/`), P1a chỉ báo đường dẫn, không tạo.
- `selection.zone` là vùng in/out của timeline; `null` khi chưa đặt (in = out = 0).
- `tracks[].items` là số clip + composition trên track. `hidden` chỉ có nghĩa với track video (đã tắt hình), `muted` chỉ với track audio (đã tắt tiếng); với track loại kia luôn `false`.

### 8.3 `get_timeline` [P1a]

Tham số (đều không bắt buộc):

| Tên | Kiểu | Mặc định | Ghi chú |
| --- | --- | --- | --- |
| `start_f` | int ≥ 0 | 0 | |
| `end_f` | int > `start_f` | độ dài timeline | Lấy item **giao** với `[start_f, end_f)` |
| `tracks` | mảng id hoặc tag | mọi track | Lọc item theo track |
| `limit` | int 1…1000 | 200 | Số item tối đa mỗi trang |
| `cursor` | chuỗi | — | `next_cursor` của trang trước |

Kết quả:

```json
{
  "revision": 1873402,
  "sequence": {"uuid": "{8a1f…}", "name": "Sequence 1", "duration_f": 216000},
  "fps": {"num": 60, "den": 1},
  "range": {"start_f": 0, "end_f": 600},
  "tracks": [ "…như get_editor_state…" ],
  "items": [
    {"id": 42, "kind": "clip", "track": 5, "start_f": 0, "end_f": 300,
     "source": "4", "src_in_f": 120, "src_out_f": 420, "name": "2026-10-20 21-00-00.mkv",
     "speed": 1.0, "enabled": true, "content": "video", "linked": 43, "effects": ["Fade in"]},
    {"id": 61, "kind": "composition", "track": 6, "start_f": 280, "end_f": 320,
     "name": "Wipe", "asset": "luma"}
  ],
  "guides": [{"f": 3600, "comment": "Hook", "category": 0}],
  "sources": {"4": {"name": "2026-10-20 21-00-00.mkv", "type": "av", "recording": true}},
  "next_cursor": null
}
```

- `items` sắp theo `start_f`, rồi thứ tự track hiển thị, rồi `id`.
- Clip: `content` là `video` | `audio` (Kdenlive luôn tách clip có tiếng thành một clip hình trên track V và một clip tiếng trên track A, nối nhau qua `linked`); `enabled` là `false` khi clip bị tắt; `linked` là id clip audio/video đi cặp (`null` nếu không có); `effects` là tên hiển thị các hiệu ứng đang bật, theo thứ tự stack; `speed` khác 1 thì `src_in_f`/`src_out_f` tính theo frame của producer đã đổi tốc độ (P1 chỉ đọc, chưa sửa tốc độ).
- `guides`: guide của sequence nằm trong `[start_f, end_f)`, mọi trang đều có (tối đa 1000, thừa thì có `"guides_truncated": true`).
- `sources`: chỉ các nguồn mà item trong trang này dùng; chi tiết ở `list_recordings`.
- Track phụ đề chưa có trong `get_timeline` (P2: `get_transcript`/phụ đề).

### 8.4 `list_recordings` [P1a]

Một project có thể có **nhiều bản ghi** (design §8.8): OBS chia file, một video ghép nhiều buổi, series "100 ngày". Bản ghi = clip trong bin có hình (kiểu `av` hoặc `video`, từ file). Nhạc, ảnh, title, màu, sequence không phải bản ghi.

Tham số: `limit` (1…500, mặc định 100), `cursor`.

```json
{
  "revision": 1873402,
  "recordings": [
    {"id": "4", "name": "2026-10-20 21-00-00.mkv", "path": "D:/OBS/2026-10-20 21-00-00.mkv",
     "file_hash": "5d41402abc4b2a76b9719d911017c592", "type": "av", "ready": true,
     "duration_f": 432000, "source_fps": 60.0, "width": 1920, "height": 1080,
     "audio_streams": [{"index": 1, "name": "Stereo 48kHz aac", "channels": 2}, {"index": 2, "name": "Mono 48kHz aac", "channels": 1}],
     "on_timeline": true, "track_map": null, "day_start": null}
  ],
  "next_cursor": null
}
```

- `id` = `kdenlive:id` của bin clip, ổn định giữa các lần mở; mọi dữ liệu phân tích (transcript, sự kiện, khoảnh khắc) về sau mang id này.
- `audio_streams[].index` là chỉ số stream MLT (đếm cả stream hình, nên OBS track 1 thường là `index: 1`); `name` là mô tả Kdenlive (`Mono 48kHz aac`) hoặc tên người dùng đặt trong Kdenlive. Tên track OBS ghi trong file (Mic, Discord…) chưa đọc ở P1a; P2 đọc bằng ffprobe khi dựng `track_map`.
- `file_hash` = hash Kdenlive tính trên phần đầu và cuối file (dùng làm khoá cache phân tích); `null` nếu file thiếu.
- `duration_f` tính theo fps của project. `ready` là `false` khi Kdenlive chưa nạp xong clip (các trường kích thước, stream có thể chưa đúng).
- Composition: `name` là tên hiển thị, `asset` là id asset Kdenlive (`luma`, `qtblend`…).
- `track_map` (P2: track nào là Mic/Discord/Game) và `day_start` (P7) là `null` cho tới khi các giai đoạn đó lưu chúng vào `MyVideo.contextcut/recordings.json`.

### 8.5 `list_operations`, `validate_operations`, `apply_operations` [P1c]

```json
{"method": "apply_operations",
 "params": {"base_revision": 1873402, "label": "AI: cắt đoạn chết 03:10–04:02",
            "reason": "đoạn đi đường không có thoại",
            "ops": [{"type": "cut_range", "start_f": 11400, "end_f": 14520}]}}
```

- `label` bắt buộc, bắt đầu bằng `"AI: "` (app tự thêm nếu thiếu); là tên bước undo trong lịch sử Kdenlive.
- Kết quả: `{"batch_id": "…", "revision": <mới>, "created": {"<op_index>": [id…]}}`.
- **Một đợt = một bước undo.** Mọi op của đợt gom `Fun undo/redo` rồi `pCore->pushUndo` đúng một lần. Op nào lỗi → chạy `undo` đã gom, timeline về y hệt, trả `apply_failed` kèm `op_index`.
- `validate_operations(ops)` cùng tham số trừ `base_revision`/`label`, trả `{"ok": bool, "errors": [{"op_index", "field", "message"}], "warnings": [...]}`, không đổi gì.
- Op P1: `cut_range`, `split`, `trim`, `move`, `insert_clip`, `add_music`, `title_card`, `caption` (bản đơn giản). Tham số theo design §9 và Kiến trúc v3 "Timeline và thao tác"; schema chốt ở P1c và trả qua `list_operations`.

### 8.6 `add_markers` [P1c]

`{"base_revision", "markers": [{"f": 43380, "comment": "phản ứng", "category": 2}]}` → thêm guide trên sequence đang mở, một bước undo "AI: thêm marker". Trả revision mới.

## 9. Phiên bản

`protocol` = 1. Thêm method hay thêm trường kết quả không làm tăng số; đổi nghĩa hay bỏ trường thì tăng và client kiểm `protocol` trong `bridge.json`/`auth`.
