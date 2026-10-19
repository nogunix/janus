#!/usr/bin/env python3
"""The send-back ledger: what was sent back, how often, and when to stop.

An agent author and an agent reviewer can keep each other busy
indefinitely. The lead reads the report, names a sub-code, synthesize
revises, the lead reads again and finds the next thing. Each round looks
locally reasonable and the loop has no natural end — the Claude Code
team measured one pull request through fifty rounds overnight, and found
that most of what later rounds flagged had been there since the first
pass. Rounds are not free: every one of them is a full re-read on both
sides while the case sits unfinished.

JANUS already had half a brake — *the same sub-code twice is a
NEEDS_HUMAN* — and it leaked in two ways. Distinct sub-codes could cycle
forever (`C1/url`, then `C2/quote-mismatch`, then `C1/basis`, each
failing exactly once), and the rule lived in the lead's memory, which a
session restart or a context compaction erases. A ledger on disk fixes
both: it survives the lead, and it can count.

    python3 sendback.py record cases/<id> C1/url C2/quote-mismatch
    python3 sendback.py status cases/<id>

`record` appends one round to `cases/<id>/audit/sendbacks.jsonl`, seals
it into the evidence chain, and prints the verdict. `status` re-prints
the verdict without recording — what to run after a restart, instead of
guessing which round you are on.

The verdict, and the exit code with it:

  OK          exit 0 — targeted revision, name the sub-codes and the
              offending lines
  RECONSIDER  exit 0 — the last allowed round. Ask synthesize to step
              back and reconsider how the report is built rather than
              patch the quoted lines; patching is what got here
  ESCALATE    exit 1 — stop the loop and write
              review-queue/NEEDS_HUMAN_<id>.md. Either a sub-code has
              now failed twice (the revision did not take, and a third
              attempt at the same defect is not better odds) or the
              round cap is spent

Sub-codes are validated against the gate vocabulary: a typo would read
as a new defect and defeat the repeat check, which is the one thing this
file exists to do.

Stdlib-only, offline, like chain.py.
"""

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
LEDGER = "audit/sendbacks.jsonl"
ROUND_CAP = 3

# The send-back vocabulary from SKILL.md step 7. Kept as a flat set so a
# new sub-code is one edit here and one in the gate table.
SUB_CODES = {
    "C1/ref", "C1/url", "C1/link", "C1/basis", "C1/spec", "C1/currency",
    "C1/source-of-truth",
    "C2/section", "C2/artifact", "C2/quote-absent", "C2/quote-mismatch",
    "C2/version", "C2/prose",
}


def read(case_dir):
    """The rounds recorded so far, oldest first."""
    path = Path(case_dir) / LEDGER
    if not path.is_file():
        return []
    rounds = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rounds.append(json.loads(line))
        except json.JSONDecodeError:
            rounds.append({"round": len(rounds) + 1, "codes": [], "malformed": line})
    return rounds


def repeated(rounds):
    """{sub-code: [round numbers]} for every code sent back more than once."""
    seen = {}
    for entry in rounds:
        for code in entry.get("codes", []):
            seen.setdefault(code, []).append(entry.get("round"))
    return {code: at for code, at in seen.items() if len(at) > 1}


def verdict(rounds):
    """(status, [lines]) — the whole decision, from the ledger alone."""
    n = len(rounds)
    again = repeated(rounds)
    lines = []
    if again:
        for code, at in sorted(again.items()):
            lines.append(
                f"{code} sent back in rounds {', '.join(str(r) for r in at)} — "
                "the revision did not take"
            )
        lines.append(
            "stop the loop: write review-queue/NEEDS_HUMAN_<id>.md noting both "
            "versions"
        )
        return "ESCALATE", lines
    if n > ROUND_CAP:
        lines.append(
            f"{n} rounds, cap is {ROUND_CAP} — stop the loop: write "
            "review-queue/NEEDS_HUMAN_<id>.md"
        )
        return "ESCALATE", lines
    if n == ROUND_CAP:
        lines.append(
            f"round {n} of {ROUND_CAP} — the last one. Do not send another "
            "list of lines to patch: ask synthesize to step back and "
            "reconsider how the report is built, since patching is what got "
            "here. If it comes back still failing, that is NEEDS_HUMAN"
        )
        return "RECONSIDER", lines
    lines.append(f"round {n} of {ROUND_CAP} — targeted revision")
    return "OK", lines


def _seal(case_dir, path):
    """Seal the ledger so step 7's chain verify does not read it as an
    unsealed write. A chain problem must never block recording, so this
    reports and moves on."""
    try:
        spec = importlib.util.spec_from_file_location("chain", HERE / "chain.py")
        chain = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(chain)
        chain.seal(case_dir, [path])
        return None
    except Exception as exc:  # noqa: BLE001 — recording outranks sealing
        return f"note: could not seal the ledger ({exc}); run chain.py seal"


def record(case_dir, codes):
    case_dir = Path(case_dir)
    unknown = [c for c in codes if c not in SUB_CODES]
    if unknown:
        print(f"error: not a gate sub-code: {', '.join(unknown)}")
        print(f"       known: {', '.join(sorted(SUB_CODES))}")
        return 2
    audit = case_dir / "audit"
    if not audit.is_dir():
        audit.mkdir(parents=True)
    rounds = read(case_dir)
    entry = {
        "round": len(rounds) + 1,
        "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "codes": list(dict.fromkeys(codes)),
    }
    path = case_dir / LEDGER
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    note = _seal(case_dir, path)
    print(f"recorded round {entry['round']}: {', '.join(entry['codes'])}")
    if note:
        print(note)
    return report(case_dir)


def report(case_dir):
    rounds = read(case_dir)
    if not rounds:
        print("OK: no send-backs recorded — this is the first read of the report")
        return 0
    for entry in rounds:
        codes = ", ".join(entry.get("codes", [])) or "(no codes recorded)"
        print(f"  round {entry.get('round')}  {entry.get('at', '')}  {codes}")
    status, lines = verdict(rounds)
    for line in lines:
        print(f"{status}: {line}")
    return 1 if status == "ESCALATE" else 0


def main(argv):
    if len(argv) < 3 or argv[1] not in ("record", "status"):
        print("usage: sendback.py record cases/<id> <sub-code> [<sub-code> ...]\n"
              "       sendback.py status cases/<id>")
        return 2
    case_dir = Path(argv[2])
    if not case_dir.is_dir():
        print(f"error: no such case directory: {case_dir}")
        return 2
    if argv[1] == "status":
        return report(case_dir)
    if len(argv) < 4:
        print("error: record needs at least one sub-code")
        return 2
    return record(case_dir, argv[3:])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
