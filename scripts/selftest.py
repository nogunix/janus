#!/usr/bin/env python3
"""Offline self-tests for the plugin's bundled scripts (CI-friendly).

Covers chain.py (seal → verify → revision → tamper detection →
ledger-edit detection, plus lock/unlock), the evidence-lock hook's deny
logic, quotecheck.py's quote extraction and verbatim matching, and
urlcheck.py's URL extraction and classification constants. No network,
no MCP servers; stdlib-only, like validate.py. Exit 1 on any failure.
"""

import errno
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

        def _reset(u, m):
            raise ConnectionResetError(errno.ECONNRESET, "Connection reset by peer")
        urlcheck._request = _reset
        status, _ = urlcheck.check("https://issues.redhat.com/browse/OCPBUGS-4077")
        check(status == "warn", "a connection reset from a live host warns, not FAILs")

        def _refused(u, m):
            raise urllib.error.URLError(
                ConnectionRefusedError(errno.ECONNREFUSED, "Connection refused"))
        urlcheck._request = _refused
        status, _ = urlcheck.check("https://nothing.example/x")
        check(status == "unreachable", "a connection refused stays a hard FAIL")
    finally:
        urlcheck._request = orig


def test_versioncheck():
    version = load("versioncheck")

    # Helpers: IP octets excluded, z-stream/prefix scope matching, family.
    check(
        version.versions("on 4.16.55 vs 4.18, ip 10.0.0.1, tag 427.105.1")
        == {"4.16.55", "4.18", "427.105.1"},
        "versions() strips 4-octet IPs, keeps dotted version tokens",
    )
    check(
        version._in_scope("4.16.55", {"4.16"}) and version._in_scope("4.16", {"4.16.55"})
        and not version._in_scope("4.18", {"4.16"}),
        "_in_scope matches a z-stream to its minor, rejects a sibling minor",
    )
    check(
        version._pinned("kernel-5.14.0-427.el9_4 kernel.spec:6317")
        and version._pinned("hyperkube@4.16.41 x.go:1")
        and version._pinned("comp@deadbeef1 x.go:1")
        and not version._pinned("pkg/kubelet/eviction/eviction.go:414"),
        "_pinned accepts an NVR/path/sha, rejects a bare file:line",
    )

    with tempfile.TemporaryDirectory() as td:
        case = Path(td) / "cases" / "2026-01-01-vc"
        (case / "findings").mkdir(parents=True)
        (case / "results").mkdir(parents=True)
        (case / "case.yaml").write_text(
            "id: vc\nversion_scope:\n  OCP: [\"4.16\"]\n")
        (case / "findings" / "source-trace.md").write_text(
            "### F1: pinned, in-scope z-stream\n"
            "- **Detail**: fix in OCP 4.16 before 4.16.55.\n"
            "- **Ref**: hyperkube@4.16.41 pkg/kubelet/eviction/eviction.go:414\n\n"
            "### F2: unpinned source read\n"
            "- **Detail**: bug here.\n"
            "- **Ref**: pkg/kubelet/eviction/eviction.go:414\n\n"
            "### F3: crossed within family\n"
            "- **Detail**: on OCP 4.16 the operator differs.\n"
            "- **Ref**: cluster-network-operator@4.18.9 pkg/network/render.go:88\n")
        (case / "results" / "report.md").write_text(
            "# Report\nSeen on OCP 4.19 and also 4.16. Kernel 5.14.0 base.\n")

        problems, warnings, notes, ok = version.run(case)
        check(len(problems) == 1 and "F2" in problems[0],
              "the unpinned source citation is the one hard FAIL")
        check(not notes, "a declared version_scope suppresses the skip note")
        joined = " | ".join(warnings)
        check("F3" in joined and "crossed" in joined,
              "a within-family Detail/Ref cross (4.16 vs 4.18) warns")
        check("4.18.9 not in version_scope" in joined,
              "an off-scope finding version in a scoped family warns")
        check("4.19 asserted" in joined,
              "a report version off-scope in a scoped family, backed by no "
              "finding, warns")
        check("4.16.41" not in joined and "5.14.0" not in joined,
              "an in-scope z-stream and a different-family kernel do not warn")


def main():
    test_chain()
    test_lock()
    test_quotecheck()
    test_urlcheck()
    test_versioncheck()
    if failures:
        print(f"{len(failures)} self-test(s) failed")
        return 1
    print("all self-tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
