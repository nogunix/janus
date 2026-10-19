<!-- Part of the janus skill. SKILL.md says when the lead reads this file. -->

# Quality check — mechanical pre-checks in detail

Read at step 7 (or whenever a check prints a warning or notice). SKILL.md
step 7 carries the summary table and the C1/C2 judgment gates; this file
carries each check's full behaviour and the fail-direction contract.

## The seven checks

Mechanical pre-checks before any content gate (all seven scripts live
in `scripts/` next to SKILL.md). `scripts/gates.py cases/<id>` runs them
in this order and prints a status per check; the detail below is what
each one means:

1. `python3 <skill-dir>/scripts/chain.py verify cases/<id>` — a FAIL
   means evidence changed after it was sealed; do not hand off. Record
   the mismatch in `cases/<id>/audit/` and write
   `review-queue/NEEDS_HUMAN_<id>.md` quoting the failing entries.
2. `python3 <skill-dir>/scripts/reportlint.py cases/<id>` — the report
   against its own template and against the findings it was built from.
   Three kinds of FAIL, each routed by the sub-code the script prints:
   **C2/section** for a missing section (by the mode `case.yaml`
   declares), an empty or still-`<placeholder>` cell, an Objectives
   Assessment status outside `Achieved | Partial | Not achieved`, and —
   the part no reader reliably does — any figure that can be recomputed
   and disagrees: the Total findings and Evidence basis tallies, the
   `models used` pairs against each findings file's own `model:` key,
   and each Stages Used row against that stage's status and finding
   count. **C1/basis** for a hypothesis whose cited findings do not
   carry its confidence (HIGH needs one VERIFIED or two REASONED from
   different stages; ASSUMED-only cannot exceed LOW). **C1/ref** for a
   cited finding number that no findings file defines — a reference to
   evidence that does not exist. Warnings: a hypothesis citing nothing,
   a finding the report never cites, a supplement the metadata omits.
   Like linkcheck.py it never fails open; every input is local.
3. `python3 <skill-dir>/scripts/urlcheck.py cases/<id>/results/synthesis.md`
   — curl-level liveness for every reference URL. A FAIL (404/410 or
   unresolvable host) is a provably dead citation: send the report back
   to synthesize **under C1/url**, quoting the dead URL. 401/403/429
   count as reachable (login-walled is normal for access.redhat.com);
   warnings (5xx/timeout) don't block. If the network itself is down
   the script says so and passes — offline installs are normal.
4. `python3 <skill-dir>/scripts/quotecheck.py cases/<id>/results/synthesis.md`
   — every attributed blockquote in the report (`> …` ending in
   `> — findings/<stage>.md`) must appear verbatim
   (whitespace-normalized) in the file it cites. A FAIL is a fact that
   mutated between findings and report, or a fabricated attribution:
   send the report back to synthesize **under C2/quote-mismatch**,
   quoting the mismatch. A "no attributed quotes" warning means
   synthesize skipped the quote convention — also a **C2/quote-absent**
   send-back for any report that makes evidence-backed claims.
5. `python3 <skill-dir>/scripts/versioncheck.py cases/<id>` — version
   provenance across findings and the report. A FAIL is a source
   location cited with no version pin anywhere in its Ref (no NVR,
   casket path, or commit) — which version was read is unrecoverable:
   send back **under C2/version**, quoting the Ref. Everything else is a
   warning the lead judges against **C2/version**: a Detail/Ref pair
   crossed *within one product family* (Detail says 4.19, Ref pins
   4.20), or — when `version_scope` is declared — a finding or report
   version in that family but off-scope (a neighbouring version drifted
   in). Warnings never block; they feed the judgment call below.
6. `python3 <skill-dir>/scripts/linkcheck.py cases/<id>/results/synthesis.md`
   — every local evidence link in the report resolves: the target file
   exists, sits inside the case directory, and any `#fragment` matches a
   heading in it. urlcheck only sees `http(s)://`, so a relative link to
   a finding that does not exist — or to an anchor no heading produces —
   renders as an ordinary link and points at nothing. A FAIL is that
   defect: send back **under C1/link**, quoting the link. This check
   never fails open; local resolution is deterministic, so there is no
   air-gapped case where the answer is unknowable. A report with no
   local links at all is a warning, not a FAIL — the lead judges it
   against C1/link.
7. `python3 <skill-dir>/scripts/prosecheck.py cases/<id>` — Japanese
   prose quality, and **only when `report_language: ja`**; an English
   case prints a notice and passes. It checks the report's prose against
   the ja-technical-writing rules configured in `scripts/textlintrc.json`,
   leaving quoted evidence, code, tables and headings alone — through the
   claude CLI (Sonnet) first, and textlint when the CLI is absent or the
   call fails. The Sonnet backend sends only the first 30,000 characters
   and warns about the unchecked rest. A FAIL is a readability
   defect in synthesize's own writing — mixed である/ですます, a sentence
   past 120 characters, 4+ 読点, 半角ｶﾀｶﾅ: send back **under C2/prose**,
   quoting the offending line. This is the only check that depends on an
   external tool, so it fails open in every direction (neither the
   claude CLI nor textlint usable, preset missing, no report yet) with a
   notice and exit 0. **A notice means *not checked*, never *passed*** —
   if a Japanese report matters and you see one, make a backend available
   rather than treating the silence as a pass.

Each check's behaviour when it *cannot* decide — and what a notice
means — is the Fail direction table below; read it before trusting a
pass.

