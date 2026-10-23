"""Behaviour guards for the forward-port / documentation reshuffle (issues #276, #277, #278).

Each test protects a rule a runtime agent follows, by reading the prose it reads:
  - every forward-port (code, module docs, docs site) is owned by odoo-forward-port and lands as a
    merge; no other skill describes a port by cherry-pick, and odoo-doc-site has no PORT mode;
  - odoo-intake dispatches a port or an upgrade directly, without recon;
  - the two documentation agents exist with their modes, and the App Store page is the
    marketer's, not the doc-writer's;
  - the read-before-act snippet is cited by the orchestrators and the writing agents;
  - the framework validation classes are unioned by the instance agent, so a module-scoped run
    cannot skip them.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"


def _read(rel: str) -> str:
    return (PLUGIN / rel).read_text(encoding="utf-8")


def _prose_files():
    for sub in ("skills", "agents", "snippets", "commands", "workflows"):
        for path in (PLUGIN / sub).rglob("*"):
            if path.is_file() and path.suffix in {".md", ".yaml"}:
                yield path


# --- #276: one owner for every port -------------------------------------------------------------


def test_doc_site_has_no_port_mode():
    assert not (PLUGIN / "skills/odoo-doc-site/references/port.md").exists()
    for path in (PLUGIN / "skills/odoo-doc-site").rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        assert "PORT FROM" not in text, path
        assert "port.md" not in text, path
        assert "cherry-pick" not in text.lower(), path


def test_doc_site_routes_a_port_to_forward_port_and_takes_a_caller_worktree():
    skill = _read("skills/odoo-doc-site/SKILL.md")
    out_of_scope = skill.split("## Out of Scope")[1].split("## Inputs")[0]
    assert "odoo-forward-port" in out_of_scope
    assert "`WORKTREE`" in skill and "`LAND: caller`" in skill
    landing = _read("skills/odoo-doc-site/references/gates-and-landing.md")
    assert "LAND: caller" in landing and "never a squash" in landing


def test_forward_port_owns_the_docs_site_lane_and_never_cherry_picks():
    skill = _read("skills/odoo-forward-port/SKILL.md")
    assert "references/fp-docs-site-lane.md" in skill
    assert "REPO KIND" in skill
    assert "`odoo-doc-site` (PORT)" not in skill
    lane = _read("skills/odoo-forward-port/references/fp-docs-site-lane.md")
    assert "never a cherry-pick, never a squash" in lane
    assert "`LAND: caller`" in lane and "`WORKTREE`" in lane
    for bucket in ("`port`", "`skip`"):
        assert bucket in lane


def test_no_skill_outside_forward_port_describes_a_port_by_cherry_pick():
    pattern = re.compile(r"cherry-pick[^\n]{0,80}(forward|port(?:ed|ing)?\b)|"
                         r"(forward|port(?:ed|ing)?\b)[^\n]{0,80}cherry-pick", re.IGNORECASE)
    offenders = []
    for path in _prose_files():
        rel = path.relative_to(PLUGIN).as_posix()
        if rel.startswith("skills/odoo-forward-port/") or rel.startswith("snippets/fp-"):
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if pattern.search(line) and "never" not in line.lower():
                offenders.append(f"{rel}: {line.strip()[:120]}")
    assert not offenders, "\n".join(offenders)


def test_docs_after_change_is_the_one_closing_docs_rule():
    snippet = _read("snippets/docs-after-change.md")
    assert "installable: False" in snippet
    for rel in ("skills/odoo-forward-port/SKILL.md", "skills/odoo-modules-upgrade/SKILL.md",
                "skills/odoo-intake/references/plan-mode-schema.md"):
        assert "snippets/docs-after-change.md" in _read(rel), rel
    # the old inline restatement is gone from both pipelines
    for rel in ("skills/odoo-forward-port/SKILL.md", "skills/odoo-modules-upgrade/SKILL.md"):
        assert "Compose a change file" not in _read(rel), rel


def test_intake_dispatches_port_and_upgrade_directly():
    intake = _read("skills/odoo-intake/SKILL.md")
    section = " ".join(intake.split("## Direct dispatch")[1].split("\n## ")[0].split())
    assert "`odoo-forward-port`" in section and "`odoo-modules-upgrade`" in section
    assert "no Phase R" in section
    assert "`odoo-doc-site` with PORT" not in intake
    table = _read("skills/odoo-intake/references/routing-table.md")
    assert re.search(r"^\| 65 \|.*`odoo-forward-port`", table, re.M)
    assert "references/routing-table.md" in intake


# --- the two documentation agents -------------------------------------------------------------


def test_marketer_owns_the_landing_page_and_doc_writer_the_guide():
    marketer = _read("agents/odoo-marketer.md")
    writer = _read("agents/odoo-doc-writer.md")
    assert "## MODE landing" in marketer and "## MODE copy" in marketer
    assert "## MODE landing" not in writer and "## MODE full" in writer
    assert "static/description/index.html" not in writer
    for agent in (marketer, writer):
        assert "## Before you write" in agent
        assert "## Splitting the work" in agent
        assert "Model-tier selection" in agent
    assert "Verify before you claim" in marketer
    manifest = json.loads((PLUGIN / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    assert "./agents/odoo-marketer.md" in manifest["agents"]


def test_launchers_of_the_marketer_are_declared():
    deps = json.loads((PLUGIN / "generator/skill_tool_deps.json").read_text(encoding="utf-8"))
    orch = deps["orchestration"]
    assert orch["odoo-content-draft"]["spawns_agents"] == ["odoo-marketer"]
    assert "odoo-marketer" in orch["odoo-doc-illustration"]["spawns_agents"]
    assert deps["agents"]["odoo-marketer"]["brief"]["required"] == ["MODE", "SHARE_DIR", "ISOLATE_DIR"]
    assert "MARKETING COPY" not in deps["agents"]["odoo-doc-writer"]["brief"]["optional"]
    assert "odoo-marketer" in _read("skills/odoo-content-draft/SKILL.md")
    assert "odoo-marketer" in _read("skills/odoo-doc-illustration/SKILL.md")


# --- #277 / #278: read before act, read before ask ---------------------------------------------


def test_read_before_act_is_cited_where_decisions_are_made():
    for rel in ("skills/odoo-intake/SKILL.md", "skills/odoo-coding/SKILL.md",
                "skills/odoo-forward-port/SKILL.md", "skills/odoo-modules-upgrade/SKILL.md",
                "agents/odoo-coder.md", "agents/odoo-doc-writer.md", "agents/odoo-marketer.md"):
        assert "snippets/read-before-act.md" in _read(rel), rel
    snippet = _read("snippets/read-before-act.md")
    assert "coding_guidelines/<series>/INDEX.md" in snippet
    assert "upg-conventions.md" in snippet
    assert "no rule found" in snippet


def test_ethos_principle_2_reads_before_asking():
    ethos = _read("ODOO-AI-ETHOS.md")
    assert "## 2. Read Before Acting, Read Before Asking" in ethos
    assert "## 12. Descriptions are Claims, Source is Truth" in ethos
    assert "never widened" in ethos


def test_framework_classes_are_unioned_by_the_instance_agent():
    ops = _read("agents/odoo-instance-ops.md")
    scope = ops.split("**Test scope (HARD RULE")[1].split("### ")[0]
    assert "Framework-class union" in scope
    assert "Framework-validation test classes" in scope
    conv = _read("snippets/upg-conventions.md")
    assert "unions it into every test run" in conv


def test_upgrade_classifies_modules_and_gates_the_pr_on_it():
    skill = _read("skills/odoo-modules-upgrade/SKILL.md")
    assert "**upgraded**" in skill and "**already installable**" in skill
    p7 = skill.split("**P7 - Final review + PR")[1]
    assert "two-class gate" in p7
    assert "migrations/<older series>" in p7


def test_reviewer_r1_checks_every_guideline_section():
    reviewer = _read("agents/odoo-code-reviewer.md")
    r1 = reviewer.split("## MODE R1")[1].split("## MODE R2")[0]
    assert "every section of every guideline file" in r1
    assert "always-invisible" in r1
