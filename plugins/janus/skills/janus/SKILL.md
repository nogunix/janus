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
| **doc-search** | Red Hat docs/CVE/KB/Slack search (+ Microsoft Learn for ARO/Azure, AWS docs for ROSA/AWS) | findings/doc-search.md | okp-mcp + rh-docs + rh-security-mcp + rh-api-mcp + slack + mslearn + aws | Static | inherit |
| **source-trace** | Version-specific source tracing | findings/source-trace.md | casket-mcp (optional) | Static | inherit |
| **github-trace** | Upstream GitHub PR/issue/commit deep-dive | findings/github-trace.md | github MCP (read-only) | Static | inherit |
| **jira-trace** | Jira ticket deep-dive (RHEL-/OCPBUGS-/CNV-…) | findings/jira-trace.md | atlassian (Rovo MCP, read-only) | Static | inherit |
| **crash-analyze** | vmcore/coredump analysis | findings/crash-analyze.md | drgn-mcp + gdb | Static | inherit |
| **iac-author** | Authors + statically validates the lab's IaC | findings/iac-author.md + `iac/` | terraform-mcp + ansible-mcp (authoring subset) | Static | inherit |
| **lab-verify** | Live cluster verification | findings/lab-verify.md | oc, terraform CLI, bpftrace, linux-mcp | Dynamic | inherit |
| **synthesize** | All findings → English report | results/synthesis.md (en) or results/synthesis-en.md (ja) | Read only | Static | inherit |
| **localize** | English report → Japanese report | results/synthesis.md | Read only | Static | inherit |

- **github-trace and jira-trace** are conditional follow-up stages: launch them at fan-in when another stage's findings reference a GitHub PR/issue/commit or a Jira ticket that no other stage can open. Include up front only when the case question itself names one.
- **source-trace** is opportunistic (`casket` MCP is optional). When preflight finds no `casket` server connected, drop source-trace silently and note it once as a gap in the report.
- **iac-author and lab-verify** are one lab split at the execution boundary (`iac-author | [approve] lab-verify`). Writing `.tf`/`.yml` touches nothing, so iac-author is static and autonomous; applying that code is lab-verify's job behind `review-queue/APPROVE_<id>.md` via explicit Bash commands recorded in `audit/`. The executing ansible-MCP tools (`ansible_navigator`, `ade_setup_environment`) are granted to no stage, and terraform grants are enumerated, never wildcarded.

## Periodic agents (outside the pipeline)

| Agent | Trigger | Role | Model |
|---|---|---|---|
| **self-improver** | 10 accumulated verdict.md files, or weekly | Metrics computation, improvement proposals | inherit |
| **upstream-adviser** | After a high-confidence report, or periodic | Drafts upstream contribution proposals | inherit |

## What the lead does directly (shell functions)

- Intake, case creation (`case.yaml`), and pipeline composition
- Presenting the pipeline and obtaining approval
- Fanning stages out and fanning them in
- Quality checks and handoff
- Triggering improvement proposals (self-improver) and upstream contributions (upstream-adviser)
- Editing the team definition

## Case directory

```
cases/<id>/
  case.yaml
  artifacts/
  audit/
  iac/               ← iac-author writes, lab-verify executes (outside chain.jsonl)
  findings/          ← the pipeline's data plane (<stage>.md, <stage>-*-supplement.md)
  results/
    synthesis.md     ← final report (synthesis-en.md holds English draft when ja)
  verdict.md         ← human post-hoc evaluation
  chain.jsonl        ← append-only evidence hash ledger
```

### case.yaml (written by the lead at intake — stages only read it)

The **lead creates `cases/<id>/case.yaml` at intake**; no stage ever writes it.
Required fields: `id`, `received_at`, `mode` (`artifact` | `theme`), `status` (`intake` / `scheduled` / `in_progress` / `needs_human` / `done` / `failed`). `mode: artifact` requires `artifacts.vmcore`; `mode: theme` requires `theme`. `tracks` drives pipeline composition. Real binaries (`vmcore`/`vmlinux`) are never committed to git.

