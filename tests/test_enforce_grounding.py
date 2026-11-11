"""Behavioral guard for hooks/enforce-grounding.sh (SubagentStop grounding enforcement).

These tests protect the BEHAVIOR contract of the hook (ETHOS#11) for its consumer - an
AI subagent (odoo-coder / odoo-frontend-coder / odoo-code-reviewer). Each test states the
business rule it locks in and fails for exactly one reason: that rule changed.

The contract under test:
- BLOCK only the provable lie: a label line of the report claims OSM grounding with ZERO
  mcp__odoo-semantic__* calls. The label quoted or mentioned anywhere else is not a claim.
- NOTE (non-blocking) the half-grounded case: backend .py written, OSM called, ORM validators
  skipped.
- NOTE (non-blocking) the SILENT-SKIPPER: backend .py written with zero OSM calls and no
  grounding label. (Deliberately a note, not a block - a block there only manufactures
  unverifiable `grounded: local-source` labels and false-blocks legit pure-python/standalone
  work. The hard quality gate is Odoo's test_lint/test_pylint CI module, not OSM-call-count.)
- PASS (stay out of the way): non-Odoo subagents (self-gate), honest local-source label,
  properly grounded work, and a lie block already given inside the same hook-continued chain
  (a continued stop is still checked; a fresh stop is blocked again).

Run with: python3.11 -m pytest tests/test_enforce_grounding.py -v
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import (block_feedback_record, brief_record, handback_records, model_context,
                      resume_record)

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / "plugins" / "odoo-ai-agents" / "hooks" / "enforce-grounding.sh"

pytestmark = pytest.mark.skipif(
    shutil.which("jq") is None or shutil.which("bash") is None,
    reason="enforce-grounding.sh needs jq + bash; absent here (the hook itself degrades to pass)",
)


def _line(role="assistant", content=None):
    return json.dumps({"role": role, "content": content or []})


OSM_PREFIXES = [
    pytest.param("mcp__plugin_odoo-semantic-mcp_odoo-semantic__", id="plugin-form"),
    pytest.param("mcp__odoo-semantic__", id="hand-registered-form"),
]


def _tool_use(name, file_path=None):
    inp = {"file_path": file_path} if file_path else {}
    return {"type": "tool_use", "name": name, "input": inp}


def _text(s):
    return {"type": "text", "text": s}


def _run(tmp_path, transcript_lines, stop_hook_active=False, last_message=None):
    """Invoke the hook with a crafted transcript + stdin; return (rc, parsed_stdout_or_None).
    `last_message` is the payload's last_assistant_message - the text of the final message."""
    tpath = tmp_path / "transcript.jsonl"
    tpath.write_text("\n".join(transcript_lines) + "\n", encoding="utf-8")
    # The real SubagentStop payload: the subagent's OWN transcript is agent_transcript_path, and
    # transcript_path is the whole session's (an empty decoy here).
    session = tmp_path / "session-transcript.jsonl"
    session.write_text("", encoding="utf-8")
    payload = {"hook_event_name": "SubagentStop", "transcript_path": str(session),
               "agent_transcript_path": str(tpath), "stop_hook_active": stop_hook_active}
    if last_message is not None:
        payload["last_assistant_message"] = last_message
    stdin = json.dumps(payload)
    proc = subprocess.run(
        ["bash", str(HOOK)], input=stdin, capture_output=True, text=True, timeout=20
    )
    out = proc.stdout.strip()
    parsed = json.loads(out) if out else None
    return proc.returncode, parsed


def _note_text(out) -> str:
    """A grounding NOTE's text: it must reach the subagent, the one agent that can still act on it
    before its report reaches the caller (SubagentStop additionalContext)."""
    assert out is not None, "expected a grounding note"
    note = model_context(out, "SubagentStop")
    assert note, out
    return note


def test_hook_exists_and_is_executable_shell():
    assert HOOK.exists(), f"hook not found at {HOOK}"
    assert HOOK.read_text(encoding="utf-8").startswith("#!"), "hook must be a shell script"


def test_lie_is_blocked(tmp_path):
    """A label line claims `grounded: osm` with ZERO OSM calls -> the provable lie -> BLOCK."""
    lines = [
        _line(content=[_tool_use("Write", "models/sale.py")]),
        _line(content=[_text("Done.\ngrounded: osm")]),
    ]
    rc, out = _run(tmp_path, lines)
    assert rc == 0  # hook signals via stdout JSON, not exit code
    assert out is not None and out.get("decision") == "block", (
        "claiming grounded:osm with zero mcp__odoo-semantic__* calls must be blocked"
    )


