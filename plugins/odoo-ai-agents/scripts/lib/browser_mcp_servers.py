#!/usr/bin/env python3
"""browser_mcp_servers.py - SSOT for how each browser MCP family is launched.

The plugin ships SIX browser MCP families: three backends (chrome-devtools, playwright,
pagecast), each with a headless default and a `-headed` variant. ONE is eager - the headless
`chrome-devtools`, bundled in the plugin's `.mcp.json` and started through
`scripts/mcp/browser_mcp_launch.py`. The other five are opt-in, registered on demand by the
odoo-setup steps (`10-browser-mcp.sh` for Codex/Gemini, `12-browser-mcp-optin.sh` for Claude's
user scope). `browser_prefixes.py` derives the permission prefixes from ALL_SERVERS.

This module owns, per family:
  - the EXACT npm package pin (`BROWSER_MCP_{CHROME,PLAYWRIGHT,PAGECAST}_PIN` env overrides it).
    An exact version, never a major range: `npx -y pkg@1` reuses whatever 1.x a machine's npm
    cache holds, so file-write rules would differ between machines;
  - the base flags (headless/headed, --isolated);
  - the state-root flags that make an absolute capture path under the state root writable:
      chrome-devtools  --workspace=<root> (+ one per $ODOO_AI_PROJECT_DIR / $ODOO_AI_WORKTREE_DIR
                       override outside the root). Without it the server writes only inside the
                       client's roots (the session cwd) and the OS temp dir.
      playwright       --output-dir=<root>/projects (allowed roots = output dir + cwd; an
                       explicit filename resolves against the cwd) and --idle-timeout, which
                       closes a browser nobody drives. --output-max-size is never set: it
                       evicts files recursively under the output dir.
      pagecast         RECORDING_OUTPUT_DIR=<root>/scratch/pagecast (default is ./recordings).
  - the roots each family can write, which the capture-path gate (`capture_paths.py`) checks;
  - the pruning of the files the servers write on their own and of the captures no skill owns
    (`prune_browser_byproducts`).

The state root comes only from `paths.py` (`state_root()`), never from a path a shell built.

Imported by the launcher BEFORE any interpreter check, so this file keeps to syntax very old
Python 3 parses (no f-strings, no annotations) and imports nothing outside the stdlib at load.

CLI (for shell callers; nothing but data on stdout):
    servers {all|optin|eager}        family names, one per line
    npx-args <server>                pin + base flags, one per line (no state-root flags)
    pin <server>                     the package pin
    playwright-core-version          the playwright-core the pinned @playwright/mcp depends on
    spec <server>                    JSON {"command","args","env"} with resolved state-root flags
    claude-config                    the file Claude Code keeps user-scope MCP servers in
    drift                            "<runtime> <server>" per registration that differs from spec
    prune                            delete stale byproducts under the state root (silent)
"""

import json
import os
import re
import sys
import time

EAGER_SERVER = "chrome-devtools"
ALL_SERVERS = [
    "chrome-devtools", "chrome-devtools-headed",
    "playwright", "playwright-headed",
    "pagecast", "pagecast-headed",
]
OPTIN_SERVERS = [s for s in ALL_SERVERS if s != EAGER_SERVER]

_DEFAULT_PINS = {
    "chrome-devtools": "chrome-devtools-mcp@1.10.1",
    "playwright": "@playwright/mcp@0.0.83",
    "pagecast": "@mcpware/pagecast@0.2.1",
}
_PIN_ENV = {
    "chrome-devtools": "BROWSER_MCP_CHROME_PIN",
    "playwright": "BROWSER_MCP_PLAYWRIGHT_PIN",
    "pagecast": "BROWSER_MCP_PAGECAST_PIN",
}
# The exact `playwright-core` dependency of the pinned @playwright/mcp (`npm view
# @playwright/mcp@<pin> dependencies`). Bump it together with that pin.
PLAYWRIGHT_CORE_VERSION = "1.64.0-alpha-1790635538000"

# Milliseconds without a completed tool call before playwright closes its browser (the next
# call relaunches it). Shorter than the server's own one-hour headless default and also applied
# to headed browsers, which otherwise never close.
PLAYWRIGHT_IDLE_TIMEOUT_MS = 900000

# Server byproducts older than this are pruned.
BYPRODUCT_MAX_AGE_S = 24 * 3600
# Captures no skill owns (<ISOLATE_DIR>/visual/adhoc/<slug>/) older than this are pruned.
ADHOC_MAX_AGE_S = 30 * 24 * 3600

