---
title: Cách dùng phần mềm
summary: Frame, khoảng nửa mở, fps, id, track và tag, bản ghi, revision/base_revision, phân trang, lỗi, tool có bây giờ và ở giai đoạn sau.
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

## Revision

- Mọi kết quả đọc có `revision`. Khác lần trước nghĩa là timeline có thể đã đổi (người dùng sửa, undo, redo, đổi sequence hay project). Chỉ so bằng; giá trị không có thứ tự.
- Chọn clip, dời playhead, zoom timeline không đổi `revision`.
- Từ P1c, lệnh sửa gửi `base_revision` = `revision` vừa đọc. Người dùng sửa chen ngang thì lệnh bị từ chối (`conflict`), timeline không đổi gì: đọc lại rồi đề xuất lại.

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
| Tham số sai | Sai kiểu hoặc ngoài khoảng | Sửa tham số |
| Không có `…` | Track hay clip không tồn tại | Xem lại `get_editor_state` |

## Tool

| Tool | Việc | Có từ |
| --- | --- | --- |
| `get_editor_state` | Project, fps, kích thước, sequence, playhead, vùng chọn, track, số lượng, revision | **bây giờ** |
| `get_timeline` | Clip, composition, marker trong một khoảng; phân trang | **bây giờ** |
| `list_recordings` | Bản ghi của project: id, file, hash, độ dài, stream audio, đã lên timeline chưa | **bây giờ** |
| `get_guide` | Đọc hướng dẫn này theo topic | **bây giờ** |
| `list_operations`, `validate_operations`, `apply_operations`, `add_markers` | Sửa timeline, mỗi đợt một bước undo nhãn `AI: …`; op `cut_range`, `split`, `trim`, `move`, `insert_clip`, `add_music`, `title_card`, `caption` | P1c |
| `transcribe`, `get_transcript`, `get_context`, `get_job` | Lời thoại theo từ, sự kiện | P2 |
| `get_contact_sheet`, `get_source_frames`, `render_frames`, `get_viewer_frame` | Xem hình | P2 |
| `export`, `zoom` | Xuất file; zoom phản ứng | P2 |
| `find_moments`, `detect_beats`, `beat_montage`, `get_outline`, `save_outline`, `list_assets` | Khoảnh khắc, beat, dàn ý, thư viện nhạc/SFX/meme | P3 |
| `register_pov`, `sync_pov`, `pov_placeholder`, `pov_switch` | Nhiều POV | P4 |

Tool chưa có thì không gọi được. Người dùng cần thì nói rõ là chưa có, rồi đề xuất cách tạm (người dùng làm tay theo mốc frame).
