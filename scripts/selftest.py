#!/usr/bin/env python3
"""Offline self-tests for the plugin's bundled scripts (CI-friendly).

Covers chain.py (seal → verify → revision → tamper detection →
ledger-edit detection, plus lock/unlock), the evidence-lock hook's deny
logic, quotecheck.py's quote extraction and verbatim matching, and
urlcheck.py's URL extraction and classification constants. No network,
no MCP servers; stdlib-only, like validate.py. Exit 1 on any failure.
"""

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent / "plugins/janus"
SCRIPTS = PLUGIN / "skills/janus/scripts"
HOOKS = PLUGIN / "hooks"

failures = []


def load(name, directory=SCRIPTS):
    spec = importlib.util.spec_from_file_location(name, directory / f"{name}.py")
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


def test_lock():
    chain = load("chain")
    lock_hook = load("evidence-lock", HOOKS)
    with tempfile.TemporaryDirectory() as td:
        case = Path(td) / "cases" / "2026-01-01-selftest"
        (case / "findings").mkdir(parents=True)
        (case / "results").mkdir()
        (case / "case.yaml").write_text("id: selftest\n")
        finding = case / "findings" / "doc-search.md"
        finding.write_text("F1\n")
        chain.seal(case)

        check(
            lock_hook.locked_reason("Write", str(finding)) is None,
            "hook allows writes to unlocked evidence",
        )

        locked = chain.lock(case)
        check(
            sorted(locked) == ["case.yaml", "findings/doc-search.md"],
            "lock covers the fact base (case.yaml + findings)",
        )
        check(
            not finding.stat().st_mode & 0o222,
            "lock drops all write bits",
        )
        check(
            lock_hook.locked_reason("Write", str(finding)) is not None
            and lock_hook.locked_reason("Edit", str(finding)) is not None,
            "hook denies Write/Edit to locked evidence",
        )
        check(
            lock_hook.locked_reason("Write", str(case / "results" / "report.md"))
            is None,
            "hook allows writing the (not yet existing) report",
        )
        check(
            lock_hook.locked_reason("Read", str(finding)) is None,
            "hook ignores non-write tools",
        )

        problems, _ = chain.verify(case)
        check(not problems, "verify still passes on a locked case")

        unlocked = chain.unlock(case)
        check(
            sorted(unlocked) == ["case.yaml", "findings/doc-search.md"]
            and finding.stat().st_mode & 0o200
            and lock_hook.locked_reason("Write", str(finding)) is None,
            "unlock restores owner write and the hook allows again",
        )


def test_quotecheck():
    quotecheck = load("quotecheck")
    with tempfile.TemporaryDirectory() as td:
        case = Path(td) / "cases" / "2026-01-01-selftest"
        (case / "findings").mkdir(parents=True)
        (case / "results").mkdir()
        (case / "findings" / "doc-search.md").write_text(
            "### F1: probe timeout\n"
            "- **Detail**: The VM fails on OCP 4.18.41 because the\n"
            "  livenessProbe times out after 30s.\n"
        )
        report = case / "results" / "report.md"

        report.write_text(
            "# Report\n\n"
            "> The VM fails on OCP 4.18.41 because the livenessProbe\n"
            "> times out after 30s.\n"
            "> — findings/doc-search.md\n\n"
            "Analysis follows.\n\n"
            "> just a stylistic blockquote, no attribution\n"
        )
        quotes = quotecheck.extract_quotes(report.read_text())
        check(
            len(quotes) == 1 and quotes[0][0] == "findings/doc-search.md",
            "extract_quotes takes attributed blockquotes, skips plain ones",
        )
        problems, warnings, ok = quotecheck.run(report)
        check(
            not problems and not warnings and ok == 1,
            "a verbatim quote (reflowed across lines) passes",
        )

        report.write_text(
            "> The VM may fail on OCP 4.18 because the livenessProbe\n"
            "> times out.\n"
            "> — findings/doc-search.md\n"
        )
        problems, _, _ = quotecheck.run(report)
        check(
            any("not found verbatim" in p for p in problems),
            "a mutated quote is detected",
        )

        report.write_text("> anything\n> — findings/nonexistent.md\n")
        problems, _, _ = quotecheck.run(report)
        check(
            any("does not exist" in p for p in problems),
            "an attribution to a missing findings file is detected",
        )

        report.write_text("# Report\n\nNo quotes at all.\n")
        problems, warnings, _ = quotecheck.run(report)
        check(
            not problems and any("no attributed quotes" in w for w in warnings),
            "a report without quotes warns instead of failing",
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
        and 403 in urlcheck.GATED_ERRORS,
        "dead vs gated classification constants",
    )
    check(
        urlcheck._is_login("https://sso.redhat.com/auth/realms/x")
        and urlcheck._is_login("https://access.redhat.com/oauth/authorize")
        and not urlcheck._is_login("https://access.redhat.com/errata/RHSA-2024:2394/"),
        "_is_login flags SSO host and /auth path, not a plain portal URL",
    )

    # check() classification without network: monkeypatch _request.
    orig = urlcheck._request
    try:
        urlcheck._request = lambda u, m: (200, "https://sso.redhat.com/auth/realms/x")
        status, _ = urlcheck.check("https://access.redhat.com/errata/RHSA-2099:9999-x/")
        check(status == "gated", "a 200 that redirects into SSO is gated, not a clean live")

        import urllib.error
        def _dead(u, m):
            raise urllib.error.HTTPError(u, 404, "Not Found", {}, None)
        urlcheck._request = _dead
        status, _ = urlcheck.check("https://access.redhat.com/errata/RHSA-2099:9999/")
        check(status == "dead", "a canonical fabricated errata (404) is dead")
    finally:
        urlcheck._request = orig


def main():
    test_chain()
    test_lock()
    test_quotecheck()
    test_urlcheck()
    if failures:
        print(f"{len(failures)} self-test(s) failed")
        return 1
    print("all self-tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
