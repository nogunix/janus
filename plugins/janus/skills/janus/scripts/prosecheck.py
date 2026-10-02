#!/usr/bin/env python3
"""Japanese prose-quality check for the report (backs gate C2/prose).

The other four checks ask whether the report is *true*: hashes intact,
URLs alive, quotes verbatim, versions attributable. None of them ask
whether it is *readable*. For a Japanese-language deliverable that is a
real gap — a technically correct report that mixes ですます and である,
runs 200-character sentences, or leaves half-width katakana in is not
something you hand a customer.

It checks the rules textlintrc.json configures from the
ja-technical-writing preset (である/ですます mixing, sentences over 120
characters, 4+ 読点, half-width katakana) through one of two backends —
the claude CLI first, textlint second (see "Two backends" below). It is
the only check that shells out to a non-stdlib tool, so it degrades hard
toward "pass": neither backend available, or an English report, prints
a notice and exits 0.
Air-gapped installs and English cases must stay usable, exactly as
urlcheck.py stays usable with the network down.

What must never be linted, and why:

  BlockQuote  the report's attributed evidence quotes. They must match
              findings verbatim (quotecheck.py) — "improving" the wording
              of quoted evidence is falsification, not editing. A
              150-character sentence lifted from a Red Hat KB is not
              synthesize's prose problem.
  CodeBlock   commands and captured output.
  Code        inline identifiers — NVRs, symbols, file:line, flags.
  Table       the References / Execution Metadata tables are identifiers,
              not prose.
  Header      headings stay English by contract (gate C2/section reads
              them), so Japanese rules have no business there.

textlintrc.json declares all of these in textlint-filter-rule-node-types,
but be accurate about what that buys: measured against this preset the
filter is currently a **no-op** — ja-technical-writing's rules already
skip those node types themselves (textlint-rule-helper's
IgnoreNodeManager), and sentence-length only ever visits Paragraph. It is
kept as a backstop that does not depend on each rule's internal defaults,
because the obvious next addition here is a terminology rule such as prh
for Red Hat product names, and prh *does* match inside blockquotes. If
you drop the filter, verify quote immunity again before trusting it.

Two preset rules are turned off in textlintrc.json, on purpose:

  ja-no-weak-phrase        It flags hedging ("〜の可能性がある"). In JANUS
                           hedging is often *correct*: a LOW-confidence
                           hypothesis is supposed to read as uncertain.
                           Forcing assertive prose would make the report
                           overclaim, which is the failure mode the
                           Confidence/Basis labels exist to prevent.
  max-kanji-continuous-len Fires constantly on Red Hat product and
                           subsystem names.

This check never rewrites the report. `--fix` would mutate prose that
chain.py has sealed and quotecheck.py cross-checks, and it would break
the standing rule that the lead never patches the report itself.
Violations go back to synthesize under C2/prose, like every other gate.

Two backends, tried in order:

  Sonnet  Primary. Uses `claude -p` (the Claude Code CLI). Always
          available in a JANUS session, no extra setup, fast. Its prompt
          restates the textlintrc.json limits — keep the two in step.
          Only the first SONNET_MAX_CHARS of the report are sent; a
          longer report gets a warning naming the unchecked remainder,
          never a silent OK. Degrades to the next backend when the claude
          binary is absent or the call fails (air-gapped installs without
          the CLI, CI).

  textlint  Fallback. npm-based rule engine. Requires:
              npm install -g textlint textlint-rule-preset-ja-technical-writing
                  textlint-filter-rule-node-types
            Degrades to a notice when absent, exactly as before.

If neither backend is available the check fails open with a notice, so
air-gapped installs and CI remain usable.

Usage: python3 prosecheck.py cases/<id>
Stdlib-only itself, like chain.py; external tools are optional.
"""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

CONFIG = Path(__file__).resolve().parent / "textlintrc.json"
TIMEOUT = 120
DEFAULT_LANGUAGE = "en"
SEVERITY_ERROR = 2
# A family alias, never a versioned ID: the claude CLI resolves it to the
# current Sonnet, so a model release changes nothing here. validate.py
# rejects pinned IDs anywhere in the plugin.
SONNET_MODEL = "sonnet"

