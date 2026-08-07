"""Behavioral guard for odoo-modules-upgrade's version-anchored deferred-work reconciliation.

Business rule: during a module upgrade to a TARGET Odoo major series X, custom-module
TODO/FIXME/XXX/HACK debt markers that carry a version anchor <= X (including an already-passed
lower version) have come DUE and must be executed NOW, in THIS upgrade, instead of slipping past
again. A marker anchored to a HIGHER future version stays DEFERRED (untouched); a marker with no
parseable version anchor is never forced into scope - it is recorded and flagged for the human.
DUE items are not a side note: they become real upgrade work-items, folded into the SAME
implement (odoo-coding) -> P4b review -> P5 test path as the rest of the cluster.

The scan itself is context-heavy (it sweeps every in-scope file of a module) and MUST NOT be run
by the orchestrating/main context. odoo-modules-upgrade already dispatches `odoo-diff-comparator`
per module in P2 (dep order, parallel within a wave) to read that module's FULL source for the
core-absorption comparison - the reconciliation reuses that SAME delegated read instead of adding
a new phase/agent/dispatch, and returns a compact structured `deferred_work` block, never raw grep
output the orchestrator would have to sift through itself.

Each test below fails for exactly one reason: the corresponding piece of the rule was removed,
reworded past detection, or the delegation was lost (e.g. rewritten as an orchestrator-run grep).

Files under test (both under plugins/odoo-ai-agents/):
  - skills/odoo-modules-upgrade/SKILL.md
  - skills/odoo-modules-upgrade/references/upg-phase-detail.md

Run with: python3 -m pytest tests/test_upg_deferred_work_reconciliation.py -v
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
SKILL_MD = PLUGIN / "skills" / "odoo-modules-upgrade" / "SKILL.md"
PHASE_DETAIL = PLUGIN / "skills" / "odoo-modules-upgrade" / "references" / "upg-phase-detail.md"


def _body(text: str) -> str:
    """Return the content after the closing --- of the frontmatter block."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if i > 0 and line.strip() == "---":
            return "\n".join(lines[i + 1:])
    return text


def _skill_body() -> str:
    assert SKILL_MD.exists(), f"skills/odoo-modules-upgrade/SKILL.md not found at {SKILL_MD}"
    return _body(SKILL_MD.read_text(encoding="utf-8"))


def _phase_detail_text() -> str:
    assert PHASE_DETAIL.exists(), f"upg-phase-detail.md not found at {PHASE_DETAIL}"
    return PHASE_DETAIL.read_text(encoding="utf-8")


def _paragraphs(text: str) -> list[str]:
    """Split markdown text on blank lines - the natural unit a rule + its qualifiers live in."""
    return re.split(r"\n\s*\n", text)


def _norm(text: str) -> str:
    """Collapse all whitespace (incl. line-wrap newlines) to single spaces.

    Markdown prose in these skill files hard-wraps at ~90-100 chars, so a literal multi-word
    phrase can legitimately split across a line break. Plain `in` checks on raw text are brittle
    against that reflow; normalize before any literal multi-word substring assertion. Also strips
    a leading blockquote marker (`>` / `> `) from each line first - a blockquote continuation line
    (as in upg-conventions.md's gating banner) would otherwise leave a literal `>` glued into the
    middle of a collapsed phrase, defeating the very substring check this helper exists to protect.
    """
    text = re.sub(r"(?m)^>\s?", "", text)
    return re.sub(r"\s+", " ", text)


# ---------------------------------------------------------------------------
# Rule 1: the full case-insensitive marker family.
# If this is trimmed to just "TODO", FIXME/XXX/HACK technical debt keeps
# silently slipping past every upgrade unreconciled.
# ---------------------------------------------------------------------------

