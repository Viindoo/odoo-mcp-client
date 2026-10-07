"""Concurrent writers must leave a Claude settings file valid and complete.

Several SessionStart hooks of odoo-ai-agents add permission rules to the same
settings file, and Claude Code runs them at the same time. On a host whose
settings file lacks those rules (every fresh cloud session) each hook writes.
The contract under test: whatever runs concurrently, the file stays valid JSON,
keeps the keys it already had, and ends up holding every rule each writer added.

The writers here are the ones those hooks use (config_merge.py json-ensure-allow),
on a throwaway settings file under tmp_path.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
CONFIG_MERGE = PLUGIN / "scripts" / "lib" / "config_merge.py"

WRITERS = 24


def _seed(path):
    path.write_text(json.dumps({
        "attribution": {"commit": "", "pr": ""},
        "permissions": {"allow": ["Bash(git status:*)"], "deny": ["Read(./.env)"]},
    }, indent=2) + "\n", encoding="utf-8")


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_parallel_allow_rule_writers_keep_every_rule_and_valid_json(tmp_path):
    settings = tmp_path / "settings.json"
    _seed(settings)
    rules = [f"Bash(tool-{i}:*)" for i in range(WRITERS)]
    procs = [
        subprocess.Popen(
            [sys.executable, str(CONFIG_MERGE), "json-ensure-allow", str(settings), rule],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
        )
        for rule in rules
    ]
    errors = [p.communicate(timeout=60)[1] for p in procs]
    codes = [p.returncode for p in procs]

    assert codes == [0] * WRITERS, errors
    data = _load(settings)
    allow = data["permissions"]["allow"]
    assert set(rules) <= set(allow), sorted(set(rules) - set(allow))
    assert "Bash(git status:*)" in allow
    assert data["permissions"]["deny"] == ["Read(./.env)"]
    assert data["attribution"] == {"commit": "", "pr": ""}

