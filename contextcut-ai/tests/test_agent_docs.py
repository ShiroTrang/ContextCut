# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
from contextcut_ai import agent_docs, guide


def test_generated_files_up_to_date():
    stale = agent_docs.write_all(check=True)
    assert stale == [], "chạy: uv run --directory contextcut-ai python scripts/gen_agent_docs.py"


def test_skill_front_matter():
    skill = agent_docs.render_skill()
    head, _, body = skill.removeprefix("---\n").partition("\n---\n")
    meta = dict(line.split(": ", 1) for line in head.splitlines())
    assert meta["name"] == "contextcut-editor"
    assert "ContextCut" in meta["description"] and len(meta["description"]) <= 1024
    assert guide.instructions() in body
    assert "\n## Quy trình dựng\n" in body  # heading của topic hạ một cấp dưới "# ContextCut editor"
    assert "\n# Quy trình dựng\n" not in body
    assert "patterns/irony-cut" in body


def test_snippet_markers():
    snippet = agent_docs.render_agents_snippet()
    assert snippet.startswith("<!-- contextcut-guide:begin")
    assert snippet.rstrip().endswith("<!-- contextcut-guide:end -->")
    assert guide.instructions() in snippet
    assert "Nhân trước, quả sau" in snippet  # quy tắc cắt/chuyển POV luôn nằm trong AGENTS.md
    for t in guide.load_topics():
        assert f"- {t.name}:" in snippet
