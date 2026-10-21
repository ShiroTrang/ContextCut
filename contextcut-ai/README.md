# contextcut-ai — dịch vụ Python (MCP server)

Tiến trình riêng, nói chuyện với app ContextCut đang mở qua WebSocket (`docs/protocol.md`). AI client (Claude Code, Claude Desktop, Codex, Antigravity) kết nối vào đây qua MCP.

Dự kiến (theo `docs/specs/kien-truc-v3.md`, `docs/specs/2026-10-21-contextcut-design.md` mục 9–10 và `docs/plans/P1.md`):

- `pyproject.toml` — pin phiên bản MCP SDK, chạy bằng `uv` (P1b).
- `src/contextcut_ai/mcp_server.py` — MCP server (stdio) (P1b).
- `src/contextcut_ai/bridge_client.py` — client WebSocket tới app (P1b).
- `src/contextcut_ai/schemas/`, `analysis/`, `jobs.py` (P2+).
- `guide/` — hướng dẫn cho AI agent, một nguồn cho mọi client (P1b).
- `tests/` (P1b).

Đã có (P1a):

- `tools/bridge_probe.py` — client thử cầu nối, script độc lập (PEP 723, `websockets==16.0`):

  ```powershell
  uv run contextcut-ai/tools/bridge_probe.py check           # các kiểm tra của cổng P1a (thêm --quick để bỏ mục chờ 6 giây)
  uv run contextcut-ai/tools/bridge_probe.py call get_editor_state
  uv run contextcut-ai/tools/bridge_probe.py call get_timeline limit=5 start_f=0
  uv run contextcut-ai/tools/bridge_probe.py watch --seconds 60   # in revision mỗi khi timeline đổi
  ```
