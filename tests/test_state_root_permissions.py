"""Behavioral + contract tests for `scripts/setup-steps/32-permissions-state-root.sh`.

This is the L2 setup step that auto-allows the narrow set of Bash/Read/Edit
permission rules the planning pipeline (odoo-planner / intake
Phase P) needs to resolve and write under the machine-global state root
(`$ODOO_AI_HOME`) without a per-call approval prompt.

Modeled on tests/test_ensure_browser_permissions.py. Contract under test (the
behavior/security contract, not the implementation):

  - `describe|check|apply` subcommand contract, idempotent;
  - writes ONLY `permissions.allow[]` - never `deny[]`/`ask[]`/`additionalDirectories`;
  - never writes an Odoo Semantic rule (that permission's owner is
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
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
STEP = PLUGIN / "scripts" / "setup-steps" / "32-permissions-state-root.sh"

_PLUGIN_NAME = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["name"]
# The give-back group: the only tools of any local server granted as exact allow rules.
GIVE_BACK_RULES = (
    f"mcp__plugin_{_PLUGIN_NAME}_odoo-local__lease_release",
    f"mcp__plugin_{_PLUGIN_NAME}_odoo-local__lease_park",
)

# The public-address group: instance_expose / instance_unexpose, the other tools of a local server
# granted as exact allow rules (an auto-mode classifier may refuse "expose a local server").
EXPOSE_RULES = (
    f"mcp__plugin_{_PLUGIN_NAME}_odoo-local__instance_expose",
    f"mcp__plugin_{_PLUGIN_NAME}_odoo-local__instance_unexpose",
)
LOCAL_TOOL_RULES = GIVE_BACK_RULES + EXPOSE_RULES

EXCLUDED_SUBPATHS = ("bin/", "venvs/", "node_tools/", "setup-scripts/", "runtime/", "instances.toml")


def _run(subcmd, settings_path, odoo_ai_home, env_extra=None, stdin_devnull=True):
    env = dict(os.environ)
    # Deterministic regardless of the runner's own session: force the SCRIPT_DIR-based
    # plugin-root fallback (never inherit a caller's $CLAUDE_PLUGIN_ROOT into the test).
    env.pop("CLAUDE_PLUGIN_ROOT", None)
    env["CLAUDE_SETTINGS"] = str(settings_path)
    env["ODOO_AI_HOME"] = str(odoo_ai_home)
    # A throwaway HOME: anything the step wrote through ~ (e.g. ~/.claude.json) would land here.
    env["HOME"] = str(Path(odoo_ai_home).parent / "home")
    # The throwaway root lives under the runner's own temp dir, which the step treats as
    # ephemeral; name a different temp dir so these tests exercise a real (non-ephemeral) root.
    env["ODOO_AI_TEMP_DIRS"] = str(Path(odoo_ai_home).parent / "system-temp-elsewhere")
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


_OSM_PLUGIN_RULE = "mcp__plugin_odoo-semantic-mcp_odoo-semantic"
_OSM_SHORT_RULE = "mcp__odoo-semantic"


def _is_osm_rule(a):
    return any(a == p or a.startswith(p + "__") for p in (_OSM_PLUGIN_RULE, _OSM_SHORT_RULE))


def _bash_rules(root):
    """The two rules of one plugin directory: the command, then a trailing ` *` (documented to
    match the bare command too; the spelling earlier releases do not recognise and so never prune)."""
    return [
        f"Bash(bash {root}/scripts/lib/resolve_project_dir.sh share *)",
        f"Bash(bash {root}/scripts/lib/resolve_project_dir.sh isolate *)",
    ]


def _install_script(root):
    """Make `root` a plugin directory that holds the script the Bash rules run."""
    script = Path(root) / "scripts" / "lib" / "resolve_project_dir.sh"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("#!/usr/bin/env bash\n", encoding="utf-8")


def _file_rules(allow):
    return [a for a in allow if a.startswith("Write(") or a.startswith("Edit(")]


# ---------------------------------------------------------------------------
# One machine, one `check` before and one `apply` + `apply` + `check` after: the allow-list that
# a first apply leaves is read by every test below that inspects it.
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def before_apply(tmp_path_factory):
    base = tmp_path_factory.mktemp("before-apply")
    settings = base / "settings.json"
    settings.write_text("{}", encoding="utf-8")
    return SimpleNamespace(check=_run("check", settings, base / ".odoo-ai"))


@pytest.fixture(scope="module")
def applied(tmp_path_factory):
    base = tmp_path_factory.mktemp("applied")
    (base / "home").mkdir()
    settings = base / "settings.json"
    settings.write_text("{}", encoding="utf-8")
    decoy = base / "other-settings.json"  # a sibling the step was never pointed at
    decoy.write_text("{}", encoding="utf-8")
    home = base / ".odoo-ai"
    first = _run("apply", settings, home)
    allow_first = _allow(settings)
    return SimpleNamespace(
        base=base, settings=settings, decoy=decoy, home=home, first=first, allow=allow_first,
        data=json.loads(settings.read_text(encoding="utf-8")),
        check=_run("check", settings, home),
        second=_run("apply", settings, home), allow_second=_allow(settings),
    )


def test_check_fails_before_apply_and_points_at_the_odoo_semantic_owner(before_apply):
    r = before_apply.check
    assert r.returncode == 1, f"check must exit 1 before apply; stdout={r.stdout} stderr={r.stderr}"
    combined = r.stdout + r.stderr
    assert _OSM_PLUGIN_RULE in combined and "connect" in combined.lower(), (
        "check should report the plugin-form Odoo Semantic rule's absence and point at the connect "
        f"command that owns it; got: {combined!r}"
    )


def test_apply_then_check_succeeds(applied):
    assert applied.first.returncode == 0, f"apply must exit 0; stderr={applied.first.stderr}"
    assert applied.check.returncode == 0, f"check must exit 0 after apply; stderr={applied.check.stderr}"


def test_apply_is_idempotent(applied):
    assert applied.second.returncode == 0, f"second apply must exit 0; stderr={applied.second.stderr}"
    assert applied.allow_second == applied.allow, "second apply changed the allow-list (not idempotent)"


def test_exact_rules_written_to_the_file_named_by_claude_settings(applied):
    """Exactly the 2 Bash rules of this plugin directory and the 2 state-root rules that cover a REAL
    write path plus the 2 lease give-back rules and the 2 public-address rules, no more, no fewer - written to the path named by $CLAUDE_SETTINGS and nowhere else
    (not a sibling settings file, not ~/.claude.json)."""
    expected = {
        *LOCAL_TOOL_RULES,
        *_bash_rules(STEP.parent.parent.parent),
        # `//<abs-path>` = one extra leading slash over the already-absolute $ODOO_AI_HOME, the
        # Claude Code path-permission marker for an ABSOLUTE (not project-relative) match.
        f"Read(/{applied.home}/**)",
        f"Edit(/{applied.home}/projects/**)",
    }
    assert set(applied.allow) == expected, f"expected exactly {expected}, got {applied.allow}"
    assert json.loads(applied.decoy.read_text(encoding="utf-8")) == {}, (
        "must not write to any settings file other than the one named by $CLAUDE_SETTINGS"
    )
    assert list((applied.base / "home").iterdir()) == [], (
        "the step wrote under HOME (e.g. ~/.claude.json, the MCP registry step 10 owns)"
    )


def test_writes_only_permissions_allow(applied):
    """The hard security contract: never permissions.deny[]/ask[], never additionalDirectories."""
    perms = applied.data.get("permissions") or {}
    assert "deny" not in perms, f"must never write permissions.deny[]; got {perms.get('deny')}"
    assert "ask" not in perms, f"must never write permissions.ask[]; got {perms.get('ask')}"
    assert "additionalDirectories" not in applied.data, (
        f"must never write additionalDirectories; got {applied.data.get('additionalDirectories')}"
    )
    assert "allow" in perms and perms["allow"], "must write permissions.allow[]"


def test_never_writes_an_odoo_semantic_rule(applied):
    assert not any(_is_osm_rule(a) for a in applied.allow), (
        f"must never write an Odoo Semantic rule (owned by odoo-semantic-mcp connect.md step 5); "
        f"allow={applied.allow}"
    )


def test_rules_exclude_dangerous_subpaths(applied):
    """Hard safety boundary: the file-editing path rules must never grant blanket access to
    bin/, venvs/, node_tools/, setup-scripts/, runtime/, or instances.toml under the state
    root - each is deferred-code-execution-adjacent, not scratch data.

    The filter stays deliberately wide (`Write(` OR `Edit(`) so this boundary still binds a
    stray `Write(<path>)` rule if one is ever re-added."""
    write_edit_rules = _file_rules(applied.allow)
    assert write_edit_rules, "apply must write at least one file-editing path rule"
    for rule in write_edit_rules:
        for excluded in EXCLUDED_SUBPATHS:
            assert excluded not in rule, (
                f"Write/Edit rule {rule!r} must not cover excluded subpath {excluded!r} - the "
                f"hard safety contract of step 32."
            )
    # And the whole allow-list, not just Write/Edit, must never wildcard the entire state root
    # (that would implicitly re-admit the excluded subpaths via a broader match).
    assert not any(a in (f"Write(/{applied.home}/**)", f"Edit(/{applied.home}/**)") for a in applied.allow), (
        "must never grant a blanket Write/Edit over the whole state root"
    )


def test_rules_scoped_to_projects_only(applied):
    """File-editing path rules cover ONLY `projects/**`: both the plan (SHARE) and the
    per-worktree worklog (ISOLATE) resolve NESTED under it, so a rule scoped anywhere else would
    never cover a real write path."""
    for rule in _file_rules(applied.allow):
        assert "/projects/**" in rule, (
            f"every file-editing path rule must scope to projects/** (the plan and worklog both "
            f"resolve nested under it); got {rule!r}"
        )


def test_bash_rules_name_one_script_with_only_a_trailing_wildcard(applied):
    """A Bash rule runs exactly this plugin's resolve script with `share` or `isolate`; the only
    wildcard is the single trailing ` *` (a `*` anywhere else would widen the rule to other
    directories or commands, and a wildcard before the subcommand makes Claude Code warn)."""
    bash_rules = [a for a in applied.allow if a.startswith("Bash(")]
    assert bash_rules, "apply must write at least one Bash() rule"
    for rule in bash_rules:
        assert rule.endswith(" *)") and rule.count("*") == 1, f"only a trailing ' *' is allowed: {rule!r}"
        assert ":*" not in rule
        assert "resolve_project_dir.sh" in rule, f"Bash rule must invoke resolve_project_dir.sh: {rule!r}"


def test_no_write_path_rule_is_ever_written(applied):
    """Claude Code matches PATH rules on `Edit(path)` only: a `Write(<path>)` rule matches nothing
    AND makes the CLI print a warning at every launch - and since the SessionStart hook re-applies
    this step whenever `check` fails, deleting it by hand would bring it back. Never write one."""
    offenders = [a for a in applied.allow if a.startswith("Write(")]
    assert not offenders, f"step 32 must never write a Write(<path>) rule; offenders: {offenders}"


@pytest.mark.parametrize("rule", [
    pytest.param(_OSM_PLUGIN_RULE, id="plugin-rule"),
    pytest.param(_OSM_PLUGIN_RULE + "__model_inspect", id="plugin-tool-entry"),
    pytest.param(_OSM_SHORT_RULE, id="hand-registered-rule"),
])
def test_check_is_silent_about_odoo_semantic_when_an_allow_entry_exists(applied, settings, rule):
    data = json.loads(applied.settings.read_text(encoding="utf-8"))
    data["permissions"]["allow"].append(rule)
    settings.write_text(json.dumps(data), encoding="utf-8")
    r = _run("check", settings, applied.home)
    combined = r.stdout + r.stderr
    assert "connect" not in combined.lower(), f"no absence message expected; got: {combined!r}"


def test_refuses_invalid_json(settings, odoo_ai_home):
    settings.write_text("not valid json", encoding="utf-8")
    r = _run("apply", settings, odoo_ai_home)
    assert r.returncode == 2, f"apply must exit 2 on invalid JSON; stdout={r.stdout} stderr={r.stderr}"
    assert settings.read_text(encoding="utf-8") == "not valid json", (
        "must refuse to overwrite a settings file that is not valid JSON"
    )


def test_the_only_tools_of_a_local_server_granted_are_the_give_back_and_the_public_address_tools(applied):
    """lease_release, lease_park, instance_expose and instance_unexpose are granted; no other
    odoo-local / odoo-media tool and no blanket server rule is ever written."""
    mcp = [a for a in applied.allow if a.startswith("mcp__")]
    assert sorted(mcp) == sorted(LOCAL_TOOL_RULES), f"unexpected MCP rules: {mcp}"


def test_give_back_rules_are_skipped_when_the_odoo_local_server_rule_already_grants_them(
        settings, odoo_ai_home, plugin_root):
    server_rule = f"mcp__plugin_{_PLUGIN_NAME}_odoo-local"
    settings.write_text(json.dumps({"permissions": {"allow": [server_rule]}}), encoding="utf-8")

    allow, r_check = _apply_and_check(settings, odoo_ai_home, plugin_root)
    assert not any(a in LOCAL_TOOL_RULES for a in allow), f"a broader rule covers them; got {allow}"
    assert server_rule in allow
    assert r_check.returncode == 0, f"check must agree they are covered; stderr={r_check.stderr}"


def test_give_back_rules_are_still_added_when_only_another_servers_rule_exists(
        settings, odoo_ai_home, plugin_root):
    other = f"mcp__plugin_{_PLUGIN_NAME}_odoo-media"
    settings.write_text(json.dumps({"permissions": {"allow": [other]}}), encoding="utf-8")

    allow, _ = _apply_and_check(settings, odoo_ai_home, plugin_root)
    for rule in LOCAL_TOOL_RULES:
        assert rule in allow, f"{rule} must be added; got {allow}"


def test_another_plugins_rules_survive_apply(settings, odoo_ai_home, plugin_root):
    others = ["mcp__plugin_other_odoo-local__lease_release", "mcp__plugin_other_odoo-local"]
    settings.write_text(json.dumps({"permissions": {"allow": others}}), encoding="utf-8")

    allow, _ = _apply_and_check(settings, odoo_ai_home, plugin_root)
    assert all(o in allow for o in others), f"another plugin's rules must stay; got {allow}"
    assert all(g in allow for g in LOCAL_TOOL_RULES)


@pytest.mark.parametrize("missing", LOCAL_TOOL_RULES)
def test_check_fails_while_a_local_tool_rule_is_missing(settings, odoo_ai_home, plugin_root, missing):
    """Everything but one give-back or public-address rule is present: check reports the step
    incomplete."""
    _apply_and_check(settings, odoo_ai_home, plugin_root)
    data = json.loads(settings.read_text(encoding="utf-8"))
    data["permissions"]["allow"].remove(missing)
    settings.write_text(json.dumps(data), encoding="utf-8")

    r = _run("check", settings, odoo_ai_home, env_extra={"CLAUDE_PLUGIN_ROOT": str(plugin_root)})
    assert r.returncode == 1, f"check must exit 1; stderr={r.stderr}"


def test_opt_out_writes_nothing(settings, odoo_ai_home):
    before = settings.read_text(encoding="utf-8")
    r = _run("apply", settings, odoo_ai_home, env_extra={"ODOO_AI_NO_AUTO_PERMS": "1"})
    assert r.returncode == 0, f"opt-out must still exit 0; stderr={r.stderr}"
    assert settings.read_text(encoding="utf-8") == before, "opt-out must not modify settings"


# ---------------------------------------------------------------------------
# Rules keyed to a plugin version directory: the Bash rules embed the directory of the session that
# runs the command, so a rule covers that directory's sessions and no others. Sessions of several
# versions share one settings file, so each version writes the rules of EVERY installed version
# directory and removes only the rules of a directory that no longer holds the script - a version
# never replaces what another version wrote.
# ---------------------------------------------------------------------------
def _versions(tmp_path, *names):
    """Version directories of one plugin (each holds the script), under a shared parent."""
    parent = tmp_path / "plugins" / "cache" / "viindoo-plugins" / "odoo-ai-agents"
    roots = []
    for name in names:
        _install_script(parent / name)
        roots.append(parent / name)
    return roots


def _apply_from(root, settings, odoo_ai_home):
    r = _run("apply", settings, odoo_ai_home, env_extra={"CLAUDE_PLUGIN_ROOT": str(root)})
    assert r.returncode == 0, f"apply for {root} must exit 0; stderr={r.stderr}"


def _bash(settings):
    return [a for a in _allow(settings) if a.startswith("Bash(")]


def test_every_installed_version_directory_gets_its_two_bash_rules(settings, odoo_ai_home, tmp_path):
    """A session of any installed version runs the script from its own directory, so one start
    grants the rules of every installed version, not only the starting version's."""
    old, mid, new = _versions(tmp_path, "4.18.0", "4.18.1", "4.20.0")
    _apply_from(new, settings, odoo_ai_home)
    assert sorted(_bash(settings)) == sorted(_bash_rules(old) + _bash_rules(mid) + _bash_rules(new))


