---
title: Quy tắc biên tập
summary: Cắt và chuyển POV cho tự nhiên (Nhan chốt bằng ví dụ), không bịa, chống "lố", tiết kiệm hạn mức gói AI, việc phải xác nhận.
order: 2
---
# Quy tắc biên tập

Lỗi nặng nhất là **video thiếu tự nhiên**: chuyển cảnh hay chuyển POV liên tục không có lý do, cắt giữa câu, giữa tràng cười, giữa pha hành động. Các quy tắc dưới đây do Nhan chốt bằng ví dụ.

## Cắt và chuyển POV

1. **Chỉ chuyển khi có lý do.** Mỗi lần cắt sang cảnh khác hay chuyển POV, ghi một câu lý do (trường `reason` của op, hoặc trong dàn ý).
2. **Để khoảnh khắc diễn ra trọn vẹn rồi mới chuyển.** Hành động xong, phản ứng xong (cười, la, câu thoại nói hết) mới cắt.
3. **Nhân trước, quả sau.** Ví dụ Among Us, người quay là imposter: POV người quay lúc "sực" bạn B, chờ "sực" xong và tràng cười xong, rồi mới sang POV bạn B bị "sực". Đảo vai thì đảo thứ tự.
4. **Song song thì kể trọn từng mạch.** Ví dụ Minecraft: kể trọn đoạn người quay và bạn A sống chết giữ nhà ban đêm (có thể kèm meme hợp cảnh), sau đó mới sang POV bạn B với thẻ chữ **"Trong lúc đó:"**: B đang thong thả đào tài nguyên dưới hang. Giá trị nằm ở sự tương phản. Xem `patterns/meanwhile`.
5. **Không đặt điểm cắt hay điểm chuyển POV:**
   - giữa một từ (theo transcript);
   - giữa một phản ứng (tràng cười, tiếng la hét);
   - tạo ra shot ngắn hơn **1,5 giây** (ngưỡng khởi đầu, sẽ chỉnh sau khi Nhan chấm).

   Được vượt, nhưng phải ghi lý do (ví dụ montage theo beat cố ý dùng shot ngắn). Validator trong app chưa chặn (P3–P4); đến lúc đó tự kiểm bằng `get_transcript(words=true)` quanh mỗi điểm cắt.

## Nội dung

- Giữ nguyên ý người nói. Câu thoại lấy nguyên câu; không ghép từ nhiều chỗ thành câu người đó không nói.
- **Không bịa** lời thoại, sự kiện, tên người hay chuyện xảy ra trong game mà chưa nghe (transcript) hoặc chưa xem (hình). Chỗ nào suy đoán thì nói "đoán là…".
- Phụ đề và câu đắt phải đúng từng chữ đã nghe; chữ nào không chắc thì đánh dấu để người dùng kiểm.
- Chọn phong cách theo yêu cầu người dùng trước, nội dung video sau; nói phong cách đã chọn và lý do trong một câu. Người dùng luôn ghi đè được ("gameplay nhưng đừng dùng meme").

## Chống "lố"

"Lố" là meme, hiệu ứng, SFX dày đặc mà không phục vụ nhịp hay câu chuyện. Hiệu ứng chỉ dùng khi làm rõ, tạo nhịp hoặc nhấn mạnh; không chắc thì bỏ.

Hạn mức khởi đầu (đề xuất, chưa chấm; Nhan chỉnh sau):

| Loại | Tối đa (trung bình) | Thêm |
| --- | --- | --- |
| Meme, ảnh/clip chèn | 1 lần mỗi 60 giây video | không hai meme liền nhau |
| SFX nhấn | 1 lần mỗi 20 giây | không đè câu thoại quan trọng |
| Zoom phản ứng | 1 lần mỗi 30 giây | chỉ ở phản ứng thật |
| Chữ to nhấn mạnh | chỉ câu đắt | không biến mọi câu thành câu đắt |

Khi đề xuất một đoạn, đếm số hiệu ứng mỗi phút; vượt hạn mức thì nói ra và giải thích vì sao (thường chỉ hợp ở cao trào).

## Tiết kiệm hạn mức gói AI

Người dùng xài gói Pro/Plus của Claude, ChatGPT…; xem ảnh tốn hạn mức nhanh nhất.

- Đọc chữ trước, xem hình sau: timeline, transcript, danh sách khoảnh khắc rồi mới xem ảnh ở chỗ đáng chú ý.
- Lướt đoạn dài bằng một `get_contact_sheet` (một ảnh ~600 token); chỉ lấy frame lẻ (`get_source_frames`, `render_frames`) ở mốc cần xác nhận. Tối đa 12 ảnh mỗi lần gọi; 512 px là đủ, nhỏ hơn khi chỉ cần bố cục.
- Đọc timeline theo khoảng và track cần thiết; không kéo 1000 item khi chỉ cần một phút.
- Không gọi lại tool khi kết quả chưa đổi (so `revision`).

## Phải xác nhận với người dùng

- Cắt bỏ đoạn dài hoặc đoạn có lời thoại; dùng asset ngoài; thêm POV; xuất file (chi tiết: `workflow`).
- Nhạc trong game và bản thu âm nhạc có thể dính Content ID YouTube. Nhạc cổ điển (Can Can…) đã hết bản quyền sáng tác nhưng bản thu cụ thể thì chưa chắc: ưu tiên bản thu public domain và nhắc người dùng.