def test_marker_set_present_in_skill_and_phase_detail():
    """SKILL.md and phase-detail.md must both name the full marker family."""
    for label, text in (("SKILL.md", _skill_body()), ("upg-phase-detail.md", _phase_detail_text())):
        for token in ("`TODO`", "`FIXME`", "`XXX`", "`HACK`", "`@todo`"):
            assert token in text, (
                f"{label}: marker set is missing {token!r}. The version-anchored "
                "deferred-work scan must cover the full TODO/todo/Todo/ToDo/@todo/"
                "FIXME/XXX/HACK family, not just TODO."
            )


# ---------------------------------------------------------------------------
# Rule 2: DUE vs DEFERRED vs UNANCHORED classification.
# anchored version <= target (incl. already-passed/overdue) -> DUE;
# anchored version > target -> DEFERRED (left untouched);
# no parseable anchor -> UNANCHORED (recorded + flagged for human, never
# silently forced into DUE, never silently dropped).
# ---------------------------------------------------------------------------

def test_due_deferred_unanchored_classification_present():
    """A single paragraph must classify markers into DUE / DEFERRED / UNANCHORED together.

    Fails if: the three-way classification is deleted, or split apart so no single rule
    statement covers the due-vs-deferred-vs-unanchored decision, or the anti-silent-absorb/
    drop guarantee for unanchored markers is dropped.
    """
    body = _skill_body()
    paras = [p for p in _paragraphs(body) if "DUE" in p and "DEFERRED" in p and "UNANCHORED" in p]
    assert paras, (
        "skills/odoo-modules-upgrade/SKILL.md: no paragraph classifies markers into "
        "DUE / DEFERRED / UNANCHORED together - the version-anchored deferred-work "
        "classification rule is missing or was split apart (this assertion would pass "
        "vacuously if the rule were deleted piecemeal, so it requires all three labels "
        "co-occurring in one paragraph)."
    )
    para = _norm(paras[0])
    assert re.search(r"(?i)already-passed", para), (
        "DUE must explicitly include an already-passed (overdue) LOWER version, not only an "
        "exact match to the target series - otherwise debt anchored two upgrades ago never "
        "comes due."
    )
    assert re.search(r"(?i)higher", para), (
        "DEFERRED must be anchored to reading a HIGHER future version than target - without "
        "this qualifier, DEFERRED could be misread as covering everything not-yet-due."
    )
    assert "no parseable version anchor" in para, (
        "UNANCHORED must be triggered specifically by 'no parseable version anchor'."
    )
    assert re.search(r"(?i)flag.{0,60}human|human.{0,60}flag", para), (
        "An UNANCHORED marker must be flagged for the human, not silently resolved."
    )
    assert re.search(r"(?i)never silently", para), (
        "Must forbid silently absorbing an unanchored marker into DUE and forbid silently "
        "dropping it - both failure modes are distinct and both must be named."
    )


# ---------------------------------------------------------------------------
# Rule 3: DUE items become REAL work-items, wired into the SAME
# implement -> P4b review -> P5 test path - not a side note.
# ---------------------------------------------------------------------------

def test_due_items_wired_into_implement_review_test_path():
    """DUE items must flow through the upgrade's real work-item pipeline (P4 -> P4b -> P5).

    Fails if: DUE items are only recorded/logged somewhere but never actually dispatched to
    odoo-coding, or the review (P4b) / test (P5) legs of that path are dropped, turning
    "reconciliation" into an inert side-note nobody implements.
    """
    body = _skill_body()
    due_work_item_paras = [
        _norm(p) for p in _paragraphs(body)
        if "DUE" in p and re.search(r"(?i)work-items?", p)
    ]
    assert due_work_item_paras, (
        "skills/odoo-modules-upgrade/SKILL.md: no paragraph wires DUE deferred-work items "
        "into the upgrade's work-item set."
    )
    full_path_paras = [p for p in due_work_item_paras if "P4b" in p and "P5" in p]
    assert full_path_paras, (
        "skills/odoo-modules-upgrade/SKILL.md: found a DUE/work-item paragraph but none "
        "references the full implement -> P4b review -> P5 test path:\n"
        + "\n---\n".join(due_work_item_paras)
    )
    assert any("not a side note" in p for p in full_path_paras), (
        "SKILL.md must explicitly state DUE items are 'not a side note' - the phrase that "
        "distinguishes 'executed now' from merely recording/logging the marker."
    )


