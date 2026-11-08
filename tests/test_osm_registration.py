"""The Odoo Semantic server counts as set up when the odoo-semantic-mcp plugin is enabled with its
URL, or when a server is registered by hand - and only then.

The setup gate (00-osm-gate.sh) and the intent hook (detect-intent.sh) share one decision,
scripts/lib/osm_registration.py. Every case runs in a sandboxed HOME, config dir, registration
file and working directory.

Run: python -m pytest tests/test_osm_registration.py -v
"""
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
HELPER = PLUGIN / "scripts" / "lib" / "osm_registration.py"
GATE = PLUGIN / "scripts" / "setup-steps" / "00-osm-gate.sh"
HOOK = PLUGIN / "hooks" / "detect-intent.sh"
PID = "odoo-semantic-mcp@viindoo-plugins"
LOOKUP = "Viindoo 17 gồm những module nào trong profile standard_viindoo_17?"

needs_bash = pytest.mark.skipif(shutil.which("bash") is None, reason="bash steps")


class Box:
    def __init__(self, tmp_path):
        self.home = tmp_path / "home"
        self.cfg_dir = tmp_path / "cfg"
        self.cwd = tmp_path / "work"
        self.bin = tmp_path / "bin"
        for d in (self.home, self.cfg_dir, self.cwd, self.bin):
            d.mkdir()
        self.claude_json = tmp_path / "claude.json"
        self.claude_json.write_text("{}", encoding="utf-8")

    def env(self):
        e = {k: v for k, v in os.environ.items()
             if not k.startswith(("CLAUDE", "ODOO_AI"))}
        e.update({"HOME": str(self.home), "CLAUDE_CONFIG_DIR": str(self.cfg_dir),
                  "CLAUDE_CONFIG": str(self.claude_json), "ODOO_AI_HOME": str(self.home / ".odoo-ai"),
                  "CLAUDE_PLUGIN_ROOT": str(PLUGIN), "PATH": f"{self.bin}{os.pathsep}{e['PATH']}"})
        return e

    def settings(self, enabled=True, url="https://osm.example/mcp/", where=None):
        data = {"enabledPlugins": {PID: enabled}}
        if url is not None:
            data["pluginConfigs"] = {PID: {"options": {"mcp_url": url}}}
        path = where or self.cfg_dir / "settings.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")

    def hand(self, url="https://hand.example/mcp", project=False):
        entry = {"mcpServers": {"odoo-semantic": {"type": "http", "url": url}}}
        data = {"projects": {str(self.cwd): entry}} if project else entry
        self.claude_json.write_text(json.dumps(data), encoding="utf-8")

    def curl(self, ok):
        path = self.bin / "curl"
        path.write_text(f"#!/bin/sh\nexit {0 if ok else 22}\n", encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IEXEC)

    def find(self):
        p = subprocess.run([sys.executable, str(HELPER), "--cwd", str(self.cwd)], capture_output=True,
                           text=True, env=self.env())
        out = dict(line.split("=", 1) for line in p.stdout.splitlines())
        return p.returncode, out

    def gate(self):
        return subprocess.run(["bash", str(GATE), "check"], capture_output=True, text=True,
                              env=self.env(), cwd=self.cwd).returncode

    def hints(self):
        payload = {"hook_event_name": "UserPromptSubmit", "prompt": LOOKUP,
                   "transcript_path": str(self.home / "none.jsonl")}
        p = subprocess.run(["bash", str(HOOK)], input=json.dumps(payload), capture_output=True,
                           text=True, env=self.env(), cwd=self.cwd)
        assert p.returncode == 0, p.stderr
        return json.loads(p.stdout)["hookSpecificOutput"]["additionalContext"] if p.stdout.strip() else ""


@pytest.fixture
def box(tmp_path):
    return Box(tmp_path)


def test_an_enabled_plugin_with_its_url_is_found_without_a_hand_registration(box):
    box.settings()
    rc, out = box.find()
    assert rc == 0 and out == {"OSM_URL": "https://osm.example", "OSM_SOURCE": "plugin"}


@pytest.mark.parametrize("kwargs", [{"enabled": False}, {"url": None}], ids=["disabled", "no-url"])
def test_a_disabled_plugin_or_one_without_a_url_is_not_found(box, kwargs):
    box.settings(**kwargs)
    rc, out = box.find()
    assert rc == 1 and out == {}


def test_a_plugin_that_is_not_installed_is_not_found(box):
    assert box.find() == (1, {})


def test_a_project_setting_overrides_the_user_setting(box):
    box.settings(url="https://user.example/mcp")
    box.settings(url="https://project.example/mcp", where=box.cwd / ".claude" / "settings.json")
    assert box.find()[1]["OSM_URL"] == "https://project.example"


@pytest.mark.parametrize("project", [False, True], ids=["user-scope", "project-scope"])
def test_a_hand_registered_server_is_found_and_wins_over_the_plugin(box, project):
    box.hand(project=project)
    assert box.find() == (0, {"OSM_URL": "https://hand.example", "OSM_SOURCE": "hand-registered"})
    box.settings()
    assert box.find()[1]["OSM_SOURCE"] == "hand-registered"


def test_a_file_that_only_mentions_the_name_in_a_path_or_usage_key_is_not_found(box):
    box.claude_json.write_text(json.dumps({
        "projects": {"/home/user/odoo-semantic-notes": {"allowedTools": []}},
        "skillUsage": {"odoo-semantic:connect": 3}}), encoding="utf-8")
    assert box.find() == (1, {})


def test_a_malformed_file_counts_as_absent(box):
    box.claude_json.write_text("{not json", encoding="utf-8")
    (box.cfg_dir / "settings.json").write_text("[", encoding="utf-8")
    assert box.find() == (1, {})


@needs_bash
@pytest.mark.parametrize("curl_ok, expected", [(True, 0), (False, 1)], ids=["reachable", "unreachable"])
def test_the_gate_passes_for_a_plugin_install_only_when_its_server_answers(box, curl_ok, expected):
    box.settings()
    box.curl(curl_ok)
    assert box.gate() == expected


@needs_bash
@pytest.mark.parametrize("kwargs", [{"enabled": False}, {"url": None}], ids=["disabled", "no-url"])
def test_the_gate_fails_when_the_plugin_is_off_or_has_no_url(box, kwargs):
    box.settings(**kwargs)
    box.curl(True)
    assert box.gate() == 1


@needs_bash
def test_the_gate_passes_for_a_hand_registered_server(box):
    box.hand()
    box.curl(True)
    assert box.gate() == 0


@needs_bash
@pytest.mark.skipif(shutil.which("jq") is None, reason="the hook needs jq")
def test_the_lookup_hint_fires_for_a_configured_plugin(box):
    box.settings()
    assert "[OSM-lookup]" in box.hints()


@needs_bash
@pytest.mark.skipif(shutil.which("jq") is None, reason="the hook needs jq")
def test_no_osm_hint_fires_when_the_name_only_appears_in_a_project_path(box):
    box.claude_json.write_text(json.dumps({"projects": {"/home/user/odoo-semantic-notes": {}}}),
                               encoding="utf-8")
    assert "[OSM" not in box.hints()
