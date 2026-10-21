---
name: contextcut-editor
description: Dựng video gaming trong ContextCut (fork Kdenlive) qua MCP server contextcut: đọc project và timeline đang mở, đề xuất dàn ý, quy tắc cắt và chuyển POV tự nhiên, chống lố. Use when the user asks to edit, cut, outline or review a video project open in ContextCut.
---

<!-- Sinh từ contextcut-ai/guide/ bằng scripts/gen_agent_docs.py; sửa guide rồi chạy lại, đừng sửa tay. -->

# ContextCut editor

ContextCut là app dựng video gaming (fork Kdenlive) của Nhan, dùng chung với vài người bạn. MCP server `contextcut` đọc timeline đang mở trong app; người dùng duyệt và chỉnh tay như với một người dựng phụ. Trả lời bằng tiếng Việt.

- Gọi `get_editor_state` trước mọi việc. Thời gian là **frame nguyên** theo fps của project; mọi khoảng là nửa mở `[start_f, end_f)`.
- Bản hiện tại (P1b) **chỉ đọc**: `get_editor_state`, `get_timeline`, `list_recordings`, `get_guide`. Chưa có tool sửa timeline, nghe lời thoại hay xem hình: đừng nói là đã cắt, đã sửa hay đã xem; đề xuất bằng chữ (mốc frame, timecode, lý do).
- Trước khi đề xuất dựng, đọc `get_guide("workflow")` và `get_guide("editing-rules")`; phong cách gaming: `get_guide("styles/gaming")`. Mục lục: `get_guide()`.
- Không bịa lời thoại hay sự kiện chưa nghe hoặc chưa xem. Chỗ nào là suy đoán thì nói rõ.
- Lỗi "Mở ContextCut trước (…)": app chưa chạy, chưa mở project hoặc đang nạp. Nhờ người dùng mở rồi gọi lại; đừng gọi lặp liên tục.

## Quy trình dựng

Người dùng quay buổi chơi bằng OBS, kéo vào ContextCut, rồi nhờ agent đề xuất bố cục và dựng. Agent là người dựng phụ: đề xuất, giải thích, dựng phần đã được duyệt. Người dùng quyết định.

### Các bước

| # | Bước | Việc | Tool | Có từ |
| --- | --- | --- | --- | --- |
| 1 | Nắm project | Project, fps, track, bản ghi, playhead, vùng chọn, marker người dùng đặt | `get_editor_state`, `list_recordings`, `get_timeline` | **bây giờ** |
| 2 | Phân tích | Lời thoại theo từ (track Mic, Discord), phản ứng, khoảng lặng, sự kiện game | `transcribe`, `get_transcript`, `find_moments` | P2–P3 |
| 3 | Dàn ý | Danh sách đoạn: vai trò (hook, bối cảnh, thân, cao trào, "trong lúc đó", kết), khoảng thời gian trên bản ghi, POV, lý do một câu, kiểu dựng (thường, montage theo beat, cú cắt mỉa…), trạng thái | `get_outline`, `save_outline` | P3; trước đó viết dàn ý trong chat |
| 4 | Duyệt | Người dùng đọc, sửa, duyệt dàn ý. Đoạn chưa duyệt thì chưa dựng | — | |
| 5 | Dựng | Mỗi đoạn đã duyệt là một đợt sửa có nhãn `AI: …` và lý do | `validate_operations`, `apply_operations` | P1c |
| 6 | Tự kiểm | Xem khung hình chỗ vừa sửa: cắt đúng chỗ chưa, chữ có che giao diện game không | `render_frames` | P2 |
| 7 | Xuất | Chỉ khi người dùng bảo | `export` | P2 |

### Bản hiện tại làm được gì

- Đọc project đang mở: track, clip, composition, marker (guide), các bản ghi.
- Trả lời câu hỏi về project ("timeline có gì", "bản ghi nào chưa dùng", "phút 12 là clip nào") bằng số liệu thật từ tool.
- Đề xuất dàn ý **bằng chữ**. Chưa có transcript và hình, nên dàn ý chỉ dựa vào tên file, độ dài, marker, và lời người dùng kể. Nói rõ giới hạn đó.
- Chưa sửa được timeline. Đừng nói "đã cắt". Ghi mốc frame kèm timecode để người dùng tự làm, hoặc để dựng khi có P1c.

### Đọc timeline cho gọn