def test_an_older_versions_start_changes_nothing_a_newer_version_wrote(settings, odoo_ai_home, tmp_path):
    """No flip-flop between two versions: after the newer version converged the file, the older
    version's start finds every rule it needs present, so it writes nothing and makes no backup."""
    old, _, new = _versions(tmp_path, "4.18.0", "4.18.1", "4.20.0")
    _apply_from(new, settings, odoo_ai_home)
    settled = settings.read_text(encoding="utf-8")
    backups = sorted(settings.parent.glob(f"{settings.name}.bak.*"))
    for root in (old, new):
        r = _run("check", settings, odoo_ai_home, env_extra={"CLAUDE_PLUGIN_ROOT": str(root)})
        assert r.returncode == 0, f"check from {root} must pass; stderr={r.stderr}"
        _apply_from(root, settings, odoo_ai_home)
    assert settings.read_text(encoding="utf-8") == settled
    assert sorted(settings.parent.glob(f"{settings.name}.bak.*")) == backups, "a no-op start must not write"


def test_a_newer_versions_start_restores_the_rules_of_an_older_directory(settings, odoo_ai_home, tmp_path):
    """What an earlier release's pruning removed (the rules of another version directory) is
    missing: `check` says so and the newer version's start writes them back."""
    old, mid, new = _versions(tmp_path, "4.18.0", "4.18.1", "4.20.0")
    _apply_from(new, settings, odoo_ai_home)
    data = json.loads(settings.read_text(encoding="utf-8"))
    data["permissions"]["allow"] = [a for a in data["permissions"]["allow"]
                                    if not a.startswith(f"Bash(bash {mid}/")]
    settings.write_text(json.dumps(data), encoding="utf-8")
    env = {"CLAUDE_PLUGIN_ROOT": str(new)}
    assert _run("check", settings, odoo_ai_home, env_extra=env).returncode == 1
    _apply_from(new, settings, odoo_ai_home)
    assert set(_bash_rules(mid)) <= set(_bash(settings))
    assert _run("check", settings, odoo_ai_home, env_extra=env).returncode == 0


