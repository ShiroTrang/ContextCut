# contextcut-ai — dịch vụ Python (MCP server)

Tiến trình riêng, nói chuyện với app ContextCut đang mở qua WebSocket (`docs/protocol.md`). AI client (Claude Code, Claude Desktop, Codex, Antigravity) kết nối vào đây qua MCP (stdio).

Project uv, Python 3.11, `mcp==2.3.0`. Tài liệu thiết kế: `docs/specs/2026-10-21-contextcut-design.md` §9–10; kế hoạch: `docs/plans/P1.md`.

## Có gì (P1b, P1c)

| Đường dẫn | Việc |
| --- | --- |
| `src/contextcut_ai/mcp_server.py` | MCP server `contextcut` (entry point `contextcut-ai`): tool đọc `get_editor_state`, `get_timeline`, `list_recordings`, `list_sources`, `list_operations`, `validate_operations`, `get_guide`; tool sửa `apply_operations`, `add_markers`, `undo_batch`, `import_media` (P1c); prompt `mo-phien-dung`; resource `contextcut://guide/<topic>`; `instructions` |
| `src/contextcut_ai/bridge_client.py` | Client WebSocket tới app: đọc `bridge.json`, một kết nối, tự nối lại khi app khởi động lại; lệnh sửa không gửi lại khi kết nối rớt sau lúc gửi |
| `src/contextcut_ai/errors.py` | Lỗi cầu nối → câu tiếng Việt cho agent ("Mở ContextCut trước (…)") |
| `guide/` | Hướng dẫn cho agent, **nguồn duy nhất** (tiếng Việt, front matter `title`/`summary`/`order`) |
| `skills/contextcut-editor/SKILL.md`, `skills/AGENTS-snippet.md` | Sinh từ `guide/` (đừng sửa tay) |
| `scripts/gen_agent_docs.py` | Sinh lại hai file trên (`--check` để kiểm) |
| `scripts/register_clients.py` | Đăng ký server cho các client có trên máy; in thay đổi, hỏi y/N từng cái, sao lưu file cũ |
| `tools/bridge_probe.py` | Client thử cầu nối (P1a) |
| `tools/p1_fixture.py` | Dựng project thử `p1-gate` cho test sống của op (P1c) |
| `tests/` | pytest: cầu nối giả (`fake_bridge.py`) + test sống `-m live` (tự bỏ qua khi app không chạy); `test_live_ops.py` chỉ chạy khi project đang mở tên `p1-gate` vì nó sửa timeline (rồi hoàn tác) |

## Lệnh

```powershell
uv run --directory contextcut-ai pytest                      # mọi test (test sống tự bỏ qua nếu app không chạy)
uv run --directory contextcut-ai pytest -m live              # chỉ test sống, cần ContextCut đang mở project
uv run contextcut-ai/tools/p1_fixture.py --out <thư mục trống>  # project p1-gate cho test op, in lệnh mở app
uv run --directory contextcut-ai python scripts/gen_agent_docs.py           # sau khi sửa guide/
uv run --directory contextcut-ai python scripts/register_clients.py --dry-run   # xem sẽ ghi gì
uv run --directory contextcut-ai python scripts/register_clients.py             # ghi (hỏi y/N từng thay đổi)
```

Lệnh server mà client chạy: `<uv.exe> --directory <repo>\contextcut-ai run --frozen contextcut-ai`.

## Sửa guide

Sửa file trong `guide/`, chạy `gen_agent_docs.py`, chạy test. Tool mới phải có tên trong `guide/software.md` (test kiểm). `guide/instructions.md` giữ dưới 1500 ký tự: nó đi vào context của agent ở mọi phiên.
