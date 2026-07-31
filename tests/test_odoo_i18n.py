"""Behavioral invariant gate for the odoo-i18n cluster (#76).

Each test protects one contract clause that would break the skill's correctness
if removed.  Tests are read-only (file/JSON inspection only) - no odoo-bin or
PO-library execution needed.

Run: python -m pytest tests/test_odoo_i18n.py -v
"""

from __future__ import annotations

import json
import re
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


# ---------------------------------------------------------------------------
# Invariant 7 (CS-C11a) - the i18n-mandate prerequisites: the P0 gate is
# foldable into the caller's own gate, and the tier-5 vi_VN default becomes
# unreachable inside a mandated invocation.
# ---------------------------------------------------------------------------

def _normalize_ws(text: str) -> str:
    """Collapse all whitespace runs (including Markdown line-wraps) to a single
    space, so a literal-absence/presence assertion cannot be fooled by a phrase
    that happens to be line-wrapped across two source lines (one such assertion
    in this test family was previously a silent tautology for exactly that
    reason - see test_dispatch_brief.py's _LEAF_STOP_AND_RETURN_NEEDS_CONTEXT)."""
    return re.sub(r"\s+", " ", text)


def test_p0_gate_is_foldable_and_tier5_is_unreachable_inside_a_mandate():
    """P0's human STOP must fold into the caller's own gate when the caller supplied
    everything (mandated invocation); standalone tier-5 vi_VN default must be
    unreachable inside a mandate - it must record `not-applicable` instead.

    Protects ledger rows N2 + N5/N6d: a mandate that always STOPs for a human is a
    deadlock (RC-4), and a mandate combined with an unqualified tier-5 default would
    silently generate Vietnamese catalogs for a user who never asked for them.
    """
    assert SKILL_MD.exists(), f"SKILL.md not found at {SKILL_MD}"
    text = SKILL_MD.read_text(encoding="utf-8")
    normalized = _normalize_ws(text)

    # The mandated/standalone discriminator must name all three field-presence
    # conditions - a caller supplying anything less falls back to the STOP.
    for field in ("TARGET LANGUAGES", "INSTANCE_HANDLE", "SELF_PROVISION: worktree-addons", "WORKTREE_PATH"):
        assert field in normalized, (
            f"SKILL.md P0 gate-fold paragraph must name {field!r} as one of the "
            "mandated-invocation discriminator fields"
        )

    # Both gate destinations must be present and distinguishable.
    assert "Standalone" in text and "Mandated" in text, (
        "SKILL.md must distinguish a Standalone STOP from a Mandated fold-into-caller's-gate"
    )
    assert "do NOT stop" in normalized or "do not stop" in normalized.lower(), (
        "SKILL.md must state the mandated path does NOT stop for a human"
    )

    # Tier 5 must be explicitly qualified as standalone-only.
    tier5_idx = text.find('Default `["vi_VN"]`')
    assert tier5_idx != -1, "SKILL.md must still carry the tier-5 `Default [\"vi_VN\"]` line"
    tier5_line = text[tier5_idx: text.find("\n", tier5_idx)]
    assert "standalone" in tier5_line.lower(), (
        "tier 5's `Default [\"vi_VN\"]` line must be qualified 'standalone invocations ONLY' - "
        "an unqualified default is reachable even inside a mandate"
    )

    # The not-applicable hatch must be the literal, documented mandated-tier-5 outcome.
    assert "not-applicable" in text, (
        "SKILL.md must document the `not-applicable` outcome for a mandated invocation "
        "that reaches tier 5 (all four resolution tiers empty)"
    )
    mandate_idx = text.find("MANDATED invocation")
    assert mandate_idx != -1, "SKILL.md must carry a 'MANDATED invocation' callout for tier 5"

    # vi_VN must never appear in the same PARAGRAPH as MANDAT* (case-insensitive) -
    # the mandate path must never resolve to the hardcoded default language. Split
    # on blank-line paragraph boundaries (robust to Markdown line-wrap AND to `**`
    # bold markers defeating a period-based sentence splitter - the tier-5 line
    # ends in "ONLY.**", which a naive `[.!?]\s+` splitter fails to break on).
    for paragraph in re.split(r"\n\s*\n", text):
        if re.search(r"mandat", paragraph, re.IGNORECASE):
            assert "vi_VN" not in paragraph, (
                f"a MANDATE-describing paragraph must never mention vi_VN directly: {paragraph!r}"
            )


def test_recipe_names_the_addons_mechanism_not_just_the_requirement():
    """Recipe § Validation item 4 (post-adapt export) must name the MECHANISM
    (WORKTREE_PATH -> odoo-instance addons re-root), not just restate the
    requirement - the requirement alone (no mechanism) is what let a
    worktree-only msgid surface as neither removed nor changed (ledger row N6d).
    """
    assert RECIPE.exists(), f"i18n-recipe.md not found at {RECIPE}"
    text = RECIPE.read_text(encoding="utf-8")

    start = text.find("Export against the adapted code")
    assert start != -1, (
        "Recipe must still carry the 'Export against the adapted code' validation item"
    )
    end = text.find("\n5.", start)
    section = text[start: end if end != -1 else len(text)]

    assert "addons" in section, (
        "Recipe's post-adapt-export item must name the addons-path mechanism, not just the "
        "requirement (this item named it ZERO times before CS-C11a)"
    )
    assert "WORKTREE_PATH" in section, (
        "Recipe's post-adapt-export item must name WORKTREE_PATH as the mechanism passed "
        "through to odoo-instance"
    )
    # Whitespace-normalized: the phrase legitimately line-wraps in the source
    # ("... § Addons coverage\n   assertion; ..."), and a literal-absence/presence
    # assertion over the raw text would be a silent tautology if it searched for
    # a phrase that can never appear unwrapped (the exact failure mode already
    # found once in this spec family).
    assert "Addons coverage assertion" in _normalize_ws(text), (
        "Recipe must point at the Addons coverage assertion (instance-handle-contract.md) "
        "before the L1 export - a pointer, not a restatement (CS-C2 declares it once)"
    )


