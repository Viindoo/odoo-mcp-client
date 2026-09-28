"""Behavioral gate: every Odoo instance build loads en_US, and the TOOL guarantees it.

The maintainer hit an operational failure where a built instance activated only the target
language and left en_US (Odoo's base/source language) missing. The guarantee now lives in
`instance_build`, which adds en_US to every build's language set itself
(tests/test_odoo_local_mcp_build_facts.py proves the argv). What the prose must do is point every
executor at that argument and never teach a second, hand-composed path: an agent that builds its
own `--load-language` set in `extra_args` is refused by the tool, and an agent told to "union
en_US" into a flag it can no longer pass stalls or improvises.

These read-only assertions lock that contract into the odoo-instance skill, the odoo-instance-ops
agent, the build-facts SSOT and the lifecycle contract doc.

Run: python -m pytest tests/test_odoo_instance_en_us.py -v
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN = REPO_ROOT / "plugins" / "odoo-ai-agents"

SKILL_MD = PLUGIN / "skills" / "odoo-instance" / "SKILL.md"
AGENT_MD = PLUGIN / "agents" / "odoo-instance-ops.md"
PIVOTS = PLUGIN / "snippets" / "odoo-version-pivots.md"
HANDLE = PLUGIN / "snippets" / "instance-handle-contract.md"
LIFECYCLE_DOC = PLUGIN / "docs" / "reference" / "INSTANCE-LIFECYCLE-BUILD-CONTRACT.md"

# The executors of an instance build: what they say is what an agent does.
BUILD_EXECUTORS = (SKILL_MD, AGENT_MD, PIVOTS, LIFECYCLE_DOC)


def _norm(path: Path) -> str:
    return re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))


def _section(text: str, start: str, end: str) -> str:
    s = text.find(start)
    assert s != -1, f"section {start!r} not found - re-anchor this test"
    e = text.find(end, s + 1)
    return text[s: e if e != -1 else len(text)]


def test_ssot_states_the_tool_adds_en_us_to_every_build():
    """One place states the rule; everyone else points at it."""
    text = _norm(PIVOTS)
    facts = _section(text, "## Build facts the odoo-local tools apply", "### Demo data by build PURPOSE")
    assert re.search(r"the tool adds `en_US` to every build", facts), (
        "the build-facts SSOT must state that instance_build adds en_US to every build"
    )
    assert "languages_failed" in facts, (
        "the SSOT must say a requested language can fail and is then reported, never assumed loaded"
    )


def test_skill_passes_languages_as_a_build_argument_and_never_adds_en_us():
    """The skill forwards the caller's languages; the tool, not the skill, adds en_US."""
    text = _norm(SKILL_MD)
    assert re.search(r"`languages` \|[^|]*`instance_build`[^|]*adds `en_US` to every build", text), (
        "the dispatch table's `languages` row must say it reaches instance_build, which adds en_US"
    )
    assert "activation_languages = {\"en_US\"} union languages" not in text, (
        "the skill must no longer compute its own en_US union - the tool owns it"
    )
    assert "must include `en_US` (Odoo's base language) itself" not in text, (
        "the caller must never be told to add en_US"
    )


def test_agent_build_operations_pass_languages_to_instance_build():
    """create-instance and init-modules hand the languages to the tool as an argument."""
    text = _norm(AGENT_MD)
    create = _section(text, "### 1. create-instance", "### 2. drop-instance")
    init = _section(text, "### 3. init-modules", "### 4. update-modules")
    for name, sec in (("create-instance", create), ("init-modules", init)):
        assert re.search(r"`instance_build` \(op `init`[^)]*`languages`", sec), (
            f"{name} must pass `languages` to instance_build"
        )
        assert "en_US` is added by the tool" in sec, (
            f"{name} must say en_US is added by the tool, so the agent never adds it"
        )


def test_no_executor_composes_a_load_language_flag():
    """A hand-composed `--load-language=...` is refused by instance_build (INVALID_ARGUMENTS).

    Mentioning the flag by name is fine (e.g. to say the tool applies it); spelling a value for it
    is an instruction to compose it, which is the defect."""
    offenders = [
        str(p.relative_to(REPO_ROOT))
        for p in BUILD_EXECUTORS
        if re.search(r"--load-language=", p.read_text(encoding="utf-8"))
    ]
    assert not offenders, (
        "these build executors still compose a --load-language value by hand instead of passing "
        f"`languages` to instance_build: {offenders}"
    )


def test_agent_reports_languages_from_job_wait():
    """The loaded set is what the build log proved, never what was asked for."""
    text = _norm(AGENT_MD)
    rule = _section(text, "## Demo, languages and server-wide modules (HARD RULE)", "## Lint modules")
    assert "never add `en_US` yourself" in rule, "the agent must not add en_US by hand"
    assert re.search(r"`languages_loaded` / `languages_failed` from the final `job_wait`", rule), (
        "the agent must report loaded/failed languages from job_wait"
    )
    assert re.search(r"`languages_failed`[^.]*`concerns:`", rule), (
        "a failed language must surface as a concern, never be reported loaded"
    )


def test_handle_contract_states_languages_loaded_is_the_database_fact():
    """INSTANCE_HANDLE.languages_loaded is what the DATABASE has active (the tools read it from
    the database, a forwarded one included), and every tool build puts en_US there - so a
    consumer checking en_US + its target language reads the database, not one lease's request."""
    text = _norm(HANDLE)
    assert re.search(r"`languages_loaded` - the languages active in the DATABASE "
                     r"\(every tool build loads `en_US`\)", text)
    assert "proved loaded" not in text, (
        "languages_loaded is read from the database, not only what a build's log proved"
    )


def test_lifecycle_doc_points_at_the_tool_owned_language_rule():
    """The lifecycle checklist must say the tools own languages (en_US included) and point at the SSOT."""
    text = _norm(LIFECYCLE_DOC)
    assert re.search(r"every requested language with `en_US` always added", text), (
        "INSTANCE-LIFECYCLE-BUILD-CONTRACT.md must state the build loads en_US on every build"
    )
    assert "§ Build facts the odoo-local tools apply" in text, (
        "the checklist item must point at the build-facts SSOT rather than restate it"
    )
