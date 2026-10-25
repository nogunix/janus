#!/usr/bin/env python3
"""Report structure, recomputable metadata, and the hypothesis rank rule.

Backs gates C2/section, C1/basis and C1/ref — the three the lead
previously had to establish by reading. Each one is mechanical once you
notice that the report and the findings are both structured documents
with a shared vocabulary: a hypothesis cites `F3`, `F3` lives in a
findings file, and that file states its own Basis. Nothing here is a
judgment about whether a claim is *good* — only about whether the report
says something the findings do not support.

Three groups of checks.

**Structure (C2/section).** The template's sections exist for the mode
the case declares, the metadata tables carry every row, and no cell is
empty or still a `<placeholder>`.

**Recomputation (C2/section).** Execution Metadata and Stages Used state
numbers that can be derived from the findings — how many HIGH findings
there are, how many VERIFIED, which model ran each stage, how many
findings each stage produced. Derived numbers are checkable numbers, and
until now nothing checked them: a miscount in the one table a reader
uses to size up the investigation was invisible. `Review rounds` is
checked the same way, against `audit/sendbacks.jsonl`.

**The rank rule (C1/basis, C1/ref).** SKILL.md: a HIGH hypothesis needs
at least one VERIFIED finding, or two REASONED findings from different
stages; a hypothesis resting only on ASSUMED findings cannot rank above
LOW. The report cites findings by number, so both halves are decidable.
A cited number that no findings file defines is the sharper failure —
the report refers to evidence that does not exist.

  FAIL  a missing section or metadata row; an empty or placeholder cell;
        a stated count that disagrees with the findings; a `model:` the
        findings do not record; a Stages Used row contradicting a
        stage's own status; an Objectives Assessment status outside its
        vocabulary; a hypothesis whose confidence its cited bases do not
        support; a cited finding number that does not exist.
  warn  a hypothesis citing no finding at all; a finding no section of
        the report cites; a supplement the metadata does not name.

Fail direction: closed on everything it can prove from the files in
hand, warn where absence is mechanically indistinguishable from a
legitimate choice. There is no fail-open path — like linkcheck.py, every
input is local.

Usage: python3 reportlint.py cases/<id> [report.md]
The report defaults to `results/synthesis.md`; synthesize passes
`results/synthesis-en.md` when it checks its own draft on a ja case.
Stdlib-only, offline, like chain.py.
"""

import importlib.util
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Sections every report carries, in both modes. Matched case-insensitively
# as a substring so `## 2. Hypotheses` counts.
COMMON_SECTIONS = (
    "Execution Metadata",
    "Objectives Assessment",
    "Executive Summary",
    "Hypotheses",
    "Investigation Gaps",
    "References",
    "Stages Used",
)
ARTIFACT_SECTIONS = ("Affected Artifacts",)
# Execution Metadata's rows — the template's full set.
METRICS = (
    "stages completed",
    "stages failed/skipped",
    "models used",
    "total findings",
    "evidence basis",
    "review rounds",
    "gaps",
)
OBJECTIVE_STATUSES = ("achieved", "partial", "not achieved")
CONFIDENCE = ("HIGH", "MEDIUM", "LOW")

