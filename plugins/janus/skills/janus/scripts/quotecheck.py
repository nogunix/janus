#!/usr/bin/env python3
"""Verbatim-quote fidelity check for the report (backs gate C2/quote).

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

The attribution may also be a markdown link, so a reader can click
through to the evidence (see linkcheck.py):

    > VM live migration fails on OCP 4.18.41 with SIGSEGV in qemu-kvm
    > — [F3](../findings/crash-analyze.md#f3-vm-live-migration-fails)

Both forms are accepted. In the linked form the *target* identifies the
source file — the link text is free-form ("F3", a stage name, anything)
and any `#fragment` is dropped, since it selects a place within the file
rather than a different source.

Whitespace-normalized, the quoted text must appear verbatim in the
cited file. A mismatch is a mutated fact; an attribution to a missing
file is a fabricated citation; both FAIL (exit 1) → send back under
C2/quote-mismatch. A report with no attributed quotes gets a warning,
not a FAIL (that residue is the lead's C2/quote-absent judgment call).

Usage: python3 quotecheck.py cases/<id>/results/report.md
Stdlib-only, offline, like chain.py.
"""

import re
import sys
from pathlib import Path

ATTRIBUTION = re.compile(
    r"^>\s*[—–-]{1,2}\s*"
    r"(?:"
    r"\[[^\]]*\]\(\s*(?P<link>[^)\s]+?)\s*\)"  # > — [F3](../findings/x.md#f3)
    r"|`?\(?(?P<plain>(?:findings|audit)/[^\s)`]+?)\)?`?"  # > — findings/x.md
    r")\s*$"
)


def _normalize(text):
    return " ".join(text.split())


def source_path(raw, report_path, case_dir):
    """Resolve an attribution target to a case-relative evidence path.

    Accepts both the case-relative plain form (`findings/x.md`) and a
    link target relative to the report (`../findings/x.md#anchor`). Any
    fragment is dropped — it selects a place *within* the file, not a
    different source. Returns None for a target that escapes the case
    directory or does not name evidence."""
    raw = raw.split("#", 1)[0].strip()
    if not raw:
        return None
    if raw.startswith(("findings/", "audit/")):
        candidate = case_dir / raw
    else:
        candidate = report_path.parent / raw
    try:
        rel = candidate.resolve().relative_to(case_dir.resolve())
    except ValueError:
        return None  # points outside the case — never valid evidence
    return rel.as_posix() if rel.parts and rel.parts[0] in ("findings", "audit") else None


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
    return [(m.group("link") or m.group("plain"), body, start)]


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
    for raw, body, line_no in quotes:
        where = f"{report_path.name}:{line_no}"
        src = source_path(raw, report_path, case_dir)
        if src is None:
            problems.append(
                f"{where}: attribution does not point at case evidence: {raw}"
            )
            continue
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
            "send back to synthesize under C2/quote-mismatch"
        )
        return 1
    if ok:
        print(f"OK: {ok}/{ok} quotes verbatim in their cited findings")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
