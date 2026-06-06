"""Guard: every skill/workflow the intake router points at must actually exist.

intake/SKILL.md hard-codes a routing table + collision-zone guidance that name
specialist skills and workflows as redirect targets. There is no automated link
between that prose and the real components, so a renamed or removed skill would
leave intake silently routing to a dead target. This test fails if intake names
a skill/workflow/command slug that no longer exists.

It deliberately checks *reference existence*, not verbatim phrase matching:
description wording is allowed to drift (it gets compacted over time); what must
never drift is that intake points at real components.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-semantic-skills"
INTAKE = PLUGIN / "skills" / "intake" / "SKILL.md"


def _valid_targets():
    skills = {p.parent.name for p in (PLUGIN / "skills").glob("*/SKILL.md")}
    workflows = {p.name[: -len(".workflow.yaml")] for p in (PLUGIN / "workflows").glob("*.workflow.yaml")}
    commands = {p.stem for p in (PLUGIN / "commands").glob("*.md")}
    # Commands are invoked via their slash name, which intake writes with an
    # `odoo-` prefix (e.g. command file `odoo-run-brl.md` -> `/odoo-run-brl`).
    command_slugs = commands | {f"odoo-{c}" for c in commands}
    extra = {"intake", "wave", "workflow-chaining"}
    return skills | workflows | command_slugs | extra


# A backticked token is treated as a routing target only if it looks like a
# skill/workflow slug — i.e. an odoo-* slug or one of the known orchestrators.
# This avoids false positives on backticked paths, tool names, or file globs.
TARGET_RE = re.compile(r"`/?([a-z][a-z0-9]*(?:-[a-z0-9]+)+|intake|wave)`")
KNOWN_NON_TARGETS = {
    # backticked tokens that look slug-ish but are not routing targets
    "odoo-ai", "set-active-version", "content-md",
    # legacy component intake names only to say it was replaced
    "odoo-upgrade-planner",
}


def test_intake_targets_exist():
    valid = _valid_targets()
    text = INTAKE.read_text(encoding="utf-8")
    referenced = set()
    for m in TARGET_RE.finditer(text):
        tok = m.group(1)
        # only care about things that plausibly name a skill/workflow target
        if tok in KNOWN_NON_TARGETS:
            continue
        if tok.startswith("odoo-") or tok in {"intake", "wave", "workflow-chaining",
                                              "support-triage", "video-produce",
                                              "content-production", "discovery-quick",
                                              "bid-respond", "feature-positioning",
                                              "upgrade-plan-full", "customer-followup-draft"}:
            referenced.add(tok)
    missing = sorted(t for t in referenced if t not in valid)
    assert not missing, (
        "intake/SKILL.md routes to targets that do not exist as a skill/workflow/command: "
        f"{missing}. Update intake's routing table/collision zones, or restore the target."
    )
    # sanity: the router must reference a meaningful number of real targets
    assert len(referenced) >= 10, (
        f"intake referenced only {len(referenced)} routing targets — parsing likely broke"
    )
