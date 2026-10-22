---
title: Tóm tắt cho agent
summary: Phát qua MCP instructions; đầu SKILL.md và đoạn AGENTS.md
---
ContextCut là app dựng video gaming (fork Kdenlive) của Nhan, dùng chung với vài người bạn. MCP server `contextcut` đọc và sửa timeline đang mở trong app; người dùng duyệt và chỉnh tay như với một người dựng phụ. Trả lời bằng tiếng Việt.

- Gọi `get_editor_state` trước mọi việc. Thời gian là **frame nguyên** theo fps của project; mọi khoảng là nửa mở `[start_f, end_f)`.
- Sửa: đọc `revision` → `validate_operations` → `apply_operations(ops, base_revision, label "AI: …")`. Một đợt là một bước undo (Ctrl+Z hoàn tác cả đợt); người dùng sửa chen ngang thì bị từ chối (`conflict`): đọc lại rồi gửi lại. Op và tham số: `list_operations`; id nguồn (nhạc, bản ghi): `list_sources`.
- Chỉ dựng phần người dùng đã duyệt; xong thì báo nhãn đợt và nhắc Ctrl+Z.
- Nghe lời thoại: `transcribe(recording)` (job nền, theo dõi bằng `get_job`) rồi `get_transcript` theo khoảng. Phụ đề: `add_subtitles` (đầy đủ) hoặc op `caption` có `speaker` (câu đắt). Chưa xem được hình: đừng nói là đã xem.
- Trước khi đề xuất dựng, đọc `get_guide("workflow")` và `get_guide("editing-rules")`; phong cách gaming: `get_guide("styles/gaming")`. Mục lục: `get_guide()`.
- Không bịa lời thoại hay sự kiện chưa nghe hoặc chưa xem. Chỗ nào là suy đoán thì nói rõ.
- Lỗi "Mở ContextCut trước (…)": app chưa chạy, chưa mở project hoặc đang nạp. Nhờ người dùng mở rồi gọi lại; đừng gọi lặp liên tục.
