"""Behavioral + contract tests for `scripts/setup-steps/32-permissions-state-root.sh`.

This is the L2 setup step that auto-allows the narrow set of Bash/Read/Edit
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
    """Hard safety boundary: the file-editing path rules must never grant blanket access to
    bin/, venvs/, node_tools/, setup-scripts/, runtime/, or instances.toml under the state
    root - each is deferred-code-execution-adjacent, not scratch data.

    The filter stays deliberately wide (`Write(` OR `Edit(`) so this boundary still binds a
    stray `Write(<path>)` rule if one is ever re-added - even though the shipped set is
    Edit-only (see test_no_write_path_rule_is_ever_written)."""
    _run("apply", settings, odoo_ai_home)
    allow = _allow(settings)
    write_edit_rules = [a for a in allow if a.startswith("Write(") or a.startswith("Edit(")]
    assert write_edit_rules, "apply must write at least one file-editing path rule"
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


def test_rules_scoped_to_projects_only(settings, odoo_ai_home):
    """File-editing path rules cover ONLY `projects/**`. Per state-root-resolution.md, both the
    plan (SHARE, `<repo-key>/plans/`) and the per-worktree worklog (ISOLATE,
    `<repo-key>/worktrees/<wt-key>/worklog/`) resolve NESTED under `projects/**` - there is no
    separate top-level `worklog/` directory, so a rule scoped to it alone (without also matching
    `/projects/**`) would never cover any real write path."""
    _run("apply", settings, odoo_ai_home)
    allow = _allow(settings)
    write_edit_rules = [a for a in allow if a.startswith("Write(") or a.startswith("Edit(")]
    assert write_edit_rules, "apply must write at least one file-editing path rule"
    for rule in write_edit_rules:
        assert "/projects/**" in rule, (
            f"every file-editing path rule must scope to projects/** (the plan and worklog both "
            f"resolve nested under it); got {rule!r}"
        )


def test_bash_rules_are_exact_no_wildcard(settings, odoo_ai_home):
    _run("apply", settings, odoo_ai_home)
    allow = _allow(settings)
    bash_rules = [a for a in allow if a.startswith("Bash(")]
    assert bash_rules, "apply must write at least one Bash() rule"
    for rule in bash_rules:
        assert ":*" not in rule and rule.endswith(")"), f"Bash rule must be exact, wildcard-free: {rule!r}"
        assert "resolve_project_dir.sh" in rule, f"Bash rule must invoke resolve_project_dir.sh: {rule!r}"


def test_no_write_path_rule_is_ever_written(settings, odoo_ai_home):
    """Regression guard: this step must NEVER emit a `Write(<path>)` rule.

    Claude Code's file-permission check matches PATH rules on `Edit(path)` ONLY - an
    `Edit(path)` rule already covers every file-editing tool, Write included. A
    `Write(<path>)` rule therefore matches nothing AND makes the CLI print a warning at
    every launch:

        Permission allow rule (.claude/settings.json): Write(<path>) is not matched by
        file permission checks - only Edit(path) rules are.

    That warning was self-healing against the user: hooks/ensure-state-root-permissions.sh
    re-runs this step's `check` on every SessionStart, so deleting the offending entry by
    hand failed `check`, the hook re-`apply`ed, and the warning came back next launch. The
    fix is to never write the rule at all - hence this test, which fails the moment a
    `Write(` path rule reappears in the RULES SSOT."""
    _run("apply", settings, odoo_ai_home)
    allow = _allow(settings)
    offenders = [a for a in allow if a.startswith("Write(")]
    assert not offenders, (
        f"step 32 must never write a Write(<path>) rule - Edit(path) already covers every "
        f"file-editing tool, and Write(path) only earns a per-launch CLI warning. "
        f"Offenders: {offenders}"
    )


def test_apply_prunes_prior_version_bash_rules(settings, odoo_ai_home, tmp_path):
    """Regression guard for the version-pinned rule leak: `${PLUGIN_ROOT}` in
    the two Bash rules resolves to the INSTALLED plugin version's own directory,
    so a naive re-apply on every upgrade keeps ADDING a new pair of rules and
    never removes the previous pair. Installing version B's rules must PRUNE
    version A's rule for the identical script (same trailing
    `scripts/lib/resolve_project_dir.sh <arg>)` suffix), not accumulate
    alongside it."""
    version_a = tmp_path / "plugins" / "cache" / "viindoo-plugins" / "odoo-ai-agents" / "4.18.0"
    version_b = tmp_path / "plugins" / "cache" / "viindoo-plugins" / "odoo-ai-agents" / "4.20.0"
    version_a.mkdir(parents=True)
    version_b.mkdir(parents=True)

    r_a = _run("apply", settings, odoo_ai_home, env_extra={"CLAUDE_PLUGIN_ROOT": str(version_a)})
    assert r_a.returncode == 0, f"apply for version A must exit 0; stderr={r_a.stderr}"
    bash_after_a = [a for a in _allow(settings) if a.startswith("Bash(")]
    assert bash_after_a == [
        f"Bash(bash {version_a}/scripts/lib/resolve_project_dir.sh share)",
        f"Bash(bash {version_a}/scripts/lib/resolve_project_dir.sh isolate)",
    ], f"unexpected state after applying version A: {bash_after_a}"

    r_b = _run("apply", settings, odoo_ai_home, env_extra={"CLAUDE_PLUGIN_ROOT": str(version_b)})
    assert r_b.returncode == 0, f"apply for version B must exit 0; stderr={r_b.stderr}"
    bash_after_b = [a for a in _allow(settings) if a.startswith("Bash(")]
    assert bash_after_b == [
        f"Bash(bash {version_b}/scripts/lib/resolve_project_dir.sh share)",
        f"Bash(bash {version_b}/scripts/lib/resolve_project_dir.sh isolate)",
    ], (
        f"installing version B's rules must PRUNE version A's rules for the "
        f"same script, not accumulate alongside them; got {bash_after_b}"
    )


def test_apply_across_three_versions_stays_at_two_bash_rules(settings, odoo_ai_home, tmp_path):
    """Reproduces the exact reported shape (3 plugin versions -> 6 accumulated
    rules pre-fix) and proves convergence: after installing N successive
    versions, exactly 2 Bash rules (share + isolate) survive - the CURRENT
    version's - never one pair per version ever installed."""
    versions = ["4.18.0", "4.18.1", "4.20.0"]
    roots = [tmp_path / "plugins" / v for v in versions]
    for root in roots:
        root.mkdir(parents=True)
    for root in roots:
        r = _run("apply", settings, odoo_ai_home, env_extra={"CLAUDE_PLUGIN_ROOT": str(root)})
        assert r.returncode == 0, f"apply for {root} must exit 0; stderr={r.stderr}"

    bash_rules = [a for a in _allow(settings) if a.startswith("Bash(")]
    assert len(bash_rules) == 2, (
        f"after installing {len(versions)} successive plugin versions, exactly "
        f"2 Bash rules for the CURRENT version must remain, not one pair per "
        f"version ever installed; got {bash_rules}"
    )
    last_root = roots[-1]
    assert set(bash_rules) == {
        f"Bash(bash {last_root}/scripts/lib/resolve_project_dir.sh share)",
        f"Bash(bash {last_root}/scripts/lib/resolve_project_dir.sh isolate)",
    }


