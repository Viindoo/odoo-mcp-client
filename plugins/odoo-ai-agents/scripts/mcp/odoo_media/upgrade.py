"""upgrade.py - the one-time upgrade pass this server runs when it starts on a new plugin version.

Why here: Claude Code runs no plugin code when a plugin is installed, updated or reloaded; the one
thing of the plugin that starts again right at `/reload-plugins` (and at the next session) is its
stdio MCP server, and THIS server is the one that receives the configured values and the
operator's environment. So the server, in a background thread that never delays or stops serving,
compares the running plugin version with a stamp in the state root and, when they differ:

  1. moves the values an earlier version read from environment variables into the plugin's
     configured options and rewrites speech.toml / youtube.toml (scripts/lib/upgrade_values.py),
     then applies the moved values to this process so the tools work in this very session;
  2. moves a stand-alone `odoo-semantic` registration made by an earlier connect command into the
     odoo-semantic-mcp plugin's options and removes it (that plugin's scripts/migrate_connection.py,
     found through Claude Code's installed-plugins record; skipped with a note when the installed
     odoo-semantic-mcp is older than the one shipping it);
  3. writes the stamp (`<state root>/state/upgrade.json`, the report without any value) and a
     one-line notice (`upgrade-notice.txt`) that the session-start readiness hook shows once.

A run from a `--plugin-dir` checkout has no marketplace id: nothing is moved and no stamp is
written. A failed configure call leaves no stamp either, so the next start tries again. Two
servers starting at once (two sessions) are serialized by a lock; the second finds the stamp.
"""
from __future__ import annotations

import datetime
import importlib.util
import json
import logging
import os
import shutil
import threading

from odoo_local import cli
from odoo_media import values

log = logging.getLogger("odoo-media.upgrade")
STAMP_NAME = "upgrade.json"
NOTICE_NAME = "upgrade-notice.txt"
LOCK_NAME = "upgrade.lock"
SIBLING = "odoo-semantic-mcp"

try:
    import fcntl
except ImportError:  # pragma: no cover - no flock on this platform
    fcntl = None


def state_dir():
    paths = cli.load_lib("paths")
    return os.path.join(paths._home(), "state")


def stamp_path():
    return os.path.join(state_dir(), STAMP_NAME)


