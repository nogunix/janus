#!/usr/bin/env python3
"""PostToolUse hook: auto-seal case evidence writes into chain.jsonl.

Prompt-level discipline can be skimmed; this hook makes evidence
sealing mechanical (same rationale as secret-safety.py). Every
Write/Edit that lands in a case's evidence set (case.yaml,
findings/*.md, results/*.md, audit/*, verdict.md) is appended to that
case's `chain.jsonl` — an append-only, hash-linked ledger (see
skills/janus/scripts/chain.py) that makes post-hoc edits to evidence
detectable.

Fail-open by design: a sealing error must never block an
investigation, so every exception exits 0 silently. The lead's
`chain.py verify` at fan-in and handoff catches anything missed here.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent / "skills" / "janus" / "scripts")
)

WRITE_TOOLS = {
    "Write",
    "Edit",
    "MultiEdit",
    "NotebookEdit",
    "write_file",
    "write_to_file",
    "edit_file",
    "replace_file_content",
    "multi_replace_file_content",
    "notebook_edit",
}
TRACKED = re.compile(
    r"^(?P<case>.*/cases/[^/]+)/"
    r"(?:case\.yaml|verdict\.md|(?:findings|results)/[^/]+\.md|audit/[^/]+)$"
)


def parse_event(data):
    """Extract (is_antigravity, tool_name, tool_input) from a hook payload."""
    if "toolCall" in data:
        tc = data.get("toolCall") or {}
        return True, tc.get("name", ""), tc.get("args") or {}
    return False, data.get("tool_name", ""), data.get("tool_input") or {}


def main():
    try:
        data = json.load(sys.stdin)
        _, tool_name, tool_input = parse_event(data)
        if tool_name not in WRITE_TOOLS:
            return
        file_path = (
            tool_input.get("file_path")
            or tool_input.get("notebook_path")
            or tool_input.get("Path")
            or tool_input.get("TargetFile")
        )
        if not file_path:
            return
        match = TRACKED.match(str(Path(file_path).resolve()))
        if not match:
            return
        import chain

        chain.seal(match.group("case"), [file_path], actor="hook")
    except Exception:
        pass
    finally:
        sys.exit(0)


if __name__ == "__main__":
    main()
