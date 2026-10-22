#!/bin/bash
# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
# Run a fresh Claude Code session (claude -p) with only the ContextCut MCP server, as a gate test from inside another
# Claude Code session. usage: agent_run.sh <prompt-file> <out.jsonl> [model]
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
OUT_DIR="$(cd "$(dirname "$2")" && pwd)"
cat > "$OUT_DIR/mcp-gate.json" <<EOF
{"mcpServers": {"contextcut": {"command": "uv", "args": ["--directory", "$(cygpath -m "$REPO/contextcut-ai")", "run", "--no-sync", "contextcut-ai"]}}}
EOF
# The parent session's CLAUDE*/ANTHROPIC_* variables would make the child talk to the parent instead of signing in
for v in $(env | grep -E '^(CLAUDE|ANTHROPIC)[A-Z_]*=' | cut -d= -f1); do unset "$v"; done
export MSYS_NO_PATHCONV=1
cd "$OUT_DIR" || exit 1
claude -p "$(cat "$1")" --mcp-config "$(cygpath -m "$OUT_DIR/mcp-gate.json")" --strict-mcp-config   --allowedTools "mcp__contextcut" --model "${3:-sonnet}" --output-format stream-json --verbose > "$2" 2>&1
echo "exit $?"