HEADING_RE = re.compile(r"^(#{1,6})\s+(?P<title>.+?)\s*#*\s*$")
HYPOTHESIS_RE = re.compile(r"^#{2,4}\s+(?P<id>H\d+[a-z]?)\s*[:.\-—]\s*(?P<title>.*)$")
FINDING_REF_RE = re.compile(r"\bF\d+[a-z]?\b")
# A citation that names its file: a link to the finding's anchor
# (`](../findings/doc-search.md#f4-…)`), or a stage/file name directly in
# front of the number (`jira-trace F1`). Stages each number from F1, so a
# bare `F1` is only resolvable when one file defines it.
LINK_CITE_RE = re.compile(
    r"\]\((?:[^)#\s]*/)?findings/(?P<stem>[^/)#\s]+)\.md#(?P<id>f\d+[a-z]?)(?=[-)])",
    re.I,
)
NAMED_CITE_RE = re.compile(r"(?<![\w-])(?P<who>[a-z][a-z0-9-]*)\s+(?P<id>F\d+[a-z]?)\b")
CONFIDENCE_RE = re.compile(r"Confidence\s*[:：]?\s*\**\s*(HIGH|MEDIUM|LOW)\b", re.I)
SEP_RE = re.compile(r"^\s*\|[\s:|-]+\|\s*$")
ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
PLACEHOLDER_RE = re.compile(r"^<[^>]*>$|^\.\.\.$|^…$")
COUNT_RE = r"{}\s*[:=]\s*(\d+)"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def strip_code(text):
    """Blank fenced blocks, keeping line numbers intact."""
    out, in_fence = [], False
    for line in text.splitlines():
        if re.match(r"^\s*(```|~~~)", line):
            in_fence = not in_fence
            out.append("")
            continue
        out.append("" if in_fence else line)
    return out


def sections(lines):
    """{normalized heading: (title, start, end)} for level-2 headings,
    plus the implicit lead-in section before the first one."""
    found, order = {}, []
    for i, line in enumerate(lines):
        m = HEADING_RE.match(line)
        if m and len(m.group(1)) == 2:
            order.append((m.group("title").strip(), i))
    bounds = {}
    for n, (title, start) in enumerate(order):
        end = order[n + 1][1] if n + 1 < len(order) else len(lines)
        bounds[title.lower()] = (title, start, end)
    found.update(bounds)
    found["__head__"] = ("", 0, order[0][1] if order else len(lines))
    return found


def find_section(secs, phrase):
    """The section whose heading contains `phrase`, or None."""
    needle = phrase.lower()
    for key, value in secs.items():
        if key != "__head__" and needle in key:
            return value
    return None


def tables(lines, start=0, end=None):
    """[(header_cells, [(row_cells, line_no)])] in the given line range."""
    end = len(lines) if end is None else end
    out, i = [], start
    while i < end - 1:
        if ROW_RE.match(lines[i]) and SEP_RE.match(lines[i + 1]):
            header, rows, j = cells(lines[i]), [], i + 2
            while j < end and ROW_RE.match(lines[j]):
                rows.append((cells(lines[j]), j + 1))
                j += 1
            out.append((header, rows))
            i = j
            continue
        i += 1
    return out


def norm(text):
    """Key form: lowercase, whitespace and emphasis removed — so
    `Stages failed / skipped` and `Stages failed/skipped` are one row."""
    return re.sub(r"[\s*`]+", "", text.lower())


def keyed(table):
    """A two-column table as {normalized key: (value, line_no)}."""
    return {
        norm(row[0]): (row[1] if len(row) > 1 else "", line)
        for row, line in table[1]
    }


# --- findings side --------------------------------------------------------

def load_findings(case_dir):
    """{(file stem, finding id): {stage, basis, confidence, file}} plus
    per-file metadata. Keyed by file as well as id: every stage numbers
    from F1, so the id alone collides as soon as two stages ran."""
    fnd = _load("findings")
    index, files = {}, []
    for path in sorted((case_dir / "findings").glob("*.md")):
        meta, found, _ = fnd.parse(path)
        stage = meta.get("stage") or path.stem
        files.append(
            {
                "path": path,
                "name": path.name,
                "stem": path.stem,
                "stage": stage,
                "status": meta.get("status", ""),
                "model": meta.get("model") or "unrecorded",
                "supplement": bool(meta.get("supplement_of")),
                "count": len(found),
            }
        )
        for f in found:
            index[(path.stem, f["id"])] = {
                "id": f["id"],
                "stage": stage,
                "file": path.name,
                "basis": fnd.first_word(f.get("Basis")),
                "confidence": fnd.first_word(f.get("Confidence")),
            }
    return index, files