Optional fields:
- `version_scope` — product version(s) in scope, grouped by product (e.g. `OCP: ["4.20"]`, `RHEL: ["9.6"]`). A scope entry matches its own z-streams (`4.16` covers `4.16.55`); `versioncheck.py` uses it to flag off-scope drift.
- `related_cases` — ids of earlier cases this one continues. A `done` case is never reopened for a new objective: new scope gets a new case naming the old one here. Lab work the lead runs itself still writes a `findings/<stage>.md` that passes `findings.py lint`.
- `report_language` — `en` (default) or `ja`. Headings, table headers and the label vocabulary stay English in both modes (gate C2/section and mechanical checks read them by name). `ja` composes `localize` and enables `prosecheck.py`.

---

## Pipeline composition

The `tracks` field in `case.yaml` determines which stages run:

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

`{ }` = parallel fan-out · `|` = serial pipe · `[approve]` = human safety gate.

---

## Shell rules (how the lead operates)

### 1. Intake: read/derive the case and decide the composition

Read (or create) `case.yaml` (`mode = artifact` includes `crash-analyze`; `theme` does not unless `debug` is in `tracks`). After intake, change `case.yaml` only with tracked file-edit tools (`Edit` / `edit_file`) — never `sed -i` or shell redirects, which trigger TAMPER in `chain.py`.

Lint `case.yaml` before anything reads it:

```bash
python3 <skill-dir>/scripts/caselint.py cases/<id>
```

Fix every FAIL before composing (`report_language: jp` would compose `localize` on `≠ en` while skipping `prosecheck` on `== ja`).

Then check each composed stage's required MCP server (`claude mcp list` or `agy mcp list` showing `✔ Connected`):
- `doc-search` → `okp-mcp` (+ optional `rh-docs`, `rh-security-mcp`, `rh-api-mcp`, `mslearn`, `aws-*`, `slack`)
- `source-trace` → `casket` (optional; drop silently if absent)
- `github-trace` → `github`
- `jira-trace` → `atlassian`
- `crash-analyze` → `drgn`
- `iac-author` → `terraform` and/or `ansible` (runs with either connected, recording the missing half as a gap; drop only when neither is connected)
- `lab-verify` → `linux`

Server names must match the enumerated tool grants (see `references/mcp-dependencies.md` for optionality rules and accepted upstream alias names). A stage whose required server is not connected is **dropped from the composition and recorded as a gap**, never launched to fail at runtime.

### 2. Present the pipeline to the human

```
Pipeline for <case-id>:
  { doc-search, source-trace } | synthesize

  Static (autonomous): doc-search (inherit), source-trace (inherit)
  Dynamic (needs approval): none
  → Proceed?
```

Once the human approves (or amends), go to step 3.

### 3. Fan out the static stages

Launch the approved pipeline's static stages simultaneously as background subagents (`Agent` in Claude Code / `invoke_subagent` in Antigravity).

Brief for each stage:
- Case directory path: `cases/<id>/`
- Output contract: write to `cases/<id>/findings/<stage>.md`, then notify (`SendMessage` / `send_message`)
- On failure: write `status: partial` or `failed` in the YAML frontmatter and notify
- Relevant `janus-lessons` entries copied in (never referenced by path)
- For OpenShift-domain symptoms, relevant `ocp-triage-heuristics` sections copied in with 🔍/⚠️ tags preserved (⚠️ remediations are report-only, never executed)
- `doc-search` only, by platform: an ARO/Azure case gets the absolute path of `references/doc-search-azure.md`; a ROSA/AWS case (or GPU/large-model lab) gets `references/doc-search-aws.md` — each with "Read this file before any call to that layer's tools".

**Copy this stage contract verbatim into every stage brief**, with `<id>`, `<stage>`, and `<skill-dir>` (absolute path) replaced by real values (briefs are plain text, never shell-expanded):