def test_rules_of_a_removed_version_directory_go_and_check_reports_them(settings, odoo_ai_home, tmp_path):
    """A directory that no longer holds the script (the version was cleaned from the plugin cache)
    leaves rules that match nothing: `check` fails while they remain, `apply` removes them - the
    rules of the exact earlier shape included - and the rules of every other directory stay."""
    (kept, current) = _versions(tmp_path, "4.18.0", "4.20.0")
    gone = kept.parent / "4.17.0"
    gone.mkdir()  # the directory exists, the script does not
    legacy = f"Bash(bash {gone}/scripts/lib/resolve_project_dir.sh share)"
    stale = [*_bash_rules(gone), legacy]
    settings.write_text(json.dumps({"permissions": {"allow": [*stale, "Bash(sudo *)"]}}), encoding="utf-8")
    env = {"CLAUDE_PLUGIN_ROOT": str(current)}
    assert _run("check", settings, odoo_ai_home, env_extra=env).returncode == 1
    _apply_from(current, settings, odoo_ai_home)
    allow = _allow(settings)
    assert not set(stale) & set(allow), f"rules of a removed version must go; got {allow}"
    assert set(_bash_rules(kept) + _bash_rules(current)) <= set(allow)
    assert "Bash(sudo *)" in allow
    assert _run("check", settings, odoo_ai_home, env_extra=env).returncode == 0


