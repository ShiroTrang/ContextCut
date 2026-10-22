# Giao thức cầu nối ContextCut (AI Bridge) — v1

21/10/2026, cập nhật 22/10/2026 (P1c, P2a, P2b) · trạng thái: **hợp đồng cho P1–P2** (P1a, P1c, P2a, P2b cài; P1b dựa vào) · nguồn: design v3.1 §9, Kiến trúc v3 mục "AI chỉnh trực tiếp và nhìn video", "Timeline và thao tác", "Bảo mật".

App ContextCut (C++) mở một server WebSocket cục bộ. Dịch vụ Python `contextcut-ai` (MCP server) là client duy nhất dự kiến; AI client (Claude, Codex, Antigravity) không nói chuyện thẳng với cầu nối. Tài liệu này là hợp đồng giữa hai bên: đổi thứ gì ở đây thì tăng `protocol` hoặc ghi rõ là trường mới không bắt buộc.

Ký hiệu: **[P1a]** cài ở P1a; **[P1c]** cài ở P1c (22/10/2026); **[P2a]** cài ở P2a; **[P2b]** cài ở P2b.

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
| Phạm vi | Chỉ có các method trong registry dưới đây. Không method nào chạy shell, đọc file tùy ý hay ghi đè file gốc. `import_media` chỉ nhận đuôi file media, đường dẫn tuyệt đối, và từ chối đường đi qua symlink/shortcut/junction (§8.8). |

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
| -32003 | `conflict` | `base_revision` khác revision hiện tại; `undo_batch` khi đợt không còn là bước undo trên cùng **[P1c]** | `current_revision` |
| -32004 | `stale_cursor` | `cursor` thuộc revision cũ hoặc sai dạng | `current_revision` |
| -32005 | `busy` | Project đang nạp hoặc đang đóng | |
| -32006 | `validation_failed` | Ops không hợp lệ, chưa đổi gì **[P1c]** | `errors[]` |
| -32007 | `apply_failed` | Một op lỗi giữa chừng, cả đợt đã hoàn tác **[P1c]** | `op_index`, `field`, `reason` |
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
| `list_sources` | Mọi clip trong bin (bản ghi, nhạc, ảnh, title…) để chọn `source`; phân trang | P1c |
| `list_operations` | Danh mục op + schema tham số | P1c |
| `validate_operations` | Kiểm một đợt op, không đổi gì | P1c |
| `apply_operations` | Một đợt op = một bước undo có nhãn | P1c |
| `add_markers` | Thêm guide/marker để Nhan xem | P1c |
| `undo_batch` | Hoàn tác đợt vừa áp dụng (khi còn là bước undo trên cùng) | P1c |
| `import_media` | Nhập một file media vào bin (một bước undo) | P1c |
| `list_subtitles` | Phụ đề trên track phụ đề của sequence đang mở; phân trang | P2a |
| `get_scene` | XML MLT của sequence đang mở như khi xuất (để `melt` dựng khung hình, xuất file) | P2b |
| `get_viewer_frame` | Khung hình monitor đang hiện (JPEG), tuỳ chọn dời playhead trước | P2b |

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
  "counts": {"clips": 24, "compositions": 0, "guides": 3, "subtitles": 0, "recordings": 2},
  "undo": {"index": 12, "count": 12, "next_undo": "AI: cắt đoạn chết 03:10–04:02", "next_redo": null}
}
```

- `project.path` là `null` khi project chưa lưu lần nào; khi đó `companion_dir` cũng `null`. `companion_dir` là chỗ dữ liệu AI sẽ nằm (`MyVideo.contextcut/`), P1a chỉ báo đường dẫn, không tạo.
- `selection.zone` là vùng in/out của timeline; `null` khi chưa đặt (in = out = 0).
- `undo` **[P1c]**: undo stack của project — `index` (số bước đang áp dụng), `count`, `next_undo`/`next_redo` là nhãn bước Ctrl+Z / Ctrl+Shift+Z sẽ chạy (`null` nếu không có; Undo History của Kdenlive hiện thêm giờ `hh:mm` phía trước, ở đây đã bỏ). Đợt của AI có nhãn `AI: …`.
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
- Track phụ đề không có trong `get_timeline`; đọc bằng `list_subtitles` (§8.9) **[P2a]**.

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
- `duration_f` tính theo fps của project. `ready` là `false` khi Kdenlive chưa nạp xong clip (các trường kích thước, stream có thể chưa đúng). Trong lúc clip còn đang nạp, `duration_f`, `source_fps`, `width`, `height` là `null` và `audio_streams` có thể rỗng: app không đọc producer của clip đang nạp, vì Kdenlive khoá nó cho tới khi nạp xong.
- Composition: `name` là tên hiển thị, `asset` là id asset Kdenlive (`luma`, `qtblend`…).
- `track_map` (P2: track nào là Mic/Discord/Game) và `day_start` (P7) là `null` cho tới khi các giai đoạn đó lưu chúng vào `MyVideo.contextcut/recordings.json`.

### 8.4b `list_sources` [P1c]

Như `list_recordings` (`limit` 1…500, mặc định 100, `cursor`) nhưng gồm **mọi** clip trong bin, không có thư mục: nguồn cho `insert_clip`/`add_music` (nhạc, SFX, ảnh, title, bản ghi).

```json
{"revision": 1873402,
 "sources": [{"id": "9", "name": "Can Can.mp3", "type": "audio", "path": "D:/Nhạc/Can Can.mp3", "duration_f": 9000,
              "has_video": false, "has_audio": true, "ready": true, "on_timeline": false, "recording": false}],
 "next_cursor": null}
