# contextcut-ai — dịch vụ Python (MCP server)

Tiến trình riêng, nói chuyện với app ContextCut đang mở qua WebSocket. AI client (Claude Code, Claude Desktop, Codex, Antigravity) kết nối vào đây qua MCP.

Dự kiến (theo `docs/specs/kien-truc-v3.md` và `docs/specs/2026-10-21-contextcut-design.md` mục 9–10):

- `pyproject.toml` — pin phiên bản MCP SDK, chạy bằng `uv`.
- `src/contextcut_ai/mcp_server.py` — MCP server (stdio).
- `src/contextcut_ai/bridge_client.py` — client WebSocket tới app.
- `src/contextcut_ai/schemas/`, `analysis/`, `jobs.py`.
- `guide/` — hướng dẫn cho AI agent, một nguồn cho mọi client.
- `tests/`.

Trạng thái P0: **chỉ có README**. Code bắt đầu từ P1.