def resolve_citations(text, index):
    """Returns (keys, unknown, ambiguous) for the finding citations in
    text. keys: resolved (stem, id) pairs in first-seen order; unknown:
    ids no findings file defines; ambiguous: {id: [files]} for a bare id
    that more than one file defines."""
    by_id = {}
    for key in index:
        by_id.setdefault(key[1], []).append(key)
    keys, unknown, ambiguous, named = [], [], {}, set()

    def add(key):
        if key not in keys:
            keys.append(key)

    for m in LINK_CITE_RE.finditer(text):
        key = (m.group("stem"), m.group("id").upper())
        if key in index:
            add(key)
        elif key[1] not in unknown:
            unknown.append(f"{key[1]} (in {key[0]}.md)")
    for m in NAMED_CITE_RE.finditer(text):
        who, fid = m.group("who"), m.group("id")
        candidates = by_id.get(fid, [])
        exact = [k for k in candidates if k[0] == who]
        by_stage = [k for k in candidates if index[k]["stage"] == who]
        hit = exact or by_stage
        if len(hit) == 1:
            add(hit[0])
            named.add(m.start("id"))
    for m in FINDING_REF_RE.finditer(text):
        if m.start() in named:
            continue
        fid = m.group(0)
        candidates = by_id.get(fid, [])
        if len(candidates) == 1:
            add(candidates[0])
        elif not candidates:
            if fid not in unknown:
                unknown.append(fid)
        else:
            ambiguous[fid] = sorted(index[k]["file"] for k in candidates)
    # A bare id that the same text also cites by link or by name (the
    # `[F3](../findings/doc-search.md#f3-…)` shape) is that citation.
    resolved_ids = {k[1] for k in keys}
    ambiguous = {i: f for i, f in ambiguous.items() if i not in resolved_ids}
    return keys, unknown, ambiguous


# --- checks ---------------------------------------------------------------

def check_sections(secs, mode, case, problems):
    required = list(COMMON_SECTIONS)
    if mode == "artifact":
        required += list(ARTIFACT_SECTIONS)
    if case.get("stakeholder_questions"):
        required.append("Stakeholder Questions")
    for phrase in required:
        if find_section(secs, phrase) is None:
            problems.append(
                f"C2/section: no `## {phrase}` section — the {mode or 'report'}"
                " template requires it"
            )


def check_cells(lines, secs, problems):
    """Empty cells in the metadata tables, placeholders anywhere."""
    strict = ["__head__"]
    for phrase in ("Execution Metadata", "Objectives Assessment", "Stages Used"):
        hit = find_section(secs, phrase)
        if hit:
            strict.append(hit[0].lower())

    for key, (title, start, end) in secs.items():
        for header, rows in tables(lines, start, end):
            where = title or "the header table"
            for row, line in rows:
                for n, cell in enumerate(row):
                    column = header[n] if n < len(header) else f"column {n + 1}"
                    if PLACEHOLDER_RE.match(cell):
                        problems.append(
                            f"C2/section: {where}:{line}: `{column}` is still "
                            f"the template placeholder `{cell}`"
                        )
                    elif not cell and key in strict:
                        problems.append(
                            f"C2/section: {where}:{line}: `{column}` is empty"
                        )


def ledger_rounds(case_dir):
    """Send-backs recorded for this case, or None when no ledger exists.
    Read through sendback.py so the two never disagree about the format."""
    if not (Path(case_dir) / "audit" / "sendbacks.jsonl").is_file():
        return None
    try:
        return len(_load("sendback").read(case_dir))
    except Exception:  # noqa: BLE001 — an unreadable ledger is not a report defect
        return None


