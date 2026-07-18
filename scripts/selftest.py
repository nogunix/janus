#!/usr/bin/env python3
"""Offline self-tests for the plugin's bundled scripts (CI-friendly).

Covers chain.py (seal → verify → revision → tamper detection →
ledger-edit detection) and urlcheck.py's URL extraction and
classification constants. No network, no MCP servers; stdlib-only,
like validate.py. Exit 1 on any failure.
"""

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "plugins/janus/skills/janus/scripts"

failures = []


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check(cond, label):
    print(("ok: " if cond else "FAIL: ") + label)
    if not cond:
        failures.append(label)


def test_chain():
    chain = load("chain")
    with tempfile.TemporaryDirectory() as td:
        case = Path(td) / "cases" / "2026-01-01-selftest"
        (case / "findings").mkdir(parents=True)
        (case / "case.yaml").write_text("id: selftest\n")
        finding = case / "findings" / "doc-search.md"
        finding.write_text("F1\n")

        sealed = chain.seal(case)
        check(
            sorted(sealed) == ["case.yaml", "findings/doc-search.md"],
            "seal covers the default targets",
        )
        problems, warnings = chain.verify(case)
        check(not problems and not warnings, "verify passes on an intact chain")

        check(chain.seal(case) == [], "unchanged files are not re-sealed")

        finding.write_text("F1 revised\n")
        chain.seal(case, [finding])
        problems, _ = chain.verify(case)
        check(not problems, "a sealed revision is legitimate")

        finding.write_text("tampered\n")
        problems, _ = chain.verify(case)
        check(
            any("TAMPER" in p for p in problems),
            "an unsealed edit is detected as tamper",
        )

        chain.seal(case, [finding])
        ledger = case / "chain.jsonl"
        lines = ledger.read_text().splitlines()
        record = json.loads(lines[0])
        record["actor"] = "evil"
        lines[0] = json.dumps(record, sort_keys=True)
        ledger.write_text("\n".join(lines) + "\n")
        problems, _ = chain.verify(case)
        check(
            any("hash mismatch" in p for p in problems),
            "an edited ledger record is detected",
        )


def test_urlcheck():
    urlcheck = load("urlcheck")
    urls = urlcheck.extract_urls(
        "see https://a.example/x. and (https://b.example/y) "
        "plus https://a.example/x again"
    )
    check(
        urls == ["https://a.example/x", "https://b.example/y"],
        "extract_urls dedupes and strips trailing punctuation",
    )
    check(
        404 in urlcheck.DEAD_ERRORS
        and 410 in urlcheck.DEAD_ERRORS
        and 403 in urlcheck.REACHABLE_ERRORS,
        "dead vs reachable classification constants",
    )


def main():
    test_chain()
    test_urlcheck()
    if failures:
        print(f"{len(failures)} self-test(s) failed")
        return 1
    print("all self-tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
