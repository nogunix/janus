#!/usr/bin/env python3
"""PreToolUse hook: refuse to write over evidence that already drifted.

The evidence chain seals on every tracked write. That is what makes it
tamper-evident, and it is also the hole: an untracked write (a shell
redirect, `sed`, a python heredoc) leaves the file out of step with its
seal, and then the *next* tracked write re-seals the drifted content as
though it were legitimate. `chain.py verify` goes back to reporting
intact, and the window closes behind itself.

JANUS-024 hit this twice. The first shell write happened to be the last
write to that file, so `verify` caught it and the case stopped for a
human. The second was followed by dozens of `Edit` calls; `verify`
reported intact throughout, and the only reason anyone knew was that the
agent reported itself.

The asymmetry is the whole bug: whether an out-of-band write is ever
noticed depends on whether anything happens to be written afterwards.

So this hook checks the one moment at which the evidence still exists —
immediately before a tracked write, while the drifted content is still
on disk and the ledger still holds the pre-drift hash. If they disagree,
the write is denied rather than allowed to paper over the difference.

Scope: files the ledger has actually sealed. An unsealed file (a fresh
findings file, an `audit/` log written by Bash and not yet sealed) has
no recorded hash to compare against and is passed through untouched.

Fail-open by design, like the other hooks here: any error exits 0
silently. A guard that blocks real work when it malfunctions is worse
than the failure it guards against.
"""

import hashlib
import json
import re
import sys
from pathlib import Path

WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
CASE_FILE = re.compile(
    r"^(?P<case>.*/cases/[^/]+)/"
    r"(?:case\.yaml|verdict\.md|(?:findings|results)/[^/]+\.md|audit/[^/]+)$"
)


def _file_sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def _sealed_sha(case_dir, rel):
    """The most recent sha the ledger recorded for this file, or None."""
    ledger = case_dir / "chain.jsonl"
    if not ledger.is_file():
        return None
    sha = None
    for line in ledger.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            # A malformed ledger is chain.py verify's problem to report,
            # not this hook's to guess at.
            return None
        if rec.get("file") == rel:
            sha = rec.get("sha256")
    return sha


def drift_reason(tool_name, file_path):
    """The deny reason if this file drifted since its last seal, else None."""
    if tool_name not in WRITE_TOOLS or not file_path:
        return None
    path = Path(file_path).resolve()
    m = CASE_FILE.match(str(path))
    if not m or not path.is_file():
        return None
    case_dir = Path(m.group("case"))
    rel = str(path.relative_to(case_dir))
    sealed = _sealed_sha(case_dir, rel)
    if not sealed:
        return None
    if _file_sha(path) == sealed:
        return None
    return (
        f"Blocked: {rel} has changed since the evidence chain last sealed it, "
        "by something the chain did not observe — a shell redirect, `sed`, a "
        "heredoc or a script. Writing it now would re-seal the drifted "
        "content as legitimate and erase the only evidence that it drifted, "
        "which is exactly how an out-of-band write goes unnoticed.\n\n"
        "Do not retry this write. Report it to the lead, who runs "
        "`chain.py verify <case-dir>` to see the full picture and decides "
        "whether to accept and re-seal or to restore. If the out-of-band "
        "write was yours, say so plainly — a disclosed mistake is cheap and "
        "a concealed one corrupts the record."
    )


def main():
    try:
        data = json.load(sys.stdin)
        tool_input = data.get("tool_input", {})
        file_path = tool_input.get("file_path") or tool_input.get("notebook_path")
        reason = drift_reason(data.get("tool_name"), file_path)
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
