---
name: contextcut-editor
description: Dựng video gaming trong ContextCut (fork Kdenlive) qua MCP server contextcut: đọc project và timeline đang mở, đề xuất dàn ý, quy tắc cắt và chuyển POV tự nhiên, chống lố. Use when the user asks to edit, cut, outline or review a video project open in ContextCut.
---

<!-- Sinh từ contextcut-ai/guide/ bằng scripts/gen_agent_docs.py; sửa guide rồi chạy lại, đừng sửa tay. -->

# ContextCut editor

ContextCut là app dựng video gaming (fork Kdenlive) của Nhan, dùng chung với vài người bạn. MCP server `contextcut` đọc và sửa timeline đang mở trong app; người dùng duyệt và chỉnh tay như với một người dựng phụ. Trả lời bằng tiếng Việt.

- Gọi `get_editor_state` trước mọi việc. Thời gian là **frame nguyên** theo fps của project; mọi khoảng là nửa mở `[start_f, end_f)`.
- Sửa: đọc `revision` → `validate_operations` → `apply_operations(ops, base_revision, label "AI: …")`. Một đợt là một bước undo (Ctrl+Z hoàn tác cả đợt); sửa chen ngang → `conflict`: đọc lại rồi gửi lại. Op: `list_operations`; id nguồn: `list_sources`.
- Chỉ dựng phần người dùng đã duyệt; xong thì báo nhãn đợt, nhắc Ctrl+Z.
- Nghe: `transcribe(recording)` (job nền, `get_job`) rồi `get_transcript` theo khoảng. Phụ đề: `add_subtitles` hoặc op `caption` có `speaker` (câu đắt).
- Xem (≤ 12 ảnh/lần, đọc chữ trước): `get_contact_sheet`/`get_source_frames` (bản ghi gốc), `render_frames` (timeline đã dựng, tự kiểm), `get_viewer_frame` (khung đang xem).
- Xuất chỉ khi người dùng bảo: `export` → họ bấm "Xuất" trong app (không bấm thay) → `get_job` → báo `checks`. Mở project khác: `open_project`.
- Trước khi đề xuất dựng, đọc `get_guide("workflow")` và `get_guide("editing-rules")`; phong cách gaming: `get_guide("styles/gaming")`. Mục lục: `get_guide()`.
- Không bịa lời thoại hay sự kiện chưa nghe, chưa xem; chỗ suy đoán thì nói rõ.
- Lỗi "Mở ContextCut trước (…)": nhờ người dùng mở app/project rồi gọi lại; đừng gọi lặp.

## Quy trình dựng

Người dùng quay buổi chơi bằng OBS, kéo vào ContextCut, rồi nhờ agent đề xuất bố cục và dựng. Agent là người dựng phụ: đề xuất, giải thích, dựng phần đã được duyệt. Người dùng quyết định.

### Các bước

| # | Bước | Việc | Tool | Có từ |
| --- | --- | --- | --- | --- |
| 1 | Nắm project | Project, fps, track, bản ghi, playhead, vùng chọn, marker người dùng đặt | `get_editor_state`, `list_recordings`, `get_timeline` | **bây giờ** |
| 2 | Phân tích | Lời thoại theo từ (track Mic, Discord); phản ứng, khoảng lặng, sự kiện game (P3) | `transcribe`, `get_job`, `get_transcript`; `find_moments` (P3) | **bây giờ** (lời thoại) |
| 3 | Dàn ý | Danh sách đoạn: vai trò (hook, bối cảnh, thân, cao trào, "trong lúc đó", kết), khoảng thời gian trên bản ghi, POV, lý do một câu, kiểu dựng (thường, montage theo beat, cú cắt mỉa…), trạng thái | `get_outline`, `save_outline` | P3; trước đó viết dàn ý trong chat |
| 4 | Duyệt | Người dùng đọc, sửa, duyệt dàn ý. Đoạn chưa duyệt thì chưa dựng | — | |
| 5 | Dựng | Mỗi đoạn đã duyệt là một đợt sửa có nhãn `AI: …` và lý do | `list_operations`, `validate_operations`, `apply_operations` | **bây giờ** |
| 6 | Tự kiểm | Xem khung hình chỗ vừa sửa: cắt đúng chỗ chưa, zoom đúng chỗ chưa, chữ có che giao diện game không | `render_frames` | **bây giờ** |
| 7 | Xuất | Chỉ khi người dùng bảo; hỏi tên và chỗ lưu file; app hỏi người dùng xác nhận | `export`, `get_job` | **bây giờ** |

