"""Guard: scouting persistence contract (CS-C4) - one write nobody read was the original defect;
persistence WITHOUT read-back is the same defect wearing a disguise. Both halves are mandatory.

Business rule this protects: a scouting/recon phase (intake Phase R, forward-port P0, the
code-review and doc-illustration scopers, the git-rebase intake) writes its findings to a file
under the ISOLATE state root AND the consuming phase READS that file back on resume - never
re-scouting from zero and never relying on the scout's chat-returned text still being in context.
The SSOT for the rule itself is `snippets/scouting-persistence-contract.md`; every consumer is a
POINTER, never a restatement.

Genre A tests (computed/structural - fail for a real code reason) throughout; the one place the
spec's own literal cap VALUE (20 lines / 200 chars) is asserted is explicitly labelled Genre B in
its own docstring (the number itself is a policy choice, not a derivable invariant).
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"

CONTRACT = PLUGIN / "snippets" / "scouting-persistence-contract.md"
STATE_ROOT_SSOT = PLUGIN / "snippets" / "state-root-resolution.md"
INTAKE = PLUGIN / "skills" / "odoo-intake" / "SKILL.md"
FP_DETAIL = PLUGIN / "skills" / "odoo-forward-port" / "references" / "fp-phase-detail.md"
CODE_REVIEW = PLUGIN / "skills" / "odoo-code-review" / "SKILL.md"
DOC_ILLUSTRATION = PLUGIN / "skills" / "odoo-doc-illustration" / "SKILL.md"
RB_DETAIL = PLUGIN / "skills" / "odoo-git-rebase" / "references" / "rb-phase-detail.md"

# The contract's own definitional sentence for clause 1 - must exist in exactly ONE file.
READBACK_DEFINER_PHRASE = (
    "the consuming phase names the artifact by filename and re-reads it from disk"
)


def _tree_texts():
    """Every text artifact under the plugin (md/yaml/json/txt/sh/py) - mirrors
    test_planning_ssot.py's `_tree_texts()` glob exactly."""
    exts = {".md", ".yaml", ".yml", ".json", ".txt", ".sh", ".py"}
    for p in PLUGIN.rglob("*"):
        if p.is_file() and p.suffix in exts:
            yield p, p.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# 1 - every named consumer both WRITES and READS BACK its own artifact.
# --------------------------------------------------------------------------- #

# (file, own artifact filename, WRITE-side regex, READ-BACK-side regex). Both regexes must
# reference the consumer's OWN filename - not a hardcoded shared template - so a consumer that
# merely points at a sibling's artifact does not pass by accident.
_CONSUMERS = [
    (
        "odoo-intake/SKILL.md (findings.md)",
        INTAKE,
        "findings.md",
        re.compile(
            r"write\s+their findings to `<ISOLATE_DIR>/recon/<slug>-<date>/findings\.md`"
        ),
        re.compile(
            r"glob `<ISOLATE_DIR>/recon/\*/findings\.md`.*?READ it and SKIP Phase R's dispatch",
            re.DOTALL,
        ),
    ),
    (
        "fp-phase-detail.md (findings.md)",
        FP_DETAIL,
        "findings.md",
        re.compile(
            r"Write the per-commit EXTRACT tier\s+and the range facts to "
            r"`<ISOLATE_DIR>/recon/<slug>-<date>/findings\.md`"
        ),
        re.compile(r"READ that file back at the\s+start of P1"),
    ),
    (
        "odoo-code-review/SKILL.md (_scope.md)",
        CODE_REVIEW,
        "_scope.md",
        re.compile(r"scoper writes `<ISOLATE_DIR>/reviews/<slug>-<date>/_scope\.md`"),
        re.compile(
            r"Resume: read `_scope\.md` back.*?glob\s*\n?`<ISOLATE_DIR>/reviews/\*/_scope\.md`",
            re.DOTALL,
        ),
    ),
    (
        "odoo-doc-illustration/SKILL.md (_scope.md)",
        DOC_ILLUSTRATION,
        "_scope.md",
        re.compile(
            r"scoper writes `_scope\.md` under\s+`<SHARE_DIR>/documentation/<slug>-<date>/`"
        ),
        re.compile(r"Resume: read `_scope\.md` back, do not re-scope"),
    ),
    (
        "rb-phase-detail.md (intake.md)",
        RB_DETAIL,
        "intake.md",
        re.compile(r"EMIT: intake\.md at <ISOLATE_DIR>/git-rebase/<slug>/intake\.md"),
        re.compile(r"Read `<ISOLATE_DIR>/git-rebase/<slug>/intake\.md` back before enumerating"),
    ),
]


def test_every_named_consumer_writes_and_reads_its_own_artifact():
    """Genre A (structural, per-consumer regex over its OWN artifact filename) - not one
    hardcoded template checked against five files identically."""
    failures = []
    for label, path, filename, write_re, read_re in _CONSUMERS:
        assert path.exists(), f"{label}: file not found at {path}"
        text = path.read_text(encoding="utf-8")
        has_write = bool(write_re.search(text))
        has_read = bool(read_re.search(text))
        if not has_write:
            failures.append(f"{label}: no WRITE instruction naming {filename!r} found")
        if not has_read:
            failures.append(f"{label}: no READ-BACK instruction naming {filename!r} found")
    assert not failures, "Scouting persistence gaps:\n" + "\n".join(failures)


