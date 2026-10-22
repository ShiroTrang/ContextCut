---
title: Quy trình dựng
summary: Phân tích → dàn ý → duyệt → dựng → tự kiểm → xuất; bước nào làm được ở bản này, khi nào phải hỏi người dùng.
order: 1
---
# Quy trình dựng

Người dùng quay buổi chơi bằng OBS, kéo vào ContextCut, rồi nhờ agent đề xuất bố cục và dựng. Agent là người dựng phụ: đề xuất, giải thích, dựng phần đã được duyệt. Người dùng quyết định.

## Các bước

| # | Bước | Việc | Tool | Có từ |
| --- | --- | --- | --- | --- |
| 1 | Nắm project | Project, fps, track, bản ghi, playhead, vùng chọn, marker người dùng đặt | `get_editor_state`, `list_recordings`, `get_timeline` | **bây giờ** |
| 2 | Phân tích | Lời thoại theo từ (track Mic, Discord); phản ứng, khoảng lặng, sự kiện game (P3) | `transcribe`, `get_job`, `get_transcript`; `find_moments` (P3) | **bây giờ** (lời thoại) |
| 3 | Dàn ý | Danh sách đoạn: vai trò (hook, bối cảnh, thân, cao trào, "trong lúc đó", kết), khoảng thời gian trên bản ghi, POV, lý do một câu, kiểu dựng (thường, montage theo beat, cú cắt mỉa…), trạng thái | `get_outline`, `save_outline` | P3; trước đó viết dàn ý trong chat |
| 4 | Duyệt | Người dùng đọc, sửa, duyệt dàn ý. Đoạn chưa duyệt thì chưa dựng | — | |
| 5 | Dựng | Mỗi đoạn đã duyệt là một đợt sửa có nhãn `AI: …` và lý do | `list_operations`, `validate_operations`, `apply_operations` | **bây giờ** |
| 6 | Tự kiểm | Xem khung hình chỗ vừa sửa: cắt đúng chỗ chưa, zoom đúng chỗ chưa, chữ có che giao diện game không | `render_frames` | **bây giờ** |
| 7 | Xuất | Chỉ khi người dùng bảo; hỏi tên và chỗ lưu file; app hỏi người dùng xác nhận | `export`, `get_job` | **bây giờ** |

## Bản hiện tại làm được gì

- Đọc project đang mở: track, clip, composition, marker (guide), các bản ghi, mọi clip trong bin.
- Trả lời câu hỏi về project ("timeline có gì", "bản ghi nào chưa dùng", "phút 12 là clip nào") bằng số liệu thật từ tool.
- **Nghe lời thoại**: phiên âm theo từng từ track Mic (Nhan) và Discord (bạn bè), đọc theo khoảng trên timeline hoặc bản ghi gốc.
- **Xem hình**: lướt bản ghi bằng contact sheet, xem frame gốc ở mốc cụ thể, xem timeline đã dựng (như file xuất) để tự kiểm, xem khung người dùng đang nhìn. Đề xuất dàn ý dựa trên transcript, hình đã xem, marker và lời người dùng kể; chỗ chưa xem thì nói rõ là đoán.
- **Sửa timeline** phần đã duyệt: cắt bỏ đoạn, cắt/tỉa/dời clip, chèn đoạn từ bản ghi, thêm nhạc, thẻ chữ "Trong lúc đó:", câu đắt theo người nói, phụ đề đầy đủ, marker, **zoom** vào gameplay. Chưa có: hiệu ứng khác (P6).
- **Xuất** MP4 (YouTube 1080p60 hoặc theo project) sau khi người dùng bấm "Xuất" trong app; **mở** project `.kdenlive` khác.

## Nghe trước khi dựng

1. `list_recordings`: bản ghi nào, có `track_map` chưa (stream nào là Mic, Discord). Sơ đồ đoán sai (người dùng bảo) thì `set_track_map`.
2. `transcribe(recording)`: trả `job_id` (hoặc `cached: true` nếu đã có). Buổi quay dài mất vài phút đến vài chục phút: báo người dùng, rồi chờ bằng `get_job(job_id, wait_s=50)` (tool tự chờ, trả ngay khi xong; chưa xong thì gọi lại). Đừng hẹn giờ quay lại hay kết thúc lượt khi job chưa xong: ở chế độ không tương tác sẽ không có lượt sau.
3. Tool báo thiếu model hay thư viện kèm **dung lượng**: hỏi người dùng có đồng ý tải không, đồng ý mới gọi lại với `allow_download: true`. Không tự tải.
4. Xong thì `get_transcript` theo khoảng (`start_f`, `end_f`), `track` khi chỉ cần một người; `words: true` khi cần mốc từng từ (câu đắt). Đọc từng khoảng, đừng kéo cả buổi 2 giờ một lần.
5. Dàn ý và mốc cắt dựa vào lời thật: không cắt giữa câu, giữa tràng cười (xem `editing-rules`).

## Phụ đề

- Phụ đề đầy đủ: `add_subtitles(start_f?, end_f?)` sau khi đã dựng xong đoạn; `preview: true` để đọc thử trước. Một bước undo.
- Câu đắt: op `caption` có `speaker`, mốc từ `get_transcript(words=true)`; style theo người nói tự điền. Xem `get_guide("patterns/subtitles")`.

## Xem hình

Ảnh tốn hạn mức gói AI nhất: đọc chữ (timeline, transcript) trước, xem hình ở chỗ đáng chú ý.