def test_apply_same_version_after_prune_is_idempotent(settings, odoo_ai_home, tmp_path):
    """Re-running apply for the SAME (already-current) version after a prune
    must change nothing - the prune itself must not become a new source of
    non-idempotency."""
    version_a = tmp_path / "plugins" / "4.18.0"
    version_b = tmp_path / "plugins" / "4.20.0"
    version_a.mkdir(parents=True)
    version_b.mkdir(parents=True)
    _run("apply", settings, odoo_ai_home, env_extra={"CLAUDE_PLUGIN_ROOT": str(version_a)})
    _run("apply", settings, odoo_ai_home, env_extra={"CLAUDE_PLUGIN_ROOT": str(version_b)})
    after_first_b = _allow(settings)

    r2 = _run("apply", settings, odoo_ai_home, env_extra={"CLAUDE_PLUGIN_ROOT": str(version_b)})
    assert r2.returncode == 0, f"second apply for the same version must exit 0; stderr={r2.stderr}"
    assert _allow(settings) == after_first_b, (
        "re-applying the SAME version after a prune must not change the allow-list"
    )


def test_check_detects_stale_prior_version_bash_rule(settings, odoo_ai_home, tmp_path):
    """`check` must fail while a stale prior-version Bash rule for the same
    script remains in permissions.allow[], even when the CURRENT version's
    rules are already present too - otherwise a machine that already has both
    (the exact accumulated-bug state) never re-triggers `apply` to prune it,
    since the SessionStart hook only calls `apply` when `check` fails."""
    version_a = tmp_path / "plugins" / "4.18.0"
    version_b = tmp_path / "plugins" / "4.20.0"
    version_a.mkdir(parents=True)
    version_b.mkdir(parents=True)
    data = {
        "permissions": {
            "allow": [
                f"Bash(bash {version_a}/scripts/lib/resolve_project_dir.sh share)",
                f"Bash(bash {version_a}/scripts/lib/resolve_project_dir.sh isolate)",
                f"Bash(bash {version_b}/scripts/lib/resolve_project_dir.sh share)",
                f"Bash(bash {version_b}/scripts/lib/resolve_project_dir.sh isolate)",
                f"Read(/{odoo_ai_home}/**)",
                f"Edit(/{odoo_ai_home}/projects/**)",
            ]
        }
    }
    settings.write_text(json.dumps(data), encoding="utf-8")

    r = _run("check", settings, odoo_ai_home, env_extra={"CLAUDE_PLUGIN_ROOT": str(version_b)})
    assert r.returncode == 1, (
        f"check must fail while a stale prior-version Bash rule remains, even "
        f"though the current version's own rules are already present; "
        f"stdout={r.stdout} stderr={r.stderr}"
    )

    # And after apply prunes it, check must now pass.
    r_apply = _run("apply", settings, odoo_ai_home, env_extra={"CLAUDE_PLUGIN_ROOT": str(version_b)})
    assert r_apply.returncode == 0, f"apply must exit 0; stderr={r_apply.stderr}"
    r_check = _run("check", settings, odoo_ai_home, env_extra={"CLAUDE_PLUGIN_ROOT": str(version_b)})
    assert r_check.returncode == 0, (
        f"check must pass once apply has pruned the stale rule; "
        f"stdout={r_check.stdout} stderr={r_check.stderr}"
    )


