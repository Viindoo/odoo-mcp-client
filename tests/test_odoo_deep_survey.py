"""Contract guards for the two capabilities added to `odoo-deep-survey`:

  A. Phase W - a LIGHTWEIGHT, CONDITIONAL, BOUNDED web-research pass that reuses the existing
     fork-worker fan-out and does NOT dispatch/depend on the heavy built-in `deep-research`
     skill.
  B. A ZERO-TRUST code-survey stance ("descriptions are CLAIMS, source is TRUTH") that is
     scoped to odoo-deep-survey ONLY and does NOT invert OSM-first.

These are CONTRACT checks (does the rule exist + is it wired + is it scoped), not string-count
snapshots - the prose may drift as long as the invariants below hold.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"

SKILL = PLUGIN / "skills" / "odoo-deep-survey" / "SKILL.md"
WEB_RESEARCH = PLUGIN / "skills" / "odoo-deep-survey" / "references" / "web-research.md"
LENSES = PLUGIN / "skills" / "odoo-deep-survey" / "references" / "survey-lenses.md"
SYNTH = PLUGIN / "skills" / "odoo-deep-survey" / "references" / "synthesis-schema.md"
ZERO_TRUST = PLUGIN / "snippets" / "zero-trust-code-survey.md"
WORKER_BRIEF = PLUGIN / "snippets" / "worker-brief.md"


def _txt(p: Path) -> str:
    assert p.exists(), f"missing required file: {p}"
    return p.read_text(encoding="utf-8")


def _tree_texts():
    exts = {".md", ".yaml", ".yml", ".json", ".txt", ".sh", ".py"}
    for p in PLUGIN.rglob("*"):
        if p.is_file() and p.suffix in exts:
            yield p, p.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# A. Phase W - web research
# ---------------------------------------------------------------------------

def test_phase_w_reference_exists_and_is_referenced_by_the_skill():
    web = _txt(WEB_RESEARCH)
    assert "Phase W" in web, "web-research.md must define Phase W."
    skill = _txt(SKILL)
    assert "## Phase W" in skill, "SKILL.md must carry a Phase W section."
    assert "references/web-research.md" in skill, (
        "SKILL.md must point at references/web-research.md for the full Phase W procedure."
    )


def test_phase_w_is_conditional_on_an_external_dimension():
    """Phase W fires ONLY on an external-dimension sub-question, and is SKIPPED for a pure
    in-codebase/OSM survey - consistent with the skill's evidence-triggered discipline."""
    for p in (SKILL, WEB_RESEARCH):
        low = _txt(p).lower()
        assert "external" in low, f"{p.name}: Phase W trigger must name an EXTERNAL dimension."
        assert "only if" in low, f"{p.name}: Phase W must state it runs 'only if' the trigger holds."
        assert "skip" in low, (
            f"{p.name}: Phase W must state it is SKIPPED for a pure in-codebase/OSM survey."
        )


def test_phase_w_is_bounded_no_loop_harness():
    """Phase W must be explicitly BOUNDED: a stated cap, and an explicit negation of a
    loop-until-dry / N-vote / unbounded fan-out harness."""
    for p in (SKILL, WEB_RESEARCH):
        low = _txt(p).lower()
        assert "loop-until-dry" in low, f"{p.name}: must explicitly rule out a loop-until-dry pass."
        assert "n-vote" in low, f"{p.name}: must explicitly rule out an N-vote adversarial harness."
        assert "unbounded" in low, f"{p.name}: must explicitly rule out unbounded fan-out."
    # A concrete numeric cap on web workers must be stated.
    assert "<= 4" in _txt(WEB_RESEARCH) or "<= 4" in _txt(SKILL), (
        "Phase W must state a concrete cap on the number of web workers."
    )


def test_phase_w_does_not_depend_on_deep_research_skill():
    """odoo-deep-survey must NOT dispatch or depend on the heavy built-in `deep-research` skill:
    every mention of it must be a NEGATION (do NOT dispatch/depend)."""
    survey_dir = PLUGIN / "skills" / "odoo-deep-survey"
    for p in survey_dir.rglob("*.md"):
        text = p.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines()):
            if "deep-research" in line:
                assert "NOT" in line or "not " in line.lower(), (
                    f"{p.name}:{i+1}: `deep-research` mentioned without a NOT-dispatch/depend "
                    f"negation -> {line.strip()!r}"
                )
    # No skill-invocation of deep-research anywhere in the survey (e.g. Skill(deep-research)).
    for p in survey_dir.rglob("*.md"):
        text = p.read_text(encoding="utf-8")
        assert "Skill(deep-research" not in text and "skill: deep-research" not in text, (
            f"{p.name}: must not invoke the deep-research skill."
        )


