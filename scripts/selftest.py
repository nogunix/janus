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
        # Regression: making the attribution clickable (what the reader
        # actually wants) must not stop it being recognised as an
        # attribution — that silently turned every report into a
        # "no attributed quotes" C2/quote-absent send-back.
        linked = (
            "# Report\n\n"
            "> The VM fails on OCP 4.18.41 because the livenessProbe\n"
            "> times out after 30s.\n"
            "> — [F1](../findings/doc-search.md#f1-probe-timeout)\n"
        )
        report.write_text(linked)
        problems, warnings, ok = quotecheck.run(report)
        check(
            not problems and not warnings and ok == 1,
            "a linked attribution is still an attributed quote",
        )
        check(
            quotecheck.source_path(
                "../findings/doc-search.md#f1-probe-timeout", report, case
            )
            == "findings/doc-search.md",
            "the link target resolves to a case-relative evidence path",
        )
        check(
            quotecheck.source_path("../../../etc/passwd", report, case) is None,
            "an attribution pointing outside the case resolves to nothing",
        )

        report.write_text(
            "# Report\n\n"
            "> The VM fails on OCP 4.18.41 because the livenessProbe\n"
            "> times out after 30s.\n"
            "> — findings/doc-search.md\n\n"
            "Analysis follows.\n\n"
            "> just a stylistic blockquote, no attribution\n"
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

    # Unverified-anchor detection is offline — no monkeypatching needed.
    status, detail = urlcheck.check(
        "https://access.redhat.com/documentation/en-us/openshift_container_platform"
        "/4.16/html-single/installation_overview/index#connected-to-disconnected"
    )
    check(
        status == "unverified_anchor",
        "a #fragment on access.redhat.com is flagged as unverified_anchor",
    )
    status, detail = urlcheck.check(
        "https://docs.redhat.com/en/documentation/openshift_container_platform"
        "/4.16/html-single/installation_overview/index#some-section"
    )
    check(
        status == "unverified_anchor",
        "a #fragment on docs.redhat.com is flagged as unverified_anchor",
    )
    status, _ = urlcheck.check(
        "https://access.redhat.com/documentation/en-us/openshift_container_platform"
        "/4.16/html-single/installation_overview/index"
    )
    check(
        status != "unverified_anchor",
        "an anchor-free access.redhat.com URL is not flagged",
    )
    check(
        urlcheck._has_unverified_anchor(
            "https://access.redhat.com/errata/RHSA-2024:1234#some-cve"
        ),
        "_has_unverified_anchor detects fragment on access.redhat.com",
    )
    check(
        not urlcheck._has_unverified_anchor(
            "https://access.redhat.com/errata/RHSA-2024:1234"
        ),
        "_has_unverified_anchor passes through anchor-free URL",
    )
    check(
        not urlcheck._has_unverified_anchor(
            "https://github.com/openshift/openshift-docs/issues/123#comment-456"
        ),
        "_has_unverified_anchor does not flag non-Red-Hat domains",
    )


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


def test_linkcheck():
    link = load("linkcheck")

    check(
        link.slug("F1: VM migration fails on OCP 4.18.41")
        == "f1-vm-migration-fails-on-ocp-41841",
        "slug drops punctuation rather than hyphenating it (GitHub's rule)",
    )
    check(link.slug("根拠となる所見") == "根拠となる所見", "slug keeps Japanese headings")

    dupes = link.anchors("# same\n\n# same\n\n# same\n")
    check(
        dupes == {"same", "same-1", "same-2"},
        "duplicate headings get GitHub's -1/-2 suffixes",
    )
    check(
        link.anchors('<a id="f7"></a>\n\n### F7: t\n') >= {"f7", "f7-t"},
        "explicit <a id> anchors count alongside heading slugs",
    )

    fenced = "```\n[x](../findings/nope.md)\n```\n[y](../findings/real.md)\n"
    targets = [t for t, _ in link.extract_links(fenced)]
    check(
        targets == ["../findings/real.md"],
        "links inside a fenced code block are not checked",
    )
    check(
        not link.extract_links("[cve](https://example.com/a) [m](mailto:a@b.c)"),
        "external links are urlcheck's job, not linkcheck's",
    )

    with tempfile.TemporaryDirectory() as td:
        case = Path(td) / "cases" / "2026-01-01-link"
        (case / "findings").mkdir(parents=True)
        (case / "audit").mkdir()
        (case / "results").mkdir()
        (case / "findings" / "crash-analyze.md").write_text(
            "### F3: SIGSEGV in qemu-kvm\ndetail\n", encoding="utf-8"
        )
        (case / "audit" / "lab-1.log").write_text("out\n")
        report = case / "results" / "report.md"

        report.write_text(
            "# R\n\n"
            "[F3](../findings/crash-analyze.md#f3-sigsegv-in-qemu-kvm)\n"
            "[log](../audit/lab-1.log)\n"
            "[toc](#r)\n",
            encoding="utf-8",
        )
        problems, warnings, ok = link.run(report)
        check(
            not problems and ok == 3,
            "valid finding-anchor, log and same-file links all resolve",
        )

        report.write_text("# R\n\n[F9](../findings/crash-analyze.md#f9-nope)\n", encoding="utf-8")
        problems, _, _ = link.run(report)
        check(
            len(problems) == 1 and "no such anchor" in problems[0],
            "an anchor no heading produces is a FAIL",
        )

        report.write_text("# R\n\n[gone](../findings/source-trace.md)\n", encoding="utf-8")
        problems, _, _ = link.run(report)
        check(
            len(problems) == 1 and "does not exist" in problems[0],
            "a link to a findings file that was never written is a FAIL",
        )

        report.write_text("# R\n\n[esc](../../../../etc/passwd)\n", encoding="utf-8")
        problems, _, _ = link.run(report)
        check(
            len(problems) == 1 and "escapes the case directory" in problems[0],
            "a link outside the case directory is a FAIL",
        )

        report.write_text("# R\n\nprose with no links.\n", encoding="utf-8")
        problems, warnings, _ = link.run(report)
        check(
            not problems and any("no local evidence links" in w for w in warnings),
            "a report with no links warns, but does not FAIL",
        )


def test_anchors():
    anchors_mod = load("anchors")
    link = load("linkcheck")

    # anchors.py slug must match linkcheck.py slug on every input
    cases = [
        ("F1: VM migration fails on OCP 4.18.41", "f1-vm-migration-fails-on-ocp-41841"),
        ("F10: ODF 4.18→4.19 アップグレード: NooBaa DB 移行デッドロック",
         "f10-odf-418419-アップグレード-noobaa-db-移行デッドロック"),
        ("F4: DFBUGS-8895 — ODF 4.18/4.19 NooBaa DB 移行 (ON_QA, 修正中)",
         "f4-dfbugs-8895-odf-418419-noobaa-db-移行-on_qa-修正中"),
        ("F1: 管理者 ACK が必須 — Kubernetes 1.32 API 削除への対応",
         "f1-管理者-ack-が必須-kubernetes-132-api-削除への対応"),
        ("根拠となる所見", "根拠となる所見"),
    ]
    for title, expected in cases:
        a_slug = anchors_mod.slug(title)
        l_slug = link.slug(title)
        check(
            a_slug == l_slug,
            f"anchors.slug == linkcheck.slug for '{title[:40]}…'",
        )
        check(
            a_slug == expected,
            f"slug value correct for '{title[:40]}…'",
        )

    with tempfile.TemporaryDirectory() as td:
        findings = Path(td) / "findings"
        findings.mkdir()
        f = findings / "doc-search.md"
        f.write_text(
            "### F1: probe timeout\n\n"
            "### F10: ODF 4.18→4.19 アップグレード: NooBaa DB 移行デッドロック\n\n"
            "### F1: probe timeout\n"
        )
        rows = list(anchors_mod.extract(f))
        check(
            rows[0] == ("f1-probe-timeout", "F1: probe timeout"),
            "extract yields correct (slug, title) for F1",
        )
        check(
            rows[1][0] == "f10-odf-418419-アップグレード-noobaa-db-移行デッドロック",
            "extract handles version arrows and Japanese correctly",
        )
        check(
            rows[2] == ("f1-probe-timeout-1", "F1: probe timeout"),
            "duplicate headings get -1 suffix (same as linkcheck)",
        )


def test_prosecheck():
    """prosecheck shells out to textlint, which CI does not have. Every
    assertion here must therefore hold with textlint absent — which is
    itself the property under test: the check degrades to a notice rather
    than failing an English case or an offline box."""
    prose = load("prosecheck")

    with tempfile.TemporaryDirectory() as td:
        case = Path(td) / "cases" / "2026-01-01-prose"
        (case / "results").mkdir(parents=True)
        report = case / "results" / "report.md"
        report.write_text("# report\n\n本文である。\n", encoding="utf-8")

        check(prose.report_language(case) is None, "a missing case.yaml reads as None")

        (case / "case.yaml").write_text("id: prose\nstatus: done\n")
        check(
            prose.report_language(case) == prose.DEFAULT_LANGUAGE,
            "an absent report_language defaults to en",
        )

        problems, warnings, notices = prose.run(case)
        check(
            not problems and len(notices) == 1 and "skipped" in notices[0],
            "an English report is skipped with a notice, never a FAIL",
        )

        (case / "case.yaml").write_text('id: prose\nreport_language: "JA"\n')
        check(
            prose.report_language(case) == "ja",
            "report_language is case-insensitive and quote-tolerant",
        )

        # With textlint absent (CI) this notices; with it installed the
        # report above is clean. Either way it must not FAIL.
        problems, _, notices = prose.run(case)
        check(not problems, "a clean/uncheckable Japanese report does not FAIL")
        if prose.textlint_command() is None:
            check(
                any("textlint not installed" in n for n in notices),
                "a missing textlint degrades to an actionable notice",
            )

        # Regression: `npx --no-install textlint` with no textlint present
        # exits non-zero with empty stdout. That once parsed as "no
        # problems" and printed OK — a check that never ran claiming to
        # pass. Every not-actually-run path must yield a notice.
        original = prose.textlint_command
        try:
            for label, cmd in (
                ("a non-zero exit with no output", ["false"]),
                ("a zero exit with no output", ["true"]),
                ("a command that does not exist", ["janus-no-such-textlint"]),
            ):
                prose.textlint_command = lambda cmd=cmd: cmd
                problems, warnings, notices = prose.run(case)
                check(
                    not problems and not warnings and len(notices) == 1,
                    f"{label} is a notice, never a silent pass",
                )
                check(
                    "skipped" in notices[0],
                    f"{label} says the check was skipped",
                )
        finally:
            prose.textlint_command = original

        (case / "case.yaml").write_text("id: prose\nreport_language: ja\n")
        report.unlink()
        _, _, notices = prose.run(case)
        check(
            any("no report yet" in n for n in notices),
            "a case with no report yet is a notice, not a FAIL",
        )

    payload = json.dumps(
        [
            {
                "filePath": "/x/results/report.md",
                "messages": [
                    {
                        "line": 12,
                        "column": 3,
                        "ruleId": "sentence-length",
                        "message": "Line 12 exceeds\nthe maximum",
                        "severity": 2,
                    },
                    {
                        "line": 20,
                        "column": 1,
                        "ruleId": "no-doubled-joshi",
                        "message": "doubled joshi",
                        "severity": 1,
                    },
                ],
            }
        ]
    )
    problems, warnings = prose.parse_results(payload)
    check(
        len(problems) == 1 and "report.md:12:3" in problems[0],
        "severity 2 becomes a problem, anchored at file:line:column",
    )
    check(
        "sentence-length" in problems[0] and "\n" not in problems[0],
        "the rule id is kept and the message is flattened to one line",
    )
    check(
        len(warnings) == 1 and "no-doubled-joshi" in warnings[0],
        "severity 1 becomes a warning, not a problem",
    )
    check(prose.parse_results("") == ([], []), "an empty payload is not an error")


def main():
    test_chain()
    test_lock()
    test_quotecheck()
    test_urlcheck()
    test_versioncheck()
    test_linkcheck()
    test_anchors()
    test_prosecheck()
    if failures:
        print(f"{len(failures)} self-test(s) failed")
        return 1
    print("all self-tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
