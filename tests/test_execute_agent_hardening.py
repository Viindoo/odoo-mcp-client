"""Contract tests for the execute-agent hardening pass.

These protect the BEHAVIOR the plugin promises to an execute AI agent (Claude /
Codex / Gemini) when it designs, codes, reviews, or debugs Odoo - NOT a snapshot
of any wording. Each assertion guards one wiring that, if silently dropped, would
take a guarantee with it: cross-agent decision logging, the three Odoo platform
design principles, bidirectional impact analysis, dynamic demo data, the
red-before-green test loop, and module-aware wave dispatch.

Red-before-green: deleting the corresponding reference makes exactly the matching
assertion fail. stdlib only.
"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
AGENTS = PLUGIN / "agents"
SNIPPETS = PLUGIN / "snippets"
SHARED = PLUGIN / "skills" / "_shared"
SKILLS = PLUGIN / "skills"

NEW_SNIPPETS = [
    SNIPPETS / "worklog-contract.md",
    SNIPPETS / "odoo-platform-design-principles.md",
    SNIPPETS / "bidirectional-impact.md",
    SNIPPETS / "demo-data-dynamic.md",
    SNIPPETS / "test-first-contract.md",
    SHARED / "odoo-module-graph.md",
]

# The seven agents that touch architecture / code / review / debug.
CORE_AGENTS = [
    "odoo-solution-architect",
    "odoo-coder",
    "odoo-frontend-coder",
    "odoo-code-reviewer",
    "odoo-ui-reviewer",
    "odoo-backend-debugger",
    "odoo-ui-debugger",
]

IMPACT_TOOL = "mcp__odoo-semantic__impact_analysis"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _frontmatter(p: Path) -> str:
    parts = _read(p).split("---", 2)
    return parts[1] if len(parts) >= 3 else ""


@pytest.mark.parametrize("snip", NEW_SNIPPETS, ids=lambda p: p.name)
def test_new_ssot_snippet_exists(snip):
    """Every cross-cutting concern has a single source-of-truth snippet."""
    assert snip.is_file(), f"missing SSOT snippet {snip}"


@pytest.mark.parametrize("snip", NEW_SNIPPETS, ids=lambda p: p.name)
def test_new_snippet_is_not_orphaned(snip):
    """A snippet nobody references is dead weight - require >=1 consumer."""
    name = snip.name
    consumers = list(AGENTS.glob("*.md")) + list(SKILLS.rglob("SKILL.md"))
    hits = sum(1 for f in consumers if name in _read(f))
    assert hits >= 1, f"{name} is referenced nowhere (orphaned SSOT)"


@pytest.mark.parametrize("agent", CORE_AGENTS)
def test_agent_can_run_impact_analysis(agent):
    """Bidirectional impact needs the tool actually granted in the allowlist."""
    fm = _frontmatter(AGENTS / f"{agent}.md")
    assert IMPACT_TOOL in fm, f"{agent}: {IMPACT_TOOL} missing from frontmatter tools"


@pytest.mark.parametrize("agent", CORE_AGENTS)
def test_agent_wires_cross_cutting_snippets(agent):
    """Every core agent reads the worklog, surveys both-direction impact, and
    respects the platform design principles."""
    body = _read(AGENTS / f"{agent}.md")
    for snip in (
        "worklog-contract.md",
        "bidirectional-impact.md",
        "odoo-platform-design-principles.md",
    ):
        assert snip in body, f"{agent}: missing reference to {snip}"


def test_coders_wire_test_first():
    """Both coders implement against a red test (red-before-green)."""
    for agent in ("odoo-coder", "odoo-frontend-coder"):
        assert "test-first-contract.md" in _read(AGENTS / f"{agent}.md"), (
            f"{agent}: missing test-first-contract reference"
        )


def test_architect_and_backend_coder_wire_demo_data():
    """Demo data is designed by the architect and built by the backend coder."""
    for agent in ("odoo-solution-architect", "odoo-coder"):
        assert "demo-data-dynamic.md" in _read(AGENTS / f"{agent}.md"), (
            f"{agent}: missing demo-data-dynamic reference"
        )


def test_module_graph_is_shared_by_coding_and_wave():
    """The module DAG is one SSOT, referenced by both dispatchers (no dup)."""
    mg = "odoo-module-graph.md"
    assert mg in _read(SKILLS / "odoo-coding" / "SKILL.md"), (
        "odoo-coding must reference the module-graph SSOT"
    )
    assert mg in _read(SKILLS / "wave" / "SKILL.md"), (
        "wave must reference the module-graph SSOT"
    )


def test_wave_respects_module_boundaries():
    """wave computes the Odoo module DAG and auto-infers WI dependencies."""
    body = _read(SKILLS / "wave" / "SKILL.md")
    assert "Odoo module DAG" in body, "wave Phase 0 must compute the Odoo module DAG"
    assert "depends_on" in body and "auto-infer" in body.lower(), (
        "wave must auto-infer WI depends_on from module dependencies"
    )


def test_code_review_gates_test_coverage_and_loops():
    """Review routes uncovered behavior to the test writer and keeps the loop."""
    body = _read(SKILLS / "odoo-code-review" / "SKILL.md")
    assert "next: odoo-test-writer" in body, (
        "code-review must route an uncovered behavior change to odoo-test-writer"
    )
    assert "next: odoo-coding" in body, (
        "code-review must keep the code->review->code loop for CRITICAL/HIGH fixes"
    )
    assert "test-first-contract.md" in body


def test_architect_reads_guidelines_and_forbids_fabrication():
    """The architect is the root of the design->code chain: if it skips the coding
    guidelines or invents field/method names, every downstream coder inherits the
    error. It must read the same guidelines as the coders and separate verified
    EXISTING entities from clearly-marked PROPOSED additions."""
    body = _read(AGENTS / "odoo-solution-architect.md")
    assert "coding_guidelines/<version>/INDEX.md" in body, (
        "architect must read coding_guidelines like odoo-coder / odoo-code-reviewer"
    )
    assert "EXISTING" in body and "PROPOSED" in body, (
        "architect must separate verified-existing entities from proposed-new ones"
    )
    assert "New/Existing" in body, (
        "the data-model table must mark each field as new vs existing"
    )


def test_new_authored_files_use_ascii_hyphen_only():
    """ETHOS output rule: no typographic dashes in files this pass authored."""
    # codepoints checked by ordinal so this guard file stays self-consistent
    banned = {0x2013: "en-dash", 0x2014: "em-dash", 0x2012: "figure-dash", 0x2015: "horizontal-bar"}
    offenders = []
    for f in NEW_SNIPPETS:
        text = _read(f)
        for cp, label in banned.items():
            if chr(cp) in text:
                offenders.append(f"{f.name}: contains {label}")
    assert not offenders, "typographic dashes found:\n" + "\n".join(offenders)