def test_a_rule_in_the_earlier_exact_shape_of_an_installed_version_is_left_alone(
        settings, odoo_ai_home, tmp_path):
    """Another release writes `Bash(... share)` for its own directory; while that directory exists
    the rule is correct and not this version's to remove."""
    old, new = _versions(tmp_path, "4.18.0", "4.20.0")
    legacy = f"Bash(bash {old}/scripts/lib/resolve_project_dir.sh share)"
    settings.write_text(json.dumps({"permissions": {"allow": [legacy]}}), encoding="utf-8")
    _apply_from(new, settings, odoo_ai_home)
    assert legacy in _allow(settings)


def test_prune_never_prunes_different_plugin_same_script(settings, odoo_ai_home, tmp_path):
    """Anchoring regression guard. Only rules of THIS plugin's removed version directories go:

      1. same plugin, removed version    -> PRUNED
      2. different plugin, same script   -> UNTOUCHED
      3. same plugin, different script   -> UNTOUCHED
      4. user's own hand-written rules   -> UNTOUCHED
    """
    cache_root = tmp_path / "plugins" / "cache" / "viindoo-plugins"
    removed = cache_root / "odoo-ai-agents" / "4.18.0"  # THIS plugin, directory without the script
    removed.mkdir(parents=True)
    (version_b,) = _versions(tmp_path, "4.20.2")
    other_plugin = cache_root / "other-plugin" / "1.0"  # a DIFFERENT plugin (script absent too)
    other_plugin.mkdir(parents=True)

    same_plugin_removed_version = _bash_rules(removed)[0]
    different_plugin_same_script = f"Bash(bash {other_plugin}/scripts/lib/resolve_project_dir.sh share *)"
    same_plugin_different_script = f"Bash(bash {removed}/scripts/lib/some_other_script.sh share *)"
    hand_written = ["Bash(sudo *)", "Read(**)", "Bash(git commit:*)", "mcp__some-other-server__tool"]

    seed = [same_plugin_removed_version, different_plugin_same_script, same_plugin_different_script,
            *hand_written]
    settings.write_text(json.dumps({"permissions": {"allow": list(seed)}}), encoding="utf-8")

    _apply_from(version_b, settings, odoo_ai_home)
    allow = _allow(settings)

    assert same_plugin_removed_version not in allow, (
        f"a rule of this plugin's removed version directory must be pruned; still in {allow}"
    )
    assert different_plugin_same_script in allow, (
        f"a DIFFERENT plugin's rule for an identically-named script must NEVER be pruned; "
        f"missing from {allow}"
    )
    assert same_plugin_different_script in allow, (
        f"a different script under the SAME plugin must not be pruned; missing from {allow}"
    )
    for u in hand_written:
        assert u in allow, f"apply must never remove a user's hand-written rule: {u!r} missing from {allow}"
    assert set(_bash_rules(version_b)) <= set(allow)


