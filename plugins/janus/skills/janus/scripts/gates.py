#!/usr/bin/env python3
"""Run the six step-7 pre-checks in one call and print only what needs reading.

    python3 gates.py cases/<id> [--skip NAME ...] [--verbose]

Each check stays a standalone CLI; this is a runner, not a replacement.
It exists for the lead's context budget: six separate calls print every
live URL and every intact seal, while the gate decision only needs the
lines that are not a clean pass. So per check it prints one status line,
then — unless the check passed cleanly — its non-`OK:` lines.

Status, per check:

  PASS    exit 0, nothing but OK lines
  WARN    exit 0 with warning / gated / unverified-anchor lines — a
          judgment call under the check's sub-code
  NOTICE  exit 0 with a notice/note — *not checked*, never *passed*
  FAIL    exit 1 — a proven defect; route it by sub-code
  ERROR   any other exit (usage, missing file) — the check did not run
  SKIP    not applicable (prosecheck when report_language is not ja)
          or skipped by --skip

The runner never upgrades or downgrades a check's verdict: it reads the
exit code and the line prefixes the checks already print. Exit status is
1 if any check FAILed or ERRORed, else 0.
"""

import importlib.util
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# (name, script, argument kind) — step-7 order: chain first, since a
# tampered evidence base makes every later answer moot.
CHECKS = [
    ("chain", "chain.py", "verify"),
    ("urlcheck", "urlcheck.py", "report"),
    ("quotecheck", "quotecheck.py", "report"),
    ("versioncheck", "versioncheck.py", "case"),
    ("linkcheck", "linkcheck.py", "report"),
    ("prosecheck", "prosecheck.py", "case"),
]
WARN_PREFIXES = ("warning:", "gated:", "unverified-anchor:")
NOTICE_PREFIXES = ("notice:", "note:")


def report_language(case_dir):
    """report_language as prosecheck.py reads it, so the two never disagree
    about whether the Japanese check applies."""
    spec = importlib.util.spec_from_file_location("prosecheck", HERE / "prosecheck.py")
    prose = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(prose)
    return prose.report_language(case_dir)


def classify(returncode, lines):
    if returncode == 1:
        return "FAIL"
    if returncode != 0:
        return "ERROR"
    if any(l.startswith(NOTICE_PREFIXES) for l in lines):
        return "NOTICE"
    if any(l.startswith(WARN_PREFIXES) for l in lines):
        return "WARN"
    return "PASS"


def run_check(script, kind, case_dir):
    report = case_dir / "results" / "synthesis.md"
    if kind == "verify":
        args = ["verify", str(case_dir)]
    elif kind == "report":
        args = [str(report)]
    else:
        args = [str(case_dir)]
    proc = subprocess.run(
        [sys.executable, str(HERE / script)] + args,
        capture_output=True,
        text=True,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, [l for l in out.splitlines() if l.strip()]


def main(argv):
    args = argv[1:]
    verbose = "--verbose" in args
    skip = set()
    positional = []
    i = 0
    while i < len(args):
        if args[i] == "--verbose":
            pass
        elif args[i] == "--skip" and i + 1 < len(args):
            skip.add(args[i + 1])
            i += 1
        else:
            positional.append(args[i])
        i += 1
    if len(positional) != 1:
        print("usage: gates.py cases/<id> [--skip NAME ...] [--verbose]")
        return 2
    case_dir = Path(positional[0])
    if not case_dir.is_dir():
        print(f"error: no such case directory: {case_dir}")
        return 2

    tally = {}
    for name, script, kind in CHECKS:
        if name in skip:
            status, lines = "SKIP", ["skipped by --skip"]
        elif name == "prosecheck" and report_language(case_dir) != "ja":
            status, lines = "SKIP", ["report_language is not ja"]
        else:
            rc, lines = run_check(script, kind, case_dir)
            status = classify(rc, lines)
        tally.setdefault(status, []).append(name)

        if status == "PASS" and not verbose:
            print(f"{name:<14}PASS  {lines[-1] if lines else ''}")
            continue
        print(f"{name:<14}{status}")
        shown = lines if verbose else [l for l in lines if not l.startswith("OK: ")]
        for line in shown:
            print(f"  {line}")

    order = ["FAIL", "ERROR", "NOTICE", "WARN", "PASS", "SKIP"]
    summary = ", ".join(
        f"{len(tally[s])} {s} ({' '.join(tally[s])})" if s not in ("PASS", "SKIP")
        else f"{len(tally[s])} {s}"
        for s in order if s in tally
    )
    print(f"gates: {summary}")
    if "NOTICE" in tally:
        print("gates: a NOTICE means not checked, never passed")
    return 1 if ("FAIL" in tally or "ERROR" in tally) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
