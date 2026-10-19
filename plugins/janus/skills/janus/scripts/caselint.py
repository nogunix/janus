#!/usr/bin/env python3
"""case.yaml validation, run at intake before any stage is launched.

Every other check in this directory reads the case *after* the work is
done. This one reads the single file that configures the work, because a
bad value there does not announce itself — it silently changes what runs.

The case that motivated it: `report_language: jp`. SKILL.md composes
localize on `≠ en`, so a Japanese report is produced; `gates.py` runs
prosecheck only on `== ja`, so the prose gate prints `SKIP
report_language is not ja` and the report ships unchecked. Both halves
behaved exactly as written. A typo in one field turned a gate off, and
the output said nothing a reader would stop at.

So the checks here are all of the same shape: a field whose wrong value
is *accepted* downstream rather than rejected.

  FAIL  a missing required key (`id`, `received_at`, `mode`, `status`);
        a `mode` / `status` / `tracks` / `report_language` value outside
        its vocabulary; `mode: artifact` with no artifact to analyse;
        `mode: theme` with no theme; a malformed `version_scope`.
  warn  no `tracks` (the lead composes the pipeline by hand); no
        `objectives` (the Objectives Assessment gets derived rather than
        declared); a version named in the theme with no `version_scope`
        declared; `id` not matching the directory name.

There is no fail-open path: every answer here is computable from the
file in hand. An unknown key is ignored, not failed — case.yaml carries
free-form context (`constraints`, `context`, `gaps`) by design.

Usage: python3 caselint.py cases/<id>   (or cases/<id>/case.yaml)
Stdlib-only, offline, like chain.py.
"""

import re
import sys
from pathlib import Path

MODES = ("artifact", "theme")
STATUSES = ("intake", "scheduled", "in_progress", "needs_human", "done", "failed")
# The composition table in SKILL.md — a track outside it maps to no stage.
TRACKS = ("documentation", "source", "debug", "iac", "github", "jira", "sno", "vm")
LANGUAGES = ("en", "ja")
REQUIRED = ("id", "received_at", "mode", "status")

KEY_RE = re.compile(r"^([A-Za-z_][\w-]*)\s*:\s*(.*)$")
BLOCK_RE = re.compile(r"^[>|][+-]?\d*$")
VERSION_TOKEN_RE = re.compile(r"^\d+(?:\.\d+){0,3}$")
# A product version in prose: 4.18, 9.6, 4.20.27 — not a bare integer.
VERSION_RE = re.compile(r"(?<![\d.])\d+\.\d+(?:\.\d+)?(?![\d.])")


# --- a deliberately small YAML subset -------------------------------------
# No yaml dependency, like the rest of scripts/. Handles what case.yaml
# actually uses: scalars, folded/literal blocks, flow and block lists, and
# one level of nested mapping. Anything deeper parses as an opaque string,
# which is correct here — nothing below that level is validated.

