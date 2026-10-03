"""Behavior tests for setup step 35: offer to raise Claude Code's skill-listing budget.

The rule protected: setup proposes a `skillListingBudgetFraction` only when the session's listing
overflows its budget, writes it only to the USER settings file and only with consent, and never
touches a value the user already set at or above the proposal. The decision is tested on the
pure `decide()`; the write paths are tested end to end through the step script against a fake
Claude config dir (installed plugin registry + settings), so the measurement path is real too.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
STEP = PLUGIN / "scripts" / "setup-steps" / "35-skill-listing-budget.sh"
sys.path.insert(0, str(PLUGIN / "scripts" / "lib"))
import skill_listing as sl  # noqa: E402

requires_bash = pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")
WINDOW = sl.DEFAULT_WINDOW_TOKENS
DEFAULT_BUDGET = sl.budget_chars(WINDOW, sl.DEFAULT_FRACTION)


# --------------------------------------------------------------------------- #
# decide(): the pure decision
# --------------------------------------------------------------------------- #
def test_overflowing_listing_gets_a_proposal_that_holds_it():
    listing = DEFAULT_BUDGET + 5_000
    d = sl.decide(listing, WINDOW)
    assert d["action"] == "propose"
    assert d["fraction"] > sl.DEFAULT_FRACTION
    assert sl.budget_chars(WINDOW, d["fraction"]) >= listing, "the proposal must fit the listing"
    assert d["listing_tokens"] * sl.CHARS_PER_TOKEN >= listing, "the question shows the real cost"


def test_listing_that_fits_needs_nothing():
    assert sl.decide(DEFAULT_BUDGET - 1, WINDOW)["action"] == "fits"


def test_large_context_window_fits_what_a_200k_window_does_not():
    listing = DEFAULT_BUDGET + 5_000
    assert sl.decide(listing, WINDOW)["action"] == "propose"
    assert sl.decide(listing, WINDOW * 5)["action"] == "fits"


@pytest.mark.parametrize("current", [0.01, 0.02, 0.05, 0.2])
@pytest.mark.parametrize("listing", [8_001, 13_137, 40_000, 120_000])
def test_a_proposal_never_lowers_the_fraction_in_force(current, listing):
    d = sl.decide(listing, WINDOW, current_fraction=current, current_scope="user")
    if d["action"] == "propose":
        assert d["fraction"] > current
    else:
        assert d["action"] == "fits"


def test_user_fraction_too_low_for_the_listing_gets_a_higher_proposal():
    listing = DEFAULT_BUDGET * 3
    d = sl.decide(listing, WINDOW, current_fraction=sl.DEFAULT_FRACTION * 2, current_scope="user")
    assert d["action"] == "propose" and d["fraction"] > sl.DEFAULT_FRACTION * 2


def test_env_budget_wins_so_no_setting_is_proposed():
    d = sl.decide(DEFAULT_BUDGET + 5_000, WINDOW, env_budget=str(DEFAULT_BUDGET))
    assert d["action"] == "env-override"


def test_project_setting_overrides_so_the_user_file_is_not_proposed():
    d = sl.decide(DEFAULT_BUDGET + 5_000, WINDOW, current_fraction=sl.DEFAULT_FRACTION,
                  current_scope="project")
    assert d["action"] == "scope-override"


def test_hidden_and_overridden_entries_cost_what_claude_code_charges():
    fm = {"description": "x" * 50}
    assert sl.entry_chars("p:s", fm) == len("p:s") + 4 + 50
    assert sl.entry_chars("p:s", dict(fm, **{"disable-model-invocation": "true"})) is None
    assert sl.entry_chars("p:s", fm, "off") is None
    assert sl.entry_chars("p:s", fm, "name-only") == len("p:s") + 2
    assert sl.entry_chars("p:s", {"description": "y" * 5000}) == len("p:s") + 4 + sl.PER_ENTRY_TEXT_CAP


def test_cli_debug_measurement_is_preferred_over_the_bundled_observation(tmp_path):
    cfg = tmp_path / "cfg"
    (cfg / "debug").mkdir(parents=True)
    (cfg / "debug" / "s.txt").write_text(
        "noise\nSkill listing over budget: 74 skills, 13137 chars > 8000 budget - truncated\n")
    r = sl.measure(cwd=str(tmp_path), config_dir=str(cfg), environ={})
    assert r["source"] == "cli-debug-log"
    assert r["listing_chars"] == 13137 and r["window_tokens"] == WINDOW
    assert r["action"] == "propose"


# --------------------------------------------------------------------------- #
# the step script, end to end against a fake config dir
# --------------------------------------------------------------------------- #
def _fake_install(tmp_path, desc_chars, user_settings=None):
    cfg = tmp_path / "cfg"
    plugin = tmp_path / "store" / "big-plugin"
    (plugin / ".claude-plugin").mkdir(parents=True)
    (plugin / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": "big-plugin"}))
    for i in range(10):
        d = plugin / "skills" / f"s{i}"
        d.mkdir(parents=True)
        d.joinpath("SKILL.md").write_text(
            f"---\nname: s{i}\ndescription: {'w' * (desc_chars // 10)}\n---\nbody\n")
    (cfg / "plugins").mkdir(parents=True)
    (cfg / "plugins" / "installed_plugins.json").write_text(json.dumps({
        "version": 2,
        "plugins": {"big-plugin@m": [{"scope": "user", "installPath": str(plugin)}]},
    }))
    settings = {"enabledPlugins": {"big-plugin@m": True}}
    settings.update(user_settings or {})
    (cfg / "settings.json").write_text(json.dumps(settings))
    proj = tmp_path / "proj"
    proj.mkdir()
    return cfg, proj


def _run(cfg, proj, *args, extra_env=None):
    env = {k: v for k, v in os.environ.items()
           if k not in ("SLASH_COMMAND_TOOL_CHAR_BUDGET", "CLAUDE_SETTINGS",
                        "ODOO_AI_NO_LISTING_BUDGET")}
    env.update({"CLAUDE_CONFIG_DIR": str(cfg), "HOME": str(cfg.parent)})
    env.update(extra_env or {})
    return subprocess.run(["bash", str(STEP), *args], cwd=proj, env=env,
                          capture_output=True, text=True, stdin=subprocess.DEVNULL)


def _settings(cfg):
    return json.loads((cfg / "settings.json").read_text())


# Room left in the default budget once the bundled observation is counted.
_ROOM = DEFAULT_BUDGET - sl.BUNDLED_OBSERVED_CHARS


@requires_bash
def test_step_overflow_is_proposed_and_written_only_with_consent(tmp_path):
    cfg, proj = _fake_install(tmp_path, desc_chars=_ROOM + 4_000)
    assert _run(cfg, proj, "check").returncode == 1
    proposal = _run(cfg, proj, "propose").stdout
    assert "ACTION=propose" in proposal and "QUESTION=" in proposal
    assert "tokens of context per turn" in proposal, "the question must state the cost"

    no_consent = _run(cfg, proj, "apply")
    assert no_consent.returncode == 0 and "Not written" in no_consent.stdout
    assert "skillListingBudgetFraction" not in _settings(cfg), "no consent -> nothing written"

    assert _run(cfg, proj, "apply", "--yes").returncode == 0
    written = _settings(cfg)["skillListingBudgetFraction"]
    fraction = float(proposal.split("FRACTION=")[1].split()[0])
    assert written == fraction
    assert _settings(cfg)["enabledPlugins"] == {"big-plugin@m": True}, "other keys preserved"
    assert _run(cfg, proj, "check").returncode == 0, "idempotent: re-run has nothing to do"
    assert not (proj / ".claude").exists(), "never writes project or local settings"


@requires_bash
def test_step_listing_that_fits_is_a_no_op(tmp_path):
    cfg, proj = _fake_install(tmp_path, desc_chars=200)
    assert _run(cfg, proj, "check").returncode == 0
    before = (cfg / "settings.json").read_text()
    assert "Nothing to write" in _run(cfg, proj, "apply", "--yes").stdout
    assert (cfg / "settings.json").read_text() == before


@requires_bash
def test_step_never_lowers_a_fraction_the_user_set_higher(tmp_path):
    cfg, proj = _fake_install(tmp_path, desc_chars=_ROOM + 4_000,
                              user_settings={"skillListingBudgetFraction": 0.5})
    assert _run(cfg, proj, "check").returncode == 0
    _run(cfg, proj, "apply", "--yes")
    assert _settings(cfg)["skillListingBudgetFraction"] == 0.5


@requires_bash
def test_step_opt_out_writes_nothing(tmp_path):
    cfg, proj = _fake_install(tmp_path, desc_chars=_ROOM + 4_000)
    env = {"ODOO_AI_NO_LISTING_BUDGET": "1"}
    assert _run(cfg, proj, "check", extra_env=env).returncode == 0
    _run(cfg, proj, "apply", "--yes", extra_env=env)
    assert "skillListingBudgetFraction" not in _settings(cfg)


@requires_bash
def test_step_refuses_a_corrupt_user_settings_file(tmp_path):
    cfg, proj = _fake_install(tmp_path, desc_chars=_ROOM + 4_000)
    (cfg / "settings.json").write_text("{not json")
    # A corrupt file also hides enabledPlugins, so force the overflow through the debug log.
    (cfg / "debug").mkdir()
    (cfg / "debug" / "s.txt").write_text(
        "Skill listing over budget: 74 skills, 13137 chars > 8000 budget\n")
    r = _run(cfg, proj, "apply", "--yes")
    assert r.returncode == 2
    assert (cfg / "settings.json").read_text() == "{not json"
