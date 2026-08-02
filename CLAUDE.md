# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A Claude Code **plugin marketplace** containing one plugin (`janus`) — an
OpenShift/RHEL/CNV research & investigation pipeline. There is no
application to build and no third-party dependencies: the deliverable is
prompts (Markdown) plus a handful of stdlib-only Python scripts. Editing
this repo means editing agent/skill prompts far more often than code.

## Commands

```bash
python3 scripts/validate.py    # repo consistency checks — run before every commit
python3 scripts/selftest.py    # offline self-tests for the plugin's bundled scripts
```

`.github/workflows/ci.yml` runs exactly these two on every push and PR.
Both are stdlib-only and offline (no network, no MCP servers).

`selftest.py` has no test filter. To run one test function in isolation
(`test_chain`, `test_lock`, `test_quotecheck`, `test_urlcheck`,
`test_versioncheck`):

```bash
python3 -c "
import importlib.util
spec = importlib.util.spec_from_file_location('st', 'scripts/selftest.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
m.test_chain(); print('failures:', m.failures)
"
```

The four integrity scripts are also CLIs, run against a case directory:

```bash
python3 plugins/janus/skills/janus/scripts/chain.py verify cases/<id>
python3 plugins/janus/skills/janus/scripts/chain.py seal|lock|unlock cases/<id> [file ...]
python3 plugins/janus/skills/janus/scripts/quotecheck.py cases/<id>/results/report.md
python3 plugins/janus/skills/janus/scripts/urlcheck.py cases/<id>/results/report.md
python3 plugins/janus/skills/janus/scripts/versioncheck.py cases/<id>
```

## Tracked repo vs. local state — read this before editing

`.gitignore` excludes `/.claude/`, `/cases/`, `/labs/`, `/review-queue/`,
`/intake/`, `/docs/`, `/tools/`, `/schema/`, `/teams/`. Only
`plugins/janus/`, `scripts/`, `.claude-plugin/`, `.github/`, and the
top-level docs actually ship.

This matters constantly: `.claude/agents/` holds ~20 agent files from the
local install and full-history branch, while **only the 10 files in
`plugins/janus/agents/` are the plugin**. Editing `.claude/agents/*.md`
changes nothing that ships. Same for `.claude/skills/janus-lessons/` —
that is deliberately project-local (plugin updates must never overwrite
it), not a plugin skill.

## Architecture

Claude Code itself is the runtime. The **lead session** (driven by
`plugins/janus/skills/janus/SKILL.md`, the `/janus` skill) orchestrates;
each agent in `plugins/janus/agents/` is one **stage**. Stages never call
each other — they are connected only by files on disk.

```
{ doc-search, source-trace, crash-analyze,
  iac-author | [human-approved] lab-verify } | synthesize
```

- **`cases/<id>/findings/<stage>.md` is the data plane.** Every stage
  writes its findings file first, *then* sends a completion message; the
  lead treats the file on disk — not the message — as the completion
  signal. A universal finding format (YAML frontmatter + `F<N>:` blocks
  with Confidence/Basis/Ref) is what makes stages composable.
- **github-trace and jira-trace are conditional follow-ups**, launched at
  fan-in when another stage surfaces a PR/issue or Jira key it cannot
  open. Include them up front only if the case question itself names one.
- **source-trace is opportunistic** — casket-mcp is unpublished and
  environment-specific, so most installs lack it. Its absence is the
  normal state: drop the stage silently, do not treat the case as
  degraded.
- **iac-author and lab-verify are one lab split at the execution
  boundary.** Authoring IaC changes no infrastructure, so iac-author is
  static and autonomous; applying it is the whole of lab-verify, behind
  the approval gate, via explicit Bash so the command lands in `audit/`
  and the evidence chain. Agent tool grants for the terraform/ansible MCP
  servers are **enumerated, never wildcarded**, and the two executing
  ansible tools (`ansible_navigator`, `ade_setup_environment`) are granted
  to no agent — `validate.py`'s `validate_tool_grants()` fails the build
  otherwise. `mcp__terraform__*` is barred because that server gains
  `create_run`/`apply_run` once a user enables its enterprise tools.
