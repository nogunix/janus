#!/usr/bin/env python3
"""Per-case tamper-evident evidence chain (blockchain-style hash ledger).

`cases/<id>/chain.jsonl` is an append-only ledger: one JSON record per
line, each carrying the sha256 of a sealed evidence file plus the hash
of the previous record. Like a blockchain, the linkage makes history
tamper-evident, not tamper-proof: edits stay possible, but every edit
either appends a visible new record or breaks verification.

Revisions are normal — re-sealing a changed file appends a new record
(report send-backs, findings updates). Tampering is a sealed file whose
current content matches no record, or a broken hash link.

Sealing happens two ways:
- hooks/evidence-chain.py (PostToolUse) seals tracked Write/Edit calls
  automatically as stages work;
- `chain.py seal` covers files written outside tracked tools (shell
  redirects into audit/, the human's hand-written verdict.md).

The CLI `seal` only adds files that are new to the ledger. A file that
was sealed and has changed since is exactly what `verify` reports as
TAMPER, and re-sealing it erases that signal: the next `verify` reads
OK. Twice in practice (a python one-off in synthesize, a lead's
`cat >>` onto an audit note) the change came from a shell write and
was re-sealed in the same command line as the failing verify. So the
CLI refuses those files and exits 1 unless the caller names the
reason with `--accept-change "<why>"`; the reason is stored in the
ledger record, so the acceptance is part of the history. The library
`seal()` stays permissive for the tracked writers (the PostToolUse
hook, sendback.py), whose changes are legitimate by construction.

The chain detects rewrites after the fact; `lock` prevents the accident
in the first place. At fan-in the lead locks the fact base synthesize
reads (case.yaml, findings/*.md, audit/*) by dropping the files' write
bits — hooks/evidence-lock.py (PreToolUse) then denies tracked writes
with an explanation instead of a bare permission error. `unlock` is the
lead's explicit escape hatch for a legitimate revision
(unlock → edit → re-seal → lock).

`close` ends a case. Nothing else ever set `status: done`: SKILL.md
step 7 wrote review-queue/DONE_<id>.md and stopped, and case.yaml was
already locked at fan-in, so a lead that tried to edit the status was
denied by the lock hook. Every case stayed `in_progress` (11 of them by
JANUS-029). `close` does the whole sequence in one step: verify the
chain, unlock case.yaml, rewrite the top-level `status:` line, seal it
with the transition stored as the accepted reason, and lock it again.
`done` is refused on a chain that does not verify — a tampered case is
`needs_human`, not finished.

Usage:
  python3 chain.py seal <case-dir> [file ...]    # no files: all default targets
          [--accept-change "<reason>"]           # also re-seal files changed since their seal
  python3 chain.py verify <case-dir>             # exit 1 on tamper / broken link
  python3 chain.py lock <case-dir> [file ...]    # no files: the fact base
  python3 chain.py unlock <case-dir> [file ...]  # restore owner write
  python3 chain.py close <case-dir> [--status done|needs_human|failed]
                                                 # set case.yaml status (default done), seal, lock

Stdlib-only, like scripts/validate.py.
"""

import fcntl
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

CHAIN_NAME = "chain.jsonl"
# Written by hooks/evidence-chain.py when an auto-seal fails; not evidence.
HOOK_ERRORS = "chain-hook-errors.log"
GENESIS = "0" * 64
# The case evidence set. artifacts/ (vmcore binaries, never committed)
# is deliberately excluded.
DEFAULT_GLOBS = ("case.yaml", "verdict.md", "findings/*.md", "results/*.md", "audit/*")
# What `lock` freezes by default: the fact base synthesize reads.
# results/ and verdict.md stay out — they are still being written after
# the fan-in lock (send-back revisions, the human's verdict).
LOCK_GLOBS = ("case.yaml", "findings/*.md", "audit/*")
# Terminal statuses `close` may set (a subset of caselint.STATUSES).
CLOSE_STATUSES = ("done", "needs_human", "failed")
STATUS_LINE = re.compile(r"^status:[ \t]*(\S*)[ \t]*(#.*)?$", re.MULTILINE)


class ChainError(Exception):
    """The ledger itself is unreadable (malformed line) — needs a human."""


def _file_sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def _record_hash(rec):
    body = {k: v for k, v in rec.items() if k != "entry"}
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _parse(lines):
    records = []
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            raise ChainError(f"malformed ledger line {i + 1}")
    return records


def _default_targets(case_dir):
    targets = []
    for pattern in DEFAULT_GLOBS:
        targets.extend(p for p in case_dir.glob(pattern) if p.is_file())
    return targets


