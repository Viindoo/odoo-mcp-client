"""Guard tests for the R12 runtime-review residual-gap fix pass (`66-fix-r12-residuals.md`).

Four DEGRADES-severity findings closed here: two were pre-existing gaps the review surfaced (A,
B), one is an asymmetry this session's own work left behind (C). Defect D
(`61-r12-waves.md` finding 4 - the worktree-addons carve-out's structural backstop) got a
prose-only cross-reference fix with no dedicated guard, per the fix brief's own scope (it asks for
guards on A/B/C only).

New file (not appended to an existing one) because two other agents were concurrently editing
`tests/test_wave_advance_and_lint_placement.py` and `tests/test_forward_port_hardening.py` in the
same worktree at fix time.

- **A** (`63-r12-i18n-evidence-prose.md` F3) - `odoo-demo-recording`'s `visual/videos/` evidence
  path had no collision-proofing suffix, unlike the four sibling `visual/*/<slug>/` evidence
  directories `visual-evidence-lifecycle-contract.md` Clause 1 governs, and the skill's own worked
  example resolved `<timestamp>` to a bare 8-digit date - the exact "date alone still collides
  same-day" shape Clause 1's own rationale warns about. Fixed by extending Clause 1 to a FIFTH
  consumer (a filename, not a directory) and rewriting every `<feature>-<timestamp>` occurrence
  (SKILL.md, examples.md, state-root-resolution.md, visual-evidence-lifecycle-contract.md) to
  `<feature>-<YYYYMMDD>-<4 random chars>`.
- **B** (`62-r12-instance-allocator.md` F3) - `agents/odoo-instance-ops.md`'s "Multi-instance
  parallel provisioning" acquire call carried no `--run-id`, unlike every other acquire call site
  in that file, so `hooks/enforce-teardown.sh`'s ownership correlation (strictly keyed on
  `--run-id` on the subagent's own acquire/bind/heartbeat calls) could never see a leaked lease
  from that one path. Fixed by threading `--run-id <run_id>` there, matching the sibling sites.
- **C** (`61-r12-waves.md` finding 2) - intake's claim that downstream execute-skills read a
  deep-survey `synthesis.md` "carried ... in the `run-<id>.json` node inputs" was false: neither
  `phase-p-run-dag.md`'s schema, `odoo-planner`'s dispatch template, nor `odoo-coding`'s per-module
  brief template carried a survey field - an asymmetry against the mandatory recon pointer, which
  IS correctly wired. Fixed by mirroring `inputs.recon_findings`'s shape end-to-end (Phase P schema
  -> `odoo-planning` Input port + P1a template -> `odoo-planner` Round 0 -> `odoo-coding` per-module
  brief), with one deliberate difference: the survey key is ALWAYS explicit (`<path>` or the literal
  `none`), never omitted when absent - unlike recon, which may be safely omitted since the
  mandatory-tier scout self-derives when the key is missing. One hop (`run-harness`'s own
  `wave-integration.md` per-module invocation-brief template) could not be edited directly in this
  pass (that file was owned by concurrently-active agents) - handed off verbatim, with the exact
  anchor and insertion text, to
  `/tmp/odoo-mcp-client-research/phase2/72-handoff-fix3.md`.

Each RED count below was measured against `git show HEAD:<path>` (the pre-fix worktree state),
never `git stash`.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"


def _iter_md_files():
    for path in sorted(PLUGIN.rglob("*.md")):
        yield path


def _rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def _text(rel_path: str) -> str:
    return (PLUGIN / rel_path).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Defect A - visual/ evidence-path collision-proofing (R12 F3)
# ---------------------------------------------------------------------------


def test_no_visual_evidence_path_uses_a_bare_timestamp_placeholder():
    """Structural, forward-looking sweep - NOT pinned to today's five evidence paths by name.

    Any line naming a `visual/`-rooted evidence path AND the literal `<timestamp>` placeholder
    token must also name the collision-proofing "random" suffix on the SAME line - the mechanism
    `visual-evidence-lifecycle-contract.md` Clause 1 defines for the four sibling
    `visual/*/<slug>/` directories and, after this fix, `odoo-demo-recording`'s `visual/videos/`
    filename (Clause 1's "fifth consumer" paragraph). A FUTURE skill that introduces a sixth
    `visual/`-rooted per-run path and reintroduces a bare `<feature>-<timestamp>` template - the
    exact defect class R12 F3 found - trips this test even though it is never named here.

    Measured RED (`git show HEAD`, before this fix): 10 offending lines across 4 files -
    `skills/odoo-demo-recording/SKILL.md` (5), `.../references/examples.md` (1),
    `snippets/state-root-resolution.md` (2), `snippets/visual-evidence-lifecycle-contract.md` (1,
    a single long table-row line that mentions `<timestamp>` twice) - re-derivable via:
    `git show HEAD:<path> | grep -nE '.*visual/.*<timestamp>|.*<timestamp>.*visual/'`.
    """
    hits = []
    for path in _iter_md_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if "visual/" not in line or "<timestamp>" not in line:
                continue
            if re.search(r"random", line, re.IGNORECASE):
                continue
            hits.append(f"{_rel(path)}:{lineno}: {line.strip()}")
    assert not hits, (
        "visual/-rooted evidence path mentions a bare <timestamp> placeholder with no "
        "collision-proofing 'random' suffix named on the same line (R12 F3 - two same-day runs "
        "on a similarly-named intent silently overwrite each other's evidence artifact):\n"
        + "\n".join(hits)
    )


def test_demo_recording_worked_examples_do_not_use_bare_date_collision_form():
    """`references/examples.md`'s worked examples must not resolve a video-evidence filename to a
    bare 8-digit date immediately followed by `-before`/`-after` with nothing in between - R12
    F3's exact "the worked example resolves <timestamp> to a bare DATE" collision shape (two
    before/after evidence recordings for a similarly-named feature on the same day would silently
    overwrite each other's clip). This is a companion to the general sweep above: the general
    sweep catches the PLACEHOLDER form (`<timestamp>`); this one catches the RESOLVED-example form
    (a concrete `YYYYMMDD`), which the general sweep cannot see since it never contains the
    literal token `<timestamp>`.

    Measured RED (`git show HEAD`): 2 lines
    (`lcl-coloader-vendor-20260803-before/` and `.../lcl-coloader-vendor-20260803-after/`).
    """
    path = PLUGIN / "skills" / "odoo-demo-recording" / "references" / "examples.md"
    text = path.read_text(encoding="utf-8")
    hits = [m.group(0) for m in re.finditer(r"\d{8}-(before|after)\b", text)]
    assert not hits, (
        "examples.md resolves a video-evidence filename to a bare date immediately followed by "
        "-before/-after with no random disambiguator between them - the exact collision shape "
        f"R12 F3 flagged: {hits}"
    )


# ---------------------------------------------------------------------------
# Defect B - odoo-instance-ops.md multi-instance acquire had no --run-id
# (R12 62-r12-instance-allocator.md F3)
# ---------------------------------------------------------------------------


def test_every_allocator_acquire_call_site_threads_run_id():
    """Structural sweep of every literal `allocator.py acquire` invocation documented in
    `agents/odoo-instance-ops.md`: each must have a run-id reference (`--run-id`, `run_id`, or
    `INST_RUN_ID`) within a bounded window around it. `hooks/enforce-teardown.sh`'s ownership
    correlation is derived STRICTLY from `--run-id` on the subagent's OWN acquire/bind/heartbeat
    Bash calls (`_run_ids()`, enforce-teardown.sh:145-156); an acquire call site with none mints a
    lease the SubagentStop hard-block can never see, even when it leaks. Generalizes to any FUTURE
    acquire call site added to this file without `--run-id` - not just today's fixed line.

    Measured RED (`git show HEAD`): 1 of 3 documented acquire call sites (the "Multi-instance
    parallel provisioning" step 1 acquire) had no run-id reference within the window.
    """
    path = PLUGIN / "agents" / "odoo-instance-ops.md"
    text = path.read_text(encoding="utf-8")
    hits = []
    for m in re.finditer(r"allocator\.py acquire\b", text):
        start = m.start()
        window = text[max(0, start - 200): start + 300]
        if not re.search(r"run[-_]id", window, re.IGNORECASE):
            lineno = text.count("\n", 0, start) + 1
            hits.append(f"{_rel(path)}:{lineno}")
    assert not hits, (
        "allocator.py acquire call site(s) with no --run-id / run_id within a 500-char window - "
        "each mints an unowned lease invisible to enforce-teardown.sh's ownership correlation:\n"
        + "\n".join(hits)
    )


# ---------------------------------------------------------------------------
# Defect C - deep-survey synthesis never reached the coder brief
# (61-r12-waves.md finding 2)
# ---------------------------------------------------------------------------


def test_phase_p_run_dag_serializes_an_explicit_survey_pointer():
    """`phase-p-run-dag.md` must declare an `inputs.survey` key (mirroring `inputs.recon_findings`)
    and state it is ALWAYS explicit - a path or the literal `none` - never silently omitted like
    the recon key may be. Without this, intake's own claim (`SKILL.md` § Deep survey, "carried ...
    in the run-<id>.json node inputs") stays false for every run that opts into a deep survey.

    Measured RED (`git show HEAD`): 0 occurrences of `inputs.survey` in this file.
    """
    text = _text("skills/odoo-intake/references/phase-p-run-dag.md")
    assert "inputs.survey:" in text, (
        "phase-p-run-dag.md has no inputs.survey key - a deep-survey synthesis path never reaches "
        "the run-dag node (R12 finding 2)"
    )
    assert re.search(r"never omit", text, re.IGNORECASE), (
        "phase-p-run-dag.md's Survey pointer clause must state the key is ALWAYS explicit "
        "(path or literal none) - never silently omitted, unlike inputs.recon_findings"
    )


def test_odoo_planner_dispatch_template_carries_survey_field():
    """`odoo-planning/SKILL.md`'s P1a dispatch template (the brief that launches `odoo-planner`)
    must carry a `SURVEY:` field alongside `DESIGN_INDEX`/`GAP_MATRIX`/`QA_ORACLE`, so a deep-survey
    synthesis authored by intake actually reaches the planner.

    Measured RED (`git show HEAD`): field absent from the P1a template.
    """
    text = _text("skills/odoo-planning/SKILL.md")
    assert "SURVEY: [none |" in text, (
        "odoo-planning's P1a dispatch template has no SURVEY field - a deep-survey synthesis "
        "authored by intake never reaches odoo-planner (R12 finding 2)"
    )


def test_odoo_planner_agent_reads_survey_as_round_0_input():
    """`agents/odoo-planner.md`'s Round 0 input list must document reading an (optional) SURVEY
    pointer, alongside DESIGN_INDEX/GAP_MATRIX/QA_ORACLE, so the agent has a documented
    instruction to consume it once threaded.

    Measured RED (`git show HEAD`): no SURVEY item in Round 0.
    """
    text = _text("agents/odoo-planner.md")
    assert re.search(r"\*\*SURVEY\b", text), (
        "odoo-planner.md's Round 0 input list has no SURVEY item - even if a survey pointer "
        "reaches this agent's brief, nothing tells it to read the field (R12 finding 2)"
    )


def test_odoo_coding_per_module_brief_carries_survey_field():
    """`odoo-coding/SKILL.md`'s per-module Coder brief template must carry a `SURVEY:` field,
    the final hop the deep-survey synthesis needs to actually ground a module's implementation -
    the concrete gap the R12 review evidenced ("a discount-cap run opted into deep-survey ...
    that work product never reaches the coder").

    Measured RED (`git show HEAD`): field absent from the Coder brief template.
    """
    text = _text("skills/odoo-coding/SKILL.md")
    assert "SURVEY: <deep-survey synthesis.md path | none>" in text, (
        "odoo-coding's per-module Coder brief template has no SURVEY field - an opted-in deep "
        "survey's synthesis never reaches the coder (R12 finding 2)"
    )
