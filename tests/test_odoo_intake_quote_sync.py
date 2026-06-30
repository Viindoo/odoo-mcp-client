"""Guard: every skill/workflow the odoo-intake router points at must actually exist.

odoo-intake/SKILL.md hard-codes a routing table + collision-zone guidance that name
specialist skills and workflows as redirect targets. There is no automated link
between that prose and the real components, so a renamed or removed skill would
leave odoo-intake silently routing to a dead target. This test fails if odoo-intake names
a skill/workflow/command slug that no longer exists.

It deliberately checks *reference existence*, not verbatim phrase matching:
description wording is allowed to drift (it gets compacted over time); what must
never drift is that odoo-intake points at real components.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
INTAKE = PLUGIN / "skills" / "odoo-intake" / "SKILL.md"


def _valid_targets():
    skills = {p.parent.name for p in (PLUGIN / "skills").glob("*/SKILL.md")}
    workflows = {p.name[: -len(".workflow.yaml")] for p in (PLUGIN / "workflows").glob("*.workflow.yaml")}
    commands = {p.stem for p in (PLUGIN / "commands").glob("*.md")}
    # Commands are invoked via their slash name, which odoo-intake writes with an
    # `odoo-` prefix (e.g. command file `odoo-run-brl.md` -> `/odoo-run-brl`).
    command_slugs = commands | {f"odoo-{c}" for c in commands}
    # Agents are not routing targets, but odoo-intake names them when explaining how a
    # spawner skill fans out (e.g. `odoo-code-review` runs `odoo-code-reviewer`).
    # Validate them as real referents too so a typo'd agent name still fails.
    agents = {p.stem for p in (PLUGIN / "agents").glob("*.md")}
    # `odoo-wave` is now a real skill dir (the internal git-executor, user-invocable: false),
    # so it is covered by `skills`; the bare `wave` skill no longer exists and intake no longer
    # names it. `odoo-intake`/`workflow-chaining`/`run-harness` are also real skill dirs - kept
    # here only as belt-and-suspenders for the router's self-references.
    extra = {"odoo-intake", "workflow-chaining", "run-harness"}
    return skills | workflows | command_slugs | agents | extra


# A backticked token is treated as a routing target only if it looks like a
# skill/workflow slug - i.e. an odoo-* slug or one of the known orchestrators.
# This avoids false positives on backticked paths, tool names, or file globs.
# `wave` is kept in the alternation on purpose: it is a single-word token that the
# hyphenated general pattern would not catch, so without it a stray `` `wave` `` reference
# (the old skill, now removed and renamed `odoo-wave`, user-invocable: false) would go
# unseen. It is intentionally NOT in `_valid_targets()`, so any such reference FAILS -
# guarding against intake routing users back to the dead skill.
TARGET_RE = re.compile(r"`/?([a-z][a-z0-9]*(?:-[a-z0-9]+)+|odoo-intake|wave)`")
KNOWN_NON_TARGETS = {
    # backticked tokens that look slug-ish but are not routing targets
    "odoo-ai", "set-active-version", "content-md",
    # legacy component odoo-intake names only to say it was replaced
    "odoo-upgrade-planner",
}


def test_intake_defers_to_forward_port_own_gate():
    """Intake must document that skills with a stronger own gate (e.g. odoo-forward-port)
    are launched directly without a duplicate soft-plan-gate emission."""
    text = INTAKE.read_text(encoding="utf-8")
    assert "stronger gate" in text.lower(), (
        "odoo-intake/SKILL.md must document the exception for skills that own a stronger gate "
        "(e.g. odoo-forward-port), instructing intake to skip the soft-plan-gate and launch directly. "
        "Add the 'Exception - skills that own a stronger gate' paragraph to the Soft plan gate section."
    )


def test_odoo_intake_targets_exist():
    valid = _valid_targets()
    text = INTAKE.read_text(encoding="utf-8")
    referenced = set()
    for m in TARGET_RE.finditer(text):
        tok = m.group(1)
        # only care about things that plausibly name a skill/workflow target
        if tok in KNOWN_NON_TARGETS:
            continue
        if tok.startswith("odoo-") or tok in {"odoo-intake", "wave", "workflow-chaining",
                                              "run-harness",
                                              "support-triage", "video-produce",
                                              "content-production", "discovery-quick",
                                              "bid-respond", "feature-positioning",
                                              "upgrade-plan-full", "customer-followup-draft"}:
            referenced.add(tok)
    missing = sorted(t for t in referenced if t not in valid)
    assert not missing, (
        "odoo-intake/SKILL.md routes to targets that do not exist as a skill/workflow/command: "
        f"{missing}. Update odoo-intake's routing table/collision zones, or restore the target."
    )
    # sanity: the router must reference a meaningful number of real targets
    assert len(referenced) >= 10, (
        f"odoo-intake referenced only {len(referenced)} routing targets - parsing likely broke"
    )
