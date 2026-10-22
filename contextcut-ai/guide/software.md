---
title: Cách dùng phần mềm
summary: Frame, khoảng nửa mở, fps, id, track và tag, bản ghi và nguồn, revision/base_revision, sửa timeline theo đợt (op, undo, xung đột), phân trang, lỗi, tool có bây giờ và ở giai đoạn sau.
order: 3
---
# ContextCut qua MCP

ContextCut là Kdenlive 26.08.2 sửa nhẹ, thêm cầu nối cho AI. Timeline đang mở trong app là nguồn sự thật: agent không giữ bản sao riêng và không sửa file `.kdenlive`. Project vẫn mở được bằng Kdenlive gốc.

## Đơn vị

- Thời gian là **frame nguyên** theo fps của project (`profile.fps`). fps là phân số `{num, den}`; `30000/1001` giữ nguyên, không làm tròn.
- Frame sang giây: frame × den / num. Giây sang frame: làm tròn giây × num / den.
- Mọi khoảng là **nửa mở** `[start_f, end_f)`: `end_f` là frame đầu tiên *không* thuộc khoảng. Clip dài 300 frame đặt ở frame 100 có `start_f: 100, end_f: 400`.
- Khoảng nguồn của clip cũng vậy: `src_in_f` thuộc clip, `src_out_f` không thuộc.
- `null` nghĩa là chưa có nguồn tin đáng tin, không phải 0.

## Id

- Id clip, composition, track là số nguyên, chỉ đúng trong một lần chạy app (`session`). Mở lại app thì id đổi.
- Id nguồn (bản ghi, bin clip) là chuỗi (`kdenlive:id`), ổn định giữa các lần mở. Mọi dữ liệu phân tích về sau (transcript, khoảnh khắc) mang id này.

## Track

- `tracks` xếp theo thứ tự hiển thị từ trên xuống: V2, V1, A1, A2… `tag` là nhãn Kdenlive (`V1`, `A2`), `name` là tên người dùng đặt. Tool nhận track bằng id (số) hoặc tag (chuỗi).
- Track video nằm trên che track video nằm dưới: chữ và meme đặt ở track trên cùng.
- Kdenlive tách clip có tiếng thành hai clip: `content: "video"` trên track V và `content: "audio"` trên track A, nối nhau qua `linked`. Cắt hay dời một bên thì nhớ bên kia.
- `hidden` chỉ có nghĩa với track video, `muted` với track audio; `locked` là track không sửa được.
- Tên track dự kiến của ContextCut (theo sơ đồ OBS bên dưới): Video, Chữ, Nhạc/SFX, Mic, Discord, Game. Project hiện tại có thể vẫn là tên mặc định: luôn đọc `tracks` từ `get_editor_state`, đừng đoán.

## Bản ghi

- Bản ghi là video nguồn, thường là file OBS `.mkv` nhiều track audio. Một project có thể có nhiều bản ghi (OBS chia file, ghép nhiều buổi).
- Sơ đồ OBS khuyến nghị: track 1 trộn chung (Discord + Game + Mic), 2 Mic của người quay, 3 Discord (giọng bạn bè), 4 âm thanh game, 5 Desktop Audio dự phòng.
- `audio_streams[].index` là chỉ số stream MLT (đếm cả stream hình), nên OBS track 1 thường là `index: 1`. `name` là mô tả Kdenlive (`Stereo 48kHz aac`), chưa phải tên track OBS. `track_map` (P2) sẽ ghi track nào là Mic, Discord, Game.
- `on_timeline`: bản ghi đã có clip trên timeline chưa. `ready: false`: Kdenlive chưa nạp xong clip.
- `list_sources` liệt kê **mọi** clip trong bin (bản ghi, nhạc, SFX, ảnh, title): `id` là `source` của `insert_clip`/`add_music`. File chưa có trong bin: `import_media(path)` với đường dẫn tuyệt đối người dùng đưa (chỉ file media, không qua symlink); kiểm `list_sources` trước để khỏi nhập trùng.

## Revision