# ---------------------------------------------------------------------------
# Rule 4: delegation. The scan reuses the ALREADY-dispatched per-module reader
# (odoo-diff-comparator, P2) - it is never a fresh grep the orchestrating/main
# context runs itself, and no new phase/agent was invented for it.
# ---------------------------------------------------------------------------

def test_scan_delegated_to_existing_per_module_reader_not_main_context():
    """The marker scan must be delegated to the existing per-module dispatch, not main context.

    Fails if: the SKILL is rewritten to describe the scan as something the orchestrator itself
    greps (main-context pollution with a cluster-wide sweep), or as a brand-new stand-alone
    phase/agent instead of reusing the odoo-diff-comparator read P2 already performs.
    """
    body = _skill_body()
    norm_body = _norm(body)
    assert "same delegated per-module read" in norm_body, (
        "skills/odoo-modules-upgrade/SKILL.md: the reconciliation must be framed as reusing "
        "the SAME delegated per-module read already used for P2 core-absorption comparison, "
        "not introduced as a new phase or a new agent dispatch."
    )
    assert re.search(r"(?i)odoo-diff-comparator.{0,300}(full source|same read)", norm_body), (
        "SKILL.md must attribute the scan to the odoo-diff-comparator dispatch already "
        "running per module in P2."
    )
    assert "never greps module source itself" in norm_body, (
        "SKILL.md must state the orchestrator never greps module source itself for this "
        "reconciliation - without this the scan could be re-described as an orchestrator/main "
        "context grep, defeating the point of delegating it to a sub-agent's own context."
    )
    assert "no separate scan or dispatch" in norm_body, (
        "SKILL.md must make explicit that no new agent/dispatch/phase was invented for this "
        "scan - it rides the existing P2 per-module dispatch."
    )


# ---------------------------------------------------------------------------
# Rule 5: the per-module dispatch-brief mechanics (marker regex source, file
# types, classification, structured output) live in the reference file the
# SKILL body points to, and the delegated agent actually returns a compact
# `deferred_work` block (not raw grep output) that P4 consumes.
# ---------------------------------------------------------------------------

def test_phase_detail_carries_scan_mechanics_and_structured_output():
    """upg-phase-detail.md must carry the per-module scan brief + deferred_work output schema."""
    detail = _norm(_phase_detail_text())
    assert "deferred_work" in detail, (
        "upg-phase-detail.md: the odoo-diff-comparator dispatch brief and the "
        "absorption/<module>.md output schema must carry a deferred_work block that P4 "
        "consumes as its work-item source."
    )
    assert re.search(r"(?i)version anchor", detail), (
        "upg-phase-detail.md must describe parsing a VERSION ANCHOR from the marker text."
    )
    assert re.search(r"(?i)same read as step 2|no separate dispatch", detail), (
        "upg-phase-detail.md must state the scan happens in the SAME read as the existing "
        "per-module comparator step, not a separate dispatch."
    )
    assert "0b." in detail and re.search(r"(?i)DUE VERSION-ANCHORED DEFERRED WORK", detail), (
        "upg-phase-detail.md P4 dispatch brief must carry an explicit instruction step that "
        "implements DUE deferred-work items now (the wiring point into odoo-coding)."
    )


# ---------------------------------------------------------------------------
# Rule 6 (CS-C7): Convention 0 - "a major-series module upgrade is a CODE
# upgrade, not a data migration" must be declared in upg-conventions.md AND
# named in the file's own CORE carve-out line. Without the carve-out naming
# it, the whole section is silently scoped to Viindoo Standard/Internal
# distributions only and never fires for a plain Odoo CE/EE (or any other
# non-Viindoo) upgrade - which is exactly the general case the rule exists
# to cover.
# ---------------------------------------------------------------------------

