"""Module version bumps and migration scripts are one decision, taken last; a database upgrade
between series is never module or plugin work."""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"


def _read(rel):
    return re.sub(r"\s+", " ", (PLUGIN / rel).read_text(encoding="utf-8"))


def test_only_the_migration_node_bumps_and_writes_migration_scripts():
    rule = _read("snippets/odoo-platform-design-principles.md")
    assert "the plan's `migration` node is the ONLY step that edits a module's `version`" in rule
    assert "immediately before `integrate`" in rule
    assert "by the smallest step (the last component +1)" in rule
    assert "`migrations/<series>.<new short version>/`" in rule
    assert "scripts/lib/migration_gate.py check" in rule


@pytest.mark.parametrize("rel, phrase", [
    ("agents/odoo-coder.md", "An existing module's `version` and anything under `migrations/` are touched only when your brief carries `MODE: migration`"),
    ("agents/odoo-frontend-coder.md", "Edit the `version` key or anything under `migrations/` only when your brief asks for it"),
    ("agents/odoo-test-writer.md", "the `version` or `migrations/` only when your brief asks for it"),
    ("skills/odoo-intake/references/plan-mode-schema.md", "A build node edits a module's `version` or `migrations/` only when its brief asks for it"),
])
def test_no_build_node_touches_a_version_or_a_migration_folder_unless_asked(rel, phrase):
    assert phrase in _read(rel)


def test_the_migration_script_is_coded_by_the_coder_and_reviewed():
    skill = _read("skills/odoo-data-migration/SKILL.md")
    assert "Launch** ONE `odoo-coder` (model `sonnet`) with `MODE: migration`" in skill
    assert "`odoo-code-reviewer` `MODE: R1` (model `haiku`)" in skill
    assert "It writes no code itself." in skill
    coder = _read("agents/odoo-coder.md")
    assert "| `MODE: migration` |" in coder and "references/writing-the-script.md" in coder
    how = _read("skills/odoo-data-migration/references/writing-the-script.md")
    assert "a real upgrade within the series" in how and "migration_gate.py check" in how


def test_the_migration_node_sits_last_before_integrate():
    schema = _read("skills/odoo-intake/references/plan-mode-schema.md")
    assert "depends_on: [i18n, docs-module]" in schema
    assert "depends_on: [migration] - id: monitor" in schema
    assert "`integrate` follows `migration` - the planner never drops or moves it" in schema
    assert "migration_gate.py check` (base tree = the branch base" in schema


def test_the_migration_skill_runs_only_as_the_plan_node_and_computes_the_version():
    skill = _read("skills/odoo-data-migration/SKILL.md")
    assert "this skill runs only as the plan's `migration` node" in skill
    how = _read("skills/odoo-data-migration/references/writing-the-script.md")
    assert "the new version is the smallest step" in how
    assert "extend its existing `migrations/<series>.<version>/` folder instead of adding a second one" in how
    carve_out = _read("snippets/planning-gate-contract.md").split("## Migration carve-out")[1]
    assert "next: odoo-coding" not in carve_out.split("## ")[0]


def test_review_flags_a_version_or_migration_edit_outside_the_migration_node():
    assert "a `version` edit or a `migrations/` file in a node that is not the plan's `migration` node" in _read(
        "agents/odoo-code-reviewer.md")


PROSE = [p for p in PLUGIN.rglob("*") if p.is_file() and p.suffix in {".md", ".yaml", ".sh"}
         and "CHANGELOG" not in p.name]


@pytest.mark.parametrize("pattern", [r"openupgrade", r"migration-notes", r"\bMIG\b", r"migration project"])
def test_no_prose_offers_a_database_upgrade_as_plugin_work(pattern):
    hits = [str(p.relative_to(PLUGIN)) for p in PROSE
            if re.search(pattern, p.read_text(encoding="utf-8", errors="ignore"), re.IGNORECASE)]
    assert not hits, hits


def test_a_database_upgrade_request_is_routed_out():
    route = "a database upgrade between series needs a dedicated upgrade tool and repository; not this plugin"
    assert route in _read("skills/odoo-intake/references/routing-table.md").lower()
    assert route in _read("skills/odoo-intake/references/collision-zones.md").lower()
    assert "needs a dedicated upgrade tool and repository" in _read("snippets/upg-conventions.md")
    assert "needs a dedicated upgrade tool and repository" in _read("skills/odoo-modules-upgrade/SKILL.md")


def test_the_code_upgrade_writes_no_migration_and_bumps_no_version():
    skill = _read("skills/odoo-modules-upgrade/SKILL.md")
    assert "never bumps a `version`" in skill
    assert "(b) any module's manifest `version` changed other than by dropping a series prefix, or a migration script was added" in skill


def test_the_deploy_checklist_has_no_database_migration_domain():
    skill = _read("skills/odoo-deploy-checklist/SKILL.md")
    template = _read("skills/odoo-deploy-checklist/references/checklist-template.md")
    assert "Seven standard domains" in skill
    assert "Data migration" not in skill and "Data migration" not in template
    assert "### 7. Rollback" in template
