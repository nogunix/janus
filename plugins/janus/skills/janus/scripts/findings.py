#!/usr/bin/env python3
"""Findings-file tooling: a mechanical format check and a fan-in digest.

    python3 findings.py lint   cases/<id>/findings/<stage>.md   (or cases/<id>)
    python3 findings.py digest cases/<id>

lint — the stage contract's mechanical half. A stage runs it on its own
file before SendMessage; the lead gets the same verdicts inside digest.
It proves only what the format can prove:

  FAIL  no YAML frontmatter; a missing `stage` / `case` / `date` /
        `status` / `model` key (`model: unrecorded` is the honest
        answer, never an omitted key); `status` outside
        complete | partial | failed; a finding with no Confidence, Basis
        or Ref, or a Confidence / Basis outside its vocabulary; a HIGH
        finding on an ASSUMED basis (a contradiction by definition); a
        finding number used twice in one file, or reused between a
        supplement and the parent named in its `supplement_of`.
  warn  no `tool_calls` / `duration_s`, a finding with no Detail or Type,
        no `## Gaps` section — absent is not wrong, but worth a look.

Whether a gap was honestly called a gap rather than a negative, or a
Basis was promoted without new evidence, is judgment; lint does not
pretend to check it.

digest — what the lead needs at fan-in, without reading every file in
full: per file, the frontmatter status line, one line per finding
(number, Confidence/Basis, title), the Gaps section verbatim (the
follow-up decision is made from it), and lint's verdicts. Synthesize
still reads the files in full; the digest is for routing, not for
writing the report.

Exit status: 1 if any FAIL, 2 on usage error, else 0. Stdlib-only.
"""

import re
import sys
from pathlib import Path

REQUIRED_KEYS = ("stage", "case", "date", "status", "model")
ADVISED_KEYS = ("tool_calls", "duration_s")
STATUSES = {"complete", "partial", "failed"}
CONFIDENCE = {"HIGH", "MEDIUM", "LOW"}
BASIS = {"VERIFIED", "REASONED", "ASSUMED"}

FINDING_RE = re.compile(r"^###\s+(F\d+[a-z]?)\s*:\s*(.*)$")
FIELD_RE = re.compile(r"^\s*-\s+\*\*(Confidence|Basis|Type|Detail|Ref)\*\*\s*:\s*(.*)$")
SECTION_RE = re.compile(r"^##\s+(.*?)\s*$")


def parse_frontmatter(lines):
    """(dict, index of the first body line) — ({}, 0) when absent."""
    if not lines or lines[0].strip() != "---":
        return {}, 0
    meta = {}
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return meta, i + 1
        m = re.match(r"^([A-Za-z_][\w-]*)\s*:\s*(.*)$", line)
        if m:
            meta[m.group(1)] = m.group(2).split(" #")[0].strip().strip("'\"")
    return {}, 0


