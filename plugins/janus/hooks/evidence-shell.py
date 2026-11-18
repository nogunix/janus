#!/usr/bin/env python3
"""PreToolUse hook: deny shell writes to sealed case evidence.

The evidence chain seals Write/Edit automatically (evidence-chain.py)
and the other write hooks (evidence-lock, evidence-drift,
findings-truncation) all key on the same tracked tools. A shell write
-- `>`/`>>`, `tee`, `sed -i`, `cp`/`mv`/`rm`, a python one-off that
calls write_text -- goes around every one of them. The prompts say
"never Bash for findings/results", and that rule was still broken
twice: a synthesize stage fixed anchors in a sealed report with a
python script, and a lead appended to a sealed audit note with
`cat >>`. Both surfaced only later as `verify` TAMPER and stopped the
case. This hook makes the rule mechanical at the moment of the write.

Scope is deliberately narrow: only files that already have a seal in
the case's chain.jsonl. Creating a new audit log with a redirect
(`... 2>&1 | tee audit/12-x.log`) is the normal way command output
lands in audit/ and stays allowed; the lead's `chain.py seal` picks
it up at fan-in. Appending to that log before it is sealed is also
fine.

Detection is lexical (the command text), so it is a backstop, not a
proof: a script file that writes a sealed path it builds at runtime is
not seen. `chain.py verify` still catches that afterwards.

Fail-open by design (same rationale as evidence-chain.py): any error
exits 0 silently.
"""

import json
import os
import re
import shlex
import sys
from pathlib import Path

BASH_TOOLS = {"Bash", "run_command"}

TRACKED = re.compile(
    r"^(?P<case>.*/cases/[^/]+)/"
    r"(?P<rel>case\.yaml|verdict\.md|(?:findings|results)/[^/]+\.md|audit/[^/]+)$"
)
# Path-looking tokens that could name a tracked evidence file, absolute
# or relative (a stage often runs from the repo root or the case dir).
CANDIDATE = re.compile(
    r"""(?P<path>(?:[^\s'"`;|&<>()=]*/)?"""
    r"""(?:case\.yaml|verdict\.md|(?:findings|results)/[^\s'"`;|&<>()/]+\.md|audit/[^\s'"`;|&<>()/]+))"""
)
SEGMENT_SPLIT = re.compile(r"\|\||&&|[;|&\n]")
PREFIX_CMDS = {"sudo", "env", "command", "nohup", "time", "xargs"}
REMOVE_CMDS = {"rm", "unlink", "truncate", "shred"}
DEST_CMDS = {"cp", "install", "rsync", "ln"}
INTERPRETER = re.compile(r"\b(python3?|perl|ruby|node)\b")
INTERP_WRITE = re.compile(
    r"write_text|write_bytes|\.write\(|open\([^)]*['\"](?:w|a|r\+|wb|ab|x)['\"]|"
    r"os\.remove|os\.unlink|\.unlink\(|os\.rename|\.rename\(|shutil\.(?:move|copy)"
)


def parse_event(data):
    """Extract (is_antigravity, tool_name, tool_input) from a hook payload."""
    if "toolCall" in data:
        tc = data.get("toolCall") or {}
        return True, tc.get("name", ""), tc.get("args") or {}
    return False, data.get("tool_name", ""), data.get("tool_input") or {}


def deny_payload(reason, is_antigravity=False):
    if is_antigravity:
        return {"decision": "deny", "reason": reason}
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def _sealed(case_dir, rel):
    """True when rel has a live (non-retired) seal in the case ledger."""
    chain = Path(case_dir) / "chain.jsonl"
    if not chain.is_file():
        return False
    state = None
    for line in chain.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("file") == rel:
            state = not rec.get("retired")
    return bool(state)


def _resolve(token, cwd):
    p = Path(os.path.expanduser(token))
    if not p.is_absolute():
        p = Path(cwd) / p
    return Path(os.path.normpath(str(p)))


