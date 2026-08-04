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
# 1 - every scouting consumer both WRITES and READS BACK its own artifact.
# --------------------------------------------------------------------------- #

# WIDENING NOTE (was a hardcoded 5-file Python allowlist - `_CONSUMERS`, a (file, artifact,
# write_re, read_re) tuple list keyed by filename). An allowlist goes green while every phrasing
# outside it walks past unseen, and grows stale as new consumers are added without anyone
# remembering to add a 6th tuple - measured concretely: a class sweep found `odoo-debug/SKILL.md`
# already implementing this exact pattern (Phase 1's Write-constrained scout) with NOTHING in this
# test noticing its absence, because the check never looked past its 5 named files. Replaced with
# a whole-tree, structural-marker scan: no filename is special-cased anywhere below.
#
# Site selection (STRUCTURAL, not filename-based): a file OPTS IN to Clause 1's write+read-back
# obligation the moment it cites `scouting-persistence-contract.md` for anything other than
# Clause 3 ALONE. Clause 3 alone (no Clause 1/2 citation) is the one legitimate structural
# exclusion - it marks a Write-constrained-scout parent-transcription site whose OWN artifact is
# consumed same-phase (measured: `upg-phase-detail.md`'s P1a/P1d graph.md /
# transitive-symbol-survey.md are fed straight into the SAME phase's next step, never re-read on a
# later resume) - Clause 3 is silent on independent resume-read, that is Clause 1's rule. A file
# that cites clause 1 or clause 2 (with or without also citing clause 3), or cites the contract
# with no clause number at all (`fp-phase-detail.md`'s plain pointer), IS in scope.
#
# Cue detection (GENERIC structural regexes, reused across every in-scope file - not one
# hand-written regex per consumer): a WRITE cue is a write-flavored verb (writes/EMIT/persists/
# transcribes - the exact vocabulary this contract's own Clause 2/3 text uses) followed by a
# `*.md` artifact reference; a READ-BACK cue is read/resume followed by "back" or "skip" (the
# vocabulary every existing consumer's own resume/staleness prose already uses:
# "READ it and SKIP...", "READ that file back...", "Resume: read...back", "Read...back...").
#
# Measured (current tree, whole-tree scan): 5 files select in - `odoo-intake/SKILL.md`,
# `odoo-code-review/SKILL.md`, `odoo-doc-illustration/SKILL.md`,
# `odoo-forward-port/references/fp-phase-detail.md`, `odoo-git-rebase/references/rb-phase-detail.md`
# - the SAME 5 the old hardcoded list named (proving the structural redesign did not silently drop
# a known-good site) - PLUS `odoo-debug/SKILL.md` once its Phase 1 write+read-back paragraph is
# added (this fix's P1 change) - 0 offenders in all 6. `upg-phase-detail.md` (Clause-3-only citer)
# correctly selects OUT.
CONTRACT_CITE_RE = re.compile(r"scouting-persistence-contract\.md", re.IGNORECASE)
CLAUSE_MENTION_RE = re.compile(r"clause\s+([123])\b", re.IGNORECASE)
WRITE_CUE_RE = re.compile(
    r"\b(?:writes?|emit:?|persists?|transcribes?)\b.{0,120}?\.md\b", re.IGNORECASE | re.DOTALL
)
READ_CUE_RE = re.compile(
    r"\b(?:read|resume)\b.{0,120}?\b(?:back|skip)\b", re.IGNORECASE | re.DOTALL
)


def _tree_md_files():
    """Every skill/agent prose file - mirrors test_recon_tier_policy.py's `_tree_md_files()`
    exactly (same whole-tree scope: skills/ + agents/, not docs/reference mirrors)."""
    for sub in ("skills", "agents"):
        base = PLUGIN / sub
        if base.is_dir():
            yield from base.rglob("*.md")