def test_silent_skipper_gets_a_note_not_a_pass(tmp_path):
    """THE tightening: backend .py + zero OSM + no label must no longer slip through silently."""
    lines = [_line(content=[_tool_use("Write", "models/sale.py")])]
    rc, out = _run(tmp_path, lines)
    assert rc == 0
    assert out is not None, "silent-skipper must produce a note, not a silent pass"
    assert out.get("decision") != "block" and _note_text(out), out


def test_silent_skipper_is_not_blocked_even_with_orm_looking_code(tmp_path):
    """A note, never a block - absence of an OSM call is not a provable lie."""
    lines = [_line(content=[_tool_use("Edit", "models/account_move.py")])]
    _, out = _run(tmp_path, lines)
    assert out is not None and out.get("decision") != "block"


@pytest.mark.parametrize("osm", OSM_PREFIXES)
def test_half_grounded_gets_a_note(tmp_path, osm):
    """Backend .py written, OSM called, but ORM validators skipped -> non-blocking note."""
    lines = [
        _line(content=[_tool_use(osm + "model_inspect")]),
        _line(content=[_tool_use("Write", "models/sale.py")]),
    ]
    _, out = _run(tmp_path, lines)
    assert out.get("decision") != "block" and _note_text(out), out


def test_a_note_after_a_delivered_handback_buys_no_turn(tmp_path):
    """A report already delivered through SubagentHandback is final - nothing the subagent writes
    now reaches its caller, and no SubagentStop channel reaches anyone else - so the note is not
    emitted at all: it must never buy the subagent another turn."""
    lines = [_line(content=[_tool_use("Write", "models/sale.py")]), *handback_records("DONE")]
    _, out = _run(tmp_path, lines)
    assert out is None, f"a note after a final report still produced output: {out!r}"


def test_honest_local_source_label_passes_clean(tmp_path):
    """Backend .py + zero OSM but an explicit `grounded: local-source` label -> pass, no note."""
    lines = [
        _line(content=[_tool_use("Write", "models/sale.py")]),
        _line(content=[_text("OSM not indexed here.\ngrounded: local-source - not OSM-indexed")]),
    ]
    _, out = _run(tmp_path, lines)
    assert out is None, "an honest local-source label must not be nagged"


@pytest.mark.parametrize("osm", OSM_PREFIXES)
def test_properly_grounded_passes_clean(tmp_path, osm):
    """OSM calls made AND validators run AND claims osm -> fully grounded -> pass."""
    lines = [
        _line(content=[_tool_use(osm + "model_inspect")]),
        _line(content=[_tool_use(osm + "validate_depends")]),
        _line(content=[_tool_use("Write", "models/sale.py")]),
        _line(content=[_text("grounded: osm")]),
    ]
    _, out = _run(tmp_path, lines)
    assert out is None, "properly grounded work must pass with no note and no block"


def test_non_odoo_subagent_self_gates_to_pass(tmp_path):
    """No OSM, no .py, no grounding vocabulary -> not our concern -> silent pass."""
    lines = [
        _line(content=[_tool_use("Write", "README.md")]),
        _line(content=[_text("Updated the docs.")]),
    ]
    _, out = _run(tmp_path, lines)
    assert out is None, "a non-Odoo subagent must be approved silently"


LIE = [
    _line(content=[_tool_use("Write", "models/sale.py")]),
    _line(content=[_text("Done.\ngrounded: osm")]),
]


def test_a_continued_stop_is_still_checked_for_the_lie(tmp_path):
    """A note or block from any SubagentStop hook buys the subagent one more turn, and the report it
    ends that turn on is the one its caller receives. stop_hook_active is true on that stop - the
    lie written there must still be blocked."""
    _, out = _run(tmp_path, LIE, stop_hook_active=True)
    assert out is not None and out.get("decision") == "block", (
        "a lie written in a hook-continued turn reached the caller unchecked"
    )


def test_the_same_lie_block_is_given_once_per_continued_chain(tmp_path):
    """The loop guard: once the subagent was refused with this exact reason, the continued stop of
    that chain with the same lie passes - a block that repeats forever traps the dispatch."""
    _, first = _run(tmp_path, [brief_record(), *LIE])
    assert first is not None and first.get("decision") == "block", first
    _, again = _run(tmp_path, [brief_record(), *LIE, block_feedback_record(first["reason"]),
                                     _line(content=[_text("Done.\ngrounded: osm")])],
                    stop_hook_active=True)
    assert again is None, f"the same block was given twice: {again!r}"