def check_rounds(metrics, ledger, problems, warnings):
    """`Review rounds` against the ledger the lead actually wrote.

    The number is the convergence signal — how many times this report
    was sent back before it passed — so it is worth exactly as much as
    its accuracy. With a ledger on disk it is checkable; without one,
    absence of the mechanism is indistinguishable from a case that
    never needed it, so a claim it cannot back only warns."""
    key = norm("review rounds")
    if key not in metrics:
        return
    stated = re.search(r"\d+", metrics[key][0])
    if not stated:
        problems.append(
            "C2/section: Execution Metadata `review rounds` states no number "
            "— write 0 for a report that passed on the first read"
        )
        return
    stated = int(stated.group())
    if ledger is None:
        if stated:
            warnings.append(
                f"Execution Metadata claims {stated} review round(s) but "
                "audit/sendbacks.jsonl does not exist — nothing backs the "
                "number (record send-backs with sendback.py)"
            )
    elif stated != ledger:
        problems.append(
            f"C2/section: Execution Metadata says {stated} review round(s), "
            f"audit/sendbacks.jsonl records {ledger}"
        )


def check_metadata(lines, secs, index, files, ledger, problems, warnings):
    hit = find_section(secs, "Execution Metadata")
    if hit is None:
        return
    _, start, end = hit
    found = tables(lines, start, end)
    if not found:
        problems.append("C2/section: Execution Metadata has no table")
        return
    metrics = keyed(found[0])
    for metric in METRICS:
        if norm(metric) not in metrics:
            problems.append(f"C2/section: Execution Metadata has no `{metric}` row")

    def stated(metric, labels):
        value = metrics.get(norm(metric), ("", 0))[0]
        return {
            label: int(m.group(1))
            for label in labels
            if (m := re.search(COUNT_RE.format(label), value, re.I))
        }

    actual_conf, actual_basis = {}, {}
    for f in index.values():
        actual_conf[f["confidence"]] = actual_conf.get(f["confidence"], 0) + 1
        actual_basis[f["basis"]] = actual_basis.get(f["basis"], 0) + 1

    for metric, labels, actual in (
        ("total findings", CONFIDENCE, actual_conf),
        ("evidence basis", ("VERIFIED", "REASONED", "ASSUMED"), actual_basis),
    ):
        if norm(metric) not in metrics:
            continue
        claimed = stated(metric, labels)
        if not claimed:
            problems.append(
                f"C2/section: Execution Metadata `{metric}` states no counts — "
                f"expected {', '.join(f'{l}: {actual.get(l, 0)}' for l in labels)}"
            )
            continue
        for label in labels:
            if claimed.get(label, 0) != actual.get(label, 0):
                problems.append(
                    f"C2/section: Execution Metadata says {metric} "
                    f"{label}: {claimed.get(label, 0)}, the findings hold "
                    f"{actual.get(label, 0)}"
                )

    if norm("models used") in metrics:
        value = metrics[norm("models used")][0]
        pairs = dict(re.findall(r"([\w.-]+)\s*=\s*([^,;\s]+)", value))
        for f in files:
            if f["supplement"]:
                if f["stem"] not in pairs and f["stage"] not in pairs:
                    warnings.append(
                        f"Execution Metadata `models used` names neither "
                        f"{f['stem']} nor its parent stage — the supplement's "
                        "provenance is not in the report"
                    )
                continue
            if f["stage"] not in pairs:
                problems.append(
                    f"C2/section: Execution Metadata `models used` does not "
                    f"name {f['stage']}, which produced {f['name']}"
                )
            elif pairs[f["stage"]] != f["model"]:
                problems.append(
                    f"C2/section: Execution Metadata says "
                    f"{f['stage']}={pairs[f['stage']]}, but {f['name']} records "
                    f"model: {f['model']} — copy the key verbatim"
                )
        if "synthesize" not in pairs:
            problems.append(
                "C2/section: Execution Metadata `models used` has no "
                "`synthesize=<model>` — the report does not say what wrote it"
            )

    check_rounds(metrics, ledger, problems, warnings)


