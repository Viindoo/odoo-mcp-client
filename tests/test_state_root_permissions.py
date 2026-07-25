"""Behavioral + contract tests for `scripts/setup-steps/32-permissions-state-root.sh`.

This is the L2 setup step that auto-allows the narrow set of Bash/Read/Write/Edit
permission rules the planning pipeline (odoo-planner / odoo-doc-planner / intake
Phase P) needs to resolve and write under the machine-global state root
(`$ODOO_AI_HOME`) without a per-call approval prompt.

Modeled on tests/test_ensure_browser_permissions.py. Contract under test (the
behavior/security contract, not the implementation):

  - `describe|check|apply` subcommand contract, idempotent;
  - writes ONLY `permissions.allow[]` - never `deny[]`/`ask[]`/`additionalDirectories`;
  - never writes `mcp__odoo-semantic` (that permission's owner is
    odoo-semantic-mcp's connect command, not this step);
  - refuses to write when the target settings file is not valid JSON (exit 2);
  - honours the `ODOO_AI_NO_AUTO_PERMS=1` opt-out (no write at all);
  - targets `${CLAUDE_SETTINGS}`, never `~/.claude.json`;
  - the write rules never cover `bin/`, `venvs/`, `node_tools/`, `setup-scripts/`,
    `runtime/`, or `instances.toml` under the state root - the hard safety
    boundary (a `sitecustomize.py` under `venvs/` or an edited
    `setup-scripts/*.sh` is deferred code execution, not scratch data).

Drives a throwaway settings.json via CLAUDE_SETTINGS and a throwaway state root
via ODOO_AI_HOME so neither the real `~/.claude/settings.json` nor
`~/.odoo-ai` is ever touched. Stdlib-only (needs bash + python3).
"""
import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
STEP = PLUGIN / "scripts" / "setup-steps" / "32-permissions-state-root.sh"

EXCLUDED_SUBPATHS = ("bin/", "venvs/", "node_tools/", "setup-scripts/", "runtime/", "instances.toml")


def _run(subcmd, settings_path, odoo_ai_home, env_extra=None, stdin_devnull=True):
    env = dict(os.environ)
    # Deterministic regardless of the runner's own session: force the SCRIPT_DIR-based
    # plugin-root fallback (never inherit a caller's $CLAUDE_PLUGIN_ROOT into the test).
    env.pop("CLAUDE_PLUGIN_ROOT", None)
    env["CLAUDE_SETTINGS"] = str(settings_path)
    env["ODOO_AI_HOME"] = str(odoo_ai_home)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        ["bash", str(STEP), subcmd],
        env=env,
        stdin=subprocess.DEVNULL if stdin_devnull else None,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _allow(settings_path):
    data = json.loads(Path(settings_path).read_text(encoding="utf-8"))
    return list((data.get("permissions") or {}).get("allow") or [])