UPG_CONVENTIONS = PLUGIN / "snippets" / "upg-conventions.md"
BACKEND_CODER = PLUGIN / "agents" / "odoo-backend-coder.md"
FRONTEND_CODER = PLUGIN / "agents" / "odoo-frontend-coder.md"


def _upg_conventions_text() -> str:
    assert UPG_CONVENTIONS.exists(), f"snippets/upg-conventions.md not found at {UPG_CONVENTIONS}"
    return UPG_CONVENTIONS.read_text(encoding="utf-8")


def test_convention_zero_is_core_and_not_viindoo_gated():
    """Convention 0 must exist, be named in the CORE carve-out, and be marked CORE.

    Fails if: Convention 0 is missing entirely, or the CORE-carve-out paragraph (the
    line that exempts Conv-3/Conv-4 from the Viindoo-only gate at the top of the file)
    does not also name Conv-0, or Convention 0's own body omits the same
    'CORE rule - applies to all distributions' marker Convention 3 and 4 already carry.
    """
    text = _upg_conventions_text()
    assert "## Convention 0" in text, (
        "snippets/upg-conventions.md must contain a '## Convention 0' heading - the "
        "CODE-upgrade-not-data-migration rule."
    )
    carve_out_paras = [p for p in _paragraphs(text) if "CORE Odoo rules" in p]
    assert carve_out_paras, (
        "snippets/upg-conventions.md: no paragraph states the CORE-rules carve-out "
        "that exempts core conventions from the Viindoo-only gate declared at the top "
        "of the file."
    )
    assert "Conv-0" in carve_out_paras[0], (
        "snippets/upg-conventions.md: the CORE carve-out line must name 'Conv-0' - "
        "without it, Convention 0 is silently gated to Viindoo distributions only and "
        "never reaches a plain (non-Viindoo) upgrade."
    )
    convention_0_body = text[text.index("## Convention 0"):]
    assert "CORE rule - applies to all distributions" in convention_0_body, (
        "snippets/upg-conventions.md: Convention 0's own body must carry the same "
        "'CORE rule - applies to all distributions' marker Convention 3 and 4 use."
    )


def _single_line_starting_with(text: str, prefix: str, label: str) -> str:
    """Return the exactly-one line in text that starts with prefix (after stripping)."""
    lines = [line for line in text.splitlines() if line.strip().startswith(prefix)]
    assert lines, f"{label}: no line starts with {prefix!r}"
    assert len(lines) == 1, (
        f"{label}: expected exactly ONE line starting with {prefix!r}, found {len(lines)}"
    )
    return lines[0]


def test_coder_agents_carry_a_byte_identical_modules_upgrade_disposition():
    """Both coder agents must carry the SAME modules-upgrade adapt disposition line.

    The line sits adjacent to the existing 'Forward-port adapt' line, which states the
    OPPOSITE disposition (preserve original behavior faithfully). If the backend and
    frontend copies drifted even by one character, a coder could silently inherit the
    wrong disposition for an upgrade brief. Fails if either line is missing, or if the
    two agents' copies differ at all.
    """
    backend_text = BACKEND_CODER.read_text(encoding="utf-8")
    frontend_text = FRONTEND_CODER.read_text(encoding="utf-8")
    line_a = _single_line_starting_with(
        backend_text, "**Modules-upgrade adapt", "odoo-backend-coder.md"
    )
    line_b = _single_line_starting_with(
        frontend_text, "**Modules-upgrade adapt", "odoo-frontend-coder.md"
    )
    assert line_a == line_b, (
        "odoo-backend-coder.md and odoo-frontend-coder.md 'Modules-upgrade adapt' lines "
        "must be byte-identical - they drifted:\n"
        f"backend:  {line_a!r}\n"
        f"frontend: {line_b!r}"
    )