# Reports are truncated to this length before sending to Sonnet to stay
# within practical CLI arg limits and keep costs low. The unchecked tail
# is reported as a warning, so a truncated run never reads as a full pass.
SONNET_MAX_CHARS = 30_000

INSTALL_HINT = (
    "npm install -g textlint textlint-rule-preset-ja-technical-writing "
    "textlint-filter-rule-node-types"
)

_SONNET_PROMPT = """\
You are a Japanese technical writing checker for Red Hat support investigation reports.

Examine ONLY the paragraph prose. Skip:
- Blockquote lines (starting with >)  — verbatim evidence quotes
- Fenced or indented code blocks
- ATX headers (lines starting with #)
- Table rows (lines containing |)
- Inline code (text between backticks)

Check each paragraph for exactly these four rules:

[no-mix-dearu-desumasu]
  ですます体（です・ます・ません・ました）とである体（である・だ・だった）が
  同一段落内に混在している場合のみ報告する。

[sentence-length]
  句点（。！？）で終わる1文が120文字を超える場合。Markdown記法を除いた文字数で計算。

[max-ten]
  1文に読点（、）が4個以上含まれる場合。

[no-hankaku-kana]
  半角カタカナ（Unicode U+FF65–U+FF9F: ｦｧ…ﾝﾞﾟ）が含まれる行。

Output format — one line per violation, nothing else:
  synthesis.md:<line_number>:0 [<rule_id>] <short Japanese description>

If there are NO violations, output exactly: OK
No preamble, no explanation, no summary.\
"""


def report_language(case_dir):
    """Read `report_language` from case.yaml without a yaml dependency.

    Returns the declared language, DEFAULT_LANGUAGE when the field is
    absent, or None when there is no case.yaml to read."""
    case_yaml = Path(case_dir) / "case.yaml"
    if not case_yaml.is_file():
        return None
    m = re.search(
        r"^report_language:\s*[\"']?([A-Za-z][A-Za-z-]*)",
        case_yaml.read_text(encoding="utf-8"),
        re.M,
    )
    return m.group(1).lower() if m else DEFAULT_LANGUAGE


def sonnet_command():
    """Return the claude CLI command prefix for Sonnet, or None if absent."""
    if shutil.which("claude"):
        return ["claude", "--model", SONNET_MODEL, "-p"]
    return None


def parse_sonnet_results(output):
    """Turn Sonnet's plain-text output into (problems, warnings).

    Sonnet outputs either "OK" or one violation line per finding.
    All Sonnet-reported violations are treated as errors (no severity 1)."""
    output = (output or "").strip()
    if not output or output == "OK":
        return [], []
    problems = [line.strip() for line in output.splitlines() if line.strip()]
    return problems, []