```
Stage contract:
1. Write cases/<id>/findings/<stage>.md FIRST, then run
   python3 <skill-dir>/scripts/findings.py lint cases/<id>/findings/<stage>.md
   and fix every FAIL before SendMessage (a completion notice, not the
   result). Create and change findings/ and results/ files only with
   Write or Edit — never a shell redirect, heredoc, script or `sed -i`,
   and that includes one-line frontmatter updates such as tool_calls or
   duration_s. The evidence chain seals only Write/Edit; any other write
   to a sealed file reads as tampering and stops the case at NEEDS_HUMAN.
1a. If your findings file already exists — you are a resumed stage, or a
   later round — **append with Edit**. A `Write` replaces the file
   wholesale, so a payload holding only your current round silently
   deletes every earlier one. The evidence chain will not catch it:
   Write is a tracked tool, so the smaller file seals as a legitimate
   change. A PreToolUse hook denies the obvious case, but it is a
   backstop, not a licence to reach for Write first.
2. VERIFIED requires tool output you observed in this session. Never
   promote a Basis without new evidence.
3. A tool failure (timeout, unreachable, not indexed) or an unexplored
   layer/phase/angle is a Gap with a reason, never a Negative Result.
   Attempt at least one scoped fallback before recording either.
4. Negative results are evidence — report them explicitly.
5. Downloads, clones and scratch output go under cases/<id>/artifacts/,
   never /tmp or findings/.
```

### 4. Gate dynamic stages

