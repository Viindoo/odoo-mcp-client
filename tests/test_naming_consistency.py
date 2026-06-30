"""Guard against bare `odoo-semantic` plugin-refs drifting back into the
trigger-phrase / fallback-prose doc surface.

After the plugin split, a lone `odoo-semantic` token in a skill trigger phrase or a
standalone-fallback sentence is ambiguous between the two plugins (`-mcp`/`-skills`).
This test fails if such a bare token appears in that surface, after the legitimate
lexical forms (tool prefix, suffixed plugin name, product URL) are stripped.

Scope is deliberately narrow: config/persona/README/CHANGELOG/snippets legitimately
use the bare server id or the brand and are NOT scanned.
"""
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SK = REPO_ROOT / "plugins" / "odoo-ai-agents"

SCANNED = sorted(
    set(SK.glob("skills/**/SKILL.md"))
    | set(SK.glob("skills/**/evals/*.json"))
    | set(SK.glob("commands/*.md"))
    | {REPO_ROOT / "tests" / "smoke" / "runtime_parity.md"}
)

_LEGIT = re.compile(
    r"mcp__odoo-semantic__\w*"
    r"|odoo-semantic-mcp"
    r"|odoo-semantic\.viindoo\.com"
)
_BARE = re.compile(r"odoo-semantic")


@pytest.mark.parametrize(
    "doc", SCANNED, ids=lambda p: str(p.relative_to(REPO_ROOT))
)
def test_no_bare_odoo_semantic_in_trigger_or_fallback_prose(doc):
    offenders = []
    for n, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
        if _BARE.search(_LEGIT.sub("", line)):
            offenders.append(f"{doc.relative_to(REPO_ROOT)}:{n}: {line.strip()}")
    assert not offenders, (
        "Bare `odoo-semantic` in a trigger phrase or fallback sentence. Use "
        "`odoo-semantic-mcp` / `odoo-ai-agents`, the brand `Odoo Semantic`, "
        "or rephrase (e.g. 'the odoo-semantic-mcp server'):\n" + "\n".join(offenders)
    )


# ===========================================================================
# Naming morphology enforcement (ADR-001 Phase A)
# ---------------------------------------------------------------------------
# Names encode role so a router can tell the three layers apart even when a
# name appears bare. Prior to this, only the bare `odoo-semantic` token was
# guarded - the morphology rule was *claimed* "enforced" in prose but had no
# test behind it, which is how a `run-driver`-class offender (unprefixed AND
# actor morphology used as a skill) slipped in. These tests make the claim
# real. Scope is `plugins/odoo-ai-agents` only (where the three-layer
# morphology applies); the `odoo-semantic-mcp` `connect` command and the
# Apache-licensed, domain-agnostic `git-toolkit` names are deliberately out of
# scope - they are not part of this plugin's role-morphology contract.
# SSOT for the prose: CLAUDE.md "Three layers", CONTRIBUTING.md "Naming
# convention", docs/authoring-skills-and-agents.md section 5.
# ===========================================================================

# The ONLY unprefixed (domain-agnostic) names allowed. `wave` left the list
# when it became `odoo-wave`; `run-harness` (the renamed run-driver sequencer)
# joined it. Keep in lockstep with the three prose statements above.
_NAMING_ALLOWLIST = {"workflow-chaining", "run-harness"}

# Agentive (actor) derivational suffixes. Matched against the LAST hyphen
# segment with `search(... $)` so it is a suffix of that single token, NOT a
# substring of the whole name (which would wrongly flag `inventory` for "or").
_ACTOR_SUFFIX = re.compile(r"(?:er|or|ist)$")
# NOTE: `(?:er|or|ist)$` also matches a segment ending in "list" (via the "ist"
# tail) - that is exactly why {checklist} is in the capability-noun exception set
# below. A FUTURE legitimate capability-noun skill whose last segment ends in
# "-list"/"-or"/"-er" (e.g. a hypothetical `odoo-watch-list`) would likewise need
# an entry added to _SKILL_CAPABILITY_NOUN_EXCEPTIONS to stay valid.

# Capability nouns whose last segment happens to END in an actor suffix but
# are NOT actor nouns - so a SKILL may legitimately use them. `checklist`
# ("check"+"list") ends in "ist" yet is a plain noun, not an "-ist" actor.
# Sourced from the current valid tree (odoo-deploy-checklist).
_SKILL_CAPABILITY_NOUN_EXCEPTIONS = {"checklist"}

# Actor nouns that are valid AGENT names but lack an -er/-or/-ist suffix.
# Sourced from the current valid agent tree: odoo-instance-ops ("ops"),
# odoo-solution-architect ("architect"). A naive "must end in -er/-or/-ist"
# rule would false-positive on these, so they are explicitly allowed.
_AGENT_ACTOR_EXCEPTIONS = {"ops", "architect"}


def _last_segment(name):
    """Last hyphen-delimited segment of a layer name (`odoo-code-review` -> `review`)."""
    return name.rsplit("-", 1)[-1]


def _is_prefixed_or_allowlisted(name):
    """Rule 1: every name is `odoo-`-prefixed, except the explicit allowlist."""
    return name.startswith("odoo-") or name in _NAMING_ALLOWLIST


def _skill_uses_actor_morphology(name):
    """Rule 2: True if a SKILL name's last segment is actor (-er/-or/-ist) morphology.

    Token-scoped: the suffix is matched against the last segment only, and a
    small capability-noun exception set keeps `checklist`-style nouns valid.
    """
    seg = _last_segment(name)
    return bool(_ACTOR_SUFFIX.search(seg)) and seg not in _SKILL_CAPABILITY_NOUN_EXCEPTIONS


