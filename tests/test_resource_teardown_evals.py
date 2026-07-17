"""Behavioral evals for the resource-teardown contract (plugins/odoo-ai-agents/snippets/
resource-teardown-contract.md): Eval A proves the CLOSE(browser)-vs-RELEASE(instance) verb split
(T2 vs T3) holds even under a forwarded-lease collision; Eval B proves the visual-regression
matrix-close (T0/T2) leaves no run-created page open.

WHY these tests exist (and what they do NOT prove): tests/test_resource_teardown_contract.py
(a static wording-freeze guard) can prove the SSOT snippet text is unchanged. It CANNOT prove
that an agent reading "never drop or release the forwarded lease" right next to a NEW "close
every page you opened" instruction actually does BOTH at once, instead of collapsing into either
failure mode:
  (a) over-applying the ban to browser pages (leaves a capture page open "to be safe"), or
  (b) under-applying it and releasing/dropping the forwarded instance lease anyway.
Proving that requires running the agent and grading its TRANSCRIPT - genuinely a live-model
question (see "Harness convention" below). What CAN run here, deterministically and in CI, is
the GRADING LOGIC itself: given a transcript (hand-authored fixture today; a real captured
transcript once someone runs the live eval), does the grader correctly call PASS/FAIL? These
tests are that proof - "transcript-fixture tests" per this repo's own established convention.

Harness convention (discovered, not invented - see the audit trail in this docstring for what
was ruled out):
- This repo's plugins/odoo-ai-agents/skills/*/evals/evals.json + the globally-installed
  skill-creator plugin's run_eval.py/run_loop.py is a TRIGGER-ONLY harness: it spawns `claude -p`
  and watches the FIRST stream event for a Skill/Read tool-use naming the skill under test, then
  returns as soon as triggering is decided (scripts/run_eval.py:run_single_query - `return True`
  the instant the skill name appears; `return False` on any other first tool). It structurally
  cannot observe a full multi-step transcript for arbitrary tool-call assertions - wrong tool for
  Eval A/B's "does the transcript contain X and not Y across the whole run" question.
- skill-creator ALSO documents a broader executor+grader convention (SKILL.md "Running and
  evaluating test cases" + agents/grader.md): spawn an executor subagent on a brief, capture its
  transcript + outputs, then grade freeform `expectations` (schemas.md) against the transcript
  with an LLM grader, writing grading.json. This is the right SHAPE for Eval A/B and is what
  evals/resource-teardown/*/*.evals.json (siblings to this file, schema-compatible) are written
  for. But it is a manual/interactive workflow the skill-creator skill drives - not a script this
  repo owns, wires into `make test`, or runs in CI.
- This repo's OWN CI-integrated mechanism (`make test` -> pytest tests/) has exactly one existing
  precedent for "grade a crafted multi-step transcript" - tests/test_enforce_teardown.py and
  tests/test_enforce_grounding.py, both driving a SubagentStop/Stop hook against a hand-built
  transcript.jsonl via the `_line`/`_tu`/`_text` builder pattern. This file mirrors that pattern
  exactly (same builder shapes, same tmp_path convention), pointed at
  evals/resource-teardown/lib/grading.py's two deterministic graders instead of a bash hook.

Because both PASS assertions given in the eval spec are mechanical (tool-name suffix match,
substring absence, page-id set membership - no subjective judgment), a deterministic Python
grader is used instead of an LLM one; the evals.json siblings document the exact live-run command
for when a real agent + browser MCP is available. Per ETHOS #8, each test below asserts on the
grader's OBSERVABLE verdict (pass/fail + evidence), not on the code path that produced it, and
each one is authored to be capable of failing for the stated reason (a FAIL fixture per PASS
fixture, proving the grader actually discriminates rather than passing unconditionally).

Run with: python3 -m pytest tests/test_resource_teardown_evals.py -v
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
GRADING_PY = ROOT / "evals" / "resource-teardown" / "lib" / "grading.py"
EVAL_A_DIR = ROOT / "evals" / "resource-teardown" / "eval-a-verb-collision"
EVAL_B_DIR = ROOT / "evals" / "resource-teardown" / "eval-b-visual-regression-matrix"


def _load_grading_module():
    spec = importlib.util.spec_from_file_location("teardown_grading", GRADING_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


grading = _load_grading_module()


# --------------------------------------------------------------------------------------------- #
# Transcript builders (mirror tests/test_enforce_teardown.py's _line/_tu/_text convention)
# --------------------------------------------------------------------------------------------- #
def _line(role="assistant", content=None):
    return json.dumps({"role": role, "content": content or []})


def _tu(name, id_=None, **input_kwargs):
    block = {"type": "tool_use", "name": name, "input": input_kwargs}
    if id_:
        block["id"] = id_
    return block


def _text(s):
    return {"type": "text", "text": s}


def _tool_result(tool_use_id, text):
    return {"type": "tool_result", "tool_use_id": tool_use_id, "content": [{"type": "text", "text": text}]}


def _list_pages_result(tool_use_id, open_pages):
    return _tool_result(tool_use_id, json.dumps({"open_pages": open_pages}))


def _write_transcript(tmp_path, lines) -> Path:
    tpath = tmp_path / "transcript.jsonl"
    tpath.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return tpath


# --------------------------------------------------------------------------------------------- #
# Eval definitions must exist and parse (the "runnable eval definition" half of the deliverable)
# --------------------------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "path",
    [
        EVAL_A_DIR / "odoo-user-doc-writer.evals.json",
        EVAL_A_DIR / "odoo-marketing-writer.evals.json",
        EVAL_B_DIR / "odoo-visual-regression.evals.json",
    ],
)
def test_evals_json_exists_and_has_required_fields(path):
    assert path.is_file(), f"eval definition missing: {path}"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data.get("agent_name") or data.get("skill_name"), "must name its target (agent_name or skill_name)"
    assert data["evals"], "evals[] must not be empty"
    for item in data["evals"]:
        assert item["prompt"], "each eval needs a self-contained prompt/brief"
        assert item["expectations"], "each eval needs at least one verifiable expectation"


def test_eval_a_briefs_carry_a_forwarded_handle_and_the_hard_lease_ban():
    """The eval prompt itself must reproduce the collision, not dodge it."""
    for path in (EVAL_A_DIR / "odoo-user-doc-writer.evals.json", EVAL_A_DIR / "odoo-marketing-writer.evals.json"):
        prompt = json.loads(path.read_text(encoding="utf-8"))["evals"][0]["prompt"]
        assert "INSTANCE_HANDLE" in prompt
        assert "Do NOT drop or release the lease" in prompt
        assert "clos" in prompt.lower(), "the brief must also carry the CLOSE-the-pages instruction"


# --------------------------------------------------------------------------------------------- #
# Eval A - verb collision: grade_eval_a on hand-authored fixture transcripts
# --------------------------------------------------------------------------------------------- #
def test_eval_a_chrome_devtools_close_with_no_release_passes(tmp_path):
    """PASS shape (chrome-devtools family): captures, closes every page, hands the lease back."""
    lines = [
        _line(content=[_tu("mcp__chrome-devtools__new_page", id_="t1")]),
        _line(role="user", content=[_tool_result("t1", "page created")]),
        _line(content=[_tu("mcp__chrome-devtools__navigate_page")]),
        _line(content=[_tu("mcp__chrome-devtools__take_screenshot")]),
        _line(content=[_tu("mcp__chrome-devtools__close_page", pageId=1)]),
        _line(content=[_text(
            "### Path-incremental completion\n"
            "instance_handle: odoo_17_0_doc:8172\n"
            "module: sale_delivery_window\n"
            "status: doc-complete\n"
        )]),
    ]
    out = grading.grade_eval_a(_write_transcript(tmp_path, lines))
    assert out["pass"] is True, out
    assert out["close_call"] == "mcp__chrome-devtools__close_page"
    assert out["forbidden_hits"] == []


def test_eval_a_playwright_browser_close_with_no_release_passes(tmp_path):
    """PASS shape (playwright family): one browser_close covers everything driven."""
    lines = [
        _line(content=[_tu("mcp__playwright__browser_navigate")]),
        _line(content=[_tu("mcp__playwright__browser_click")]),
        _line(content=[_tu("mcp__playwright__browser_close")]),
        _line(content=[_text("status: doc-complete\ninstance_handle: odoo_17_0_doc:8172")]),
    ]
    out = grading.grade_eval_a(_write_transcript(tmp_path, lines))
    assert out["pass"] is True, out
    assert out["close_call"] == "mcp__playwright__browser_close"


def test_eval_a_pagecast_stop_recording_with_no_release_passes(tmp_path):
    """PASS shape (pagecast family): stop_recording is the close-equivalent."""
    lines = [
        _line(content=[_tu("mcp__pagecast__record_page")]),
        _line(content=[_tu("mcp__pagecast__stop_recording")]),
        _line(content=[_text("status: doc-complete\ninstance_handle: odoo_17_0_doc:8172")]),
    ]
    out = grading.grade_eval_a(_write_transcript(tmp_path, lines))
    assert out["pass"] is True, out
    assert out["close_call"] == "mcp__pagecast__stop_recording"


def test_eval_a_suffix_matching_across_headed_and_plugin_prefixes(tmp_path):
    """The close-call check is suffix-keyed, not tied to one fixed MCP prefix namespace."""
    lines = [
        _line(content=[_tu("mcp__chrome-devtools-headed__new_page")]),
        _line(content=[_tu("mcp__plugin_odoo-ai-agents_chrome-devtools__close_page", pageId=1)]),
        _line(content=[_text("status: doc-complete")]),
    ]
    out = grading.grade_eval_a(_write_transcript(tmp_path, lines))
    assert out["pass"] is True, out
    assert out["close_call"] == "mcp__plugin_odoo-ai-agents_chrome-devtools__close_page"


def test_eval_a_forgetting_to_close_fails_direction_one(tmp_path):
    """FAIL direction 1: over-applying the lease-ban - captures a page, never closes it."""
    lines = [
        _line(content=[_tu("mcp__chrome-devtools__new_page")]),
        _line(content=[_tu("mcp__chrome-devtools__take_screenshot")]),
        _line(content=[_text("status: doc-complete\ninstance_handle: odoo_17_0_doc:8172")]),
    ]
    out = grading.grade_eval_a(_write_transcript(tmp_path, lines))
    assert out["pass"] is False, out
    assert out["close_call"] is None
    assert out["forbidden_hits"] == []
    failed_texts = [e["text"] for e in out["expectations"] if not e["passed"]]
    assert any("CLOSE call" in t for t in failed_texts)


def test_eval_a_releasing_the_forwarded_lease_fails_direction_two(tmp_path):
    """FAIL direction 2: under-applying the ban - closes pages correctly, THEN releases the lease anyway."""
    lines = [
        _line(content=[_tu("mcp__chrome-devtools__new_page")]),
        _line(content=[_tu("mcp__chrome-devtools__take_screenshot")]),
        _line(content=[_tu("mcp__chrome-devtools__close_page", pageId=1)]),
        _line(content=[_tu(
            "Bash",
            command='python3 "${CLAUDE_PLUGIN_ROOT}/scripts/lib/allocator.py" release odoo_17_0_doc:8172 --run-id doc-run-42',
        )]),
        _line(content=[_text("status: DONE")]),
    ]
    out = grading.grade_eval_a(_write_transcript(tmp_path, lines))
    assert out["pass"] is False, out
    assert out["close_call"] is not None, "the page WAS correctly closed - only the lease release should fail this"
    assert out["forbidden_hits"], "the allocator.py release call on a forwarded handle must be caught"
    assert out["forbidden_hits"][0]["token"] == "allocator.py release"
    failed_texts = [e["text"] for e in out["expectations"] if not e["passed"]]
    assert any("release/drop token" in t for t in failed_texts)


def test_eval_a_operation_drop_prose_also_fails(tmp_path):
    """FAIL direction 2, alternate token: the ban can also be violated in prose, not just a Bash call."""
    lines = [
        _line(content=[_tu("mcp__chrome-devtools__close_page", pageId=1)]),
        _line(content=[_text("Cleaning up: operation: drop on the shared instance, then status: DONE")]),
    ]
    out = grading.grade_eval_a(_write_transcript(tmp_path, lines))
    assert out["pass"] is False, out
    assert any(h["token"] == "operation: drop" for h in out["forbidden_hits"])


def test_eval_a_forbidden_token_in_tool_result_is_not_the_agents_fault(tmp_path):
    """A tool_result that merely ECHOES a forbidden phrase (e.g. an error message) is not an
    agent action - only the agent's OWN tool_use/text counts (mirrors enforce-teardown.sh's
    assistant-only NORM extraction)."""
    lines = [
        _line(content=[_tu("mcp__chrome-devtools__close_page", pageId=1, id_="t1")]),
        _line(role="user", content=[_tool_result(
            "t1", "note: a prior run once needed odoo_db.py drop, this one does not"
        )]),
        _line(content=[_text("status: doc-complete")]),
    ]
    out = grading.grade_eval_a(_write_transcript(tmp_path, lines))
    assert out["pass"] is True, out
    assert out["forbidden_hits"] == []


# --------------------------------------------------------------------------------------------- #
# Eval B - visual-regression matrix: grade_eval_b on a 5-screen x 4-breakpoint x 2-state fixture
# --------------------------------------------------------------------------------------------- #
SCREENS = ["sale_order_form", "sale_order_list", "quotation_kanban", "invoice_form", "invoice_list"]
BREAKPOINTS = [375, 768, 1280, 1920]
STATES = ["baseline", "current"]


def _matrix_capture_lines(extra_page_created: bool) -> list[str]:
    """Build the full 5x4x2 = 40-combination sweep, reusing page 0 throughout (Round 2/3's
    single-page discipline), optionally injecting one single-page-discipline lapse (an extra
    `new_page` for one breakpoint, as a real agent might slip and do) partway through."""
    lines = []
    combo = 0
    for screen in SCREENS:
        for breakpoint in BREAKPOINTS:
            for state in STATES:
                combo += 1
                if extra_page_created and combo == 7:
                    # A single lapse: one extra page opened instead of reusing page 0.
                    lines.append(_line(content=[_tu("mcp__chrome-devtools__new_page")]))
                lines.append(_line(content=[_tu(
                    "mcp__chrome-devtools__navigate_page", screen=screen, state=state,
                )]))
                lines.append(_line(content=[_tu("mcp__chrome-devtools__resize_page", width=breakpoint)]))
                lines.append(_line(content=[_tu(
                    "mcp__chrome-devtools__take_screenshot",
                    path=f"{state}/{screen}-{breakpoint}.png",
                )]))
    assert combo == len(SCREENS) * len(BREAKPOINTS) * len(STATES) == 40
    return lines


def test_matrix_fixture_covers_the_full_5x4x2_sweep():
    """Guard the fixture itself: the eval must exercise the whole matrix, not a stub subset."""
    lines = _matrix_capture_lines(extra_page_created=False)
    navigate_calls = sum(1 for l in lines if "navigate_page" in l)
    assert navigate_calls == 40, "the sweep must cover all 5 screens x 4 breakpoints x 2 states"


def test_eval_b_clean_single_page_sweep_with_no_leftover_passes(tmp_path):
    """PASS shape: single-page discipline held throughout - zero pages created, nothing to leak."""
    lines = _matrix_capture_lines(extra_page_created=False)
    lines.append(_line(content=[_tu("mcp__chrome-devtools__list_pages", id_="lp1")]))
    lines.append(_line(role="user", content=[_list_pages_result("lp1", open_pages=[0])]))
    lines.append(_line(content=[_text("## Visual Regression: baseline vs current (Odoo v17)\nstatus: DONE")]))
    out = grading.grade_eval_b(_write_transcript(tmp_path, lines))
    assert out["pass"] is True, out
    assert out["created_pages"] == []
    assert out["leftover_created_pages"] == []


def test_eval_b_lapse_correctly_closed_before_final_report_passes(tmp_path):
    """PASS shape, discriminating: a real single-page-discipline lapse occurs mid-sweep (an
    extra page gets created), but Round 4's matrix-shaped close catches it - the FINAL list_pages
    (the independent, ground-truth check) shows it gone before the report."""
    lines = _matrix_capture_lines(extra_page_created=True)
    # Round 4: discover the leftover, close it, THEN an independent post-hoc verification.
    lines.append(_line(content=[_tu("mcp__chrome-devtools__list_pages", id_="lp1")]))
    lines.append(_line(role="user", content=[_list_pages_result("lp1", open_pages=[0, 1])]))
    lines.append(_line(content=[_tu("mcp__chrome-devtools__close_page", pageId=1)]))
    lines.append(_line(content=[_tu("mcp__chrome-devtools__list_pages", id_="lp2")]))
    lines.append(_line(role="user", content=[_list_pages_result("lp2", open_pages=[0])]))
    lines.append(_line(content=[_text("## Visual Regression: baseline vs current (Odoo v17)\nstatus: DONE")]))
    out = grading.grade_eval_b(_write_transcript(tmp_path, lines))
    assert out["pass"] is True, out
    assert out["created_pages"] == [1]
    assert out["final_list_pages_open"] == [0], "the FINAL (second) list_pages must be what's graded"
    assert out["leftover_created_pages"] == []
    assert out["list_pages_call_count"] == 2


def test_eval_b_lapse_left_open_fails_and_gates_the_keep_inline_decision(tmp_path):
    """FAIL shape: the single-page-discipline lapse is never closed - the final list_pages
    (ground truth) still shows the run-created page open. Per L1.7, this result is what would
    force revisiting the keep-inline decision for odoo-visual-regression."""
    lines = _matrix_capture_lines(extra_page_created=True)
    # Round 4 calls list_pages but the created page (id 1) is never closed.
    lines.append(_line(content=[_tu("mcp__chrome-devtools__list_pages", id_="lp1")]))
    lines.append(_line(role="user", content=[_list_pages_result("lp1", open_pages=[0, 1])]))
    lines.append(_line(content=[_text("## Visual Regression: baseline vs current (Odoo v17)\nstatus: DONE")]))
    out = grading.grade_eval_b(_write_transcript(tmp_path, lines))
    assert out["pass"] is False, out
    assert out["created_pages"] == [1]
    assert out["leftover_created_pages"] == [1]
    failed_texts = [e["text"] for e in out["expectations"] if not e["passed"]]
    assert any("none of the page ids" in t for t in failed_texts)


def test_eval_b_list_pages_never_called_fails_the_matrix_shaped_close_check(tmp_path):
    """FAIL shape: Round 4's close step never fired at all (no list_pages call whatsoever) -
    there is no ground truth to confirm nothing leaked, so this cannot be graded PASS."""
    lines = _matrix_capture_lines(extra_page_created=False)
    lines.append(_line(content=[_text("## Visual Regression: baseline vs current (Odoo v17)\nstatus: DONE")]))
    out = grading.grade_eval_b(_write_transcript(tmp_path, lines))
    assert out["pass"] is False, out
    assert out["list_pages_call_count"] == 0
    failed_texts = [e["text"] for e in out["expectations"] if not e["passed"]]
    assert any("Round-4 close step actually fired" in t for t in failed_texts)


# --------------------------------------------------------------------------------------------- #
# CLI smoke: the live-run entry point documented in each evals.json's how_to_run_live
# --------------------------------------------------------------------------------------------- #
def test_cli_eval_a_exits_nonzero_on_fail_and_zero_on_pass(tmp_path):
    import subprocess
    import sys

    fail_dir = tmp_path / "fail"
    fail_dir.mkdir()
    fail_lines = [_line(content=[_text("status: doc-complete")])]  # no close call at all
    fail_path = _write_transcript(fail_dir, fail_lines)
    proc = subprocess.run(
        [sys.executable, str(GRADING_PY), "eval-a", str(fail_path)],
        capture_output=True, text=True, timeout=20,
    )
    assert proc.returncode == 1, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["pass"] is False

    pass_dir = tmp_path / "pass"
    pass_dir.mkdir()
    pass_lines = [
        _line(content=[_tu("mcp__chrome-devtools__close_page", pageId=1)]),
        _line(content=[_text("status: doc-complete")]),
    ]
    pass_path = _write_transcript(pass_dir, pass_lines)
    proc = subprocess.run(
        [sys.executable, str(GRADING_PY), "eval-a", str(pass_path)],
        capture_output=True, text=True, timeout=20,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["pass"] is True
