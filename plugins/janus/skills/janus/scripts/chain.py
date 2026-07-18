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

Usage:
  python3 chain.py seal <case-dir> [file ...]  # no files: all default targets
  python3 chain.py verify <case-dir>           # exit 1 on tamper / broken link

Stdlib-only, like scripts/validate.py.
"""

import fcntl
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

CHAIN_NAME = "chain.jsonl"
GENESIS = "0" * 64
# The case evidence set. artifacts/ (vmcore binaries, never committed)
# is deliberately excluded.
DEFAULT_GLOBS = ("case.yaml", "verdict.md", "findings/*.md", "results/*.md", "audit/*")


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


def seal(case_dir, paths=None, actor="lead"):
    """Append records for new/changed files; returns the sealed rel-paths."""
    case_dir = Path(case_dir).resolve()
    chain_path = case_dir / CHAIN_NAME
    targets = (
        [Path(p).resolve() for p in paths] if paths else _default_targets(case_dir)
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
            if rel == CHAIN_NAME:
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
            rec["entry"] = _record_hash(rec)
            f.write(json.dumps(rec, sort_keys=True) + "\n")
            latest[rel] = sha
            prev = rec["entry"]
            seq += 1
            sealed.append(rel)
        f.flush()
    return sealed


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
        latest[rec.get("file", "?")] = rec.get("sha256", "")

    for rel in sorted(latest):
        path = case_dir / rel
        if not path.is_file():
            problems.append(f"sealed file missing: {rel}")
        elif _file_sha(path) != latest[rel]:
            problems.append(f"TAMPER: {rel} changed after last seal")

    for p in _default_targets(case_dir):
        rel = str(p.relative_to(case_dir))
        if rel not in latest:
            warnings.append(f"unsealed: {rel}")
    return problems, warnings


def main(argv):
    if len(argv) < 3 or argv[1] not in ("seal", "verify"):
        print(__doc__.strip().splitlines()[0])
        print("usage: chain.py seal <case-dir> [file ...] | chain.py verify <case-dir>")
        return 2
    cmd, case_dir = argv[1], Path(argv[2])
    if not case_dir.is_dir():
        print(f"error: not a case directory: {case_dir}")
        return 2
    try:
        if cmd == "seal":
            sealed = seal(case_dir, argv[3:] or None)
            for rel in sealed:
                print(f"sealed: {rel}")
            if not sealed:
                print("chain up to date — nothing new to seal")
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