def test_vendor_currency_trigger_is_decidable_and_actionable():
    """Convention 0(c)'s vendor-currency pass must be a decidable trigger + action rule.

    Fails if: the trigger predicate loses either signal (`external_dependencies` or
    `sys.stdlib_module_names`), the numeric cap on third-party packages is dropped, any
    of the six enumerated `vendor_api_checked:` outcomes goes missing (the action half -
    `adapted-to` / `deferred` - is what stops (c) degenerating into a mere record with
    no decision), or a judgment-shaped phrase ('if it seems', 'when appropriate', 'judge
    whether') creeps back in, re-introducing an undecidable predicate.
    """
    text = _upg_conventions_text()
    body = text[text.index("## Convention 0"):]
    norm = _norm(body)

    assert "external_dependencies" in norm, "Convention 0(c) must name `external_dependencies`"
    assert "sys.stdlib_module_names" in norm, "Convention 0(c) must name `sys.stdlib_module_names`"
    assert re.search(r"(?i)\bthree\b.{0,20}packages", norm), (
        "Convention 0(c) must declare a NUMERIC cap (THREE packages) on third-party "
        "packages checked per module"
    )

    for outcome in ("adapted-to", "(already current)", "over-cap", "not-triggered", "unreachable", "deferred"):
        assert outcome in norm, (
            f"Convention 0(c) must enumerate the `vendor_api_checked:` outcome marker {outcome!r}"
        )

    for phrase in ("if it seems", "when appropriate", "judge whether"):
        assert phrase not in norm.lower(), (
            f"Convention 0(c) must not contain the judgment-shaped phrase {phrase!r} - the "
            "trigger must stay decidable, not softened back into prose"
        )


# ---------------------------------------------------------------------------
# Runtime-reachability fixes (PR #189 review findings F1, F2, F5/C2, F6):
# Convention 0 was declared but never actually became reachable at the moment
# it must fire - the P2-phase aside that pointed at it was two phases removed
# from the actual P4 dispatch brief template, the file's own gating banner
# contradicted its "reachable for ALL profiles" claim, the coder's disposition
# selector had no guaranteed marker in a template-built brief, and P5's
# create-instance dispatch never established the addons path P5.7 assumes.
# ---------------------------------------------------------------------------

def _fenced_block(text: str, anchor: str) -> str:
    """Return the first ``` … ``` fenced block that starts at or after `anchor`."""
    start = text.index(anchor)
    fence_start = text.index("```", start)
    fence_end = text.index("```", fence_start + 3)
    return text[fence_start:fence_end]


def _p4_brief_block() -> str:
    """The literal '### odoo-coding dispatch brief' template P4 dispatches from - the
    ONLY concrete brief template odoo-modules-upgrade gives a real P4 dispatch."""
    return _fenced_block(_phase_detail_text(), "### odoo-coding dispatch brief")


def _p5_step1_block() -> str:
    """The literal 'Step 1 - create instance' fenced block P5 dispatches from."""
    return _fenced_block(_phase_detail_text(), "Step 1 - create instance")


def test_p4_brief_template_cites_convention_zero_by_literal_path():
    """The P4 dispatch brief TEMPLATE (not a P2-phase aside two phases upstream) must
    literally cite upg-conventions.md, so (a) a coder dispatched from a REAL P4 brief
    learns Convention 0 exists, and (b) the brief guarantees the exact literal string
    odoo-backend-coder.md / odoo-frontend-coder.md key their 'Modules-upgrade adapt'
    disposition trigger on ('your brief references ...upg-conventions.md').

    Base commit: the template's INPUTS list names absorption verdict, deferred-work,
    blockers, deprecation fix list, breaking-change catalog, version delta, and design
    doc - never upg-conventions.md or 'Convention 0'. RED on that text.
    """
    block = _norm(_p4_brief_block())
    assert "${CLAUDE_PLUGIN_ROOT}/snippets/upg-conventions.md" in block, (
        "upg-phase-detail.md's P4 '### odoo-coding dispatch brief' template must literally "
        "contain '${CLAUDE_PLUGIN_ROOT}/snippets/upg-conventions.md' - the exact string "
        "odoo-backend-coder.md / odoo-frontend-coder.md key their 'Modules-upgrade adapt' "
        "disposition trigger on."
    )
    assert "Convention 0" in block, (
        "upg-phase-detail.md's P4 brief template must name 'Convention 0' explicitly - a "
        "coder must learn the CONVENTION exists, not merely see an unlabeled file path."
    )