# --------------------------------------------------------------------------- #
# 2 - the read-back rule is defined exactly once (SSOT), everywhere else is a pointer.
# --------------------------------------------------------------------------- #


def test_readback_rule_has_exactly_one_definer():
    """Genre A (count == 1). A future restatement of the definitional sentence anywhere else
    in the plugin tree goes red."""
    definers = [
        str(p.relative_to(PLUGIN)) for p, t in _tree_texts() if READBACK_DEFINER_PHRASE in t
    ]
    assert definers == ["snippets/scouting-persistence-contract.md"], (
        f"The read-back discipline sentence must be defined in exactly ONE place; found in: "
        f"{definers}"
    )


# --------------------------------------------------------------------------- #
# 3 - the new recon/ ISOLATE subpath is declared in the right SSOT table (not a stray mention).
# --------------------------------------------------------------------------- #


def test_new_isolate_subpath_is_declared_in_the_state_root_ssot():
    """Genre A (cross-SSOT, section-scoped). Catches a row added to the wrong table (e.g. the
    Tier-2 SHARE list instead of ISOLATE)."""
    assert STATE_ROOT_SSOT.exists(), "snippets/state-root-resolution.md is missing."
    text = STATE_ROOT_SSOT.read_text(encoding="utf-8")
    m = re.search(
        r"## Tier-2 ISOLATE list.*?(?=\n## )", text, re.DOTALL,
    )
    assert m, "Could not locate the '## Tier-2 ISOLATE list' section."
    section = m.group(0)
    assert "recon/<slug>-<date>/" in section, (
        "The literal `recon/<slug>-<date>/` subpath must appear inside the Tier-2 ISOLATE list "
        "section of state-root-resolution.md, not merely somewhere in the file."
    )


# --------------------------------------------------------------------------- #
# 4 - the contract declares a numeric cap and a fixed four-field record shape.
# --------------------------------------------------------------------------- #


def test_contract_declares_a_numeric_cap_and_a_fixed_key_set():
    """Genre A for structure (a field added/dropped from the record shape goes red). Genre B
    for the cap VALUE itself: '20 finding lines' / '200 characters' are a policy choice made by
    this contract, not a derivable invariant - only the PRESENCE of a digit-bearing cap statement
    is asserted, never a specific number, so a future deliberate cap change does not spuriously
    fail this test.
    """
    assert CONTRACT.exists(), "snippets/scouting-persistence-contract.md (the new SSOT) is missing."
    text = CONTRACT.read_text(encoding="utf-8")

    # Genre B: presence of a digit-bearing cap statement (not the specific value).
    cap_match = re.search(r"\bCap:[^.\n]*\d+[^.\n]*\d+", text)
    assert cap_match, (
        "The contract must state a numeric cap (finding-line count AND per-line character count) "
        "so a findings file cannot grow unbounded and poison a later phase's context."
    )

    # Genre A: the record-shape fence has EXACTLY 4 fields, the last one being the fixed
    # `resolved:yes|no` sentinel - a field added or dropped structurally breaks this. A naive
    # `str.split("|")` over-counts because the citation sub-field and the sentinel itself use
    # "|" internally as OR-alternation, not as a field delimiter - so the 4 fields are extracted
    # via a fixed 4-group anchored regex instead (area / finding / citation / resolved), which
    # fails to match at all if a field is inserted, dropped, or reordered.
    fence_match = re.search(r"```\n(- <area> \|.*?)\n```", text, re.DOTALL)
    assert fence_match, "Could not locate the record-shape code fence."
    record_line = fence_match.group(1)
    field_pattern = re.compile(
        r"^- (?P<area><[^|<>]*>) \| (?P<finding><[^|<>]*>) \| "
        r"(?P<citation><citation:.*?>) \| (?P<resolved>resolved:yes\|no)$"
    )
    field_match = field_pattern.match(record_line)
    assert field_match, (
        f"Record shape must have exactly 4 fields (area, finding, citation, resolved) in that "
        f"order, with 'resolved:yes|no' as the fixed final sentinel; got: {record_line!r}"
    )
    assert len(field_match.groupdict()) == 4


# --------------------------------------------------------------------------- #
# 5 - Phase R's persist step is threaded BEFORE Phase P can serialize the plan.
# --------------------------------------------------------------------------- #


def test_phase_r_write_precedes_phase_p_serialization():
    """Genre A (order). If 'Persist before you propose' were ever moved after '## Plan Mode',
    the recon pointer could be threaded into a run-DAG node before the file backing it exists."""
    text = INTAKE.read_text(encoding="utf-8")
    write_pos = text.find("Persist before you propose")
    plan_mode_pos = text.find("## Plan Mode")
    assert write_pos != -1, "odoo-intake/SKILL.md must contain the 'Persist before you propose' step."
    assert plan_mode_pos != -1, "odoo-intake/SKILL.md must contain a '## Plan Mode' section."
    assert write_pos < plan_mode_pos, (
        "Phase R's persist-before-propose instruction must appear BEFORE '## Plan Mode' in "
        "odoo-intake/SKILL.md - the recon findings file must exist before any node pointing at "
        "it can be serialized."
    )
