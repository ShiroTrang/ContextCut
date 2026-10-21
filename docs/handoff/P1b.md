# Bàn giao P1b — MCP server Python, guide v0, đăng ký client

22/10/2026 · kế hoạch: `docs/plans/P1.md` (phần "P1b — chi tiết") · giao thức: `docs/protocol.md` · session P1b (Claude Opus 5.5)

## Đã xong

| Việc | Ở đâu |
| --- | --- |
| Project uv: Python 3.11, `mcp==2.3.0`, `websockets>=16,<18` (lock 17.3), `pydantic>=2.12,<3`; entry point `contextcut-ai` (stdio) | `contextcut-ai/pyproject.toml`, `uv.lock` |
| `BridgeClient`: đọc `bridge.json` mỗi lần nối (có BOM cũng được), chỉ nối `127.0.0.1`, một kết nối, khoá tuần tự, kết nối rớt thì đọc lại file và gửi lại **một** lần, bỏ trả lời trễ theo `id`; nối 5 s, chờ trả lời 30 s | `src/contextcut_ai/bridge_client.py` |
| Lỗi cho agent bằng tiếng Việt: "Mở ContextCut trước (…)" khi thiếu file, cổng chết, token cũ, `no_project`, `busy`; câu riêng cho `stale_cursor`, `invalid_params`, `not_found`, hết giờ, sai giao thức | `src/contextcut_ai/errors.py` |
| MCP server `contextcut`: tool `get_editor_state`, `get_timeline(start_f, end_f, tracks, limit=100, cursor)`, `list_recordings(limit, cursor)`, `get_guide(topic)`; JSON một dòng giữ UTF-8, không `structuredContent`, `readOnlyHint`; prompt `mo-phien-dung(style, goal)`; resource tĩnh `contextcut://guide/<topic>` + `index`; `instructions` | `src/contextcut_ai/mcp_server.py` |
| Guide v0 (tiếng Việt, front matter): `instructions`, `workflow`, `editing-rules` (§8.6, không bịa, chống "lố" có hạn mức khởi đầu, tiết kiệm hạn mức ảnh), `software` (frame, nửa mở, id, track, bản ghi, revision, phân trang, lỗi, bảng tool theo GĐ), `styles/gaming`, 4 pattern dạng khung | `contextcut-ai/guide/` |
| `SKILL.md` và đoạn `AGENTS.md` sinh từ guide (test báo khi lệch) | `skills/`, `scripts/gen_agent_docs.py`, `src/contextcut_ai/agent_docs.py` |
| Đăng ký client: dò Claude Code (CLI `claude mcp add --scope user`, cài skill vào `~/.claude/skills/contextcut-editor/`), Claude Desktop, Codex (TOML, giữ chú thích), Antigravity; in diff/lệnh, hỏi y/N từng cái, sao lưu `.bak-<giờ>`; chạy lại thì báo "đã đăng ký đúng" | `scripts/register_clients.py`, `src/contextcut_ai/register.py` |
| 52 test pytest: cầu nối giả (server WebSocket thật), MCP qua `mcp.Client` trong bộ nhớ, guide, file sinh ra, đăng ký (thư mục giả) + 1 test sống qua stdio (`-m live`) | `contextcut-ai/tests/` |

## Bằng chứng cổng

Đo 22/10/2026 trên máy Nhan. App: `stage\bin\contextcut.exe` bản P1a (P1b không đổi C++). Project thử: bản sao `tests/dataset/clip-ids.kdenlive` + 4 `.mpg` (25 fps, V2/V1/A1/A2, 16 clip) trong scratchpad, thêm bản OBS giả `Ông Sang câu cá 2026-10-22.mkv` (ffmpeg, 640×360, 30 fps, 6 s, 3 stream audio) bằng `-i`. Không file nào trong repo bị sửa.