@pytest.fixture()
def settings(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text("{}", encoding="utf-8")
    return p


@pytest.fixture()
def odoo_ai_home(tmp_path):
    return tmp_path / ".odoo-ai"


def test_step_file_present_and_executable():
    assert STEP.is_file(), f"missing step script: {STEP}"
    assert os.access(STEP, os.X_OK), f"step script must be executable: {STEP}"


def test_describe_returns_nonempty_one_liner(settings, odoo_ai_home):
    r = _run("describe", settings, odoo_ai_home)
    assert r.returncode == 0, f"describe must exit 0; stderr={r.stderr}"
    assert r.stdout.strip(), "describe must print a non-empty description"
    assert "\n" not in r.stdout.strip(), "describe should be a single line"


def test_check_fails_before_apply(settings, odoo_ai_home):
    r = _run("check", settings, odoo_ai_home)
    assert r.returncode == 1, f"check must exit 1 before apply; stdout={r.stdout} stderr={r.stderr}"


def test_apply_then_check_succeeds(settings, odoo_ai_home):
    r_apply = _run("apply", settings, odoo_ai_home)
    assert r_apply.returncode == 0, f"apply must exit 0; stderr={r_apply.stderr}"
    r_check = _run("check", settings, odoo_ai_home)
    assert r_check.returncode == 0, f"check must exit 0 after apply; stderr={r_check.stderr}"


def test_apply_is_idempotent(settings, odoo_ai_home):
    _run("apply", settings, odoo_ai_home)
    first = _allow(settings)
    r2 = _run("apply", settings, odoo_ai_home)
    assert r2.returncode == 0, f"second apply must exit 0; stderr={r2.stderr}"
    assert _allow(settings) == first, "second apply changed the allow-list (not idempotent)"


def test_writes_only_permissions_allow(settings, odoo_ai_home):
    """The hard security contract: never permissions.deny[]/ask[], never additionalDirectories."""
    _run("apply", settings, odoo_ai_home)
    data = json.loads(settings.read_text(encoding="utf-8"))
    perms = data.get("permissions") or {}
    assert "deny" not in perms, f"must never write permissions.deny[]; got {perms.get('deny')}"
    assert "ask" not in perms, f"must never write permissions.ask[]; got {perms.get('ask')}"
    assert "additionalDirectories" not in data, (
        f"must never write additionalDirectories; got {data.get('additionalDirectories')}"
    )
    assert "allow" in perms and perms["allow"], "must write permissions.allow[]"


def test_never_writes_mcp_odoo_semantic(settings, odoo_ai_home):
    _run("apply", settings, odoo_ai_home)
    allow = _allow(settings)
    assert not any(a == "mcp__odoo-semantic" or a.startswith("mcp__odoo-semantic__") for a in allow), (
        f"must never write mcp__odoo-semantic (owned by odoo-semantic-mcp connect.md step 5); "
        f"allow={allow}"
    )


def test_check_reports_mcp_odoo_semantic_absence_pointer(settings, odoo_ai_home):
    r = _run("check", settings, odoo_ai_home)
    combined = r.stdout + r.stderr
    assert "mcp__odoo-semantic" in combined and "connect" in combined.lower(), (
        "check should report mcp__odoo-semantic's absence and point at the connect command "
        f"that owns it; got: {combined!r}"
    )


def test_refuses_invalid_json(settings, odoo_ai_home):
    settings.write_text("not valid json", encoding="utf-8")
    r = _run("apply", settings, odoo_ai_home)
    assert r.returncode == 2, f"apply must exit 2 on invalid JSON; stdout={r.stdout} stderr={r.stderr}"
    assert settings.read_text(encoding="utf-8") == "not valid json", (
        "must refuse to overwrite a settings file that is not valid JSON"
    )


def test_opt_out_writes_nothing(settings, odoo_ai_home):
    before = settings.read_text(encoding="utf-8")
    r = _run("apply", settings, odoo_ai_home, env_extra={"ODOO_AI_NO_AUTO_PERMS": "1"})
    assert r.returncode == 0, f"opt-out must still exit 0; stderr={r.stderr}"
    assert settings.read_text(encoding="utf-8") == before, "opt-out must not modify settings"


def test_targets_claude_settings_env_var(settings, odoo_ai_home, tmp_path):
    """Must honour CLAUDE_SETTINGS (never hard-code ~/.claude.json or the real settings.json)."""
    other = tmp_path / "other-settings.json"
    other.write_text("{}", encoding="utf-8")
    _run("apply", other, odoo_ai_home)
    assert _allow(other), "must write to the path named by $CLAUDE_SETTINGS"
    # The fixture-default settings.json (a sibling throwaway) must be untouched.
    assert json.loads(settings.read_text(encoding="utf-8")) == {}, (
        "must not write to any settings file other than the one named by $CLAUDE_SETTINGS"
    )


def test_never_hardcodes_claude_dot_json():
    """Static guard: the script's EXECUTABLE code (comments may mention it for clarity, exactly
    like 30-permissions.sh's own header does) must never read/write ~/.claude.json (the MCP
    registry step 10 owns) - permissions live only in $CLAUDE_SETTINGS (~/.claude/settings.json)."""
    code_lines = [
        ln for ln in STEP.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    offenders = [ln for ln in code_lines if ".claude.json" in ln]
    assert not offenders, (
        f"32-permissions-state-root.sh's executable code must never reference ~/.claude.json - "
        f"that is the MCP registry (owned by step 10), not the permissions file this step "
        f"writes. Offending lines: {offenders}"
    )


def test_rules_exclude_dangerous_subpaths(settings, odoo_ai_home):
    """Hard safety boundary: the Write/Edit rules must never grant blanket access to
    bin/, venvs/, node_tools/, setup-scripts/, runtime/, or instances.toml under the state
    root - each is deferred-code-execution-adjacent, not scratch data."""
    _run("apply", settings, odoo_ai_home)
    allow = _allow(settings)
    write_edit_rules = [a for a in allow if a.startswith("Write(") or a.startswith("Edit(")]
    assert write_edit_rules, "apply must write at least one Write()/Edit() rule"
    for rule in write_edit_rules:
        for excluded in EXCLUDED_SUBPATHS:
            assert excluded not in rule, (
                f"Write/Edit rule {rule!r} must not cover excluded subpath {excluded!r} - the "
                f"hard safety contract of step 32."
            )
    # And the whole allow-list, not just Write/Edit, must never wildcard the entire state root
    # (that would implicitly re-admit the excluded subpaths via a broader match).
    assert not any(a in (f"Write(/{odoo_ai_home}/**)", f"Edit(/{odoo_ai_home}/**)") for a in allow), (
        "must never grant a blanket Write/Edit over the whole state root"
    )


def test_rules_scoped_to_projects_and_worklog_only(settings, odoo_ai_home):
    _run("apply", settings, odoo_ai_home)
    allow = _allow(settings)
    write_edit_rules = [a for a in allow if a.startswith("Write(") or a.startswith("Edit(")]
    for rule in write_edit_rules:
        assert "/projects/**" in rule or "/worklog/**" in rule, (
            f"every Write/Edit rule must scope to projects/** or worklog/**; got {rule!r}"
        )


def test_bash_rules_are_exact_no_wildcard(settings, odoo_ai_home):
    _run("apply", settings, odoo_ai_home)
    allow = _allow(settings)
    bash_rules = [a for a in allow if a.startswith("Bash(")]
    assert bash_rules, "apply must write at least one Bash() rule"
    for rule in bash_rules:
        assert ":*" not in rule and rule.endswith(")"), f"Bash rule must be exact, wildcard-free: {rule!r}"
        assert "resolve_project_dir.sh" in rule, f"Bash rule must invoke resolve_project_dir.sh: {rule!r}"


def test_seven_exact_rules_written(settings, odoo_ai_home):
    """Anti-drift: exactly the 7 rules named in the P3 design, no more, no fewer."""
    _run("apply", settings, odoo_ai_home)
    allow = set(_allow(settings))
    expected = {
        f"Bash(bash {STEP.parent.parent.parent}/scripts/lib/resolve_project_dir.sh share)",
        f"Bash(bash {STEP.parent.parent.parent}/scripts/lib/resolve_project_dir.sh isolate)",
        # `//<abs-path>` = one extra leading slash over the already-absolute $ODOO_AI_HOME, the
        # Claude Code path-permission marker for an ABSOLUTE (not project-relative) match.
        f"Read(/{odoo_ai_home}/**)",
        f"Write(/{odoo_ai_home}/projects/**)",
        f"Edit(/{odoo_ai_home}/projects/**)",
        f"Write(/{odoo_ai_home}/worklog/**)",
        f"Edit(/{odoo_ai_home}/worklog/**)",
    }
    assert allow == expected, f"expected exactly {expected}, got {allow}"
