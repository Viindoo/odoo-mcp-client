"""Validate that every command ships well-formed YAML frontmatter.

Commands must have `name` + `description` keys in frontmatter, and their names
must be disjoint from skill names (no namespace collision).

Frontmatter is parsed line-by-line (stdlib only) so the suite has no third-party
dependency on PyYAML.
"""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGINS_DIR = ROOT / "plugins"
SKILLS_PLUGIN = PLUGINS_DIR / "odoo-ai-agents"
MCP_PLUGIN = PLUGINS_DIR / "odoo-semantic-mcp"

# After the v2 split, commands live in two plugins:
#   - 5 workflow commands under odoo-ai-agents/commands/
#   - the connect command under odoo-semantic-mcp/commands/
COMMAND_FILES = sorted(
    list((SKILLS_PLUGIN / "commands").glob("*.md"))
    + list((MCP_PLUGIN / "commands").glob("*.md"))
)
SKILL_FILES = sorted((SKILLS_PLUGIN / "skills").glob("*/SKILL.md"))


def _plugin_root_for(command_path):
    """Return the plugin root directory that contains the given command file."""
    # commands/<file>.md lives directly under <plugin_root>/commands/
    return command_path.parent.parent


def _frontmatter(text):
    """Return the dict of top-level keys in the leading --- ... --- block.

    Handles both inline scalars (``key: value``) and YAML block scalars
    (``key: >`` / ``key: |`` followed by indented lines).
    """
    lines = text.splitlines()
    assert lines and lines[0].strip() == "---", "file must start with '---' frontmatter"
    keys = {}
    i = 1
    while i < len(lines):
        line = lines[i]
        if line.strip() == "---":
            return keys
        # only capture top-level (unindented) "key: value" pairs
        if line and not line[0].isspace() and ":" in line:
            k, _, v = line.partition(":")
            v = v.strip()
            if v in (">", "|", ">-", "|-", ">+", "|+", ""):
                # block scalar (or empty): gather following indented lines
                body = []
                j = i + 1
                while j < len(lines) and lines[j].strip() != "---" and (
                    lines[j].strip() == "" or lines[j][:1].isspace()
                ):
                    body.append(lines[j].strip())
                    j += 1
                v = " ".join(b for b in body if b).strip()
                i = j
                keys[k.strip()] = v
                continue
            keys[k.strip()] = v
        i += 1
    raise AssertionError("frontmatter not closed with '---'")


def _skill_names():
    """Return the set of all skill directory names (which must match their frontmatter 'name')."""
    names = set()
    for skill_file in SKILL_FILES:
        text = skill_file.read_text(encoding="utf-8")
        fm = _frontmatter(text)
        if fm.get("name"):
            names.add(fm["name"])
    return names


def _command_names():
    """Return the dict of command file -> frontmatter name."""
    names = {}
    for cmd_file in COMMAND_FILES:
        text = cmd_file.read_text(encoding="utf-8")
        fm = _frontmatter(text)
        if fm.get("name"):
            names[cmd_file] = fm["name"]
    return names


def _plugin_json_commands(plugin_root):
    """Return the list of command paths listed in the given plugin's plugin.json."""
    plugin_file = plugin_root / ".claude-plugin" / "plugin.json"
    if not plugin_file.exists():
        return []
    with open(plugin_file, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("commands", [])


def test_at_least_6_commands():
    # Floor at the real count (6 workflow commands today) so a dropped command
    # trips CI, while adding commands never breaks it.
    assert len(COMMAND_FILES) >= 6, f"expected >=6 commands, found {len(COMMAND_FILES)}"


@pytest.mark.parametrize("cmd", COMMAND_FILES, ids=lambda p: p.stem)
def test_command_frontmatter(cmd):
    text = cmd.read_text(encoding="utf-8")
    fm = _frontmatter(text)
    assert fm.get("name"), f"{cmd.stem}: missing 'name' in frontmatter"
    assert fm.get("description"), f"{cmd.stem}: missing 'description' in frontmatter"


@pytest.mark.parametrize("cmd", COMMAND_FILES, ids=lambda p: p.stem)
def test_command_description_no_trailing_punctuation(cmd):
    """Command descriptions must not end in . ! ? — Anthropic plugin marketplace style."""
    fm = _frontmatter(cmd.read_text(encoding="utf-8"))
    desc = fm.get("description", "").rstrip()
    assert desc and desc[-1] not in ".!?", (
        f"{cmd.stem}: description must not end with '.', '!', or '?' "
        f"(found: ...{desc[-40:]!r})"
    )


def test_command_name_disjoint_from_skill_name():
    """Assert no command name collides with any skill name."""
    skill_names = _skill_names()
    command_names = _command_names()
    collisions = set()
    for cmd_file, cmd_name in command_names.items():
        if cmd_name in skill_names:
            collisions.add(f"{cmd_file.stem} (command) == {cmd_name} (skill)")
    assert not collisions, f"command/skill name collision(s): {collisions}"


@pytest.mark.parametrize("cmd", COMMAND_FILES, ids=lambda p: p.stem)
def test_command_in_plugin_manifest(cmd):
    """Each command must be declared in the plugin.json of the plugin that contains it.

    After the v2 split, the 5 workflow commands belong to the skills manifest
    and connect.md belongs to the mcp manifest — a command declared in the wrong
    manifest (or in neither) is a packaging bug.
    """
    plugin_root = _plugin_root_for(cmd)
    declared_stems = {Path(p).stem for p in _plugin_json_commands(plugin_root)}
    assert cmd.stem in declared_stems, (
        f"command '{cmd.stem}' not listed in {plugin_root.name}'s plugin.json. "
        f"Add './commands/{cmd.name}' to its '.claude-plugin/plugin.json' 'commands' array."
    )
