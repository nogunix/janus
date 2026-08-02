# Changelog

Versions refer to the `janus` plugin (`plugins/janus/.claude-plugin/plugin.json`).

## 0.23.0 — 2026-08-02

Click-through evidence: the report's claims now link straight to the
finding that backs them, and a sixth mechanical pre-check makes sure
those links actually land somewhere.

- **synthesize emits links, not bare filenames.** Hypothesis evidence
  bullets, the Affected Artifacts source column, the References table,
  and — most importantly — each quote's attribution line become markdown
  links into `../findings/<stage>.md#f<n>-<slug>` or `../audit/<log>`.
  The anchor is built from the finding's own `### F<N>: <title>` heading
  using GitHub's rule, which the agent prompt now spells out: punctuation
  is *dropped*, not hyphenated, so `### F1: VM migration fails on OCP
  4.18.41` becomes `#f1-vm-migration-fails-on-ocp-41841` — the version's
  dots vanish rather than becoming separators.
- **`scripts/linkcheck.py`** (stdlib-only, offline) backs a new sub-code
  **C1/link**: every local link must resolve to a file that exists,
  inside the case directory, with any `#fragment` matching a heading
  there. `urlcheck.py` only sees `http(s)://`, so before this a relative
  link to a finding that was never written rendered as a perfectly
  ordinary link pointing at nothing — the same failure urlcheck catches,
  one layer down, and more misleading because a local link looks
  authoritative. It **never fails open**: local resolution is
  deterministic, so there is no air-gapped case where the answer is
  unknowable. Fenced code blocks are ignored; a report with no links at
  all warns rather than failing.
- **`quotecheck.py` accepts a linked attribution.** This was a blocking
  interaction, found by testing before shipping: making the attribution
  line clickable — the reader's main jump-off point — caused quotecheck
  to stop recognising the blockquote as attributed at all, silently
  turning every report into a `C2/quote-absent` send-back. It now takes
  both `> — findings/x.md` and `> — [F3](../findings/x.md#f3-…)`, reads
  the *target* rather than the free-form link text, drops the fragment,
  and rejects a target that escapes the case directory. Quote text
  itself must still never contain a link — it stays byte-identical to
  the finding.

## 0.22.0 — 2026-08-02

Japanese report mode, plus a fifth mechanical pre-check that keeps its
prose readable. The other four checks ask whether the report is *true*;
none asked whether it was *readable*, which for a Japanese deliverable is
a real gap — a technically correct report that mixes ですます and である or
runs 200-character sentences is not something you hand a customer.

- **`report_language` in `case.yaml`** — `en` (default) or `ja`. With
  `ja`, synthesize writes the **prose** in Japanese while the
  **structure stays English**: headings, table headers, and the label
  vocabulary (`Confidence`, `Basis`, `VERIFIED`, `H1`/`F1`) are a
  machine-readable contract that gate C2/section and the mechanical
  checks read by name, so translating a heading breaks a gate rather
  than restyling it.