def _unquote(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _strip_comment(line):
    """Drop a trailing ` # comment`, leaving a `#` inside a value alone."""
    if line.lstrip().startswith("#"):
        return ""
    return line.split(" #")[0] if " #" in line else line


def _flow_list(value):
    inner = value.strip()[1:]
    inner = inner[:-1] if inner.endswith("]") else inner
    return [_unquote(x) for x in inner.split(",") if x.strip()]


def _deeper(lines, start, indent):
    """The run of lines indented past `indent`, and the index after it."""
    block, i = [], start
    while i < len(lines):
        line = lines[i]
        if line.strip() and (len(line) - len(line.lstrip())) <= indent:
            break
        block.append(line)
        i += 1
    return block, i


def _block(lines, i, indent):
    """The mapping or sequence at `indent`, and the index after it.
    A block holding both `- items` and `key: value` returns the items —
    case.yaml never mixes them, and guessing is worse than choosing."""
    items, mapping = [], {}
    while i < len(lines):
        raw = lines[i]
        line = _strip_comment(raw).strip()
        if not line or line in ("---", "..."):
            i += 1
            continue
        cur = len(raw) - len(raw.lstrip())
        if cur < indent:
            break
        i += 1
        if line.startswith("- "):
            item = line[2:].strip()
            m = KEY_RE.match(item)
            items.append({m.group(1): _unquote(m.group(2))} if m else _unquote(item))
            continue
        m = KEY_RE.match(line)
        if not m:
            continue
        key, rest = m.group(1), m.group(2).strip()
        if BLOCK_RE.match(rest):
            folded, i = _deeper(lines, i, cur)
            mapping[key] = " ".join(l.strip() for l in folded if l.strip())
        elif rest.startswith("["):
            mapping[key] = _flow_list(rest)
        elif rest:
            mapping[key] = _unquote(rest)
        else:
            mapping[key], i = _block(lines, i, cur + 1)
    return (items if items else mapping), i


def parse_yaml(text):
    """A case.yaml as nested dicts, lists and strings."""
    return _block(text.splitlines(), 0, 0)[0]


# --- the checks -----------------------------------------------------------

def _as_list(value):
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value:
        return [value]
    return []


def check_language(case, problems):
    lang = case.get("report_language")
    if lang is None:
        return
    if not isinstance(lang, str) or lang.lower() not in LANGUAGES:
        problems.append(
            f"report_language `{lang}` is not en | ja — localize runs on "
            "anything that is not `en`, while gates.py runs prosecheck only "
            "on exactly `ja`, so this value produces a translated report "
            "with the prose gate silently skipped"
        )


def check_mode(case, problems):
    mode = case.get("mode")
    if mode and mode not in MODES:
        problems.append(f"mode `{mode}` is not {' | '.join(MODES)}")
        return
    if mode == "artifact":
        artifacts = case.get("artifacts")
        have = isinstance(artifacts, dict) and any(
            artifacts.get(k) for k in ("vmcore", "coredump")
        )
        if not have:
            problems.append(
                "mode: artifact with no `artifacts.vmcore` (or `coredump`) — "
                "crash-analyze has nothing to open"
            )
    elif mode == "theme" and not case.get("theme"):
        problems.append("mode: theme with no `theme` — the stages have no question")


def check_tracks(case, problems, warnings):
    if "tracks" not in case:
        warnings.append(
            "no `tracks` — the pipeline composition table in SKILL.md cannot "
            "be applied, so the lead composes by hand"
        )
        return
    for track in _as_list(case["tracks"]):
        if track not in TRACKS:
            problems.append(
                f"tracks: `{track}` is not one of {', '.join(TRACKS)} — "
                "it composes no stage"
            )


def check_scope(case, problems):
    scope = case.get("version_scope")
    if scope is None:
        return
    if not isinstance(scope, dict) or not scope:
        problems.append(
            "version_scope is not a product → version-list mapping "
            "(e.g. `OCP: [\"4.20\"]`) — versioncheck.py reads no scope from it"
        )
        return
    for product, declared in scope.items():
        tokens = _as_list(declared)
        if not tokens:
            problems.append(f"version_scope.{product} declares no version")
            continue
        for token in tokens:
            if not VERSION_TOKEN_RE.match(str(token).strip()):
                problems.append(
                    f"version_scope.{product}: `{token}` is not a version token"
                )


def check_scope_declared(case, warnings):
    """A version named in the question with no scope declared: versioncheck
    then skips every scope and attribution warning for that case."""
    if case.get("version_scope"):
        return
    text = " ".join(
        str(case.get(key, "")) for key in ("theme", "question", "title")
    )
    found = sorted(set(VERSION_RE.findall(text)))
    if found:
        warnings.append(
            f"the question names {', '.join(found)} but no `version_scope` is "
            "declared — versioncheck.py will skip its scope and attribution "
            "warnings"
        )


def check_objectives(case, warnings):
    if not case.get("objectives") and not case.get("stakeholder_questions"):
        warnings.append(
            "no `objectives` — synthesize derives the Objectives Assessment "
            "rows from the theme instead of from a declared list; declare "
            "them to pin what the case must answer"
        )


def run(target):
    """Returns (problems, warnings). target is a case dir or a case.yaml."""
    target = Path(target)
    case_yaml = target if target.is_file() else target / "case.yaml"
    case_dir = case_yaml.parent
    case = parse_yaml(case_yaml.read_text(encoding="utf-8"))

    problems, warnings = [], []
    if not isinstance(case, dict) or not case:
        problems.append("no top-level keys parsed — is this a case.yaml?")
        return problems, warnings

    for key in REQUIRED:
        if not case.get(key):
            problems.append(f"no `{key}`")
    status = case.get("status")
    if status and status not in STATUSES:
        problems.append(f"status `{status}` is not {' | '.join(STATUSES)}")
    if case.get("id") and case["id"] != case_dir.name:
        warnings.append(
            f"id `{case['id']}` is not the directory name `{case_dir.name}` — "
            "review-queue files are named from the id"
        )

    check_mode(case, problems)
    check_language(case, problems)
    check_tracks(case, problems, warnings)
    check_scope(case, problems)
    check_scope_declared(case, warnings)
    check_objectives(case, warnings)
    return problems, warnings


def main(argv):
    if len(argv) != 2:
        print("usage: caselint.py cases/<id>")
        return 2
    target = Path(argv[1])
    case_yaml = target if target.is_file() else target / "case.yaml"
    if not case_yaml.is_file():
        print(f"error: no case.yaml at {target}")
        return 2

    problems, warnings = run(target)
    for w in warnings:
        print(f"warning: {case_yaml.name}: {w}")
    for p in problems:
        print(f"FAIL: {case_yaml.name}: {p}")
    if problems:
        print(
            f"{len(problems)} problem(s) in {case_yaml} — fix the case before "
            "launching any stage"
        )
        return 1
    print(f"OK: {case_yaml} is a well-formed case")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
