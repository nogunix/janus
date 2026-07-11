# Changelog

Versions refer to the `janus` plugin (`plugins/janus/.claude-plugin/plugin.json`).

## 0.8.2 — 2026-07-11

- **source-trace is now positioned as opportunistic.** casket-mcp is an
  unpublished, environment-specific server, so most installs won't have
  it. The lead's preflight already dropped unreachable stages; the skill
  now says explicitly that source-trace's absence is the normal state —
  drop it silently, note the gap once in the report, and don't surface
  setup instructions or treat the case as degraded. Public-facing
  descriptions (plugin.json) no longer name casket as a dependency.

## 0.8.1 — 2026-07-11

- **source-trace: adopt casket's 2026-07-11 phase-id rename.** casket-mcp
  renamed its phase ids from `A/B/C/D` to `a`/`a-rpm`/`b`/`b-operand`, and
  added two new operator-catalog phases `b-certified`/`b-community`.
  source-trace's phase-enumeration guidance, Gaps wording, and the CNV
  multipath reusable pattern now use the new ids.
- **source-trace: new reusable pattern for CNV virt-core downstream gaps.**
  Records that casket's `b-operand` virt-core sources track the public
  upstream tag only (not the true downstream build delta — a deliberate
  casket scope decision, case cnv-downstream-gap 2026-07-11); the fallback
  is errata/Jira or internal access, not a false negative from the
  upstream tree.

## 0.8.0 — 2026-07-11

- **New conditional stage: jira-trace.** Jira ticket deep-dive (e.g. Red
  Hat Jira `RHEL-NNNNN` / `OCPBUGS-NNNNN`) via
  [sooperset/mcp-atlassian](https://github.com/sooperset/mcp-atlassian),
  launched by the lead at fan-in when another stage surfaces a ticket
  key no stage can open — the gap seen in the scsi3pr-multipath case
  (RHEL-65852, RHEL-118722 stayed uninvestigated). Reads ticket fields,
  comment threads, changelogs, clone chains, and attachments;
  `fixVersions` is treated as intent, never as shipped-in-build proof
  (that stays source-trace's call). Strictly read-only: the agent's
  allowlist contains only read tools, and the server is registered with
  `READ_ONLY_MODE=true` as the second boundary.
- doc-search and github-trace now record unopenable Jira keys in Gaps
  (fixed format) so the lead can trigger the follow-up.

## 0.7.0 — 2026-07-11

Working-method discipline: make the pipeline's quality behavior explicit
and enforceable, so output quality no longer depends on which model sits
in each seat.

- **Evidence-basis labels.** Every finding now carries
  `Basis: VERIFIED | REASONED | ASSUMED` alongside Confidence —
  tool-output-backed vs. inferred vs. carried-in. Promotion requires new
  evidence; each stage defines what VERIFIED means for its tools.
- **Named report-acceptance gates.** The lead's quality check is six
  named gates (G1-REF … G6-ARTIFACTS) with mechanical send-back to
  synthesize; the same gate failing twice escalates to `NEEDS_HUMAN_*`.
- **Verbatim stage contract.** The lead copies a fixed six-line contract
  (file-write-first, Basis labels, gap-vs-negative, fallback-before-
  giving-up) into every stage brief, so core rules arrive even if an
  agent skims its own definition.
- **Causation gate (crash-analyze).** A `crash-cause` finding requires
  "X causes Y because Z" with X and Y observed in this vmcore; a missing
  mechanism Z caps the finding at MEDIUM as correlation.
- **Failure-pattern catalogs.** doc-search and source-trace gain compact
  `symptom → wrong move → correct move` catalogs seeded from real case
  history (snippet-only conclusions, corpus-gap vs. negative,
  cross-layer misses, timeout handling).
- **Project-local lessons loop.** `.claude/skills/janus-lessons/SKILL.md`
  is created per project (never overwritten by plugin updates); the lead
  banks human-approved lessons there and injects relevant ones into
  stage briefs; self-improver promotes lessons recurring across ≥2 cases
  into the owning agent's catalog.
- **synthesize** enforces Basis: HIGH hypotheses need ≥1 VERIFIED
  finding (or 2+ independent REASONED from different stages), reports
  the basis distribution, and never promotes a label it cites.
- **Reliable fan-in.** Fix for a real handoff loss (source-trace wrote
  its findings file but the lead never picked it up): `SendMessage` is
  now actually in every stage agent's tools allowlist (the contract
  demanded it but no agent had it), and the lead treats the findings
  file on disk — not notifications — as the authoritative completion
  signal, re-checking `findings/*.md` frontmatter on every wake.
- Intake now verifies each composed stage's MCP server is connected
  (`claude mcp list`); a stage with an unreachable server is dropped
  from the composition and recorded as a gap instead of launched to
  fail.

## 0.6.2 — 2026-07-10

- doc-search: Microsoft Learn (mslearn MCP) for the ARO/Azure layer,
  with an okp-vs-mslearn division-of-labor rule.
- deck: bundled brand template removed (not redistributable); the skill
  now requires a user-supplied .pptx template.
- MIT LICENSE; README setup guidance for all non-casket MCP servers.

## 0.6.1 — 2026-07-10

- lab-verify: linux-mcp read-only node/VM diagnostics (journald,
  systemd, processes, network, storage — local or over SSH), registered
  with `LINUX_MCP_TOOLSET=fixed` as the read-only safety boundary.

## 0.6.0 — 2026-07-10

- New conditional stage **github-trace**: upstream PR/issue/commit
  deep-dive, launched at fan-in when another stage surfaces a GitHub
  reference it cannot open.
- Gap-driven follow-up at fan-in: the lead reads each findings file's
  Gaps and may launch up to 2 static follow-up stages (one round).

## 0.5.x — 2026-07-09 .. 07-10

- 0.5.5: source-trace layer-coverage check (Phase B + Phase D),
  large-tree timeout fallback (scope reduction, never give up),
  version-diff as a first-class method, stricter negative-result
  criteria.
- 0.5.4: source-trace emits GitHub permalinks (INDEX.tsv repo+SHA).
- 0.5.3: reports preserve artifact names verbatim and human-verifiable
  URLs.
- 0.5.2: okp-doc-search skill (query construction, doc_id rules).
- 0.5.1: okp-mcp usage knowledge folded into doc-search.
- 0.5.0: active-team.md folded into the janus SKILL; case.yaml intake
  contract documented.

## 0.4.x — 2026-07-08 .. 07-09

- OpenShift-wide rebrand (research & investigation pipeline, not only
  crash forensics); agent-definition hardening; SKILL deduplication;
  deck skill imported.

## Earlier

Pre-plugin history (full JANUS repo: SPEC/PLAN, labs, cases,
self-improvement loop) lives in the git log before `plugin-slim`
(bceeb62).