def test_dev_checkout_without_version_segment_writes_its_own_rules_and_prunes_nothing(
        settings, odoo_ai_home, tmp_path):
    """A --plugin-dir dev checkout has no version segment in its path, so there is no way to tell
    which directories are versions of the same plugin: it grants its own two rules, grants no
    sibling's, and removes nothing. A marketplace rule of the same plugin stays."""
    (marketplace_version,) = _versions(tmp_path, "4.18.0")
    dev_checkout = tmp_path / "worktrees" / "some-feature-branch" / "plugins" / "odoo-ai-agents"
    dev_checkout.mkdir(parents=True)
    gone = marketplace_version.parent / "4.17.0"
    gone.mkdir()
    marketplace_rules = _bash_rules(marketplace_version)
    removed_rule = _bash_rules(gone)[0]
    settings.write_text(json.dumps({"permissions": {"allow": [*marketplace_rules, removed_rule]}}),
                        encoding="utf-8")

    _apply_from(dev_checkout, settings, odoo_ai_home)

    allow = _allow(settings)
    assert set(marketplace_rules) <= set(allow) and removed_rule in allow, (
        f"a dev checkout must never prune a marketplace-cache rule; got {allow}")
    assert set(_bash_rules(dev_checkout)) <= set(allow), "the dev checkout's own rules must be added"
    assert len(_bash(settings)) == len(marketplace_rules) + 1 + 2, "no sibling directory is granted"