def parse(path):
    """Returns (meta, findings, sections). findings: list of dicts with
    id, title, line and the bold fields; sections: {heading: [lines]}."""
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    meta, start = parse_frontmatter(lines)
    findings, sections = [], {}
    current, section = None, None
    in_fence = False
    for n, line in enumerate(lines[start:], start=start + 1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        if in_fence:
            if section is not None:
                sections[section].append(line)
            continue
        m = FINDING_RE.match(line)
        if m:
            current = {"id": m.group(1), "title": m.group(2).strip(), "line": n}
            findings.append(current)
            continue
        m = SECTION_RE.match(line)
        if m:
            current = None
            section = m.group(1)
            sections[section] = []
            continue
        if section is not None:
            sections[section].append(line)
        if current is not None:
            f = FIELD_RE.match(line)
            if f and f.group(1) not in current:
                current[f.group(1)] = f.group(2).strip()
    return meta, findings, sections


def first_word(value):
    m = re.match(r"[`*_]*([A-Za-z]+)", value or "")
    return m.group(1).upper() if m else ""


def lint_file(path, case_findings=None):
    """Returns (problems, warnings) for one findings file. case_findings
    maps file name → set of finding ids, for the supplement check."""
    problems, warnings = [], []
    name = Path(path).name
    meta, findings, sections = parse(path)

    if not meta:
        problems.append(f"{name}: no YAML frontmatter")
    else:
        for key in REQUIRED_KEYS:
            if not meta.get(key):
                hint = " (write `model: unrecorded` if unknown)" if key == "model" else ""
                problems.append(f"{name}: frontmatter has no `{key}`{hint}")
        status = meta.get("status")
        if status and status not in STATUSES:
            problems.append(f"{name}: status `{status}` is not complete | partial | failed")
        for key in ADVISED_KEYS:
            if key not in meta:
                warnings.append(f"{name}: frontmatter has no `{key}`")

    seen = set()
    for f in findings:
        where = f"{name}:{f['line']} {f['id']}"
        if f["id"] in seen:
            problems.append(f"{where}: finding number used twice in this file")
        seen.add(f["id"])
        conf, basis = first_word(f.get("Confidence")), first_word(f.get("Basis"))
        if "Confidence" not in f:
            problems.append(f"{where}: no Confidence")
        elif conf not in CONFIDENCE:
            problems.append(f"{where}: Confidence `{f['Confidence']}` is not HIGH | MEDIUM | LOW")
        if "Basis" not in f:
            problems.append(f"{where}: no Basis")
        elif basis not in BASIS:
            problems.append(f"{where}: Basis `{f['Basis']}` is not VERIFIED | REASONED | ASSUMED")
        if conf == "HIGH" and basis == "ASSUMED":
            problems.append(f"{where}: HIGH confidence on an ASSUMED basis")
        if not f.get("Ref"):
            problems.append(f"{where}: no Ref")
        for field in ("Detail", "Type"):
            if field not in f:
                warnings.append(f"{where}: no {field}")

    if "Gaps" not in sections:
        warnings.append(f"{name}: no `## Gaps` section")

    parent = meta.get("supplement_of")
    if parent and case_findings is not None and parent in case_findings:
        clash = sorted(seen & case_findings[parent], key=lambda s: int(re.sub(r"\D", "", s)))
        if clash:
            problems.append(
                f"{name}: reuses {', '.join(clash)} from its parent {parent} — "
                "supplements take a fresh block of 10"
            )
    return problems, warnings


def findings_files(target):
    target = Path(target)
    if target.is_file():
        return [target]
    directory = target / "findings" if (target / "findings").is_dir() else target
    return sorted(directory.glob("*.md"))


def case_ids(files):
    return {f.name: {x["id"] for x in parse(f)[1]} for f in files}


def cmd_lint(target):
    files = findings_files(target)
    if not files:
        print(f"error: no findings files at {target}")
        return 2
    siblings = findings_files(Path(files[0]).parent) if len(files) == 1 else files
    ids = case_ids(siblings)
    failed = False
    for f in files:
        problems, warnings = lint_file(f, ids)
        for w in warnings:
            print(f"warning: {w}")
        for p in problems:
            print(f"FAIL: {p}")
        failed = failed or bool(problems)
        if not problems:
            print(f"OK: {f.name} passes the findings format")
    return 1 if failed else 0


def cmd_digest(case_dir):
    files = findings_files(case_dir)
    if not files:
        print(f"no findings files under {case_dir}")
        return 0
    ids = case_ids(files)
    failed = False
    for f in files:
        meta, findings, sections = parse(f)
        head = [f"status={meta.get('status', '?')}", f"model={meta.get('model', '?')}"]
        for key in ("tool_calls", "supplement_of", "source"):
            if key in meta:
                head.append(f"{key}={meta[key]}")
        print(f"== {f.name}  {' '.join(head)}")
        for x in findings:
            conf = first_word(x.get("Confidence")) or "?"
            basis = first_word(x.get("Basis")) or "?"
            print(f"  {x['id']} [{conf}/{basis}] {x['title']}")
        gaps = [l for l in sections.get("Gaps", []) if l.strip()]
        print("  Gaps:" if gaps else "  Gaps: (none)")
        for line in gaps:
            print(f"    {line.strip()}")
        problems, warnings = lint_file(f, ids)
        for p in problems:
            print(f"  lint FAIL: {p}")
        for w in warnings:
            print(f"  lint warning: {w}")
        failed = failed or bool(problems)
    return 1 if failed else 0


def main(argv):
    if len(argv) != 3 or argv[1] not in ("lint", "digest"):
        print("usage: findings.py lint <findings.md | cases/<id>>\n"
              "       findings.py digest cases/<id>")
        return 2
    target = Path(argv[2])
    if not target.exists():
        print(f"error: no such path: {target}")
        return 2
    return cmd_lint(target) if argv[1] == "lint" else cmd_digest(target)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