### Bản hiện tại làm được gì

- Đọc project đang mở: track, clip, composition, marker (guide), các bản ghi, mọi clip trong bin.
- Trả lời câu hỏi về project ("timeline có gì", "bản ghi nào chưa dùng", "phút 12 là clip nào") bằng số liệu thật từ tool.
- **Nghe lời thoại**: phiên âm theo từng từ track Mic (Nhan) và Discord (bạn bè), đọc theo khoảng trên timeline hoặc bản ghi gốc.
- **Xem hình**: lướt bản ghi bằng contact sheet, xem frame gốc ở mốc cụ thể, xem timeline đã dựng (như file xuất) để tự kiểm, xem khung người dùng đang nhìn. Đề xuất dàn ý dựa trên transcript, hình đã xem, marker và lời người dùng kể; chỗ chưa xem thì nói rõ là đoán.
- **Sửa timeline** phần đã duyệt: cắt bỏ đoạn, cắt/tỉa/dời clip, chèn đoạn từ bản ghi, thêm nhạc, thẻ chữ "Trong lúc đó:", câu đắt theo người nói, phụ đề đầy đủ, marker, **zoom** vào gameplay. Chưa có: hiệu ứng khác (P6).
- **Xuất** MP4 (YouTube 1080p60 hoặc theo project) sau khi người dùng bấm "Xuất" trong app; **mở** project `.kdenlive` khác.

### Nghe trước khi dựng

1. `list_recordings`: bản ghi nào, có `track_map` chưa (stream nào là Mic, Discord). Sơ đồ đoán sai (người dùng bảo) thì `set_track_map`.
2. `transcribe(recording)`: trả `job_id` (hoặc `cached: true` nếu đã có). Buổi quay dài mất vài phút đến vài chục phút: báo người dùng, rồi chờ bằng `get_job(job_id, wait_s=50)` (tool tự chờ, trả ngay khi xong; chưa xong thì gọi lại). Đừng hẹn giờ quay lại hay kết thúc lượt khi job chưa xong: ở chế độ không tương tác sẽ không có lượt sau.
3. Tool báo thiếu model hay thư viện kèm **dung lượng**: hỏi người dùng có đồng ý tải không, đồng ý mới gọi lại với `allow_download: true`. Không tự tải.
4. Xong thì `get_transcript` theo khoảng (`start_f`, `end_f`), `track` khi chỉ cần một người; `words: true` khi cần mốc từng từ (câu đắt). Đọc từng khoảng, đừng kéo cả buổi 2 giờ một lần.
5. Dàn ý và mốc cắt dựa vào lời thật: không cắt giữa câu, giữa tràng cười (xem `editing-rules`).

### Phụ đề

- Phụ đề đầy đủ: `add_subtitles(start_f?, end_f?)` sau khi đã dựng xong đoạn; `preview: true` để đọc thử trước. Một bước undo.
- Câu đắt: op `caption` có `speaker`, mốc từ `get_transcript(words=true)`; style theo người nói tự điền. Xem `get_guide("patterns/subtitles")`.

### Xem hình

Ảnh tốn hạn mức gói AI nhất: đọc chữ (timeline, transcript) trước, xem hình ở chỗ đáng chú ý.

1. Lướt một đoạn dài của bản ghi: `get_contact_sheet(recording, start_f, end_f)`: một ảnh 4×3 ô có nhãn giờ, phần chữ cho biết ô nào là frame nào.
2. Xem kỹ một mốc: `get_source_frames(recording, frames)` (frame gốc, chưa có hiệu ứng; `on: "timeline"` để đưa frame timeline).
3. Sau khi sửa: `render_frames(frames)` ở chỗ vừa sửa (đầu, giữa, cuối đoạn): đúng như file xuất (cắt, zoom, chữ, phụ đề). Sai thì sửa tiếp hoặc `undo_batch`, rồi kiểm lại.
4. Người dùng nói "chỗ này": `get_viewer_frame()` là khung họ đang xem; `at_f` dời playhead tới mốc mình muốn chỉ cho họ thấy.
5. Client không hiện ảnh: mỗi ảnh có đường dẫn file trong phần chữ, mở file đó (vd. tool đọc file của client).

### Xuất