# ---------------------------------------------------------------------------
# Subsumption - do not add a rule the user already has
# ---------------------------------------------------------------------------
#
# On a machine whose permissions.allow[] already holds a blanket like Bash(*)/Read/Edit, the
# step's rules are redundant the moment they are written. `apply` checks every rule against
# config_merge.py json-rule-covered before writing it, and `check` must agree with whatever
# `apply` decided (a rule apply skips as covered must not make check report incompleteness, or
# the SessionStart hook loops).
#
# The bias is deliberately asymmetric: wrongly concluding "covered" silently withholds a needed
# permission; wrongly concluding "not covered" only writes one harmless redundant rule. So only a
# small enumerated set of forms counts as coverage. A parenthesized `Read(**)` / `Edit(**)` is NOT
# one of them: it is anchored to the SESSION's working directory at match time, so it cannot be
# proven to contain an absolute target like $ODOO_AI_HOME. Each case below seeds rules that touch
# DIFFERENT step rules, so one apply decides them all independently.
def _apply_and_check(settings, odoo_ai_home, plugin_root):
    env = {"CLAUDE_PLUGIN_ROOT": str(plugin_root)}
    r = _run("apply", settings, odoo_ai_home, env_extra=env)
    assert r.returncode == 0, f"apply must exit 0; stderr={r.stderr}"
    allow = _allow(settings)
    r_check = _run("check", settings, odoo_ai_home, env_extra=env)
    return allow, r_check


