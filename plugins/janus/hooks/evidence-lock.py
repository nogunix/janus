#!/usr/bin/env python3
"""PreToolUse hook: deny tracked writes to locked (read-only) case evidence.

`chain.py lock` drops the write bits on a case's fact base (case.yaml,
findings/*.md, audit/*) when the lead closes it at fan-in — from then
on the facts synthesize and the gates read are frozen. Without this
hook a Write/Edit against a locked file dies with a bare permission
error, which an agent may "fix" with chmod; the deny explains the
invariant instead. A legitimate revision goes through the lead:
`chain.py unlock`, edit, re-seal, `lock` again.

Fail-open by design (same rationale as evidence-chain.py): any error
exits 0 silently — the OS write bit still backs the invariant.
"""

import json
import re
import sys
from pathlib import Path

WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
TRACKED = re.compile(
    r"^(?P<case>.*/cases/[^/]+)/"
    r"(?:case\.yaml|verdict\.md|(?:findings|results)/[^/]+\.md|audit/[^/]+)$"
)


def locked_reason(tool_name, file_path):
    """The deny reason if this call writes a locked evidence file, else None."""
    if tool_name not in WRITE_TOOLS or not file_path:
        return None
    path = Path(file_path).resolve()
    if not TRACKED.match(str(path)) or not path.is_file():
        return None
    if path.stat().st_mode & 0o222:
        return None
    return (
        f"Blocked: {path.name} is locked case evidence (chain.py lock) — the "
        "fact base is frozen once the lead closes it at fan-in, so facts "
        "cannot mutate mid-collaboration. Do not chmod it writable. If a "
        "revision is genuinely needed, the lead runs `chain.py unlock`, the "
        "edit is made, then re-seal and `lock` again."
    )


def main():
    try:
        data = json.load(sys.stdin)
        tool_input = data.get("tool_input", {})
        file_path = tool_input.get("file_path") or tool_input.get("notebook_path")
        reason = locked_reason(data.get("tool_name"), file_path)
        if reason:
            json.dump(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": reason,
                    }
                },
                sys.stdout,
            )
    except Exception:
        pass
    finally:
        sys.exit(0)


if __name__ == "__main__":
    main()