def _is_write_readback_consumer(text: str) -> bool:
    """STRUCTURAL site selection - see the widening note above `CONTRACT_CITE_RE`. A file is in
    scope for the write+read-back check iff it cites the contract for anything beyond Clause 3
    alone."""
    if not CONTRACT_CITE_RE.search(text):
        return False
    clauses = {m.group(1) for m in CLAUSE_MENTION_RE.finditer(text)}
    return clauses != {"3"}


def test_every_scouting_consumer_writes_and_reads_its_own_artifact():
    """Genre A (whole-tree, no allowlist - see the widening note above `CONTRACT_CITE_RE` for the
    measured before/after and the structural site-selection/cue-detection rules).

    Fails if: a file that cites the contract for Clause 1 or Clause 2 (the write+read-back
    obligation) lacks either a WRITE cue or a READ-BACK cue anywhere in its own text - including a
    brand-new consumer nobody has written yet, which is the entire point of a citation-driven scan
    rather than a 5-file Python list.
    """
    failures = []
    for path in _tree_md_files():
        text = path.read_text(encoding="utf-8")
        if not _is_write_readback_consumer(text):
            continue
        relpath = str(path.relative_to(PLUGIN))
        has_write = bool(WRITE_CUE_RE.search(text))
        has_read = bool(READ_CUE_RE.search(text))
        if not has_write:
            failures.append(
                f"{relpath}: cites scouting-persistence-contract.md (clause 1/2) but no WRITE "
                "cue (writes/EMIT/persists/transcribes ... *.md) found"
            )
        if not has_read:
            failures.append(
                f"{relpath}: cites scouting-persistence-contract.md (clause 1/2) but no "
                "READ-BACK cue (read/resume ... back/skip) found"
            )
    assert not failures, "Scouting persistence gaps:\n" + "\n".join(failures)


def test_evasive_worker_phrasing_construct_has_neither_write_nor_read_cue():
    """Genre A (regression/construct test - proves the GENERIC structural cues above, not a copy
    of them, correctly reject a real evasive phrasing this guard's predecessor could not even see
    because it only ever looked at 5 hardcoded filenames).

    Verified evasive construct (from the same lane finding `test_widened_detector_catches_
    evasive_worker_phrasing` in test_recon_tier_policy.py exercises for the tier-check guard):
    a "Discovery sweep" that dispatches an anonymous worker agent and explicitly folds distinct
    scouts' returns into one summary - the exact parent-authored-digest failure Clause 3 bans, and
    it neither writes a `*.md` artifact nor reads one back.

    Fails if: `WRITE_CUE_RE` or `READ_CUE_RE` starts matching this construct - meaning the generic
    cue detection has become loose enough to rubber-stamp a site that never persists or reads back
    anything.
    """
    construct = (
        "### Discovery sweep\n"
        "Spin up one worker agent per candidate area to map current usage. Each worker keeps its\n"
        "findings in its reply; fold the replies together into one summary before continuing.\n"
    )
    assert not WRITE_CUE_RE.search(construct), (
        "the evasive construct never writes a *.md artifact - WRITE_CUE_RE must NOT match it."
    )
    assert not READ_CUE_RE.search(construct), (
        "the evasive construct never reads anything back - READ_CUE_RE must NOT match it."
    )


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


# --------------------------------------------------------------------------- #
# 6 (PR #189 final-batch review finding F3, WRONG): the staleness check reads a
# field the writer never wrote. odoo-intake/SKILL.md:60 told the reader to check
# "the recorded target ref" but the four-field findings.md schema had no ref
# field at all - the staleness branch was unexecutable. Fix: the contract's
# Clause 2 schema gains a `target_ref:` header line, and both the writer
# (odoo-intake Phase R) and the reader (odoo-intake Phase 0 3a) name that exact
# field. The four-field record-shape fence (test 4 above) is untouched by this -
# the header lives OUTSIDE that fence, so it does not count against the cap.
# --------------------------------------------------------------------------- #