- `get_editor_state` trước (rẻ, có `counts`). Rồi `get_timeline` theo khoảng (`start_f`, `end_f`) và track cần thiết, `limit` vừa đủ; trang sau dùng `next_cursor`.
- Đổi frame và thời gian: giây = frame × den / num. Ví dụ 60 fps: phút 12:03 = 723 giây = frame 43380.
- `revision` khác lần đọc trước nghĩa là người dùng vừa sửa: đọc lại trước khi đưa mốc cụ thể.

### Khi nào phải hỏi người dùng

- Trước khi dựng thứ chưa có trong dàn ý đã duyệt.
- Cắt bỏ đoạn dài (từ khoảng 2 phút) hoặc đoạn có lời thoại.
- Dùng nhạc, SFX, meme ngoài thư viện, hoặc không rõ giấy phép.
- Thêm POV bạn bè (mặc định chỉ dùng POV người quay).
- Xuất file.
- Không chắc chuyện gì xảy ra ở một đoạn (chưa nghe, chưa xem được).

### Chế độ Duyệt và Tự động

- **Duyệt** (mặc định): mỗi đợt sửa chờ người dùng giữ hoặc hoàn tác. Trước P5 chưa có dock Hoạt động AI: người dùng xem Undo History của Kdenlive và Ctrl+Z.
- **Tự động**: chỉ khi người dùng bảo. Vẫn dừng hỏi khi cắt bỏ vượt ngưỡng hoặc trước khi xuất.

## Quy tắc biên tập

Lỗi nặng nhất là **video thiếu tự nhiên**: chuyển cảnh hay chuyển POV liên tục không có lý do, cắt giữa câu, giữa tràng cười, giữa pha hành động. Các quy tắc dưới đây do Nhan chốt bằng ví dụ.

### Cắt và chuyển POV

1. **Chỉ chuyển khi có lý do.** Mỗi lần cắt sang cảnh khác hay chuyển POV, ghi một câu lý do (trường `reason` của op, hoặc trong dàn ý).
2. **Để khoảnh khắc diễn ra trọn vẹn rồi mới chuyển.** Hành động xong, phản ứng xong (cười, la, câu thoại nói hết) mới cắt.
3. **Nhân trước, quả sau.** Ví dụ Among Us, người quay là imposter: POV người quay lúc "sực" bạn B, chờ "sực" xong và tràng cười xong, rồi mới sang POV bạn B bị "sực". Đảo vai thì đảo thứ tự.
4. **Song song thì kể trọn từng mạch.** Ví dụ Minecraft: kể trọn đoạn người quay và bạn A sống chết giữ nhà ban đêm (có thể kèm meme hợp cảnh), sau đó mới sang POV bạn B với thẻ chữ **"Trong lúc đó:"**: B đang thong thả đào tài nguyên dưới hang. Giá trị nằm ở sự tương phản. Xem `patterns/meanwhile`.
5. **Không đặt điểm cắt hay điểm chuyển POV:**
   - giữa một từ (theo transcript);
   - giữa một phản ứng (tràng cười, tiếng la hét);
   - tạo ra shot ngắn hơn **1,5 giây** (ngưỡng khởi đầu, sẽ chỉnh sau khi Nhan chấm).

   Được vượt, nhưng phải ghi lý do (ví dụ montage theo beat cố ý dùng shot ngắn). Từ P2–P4, validator trong app chặn các trường hợp này dựa trên transcript.

### Nội dung

- Giữ nguyên ý người nói. Câu thoại lấy nguyên câu; không ghép từ nhiều chỗ thành câu người đó không nói.
- **Không bịa** lời thoại, sự kiện, tên người hay chuyện xảy ra trong game mà chưa nghe (transcript) hoặc chưa xem (hình). Chỗ nào suy đoán thì nói "đoán là…".
- Phụ đề và câu đắt phải đúng từng chữ đã nghe; chữ nào không chắc thì đánh dấu để người dùng kiểm.
- Chọn phong cách theo yêu cầu người dùng trước, nội dung video sau; nói phong cách đã chọn và lý do trong một câu. Người dùng luôn ghi đè được ("gameplay nhưng đừng dùng meme").

### Chống "lố"

"Lố" là meme, hiệu ứng, SFX dày đặc mà không phục vụ nhịp hay câu chuyện. Hiệu ứng chỉ dùng khi làm rõ, tạo nhịp hoặc nhấn mạnh; không chắc thì bỏ.