- Mọi kết quả đọc có `revision`. Khác lần trước nghĩa là timeline có thể đã đổi (người dùng sửa, undo, redo, đổi sequence hay project). Chỉ so bằng; giá trị không có thứ tự.
- Chọn clip, dời playhead, zoom timeline không đổi `revision`.
- Lệnh sửa gửi `base_revision` = `revision` vừa đọc. Người dùng sửa chen ngang thì lệnh bị từ chối (`conflict`), timeline không đổi gì: đọc lại rồi đề xuất lại.
- `get_editor_state` có `undo`: `next_undo` là nhãn bước Ctrl+Z sẽ hoàn tác (đợt của agent mang nhãn `AI: …`).

## Sửa timeline

- Một lần `apply_operations` là **một đợt**: danh sách op chạy theo thứ tự, thành **một bước undo** nhãn `AI: …` (app tự thêm `AI: ` nếu thiếu). Ctrl+Z một lần hoàn tác cả đợt; `undo_batch(batch_id)` làm việc đó khi đợt còn là bước trên cùng.
- Op sau thấy timeline đã bị op trước đổi: sau `cut_range`, mọi thứ phía sau dời sớm hơn đúng độ dài đã cắt. Tính mốc frame cho op sau theo timeline mới, hoặc tách thành đợt khác rồi đọc lại.
- Một op lỗi thì cả đợt tự hoàn tác (`apply_failed` kèm `op_index`); tham số sai thì không đổi gì (`validation_failed`). `validate_operations` kiểm trước mà không đổi gì.
- Kết quả: `batch_id`, `revision` mới (dùng làm `base_revision` cho đợt sau, khỏi đọc lại), `created` (id clip mới theo chỉ số op), `warnings` (đọc và báo người dùng).
- Ghi `reason` một câu cho mỗi op cắt hay chuyển cảnh.

| Op | Tham số | Việc |
| --- | --- | --- |
| `cut_range` | `start_f`, `end_f` | Cắt bỏ khoảng trên mọi track không khoá, kéo phần sau lên (ripple); marker sau khoảng dời theo. Track khoá thì lệch đồng bộ (có cảnh báo) |
| `split` | `clip_id`, `at_f` | Cắt clip (cả clip cặp `linked`) làm đôi; `created` = nửa sau |
| `trim` | `clip_id`, `start_f?`, `end_f?` | Đặt mép mới trên timeline; điểm vào nguồn dời theo mép trái |
| `move` | `clip_id`, `at_f`, `track?` | Dời clip (cả clip cặp) tới `at_f`; chỗ đích phải trống |
| `insert_clip` | `source`, `in_f`, `out_f`, `track`, `at_f`, `audio_track?`, `audio_stream?`, `audio?` | Đặt khoảng nguồn `[in_f, out_f)` vào chỗ trống. Track video: hình lên `track`, tiếng xuống `audio_track` (mặc định track audio đối xứng), stream `audio_stream` (chỉ số như `list_recordings`, mặc định stream mặc định); track audio: chỉ tiếng |
| `add_music` | `source`, `at_f`, `in_f?`, `out_f?`, `track?`, `gain_db?` | Phần tiếng của nguồn lên track `Nhạc`/`Music` (hoặc `track`), `gain_db` -60…20 |
| `title_card` | `text`, `start_f`, `end_f`, `track?`, `style?` | Thẻ chữ toàn màn hình (`black` nền đen, `dim` nền mờ), vd. "Trong lúc đó:" |
| `caption` | `text`, `start_f`, `end_f`, `speaker?`, `track?`, `style?` | Câu đắt chữ viền đen (`bottom`, `top`) hoặc vàng to (`pop`) |

- Track nhận id, tag (`V2`) hoặc tên track. Chữ mặc định lên track tên `Chữ`/`Text`/`Title`, không có thì track video trên cùng (có cảnh báo).
- Chèn và dời chỉ vào chỗ trống: cần chỗ thì `cut_range`/`move` trước, trong cùng đợt.
- `add_markers(markers, base_revision)` thêm marker (`f`, `comment`, `category`) để chỉ chỗ cho người dùng xem: một bước undo riêng.


## Phân trang

- `get_timeline`: `start_f`, `end_f` (lấy item **giao** với khoảng), `tracks` (id hoặc tag), `limit` (mặc định 100, tối đa 1000), `cursor`.
- Còn trang thì `next_cursor` là chuỗi; trang sau gửi `cursor` cùng bộ lọc như trang đầu. Timeline đổi giữa hai trang thì lỗi `stale_cursor`: đọc lại từ đầu.
- `list_recordings`: `limit` (tối đa 500), `cursor`.
- `guides` (marker trên timeline: `f`, `comment`, `category`) có ở mọi trang. Người dùng hay đặt marker để chỉ chỗ quan trọng: đọc `comment`.
- `selection.zone` là vùng in/out người dùng đặt trên timeline (`null` khi chưa đặt): "đoạn này" thường là vùng đó hoặc chỗ `playhead_f`.