def check_stages_used(lines, secs, files, problems, warnings):
    hit = find_section(secs, "Stages Used")
    if hit is None:
        return
    _, start, end = hit
    found = tables(lines, start, end)
    if not found:
        problems.append("C2/section: Stages Used has no table")
        return
    rows = found[0][1]
    for f in files:
        match = next(
            (r for r, _ in rows if f["stage"] in r[0] or f["stem"] in r[0]), None
        )
        if match is None:
            if f["supplement"]:
                warnings.append(f"Stages Used has no row for {f['name']}")
            else:
                problems.append(
                    f"C2/section: Stages Used has no row for {f['stage']}, "
                    f"which wrote {f['name']}"
                )
            continue
        if f["supplement"]:
            continue
        status = match[1].lower() if len(match) > 1 else ""
        if f["status"] and f["status"] not in status:
            problems.append(
                f"C2/section: Stages Used calls {f['stage']} `{match[1]}`, but "
                f"{f['name']} records status: {f['status']}"
            )
        stated = re.search(r"\d+", match[2]) if len(match) > 2 else None
        if stated and int(stated.group()) != f["count"]:
            problems.append(
                f"C2/section: Stages Used credits {f['stage']} with "
                f"{stated.group()} findings, {f['name']} holds {f['count']}"
            )


def check_objectives(lines, secs, case, problems):
    hit = find_section(secs, "Objectives Assessment")
    if hit is None:
        return
    _, start, end = hit
    found = tables(lines, start, end)
    rows = found[0][1] if found else []
    if not rows:
        problems.append(
            "C2/section: Objectives Assessment has no rows — every objective "
            "needs an Achieved / Partial / Not achieved verdict"
        )
        return
    declared = case.get("objectives")
    declared = declared if isinstance(declared, list) else []
    if declared and len(rows) < len(declared):
        problems.append(
            f"C2/section: Objectives Assessment has {len(rows)} row(s) for "
            f"{len(declared)} objective(s) declared in case.yaml"
        )
    for row, line in rows:
        status = (row[1] if len(row) > 1 else "").lower().strip("* ")
        if not any(v in status for v in OBJECTIVE_STATUSES):
            problems.append(
                f"C2/section: Objectives Assessment:{line}: status `{row[1] if len(row) > 1 else ''}` "
                "is not Achieved | Partial | Not achieved"
            )


def check_artifacts(lines, secs, mode, problems):
    if mode != "artifact":
        return
    hit = find_section(secs, "Affected Artifacts")
    if hit is None:
        return  # already reported by check_sections
    _, start, end = hit
    found = tables(lines, start, end)
    if found and found[0][1]:
        return
    if "none" not in " ".join(lines[start + 1:end]).lower():
        problems.append(
            "C2/section: Affected Artifacts names nothing and does not say "
            "`none` — the section cannot be left blank"
        )


def check_hypotheses(lines, secs, index, problems, warnings):
    hit = find_section(secs, "Hypotheses")
    if hit is None:
        return
    _, start, end = hit
    blocks, current = [], None
    for i in range(start + 1, end):
        m = HYPOTHESIS_RE.match(lines[i])
        if m:
            current = {
                "id": m.group("id"),
                "title": m.group("title"),
                "line": i + 1,
                "body": [lines[i]],
            }
            blocks.append(current)
        elif current is not None:
            current["body"].append(lines[i])

    if not blocks:
        warnings.append(
            "no `### H<n>:` hypothesis headings — the rank rule cannot be "
            "checked against the findings"
        )
        return

    for block in blocks:
        text = "\n".join(block["body"])
        where = f"{block['id']} (line {block['line']})"
        m = CONFIDENCE_RE.search(text)
        if not m:
            problems.append(
                f"C2/section: {where} states no Confidence: HIGH | MEDIUM | LOW"
            )
            continue
        confidence = m.group(1).upper()

        cited, unknown, ambiguous = resolve_citations(text, index)
        for ref in unknown:
            problems.append(
                f"C1/ref: {where} cites {ref}, which no findings file defines"
            )
        for ref, owners in ambiguous.items():
            warnings.append(
                f"{where} cites a bare {ref}, which {', '.join(owners)} all "
                "define — name the stage (`jira-trace F1`) or link the "
                "finding's anchor; it is left out of the rank rule"
            )
        if not cited:
            if not unknown:
                warnings.append(f"{where} cites no finding — every claim needs one")
            continue

        def label(key):
            return f"{index[key]['stage']} {key[1]}"

        bases = {key: index[key]["basis"] for key in cited}
        verified = [k for k, b in bases.items() if b == "VERIFIED"]
        reasoned = [k for k, b in bases.items() if b == "REASONED"]
        stages = {index[k]["stage"] for k in reasoned}

        if confidence == "HIGH" and not verified and len(stages) < 2:
            shown = ", ".join("{}={}".format(label(k), bases[k] or "?") for k in cited)
            problems.append(
                f"C1/basis: {where} ranks HIGH on {shown} — HIGH needs one "
                "VERIFIED finding, or two REASONED ones from different stages"
            )
        elif confidence != "LOW" and bases and set(bases.values()) == {"ASSUMED"}:
            problems.append(
                f"C1/basis: {where} ranks {confidence} on ASSUMED findings only "
                f"({', '.join(label(k) for k in cited)}) — repetition of an assumption is not "
                "convergence"
            )