# Files playwright names itself at the top level of its output dir (`--output-dir`), plus its
# trace and session folders. The per-repo state dirs there are 12-hex keys and never match.
_PLAYWRIGHT_BYPRODUCT = re.compile(
    r"^(?:(?:console|page|element|video|download|storage-state|network|request|response|"
    r"result|find|session)-.+|traces)$")
_REPO_KEY = re.compile(r"^[0-9a-f]{12}$")


def backend(server):
    """'chrome-devtools' / 'playwright' / 'pagecast' for a family name; ValueError otherwise."""
    if server not in ALL_SERVERS:
        raise ValueError("unknown browser MCP family: %r" % (server,))
    return server[:-len("-headed")] if server.endswith("-headed") else server


def is_headed(server):
    return backend(server) != server


def pin(server, environ=None):
    environ = os.environ if environ is None else environ
    b = backend(server)
    return environ.get(_PIN_ENV[b]) or _DEFAULT_PINS[b]


def base_flags(server):
    b = backend(server)
    headless = [] if is_headed(server) else ["--headless"]
    if b == "chrome-devtools":
        return headless + ["--isolated"]
    if b == "playwright":
        return ["--caps=devtools"] + headless + ["--isolated"]
    # pagecast isolates per session itself and takes no --isolated.
    return headless


def npx_args(server, environ=None):
    """The args after `npx -y`: the pinned package, then the base flags."""
    return [pin(server, environ)] + base_flags(server)


def _clean(path):
    """A directory override as paths.py reads it: trailing separators stripped, absolute."""
    stripped = path.rstrip("/\\") or path[:1]
    return os.path.abspath(stripped)


def _key(path):
    return os.path.normcase(os.path.realpath(path))


def is_inside(path, root):
    """True when `path` is `root` or below it, both resolved through symlinks."""
    p, r = _key(path), _key(root)
    if p == r:
        return True
    return p.startswith(r.rstrip(os.sep) + os.sep)


def override_dirs(root, environ=None):
    """$ODOO_AI_PROJECT_DIR / $ODOO_AI_WORKTREE_DIR when set and outside the state root."""
    environ = os.environ if environ is None else environ
    out = []
    for var in ("ODOO_AI_PROJECT_DIR", "ODOO_AI_WORKTREE_DIR"):
        value = environ.get(var)
        if not value:
            continue
        d = _clean(value)
        if is_inside(d, root) or any(_key(d) == _key(o) for o in out):
            continue
        out.append(d)
    return out


def playwright_output_dir(root):
    return os.path.join(root, "projects")


def pagecast_output_dir(root):
    return os.path.join(root, "scratch", "pagecast")


def root_flags(server, root, overrides=()):
    b = backend(server)
    if b == "chrome-devtools":
        return ["--workspace=" + root] + ["--workspace=" + d for d in overrides]
    if b == "playwright":
        return ["--output-dir=" + playwright_output_dir(root),
                "--idle-timeout=" + str(PLAYWRIGHT_IDLE_TIMEOUT_MS)]
    return []


def server_env(server, root):
    if backend(server) == "pagecast":
        return {"RECORDING_OUTPUT_DIR": pagecast_output_dir(root)}
    return {}


def allowed_roots(server, root, environ=None):
    """The directories a family is launched to write under - what the capture gate allows."""
    b = backend(server)
    if b == "chrome-devtools":
        return [root] + override_dirs(root, environ)
    if b == "playwright":
        return [playwright_output_dir(root)]
    return [root]


def state_root():
    """The state root, from paths.py (the one resolver)."""
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    import paths  # noqa: E402  (sibling lib)
    return paths.state_root()


def desired_spec(server, root, environ=None):
    """The user-scope registration for a family: npx, the pinned package, base flags, resolved
    state-root flags, and its environment."""
    environ = os.environ if environ is None else environ
    overrides = override_dirs(root, environ) if backend(server) == "chrome-devtools" else []
    return {
        "command": "npx",
        "args": ["-y"] + npx_args(server, environ) + root_flags(server, root, overrides),
        "env": server_env(server, root),
    }


def _same_dir(a, b):
    return os.path.normcase(os.path.normpath(a)) == os.path.normcase(os.path.normpath(b))