| Kiểm | Kết quả |
| --- | --- |
| `uv run --directory contextcut-ai pytest` | 52 passed (test sống chạy khi app mở; bỏ qua khi tắt) |
| `bridge_probe.py check --quick` (cầu nối P1a vẫn đúng) | mọi mục PASS |
| UTF-8 qua stdio thật | `list_recordings` một dòng 2254 ký tự, có "Ông Sang câu cá", không `\u` |
| App ở **màn hình chào** (mở không project, không `--no-welcome`) | 30 s không có `bridge.json` (cửa sổ `Splash`, MainWindow chưa dựng nên cầu nối chưa mở); agent nhận "Mở ContextCut trước (không thấy …\bridge.json: app chưa chạy, hoặc còn ở màn hình chào)" |
| Đăng ký (Nhan đồng ý cả 4) | Claude Code: `claude mcp get contextcut` → `✓ Connected`; skill `contextcut-editor` cài; Claude Desktop, Codex, Antigravity: ghi + `.bak-20261022-015728`; chạy lại `--dry-run` → cả 5 mục "đã đăng ký đúng / mới nhất" |
| **Claude Code** (`claude -p`, sonnet, app mở) | Agent tự tải tool (ToolSearch), gọi `get_editor_state`, `list_recordings`, `get_guide("editing-rules")`; trả lời đúng 25 fps, V2/V1/A1/A2 mỗi track 4 clip, 16 clip, 5 bản ghi (bản OBS "chưa" lên timeline), nêu đúng "Nhân trước, quả sau". Lần đầu agent bỏ qua `list_recordings`: đã thêm vào mô tả `get_editor_state` câu "tên và chi tiết bản ghi ở list_recordings", lần sau gọi đủ |
| Claude Code, app tắt | `get_editor_state` → "Mở ContextCut trước (không thấy …bridge.json…)"; agent báo người dùng mở app, không gọi lặp |
| Claude Code, prompt | `/mcp__contextcut__mo-phien-dung gaming "…"` được mở thành lệnh; agent làm đủ các bước (state, bản ghi, 3 guide, timeline), ghi rõ dàn ý là đoán vì chưa nghe/xem, dừng chờ duyệt. Init của phiên liệt kê đủ 4 tool, prompt và skill |
| **Codex** (`codex exec -m gpt-5.6-terra`, sandbox read-only, app mở) | Gọi `get_editor_state`, `list_recordings`, `get_guide("editing-rules")`, trả lời đúng; tool chỉ đọc được duyệt tự động. Lần đầu nó đi lạc sang computer-use và đọc tài liệu plugin trước (165k token vào, 130k cache) |
| Codex, app tắt | `get_editor_state` lỗi "Mở ContextCut trước (…)"; agent báo mở app |
| Đóng app bình thường | `bridge.json` biến mất, app thoát mã 0 |

## Chưa thử

- **Antigravity**: đã đăng ký (`~\.gemini\config\mcp_config.json`) nhưng chưa ai hỏi thử; Antigravity không có chế độ dòng lệnh dùng được (`agentapi.bat` trỏ tới file không còn).
- **Claude Desktop**: đã ghi cấu hình; phải thoát hẳn app Claude rồi mở lại mới nạp. Chưa thử.
- **Claude Code trong app desktop** (session Code mới): chưa thử; cổng chạy bằng CLI `claude -p`.
- Codex có hiện prompt/resource MCP không: chưa thử (chỉ thử tool). Resource `contextcut://guide/…` chưa thử ở client nào (tool `get_guide` thay được).

## Lệch so với thiết kế / kế hoạch