def read_stamp():
    try:
        with open(stamp_path(), encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def summary():
    """What media_info reports: the last upgrade pass, without any value."""
    stamp = read_stamp()
    if not stamp:
        return {"version": None}
    keep = ("version", "at", "moved", "missing", "skipped", "connection", "notes")
    return dict((k, stamp.get(k)) for k in keep if k in stamp)


def _installed_path(plugin_id, config_dir=None):
    """The install path Claude Code records for `name@marketplace`, or ''."""
    base = config_dir or os.environ.get("CLAUDE_CONFIG_DIR", "").strip() or os.path.expanduser("~/.claude")
    try:
        with open(os.path.join(base, "plugins", "installed_plugins.json"), encoding="utf-8") as fh:
            rows = (json.load(fh).get("plugins") or {}).get(plugin_id) or []
    except (OSError, ValueError):
        return ""
    if isinstance(rows, dict):
        rows = [rows]
    for row in rows:
        path = str((row or {}).get("installPath") or "")
        if path and os.path.isdir(path):
            return path
    return ""


def _sibling_module(marketplace, config_dir=None):
    path = _installed_path("%s@%s" % (SIBLING, marketplace), config_dir)
    script = os.path.join(path, "scripts", "migrate_connection.py") if path else ""
    if not script or not os.path.isfile(script):
        return None
    spec = importlib.util.spec_from_file_location("odoo_semantic_migrate_connection", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _apply_in_process(moved, environ):
    """The moved values reach this server at the next reload; apply them now as well."""
    env_for_option = dict((option, name) for name, option in values.OPTION.items())
    for option, source in moved:
        target = env_for_option.get(option)
        value = environ.get(source, "").strip()
        if target and value and not values.present(target):
            os.environ[target] = value


def run_once(version, plugin_root, environ=None, claude=None, config_dir=None):
    """The pass itself. Returns the report, or None when nothing had to run."""
    environ = os.environ if environ is None else environ
    upgrade_values = cli.load_lib("upgrade_values")
    # ODOO_MEDIA_PLUGIN_ID: the test seam that stands in for a marketplace install path
    pid = environ.get("ODOO_MEDIA_PLUGIN_ID", "").strip() or upgrade_values.plugin_id(root=str(plugin_root))
    if not pid:
        log.info("upgrade pass skipped: %s is not a marketplace install", plugin_root)
        return None
    marketplace = pid.split("@", 1)[1]
    claude = claude or shutil.which("claude")
    report = {"version": version, "at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
              "moved": [], "missing": [], "skipped": [], "connection": {}, "notes": []}
    clean = True
    if not claude:
        report["notes"].append("the claude command is not on PATH: nothing could be moved")
        clean = False
    else:
        vals = upgrade_values.apply(pid, claude, environ)
        report["moved"] = [option for option, _ in vals["moved"]]
        report["missing"] = list(vals["missing"])
        report["skipped"] = list(vals["skipped"])
        if vals["failed"]:
            report["notes"].append("configure failed for %s: %s" % (", ".join(vals["failed"]), vals["error"]))
            clean = False
        _apply_in_process(vals["moved"], environ)
        try:
            module = _sibling_module(marketplace, config_dir)
        except Exception as exc:  # noqa: BLE001 - a broken sibling must not stop this server
            module, report["connection"] = None, {"error": "could not load %s: %s" % (SIBLING, exc)}
        if module is not None:
            conn = module.apply("%s@%s" % (SIBLING, marketplace), claude)
            report["connection"] = {"found": conn["found"], "moved": conn["moved"], "removed": conn["removed"],
                                    "error": conn["error"]}
            if conn["error"] and conn["found"]:
                clean = False
        elif "error" not in report["connection"]:
            report["connection"] = {"found": None, "note": "%s on this machine ships no migration; "
                                    "/odoo-semantic-mcp:connect handles an older registration" % SIBLING}
    if clean:
        _write_stamp(report)
    else:
        log.warning("upgrade pass incomplete, will run again at the next start: %s", report["notes"])
    return report


def _write_stamp(report):
    os.makedirs(state_dir(), exist_ok=True)
    tmp = stamp_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, sort_keys=True)
    os.replace(tmp, stamp_path())
    lines = []
    if report["moved"]:
        lines.append("moved into the plugin configuration: %s" % ", ".join(report["moved"]))
    if report["missing"]:
        lines.append("still to enter in the plugin dialog (/plugin > odoo-ai-agents > Configure): %s"
                     % ", ".join(report["missing"]))
    conn = report.get("connection") or {}
    if conn.get("removed"):
        lines.append("the stand-alone odoo-semantic registration moved into odoo-semantic-mcp and was removed")
    elif conn.get("error"):
        lines.append("odoo-semantic registration: %s" % conn["error"])
    if lines:
        text = "odoo-ai-agents %s upgrade: %s. Run /reload-plugins once (or start a new session)." % (
            report["version"], "; ".join(lines))
        with open(os.path.join(state_dir(), NOTICE_NAME), "w", encoding="utf-8") as fh:
            fh.write(text + "\n")


def _locked_run(version, plugin_root):
    try:
        os.makedirs(state_dir(), exist_ok=True)
        if read_stamp().get("version") == version:
            return
        with open(os.path.join(state_dir(), LOCK_NAME), "a+") as lock:
            if fcntl is not None:
                try:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError:
                    log.info("upgrade pass: another server holds the lock")
                    return
            if read_stamp().get("version") == version:
                return
            report = run_once(version, plugin_root)
            if report:
                log.info("upgrade pass for %s: moved=%s missing=%s connection=%s", version, report["moved"],
                         report["missing"], (report.get("connection") or {}).get("removed"))
    except Exception:  # noqa: BLE001 - never let the pass take the server down
        log.exception("upgrade pass failed")


def start(version, plugin_root):
    """Run the pass in a daemon thread; serving starts at once."""
    thread = threading.Thread(target=_locked_run, args=(version, plugin_root), name="odoo-media-upgrade", daemon=True)
    thread.start()
    return thread
