#!/usr/bin/env python3
"""Version-provenance check for findings and the report (backs gate C2/version).

The failure this catches: a fact observed at one product version drifts
into a claim about another. Two shapes —

1. Source drift — a finding's Detail argues about "OCP 4.16" while its
   Ref pins `component@4.18.41 file:line`, or the Ref pins no version at
   all (`hyperkube pkg/.../eviction.go:414`), so which version was read
   is unrecoverable. A source location with no `@`-pin is unverifiable
   by construction: that is the one hard FAIL.
2. Attribution drift — the report asserts a version that no finding is
   scoped to, or a finding cites a version outside the case's declared
   `version_scope`. Regex cannot know a CVE's affected range, so these
   stay WARNINGS that feed the lead's C2/version judgment, never a FAIL.

Only the missing `@`-pin FAILs (exit 1) — it is precise and unambiguous.
Everything else is a warning: version tokens are extracted heuristically
(dotted numbers, IP-octets excluded), so the lead reads them and decides.

`version_scope` in case.yaml is the anchor for the scope/attribution
warnings:

    version_scope:
      OCP: ["4.16"]        # z-stream of a scope entry counts as in-scope
      CNV: ["4.16"]

Absent it, scope/attribution checks are skipped with a note — the
@-pin FAIL still runs.

Usage: python3 versioncheck.py cases/<id>
Stdlib-only, offline, like chain.py.
"""

import re
import sys
from pathlib import Path

# A product version token: dotted numbers with 2-3 components. The
# lookbehind/lookahead reject a token bounded by a dot or digit, which
# excludes 4-octet IPs (10.0.0.1) and longer sequences without a special
# case — no interior 2-3 component slice of an IP is ever isolated.
VERSION_RE = re.compile(r"(?<![\d.])\d+\.\d+(?:\.\d+)?(?![\d.])")

# A source location inside a Ref: path/to/file.ext:line — the signature
# of a source citation (drgn/lab/slack/doc Refs never match this shape).
SOURCE_LOC_RE = re.compile(r"[\w./+-]+\.[A-Za-z]+:\d+")

# A commit-sha pin — a precise version anchor without a dotted number.
SHA_RE = re.compile(r"\b[0-9a-f]{7,40}\b")

FINDING_RE = re.compile(r"^#{1,6}\s+F\d+\b.*$", re.M)
FIELD_RE = re.compile(r"^\s*[-*]\s*\*\*(?P<key>[\w /-]+)\*\*\s*:\s*(?P<val>.*)$")


def versions(text):
    """Set of product-version tokens in text (IP octets excluded)."""
    return set(VERSION_RE.findall(text or ""))


def _pinned(ref):
    """A source Ref pins a version if any version token (in the NVR or the
    casket path — `sources-layered-ocp4.20/…`) or a commit sha appears."""
    return bool(VERSION_RE.search(ref) or SHA_RE.search(ref))


def _family(token):
    """Product family = the major component. 4.16 and 4.18 share family
    "4"; kernel 5.14 and OCP 4.16 do not — a cross-family disagreement is
    two legitimately different products, not a crossed version."""
    return token.split(".")[0]


def _in_scope(token, scope):
    """A token is in scope if it and a scope entry share a dotted prefix
    — 4.16.41 is in scope for [4.16], and 4.16 is in scope for [4.16.41]."""
    t = token.split(".")
    for s in scope:
        parts = s.split(".")
        n = min(len(t), len(parts))
        if t[:n] == parts[:n]:
            return True
    return False


def parse_scope(case_yaml):
    """Version tokens declared under a top-level `version_scope:` block.
    A deliberately small hand-parse — no yaml dependency, like the rest
    of scripts/. Returns None when the key is absent."""
    if not case_yaml.is_file():
        return None
    lines = case_yaml.read_text(encoding="utf-8").splitlines()
    scope, in_block, indent = set(), False, None
    for line in lines:
        if re.match(r"^version_scope\s*:", line):
            in_block = True
            scope |= versions(line.split(":", 1)[1])
            continue
        if in_block:
            stripped = line.lstrip()
            cur = len(line) - len(stripped)
            if not stripped:
                continue
            if indent is None and cur > 0:
                indent = cur
            if cur == 0:  # dedent to a new top-level key ends the block
                in_block = False
                continue
            scope |= versions(line)
    return scope if scope else set()


