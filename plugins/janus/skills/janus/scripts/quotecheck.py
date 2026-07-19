#!/usr/bin/env python3
"""Verbatim-quote fidelity check for the report (backs gate G7-QUOTE).

The telephone-game failure: the findings survive intact on disk while
the fact mutates as synthesize copies it into the report — "reproduced"
softens into "may reproduce", a version number drifts. A hash ledger
cannot see that (the report is a legitimately new file), so the
report's load-bearing facts are quoted verbatim and checked
mechanically against the findings they cite.

Contract (synthesize writes it, this script checks it): a quote is a
markdown blockquote whose last line attributes a case-relative
evidence file —

    > VM live migration fails on OCP 4.18.41 with SIGSEGV in qemu-kvm
    > — findings/crash-analyze.md

Whitespace-normalized, the quoted text must appear verbatim in the
cited file. A mismatch is a mutated fact; an attribution to a missing
file is a fabricated citation; both FAIL (exit 1) → send back under
G7-QUOTE. A report with no attributed quotes gets a warning, not a
FAIL — whether quotes were required is the content gates' call.

Usage: python3 quotecheck.py cases/<id>/results/report.md
Stdlib-only, offline, like chain.py.
"""

import re
import sys
from pathlib import Path

ATTRIBUTION = re.compile(
    r"^>\s*[—–-]{1,2}\s*`?\(?(?P<src>(?:findings|audit)/[^\s)`]+)\)?`?\s*$"
)


def _normalize(text):
    return " ".join(text.split())


def extract_quotes(text):
    """Returns (src, quoted_text, line_no) per attributed blockquote."""
    quotes = []
    block, start = [], 0
    for i, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith(">"):
            if not block:
                start = i
            block.append(line.lstrip())
            continue
        if block:
            quotes.extend(_from_block(block, start))
            block = []
    if block:
        quotes.extend(_from_block(block, start))
    return quotes


def _from_block(block, start):
    m = ATTRIBUTION.match(block[-1])
    if not m:
        return []  # a plain blockquote, not an evidence quote
    body = _normalize(" ".join(line.lstrip(">").strip() for line in block[:-1]))
    return [(m.group("src"), body, start)]


def run(report_path):
    """Returns (problems, warnings, ok_count)."""
    report_path = Path(report_path).resolve()
    case_dir = (
        report_path.parent.parent
        if report_path.parent.name == "results"
        else report_path.parent
    )
    problems, warnings, ok = [], [], 0
    quotes = extract_quotes(report_path.read_text(encoding="utf-8"))
    if not quotes:
        warnings.append(
            "no attributed quotes found — evidence-backed claims should "
            "quote their finding verbatim (> …\\n> — findings/<stage>.md)"
        )
        return problems, warnings, ok
    sources = {}
    for src, body, line_no in quotes:
        where = f"{report_path.name}:{line_no}"
        if not body:
            problems.append(f"{where}: empty quote attributed to {src}")
            continue
        if src not in sources:
            src_path = case_dir / src
            sources[src] = (
                _normalize(src_path.read_text(encoding="utf-8"))
                if src_path.is_file()
                else None
            )
        if sources[src] is None:
            problems.append(f"{where}: attributed file does not exist: {src}")
        elif body in sources[src]:
            ok += 1
        else:
            problems.append(
                f'{where}: quote not found verbatim in {src}: "{body[:80]}…"'
                if len(body) > 80
                else f'{where}: quote not found verbatim in {src}: "{body}"'
            )
    return problems, warnings, ok


def main(argv):
    if len(argv) != 2:
        print("usage: quotecheck.py cases/<id>/results/report.md")
        return 2
    report = Path(argv[1])
    if not report.is_file():
        print(f"error: no such file: {report}")
        return 2
    problems, warnings, ok = run(report)
    for w in warnings:
        print(f"warning: {w}")
    for p in problems:
        print(f"FAIL: {p}")
    if problems:
        print(
            f"{len(problems)} quote(s) diverge from the findings they cite — "
            "send back to synthesize under G7-QUOTE"
        )
        return 1
    if ok:
        print(f"OK: {ok}/{ok} quotes verbatim in their cited findings")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
