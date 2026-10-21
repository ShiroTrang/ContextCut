# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
"""Đăng ký MCP server contextcut cho Claude Code, Claude Desktop, Codex, Antigravity (hỏi y/N từng thay đổi).

    uv run --directory contextcut-ai python scripts/register_clients.py [--dry-run] [--client codex]
"""

import sys

from contextcut_ai.register import main

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