## Fail direction (what each check does when it cannot decide)

Every check answers two questions, and the second is the one that gets
forgotten: what does it do when it **proves** a defect, and what does it
do when it **cannot tell**? The second answer is a safety property, not
an implementation detail — it decides whether an unprovable case leaves
the pipeline blocked or quietly released. Three directions, and only
three:

- **closed** — blocks the handoff. Reserved for defects the check can
  prove from what it has in hand.
- **open** — passes with a notice, because the answer is genuinely
  unknowable here (no network, no prose backend, nothing sealed yet).
  Air-gapped and minimal installs have to stay usable.
- **warn** — passes, and hands the lead a judgment call under a named
  sub-code.

**A notice means *not checked*, never *passed*.** This holds for every
row below, not only prosecheck: a check that printed a notice has told
you it declined to answer. Reading that as a pass is the one way this
table gets silently defeated. If the property matters for the case in
hand, restore what the check needs — network, a prose backend, a seal — and run
it again.

| Check | Proves a defect → | Cannot decide → | Note |
|---|---|---|---|
| `chain.py verify` | **closed** — a file changed after its seal (TAMPER), or a malformed ledger | **warn** — a tracked file that was never sealed prints `warning: unsealed` and exits 0 | Unsealed is the shape a *hook* failure takes, not a tamper. A persistent unsealed warning on evidence you expect sealed is a hook to fix, not noise. |
| `reportlint.py` | **closed** — a missing section, an empty or placeholder cell, a stated figure the findings contradict (`C2/section`), a confidence its cited bases do not carry (`C1/basis`), a cited finding number that does not exist (`C1/ref`) | **warn** — a hypothesis citing no finding, a finding the report never cites, a supplement the metadata omits | Absence of a citation is mechanically indistinguishable from a section that legitimately needs none, so it warns. Everything it fails on is derived from files in the case directory. |
| `sendback.py` (step 7, each send-back) | **closed** — a sub-code recorded twice, or a fourth round: exit 1, stop the loop at NEEDS_HUMAN | **never arises** — the verdict is computed from the ledger on disk | Not a check on the report but on the review of it. The ledger outlives the session: after a compaction, `sendback.py status` is how the lead learns which round it is on instead of guessing low. |
| `caselint.py` (intake, step 1) | **closed** — a required key missing, or a `mode` / `status` / `tracks` / `report_language` / `version_scope` value outside its vocabulary | **never arises** — the case.yaml is the whole input | The only check that runs *before* the work. Its subject is the fields whose wrong value is accepted rather than rejected downstream — `report_language: jp` composes localize and skips prosecheck. |
| `urlcheck.py` | **closed** — 404/410 or an unresolvable host: a provably dead citation (`C1/url`) | **open** — no network at all: says so and passes; 5xx/timeout warn | 401/403/429 count as reachable. Login-walled is normal for access.redhat.com, so a gated URL is classified, never failed. |
| `quotecheck.py` | **closed** — an attributed quote not verbatim in the file it cites (`C2/quote-mismatch`) | **warn** — no attributed quotes at all (`C2/quote-absent` for any evidence-backed report) | Absence of quotes is mechanically indistinguishable from a report that legitimately has none. |
| `versioncheck.py` | **closed** — a source citation with no version pin anywhere in its Ref: which version was read is unrecoverable | **warn** — crossed or off-scope versions (`C2/version`), and every scope check when no `version_scope` is declared | |
| `linkcheck.py` | **closed** — a local evidence link resolving to no file or no anchor (`C1/link`) | **never arises** — local resolution is deterministic | The one check with no fail-open path. A report with no local links at all is a warning. |
| `prosecheck.py` | **closed** — a ja-technical-writing violation in the report's prose (`C2/prose`) | **open in every direction** — neither claude CLI nor textlint usable, preset missing, no report yet; **warn** — a report past 30,000 characters, for the tail the Sonnet backend did not see | The only check that shells out, hence the widest open path. A `report_language` that is neither `en` nor `ja` is *not* one of those directions: localize still translates the report, so gates.py reports an ERROR naming caselint.py rather than a skip that reads like an English case. |
| `secret-safety.py` (PreToolUse) | **closed** — denies a matched bulk-secret command | **open by construction** — it stops only the patterns it knows | A known-shape blocklist, not a boundary. Never restructure a command to slip past it. |
| `evidence-lock.py` (PreToolUse) | **closed** — denies a write to a locked file | **open** — an exception emits no deny and the write proceeds | Backstopped by the filesystem: `chain.py lock` drops the write bits, so the write still fails when the hook does. |
| `evidence-chain.py` (PostToolUse) | *n/a* — auto-seals tracked writes | **open, silently** — every exception is swallowed, exit 0 | A failed seal is invisible at write time and surfaces only as `chain.py verify`'s unsealed warning. |

`chain.py verify` is the one that behaves like attestation: it runs
before handoff, and on a proven mismatch the case does not go out
degraded-but-delivered — it stops and becomes `NEEDS_HUMAN_<id>.md`. The
report is never released as "produced, but with an evidence base we
could not vouch for".

**Preserve the direction when editing a check.** Fail-open where a check
cannot prove a negative is deliberate: it is what keeps offline and
minimal installs usable. Fail-closed where it can prove one. Moving a
row from open to closed makes JANUS unusable in some install; moving one
from closed to open removes a guarantee without announcing it. Either
way, move the row in this table in the same commit.
