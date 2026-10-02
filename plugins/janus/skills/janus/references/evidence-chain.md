<!-- Part of the janus skill. SKILL.md says when the lead reads this file. -->

# Evidence chain (tamper-evidence)

Each case carries an append-only hash ledger, `cases/<id>/chain.jsonl`:
every record holds the sha256 of one evidence file plus the hash of the
previous record, blockchain-style. It makes edits **visible, never
impossible** — a legitimate revision appends a new record; an edit that
bypasses sealing breaks `verify`. The helper is `scripts/chain.py`,
next to SKILL.md (stdlib-only):

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
revisions of `synthesis.md` are normal, and the ledger keeps the full
revision history. Warnings (`unsealed: …`) mean a file exists but was
never sealed — run `seal`; FAILs mean the ledger or a sealed file was
altered — that is a human matter, never something to quietly repair.
`artifacts/` (vmcore binaries) stays outside the chain, as it stays
outside git.
