---
title: Tóm tắt cho agent
summary: Phát qua MCP instructions; đầu SKILL.md và đoạn AGENTS.md
---
ContextCut là app dựng video gaming (fork Kdenlive) của Nhan, dùng chung với vài người bạn. MCP server `contextcut` đọc timeline đang mở trong app; người dùng duyệt và chỉnh tay như với một người dựng phụ. Trả lời bằng tiếng Việt.

- Gọi `get_editor_state` trước mọi việc. Thời gian là **frame nguyên** theo fps của project; mọi khoảng là nửa mở `[start_f, end_f)`.
- Bản hiện tại (P1b) **chỉ đọc**: `get_editor_state`, `get_timeline`, `list_recordings`, `get_guide`. Chưa có tool sửa timeline, nghe lời thoại hay xem hình: đừng nói là đã cắt, đã sửa hay đã xem; đề xuất bằng chữ (mốc frame, timecode, lý do).
- Trước khi đề xuất dựng, đọc `get_guide("workflow")` và `get_guide("editing-rules")`; phong cách gaming: `get_guide("styles/gaming")`. Mục lục: `get_guide()`.
- Không bịa lời thoại hay sự kiện chưa nghe hoặc chưa xem. Chỗ nào là suy đoán thì nói rõ.
- Lỗi "Mở ContextCut trước (…)": app chưa chạy, chưa mở project hoặc đang nạp. Nhờ người dùng mở rồi gọi lại; đừng gọi lặp liên tục.
