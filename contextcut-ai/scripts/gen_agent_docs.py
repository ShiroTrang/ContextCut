# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
"""Sinh skills/contextcut-editor/SKILL.md và skills/AGENTS-snippet.md từ guide/.

    uv run --directory contextcut-ai python scripts/gen_agent_docs.py [--check]
"""

import sys

from contextcut_ai.agent_docs import write_all


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    check = "--check" in sys.argv[1:]
    stale = write_all(check=check)
    for path in stale:
        print(("lệch: " if check else "đã ghi: ") + str(path))
    if not stale:
        print("SKILL.md và AGENTS-snippet.md khớp guide")
    return 1 if check and stale else 0


if __name__ == "__main__":
    sys.exit(main())
