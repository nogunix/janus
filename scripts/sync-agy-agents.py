#!/usr/bin/env python3
"""Generate Antigravity-compatible agent definitions under .agents/agents/.

plugins/janus/agents/*.md use Claude Code tool names (Read, Write, Edit, Bash,
Glob, Grep, SendMessage, mcp__*) and are validated for Claude Code by
scripts/validate.py. Antigravity (`agy`) resolves each entry in `tools:`
against its internal component registry and rejects Claude Code tool names.

This script reads plugins/janus/agents/*.md and writes Antigravity overrides
to .agents/agents/<name>.md and .agents/agents/<name>/agent.md (which are
gitignored via `/.agents/` in .gitignore), mapping `tools:` to Antigravity's
native component names and enabling `inheritMcp: true`. `model:` is
rewritten to `inherit`: the plugin pins light stages to the Claude family
alias `sonnet`, which Antigravity's model tiers do not resolve.

Usage:
    python3 scripts/sync-agy-agents.py
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "plugins" / "janus" / "agents"
OUT_DIR = REPO_ROOT / ".agents" / "agents"

AGY_TOOLS = (
    "[send_message, view_file, search_web, schedule, generate_image, "
    "multi_replace_file_content, replace_file_content, write_to_file, "
    "run_command, manage_task]"
)

AGY_TOOL_NOTE = """\
## Antigravity Tool Mapping (when running under Antigravity / agy)

When running inside Google Antigravity (`agy`), use the native Antigravity tool names:
- File reading: `read_file` / `view_file` (instead of `Read`)
- File writing/editing: `write_file` / `write_to_file` and `edit_file` / `replace_file_content` / `multi_replace_file_content` (instead of `Write` / `Edit`). **Always** use these file tools for tracked files under `cases/<id>/` so the PostToolUse evidence-chain hook seals every write.
- Shell commands: `run_command` (instead of `Bash`)
- Messaging: `send_message` (instead of `SendMessage`)
- MCP tools: All MCP servers are lazy-loaded. Read `~/.gemini/antigravity-cli/mcp/<serverName>/<toolName>.json` for a tool schema if needed, then call `call_mcp_tool(ServerName="<serverName>", ToolName="<toolName>", Arguments={...})`.
"""

FRONTMATTER_RE = re.compile(r"^---\n(.*?\n)---\n(.*)$", re.S)


def convert_agent_markdown(text: str) -> str:
    m = FRONTMATTER_RE.match(text)
    if not m:
        raise ValueError("Missing YAML frontmatter")
    fm, body = m.group(1), m.group(2)
    fm_new = re.sub(
        r"^tools:.*$",
        f"tools: {AGY_TOOLS}\ninheritMcp: true",
        fm,
        flags=re.M,
    )
    fm_new = re.sub(r"^model:.*$", "model: inherit", fm_new, flags=re.M)
    return f"---\n{fm_new}---\n\n{AGY_TOOL_NOTE}\n{body.lstrip()}"


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    count = 0
    for src in sorted(SRC_DIR.glob("*.md")):
        converted = convert_agent_markdown(src.read_text(encoding="utf-8"))
        (OUT_DIR / f"{src.stem}.md").write_text(converted, encoding="utf-8")
        sub_dir = OUT_DIR / src.stem
        sub_dir.mkdir(parents=True, exist_ok=True)
        (sub_dir / "agent.md").write_text(converted, encoding="utf-8")
        count += 1
    print(f"Synced {count} Antigravity agent definitions to {OUT_DIR.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
