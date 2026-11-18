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
investigation, so every exception exits 0. But not silently any more:
a seal that failed for a tracked case file is appended to
`cases/<id>/chain-hook-errors.log` (outside the evidence set), and
`chain.py verify` warns while that file exists. A missed seal on a file
that was sealed before surfaces later as TAMPER, and without this record
the content check afterwards could only guess whether the hook or an
out-of-band write was responsible. (A hook killed by its timeout
runs no handler and still leaves no record.)
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


def _record_failure(case_dir, file_path, error):
    try:
        from datetime import datetime, timezone

        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with open(Path(case_dir) / "chain-hook-errors.log", "a", encoding="utf-8") as f:
            f.write(f"{ts} seal failed: {file_path}: {type(error).__name__}: {error}\n")
    except Exception:
        pass


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

        try:
            chain.seal(match.group("case"), [file_path], actor="hook")
        except Exception as e:
            _record_failure(match.group("case"), file_path, e)
    except Exception:
        pass
    finally:
        sys.exit(0)


if __name__ == "__main__":
    main()