- **`scripts/prosecheck.py`** (stdlib-only itself) wraps
  [textlint](https://github.com/textlint/textlint) with the
  [ja-technical-writing](https://github.com/textlint-ja/textlint-rule-preset-ja-technical-writing)
  preset, backing a new sub-code **C2/prose**. It never rewrites: `--fix`
  would mutate prose that `chain.py` has sealed and `quotecheck.py`
  cross-checks, and would break the standing rule that the lead never
  patches the report itself. Violations go back to synthesize.
- **Two preset rules deliberately off.** `ja-no-weak-phrase` flags
  hedging, but in JANUS a LOW-confidence hypothesis is *supposed* to read
  as uncertain — forcing assertive prose would make the report overclaim,
  the exact failure the Confidence/Basis labels prevent.
  `max-kanji-continuous-len` fires constantly on Red Hat product names.
- **Fails open in every direction**, as the only check depending on an
  external tool: English case, textlint not installed, preset missing, no
  report yet — all print a notice and exit 0. `npx` is invoked with
  `--no-install` so nothing downloads mid-investigation. **A notice means
  *not checked*, never *passed***: an early cut printed `OK: passes` when
  `npx --no-install` exited non-zero with empty stdout, i.e. claimed a
  pass for a check that never ran. Now any non-JSON or unexpected-exit
  result is a notice, with three regression tests behind it.
- **Quoted evidence is never linted.** `textlintrc.json` excludes
  BlockQuote / CodeBlock / Code / Table / Header via
  `textlint-filter-rule-node-types` — "improving" the wording of a quote
  that `quotecheck.py` matches byte-for-byte against its finding is
  falsification, not editing. Measured honestly, this filter is currently
  a no-op: the preset's own rules already skip those node types. It is
  kept as a backstop for rules added later (`prh` for terminology does
  match inside blockquotes), and the script says so rather than implying
  the filter is what protects the quotes.
- CI is unchanged — no npm install step, because the check degrades to a
  notice there.

## 0.21.0 — 2026-08-02

iac-author: a new static stage that builds the lab's Infrastructure-as-Code
with the `terraform` and `ansible` MCP servers, and hands it to lab-verify
to execute. The split is the point — authoring a `.tf` touches no
infrastructure, so it runs autonomously in the fan-out; *applying* it stays
entirely inside lab-verify's `review-queue/APPROVE_<id>.md` gate.

- **`agents/iac-author.md`** (sonnet, static). Looks every provider
  argument, version pin and module up in the registry rather than
  recalling it — a remembered argument name is the most common reason
  generated IaC fails at apply time, after the human has approved and
  started paying. Runs the pre-deploy constraint check *before* writing
  values (instance-type allowlist, GPU AZ availability, node disk ≥ 3×
  model size, image tags that actually exist), and writes `fmt`-ed,
  `validate`-d, `ansible-lint`-clean code into `cases/<id>/iac/`. An
  unconfirmed value is left un-defaulted with a `TODO(iac-author)` at the
  line, never filled with a plausible guess.
- **Static validation only**: `terraform fmt` / `init -backend=false` /
  `validate`, `ansible-lint`, `ansible-playbook --syntax-check`.
  `terraform plan` is forbidden in this stage alongside `apply` — plan
  needs real credentials and reads live state, which makes it a
  live-target read, not a syntax check.
- **lab-verify consumes `cases/<id>/iac/`** and is the only stage that
  executes it, as explicit Bash commands teed into `audit/` — so the
  command string is what the evidence chain hashes. It refuses to apply
  code whose `findings/iac-author.md` says `status: failed`, and the lead
  will not launch it before that file exists (approval covers applying
  the code; there is nothing to apply yet).
- **The tool-grant boundary is now mechanical.** `validate.py` gained
  `validate_tool_grants()`, which fails the build if any agent grants
  `mcp__ansible__ansible_navigator` (runs playbooks, and auto-retries with
  `--ee false` on a container error — changing execution semantics without
  the agent deciding to), `mcp__ansible__ade_setup_environment` (runs the
  host package manager), or either server as a wildcard. `mcp__terraform__*`
  is barred specifically because that server's read-only registry tool set
  gains `create_run` / `apply_run` the moment a user enables its enterprise
  tools with a token — a wildcard would inherit them silently. Grants are
  enumerated instead.
- **No Terraform state in context**, in both agents and the SKILL safety
  list: `terraform.tfstate` routinely holds plaintext credentials and
  findings are committed to git, so a single value comes from
  `terraform output <name>`. `cases/<id>/iac/` stays outside the evidence
  chain, as `artifacts/` does.
- Finding `Type` gained `constraint`; the reference table gained
  `terraform` and `iac` rows; `tracks: [iac]` composes
  `iac-author | synthesize` when reproducible IaC is the deliverable
  rather than a lab run.

## 0.20.2 — 2026-07-30

doc-search: propagate the 0.20.1 okp-mcp corrections into the agent that
actually runs. 0.20.1 fixed `skills/okp-doc-search/SKILL.md` only, but the
same guidance is inlined in `agents/doc-search.md` — the copy the pipeline
stage reads — so the wrong `/index.html` rule and the "query is required"
half-truth were still in force at run time.

- **`agents/doc-search.md` okp-mcp usage knowledge** now carries the
  trailing-slash rule (errata / CVE take a bare `/`, appending
  `/index.html` breaks them), the articles and CVE doc_id rows, the URL-as-
  doc_id nuance, and the lexical-query requirement.
- **Two new failure patterns** in the same agent: "Document not found"
  covers four causes and must be worked in order; a recent-topic negative
  is judged against the cutoff derived from `Issued`/`Updated` dates on
  real hits, not assumed to be a corpus gap.

Reminder for future edits: okp-mcp mechanics live in **two** places by
design (skill + inlined agent knowledge). Fixing one without the other
leaves the pipeline on the old text.

## 0.20.1 — 2026-07-30

okp-doc-search: correct three factual errors in the `get_document`
mechanics section, all re-verified against a live okp-mcp corpus.

- **`/index.html` is not universal.** Errata (`/errata/RHSA-YYYY:NNNNN/`)
  and CVE (`/security/cve/CVE-YYYY-NNNN/`) doc_ids end in a bare slash;
  appending `/index.html` to an erratum returns "Document not found". The
  rule is now stated as: use the result URL's path as-is, appending
  `/index.html` only when it does not already end in `/`. Errata, CVE and
  articles rows added to the doc_id table.
- **A missing `query` does not produce a nudge** — it returns
  `Document not found: <doc_id>` for a doc_id that resolves fine with a
  query. So does a query sharing no terms with the document, since
  retrieval is lexical.
- **A URL is accepted as doc_id** (the domain is stripped), but only when
  the remaining path already matches the doc_id form — previously
  documented as always failing.
- New "Document not found is ambiguous" recovery order: suffix form →
  missing query → non-matching query → genuinely unindexed.
- **Corpus-staleness principle re-scoped** — "content from the last few
  months is likely absent" was pessimistic (the corpus carried
  two-week-old errata when checked); the skill now says to derive the
  cutoff from the `Issued`/`Updated` dates on actual hits.

The rest of the skill was spot-checked at the same time and left as is:
the docs.redhat.com → doc_id conversion example resolves, docs.redhat.com
still 403s direct fetches, and both "whole URL as query" and "bare
solution number" do miss as documented.

## 0.20.0 — 2026-07-25

knowledge: bundle a read-only OpenShift triage reference, distilled from
the community `openshift-ops` plugin (4 skills) and re-scoped to JANUS's
read-only / approval-gated discipline. Every item is tagged 🔍 DIAGNOSTIC
(autonomous-safe on an approved lab) or ⚠️ REMEDIATION (report-only —
JANUS never mutates cluster state autonomously).

- **New plugin-bundled skill** `skills/ocp-triage-heuristics/SKILL.md` —
  layered triage, app failure-mode chains, operator status-triple + OLM
  lifecycle, node lifecycle, and upgrade gates.
- **Wired into fan-out** — relevant sections are copied into the briefs
  of investigation-planner, lab-verify, live-tracer, doc-search and
  synthesize, and into the upgrade-compat case type; 🔍/⚠️ tags are
  preserved through the copy.
- **Documented as a plugin-bundled reference**, distinct from the
  writable, project-local `janus-lessons` loop.

Source: `openshift-ops`, marketplace ecosystem-claude-plugins
(redhat-community-ai-tools/claude-plugins), Apache-2.0, author Eran Cohen.

## 0.19.1 — 2026-07-20

source-trace: two guardrails from case osc-112-lab-verify, where a
finding was marked VERIFIED off a source comment that was itself wrong,
and a proposal carried line numbers that had drifted between the casket
snapshot and upstream HEAD.

- **Basis semantics** sharpened: a code comment or doc string is the
  author's *intent*, not the code's *behavior*, and can be wrong — a
  claim resting on a comment is REASONED at most; a VERIFIED behavioral
  claim needs the executable code path itself (or an execution result),
  never a comment asserting it.
- **Line numbers are pinned to the casket snapshot, not HEAD**: casket
  indexes a specific commit whose file structure and line numbers can
  differ from current upstream HEAD. State the casket ref (SHA/NVR) on
  any `file:line` citation, and flag a load-bearing line number for
  github-trace to confirm against HEAD before it ships in a report.

Both are also captured as transferable `janus-lessons` entries (the
project-local ledger copied into stage briefs at fan-out).

## 0.19.0 — 2026-07-20

guardrails: close two AI-runaway gaps the existing checks left open,
raised in review — an AI that generates settings without confirming
they aren't deprecated, and reliance on GitHub URLs that resolve but may
be inaccurate. Both were guidance living in agent prose; this makes them
named send-back gates the lead enforces.

- **`C1/currency`** — a report that recommends a configuration, feature,
  flag, or API with no lifecycle check against the target version is
  sent back to doc-search. doc-search gains a **Currency / deprecation
  check** phase (parallel to the pre-deploy constraint check): any
  setting the report would recommend must be confirmed against official
  release notes / lifecycle docs (deprecated / removed / superseded)
  before it becomes a finding; an unconfirmable one rides as ASSUMED,
  never HIGH. Trusted-doc-path principle — only official sources
  ground a recommendation.
- **`C1/source-of-truth`** — a load-bearing source-content claim resting
  only on a GitHub URL while a `casket` server is connected is sent back
  to source-trace for corroboration against the own-server source index.
  github-trace's rule is strengthened: a resolving GitHub URL is not an
  accurate one (wrong line, build divergence, plausible-but-wrong page),
  so a source-content claim is at most REASONED-about-upstream on GitHub
  alone and must be casket-corroborated before a HIGH downstream
  conclusion. Own-server-source-of-truth principle, complementing
  urlcheck.py (which catches only dead URLs, not inaccurate live ones).

## 0.18.0 — 2026-07-19

pipeline: catch version-provenance drift mechanically — a fact observed
at one product version reworded into a claim about another. The gap the
existing integrity checks left open: the hash chain sees file edits, the
quote check sees mutated verbatim quotes, but neither catches a finding
or report that silently attributes a fact to the wrong OCP/RHEL/CNV
version. Staged rollout — anchor + one precise hard-FAIL now, per-finding
`Applies-to` fields deferred until warnings show they're needed.

- **`scripts/versioncheck.py`** (stdlib-only, offline, like the other
  three) walks a case's findings and report. **One hard FAIL**: a source
  location cited with no version anywhere in its Ref (no NVR, casket
  path, or commit sha) — which version was read is unrecoverable. Sent
  back **under the new `C2/version` sub-code**. Everything else is a
  warning the lead judges: a Detail/Ref pair crossed *within one product
  family* (Detail says 4.16, Ref pins 4.18), or a finding/report version
  in a scoped family but off-scope.
- **`version_scope` in `case.yaml`** (optional) — the version(s) a case
  turns on, grouped by product (`OCP: ["4.16"]`); a z-stream matches its
  minor (`4.16` covers `4.16.55`). It anchors the scope/attribution
  warnings; absent it, only the unpinned-citation FAIL runs.
- **Family-anchoring keeps the signal clean** — version tokens are
  grouped by major component, so kernel `5.14`, image tags (`427.105.1`),
  and RPM releases never get compared against an OCP minor. 4-octet IPs
  are excluded from token extraction outright.
- Wired into Step 7 as the fourth mechanical pre-check; `C2/version`
  added to the C2 gate's send-back vocabulary; self-tests extended.

## 0.17.0 — 2026-07-19

pipeline: consolidate the seven step-7 acceptance gates into two
judgment gates. Prompted by the "add as little process as you can"
lens from *Project management at Big Tech* (Pragmatic Engineer) — where
a mechanical check already exists, the human's read of the report
should not repeat it.

- **Step 7 gates G1–G7 → C1/C2** — the lead's read of `report.md`
  collapses from seven passes to two: **C1 GROUNDING** (is every claim
  anchored to evidence at the right strength?) absorbs the old
  G1-REF/G2-URL/G3-SPECULATION/G4-BASIS; **C2 COMPLETENESS & FIDELITY**
  (is the report structurally complete and are identifiers/quotes
  reproduced exactly?) absorbs G5-COMPLETE/G6-ARTIFACTS/G7-QUOTE.
  Failure coverage is unchanged — every old trigger survives either as
  a mechanical pre-check (urlcheck/quotecheck) or as a named send-back
  sub-code (`C1/ref`, `C1/url`, `C1/basis`, `C1/spec`, `C2/section`,
  `C2/artifact`, `C2/quote-absent`, `C2/quote-mismatch`). The send-back
  vocabulary keeps the diagnostic granularity of the old seven gates;
  only the reviewer's entry points shrink.
- **Loop-stop granularity moved to the sub-code** — "same gate fails
  twice → NEEDS_HUMAN" is now "same *sub-code* fails twice", preserving
  the old behavior (a specific unresolved defect recurring) under the
  coarser gates rather than stopping on any C1 repeat.
- **Companion updates** — `synthesize.md` (G7-QUOTE→C2/quote,
  G4-BASIS→C1/basis), `urlcheck.py`/`quotecheck.py` docstrings and
  send-back messages, and README gate prose all track the new codes.

## 0.16.1 — 2026-07-19

urlcheck: a second false-live/false-dead gap, the mirror of 0.15.1 —
this time a live host wrongly reported dead.

- **`urlcheck.py` connection-reset classification** — `issues.redhat.com`
  resets automated clients (anti-automation), which `check()` was
  lumping into the catch-all `unreachable` → hard **G2-URL FAIL**, so
  any report citing an OCPBUGS-/RHEL- Jira URL risked a spurious
  send-back (and pressure to drop a valid citation). A connection
  *reset* proves the host resolved and completed the TCP handshake — it
  is provably live — so it is now a non-blocking `warn`, alongside
  5xx/timeout. Unresolvable-host and connection-*refused* stay hard
  FAILs. Found by case 2026-07-19-strace-eacces-svc (OCPBUGS-4077
  reported dead while returning HTTP 200 by hand). Fail-open, stdlib-only.
- **selftest.py** — two cases added: a reset from a live host warns (not
  FAILs); a connection refused stays a hard FAIL.

## 0.16.0 — 2026-07-19

Keep facts from mutating mid-collaboration, on both paths: a stage
accidentally overwriting another stage's findings file, and the
telephone-game drift where synthesize subtly rewrites a fact while
copying it into the report.

- **Fan-in write-lock** — `chain.py lock|unlock`: at step 6 the lead
  drops the write bits on the fact base (`case.yaml`, `findings/*.md`,
  `audit/*`). New PreToolUse hook `hooks/evidence-lock.py` denies
  tracked Write/Edit calls against locked files with an explanation
  (instead of a bare permission error an agent might chmod around).
  The chain detects rewrites after the fact; the lock prevents the
  accident. `unlock` is the lead's explicit escape hatch
  (unlock → edit → re-seal → lock). Fail-open, stdlib-only.
- **`quotecheck.py` + gate G7-QUOTE** — the report carries its
  load-bearing facts as attributed verbatim blockquotes
  (`> …` / `> — findings/<stage>.md`); the script verifies each quote
  appears word-for-word (whitespace-normalized) in the file it cites.
  A mutated quote or fabricated attribution FAILs → send-back under
  the new G7-QUOTE gate (step 7 mechanical pre-check #3). synthesize's
  template and rules now require the quote convention.
- **selftest.py** — lock/deny/unlock round-trip and quotecheck
  extraction/mutation/missing-file/no-quotes cases (24 checks total).

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