def test_prune_never_prunes_different_plugin_same_script(settings, odoo_ai_home, tmp_path):
    """Anchoring regression guard - covers all 5 required cases in one pass.

    An earlier revision of the prune matcher keyed off the script SUFFIX only
    (`allow[].endswith(".../resolve_project_dir.sh share)")`), with no check
    that the matched rule actually belonged to THIS plugin. Reproduced
    directly against that suffix-only subcommand: seeding a decoy rule for a
    DIFFERENT plugin (`other-plugin/1.0`) that happens to ship an
    identically-named+argued script, then applying THIS plugin's version
    4.20.2 rule, deleted the other plugin's rule too - a real permission the
    other plugin's user had approved away, gone with no indication why. This
    test seeds that exact decoy (plus 3 more) and asserts the anchored
    matcher gets all 5 required cases right:

      1. same plugin, different version  -> PRUNED
      2. different plugin, same script   -> UNTOUCHED (the case that slipped through)
      3. same plugin, different script   -> UNTOUCHED
      4. user's own hand-written rules   -> UNTOUCHED
      (case 5, a --plugin-dir dev checkout with no version segment, is
      covered separately by test_dev_checkout_without_version_segment_skips_pruning_safely)
    """
    cache_root = tmp_path / "plugins" / "cache" / "viindoo-plugins"
    version_a = cache_root / "odoo-ai-agents" / "4.18.0"  # THIS plugin, prior version
    version_b = cache_root / "odoo-ai-agents" / "4.20.2"  # THIS plugin, current version
    other_plugin = cache_root / "other-plugin" / "1.0"  # a DIFFERENT plugin
    for d in (version_a, version_b, other_plugin):
        d.mkdir(parents=True)

    same_plugin_prior_version = f"Bash(bash {version_a}/scripts/lib/resolve_project_dir.sh share)"
    different_plugin_same_script = f"Bash(bash {other_plugin}/scripts/lib/resolve_project_dir.sh share)"
    same_plugin_different_script = f"Bash(bash {version_a}/scripts/lib/some_other_script.sh share)"
    hand_written = ["Bash(sudo *)", "Read(**)", "Bash(git commit:*)", "mcp__some-other-server__tool"]

    seed = [same_plugin_prior_version, different_plugin_same_script, same_plugin_different_script, *hand_written]
    data = {"permissions": {"allow": list(seed)}}
    settings.write_text(json.dumps(data), encoding="utf-8")

    r = _run("apply", settings, odoo_ai_home, env_extra={"CLAUDE_PLUGIN_ROOT": str(version_b)})
    assert r.returncode == 0, f"apply must exit 0; stderr={r.stderr}"
    allow = _allow(settings)

    # Case 1: same plugin, different version -> PRUNED.
    assert same_plugin_prior_version not in allow, (
        f"stale same-plugin prior-version rule must be pruned; still present in {allow}"
    )
    # Case 2: different plugin, same script -> UNTOUCHED (the bug this guards).
    assert different_plugin_same_script in allow, (
        f"a DIFFERENT plugin's rule for an identically-suffixed script must NEVER be pruned "
        f"just because it shares the script suffix; missing from {allow}"
    )
    # Case 3: same plugin, different script -> UNTOUCHED.
    assert same_plugin_different_script in allow, (
        f"a different script under the SAME plugin must not be pruned; missing from {allow}"
    )
    # Case 4: user's own hand-written rules -> UNTOUCHED.
    for u in hand_written:
        assert u in allow, f"apply must never remove a user's hand-written rule: {u!r} missing from {allow}"
    # And the current version's own rule was added.
    assert f"Bash(bash {version_b}/scripts/lib/resolve_project_dir.sh share)" in allow