def _words(segment):
    try:
        words = shlex.split(segment, posix=True)
    except ValueError:
        words = segment.split()
    while words and (words[0] in PREFIX_CMDS or re.match(r"^\w+=", words[0])):
        words = words[1:]
    return words


def _is_write(command, token, start):
    """Does the command write the file named by `token` (found at `start`)?"""
    before = command[:start].rstrip(" \t'\"")
    if before.endswith(">") or before.endswith(">|"):
        return "redirect"
    if re.search(r"\bof=$", before):
        return "dd"
    seg_start = max((m.end() for m in SEGMENT_SPLIT.finditer(command, 0, start)), default=0)
    seg_end_m = SEGMENT_SPLIT.search(command, start)
    segment = command[seg_start:seg_end_m.start() if seg_end_m else len(command)]
    words = _words(segment)
    if not words:
        return None
    cmd = os.path.basename(words[0])
    args = [w for w in words[1:]]
    named = [w for w in args if w.strip("'\"") == token or w.endswith(token)]
    if not named:
        return None
    if cmd in REMOVE_CMDS:
        return cmd
    if cmd == "mv":
        return "mv"
    if cmd in DEST_CMDS and args and (args[-1] == token or args[-1].endswith(token)):
        return cmd
    if cmd == "tee":
        return "tee"
    if cmd in ("sed", "perl", "gsed") and any(
        a == "-i" or a.startswith("-i") or a.startswith("--in-place") or a == "-pi"
        for a in args
    ):
        return f"{cmd} -i"
    if cmd == "git" and args and args[0] in ("checkout", "restore", "rm", "mv"):
        return f"git {args[0]}"
    return None


def shell_write_reason(tool_name, command, cwd):
    """The deny reason if `command` writes a sealed evidence file, else None."""
    if tool_name not in BASH_TOOLS or not command:
        return None
    interp_write = bool(INTERPRETER.search(command) and INTERP_WRITE.search(command))
    for m in CANDIDATE.finditer(command):
        token = m.group("path")
        path = _resolve(token, cwd)
        tm = TRACKED.match(str(path))
        if not tm or not path.is_file():
            continue
        if not _sealed(tm.group("case"), tm.group("rel")):
            continue
        how = _is_write(command, token, m.start("path"))
        if not how and interp_write:
            how = "a script that writes files"
        if not how:
            continue
        rel = tm.group("rel")
        if how in REMOVE_CMDS or how in ("mv", "git rm", "git mv"):
            fix = (
                "If the file really must go, the lead records why in audit/ and "
                "runs `chain.py retire <case> " + rel + " --reason '...'` after "
                "removing it."
            )
        elif rel.startswith("audit/"):
            fix = (
                "Write the new output to a new audit file (e.g. the next "
                "NN-<name>.log) instead of changing the sealed one, or append "
                "with Edit if it is a hand-written note."
            )
        else:
            fix = "Make the change with Edit (or Write), which the chain seals."
        return (
            f"Blocked: {rel} is sealed in this case's chain.jsonl and this command "
            f"would change it via {how}. Shell writes bypass the evidence chain, so "
            "the change would surface later as `chain.py verify` TAMPER and stop "
            f"the case at NEEDS_HUMAN. {fix}"
        )
    return None


def main():
    try:
        data = json.load(sys.stdin)
        is_agy, tool_name, tool_input = parse_event(data)
        command = (
            tool_input.get("command")
            or tool_input.get("CommandLine")
            or tool_input.get("commandLine")
            or ""
        )
        cwd = (
            tool_input.get("Cwd")
            or tool_input.get("cwd")
            or data.get("cwd")
            or os.getcwd()
        )
        reason = shell_write_reason(tool_name, command, cwd)
        if reason:
            json.dump(deny_payload(reason, is_antigravity=is_agy), sys.stdout)
    except Exception:
        pass
    finally:
        sys.exit(0)


if __name__ == "__main__":
    main()
