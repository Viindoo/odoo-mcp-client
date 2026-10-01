#!/usr/bin/env python3
"""capture_paths.py - the decision behind hooks/block-capture-outside-state-root.sh.

A browser MCP tool that writes a file (a screenshot, a snapshot, a trace, a Lighthouse report, a
network body) takes the destination as an argument. A RELATIVE destination resolves against the
session's working directory - usually the user's repository - and the servers allow it, because
the client's roots include that directory. So the launch flags (browser_mcp_servers.py) only make
an absolute capture under the state root succeed; they cannot stop a relative one. This check
does: for this plugin's browser families (bare `mcp__<family>__*` names and this plugin's own
`mcp__plugin_<plugin>_<family>__*` namespace - never another plugin's), a write destination must
be absolute and inside the roots the family is launched to write under
(browser_mcp_servers.allowed_roots: the state root, plus the $ODOO_AI_PROJECT_DIR /
$ODOO_AI_WORKTREE_DIR overrides for chrome-devtools; <root>/projects for playwright).

Hard deny only when the server provably runs with its state-root flag: the bundled chrome-devtools
(started by scripts/mcp/browser_mcp_launch.py), or an opt-in family whose user-scope entry in
Claude's config carries the flag for this state root. Otherwise the call is allowed with an
advisory to re-run setup - refusing every capture of a user who has not re-run setup since the
flags existed would break them outright.

Paths are compared with realpath on both sides (a macOS temp dir is a symlink) and
os.path.normcase, and a Git-Bash `/c/Users/...` path is read as `C:\\Users\\...` on Windows.

Fails OPEN on every error: no output means "allow". Syntax stays parseable by very old Python 3
(no f-strings, no annotations).

CLI:  python3 capture_paths.py hook   < PreToolUse payload JSON   (prints the hook output or nothing)
"""

import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.path.dirname(os.path.dirname(_HERE))

# Keys whose value is a file or directory the tool WRITES.
PATH_KEYS = ("filePath", "filename", "outputDirPath", "webmPath", "requestFilePath",
             "responseFilePath")

# Tools whose path argument is only READ (an upload, an extension, a heap snapshot being
# queried, a storage state or a script being loaded, a directory being listed).
READ_ONLY_TOOLS = frozenset([
    "upload_file", "install_extension", "close_heapsnapshot", "compare_heapsnapshots",
    "query_heapsnapshot_objects", "browser_file_upload", "browser_run_code_unsafe",
    "browser_set_storage_state", "list_recordings",
])
READ_ONLY_PREFIXES = ("get_heapsnapshot_",)

SETUP_REMEDY = "Run /odoo-ai-agents:odoo-setup browser, then restart the session."


def _lib():
    if _HERE not in sys.path:
        sys.path.insert(0, _HERE)
    import browser_mcp_servers
    import browser_prefixes
    return browser_mcp_servers, browser_prefixes


def split_tool(tool_name):
    """(family, short_tool, namespace) for one of this plugin's browser tools, else None.
    namespace is "plugin" (mcp__plugin_<this plugin>_<family>__) or "bare" (mcp__<family>__)."""
    ssot, prefixes = _lib()
    plugin = prefixes._normalize(prefixes._read_plugin_name(prefixes.PLUGIN_ROOT))
    families = sorted(ssot.ALL_SERVERS, key=len, reverse=True)
    alt = "|".join(re.escape(f) for f in families)
    m = re.match(r"^mcp__(plugin_" + re.escape(plugin) + r"_)?(" + alt + r")__(.+)$", tool_name)
    if not m:
        return None
    return m.group(2), m.group(3), ("plugin" if m.group(1) else "bare")


def _bundled_via_launcher(family):
    """True when this plugin's .mcp.json starts `family` through browser_mcp_launch.py."""
    with open(os.path.join(PLUGIN_ROOT, ".mcp.json"), encoding="utf-8") as fh:
        entry = (json.load(fh).get("mcpServers") or {}).get(family) or {}
    args = [str(a) for a in (entry.get("args") or [])]
    return family in args and any(a.endswith("browser_mcp_launch.py") for a in args)


