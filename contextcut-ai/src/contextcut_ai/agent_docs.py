# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
"""Sinh `SKILL.md` (Claude Code/Desktop) và đoạn `AGENTS.md` (Codex, Antigravity) từ guide (design §10)."""

from __future__ import annotations

import re
from pathlib import Path

from . import guide

ROOT = Path(__file__).resolve().parents[2]  # contextcut-ai/
SKILL_PATH = ROOT / "skills" / "contextcut-editor" / "SKILL.md"
SNIPPET_PATH = ROOT / "skills" / "AGENTS-snippet.md"
SKILL_CORE = ["workflow", "editing-rules", "software"]
GENERATED = "Sinh từ contextcut-ai/guide/ bằng scripts/gen_agent_docs.py; sửa guide rồi chạy lại, đừng sửa tay."

SKILL_DESCRIPTION = (
    "Dựng video gaming trong ContextCut (fork Kdenlive) qua MCP server contextcut: đọc project và timeline đang "
    "mở, đề xuất dàn ý, quy tắc cắt và chuyển POV tự nhiên, chống lố. Use when the user asks to edit, cut, outline "
    "or review a video project open in ContextCut."
)


def demote(markdown: str) -> str:
    """Hạ mọi heading một cấp để topic nằm dưới heading của file đích."""
    return re.sub(r"^(#+) ", r"#\1 ", markdown, flags=re.MULTILINE)


def section(markdown: str, heading: str) -> str:
    """Một mục `## heading` của topic, tới mục `## ` kế tiếp."""
    match = re.search(rf"^## {re.escape(heading)}\n.*?(?=^## |\Z)", markdown, flags=re.MULTILINE | re.DOTALL)
    if match is None:
        raise KeyError(heading)
    return match.group(0).strip() + "\n"


def topic_list(exclude: list[str]) -> str:
    return "".join(f"- {t.name}: {t.title}. {t.summary}\n" for t in guide.load_topics() if t.name not in exclude)


def render_skill() -> str:
    parts = [f"---\nname: contextcut-editor\ndescription: {SKILL_DESCRIPTION}\n---\n",
             f"<!-- {GENERATED} -->\n",
             f"# ContextCut editor\n\n{guide.instructions()}\n"]
    parts += [demote(guide.find_topic(name).body) for name in SKILL_CORE]
    parts.append("## Topic khác\n\nĐọc khi cần bằng `get_guide(\"<topic>\")` hoặc resource "
                 "`contextcut://guide/<topic>`:\n\n" + topic_list(SKILL_CORE))
    return "\n".join(parts)


def render_agents_snippet() -> str:
    rules = demote(section(guide.find_topic("editing-rules").body, "Cắt và chuyển POV"))
    return "\n".join([
        f"<!-- contextcut-guide:begin ({GENERATED}) -->",
        "## ContextCut (MCP server `contextcut`)\n",
        guide.instructions() + "\n",
        rules,
        "### Hướng dẫn đầy đủ\n\nĐọc bằng `get_guide(\"<topic>\")` hoặc resource `contextcut://guide/<topic>`:\n",
        topic_list([]),
        "<!-- contextcut-guide:end -->\n",
    ])


def write_all(check: bool = False) -> list[Path]:
    """Ghi các file sinh ra; trả các file đã lệch so với guide. `check=True`: chỉ kiểm, không ghi."""
    stale = []
    for path, text in [(SKILL_PATH, render_skill()), (SNIPPET_PATH, render_agents_snippet())]:
        current = path.read_text(encoding="utf-8") if path.is_file() else None
        if current == text:
            continue
        stale.append(path)
        if not check:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
    return stale