def test_contract_declares_a_target_ref_header_outside_the_finding_line_cap():
    """Genre A (structural). The contract must declare a `target_ref:` header line as its
    own distinct fenced example, separate from the four-field finding-line fence, and must
    explicitly state the header does not count against the 20-finding-line cap.

    Fails if: no `target_ref:` header is declared, or the cap paragraph loses the explicit
    carve-out stating the header does not count against it (in which case the size-cap claim
    from test 4 would be silently violated the moment a header field exists).
    """
    text = CONTRACT.read_text(encoding="utf-8")
    header_fence = re.search(r"```\ntarget_ref: <ref>\n```", text)
    assert header_fence, (
        "scouting-persistence-contract.md must declare a distinct `target_ref: <ref>` header "
        "fence - the staleness-check anchor the four-field record shape has no room for."
    )
    assert re.search(r"NOT.{0,40}finding lines?", text, re.DOTALL) or re.search(
        r"header lines?.{0,60}(NOT|not) finding lines", text
    ), (
        "scouting-persistence-contract.md must explicitly state the target_ref/stale header "
        "line(s) are NOT finding lines and do not count against the 20-line cap."
    )
    # test 4's own fence-locator regex must still find the ORIGINAL 4-field fence unchanged.
    fence_match = re.search(r"```\n(- <area> \|.*?)\n```", text, re.DOTALL)
    assert fence_match, "the four-field record-shape fence must remain intact and locatable."


def test_staleness_clause_names_target_ref_concretely():
    """Genre A. Clause 1's staleness rule must name `target_ref:` concretely (not just the
    vague prose 'recorded target ref') so it is grounded in an actual schema field.

    Fails if: Clause 1 still says only "the recorded target ref/branch" with no pointer to
    where that field is actually declared.
    """
    text = CONTRACT.read_text(encoding="utf-8")
    clause1 = re.search(r"## Clause 1.*?(?=\n## )", text, re.DOTALL).group(0)
    assert "target_ref" in clause1, (
        "Clause 1's staleness bullet must reference the concrete `target_ref` field name, not "
        "just vague prose about a 'recorded target ref'."
    )


def test_intake_write_and_read_both_name_target_ref():
    """Genre A. odoo-intake/SKILL.md must both WRITE a `target_ref:` header (Phase R persist
    step) and READ it back (Phase 0 3a resume check) - using the identical field name, so the
    staleness branch the reader is told to execute is actually backed by something the writer
    produces.

    Fails if: either the write step or the read-back step drops the `target_ref` field name,
    reintroducing the write/read mismatch (F3).
    """
    text = INTAKE.read_text(encoding="utf-8")
    write_section = text[text.index("Persist before you propose"):text.index("**Inventory discovery")]
    assert "target_ref" in write_section, (
        "odoo-intake/SKILL.md: the 'Persist before you propose' write step must name "
        "`target_ref` - the field the Phase 0 3a staleness read-back depends on."
    )
    phase0_start = text.index("**3a. Read existing context")
    phase0_section = text[phase0_start:phase0_start + 1200]
    assert "target_ref" in phase0_section, (
        "odoo-intake/SKILL.md Phase 0 3a: the existing-recon staleness check must name "
        "`target_ref` concretely, not just 'the recorded target ref'."
    )


def test_forward_port_p0_writer_inherits_schema_by_pointer_not_restatement():
    """Genre A. forward-port P0 must still write findings.md purely BY POINTER to the
    contract (never restating the four-field-only shape), so it automatically inherits the
    new `target_ref` header without needing its own edit - proving the SSOT actually is one
    place.

    Fails if: fp-phase-detail.md hardcodes its own record-shape fence (a restatement that
    would silently diverge from the contract's schema instead of inheriting it).
    """
    text = FP_DETAIL.read_text(encoding="utf-8")
    assert "scouting-persistence-contract.md" in text, (
        "fp-phase-detail.md must point at scouting-persistence-contract.md rather than "
        "restating the findings.md schema inline."
    )
    assert "<area> |" not in text, (
        "fp-phase-detail.md must NOT restate the four-field record-shape fence inline - it "
        "must inherit the schema from the contract by pointer only."
    )


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