# ---------------------------------------------------------------------------
# Invariant 8 (CS-C11b) - the i18n mandate: MANDATORY reconcile with an
# enumerated escape, declared ONCE in snippets/i18n-mandate-contract.md, and
# odoo-modules-upgrade's P5.7 no longer auto-SKIPs on a content-diff predicate.
# ---------------------------------------------------------------------------

UPG_PHASE_DETAIL = (
    PLUGIN / "skills" / "odoo-modules-upgrade" / "references" / "upg-phase-detail.md"
)
MANDATE_CONTRACT = PLUGIN / "snippets" / "i18n-mandate-contract.md"


def _tree_texts():
    """Every text artifact under the plugin (md/yaml/json/txt/sh/py) - mirrors
    test_planning_ssot.py's `_tree_texts` glob so a "declared exactly once"
    check has the same reach across the whole plugin tree."""
    exts = {".md", ".yaml", ".yml", ".json", ".txt", ".sh", ".py"}
    for p in PLUGIN.rglob("*"):
        if p.is_file() and p.suffix in exts:
            yield p, p.read_text(encoding="utf-8")


def test_upgrade_i18n_gate_has_no_content_diff_skip():
    """upg-phase-detail.md's P5.7 must no longer auto-SKIP on a content-diff predicate.

    RC-4: a CONTENT predicate ("did the diff touch a label?") guards a FORMAT concern (the
    `.pot`/`.po` tooling changes across a major series independently of content). Both literals
    below were the auto-SKIP wording this replaces; their presence means the mandate regressed
    back to a silent content-diff skip. Whitespace-normalized so a hard-wrapped reintroduction of
    either phrase cannot slip past a raw substring search.
    """
    assert UPG_PHASE_DETAIL.exists(), f"upg-phase-detail.md not found at {UPG_PHASE_DETAIL}"
    norm = _normalize_ws(UPG_PHASE_DETAIL.read_text(encoding="utf-8"))
    for literal in ("no translatable-surface change", "diff the P4 commits for translatable tokens"):
        assert literal not in norm, (
            f"upg-phase-detail.md P5.7 must NOT contain {literal!r} - the i18n reconcile is "
            "MANDATORY for every surviving module, not auto-skipped on a content-diff read"
        )


def test_i18n_mandate_contract_is_the_single_definer():
    """The mandate's definitional phrase must be declared in EXACTLY ONE file: the new
    snippets/i18n-mandate-contract.md SSOT. Any other file carrying it would be a 2nd,
    driftable definition instead of a pointer."""
    assert MANDATE_CONTRACT.exists(), f"i18n-mandate-contract.md not found at {MANDATE_CONTRACT}"
    text = MANDATE_CONTRACT.read_text(encoding="utf-8")
    assert "The run is not DONE until" in text and "a per-module result or a RECORDED escape" in text, (
        "i18n-mandate-contract.md must carry the authoritative mandate definition"
    )
    definers = sorted(
        str(p.relative_to(PLUGIN))
        for p, t in _tree_texts()
        if "The run is not DONE until" in t and "a per-module result or a RECORDED escape" in t
    )
    assert definers == ["snippets/i18n-mandate-contract.md"], (
        f"The i18n mandate definition must exist in exactly ONE place; found in: {definers}"
    )


def test_mandate_contract_enumerates_escapes_and_the_right_predicate():
    """The mandate contract must enumerate all six escapes + all eight trigger signals and the
    `installable_false` predicate, and must NOT let the falsified `target_installable` /
    `target_grounding` predicate creep back in (the two-sided form is what gives this teeth)."""
    assert MANDATE_CONTRACT.exists()
    text = MANDATE_CONTRACT.read_text(encoding="utf-8")

    for escape_id in ("E1", "E2", "E3", "E4", "E5", "E6"):
        assert escape_id in text, f"i18n-mandate-contract.md must enumerate escape {escape_id}"
    for signal_id in ("S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8"):
        assert signal_id in text, f"i18n-mandate-contract.md must enumerate trigger signal {signal_id}"

    assert "installable_false" in text, (
        "i18n-mandate-contract.md condition 2 must read the `installable_false` field"
    )
    assert "Ambiguity counts as a HIT" in text, (
        "i18n-mandate-contract.md must state the trigger's HIT-biased ambiguity rule explicitly"
    )
    assert "not-applicable" in text, (
        "i18n-mandate-contract.md must document the tier-5 `not-applicable` escape wording"
    )

    normalized = _normalize_ws(text)
    for banned in ("target_installable", "target_grounding"):
        assert banned not in normalized, (
            f"i18n-mandate-contract.md must NOT reference {banned!r} - the falsified predicate "
            "must not creep back; installable_false is the ONE field any consumer reads"
        )
