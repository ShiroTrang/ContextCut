# P2a — Đo ASR tiếng Việt (WER, lệch thời gian, tốc độ, VRAM)

22/10/2026 · máy Nhan: RTX 3060 Laptop 6 GB (desktop chiếm sẵn 0,7–1,6 GB), driver 596.49 · công cụ: `contextcut-ai/tools/asr_eval.py` (mỗi model một tiến trình, cùng pipeline với job `transcribe`: Silero VAD → chunk → ASR → lọc ảo giác → tinh chỉnh ranh giới theo năng lượng).

## Ứng viên

| Model | Engine | Cấu hình | Dung lượng | Ghi chú |
| --- | --- | --- | --- | --- |
| `large-v3` | faster-whisper 1.2.1 / CTranslate2 4.8.3 | `int8_float16`, beam 5, `word_timestamps`, có token timestamp | 3,1 GB (`Systran/faster-whisper-large-v3`) | |
| `phowhisper-large` | như trên | `int8_float16`, `without_timestamps=True` (bản fine-tune không sinh token timestamp đáng tin; mốc từ lấy bằng DTW trên alignment heads) | 3,1 GB, chuyển tại máy từ `vinai/PhoWhisper-large` (6,2 GB) bằng `tools/convert_phowhisper.py` | Lần đầu để `float16` + có token timestamp: 60 s audio mất 63 s, VRAM đỉnh 5,6 GB; sau khi đổi: 10,7 s, 3,3 GB |
| `parakeet-ctc-vi` | NeMo 2.6.2 + PyTorch 2.9.1 cu126 | fp32, CTC greedy, timestamp từ | 2,6 GB (`nvidia/parakeet-ctc-0.6b-Vietnamese`, Nhan thêm và đồng ý tải 22/10) | `restore_from(map_location="cuda")` giữ **hai bản** trọng số (4,7 GB) → card 6 GB tràn sang RAM chung, 20 s audio mất 37–83 s. Nạp lên CPU rồi `.to("cuda")`: 2,4 GB, 60 s audio < 1 s |

## Bộ đo tạm: 3 bài hát SongMV (giọng hát, chưa phải lời nói)

Mốc gõ tay của Nhan trong Lyric Calibrator (`D:\SongMV\tools\lyric_calibrator\songs\*\versions\`), chỉ có **đầu từ** (gõ không giữ phím; `latency_ms: 0` — chưa trừ độ trễ tay). Audio = stem giọng Demucs. Đầu câu = đầu từ ASR khớp với từ đầu dòng lời. Số trong ô: trung vị / p90 (ms).

| Bài (số từ) | Model | WER | Từ khớp | Đầu từ | Đầu câu (raw) | Đầu câu (tinh chỉnh) | ASR (s) | VRAM đỉnh card (MiB) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Lỡ Thương Nhau (378) | large-v3 | 0,508 | 186 | 237/419 | 538/964 | 539/953 | 24,8 | 3383 |
| | phowhisper-large | **0,177** | 316 | **128**/308 | 588/981 | 578/976 | 49,0 | 4385 |
| | parakeet-ctc-vi | 0,291 | 278 | 183/321 | 265/305 | **99**/290 | **3,4** | 3970 |
| Em Đau (333) | large-v3 | 0,530 | 158 | 282/570 | 696/2302 | 640/2302 | 16,3 | 3379 |
| | phowhisper-large | **0,359** | 215 | **119**/327 | 476/1101 | 448/1018 | 21,5 | 3379 |
| | parakeet-ctc-vi | 0,404 | 205 | 238/377 | 216/504 | **91**/504 | **3,0** | 4294 |
| Có Em Đời Bỗng Vui (305) | large-v3 | 0,259 | 226 | 280/746 | 782/1448 | 766/1442 | 23,0 | 3401 |
| | phowhisper-large | **0,088** | 281 | **88**/638 | 673/1518 | 638/1513 | 26,3 | 3455 |
| | parakeet-ctc-vi | 0,197 | 253 | 196/444 | 173/1463 | **77**/1463 | **3,3** | 4465 |

Đọc số:

- **Chữ:** PhoWhisper tốt nhất, Parakeet thứ hai, large-v3 kém nhất trên giọng hát (bỏ cả đoạn đầu bài, thay bằng câu ảo giác "Hãy subscribe cho kênh Ghiền Mì Gõ…" — bộ lọc đã bỏ câu này).
- **Đầu câu (thứ phụ đề cần):** chỉ Parakeet + tinh chỉnh đạt < 100 ms (77–99 ms). Mốc từ của Whisper (DTW) ở từ đầu câu sau khoảng lặng lệch 0,4–0,8 s, ngoài cửa sổ ±0,3 s của bước tinh chỉnh nên tinh chỉnh không cứu được. Timestamp CTC của Parakeet rơi đúng khung 80 ms quanh chỗ bắt đầu nói, nên tinh chỉnh kéo được về đúng chỗ có tiếng.
- **Tốc độ:** Parakeet nhanh hơn ~7–15 lần.
- **VRAM:** đỉnh toàn card 3,4–4,5 GB trên 6 GB.
- Hát kéo dài chữ và có nhạc nền rò vào stem: không dùng bộ này cho cổng, chỉ để xếp hạng.

## Bản ghi thật một track (khói)

`C:\Users\VuNhan\Videos\2026-07-10 00-24-05.mkv` (34 phút, 1 track trộn, không có mốc tay), job `transcribe` thật qua worker, `large-v3`: 375 s (Silero thấy 20,5 phút có tiếng; 5,4× thời gian thực), VRAM đỉnh 4451/6144 MiB, 555 câu, 3396 từ, bỏ 7 câu ảo giác, tinh chỉnh 236 đầu câu / 191 cuối câu. Chữ đọc được tốt (lời nói thường, có chửi thề).

## Quyết định tạm

Quy tắc của kế hoạch: chọn WER thấp hơn, miễn trung vị lệch đầu/cuối câu sau tinh chỉnh < 100 ms. Trên bộ bài hát chỉ `parakeet-ctc-vi` đạt điều kiện thời gian → **mặc định tạm = `parakeet-ctc-vi`**, máy thiếu thì lùi `phowhisper-large` rồi `large-v3` (`asr.PREFERENCE`, `asr.default_model()`). Chốt lại trên bản ghi OBS của Nhan (giọng nói thật, mốc có cả cuối từ).

Hướng thử nếu lời nói thật cho kết quả giống bài hát: lấy **chữ của PhoWhisper + mốc của Parakeet** (căn hai chuỗi từ bằng Levenshtein như `asr_eval.align_words`, từ khớp lấy mốc Parakeet, từ không khớp nội suy). Chưa làm.

## Chạy lại

```powershell
uv run --directory contextcut-ai --no-sync python tools/asr_eval.py --calibration <file mốc.json> --audio <wav|mkv> [--index N] [--ends] --out kết-quả.json
```