def _resolve_arg(case_dir, p):
    """A file argument as the user meant it. SKILL.md documents
    `chain.py unlock cases/<id> findings/x.md` — case-relative — but the
    path used to resolve against the CWD only, so from the repo root it
    named nothing and the command said "nothing to unlock" with exit 0.
    Absolute and CWD-relative paths that exist still win."""
    path = Path(p)
    if path.is_absolute() or path.exists():
        return path.resolve()
    return (Path(case_dir).resolve() / path).resolve()


def changed_since_seal(case_dir, paths=None):
    """Rel-paths of sealed files whose content no longer matches their
    newest record (what `verify` calls TAMPER). Retired paths and files
    never sealed are not included."""
    case_dir = Path(case_dir).resolve()
    chain_path = case_dir / CHAIN_NAME
    if not chain_path.is_file():
        return []
    records = _parse(chain_path.read_text(encoding="utf-8").splitlines())
    latest = {}
    for r in records:
        latest[r.get("file")] = None if r.get("retired") else r.get("sha256")
    targets = (
        [_resolve_arg(case_dir, p) for p in paths] if paths else _default_targets(case_dir)
    )
    changed = []
    for target in sorted(set(targets)):
        if not target.is_file():
            continue
        try:
            rel = str(target.relative_to(case_dir))
        except ValueError:
            continue
        if latest.get(rel) and latest[rel] != _file_sha(target):
            changed.append(rel)
    return changed


