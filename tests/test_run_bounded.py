"""scripts/lib/run_bounded.sh: a wall-clock bound that works on every host.

`timeout` is GNU coreutils, not POSIX: stock macOS has none (Homebrew names it `gtimeout`). A bare
`timeout 5 cmd` there fails before cmd runs, and behind `|| true` the call silently became a
no-op: the teardown gate never asked the allocator (so it never blocked a leaked lease) and the
SessionEnd reclaim never ran. Every test here runs with a PATH that holds the host's tools EXCEPT
`timeout` and `gtimeout` - the stock-macOS shape - unless it says otherwise.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest
from conftest import farm_path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
LIB = PLUGIN / "scripts" / "lib"
HELPER = LIB / "run_bounded.sh"
HOOKS = PLUGIN / "hooks"

posix_only = pytest.mark.skipif(os.name == "nt", reason="POSIX process groups and shell stubs")


def _bash(snippet, path, *args, timeout=60):
    env = dict(os.environ, PATH=path)
    return subprocess.run(["bash", "-c", f'. "{HELPER}"\n{snippet}', "bash", *args], env=env,
                          capture_output=True, text=True, timeout=timeout)


@pytest.fixture
def no_timeout(path_farm):
    path = farm_path(path_farm(drop=("timeout", "gtimeout")))
    probe = subprocess.run(["bash", "-c", "command -v timeout || command -v gtimeout"],
                           env=dict(os.environ, PATH=path), capture_output=True, text=True)
    assert probe.returncode != 0, "premise: neither timeout nor gtimeout is reachable"
    assert shutil.which("python3", path=path), "premise: python3 stays reachable"
    return path


# --------------------------------------------------------------------------- #
# the helper itself, on a host without timeout / gtimeout
# --------------------------------------------------------------------------- #
@posix_only
def test_the_command_runs_and_its_status_and_output_pass_through(no_timeout):
    p = _bash('run_bounded 5 sh -c "echo out; echo err >&2; exit 3"', no_timeout)
    assert p.returncode == 3 and p.stdout == "out\n" and p.stderr == "err\n", p


@posix_only
def test_stdin_reaches_the_command(no_timeout):
    env = dict(os.environ, PATH=no_timeout)
    p = subprocess.run(["bash", "-c", f'. "{HELPER}"; run_bounded 5 cat'], input="piped\n",
                       env=env, capture_output=True, text=True, timeout=30)
    assert p.stdout == "piped\n"


@posix_only
def test_the_bound_elapses_with_124_and_kills_the_whole_group(no_timeout, tmp_path):
    """A command that would outlive the bound is stopped at it - grandchildren included - and the
    status is timeout's own 124, which callers already read as 'no answer'."""
    marker = tmp_path / "grandchild-survived"
    started = time.monotonic()
    p = _bash(f'run_bounded 1 sh -c "(sleep 3; touch {marker}) & sleep 30"', no_timeout)
    elapsed = time.monotonic() - started
    assert p.returncode == 124, p
    assert elapsed < 10, elapsed
    time.sleep(3.5)
    assert not marker.exists(), "a grandchild outlived the bound"


@posix_only
def test_a_command_that_cannot_start_reports_127(no_timeout):
    assert _bash("run_bounded 5 no-such-command-here", no_timeout).returncode == 127


@posix_only
def test_gtimeout_is_used_when_timeout_is_missing(tmp_path, path_farm):
    log = tmp_path / "gtimeout.log"
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    (stubs / "gtimeout").write_text(f'#!/bin/sh\necho "$@" >> "{log}"\nshift\nexec "$@"\n',
                                    encoding="utf-8")
    (stubs / "gtimeout").chmod(0o755)
    path = farm_path(path_farm(drop=("timeout", "gtimeout")), stubs)
    p = _bash("run_bounded 7 sh -c 'exit 4'", path)
    assert p.returncode == 4
    assert log.read_text().split()[0] == "7", "gtimeout must receive the bound"


# --------------------------------------------------------------------------- #
# the callers: no bare `timeout` anywhere, and they still work without one
# --------------------------------------------------------------------------- #
# `timeout` in command position, followed by its bound (a number or a $VAR, after any options)
# and then the command it bounds.
_BARE = re.compile(r"(?:^|[;&|(`]|\$\(|\bthen\b|\bdo\b|\belse\b)\s*g?timeout\s+"
                   r"(?:-\w+\s+\S+\s+)*(?:\"?\$\{?\w+\}?\"?|\d+(?:\.\d+)?)\s+\S")


def test_no_shell_file_calls_a_bare_timeout():
    """Every bounded call goes through run_bounded (the one place that knows the ladder).
    pg_mode.sh keeps its own guarded ladder (group-kill + function re-entry) and calls
    `timeout` only behind `_pg_mode_have timeout`."""
    offenders = []
    for path in sorted(PLUGIN.rglob("*.sh")):
        if path == HELPER:
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            if _BARE.search(line):
                offenders.append(f"{path.relative_to(ROOT)}:{n}: {line.strip()}")
    assert not offenders, "bare `timeout` (absent on stock macOS):\n" + "\n".join(offenders)