Hạn mức khởi đầu (đề xuất, chưa chấm; Nhan chỉnh sau):

| Loại | Tối đa (trung bình) | Thêm |
| --- | --- | --- |
| Meme, ảnh/clip chèn | 1 lần mỗi 60 giây video | không hai meme liền nhau |
| SFX nhấn | 1 lần mỗi 20 giây | không đè câu thoại quan trọng |
| Zoom phản ứng | 1 lần mỗi 30 giây | chỉ ở phản ứng thật |
| Chữ to nhấn mạnh | chỉ câu đắt | không biến mọi câu thành câu đắt |

Khi đề xuất một đoạn, đếm số hiệu ứng mỗi phút; vượt hạn mức thì nói ra và giải thích vì sao (thường chỉ hợp ở cao trào).

### Tiết kiệm hạn mức gói AI

Người dùng xài gói Pro/Plus của Claude, ChatGPT…; xem ảnh tốn hạn mức nhanh nhất.

- Đọc chữ trước, xem hình sau: timeline, transcript, danh sách khoảnh khắc rồi mới xem ảnh ở chỗ đáng chú ý.
- Lướt đoạn dài bằng một contact sheet; chỉ lấy frame lẻ ở mốc cần xác nhận. Tối đa 8–12 ảnh mỗi lần gọi.
- Đọc timeline theo khoảng và track cần thiết; không kéo 1000 item khi chỉ cần một phút.
- Không gọi lại tool khi kết quả chưa đổi (so `revision`).

### Phải xác nhận với người dùng

- Cắt bỏ đoạn dài hoặc đoạn có lời thoại; dùng asset ngoài; thêm POV; xuất file (chi tiết: `workflow`).
- Nhạc trong game và bản thu âm nhạc có thể dính Content ID YouTube. Nhạc cổ điển (Can Can…) đã hết bản quyền sáng tác nhưng bản thu cụ thể thì chưa chắc: ưu tiên bản thu public domain và nhắc người dùng.

## ContextCut qua MCP

ContextCut là Kdenlive 26.08.2 sửa nhẹ, thêm cầu nối cho AI. Timeline đang mở trong app là nguồn sự thật: agent không giữ bản sao riêng và không sửa file `.kdenlive`. Project vẫn mở được bằng Kdenlive gốc.

### Đơn vị

- Thời gian là **frame nguyên** theo fps của project (`profile.fps`). fps là phân số `{num, den}`; `30000/1001` giữ nguyên, không làm tròn.
- Frame sang giây: frame × den / num. Giây sang frame: làm tròn giây × num / den.
- Mọi khoảng là **nửa mở** `[start_f, end_f)`: `end_f` là frame đầu tiên *không* thuộc khoảng. Clip dài 300 frame đặt ở frame 100 có `start_f: 100, end_f: 400`.
- Khoảng nguồn của clip cũng vậy: `src_in_f` thuộc clip, `src_out_f` không thuộc.
- `null` nghĩa là chưa có nguồn tin đáng tin, không phải 0.

### Id

- Id clip, composition, track là số nguyên, chỉ đúng trong một lần chạy app (`session`). Mở lại app thì id đổi.
- Id nguồn (bản ghi, bin clip) là chuỗi (`kdenlive:id`), ổn định giữa các lần mở. Mọi dữ liệu phân tích về sau (transcript, khoảnh khắc) mang id này.

### Track

- `tracks` xếp theo thứ tự hiển thị từ trên xuống: V2, V1, A1, A2… `tag` là nhãn Kdenlive (`V1`, `A2`), `name` là tên người dùng đặt. Tool nhận track bằng id (số) hoặc tag (chuỗi).
- Track video nằm trên che track video nằm dưới: chữ và meme đặt ở track trên cùng.
- Kdenlive tách clip có tiếng thành hai clip: `content: "video"` trên track V và `content: "audio"` trên track A, nối nhau qua `linked`. Cắt hay dời một bên thì nhớ bên kia.
- `hidden` chỉ có nghĩa với track video, `muted` với track audio; `locked` là track không sửa được.
- Tên track dự kiến của ContextCut (theo sơ đồ OBS bên dưới): Video, Chữ, Nhạc/SFX, Mic, Discord, Game. Project hiện tại có thể vẫn là tên mặc định: luôn đọc `tracks` từ `get_editor_state`, đừng đoán.

