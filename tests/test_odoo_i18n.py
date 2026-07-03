"""Behavioral invariant gate for the odoo-i18n cluster (#76).

Each test protects one contract clause that would break the skill's correctness
if removed.  Tests are read-only (file/JSON inspection only) - no odoo-bin or
PO-library execution needed.

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
# Invariant 1 - Recipe is non-destructive via load + re-export + git-ops
# diff-review (NO polib); diff-review adjudication is the L2 core.
# ---------------------------------------------------------------------------

def test_recipe_non_destructive_diff_review_no_polib():
    """Recipe SSOT must use load + re-export + diff-review as the non-destructive core, NOT polib."""
    assert RECIPE.exists(), f"i18n-recipe.md not found at {RECIPE}"
    text = RECIPE.read_text(encoding="utf-8")

    # No polib USAGE (the merge/parse calls whose behavior is polib-version-dependent). The word
    # "polib" may still appear in prose that says it is NOT used ("no polib") - only the code
    # patterns are forbidden.
    for pat in ("import polib", "polib.pofile", "po.merge(", ".merge(pot"):
        assert pat not in text, (
            f"Recipe must NOT use polib ({pat!r}) - the non-destructive core is now "
            "load + re-export + git-ops diff-review"
        )
    assert "diff-review" in text.lower(), (
        "Recipe L2 must name the diff-review reconcile as the non-destructive core"
    )
    assert "git-ops" in text and "adjudicat" in text.lower(), (
        "Recipe must delegate the diff to git-ops and require adjudicating every removed/changed entry"
    )


def test_recipe_skip_auto_install():
    """Recipe must prescribe --skip-auto-install for Odoo >= 17 isolation."""
    assert RECIPE.exists()
    text = RECIPE.read_text(encoding="utf-8")
    assert "--skip-auto-install" in text, (
        "Recipe must require --skip-auto-install (Odoo >=17) to block auto_install "
        "siblings from polluting the .pot"
    )


def test_recipe_diff_review_loads_before_reexport():
    """Recipe must load the existing .po into a fresh instance BEFORE re-export, then diff-review."""
    assert RECIPE.exists()
    text = RECIPE.read_text(encoding="utf-8")

    # git-ops owns the diff (the skill/agent never runs git itself)
    assert "git-ops" in text, "Recipe must delegate the diff to git-toolkit:git-ops"

    # The load-into-fresh-instance-before-re-export mechanism is what preserves translations
    low = text.lower()
    assert "re-export" in low and "load" in low and ("fresh instance" in low or "fresh db" in low), (
        "Recipe must state the existing .po is loaded into a FRESH instance before the re-export, "
        "so the re-export reproduces the human translation (the non-destructive mechanism)"
    )
    # Adjudication of losses replaces the old polib regression count
    assert "correct" in low and "wrong" in low, (
        "Recipe must require adjudicating every removed/changed entry as correct (term gone) or "
        "wrong (accidental loss -> BLOCK)"
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
    for section in ("## Role", "## Out of Scope", "## Standalone-first fallback"):
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


# ---------------------------------------------------------------------------
# Invariant 5 - P0 documents the language resolution mechanism
# ---------------------------------------------------------------------------

def test_p0_documents_language_resolution():
    """SKILL.md P0 must document the explicit language-resolution precedence mechanism.

    This gate protects the multi-language contract: an agent executing odoo-i18n MUST
    know HOW to resolve the target language list without guessing.  If the mechanism
    is removed from SKILL.md, the agent silently defaults to vi_VN or misreads the
    caller intent.

    The substrings asserted here are canonical strings from the SKILL.md P0 section.
    Removing or renaming any of them makes this test red.
    """
    assert SKILL_MD.exists(), f"SKILL.md not found at {SKILL_MD}"
    text = SKILL_MD.read_text(encoding="utf-8")

    # P0 section must exist
    assert "**P0" in text, "P0 section must be present in SKILL.md"

    # Machine-global registry path - the primary multi-lang config source
    assert "i18n.json" in text, (
        "P0 must reference i18n.json as the machine-global registry "
        "for default_languages (tier 2 of resolution precedence)"
    )

    # The key inside i18n.json that carries the language list
    assert "default_languages" in text, (
        "P0 must reference the `default_languages` array inside i18n.json "
        "so the agent knows which key to read"
    )

    # Tier 4: query live instance for active languages
    assert "res.lang" in text, (
        "P0 must document querying `res.lang` (active=True) as a fallback tier "
        "when neither args nor i18n.json nor existing .po files supply a language list"
    )

    # Per-lang artifact naming confirms multi-language is operational (D3 contract)
    assert "glossary-tm-<lang>" in text, (
        "SKILL.md must use per-language artifact naming `glossary-tm-<lang>.json` "
        "(D3 contract) - removing it breaks the multi-language dispatch contract"
    )


# ---------------------------------------------------------------------------
# Invariant 6 - en_US is ALWAYS loaded (KT3), and the .pot is ALWAYS re-exported
# fresh. Both are operational failure modes the maintainer hit in practice.
# ---------------------------------------------------------------------------

def test_recipe_kt3_en_us_always_loaded():
    """Recipe must state en_US is ALWAYS loaded alongside every target language (KT3)."""
    text = RECIPE.read_text(encoding="utf-8")
    assert "KT3" in text, "Recipe must carry a named KT3 callout for the en_US-always rule"
    assert "en_US" in text, "Recipe KT3 must name en_US as the base/source language"
    assert "--load-language=en_US" in text, (
        "Recipe L1 example commands must load en_US in the activation set "
        "(e.g. --load-language=en_US,<lang>), not the target language alone"
    )


def test_recipe_pot_freshness_gate():
    """Recipe must require a FRESH .pot re-export every run (never reuse a stale on-disk .pot)."""
    text = RECIPE.read_text(encoding="utf-8")
    assert "FRESH" in text and "stale" in text, (
        "Recipe must document the always-re-export-fresh .pot rule and warn against a stale "
        "on-disk template (the silent under-merge failure mode)"
    )


def test_p0_documents_en_us_mandatory_activation():
    """SKILL.md P0 must union en_US into the activation set, independent of the target tiers."""
    text = SKILL_MD.read_text(encoding="utf-8")
    assert "activation_languages" in text, (
        "P0 must define activation_languages (the DB-load set) distinct from the target languages"
    )
    assert 'union' in text and 'en_US' in text, (
        "P0 must state activation_languages = {\"en_US\"} union target_languages so en_US is "
        "ALWAYS loaded even though no resolution tier can produce it"
    )


def test_p4_gates_en_us_and_pot_freshness():
    """SKILL.md P4 validate must check en_US active AND .pot freshness, not the target lang alone."""
    text = SKILL_MD.read_text(encoding="utf-8")
    start = text.find("**P4")
    assert start != -1, "P4 section must be present"
    end = text.find("**P5", start + 1)
    p4 = text[start: end if end != -1 else len(text)]
    assert "en_US" in p4, (
        "P4 reload precondition must require en_US active too (KT3), not the target language alone"
    )
    assert "gate 5" in p4 or "re-exported THIS run" in p4, (
        "P4 must verify the .pot consumed was freshly re-exported this run (recipe gate 5)"
    )
