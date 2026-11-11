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
    return [
        f"Bash(bash {root}/scripts/lib/resolve_project_dir.sh share)",
        f"Bash(bash {root}/scripts/lib/resolve_project_dir.sh isolate)",
    ]


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


def test_four_exact_rules_written_to_the_file_named_by_claude_settings(applied):
    """Exactly the 4 rules that cover a REAL write path, no more, no fewer - written to the path
    named by $CLAUDE_SETTINGS and nowhere else (not a sibling settings file, not ~/.claude.json)."""
    expected = {
        f"Bash(bash {STEP.parent.parent.parent}/scripts/lib/resolve_project_dir.sh share)",
        f"Bash(bash {STEP.parent.parent.parent}/scripts/lib/resolve_project_dir.sh isolate)",
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


def test_bash_rules_are_exact_no_wildcard(applied):
    bash_rules = [a for a in applied.allow if a.startswith("Bash(")]
    assert bash_rules, "apply must write at least one Bash() rule"
    for rule in bash_rules:
        assert ":*" not in rule and rule.endswith(")"), f"Bash rule must be exact, wildcard-free: {rule!r}"
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


def test_opt_out_writes_nothing(settings, odoo_ai_home):
    before = settings.read_text(encoding="utf-8")
    r = _run("apply", settings, odoo_ai_home, env_extra={"ODOO_AI_NO_AUTO_PERMS": "1"})
    assert r.returncode == 0, f"opt-out must still exit 0; stderr={r.stderr}"
    assert settings.read_text(encoding="utf-8") == before, "opt-out must not modify settings"


# ---------------------------------------------------------------------------
# Version-pinned rules converge: `${PLUGIN_ROOT}` in the two Bash rules is the INSTALLED version's
# directory, so a naive re-apply on every upgrade would add a pair per version and never remove
# the previous one.
# ---------------------------------------------------------------------------
def test_apply_across_versions_keeps_only_the_current_versions_two_bash_rules(
        settings, odoo_ai_home, tmp_path):
    roots = [tmp_path / "plugins" / v for v in ("4.18.0", "4.18.1", "4.20.0")]
    for root in roots:
        root.mkdir(parents=True)

    def apply(root):
        r = _run("apply", settings, odoo_ai_home, env_extra={"CLAUDE_PLUGIN_ROOT": str(root)})
        assert r.returncode == 0, f"apply for {root} must exit 0; stderr={r.stderr}"
        return [a for a in _allow(settings) if a.startswith("Bash(")]

    assert apply(roots[0]) == _bash_rules(roots[0])
    assert apply(roots[1]) == _bash_rules(roots[1]), (
        "installing a newer version's rules must PRUNE the previous version's rules for the "
        "same script, not accumulate alongside them"
    )
    after_c = apply(roots[2])
    assert set(after_c) == set(_bash_rules(roots[2])) and len(after_c) == 2, (
        f"after 3 successive plugin versions exactly the CURRENT version's 2 Bash rules must "
        f"remain, not one pair per version ever installed; got {after_c}"
    )
    settled = _allow(settings)
    apply(roots[2])
    assert _allow(settings) == settled, (
        "re-applying the SAME version after a prune must not change the allow-list"
    )


def test_check_detects_stale_prior_version_bash_rule(settings, odoo_ai_home, tmp_path):
    """`check` must fail while a stale prior-version Bash rule for the same
    script remains in permissions.allow[], even when the CURRENT version's
    rules are already present too - the SessionStart hook only calls `apply`
    when `check` fails, so a machine in the accumulated state would never be pruned."""
    version_a = tmp_path / "plugins" / "4.18.0"
    version_b = tmp_path / "plugins" / "4.20.0"
    version_a.mkdir(parents=True)
    version_b.mkdir(parents=True)
    data = {
        "permissions": {
            "allow": [
                *_bash_rules(version_a),
                *_bash_rules(version_b),
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

    A suffix-only prune matcher deleted another plugin's rule for an identically-named script.
    The matcher is anchored on THIS plugin's own path:

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

    assert same_plugin_prior_version not in allow, (
        f"stale same-plugin prior-version rule must be pruned; still present in {allow}"
    )
    assert different_plugin_same_script in allow, (
        f"a DIFFERENT plugin's rule for an identically-suffixed script must NEVER be pruned "
        f"just because it shares the script suffix; missing from {allow}"
    )
    assert same_plugin_different_script in allow, (
        f"a different script under the SAME plugin must not be pruned; missing from {allow}"
    )
    for u in hand_written:
        assert u in allow, f"apply must never remove a user's hand-written rule: {u!r} missing from {allow}"
    assert f"Bash(bash {version_b}/scripts/lib/resolve_project_dir.sh share)" in allow


def test_dev_checkout_without_version_segment_skips_pruning_safely(settings, odoo_ai_home, tmp_path):
    """A --plugin-dir dev checkout has no version segment in $PLUGIN_ROOT, so there is no reliable
    way to tell which path segment IS the version: pruning is skipped entirely rather than guessed
    (it could otherwise strip the wrong segment and widen the anchor). The marketplace-cache rule
    of the SAME plugin survives, the dev checkout's own rule is added, and nothing crashes."""
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
        f"the same plugin; missing from {allow}"
    )
    assert f"Bash(bash {dev_checkout}/scripts/lib/resolve_project_dir.sh share)" in allow, (
        "the dev checkout's own rule must still be added (plain add, no pruning)"
    )


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
    """Bash(*) covers both Bash rules, a bare Read covers the Read rule and the Edit rule is an
    exact duplicate: all 4 covered, so apply performs zero writes - no backup at all."""
    edit_rule = f"Edit(/{odoo_ai_home}/projects/**)"
    seed = ["Bash(*)", "Read", edit_rule]
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
