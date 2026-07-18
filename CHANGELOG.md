# Changelog

Versions refer to the `janus` plugin (`plugins/janus/.claude-plugin/plugin.json`).

## 0.15.1 — 2026-07-18

urlcheck: close a false-live gap found by a tamper/fabrication test case
against a real completed investigation.

- **`urlcheck.py` login-redirect detection** — access.redhat.com
  302-redirects some non-existent/gated paths into the SSO login flow,
  which returns 200; following that redirect made a dead reference look
  live. `check()` now inspects the final URL after redirects and
  classifies a landing on a login/SSO host (or `/auth|/oauth|/saml|…`
  path) as **gated** — existence not content-confirmed, reported
  separately, never counted as a clean live URL and never a hard FAIL.
  401/403/429 fold into the same `gated` class. Canonical fabricated
  errata IDs (e.g. `RHSA-2099:9999/` → 404) still FAIL as before; the
  real 18-URL report regresses clean at 18/18 live.
- **selftest.py** — added offline unit tests for `_is_login` and for
  `check()`'s gated-vs-dead classification (monkeypatched `_request`,
  no network), alongside the existing chain tamper/ledger-edit tests.

## 0.15.0 — 2026-07-18

pipeline: tamper-evident evidence chain — blockchain-style integrity
checking for case evidence:

- **`skills/janus/scripts/chain.py`** (stdlib-only) — per-case
  append-only hash ledger `cases/<id>/chain.jsonl`: each record holds a
  sealed file's sha256 plus the previous record's hash, so post-hoc
  edits to evidence are detectable (visible, never impossible —
  legitimate revisions append new records). `seal` / `verify` CLI;
  flock-serialized appends survive parallel stage writes;
  `artifacts/` (vmcore binaries) stays outside the chain as it stays
  outside git.
- **`hooks/evidence-chain.py`** (PostToolUse, fail-open) — auto-seals
  every Write/Edit into the evidence set (`case.yaml`,
  `findings/*.md`, `results/*.md`, `audit/*`, `verdict.md`); sealing
  never depends on agent diligence (the "make the signal external"
  principle).
- SKILL.md wiring: step 6 verifies+seals the chain before synthesize
  reads findings; step 7 runs `verify` as a mechanical pre-check before
  the named gates (FAIL → `NEEDS_HUMAN_<id>.md`, never quietly
  repaired); verdict.md is sealed after the human writes it, anchoring
  self-improver's ground-truth metrics. New "Evidence chain" section +
  case-tree entry.
- **`skills/janus/scripts/urlcheck.py`** (stdlib-only) — mechanical
  reference-URL liveness check backing gate G2-URL, run as a step-7
  pre-check on `results/report.md`: 404/410 or an unresolvable host is
  a provably fabricated citation (send-back under G2-URL); 401/403/429
  count as reachable (login-walled), 5xx/timeouts warn without
  blocking, and a fully-unreachable network downgrades to a notice —
  air-gapped okp-mcp installs stay usable.

## 0.14.0 — 2026-07-15

deck: pptx quality items C2–C4 from the JANUS-004 follow-up list (C1 —
body() run-level sizes — had already shipped in 0.12.0):