- **self-improver and upstream-adviser sit outside the pipeline**, feeding
  human-gated proposals into `review-queue/`. Both are advisory —
  upstream-adviser never opens an issue or PR itself.

Model assignment is per stage and deliberate (sonnet for search/tracing,
opus for crash-analyze / lab-verify / synthesize); see the Model strategy
table in `SKILL.md` before changing it.

### Quality is enforced by mechanism, not by the model

The central design premise is that investigation quality must survive a
model swap. Understanding these before editing agent prompts avoids
accidentally removing load-bearing discipline:

- **Basis labels** — `VERIFIED | REASONED | ASSUMED`, promoted only by new
  evidence. A HIGH-confidence hypothesis needs a VERIFIED finding behind it.
- **Two judgment gates at handoff** — C1 GROUNDING and C2 COMPLETENESS &
  FIDELITY. Failures go back to synthesize by *sub-code* (`C1/basis`,
  `C1/url`, `C2/quote-absent`, `C2/version`, …); the same sub-code failing
  twice escalates to NEEDS_HUMAN. Sub-codes carry the diagnostic
  granularity of the seven gates they replaced in 0.17.0 — keep them named.
- **Four mechanical pre-checks** back those gates: `chain.py` (append-only
  hash ledger making edits visible, plus `lock` freezing the fact base at
  fan-in), `quotecheck.py` (report quotes must appear verbatim in the
  finding they cite), `urlcheck.py` (dead citations), `versioncheck.py`
  (version-provenance drift).
- **Hooks in `plugins/janus/hooks/`** enforce this at tool level:
  `secret-safety.py` and `evidence-lock.py` are PreToolUse denies;
  `evidence-chain.py` is a PostToolUse auto-seal.

Checks are deliberately fail-open where they cannot prove a negative — an
SSO-gated URL is classified `gated` rather than passed or failed, and a
fully unreachable network downgrades to a notice so air-gapped installs
stay usable. Preserve that property when touching them.

## Conventions

- **Reusable knowledge is inlined into agents on purpose** — okp-mcp
  mechanics, for instance, live both in `skills/okp-doc-search/SKILL.md`
  and in `agents/doc-search.md`, and the pipeline stage reads the *agent*.
  Fixing only the skill does not reach the pipeline (that was 0.20.1 →
  0.20.2). `validate.py` now treats the skill's doc_id table as the source
  of truth and fails when the agent lacks a format from it, plus rejects a
  list of retired okp-mcp claims across all agents and skills.
- **`validate.py` enforces SKILL.md ↔ `agents/` sync**: a stage named in
  SKILL.md must have `agents/<stage>.md`, and every agent file must be
  mentioned in SKILL.md. Adding or removing a stage is a multi-file change
  — agent file, SKILL.md, README (including the agent *count* in prose),
  and `plugin.json`'s description.
- **Versioning**: bump `plugins/janus/.claude-plugin/plugin.json` and add a
  `CHANGELOG.md` entry in the same commit — these have drifted before.
  Commit subject style: `<area>: <summary> (<version>)`, e.g.
  `source-trace: comment≠fact + snapshot-pinned line numbers (0.19.1)`.
  Omit the version for changes that do not bump the plugin.
- **Language**: agent-to-agent content (SKILL.md, agent prompts, findings
  format) is written in English; human-facing prose may be Japanese.
- **Scripts stay stdlib-only and offline-testable** — that is why CI needs
  no install step.
- `plugins/janus/.mcp.json` is intentionally empty. MCP server paths are
  machine-specific and users register them; do not commit server config.
- `plugins/janus/skills/deck/template/` is gitignored (a licensed brand
  template). The deck skill must keep working with any user-supplied
  `.pptx`.

## Safety invariants

Read-only by default. Dead-artifact analysis (vmcore, coredump) is
autonomous-safe; anything touching a live target (lab provisioning,
dynamic tracing, GDB attach) requires explicit human approval via
`review-queue/APPROVE_<id>.md` and runs on a disposable lab, never
production. In `skills/ocp-triage-heuristics/SKILL.md`, every item is
tagged 🔍 DIAGNOSTIC or ⚠️ REMEDIATION — remediation items are
report-only, since JANUS never mutates cluster state autonomously. The
final root-cause call belongs to the human.
