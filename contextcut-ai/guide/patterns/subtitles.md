---
title: Phụ đề đầy đủ và câu đắt
summary: Hai kiểu phụ đề (đầy đủ trên track phụ đề, câu đắt trên track Chữ), timing theo từ, style theo người nói, khi nào dùng.
order: 24
---
# Phụ đề đầy đủ và câu đắt

Phụ đề lệch timing là một phản mục tiêu: câu phải hiện đúng lúc bắt đầu nói và tắt đúng lúc nói xong. Cả hai kiểu dưới đây lấy mốc từ transcript (từng từ), không đoán.

## Phụ đề đầy đủ

- Tool `add_subtitles(start_f?, end_f?)`: lấy lời trong khoảng theo timeline đang mở, ngắt dòng ≤ 42 ký tự ở chỗ nghỉ, đưa vào track phụ đề của Kdenlive. Một bước undo.
- `preview: true` trước khi áp dụng đoạn dài, để đọc thử vài dòng và báo người dùng số dòng.
- Mặc định thay phụ đề cũ trong khoảng (`replace`). Muốn giữ phụ đề người dùng tự gõ thì `replace: false` và chọn khoảng không chồng.
- Dựng xong (cắt, dời) rồi mới thêm phụ đề đầy đủ. Cắt sau khi đã có phụ đề cũng được: `cut_range` dời phụ đề theo.
- Hai người nói chồng nhau lâu thì thành một dòng hai hàng "– …".

## Câu đắt

- Câu ngắn, có lực (câu tự tin trước cú cắt mỉa, câu la khi chết, câu chốt hài). Một đoạn vài phút chỉ vài câu: dày quá thì "lố".
- Op `caption{text, start_f, end_f, speaker}` trên track Chữ. Lấy `start_f`/`end_f` từ `get_transcript(words=true)`: đầu từ đầu và cuối từ cuối của câu. MCP server tự bắt mép về đúng đầu/cuối từ gần nhất (±0,4 s) và tự điền style theo người nói: Nhan chữ trắng, bạn bè chữ vàng, in hoa, không ghi tên. Bảng màu sửa được ở `<project>.contextcut/speakers.json`.
- `text` được rút gọn hoặc sửa lỗi chính tả máy nghe sai, nhưng không đổi ý câu, không bịa lời.
- `style: "pop"` (vàng to) để nhấn khoảnh khắc lớn; `top` khi đáy khung đang có phụ đề đầy đủ.

## Lưu ý

- Từ trong `low_conf` là máy nghe chưa chắc: đọc kỹ ngữ cảnh, không chắc thì hỏi người dùng thay vì đoán.
- Track Mic là Nhan, Discord là "bạn bè" (cả nhóm chung một track): đừng gán tên bạn cụ thể khi chưa có thông tin.
- Chỉ phụ đề phần đã có trên timeline: `get_transcript` mặc định chỉ trả lời của đoạn bản ghi đang hiện.

## Tool cần

`transcribe`, `get_job`, `get_transcript`, `add_subtitles` (P2a); op `caption` (P1c, style theo người nói từ P2a).