def test_a_lie_in_a_resumed_dispatch_is_blocked_again(tmp_path):
    """Round 1 was refused and fixed. Later the caller resumes the subagent and its NEW report lies
    again: that is a fresh stop (no hook continued it) and a new report, so the same reason must be
    given again - a reason from an earlier round says nothing about this report."""
    _, first = _run(tmp_path, LIE)
    round_two = LIE + [block_feedback_record(first["reason"]),
                       _line(content=[_text("Done. grounded: local-source (not OSM-indexed)")]),
                       resume_record("Add the second field."),
                       _line(content=[_tool_use("Write", "models/sale_extra.py")]),
                       _line(content=[_text("Done.\ngrounded: osm")])]
    _, out = _run(tmp_path, round_two)
    assert out is not None and out.get("decision") == "block", (
        "a lie in a resumed dispatch passed because an earlier round's refusal was in the window"
    )


def test_a_lie_first_met_in_a_note_continued_turn_of_a_later_round_is_blocked(tmp_path):
    """The same reason was given in round 1. In round 2 a note buys the subagent a turn and THAT
    turn lies: the continued stop is inside a chain where this refusal was never given, so it fires
    once."""
    _, first = _run(tmp_path, LIE)
    note = _note_attachment("Grounding note: round two.")
    round_two = LIE + [block_feedback_record(first["reason"]), resume_record("Go on."),
                       _line(content=[_tool_use("Write", "models/sale_extra.py")]),
                       _line(content=[_text("Done.")]), note,
                       _line(content=[_text("Done.\ngrounded: osm")])]
    _, out = _run(tmp_path, round_two, stop_hook_active=True)
    assert out is not None and out.get("decision") == "block", out


def test_an_unreadable_transcript_never_reblocks_a_continued_stop(tmp_path):
    """An unreadable transcript holds no record of what was already said: a first stop is still
    checked (the claim is in the payload's final message), but a hook-continued stop is never
    blocked again - the missing record must not turn into a loop."""
    t = tmp_path / "agent.jsonl"
    t.write_text("\n".join(LIE) + "\n", encoding="utf-8")
    t.chmod(0)
    if os.access(t, os.R_OK):
        pytest.skip("running as a user that reads any file")

    def _stop(active):
        stdin = json.dumps({"hook_event_name": "SubagentStop", "stop_hook_active": active,
                            "transcript_path": str(t), "agent_transcript_path": str(t),
                            "last_assistant_message": "Done.\ngrounded: osm"})
        proc = subprocess.run(["bash", str(HOOK)], input=stdin, capture_output=True, text=True,
                              timeout=20)
        assert proc.returncode == 0, proc.stderr
        return proc.stdout.strip()

    assert '"block"' in _stop(False), "a first stop with the claim must still be checked"
    assert _stop(True) == "", "a continued stop was blocked again with no record to dedupe on"


def _note_attachment(text):
    """How the harness records a SubagentStop additionalContext in the subagent's own transcript."""
    return json.dumps({"type": "attachment", "attachment": {
        "type": "hook_additional_context", "content": [text], "hookName": "SubagentStop",
        "hookEvent": "SubagentStop", "toolUseID": "x"}}, ensure_ascii=False)


def test_a_grounding_note_already_in_the_context_is_not_repeated(tmp_path):
    """A subagent woken again after a stop already holds the note it got at the first stop: the
    same note is not injected again at the next stop - but a lie written in the turn the note
    bought is still blocked, on that continued stop."""
    work = [_line(content=[_tool_use("Write", "models/sale.py")])]
    _, first = _run(tmp_path, work)
    note = _note_text(first)
    _, again = _run(tmp_path, work + [_note_attachment(note), _line("user", [_text("go on")])])
    assert again is None, f"the same grounding note was repeated: {again!r}"
    lie = work + [_note_attachment(note), _line(content=[_text("Done.\ngrounded: osm")])]
    _, out = _run(tmp_path, lie, stop_hook_active=True)
    assert out is not None and out.get("decision") == "block"


# --------------------------------------------------------------------------- #
# A claim versus a mention of the label
#
# The claim is the report's own label line - a line that starts with `grounded:`, outside any code
# fence. Reviewers, test writers and corrected agents QUOTE the label all the time; blocking them
# costs a turn and makes them rewrite a truthful report.
# --------------------------------------------------------------------------- #
REVIEW_DONE = "Reviewed the diff; two findings below.\n"


