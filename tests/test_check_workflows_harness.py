"""Tests for check_workflows._driver_required_warnings() sentinel mechanism.

Business contract being protected:
- A command that references a driver-required workflow (one declaring on_complete)
  and has NO engages-run-harness sentinel MUST trigger a warning.
- A command that carries the sentinel MUST suppress the warning for that command.
- The real odoo-plan-upgrade command MUST carry the sentinel (regression guard
  for issue #93: the command previously dispatched workflow-chaining directly,
  making the on_complete handoff degrade to a human suggestion).

Tests are behavior-first (ETHOS #10): each test name states the business rule,
asserts on observable outcomes, and must fail for the right reason.
"""
import importlib.util
import pathlib
import textwrap

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
CHECK = ROOT / "plugins" / "odoo-ai-agents" / "generator" / "check_workflows.py"

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

pytestmark = pytest.mark.skipif(not HAS_YAML, reason="PyYAML not installed")


def _load():
    """Load check_workflows as a module (it is not a package)."""
    spec = importlib.util.spec_from_file_location("check_workflows_under_test", CHECK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Test 1: sentinel mechanism (isolated, uses tmp_path + monkeypatch)
# ---------------------------------------------------------------------------

_FAKE_WF = textwrap.dedent("""\
    name: fake-driver-wf
    on_complete:
      - when: "x == true"
        next: somewhere
""")

_CMD_WITHOUT_SENTINEL = textwrap.dedent("""\
    ---
    name: fake-command
    ---
    # /fake-command

    Dispatch to fake-driver-wf to do something.
""")

_CMD_WITH_SENTINEL = textwrap.dedent("""\
    ---
    name: fake-command
    ---
    # /fake-command

    <!-- engages-run-harness: routes via /odoo-intake Phase P -->

    Dispatch to fake-driver-wf to do something.
""")


def test_on_complete_command_without_sentinel_warns(tmp_path, monkeypatch):
    """A command referencing a driver-required workflow with no sentinel must produce >=1 warning."""
    wf_dir = tmp_path / "workflows"
    wf_dir.mkdir()
    (wf_dir / "fake-driver-wf.workflow.yaml").write_text(_FAKE_WF, encoding="utf-8")

    cmd_dir = tmp_path / "commands"
    cmd_dir.mkdir()
    (cmd_dir / "fake-command.md").write_text(_CMD_WITHOUT_SENTINEL, encoding="utf-8")

    mod = _load()
    monkeypatch.setattr(mod, "WORKFLOWS_DIR", wf_dir)
    monkeypatch.setattr(mod, "COMMANDS_DIR", cmd_dir)

    warnings = mod._driver_required_warnings()
    assert len(warnings) >= 1, (
        "Expected at least one driver-required warning for a command that references "
        "a driver-required workflow but carries no engages-run-harness sentinel; got none."
    )


def test_sentinel_clears_driver_required_warning(tmp_path, monkeypatch):
    """A command that carries the engages-run-harness sentinel must produce zero warnings."""
    wf_dir = tmp_path / "workflows"
    wf_dir.mkdir()
    (wf_dir / "fake-driver-wf.workflow.yaml").write_text(_FAKE_WF, encoding="utf-8")

    cmd_dir = tmp_path / "commands"
    cmd_dir.mkdir()
    (cmd_dir / "fake-command.md").write_text(_CMD_WITH_SENTINEL, encoding="utf-8")

    mod = _load()
    monkeypatch.setattr(mod, "WORKFLOWS_DIR", wf_dir)
    monkeypatch.setattr(mod, "COMMANDS_DIR", cmd_dir)

    warnings = mod._driver_required_warnings()
    assert warnings == [], (
        "Expected zero driver-required warnings when the command carries the "
        f"engages-run-harness sentinel; got: {warnings}"
    )


# ---------------------------------------------------------------------------
# Test 2: end-to-end regression guard for issue #93 (real repo dirs, no monkeypatch)
# ---------------------------------------------------------------------------


def test_no_driver_required_warnings_on_real_repo():
    """After fix, _driver_required_warnings() must return [] on the real repo.

    Regression guard for issue #93: odoo-plan-upgrade previously dispatched
    workflow-chaining directly, causing the on_complete design handoff to
    degrade to a human suggestion. The fix routes via /odoo-intake and adds
    the engages-run-harness sentinel so this check passes.
    """
    mod = _load()
    warnings = mod._driver_required_warnings()
    assert warnings == [], (
        "driver-required warnings found on real repo - at least one command "
        "references a workflow with on_complete but lacks the engages-run-harness "
        f"sentinel:\n" + "\n".join(warnings)
    )
