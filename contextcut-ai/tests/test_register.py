# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
import json
import subprocess
import tomllib

import pytest

from contextcut_ai import agent_docs
from contextcut_ai.register import Context, main, plan

UV = "C:/tools/uv.exe"
ARGS = ["--directory", "D:/repo/contextcut-ai", "run", "--frozen", "contextcut-ai"]
WANT = {"command": UV, "args": ARGS}


class FakeRunner:
    def __init__(self, registered: bool = False):
        self.registered = registered
        self.commands: list[list[str]] = []

    def __call__(self, cmd: list[str]) -> subprocess.CompletedProcess:
        self.commands.append(cmd)
        code = 0 if cmd[1:3] != ["mcp", "get"] or self.registered else 1
        return subprocess.CompletedProcess(cmd, code, stdout="", stderr="")


@pytest.fixture
def ctx(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    env = {"APPDATA": str(tmp_path / "Roaming"), "LOCALAPPDATA": str(tmp_path / "Local"), "USERPROFILE": str(home)}
    return Context(env=env, home=home, which=lambda name: None, run=FakeRunner(), command=(UV, ARGS))


def never_ask(prompt: str) -> str:
    raise AssertionError(f"không được hỏi: {prompt}")


def write(path, text, *, bom=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((b"\xef\xbb\xbf" if bom else b"") + text.encode("utf-8"))
    return path


def test_detects_only_installed_clients(ctx):
    assert plan(ctx) == []
    (ctx.home / ".codex").mkdir()
    assert [c.client for c in plan(ctx)] == ["Codex"]


def test_claude_desktop_relocated_data(ctx, tmp_path):
    cfg = write(tmp_path / "Local" / "Claude-Data" / "claude_abc" / "claude_desktop_config.json",
                json.dumps({"mcpServers": {"other": {"command": "node"}}, "preferences": {"x": 1}}, indent=2))
    [change] = plan(ctx)
    assert (change.client, change.target) == ("Claude Desktop", str(cfg))
    assert '+    "contextcut": {' in change.preview
    change.apply()
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data == {"mcpServers": {"other": {"command": "node"}, "contextcut": WANT}, "preferences": {"x": 1}}


def test_json_with_bom(ctx):
    cfg = write(ctx.home / ".gemini" / "config" / "mcp_config.json", '{"mcpServers": {}}', bom=True)
    [change] = plan(ctx)
    assert change.client == "Antigravity"
    change.apply()
    raw = cfg.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    assert json.loads(raw.decode("utf-8-sig"))["mcpServers"]["contextcut"] == WANT


def test_answer_no_writes_nothing(ctx):
    cfg = write(ctx.home / ".gemini" / "config" / "mcp_config.json", '{"mcpServers": {}}')
    for answer in ["n", "", "x"]:
        assert main([], ask=lambda _, a=answer: a, ctx=ctx) == 0
    assert cfg.read_text(encoding="utf-8") == '{"mcpServers": {}}'
    assert list(cfg.parent.iterdir()) == [cfg]


def test_answer_yes_writes_and_backs_up(ctx):
    cfg = write(ctx.home / ".gemini" / "config" / "mcp_config.json", '{"mcpServers": {}}')
    asked = []
    assert main([], ask=lambda p: asked.append(p) or "y", ctx=ctx) == 0
    assert len(asked) == 1
    backups = [p for p in cfg.parent.iterdir() if p.name.startswith("mcp_config.json.bak-")]
    assert len(backups) == 1 and backups[0].read_text(encoding="utf-8") == '{"mcpServers": {}}'
    assert json.loads(cfg.read_text(encoding="utf-8"))["mcpServers"]["contextcut"] == WANT


def test_already_registered_is_skipped(ctx):
    write(ctx.home / ".gemini" / "config" / "mcp_config.json", json.dumps({"mcpServers": {"contextcut": WANT}}))
    [change] = plan(ctx)
    assert change.apply is None
    assert main([], ask=never_ask, ctx=ctx) == 0


def test_toml_append_keeps_comments(ctx):
    original = ("# cấu hình của tôi\nmodel = 'gpt-5'\n\n[mcp_servers.node_repl]\n"
                "command = 'C:\\x\\node_repl.exe'  # đừng xoá\n")
    cfg = write(ctx.home / ".codex" / "config.toml", original)
    [change] = plan(ctx)
    change.apply()
    text = cfg.read_text(encoding="utf-8")
    assert text.startswith(original)
    data = tomllib.loads(text)
    assert data["mcp_servers"]["contextcut"] == WANT | {"startup_timeout_sec": 60}
    assert data["mcp_servers"]["node_repl"]["command"] == "C:\\x\\node_repl.exe"


def test_toml_replace_existing_table(ctx):
    cfg = write(ctx.home / ".codex" / "config.toml",
                "[mcp_servers.contextcut]\ncommand = 'uv'\nargs = ['old']\n\n[mcp_servers.contextcut.env]\nA = '1'\n\n"
                "[mcp_servers.other]\ncommand = 'other'\n")
    [change] = plan(ctx)
    assert "-args = ['old']" in change.preview
    change.apply()
    data = tomllib.loads(cfg.read_text(encoding="utf-8"))
    assert data["mcp_servers"]["contextcut"] == WANT | {"startup_timeout_sec": 60}
    assert data["mcp_servers"]["other"] == {"command": "other"}


def test_claude_code_uses_cli(ctx):
    (ctx.home / ".claude").mkdir()
    ctx.which = lambda name: "C:/npm/claude.cmd" if name == "claude" else None
    changes = {c.target: c for c in plan(ctx)}
    add = changes["claude mcp (scope user)"]
    assert add.client == "Claude Code"
    add.apply()
    assert ctx.run.commands[-1] == ["C:/npm/claude.cmd", "mcp", "add", "--scope", "user", "contextcut", "--", UV, *ARGS]
    ctx.run.registered = True
    assert {c.target: c for c in plan(ctx)}["claude mcp (scope user)"].apply is None


def test_claude_code_skill(ctx):
    (ctx.home / ".claude").mkdir()
    [skill] = [c for c in plan(ctx) if c.target.endswith("SKILL.md")]
    skill.apply()
    path = ctx.home / ".claude" / "skills" / "contextcut-editor" / "SKILL.md"
    assert path.read_text(encoding="utf-8") == agent_docs.render_skill()
    assert [c for c in plan(ctx) if c.target.endswith("SKILL.md")][0].apply is None


def test_dry_run_never_asks(ctx):
    cfg = write(ctx.home / ".gemini" / "config" / "mcp_config.json", '{"mcpServers": {}}')
    assert main(["--dry-run"], ask=never_ask, ctx=ctx) == 0
    assert cfg.read_text(encoding="utf-8") == '{"mcpServers": {}}'


def test_client_filter(ctx):
    write(ctx.home / ".gemini" / "config" / "mcp_config.json", '{"mcpServers": {}}')
    (ctx.home / ".codex").mkdir()
    assert [c.client for c in plan(ctx, clients=["codex"])] == ["Codex"]