1. Chỉ xuất khi người dùng bảo. Hỏi tên file và chỗ lưu nếu họ chưa nói (đường dẫn tuyệt đối `.mp4`, không trùng file nguồn), cả timeline hay một đoạn.
2. Preset `youtube-1080p60` khi project là 1920×1080 60 fps (như bản ghi OBS khuyến nghị); project khác cỡ/fps thì `project`, hoặc nhờ người dùng đổi Project Settings. Tool báo rõ khi không khớp.
3. `export(output, start_f?, end_f?)`: ContextCut hiện hộp "AI muốn xuất video" cho người dùng. **Chỉ người dùng bấm "Xuất"**: agent không bấm thay, không điều khiển giao diện, không xuất bằng đường khác (melt, ffmpeg) để lách. Báo người dùng nhìn sang app.
4. Gọi ngay `get_job(job_id, wait_s=50)`, lặp tới khi `done` (job chờ người dùng bấm rồi mới xuất); đừng kết thúc lượt khi job còn chạy. Xuất mất cỡ thời lượng đoạn đó (1080p60 HEVC: ~1× thời gian thực) hoặc lâu hơn với x264.
5. Báo: file, thời lượng, dung lượng, bộ mã hoá (`fallback_reason` khi NVENC hỏng phải dùng x264), `ok` và các `checks` hỏng nếu có. `cancelled` là người dùng không đồng ý (hoặc huỷ): không hỏi lại trừ khi họ bảo.
6. File đã có: chỉ `overwrite: true` khi người dùng đồng ý ghi đè (hộp xác nhận ghi rõ "GHI ĐÈ").

### Mở project khác

`open_project(path)` mở file `.kdenlive` người dùng chỉ. Project đang mở có thay đổi chưa lưu thì app hỏi người dùng Save / Don't Save / Cancel: báo họ trả lời trong app, đừng chọn thay. Kết quả `pending` (kèm `dialog` app đang hỏi): gọi lại `open_project` cùng path để chờ tiếp; `cancelled`: project cũ còn nguyên. Sau khi mở, mọi id clip, track, `batch_id` cũ hết giá trị: đọc lại `get_editor_state`.

### Một lần sửa

1. `get_editor_state` (lấy `revision`, track) và `get_timeline` đúng khoảng sắp sửa; `list_sources` khi cần id nhạc hay bản ghi. Lần đầu: `list_operations`.
2. Soạn đợt op theo đoạn đã duyệt; mỗi op cắt hay chuyển cảnh có `reason`. Mốc frame của op sau tính theo timeline sau op trước (`cut_range` làm dời mọi thứ phía sau).
3. `validate_operations` nếu đợt phức tạp; sửa lỗi theo `op_index`/`field`.
4. `apply_operations(ops, base_revision, label)`; nhãn ngắn, nói được việc: "AI: cắt đoạn chết 03:10–04:02".
5. Báo người dùng: nhãn đợt, đã đổi gì (mốc timecode), cảnh báo nếu có, và "Ctrl+Z để hoàn tác". `conflict` thì đọc lại và hỏi lại nếu đoạn đó người dùng vừa sửa.
6. Đợt sau dùng `revision` trả về làm `base_revision`.

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
- Tải model hoặc thư viện (tool báo dung lượng).
- Không chắc chuyện gì xảy ra ở một đoạn (chưa nghe, chưa xem được), hoặc transcript có từ `low_conf` ở chỗ quan trọng.

### Chế độ Duyệt và Tự động

- **Duyệt** (mặc định): mỗi đợt sửa chờ người dùng giữ hoặc hoàn tác. Trước P5 chưa có dock Hoạt động AI: người dùng xem Undo History của Kdenlive và Ctrl+Z; agent tự hoàn tác đợt vừa làm bằng `undo_batch` khi người dùng bảo.
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

   Được vượt, nhưng phải ghi lý do (ví dụ montage theo beat cố ý dùng shot ngắn). Validator trong app chưa chặn (P3–P4); đến lúc đó tự kiểm bằng `get_transcript(words=true)` quanh mỗi điểm cắt.

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
- Lướt đoạn dài bằng một `get_contact_sheet` (một ảnh ~600 token); chỉ lấy frame lẻ (`get_source_frames`, `render_frames`) ở mốc cần xác nhận. Tối đa 12 ảnh mỗi lần gọi; 512 px là đủ, nhỏ hơn khi chỉ cần bố cục.
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
- `audio_streams[].index` là chỉ số stream MLT (đếm cả stream hình), nên OBS track 1 thường là `index: 1`. `name` là mô tả Kdenlive (`Stereo 48kHz aac`), chưa phải tên track OBS.
- `track_map` ghi stream nào là gì: `[{index, obs_track, title, role, speaker, transcribe}]`, `role` ∈ `mix | mic | discord | game | desktop | other`. ContextCut đoán theo tên stream OBS (Mic, Discord…) rồi theo thứ tự trên; file chỉ có một track audio → `mix`, phiên âm track đó, `speaker: null`. `null` tới lần `transcribe`/`set_track_map` đầu. Sửa bằng `set_track_map(recording, tracks)`; chỉ track `transcribe: true` được phiên âm.
- `on_timeline`: bản ghi đã có clip trên timeline chưa. `ready: false`: Kdenlive chưa nạp xong clip.
- `list_sources` liệt kê **mọi** clip trong bin (bản ghi, nhạc, SFX, ảnh, title): `id` là `source` của `insert_clip`/`add_music`. File chưa có trong bin: `import_media(path)` với đường dẫn tuyệt đối người dùng đưa (chỉ file media, không qua symlink); kiểm `list_sources` trước để khỏi nhập trùng.