def test_p4_brief_template_wires_vendor_currency_pass_as_an_instruction_step():
    """Convention 0(c)'s vendor-currency pass must be wired as an actionable INSTRUCTION
    step in the P4 brief template (not merely mentioned in passing in INPUTS), so it
    actually fires for the KEEP/REWRITE/MERGE/SPLIT branch that writes code.

    Base commit: no instruction step references the vendor-currency pass at all. RED.
    """
    block = _norm(_p4_brief_block())
    assert "0c." in block, (
        "upg-phase-detail.md's P4 brief template must carry a numbered instruction step "
        "(0c) wiring Convention 0(c)'s vendor-currency pass into the KEEP/REWRITE/MERGE/"
        "SPLIT instruction list - the branch that actually adapts code."
    )
    assert re.search(r"(?i)vendor.currency", block), (
        "upg-phase-detail.md's P4 brief template step 0c must name the vendor-currency pass."
    )


# --------------------------------------------------------------------------- #
# PR #189 final-batch review (FIX 4): Convention 0(c) tells the agent to
# RECORD a `vendor_api_checked:` value with one of six enumerated forms, but no
# P2/P4/P5 output schema reserved a field for it - the agent was instructed to
# write into a structure with nowhere to land the value. Fix: the P2 output
# FORMAT (`absorption/<module>.md`) reserves a `vendor_api_checked:` slot, and
# the P4 dispatch brief's step 0c (the actual write instruction) names that
# SAME field + file as its destination.
# --------------------------------------------------------------------------- #


def test_absorption_output_format_reserves_a_vendor_api_checked_slot():
    """Genre A (structural). The P2 output FORMAT block (absorption/<module>.md schema) must
    declare a `vendor_api_checked:` field, adjacent to the other per-module verdict fields
    (data_at_risk, deferred_work) it already reserves slots for.

    Fails if: no `vendor_api_checked:` key exists in the FORMAT block, i.e. Convention 0(c)'s
    record instruction has nowhere to land.
    """
    detail = _phase_detail_text()
    fmt_start = detail.index("OUTPUT: write to absorption/<module>.md")
    fmt_end = detail.index("### P2 - odoo-gap-analysis dispatch")
    fmt_block = detail[fmt_start:fmt_end]
    assert re.search(r"^\s*vendor_api_checked:", fmt_block, re.MULTILINE), (
        "upg-phase-detail.md: the P2 output FORMAT block (absorption/<module>.md schema) must "
        "reserve a `vendor_api_checked:` field - without it, Convention 0(c)'s vendor-currency "
        "record has no schema slot to land in."
    )


def test_p4_step_0c_names_the_same_field_and_file_as_the_schema():
    """Genre A. The P4 dispatch brief's step 0c (the ACTUAL write instruction a coder receives)
    must name the identical `vendor_api_checked:` field AND the identical destination file
    (`absorption/<module>.md`) the P2 output FORMAT reserves the slot in - proving the writer
    and the schema agree on where the value lands.

    Fails if: step 0c records the vendor-currency finding without naming a destination field/
    file, or names a different field/file than the schema declares.
    """
    block = _norm(_p4_brief_block())
    assert "0c." in block, "P4 brief template must retain step 0c (vendor-currency pass)."
    step_0c_pos = block.index("0c.")
    next_step_pos = block.find("\n  1.", step_0c_pos)
    if next_step_pos == -1:
        next_step_pos = len(block)
    step_0c_text = block[step_0c_pos:next_step_pos]
    assert "vendor_api_checked" in step_0c_text, (
        "P4 brief template step 0c must name the `vendor_api_checked:` field explicitly as "
        "its write destination."
    )
    assert "absorption/<module>.md" in step_0c_text, (
        "P4 brief template step 0c must name `absorption/<module>.md` as the file "
        "`vendor_api_checked:` is persisted into - the SAME file the P2 output FORMAT reserves "
        "the slot in, and the SAME file P6 presents at the human gate."
    )