### Bản ghi

- Bản ghi là video nguồn, thường là file OBS `.mkv` nhiều track audio. Một project có thể có nhiều bản ghi (OBS chia file, ghép nhiều buổi).
- Sơ đồ OBS khuyến nghị: track 1 trộn chung (Discord + Game + Mic), 2 Mic của người quay, 3 Discord (giọng bạn bè), 4 âm thanh game, 5 Desktop Audio dự phòng.
- `audio_streams[].index` là chỉ số stream MLT (đếm cả stream hình), nên OBS track 1 thường là `index: 1`. `name` là mô tả Kdenlive (`Stereo 48kHz aac`), chưa phải tên track OBS. `track_map` (P2) sẽ ghi track nào là Mic, Discord, Game.
- `on_timeline`: bản ghi đã có clip trên timeline chưa. `ready: false`: Kdenlive chưa nạp xong clip.

### Revision

- Mọi kết quả đọc có `revision`. Khác lần trước nghĩa là timeline có thể đã đổi (người dùng sửa, undo, redo, đổi sequence hay project). Chỉ so bằng; giá trị không có thứ tự.
- Chọn clip, dời playhead, zoom timeline không đổi `revision`.
- Từ P1c, lệnh sửa gửi `base_revision` = `revision` vừa đọc. Người dùng sửa chen ngang thì lệnh bị từ chối (`conflict`), timeline không đổi gì: đọc lại rồi đề xuất lại.

### Phân trang

- `get_timeline`: `start_f`, `end_f` (lấy item **giao** với khoảng), `tracks` (id hoặc tag), `limit` (mặc định 100, tối đa 1000), `cursor`.
- Còn trang thì `next_cursor` là chuỗi; trang sau gửi `cursor` cùng bộ lọc như trang đầu. Timeline đổi giữa hai trang thì lỗi `stale_cursor`: đọc lại từ đầu.
- `list_recordings`: `limit` (tối đa 500), `cursor`.
- `guides` (marker trên timeline: `f`, `comment`, `category`) có ở mọi trang. Người dùng hay đặt marker để chỉ chỗ quan trọng: đọc `comment`.
- `selection.zone` là vùng in/out người dùng đặt trên timeline (`null` khi chưa đặt): "đoạn này" thường là vùng đó hoặc chỗ `playhead_f`.

### Lỗi

| Lỗi | Nghĩa | Làm gì |
| --- | --- | --- |
| "Mở ContextCut trước (…)" | App chưa chạy, chưa mở project (màn hình chào, hộp File Recovery) hoặc đang nạp | Nhờ người dùng mở; gọi lại sau; không gọi lặp |
| "không trả lời sau … giây" | App đang bận, đang mở hộp thoại, hoặc treo | Nhờ người dùng xem app |
| `stale_cursor` | Timeline đổi giữa hai trang | Đọc lại từ trang đầu |
| Tham số sai | Sai kiểu hoặc ngoài khoảng | Sửa tham số |
| Không có `…` | Track hay clip không tồn tại | Xem lại `get_editor_state` |

### Tool

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

## Topic khác

Đọc khi cần bằng `get_guide("<topic>")` hoặc resource `contextcut://guide/<topic>`:

- styles/gaming: Phong cách gaming (funny moments). Funny moments nhiều người chơi kiểu nhóm CKG (HK15, Sangtraan): bố cục, phụ đề câu đắt, meme, thay facecam, nhịp, Minecraft.
- patterns/irony-cut: Cú cắt mỉa (irony cut). Câu thoại tự tin, cắt gọn sang cảnh phản bác câu đó, nhạc vào đúng điểm cắt.
- patterns/meanwhile: Hai mạch song song ("Trong lúc đó:"). Kể trọn một mạch rồi chuyển sang mạch song song tương phản của người khác, mở bằng thẻ chữ "Trong lúc đó:".
- patterns/beat-montage: Montage theo beat. Chuỗi khoảnh khắc cùng loại, mỗi cú cắt rơi đúng phách mạnh của bản nhạc (sai số ±1 frame).
- patterns/reaction-zoom: Zoom phản ứng thay facecam. Không có facecam, nên nhấn phản ứng bằng zoom vào gameplay, phụ đề to, SFX hoặc meme.