If the pipeline has a dynamic stage:
1. Generate `review-queue/APPROVE_<id>.md` (on approval, mark its title `APPROVED <date>`; quoting `iac-author`'s "What this builds" table when `iac-author` is composed) and present it to the human.
2. Approved → launch `lab-verify` (only after `cases/<id>/findings/iac-author.md` exists when `iac-author` is composed).
3. Rejected → skip and pass to `synthesize` as a gap.

If `iac-author` has `status: failed` or unresolved `TODO(iac-author)` markers, do not launch `lab-verify`. Route each marker by who can close it:
- *Provider argument, module version, lint finding* → send back to `iac-author`.
- *Cloud-service semantics* (what the service requires regardless of provider schema) → the lead closes it via a step-5a supplement or `doc-search` (never re-run `iac-author`, which has no cloud-doc tools).
- *Live-cluster or real-credential question* → leave for `lab-verify` inside the approved window if the marker names the probe command.

### 5. Fan in (collect) — and gap-driven follow-up

**The findings file on disk is the authoritative completion signal.** On every wake while stages are outstanding, check `ls cases/<id>/findings/*.md`. Once all composed stages have files on disk, run the digest instead of reading the full files — **even if some completion notification never arrived**; never sit waiting for a message about a stage whose file is already on disk.

- Expected file present → normal (whatever its status says)
- No file and the stage has been silent well past its expected duration (no running task, no partial output) → treat as failed: record it in `cases/<id>/audit/` and proceed without it

Then run the digest:

```bash
python3 <skill-dir>/scripts/findings.py digest cases/<id>
```

If a stage has `lint FAIL`, message it to fix the file before step 6. Decide from the digest whether a follow-up stage can fill a gap before `synthesize` runs:

| Gap signal in findings | Follow-up stage |
|---|---|
| GitHub PR/issue/commit referenced but not investigated, or `release_diff` range handed off | github-trace |
| Jira ticket (RHEL-/OCPBUGS-/CNV-…) referenced but not opened | jira-trace |
| casket phase/layer "unexplored (reason: ...)" or symbol/version question from crash-analyze | source-trace |
| `TODO(iac-author)` marked *service-semantics* | doc-search (or lead step-5a supplement) |

- **Cap: at most 2 follow-up stages per case, one follow-up round** (static-track only).

### 5a. Lead-side supplemental searches

When a subagent stage fails or returns `status: partial` with MCP gaps and the lead's own session has the MCP server connected, the lead runs the supplemental searches directly and writes `<stage>-<source>-supplement.md` (with `supplement_of:` / `source:` frontmatter and finding numbers in blocks of 10 starting at F20). Read `references/findings-format.md` before writing one, and run `findings.py lint` on it afterwards.

### 6. Launch synthesize

First close and freeze the evidence chain over the inputs `synthesize` will read (read `references/evidence-chain.md` if any command reports non-OK):

```bash
python3 <skill-dir>/scripts/chain.py verify cases/<id>
python3 <skill-dir>/scripts/chain.py seal cases/<id>
python3 <skill-dir>/scripts/chain.py lock cases/<id>
```

Generate the anchor map for evidence links and paste its full stdout text as an `## Anchor Map` section in the `synthesize` brief:

```bash
python3 <skill-dir>/scripts/anchors.py cases/<id>/findings/
```

Include `<skill-dir>` (absolute path) in the brief so `synthesize` runs `reportlint.py`, `linkcheck.py`, and `quotecheck.py` on its own report before reporting complete. **Synthesize always writes in English**:
- `report_language: en` (or absent) → `results/synthesis.md`.
- `report_language: ja` → `results/synthesis-en.md`, then launch `localize` (step 6a).

### 6a. Launch localize (only when `report_language` ≠ `en`)

After `results/synthesis-en.md` exists, launch `localize` with:
1. The case directory path
2. The **Anchor Map** from step 6
3. `<skill-dir>` (absolute path) so `localize` runs `prosecheck.py`, `linkcheck.py`, `quotecheck.py`, and `reportlint.py` before reporting complete

**Do not specify a Japanese prose style in the brief** — style is governed by `scripts/textlintrc.json` (である調 by default).

### 7. Quality check (the lead's own job) — named gates

Run the eight mechanical pre-checks in one call:

```bash
python3 <skill-dir>/scripts/gates.py cases/<id>
```

| # | Command | FAIL → |
|---|---|---|
| 1 | `chain.py verify cases/<id>` | evidence tampered after seal → record in `audit/`, write `review-queue/NEEDS_HUMAN_<id>.md` |
| 2 | `approvalcheck.py cases/<id>` | lab-verify ran with no `review-queue/APPROVE_<id>*.md` → record in `audit/`, `NEEDS_HUMAN_<id>.md` |
| 3 | `reportlint.py cases/<id>` | missing section/cell or mismatched count/`model:` → **C2/section**; unsupported hypothesis rank → **C1/basis**; nonexistent finding ref → **C1/ref** |
| 4 | `urlcheck.py cases/<id>/results/synthesis.md` | dead citation (404/410, unresolvable host) → **C1/url** |
| 5 | `quotecheck.py cases/<id>/results/synthesis.md` | mutated/fabricated quote → **C2/quote-mismatch**; no attributed quotes → **C2/quote-absent** |
| 6 | `versioncheck.py cases/<id>` | unpinned source citation → **C2/version** |
| 7 | `linkcheck.py cases/<id>/results/synthesis.md` | local link resolves to no file/anchor → **C1/link** |
| 8 | `prosecheck.py cases/<id>` | `report_language: ja` only — prose defect → **C2/prose** |

**A notice means *not checked*, never *passed*.** On any FAIL, WARN, or NOTICE, or before writing a send-back brief, read `references/quality-gates.md` for full check behavior, fail directions, and the **C1 (GROUNDING)** / **C2 (COMPLETENESS & FIDELITY)** judgment-gate definitions:
- **C1 sub-codes**: `C1/ref`, `C1/url`, `C1/link`, `C1/basis`, `C1/spec`, `C1/currency`, `C1/source-of-truth`
- **C2 sub-codes**: `C2/section`, `C2/artifact`, `C2/quote-absent`, `C2/quote-mismatch`, `C2/version`, `C2/prose`

Record every send-back before writing the revision brief:

```bash
python3 <skill-dir>/scripts/sendback.py record cases/<id> <sub-code> [<sub-code> ...]
```

Obey the verdict (`OK` → targeted in-place revision naming the defect class; `RECONSIDER` → last allowed round; `ESCALATE` → stop, write `review-queue/NEEDS_HUMAN_<id>.md`). Both gates pass → `review-queue/DONE_<id>.md`.

### What the lead does NOT do

Never read source, search docs, chase PRs/Jira, analyze crashes, write IaC, build labs, write stage findings, write/patch the report directly, or intervene in a running stage.

---

## Inter-stage data format & Evidence chain

- **Findings format**: YAML frontmatter (`stage`, `case`, `date`, `status`, `model`, `tool_calls`, `duration_s`) + `### F<N>:` blocks with `Confidence`, `Basis` (`VERIFIED | REASONED | ASSUMED`), `Type`, `Detail`, `Ref`. Full schema in `references/findings-format.md`.
- **Evidence chain**: `cases/<id>/chain.jsonl` is an append-only sha256 ledger; `hooks/evidence-chain.py` auto-seals tracked writes, `hooks/evidence-lock.py` denies writes to locked files, `hooks/evidence-shell.py` denies shell writes to sealed files, `hooks/evidence-drift.py` denies writes over out-of-band drift, and `hooks/findings-truncation.py` denies overwrites that drop findings. Full semantics in `references/evidence-chain.md`.

## Safety (invariant)

- **Static stages are autonomous**; **dynamic stages (`lab-verify`) require human approval** via `review-queue/APPROVE_<id>.md` and run on a disposable lab, never production.
- **No remediation** (root cause only) and **no guardrail spoofing**.
- **No secret material or Terraform state in context**: `hooks/secret-safety.py` blocks bulk secret dumps (`oc/kubectl get secret -o yaml|json`, `oc extract secret`, `aws secretsmanager get-secret-value`) and AWS support-case writes. Never read `terraform.tfstate`.
- **Provisioning happens only in `lab-verify`** post-approval via explicit Bash commands logged in `audit/`.
- **Parallelism cap: 4 stages.** Keep vmcore/debuginfo and any scratch files under `cases/<id>/`, never `/tmp`.

## Model strategy

| Stage | Model | Rationale |
|---|---|---|
| doc-search | inherit | Adapts to the host session model across Claude Code and Antigravity; search and organization |
| source-trace | inherit | Adapts to the host session model; symbol tracing and diff extraction |
| github-trace | inherit | Adapts to the host session model; PR/issue reading and link following |
| jira-trace | inherit | Adapts to the host session model; ticket reading and link following |
| crash-analyze | inherit | Heavy reasoning — runs on the session's model (e.g., Opus, Sonnet, or Gemini Pro/Argon) |
| iac-author | inherit | Adapts to the host session model; registry lookup and templating against a documented schema |
| lab-verify | inherit | Heavy reasoning — runs on the session's model (e.g., Opus, Sonnet, or Gemini Pro/Argon) |
| synthesize | inherit | Adapts to the host session model; structured input + mechanical pre-checks enforce quality |
| localize | inherit | Adapts to the host session model; translation against a fixed anchor map and textlint preset |

All agents declare `model: inherit` in frontmatter so they load natively in both Claude Code and Antigravity (`opus` / `sonnet` / `haiku` / `inherit` are family aliases; versioned IDs are rejected by `validate.py`). **The model that actually ran is recorded in each findings file's `model:` frontmatter key and surfaced in the report's Execution Metadata.** Under budget pressure (lower effort → hold cases → reduce parallelism) or on refusal (record it, step down model tiers, or escalate to `NEEDS_HUMAN_*`), record any model substitution in `cases/<id>/audit/`.

## Failure handling, Escalation & Learning loop

- **Failure handling**: if a stage fails, write `status: failed` in its findings file, record details in `cases/<id>/audit/`, do not block other stages, and hand off as `NEEDS_HUMAN_*` if the gap is critical. Once `NEEDS_HUMAN_*` files accumulate in `review-queue/`, batch them into `review-queue/CONSULT_<date>.md`.
- **Learning loop (`janus-lessons`)**: project-local lessons live in `.claude/skills/janus-lessons/SKILL.md` (or `.agents/skills/janus-lessons/SKILL.md` in Antigravity). Create on first case if absent; copy relevant entries into stage briefs at fan-out; append new `- <symptom> → <wrong move> → <correct move> [case: <id>]` entries at case close only with human approval. `self-improver` runs every 10 `verdict.md` files (or weekly) and proposes promoting recurring lessons (`≥2` cases) via `review-queue/IMPROVE_*`.
- **Reference assets (`ocp-triage-heuristics`)**: read-only OpenShift SRE reference at `skills/ocp-triage-heuristics/SKILL.md`. Copy relevant sections into stage briefs for OpenShift cases (🔍 DIAGNOSTIC items are read-only; ⚠️ REMEDIATION items are report-only recommendations).
- **MCP dependencies**: see step 1 and `references/mcp-dependencies.md`.

## Antigravity host notes (`agy`)

- **Subagent tools**: `plugins/janus/agents/*.md` declare Claude Code tool names. Before launching stages on Antigravity, run `python3 scripts/sync-agy-agents.py` to generate `.agents/agents/` overrides, or invoke `TypeName: "self"` and instruct the subagent to use Antigravity tools (`read_file`, `write_file`, `edit_file`, `run_command`, `send_message`, `call_mcp_tool`).
- **Quota / mid-stage recovery**: If a subagent stops mid-stage (e.g., `429 RESOURCE_EXHAUSTED` after completing MCP queries), launch a replacement subagent and pass the stopped subagent's `transcript.jsonl` path so it can write and lint `findings/*.md` / `results/*.md` without repeating MCP calls.
