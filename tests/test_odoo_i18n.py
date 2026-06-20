"""Behavioral invariant gate for the odoo-i18n cluster (#76).

Each test protects one contract clause that would break the skill's correctness
if removed.  Tests are read-only (file/JSON inspection only) - no odoo-bin or
polib execution needed.

Run: python -m pytest tests/test_odoo_i18n.py -v
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN = REPO_ROOT / "plugins" / "odoo-ai-agents"

RECIPE = PLUGIN / "skills" / "odoo-i18n" / "references" / "i18n-recipe.md"
SKILL_MD = PLUGIN / "skills" / "odoo-i18n" / "SKILL.md"
PLUGIN_JSON = PLUGIN / ".claude-plugin" / "plugin.json"
SKILL_TOOL_DEPS = PLUGIN / "generator" / "skill_tool_deps.json"
AGENT_FILE = PLUGIN / "agents" / "odoo-translator.md"


# ---------------------------------------------------------------------------
# Invariant 1 - Recipe is non-destructive: polib + .merge + --skip-auto-install
# + entry.msgstr count, + warns away from grep -c '^msgstr ""'
# ---------------------------------------------------------------------------

def test_recipe_non_destructive_polib_and_merge():
    """Recipe SSOT must document polib TM-merge as the non-destructive L2 step."""
    assert RECIPE.exists(), f"i18n-recipe.md not found at {RECIPE}"
    text = RECIPE.read_text(encoding="utf-8")

    # L2 headline marker - names the non-destructive core
    assert "polib" in text, "Recipe must mention `polib` as the TM-merge library"
    # The merge call itself
    assert ".merge(" in text, "Recipe must show `po.merge(pot)` TM-merge call"


def test_recipe_skip_auto_install():
    """Recipe must prescribe --skip-auto-install for Odoo >= 17 isolation."""
    assert RECIPE.exists()
    text = RECIPE.read_text(encoding="utf-8")
    assert "--skip-auto-install" in text, (
        "Recipe must require --skip-auto-install (Odoo >=17) to block auto_install "
        "siblings from polluting the .pot"
    )


def test_recipe_msgstr_count_via_polib_not_grep():
    """Recipe must document polib entry.msgstr count AND warn against grep -c '^msgstr'."""
    assert RECIPE.exists()
    text = RECIPE.read_text(encoding="utf-8")

    # The polib-based non-empty-msgstr count pattern
    assert "e.msgstr" in text, (
        "Recipe must show `e.msgstr` (polib entry attribute) as the correct way to "
        "count non-empty msgstr entries"
    )

    # Explicit prohibition of the grep shortcut
    assert "grep -c" in text and "msgstr" in text, (
        "Recipe must mention `grep -c` in the context of msgstr to warn it is wrong"
    )
    # The warning must say it is wrong / do NOT use
    grep_idx = text.find("grep -c")
    surrounding = text[max(0, grep_idx - 200): grep_idx + 300]
    negative_signals = ("Do NOT", "do NOT", "NOT measure", "not measure",
                        "miscounts", "false", "wrong", "PROHIBITION")
    assert any(sig in surrounding for sig in negative_signals), (
        "Recipe must warn that `grep -c '^msgstr'` is incorrect for multi-line entries; "
        f"no negative signal found near the grep mention: {surrounding!r}"
    )


def test_recipe_requires_load_language():
    """Recipe must require --load-language to activate translations before a .po export (KT1).

    Without loading the language into the DB, an existing-translation export emits empty
    msgstr (template only). The recipe must distinguish --load-language (activate in DB)
    from --language/-l (select export file).
    """
    assert RECIPE.exists()
    text = RECIPE.read_text(encoding="utf-8")
    assert "--load-language" in text, (
        "Recipe must require --load-language to load the language into the DB so an "
        "existing translation re-exports with msgstr (KT1)"
    )


def test_recipe_covers_v19_subcommand():
    """Recipe must cover the v19 `odoo-bin i18n` subcommand, not the v8-v18 server flag (KT2).

    v8-v18 use server flags; v19 moves i18n onto a dedicated subcommand. A recipe that only
    documents the server-flag form is wrong for v19.
    """
    assert RECIPE.exists()
    text = RECIPE.read_text(encoding="utf-8")
    assert ("i18n export" in text or "i18n loadlang" in text), (
        "Recipe must document the v19 `odoo-bin i18n` subcommand form "
        "(e.g. `i18n export` or `i18n loadlang`), not only the v8-v18 server flag"
    )
    assert "19" in text, (
        "Recipe must name the v19 series so the per-version CLI split is explicit (KT2)"
    )


# ---------------------------------------------------------------------------
# Invariant 2 - Orchestration entry in skill_tool_deps.json
# ---------------------------------------------------------------------------

def test_orchestration_entry_odoo_i18n():
    """skill_tool_deps.json must declare odoo-i18n as a spawner-agent with odoo-translator."""
    assert SKILL_TOOL_DEPS.exists(), f"skill_tool_deps.json not found at {SKILL_TOOL_DEPS}"
    deps = json.loads(SKILL_TOOL_DEPS.read_text(encoding="utf-8"))

    orch = deps.get("orchestration", {})
    assert "odoo-i18n" in orch, (
        "orchestration.odoo-i18n key is missing from skill_tool_deps.json"
    )
    entry = orch["odoo-i18n"]

    assert entry.get("spawn_class") == "spawner-agent", (
        f"orchestration.odoo-i18n.spawn_class must be 'spawner-agent', got {entry.get('spawn_class')!r}"
    )
    assert entry.get("instance_touching") is True, (
        "orchestration.odoo-i18n.instance_touching must be true (skill needs live DB)"
    )
    assert entry.get("default_gate_tier") == "L2", (
        f"orchestration.odoo-i18n.default_gate_tier must be 'L2', got {entry.get('default_gate_tier')!r}"
    )
    spawns = entry.get("spawns", [])
    assert "odoo-translator" in spawns, (
        f"orchestration.odoo-i18n.spawns must include 'odoo-translator', got {spawns!r}"
    )


# ---------------------------------------------------------------------------
# Invariant 3 - Agent declared in plugin.json AND file exists
# ---------------------------------------------------------------------------

def test_odoo_translator_declared_in_plugin_json():
    """plugin.json agents array must include odoo-translator."""
    assert PLUGIN_JSON.exists(), f"plugin.json not found at {PLUGIN_JSON}"
    data = json.loads(PLUGIN_JSON.read_text(encoding="utf-8"))

    agents: list[str] = data.get("agents", [])
    # entries are relative paths like './agents/odoo-translator.md'
    agent_basenames = [Path(a).name for a in agents]
    assert "odoo-translator.md" in agent_basenames, (
        f"odoo-translator.md is missing from plugin.json agents array. "
        f"Found: {agent_basenames}"
    )


def test_odoo_translator_file_exists():
    """agents/odoo-translator.md must exist on disk."""
    assert AGENT_FILE.exists(), (
        f"agents/odoo-translator.md not found at {AGENT_FILE}. "
        "The file must be present for the plugin to load the agent."
    )


# ---------------------------------------------------------------------------
# Invariant 4 - SKILL.md contract: name, required sections, instance-BLOCK
# ---------------------------------------------------------------------------

def _skill_frontmatter_and_body(text: str) -> tuple[str, str]:
    """Split SKILL.md into frontmatter (between --- delimiters) and body."""
    lines = text.splitlines()
    delims = [i for i, l in enumerate(lines) if l.strip() == "---"]
    if len(delims) >= 2:
        fm = "\n".join(lines[delims[0] + 1: delims[1]])
        body = "\n".join(lines[delims[1] + 1:])
    else:
        fm, body = "", text
    return fm, body


def test_skill_frontmatter_name_is_odoo_i18n():
    """SKILL.md frontmatter must declare name: odoo-i18n."""
    assert SKILL_MD.exists(), f"SKILL.md not found at {SKILL_MD}"
    fm, _ = _skill_frontmatter_and_body(SKILL_MD.read_text(encoding="utf-8"))
    # name line: 'name: odoo-i18n'
    name_lines = [l.strip() for l in fm.splitlines() if l.strip().startswith("name:")]
    assert name_lines, "SKILL.md frontmatter is missing a `name:` field"
    assert any("odoo-i18n" in l for l in name_lines), (
        f"SKILL.md frontmatter name must be 'odoo-i18n', got: {name_lines}"
    )


def test_skill_required_sections_present():
    """SKILL.md must contain the three required sections."""
    assert SKILL_MD.exists()
    text = SKILL_MD.read_text(encoding="utf-8")
    for section in ("## Persona", "## Out of Scope", "## Standalone-first fallback"):
        assert section in text, (
            f"SKILL.md is missing required section `{section}`"
        )


def test_skill_standalone_fallback_blocks_on_missing_instance():
    """Standalone-first fallback section must state instance is REQUIRED and missing = BLOCK."""
    assert SKILL_MD.exists()
    text = SKILL_MD.read_text(encoding="utf-8")

    # Locate the section body
    start = text.find("## Standalone-first fallback")
    assert start != -1, "## Standalone-first fallback section not found"
    # Everything after the section heading up to the next ## heading
    section_end = text.find("\n## ", start + 1)
    section = text[start: section_end if section_end != -1 else len(text)]

    assert "BLOCK" in section, (
        "Standalone-first fallback must say missing instance is a BLOCK "
        "(not a degraded path or warning)"
    )
    # Must not offer a no-DB workaround
    no_db_workaround_signals = ("no-DB workaround", "babel/polib alone", "NO no-DB")
    assert any(sig in section for sig in no_db_workaround_signals), (
        "Standalone-first fallback must explicitly state there is NO no-DB workaround; "
        "this rules out babel/polib-only paths that produce incomplete results"
    )
    assert "NEEDS_CONTEXT" in section, (
        "Standalone-first fallback must declare NEEDS_CONTEXT as the status when "
        "instance is missing (Continuation Contract compatibility)"
    )