def check_orphans(lines, index, warnings):
    text = "\n".join(lines)
    cited = set(resolve_citations(text, index)[0])
    orphans = [
        f"{key[1]} [{index[key]['confidence'] or '?'}/{index[key]['basis'] or '?'}] "
        f"in {index[key]['file']}"
        for key in sorted(index, key=lambda k: (k[0], int(re.sub(r"\D", "", k[1]))))
        if key not in cited
    ]
    if orphans:
        warnings.append(
            f"{len(orphans)} finding(s) the report never cites: "
            + "; ".join(orphans)
        )


def run(case_dir, report=None):
    """Returns (problems, warnings). case_dir holds case.yaml and
    findings/; report defaults to results/synthesis.md and is given
    explicitly when synthesize checks its own English draft
    (results/synthesis-en.md) before handing it to the lead."""
    case_dir = Path(case_dir)
    report = Path(report) if report else case_dir / "results" / "synthesis.md"
    lines = strip_code(report.read_text(encoding="utf-8"))
    case_yaml = case_dir / "case.yaml"
    case = (
        _load("caselint").parse_yaml(case_yaml.read_text(encoding="utf-8"))
        if case_yaml.is_file()
        else {}
    )
    case = case if isinstance(case, dict) else {}
    mode = case.get("mode", "")
    index, files = load_findings(case_dir)

    problems, warnings = [], []
    secs = sections(lines)
    check_sections(secs, mode, case, problems)
    check_cells(lines, secs, problems)
    check_metadata(lines, secs, index, files, ledger_rounds(case_dir),
                   problems, warnings)
    check_stages_used(lines, secs, files, problems, warnings)
    check_objectives(lines, secs, case, problems)
    check_artifacts(lines, secs, mode, problems)
    check_hypotheses(lines, secs, index, problems, warnings)
    if index:
        check_orphans(lines, index, warnings)
    return problems, warnings


def main(argv):
    if len(argv) not in (2, 3):
        print("usage: reportlint.py cases/<id> [report.md]")
        return 2
    case_dir = Path(argv[1])
    report = Path(argv[2]) if len(argv) == 3 else case_dir / "results" / "synthesis.md"
    if not report.is_file():
        print(f"error: no report at {report}")
        return 2

    problems, warnings = run(case_dir, report)
    for w in warnings:
        print(f"warning: {w}")
    for p in problems:
        print(f"FAIL: {p}")
    if problems:
        codes = sorted({p.split(":")[0] for p in problems})
        print(
            f"{len(problems)} problem(s) — send back to synthesize under "
            f"{', '.join(codes)}"
        )
        return 1
    print(f"OK: {report.name} is structurally complete and its counts match "
          "the findings")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
