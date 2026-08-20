"""Behavioral gate: every Odoo instance BUILD must load en_US.

The maintainer hit an operational failure where a built instance (create / init /
fresh test-DB) activated only the target language and left en_US (Odoo's base/source
language) missing. These read-only assertions lock the "en_US always on every build"
invariant into the odoo-instance skill, the odoo-instance-ops agent, and the shared
lifecycle contract doc.

Run: python -m pytest tests/test_odoo_instance_en_us.py -v
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN = REPO_ROOT / "plugins" / "odoo-ai-agents"

SKILL_MD = PLUGIN / "skills" / "odoo-instance" / "SKILL.md"
AGENT_MD = PLUGIN / "agents" / "odoo-instance-ops.md"
LIFECYCLE_DOC = PLUGIN / "docs" / "reference" / "INSTANCE-LIFECYCLE-BUILD-CONTRACT.md"


def test_skill_states_en_us_mandatory_on_build():
    """odoo-instance SKILL.md must own the en_US-on-every-build invariant (union rule)."""
    text = SKILL_MD.read_text(encoding="utf-8")
    assert "en_US" in text and "mandatory on every build" in text, (
        "odoo-instance SKILL.md must state en_US is mandatory on every build"
    )
    assert 'activation_languages = {"en_US"} union languages' in text, (
        "SKILL.md must define the union formula so the skill adds en_US before dispatch"
    )


def test_skill_no_longer_pushes_en_us_to_caller():
    """The old pass-through wording (caller must add en_US) must be gone - the skill owns it."""
    text = SKILL_MD.read_text(encoding="utf-8")
    assert "must include `en_US` (Odoo's base language) itself" not in text, (
        "SKILL.md must NOT tell the caller to add en_US - the instance layer now owns the invariant"
    )


def test_agent_hard_rule_en_us_on_build():
    """odoo-instance-ops.md must carry a HARD RULE that en_US is always loaded on build ops."""
    text = AGENT_MD.read_text(encoding="utf-8")
    assert "en_US" in text and "HARD RULE" in text, (
        "odoo-instance-ops.md must carry an en_US HARD RULE"
    )
    # names the build ops it governs
    for op in ("create-instance", "init-modules"):
        assert op in text, f"agent HARD RULE must name the build op {op!r}"


def test_agent_create_and_init_activate_en_us():
    """create-instance and init-modules sections must fold en_US into --load-language."""
    text = AGENT_MD.read_text(encoding="utf-8")

    def _section(header_start: str, header_end: str) -> str:
        s = text.find(header_start)
        assert s != -1, f"section {header_start!r} not found"
        e = text.find(header_end, s + 1)
        return text[s: e if e != -1 else len(text)]

    create = _section("### 1. create-instance", "### 2. drop-instance")
    init = _section("### 3. init-modules", "### 4. update-modules")
    for name, sec in (("create-instance", create), ("init-modules", init)):
        assert "en_US" in sec and "load-language" in sec, (
            f"{name} section must activate en_US via --load-language (build-time invariant)"
        )


def test_agent_self_review_covers_en_us_build():
    """The agent self-review checklist must include an en_US-on-build item."""
    text = AGENT_MD.read_text(encoding="utf-8")
    assert "no build completes without `en_US` active" in text, (
        "self-review checklist must assert no build completes without en_US active"
    )


def test_lifecycle_doc_cross_references_en_us_invariant():
    """INSTANCE-LIFECYCLE-BUILD-CONTRACT.md must carry the en_US-always-on-build item."""
    text = LIFECYCLE_DOC.read_text(encoding="utf-8")
    assert "en_US" in text and "always active on any first `-i`" in text, (
        "INSTANCE-LIFECYCLE-BUILD-CONTRACT.md must document the en_US-on-every-build rule"
    )