## Lỗi

| Lỗi | Nghĩa | Làm gì |
| --- | --- | --- |
| "Mở ContextCut trước (…)" | App chưa chạy, chưa mở project (màn hình chào, hộp File Recovery) hoặc đang nạp | Nhờ người dùng mở; gọi lại sau; không gọi lặp |
| "không trả lời sau … giây" | App đang bận, đang mở hộp thoại, hoặc treo | Nhờ người dùng xem app |
| `stale_cursor` | Timeline đổi giữa hai trang | Đọc lại từ trang đầu |
| "Timeline đã đổi từ lúc đọc" (`conflict`) | Người dùng vừa sửa, undo, hoặc đợt khác đã áp dụng; không có gì bị đổi | Đọc lại `get_timeline`, gửi lại với `base_revision` mới |
| "Đợt sửa không hợp lệ" (`validation_failed`) | Tham số sai; không có gì bị đổi | Sửa theo từng dòng `op <i> (<trường>)` |
| "op <i> lỗi khi áp dụng" (`apply_failed`) | Op đó không làm được trên timeline lúc tới lượt; cả đợt đã hoàn tác | Đọc lại, sửa op đó rồi gửi lại |
| "có thể đã được áp dụng" | Kết nối rớt sau khi gửi lệnh sửa | Xem `get_editor_state` (`undo.next_undo`) trước khi gửi lại, tránh áp dụng hai lần |
| Tham số sai | Sai kiểu hoặc ngoài khoảng | Sửa tham số |
| Không có `…` | Track hay clip không tồn tại | Xem lại `get_editor_state` |

## Tool

| Tool | Việc | Có từ |
| --- | --- | --- |
| `get_editor_state` | Project, fps, kích thước, sequence, playhead, vùng chọn, track, số lượng, revision | **bây giờ** |
| `get_timeline` | Clip, composition, marker trong một khoảng; phân trang | **bây giờ** |
| `list_recordings` | Bản ghi của project: id, file, hash, độ dài, stream audio, đã lên timeline chưa | **bây giờ** |
| `get_guide` | Đọc hướng dẫn này theo topic | **bây giờ** |
| `list_sources` | Mọi clip trong bin (nhạc, ảnh, title, bản ghi): id làm `source` | **bây giờ** |
| `list_operations`, `validate_operations` | Danh mục op + schema; kiểm một đợt không đổi gì | **bây giờ** |
| `apply_operations` | Sửa timeline, mỗi đợt một bước undo nhãn `AI: …`; op `cut_range`, `split`, `trim`, `move`, `insert_clip`, `add_music`, `title_card`, `caption` | **bây giờ** |
| `add_markers`, `undo_batch` | Thêm marker; hoàn tác đợt vừa áp dụng | **bây giờ** |
| `import_media` | Nhập file media (nhạc, SFX, video, ảnh) vào bin | **bây giờ** |
| `set_track_map` | Sửa sơ đồ track audio của bản ghi (stream nào là Mic, Discord, game) | **bây giờ** |
| `get_job`, `cancel_job` | Theo dõi / huỷ job nền (phiên âm) | **bây giờ** |
| `open_project` | Mở project | P2 |
| `transcribe`, `get_transcript`, `get_context`, `get_job` | Lời thoại theo từ, sự kiện | P2 |
| `get_contact_sheet`, `get_source_frames`, `render_frames`, `get_viewer_frame` | Xem hình | P2 |
| `export`, `zoom` | Xuất file; zoom phản ứng | P2 |
| `find_moments`, `detect_beats`, `beat_montage`, `get_outline`, `save_outline`, `list_assets` | Khoảnh khắc, beat, dàn ý, thư viện nhạc/SFX/meme | P3 |
| `register_pov`, `sync_pov`, `pov_placeholder`, `pov_switch` | Nhiều POV | P4 |

Tool chưa có thì không gọi được. Người dùng cần thì nói rõ là chưa có, rồi đề xuất cách tạm (người dùng làm tay theo mốc frame).
