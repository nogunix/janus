---
name: janus
description: >-
  Autonomous research & investigation pipeline for OpenShift / RHEL /
  OpenShift-Virtualization (CNV/KubeVirt). Case types: kernel crash &
  forensics (vmcore / panic / Oops / OOM / hung-task / guest crash, via
  drgn), upgrade & cross-version compatibility analysis, CVE/errata impact
  assessment, operator/component behavior investigation, release diffing.
  Correlates symptoms with CVE/errata/KB via okp (plus versioned-source
  tracing when a source-index server is registered), and produces a
  ranked-hypothesis report handed off to a human review queue.
  Read-only, sandboxed; never spoofs guardrails. Triggers: "vmcoreを解析", "このpanicの原因", "OOM調査",
  "アップグレード互換性を調査", "CVEの影響評価", "オペレータの挙動を調査",
  "バージョン間の差分を調査".
---

# JANUS — OpenShift research & investigation pipeline

Investigate an OpenShift / RHEL / CNV question — a kernel crash, an
upgrade-compatibility concern, a CVE impact, a component behavior — and lay
**evidence, ranked hypotheses, and repro steps** on the table for a human to
decide. The lead (this session) acts as the Unix shell: it composes a
pipeline of small agent stages connected by a universal finding format,
gates the dynamic stages, and quality-checks the report. **The human makes
the final call.**

Design principle: **Unix philosophy** — one tool, one job. Connect via
text streams (`findings/`). Compose small tools. The shell (lead) only
connects, it does not process.

```
{ doc-search, source-trace, crash-analyze, iac-author | [approve] lab-verify } | synthesize [| localize]
```

`localize` runs only when `report_language` ≠ `en`.

## Pipeline stages

| Stage | Role | Output | Tools | Safety | Model |
|---|---|---|---|---|---|
| **doc-search** | Red Hat docs/CVE/KB/Slack search (+ Microsoft Learn for ARO/Azure, AWS docs for ROSA/AWS) | findings/doc-search.md | okp-mcp + rh-api-mcp + slack + mslearn + aws | Static | sonnet |
| **source-trace** | Version-specific source tracing | findings/source-trace.md | casket-mcp (optional) | Static | sonnet |
| **github-trace** | Upstream GitHub PR/issue/commit deep-dive | findings/github-trace.md | github MCP (read-only) | Static | sonnet |
| **jira-trace** | Jira ticket deep-dive (RHEL-/OCPBUGS-/CNV-…) | findings/jira-trace.md | atlassian (Rovo MCP, read-only) | Static | sonnet |
| **crash-analyze** | vmcore/coredump analysis | findings/crash-analyze.md | drgn-mcp + gdb | Static | opus |
| **iac-author** | Authors + statically validates the lab's IaC | findings/iac-author.md + `iac/` | terraform-mcp + ansible-mcp (authoring subset) | Static | sonnet |
| **lab-verify** | Live cluster verification | findings/lab-verify.md | oc, terraform CLI, bpftrace, linux-mcp | Dynamic | opus |
| **synthesize** | All findings → English report | results/synthesis.md (en) or results/synthesis-en.md (ja) | Read only | Static | sonnet |
| **localize** | English report → Japanese report | results/synthesis.md | Read only | Static | sonnet |

