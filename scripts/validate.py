#!/usr/bin/env python3
"""Validate the janus marketplace, plugin manifests, skills, agents, and hooks.

Deterministic consistency checks that previously lived only in the
team-developer agent's judgment (pattern adopted from
aws/agent-toolkit-for-aws tools/validate.py). Stdlib-only, CI-friendly.
Exit 0 on success, 1 on failure.

Usage:
    python3 scripts/validate.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
KEBAB_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")

errors: list[str] = []


def error(msg: str) -> None:
    errors.append(msg)
    print(f"  ERROR: {msg}", file=sys.stderr)


def rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


def load_json(path: Path, required_keys: list[str]) -> dict | None:
    if not path.exists():
        error(f"Missing file: {rel(path)}")
        return None
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        error(f"Invalid JSON in {rel(path)}: {e}")
        return None
    for key in required_keys:
        if key not in data:
            error(f"Missing key '{key}' in {rel(path)}")
    return data


def parse_frontmatter(md: Path) -> dict | None:
    """Parse simple key: value YAML frontmatter without a yaml dependency."""
    text = md.read_text()
    if not text.startswith("---\n"):
        error(f"Missing YAML frontmatter in {rel(md)}")
        return None
    end = text.find("\n---\n", 4)
    if end == -1:
        error(f"Unterminated frontmatter in {rel(md)}")
        return None
    fm: dict[str, str] = {}
    current_key = None
    for line in text[4:end].splitlines():
        if ":" in line and not line.startswith((" ", "\t", "#")):
            key, _, value = line.partition(":")
            value = value.strip().strip('"').strip("'")
            if value in (">", "|", ">-", "|-"):
                value = ""
            current_key = key.strip()
            fm[current_key] = value
        elif current_key and line.startswith("  "):
            fm[current_key] = (fm[current_key] + " " + line.strip()).strip()
    return fm


def validate_named_md(md: Path, kind: str) -> None:
    """Shared checks for SKILL.md (name==dir) and agents/*.md (name==stem)."""
    fm = parse_frontmatter(md)
    if fm is None:
        return
    name = fm.get("name", "")
    desc = fm.get("description", "")
    expected = md.parent.name if kind == "skill" else md.stem
    if not name:
        error(f"Missing 'name' in frontmatter: {rel(md)}")
    elif not KEBAB_RE.match(name):
        error(f"Name '{name}' is not kebab-case in {rel(md)}")
    elif name != expected:
        error(f"Name '{name}' does not match '{expected}' in {rel(md)}")
    if not desc:
        error(f"Missing 'description' in frontmatter: {rel(md)}")
    elif len(desc) < 20:
        error(f"Description too short (<20 chars) in {rel(md)}")
    if kind == "agent" and not fm.get("tools"):
        error(f"Missing 'tools' in frontmatter: {rel(md)}")


def validate_hooks(plugin_dir: Path) -> None:
    hooks_json = plugin_dir / "hooks" / "hooks.json"
    if not hooks_json.exists():
        return
    data = load_json(hooks_json, ["hooks"])
    if data is None:
        return
    for event, matchers in data.get("hooks", {}).items():
        for matcher in matchers:
            for hook in matcher.get("hooks", []):
                cmd = hook.get("command", "")
                for m in re.finditer(r"\$\{CLAUDE_PLUGIN_ROOT\}/(\S+?)(?=[\s\"])", cmd):
                    script = plugin_dir / m.group(1)
                    if not script.exists():
                        error(f"Hook script missing: {rel(hooks_json)} → {m.group(1)}")


def validate_pipeline_stage_sync(plugin_dir: Path) -> None:
    """Every stage named in the SKILL.md pipeline-stages table must have an
    agent definition, and vice versa for pipeline-stage agents."""
    skill_md = plugin_dir / "skills" / "janus" / "SKILL.md"
    if not skill_md.exists():
        error(f"Missing pipeline skill: {rel(skill_md)}")
        return
    text = skill_md.read_text()
    stages = set(re.findall(r"^\| \*\*([a-z-]+)\*\* \|", text, re.M))
    if not stages:
        error(f"No pipeline stages parsed from {rel(skill_md)}")
        return
    agent_names = {p.stem for p in (plugin_dir / "agents").glob("*.md")}
    for stage in sorted(stages):
        if stage not in agent_names:
            error(f"Stage '{stage}' in SKILL.md has no agents/{stage}.md")
    for agent in sorted(agent_names - stages):
        if agent not in text:
            error(f"agents/{agent}.md is never mentioned in SKILL.md")


def main() -> int:
    print(f"Validating marketplace: .claude-plugin/marketplace.json")
    marketplace = load_json(
        REPO_ROOT / ".claude-plugin" / "marketplace.json", ["name", "plugins"]
    )
    plugin_dirs: list[Path] = []
    if marketplace:
        for entry in marketplace.get("plugins", []):
            source = entry.get("source", "")
            plugin_dir = (REPO_ROOT / source).resolve()
            if not plugin_dir.is_dir():
                error(f"Marketplace plugin source does not exist: {source}")
                continue
            plugin_dirs.append(plugin_dir)

    for plugin_dir in plugin_dirs:
        print(f"Validating plugin: {rel(plugin_dir)}")
        load_json(
            plugin_dir / ".claude-plugin" / "plugin.json",
            ["name", "description", "version"],
        )
        if (plugin_dir / ".mcp.json").exists():
            load_json(plugin_dir / ".mcp.json", ["mcpServers"])

        for skill_md in sorted(plugin_dir.glob("skills/*/SKILL.md")):
            validate_named_md(skill_md, "skill")
        for agent_md in sorted(plugin_dir.glob("agents/*.md")):
            validate_named_md(agent_md, "agent")

        validate_hooks(plugin_dir)
        validate_pipeline_stage_sync(plugin_dir)

    claude_md = REPO_ROOT / ".claude" / "CLAUDE.md"
    if claude_md.exists():
        for m in re.finditer(r"^@(\S+)", claude_md.read_text(), re.M):
            if not (REPO_ROOT / m.group(1)).exists():
                error(f".claude/CLAUDE.md references missing file: {m.group(1)}")

    if errors:
        print(f"\nFAILED: {len(errors)} error(s)", file=sys.stderr)
        return 1
    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
