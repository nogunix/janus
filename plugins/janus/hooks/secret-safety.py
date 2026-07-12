#!/usr/bin/env python3
"""PreToolUse hook: deterministic enforcement of two JANUS invariants.

Prompt-level rules can be skimmed or forgotten; this hook makes two of
them mechanical (pattern adopted from aws/agent-toolkit-for-aws):

1. Secret material must never enter the context window. Findings and
   reports are committed to git and handed to humans — a dumped
   kubeconfig token or Secret payload would persist there. Bulk secret
   dumps (`oc/kubectl get secret -o yaml|json`, `oc extract secret`,
   `aws secretsmanager get-secret-value`) are denied; reading a single
   named non-credential key via `-o jsonpath` stays possible.

2. JANUS never mutates an AWS support case (doc-search is granted only
   read-only describe_* MCP tools; this closes the AWS-CLI side path).

Reads the PreToolUse JSON from stdin; exits 0 with a deny decision on
stdout to block, exits 0 silently to allow.
"""

import json
import re
import sys

# oc/kubectl full-object secret dumps. `json\b` does not match "jsonpath",
# so scoped single-key reads are allowed through.
KUBE_SECRET_DUMP = re.compile(
    r"\b(oc|kubectl)\b[^|;&]*\bget\b[^|;&]*\bsecrets?\b[^|;&]*"
    r"(-o|--output)[= ]*(yaml|json)\b",
    re.I,
)
KUBE_SECRET_EXTRACT = re.compile(
    r"\b(oc|kubectl)\b[^|;&]*\bextract\b[^|;&]*\bsecrets?[/ ]", re.I
)
ASM_GET = re.compile(
    r"\baws\b[^|;&]*\bsecretsmanager\b[^|;&]*"
    r"\b(batch-)?get-secret-value\b",
    re.I,
)
AWS_SUPPORT_WRITE = re.compile(
    r"\baws\b[^|;&]*\bsupport\b[^|;&]*"
    r"\b(create-case|resolve-case|add-communication-to-case|"
    r"add-attachments-to-set)\b",
    re.I,
)

RULES = [
    (
        KUBE_SECRET_DUMP,
        "Blocked: full Secret dumps put credential material into the "
        "context window (findings/reports are committed to git). Read "
        "the specific non-credential key you need with "
        "-o jsonpath='{.data.<key>}', or leave secret inspection to "
        "the human.",
    ),
    (
        KUBE_SECRET_EXTRACT,
        "Blocked: `oc extract secret` writes credential material to "
        "disk and into the context window. Read the specific "
        "non-credential key you need with -o jsonpath='{.data.<key>}', "
        "or leave secret inspection to the human.",
    ),
    (
        ASM_GET,
        "Blocked: fetching Secrets Manager values puts credentials "
        "into the context window. JANUS stages never need secret "
        "values — leave secret inspection to the human.",
    ),
    (
        AWS_SUPPORT_WRITE,
        "Blocked: JANUS never creates, replies to, or resolves an AWS "
        "support case — only the read-only describe_* operations are "
        "allowed.",
    ),
]


def deny(reason):
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        },
        sys.stdout,
    )
    sys.exit(0)


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    if data.get("tool_name") != "Bash":
        sys.exit(0)

    command = data.get("tool_input", {}).get("command", "")
    for pattern, reason in RULES:
        if pattern.search(command):
            deny(reason)

    sys.exit(0)


if __name__ == "__main__":
    main()