```

`duration_f` là `null` với nguồn không giới hạn độ dài (màu, ảnh tĩnh kéo dài tuỳ ý) và với clip đang nạp (`ready: false`, như §8.4); `recording` như định nghĩa ở §8.4.

### 8.5 Sửa timeline: `list_operations`, `validate_operations`, `apply_operations` [P1c]

Một **đợt** là danh sách op chạy theo thứ tự trên sequence đang mở. Op sau thấy timeline đã bị op trước đổi (vd. sau `cut_range` mọi clip phía sau đã dời sớm hơn).

```json
{"method": "apply_operations",
 "params": {"base_revision": 1873402, "label": "AI: cắt đoạn chết 03:10–04:02",
            "reason": "đoạn đi đường không có thoại",
            "ops": [{"type": "cut_range", "start_f": 11400, "end_f": 14520, "reason": "im lặng 52 giây"}]}}
```

Kết quả:

```json
{"batch_id": "5f0c…", "revision": 1873460, "label": "AI: cắt đoạn chết 03:10–04:02", "created": {}, "warnings": []}
```

- `base_revision` (bắt buộc): `revision` vừa đọc. Khác revision hiện tại → `conflict` kèm `current_revision`, **không đổi gì**. Kiểm trước mọi thứ khác (kể cả kiểm tham số).
- `label` (bắt buộc, 1…200 ký tự): tên bước undo trong Undo History; app thêm `"AI: "` nếu thiếu. `reason` (không bắt buộc, ≤ 500 ký tự) ở cả đợt và từng op: lý do một câu, P5 hiện trong dock Hoạt động AI.
- `ops`: 1…200 op. Trường lạ trong op bị bỏ qua kèm cảnh báo (dễ thấy gõ sai tên trường).
- **Một đợt = một bước undo.** Mọi op gom `Fun undo/redo` rồi `pCore->pushUndo` đúng một lần. Ctrl+Z một lần hoàn tác cả đợt.
- Tham số sai kiểu/khoảng (kiểm trước khi chạy) → `validation_failed`, `data.errors = [{"op_index", "field", "message"}]`, không đổi gì.
- Op lỗi khi chạy (kiểm theo trạng thái lúc tới lượt op đó, hoặc hàm Kdenlive từ chối) → hoàn tác mọi op trước của đợt, trả `apply_failed` kèm `op_index`, `field`, `reason`; undo stack không thêm bước nào.
- `created`: id clip mới theo chỉ số op (`{"3": [87, 88]}`): clip nửa sau của `split`, clip hình + tiếng của `insert_clip`, clip của `add_music`/`title_card`/`caption`.
- `warnings`: `[{"op_index", "message"}]`, vd. track khoá không bị `cut_range` cắt (lệch đồng bộ), dùng track mặc định thay track không tìm thấy theo tên.
- Thanh trạng thái của app hiện "AI đang sửa: <nhãn>…" lúc chạy và "<nhãn> — xong. Ctrl+Z để hoàn tác." khi xong.

`validate_operations(ops)` kiểm như `apply_operations` nhưng không đổi gì và không cần `base_revision`/`label`:

```json
{"ok": false, "errors": [{"op_index": 1, "field": "at_f", "message": "V1 already has a clip in [300, 450)"}],
 "warnings": [{"op_index": 2, "message": "checked against the current timeline; earlier ops of this batch change it, apply re-checks"}]}
