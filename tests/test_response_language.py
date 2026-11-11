"""The configured response language reaches the agent: the script follows Claude Code's settings
precedence and the SessionStart hook states the value in one line, only when one is set."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parent.parent / "plugins" / "odoo-ai-agents"
SCRIPT = PLUGIN / "scripts" / "lib" / "response_language.py"
HOOK = PLUGIN / "hooks" / "check-setup-deps.sh"


def _put(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")


@pytest.fixture
def world(tmp_path):
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_CONFIG_DIR", "CLAUDE_PROJECT_DIR")}
    env["HOME"] = str(tmp_path / "home")
    env["CLAUDE_CONFIG_DIR"] = str(tmp_path / "cfg")
    env["CLAUDE_MANAGED_SETTINGS_DIR"] = str(tmp_path / "managed")
    (tmp_path / "proj").mkdir()
    return {"env": env, "proj": tmp_path / "proj", "cfg": tmp_path / "cfg",
            "managed": tmp_path / "managed", "tmp": tmp_path}


def _lang(world, project=None):
    res = subprocess.run([sys.executable, str(SCRIPT), str(project or world["proj"])],
                         env=world["env"], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0
    return res.stdout


def test_nothing_is_printed_when_no_setting_exists(world):
    assert _lang(world) == ""


def test_the_user_setting_is_used_when_it_is_the_only_one(world):
    _put(world["cfg"] / "settings.json", {"language": "japanese"})
    assert _lang(world) == "japanese\n"


def test_the_project_setting_beats_the_user_setting(world):
    _put(world["cfg"] / "settings.json", {"language": "japanese"})
    _put(world["proj"] / ".claude" / "settings.json", {"language": "vietnamese"})
    assert _lang(world) == "vietnamese\n"


def test_the_project_local_setting_beats_the_project_setting(world):
    _put(world["proj"] / ".claude" / "settings.json", {"language": "vietnamese"})
    _put(world["proj"] / ".claude" / "settings.local.json", {"language": "french"})
    assert _lang(world) == "french\n"


def test_the_managed_setting_beats_everything(world):
    _put(world["proj"] / ".claude" / "settings.local.json", {"language": "french"})
    _put(world["managed"] / "managed-settings.json", {"language": "german"})
    assert _lang(world) == "german\n"


def test_a_file_without_the_key_falls_through_to_the_next_one(world):
    _put(world["proj"] / ".claude" / "settings.local.json", {"model": "opus"})
    _put(world["cfg"] / "settings.json", {"language": "korean"})
    assert _lang(world) == "korean\n"


def test_the_relocated_config_dir_is_read_and_the_default_home_is_not(world):
    _put(Path(world["env"]["HOME"]) / ".claude" / "settings.json", {"language": "spanish"})
    assert _lang(world) == ""
    _put(world["cfg"] / "settings.json", {"language": "korean"})
    assert _lang(world) == "korean\n"


def test_malformed_files_are_skipped_not_fatal(world):
    _put(world["proj"] / ".claude" / "settings.local.json", "{ not json")
    _put(world["proj"] / ".claude" / "settings.json", "[1, 2]")
    _put(world["cfg"] / "settings.json", {"language": "thai"})
    assert _lang(world) == "thai\n"


def test_a_non_string_or_blank_value_is_ignored(world):
    _put(world["proj"] / ".claude" / "settings.local.json", {"language": 7})
    _put(world["proj"] / ".claude" / "settings.json", {"language": "  "})
    assert _lang(world) == ""


def test_only_the_language_value_is_printed(world):
    _put(world["cfg"] / "settings.json", {"language": "thai", "env": {"TOKEN": "s3cret-value"}})
    assert _lang(world) == "thai\n"


def test_a_linked_worktree_reads_the_main_checkout_project_file(world):
    main = world["tmp"] / "main"
    wt = world["tmp"] / "wt"
    (main / ".git" / "worktrees" / "wt").mkdir(parents=True)
    wt.mkdir()
    (wt / ".git").write_text(f"gitdir: {main / '.git' / 'worktrees' / 'wt'}\n", encoding="utf-8")
    _put(main / ".claude" / "settings.local.json", {"language": "vietnamese"})
    _put(world["cfg"] / "settings.json", {"language": "thai"})
    assert _lang(world, wt) == "vietnamese\n"


# --- the SessionStart hook ----------------------------------------------------------------------
def _hook(world, source="startup"):
    env = dict(world["env"], CLAUDE_PROJECT_DIR=str(world["proj"]))
    res = subprocess.run(["bash", str(HOOK)], input=json.dumps({"source": source}), env=env,
                         capture_output=True, text=True, timeout=60)
    assert res.returncode == 0
    ctx = ""
    for line in res.stdout.splitlines():
        if line.strip():
            ctx += json.loads(line)["hookSpecificOutput"]["additionalContext"]
    return ctx


@pytest.mark.parametrize("source", ["startup", "resume", "clear", "compact"])
def test_the_hook_context_carries_the_configured_language_on_every_source(world, source):
    _put(world["cfg"] / "settings.json", {"language": "vietnamese"})
    assert "vietnamese" in _hook(world, source)


def test_the_hook_context_is_silent_about_language_when_none_is_set(world):
    ctx = _hook(world)
    assert "vietnamese" not in ctx.lower() and "language:" not in ctx.lower()


def test_the_language_line_is_one_short_line(world):
    _put(world["cfg"] / "settings.json", {"language": "vietnamese"})
    with_lang = _hook(world)
    without = _hook(dict(world, env=dict(world["env"], CLAUDE_CONFIG_DIR=str(world["tmp"] / "none"))))
    extra = with_lang.replace(without, "").strip()
    assert "vietnamese" in extra and "\n" not in extra and len(extra) < 120
    assert len(with_lang) < 4500