github-trace and jira-trace are normally **conditional follow-up
stages**: the lead launches them at fan-in when another stage's
findings reference a GitHub PR/issue/commit or a Jira ticket that no
other stage can open (doc-search has only okp/slack; source-trace only
casket, plus fetching a fix's diff for `check_patch_shipped`). Include one up front only when the case question itself names
an upstream PR/issue or a Jira key.

source-trace is **opportunistic**: casket-mcp is an environment-specific
server ([ocp-source-collector](https://github.com/nogunix/ocp-source-collector)),
so not every install has it. When the
preflight (step 1) finds no `casket` server connected, drop source-trace
silently — its absence is the normal state, not an error. Note it once
as a gap in the report; do not surface setup instructions or treat the
case as degraded.

iac-author and lab-verify are **one lab, split at the execution
boundary**. Writing a `.tf` or a `.yml` touches nothing, so iac-author is
static and runs in the normal fan-out with no approval; *applying* that
code is the whole of lab-verify and stays behind
`review-queue/APPROVE_<id>.md`. This is also why they are written
`iac-author | [approve] lab-verify` — a serial pipe inside the fan-out:
when both are composed, lab-verify must not start Phase 2 until
`cases/<id>/iac/` and `findings/iac-author.md` exist. iac-author is
worth composing on its own (`tracks: [iac]`) when the deliverable is
reproducible, customer-presentable IaC rather than a lab run.

The executing ansible-MCP tools (`ansible_navigator`,
`ade_setup_environment`) are granted to no stage, and terraform grants
are enumerated, never `mcp__terraform__*` — `scripts/validate.py`
enforces both. lab-verify executes IaC only as explicit Bash commands so
the invocation lands in `audit/` and the evidence chain.

## Periodic agents (outside the pipeline)

| Agent | Trigger | Role | Model |
|---|---|---|---|
| **self-improver** | 10 accumulated verdict.md files, or weekly | Metrics computation, improvement proposals | sonnet |
| **upstream-adviser** | After a high-confidence report, or periodic | Drafts upstream contribution proposals | sonnet |

## What the lead does directly (shell functions)

- Intake, case creation (`case.yaml`), and pipeline composition
- Presenting the pipeline and obtaining approval
- Fanning stages out and fanning them in
- Quality checks and handoff
- Triggering improvement proposals (self-improver)
- Triggering upstream contribution (upstream-adviser)
- Editing the team definition

## Case directory

```
cases/<id>/
  case.yaml
  artifacts/
  audit/
  iac/               ← iac-author writes, lab-verify executes (outside the
                       evidence chain, like artifacts/ — it holds tfstate)
  findings/          ← the pipeline's data plane
    doc-search.md
    doc-search-*-supplement.md  ← lead-written supplements (see 5a)
    source-trace.md
    github-trace.md  ← usually a conditional follow-up
    crash-analyze.md
    iac-author.md
    lab-verify.md
  results/
    synthesis.md     ← synthesize's final output
  verdict.md         ← human post-hoc evaluation
  chain.jsonl        ← append-only evidence hash ledger (see Evidence chain)
```

### case.yaml (written by the lead at intake — stages only read it)

The **lead creates `cases/<id>/case.yaml` at intake**: it assigns the case
ID, classifies the case type, and records what the stages need. No stage
ever writes it.

Required fields: `id`, `received_at`, `mode` (`artifact` | `theme`),
`status` (`intake` / `scheduled` / `in_progress` / `needs_human` / `done` /
`failed`). `mode: artifact` additionally requires `artifacts.vmcore`;
`mode: theme` requires `theme`. The `tracks` field drives pipeline
composition (below). Real binaries (vmcore/vmlinux) are never committed to
git — only `case.yaml` and the directory structure are tracked.

Optional but recommended when the case is version-specific:
`version_scope` — the product version(s) the investigation is about,
grouped by product. It is the anchor `versioncheck.py` (Step 7) uses to
flag findings and report claims that drift onto a neighbouring version.
A scope entry matches its own z-streams (`4.16` covers `4.16.55`):

```yaml
version_scope:
  OCP: ["4.20"]
  RHEL: ["9.6"]
```

Absent it, versioncheck still hard-fails an unpinned source citation but
skips the scope/attribution warnings — so declare it whenever the case
turns on one version rather than a whole family.

`report_language` — `en` (default) or `ja`, the language synthesize
writes the report's **prose** in. Headings, table headers and the label
vocabulary stay English in both modes: gate C2/section and the mechanical
checks read them by name, so translating a heading breaks a gate. Set
`ja` when the deliverable goes to a Japanese-speaking reader; it also
switches on `prosecheck.py` (Step 7).

---

## Pipeline composition

The `tracks` field in `case.yaml` determines which stages run.

| tracks | Pipeline |
|---|---|
| `[documentation, source]` | `{ doc-search, source-trace } \| synthesize` |
| `[documentation, source, debug]` | `{ doc-search, source-trace, crash-analyze } \| synthesize` |
| `[documentation, source, debug, sno\|vm]` | `{ doc-search, source-trace, crash-analyze, iac-author \| [approve] lab-verify } \| synthesize` |
| `[iac]` | `iac-author \| synthesize` — reproducible IaC as the deliverable, no lab run |
| `[source]` | `source-trace \| synthesize` |
| `[debug]` | `crash-analyze \| synthesize` |
| `[documentation, source, github]` | `{ doc-search, source-trace, github-trace } \| synthesize` |
| `[documentation, source, jira]` | `{ doc-search, source-trace, jira-trace } \| synthesize` |

- `{ }` = parallel fan-out (each stage launched simultaneously as a background Agent)
- `|` = serial pipe (wait for the prior stage to fully complete before starting the next)
- `[approve]` = safety gate (skipped without human approval)

The `github` / `jira` tracks are set at intake only when the case
question itself names an upstream PR/issue or a Jira key. Otherwise
github-trace / jira-trace join dynamically as gap-driven follow-ups at
fan-in (step 5).

---

## Shell rules (how the lead operates)

### 1. Intake: read/derive the case and decide the composition

Read (or, for a new case, create) `case.yaml` and derive:

```
tracks = the tracks field in case.yaml
mode = artifact → includes crash-analyze
       theme → does not include crash-analyze (unless debug is explicit in tracks)
```

Then check each composed stage's required MCP server with
`claude mcp list` (`✔ Connected` — a tool being advertised is not the
server being reachable): doc-search → okp-mcp (+ rh-api-mcp for live
errata), source-trace → casket, github-trace → github, jira-trace →
atlassian, crash-analyze → drgn, iac-author → terraform and/or
ansible, lab-verify → linux.
A stage whose server is not connected is **dropped from the composition
and recorded as a gap** (note it in the step-2 presentation; synthesize
reports it under Investigation Gaps) — never launched to fail at
runtime. iac-author is the one exception to the all-or-nothing rule: it
runs with **either** `terraform` or `ansible` connected, in reduced
scope, recording the missing half as a gap; drop it only when neither is
there. Without `terraform` its version pins are REASONED at best, and it
must label them so. rh-api-mcp is optional for doc-search: okp-mcp alone
is sufficient to run the stage, but when rh-api-mcp is not connected
doc-search records the absence as a gap in cases where live errata lookup
would have strengthened a finding.

### 2. Present the pipeline to the human

```
Pipeline for <case-id>:
  { doc-search, source-trace } | synthesize

  Static (autonomous): doc-search (sonnet), source-trace (sonnet)
  Dynamic (needs approval): none
  → Proceed?
```

Once the human approves (or amends), go to step 3.

### 3. Fan out the static stages

Launch the approved pipeline's static stages simultaneously as
background Agents.

Brief for each stage:
- Case directory path: `cases/<id>/`
- Output contract: write to `cases/<id>/findings/<stage>.md`, then SendMessage
- On failure: write `status: partial` or `failed` in the YAML frontmatter and notify
- Any janus-lessons entries relevant to this case and stage (see
  Learning loop below) — copied in, not referenced by path
- For OpenShift-domain symptoms (cluster/operator/node/upgrade), the
  relevant `ocp-triage-heuristics` sections — copied into the briefs of
  investigation-planner, lab-verify, live-tracer, doc-search and
  synthesize (see Reference assets below). Preserve the 🔍/⚠️ tags:
  ⚠️ remediations are report-only recommendations, never executed
  autonomously
- doc-search only, by platform: an ARO / Azure case gets the absolute
  path of `references/doc-search-azure.md`, a ROSA / AWS case (or one
  deploying GPU / large-model serving on a lab) gets
  `references/doc-search-aws.md` — each with "Read this file before any
  call to that layer's tools". A case touching neither gets neither;
  doc-search then never loads that knowledge.

**Copy this stage contract verbatim into every stage brief**, with
every placeholder — `<id>`, `<stage>`, `<skill-dir>` (absolute path) —
replaced by its real value (agent definitions can be skimmed; the brief
is always read). A brief is plain text handed to the Agent tool, never
shell-expanded: `$(cat …)` or `$VAR` reaches the stage literally, so
paste values and command output, not expressions that would produce
them. Its mechanical half — frontmatter
keys, Confidence / Basis / Ref on every finding, no HIGH on ASSUMED —
is enforced by `findings.py lint`, so the contract spends its words on
the judgment half:

```
Stage contract:
1. Write cases/<id>/findings/<stage>.md FIRST, then run
   python3 <skill-dir>/scripts/findings.py lint cases/<id>/findings/<stage>.md
   and fix every FAIL before SendMessage (a completion notice, not the
   result). Create and change findings/ and results/ files only with
   Write or Edit — never a shell redirect, heredoc or script. The
   evidence chain seals only Write/Edit; any other write to a sealed
   file reads as tampering and stops the case at NEEDS_HUMAN.
2. VERIFIED requires tool output you observed in this session. Never
   promote a Basis without new evidence.
3. A tool failure (timeout, unreachable, not indexed) or an unexplored
   layer/phase/angle is a Gap with a reason, never a Negative Result.
   Attempt at least one scoped fallback before recording either.
4. Negative results are evidence — report them explicitly.
```

### 4. Gate dynamic stages

If the pipeline has a dynamic stage:
1. Generate `review-queue/APPROVE_<id>.md` and present it to the human
2. Approved → launch lab-verify
3. Rejected → skip. This is passed to synthesize as a gap (no file in findings/)

When iac-author is also composed, it is lab-verify's input, so:

- Put the concrete plan into `APPROVE_<id>.md` — the backend, the pinned
  versions, the node topology, the estimated cost — by quoting
  iac-author's "What this builds" table. Approving a named, reviewable
  set of resources beats approving "a lab".
- **Do not launch lab-verify before `cases/<id>/findings/iac-author.md`
  exists**, even with approval in hand. The approval covers applying that
  code; there is nothing to apply yet. Human approval is never a reason
  to skip an input dependency.
- iac-author `status: failed`, or unresolved `TODO(iac-author)` markers →
  do not launch lab-verify. Send it back or record the gap.

### 5. Fan in (collect) — and gap-driven follow-up

**The findings file on disk is the authoritative completion signal.**
A stage is complete when `cases/<id>/findings/<stage>.md` exists with
frontmatter `status: complete | partial | failed` — not when a message
arrives. SendMessage and background-task completion notifications are
hints, and hints get lost (session restart, context compaction, the
lead being mid-turn). Therefore, on **every** wake while stages are
outstanding — a stage notification, or a periodic check — re-run:

```bash
ls cases/<id>/findings/*.md
```

and, once files are present, run the digest (below) rather than opening
them. Fan in as soon as
every composed stage has a file, **even if some completion notification
never arrived**. Never sit waiting for a message about a stage whose
file is already on disk.

- Expected file present → normal (whatever its status says)
- No file and the stage has been silent well past its expected duration
  (no running task, no partial output) → treat as failed: record it in
  `cases/<id>/audit/` and proceed without it

Then run the digest — **instead of reading the findings files**:

```bash
python3 <skill-dir>/scripts/findings.py digest cases/<id>
```

Per file it prints the frontmatter status line, one line per finding
(`F3 [HIGH/VERIFIED] <title>`), the **Gaps section** verbatim, and
`findings.py lint`'s verdicts (`lint: OK` for a clean file). Read it
from the command output — do not redirect it to a file; it is cheap to
rerun, and a lead scratch file belongs under `cases/<id>/`, never
`/tmp`. That is everything the routing decision
needs; the full files are synthesize's to read, not the lead's. Open a
file only when a Gaps line is ambiguous about which follow-up it needs.
A `lint FAIL` means the stage skipped its own lint: SendMessage it to
fix the file (nothing is locked before step 6); if it cannot, record
the failure in `audit/` and let synthesize see it as a gap.

Decide from the digest whether another stage can fill a gap before
synthesize runs:

| Gap signal in findings | Follow-up stage |
|---|---|
| GitHub PR/issue/commit referenced but not investigated | github-trace |
| Jira ticket (RHEL-/OCPBUGS-/CNV-…) referenced but not opened | jira-trace |
| casket phase/layer "unexplored (reason: ...)" | source-trace (re-run, scoped to that layer) |
| `release_diff` range handed off (`{owner, repo, base, head}`) — PRs / Jira keys behind it not yet read | github-trace |
| Symbol/version question raised by crash-analyze | source-trace |

- **Cap: at most 2 follow-up stages per case, one follow-up round.**
  Follow-ups launched by follow-ups are not allowed — if gaps remain
  after the round, they go to synthesize as gaps (and, if critical,
  `NEEDS_HUMAN_*`).
- Follow-up stages are static-track only. A gap can never promote a
  dynamic stage past its approval gate.
- Brief the follow-up with the specific gap it must fill and which
  finding raised it; it writes its own `findings/<stage>.md` like any
  stage.

### 5a. Lead-side supplemental searches

When a subagent stage fails to access an MCP server (API connection
error, session loss, server not propagated to the subagent), the lead
runs the supplemental searches directly and writes the results as
**supplement findings files**. This is the documented fallback — not
an exception.

**When to supplement (decision tree):**
1. A composed stage's subagent failed or returned `status: partial`
   with MCP gaps
2. The lead's own session has the MCP server connected
   (`claude mcp list` shows `✔ Connected`)
3. The gap is fillable by a search the lead can run now

**Supplement file conventions** (naming `<stage>-<source>-supplement.md`,
`supplement_of:` / `source:` frontmatter, finding numbers in fresh blocks
of 10 starting at F20): read `references/findings-format.md` before
writing one, and run `findings.py lint` on it afterwards — the lead's
supplements meet the same contract as a stage's file.

### 6. Launch synthesize

First close the evidence chain over the inputs synthesize will read:
`chain.py verify` then `chain.py seal` on the case dir (see **Evidence
chain** below — verify first, so a sealed file changed outside tracked
tools is noticed before it is re-sealed). Then freeze the fact base:
`chain.py lock cases/<id>` drops the write bits on `case.yaml`,
`findings/*.md` and `audit/*`, and a PreToolUse hook
(`hooks/evidence-lock.py`) denies tracked writes to locked files — from
here on the facts can be read, never rewritten. A genuinely needed
revision goes through the lead: `chain.py unlock cases/<id> <file>`,
edit, re-seal, `lock` again.

Before writing the brief, generate the anchor map that synthesize will
use for evidence links:

```bash
python3 <skill-dir>/scripts/anchors.py cases/<id>/findings/
```

Paste the full output, as text, as an `## Anchor Map` section at the
end of the synthesize brief — not a `$(cat …)` or a path to a file
(the brief is not shell-expanded; see step 3). This gives synthesize a deterministic, pre-computed
slug for every finding heading — it copies them verbatim instead of
computing slugs by hand (which breaks on version strings, Japanese
text, and punctuation). Slugs containing non-ASCII characters are
tagged `(file-only)` — synthesize must link to the file path alone
for those headings because non-ASCII slug generation is
renderer-dependent.

Instruct synthesize to read all of `findings/*.md` and write the
report. **Synthesize always writes in English:**

- `report_language: en` (or absent) → synthesize writes
  `results/synthesis.md` directly. Done.
- `report_language: ja` → synthesize writes `results/synthesis-en.md`
  (English draft). Then launch the **localize** step (see 6a below).

synthesize works with whatever findings exist — it reports missing ones
as gaps.

### 6a. Launch localize (only when `report_language` ≠ `en`)

After synthesize completes and `results/synthesis-en.md` exists, launch
the **localize** agent (`janus:localize` / `localize`). Include in
its brief:

1. The case directory path
2. The same **Anchor Map** from step 6 (or regenerate it)

localize reads `synthesis-en.md`, translates prose to Japanese, applies
the anchor map to all evidence links, and writes `results/synthesis.md`.

This two-pass process (English → Japanese) avoids the chronic
prosecheck failures that occur when synthesize writes Japanese
directly: English sentences are naturally short, and faithful
translation preserves that structure.

### 7. Quality check (the lead's own job) — named gates

Run the six mechanical pre-checks in one call:

```bash
python3 <skill-dir>/scripts/gates.py cases/<id>
```

It prints one status line per check — PASS / WARN / NOTICE / FAIL /
ERROR / SKIP — and, for anything but a clean PASS, only that check's
non-`OK:` lines. Exit 1 means a FAIL or an ERROR. The checks remain
standalone CLIs; rerun one directly (scripts live in
`<skill-dir>/scripts/`) after a fix, or with `gates.py --verbose` to see
every line. On any WARN or NOTICE, read `references/quality-gates.md`
before judging it — it holds each check's full behaviour and the **Fail
direction** table (what each check does when it cannot decide).

| # | Command | FAIL → |
|---|---|---|
| 1 | `chain.py verify cases/<id>` | evidence changed after sealing: record in `audit/`, write `review-queue/NEEDS_HUMAN_<id>.md` quoting the failing entries — never hand off |
| 2 | `urlcheck.py cases/<id>/results/synthesis.md` | dead citation (404/410, unresolvable host) → send back under **C1/url** |
| 3 | `quotecheck.py cases/<id>/results/synthesis.md` | mutated/fabricated quote → **C2/quote-mismatch**; "no attributed quotes" warning → **C2/quote-absent** for any evidence-backed report |
| 4 | `versioncheck.py cases/<id>` | unpinned source citation → **C2/version**; crossed/off-scope warnings are judged against C2/version |
| 5 | `linkcheck.py cases/<id>/results/synthesis.md` | local link to no file/anchor → **C1/link** (never fails open) |
| 6 | `prosecheck.py cases/<id>` | `report_language: ja` only — prose defect → **C2/prose** |

**A notice means *not checked*, never *passed*.** If the property matters
for the case, restore what the check needs (network, the claude CLI or textlint, a seal)
and rerun.

Read `results/synthesis.md` and check it against these two judgment gates
(the six mechanical pre-checks above already cover the rest). **A
failed gate = send the report back to synthesize, naming the sub-code
and quoting the offending line** — the lead never patches the report
itself. The sub-codes are the send-back vocabulary: they keep the
diagnostic granularity of the old seven gates while collapsing the
lead's read of the report into two passes.

| Gate | The one question | Sub-codes (send-back vocabulary) |
|---|---|---|
| **C1 — GROUNDING** | Is every claim anchored to evidence at the right strength? | `C1/ref` — a claim with no reference · `C1/url` — a resolvable-pattern ID (CVE/RHSA/KB/PR) with no public URL; dead URLs are caught mechanically by urlcheck.py · `C1/link` — a claim whose evidence the reader cannot click through to: a bare filename where a link belongs, or a local link that linkcheck.py proved resolves to no file or no anchor · `C1/basis` — a HIGH hypothesis without ≥1 VERIFIED or 2+ independent REASONED findings from different stages, or an unlabeled citation · `C1/spec` — an unsupported "likely / probably / should" claim · `C1/currency` — a recommended configuration, feature, flag, or API with no lifecycle check against the target version, so the report may prescribe a setting that is deprecated / removed / superseded in that release; send back to doc-search to confirm against official release notes and lifecycle docs · `C1/source-of-truth` — a load-bearing source-content claim (what the code does, that a fix or behavior is present) resting only on a GitHub URL while a `casket` server is connected: a live URL is not an accurate one, so the own-server source index must corroborate it; send back to source-trace, or downgrade and label the claim upstream-only |
| **C2 — COMPLETENESS & FIDELITY** | Is the report structurally complete, and are identifiers and quotes reproduced exactly? | `C2/section` — an empty Objectives Assessment or Execution Metadata cell · `C2/artifact` — a paraphrased concrete identifier (file, resource, symbol, version) · `C2/quote-absent` — an evidence-backed report with no attributed verbatim quotes; mutated quotes and fabricated attributions are caught mechanically by quotecheck.py and sent back as `C2/quote-mismatch` · `C2/version` — a fact attributed to the wrong product version: an unpinned source citation (FAIL) or a crossed / off-scope version that versioncheck.py flagged and the read confirms · `C2/prose` — a `report_language: ja` report whose prose fails the ja-technical-writing checks prosecheck.py runs (mixed である/ですます, over-long sentences, 4+ 読点, 半角ｶﾀｶﾅ). Style only: never send back under C2/prose for hedging — 「〜の可能性がある」 on a LOW-confidence hypothesis is correct writing, not weak writing |

**Send-backs are targeted revisions, not reruns.** The brief names the
report path, each sub-code, and the quoted offending line(s), and says
*revise in place* — synthesize then edits only those spots (its
Revision mode) instead of re-reading every finding and regenerating the
report. Route by where the defect lives:

- `report_language: en` → synthesize, on `results/synthesis.md`.
- `report_language: ja`, `C2/prose` → localize directly, on
  `results/synthesis.md` — the defect is in the translation.
- `report_language: ja`, any other sub-code → synthesize, on
  `results/synthesis-en.md` (quote the English counterpart of the
  offending line); then localize, briefed with the sections synthesize
  reported changing, re-translates only those.

After a revision, rerun just the checks that failed, then `gates.py`
once more before handoff.

Both gates pass → `review-queue/DONE_<id>.md`
The same sub-code fails twice on one report → stop the loop:
`review-queue/NEEDS_HUMAN_<id>.md` with both versions noted.

### What the lead does NOT do

- Read source (that's source-trace's job)
- Search documentation (that's doc-search's job)
- Chase GitHub PRs/issues (that's github-trace's job)
- Analyze crashes (that's crash-analyze's job)
- Write IaC (that's iac-author's job)
- Build labs (that's lab-verify's job)
- Write findings (each stage's own job)
- Write the report (that's synthesize's job)
- Intervene in a stage while it's running

---

## Inter-stage data format

Every stage writes `cases/<id>/findings/<stage>.md`: YAML frontmatter
(`stage`, `case`, `date`, `status: complete | partial | failed`, `model`
— what actually ran, or `unrecorded` — `tool_calls`, `duration_s`) and
`### F<N>:` blocks carrying Confidence / Basis / Type / Detail / Ref.
Basis is **VERIFIED** (tool output observed this session), **REASONED**
(inferred from something read) or **ASSUMED**; it is promoted only by new
evidence, and a HIGH finding on an ASSUMED basis is a contradiction. The
full schema and the per-source Ref formats are in
`references/findings-format.md`.

## Evidence chain (tamper-evidence)

`cases/<id>/chain.jsonl` is an append-only sha256 ledger over the
evidence set; `hooks/evidence-chain.py` auto-seals tracked writes, and
the lead runs `chain.py verify` → `seal` → `lock` at step 6 and `verify`
at step 7 (`seal` again after the human writes `verdict.md`). A FAIL is a
human matter, never something to quietly repair. Full semantics
(what is sealed, unsealed warnings, unlock/re-lock): read
`references/evidence-chain.md` when a chain command reports anything
other than OK.

## Safety (invariant)

- **Static stages are autonomous.** Dead-artifact analysis
  (vmcore/coredump), doc search, source tracing, and IaC *authoring* all
  run without human approval — writing infrastructure code changes no
  infrastructure.
- **Dynamic stages require human approval.** Live-target intervention (lab
  provisioning, strace/eBPF, gdb-attach) — the entirety of lab-verify —
  needs prior approval, obtained via `review-queue/APPROVE_<id>.md`.
  Disposable lab only.
- **Once approved, run end to end.** Once approved, lab-verify builds,
  verifies, and tears down autonomously (unless it deviates from the
  plan, in which case it stops).
- **No production, ever.** Every stage is read-only against production.
- **No remediation.** Stages identify root cause only; no
  writes/restarts/fixes applied autonomously — fixes are done by humans.
- **No guardrail spoofing.** On refusal, record it → degrade to the safe
  side → hand to the human. Never rewrite/re-send a prompt to bypass a
  classifier.
- **No secret material in context — enforced by hook.** The plugin ships
  a PreToolUse hook (`hooks/secret-safety.py`) that deterministically
  denies bulk secret dumps (`oc/kubectl get secret -o yaml|json`,
  `oc extract secret`, `aws secretsmanager get-secret-value`) and AWS
  support-case writes, in every stage and in the lead. Findings and
  reports are committed to git, so dumped credentials would persist
  there. Read a specific non-credential key with `-o jsonpath` if truly
  needed; a hook denial is a guardrail, not an obstacle — never
  restructure a command to slip past it.
- **No Terraform state in context.** `terraform.tfstate` /
  `*.tfstate.backup` routinely hold credentials in plaintext, and
  findings are committed to git. No stage reads or quotes them; a single
  value comes from `terraform output <name>`. `cases/<id>/iac/` therefore
  stays outside the evidence chain, as `artifacts/` does.
- **Provisioning happens in one place.** Only lab-verify applies IaC,
  only after approval, and only through explicit Bash commands recorded
  in `audit/` — never through an MCP tool that wraps the invocation.
- **Parallelism cap: 4 stages.** No more than 4 stages run concurrently
  even at full fan-out.
- **Sandbox**: drgn's `eval_expression` runs arbitrary Python — run it
  network-cut, read-only, unprivileged, with an external per-call timeout
  wrapper. Keep confidential vmcores out of the autonomous deep-tier loop
  unless that timeout is enforced. Keep vmcore/debuginfo under
  `cases/<id>/`, not `/tmp` (the sandbox's read-only protection does not
  reliably cover /tmp). The same holds for any scratch file the lead or
  a stage writes: script output is read from stdout, and anything that
  must persist goes under `cases/<id>/`.

## File-write-first rule

Stages **write the findings file first, then SendMessage** (paths in the
Pipeline stages table). The file on disk, not the notice, is the
completion signal (step 5).

## Model strategy

| Stage | Model | Rationale |
|---|---|---|
| doc-search | sonnet | Search and organization. Doesn't need heavy reasoning |
| source-trace | sonnet | Symbol tracing and diff extraction. Routine work |
| github-trace | sonnet | PR/issue reading and link following. Routine work |
| jira-trace | sonnet | Ticket reading and link following. Routine work |
| crash-analyze | opus | Needs heavy reasoning for the iterative hypothesis-test loop |
| iac-author | sonnet | Registry lookup and templating against a documented schema. The judgment — is this the right lab, is the cost worth it — sits with lab-verify and the human |
| lab-verify | opus | Needs heavy reasoning for verification judgment and trace interpretation |
| synthesize | sonnet | Structured input (YAML frontmatter + Basis labels); mechanical pre-checks enforce quality. Well-defined synthesis, not novel reasoning |
| localize | sonnet | Translation against a fixed anchor map, with the label vocabulary held in English. Mechanical, not interpretive |

This table is the **declared** assignment. Both ladders below substitute
a different model, and a substitution is a legitimate, unannounced event
— so the table can never be read backwards to learn what produced a
given finding. **The model that actually ran is recorded in each
findings file's `model:` frontmatter key and surfaced in the report's
Execution Metadata.** That record is the point: the design premise is
that investigation quality survives a model swap, and a premise nobody
can check after the fact is an assumption, not a property.

**Cost de-escalation ladder** (applied in order under budget pressure):
1. Lower the effort level for doc-search / source-trace
2. Hold cases (wait for token budget to recover)
3. Reduce parallelism (fan-out becomes sequential)

**Refusal handling**: on refusal, record it, then degrade Opus → Sonnet
→ Haiku in order. If all refuse, `NEEDS_HUMAN_*`.

**Families, not versions.** Every assignment here and in the agents'
`model:` is a family alias (`opus` / `sonnet` / `haiku`) that resolves
to the current release, so a new model version changes nothing in the
pipeline and the ladders above step between families, not version
numbers. Never brief a stage — or pass a script — a versioned model ID;
`validate.py` rejects one anywhere in the plugin. The findings' `model:`
key is the exception: it records the resolved model that actually ran.

Either ladder firing changes what the stage's `model:` key must say. The
substituted model is the one that ran; record it there, and record the
substitution itself in `cases/<id>/audit/` so the report's Execution
Metadata and the reason behind it can be reconciled later.

## Failure handling

If a stage fails (timeout, refusal, error):
1. Write `status: failed` in the findings file
2. Record the details in `cases/<id>/audit/`
3. Don't block other stages
4. synthesize works with whatever findings are available
5. If the gap is critical, hand off as `NEEDS_HUMAN_*`

## Escalation: generating CONSULT_*.md

Once `NEEDS_HUMAN_*` files accumulate in `review-queue/`, the lead
generates a `CONSULT_<date>.md` and presents it to the human in one
batch.

## Learning loop: janus-lessons (project-local)

Plugin files are read-only after install, so lessons specific to *this
project* live in the project itself:
`.claude/skills/janus-lessons/SKILL.md`. It is created once and never
overwritten by plugin updates.

- **At intake** (first case in a project): if the file does not exist,
  create it with a `name: janus-lessons` frontmatter, a one-line
  description, and an empty `## Lessons` section.
- **At fan-out**: read it and copy the entries relevant to the case
  into the stage briefs (never just point a stage at the path).
- **At case close** (DONE or verdict): if the case hit a failure that no
  agent rule or lesson covers, draft an entry in this fixed format and
  ask the human to approve adding it:

  ```
  - <symptom> → <the wrong move a model makes here> → <the correct move>
    [case: <id>]
  ```

  On approval, append it — after checking for a near-duplicate to update
  instead. Never add an entry without human approval.
- **Promotion**: when self-improver finds the same lesson recurring
  across ≥2 cases, it proposes moving it into the owning agent's own
  patterns via `review-queue/IMPROVE_*` — project lessons are the
  staging area for plugin knowledge.

## Reference assets: ocp-triage-heuristics (plugin-bundled)

Distilled OpenShift SRE decision knowledge — layered triage, failure-mode
classification, the operator status-triple, node lifecycle, and upgrade
gates — ships with the plugin at
`skills/ocp-triage-heuristics/SKILL.md`. Unlike janus-lessons (project-
local, writable, grows from case failures under human approval), this is a
read-only fixed reference distilled once from the community `openshift-ops`
plugin and re-scoped to JANUS's read-only discipline.

- **Scope**: every item is tagged 🔍 DIAGNOSTIC (read-only, autonomous-safe
  on an approved lab, never production) or ⚠️ REMEDIATION (mutates state —
  JANUS never runs these; they exist only so a report can recommend a fix
  to a human). The write-boundary is absolute: propose, never perform.
- **At fan-out**: for OpenShift-domain cases, copy the relevant sections
  into the stage briefs (as with janus-lessons — copied in, not
  referenced by path). Consumers: investigation-planner (triage +
  failure-mode decomposition), lab-verify / live-tracer (🔍 chains as
  read-only verification steps), doc-search / synthesize (failure-mode
  vocabulary for CVE/errata/KB correlation), and the upgrade-compatibility
  case type (pre-upgrade gates + stuck-upgrade chain map onto its
  investment/verify gates).

## Retrospective (management control)

Every time 10 `cases/<id>/verdict.md` files have accumulated, the lead
launches self-improver.

## MCP dependencies

Stage → server mapping is in step 1. Not bundled with the plugin — users
register servers themselves. For each server's role, optionality and
which of its tools are deliberately never granted, read
`references/mcp-dependencies.md`.
