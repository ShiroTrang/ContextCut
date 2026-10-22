# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
"""Đăng ký MCP server `contextcut` cho các AI client có trên máy.

In đúng thay đổi sẽ ghi (diff hoặc lệnh) và hỏi y/N từng cái; ghi file thì sao lưu bản cũ trước.
Không có cờ tự đồng ý.
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import agent_docs

SERVER = "contextcut"
PROJECT_DIR = Path(__file__).resolve().parents[2]  # contextcut-ai/
CLIENTS = ["claude-code", "claude-desktop", "codex", "antigravity"]
CODEX_TIMEOUT = 60  # giây; lần đầu nạp Python + thư viện có thể chậm


def server_command(project_dir: Path = PROJECT_DIR) -> tuple[str, list[str]]:
    uv = shutil.which("uv")
    if uv is None:
        raise SystemExit("không thấy uv trên PATH (cài: https://docs.astral.sh/uv/)")
    # --no-sync: `uv run` (kể cả --frozen) cài lại project khi pyproject đổi, mà Windows khoá contextcut-ai.exe
    # khi một client khác đang chạy server → server mới thoát ngay ("Connection closed"). Cài bằng `uv sync`.
    return str(Path(uv).resolve()), ["--directory", str(project_dir), "run", "--no-sync", "contextcut-ai"]


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


@dataclass
class Context:
    env: Mapping[str, str] = field(default_factory=lambda: dict(os.environ))
    home: Path = field(default_factory=Path.home)
    which: Callable[[str], str | None] = shutil.which
    run: Callable[[list[str]], subprocess.CompletedProcess] = _run
    command: tuple[str, list[str]] = field(default_factory=server_command)

    def path(self, var: str, *parts: str) -> Path | None:
        base = self.env.get(var)
        return Path(base, *parts) if base else None


@dataclass
class Change:
    client: str
    target: str
    summary: str
    preview: str = ""
    apply: Callable[[], str] | None = None  # None: không có gì để ghi


def _diff(old: str, new: str, name: str) -> str:
    return "".join(difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True),
                                        fromfile=name, tofile=f"{name} (sau khi ghi)"))


def _backup(path: Path) -> str:
    if not path.exists():
        return f"tạo mới {path}"
    backup = path.with_name(f"{path.name}.bak-{datetime.now():%Y%m%d-%H%M%S}")
    shutil.copy2(path, backup)
    return f"sao lưu bản cũ: {backup}"


def _write_file(path: Path, text: str, bom: bool = False) -> Callable[[], str]:
    def apply() -> str:
        note = _backup(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((b"\xef\xbb\xbf" if bom else b"") + text.encode("utf-8"))
        return note
    return apply


def _json_change(client: str, path: Path, want: dict, note: str = "") -> Change:
    raw = path.read_bytes() if path.exists() else b""
    bom = raw.startswith(b"\xef\xbb\xbf")
    old = raw.decode("utf-8-sig")
    try:
        data = json.loads(old) if old.strip() else {}
    except json.JSONDecodeError as e:
        return Change(client, str(path), f"không đọc được JSON ({e}); sửa tay rồi chạy lại")
    servers = data.setdefault("mcpServers", {})
    if servers.get(SERVER) == want:
        return Change(client, str(path), "đã đăng ký đúng, bỏ qua")
    action = "thay" if SERVER in servers else "thêm"
    servers[SERVER] = want
    new = json.dumps(data, indent=2, ensure_ascii=False) + ("\n" if old.endswith("\n") or not old else "")
    summary = f"{action} mcpServers.{SERVER}"
    if note:
        summary += f" ({note})"
    return Change(client, str(path), summary, _diff(old, new, path.name), _write_file(path, new, bom))


def _toml_str(s: str) -> str:
    return f"'{s}'" if "'" not in s and "\n" not in s else json.dumps(s)


_TABLE_HEADER = re.compile(r"^\s*\[\[?\s*([^\]]+?)\s*\]\]?\s*(#.*)?$")


def _replace_toml_table(text: str, table: str, block: str) -> str | None:
    """Thay bảng `[table]` (cùng các bảng con) bằng `block`; None nếu không thấy header dạng thường."""
    lines = text.splitlines(keepends=True)
    start = end = None
    for i, line in enumerate(lines):
        m = _TABLE_HEADER.match(line)
        if not m:
            continue
        name = m.group(1)
        if start is None and name == table:
            start = i
        elif start is not None and not name.startswith(table + "."):
            end = i
            break
    if start is None:
        return None
    end = len(lines) if end is None else end
    tail = "".join(lines[end:])
    return "".join(lines[:start]) + block + ("\n" + tail if tail else "")


def _codex_change(path: Path, uv: str, args: list[str]) -> Change:
    old = path.read_text(encoding="utf-8-sig") if path.exists() else ""
    try:
        current = tomllib.loads(old).get("mcp_servers", {}).get(SERVER)
    except tomllib.TOMLDecodeError as e:
        return Change("Codex", str(path), f"không đọc được TOML ({e}); sửa tay rồi chạy lại")
    want = {"command": uv, "args": args, "startup_timeout_sec": CODEX_TIMEOUT}
    if current == want:
        return Change("Codex", str(path), "đã đăng ký đúng, bỏ qua")
    block = (f"[mcp_servers.{SERVER}]\ncommand = {_toml_str(uv)}\n"
             f"args = [{', '.join(_toml_str(a) for a in args)}]\nstartup_timeout_sec = {CODEX_TIMEOUT}\n")
    if current is None:
        new = (old.rstrip("\n") + "\n\n" if old.strip() else "") + block
    else:
        new = _replace_toml_table(old, f"mcp_servers.{SERVER}", block)
        if new is None:
            return Change("Codex", str(path), f"mcp_servers.{SERVER} viết ở dạng lạ; sửa tay")
    if tomllib.loads(new).get("mcp_servers", {}).get(SERVER) != want:
        return Change("Codex", str(path), "không ghép được TOML an toàn; sửa tay")
    action = "thay" if current is not None else "thêm"
    return Change("Codex", str(path), f"{action} [mcp_servers.{SERVER}]", _diff(old, new, path.name),
                  _write_file(path, new))


def _first_existing(paths: list[Path | None]) -> list[Path]:
    return [p for p in paths if p is not None and p.is_file()]


def _glob(base: Path | None, pattern: str) -> list[Path]:
    return sorted(base.glob(pattern)) if base is not None and base.is_dir() else []


def _claude_registered(out: str) -> tuple[str, str] | None:
    """(Command, Args) của server scope user trong output `claude mcp get`; None nếu scope khác hoặc không đọc được."""
    if "Scope: User" not in out:
        return None
    fields = dict(m.groups() for m in re.finditer(r"^\s*(Command|Args):[ \t]*(.*?)[ \t]*$", out, re.M))
    if "Command" not in fields:
        return None
    return os.path.normcase(os.path.normpath(fields["Command"])), fields.get("Args", "")


def _run_all(ctx: Context, *cmds: list[str]) -> Callable[[], str]:
    def apply() -> str:
        out = []
        for cmd in cmds:
            done = ctx.run(cmd)
            if done.returncode != 0:
                raise RuntimeError(f"claude {' '.join(cmd[1:3])} lỗi {done.returncode}: {done.stderr.strip()}")
            out.append(done.stdout.strip())
        return "\n".join(o for o in out if o) or "đã ghi"
    return apply


def _claude_code(ctx: Context) -> list[Change]:
    changes = []
    uv, args = ctx.command
    claude = ctx.which("claude")
    if claude:
        add = [claude, "mcp", "add", "--scope", "user", SERVER, "--", uv, *args]
        got = ctx.run([claude, "mcp", "get", SERVER])
        if got.returncode != 0:
            changes.append(Change("Claude Code", "claude mcp (scope user)", f"thêm server {SERVER} bằng lệnh",
                                  subprocess.list2cmdline(add), _run_all(ctx, add)))
        elif (registered := _claude_registered(got.stdout)) is None:
            changes.append(Change("Claude Code", "claude mcp (scope user)",
                                  f"đã có server {SERVER} (muốn thay: claude mcp remove {SERVER} -s user, rồi chạy lại)"))
        elif registered == (os.path.normcase(os.path.normpath(uv)), " ".join(args)):  # claude in Args nối bằng dấu cách
            changes.append(Change("Claude Code", "claude mcp (scope user)", f"server {SERVER} đã đúng lệnh, bỏ qua"))
        else:
            remove = [claude, "mcp", "remove", SERVER, "-s", "user"]
            changes.append(Change("Claude Code", "claude mcp (scope user)", f"thay lệnh server {SERVER} (gỡ rồi thêm lại)",
                                  f"{subprocess.list2cmdline(remove)}\n{subprocess.list2cmdline(add)}",
                                  _run_all(ctx, remove, add)))
    if (ctx.home / ".claude").is_dir():
        path = ctx.home / ".claude" / "skills" / "contextcut-editor" / "SKILL.md"
        new = agent_docs.render_skill()
        old = path.read_text(encoding="utf-8") if path.is_file() else ""
        if old == new:
            changes.append(Change("Claude Code", str(path), "skill contextcut-editor đã mới nhất, bỏ qua"))
        else:
            summary = "cập nhật skill contextcut-editor" if old else "cài skill contextcut-editor (sinh từ guide)"
            preview = _diff(old, new, path.name) if old else f"(file mới, {len(new.splitlines())} dòng: {agent_docs.SKILL_PATH})"
            changes.append(Change("Claude Code", str(path), summary, preview, _write_file(path, new)))
    return changes


def _claude_desktop(ctx: Context) -> list[Change]:
    local = ctx.path("LOCALAPPDATA")
    candidates = _first_existing([ctx.path("APPDATA", "Claude", "claude_desktop_config.json")])
    candidates += _glob(local / "Claude-Data" if local else None, "*/claude_desktop_config.json")  # bản MSIX dời dữ liệu
    candidates += _glob(local / "Packages" if local else None, "Claude_*/LocalCache/Roaming/Claude/claude_desktop_config.json")
    uv, args = ctx.command
    note = "Claude Desktop đang mở có thể ghi đè file này: thoát hẳn app trước khi ghi, mở lại sau khi ghi"
    return [_json_change("Claude Desktop", p, {"command": uv, "args": args}, note) for p in candidates]


def _codex(ctx: Context) -> list[Change]:
    home = Path(ctx.env["CODEX_HOME"]) if ctx.env.get("CODEX_HOME") else ctx.home / ".codex"
    if not home.is_dir() and not ctx.which("codex"):
        return []
    return [_codex_change(home / "config.toml", *ctx.command)]


def _antigravity(ctx: Context) -> list[Change]:
    gemini = ctx.home / ".gemini"
    paths = [gemini / "config" / "mcp_config.json", gemini / "antigravity" / "mcp_config.json"]
    found = _first_existing(paths)
    if not found:
        if (gemini / "config").is_dir():
            found = [paths[0]]
        elif (gemini / "antigravity").is_dir():
            found = [paths[1]]
    uv, args = ctx.command
    return [_json_change("Antigravity", p, {"command": uv, "args": args}) for p in found]


DETECTORS = {"claude-code": _claude_code, "claude-desktop": _claude_desktop, "codex": _codex,
             "antigravity": _antigravity}


def plan(ctx: Context, clients: list[str] | None = None) -> list[Change]:
    return [c for name in (clients or CLIENTS) for c in DETECTORS[name](ctx)]


def main(argv: list[str] | None = None, ask: Callable[[str], str] = input, ctx: Context | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="chỉ in thay đổi, không hỏi, không ghi")
    parser.add_argument("--client", action="append", choices=CLIENTS, help="chỉ xét client này (lặp được)")
    args = parser.parse_args(argv)
    ctx = ctx or Context()
    uv, uv_args = ctx.command
    print(f"Server {SERVER}: {subprocess.list2cmdline([uv, *uv_args])}")
    if not (PROJECT_DIR / ".venv").is_dir():
        print(f"Chưa có môi trường: chạy `uv sync --directory {PROJECT_DIR}` trước (server chạy --no-sync, không tự cài)")
    changes = plan(ctx, args.client)
    if not changes:
        print("Không thấy AI client nào (Claude Code, Claude Desktop, Codex, Antigravity).")
    for change in changes:
        print(f"\n== {change.client}: {change.target}\n{change.summary}")
        if change.preview:
            print(change.preview.rstrip("\n"))
        if change.apply is None or args.dry_run:
            continue
        try:
            answer = ask("Ghi thay đổi này? [y/N] ").strip().lower()
        except EOFError:
            answer = ""
        if answer not in ("y", "yes"):
            print("bỏ qua")
            continue
        print(change.apply())
    return 0


if __name__ == "__main__":
    sys.exit(main())
