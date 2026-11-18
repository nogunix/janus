#!/usr/bin/env python3
"""Dynamic-track approval record check: lab work needs a file, not a memory.

lab-verify is the one stage that touches live infrastructure, and the
rule is that it runs only after the human approves
`review-queue/APPROVE_<id>.md`. Every prompt says so. What no check
asked was whether that file exists once the lab work is done. In
practice a case reached handoff with a full lab-verify findings file and
no approval file at all; the approval had probably been given in the
conversation, but nothing in the case could show it, and the record a
reviewer or auditor would look for was missing.

  FAIL  cases/<id>/findings/lab-verify.md exists and no
        review-queue/APPROVE_<id>.md (or APPROVE_<id>-<suffix>.md) does.
        Not a report defect synthesize can fix: the lead records what
        happened in audit/ and raises NEEDS_HUMAN_<id>.md.
  warn  approval files exist but none carries an approval marker
        (`APPROVED` or 承認済) — the file may be the request, never
        answered. The lead marks the title when the human approves.
  OK    no lab-verify findings (no dynamic stage ran), or an approval
        file with a marker.

review-queue/ is looked up next to cases/ (the repo root that holds
both). No fail-open path: the answer is computable from the tree.

Usage: python3 approvalcheck.py cases/<id>
Stdlib-only, offline, like chain.py.
"""

import re
import sys
from pathlib import Path

MARKER = re.compile(r"\bAPPROVED\b|承認済")


def approval_files(case_dir):
    case_dir = Path(case_dir).resolve()
    queue = case_dir.parent.parent / "review-queue"
    cid = case_dir.name
    if not queue.is_dir():
        return queue, []
    files = sorted(
        p for p in queue.glob(f"APPROVE_{cid}*.md")
        if p.name == f"APPROVE_{cid}.md" or p.name.startswith(f"APPROVE_{cid}-")
    )
    return queue, files


def run(case_dir):
    """Returns (problems, warnings, oks)."""
    case_dir = Path(case_dir).resolve()
    lab = case_dir / "findings" / "lab-verify.md"
    if not lab.is_file():
        return [], [], ["no lab-verify findings — no dynamic stage to approve"]
    queue, files = approval_files(case_dir)
    if not files:
        return [
            f"findings/lab-verify.md exists but {queue.name}/APPROVE_{case_dir.name}.md "
            "does not — lab work ran with no approval on record; record what was "
            "approved and when in audit/, and raise NEEDS_HUMAN"
        ], [], []
    marked = [p for p in files if MARKER.search(p.read_text(encoding="utf-8", errors="replace"))]
    if not marked:
        return [], [
            "approval file(s) carry no APPROVED / 承認済 marker — the request may "
            "never have been answered: " + ", ".join(p.name for p in files)
        ], []
    return [], [], ["approval on record: " + ", ".join(p.name for p in marked)]


def main(argv):
    if len(argv) != 2:
        print("usage: approvalcheck.py cases/<id>")
        return 2
    case_dir = Path(argv[1])
    if not case_dir.is_dir():
        print(f"error: no such case directory: {case_dir}")
        return 2
    problems, warnings, oks = run(case_dir)
    for w in warnings:
        print(f"warning: {w}")
    for p in problems:
        print(f"FAIL: {p}")
    if problems:
        return 1
    for o in oks:
        print(f"OK: {o}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