```

Op đứng sau một op làm đổi timeline thì lỗi theo trạng thái chỉ là cảnh báo (`apply` kiểm lại đúng lúc).

`list_operations()` trả schema mọi op:

```json
{"ops": [{"type": "split", "summary": "Cut a clip (and its linked audio/video) in two at a timeline frame",
          "params": {"clip_id": {"type": "clip", "required": true, "description": "…"},
                     "at_f": {"type": "frame", "required": true, "description": "…"}}}]}
```

Kiểu tham số: `frame` (int ≥ 0, frame timeline hoặc frame nguồn theo fps project), `int`, `number`, `string`, `enum` (`values`), `bool`, `track` (id số, tag `"V1"` hoặc tên track, không phân biệt hoa thường), `clip` (id clip timeline), `source` (id bin clip = `kdenlive:id`, chuỗi, xem `list_sources`), `items` (mảng object, mô tả phần tử trong `description`) **[P2a]**. Có `min`/`max` (số), `min_length`/`max_length` (chuỗi), `min_items`/`max_items` (`items`), `values` (enum), `default` khi áp dụng.

#### Op P1

Mọi khoảng nửa mở; mọi op nhận thêm `reason`.

| Op | Tham số | Việc (hàm Kdenlive) |
| --- | --- | --- |
| `cut_range` | `start_f`, `end_f` | Cắt bỏ `[start_f, end_f)` trên **mọi track không khoá** rồi kéo phần sau lên lấp chỗ trống (ripple). Không track nào khoá và guide không bị khoá thì guide trong khoảng bị xoá, guide sau khoảng dời theo (như Extract Zone). Track khoá giữ nguyên → cảnh báo lệch đồng bộ. **[P2a]** Track phụ đề không khoá thì đi theo: phụ đề nằm trọn trong khoảng bị xoá, phụ đề cắt ngang bị thu lại phần nằm trong khoảng, phụ đề sau khoảng dời lên; khoá thì giữ nguyên (cảnh báo). |
| `split` | `clip_id`, `at_f` | Cắt clip (và clip cặp `linked`/cùng nhóm) tại `at_f`, `start_f < at_f < end_f`. `created` = các clip nửa sau. |
| `trim` | `clip_id`, `start_f?`, `end_f?` | Đặt mép mới trên timeline (ít nhất một). Mép trái dời thì điểm vào nguồn dời theo. Clip cặp có cùng mép được cắt theo. Không vượt nguồn, không chồng clip bên cạnh. |
| `move` | `clip_id`, `at_f`, `track?` | Dời clip tới `at_f` (mép trái), giữ track nếu không nói. Clip trong nhóm (cặp hình+tiếng) dời cả nhóm cùng độ lệch. Chỗ đích phải trống. |
| `insert_clip` | `source`, `in_f`, `out_f`, `track`, `at_f`, `audio_track?`, `audio_stream?`, `audio?` (mặc định `true`) | Đặt khoảng nguồn `[in_f, out_f)` vào `at_f` trên `track` (chỗ trống, không ripple). Nguồn có hình + tiếng và track là track video: clip tiếng lên `audio_track` (mặc định track audio đối xứng của `track`), stream `audio_stream` (chỉ số MLT như `list_recordings`; mặc định stream mặc định của clip), hai clip `linked`. Track audio → chỉ tiếng. Không bao giờ hỏi tạo track. |
| `add_music` | `source`, `at_f`, `in_f?` (0), `out_f?` (hết nguồn), `track?`, `gain_db?` (0, -60…20) | Như `insert_clip` chỉ phần tiếng, lên track tên `Nhạc`/`Nhạc/SFX`/`Music` (hoặc `track`). `gain_db ≠ 0` → hiệu ứng `volume` (`level` dB). |
| `title_card` | `text` (1…200), `start_f`, `end_f`, `track?`, `style?` (`black` \| `dim`) | Thẻ chữ toàn màn hình: title clip (`kdenlivetitle`) mới trong bin, chữ trắng giữa khung trên nền đen (`black`) hoặc đen mờ (`dim`). Track mặc định: track video tên `Chữ`/`Text`/`Title`, không có thì track video trên cùng (cảnh báo). |
| `caption` | `text` (1…300), `start_f`, `end_f`, `speaker?`, `track?`, `style?` (`bottom` \| `top` \| `pop`), `color?`, `uppercase?`, `label?` | Câu đắt: title clip chữ trắng viền đen ở đáy (`bottom`) hoặc trên (`top`) khung, `pop` chữ vàng to; `speaker` thêm "<speaker>: " đầu câu khi `label` (mặc định `true`). Track như `title_card`. **[P2a]** `color` = màu chữ `#RRGGBB` (thay màu của style), `uppercase` (mặc định `false`) viết hoa toàn câu. MCP server tự điền ba trường này theo người nói (`speakers.json`) nếu agent bỏ trống. |
| `add_subtitles` **[P2a]** | `items` (1…5000 phần tử `{start_f, end_f, text (1…500), speaker?}`), `layer?` (0) | Thêm từng dòng vào **track phụ đề** của sequence (tạo track nếu chưa có, như khi thêm phụ đề tay). Các dòng không được chồng nhau, không chồng phụ đề có sẵn trên layer đó, track phụ đề không khoá. `speaker` ghi vào trường Name của sự kiện ASS. `
` trong `text` là xuống dòng. `created` = id phụ đề mới. |
| `clear_subtitles` **[P2a]** | `start_f`, `end_f`, `layer?` | Xoá phụ đề **bắt đầu** trong `[start_f, end_f)` (bỏ trống `layer` = mọi layer). Đặt trước `add_subtitles` trong cùng đợt để thay phụ đề một đoạn bằng một bước undo. |
| `zoom` **[P2b]** | `start_f`, `end_f`, `scale?` (1.05…4, mặc định 1.2), `focus_x?`, `focus_y?` (0…1, mặc định 0.5), `ramp_in_f?` (mặc định ≈ 0,2 s), `ramp_out_f?` (0), `ease?` (`out` \| `in` \| `linear` \| `smooth`, mặc định `out`), `track?` | Zoom vào khung: cắt clip hình phủ trọn khoảng tại `start_f`/`end_f` (khi hai mốc nằm giữa clip; clip cặp tiếng cắt theo), thêm hiệu ứng **Transform** (`qtblend`) có keyframe `rect` vào clip ở giữa: từ 1 lên `scale` trong `ramp_in_f` frame đầu, giữ, về 1 trong `ramp_out_f` frame cuối (0 = cắt thẳng về khung thường ở `end_f`). Điểm (`focus_x`, `focus_y`) của khung (0,0 = góc trái trên) đứng yên khi zoom. `ease` là kiểu keyframe MLT của đoạn chuyển (`cubic_out`, `cubic_in`, `linear`, `smooth_natural`). Track mặc định: track video không khoá trên cùng có clip **từ file có hình** (không phải title, màu) phủ trọn khoảng. Lỗi: khoảng không nằm trọn trong một clip, clip đã có Transform, `ramp_in_f + ramp_out_f > end_f − start_f`. `created` = `[id clip mang zoom]`. |