def test_dev_checkout_without_version_segment_skips_pruning_safely(settings, odoo_ai_home, tmp_path):
    """Case 5: a --plugin-dir dev checkout has no version segment in
    $PLUGIN_ROOT (its last path component is the plugin name, e.g.
    "odoo-ai-agents", not a MAJOR.MINOR.PATCH version). Pruning must be
    skipped entirely in that case - not attempted with a guessed anchor -
    because there is no reliable way to tell which path segment IS the
    version, so pruning could otherwise strip the wrong segment and either
    prune nothing meaningful or (worse) widen the anchor. Must not prune an
    existing marketplace-cache rule for the SAME plugin, and must not crash."""
    marketplace_version = tmp_path / "plugins" / "cache" / "viindoo-plugins" / "odoo-ai-agents" / "4.18.0"
    dev_checkout = tmp_path / "worktrees" / "some-feature-branch" / "plugins" / "odoo-ai-agents"
    marketplace_version.mkdir(parents=True)
    dev_checkout.mkdir(parents=True)

    marketplace_rule = f"Bash(bash {marketplace_version}/scripts/lib/resolve_project_dir.sh share)"
    data = {"permissions": {"allow": [marketplace_rule]}}
    settings.write_text(json.dumps(data), encoding="utf-8")

    r = _run("apply", settings, odoo_ai_home, env_extra={"CLAUDE_PLUGIN_ROOT": str(dev_checkout)})
    assert r.returncode == 0, f"apply from a dev checkout must not crash; stderr={r.stderr}"

    allow = _allow(settings)
    assert marketplace_rule in allow, (
        f"a dev checkout (no version segment) must NEVER prune a marketplace-cache rule for "
        f"the same plugin - the version segment cannot be safely identified, so pruning must "
        f"be skipped entirely rather than guessed; missing from {allow}"
    )
    assert f"Bash(bash {dev_checkout}/scripts/lib/resolve_project_dir.sh share)" in allow, (
        "the dev checkout's own rule must still be added (plain add, no pruning)"
    )