### Revision

- Mọi kết quả đọc có `revision`. Khác lần trước nghĩa là timeline có thể đã đổi (người dùng sửa, undo, redo, đổi sequence hay project). Chỉ so bằng; giá trị không có thứ tự.
- Chọn clip, dời playhead, zoom timeline không đổi `revision`.
- Lệnh sửa gửi `base_revision` = `revision` vừa đọc. Người dùng sửa chen ngang thì lệnh bị từ chối (`conflict`), timeline không đổi gì: đọc lại rồi đề xuất lại.
- `get_editor_state` có `undo`: `next_undo` là nhãn bước Ctrl+Z sẽ hoàn tác (đợt của agent mang nhãn `AI: …`).

### Sửa timeline

- Một lần `apply_operations` là **một đợt**: danh sách op chạy theo thứ tự, thành **một bước undo** nhãn `AI: …` (app tự thêm `AI: ` nếu thiếu). Ctrl+Z một lần hoàn tác cả đợt; `undo_batch(batch_id)` làm việc đó khi đợt còn là bước trên cùng.
- Op sau thấy timeline đã bị op trước đổi: sau `cut_range`, mọi thứ phía sau dời sớm hơn đúng độ dài đã cắt. Tính mốc frame cho op sau theo timeline mới, hoặc tách thành đợt khác rồi đọc lại.
- Một op lỗi thì cả đợt tự hoàn tác (`apply_failed` kèm `op_index`); tham số sai thì không đổi gì (`validation_failed`). `validate_operations` kiểm trước mà không đổi gì.
- Kết quả: `batch_id`, `revision` mới (dùng làm `base_revision` cho đợt sau, khỏi đọc lại), `created` (id clip mới theo chỉ số op), `warnings` (đọc và báo người dùng).
- Ghi `reason` một câu cho mỗi op cắt hay chuyển cảnh.