@pytest.fixture()
def plugin_root(tmp_path):
    root = tmp_path / "plugins" / "4.20.2"
    root.mkdir(parents=True)
    return root


def test_apply_skips_what_an_exact_duplicate_or_a_blanket_already_covers_and_writes_nothing(
        settings, odoo_ai_home, plugin_root):
    """Bash(*) covers both Bash rules, a bare Read covers the Read rule, the Edit rule is an
    exact duplicate and the give-back rules are exact duplicates: all covered, so apply performs
    zero writes - no backup at all."""
    edit_rule = f"Edit(/{odoo_ai_home}/projects/**)"
    seed = ["Bash(*)", "Read", edit_rule, *LOCAL_TOOL_RULES]
    settings.write_text(json.dumps({"permissions": {"allow": seed}}), encoding="utf-8")

    allow, r_check = _apply_and_check(settings, odoo_ai_home, plugin_root)
    assert allow == seed, f"every rule is covered, nothing may be added; got {allow}"
    assert not list(settings.parent.glob(f"{settings.name}.bak.*")), (
        "with all 4 rules already covered, apply must perform zero writes and thus create no backup"
    )
    assert r_check.returncode == 0, f"check must agree everything is satisfied; stderr={r_check.stderr}"


def test_apply_skips_the_edit_rule_covered_by_a_bare_edit_blanket(settings, odoo_ai_home, plugin_root):
    """A bare "Edit" (no parentheses) matches all file edits: the Edit rule is skipped, the Read
    rule beside it (covered by nothing here) is added, and check agrees."""
    settings.write_text(json.dumps({"permissions": {"allow": ["Edit"]}}), encoding="utf-8")

    allow, r_check = _apply_and_check(settings, odoo_ai_home, plugin_root)
    assert not any(a.startswith("Edit(") for a in allow), f"Edit rule must be skipped; got {allow}"
    assert f"Read(/{odoo_ai_home}/**)" in allow, f"the uncovered Read rule must be added; got {allow}"
    assert r_check.returncode == 0, f"check must agree bare Edit covers the Edit rule; stderr={r_check.stderr}"


