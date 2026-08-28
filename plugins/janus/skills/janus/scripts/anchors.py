#!/usr/bin/env python3
"""List all heading anchors in findings files for synthesize to use.

synthesize must link to specific findings using GitHub-style slugs, but
computing slugs by hand is error-prone — especially with Japanese text,
version strings (4.18→4.19 → 418419), and special characters.  This
script derives every anchor deterministically, so synthesize can copy
them rather than guess.

Usage:
    python3 anchors.py cases/<id>/findings/
    python3 anchors.py cases/<id>/findings/doc-search.md

Output (one per heading, tab-separated):
    findings/doc-search.md	#f1-管理者-ack-が必須-kubernetes-132-api-削除への対応	F1: 管理者 ACK が必須 — Kubernetes 1.32 API 削除への対応

Stdlib-only, offline.
"""

import re
import sys
from pathlib import Path

HEADING_RE = re.compile(r"^(#{1,6})\s+(?P<title>.+?)\s*#*\s*$")


def slug(title):
    """GitHub's heading-anchor algorithm (same as linkcheck.py)."""
    s = title.strip().lower()
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE)
    s = re.sub(r"\s+", "-", s)
    return s.strip("-")


def extract(path):
    """Yield (slug, title) for every heading in a markdown file."""
    text = path.read_text(encoding="utf-8", errors="replace")
    seen = {}
    for line in text.splitlines():
        m = HEADING_RE.match(line)
        if not m:
            continue
        title = m.group("title")
        base = slug(title)
        if not base:
            continue
        n = seen.get(base, 0)
        seen[base] = n + 1
        anchor = base if n == 0 else f"{base}-{n}"
        yield anchor, title


def main(argv):
    if len(argv) != 2:
        print("usage: anchors.py cases/<id>/findings/ | <file>.md")
        return 2

    target = Path(argv[1])
    if target.is_dir():
        files = sorted(target.glob("*.md"))
    elif target.is_file():
        files = [target]
    else:
        print(f"error: {target} is not a file or directory")
        return 2

    for f in files:
        rel = f.name
        if f.parent.name:
            rel = f"{f.parent.name}/{f.name}"
        for anchor, title in extract(f):
            print(f"{rel}\t#{anchor}\t{title}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