1. Lướt một đoạn dài của bản ghi: `get_contact_sheet(recording, start_f, end_f)`: một ảnh 4×3 ô có nhãn giờ, phần chữ cho biết ô nào là frame nào.
2. Xem kỹ một mốc: `get_source_frames(recording, frames)` (frame gốc, chưa có hiệu ứng; `on: "timeline"` để đưa frame timeline).
3. Sau khi sửa: `render_frames(frames)` ở chỗ vừa sửa (đầu, giữa, cuối đoạn): đúng như file xuất (cắt, zoom, chữ, phụ đề). Sai thì sửa tiếp hoặc `undo_batch`, rồi kiểm lại.
4. Người dùng nói "chỗ này": `get_viewer_frame()` là khung họ đang xem; `at_f` dời playhead tới mốc mình muốn chỉ cho họ thấy.
5. Client không hiện ảnh: mỗi ảnh có đường dẫn file trong phần chữ, mở file đó (vd. tool đọc file của client).

## Xuất

1. Chỉ xuất khi người dùng bảo. Hỏi tên file và chỗ lưu nếu họ chưa nói (đường dẫn tuyệt đối `.mp4`, không trùng file nguồn), cả timeline hay một đoạn.
2. Preset `youtube-1080p60` khi project là 1920×1080 60 fps (như bản ghi OBS khuyến nghị); project khác cỡ/fps thì `project`, hoặc nhờ người dùng đổi Project Settings. Tool báo rõ khi không khớp.
3. `export(output, start_f?, end_f?)`: ContextCut hiện hộp "AI muốn xuất video" cho người dùng. **Chỉ người dùng bấm "Xuất"**: agent không bấm thay, không điều khiển giao diện, không xuất bằng đường khác (melt, ffmpeg) để lách. Báo người dùng nhìn sang app.
4. `get_job(job_id, wait_s=50)` tới khi `done`. Đoạn dài xuất mất vài phút (NVENC nhanh hơn thời gian thực nhiều lần; x264 chậm hơn).
5. Báo: file, thời lượng, dung lượng, bộ mã hoá (`fallback_reason` khi NVENC hỏng phải dùng x264), `ok` và các `checks` hỏng nếu có. `cancelled` là người dùng không đồng ý (hoặc huỷ): không hỏi lại trừ khi họ bảo.
6. File đã có: chỉ `overwrite: true` khi người dùng đồng ý ghi đè (hộp xác nhận ghi rõ "GHI ĐÈ").

## Mở project khác

`open_project(path)` mở file `.kdenlive` người dùng chỉ. Project đang mở có thay đổi chưa lưu thì app hỏi người dùng Save / Don't Save / Cancel: báo họ trả lời trong app, đừng chọn thay. Kết quả `pending` (kèm `dialog` app đang hỏi): gọi lại `open_project` cùng path để chờ tiếp; `cancelled`: project cũ còn nguyên. Sau khi mở, mọi id clip, track, `batch_id` cũ hết giá trị: đọc lại `get_editor_state`.

## Một lần sửa

1. `get_editor_state` (lấy `revision`, track) và `get_timeline` đúng khoảng sắp sửa; `list_sources` khi cần id nhạc hay bản ghi. Lần đầu: `list_operations`.
2. Soạn đợt op theo đoạn đã duyệt; mỗi op cắt hay chuyển cảnh có `reason`. Mốc frame của op sau tính theo timeline sau op trước (`cut_range` làm dời mọi thứ phía sau).
3. `validate_operations` nếu đợt phức tạp; sửa lỗi theo `op_index`/`field`.
4. `apply_operations(ops, base_revision, label)`; nhãn ngắn, nói được việc: "AI: cắt đoạn chết 03:10–04:02".
5. Báo người dùng: nhãn đợt, đã đổi gì (mốc timecode), cảnh báo nếu có, và "Ctrl+Z để hoàn tác". `conflict` thì đọc lại và hỏi lại nếu đoạn đó người dùng vừa sửa.
6. Đợt sau dùng `revision` trả về làm `base_revision`.

## Đọc timeline cho gọn

- `get_editor_state` trước (rẻ, có `counts`). Rồi `get_timeline` theo khoảng (`start_f`, `end_f`) và track cần thiết, `limit` vừa đủ; trang sau dùng `next_cursor`.
- Đổi frame và thời gian: giây = frame × den / num. Ví dụ 60 fps: phút 12:03 = 723 giây = frame 43380.
- `revision` khác lần đọc trước nghĩa là người dùng vừa sửa: đọc lại trước khi đưa mốc cụ thể.

## Khi nào phải hỏi người dùng

- Trước khi dựng thứ chưa có trong dàn ý đã duyệt.
- Cắt bỏ đoạn dài (từ khoảng 2 phút) hoặc đoạn có lời thoại.
- Dùng nhạc, SFX, meme ngoài thư viện, hoặc không rõ giấy phép.
- Thêm POV bạn bè (mặc định chỉ dùng POV người quay).
- Xuất file.
- Tải model hoặc thư viện (tool báo dung lượng).
- Không chắc chuyện gì xảy ra ở một đoạn (chưa nghe, chưa xem được), hoặc transcript có từ `low_conf` ở chỗ quan trọng.

## Chế độ Duyệt và Tự động

- **Duyệt** (mặc định): mỗi đợt sửa chờ người dùng giữ hoặc hoàn tác. Trước P5 chưa có dock Hoạt động AI: người dùng xem Undo History của Kdenlive và Ctrl+Z; agent tự hoàn tác đợt vừa làm bằng `undo_batch` khi người dùng bảo.
- **Tự động**: chỉ khi người dùng bảo. Vẫn dừng hỏi khi cắt bỏ vượt ngưỡng hoặc trước khi xuất.
