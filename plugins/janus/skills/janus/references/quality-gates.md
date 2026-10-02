<!-- Part of the janus skill. SKILL.md says when the lead reads this file. -->

# Quality check — mechanical pre-checks in detail

Read at step 7 (or whenever a check prints a warning or notice). SKILL.md
step 7 carries the summary table and the C1/C2 judgment gates; this file
carries each check's full behaviour and the fail-direction contract.

## The six checks

Mechanical pre-checks before any content gate (all six scripts live
in `scripts/` next to SKILL.md):

1. `python3 <skill-dir>/scripts/chain.py verify cases/<id>` — a FAIL
   means evidence changed after it was sealed; do not hand off. Record
   the mismatch in `cases/<id>/audit/` and write
   `review-queue/NEEDS_HUMAN_<id>.md` quoting the failing entries.
2. `python3 <skill-dir>/scripts/urlcheck.py cases/<id>/results/synthesis.md`
   — curl-level liveness for every reference URL. A FAIL (404/410 or
   unresolvable host) is a provably dead citation: send the report back
   to synthesize **under C1/url**, quoting the dead URL. 401/403/429
   count as reachable (login-walled is normal for access.redhat.com);
   warnings (5xx/timeout) don't block. If the network itself is down
   the script says so and passes — offline installs are normal.
3. `python3 <skill-dir>/scripts/quotecheck.py cases/<id>/results/synthesis.md`
   — every attributed blockquote in the report (`> …` ending in
   `> — findings/<stage>.md`) must appear verbatim
   (whitespace-normalized) in the file it cites. A FAIL is a fact that
   mutated between findings and report, or a fabricated attribution:
   send the report back to synthesize **under C2/quote-mismatch**,
   quoting the mismatch. A "no attributed quotes" warning means
   synthesize skipped the quote convention — also a **C2/quote-absent**
   send-back for any report that makes evidence-backed claims.
4. `python3 <skill-dir>/scripts/versioncheck.py cases/<id>` — version
   provenance across findings and the report. A FAIL is a source
   location cited with no version pin anywhere in its Ref (no NVR,
   casket path, or commit) — which version was read is unrecoverable:
   send back **under C2/version**, quoting the Ref. Everything else is a
   warning the lead judges against **C2/version**: a Detail/Ref pair
   crossed *within one product family* (Detail says 4.19, Ref pins
   4.20), or — when `version_scope` is declared — a finding or report
   version in that family but off-scope (a neighbouring version drifted
   in). Warnings never block; they feed the judgment call below.
5. `python3 <skill-dir>/scripts/linkcheck.py cases/<id>/results/synthesis.md`
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
6. `python3 <skill-dir>/scripts/prosecheck.py cases/<id>` — Japanese
   prose quality, and **only when `report_language: ja`**; an English
   case prints a notice and passes. It runs textlint with the
   ja-technical-writing preset over the report's prose, leaving quoted
   evidence, code, tables and headings alone. A FAIL is a readability
   defect in synthesize's own writing — mixed である/ですます, a sentence
   past ~120 characters, 4+ 読点, 半角ｶﾀｶﾅ: send back **under C2/prose**,
   quoting the offending line. This is the only check that depends on an
   external tool, so it fails open in every direction (textlint not
   installed, preset missing, no report yet) with a notice and exit 0.
   **A notice means *not checked*, never *passed*** — if a Japanese
   report matters and you see one, install textlint rather than treating
   the silence as a pass.

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
  unknowable here (no network, no textlint, nothing sealed yet).
  Air-gapped and minimal installs have to stay usable.
- **warn** — passes, and hands the lead a judgment call under a named
  sub-code.

**A notice means *not checked*, never *passed*.** This holds for every
row below, not only prosecheck: a check that printed a notice has told
you it declined to answer. Reading that as a pass is the one way this
table gets silently defeated. If the property matters for the case in
hand, restore what the check needs — network, textlint, a seal — and run
it again.

| Check | Proves a defect → | Cannot decide → | Note |
|---|---|---|---|
| `chain.py verify` | **closed** — a file changed after its seal (TAMPER), or a malformed ledger | **warn** — a tracked file that was never sealed prints `warning: unsealed` and exits 0 | Unsealed is the shape a *hook* failure takes, not a tamper. A persistent unsealed warning on evidence you expect sealed is a hook to fix, not noise. |
| `urlcheck.py` | **closed** — 404/410 or an unresolvable host: a provably dead citation (`C1/url`) | **open** — no network at all: says so and passes; 5xx/timeout warn | 401/403/429 count as reachable. Login-walled is normal for access.redhat.com, so a gated URL is classified, never failed. |
| `quotecheck.py` | **closed** — an attributed quote not verbatim in the file it cites (`C2/quote-mismatch`) | **warn** — no attributed quotes at all (`C2/quote-absent` for any evidence-backed report) | Absence of quotes is mechanically indistinguishable from a report that legitimately has none. |
| `versioncheck.py` | **closed** — a source citation with no version pin anywhere in its Ref: which version was read is unrecoverable | **warn** — crossed or off-scope versions (`C2/version`), and every scope check when no `version_scope` is declared | |
| `linkcheck.py` | **closed** — a local evidence link resolving to no file or no anchor (`C1/link`) | **never arises** — local resolution is deterministic | The one check with no fail-open path. A report with no local links at all is a warning. |
| `prosecheck.py` | **closed** — a ja-technical-writing violation in synthesize's own prose (`C2/prose`) | **open in every direction** — textlint absent, preset missing, no report yet | The only check that shells out, hence the widest open path. |
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
