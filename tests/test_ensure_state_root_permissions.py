"""Behavioral tests for the SessionStart state-root-permission self-apply hook.

`hooks/ensure-state-root-permissions.sh` is a thin SessionStart wrapper around
`scripts/setup-steps/32-permissions-state-root.sh` - the ONE machine-level bit that
cannot ship in the repo: it idempotently self-applies the narrow state-root
Bash/Read/Write/Edit permission rules to the user's settings.json so the planning
pipeline (odoo-planner / odoo-doc-planner / intake Phase P) runs without a per-call
approval prompt. Modeled on tests/test_ensure_browser_permissions.py (its sibling hook
for the browser-MCP permission surface) and reuses tests/test_state_root_permissions.py's
throwaway-settings/throwaway-state-root fixture pattern for the step script it delegates to.

Contract under test (the hook WRAPPER's own behavior - test_state_root_permissions.py
already covers step 32's internal rule set; this file does not re-test that):

  - the hook file exists and is executable;
  - honours the ODOO_AI_NO_AUTO_PERMS=1 opt-out at the HOOK layer (no write at all, and no
    output) - belt-and-braces alongside the step script's own independent opt-out check;
  - when the step script is absent (partial/degraded install), the hook stays silent
    (exit 0, no output, no write) rather than erroring - a SessionStart hook must never
    block a session;
  - on a fresh settings file, the hook actually delegates to step 32's `apply` end-to-end
    (not mocked) and the rules land in permissions.allow[], with a structured SessionStart
    `additionalContext` JSON on stdout plus a console nudge on stderr;
  - idempotent: once `check` already passes, a second run is a silent no-op (no re-apply,
    no output) - only the FIRST apply is newsworthy;
  - runs non-interactively (stdin closed) and always exits 0 (never blocks the session).

Drives a throwaway settings.json (CLAUDE_SETTINGS) and a throwaway state root
(ODOO_AI_HOME) so neither the real ~/.claude/settings.json nor ~/.odoo-ai is ever touched.
Stdlib-only (needs bash + python3, which the delegated step script also needs).
"""
import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
HOOK = PLUGIN / "hooks" / "ensure-state-root-permissions.sh"


def _run(settings_path, odoo_ai_home, env_extra=None):
    env = dict(os.environ)
    # Deterministic regardless of the runner's own session: the hook resolves its own
    # plugin root relative to its own file location, never via $CLAUDE_PLUGIN_ROOT - but
    # strip it anyway so a stray inherited value can never leak in and mask a bug.
    env.pop("CLAUDE_PLUGIN_ROOT", None)
    env["CLAUDE_SETTINGS"] = str(settings_path)
    env["ODOO_AI_HOME"] = str(odoo_ai_home)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        ["bash", str(HOOK)],
        env=env,
        stdin=subprocess.DEVNULL,  # non-interactive: no TTY, matches a real SessionStart
        capture_output=True,
        text=True,
        timeout=60,
    )


def _allow(settings_path):
    data = json.loads(Path(settings_path).read_text(encoding="utf-8"))
    return set((data.get("permissions") or {}).get("allow") or [])


@pytest.fixture()
def settings(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text("{}", encoding="utf-8")
    return p


@pytest.fixture()
def odoo_ai_home(tmp_path):
    return tmp_path / ".odoo-ai"


def test_hook_file_present_and_executable():
    assert HOOK.is_file(), f"missing hook: {HOOK}"
    assert os.access(HOOK, os.X_OK), f"hook must be executable: {HOOK}"


def test_opt_out_writes_nothing(settings, odoo_ai_home):
    before = settings.read_text(encoding="utf-8")
    r = _run(settings, odoo_ai_home, env_extra={"ODOO_AI_NO_AUTO_PERMS": "1"})
    assert r.returncode == 0, f"opt-out must still exit 0; stderr={r.stderr}"
    assert settings.read_text(encoding="utf-8") == before, "opt-out must not modify settings"
    assert r.stdout == "", f"opt-out must produce no SessionStart output; got {r.stdout!r}"


def test_first_apply_wires_step_32_rules_into_settings(settings, odoo_ai_home):
    """End-to-end wiring, not a mock: invoking the hook against a fresh settings file must
    actually delegate to step 32's `apply` and land its Write(...) rule in
    permissions.allow[], plus emit the documented SessionStart context + console nudge."""
    r = _run(settings, odoo_ai_home)
    assert r.returncode == 0, f"hook must exit 0 even on first apply; stderr={r.stderr}"

    allow = _allow(settings)
    assert any(a.startswith("Write(") and "/projects/**" in a for a in allow), (
        f"hook must have delegated to step 32's apply and landed its projects/** Write rule; "
        f"allow={allow}"
    )

    assert r.stdout.strip(), "first apply must emit a SessionStart additionalContext JSON"
    payload = json.loads(r.stdout)
    hook_output = payload["hookSpecificOutput"]
    assert hook_output["hookEventName"] == "SessionStart"
    assert "restart" in hook_output["additionalContext"].lower(), (
        "first-apply context must instruct the documented one-time restart"
    )

    assert r.stderr.strip(), "first apply must also emit a visible console nudge on stderr"


def test_second_run_is_silent_idempotent_noop(settings, odoo_ai_home):
    """Steady state: once `check` already passes, the hook must not re-apply or print
    anything at all - only the FIRST apply is newsworthy."""
    _run(settings, odoo_ai_home)
    first_allow = _allow(settings)

    r2 = _run(settings, odoo_ai_home)
    assert r2.returncode == 0, f"second run must exit 0; stderr={r2.stderr}"
    assert _allow(settings) == first_allow, "second run must not change the allow-list"
    assert r2.stdout == "", f"already-satisfied run must print no SessionStart JSON; got {r2.stdout!r}"
    assert r2.stderr == "", f"already-satisfied run must print no console nudge; got {r2.stderr!r}"


def test_silent_when_step_script_absent(settings, odoo_ai_home, tmp_path):
    """A partial/degraded install (step 32 missing) must never block the session - the hook
    stays silent (exit 0, no output, no write) rather than erroring."""
    fake_plugin = tmp_path / "fake-plugin"
    (fake_plugin / "hooks").mkdir(parents=True)
    hook_copy = fake_plugin / "hooks" / "ensure-state-root-permissions.sh"
    hook_copy.write_text(HOOK.read_text(encoding="utf-8"), encoding="utf-8")
    hook_copy.chmod(0o755)
    # Deliberately no scripts/setup-steps/32-permissions-state-root.sh sibling.

    env = dict(os.environ)
    env.pop("CLAUDE_PLUGIN_ROOT", None)
    env["CLAUDE_SETTINGS"] = str(settings)
    env["ODOO_AI_HOME"] = str(odoo_ai_home)
    r = subprocess.run(
        ["bash", str(hook_copy)],
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, f"must exit 0 even when step 32 is absent; stderr={r.stderr}"
    assert r.stdout == "" and r.stderr == "", (
        f"must stay silent when step 32 is absent; stdout={r.stdout!r} stderr={r.stderr!r}"
    )
    assert _allow(settings) == set(), "must write nothing when step 32 is absent"
