"""Behavioral guard for hooks/enforce-grounding.sh (SubagentStop grounding enforcement).

These tests protect the BEHAVIOR contract of the hook (ETHOS#11) for its consumer - an
AI subagent (odoo-coder / odoo-frontend-coder / odoo-code-reviewer). Each test states the
business rule it locks in and fails for exactly one reason: that rule changed.

The contract under test:
- BLOCK only the provable lie: artifact claims `grounded: osm` with ZERO mcp__odoo-semantic__*
  calls.
- NOTE (non-blocking) the half-grounded case: backend .py written, OSM called, ORM validators
  skipped.
- NOTE (non-blocking) the SILENT-SKIPPER: backend .py written with zero OSM calls and no
  grounding label. (Deliberately a note, not a block - a block there only manufactures
  unverifiable `grounded: local-source` labels and false-blocks legit pure-python/standalone
  work. The hard quality gate is Odoo's test_lint/test_pylint CI module, not OSM-call-count.)
- PASS (stay out of the way): non-Odoo subagents (self-gate), honest local-source label,
  properly grounded work, and any loop re-entry (stop_hook_active).

Run with: python3.11 -m pytest tests/test_enforce_grounding.py -v
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / "plugins" / "odoo-ai-agents" / "hooks" / "enforce-grounding.sh"

pytestmark = pytest.mark.skipif(
    shutil.which("jq") is None or shutil.which("bash") is None,
    reason="enforce-grounding.sh needs jq + bash; absent here (the hook itself degrades to pass)",
)


def _line(role="assistant", content=None):
    return json.dumps({"role": role, "content": content or []})


def _tool_use(name, file_path=None):
    inp = {"file_path": file_path} if file_path else {}
    return {"type": "tool_use", "name": name, "input": inp}


def _text(s):
    return {"type": "text", "text": s}


def _run(tmp_path, transcript_lines, stop_hook_active=False):
    """Invoke the hook with a crafted transcript + stdin; return (rc, parsed_stdout_or_None)."""
    tpath = tmp_path / "transcript.jsonl"
    tpath.write_text("\n".join(transcript_lines) + "\n", encoding="utf-8")
    stdin = json.dumps({"transcript_path": str(tpath), "stop_hook_active": stop_hook_active})
    proc = subprocess.run(
        ["bash", str(HOOK)], input=stdin, capture_output=True, text=True, timeout=20
    )
    out = proc.stdout.strip()
    parsed = json.loads(out) if out else None
    return proc.returncode, parsed


def test_hook_exists_and_is_executable_shell():
    assert HOOK.exists(), f"hook not found at {HOOK}"
    assert HOOK.read_text(encoding="utf-8").startswith("#!"), "hook must be a shell script"


def test_lie_is_blocked(tmp_path):
    """Claims `grounded: osm` but made ZERO OSM calls -> the one provable lie -> BLOCK."""
    lines = [
        _line(content=[_tool_use("Write", "models/sale.py")]),
        _line(content=[_text("Done. grounded: osm")]),
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
    assert out.get("continue") is True and "systemMessage" in out, (
        "silent-skipper must be a NON-blocking note (continue:true + systemMessage)"
    )
    assert "decision" not in out, "silent-skipper must NOT be blocked"


def test_silent_skipper_is_not_blocked_even_with_orm_looking_code(tmp_path):
    """A note, never a block - absence of an OSM call is not a provable lie."""
    lines = [_line(content=[_tool_use("Edit", "models/account_move.py")])]
    _, out = _run(tmp_path, lines)
    assert out is not None and out.get("decision") != "block"


def test_half_grounded_gets_a_note(tmp_path):
    """Backend .py written, OSM called, but ORM validators skipped -> non-blocking note."""
    lines = [
        _line(content=[_tool_use("mcp__odoo-semantic__model_inspect")]),
        _line(content=[_tool_use("Write", "models/sale.py")]),
    ]
    _, out = _run(tmp_path, lines)
    assert out is not None and out.get("continue") is True and "decision" not in out


def test_honest_local_source_label_passes_clean(tmp_path):
    """Backend .py + zero OSM but an explicit `grounded: local-source` label -> pass, no note."""
    lines = [
        _line(content=[_tool_use("Write", "models/sale.py")]),
        _line(content=[_text("OSM not indexed here. grounded: local-source (not OSM-indexed)")]),
    ]
    _, out = _run(tmp_path, lines)
    assert out is None, "an honest local-source label must not be nagged"


def test_properly_grounded_passes_clean(tmp_path):
    """OSM calls made AND validators run AND claims osm -> fully grounded -> pass."""
    lines = [
        _line(content=[_tool_use("mcp__odoo-semantic__model_inspect")]),
        _line(content=[_tool_use("mcp__odoo-semantic__validate_depends")]),
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


def test_loop_guard_never_re_blocks(tmp_path):
    """stop_hook_active=true means we already forced one continue -> never block again."""
    lines = [
        _line(content=[_tool_use("Write", "models/sale.py")]),
        _line(content=[_text("grounded: osm")]),  # would be a BLOCK on first pass
    ]
    _, out = _run(tmp_path, lines, stop_hook_active=True)
    assert out is None, "with stop_hook_active=true the hook must stay out of the way (no loop)"
