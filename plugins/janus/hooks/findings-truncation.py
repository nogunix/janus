#!/usr/bin/env python3
"""PreToolUse hook: deny a Write that would delete findings from a findings file.

`Write` replaces a file wholesale. A stage resumed for a later round
reads part of its own findings file, writes "its" findings, and silently
destroys every earlier round's — which is exactly what happened in
JANUS-024: a resumed iac-author wrote F160-F167 over a file that also
held F80-F89 and F140-F148, deleting 19 findings the report cited in 36
places.

Nothing caught it. `chain.py verify` reported **intact** the whole time,
because `Write` is a tracked tool and the PostToolUse hook dutifully
sealed the smaller file as a legitimate change. The evidence chain
proves a sealed file has not changed by means the chain cannot see; it
says nothing about whether the contents shrank. The loss surfaced only
because a downstream stage's `linkcheck` failed on the orphaned
citations.

So this hook closes the gap the chain structurally cannot: it compares
the `### F<N>` findings in the proposed payload against those already on
disk and denies any Write that drops one. Growing a file, reordering it,
or rewriting a finding's body are all allowed — only *losing* a finding
is refused.

Scope is deliberately narrow. `Edit` is untouched (it cannot truncate a
file it does not match), and so is the first write of a new file. Only
`Write` over an existing `findings/*.md` is examined.

Fail-open by design, like the other hooks here: any error exits 0
silently. A guard that blocks real work when it malfunctions is worse
than the failure mode it guards against.
"""

import json
import re
import sys
from pathlib import Path

FINDINGS_FILE = re.compile(r"^.*/cases/[^/]+/findings/[^/]+\.md$")
FINDING_ID = re.compile(r"^###\s+(F\d+)\s*:", re.M)


def lost_findings(file_path, content):
    """Finding IDs present on disk but absent from the proposed content."""
    path = Path(file_path).resolve()
    if not FINDINGS_FILE.match(str(path)) or not path.is_file():
        return []
    existing = FINDING_ID.findall(path.read_text(encoding="utf-8", errors="replace"))
    if not existing:
        return []
    proposed = set(FINDING_ID.findall(content or ""))
    # Order-preserving, so the message reads like the file does.
    return [fid for fid in existing if fid not in proposed]


def deny_reason(lost, file_path):
    name = Path(file_path).name
    shown = ", ".join(lost[:12]) + (" …" if len(lost) > 12 else "")
    return (
        f"Blocked: this Write would delete {len(lost)} finding(s) already in "
        f"{name} — {shown}. `Write` replaces the whole file, so a payload "
        "containing only the round you are working on destroys every earlier "
        "round's findings, which the report and the evidence chain both cite. "
        "The chain will NOT catch this: Write is a tracked tool, so the "
        "overwrite gets sealed as a legitimate change.\n\n"
        "Use `Edit` to append or amend in place. If you genuinely need a "
        "whole-file Write, build the payload from the file's *current* full "
        "contents (Read it first) so no finding is lost. If a finding really "
        "should be removed, that is the lead's call, not a side effect of a "
        "write."
    )


def main():
    try:
        data = json.load(sys.stdin)
        if data.get("tool_name") != "Write":
            return
        tool_input = data.get("tool_input", {})
        file_path = tool_input.get("file_path")
        if not file_path:
            return
        lost = lost_findings(file_path, tool_input.get("content", ""))
        if lost:
            json.dump(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": deny_reason(lost, file_path),
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
