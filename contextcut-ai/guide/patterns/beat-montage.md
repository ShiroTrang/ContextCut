---
title: Montage theo beat
summary: Chuỗi khoảnh khắc cùng loại, mỗi cú cắt rơi đúng phách mạnh của bản nhạc (sai số ±1 frame).
order: 22
---
# Montage theo beat

Trạng thái: khung (guide v0). Cần `detect_beats`, `beat_montage`, `find_moments` (P3); trước đó chỉ đề xuất bằng chữ.

## Khi dùng

Chuỗi sự kiện cùng loại mà từng cái không đủ dài để đứng riêng: chết liên tiếp ("tạch liên hoàn"), đồ hiếm, fail, troll nhau.

## Các bước

1. Chọn nhạc trong thư viện (có manifest ghi nguồn và giấy phép); ưu tiên bản thu public domain.
2. `detect_beats` lấy danh sách phách kèm độ mạnh.
3. Chọn khoảnh khắc (`find_moments`, xác nhận bằng hình ở mốc nghi ngờ).
4. Mỗi clip có điểm vào hợp lý: khoảnh khắc chính (ví dụ màn hình chết) rơi gần đầu phách, không bị cắt cụt.
5. `beat_montage` đặt mỗi cú cắt trùng phách mạnh, sai số ±1 frame.

## Lưu ý

- Shot ngắn hơn 1,5 giây được phép trong montage, nhưng ghi lý do.
- Lời thoại trong montage thường tắt hoặc nhỏ, trừ câu đắt.
- Hay đi sau một cú cắt mỉa (`patterns/irony-cut`).

## Tool cần

`detect_beats`, `beat_montage`, `find_moments`, `list_assets` (P3), `add_music` (P1c).