| Op | Tham số | Việc |
| --- | --- | --- |
| `cut_range` | `start_f`, `end_f` | Cắt bỏ khoảng trên mọi track không khoá, kéo phần sau lên (ripple); marker và phụ đề sau khoảng dời theo, phụ đề trong khoảng bị xoá, cắt ngang thì thu lại. Track khoá thì lệch đồng bộ (có cảnh báo) |
| `split` | `clip_id`, `at_f` | Cắt clip (cả clip cặp `linked`) làm đôi; `created` = nửa sau |
| `trim` | `clip_id`, `start_f?`, `end_f?` | Đặt mép mới trên timeline; điểm vào nguồn dời theo mép trái |
| `move` | `clip_id`, `at_f`, `track?` | Dời clip (cả clip cặp) tới `at_f`; chỗ đích phải trống |
| `insert_clip` | `source`, `in_f`, `out_f`, `track`, `at_f`, `audio_track?`, `audio_stream?`, `audio?` | Đặt khoảng nguồn `[in_f, out_f)` vào chỗ trống. Track video: hình lên `track`, tiếng xuống `audio_track` (mặc định track audio đối xứng), stream `audio_stream` (chỉ số như `list_recordings`, mặc định stream mặc định); track audio: chỉ tiếng |
| `add_music` | `source`, `at_f`, `in_f?`, `out_f?`, `track?`, `gain_db?` | Phần tiếng của nguồn lên track `Nhạc`/`Music` (hoặc `track`), `gain_db` -60…20 |
| `title_card` | `text`, `start_f`, `end_f`, `track?`, `style?` | Thẻ chữ toàn màn hình (`black` nền đen, `dim` nền mờ), vd. "Trong lúc đó:" |
| `caption` | `text`, `start_f`, `end_f`, `speaker?`, `track?`, `style?`, `color?`, `uppercase?`, `label?` | Câu đắt chữ viền đen (`bottom`, `top`) hoặc vàng to (`pop`); `color` `#RRGGBB`, `uppercase` in hoa, `label` thêm "<speaker>: ". Có `speaker` mà bỏ trống ba trường kia thì MCP server điền theo người nói (`speakers.json`) và bắt mép về đầu/cuối từ (`snap: false` để tắt) |
| `add_subtitles` | `items` (`[{start_f, end_f, text, speaker?}]`, tối đa 5000), `layer?` | Thêm dòng vào track phụ đề (tạo nếu chưa có); các dòng không chồng nhau và không chồng phụ đề có sẵn. Thường dùng tool `add_subtitles` thay vì tự soạn |
| `clear_subtitles` | `start_f`, `end_f`, `layer?` | Xoá phụ đề bắt đầu trong khoảng; đặt trước `add_subtitles` cùng đợt để thay một đoạn |
| `zoom` | `start_f`, `end_f`, `scale?` (1.05…4, mặc định 1.2), `focus_x?`, `focus_y?` (0…1, mặc định 0.5), `ramp_in_f?` (≈ 0,2 s), `ramp_out_f?` (0), `ease?` (`out`, `in`, `linear`, `smooth`), `track?` | Zoom vào khung trong `[start_f, end_f)`: cắt clip hình ở hai mốc, thêm hiệu ứng Transform có keyframe vào mảnh giữa (vào trong `ramp_in_f`, giữ, ra trong `ramp_out_f`; 0 = cắt thẳng). Điểm (`focus_x`, `focus_y`) của khung đứng yên: đặt vào chỗ chuyện xảy ra (0,0 = góc trái trên). Track mặc định: track video trên cùng có clip từ file (bỏ qua title). Khoảng phải nằm trong một clip; clip đã có Transform (zoom trước) thì lỗi |

- Track nhận id, tag (`V2`) hoặc tên track. Chữ mặc định lên track tên `Chữ`/`Text`/`Title`, không có thì track video trên cùng (có cảnh báo).
- Chèn và dời chỉ vào chỗ trống: cần chỗ thì `cut_range`/`move` trước, trong cùng đợt.
- `add_markers(markers, base_revision)` thêm marker (`f`, `comment`, `category`) để chỉ chỗ cho người dùng xem: một bước undo riêng.


### Lời thoại (transcript)

- `transcribe(recording, tracks?, language="vi", model?, prompt?)` phiên âm theo từng từ các track `transcribe: true` của `track_map` (Mic = Nhan, Discord = "bạn bè"). Chạy nền trong worker riêng: trả `job_id`; `get_job(job_id, wait_s=50)` (chờ tới khi xong, tối đa 55 s mỗi lần gọi) cho `status` (`queued` khi đang chờ GPU vì job khác chạy, `running`, `done`, `failed`, `cancelled`), `stage`, `progress`, `eta_s`. Client đóng giữa chừng thì job vẫn chạy; job hỏng thì gọi lại `transcribe`, phần đã xong được giữ.
- Kết quả lưu ở `<project>.contextcut/analysis/<hash file>/transcript.json` theo **giây trên bản ghi gốc**; gọi lại với cùng model trả `cached: true` ngay. `force: true` để phiên âm lại. `prompt` là tên riêng/thuật ngữ để nghe đúng chính tả ("Minecraft, creeper, Sang").
- Model: `parakeet-ctc-vi`, `phowhisper-large`, `large-v3` (mặc định chọn theo số đo, cái nào có trên máy). Máy không có GPU NVIDIA vẫn chạy được (CPU, chậm hơn).
- `get_transcript(recording?, start_f?, end_f?, track?, on, words?, limit, cursor)`: câu `{recording, track, speaker, start_f, end_f, tc, text}`; `tc` là `mm:ss.ff`. Mặc định `on="timeline"`: frame trên timeline đang mở, chỉ lời của đoạn bản ghi đang hiện (đoạn đã cắt không có; câu bị cắt dở có `partial: true`). `on="source"`: frame trên bản ghi gốc (để viết dàn ý theo bản ghi). `low_conf`: từ máy nghe chưa chắc. `words: true`: kèm từng từ `{w, start_f, end_f, p}`.
- Câu "ảo giác" quen của Whisper trên đoạn im lặng ("Hãy subscribe cho kênh…") đã bị lọc; vẫn có thể sai chữ: không trích nguyên văn một câu `low_conf` làm câu đắt khi chưa hỏi.