@pytest.mark.parametrize("report", [
    pytest.param(REVIEW_DONE + "The test `test_lie_is_blocked` feeds `grounded: osm` with zero OSM "
                 "calls and asserts a block - it fails for the right reason.", id="backticks"),
    pytest.param(REVIEW_DONE + "- [x] ORM validation gate - not applicable. `grounded: osm` not "
                 "claimed for this static-shape change.", id="negated-checklist"),
    pytest.param(REVIEW_DONE + 'My earlier "grounded: osm" label was wrong; nothing here needed '
                 "OSM.", id="double-quotes"),
    pytest.param(REVIEW_DONE + "The fixture's report is:\n```\nDone.\ngrounded: osm\n```\n"
                 "and the hook blocks it.", id="code-fence"),
    pytest.param(REVIEW_DONE + "The coder's report ended on grounded: osm although its transcript "
                 "shows no OSM call.", id="describes-another-agent"),
    pytest.param(REVIEW_DONE + "e.g. grounded: osm is the label a fully verified worker emits.",
                 id="example"),
    pytest.param(REVIEW_DONE + "grounded: ungrounded - OSM unavailable", id="honest-ungrounded"),
    pytest.param("gap-analyzer result\ngrounded: osm=0 hybrid=0 local-source=4 unknown=1",
                 id="tally-of-zero-osm-rows"),
])
def test_a_report_that_only_mentions_the_label_is_not_blocked(tmp_path, report):
    """No OSM call and no claim of OSM grounding for this agent's own work: the label appears only
    as a quotation, an example, another agent's output, or a label that is not OSM at all."""
    _, out = _run(tmp_path, [brief_record("Review the diff.")], last_message=report)
    assert out is None or out.get("decision") != "block", (
        f"a report that only mentions the label was blocked: {out!r}"
    )


def test_a_test_writer_describing_what_its_test_checks_is_not_blocked(tmp_path):
    """The author of a grounding test names the label in its test and in its report."""
    lines = [brief_record("Write the test."),
             _line(content=[_tool_use("Write", "tests/test_grounding_gate.py")])]
    report = ("Added `test_lie_is_blocked`: a report ending on `grounded: osm` with no OSM call is "
              "blocked.\ngrounded: local-source (not OSM-indexed)")
    _, out = _run(tmp_path, lines, last_message=report)
    assert out is None or out.get("decision") != "block", out


def test_a_claim_corrected_before_a_resume_is_not_blocked_again(tmp_path):
    """Round 1 claimed `grounded: osm`, was refused and relabelled honestly. The caller resumes the
    subagent and its NEW report carries the honest label: the old claim is no longer in any report
    the caller receives, so this fresh stop passes."""
    _, first = _run(tmp_path, LIE)
    honest = "Added the second field.\ngrounded: local-source (not OSM-indexed)"
    lines = [brief_record(), *LIE, block_feedback_record(first["reason"]),
             _line(content=[_text("Done.\ngrounded: local-source (not OSM-indexed)")]),
             resume_record("Add the second field."),
             _line(content=[_tool_use("Write", "models/sale_extra.py")]),
             _line(content=[_text(honest)])]
    _, out = _run(tmp_path, lines, last_message=honest)
    assert out is None or out.get("decision") != "block", out


@pytest.mark.parametrize("label", [
    "grounded: osm",
    "- **grounded:** osm + local-source (hybrid)",
    "**Grounded**: OSM",
    "grounded: osm=3 hybrid=0 local-source=1 unknown=0",
])
def test_a_label_line_claiming_osm_without_an_osm_call_is_blocked(tmp_path, label):
    """The claim in its defined position - a line of the report that starts with the label - still
    blocks when the subagent made no OSM call, whatever list or bold markup surrounds it."""
    _, out = _run(tmp_path, [brief_record()], last_message="Added the field.\n" + label)
    assert out is not None and out.get("decision") == "block", out


@pytest.mark.parametrize("osm", OSM_PREFIXES)
def test_a_label_line_claiming_osm_with_osm_calls_passes(tmp_path, osm):
    lines = [brief_record(),
             _line(content=[_tool_use(osm + "set_active_version")]),
             _line(content=[_tool_use(osm + "model_inspect")])]
    _, out = _run(tmp_path, lines,
                  last_message="Checked sale.order.\ngrounded: osm\n```continuation\nstatus: DONE\n```")
    assert out is None, out