def test_four_exact_rules_written(settings, odoo_ai_home):
    """Anti-drift: exactly the 4 rules that cover a REAL write path, no more, no fewer.

    History of this set:
      - A 7-rule version added a separate `Write/Edit(/${ODOO_AI_HOME}/worklog/**)` pair.
        Dead weight: per state-root-resolution.md the per-worktree worklog resolves at
        `<repo-key>/worktrees/<wt-key>/worklog/` - NESTED under `projects/**`, never at a
        bare top-level `worklog/`. Dropped -> 5 rules.
      - The 5-rule version still paired `Write(...projects/**)` with `Edit(...projects/**)`.
        The Write half matches nothing in Claude Code's path-permission layer and triggers
        a per-launch CLI warning (see test_no_write_path_rule_is_ever_written). Dropped ->
        the 4 rules below; `Edit(...)` alone already covers Write and every other
        file-editing tool."""
    _run("apply", settings, odoo_ai_home)
    allow = set(_allow(settings))
    expected = {
        f"Bash(bash {STEP.parent.parent.parent}/scripts/lib/resolve_project_dir.sh share)",
        f"Bash(bash {STEP.parent.parent.parent}/scripts/lib/resolve_project_dir.sh isolate)",
        # `//<abs-path>` = one extra leading slash over the already-absolute $ODOO_AI_HOME, the
        # Claude Code path-permission marker for an ABSOLUTE (not project-relative) match.
        f"Read(/{odoo_ai_home}/**)",
        f"Edit(/{odoo_ai_home}/projects/**)",
    }
    assert allow == expected, f"expected exactly {expected}, got {allow}"


# ---------------------------------------------------------------------------
# Subsumption - do not add a rule the user already has
# ---------------------------------------------------------------------------
#
# Root cause this guards: on a machine whose permissions.allow[] already
# contains a blanket like Bash(*)/Read/Edit, ALL FOUR of this step's rules
# were redundant the moment they were first written - version-pinning aside.
# `apply` must check every rule against config_merge.py json-rule-covered
# before writing it, and `check` must agree with whatever `apply` decided (a
# rule apply skips as covered must not make check report incompleteness, or
# the SessionStart hook loops).
#
# The bias is deliberately asymmetric: wrongly concluding "covered" silently
# withholds a needed permission (breaks function); wrongly concluding "not
# covered" only writes one harmless redundant rule (visible, self-correcting
# clutter). So only a small, explicitly enumerated set of forms - grounded in
# https://code.claude.com/docs/en/permissions, re-verified for this change,
# not assumed from one user's settings shape - counts as coverage. Notably,
# a bare relative `Read(**)`/`Edit(**)` (no `//` or `~/` anchor) is NOT one
# of them: the docs state "To allow all file access, use only the tool name
# without parentheses: `Read`, `Edit`, or `Write`" - a parenthesized `(**)`
# pattern is anchored to the SESSION's actual working directory at match
# time, not the filesystem root, so it cannot be proven ahead of time to
# contain an absolute target path like $ODOO_AI_HOME.


