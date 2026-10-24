#!/usr/bin/env python3
"""upgrade_values.py - move the values an earlier plugin version kept in environment variables
into the plugin's configured options, and rewrite the files that named those variables.

An earlier `speech.toml` spelled `api_key_env = "<NAME>"` and an earlier `youtube.toml` spelled
`client_id_env` / `client_secret_env` / `refresh_token_env` (defaults YOUTUBE_CLIENT_ID,
YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN): the NAME of a variable the operator exported in
their shell. The current plugin reads those values from its configured options instead
(`plugin.json` userConfig, stored by Claude Code), which only the odoo-media MCP server receives.

    upgrade_values.py plan  [--plugin-id ID]
        One line per option an earlier configuration points at:
          OPTION=<option> SOURCE=<variable name> VALUE=present|absent STATE=unset|configured|unknown
        plus PLUGIN_ID=<name@marketplace or empty> and SPEECH=<path>|none, YOUTUBE=<path>|none.
        `present` = the variable is set and non-empty in THIS process's environment (a value
        never prints). STATE comes from `claude plugin configure ID --json` when it runs.

    upgrade_values.py apply [--plugin-id ID]
        For every option whose value is present and not configured yet: one
        `claude plugin configure ID --values-stdin` call carrying all of them (stdin only, never
        an argument, never printed), then the files are rewritten in the current form (backup,
        atomic) so the variable names disappear. Prints MOVED=<option>, SKIPPED=<option>
        (already configured), MISSING=<option> (the variable is not set here: enter the value
        in the plugin dialog), FAILED=<option>, REWROTE=<path>, and NEXT=/reload-plugins when
        anything moved. Exit 1 when a configure call failed or no plugin id is known.

Who runs it: the operator in their own terminal, or the odoo-media server when it starts on a new
plugin version (scripts/mcp/odoo_media/upgrade.py) - never the agent (Claude Code's auto mode
stops an agent that materializes such a value). The plugin id is `--plugin-id`, else derived from
`$CLAUDE_PLUGIN_ROOT` (`.../cache/<marketplace>/<plugin>/<version>`); a checkout loaded with
`--plugin-dir` has none, and `apply` then only reports.

Stdlib only. Tests: tests/test_upgrade_values.py (a stub `claude` on PATH).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

_LIB_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _LIB_DIR)
import config_merge  # noqa: E402
import docs_site_config  # noqa: E402
import speech_config  # noqa: E402
import youtube_config  # noqa: E402

PLUGIN_NAME = "odoo-ai-agents"
SPEECH_OPTION = "speech_api_key"
YOUTUBE_LEGACY_DEFAULTS = {"client_id_env": "YOUTUBE_CLIENT_ID", "client_secret_env": "YOUTUBE_CLIENT_SECRET",
                           "refresh_token_env": "YOUTUBE_REFRESH_TOKEN"}
YOUTUBE_OPTION_FOR = {"client_id_env": "youtube_client_id", "client_secret_env": "youtube_client_secret",
                      "refresh_token_env": youtube_config.OPTION_FOR_SLOT["docs"]}
_CACHE_RE = re.compile(r"[/\\]cache[/\\]([^/\\]+)[/\\]([^/\\]+)[/\\][^/\\]+[/\\]?$")


def plugin_id(explicit=None, root=None, name=PLUGIN_NAME):
    """`name@marketplace` from --plugin-id, else from a marketplace cache path; '' otherwise."""
    if explicit:
        return explicit
    root = root if root is not None else os.environ.get("CLAUDE_PLUGIN_ROOT", "")
    m = _CACHE_RE.search(root.rstrip("/\\") + "/") if root else None
    if m and m.group(2) == name:
        return "%s@%s" % (m.group(2), m.group(1))
    return ""


def _raw(path):
    """The file as written, no migration (the legacy names are what we need)."""
    try:
        with open(path, encoding="utf-8") as fh:
            return docs_site_config._loads(fh.read())
    except FileNotFoundError:
        return None


def legacy_sources(speech_path=None, youtube_path=None):
    """[(option, variable name, file path)] for every legacy variable name on disk."""
    out = []
    sp = speech_path or speech_config.speech_path()
    cfg = _raw(sp)
    if isinstance(cfg, dict):
        for section in ("tts", "stt"):
            table = cfg.get(section)
            if isinstance(table, dict):
                name = str(table.get(speech_config.LEGACY_KEY) or "").strip()
                if name:
                    out.append((SPEECH_OPTION, name, sp))
                    break
    yp = youtube_path or youtube_config.youtube_path()
    cfg = _raw(yp)
    if isinstance(cfg, dict) and isinstance(cfg.get(youtube_config.LEGACY_TABLE), dict):
        old = cfg[youtube_config.LEGACY_TABLE]
        for key in youtube_config.LEGACY_ENV_KEYS:
            name = str(old.get(key) or YOUTUBE_LEGACY_DEFAULTS[key]).strip()
            if name:
                out.append((YOUTUBE_OPTION_FOR[key], name, yp))
    return out


def configured_options(pid, claude="claude"):
    """The option names already configured, or None when that cannot be read."""
    if not pid:
        return None
    try:
        proc = subprocess.run([claude, "plugin", "configure", pid, "--json"], capture_output=True, text=True,
                              timeout=60, check=False)
        data = json.loads(proc.stdout)
        return set(data.get("configured") or [])
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def plan(pid, claude="claude", environ=None, speech_path=None, youtube_path=None):
    env = os.environ if environ is None else environ
    sources = legacy_sources(speech_path, youtube_path)
    done = configured_options(pid, claude) if sources else set()
    rows = []
    for option, name, path in sources:
        present = bool(env.get(name, "").strip())
        state = "unknown" if done is None else ("configured" if option in done else "unset")
        rows.append({"option": option, "source": name, "present": present, "state": state, "path": path})
    return rows


def _rewrite(path, kind):
    """Rewrite one file in the current form (its reader migrates), with a backup; '' when absent."""
    if not os.path.exists(path):
        return ""
    if kind == "speech":
        cfg = speech_config.read_config(path)
        text = speech_config.render(cfg)
    else:
        cfg = youtube_config.read_config(path)
        text = youtube_config.render({"channels": cfg["channels"]})
    with config_merge.locked_target(path):
        config_merge._backup(path)
        config_merge._atomic_replace(path, text)
    return path


def apply(pid, claude="claude", environ=None, speech_path=None, youtube_path=None):
    """Move what can be moved. Returns a report (no value in it):
    {"nothing": bool, "no_plugin_id": bool, "moved": [(option, variable name)], "skipped": [...],
     "missing": [...], "failed": [...], "rewrote": [paths], "error": str}."""
    env = os.environ if environ is None else environ
    sp = speech_path or speech_config.speech_path()
    yp = youtube_path or youtube_config.youtube_path()
    report = {"nothing": False, "no_plugin_id": False, "moved": [], "skipped": [], "missing": [], "failed": [],
              "rewrote": [], "error": ""}
    rows = plan(pid, claude, env, sp, yp)
    if not rows:
        report["nothing"] = True
        return report
    if not pid:
        report["no_plugin_id"] = True
        report["missing"] = [row["option"] for row in rows]
        return report
    values = {}
    for row in rows:
        if row["state"] == "configured":
            report["skipped"].append(row["option"])
        elif not row["present"]:
            report["missing"].append(row["option"])
        else:
            values[row["option"]] = env[row["source"]].strip()
    if values:
        try:
            proc = subprocess.run([claude, "plugin", "configure", pid, "--values-stdin"], input=json.dumps(values),
                                  capture_output=True, text=True, timeout=120, check=False)
            rc, err = proc.returncode, proc.stderr.strip()
        except (OSError, subprocess.TimeoutExpired) as exc:
            rc, err = 1, str(exc)
        if rc == 0:
            report["moved"] = [(row["option"], row["source"]) for row in rows if row["option"] in values]
        else:
            report["failed"] = sorted(values)
            report["error"] = err.splitlines()[-1] if err else "claude plugin configure exited %d" % rc
            return report
    moved = {option for option, _ in report["moved"]}
    touched = {row["path"] for row in rows if row["option"] in moved or row["state"] == "configured"}
    for path in sorted(touched):
        done = _rewrite(path, "speech" if path == sp else "youtube")
        if done:
            report["rewrote"].append(done)
    return report


def cmd_plan(args):
    pid = plugin_id(args.plugin_id)
    print("PLUGIN_ID=%s" % pid)
    sp = args.speech or speech_config.speech_path()
    yp = args.youtube or youtube_config.youtube_path()
    print("SPEECH=%s" % (sp if os.path.exists(sp) else "none"))
    print("YOUTUBE=%s" % (yp if os.path.exists(yp) else "none"))
    for row in plan(pid, args.claude, speech_path=sp, youtube_path=yp):
        print("OPTION=%s SOURCE=%s VALUE=%s STATE=%s" % (row["option"], row["source"],
                                                         "present" if row["present"] else "absent", row["state"]))
    return 0


def cmd_apply(args):
    pid = plugin_id(args.plugin_id)
    report = apply(pid, args.claude, speech_path=args.speech or None, youtube_path=args.youtube or None)
    if report["nothing"]:
        print("NOTHING=no earlier variable names on disk")
        return 0
    if report["no_plugin_id"]:
        print("x no plugin id: pass --plugin-id <name@marketplace> (what `claude plugin list` shows); "
              "the values are then entered in the plugin dialog", file=sys.stderr)
    for option in report["skipped"]:
        print("SKIPPED=%s" % option)
    for option in report["missing"]:
        print("MISSING=%s" % option)
    for option, _ in report["moved"]:
        print("MOVED=%s" % option)
    if report["error"]:
        print("x %s" % report["error"], file=sys.stderr)
    for option in report["failed"]:
        print("FAILED=%s" % option)
    for path in report["rewrote"]:
        print("REWROTE=%s" % path)
    if report["moved"]:
        print("NEXT=/reload-plugins")
    return 1 if (report["failed"] or report["no_plugin_id"]) else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--plugin-id", dest="plugin_id", default="")
    parser.add_argument("--claude", default="claude", help=argparse.SUPPRESS)
    parser.add_argument("--speech", default="", help=argparse.SUPPRESS)
    parser.add_argument("--youtube", default="", help=argparse.SUPPRESS)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("plan")
    sub.add_parser("apply")
    args = parser.parse_args(argv)
    return {"plan": cmd_plan, "apply": cmd_apply}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