Kiểm trước khi chạy (validator P1, thêm phụ đề ở P2a): op có trong registry; tham số đúng kiểu và khoảng; track có, không khoá, đúng loại (op hình → track video; `add_music` → track audio); clip có, không nằm trên track khoá, không có mix (chuyển cảnh cùng track) khi `trim`/`move`; nguồn có trong bin, đã nạp, có hình/tiếng mà op cần; frame trong độ dài nguồn; khoảng đích trống trên track. Quy tắc §8.6 của thiết kế (giữa từ, giữa phản ứng, shot quá ngắn) chờ transcript (P2–P4).

### 8.6 `add_markers` [P1c]

```json
{"method": "add_markers",
 "params": {"base_revision": 1873402, "label": "AI: đánh dấu chỗ cần xem",
            "markers": [{"f": 43380, "comment": "phản ứng", "category": 2}]}}
```

Thêm guide trên sequence đang mở, một bước undo (nhãn mặc định `"AI: thêm marker"`). `markers`: 1…500; `f` ≥ 0; `comment` ≤ 500 ký tự; `category` là loại guide của project (0…8 mặc định, xem Kdenlive › Project › Guide categories), bỏ trống thì dùng loại mặc định. Đã có guide tại frame đó thì đổi chú thích/loại. Kết quả `{"batch_id", "revision", "added"}`. Lỗi như `apply_operations` (`conflict`, `validation_failed`).