def test_apply_skips_exact_duplicate_no_write_at_all(settings, odoo_ai_home, tmp_path):
    """Covered by an exact duplicate -> not (re-)added. Isolated with the
    other 3 rules ALSO already covered (by blankets), so that when the
    fourth (Edit) is additionally an exact duplicate, apply performs zero
    writes overall - proving the exact-duplicate path truly short-circuits
    rather than merely being idempotent after a write."""
    plugin_root = tmp_path / "plugins" / "4.20.2"
    plugin_root.mkdir(parents=True)
    edit_rule = f"Edit(/{odoo_ai_home}/projects/**)"
    data = {"permissions": {"allow": ["Bash(*)", "Read", edit_rule]}}
    settings.write_text(json.dumps(data), encoding="utf-8")

    r = _run("apply", settings, odoo_ai_home, env_extra={"CLAUDE_PLUGIN_ROOT": str(plugin_root)})
    assert r.returncode == 0, f"apply must exit 0; stderr={r.stderr}"
    assert _allow(settings).count(edit_rule) == 1, "exact duplicate must not be re-added"
    assert not list(settings.parent.glob(f"{settings.name}.bak.*")), (
        "with all 4 rules already covered (3 by blanket, 1 by exact duplicate), apply must "
        "perform zero writes and thus create no backup at all"
    )

    r_check = _run("check", settings, odoo_ai_home, env_extra={"CLAUDE_PLUGIN_ROOT": str(plugin_root)})
    assert r_check.returncode == 0, f"check must agree everything is already satisfied; stderr={r_check.stderr}"


def test_apply_skips_bash_rules_covered_by_bash_blanket(settings, odoo_ai_home, tmp_path):
    """Covered by Bash(*) -> neither Bash rule is added, and check agrees."""
    plugin_root = tmp_path / "plugins" / "4.20.2"
    plugin_root.mkdir(parents=True)
    settings.write_text(json.dumps({"permissions": {"allow": ["Bash(*)"]}}), encoding="utf-8")

    r = _run("apply", settings, odoo_ai_home, env_extra={"CLAUDE_PLUGIN_ROOT": str(plugin_root)})
    assert r.returncode == 0, f"apply must exit 0; stderr={r.stderr}"
    allow = _allow(settings)
    assert [a for a in allow if a.startswith("Bash(") and a != "Bash(*)"] == [], (
        f"both Bash rules must be skipped as covered by Bash(*); got {allow}"
    )
    assert "Bash(*)" in allow

    r_check = _run("check", settings, odoo_ai_home, env_extra={"CLAUDE_PLUGIN_ROOT": str(plugin_root)})
    assert r_check.returncode == 0, f"check must agree Bash(*) already covers both Bash rules; stderr={r_check.stderr}"


def test_apply_skips_read_edit_covered_by_bare_tool_blanket(settings, odoo_ai_home, tmp_path):
    """Covered by a bare "Read"/"Edit" (no parentheses) -> not added, and
    check agrees. Documented: "Read | Matches all file reads" / "To allow
    all file access, use only the tool name without parentheses"."""
    plugin_root = tmp_path / "plugins" / "4.20.2"
    plugin_root.mkdir(parents=True)
    settings.write_text(json.dumps({"permissions": {"allow": ["Read", "Edit"]}}), encoding="utf-8")

    r = _run("apply", settings, odoo_ai_home, env_extra={"CLAUDE_PLUGIN_ROOT": str(plugin_root)})
    assert r.returncode == 0, f"apply must exit 0; stderr={r.stderr}"
    allow = _allow(settings)
    assert not any(a.startswith("Read(") for a in allow), f"Read rule must be skipped; got {allow}"
    assert not any(a.startswith("Edit(") for a in allow), f"Edit rule must be skipped; got {allow}"

    r_check = _run("check", settings, odoo_ai_home, env_extra={"CLAUDE_PLUGIN_ROOT": str(plugin_root)})
    assert r_check.returncode == 0, f"check must agree bare Read/Edit already cover both rules; stderr={r_check.stderr}"