def configured_with_root(server, entry, root):
    """True when a registered server entry ({"args": [...], "env": {...}}) already carries this
    family's state-root flag for `root` - i.e. an absolute capture under the root will succeed."""
    if not isinstance(entry, dict):
        return False
    args = [a for a in (entry.get("args") or []) if isinstance(a, str)]
    env = entry.get("env") or {}
    b = backend(server)
    if b == "chrome-devtools":
        flag, want = "--workspace", root
    elif b == "playwright":
        flag, want = "--output-dir", playwright_output_dir(root)
    else:
        value = env.get("RECORDING_OUTPUT_DIR") if isinstance(env, dict) else None
        return isinstance(value, str) and _same_dir(value, pagecast_output_dir(root))
    for i, a in enumerate(args):
        if a.startswith(flag + "=") and _same_dir(a[len(flag) + 1:], want):
            return True
        if a == flag and i + 1 < len(args) and _same_dir(args[i + 1], want):
            return True
    return False


def spec_matches(entry, desired):
    """True when a registered entry launches exactly the desired command, args and env."""
    if not isinstance(entry, dict):
        return False
    env = entry.get("env") or {}
    return (entry.get("command") == desired["command"]
            and list(entry.get("args") or []) == desired["args"]
            and dict(env) == desired["env"])


# --------------------------------------------------------------------------- #
# registrations in the user's own CLI configs
# --------------------------------------------------------------------------- #
def claude_config_path(environ=None):
    """The file Claude Code keeps user- and local-scope MCP servers in."""
    environ = os.environ if environ is None else environ
    base = environ.get("CLAUDE_CONFIG_DIR")
    if base:
        return os.path.join(base, ".claude.json")
    return os.path.join(os.path.expanduser("~"), ".claude.json")


def _load_json_file(path):
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _load_toml_file(path):
    try:
        import tomllib  # 3.11+; older interpreters cannot read Codex's config here
    except ImportError:
        return {}
    try:
        with open(path, "rb") as fh:
            return tomllib.load(fh)
    except (OSError, ValueError):
        return {}


def drifted_registrations(root, environ=None):
    """[(runtime, server)] for each browser family REGISTERED in the user's Claude (user scope),
    Codex or Gemini config with another command, args or env than the setup steps would write
    now. A family that is not registered at all is not drift."""
    environ = os.environ if environ is None else environ
    home = os.path.expanduser("~")
    sources = [
        ("claude", (_load_json_file(claude_config_path(environ)).get("mcpServers") or {}),
         OPTIN_SERVERS),
        ("codex", (_load_toml_file(environ.get("CODEX_CONFIG")
                                   or os.path.join(home, ".codex", "config.toml"))
                   .get("mcp_servers") or {}), ALL_SERVERS),
        ("gemini", (_load_json_file(environ.get("GEMINI_SETTINGS")
                                    or os.path.join(home, ".gemini", "settings.json"))
                    .get("mcpServers") or {}), ALL_SERVERS),
    ]
    out = []
    for runtime, servers, names in sources:
        if not isinstance(servers, dict):
            continue
        for name in names:
            entry = servers.get(name)
            if entry is not None and not spec_matches(entry, desired_spec(name, root, environ)):
                out.append((runtime, name))
    return out


# --------------------------------------------------------------------------- #
# byproduct pruning
# --------------------------------------------------------------------------- #
def _remove(path):
    """Unlink a file or a symlink (never its target); 1 when it went."""
    try:
        os.unlink(path)
        return 1
    except OSError:
        return 0


def _prune_tree(path, cutoff):
    """Delete what is older than `cutoff` in a byproduct tree, `path` itself included: files and
    symlinks (never followed), then each directory that was already old BEFORE the pass and is
    left empty. Ages are read first, since deleting a child refreshes its parent's mtime.
    Returns how many entries went."""
    if os.path.islink(path) or not os.path.isdir(path):
        return _remove(path) if _old(path, cutoff) else 0
    old_dirs = set()
    for dirpath, _dirnames, _filenames in os.walk(path):
        if _old(dirpath, cutoff):
            old_dirs.add(dirpath)
    removed = 0
    for dirpath, dirnames, filenames in os.walk(path, topdown=False):
        for name in filenames + [d for d in dirnames if os.path.islink(os.path.join(dirpath, d))]:
            full = os.path.join(dirpath, name)
            if _old(full, cutoff):
                try:
                    os.unlink(full)
                    removed += 1
                except OSError:
                    pass
        if dirpath in old_dirs:
            try:
                os.rmdir(dirpath)
                removed += 1
            except OSError:
                pass
    return removed


