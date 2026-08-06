"""Guard: no `L0`/`L1`/`L2` tier token in any EMITTED template.

Business contract being protected: `L0`/`L1`/`L2` is the DRIVER's internal gate-tier control
vocabulary. It belongs in `run-harness`'s resolution logic, in the registry's `default_gate_tier`,
in a node's `gate_tier`, and in `generator/check_orchestration.py`'s `VALID_GATE_TIER` - all
machinery a human never reads. It does NOT belong in anything the plugin RENDERS: a gate prompt the
human answers, or a Continuation Contract a step emits. A tier token there leaks scheduler jargon
into the surface people (and downstream readers) actually see.

Scope - and why the scoping matters more than the breadth: a version of this test that also flagged
`run-harness`'s driver-loop pseudocode or the registry's `default_gate_tier` would be flagging the
legitimate internal use, and the next maintainer would delete it. So the corpus is narrowed
mechanically to EMITTED TEMPLATE blocks - a fenced block that is one of:

  * a gate prompt (its body carries a gate keyword set verbatim: `approve / refine` or
    `approve / skip`, the two sets `snippets/planning-gate-contract.md` declares), or
  * a Continuation Contract template (fence info-string `continuation`, or a body carrying a
    `- skill:` entry - the shape of the contract's `next[]` list).

Everything else - prose, the driver loop, JSON blackboard examples, the registry, this repo's
Python - is out of scope by construction, and `test_internal_gate_tier_control_values_are_out_of_
scope` proves it with the real files rather than by assertion.

Tests are behavior-first (ETHOS #8): the rule is stated as a business rule ("an emitted template
carries no tier token"), the detector is proven capable of failing on a synthetic fixture, and the
scoping is proven against the real tree in both directions.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN = REPO_ROOT / "plugins" / "odoo-ai-agents"
if str(PLUGIN) not in sys.path:
    sys.path.insert(0, str(PLUGIN))

from generator.check_orchestration import agent_facing_files  # noqa: E402

# A fenced block. 3+ backticks with a matching closer, so a ````-wrapped example that itself
# contains a ``` fence (snippets/continuation-contract.md does exactly this) is read as ONE block
# instead of terminating early.
FENCE_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?P<ticks>`{3,})(?P<info>[^\n]*)\n(?P<body>.*?)^(?P=indent)(?P=ticks)",
    re.S | re.M,
)
# The two gate keyword sets, spelled the way snippets/planning-gate-contract.md declares them.
# Case- and space-exact on purpose: `run-harness`'s driver-loop comment says "resume after
# approve/skip/cancel" (no spaces) - a description of the mechanism, not a rendered prompt.
GATE_KEYWORDS_RE = re.compile(r"approve / (?:refine|skip)")
# A `next[]` entry - unique to a Continuation Contract template.
CONTRACT_NEXT_ITEM_RE = re.compile(r"^\s*-\s*skill\s*:", re.M)
CONTINUATION_FENCE_INFO = "continuation"

TIER_TOKEN_RE = re.compile(r"\bL[012]\b")


def _emitted_templates(text: str):
    """Yield (fence_info, body, body_offset) for every EMITTED template block in `text`."""
    for m in FENCE_RE.finditer(text):
        info = m.group("info").strip().lower()
        body = m.group("body")
        is_emitted = (
            info == CONTINUATION_FENCE_INFO
            or bool(GATE_KEYWORDS_RE.search(body))
            or bool(CONTRACT_NEXT_ITEM_RE.search(body))
        )
        if is_emitted:
            yield info, body, m.start("body")


def _tier_findings(files) -> list[str]:
    """Every `<relpath>:<line>: <line text>` where an emitted template carries a tier token."""
    findings: list[str] = []
    for f in files:
        text = f.read_text(encoding="utf-8")
        rel = f.relative_to(PLUGIN)
        for _info, body, offset in _emitted_templates(text):
            for m in TIER_TOKEN_RE.finditer(body):
                line_no = text.count("\n", 0, offset + m.start()) + 1
                line = body[body.rfind("\n", 0, m.start()) + 1: body.find("\n", m.start())]
                findings.append(f"{rel}:{line_no}: {line.strip()}")
    return sorted(set(findings))


# ---------------------------------------------------------------------------
# The rule
# ---------------------------------------------------------------------------


def test_no_emitted_gate_or_contract_template_carries_a_tier_token():
    """A rendered gate prompt / emitted Continuation Contract must carry no L0/L1/L2 token."""
    findings = _tier_findings(agent_facing_files())
    assert not findings, (
        "L0/L1/L2 is the driver's INTERNAL gate-tier vocabulary - it must not appear in a gate "
        "prompt or an emitted Continuation Contract template:\n  " + "\n  ".join(findings)
    )


# ---------------------------------------------------------------------------
# Scoping proofs - the legitimate internal uses must stay unflagged, and the
# detector must be able to fail (red-before-green).
# ---------------------------------------------------------------------------


def test_run_harness_driver_loop_pseudocode_is_out_of_scope():
    """`run-harness`'s gate-tier resolution is the legitimate internal use and must not be flagged.

    Premise first (so this cannot pass vacuously): the driver-loop fence really does carry tier
    tokens. Then: none of this file's findings point at it.
    """
    text = (PLUGIN / "skills" / "run-harness" / "SKILL.md").read_text(encoding="utf-8")
    loop_fences = [
        m.group("body") for m in FENCE_RE.finditer(text)
        if TIER_TOKEN_RE.search(m.group("body")) and "pick_ready" in m.group("body")
    ]
    assert loop_fences, (
        "premise: run-harness's driver-loop fence must carry tier tokens, otherwise this test "
        "proves nothing about scoping"
    )
    findings = _tier_findings([PLUGIN / "skills" / "run-harness" / "SKILL.md"])
    assert not findings, (
        "run-harness's internal gate-tier control values must never be flagged - a test that "
        f"flags them protects nothing because it will be deleted:\n  " + "\n  ".join(findings)
    )


def test_registry_and_lint_tier_values_are_out_of_scope():
    """`skill_tool_deps.json`'s `default_gate_tier` and the lint's `VALID_GATE_TIER` are internal.

    Neither is a template, so neither is in the scanned corpus at all - asserted structurally so a
    future widening of `agent_facing_files()` cannot silently pull them in.
    """
    scanned = set(agent_facing_files())
    for internal in (
        PLUGIN / "generator" / "skill_tool_deps.json",
        PLUGIN / "generator" / "check_orchestration.py",
    ):
        assert internal.is_file(), f"premise: {internal} must exist"
        assert internal not in scanned, (
            f"{internal.name} declares the tier ENUM - it is machinery, never an emitted template"
        )


def test_detector_flags_a_synthetic_gate_prompt_and_contract(tmp_path):
    """Mutation proof: the detector goes red on both emitted-template shapes, and stays quiet on
    the same tier token sitting in ordinary prose or an unrelated fence."""
    offender = tmp_path / "SKILL.md"
    offender.write_text(
        "Prose mentioning L1 outside any fence must not be flagged.\n"
        "\n"
        "```\n"
        "## Proposed Plan\n"
        "Risk: L2\n"
        "Gate: approve / refine: [feedback] / cancel\n"
        "```\n"
        "\n"
        "```continuation\n"
        "status: NEEDS_NEXT\n"
        "next:\n"
        "  - skill: odoo-acceptance\n"
        "    risk_level: L2\n"
        "```\n"
        "\n"
        "```python\n"
        "tier = 'L1'  # an unrelated code fence, not an emitted template\n"
        "```\n",
        encoding="utf-8",
    )
    # Relative-path rendering in _tier_findings needs the file under PLUGIN; use the raw helper.
    hits = []
    text = offender.read_text(encoding="utf-8")
    for _info, body, _offset in _emitted_templates(text):
        hits += [m.group() for m in TIER_TOKEN_RE.finditer(body)]
    assert hits == ["L2", "L2"], (
        f"expected exactly the gate-prompt and contract tier tokens, got {hits}"
    )


def test_clean_synthetic_templates_produce_no_finding(tmp_path):
    """The same two template shapes without tier tokens must be silent - so the rule fails for the
    right reason (the token), not merely because a gate/contract block exists."""
    clean = tmp_path / "SKILL.md"
    clean.write_text(
        "```\n"
        "## Proposed Plan\n"
        "Gate: approve / refine: [feedback] / cancel\n"
        "```\n"
        "\n"
        "```continuation\n"
        "status: NEEDS_NEXT\n"
        "next:\n"
        "  - skill: odoo-acceptance\n"
        "    confidence: 0.7\n"
        "```\n",
        encoding="utf-8",
    )
    text = clean.read_text(encoding="utf-8")
    blocks = list(_emitted_templates(text))
    assert len(blocks) == 2, f"premise: both blocks must be recognised as emitted, got {blocks}"
    hits = [m.group() for _i, body, _o in blocks for m in TIER_TOKEN_RE.finditer(body)]
    assert hits == [], f"a tier-free emitted template must produce no finding, got {hits}"