### Xem hình

| Tool | Ảnh | Dùng khi |
| --- | --- | --- |
| `get_contact_sheet(recording, start_f, end_f, on?, cols?, rows?)` | Một ảnh lưới (mặc định 4×3 ô 256 px, ~600 token), ô rải đều trong khoảng, nhãn `mm:ss.ff` | Lướt đoạn dài để biết chỗ nào đáng xem |
| `get_source_frames(recording, frames, on?, width?)` | Khung bản ghi gốc ở từng frame (≤ 12, mặc định 512 px ≈ 200 token) | Hiểu chuyện trong game, chọn chỗ zoom |
| `render_frames(frames, width?, originals?)` | Khung timeline đã dựng, dựng bằng MLT như khi xuất | Tự kiểm sau khi sửa |
| `get_viewer_frame(monitor?, at_f?, width?)` | Khung monitor đang hiện trong app (proxy, chất lượng preview) | Bàn về "chỗ này" với người dùng; `at_f` dời playhead |

- `on: "source"` (mặc định của hai tool bản ghi): frame trên bản ghi gốc theo fps project; `on: "timeline"`: frame timeline, đổi qua clip của bản ghi (frame không có bản ghi thì báo lỗi riêng frame đó).
- Bản ghi fps khác project (OBS 60 fps, project 25 fps): ảnh là đúng frame app hiện ở mốc đó.
- `render_frames` chạy melt trong job nền, thường vài giây; quá 45 s thì trả `job_id`: `get_job(job_id, wait_s=50)` trả ảnh khi xong. Ảnh đã dựng của cùng timeline được dùng lại.
- Mọi ảnh cũng lưu thành file JPEG (`<project>.contextcut/…`, project chưa lưu thì `%LOCALAPPDATA%\contextcut\frames\…`), đường dẫn nằm trong phần chữ.

Client hiện ảnh từ tool (thử 22/10/2026 với video in số frame: agent phải đọc đúng số trong ảnh):

| Client | Ảnh từ tool MCP | Ghi chú |
| --- | --- | --- |
| Claude Code (CLI, `claude -p`, sonnet) | **Có**: đọc đúng | |
| Codex CLI (`codex exec`, gpt-5.6-terra, gói free) | **Có**: đọc đúng | Tool chỉ đọc chạy được ở `exec`; tool sửa cần chạy tương tác |
| Claude Desktop | Chưa thử | Chưa đăng ký server trên máy Nhan |
| Antigravity | Chưa thử | Đã đăng ký server; cần thử qua giao diện |

Client không hiện ảnh thì mở file theo đường dẫn trong phần chữ.

### Xuất file

`export(output, start_f?, end_f?, preset?, encoder?, overwrite?, originals?)` xuất timeline (hoặc `[start_f, end_f)`) ra MP4 H.264 + AAC 320k bằng melt trên chính timeline đang mở (cùng engine với preview và `render_frames`), file gốc thay proxy.

| Tham số | Ý nghĩa |
| --- | --- |
| `output` | Đường dẫn tuyệt đối `.mp4`, thư mục đã có; không trùng file nguồn nào của project (kể cả proxy) hay file `.kdenlive`; không qua symlink |
| `preset` | `youtube-1080p60` (mặc định; project phải 1920×1080, 60 hoặc 59,94 fps) hoặc `project` (giữ cỡ, fps của project). ContextCut không tự đổi cỡ khi xuất |
| `encoder` | `auto` (mặc định: NVENC trên GPU NVIDIA, hỏng thì x264), `nvenc`, `x264` (CPU, chậm hơn) |
| `overwrite` | Ghi đè file đã có; chỉ khi người dùng đồng ý |
| `originals` | `false` dùng proxy (nhanh, mờ): chỉ để thử |

