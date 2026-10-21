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
| 2 | Phân tích | Lời thoại theo từ (track Mic, Discord), phản ứng, khoảng lặng, sự kiện game | `transcribe`, `get_transcript`, `find_moments` | P2–P3 |
| 3 | Dàn ý | Danh sách đoạn: vai trò (hook, bối cảnh, thân, cao trào, "trong lúc đó", kết), khoảng thời gian trên bản ghi, POV, lý do một câu, kiểu dựng (thường, montage theo beat, cú cắt mỉa…), trạng thái | `get_outline`, `save_outline` | P3; trước đó viết dàn ý trong chat |
| 4 | Duyệt | Người dùng đọc, sửa, duyệt dàn ý. Đoạn chưa duyệt thì chưa dựng | — | |
| 5 | Dựng | Mỗi đoạn đã duyệt là một đợt sửa có nhãn `AI: …` và lý do | `list_operations`, `validate_operations`, `apply_operations` | **bây giờ** |
| 6 | Tự kiểm | Xem khung hình chỗ vừa sửa: cắt đúng chỗ chưa, chữ có che giao diện game không | `render_frames` | P2 |
| 7 | Xuất | Chỉ khi người dùng bảo | `export` | P2 |

## Bản hiện tại làm được gì

- Đọc project đang mở: track, clip, composition, marker (guide), các bản ghi, mọi clip trong bin.
- Trả lời câu hỏi về project ("timeline có gì", "bản ghi nào chưa dùng", "phút 12 là clip nào") bằng số liệu thật từ tool.
- Đề xuất dàn ý **bằng chữ**. Chưa có transcript và hình, nên dàn ý chỉ dựa vào tên file, độ dài, marker, và lời người dùng kể. Nói rõ giới hạn đó.
- **Sửa timeline** phần đã duyệt: cắt bỏ đoạn, cắt/tỉa/dời clip, chèn đoạn từ bản ghi, thêm nhạc, thẻ chữ "Trong lúc đó:", câu đắt, marker. Chưa có: zoom, hiệu ứng, phụ đề tự động, xem hình (P2 trở đi).

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
- Không chắc chuyện gì xảy ra ở một đoạn (chưa nghe, chưa xem được).

## Chế độ Duyệt và Tự động

- **Duyệt** (mặc định): mỗi đợt sửa chờ người dùng giữ hoặc hoàn tác. Trước P5 chưa có dock Hoạt động AI: người dùng xem Undo History của Kdenlive và Ctrl+Z; agent tự hoàn tác đợt vừa làm bằng `undo_batch` khi người dùng bảo.
- **Tự động**: chỉ khi người dùng bảo. Vẫn dừng hỏi khi cắt bỏ vượt ngưỡng hoặc trước khi xuất.