def test_apply_skips_what_an_ancestor_glob_and_a_prefix_wildcard_cover_and_adds_the_rest(
        settings, odoo_ai_home, plugin_root):
    """An absolute Read(//<ancestor>/**) covers the Read rule (plain string containment, no
    dependency on a session's working directory); a Bash(<prefix> *) trailing wildcard covers both
    Bash rules; the Edit rule, covered by neither, is still added."""
    ancestor_rule = f"Read(/{odoo_ai_home.parent}/**)"
    prefix_rule = f"Bash(bash {plugin_root}/scripts/lib/resolve_project_dir.sh *)"
    settings.write_text(json.dumps({"permissions": {"allow": [ancestor_rule, prefix_rule]}}),
                        encoding="utf-8")

    allow, r_check = _apply_and_check(settings, odoo_ai_home, plugin_root)
    assert f"Read(/{odoo_ai_home}/**)" not in allow, (
        f"the specific Read rule must be skipped - an ancestor directory rule covers it; got {allow}"
    )
    for rule in _bash_rules(plugin_root):
        assert rule not in allow, f"{rule} must be skipped - the prefix wildcard covers it; got {allow}"
    assert ancestor_rule in allow and prefix_rule in allow
    assert f"Edit(/{odoo_ai_home}/projects/**)" in allow, "the uncovered Edit rule must be added"
    assert r_check.returncode == 0, f"check must agree the existing rules cover theirs; stderr={r_check.stderr}"


def test_a_relative_double_star_or_an_ambiguous_wildcard_is_not_coverage_so_the_rules_are_added(
        settings, odoo_ai_home, plugin_root):
    """Read(**) / Edit(**) (no `//` or `~/` anchor) and a Bash rule with a wildcard outside the
    documented trailing position are outside the enumerated set: the conservative direction is to
    still add the rule rather than guess."""
    ambiguous_rule = "Bash(bash */scripts/lib/resolve_project_dir.sh share)"
    seed = ["Read(**)", "Edit(**)", ambiguous_rule]
    settings.write_text(json.dumps({"permissions": {"allow": seed}}), encoding="utf-8")

    allow, _ = _apply_and_check(settings, odoo_ai_home, plugin_root)
    assert f"Read(/{odoo_ai_home}/**)" in allow, f"bare relative Read(**) is not coverage; got {allow}"
    assert f"Edit(/{odoo_ai_home}/projects/**)" in allow, f"bare relative Edit(**) is not coverage; got {allow}"
    assert _bash_rules(plugin_root)[0] in allow, (
        f"an unrecognized wildcard shape is not coverage - the rule must still be added; got {allow}"
    )


def test_stale_rule_pruned_even_when_current_rule_skipped_as_covered(settings, odoo_ai_home, tmp_path):
    """Pruning and subsumption interact: a stale prior-version Bash rule is still REMOVED when the
    CURRENT version's own rule is skipped as covered by a blanket - it grants nothing a broader
    existing permission does not already cover, and is exactly the accumulation this step fixes."""
    version_a = tmp_path / "plugins" / "4.18.0"
    version_b = tmp_path / "plugins" / "4.20.2"
    version_a.mkdir(parents=True)
    version_b.mkdir(parents=True)
    stale_rule = _bash_rules(version_a)[0]
    data = {"permissions": {"allow": [stale_rule, "Bash(*)"]}}
    settings.write_text(json.dumps(data), encoding="utf-8")

    allow, r_check = _apply_and_check(settings, odoo_ai_home, version_b)
    assert stale_rule not in allow, (
        f"the stale prior-version rule must be pruned even though the current version's rule was "
        f"skipped as covered by Bash(*); got {allow}"
    )
    assert _bash_rules(version_b)[0] not in allow, (
        "the current version's rule must stay skipped (still covered by Bash(*)), not added "
        "just because pruning ran"
    )
    assert "Bash(*)" in allow
    assert r_check.returncode == 0, f"check must agree the state is fully converged; stderr={r_check.stderr}"
