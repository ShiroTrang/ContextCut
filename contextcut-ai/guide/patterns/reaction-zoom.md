---
title: Zoom phản ứng thay facecam
summary: Không có facecam, nên nhấn phản ứng bằng zoom vào gameplay, phụ đề to, SFX hoặc meme.
order: 23
---
# Zoom phản ứng thay facecam

Trạng thái: khung (guide v0). Cần `zoom`, `render_frames` (P2b) và `find_moments` (P3); trước đó chỉ đề xuất bằng chữ (phản ứng tìm được bằng lời thoại trong transcript).

## Khi dùng

Người chơi la, cười to, hoặc nói câu đắt khi có chuyện bất ngờ trong game.

## Các bước

1. Tìm phản ứng thật: đỉnh âm lượng, tiếng cười trên track Mic.
2. Xem khung hình quanh mốc để biết zoom vào đâu: chỗ chuyện xảy ra, không mặc định giữa màn hình.
3. Zoom nhanh vào (khoảng 1,0 → 1,2, ease out) đúng lúc phản ứng bắt đầu, giữ hết phản ứng, rồi về lại hoặc cắt.
4. Tuỳ: phụ đề câu đắt chữ to, SFX nhẹ. Không dồn zoom, SFX và meme vào một chỗ, trừ ở cao trào.

## Lưu ý

- Theo hạn mức zoom trong `editing-rules`.
- Zoom không được che mất chuyện chính (kẻ địch, thanh máu khi đang nói về máu).
- Tự kiểm bằng `render_frames` sau khi dựng.

## Tool cần

`zoom`, `render_frames` (P2b), `find_moments` (P3), `get_transcript` (P2a), `caption` (P1c).