def server_has_root_flag(family, namespace, root, cwd, environ):
    """True when the server answering this tool is launched with its state-root flag."""
    ssot, _prefixes = _lib()
    if namespace == "plugin":
        return _bundled_via_launcher(family)
    try:
        with open(ssot.claude_config_path(environ), encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return False
    entries = [(data.get("mcpServers") or {}).get(family)]
    projects = data.get("projects") or {}
    for key in (cwd, os.path.realpath(cwd) if cwd else None):
        if key and isinstance(projects.get(key), dict):
            entries.append((projects[key].get("mcpServers") or {}).get(family))
    return any(ssot.configured_with_root(family, e, root) for e in entries if e)


def native_path(path):
    """A Git-Bash/MSYS drive path (/c/Users/x) as the Windows path it names; else unchanged."""
    if os.name == "nt":
        m = re.match(r"^/([A-Za-z])(?:/(.*))?$", path)
        if m:
            return m.group(1).upper() + ":\\" + (m.group(2) or "").replace("/", "\\")
    return path


def violations(family, tool_input, root, environ):
    """[(key, value, why)] for every write destination outside the family's allowed roots."""
    ssot, _prefixes = _lib()
    allowed = ssot.allowed_roots(family, root, environ)
    out = []
    for key in PATH_KEYS:
        value = tool_input.get(key)
        if not isinstance(value, str) or not value.strip():
            continue
        path = native_path(value.strip())
        if not os.path.isabs(path):
            out.append((key, value, "a relative path (it resolves against the session's working "
                                    "directory, usually the repository)"))
        elif not any(ssot.is_inside(path, r) for r in allowed):
            out.append((key, value, "outside " + " and ".join(allowed)))
    return out


def check(tool_name, tool_input, cwd, environ):
    """Return (decision, message): ("allow", None), ("deny", reason) or ("advise", text)."""
    parsed = split_tool(tool_name)
    if parsed is None or not isinstance(tool_input, dict):
        return "allow", None
    family, short, namespace = parsed
    if short in READ_ONLY_TOOLS or short.startswith(READ_ONLY_PREFIXES):
        return "allow", None
    if not any(isinstance(tool_input.get(k), str) and tool_input.get(k).strip() for k in PATH_KEYS):
        return "allow", None
    ssot, _prefixes = _lib()
    root = ssot.state_root()
    allowed = ssot.allowed_roots(family, root, environ)
    bad = violations(family, tool_input, root, environ)
    remedy = ("Capture to an absolute path under %s (your run's <ISOLATE_DIR>/visual/...), then "
              "mv the file where it must go; never retry with a relative path." % allowed[0])
    findings = "; ".join("%s=%r is %s" % (k, v, why) for k, v, why in bad)
    if server_has_root_flag(family, namespace, root, cwd or "", environ):
        if not bad:
            return "allow", None
        return "deny", "Capture destination refused: %s. %s" % (findings, remedy)
    text = ("The %s browser MCP server is not launched with its state-root flag, so a capture "
            "under %s can be refused and a relative path lands in the working directory. %s"
            % (family, root, SETUP_REMEDY))
    if bad:
        text += " This call: %s. %s" % (findings, remedy)
    return "advise", text


def hook_output(payload, environ):
    decision, message = check(payload.get("tool_name") or "", payload.get("tool_input"),
                              payload.get("cwd") or "", environ)
    if decision == "deny":
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                       "permissionDecisionReason": message}}
    if decision == "advise":
        return {"systemMessage": message,
                "hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": message}}
    return None


def main(argv):
    if argv != ["hook"]:
        sys.stderr.write("Usage: capture_paths.py hook < payload.json\n")
        return 2
    try:
        payload = json.loads(sys.stdin.read())
        out = hook_output(payload, os.environ) if isinstance(payload, dict) else None
    except Exception:
        return 0
    if out is not None:
        sys.stdout.write(json.dumps(out) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