### 8.7 `undo_batch` [P1c]

`{"batch_id": "5f0c…"}` → hoàn tác đợt (của `apply_operations` hoặc `add_markers`) **chỉ khi** đợt đó còn là bước undo trên cùng (giống bấm Ctrl+Z đúng một lần). Kết quả `{"revision", "undone": "<nhãn>"}`. Đã có bước khác chồng lên (người dùng sửa tay, đợt sau) hoặc đợt đã bị hoàn tác → `conflict`; `batch_id` lạ (kể cả của lần chạy app trước) → `not_found`. P5 mở rộng thành Giữ/Hoàn tác trong dock Hoạt động AI.

### 8.8 `import_media` [P1c]

`{"path": "D:/Nhạc/Can Can.mp3"}` → thêm file vào gốc bin như kéo thả (`ClipCreator::createClipFromFile`), một bước undo `"AI: nhập <tên file>"`, chờ Kdenlive nạp xong tối đa 20 giây (request khác xếp hàng trong lúc đó). Kết quả `{"batch_id", "revision", "source": {…như list_sources…}}`; `ready: false` nếu chưa nạp xong (xem lại `list_sources`).

- `path` phải là đường dẫn tuyệt đối tới một file có thật, đuôi thuộc: video `mkv mp4 mov webm avi mpg mpeg m4v ts flv`, âm thanh `wav mp3 flac ogg oga m4a aac opus wma`, ảnh `png jpg jpeg webp bmp gif`. Sai → `invalid_params` (`field: "path"`).
- Đường dẫn đã resolve (`canonicalFilePath`) phải trùng đường dẫn đưa vào (không phân biệt hoa thường): file hay thư mục cha là symlink, shortcut `.lnk` hay junction thì bị từ chối.
- Nhập lại file đã có trong bin tạo thêm một clip (như Kdenlive); kiểm `list_sources` trước. `open_project` để P2.

### 8.9 `list_subtitles` [P2a]

