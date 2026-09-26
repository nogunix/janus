#!/usr/bin/env python3
"""Print the CHANGELOG.md section for a plugin version, as release notes.

Usage: release_notes.py [VERSION]

VERSION defaults to the version in plugins/janus/.claude-plugin/plugin.json.
The section body (heading excluded) goes to stdout; exits 1 when CHANGELOG.md
has no `## <VERSION> — ...` heading. Used by .github/workflows/release.yml and
by validate.py's changelog check.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_JSON = REPO_ROOT / "plugins" / "janus" / ".claude-plugin" / "plugin.json"
CHANGELOG = REPO_ROOT / "CHANGELOG.md"


def plugin_version() -> str:
    return json.loads(PLUGIN_JSON.read_text())["version"]


def changelog_section(version: str, text: str | None = None) -> str | None:
    """Return the body under `## <version>`, or None if there is no such heading."""
    if text is None:
        text = CHANGELOG.read_text()
    m = re.search(
        rf"^## {re.escape(version)}(?:[ \t][^\n]*)?\n(.*?)(?=^## |\Z)", text, re.M | re.S
    )
    return m.group(1).strip() if m else None


def main() -> int:
    version = sys.argv[1] if len(sys.argv) > 1 else plugin_version()
    body = changelog_section(version)
    if body is None:
        print(f"CHANGELOG.md has no section for {version}", file=sys.stderr)
        return 1
    print(body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