def test_apply_skips_read_covered_by_absolute_ancestor_glob(settings, odoo_ai_home, tmp_path):
    """Covered by an existing Read(//<ancestor>/**) whose anchor is a strict
    parent directory of $ODOO_AI_HOME - provable by plain string containment
    since both sides are filesystem-root anchored (the "//" form), with no
    dependency on any session's working directory."""
    plugin_root = tmp_path / "plugins" / "4.20.2"
    plugin_root.mkdir(parents=True)
    ancestor_rule = f"Read(/{odoo_ai_home.parent}/**)"
    settings.write_text(json.dumps({"permissions": {"allow": [ancestor_rule]}}), encoding="utf-8")

    r = _run("apply", settings, odoo_ai_home, env_extra={"CLAUDE_PLUGIN_ROOT": str(plugin_root)})
    assert r.returncode == 0, f"apply must exit 0; stderr={r.stderr}"
    allow = _allow(settings)
    assert f"Read(/{odoo_ai_home}/**)" not in allow, (
        f"the specific Read rule must be skipped - an ancestor directory rule already covers it; got {allow}"
    )
    assert ancestor_rule in allow

    r_check = _run("check", settings, odoo_ai_home, env_extra={"CLAUDE_PLUGIN_ROOT": str(plugin_root)})
    assert r_check.returncode == 0, f"check must agree the ancestor rule covers Read; stderr={r_check.stderr}"


def test_apply_skips_bash_covered_by_prefix_wildcard(settings, odoo_ai_home, tmp_path):
    """Covered by an existing Bash(<literal-prefix> *) trailing-wildcard rule
    - the documented Bash prefix-match form - that happens to cover both the
    "share" and "isolate" argument variants."""
    plugin_root = tmp_path / "plugins" / "4.20.2"
    plugin_root.mkdir(parents=True)
    prefix_rule = f"Bash(bash {plugin_root}/scripts/lib/resolve_project_dir.sh *)"
    settings.write_text(json.dumps({"permissions": {"allow": [prefix_rule]}}), encoding="utf-8")

    r = _run("apply", settings, odoo_ai_home, env_extra={"CLAUDE_PLUGIN_ROOT": str(plugin_root)})
    assert r.returncode == 0, f"apply must exit 0; stderr={r.stderr}"
    allow = _allow(settings)
    assert f"Bash(bash {plugin_root}/scripts/lib/resolve_project_dir.sh share)" not in allow
    assert f"Bash(bash {plugin_root}/scripts/lib/resolve_project_dir.sh isolate)" not in allow
    assert prefix_rule in allow

    r_check = _run("check", settings, odoo_ai_home, env_extra={"CLAUDE_PLUGIN_ROOT": str(plugin_root)})
    assert r_check.returncode == 0, f"check must agree the prefix-wildcard rule covers both Bash rules; stderr={r_check.stderr}"


def test_relative_double_star_is_not_treated_as_coverage_still_added(settings, odoo_ai_home, tmp_path):
    """A bare relative Read(**)/Edit(**) (no `//` or `~/` anchor) must NOT be
    treated as coverage, even though it looks like an obvious blanket. Per
    the docs, only the tool name WITHOUT parentheses allows all file access;
    a parenthesized "(**)" pattern is anchored at the session's actual
    working directory at match time, not the filesystem root - it cannot be
    proven ahead of time to contain $ODOO_AI_HOME. Treating it as coverage
    would risk silently withholding the permission - the conservative bias
    says: when in doubt, still add the rule."""
    plugin_root = tmp_path / "plugins" / "4.20.2"
    plugin_root.mkdir(parents=True)
    settings.write_text(json.dumps({"permissions": {"allow": ["Read(**)", "Edit(**)"]}}), encoding="utf-8")

    r = _run("apply", settings, odoo_ai_home, env_extra={"CLAUDE_PLUGIN_ROOT": str(plugin_root)})
    assert r.returncode == 0, f"apply must exit 0; stderr={r.stderr}"
    allow = _allow(settings)
    assert f"Read(/{odoo_ai_home}/**)" in allow, (
        f"bare relative Read(**) must NOT be treated as coverage - the Read rule must still be added; got {allow}"
    )
    assert f"Edit(/{odoo_ai_home}/projects/**)" in allow, (
        f"bare relative Edit(**) must NOT be treated as coverage - the Edit rule must still be added; got {allow}"
    )


