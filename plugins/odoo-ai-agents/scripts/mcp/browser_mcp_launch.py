#!/usr/bin/env python3
"""browser_mcp_launch.py - start one browser MCP family with its state-root flags.

Launch: python3 <plugin>/scripts/mcp/browser_mcp_launch.py <family>   (e.g. chrome-devtools)

A static MCP manifest cannot spell a state root that defaults to ~/.odoo-ai unless
$ODOO_AI_HOME is set, so this launcher resolves it (scripts/lib/paths.py), creates the
directories the server writes into, prunes stale byproducts, and replaces itself with
`npx -y <pin> <flags> <state-root flags>` (scripts/lib/browser_mcp_servers.py is the SSOT).

stdout is the MCP channel: nothing here ever writes to it. Only a state root that cannot be
computed (or a Python older than the SSOT's LAUNCH_MIN_PYTHON) starts the server with the pinned
package and its base flags alone, the reason on stderr. Creating a directory or pruning can fail
(another launch racing this one, a read-only subtree) without costing the flags: the capture gate
treats the bundled server as flagged, so dropping them would refuse every capture of the session.
Syntax stays parseable by very old Python 3 (no f-strings, no annotations): this file runs before
any version check.
"""

import os
import shutil
import subprocess
import sys

_PLAYWRIGHT_MAX_SIZE_ENV = "PLAYWRIGHT_MCP_OUTPUT_MAX_SIZE"

_HERE = os.path.dirname(os.path.abspath(__file__))
_LIB = os.path.join(os.path.dirname(_HERE), "lib")


def _warn(msg):
    sys.stderr.write("browser_mcp_launch: %s\n" % msg)
    sys.stderr.flush()


def _ssot():
    if _LIB not in sys.path:
        sys.path.insert(0, _LIB)
    import browser_mcp_servers
    return browser_mcp_servers


def _prepare(ssot, root, overrides):
    """Create the directories the server writes into (chrome-devtools silently drops a
    --workspace that does not exist) and prune stale byproducts. Each step is best effort on its
    own: a failure here never costs the state-root flags."""
    for d in [ssot.capture_area(root), ssot.pagecast_output_dir(root)] + list(overrides):
        try:
            os.makedirs(d, exist_ok=True)
        except Exception as exc:
            _warn("cannot create %s (%s)" % (d, exc))
    try:
        ssot.prune_browser_byproducts(root)
    except Exception:
        pass


def plan_launch(server, version_info):
    """Return (argv, env, reason) for this process's environment. argv starts with "npx";
    reason is None when the state-root flags were applied, else the one-line cause of starting
    with the base flags only (no computable state root, or a Python below the floor)."""
    ssot = _ssot()
    environ = os.environ
    args = ["npx", "-y"] + ssot.npx_args(server, environ)
    env = dict(environ)
    # The eviction this enables deletes recursively under the output dir, which is the state
    # root's projects tree here.
    env.pop(_PLAYWRIGHT_MAX_SIZE_ENV, None)
    floor = ssot.LAUNCH_MIN_PYTHON
    if tuple(version_info[:2]) < floor:
        return args, env, ("python3 is %d.%d, the state-root flags need %d.%d or newer"
                           % (version_info[0], version_info[1], floor[0], floor[1]))
    try:
        root = ssot.state_root()
        overrides = ssot.override_dirs(root, environ)
        flags = ssot.root_flags(server, root, overrides)
        server_env = ssot.server_env(server, root)
    except Exception as exc:
        return args, env, "%s: %s" % (type(exc).__name__, exc)
    _prepare(ssot, root, overrides)
    env.update(server_env)
    return args + flags, env, None


def _exec(argv, env):
    if os.name == "nt":
        # A replaced process on Windows ends the parent the client is waiting on, so the server
        # runs as a child with inherited stdio and its exit code is passed through.
        npx = shutil.which("npx") or "npx"
        sys.exit(subprocess.call([npx] + argv[1:], env=env))
    os.execvpe(argv[0], argv, env)


def main(argv):
    if len(argv) != 1:
        _warn("usage: browser_mcp_launch.py <family>")
        return 2
    server = argv[0]
    try:
        ssot = _ssot()
    except Exception as exc:
        _warn("cannot load scripts/lib/browser_mcp_servers.py (%s); reinstall the plugin" % exc)
        return 1
    if server not in ssot.ALL_SERVERS:
        _warn("unknown browser MCP family %r (one of: %s)" % (server, ", ".join(ssot.ALL_SERVERS)))
        return 2
    argv_out, env, reason = plan_launch(server, sys.version_info)
    if reason:
        _warn("starting %s without state-root flags - captures outside the OS temp dir and the "
              "session roots will be refused (%s)" % (server, reason))
    try:
        _exec(argv_out, env)
    except OSError as exc:
        _warn("cannot run npx (%s); install Node.js 20+ so npx is on PATH" % exc)
        return 127
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
