#!/usr/bin/env python3
"""video_record.py - run the scene recorder (``scripts/recorder/record.mjs``) with the pinned library.

Subcommands (stdlib only; every result is KEY=VALUE on stdout)::

  record    --script SCENE.json [--out-dir DIR]   drive and record one scene
  prepare   --script SCENE.json [--out-dir DIR]   drive a scene without recording
  trial     --script SCENE.json [--out-dir DIR]   prepare, then ANSWER= and WAIT_S=
  self-test [--out-dir DIR]                       fake microphone and video recording work (the
                                                  probe's files: DIR, else under the state root,
                                                  removed afterwards)
  install-check                                   exit 0 when the recorder can run, else 1

The library lives under ``<state root>/recorder`` and must be the pinned version. Exit codes:
2 the recorder is not installed (``REMEDY=``), 3 a step found no target, 4 unusable script, 6 the
take showed a key; every other code is the recorder's own. No environment variable value is
ever printed.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import browser_mcp_servers  # noqa: E402
import paths  # noqa: E402

RECORDER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "recorder", "record.mjs")
REMEDY = "run /odoo-ai-agents:odoo-setup browser"
NODE_MIN_MAJOR = 20


def recorder_home():
    """:returns: the directory that holds the recorder's node_modules."""
    return os.path.join(paths.state_root(), "recorder")


def node_modules():
    """:returns: the node_modules the recorder resolves playwright from.

    ``ODOO_AI_RECORDER_NODE_PATH`` is a test-only override for a developer without the setup step.
    """
    return os.environ.get("ODOO_AI_RECORDER_NODE_PATH") or os.path.join(recorder_home(), "node_modules")


def installed_version():
    """:returns: the installed playwright version, or None when the library is absent."""
    try:
        with open(os.path.join(node_modules(), "playwright", "package.json"), encoding="utf-8") as fh:
            return json.load(fh).get("version")
    except (OSError, ValueError):
        return None


def node_ok():
    """:returns: the ``node`` path when it is on PATH and at least version 20, else None."""
    node = shutil.which("node")
    if not node:
        return None
    try:
        out = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.match(r"v(\d+)\.", out.strip())
    return node if match and int(match.group(1)) >= NODE_MIN_MAJOR else None


def problems():
    """:returns: a list of ``(key, text)`` for everything that stops the recorder from running."""
    found = []
    if not node_ok():
        found.append(("NODE", "node >= %d is not on PATH" % NODE_MIN_MAJOR))
    pin = browser_mcp_servers.browser_playwright_version()
    have = installed_version()
    if have != pin:
        found.append(("LIBRARY", "the recorder library is %s, the pin is %s" % (have or "not installed", pin)))
    if not os.path.isfile(RECORDER):
        found.append(("RECORDER", "the recorder script is missing"))
    return found


def run(mode, rest):
    """Runs the recorder for `mode`, streaming its stdout.

    :param str mode: record, prepare, trial or self-test
    :param list rest: the remaining recorder arguments
    :returns: the exit code
    """
    found = problems()
    if found:
        for key, text in found:
            print("ERROR=%s: %s" % (key, text))
        print("REMEDY=" + REMEDY)
        return 2
    env = dict(os.environ)
    env["NODE_PATH"] = node_modules()
    proc = subprocess.Popen([node_ok(), RECORDER, mode, *rest], env=env, stdout=subprocess.PIPE, text=True)
    for line in proc.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()
    return proc.wait()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("record", "prepare", "trial"):
        p = sub.add_parser(name)
        p.add_argument("--script", required=True)
        p.add_argument("--out-dir")
    p = sub.add_parser("self-test")
    p.add_argument("--out-dir")
    sub.add_parser("install-check")
    args = parser.parse_args(argv)

    if args.cmd == "install-check":
        found = problems()
        for key, text in found:
            print("%s=missing" % key)
        print("OK=%d" % (0 if found else 1))
        if found:
            print("REMEDY=" + REMEDY)
        return 1 if found else 0
    rest = []
    if getattr(args, "script", None):
        rest += ["--script", args.script]
    if args.out_dir:
        rest += ["--out-dir", args.out_dir]
    if args.cmd == "self-test" and not args.out_dir:
        # The probe's files live under the state root, never in an ambient temp dir.
        scratch = os.path.join(recorder_home(), "self-test")
        os.makedirs(scratch, exist_ok=True)
        try:
            return run(args.cmd, rest + ["--out-dir", scratch])
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
    return run(args.cmd, rest)


if __name__ == "__main__":
    sys.exit(main())