@posix_only
@pytest.mark.skipif(shutil.which("jq") is None, reason="enforce-teardown.sh needs jq")
def test_the_teardown_gate_still_blocks_a_live_lease_without_timeout(no_timeout, tmp_path):
    """Without `timeout` the allocator was never asked, so the gate failed open on every lease:
    a leaked instance passed the one hard block meant to catch it."""
    token = "ab" * 16
    home = tmp_path / "home"
    (home / "runtime").mkdir(parents=True)
    now = int(time.time())
    (home / "runtime" / "leases.json").write_text(json.dumps({"schema_version": 2, "leases": [{
        "token": token, "mode": "exclusive", "series": "17.0", "db_name": "odoo_17_0",
        "drop_on_release": True, "ports": [8170],
        "owner": {"host": os.uname().nodename, "pid": None, "run_id": "run-abc",
                  "started_at": now},
        "ttl_s": 7200, "heartbeat_at": now, "_pg": {"host": "localhost", "user": "odoo"}}]}))
    acquire = {"type": "assistant", "message": {"role": "assistant", "content": [{
        "type": "tool_use", "id": "toolu_1", "name": "Bash", "input": {"command": (
            "python3 ${CLAUDE_PLUGIN_ROOT}/scripts/lib/allocator.py acquire --series 17.0 "
            "--mode ephemeral --ports 1 --run-id run-abc")}}]}}
    result = {"type": "user", "message": {"role": "user", "content": [{
        "type": "tool_result", "tool_use_id": "toolu_1",
        "content": f"ALLOC_TOKEN={token}\nALLOC_DB=odoo_17_0\n"}]}}
    done = {"role": "assistant", "content": [{"type": "text", "text": (
        "```continuation\nstatus: DONE\nproduced: []\nnext: []\n```")}]}
    transcript = tmp_path / "agent.jsonl"
    transcript.write_text("\n".join(json.dumps(r) for r in (acquire, result, done)) + "\n")
    session = tmp_path / "session.jsonl"
    session.write_text("\n")
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_PID", "CLAUDE_CODE_SESSION_ID")}
    env.update(PATH=no_timeout, CLAUDE_PLUGIN_ROOT=str(PLUGIN), ODOO_AI_HOME=str(home),
               HOME=str(home), ODOO_AI_SESSION_ANCHOR="none")
    payload = {"hook_event_name": "SubagentStop", "stop_hook_active": False,
               "transcript_path": str(session), "agent_transcript_path": str(transcript)}
    p = subprocess.run(["bash", str(HOOKS / "enforce-teardown.sh")], input=json.dumps(payload),
                       env=env, capture_output=True, text=True, timeout=60)
    out = json.loads(p.stdout) if p.stdout.strip() else None
    assert out is not None and out.get("decision") == "block", (p.stdout, p.stderr)
    assert token in out["reason"]


@posix_only
def test_the_session_end_reclaim_runs_without_timeout(no_timeout, tmp_path):
    """The SessionEnd worker's gc and reap calls ran behind a bare `timeout ... || true`: on
    stock macOS not one of them ever ran."""
    root = tmp_path / "plugin"
    lib = root / "scripts" / "lib"
    lib.mkdir(parents=True)
    shutil.copy2(HELPER, lib / "run_bounded.sh")
    calls = tmp_path / "allocator-calls.log"
    (lib / "allocator.py").write_text(
        f"import sys\nopen({str(calls)!r}, 'a').write(' '.join(sys.argv[1:]) + '\\n')\n")
    env = dict(os.environ, PATH=no_timeout, CLAUDE_PLUGIN_ROOT=str(root),
               ODOO_AI_HOME=str(tmp_path / "state"), HOME=str(tmp_path / "home"))
    p = subprocess.run(["bash", str(HOOKS / "session-end-gc.sh"), "--detached-worker", "", ""],
                       env=env, capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    assert calls.exists() and "gc --scope dead-sessions" in calls.read_text(), (
        "the dead-session reclaim never ran", p.stderr)


@posix_only
def test_the_session_end_browser_prune_is_bounded_too(tmp_path, path_farm):
    """Every python call of the SessionEnd worker runs under a bound, the browser prune included:
    a hung filesystem must not hold the detached worker forever."""
    root = tmp_path / "plugin"
    lib = root / "scripts" / "lib"
    lib.mkdir(parents=True)
    shutil.copy2(HELPER, lib / "run_bounded.sh")
    (lib / "allocator.py").write_text("import sys\n")
    (lib / "browser_mcp_servers.py").write_text("import sys\n")
    log = tmp_path / "timeout.log"
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    (stubs / "timeout").write_text(f'#!/bin/sh\necho "$@" >> "{log}"\nshift\nexec "$@"\n',
                                   encoding="utf-8")
    (stubs / "timeout").chmod(0o755)
    env = dict(os.environ, PATH=farm_path(path_farm(drop=("timeout", "gtimeout")), stubs),
               CLAUDE_PLUGIN_ROOT=str(root), ODOO_AI_HOME=str(tmp_path / "state"),
               HOME=str(tmp_path / "home"))
    p = subprocess.run(["bash", str(HOOKS / "session-end-gc.sh"), "--detached-worker", "", ""],
                       env=env, capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    bounded = log.read_text(encoding="utf-8").splitlines()
    assert any(line.endswith("browser_mcp_servers.py prune") for line in bounded), bounded
