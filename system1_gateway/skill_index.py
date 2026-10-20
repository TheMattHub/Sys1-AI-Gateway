"""Skills Claude could load in this session, as (name, description) pairs, for the System-1 skill picker.

Taken from the hook input when Claude Code sends a list (availableSkills; undocumented, so used only if present),
otherwise from SKILL.md frontmatter on disk: ~/.claude/skills, <cwd>/.claude/skills, and the skills/ folder of
every enabled plugin. Skills marked disable-model-invocation are left out: Claude can't load them itself.
"""

import json
import os
from pathlib import Path

BLOCK = (">", "|", ">-", "|-")


def frontmatter(path: Path) -> dict:
    """Top-level `key: value` pairs of a SKILL.md header; {} if unreadable or unterminated.
    ponytail: a line reader, not YAML. Folded (>) and literal (|) blocks are joined with spaces."""
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()  # -sig: editors on Windows may add a BOM
    except (OSError, UnicodeDecodeError):
        return {}
    if not lines or lines[0].strip() != "---":
        return {}
    out, key = {}, None
    for line in lines[1:]:
        if line[:1] in (" ", "\t"):
            # continuation of a block value or a wrapped description; nested maps (metadata:) are ignored.
            # Checked before the fence, so an indented "---" stays inside the value.
            if key == "description" or (key and out.get(key) == ""):
                out[key] = f"{out[key]} {line.strip()}".strip()
            continue
        if line.strip() == "---":
            return out
        name, sep, value = line.partition(":")
        key = name.strip() if sep else None
        if key:
            value = value.strip()
            out[key] = "" if value in BLOCK else value.strip("\"'")
    return {}


def _scan(root: Path, prefix: str = "") -> list:
    found = []
    for skill_md in sorted(root.glob("*/SKILL.md")):
        fm = frontmatter(skill_md)
        if str(fm.get("disable-model-invocation", "")).lower() == "true":
            continue
        found.append((prefix + (fm.get("name") or skill_md.parent.name), fm.get("description", "")))
    return found


def _enabled_plugins(claude_dir: Path) -> list:
    """(plugin name, install path) for every plugin enabled in settings.json."""
    try:
        installed = json.loads((claude_dir / "plugins" / "installed_plugins.json").read_text(encoding="utf-8"))["plugins"]
        enabled = json.loads((claude_dir / "settings.json").read_text(encoding="utf-8")).get("enabledPlugins") or {}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return []
    out = []
    for key, installs in installed.items():
        if enabled.get(key) is not True or not isinstance(installs, list):
            continue
        # ponytail: the user-scope install wins; project-scoped installs of the same plugin are ignored
        entry = next((i for i in installs if isinstance(i, dict) and i.get("scope") == "user"), None)
        if entry and entry.get("installPath"):
            out.append((key.split("@", 1)[0], Path(entry["installPath"])))
    return out


def available_skills(payload, cwd, claude_dir: Path | None = None) -> list:
    listed = payload.get("availableSkills") if isinstance(payload, dict) else None
    if isinstance(listed, list):
        from_hook = [(s["name"], str(s.get("description") or "")) for s in listed
                     if isinstance(s, dict) and isinstance(s.get("name"), str) and s["name"].strip()]
        if from_hook:
            return from_hook
    claude_dir = claude_dir or Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    skills = _scan(claude_dir / "skills")
    if isinstance(cwd, str) and cwd:
        skills += _scan(Path(cwd) / ".claude" / "skills")
    for plugin, root in _enabled_plugins(claude_dir):
        skills += _scan(root / "skills", f"{plugin}:")
    seen = {}  # first description per name wins, order kept
    for name, description in skills:
        seen.setdefault(name, description)
    return list(seen.items())