def _agent_is_actor_noun(name):
    """Rule 3: True if an AGENT name is an actor noun.

    Actor = last segment ends in -er/-or/-ist, OR is one of the explicit actor
    nouns that lack such a suffix (`ops`, `architect`). This avoids the
    documented false-positive a bare "-er/-or/-ist required" rule would cause.
    """
    seg = _last_segment(name)
    return bool(_ACTOR_SUFFIX.search(seg)) or seg in _AGENT_ACTOR_EXCEPTIONS


def _fm_name(path):
    """Return the top-level `name:` scalar from a file's leading frontmatter."""
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() == "---":
            continue
        if line.startswith("name:"):
            return line.split(":", 1)[1].strip()
    return None


_SKILL_NAMES = sorted(p.parent.name for p in SK.glob("skills/*/SKILL.md"))
_AGENT_PATHS = sorted(SK.glob("agents/*.md"))
_AGENT_NAMES = sorted(p.stem for p in _AGENT_PATHS)
_COMMAND_PATHS = sorted(SK.glob("commands/*.md"))
_COMMAND_NAMES = sorted(p.stem for p in _COMMAND_PATHS)
_ALL_NAMES = sorted(set(_SKILL_NAMES) | set(_AGENT_NAMES) | set(_COMMAND_NAMES))


def test_enumeration_is_non_empty():
    """Guard: a broken glob must not make the morphology tests vacuously pass."""
    assert _SKILL_NAMES and "odoo-coding" in _SKILL_NAMES
    assert _AGENT_NAMES and "odoo-coder" in _AGENT_NAMES
    assert _COMMAND_NAMES and "odoo-run-brl" in _COMMAND_NAMES


@pytest.mark.parametrize("name", _ALL_NAMES)
def test_name_is_prefixed_or_allowlisted(name):
    """Rule 1: every skill/agent/command is `odoo-`-prefixed unless allowlisted.

    Catches the run-driver class of offender: an unprefixed name that is not in
    the {workflow-chaining, run-harness} domain-agnostic allowlist.
    """
    assert _is_prefixed_or_allowlisted(name), (
        f"name '{name}' is not `odoo-`-prefixed and not in the unprefixed "
        f"allowlist {sorted(_NAMING_ALLOWLIST)}. Add the `odoo-` prefix."
    )


@pytest.mark.parametrize("name", _SKILL_NAMES)
def test_skill_name_is_not_actor_morphology(name):
    """Rule 2: a SKILL is a capability noun, never an actor (-er/-or/-ist).

    Catches `run-driver` ("driver" = actor morphology used as a skill) while
    leaving capability nouns like `odoo-deploy-checklist` valid.
    """
    assert not _skill_uses_actor_morphology(name), (
        f"skill '{name}' ends in actor morphology ('{_last_segment(name)}'). "
        f"Skills are capability nouns; rename or move it to an agent."
    )


@pytest.mark.parametrize("name", _AGENT_NAMES)
def test_agent_name_is_actor_noun(name):
    """Rule 3: an AGENT is an actor noun.

    Actor = -er/-or/-ist suffix, or an explicit exception (`ops`, `architect`)
    that is an actor noun without such a suffix. A capability-noun name (e.g.
    `*-analysis`, `*-ing`) used as an agent fails here.
    """
    assert _agent_is_actor_noun(name), (
        f"agent '{name}' is not an actor noun (last segment "
        f"'{_last_segment(name)}'). Agents are actor nouns - use an "
        f"-er/-or/-ist suffix, or add it to the actor exception set if it is a "
        f"genuine actor noun without one."
    )


@pytest.mark.parametrize(
    "path", _AGENT_PATHS + _COMMAND_PATHS, ids=lambda p: p.stem
)
def test_name_matches_filename(path):
    """Frontmatter `name` must equal the filename for agents and commands.

    (Skill name==directory is already covered by test_skill_format.py, so it is
    not duplicated here.)
    """
    assert _fm_name(path) == path.stem, (
        f"{path.stem}: frontmatter name '{_fm_name(path)}' must equal the "
        f"filename '{path.stem}'"
    )


def test_naming_classifier_self_check():
    """Red-before-green: prove the classifier FLAGS violators and PASSES valid
    names, without depending on mutating the real tree (behavior, not snapshot).
    """
    # (a) FLAGS synthetic violators ------------------------------------------
    # Skill with actor morphology (the run-driver class, suffix as own segment):
    assert _skill_uses_actor_morphology("odoo-foo-er")
    # Unprefixed, non-allowlisted name:
    assert not _is_prefixed_or_allowlisted("foo-bar")
    # The historical offender is caught on BOTH axes:
    assert not _is_prefixed_or_allowlisted("run-driver")
    assert _skill_uses_actor_morphology("run-driver")
    # Capability noun masquerading as an agent:
    assert not _agent_is_actor_noun("odoo-foo-analysis")

    # (b) PASSES valid names -------------------------------------------------
    assert _is_prefixed_or_allowlisted("odoo-planning")
    assert not _skill_uses_actor_morphology("odoo-planning")
    assert _agent_is_actor_noun("odoo-planner")
    assert not _skill_uses_actor_morphology("odoo-deploy-checklist")  # ends "ist"
    assert _is_prefixed_or_allowlisted("run-harness")
    assert not _skill_uses_actor_morphology("run-harness")            # "harness"
    assert _agent_is_actor_noun("odoo-solution-architect")            # "architect"
    assert _agent_is_actor_noun("odoo-instance-ops")                  # "ops"
