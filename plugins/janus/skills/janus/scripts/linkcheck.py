#!/usr/bin/env python3
"""Evidence-link resolution check for the report (backs gate C1/link).

The report is meant to be read by clicking: a claim in the prose links
straight to the finding that backs it, so a reviewer lands on the
evidence instead of grepping for it.

    H1 rests on [F3](../findings/crash-analyze.md#f3-sigsegv-in-qemu-kvm)
    and the [lab trace](../audit/lab-1.log).

That affordance creates a new way to lie. urlcheck.py only sees
`http(s)://`, so a relative link that points at a finding which does not
exist — or at an `#anchor` no heading produces — renders as a perfectly
ordinary blue link and resolves to nothing. That is the same failure
urlcheck exists to catch, one layer down, and it is *more* misleading
because a local link looks authoritative.

So every local link in the report must resolve:

  * the target file exists,
  * it lives inside the case directory (evidence, not the filesystem),
  * and any `#fragment` matches a heading in that file.

Unlike urlcheck.py this never fails open. Resolution is local,
deterministic and offline — there is no air-gapped case where the answer
is unknowable, so a broken link is always a real defect.

Anchors are matched the way GitHub and VS Code generate them from
headings (lowercase, punctuation dropped, spaces to hyphens, duplicates
suffixed `-1`, `-2`), plus any explicit `<a id="…">` / `<a name="…">`.

Usage: python3 linkcheck.py cases/<id>/results/report.md
Stdlib-only, offline, like chain.py.
"""

import re
import sys
from pathlib import Path

# [text](target) and ![alt](target); the target stops at whitespace so a
# `[x](path "title")` form keeps only the path.
LINK_RE = re.compile(r"!?\[(?P<text>[^\]]*)\]\(\s*(?P<target>[^)\s]+)")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
HEADING_RE = re.compile(r"^(#{1,6})\s+(?P<title>.+?)\s*#*\s*$")
EXPLICIT_ANCHOR_RE = re.compile(r"<a\s[^>]*\b(?:id|name)\s*=\s*[\"'](?P<id>[^\"']+)", re.I)
EXTERNAL_RE = re.compile(r"^(?:[a-z][a-z0-9+.-]*:|//)", re.I)


def slug(title):
    """GitHub's heading-anchor algorithm, close enough to be checkable."""
    s = title.strip().lower()
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE)
    s = re.sub(r"\s+", "-", s)
    return s.strip("-")


def strip_code(text):
    """Blank out fenced code blocks so example links are not checked."""
    out, in_fence = [], False
    for line in text.splitlines():
        if FENCE_RE.match(line):
            in_fence = not in_fence
            out.append("")
            continue
        out.append("" if in_fence else line)
    return "\n".join(out)


def anchors(text):
    """Every fragment the given markdown exposes."""
    found, seen = set(), {}
    for line in strip_code(text).splitlines():
        m = HEADING_RE.match(line)
        if m:
            base = slug(m.group("title"))
            if not base:
                continue
            n = seen.get(base, 0)
            seen[base] = n + 1
            found.add(base if n == 0 else f"{base}-{n}")
        for a in EXPLICIT_ANCHOR_RE.finditer(line):
            found.add(a.group("id"))
    return found


def extract_links(text):
    """Returns (target, line_no) for every non-external markdown link."""
    links = []
    for i, line in enumerate(strip_code(text).splitlines(), 1):
        for m in LINK_RE.finditer(line):
            target = m.group("target")
            if EXTERNAL_RE.match(target):
                continue  # urlcheck.py's job
            links.append((target, i))
    return links


def run(report_path):
    """Returns (problems, warnings, ok_count)."""
    report_path = Path(report_path).resolve()
    case_dir = (
        report_path.parent.parent
        if report_path.parent.name == "results"
        else report_path.parent
    )
    case_dir = case_dir.resolve()
    text = report_path.read_text(encoding="utf-8")

    problems, warnings, ok = [], [], 0
    links = extract_links(text)
    if not links:
        warnings.append(
            "no local evidence links — the report's claims cannot be "
            "clicked through to the findings that back them"
        )
        return problems, warnings, ok

    anchor_cache = {report_path: anchors(text)}
    for target, line_no in links:
        where = f"{report_path.name}:{line_no}"
        path_part, _, fragment = target.partition("#")

        if not path_part:  # same-file anchor, e.g. a table of contents
            if fragment and fragment not in anchor_cache[report_path]:
                problems.append(f"{where}: no such anchor in this report: #{fragment}")
            else:
                ok += 1
            continue

        candidate = (report_path.parent / path_part).resolve()
        try:
            rel = candidate.relative_to(case_dir)
        except ValueError:
            problems.append(
                f"{where}: link escapes the case directory: {target}"
            )
            continue
        if not candidate.is_file():
            problems.append(f"{where}: evidence file does not exist: {rel.as_posix()}")
            continue
        if not fragment:
            ok += 1
            continue
        if candidate not in anchor_cache:
            anchor_cache[candidate] = (
                anchors(candidate.read_text(encoding="utf-8", errors="replace"))
                if candidate.suffix.lower() in (".md", ".markdown")
                else set()
            )
        if candidate.suffix.lower() not in (".md", ".markdown"):
            # A fragment on a .log/.yaml is meaningless but harmless.
            warnings.append(f"{where}: fragment ignored on a non-markdown target: {target}")
            ok += 1
        elif fragment in anchor_cache[candidate]:
            ok += 1
        else:
            problems.append(
                f"{where}: no such anchor in {rel.as_posix()}: #{fragment}"
            )
    return problems, warnings, ok


def main(argv):
    if len(argv) != 2:
        print("usage: linkcheck.py cases/<id>/results/report.md")
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
            f"{len(problems)} evidence link(s) resolve to nothing — "
            "send back to synthesize under C1/link"
        )
        return 1
    if ok:
        print(f"OK: {ok}/{ok} evidence links resolve")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
