"""Behaviour tests for config_merge.py `json-prune-tagged` and `json-ensure-first`.

They let a setup step own a tagged slice of a settings array: remove its own earlier entries,
never the literal "$defaults", never a user's or a non-string entry, and keep "$defaults" first.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "lib" / "config_merge.py"


def _run(*args):
    return subprocess.run([sys.executable, str(LIB), *args], capture_output=True, text=True, timeout=60)


def _write(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


def test_prune_removes_only_entries_with_the_prefix_and_keeps_defaults_and_non_strings(tmp_path):
    p = _write(tmp_path / "s.json", {"autoMode": {"allow": ["$defaults", "tag: a", "mine", 7, {"x": 1}, "tag: b"]}})
    out = _run("json-prune-tagged", p, "autoMode.allow", "tag: ")
    assert out.returncode == 0
    assert json.loads(Path(p).read_text())["autoMode"]["allow"] == ["$defaults", "mine", 7, {"x": 1}]


def test_prune_never_removes_defaults_even_when_the_prefix_would_match(tmp_path):
    p = _write(tmp_path / "s.json", {"autoMode": {"allow": ["$defaults", "$x"]}})
    _run("json-prune-tagged", p, "autoMode.allow", "$")
    assert json.loads(Path(p).read_text())["autoMode"]["allow"] == ["$defaults"]


def test_prune_with_nothing_to_do_or_a_missing_path_exits_0_and_does_not_write(tmp_path):
    p = _write(tmp_path / "s.json", {"autoMode": {"allow": ["mine"]}})
    before = Path(p).read_text()
    assert _run("json-prune-tagged", p, "autoMode.allow", "tag: ").returncode == 0
    assert _run("json-prune-tagged", p, "autoMode.soft_deny", "tag: ").returncode == 0
    assert Path(p).read_text() == before
    assert not list(tmp_path.glob("s.json.bak.*"))


def test_prune_regex_form_matches_from_the_start_of_the_entry(tmp_path):
    p = _write(tmp_path / "s.json", {"permissions": {"ask": ["Bash(git push * 17.0)", "Bash(git push origin 17.0)", "x"]}})
    _run("json-prune-tagged", p, "permissions.ask", r"^Bash\(git push \* [0-9.]+\)$", "--regex")
    assert json.loads(Path(p).read_text())["permissions"]["ask"] == ["Bash(git push origin 17.0)", "x"]


def test_prune_refuses_invalid_json_with_exit_2_and_leaves_the_file(tmp_path):
    f = tmp_path / "s.json"
    f.write_text("{oops")
    assert _run("json-prune-tagged", str(f), "autoMode.allow", "tag: ").returncode == 2
    assert f.read_text() == "{oops"


def test_prune_backs_up_before_it_writes(tmp_path):
    p = _write(tmp_path / "s.json", {"autoMode": {"allow": ["tag: a"]}})
    _run("json-prune-tagged", p, "autoMode.allow", "tag: ")
    assert list(tmp_path.glob("s.json.bak.*"))


def test_ensure_first_moves_or_creates_defaults_at_the_front_and_is_idempotent(tmp_path):
    p = _write(tmp_path / "s.json", {"autoMode": {"allow": ["mine", "$defaults"]}})
    _run("json-ensure-first", p, "autoMode.allow", "$defaults")
    _run("json-ensure-first", p, "autoMode.environment", "$defaults")
    data = json.loads(Path(p).read_text())
    assert data["autoMode"]["allow"] == ["$defaults", "mine"]
    assert data["autoMode"]["environment"] == ["$defaults"]
    before = Path(p).read_text()
    _run("json-ensure-first", p, "autoMode.allow", "$defaults")
    assert Path(p).read_text() == before


def test_json_merge_unions_an_automode_array_without_dropping_existing_entries(tmp_path):
    p = _write(tmp_path / "s.json", {"autoMode": {"allow": ["$defaults", "mine"]}, "permissions": {"ask": ["a"]}})
    frag = json.dumps({"autoMode": {"allow": ["new", "mine"]}, "permissions": {"ask": ["b"]}})
    out = subprocess.run([sys.executable, str(LIB), "json-merge", p], input=frag, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0
    data = json.loads(Path(p).read_text())
    assert data["autoMode"]["allow"] == ["$defaults", "mine", "new"]
    assert data["permissions"]["ask"] == ["a", "b"]