def test_source_credibility_ladder_and_web_subordinate_rule_present():
    web = _txt(WEB_RESEARCH)
    low = web.lower()
    # Three-tier ladder.
    for tier in ("authoritative", "reputable", "low-trust"):
        assert tier in low, f"web-research.md: source-credibility ladder must name the '{tier}' tier."
    # Authoritative anchors.
    assert "github.com/odoo/odoo" in web and "github.com/OCA" in web, (
        "web-research.md: authoritative tier must name the odoo/odoo and OCA sources."
    )
    # Web-subordinate-to-OSM HARD rule.
    assert "subordinate" in low, "web-research.md: must state web is SUBORDINATE to OSM/source."
    assert "osm/source wins" in low or "osm/source win" in low, (
        "web-research.md: must state OSM/source WINS on disagreement with a web claim."
    )
    # Every finding carries provenance.
    assert "fetch-date" in low, "web-research.md: web findings must carry a fetch-date."


def test_web_findings_section_in_synthesis_schema():
    synth = _txt(SYNTH)
    assert "web_findings" in synth, "synthesis-schema.md must declare a web_findings section."
    assert "VERIFIED/UNVERIFIED" in synth or "VERIFIED / UNVERIFIED" in synth, (
        "web_findings rows must carry a VERIFIED/UNVERIFIED verdict."
    )
    assert "source-tier" in synth, "web_findings rows must carry a source-tier."
    # Present only when Phase W ran.
    assert "only when Phase W ran" in synth or "present only when phase w" in synth.lower(), (
        "synthesis-schema.md must state web_findings is present only when Phase W ran."
    )


# ---------------------------------------------------------------------------
# B. Zero-trust code survey
# ---------------------------------------------------------------------------

def test_zero_trust_snippet_exists_and_states_the_rule():
    z = _txt(ZERO_TRUST)
    low = z.lower()
    assert "descriptions are claims" in low and "source is truth" in low, (
        "zero-trust-code-survey.md must state 'descriptions are CLAIMS, source is TRUTH'."
    )
    # Descriptive OSM fields are demoted to claims...
    assert "describe_module" in z, (
        "zero-trust snippet must name OSM DESCRIPTIVE fields (e.g. describe_module) as claims."
    )
    # ...but OSM STRUCTURE stays trusted (does NOT invert OSM-first).
    for struct_tool in ("model_inspect", "entity_lookup", "resolve_orm_chain",
                        "find_override_point", "impact_analysis"):
        assert struct_tool in z, (
            f"zero-trust snippet must name the trusted OSM STRUCTURE tool '{struct_tool}'."
        )
    assert "not" in low and "invert" in low, (
        "zero-trust snippet must explicitly state it does NOT invert OSM-first."
    )
    # Source wins on disagreement.
    assert "source wins" in low, (
        "zero-trust snippet must state source WINS when a description disagrees with source."
    )
    # RESOLVED only when source-grounded.
    assert "resolved" in low, "zero-trust snippet must tie a RESOLVED finding to the source."


def test_zero_trust_wired_into_deep_survey():
    skill = _txt(SKILL)
    assert "snippets/zero-trust-code-survey.md" in skill, (
        "SKILL.md must point at the zero-trust snippet (Hard-rule + worker-brief inline)."
    )
    # Prepended to the survey-lenses preamble.
    assert "snippets/zero-trust-code-survey.md" in _txt(LENSES), (
        "survey-lenses.md preamble must carry the one-line zero-trust rule + pointer."
    )


def test_zero_trust_scope_is_deep_survey_only():
    """Scope discipline: the zero-trust snippet must be referenced ONLY by odoo-deep-survey
    files (and itself) - NOT promoted to worker-brief.md or any other skill."""
    referrers = sorted(
        str(p.relative_to(PLUGIN))
        for p, t in _tree_texts()
        if "zero-trust-code-survey" in t
    )
    for rel in referrers:
        assert rel.startswith("skills/odoo-deep-survey/") or rel == "snippets/zero-trust-code-survey.md", (
            f"zero-trust-code-survey is out of scope: referenced by {rel} (deep-survey ONLY)."
        )
    assert "zero-trust-code-survey" not in _txt(WORKER_BRIEF), (
        "worker-brief.md must NOT reference the zero-trust snippet (scope = deep-survey only)."
    )
