<!-- contextcut-guide:begin (Sinh từ contextcut-ai/guide/ bằng scripts/gen_agent_docs.py; sửa guide rồi chạy lại, đừng sửa tay.) -->
## ContextCut (MCP server `contextcut`)

ContextCut là app dựng video gaming (fork Kdenlive) của Nhan, dùng chung với vài người bạn. MCP server `contextcut` đọc và sửa timeline đang mở trong app; người dùng duyệt và chỉnh tay như với một người dựng phụ. Trả lời bằng tiếng Việt.

- Gọi `get_editor_state` trước mọi việc. Thời gian là **frame nguyên** theo fps của project; mọi khoảng là nửa mở `[start_f, end_f)`.
- Sửa: đọc `revision` → `validate_operations` → `apply_operations(ops, base_revision, label "AI: …")`. Một đợt là một bước undo (Ctrl+Z hoàn tác cả đợt); người dùng sửa chen ngang thì bị từ chối (`conflict`): đọc lại rồi gửi lại. Op và tham số: `list_operations`; id nguồn (nhạc, bản ghi): `list_sources`.
- Chỉ dựng phần người dùng đã duyệt; xong thì báo nhãn đợt và nhắc Ctrl+Z.
- Nghe lời thoại: `transcribe(recording)` (job nền, theo dõi bằng `get_job`) rồi `get_transcript` theo khoảng. Phụ đề: `add_subtitles` (đầy đủ) hoặc op `caption` có `speaker` (câu đắt). Chưa xem được hình: đừng nói là đã xem.
- Trước khi đề xuất dựng, đọc `get_guide("workflow")` và `get_guide("editing-rules")`; phong cách gaming: `get_guide("styles/gaming")`. Mục lục: `get_guide()`.
- Không bịa lời thoại hay sự kiện chưa nghe hoặc chưa xem. Chỗ nào là suy đoán thì nói rõ.
- Lỗi "Mở ContextCut trước (…)": app chưa chạy, chưa mở project hoặc đang nạp. Nhờ người dùng mở rồi gọi lại; đừng gọi lặp liên tục.

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

### Hướng dẫn đầy đủ

Đọc bằng `get_guide("<topic>")` hoặc resource `contextcut://guide/<topic>`:

- workflow: Quy trình dựng. Phân tích → dàn ý → duyệt → dựng → tự kiểm → xuất; bước nào làm được ở bản này, khi nào phải hỏi người dùng.
- editing-rules: Quy tắc biên tập. Cắt và chuyển POV cho tự nhiên (Nhan chốt bằng ví dụ), không bịa, chống "lố", tiết kiệm hạn mức gói AI, việc phải xác nhận.
- software: Cách dùng phần mềm. Frame, khoảng nửa mở, fps, id, track và tag, bản ghi, track_map và nguồn, revision/base_revision, sửa timeline theo đợt (op, undo, xung đột, phụ đề), lời thoại (transcript, job), phân trang, lỗi, tool có bây giờ và ở giai đoạn sau.
- styles/gaming: Phong cách gaming (funny moments). Funny moments nhiều người chơi kiểu nhóm CKG (HK15, Sangtraan): bố cục, phụ đề câu đắt, meme, thay facecam, nhịp, Minecraft.
- patterns/irony-cut: Cú cắt mỉa (irony cut). Câu thoại tự tin, cắt gọn sang cảnh phản bác câu đó, nhạc vào đúng điểm cắt.
- patterns/meanwhile: Hai mạch song song ("Trong lúc đó:"). Kể trọn một mạch rồi chuyển sang mạch song song tương phản của người khác, mở bằng thẻ chữ "Trong lúc đó:".
- patterns/beat-montage: Montage theo beat. Chuỗi khoảnh khắc cùng loại, mỗi cú cắt rơi đúng phách mạnh của bản nhạc (sai số ±1 frame).
- patterns/reaction-zoom: Zoom phản ứng thay facecam. Không có facecam, nên nhấn phản ứng bằng zoom vào gameplay, phụ đề to, SFX hoặc meme.
- patterns/subtitles: Phụ đề đầy đủ và câu đắt. Hai kiểu phụ đề (đầy đủ trên track phụ đề, câu đắt trên track Chữ), timing theo từ, style theo người nói, khi nào dùng.

<!-- contextcut-guide:end -->