- **`d.add_code_block(slide, l, t, w, code, lang=…)` (C2 + C4)** — dark
  (#1E1E1E) ROUNDED_RECTANGLE code panel with VS Code Dark+ per-run
  syntax colors (yaml / bash / none), corner radius pinned small
  (`adjustments[0]=0.05`, adj 5000 ≈ 5% — the theme default is far too
  round), every line forced `PP_ALIGN.LEFT` (theme defaults can center
  shape text), auto-height from line count, `Courier New` mono (maps to
  Liberation Mono on Linux LibreOffice). The code stays real text —
  editable in pptx, copy-pastable from the PDF. Verified end-to-end:
  YAML/bash specs → pptx → PDF render with correct colors, JP comments
  in CJKjp, LiberationMono embedded.
- **body() overflow rule (C3)** — new gotcha #9: cap 16pt head / 14pt
  detail, max 5–6 pairs per slide, split beyond that; `body(tight=True)`
  compresses spacing to 1pt before/after. `body()` now warns on stderr
  when the caps are exceeded (build still succeeds); the rendered-PDF
  check remains the real catch.
- build_deck.py: `add_code_block` exposed as a spec op; `code:` values
  are verbatim (no `$today` expansion inside snippets). Date gotcha
  renumbered to #10.

## 0.13.0 — 2026-07-15

deck: declarative builds — writing a fresh Python build script per deck
was the remaining per-deck toil:

- **`scripts/build_deck.py`** — build a pptx from a YAML/JSON deck spec
  (`python3 scripts/build_deck.py deck.yaml`). Each slide is
  `layout:` + a `do:` list of `- <decklib method>: {kwargs}` entries
  (text/body/prose/disclaimer/fit/move/clear/picture/svg/refs/table/
  add_textbox); top-level keys cover template, output, named colors,
  `master_replace`, `keep_slides`, `move_to_end`. Iterating on a deck is
  now editing data, not rewriting code; the Python API stays as the
  escape hatch for what the ops can't express.
- The driver **enforces the gotchas instead of instructing them**:
  `refs` is reordered to run last on its slide (gotcha #7); a wrong
  placeholder `idx` fails loudly with the layout's available idx list
  (raw decklib silently no-ops); `$today` expands to the build date
  (gotcha #9); colors resolve from a named palette or hex; paths resolve
  relative to the spec file.
- SKILL.md: the spec build is the default step 3 (verified end-to-end:
  build → topdf → render, JP fonts intact); the direct-decklib path moved
  to 3b. New prerequisite: `pyyaml`.

## 0.12.0 — 2026-07-15

Pipeline knowledge from a GPU / model-serving case (deploy-then-discover
constraints cost hours of rebuild; written generically — the driving case
IDs stay in the project-local janus-lessons file):

- **doc-search: pre-deployment constraint check** — a new explicit phase
  for GPU / model-serving cases: ROSA Classic Marketplace-AMI
  instance-type allowlist (`rosa list instance-types` listing a type does
  not prove the AMI permits it — self-managed OCP has no such limit; the
  distinction must be stated in findings), GPU AZ availability, node disk
  ≥ 3× model size, serving-image quantization support (e.g. MXFP4). Plus
  a matching failure pattern.
- **lab-verify: pre-deploy gate + model-serving patterns** — confirm the
  doc-search constraint check ran before provisioning GPU/model-serving
  labs; never guess a serving-image tag (list running images with
  `oc get servingruntime -A -o custom-columns=...` and reuse a proven
  one — a guessed vLLM tag ends in ImagePullBackOff, and the same
  existence check applies when bumping an image in IaC); ModelCar disk
  ≥ 3× model size; endpoint clients (e.g. NeMo Guardrails
  `openai_api_base`) target the vLLM container port 8080, not the KServe
  Service port 80.
- **source-trace: TrustyAI guardrails dual-path pattern** — always trace
  both GuardrailsOrchestrator (FMS, legacy) and NemoGuardrails
  (recommended, RHOAI 3.4+), cross-check doc-search for the recommended
  path, and label which implementation each finding applies to; plus a
  generic parallel-implementations failure pattern.
- **synthesize: format-compatibility risk rule** — model/tool-selection
  hypotheses must name model-specific response-format interop risks
  (e.g. a Harmony-format model vs a guardrails self-check yes/no parser)
  explicitly, and list unverified integrations as gaps.
- **decklib: `body()` stamps paragraph-level default sizes** — run-level
  `rPr sz` was already set; `body()` now also writes `pPr/defRPr sz` at
  both levels so renderers that resolve from the paragraph default can't
  fall back to the theme size.

## 0.11.0 — 2026-07-13

deck skill improvements from case JANUS-002's IMPROVE feedback
(`review-queue/IMPROVE_2026-07-13-deck.md`; items 1–5 shipped, item 6 —
JANUS-report→slide semi-automation — deferred):

- **`d.refs(slide, items)` — overlap-safe reference footnotes** (was a local
  function in each build script). Call it last on a slide: it estimates the
  *rendered-text* bottom of the content (not the placeholder box, which often
  stretches to the slide bottom), places the refs in the free zone above the
  bottom margin, and with 3+ refs or too little room auto-compacts them into
  one wrapped `a | b | c` line a point smaller. Default width stays clear of
  the bottom-right footer chrome. Placement rules are keyword args, not a
  config file.
- **`d.prose(slide, idx, text)` — bullet-free narrative paragraphs.**
  `\n\n` splits spaced paragraphs, single `\n` is an in-paragraph line break;
  fixes `body()` rendering blank lines as empty ▸ bullets (公式見解 slides).
- **`d.svg(slide, src, l, t, …)` — one-call SVG embedding** (path or markup),
  rendered via svgtools/rsvg-convert with optional `light=True` recolor to the
  template palette; replaces the manual SVG→rsvg-convert→picture() dance. The
  svgtools CLI also accepts a bare `.svg` file (documented; already worked).
- **`d.disclaimer(slide, idx, conditions, notes)`** — the standard disclaimer
  pattern: conditions as bullets, notes as smaller grey non-bulleted ※-lines.
- **SKILL.md gotchas #6–#8**: `\n\n`-in-`body()` empty bullets → use `prose()`;
  fixed-top footnotes overlap full-height bodies → use `refs()` last; don't
  hard-code slide numbers in build-script comments — section names only.

All verified visually against the consulting template (5-slide smoke deck →
PDF → page render, including the compact-refs and full-height-body cases).
## 0.10.0 — 2026-07-12

Patterns adopted from [aws/agent-toolkit-for-aws](https://github.com/aws/agent-toolkit-for-aws):

- **Deterministic secret-safety PreToolUse hook.** The "no secret material
  in context" and "JANUS never mutates an AWS support case" invariants were
  prompt-level only; `plugins/janus/hooks/secret-safety.py` now denies them
  mechanically at the harness level: bulk secret dumps
  (`oc/kubectl get secret -o yaml|json`, `oc extract secret`,
  `aws secretsmanager get-secret-value`) and AWS support-case write
  commands. Scoped `-o jsonpath` single-key reads still pass. Findings and
  reports are committed to git, so dumped credentials would persist there —
  this closes the Bash side path that MCP tool grants could not cover.
- **Repo validator (`scripts/validate.py`).** Stdlib-only, CI-friendly
  checks for what the team-developer agent previously audited by judgment:
  marketplace ↔ plugin source paths, plugin.json/.mcp.json/hooks.json
  schema, SKILL.md and agent frontmatter (kebab-case name matching
  directory/filename), hook scripts existing, every SKILL.md pipeline
  stage having an agent definition (and vice versa), and CLAUDE.md
  @-references resolving.
- **doc-search recognizes the awslabs servers' successor.** AWS designated
  the Agent Toolkit for AWS as the successor to awslabs/mcp. When its
  managed `aws-mcp` server is registered, doc-search prefers its no-auth
  `search_documentation` / `retrieve_skill` over aws-docs; `call_aws` and
  `run_script` (live API access, script execution) are deliberately never
  granted to the static stage. The 0.9.0 awslabs servers keep working —
  this is a forward-compatibility path, not a migration.

## 0.9.0 — 2026-07-12

- **doc-search gains the ROSA/AWS layer via three AWS MCP servers.** The AWS
  mirror of the existing mslearn (ARO/Azure) integration, from
  [awslabs/mcp](https://github.com/awslabs/mcp): `aws-knowledge` (hosted,
  read-only, no auth — cross-searches AWS docs/blogs/What's New/API refs),
  `aws-docs` (read-only, no credentials, via `uvx`), and `aws-support`
  (needs AWS credentials + a Business/Enterprise plan). doc-search now
  covers ROSA-the-managed-service questions (supported versions, AWS-SRE
  responsibility split, AWS quotas/VPC/IAM/EC2 limits) the same way mslearn
  covers ARO, while OpenShift-the-product questions stay with okp-mcp.
- **aws-support is granted only its read-only `describe_*` tools.** The
  case create / reply / resolve / attachment-upload write tools are
  deliberately withheld from the doc-search agent — JANUS never mutates an
  AWS support case, keeping the read-only invariant intact.
- All three servers are **optional and environment-specific** — not bundled
  with the plugin. doc-search uses whichever are connected and skips the
  rest silently, noting the gap. Registration commands are documented in the
  README and the skill's MCP-dependencies section.

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