Tham số (đều không bắt buộc): `start_f` (0), `end_f` (hết timeline), `limit` (1…1000, mặc định 200), `cursor`. Lấy phụ đề **giao** `[start_f, end_f)`, sắp theo `start_f` rồi `layer`. Chưa có track phụ đề → `items: []`.

```json
{"revision": 1873460,
 "track": {"exists": true, "locked": false, "disabled": false, "layers": 1},
 "items": [{"id": 512, "layer": 0, "start_f": 3600, "end_f": 3702, "text": "Ủa alo, nghe không?", "speaker": "Nhan"}],
 "next_cursor": null}
```

`id` là id phụ đề của mô hình timeline (chỉ đúng trong một lần chạy app, như id clip). `speaker` là trường Name của sự kiện ASS (`""` nếu trống). Cursor theo §7.

### 8.10 `get_scene` [P2b]

Tham số: `originals` (bool, mặc định `true`). Không có project → `no_project`/`busy`.

```json
{"revision": 1873460,
 "xml": "<?xml version='1.0' encoding='utf-8'?>
<mlt LC_NUMERIC=\"C\" root=\"D:/Videos\" …>…</mlt>",
 "root": "D:/Videos",
 "profile": {"fps": {"num": 25, "den": 1}, "width": 1920, "height": 1080},
 "duration_f": 30750,
 "proxies": true}
```

- `xml` là XML MLT của **sequence đang mở** đúng như Kdenlive dựng khi xuất (`ProjectManager::projectSceneList(<thư mục project>)`): mọi track, hiệu ứng, title, track phụ đề (filter trỏ tới file `.ass` tạm của app), chưa cần lưu project. `melt` đọc được trực tiếp (`melt scene.mlt in=N out=N …`).
- `originals: true` và project dùng proxy (`proxies: true`) → đường dẫn proxy được thay bằng file gốc (`KdenliveDoc::useOriginals`, như xuất không chọn "dùng proxy"); `false` giữ proxy (nhanh hơn, ảnh mờ hơn).
- `root` là thư mục gốc cho đường dẫn tương đối trong XML (thư mục project; project chưa lưu thì là chuỗi app đặt, đường dẫn trong XML khi đó là tuyệt đối hoặc theo `root`).
- Chỉ đọc, không đổi timeline, không ghi file.

### 8.11 `get_viewer_frame` [P2b]

Tham số (đều không bắt buộc):

| Tên | Kiểu | Mặc định | Ghi chú |
| --- | --- | --- | --- |
| `monitor` | `"active"` \| `"project"` \| `"clip"` | `"active"` | Monitor người dùng đang dùng, monitor project (timeline) hay monitor clip |
| `at_f` | int ≥ 0 | — | Dời playhead của monitor **project** tới frame này trước khi lấy ảnh (người dùng thấy playhead nhảy); ≥ độ dài sequence → `invalid_params` |
| `width` | int 64…1920 | 512 | Chiều cao theo tỉ lệ khung project, làm tròn chẵn |
| `quality` | int 1…100 | 80 | Chất lượng JPEG |

```json
{"monitor": "project", "position_f": 43380, "playing": false, "clip": null,
 "width": 512, "height": 288, "format": "jpeg", "data": "/9j/4AAQ…"}
```

- Ảnh là khung monitor đang hiện, như lệnh Extract Frame của Kdenlive (`MonitorProxy::extractFrame`): cùng proxy và hiệu ứng người dùng đang xem. Monitor clip: `clip` = `{"source", "name"}` của clip đang mở, `position_f` là frame trong clip đó; chưa mở clip nào → `not_found`.
- `at_f` kèm `monitor: "clip"` → `invalid_params`. Dời playhead không đổi `revision`.
- Ảnh trả trong JSON (`data` base64); app không ghi file.

## 9. Phiên bản

`protocol` = 1. Thêm method hay thêm trường kết quả không làm tăng số; đổi nghĩa hay bỏ trường thì tăng và client kiểm `protocol` trong `bridge.json`/`auth`.