def parse_findings(md):
    """Returns [(label, type, detail, ref)] per finding block."""
    text = md.read_text(encoding="utf-8")
    starts = [m.start() for m in FINDING_RE.finditer(text)]
    if not starts:
        return []
    starts.append(len(text))
    out = []
    for i in range(len(starts) - 1):
        block = text[starts[i]:starts[i + 1]]
        label = block.splitlines()[0].lstrip("# ").strip()
        fields = {}
        for line in block.splitlines()[1:]:
            m = FIELD_RE.match(line)
            if m:
                fields[m.group("key").strip().lower()] = m.group("val").strip()
        out.append((label, fields.get("type", ""), fields.get("detail", ""),
                    fields.get("ref", "")))
    return out


def run(case_dir):
    """Returns (problems, warnings, notes, ok_count)."""
    case_dir = Path(case_dir).resolve()
    problems, warnings, notes, ok = [], [], [], 0
    scope = parse_scope(case_dir / "case.yaml")
    if scope is None:
        notes.append(
            "no version_scope in case.yaml — scope/attribution checks "
            "skipped; add `version_scope:` to anchor them")
        scope = set()

    scope_families = {_family(s) for s in scope}
    finding_versions = set()
    for md in sorted((case_dir / "findings").glob("*.md")):
        rel = f"findings/{md.name}"
        for label, ftype, detail, ref in parse_findings(md):
            where = f"{rel} {label}"
            dv, rv = versions(detail), versions(ref)
            finding_versions |= dv | rv

            # 1. HARD FAIL: a source location with no version anywhere in
            #    the Ref (NVR, casket path, or commit sha) — which version
            #    was read is unrecoverable.
            if SOURCE_LOC_RE.search(ref):
                if _pinned(ref):
                    ok += 1
                else:
                    problems.append(
                        f'{where}: source location cited with no version '
                        f'pin (NVR/path/commit): "{ref}"')

            # 2. WARN: Detail and Ref disagree *within one product family*
            #    (4.16 vs 4.18) — a crossed version, not two products. A
            #    z-stream refines its minor (4.16 vs 4.16.41), so only a
            #    prefix-incompatible pair counts.
            crossed = sorted({
                (d, r) for d in dv for r in rv
                if _family(d) == _family(r) and not _in_scope(d, {r})})
            for d, r in crossed:
                warnings.append(
                    f"{where}: Detail cites {d} but Ref pins {r} — "
                    "attribution may be crossed")

            # 3. WARN: a finding version in a scoped family but off-scope.
            for v in sorted(dv | rv):
                if _family(v) in scope_families and not _in_scope(v, scope):
                    warnings.append(
                        f"{where}: version {v} not in version_scope "
                        f"{sorted(scope)}")

    # 4. WARN: a report version in a scoped family, off-scope, and backed
    #    by no finding — the attribution-drift signal. Needs a declared
    #    scope to have a family to anchor to; otherwise skipped.
    report = case_dir / "results" / "report.md"
    if report.is_file():
        for v in sorted(versions(report.read_text(encoding="utf-8"))):
            if (_family(v) in scope_families and not _in_scope(v, scope)
                    and v not in finding_versions):
                warnings.append(
                    f"results/report.md: version {v} asserted but backed "
                    f"by no finding and outside version_scope {sorted(scope)}")

    return problems, warnings, notes, ok


def main(argv):
    if len(argv) != 2:
        print("usage: versioncheck.py cases/<id>")
        return 2
    case_dir = Path(argv[1])
    if not case_dir.is_dir():
        print(f"error: no such case dir: {case_dir}")
        return 2
    problems, warnings, notes, ok = run(case_dir)
    for n in notes:
        print(f"note: {n}")
    for w in warnings:
        print(f"warning: {w}")
    for p in problems:
        print(f"FAIL: {p}")
    if problems:
        print(f"{len(problems)} source Ref(s) pin no version — send back "
              "under C2/version")
        return 1
    tail = f"; {len(warnings)} version warning(s) for the lead to judge" \
        if warnings else ""
    print(f"OK: {ok} source Ref(s) version-pinned{tail}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