def _old(path, cutoff):
    try:
        return os.lstat(path).st_mtime < cutoff
    except OSError:
        return False


def _adhoc_dirs(root, environ):
    """Every <ISOLATE_DIR>/visual/adhoc under the state root (ISOLATE dirs are
    projects/<repo-key>/worktrees/<wt-key>), plus the $ODOO_AI_WORKTREE_DIR override's."""
    out = []
    projects = playwright_output_dir(root)
    try:
        repos = [r for r in os.listdir(projects) if _REPO_KEY.match(r)]
    except OSError:
        repos = []
    for repo in repos:
        trees = os.path.join(projects, repo, "worktrees")
        try:
            keys = [k for k in os.listdir(trees) if _REPO_KEY.match(k)]
        except OSError:
            keys = []
        out.extend(os.path.join(trees, k, "visual", "adhoc") for k in keys)
    override = environ.get("ODOO_AI_WORKTREE_DIR")
    if override:
        out.append(os.path.join(_clean(override), "visual", "adhoc"))
    return out


def _prune_children(directory, cutoff):
    try:
        names = os.listdir(directory)
    except OSError:
        return 0
    return sum(_prune_tree(os.path.join(directory, name), cutoff) for name in names)


def prune_browser_byproducts(root, now=None, max_age_s=BYPRODUCT_MAX_AGE_S,
                             adhoc_max_age_s=ADHOC_MAX_AGE_S, environ=None):
    """Delete stale files under the state root that no skill's own sweep owns:
      - playwright's auto-named files at the top level of <root>/projects and everything in
        <root>/scratch/pagecast, older than `max_age_s` (the servers write these on their own);
      - the children of every <ISOLATE_DIR>/visual/adhoc/ (captures made outside any skill),
        older than `adhoc_max_age_s`. No other visual/ sibling is touched.
    Per-repo state dirs (12-hex keys) are otherwise never touched. Best effort, never raises."""
    now = time.time() if now is None else now
    environ = os.environ if environ is None else environ
    cutoff = now - max_age_s
    removed = 0
    projects = playwright_output_dir(root)
    try:
        names = os.listdir(projects)
    except OSError:
        names = []
    for name in names:
        if _REPO_KEY.match(name) or not _PLAYWRIGHT_BYPRODUCT.match(name):
            continue
        removed += _prune_tree(os.path.join(projects, name), cutoff)
    removed += _prune_children(pagecast_output_dir(root), cutoff)
    for adhoc in _adhoc_dirs(root, environ):
        removed += _prune_children(adhoc, now - adhoc_max_age_s)
    return removed


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv):
    usage = ("Usage: browser_mcp_servers.py {servers all|optin|eager | npx-args <server> | "
             "pin <server> | playwright-core-version | spec <server> | claude-config | drift | "
             "prune}")
    if not argv:
        sys.stderr.write(usage + "\n")
        return 2
    cmd, rest = argv[0], argv[1:]
    try:
        if cmd == "servers" and len(rest) == 1 and rest[0] in ("all", "optin", "eager"):
            names = {"all": ALL_SERVERS, "optin": OPTIN_SERVERS, "eager": [EAGER_SERVER]}[rest[0]]
            sys.stdout.write("".join(n + "\n" for n in names))
            return 0
        if cmd == "npx-args" and len(rest) == 1:
            sys.stdout.write("".join(a + "\n" for a in npx_args(rest[0])))
            return 0
        if cmd == "pin" and len(rest) == 1:
            sys.stdout.write(pin(rest[0]) + "\n")
            return 0
        if cmd == "playwright-core-version" and not rest:
            sys.stdout.write(PLAYWRIGHT_CORE_VERSION + "\n")
            return 0
        if cmd == "spec" and len(rest) == 1:
            sys.stdout.write(json.dumps(desired_spec(rest[0], state_root()), sort_keys=True) + "\n")
            return 0
        if cmd == "claude-config" and not rest:
            sys.stdout.write(claude_config_path() + "\n")
            return 0
        if cmd == "drift" and not rest:
            for runtime, name in drifted_registrations(state_root()):
                sys.stdout.write("%s %s\n" % (runtime, name))
            return 0
        if cmd == "prune" and not rest:
            prune_browser_byproducts(state_root())
            return 0
    except ValueError as exc:
        sys.stderr.write("browser_mcp_servers.py: %s\n" % exc)
        return 2
    sys.stderr.write(usage + "\n")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
