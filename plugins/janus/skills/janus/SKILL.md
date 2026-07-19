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
{ doc-search, source-trace, crash-analyze, [approve] lab-verify } | synthesize
```

## Pipeline stages

| Stage | Role | Output | Tools | Safety | Model |
|---|---|---|---|---|---|
| **doc-search** | Red Hat docs/CVE/KB/Slack search (+ Microsoft Learn for ARO/Azure, AWS docs for ROSA/AWS) | findings/doc-search.md | okp-mcp + slack + mslearn + aws | Static | sonnet |
| **source-trace** | Version-specific source tracing | findings/source-trace.md | casket-mcp (optional, unpublished) | Static | sonnet |
| **github-trace** | Upstream GitHub PR/issue/commit deep-dive | findings/github-trace.md | github MCP (read-only) | Static | sonnet |
| **jira-trace** | Jira ticket deep-dive (RHEL-/OCPBUGS-/CNV-…) | findings/jira-trace.md | mcp-atlassian (read-only) | Static | sonnet |
| **crash-analyze** | vmcore/coredump analysis | findings/crash-analyze.md | drgn-mcp + gdb | Static | opus |
| **lab-verify** | Live cluster verification | findings/lab-verify.md | oc, terraform, bpftrace, linux-mcp | Dynamic | opus |
| **synthesize** | All findings → report | results/report.md | Read only | Static | opus |

github-trace and jira-trace are normally **conditional follow-up
stages**: the lead launches them at fan-in when another stage's
findings reference a GitHub PR/issue/commit or a Jira ticket that no
other stage can open (doc-search has only okp/slack; source-trace only
casket). Include one up front only when the case question itself names
an upstream PR/issue or a Jira key.

source-trace is **opportunistic**: casket-mcp is an unpublished,
environment-specific server, so most installs won't have it. When the
preflight (step 1) finds no `casket` server connected, drop source-trace
silently — its absence is the normal state, not an error. Note it once
as a gap in the report; do not surface setup instructions or treat the
case as degraded.

## Periodic agents (outside the pipeline)

| Agent | Trigger | Role |
|---|---|---|
| **self-improver** | 10 accumulated verdict.md files, or weekly | Metrics computation, improvement proposals |
| **upstream-adviser** | After a high-confidence report, or periodic | Drafts upstream contribution proposals |

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
  findings/          ← the pipeline's data plane
    doc-search.md
    source-trace.md
    github-trace.md  ← usually a conditional follow-up
    crash-analyze.md
    lab-verify.md
  results/
    report.md        ← synthesize's final output
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

---

## Pipeline composition

The `tracks` field in `case.yaml` determines which stages run.

| tracks | Pipeline |
|---|---|
| `[documentation, source]` | `{ doc-search, source-trace } \| synthesize` |
| `[documentation, source, debug]` | `{ doc-search, source-trace, crash-analyze } \| synthesize` |
| `[documentation, source, debug, sno\|vm]` | `{ doc-search, source-trace, crash-analyze, [approve] lab-verify } \| synthesize` |
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
server being reachable): doc-search → okp-mcp, source-trace → casket,
github-trace → github, jira-trace → mcp-atlassian, crash-analyze →
drgn, lab-verify → linux.
A stage whose server is not connected is **dropped from the composition
and recorded as a gap** (note it in the step-2 presentation; synthesize
reports it under Investigation Gaps) — never launched to fail at
runtime.

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

**Copy this stage contract verbatim into every stage brief** (do not
paraphrase or trim — agent definitions can be skimmed; the brief is
always read):

```
Stage contract:
1. Write cases/<id>/findings/<stage>.md FIRST; SendMessage is a
   completion notice, not the result.
2. Every finding carries Confidence, Basis (VERIFIED | REASONED |
   ASSUMED), and a verifiable Ref (+ public URL where one exists).
3. VERIFIED requires tool output you observed in this session. Never
   promote a Basis without new evidence.
4. A tool failure (timeout, unreachable, not indexed) is a Gap, not a
   Negative Result. Attempt at least one scoped fallback before
   recording either.
5. An unexplored layer/phase/angle is a Gap with a reason — never a
   negative.
