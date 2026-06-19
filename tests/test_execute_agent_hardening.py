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
    SNIPPETS / "read-before-write-contract.md",
    SNIPPETS / "test-behavior-contract.md",
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
    """Bidirectional impact needs OSM available. Agents inherit the full surface
    (no `tools:` allowlist), so impact_analysis is available unless explicitly disallowed."""
    fm = _frontmatter(AGENTS / f"{agent}.md")
    assert "\ntools:" not in ("\n" + fm), (
        f"{agent}: must omit the `tools:` allowlist so it inherits the full odoo-semantic surface"
    )
    assert IMPACT_TOOL not in fm, (
        f"{agent}: must not disallow {IMPACT_TOOL} (inherited; required for impact analysis)"
    )


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
    assert "next: odoo-test-writing" in body, (
        "code-review must route an uncovered behavior change to odoo-test-writing"
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


# ---------------------------------------------------------------------------
# B2 - coding-guidelines as mandatory context (read-before-write)
# ---------------------------------------------------------------------------

GUIDELINE_STRING = "coding_guidelines/<version>/INDEX.md"


@pytest.mark.parametrize(
    "agent", ["odoo-coder", "odoo-frontend-coder", "odoo-code-reviewer"]
)
def test_coders_and_reviewer_read_coding_guidelines(agent):
    """Each code-writing/reviewing agent names the version-pinned guideline index, so a
    dispatched agent is told - at execution time - to read it before writing."""
    body = _read(AGENTS / f"{agent}.md")
    assert GUIDELINE_STRING in body, (
        f"{agent}: must reference {GUIDELINE_STRING} (read-before-write)"
    )


def test_read_before_write_snippet_wired_into_code_agents():
    """The read-before-write SSOT is referenced by the agents that write/review code."""
    snip = "read-before-write-contract.md"
    for agent in (
        "odoo-coder",
        "odoo-frontend-coder",
        "odoo-code-reviewer",
        "odoo-solution-architect",
    ):
        assert snip in _read(AGENTS / f"{agent}.md"), (
            f"{agent}: missing reference to {snip}"
        )


def test_coding_brief_defers_procedure_to_agent_system_prompt():
    """A dispatched coder reads the coding guidelines before writing. After the brief slim-down
    the execution-time SSOT for that read-before-write rule is the coder AGENT BODY (its Round-1
    HARD RULE) - NOT a re-taught copy in the odoo-coding dispatch brief, which would duplicate the
    SSOT and silently drift. So this protects the real behavior, not a brief snapshot:
    (1) each coder agent body names the version-pinned guideline index, and (2) the odoo-coding
    brief defers procedure to the coder's own system prompt instead of re-teaching it."""
    guideline = "coding_guidelines/<version>/INDEX.md"
    for agent in ("odoo-coder", "odoo-frontend-coder"):
        assert guideline in _read(AGENTS / f"{agent}.md"), (
            f"{agent}: agent body must name {guideline} (execution-time SSOT for read-before-write)"
        )
    skill = _read(SKILLS / "odoo-coding" / "SKILL.md")
    assert "system prompt" in skill.lower(), (
        "odoo-coding brief must defer procedure to the coder's system-prompt Rounds "
        "(not re-teach the guideline read)"
    )


# ---------------------------------------------------------------------------
# B3 - test-behavior contract (anti-shortcut)
# ---------------------------------------------------------------------------

TEST_BEHAVIOR_SNIPPET = "test-behavior-contract.md"

# Every file wired to the anti-shortcut contract (agents + skills).
TEST_BEHAVIOR_WIRED = [
    AGENTS / "odoo-coder.md",
    AGENTS / "odoo-frontend-coder.md",
    AGENTS / "odoo-code-reviewer.md",
    AGENTS / "odoo-solution-architect.md",
    AGENTS / "odoo-backend-debugger.md",
    SKILLS / "odoo-test-writing" / "SKILL.md",
    SKILLS / "odoo-qa-suite" / "SKILL.md",
    SKILLS / "odoo-coding" / "SKILL.md",
]


@pytest.mark.parametrize("f", TEST_BEHAVIOR_WIRED, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_behavior_contract_is_wired(f):
    """Every author/reviewer of a test references the anti-shortcut arrange contract."""
    assert TEST_BEHAVIOR_SNIPPET in _read(f), (
        f"{f.name}: missing reference to {TEST_BEHAVIOR_SNIPPET}"
    )


def test_behavior_contract_names_forbidden_and_required_tokens():
    """The snippet must concretely name the forbidden shortcut and the required real-workflow
    tokens - a vague 'test the behavior' note would not actually steer an agent."""
    body = _read(SNIPPETS / TEST_BEHAVIOR_SNIPPET)
    assert "create({'state'" in body, "snippet must name the forbidden shortcut pattern"
    assert "Form(" in body, "snippet must require Form() for onchange arrange"
    for tok in ("action_confirm", "action_validate", "button_validate"):
        assert tok in body, f"snippet must name the real workflow method {tok}"
    assert "with_user(" in body and "sudo(" in body, (
        "snippet must state the with_user-not-sudo access rule"
    )


def test_code_reviewer_rejects_shortcut_tests():
    """The reviewer must treat a shortcut test as a HIGH finding, not wave it through."""
    body = _read(AGENTS / "odoo-code-reviewer.md")
    assert TEST_BEHAVIOR_SNIPPET in body
    assert "change-detector" in body or "shortcut" in body, (
        "code-reviewer must call out shortcut/change-detector tests"
    )


def test_qa_suite_steps_name_action_methods():
    """The QA suite Steps column must drive real workflow actions, not seed states."""
    body = _read(SKILLS / "odoo-qa-suite" / "SKILL.md")
    assert TEST_BEHAVIOR_SNIPPET in body
    assert "action_" in body, "qa-suite must name action_* methods in its Steps guidance"


# ---------------------------------------------------------------------------
# B4 - security.md pitfalls doc: existence, wiring, and hygiene
# ---------------------------------------------------------------------------

VERSIONS = ["14.0", "15.0", "16.0", "17.0", "18.0", "19.0"]

CODING_GUIDELINES = SHARED / "coding_guidelines"

SECURITY_AGENTS = [
    "odoo-coder",
    "odoo-frontend-coder",
    "odoo-code-reviewer",
    "odoo-solution-architect",
]


@pytest.mark.parametrize("ver", VERSIONS)
def test_security_pitfalls_doc_exists(ver):
    """Each version directory ships a security.md containing the canonical heading.
    Red-before-green: deleting a security.md fails exactly its parametrized case."""
    sec = CODING_GUIDELINES / ver / "security.md"
    assert sec.is_file(), f"missing {sec}"
    assert "# Security Pitfalls" in _read(sec), (
        f"{sec}: must contain '# Security Pitfalls' heading"
    )


@pytest.mark.parametrize("ver", VERSIONS)
def test_python_guideline_warning_resolves_to_security_md(ver):
    """python.md warns about Security Pitfalls and the warning resolves locally
    via the substring 'security.md' - the old dangling token
    'reference/security/pitfalls' must be gone.
    Red-before-green: reverting python.md to the dangling form fails this case."""
    python_md = _read(CODING_GUIDELINES / ver / "python.md")
    assert "security.md" in python_md, (
        f"{ver}/python.md: must contain 'security.md' (locally-resolvable warning)"
    )
    assert "reference/security/pitfalls" not in python_md, (
        f"{ver}/python.md: must NOT contain the old dangling token 'reference/security/pitfalls'"
    )


@pytest.mark.parametrize("agent", SECURITY_AGENTS)
def test_code_agents_must_read_security_guideline(agent):
    """Secure-coding pitfalls are now part of the mandatory read-before-write set.
    Each code-writing/reviewing agent body must contain 'security.md' so a
    dispatched agent is told to read it before producing any code.
    Red-before-green: removing the reference from an agent body fails that case."""
    body = _read(AGENTS / f"{agent}.md")
    assert "security.md" in body, (
        f"{agent}: must reference 'security.md' (mandatory read-before-write for secure coding)"
    )


def test_read_before_write_snippet_lists_security():
    """The read-before-write SSOT snippet must enumerate security.md so every
    consumer of that snippet inherits the secure-coding read obligation."""
    snip = _read(SNIPPETS / "read-before-write-contract.md")
    assert "security.md" in snip, (
        "read-before-write-contract.md: must list 'security.md' in its backend read set"
    )


@pytest.mark.parametrize("ver", VERSIONS)
def test_security_docs_use_ascii_hyphen_only(ver):
    """ETHOS output rule: no typographic dashes or smart quotes in the new security.md files.
    Checked by ordinal so this guard file stays self-consistent."""
    # codepoints checked by ordinal so this guard file stays self-consistent
    banned = {
        0x2013: "en-dash",
        0x2014: "em-dash",
        0x2012: "figure-dash",
        0x2015: "horizontal-bar",
        0x2018: "left-single-quote",
        0x2019: "right-single-quote",
        0x201C: "left-double-quote",
        0x201D: "right-double-quote",
    }
    sec = CODING_GUIDELINES / ver / "security.md"
    text = _read(sec)
    offenders = []
    for cp, label in banned.items():
        if chr(cp) in text:
            offenders.append(f"{ver}/security.md: contains {label} (U+{cp:04X})")
    assert not offenders, "typographic characters found:\n" + "\n".join(offenders)


def test_no_dangling_verify_guidelines_script():
    """'verify-guidelines.sh' was a dangling reference to a non-existent script.
    It must not appear in INDEX.md or read-before-write-contract.md after being
    replaced by the real verify-backend.sh / verify-frontend.sh."""
    dangling = "verify-guidelines.sh"
    index_md = _read(CODING_GUIDELINES / "INDEX.md")
    assert dangling not in index_md, (
        f"coding_guidelines/INDEX.md: must not reference the non-existent '{dangling}'"
    )
    rbw = _read(SNIPPETS / "read-before-write-contract.md")
    assert dangling not in rbw, (
        f"read-before-write-contract.md: must not reference the non-existent '{dangling}'"
    )