- **Người dùng xác nhận trong app**: tool hiện hộp "AI muốn xuất video" (file, đoạn, preset, mã hoá) trong ContextCut và tạo job; job chờ tới khi người dùng bấm "Xuất" (nút mặc định là "Không xuất"; hộp tự đóng sau 15 phút). Tool chờ tối đa 50 s rồi trả `job_id` với `stage` cho biết còn chờ người dùng hay đang xuất. Agent không bấm thay.
- Job: lấy timeline lúc người dùng bấm Xuất → mã hoá ra `<tên>.part.mp4` cạnh file đích → kiểm bằng ffprobe → đổi tên thành `output`. Hỏng, huỷ hay từ chối thì không có file nào ở `output`. NVENC giữ khoá GPU (job phiên âm chờ), x264 thì không.
- `get_job` khi `done`: `result.ok`, `checks` (`streams`: 1 hình H.264 + 1 tiếng AAC; `frames`: đúng số frame của khoảng; `duration`, `av_offset`: lệch đầu hình/tiếng < 1 frame; `audio_length`; `format`: cỡ, fps), `encoder`, `fallback_reason`, `size_mb`, `encode_s`, `realtime_x`.

### Mở project

`open_project(path, wait_s?)` mở file `.kdenlive` khác như File › Open. Project đang mở có thay đổi chưa lưu thì Kdenlive hỏi người dùng (Save / Don't Save / Cancel); hộp khôi phục file, file thiếu… cũng do người dùng trả lời. Trong lúc đó tool khác trả "ContextCut đang bận".

| `state` | Nghĩa |
| --- | --- |
| `opened` | Project mới đang mở; kèm `project`, `profile`, `sequence`, `counts`, `revision` |
| `pending` | App còn hỏi người dùng (`dialog`: tiêu đề + chữ) hoặc đang nạp: gọi lại `open_project` cùng path để chờ tiếp |
| `cancelled` | Người dùng bấm Cancel (hoặc lưu không được): project cũ còn nguyên |
| `failed` | Kdenlive không mở được file (người dùng đã thấy lý do) |

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
| "ContextCut đang bận (…)" | App đang hỏi người dùng (hộp thoại) hoặc đang mở project; tool sửa không chạy khi có hộp thoại modal | Nhờ người dùng trả lời hộp thoại trong app, rồi gọi lại; không gọi dồn |
| "Project đang là …, preset … cần …" | Project không hợp preset xuất | Dùng preset `project` hoặc nhờ người dùng đổi Project Settings |
| "output trùng file nguồn…" / "… đã có" | Đường dẫn xuất không an toàn | Hỏi người dùng tên khác (hoặc đồng ý ghi đè: `overwrite`) |
| `stale_cursor` | Timeline đổi giữa hai trang | Đọc lại từ trang đầu |
| "Timeline đã đổi từ lúc đọc" (`conflict`) | Người dùng vừa sửa, undo, hoặc đợt khác đã áp dụng; không có gì bị đổi | Đọc lại `get_timeline`, gửi lại với `base_revision` mới |
| "Đợt sửa không hợp lệ" (`validation_failed`) | Tham số sai; không có gì bị đổi | Sửa theo từng dòng `op <i> (<trường>)` |
| "op <i> lỗi khi áp dụng" (`apply_failed`) | Op đó không làm được trên timeline lúc tới lượt; cả đợt đã hoàn tác | Đọc lại, sửa op đó rồi gửi lại |
| "có thể đã được áp dụng" | Kết nối rớt sau khi gửi lệnh sửa | Xem `get_editor_state` (`undo.next_undo`) trước khi gửi lại, tránh áp dụng hai lần |
| Tham số sai | Sai kiểu hoặc ngoài khoảng | Sửa tham số |
| Không có `…` | Track hay clip không tồn tại | Xem lại `get_editor_state` |
| "Lưu project trước (Ctrl+S)…" | Project chưa lưu lần nào nên chưa có thư mục `.contextcut` để lưu transcript | Nhờ người dùng lưu project rồi gọi lại |
| "Chưa có transcript…" | Bản ghi chưa phiên âm, hoặc job chưa xong | `transcribe`, đợi `get_job` xong |
| "Chưa có model … (… GB)" / "Chưa cài thư viện phân tích…" | Thiếu model hoặc thư viện trên máy | Báo dung lượng, hỏi người dùng; đồng ý thì `allow_download: true` (model) hoặc người dùng chạy lệnh cài thư viện |

### Tool

| Tool | Việc | Có từ |
| --- | --- | --- |
| `get_editor_state` | Project, fps, kích thước, sequence, playhead, vùng chọn, track, số lượng, revision | **bây giờ** |
| `get_timeline` | Clip, composition, marker trong một khoảng; phân trang | **bây giờ** |
| `list_recordings` | Bản ghi của project: id, file, hash, độ dài, stream audio, đã lên timeline chưa | **bây giờ** |
| `get_guide` | Đọc hướng dẫn này theo topic | **bây giờ** |
| `list_sources` | Mọi clip trong bin (nhạc, ảnh, title, bản ghi): id làm `source` | **bây giờ** |
| `list_operations`, `validate_operations` | Danh mục op + schema; kiểm một đợt không đổi gì | **bây giờ** |
| `apply_operations` | Sửa timeline, mỗi đợt một bước undo nhãn `AI: …`; op `cut_range`, `split`, `trim`, `move`, `insert_clip`, `add_music`, `title_card`, `caption`, `add_subtitles`, `clear_subtitles`, `zoom` | **bây giờ** |
| `add_markers`, `undo_batch` | Thêm marker; hoàn tác đợt vừa áp dụng | **bây giờ** |
| `import_media` | Nhập file media (nhạc, SFX, video, ảnh) vào bin | **bây giờ** |
| `set_track_map` | Sửa sơ đồ track audio của bản ghi (stream nào là Mic, Discord, game) | **bây giờ** |
| `get_job`, `cancel_job` | Theo dõi / huỷ job nền (phiên âm, dựng khung hình, xuất) | **bây giờ** |
| `transcribe` | Phiên âm theo từ track Mic/Discord của bản ghi (job nền) | **bây giờ** |
| `get_transcript` | Lời thoại theo câu/từ, người nói, frame timeline hoặc nguồn; phân trang | **bây giờ** |
| `add_subtitles` | Phụ đề đầy đủ từ transcript vào track phụ đề Kdenlive (một bước undo; `preview` xem trước) | **bây giờ** |
| `get_contact_sheet`, `get_source_frames` | Xem bản ghi gốc: lưới ảnh một đoạn, khung ở từng frame | **bây giờ** |
| `render_frames` | Xem timeline đã dựng (như file xuất) để tự kiểm | **bây giờ** |
| `get_viewer_frame` | Khung người dùng đang xem trong monitor | **bây giờ** |
| `export` | Xuất MP4 (YouTube 1080p60 hoặc theo project) sau khi người dùng bấm Xuất trong app; kiểm ffprobe | **bây giờ** |
| `open_project` | Mở project `.kdenlive` khác (app hỏi lưu project đang sửa) | **bây giờ** |
| `get_context` | Lời thoại + sự kiện gộp theo thời gian | P3 |
| `find_moments`, `detect_beats`, `beat_montage`, `get_outline`, `save_outline`, `list_assets` | Khoảnh khắc, beat, dàn ý, thư viện nhạc/SFX/meme | P3 |
| `register_pov`, `sync_pov`, `pov_placeholder`, `pov_switch` | Nhiều POV | P4 |

Tool chưa có thì không gọi được. Người dùng cần thì nói rõ là chưa có, rồi đề xuất cách tạm (người dùng làm tay theo mốc frame).

## Topic khác

Đọc khi cần bằng `get_guide("<topic>")` hoặc resource `contextcut://guide/<topic>`:

- styles/gaming: Phong cách gaming (funny moments). Funny moments nhiều người chơi kiểu nhóm CKG (HK15, Sangtraan): bố cục, phụ đề câu đắt, meme, thay facecam, nhịp, Minecraft.
- patterns/irony-cut: Cú cắt mỉa (irony cut). Câu thoại tự tin, cắt gọn sang cảnh phản bác câu đó, nhạc vào đúng điểm cắt.
- patterns/meanwhile: Hai mạch song song ("Trong lúc đó:"). Kể trọn một mạch rồi chuyển sang mạch song song tương phản của người khác, mở bằng thẻ chữ "Trong lúc đó:".
- patterns/beat-montage: Montage theo beat. Chuỗi khoảnh khắc cùng loại, mỗi cú cắt rơi đúng phách mạnh của bản nhạc (sai số ±1 frame).
- patterns/reaction-zoom: Zoom phản ứng thay facecam. Không có facecam, nên nhấn phản ứng bằng zoom vào gameplay (op zoom), phụ đề to, SFX hoặc meme; tự kiểm bằng render_frames.
- patterns/subtitles: Phụ đề đầy đủ và câu đắt. Hai kiểu phụ đề (đầy đủ trên track phụ đề, câu đắt trên track Chữ), timing theo từ, style theo người nói, khi nào dùng.