6. Negative results are evidence — report them explicitly.
```

### 4. Gate dynamic stages

If the pipeline has a dynamic stage:
1. Generate `review-queue/APPROVE_<id>.md` and present it to the human
2. Approved → launch lab-verify
3. Rejected → skip. This is passed to synthesize as a gap (no file in findings/)

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

and read each present file's frontmatter `status`. Fan in as soon as
every composed stage has a file, **even if some completion notification
never arrived**. Never sit waiting for a message about a stage whose
file is already on disk.

- Expected file present → normal (whatever its status says)
- No file and the stage has been silent well past its expected duration
  (no running task, no partial output) → treat as failed: record it in
  `cases/<id>/audit/` and proceed without it

Then read each findings file's frontmatter `status` and its **Gaps
section** and decide whether another stage can fill a gap before
synthesize runs:

| Gap signal in findings | Follow-up stage |
|---|---|
| GitHub PR/issue/commit referenced but not investigated | github-trace |
| Jira ticket (RHEL-/OCPBUGS-/CNV-…) referenced but not opened | jira-trace |
| casket phase/layer "unexplored (reason: ...)" | source-trace (re-run, scoped to that layer) |
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

Instruct it to read all of `findings/*.md` and write `results/report.md`.
synthesize works with whatever findings exist — it reports missing ones
as gaps.

### 7. Quality check (the lead's own job) — named gates

Mechanical pre-checks before any content gate (all three scripts live
in `scripts/` next to this file):

1. `python3 <skill-dir>/scripts/chain.py verify cases/<id>` — a FAIL
   means evidence changed after it was sealed; do not hand off. Record
   the mismatch in `cases/<id>/audit/` and write
   `review-queue/NEEDS_HUMAN_<id>.md` quoting the failing entries.
2. `python3 <skill-dir>/scripts/urlcheck.py cases/<id>/results/report.md`
   — curl-level liveness for every reference URL. A FAIL (404/410 or
   unresolvable host) is a provably dead citation: send the report back
   to synthesize **under C1/url**, quoting the dead URL. 401/403/429
   count as reachable (login-walled is normal for access.redhat.com);
   warnings (5xx/timeout) don't block. If the network itself is down
   the script says so and passes — offline installs are normal.
3. `python3 <skill-dir>/scripts/quotecheck.py cases/<id>/results/report.md`
   — every attributed blockquote in the report (`> …` ending in
   `> — findings/<stage>.md`) must appear verbatim
   (whitespace-normalized) in the file it cites. A FAIL is a fact that
   mutated between findings and report, or a fabricated attribution:
   send the report back to synthesize **under C2/quote-mismatch**,
   quoting the mismatch. A "no attributed quotes" warning means
   synthesize skipped the quote convention — also a **C2/quote-absent**
   send-back for any report that makes evidence-backed claims.

Read `results/report.md` and check it against these two judgment gates
(the three mechanical pre-checks above already cover the rest). **A
failed gate = send the report back to synthesize, naming the sub-code
and quoting the offending line** — the lead never patches the report
itself. The sub-codes are the send-back vocabulary: they keep the
diagnostic granularity of the old seven gates while collapsing the
lead's read of the report into two passes.

| Gate | The one question | Sub-codes (send-back vocabulary) |
|---|---|---|
| **C1 — GROUNDING** | Is every claim anchored to evidence at the right strength? | `C1/ref` — a claim with no reference · `C1/url` — a resolvable-pattern ID (CVE/RHSA/KB/PR) with no public URL; dead URLs are caught mechanically by urlcheck.py · `C1/basis` — a HIGH hypothesis without ≥1 VERIFIED or 2+ independent REASONED findings from different stages, or an unlabeled citation · `C1/spec` — an unsupported "likely / probably / should" claim |
| **C2 — COMPLETENESS & FIDELITY** | Is the report structurally complete, and are identifiers and quotes reproduced exactly? | `C2/section` — an empty Objectives Assessment or Execution Metadata cell · `C2/artifact` — a paraphrased concrete identifier (file, resource, symbol, version) · `C2/quote-absent` — an evidence-backed report with no attributed verbatim quotes; mutated quotes and fabricated attributions are caught mechanically by quotecheck.py and sent back as `C2/quote-mismatch` |

Both gates pass → `review-queue/DONE_<id>.md`
The same sub-code fails twice on one report → stop the loop:
`review-queue/NEEDS_HUMAN_<id>.md` with both versions noted.

### What the lead does NOT do

- Read source (that's source-trace's job)
- Search documentation (that's doc-search's job)
- Chase GitHub PRs/issues (that's github-trace's job)
- Analyze crashes (that's crash-analyze's job)
- Build labs (that's lab-verify's job)
- Write findings (each stage's own job)
- Write the report (that's synthesize's job)
- Intervene in a stage while it's running

---

## Inter-stage data format

Every stage writes to `cases/<id>/findings/<stage>.md` in the same format.

### YAML frontmatter (required)

```yaml
---
stage: <stage-name>
case: <case-id>
date: <ISO 8601>
status: complete | partial | failed
tool_calls: <N>
duration_s: <seconds>
---
```

### Finding structure

```markdown
### F<N>: <one-line title>
- **Confidence**: HIGH | MEDIUM | LOW
- **Basis**: VERIFIED | REASONED | ASSUMED
- **Type**: known-issue | implementation | version-change | crash-cause | behavior | negative
- **Detail**: <2-5 sentences>
- **Ref**: <verifiable reference>
```

**Basis** states what backs the claim — it is orthogonal to Confidence:

- **VERIFIED** — tool output observed in this session backs the claim
  (the Ref points at that output: a document actually opened, code
  actually read/diffed, a drgn/oc command actually run).
- **REASONED** — inferred from something read (a search snippet, a code
  structure, a cross-reference) without direct verification.
- **ASSUMED** — neither; carried in from the question or from prior
  knowledge.

A claim's Basis may only be promoted by new evidence, never by
restatement. A HIGH-confidence finding on an ASSUMED basis is a
contradiction — synthesize and the lead's gates reject it.

### Reference format

| Source | Format | Example |
|---|---|---|
| docs | CVE / RHSA / KB ID | `CVE-2024-1086` |
| source | `component@NVR file:line` | `hyperkube@4.18.41 pkg/…/eviction.go:414` |
| drgn | script + output path | `audit/drgn-1.py → audit/drgn-1.log` |
| lab | command + cluster ver | `oc get pods (OCP 4.18.45) → audit/lab-1.log` |
| slack | `#channel, YYYY-MM-DD` | `#forum-kubevirt, 2026-06-15` |
| github | `owner/repo#N` or commit SHA + URL | `kubevirt/kubevirt#14309` |
| mslearn | Learn URL | `https://learn.microsoft.com/azure/openshift/support-lifecycle` |
| aws-docs | `docs.aws.amazon.com` URL | `https://docs.aws.amazon.com/rosa/latest/userguide/rosa-sts.html` |
| aws-support | `AWS support case <id>` | `AWS support case 1234567890` |

---

## Evidence chain (tamper-evidence)

Each case carries an append-only hash ledger, `cases/<id>/chain.jsonl`:
every record holds the sha256 of one evidence file plus the hash of the
previous record, blockchain-style. It makes edits **visible, never
impossible** — a legitimate revision appends a new record; an edit that
bypasses sealing breaks `verify`. The helper is `scripts/chain.py`,
next to this file (stdlib-only):

```bash
python3 <skill-dir>/scripts/chain.py verify cases/<id>   # exit 1 on tamper
python3 <skill-dir>/scripts/chain.py seal cases/<id>     # seal new/changed files
```

Sealing is mostly automatic: a PostToolUse hook
(`hooks/evidence-chain.py`) seals every Write/Edit into the evidence
set (`case.yaml`, `findings/*.md`, `results/*.md`, `audit/*`,
`verdict.md`). The lead's explicit calls cover the rest:

- **Step 6 (before synthesize)**: `verify` then `seal` — verify first;
  a FAIL means a sealed file changed outside tracked tools (e.g. a
  shell redirect), so record the mismatch in `cases/<id>/audit/` before
  re-sealing. The plain `seal` picks up shell-written audit logs the
  hook cannot see. Then `lock` — the chain detects rewrites after the
  fact; the lock prevents the accident in the first place by dropping
  the write bits on the fact base (`case.yaml`, `findings/*.md`,
  `audit/*`), with `hooks/evidence-lock.py` (PreToolUse) denying
  tracked writes to locked files. `unlock` is the lead's explicit
  escape hatch for a legitimate revision (unlock → edit → re-seal →
  lock). New files (a follow-up stage's findings, a new audit log) are
  unaffected — lock freezes files, not directories.
- **Step 7 (before the named gates)**: `verify` — a FAIL blocks
  handoff (`NEEDS_HUMAN_<id>.md`).
- **At verdict**: `seal` after the human writes `verdict.md` — the
  sealed verdict is the ground truth self-improver's metrics stand on.

`verify` checks each file against its **newest** record, so send-back
revisions of `report.md` are normal, and the ledger keeps the full
revision history. Warnings (`unsealed: …`) mean a file exists but was
never sealed — run `seal`; FAILs mean the ledger or a sealed file was
altered — that is a human matter, never something to quietly repair.
`artifacts/` (vmcore binaries) stays outside the chain, as it stays
outside git.

## Safety (invariant)

- **Static stages are autonomous.** Dead-artifact analysis
  (vmcore/coredump), doc search, and source tracing all run without human
  approval.
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
- **Parallelism cap: 4 stages.** No more than 4 stages run concurrently
  even at full fan-out.
- **Sandbox**: drgn's `eval_expression` runs arbitrary Python — run it
  network-cut, read-only, unprivileged, with an external per-call timeout
  wrapper. Keep confidential vmcores out of the autonomous deep-tier loop
  unless that timeout is enforced. Keep vmcore/debuginfo under
  `cases/<id>/`, not `/tmp` (the sandbox's read-only protection does not
  reliably cover /tmp).

## Output contract

| Stage | Output file |
|---|---|
| doc-search | `cases/<id>/findings/doc-search.md` |
| source-trace | `cases/<id>/findings/source-trace.md` |
| github-trace | `cases/<id>/findings/github-trace.md` |
| jira-trace | `cases/<id>/findings/jira-trace.md` |
| crash-analyze | `cases/<id>/findings/crash-analyze.md` |
| lab-verify | `cases/<id>/findings/lab-verify.md` |
| synthesize | `cases/<id>/results/report.md` |

### File-write-first rule

Stages **write the findings file first, then SendMessage**. SendMessage
is a completion notice, not the result itself — the lead treats the
file on disk, not the notice, as the completion signal (step 5), so a
lost notice delays nothing and a notice without a file counts for
nothing.

## Model strategy

| Stage | Model | Rationale |
|---|---|---|
| doc-search | sonnet | Search and organization. Doesn't need heavy reasoning |
| source-trace | sonnet | Symbol tracing and diff extraction. Routine work |
| github-trace | sonnet | PR/issue reading and link following. Routine work |
| jira-trace | sonnet | Ticket reading and link following. Routine work |
| crash-analyze | opus | Needs heavy reasoning for the iterative hypothesis-test loop |
| lab-verify | opus | Needs heavy reasoning for verification judgment and trace interpretation |
| synthesize | opus | Cross-references multiple stages and ranks hypotheses |

**Cost de-escalation ladder** (applied in order under budget pressure):
1. Lower the effort level for doc-search / source-trace
2. Hold cases (wait for token budget to recover)
3. Reduce parallelism (fan-out becomes sequential)

**Refusal handling**: on refusal, record it, then degrade Opus → Sonnet
→ Haiku in order. If all refuse, `NEEDS_HUMAN_*`.

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

## Retrospective (management control)

Every time 10 `cases/<id>/verdict.md` files have accumulated, the lead
launches self-improver.

## MCP dependencies

`casket` (versioned source — optional and unpublished; source-trace
activates only when this server happens to be registered, and its absence
is normal), `okp-mcp` (Red Hat docs/CVE/errata/KB), `mslearn`
(Microsoft Learn docs — ARO/Azure layer for doc-search; public remote server,
no auth: `claude mcp add --transport http mslearn
https://learn.microsoft.com/api/mcp`), `aws-docs` / `aws-knowledge` /
`aws-support` (AWS docs — ROSA/AWS layer for doc-search, the AWS mirror of
mslearn; all optional, from
[awslabs/mcp](https://github.com/awslabs/mcp). `aws-knowledge` is the hosted
read-only endpoint `https://knowledge-mcp.global.api.aws` (no auth);
`aws-docs` is read-only via `uvx awslabs.aws-documentation-mcp-server`;
`aws-support` needs AWS credentials + a Business/Enterprise support plan and
only its read-only `describe_*` tools are granted — JANUS never opens, replies
to, or resolves a case. AWS has designated the
[Agent Toolkit for AWS](https://github.com/aws/agent-toolkit-for-aws) as the
awslabs servers' successor: if its managed `aws-mcp` server is registered,
doc-search prefers its no-auth `search_documentation` / `retrieve_skill`
over aws-docs — its `call_aws` / `run_script` tools are never granted),
`drgn` (vmcore), `github` (upstream
PR/issue/commit — github-trace and upstream-adviser), `mcp-atlassian`
(Jira tickets — jira-trace; register with `READ_ONLY_MODE=true` so all
write tools stay disabled — that is the safety boundary), `linux` (read-only
RHEL node/VM diagnostics, local or over SSH — lab-verify; register with
`LINUX_MCP_TOOLSET=fixed` so `run_script` stays disabled). Not bundled with
the plugin — paths are environment-specific, so register them yourself
(`claude mcp add …`); confirm `claude mcp list` shows them `✔ Connected`
before relying on them (a tool being advertised ≠ the server being
connected).