def test_convention_0c_points_at_the_reserved_slot_not_just_the_bare_field_name():
    """Genre A. Convention 0(c)'s own text (the canonical definition of the six outcome forms)
    must point at WHERE `vendor_api_checked:` is recorded (the absorption/<module>.md schema),
    not merely name the field with no destination - so a reader of the convention alone (not
    the P4 brief) still learns where the record lands.

    Fails if: Convention 0(c) enumerates the six forms but never names
    `absorption/<module>.md` as the destination.
    """
    text = _upg_conventions_text()
    body = text[text.index("## Convention 0"):]
    assert "absorption/<module>.md" in body, (
        "snippets/upg-conventions.md Convention 0(c) must name `absorption/<module>.md` as the "
        "reserved destination for the `vendor_api_checked:` record."
    )


def test_p5_create_instance_dispatch_names_worktree_path_over_integration_worktree():
    """P5 Step 1 (create instance) must name a WORKTREE_PATH covering the SAME P4
    integration worktree - P5.7 asserts 'its addons path MUST cover WORKTREE_PATH', a
    property the create-instance dispatch never established before this fix. Reuses the
    EXISTING odoo-instance WORKTREE_PATH field + substitution mechanism (no second,
    bespoke addons-path mechanism).

    Base commit: Step 1 carries only operation/series/demo - no WORKTREE_PATH field at
    all. RED.
    """
    block = _norm(_p5_step1_block())
    assert "WORKTREE_PATH" in block, (
        "upg-phase-detail.md's P5 Step 1 create-instance dispatch must name a "
        "WORKTREE_PATH field (the existing odoo-instance mechanism) - without it the "
        "instance's addons path is never established to cover the integration worktree."
    )
    assert "upg-integration" in block, (
        "upg-phase-detail.md's P5 Step 1 WORKTREE_PATH must point at the SAME "
        "'<path>/upg-integration' literal the P4 integration worktree uses - a different "
        "or unspecified path would not satisfy P5.7's coverage requirement."
    )