# --------------------------------------------------------------------------- #
# Return blocks: a claim placed where the gate reads it must block
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("report", [
    pytest.param("- walkthrough_path: /w/walkthrough.md\n- `grounded`: `osm`\n- catalog: none",
                 id="doc-scenarist-summary"),
    pytest.param("Scenarios: High=3 Med=2 Low=1\nSCENARIOS_PATH: /q/scenarios.md\ngrounded: osm",
                 id="qa-planner-summary"),
    pytest.param("cluster: sale\n  grounded: \"osm\"\n  blockers: []", id="quoted-yaml-value"),
])
def test_a_false_claim_in_a_summary_list_is_blocked(tmp_path, report):
    _, out = _run(tmp_path, [brief_record()], last_message=report)
    assert out is not None and out.get("decision") == "block", out


@pytest.mark.parametrize("label", [
    pytest.param("grounded: hybrid - OSM for core, disk for the custom module", id="hybrid"),
    pytest.param("grounded: osm=0 hybrid=4 local-source=0 unknown=0", id="hybrid-tally"),
    pytest.param("grounded: local-source=2 osm=3 hybrid=0", id="tally-any-order"),
    pytest.param("> grounded: osm", id="blockquote"),
    pytest.param("grounded: OSM - verified via model_inspect", id="osm-upper-case"),
    pytest.param("grounded: osm, checked earlier", id="osm-with-punctuation"),
    pytest.param("grounded: OSM unavailable - ungrounded", id="value-first-word-is-osm"),
])
def test_each_claim_value_without_an_osm_call_is_blocked(tmp_path, label):
    """The value is the first word - `osm` here claims OSM whatever follows; the honest form puts
    its value first (`grounded: ungrounded - OSM unavailable`)."""
    _, out = _run(tmp_path, [brief_record()], last_message="Checked the module.\n" + label)
    assert out is not None and out.get("decision") == "block", out


@pytest.mark.parametrize("report", [
    pytest.param("grounded: ungrounded - OSM unavailable", id="ungrounded"),
    pytest.param("grounded: ungrounded - OSM unavailable (OSM server down)", id="osm-in-explanation"),
    pytest.param("grounded: ungrounded - OSM error, nothing checked", id="osm-error"),
    pytest.param("- grounded: local-source - OSM unreachable earlier, now OSM-verified elsewhere",
                 id="osm-verified-in-explanation"),
    pytest.param("grounded: local-source - my previous draft said osm", id="earlier-label-noted"),
    pytest.param("grounded: unknown - neither OSM nor a checkout has it", id="unknown"),
    pytest.param("grounded: osm=0 hybrid=0 local-source=3", id="honest-tally"),
    pytest.param("| module | grounded: osm |\n|---|---|", id="table-cell"),
    pytest.param('{"module": "sale", "grounded": "osm"}', id="json-key"),
])
def test_an_honest_value_or_a_mention_passes_whatever_the_explanation_says(tmp_path, report):
    """Only the value decides; the explanation is for people, so an honest value whose explanation
    names OSM - unavailable, down, verified earlier - is never refused."""
    _, out = _run(tmp_path, [brief_record()], last_message="Checked the module.\n" + report)
    assert out is None or out.get("decision") != "block", out


@pytest.mark.parametrize("label", [
    pytest.param("grounded: OSM-verified", id="osm-variant"),
    pytest.param("grounded: verified against the index", id="free-text"),
    pytest.param("grounded: oss=2 local-source=1", id="tally-unknown-key"),
    pytest.param("grounded: local-source=2 disk=1", id="tally-bad-key-without-an-osm-count"),
])
def test_a_malformed_label_claims_nothing_and_earns_a_note(tmp_path, label):
    """A value outside the closed set states no grounding: it is never blocked as a lie, and the
    subagent still gets a note."""
    _, out = _run(tmp_path, [brief_record()], last_message="Checked the module.\n" + label)
    assert out is not None and out.get("decision") != "block" and _note_text(out), out


@pytest.mark.parametrize("label", [
    pytest.param("grounded: osm+local-source", id="plus-joined"),
    pytest.param("grounded: osm/local-source", id="slash-joined"),
    pytest.param("grounded: (osm)", id="parenthesised"),
    pytest.param("grounded: [osm]", id="bracketed"),
    pytest.param("grounded: osm=3 disk=2", id="tally-osm-beside-bad-key"),
    pytest.param("grounded: hybrid=2 standalone=1", id="tally-hybrid-beside-bad-key"),
])
def test_punctuation_or_a_bad_tally_key_does_not_hide_a_claim(tmp_path, label):
    """The value word is split at punctuation, and a positive osm or hybrid count claims OSM even
    beside a key outside the set - so a claim cannot pass as merely malformed."""
    _, out = _run(tmp_path, [brief_record()], last_message="Checked the module.\n" + label)
    assert out is not None and out.get("decision") == "block", out
