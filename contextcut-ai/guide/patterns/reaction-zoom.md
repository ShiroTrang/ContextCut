---
title: Zoom phản ứng thay facecam
summary: Không có facecam, nên nhấn phản ứng bằng zoom vào gameplay (op zoom), phụ đề to, SFX hoặc meme; tự kiểm bằng render_frames.
order: 23
---
# Zoom phản ứng thay facecam

Không có facecam: phản ứng của người chơi thể hiện bằng zoom nhanh vào chỗ chuyện xảy ra trong game.

## Khi dùng

Người chơi la, cười to, hoặc nói câu đắt khi có chuyện bất ngờ trong game. Tìm phản ứng thật bằng lời thoại (`get_transcript`, words=true); P3 thêm `find_moments` (đỉnh âm lượng, tiếng cười).

## Các bước

1. Mốc phản ứng: đầu từ đầu tiên của câu la/cười (`get_transcript` với `words: true`, khoảng quanh chỗ đó).
2. Xem hình quanh mốc: `get_source_frames(recording, [mốc − 1 s, mốc, mốc + 1 s], on: "timeline")`. Tìm chỗ chuyện xảy ra (creeper, kẻ địch, thanh máu…), ước `focus_x`/`focus_y` theo tỉ lệ khung (0,0 trái trên, 1,1 phải dưới). Không mặc định giữa màn hình.
3. Dựng: op `zoom{start_f: mốc, end_f: hết phản ứng, scale: 1.2–1.3, focus_x, focus_y, ramp_in_f: ~0,2 s, ease: "out"}`. Thường cắt thẳng về khung thường ở `end_f` (`ramp_out_f: 0`); muốn êm thì `ramp_out_f` ~0,3 s.
4. Tự kiểm: `render_frames([start_f + ramp_in_f, giữa đoạn, end_f])`: đúng chỗ chưa, có che mất chuyện chính không. Sai thì `undo_batch` rồi dựng lại.
5. Tuỳ: câu đắt chữ to (`caption` có `speaker`), SFX nhẹ. Không dồn zoom, SFX và meme vào một chỗ, trừ ở cao trào.

## Lưu ý

- Theo hạn mức zoom trong `editing-rules` (khoảng 1 lần mỗi 30 giây).
- Zoom không được che mất chuyện chính (kẻ địch, thanh máu khi đang nói về máu): scale nhỏ (1.15–1.25) an toàn hơn.
- Khoảng zoom phải nằm trong một clip; vắt qua chỗ cắt thì chia thành hai op.
- Zoom cắt clip thành mảnh (thấy trong `get_timeline`, mảnh giữa có hiệu ứng "Transform"); người dùng sửa tay trong Effect Stack được.

## Tool cần

`get_transcript`, `get_source_frames`, op `zoom`, `render_frames` (có từ P2b); `find_moments` (P3).
