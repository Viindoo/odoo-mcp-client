#!/usr/bin/env python3
"""migrate_connection.py - move a stand-alone `odoo-semantic` registration into the plugin's
configured options, and remove the registration that hides the plugin's server.

An earlier `/odoo-semantic-mcp:connect` registered the server by hand (`claude mcp add --scope
user odoo-semantic <url> --header "X-API-Key: ..."`), which Claude Code keeps in its user
configuration file and which SHADOWS the plugin's own server of the same name. The plugin now
declares the two values as options (`plugin.json` userConfig `mcp_url`, `api_key`), read by its
`.mcp.json`.

    migrate_connection.py plan  [--plugin-id ID]
        FOUND=user|local|none  URL=<url>  VALUE=present|absent  STATE=unset|configured|unknown
        PLUGIN_ID=<name@marketplace or empty>
    migrate_connection.py apply [--plugin-id ID]
        One `claude plugin configure ID --values-stdin` call with the URL and the value (stdin
        only, never an argument, never printed), then a backup of the user configuration file and
        `claude mcp remove odoo-semantic --scope <scope>`. Prints MOVED=mcp_url, MOVED=api_key,
        REMOVED=<scope>, NEXT=/reload-plugins; SKIPPED=<option> when the plugin already holds it
        (the stand-alone entry is still removed, after a backup); exit 1 when a step failed.

Who runs it: the operator in their own terminal, or the odoo-ai-agents odoo-media server when it
starts on a new plugin version (that plugin depends on this one and imports `apply`) - never the
agent (Claude Code's auto mode stops an agent that materializes such a value). The plugin id is
`--plugin-id`, else derived from `$CLAUDE_PLUGIN_ROOT` (`.../cache/<marketplace>/<plugin>/<version>`).
The user configuration file is `$CLAUDE_CONFIG_DIR/.claude.json` when that variable is set, else
`~/.claude.json`. Stdlib only. Tests: tests/test_migrate_connection.py (a stub `claude` on PATH).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time

PLUGIN_NAME = "odoo-semantic-mcp"
SERVER = "odoo-semantic"
HEADER = "X-API-Key"
_CACHE_RE = re.compile(r"[/\\]cache[/\\]([^/\\]+)[/\\]([^/\\]+)[/\\][^/\\]+[/\\]?$")


def plugin_id(explicit=None, root=None):
    if explicit:
        return explicit
    root = root if root is not None else os.environ.get("CLAUDE_PLUGIN_ROOT", "")
    m = _CACHE_RE.search(root.rstrip("/\\") + "/") if root else None
    if m and m.group(2) == PLUGIN_NAME:
        return "%s@%s" % (m.group(2), m.group(1))
    return ""


def config_path():
    base = os.environ.get("CLAUDE_CONFIG_DIR", "").strip()
    return os.path.join(base, ".claude.json") if base else os.path.expanduser("~/.claude.json")


def find_entry(path=None, cwd=None):
    """(scope, entry) for a stand-alone odoo-semantic registration: user scope first, then the
    local scope of the current project; (None, None) when there is none or the file is unreadable."""
    path = path or config_path()
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None, None
    entry = (data.get("mcpServers") or {}).get(SERVER)
    if isinstance(entry, dict):
        return "user", entry
    cwd = cwd or os.getcwd()
    project = (data.get("projects") or {}).get(cwd) or {}
    entry = (project.get("mcpServers") or {}).get(SERVER)
    if isinstance(entry, dict):
        return "local", entry
    return None, None


def values_of(entry):
    url = str(entry.get("url") or "").strip()
    headers = entry.get("headers") or {}
    value = ""
    for key, val in headers.items():
        if str(key).lower() == HEADER.lower():
            value = str(val or "").strip()
    return url, value


def configured_options(pid, claude="claude"):
    if not pid:
        return None
    try:
        proc = subprocess.run([claude, "plugin", "configure", pid, "--json"], capture_output=True, text=True,
                              timeout=60, check=False)
        return set(json.loads(proc.stdout).get("configured") or [])
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def apply(pid, claude="claude", config=None):
    """Move the registration. Returns a report (no value in it):
    {"found": scope|None, "no_plugin_id": bool, "moved": [...], "skipped": [...], "missing": [...],
     "failed": [...], "backup": path, "removed": scope|None, "error": str}."""
    path = config or config_path()
    scope, entry = find_entry(path)
    report = {"found": scope, "no_plugin_id": False, "moved": [], "skipped": [], "missing": [], "failed": [],
              "backup": "", "removed": None, "error": ""}
    if not entry:
        return report
    if not pid:
        report["no_plugin_id"] = True
        report["error"] = "no plugin id: pass --plugin-id <name@marketplace> (what `claude plugin list` shows)"
        return report
    url, value = values_of(entry)
    done = configured_options(pid, claude) or set()
    payload = {}
    if url and "mcp_url" not in done:
        payload["mcp_url"] = url
    elif url:
        report["skipped"].append("mcp_url")
    if value and "api_key" not in done:
        payload["api_key"] = value
    elif "api_key" in done:
        report["skipped"].append("api_key")
    else:
        report["missing"].append("api_key")
    if payload:
        try:
            proc = subprocess.run([claude, "plugin", "configure", pid, "--values-stdin"], input=json.dumps(payload),
                                  capture_output=True, text=True, timeout=120, check=False)
            rc, err = proc.returncode, proc.stderr.strip()
        except (OSError, subprocess.TimeoutExpired) as exc:
            rc, err = 1, str(exc)
        if rc != 0:
            report["failed"] = sorted(payload)
            report["error"] = (err.splitlines()[-1] if err else "claude plugin configure exited %d" % rc) \
                + " - the stand-alone registration was left in place"
            return report
        report["moved"] = sorted(payload)
    if "api_key" not in done and "api_key" not in payload:
        report["error"] = ("no value to move and none configured: the stand-alone registration was left in "
                           "place; enter the value in the plugin dialog, then remove the registration")
        return report
    backup = "%s.bak.%d" % (path, int(time.time()))
    try:
        shutil.copy2(path, backup)
        os.chmod(backup, 0o600)
    except OSError as exc:
        report["error"] = "could not back up %s: %s - the stand-alone registration was left in place" % (path, exc)
        return report
    report["backup"] = backup
    try:
        proc = subprocess.run([claude, "mcp", "remove", SERVER, "--scope", scope], capture_output=True, text=True,
                              timeout=60, check=False)
        rc = proc.returncode
    except (OSError, subprocess.TimeoutExpired) as exc:
        rc = 1
    if rc != 0:
        report["error"] = ("could not remove the %s-scope registration; run: claude mcp remove %s --scope %s"
                           % (scope, SERVER, scope))
        return report
    report["removed"] = scope
    return report


def cmd_plan(args):
    pid = plugin_id(args.plugin_id)
    scope, entry = find_entry(args.config)
    print("PLUGIN_ID=%s" % pid)
    if not entry:
        print("FOUND=none")
        return 0
    url, value = values_of(entry)
    done = configured_options(pid, args.claude)
    state = "unknown" if done is None else ("configured" if "api_key" in done else "unset")
    print("FOUND=%s URL=%s VALUE=%s STATE=%s" % (scope, url, "present" if value else "absent", state))
    return 0


def cmd_apply(args):
    pid = plugin_id(args.plugin_id)
    report = apply(pid, args.claude, args.config or None)
    if not report["found"]:
        print("FOUND=none")
        return 0
    for option in report["skipped"]:
        print("SKIPPED=%s" % option)
    for option in report["missing"]:
        print("MISSING=%s" % option)
    for option in report["moved"]:
        print("MOVED=%s" % option)
    for option in report["failed"]:
        print("FAILED=%s" % option)
    if report["backup"]:
        print("BACKUP=%s" % report["backup"])
    if report["removed"]:
        print("REMOVED=%s" % report["removed"])
        print("NEXT=/reload-plugins")
    if report["error"]:
        print("x %s" % report["error"], file=sys.stderr)
        return 1
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--plugin-id", dest="plugin_id", default="")
    parser.add_argument("--claude", default="claude", help=argparse.SUPPRESS)
    parser.add_argument("--config", default="", help=argparse.SUPPRESS)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("plan")
    sub.add_parser("apply")
    args = parser.parse_args(argv)
    return {"plan": cmd_plan, "apply": cmd_apply}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
