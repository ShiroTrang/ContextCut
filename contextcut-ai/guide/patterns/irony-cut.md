---
title: Cú cắt mỉa (irony cut)
summary: Câu thoại tự tin, cắt gọn sang cảnh phản bác câu đó, nhạc vào đúng điểm cắt.
order: 20
---
# Cú cắt mỉa

Trạng thái: khung (guide v0). Đã có transcript (P2a) để chọn câu tự tin và cắt đúng cuối câu; `find_moments` và `beat_montage` (P3) chưa có, nên đoạn montage chết dựng tay bằng `insert_clip` theo mốc người dùng chỉ.

## Khi dùng

Ai đó nói một câu tự tin ("modpack này chưa gì thấy ok rồi đó") và ngay sau đó thực tế phản bác: chết liên tục, thất bại, bị troll.

## Các bước (ví dụ của Nhan)

1. Thẻ chữ dẫn chuyện, ví dụ nhạc Can Can và chữ "Chúng tôi đã thử chơi modded SMP này:".
2. Câu thoại tự tin, lấy **nguyên câu**, không cắt giữa từ, để người nói nói hết.
3. Cắt gọn sang montage phản bác, ví dụ chuỗi cảnh chết khớp theo nhạc (`patterns/beat-montage`).
4. Nhạc vào đúng điểm cắt.

## Lưu ý

- Câu tự tin phải là lời thật (đã nghe trong transcript), không bịa, không ghép.
- Cảnh phản bác phải thật sự phản bác câu đó. Ghi lý do vào đợt sửa.
- Mỗi video dùng vài lần là đủ; dùng nhiều thì mất tác dụng.

## Tool cần

`get_transcript` (P2a), `find_moments`, `detect_beats`, `beat_montage` (P3), `title_card`, `insert_clip`, `add_music` (P1c).