def test_convention_zero_gate_is_explicitly_scoped_off_convention_zero():
    """The Viindoo-profile gate must name exactly which Convention number(s) it covers, and
    Convention 0 must never fall inside that gated scope - neither DIRECTLY (named by number
    in the gate itself) nor TRANSITIVELY (Convention 0's own body delegates its rule text to
    a convention that IS inside the gated scope, which makes the CORE rule unreachable on a
    non-Viindoo profile even though Convention 0 itself was correctly carved out by name).

    Guards two distinct historical defects:
      1. An UNSCOPED gate ('the rules below ... DO NOT apply these rules') that cannot be
         checked for scope at all, and so silently covers Convention 0 by omission.
      2. A gate that correctly excludes Convention 0 BY NAME, while Convention 0's own body
         delegates its rule (via 'Convention N owns ...') to a convention number that IS
         inside the gated scope - the actual defect this fix corrects: Convention 0(a) says
         'Convention 1 owns the no-bump rule', and Convention 1 sat inside a Viindoo-only
         gate, so a non-Viindoo profile was sent by CORE Convention 0 to Convention 1 for the
         rule text, then told by Convention 1's own gate not to apply it there - unreachable
         by construction.

    Base commit: the gate read 'DO NOT apply Conventions 1-2' while Convention 0(a) still
    delegated to Convention 1 - RED on that combination (case 2 above).
    """
    text = _upg_conventions_text()
    banner_region = text[: text.index("## Convention 1")]
    norm_banner = _norm(banner_region)

    # 1. The DO-NOT-apply clause must name specific Convention number(s), not a blanket
    #    "these rules"/"the rules below" - an unscoped clause can't be checked for scope and
    #    would silently cover Convention 0 by omission.
    do_not_match = re.search(
        r"DO NOT apply Convention[s]?\s+([0-9]+(?:\s*(?:,|-|and)\s*[0-9]+)*)", norm_banner
    )
    assert do_not_match, (
        "snippets/upg-conventions.md: the gating banner's DO-NOT-apply clause must name "
        "specific Convention number(s) explicitly, not a blanket 'these rules'/'the rules "
        "below' - an unscoped clause cannot be checked for whether it silently swallows "
        "Convention 0."
    )
    gated_numbers = {int(n) for n in re.findall(r"\d+", do_not_match.group(1))}

    # 2. Convention 0 must never be one of the gated numbers.
    assert 0 not in gated_numbers, (
        "snippets/upg-conventions.md: the DO-NOT-apply clause names Convention 0 among the "
        f"gated conventions ({sorted(gated_numbers)}) - Convention 0 is CORE and must never "
        "sit inside the Viindoo-profile-gated scope."
    )

    # 3. The CORE carve-out must explicitly name Convention 0 as exempt from the gate.
    carve_out_paras = [p for p in _paragraphs(text) if "CORE Odoo rules" in p]
    assert carve_out_paras and "does NOT apply to them" in _norm(carve_out_paras[0]), (
        "snippets/upg-conventions.md: the CORE carve-out paragraph must explicitly state "
        "the Viindoo gate does NOT apply to Convention 0 (and the file's other CORE "
        "conventions)."
    )
    assert re.search(r"Conv-0\b", carve_out_paras[0]), (
        "snippets/upg-conventions.md: the CORE carve-out paragraph must name 'Conv-0' "
        "explicitly among the conventions the gate does not apply to."
    )

    # 4. Transitive check: Convention 0's own body must not delegate its rule text (via
    #    "Convention N owns ...") to a convention number that IS inside the gated scope -
    #    otherwise a non-Viindoo profile is directed by CORE Convention 0 to a convention its
    #    own gate forbids applying there. This is the check that catches the original defect.
    convention_0_body_norm = _norm(text[text.index("## Convention 0"):])
    delegate_targets = {
        int(m.group(1)) for m in re.finditer(r"Convention (\d+) owns", convention_0_body_norm)
    }
    assert delegate_targets, (
        "snippets/upg-conventions.md: Convention 0's body no longer names which convention "
        "'owns' the no-bump rule referenced in clause (a) - this test can no longer verify "
        "the delegation target stays outside the gated scope."
    )
    leaking_targets = delegate_targets & gated_numbers
    assert not leaking_targets, (
        "snippets/upg-conventions.md: Convention 0 delegates its rule text to Convention "
        f"{sorted(leaking_targets)} ('Convention N owns ...'), but that convention is inside "
        f"the Viindoo-gated scope {sorted(gated_numbers)} - a non-Viindoo profile would be "
        "sent by CORE Convention 0 to a rule its own gate forbids applying there. The "
        "delegation target must itself be CORE (outside the gated scope)."
    )


def test_convention_zero_reachability_route_is_the_p4_brief_not_a_dead_index_pointer():
    """The carve-out must point at the REAL reachability route (the P4 dispatch brief
    citing this file unconditionally + the coder's own unconditional disposition
    trigger) - not at 'the version INDEX By-task table', which review verification found
    carries no row for Convention 0 in either the top-level Snippets catalog or any
    per-version § By task table.

    Base commit: the carve-out claims 'reachable for ALL profiles via the version INDEX
    By-task table' - a route verification found does not exist for Convention 0. RED.
    """
    text = _upg_conventions_text()
    norm = _norm(text)
    assert "version INDEX By-task table" not in norm, (
        "snippets/upg-conventions.md must not re-claim Convention 0 is reachable via 'the "
        "version INDEX By-task table' - no such row exists for Convention 0 in either the "
        "top-level Snippets catalog or any per-version § By task table."
    )
    assert "upg-phase-detail.md" in norm and "odoo-coding dispatch brief" in norm, (
        "snippets/upg-conventions.md's carve-out must name the REAL route: the "
        "odoo-modules-upgrade P4 'odoo-coding dispatch brief' template that cites this "
        "file unconditionally."
    )