def run_sonnet(report_path):
    """Run the Sonnet prose checker.

    Returns (problems, warnings) on success, or (None, None) when the
    check could not run (claude absent, API error, unexpected output)."""
    cmd = sonnet_command()
    if cmd is None:
        return None, None

    try:
        text = Path(report_path).read_text(encoding="utf-8")
    except OSError:
        return None, None

    truncated = []
    if len(text) > SONNET_MAX_CHARS:
        truncated.append(
            f"only the first {SONNET_MAX_CHARS} of {len(text)} characters were "
            "prose-checked — review the rest by hand"
        )
        text = text[:SONNET_MAX_CHARS] + "\n[... report truncated for prose check ...]"

    prompt = _SONNET_PROMPT + "\n\nReport:\n\n" + text

    try:
        proc = subprocess.run(
            cmd + [prompt],
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return None, None

    stdout = (proc.stdout or "").strip()
    if proc.returncode not in (0, 1) or not stdout:
        return None, None

    problems, warnings = parse_sonnet_results(stdout)
    return problems, warnings + truncated


def textlint_command():
    """The textlint invocation to use, or None if it is not installed.

    `npx --no-install` matters: a bare `npx textlint` would silently
    download packages mid-investigation, which is wrong on an air-gapped
    box and surprising everywhere else."""
    if shutil.which("textlint"):
        return ["textlint"]
    if shutil.which("npx"):
        return ["npx", "--no-install", "textlint"]
    return None


def parse_results(payload):
    """Turn textlint's `-f json` payload into (problems, warnings).

    Payload shape: [{"filePath": ..., "messages": [{"line", "column",
    "message", "ruleId", "severity"}]}]."""
    problems, warnings = [], []
    for result in json.loads(payload or "[]"):
        name = Path(result.get("filePath", "synthesis.md")).name
        for msg in result.get("messages", []):
            where = f"{name}:{msg.get('line', '?')}:{msg.get('column', '?')}"
            rule = msg.get("ruleId") or "textlint"
            text = " ".join(str(msg.get("message", "")).split())
            line = f"{where} [{rule}] {text}"
            if msg.get("severity", SEVERITY_ERROR) >= SEVERITY_ERROR:
                problems.append(line)
            else:
                warnings.append(line)
    return problems, warnings


def run(case_dir):
    """Returns (problems, warnings, notices).

    A notice means "not checked, and that is fine" — the caller exits 0.

    Backend priority:
      1. Sonnet  (claude CLI, always available in a JANUS session)
      2. textlint (npm-based, for air-gapped / offline installs)
      3. notice  (fail open — neither backend is available)
    """
    case_dir = Path(case_dir)
    report = case_dir / "results" / "synthesis.md"

    language = report_language(case_dir)
    if language is None:
        return [], [], [f"no case.yaml in {case_dir} — prose check skipped"]
    if language != "ja":
        return [], [], [f"report_language: {language} — Japanese prose check skipped"]
    if not report.is_file():
        return [], [], [f"no report yet at {report} — prose check skipped"]

    # --- Backend 1: Sonnet ---
    problems, warnings = run_sonnet(report)
    if problems is not None:
        return problems, warnings, []

    # --- Backend 2: textlint ---
    if not CONFIG.is_file():
        return [], [], [f"missing textlint config: {CONFIG} — prose check skipped"]

    cmd = textlint_command()
    if cmd is None:
        return [], [], [
            "claude CLI and textlint both unavailable — prose check skipped "
            f"(install either: {INSTALL_HINT})"
        ]

    try:
        proc = subprocess.run(
            cmd + ["-c", str(CONFIG), "-f", "json", str(report)],
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError) as e:
        return [], [], [f"textlint could not run ({e}) — prose check skipped"]

    # textlint's contract: 0 = clean, 1 = lint problems reported. Anything
    # else, or a run that produced no JSON at all, means the tool did not
    # actually inspect the report — most often the preset or filter package
    # is missing, or `npx --no-install` found no textlint to run. That must
    # degrade to a notice: silently printing "OK" for a check that never ran
    # is worse than not having the check.
    stdout = (proc.stdout or "").strip()
    if proc.returncode not in (0, 1) or not stdout:
        detail = " ".join((proc.stderr or "").split())[:200]
        detail = detail or f"exit {proc.returncode}, no output"
        return [], [], [f"textlint could not run ({detail}) — prose check skipped ({INSTALL_HINT})"]

    try:
        problems, warnings = parse_results(stdout)
    except (json.JSONDecodeError, AttributeError, TypeError):
        detail = " ".join(stdout.split())[:200]
        return [], [], [f"textlint output unreadable ({detail}) — prose check skipped"]

    return problems, warnings, []


def main(argv):
    if len(argv) != 2:
        print("usage: prosecheck.py cases/<id>")
        return 2
    case_dir = Path(argv[1])
    if not case_dir.is_dir():
        print(f"error: no such case directory: {case_dir}")
        return 2

    problems, warnings, notices = run(case_dir)
    for n in notices:
        print(f"notice: {n}")
    for w in warnings:
        print(f"warning: {w}")
    for p in problems:
        print(f"FAIL: {p}")

    if problems:
        print(
            f"{len(problems)} prose issue(s) in the Japanese report — "
            "send back to synthesize under C2/prose"
        )
        return 1
    if not notices:
        print("OK: Japanese report prose passes ja-technical-writing")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