1. **`mcp` 2.x** (2.3.0, 02/10/2026) đổi API: `from mcp.server import MCPServer`, lỗi cho agent bằng `mcp.server.mcpserver.exceptions.ToolError`; SDK thêm tiền tố "Error executing tool <tên>: " vào câu lỗi.
2. **Màn hình chào không trả `no_project`**: cầu nối chỉ mở sau khi rời màn hình chào (handoff P1a mục 9 đoán sai). `no_project` vẫn xảy ra lúc hộp File Recovery mở. Câu lỗi khi thiếu `bridge.json` nhắc cả hai khả năng.
3. `get_timeline` qua MCP mặc định `limit` 100 (app mặc định 200) để đỡ token.
4. Guide ở `contextcut-ai/guide/` (theo design §10), không phải `src/contextcut_ai/guide/` như phác thảo; đường dẫn tìm từ package (bản cài editable của uv) hoặc `CONTEXTCUT_GUIDE_DIR`.
5. Hạn mức chống "lố" trong `editing-rules.md` (meme 1/60 s, SFX 1/20 s, zoom 1/30 s) là **đề xuất chưa chấm**.
6. Cấu hình Claude Desktop trên máy Nhan nằm ở `%LOCALAPPDATA%\Claude-Data\claude_<id>\claude_desktop_config.json` (bản MSIX đã dời dữ liệu), không phải `%APPDATA%\Claude\`. Antigravity bản này đọc `~\.gemini\config\mcp_config.json`.
7. Model mặc định trong `~\.codex\config.toml` của Nhan (`gpt-5.6-sol`) bị tài khoản ChatGPT từ chối; cổng chạy với `-m gpt-5.6-terra`, không sửa cấu hình.
8. Trong các lần `claude -p` với `--allowedTools mcp__contextcut`, agent gọi skill `contextcut-editor` trước và bị từ chối quyền (không có trong allowedTools); agent vẫn làm đúng nhờ `instructions` và `get_guide`.

## Lệnh

```powershell
uv run --directory contextcut-ai pytest                 # 52 test; -m live: chỉ test sống
uv run --directory contextcut-ai python scripts/register_clients.py --dry-run
uv run --directory contextcut-ai python scripts/gen_agent_docs.py [--check]
claude mcp get contextcut                                # Claude Code thấy server không
```

Thử agent không giao diện từ Git Bash (bỏ biến của app desktop trước):

```bash
for v in $(env | grep -E "^(CLAUDE|ANTHROPIC_)" | cut -d= -f1); do unset "$v"; done
MSYS_NO_PATHCONV=1 claude -p "Project đang mở trong ContextCut có gì?" --model sonnet --allowedTools mcp__contextcut --output-format stream-json --verbose
"$LOCALAPPDATA/OpenAI/Codex/bin/<hash>/codex.exe" exec --skip-git-repo-check --ephemeral -s read-only --json -m gpt-5.6-terra "…" < /dev/null
```

## Bẫy mới (đã chép phần cần vào CLAUDE.md)

- `claude` CLI chạy từ trong phiên của app desktop thừa hưởng `ANTHROPIC_BASE_URL`, `CLAUDE_CODE_*`; token riêng của CLI trên máy Nhan đã hết hạn một lần (401 "revoked", Nhan `claude auth login` lại).
- Git Bash đổi đối số `/mcp__…` thành đường dẫn: `MSYS_NO_PATHCONV=1`.
- `codex exec` đợi stdin nếu không chuyển hướng (`< /dev/null`).
- Đóng app có hộp "save changes?": UIA `WindowPattern.Close` treo, UIA không thấy nút trong hộp; dùng `WM_CLOSE` + `PostMessage` nhấp vào "Do Not Save" (toạ độ trong CLAUDE.md).
- MCP server được client chạy thẳng từ repo (`uv --directory …\contextcut-ai run --frozen`): sửa code thì client nạp bản mới ở phiên sau; đổi phụ thuộc thì nhớ `uv lock` (`--frozen` không tự cập nhật lock).

## P1c cần biết

- Thêm tool ghi vào `build_server` trong `mcp_server.py`. `read_tool` gắn `readOnlyHint=True`; tool sửa cần chú thích khác (`readOnlyHint=False`, `destructiveHint` tuỳ op) và vẫn trả JSON một dòng qua `call()`.
- `BridgeClient.call` gửi lại **một** lần khi kết nối rớt giữa chừng. Với `apply_operations`, `base_revision` chặn áp dụng hai lần (lần gửi lại sẽ gặp `conflict`), nhưng agent sẽ thấy `conflict` thay vì kết quả đợt đầu: cân nhắc tham số không gửi lại cho method ghi, hoặc báo rõ "có thể đã áp dụng, đọc lại".
- `errors.agent_message` cần câu cho `conflict`, `validation_failed` (`errors[]`), `apply_failed` (`op_index`, `reason`).
- Cập nhật `guide/instructions.md` (bỏ "chỉ đọc"), bảng tool trong `guide/software.md` (test bắt mọi tool đăng ký phải có tên ở đó), `workflow.md`; chạy `gen_agent_docs.py`, rồi `register_clients.py` để cập nhật skill đã cài.
- `FakeBridge.responses` nhận dict hoặc hàm `(params) -> dict`: dùng để giả `apply_operations`/`conflict`.
- Cổng P1 cần Claude Code **và** Codex: lệnh thử ở trên chạy được không giao diện.