def test_apply_ambiguous_pattern_not_recognized_still_added(settings, odoo_ai_home, tmp_path):
    """A pattern outside the small enumerated set - here, a Bash rule with an
    embedded wildcard NOT in the documented trailing-wildcard position - is
    NOT recognized as coverage. The conservative direction: still add the
    rule rather than guess."""
    plugin_root = tmp_path / "plugins" / "4.20.2"
    plugin_root.mkdir(parents=True)
    ambiguous_rule = f"Bash(bash */scripts/lib/resolve_project_dir.sh share)"
    settings.write_text(json.dumps({"permissions": {"allow": [ambiguous_rule]}}), encoding="utf-8")

    r = _run("apply", settings, odoo_ai_home, env_extra={"CLAUDE_PLUGIN_ROOT": str(plugin_root)})
    assert r.returncode == 0, f"apply must exit 0; stderr={r.stderr}"
    allow = _allow(settings)
    assert f"Bash(bash {plugin_root}/scripts/lib/resolve_project_dir.sh share)" in allow, (
        f"an unrecognized wildcard shape must not be treated as coverage - the rule must still be added; got {allow}"
    )


def test_not_covered_at_all_everything_added(settings, odoo_ai_home, tmp_path):
    """Baseline: nothing in allow[] covers anything -> all 4 rules are added,
    matching the pre-subsumption behavior for the genuinely-uncovered case."""
    plugin_root = tmp_path / "plugins" / "4.20.2"
    plugin_root.mkdir(parents=True)

    r = _run("apply", settings, odoo_ai_home, env_extra={"CLAUDE_PLUGIN_ROOT": str(plugin_root)})
    assert r.returncode == 0, f"apply must exit 0; stderr={r.stderr}"
    allow = set(_allow(settings))
    expected = {
        f"Bash(bash {plugin_root}/scripts/lib/resolve_project_dir.sh share)",
        f"Bash(bash {plugin_root}/scripts/lib/resolve_project_dir.sh isolate)",
        f"Read(/{odoo_ai_home}/**)",
        f"Edit(/{odoo_ai_home}/projects/**)",
    }
    assert allow == expected, f"expected exactly {expected}, got {allow}"


def test_stale_rule_pruned_even_when_current_rule_skipped_as_covered(settings, odoo_ai_home, tmp_path):
    """Interaction between pruning and subsumption: a stale prior-version
    Bash rule must still be REMOVED even when the CURRENT version's own rule
    is skipped as already covered by a blanket. Leaving the stale rule in
    place would not be defensible - it grants nothing a broader existing
    permission does not already cover, and is exactly the accumulation this
    step exists to fix."""
    version_a = tmp_path / "plugins" / "4.18.0"
    version_b = tmp_path / "plugins" / "4.20.2"
    version_a.mkdir(parents=True)
    version_b.mkdir(parents=True)
    stale_rule = f"Bash(bash {version_a}/scripts/lib/resolve_project_dir.sh share)"
    data = {"permissions": {"allow": [stale_rule, "Bash(*)"]}}
    settings.write_text(json.dumps(data), encoding="utf-8")

    r = _run("apply", settings, odoo_ai_home, env_extra={"CLAUDE_PLUGIN_ROOT": str(version_b)})
    assert r.returncode == 0, f"apply must exit 0; stderr={r.stderr}"
    allow = _allow(settings)
    assert stale_rule not in allow, (
        f"the stale prior-version rule must be pruned even though the current version's rule was "
        f"skipped as covered by Bash(*); got {allow}"
    )
    assert f"Bash(bash {version_b}/scripts/lib/resolve_project_dir.sh share)" not in allow, (
        "the current version's rule must stay skipped (still covered by Bash(*)), not added "
        "just because pruning ran"
    )
    assert "Bash(*)" in allow

    r_check = _run("check", settings, odoo_ai_home, env_extra={"CLAUDE_PLUGIN_ROOT": str(version_b)})
    assert r_check.returncode == 0, f"check must agree the state is fully converged; stderr={r_check.stderr}"