def seal(case_dir, paths=None, actor="lead", skip=(), reason=None):
    """Append records for new/changed files; returns the sealed rel-paths.

    `skip` names rel-paths to leave unsealed (the CLI's refused changes).
    `reason`, when given, is stored on records that re-seal a file that
    already had a record — the documented acceptance of a change."""
    case_dir = Path(case_dir).resolve()
    chain_path = case_dir / CHAIN_NAME
    targets = (
        [_resolve_arg(case_dir, p) for p in paths] if paths else _default_targets(case_dir)
    )
    sealed = []
    with open(chain_path, "a+", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.seek(0)
        records = _parse(f.readlines())
        latest = {r["file"]: r["sha256"] for r in records}
        prev = records[-1]["entry"] if records else GENESIS
        seq = len(records)
        for target in sorted(set(targets)):
            if not target.is_file():
                continue
            try:
                rel = str(target.relative_to(case_dir))
            except ValueError:
                continue  # outside the case dir — not ours to seal
            if rel == CHAIN_NAME or rel in skip:
                continue
            sha = _file_sha(target)
            if latest.get(rel) == sha:
                continue  # unchanged since last seal
            rec = {
                "seq": seq,
                "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "actor": actor,
                "file": rel,
                "sha256": sha,
                "prev": prev,
            }
            if reason and latest.get(rel):
                rec["accepted"] = reason
            rec["entry"] = _record_hash(rec)
            f.write(json.dumps(rec, sort_keys=True) + "\n")
            latest[rel] = sha
            prev = rec["entry"]
            seq += 1
            sealed.append(rel)
        f.flush()
    return sealed


def retire(case_dir, paths, actor="lead", reason=""):
    """Append a retirement record for a sealed file that is intentionally gone.

    A sealed file that no longer exists is a `verify` problem, and
    rightly so — evidence does not just vanish. But there is a
    legitimate case: a file sealed by accident, most often a scratch
    file a stage created inside `findings/` where the PostToolUse hook
    sealed it before anyone could object. Without a way to record the
    removal, that case leaves a permanent FAIL and the gate stops
    distinguishing real tampering from a known housekeeping artefact —
    which is how a check stops being read.

    Deleting the record would be the actual tamper. The ledger is
    append-only, so retirement is an *append*: a record saying this path
    was deliberately removed, by whom, and why. The history stays
    complete and `verify` stops reporting the absence as a problem.

    Retirement is not a way to drop inconvenient evidence. The record
    names a reason precisely so a reader can judge that for themselves.
    """
    case_dir = Path(case_dir).resolve()
    chain_path = case_dir / CHAIN_NAME
    retired = []
    with open(chain_path, "a+", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.seek(0)
        records = _parse(f.readlines())
        known = {r["file"] for r in records}
        prev = records[-1]["entry"] if records else GENESIS
        seq = len(records)
        for raw in paths:
            target = Path(raw)
            if target.is_absolute():
                try:
                    rel = str(target.resolve().relative_to(case_dir))
                except ValueError:
                    continue
            else:
                rel = str(target)
            if rel not in known:
                continue  # never sealed — nothing to retire
            if (case_dir / rel).is_file():
                continue  # still on disk — retire is for removed files only
            rec = {
                "seq": seq,
                "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "actor": actor,
                "file": rel,
                "sha256": None,
                "retired": True,
                "reason": reason or "intentionally removed",
                "prev": prev,
            }
            rec["entry"] = _record_hash(rec)
            f.write(json.dumps(rec, sort_keys=True) + "\n")
            prev = rec["entry"]
            seq += 1
            retired.append(rel)
        f.flush()
    return retired


def _case_files(case_dir, paths, globs):
    """Resolve paths (or globs) to (path, rel) pairs inside the case dir."""
    case_dir = Path(case_dir).resolve()
    if paths:
        targets = [_resolve_arg(case_dir, p) for p in paths]
    else:
        targets = []
        for pattern in globs:
            targets.extend(case_dir.glob(pattern))
    out = []
    for target in sorted(set(targets)):
        if not target.is_file():
            continue
        try:
            rel = str(target.relative_to(case_dir))
        except ValueError:
            continue  # outside the case dir — not ours
        if rel != CHAIN_NAME:
            out.append((target, rel))
    return out


def lock(case_dir, paths=None):
    """Drop all write bits on the fact base; returns newly locked rel-paths."""
    locked = []
    for target, rel in _case_files(case_dir, paths, LOCK_GLOBS):
        mode = target.stat().st_mode
        if mode & 0o222:
            os.chmod(target, mode & ~0o222)
            locked.append(rel)
    return locked


def unlock(case_dir, paths=None):
    """Restore owner write; returns newly unlocked rel-paths."""
    unlocked = []
    for target, rel in _case_files(case_dir, paths, LOCK_GLOBS):
        mode = target.stat().st_mode
        if not mode & 0o200:
            os.chmod(target, mode | 0o200)
            unlocked.append(rel)
    return unlocked


def close(case_dir, status="done", actor="lead"):
    """Set case.yaml's top-level status, seal it, and lock it.

    Returns (old_status, new_status). Raises ValueError for a status
    outside CLOSE_STATUSES, a case.yaml without exactly one top-level
    `status:` line, or `done` on a chain that does not verify."""
    if status not in CLOSE_STATUSES:
        raise ValueError(f"status must be one of {' | '.join(CLOSE_STATUSES)}")
    case_dir = Path(case_dir).resolve()
    case_yaml = case_dir / "case.yaml"
    if not case_yaml.is_file():
        raise ValueError(f"no case.yaml in {case_dir}")
    problems, _ = verify(case_dir)
    if problems and status == "done":
        raise ValueError(
            "chain does not verify — refusing `done`; close with "
            "--status needs_human and record the problem in audit/: "
            + "; ".join(problems)
        )
    text = case_yaml.read_text(encoding="utf-8")
    matches = list(STATUS_LINE.finditer(text))
    if len(matches) != 1:
        raise ValueError(
            f"case.yaml needs exactly one top-level `status:` line (found {len(matches)})"
        )
    m = matches[0]
    old = m.group(1)
    if old != status:
        comment = f" {m.group(2)}" if m.group(2) else ""
        new_text = text[:m.start()] + f"status: {status}{comment}" + text[m.end():]
        unlock(case_dir, ["case.yaml"])
        case_yaml.write_text(new_text, encoding="utf-8")
        seal(case_dir, ["case.yaml"], actor=actor,
             reason=f"status {old or '(empty)'} -> {status} (chain.py close)")
    lock(case_dir, ["case.yaml"])
    return old, status


def verify(case_dir):
    """Returns (problems, warnings). Any problem = tamper / broken ledger."""
    case_dir = Path(case_dir).resolve()
    chain_path = case_dir / CHAIN_NAME
    problems, warnings = [], []
    if not chain_path.is_file():
        for p in _default_targets(case_dir):
            warnings.append(f"unsealed (no ledger yet): {p.relative_to(case_dir)}")
        return problems, warnings
    try:
        records = _parse(chain_path.read_text(encoding="utf-8").splitlines())
    except ChainError as e:
        return [str(e)], warnings

    prev = GENESIS
    latest = {}
    for i, rec in enumerate(records):
        if rec.get("seq") != i:
            problems.append(f"entry {i}: sequence gap (has seq {rec.get('seq')})")
        if rec.get("prev") != prev:
            problems.append(f"entry {i}: broken link to previous entry")
        if rec.get("entry") != _record_hash(rec):
            problems.append(f"entry {i}: entry hash mismatch (record edited)")
        prev = rec.get("entry", "")
        # A retirement record supersedes the file's last seal: the path was
        # deliberately removed and its absence is recorded, not unexplained.
        latest[rec.get("file", "?")] = (
            None if rec.get("retired") else rec.get("sha256", "")
        )

    for rel in sorted(latest):
        if latest[rel] is None:
            continue  # retired — see the ledger record for who and why
        path = case_dir / rel
        if not path.is_file():
            problems.append(f"sealed file missing: {rel}")
        elif _file_sha(path) != latest[rel]:
            problems.append(f"TAMPER: {rel} changed after last seal")

    for p in _default_targets(case_dir):
        rel = str(p.relative_to(case_dir))
        if rel not in latest:
            warnings.append(f"unsealed: {rel}")
    hook_log = case_dir / HOOK_ERRORS
    if hook_log.is_file() and hook_log.stat().st_size:
        n = len(hook_log.read_text(encoding="utf-8", errors="replace").splitlines())
        warnings.append(
            f"{HOOK_ERRORS}: the auto-seal hook failed {n} time(s) — a TAMPER on "
            "one of those files may be a missed seal; read the log before judging"
        )
    return problems, warnings


def main(argv):
    if len(argv) < 3 or argv[1] not in (
        "seal", "verify", "lock", "unlock", "retire", "close"
    ):
        print(__doc__.strip().splitlines()[0])
        print(
            "usage: chain.py seal <case-dir> [file ...] [--accept-change '...'] "
            "| chain.py lock|unlock <case-dir> [file ...] "
            "| chain.py verify <case-dir> "
            "| chain.py retire <case-dir> <file> [--reason '...'] "
            "| chain.py close <case-dir> [--status done|needs_human|failed]"
        )
        return 2
    cmd, case_dir = argv[1], Path(argv[2])
    if not case_dir.is_dir():
        print(f"error: not a case directory: {case_dir}")
        return 2
    try:
        if cmd == "seal":
            args, reason = list(argv[3:]), None
            if "--accept-change" in args:
                i = args.index("--accept-change")
                reason = args[i + 1].strip() if i + 1 < len(args) else ""
                del args[i:i + 2]
                if not reason:
                    print("error: --accept-change needs a reason")
                    return 2
            changed = changed_since_seal(case_dir, args or None)
            refused = [] if reason else changed
            sealed = seal(case_dir, args or None, skip=set(refused), reason=reason)
            for rel in sealed:
                note = f"  (change accepted: {reason})" if rel in changed else ""
                print(f"sealed: {rel}{note}")
            for rel in refused:
                print(f"REFUSED: {rel} changed after its last seal (verify reports TAMPER)")
            if refused:
                print(
                    "Not re-sealed. A change outside tracked tools is a finding, "
                    "not housekeeping: record what changed and why in audit/, "
                    "tell the human, and only then re-run with "
                    "--accept-change \"<reason>\" (stored in the ledger)."
                )
                return 1
            if not sealed:
                print("chain up to date — nothing new to seal")
            return 0
        if cmd == "close":
            args, status = list(argv[3:]), "done"
            if "--status" in args:
                i = args.index("--status")
                status = args[i + 1] if i + 1 < len(args) else ""
                del args[i:i + 2]
            if args:
                print(f"error: unexpected argument(s): {' '.join(args)}")
                return 2
            try:
                old, new = close(case_dir, status)
            except ValueError as e:
                print(f"error: {e}")
                return 1
            if old == new:
                print(f"status already {new} — case.yaml locked")
            else:
                print(f"closed: status {old or '(empty)'} -> {new}; case.yaml sealed and locked")
            return 0
        if cmd == "retire":
            args, reason = list(argv[3:]), ""
            if "--reason" in args:
                i = args.index("--reason")
                reason = args[i + 1] if i + 1 < len(args) else ""
                del args[i:i + 2]
            if not args:
                print("error: retire needs at least one file")
                return 2
            gone = retire(case_dir, args, reason=reason)
            for rel in gone:
                print(f"retired: {rel}")
            if not gone:
                print("nothing to retire — paths are unsealed or still on disk")
            return 0
        if cmd in ("lock", "unlock"):
            named = argv[3:]
            missing = [p for p in named if not _case_files(case_dir, [p], LOCK_GLOBS)]
            if missing:
                for p in missing:
                    print(f"error: {p} -> {_resolve_arg(case_dir, p)} is not a file "
                          f"inside {case_dir}")
                print(f"nothing was {cmd}ed")
                return 2
            changed = (lock if cmd == "lock" else unlock)(case_dir, named or None)
            for rel in changed:
                print(f"{cmd}ed: {rel}")
            if not changed:
                print(f"nothing to {cmd}")
            return 0
        problems, warnings = verify(case_dir)
        for w in warnings:
            print(f"warning: {w}")
        for p in problems:
            print(f"FAIL: {p}")
        if problems:
            return 1
        print(f"OK: chain intact ({case_dir / CHAIN_NAME})")
        return 0
    except ChainError as e:
        print(f"FAIL: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
