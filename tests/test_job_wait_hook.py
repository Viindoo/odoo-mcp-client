"""Behavioral guard for hooks/enforce-job-wait.sh (Stop and SubagentStop).

`instance_build` / `instance_i18n_export` start an odoo-local job and return its job_id; `job_wait`
collects it. A job that finishes notifies nobody, so a turn that ends with a job THIS agent started
still running leaves the session idle until a human asks. The gate stops such a turn once.

What counts (tests/test_job_wait_hook.py protects exactly this):
  - the agent's OWN transcript nominates a job: a starter call whose successful result carries a
    job_id, with no `job_wait` result for it in a terminal state;
  - the job store has the last word: only a job that is still the running process is stopped for;
  - never a false stop: a finished job, a job another agent started, a job whose terminal result
    was already read, a record whose process is gone or was recycled, a refused start;
  - bounded: a stop a hook already continued passes.

Assertions are on decisions and structured facts, never the wording of the reason.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

import odoo_local_mcp_harness as harness
from conftest import brief_record

ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = ROOT / "plugins" / "odoo-ai-agents"
HOOK = PLUGIN_ROOT / "hooks" / "enforce-job-wait.sh"
HOOKS_JSON = PLUGIN_ROOT / "hooks" / "hooks.json"
MCP_DIR = PLUGIN_ROOT / "scripts" / "mcp"
PREFIX = "mcp__plugin_odoo-ai-agents_odoo-local__"

pytestmark = pytest.mark.skipif(
    shutil.which("jq") is None or shutil.which("bash") is None or shutil.which("python3") is None,
    reason="the hook needs jq + bash + python3; absent here it degrades to pass",
)


# --------------------------------------------------------------------------- #
# Real job records, in a hermetic ODOO_AI_HOME
# --------------------------------------------------------------------------- #
_PY = (
    "import json, sys\n"
    f"sys.path.insert(0, {str(MCP_DIR)!r})\n"
    "from odoo_local import jobs\n"
    "rec = jobs.start(sys.argv[2:], sys.argv[1], meta={'op': 'init', 'kind': 'build'})\n"
    "print(json.dumps(rec))\n"
)


def _env(home: Path) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith("ODOO_AI_")}
    env.update({"ODOO_AI_HOME": str(home), "ODOO_AI_SESSION_ANCHOR": "none", "HOME": str(home),
                "CLAUDE_PLUGIN_ROOT": str(PLUGIN_ROOT)})
    return env


_STARTED: list[int] = []  # process groups of the jobs a test started, killed when it ends


@pytest.fixture
def home(tmp_path):
    h = tmp_path / "home"
    h.mkdir()
    yield h
    while _STARTED:
        try:
            os.killpg(_STARTED.pop(), signal.SIGKILL)
        except OSError:
            pass


def _start_job(home: Path, *cmd: str, cwd: Path | None = None) -> dict:
    out = subprocess.run([sys.executable, "-c", _PY, str(cwd or home), *cmd], env=_env(home),
                         capture_output=True, text=True, timeout=30, check=True).stdout
    rec = json.loads(out)
    _STARTED.append(rec["pid"])
    return rec


def _running_job(home: Path) -> str:
    return _start_job(home, "sleep", "300")["job_id"]


def _finished_job(home: Path) -> str:
    rec = _start_job(home, "true")
    rc = home / "runtime" / "jobs" / (rec["job_id"] + ".rc")
    deadline = time.time() + 15
    while not rc.exists() and time.time() < deadline:
        time.sleep(0.1)
    assert rc.exists(), "the job wrapper never published its exit code"
    return rec["job_id"]


def _lost_job(home: Path) -> str:
    """A record whose process is gone and left no exit file: what a dead server's job looks like."""
    rec = _start_job(home, "sleep", "300")
    os.killpg(rec["pid"], signal.SIGKILL)
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            os.kill(rec["pid"], 0)
        except OSError:
            break
        time.sleep(0.1)
    return rec["job_id"]


def _recycled_job(home: Path) -> str:
    """A record whose pid is alive but belongs to another process: its start fingerprint differs."""
    rec = _start_job(home, "sleep", "300")
    path = home / "runtime" / "jobs" / (rec["job_id"] + ".json")
    data = json.loads(path.read_text(encoding="utf-8"))
    fp = data["pid_started"]
    assert fp, "no start fingerprint available on this host"
    data["pid_started"] = fp[:-1] + ("1" if not fp.endswith("1") else "2")
    path.write_text(json.dumps(data), encoding="utf-8")
    return rec["job_id"]


# --------------------------------------------------------------------------- #
# Transcript builders
# --------------------------------------------------------------------------- #
def _assistant(*blocks) -> str:
    return json.dumps({"type": "assistant", "message": {"role": "assistant", "content": list(blocks)}})


def _text(s: str) -> str:
    return _assistant({"type": "text", "text": s})


def _result(tid: str, payload: dict, *, error: bool = False) -> str:
    block = {"type": "tool_result", "tool_use_id": tid, "content": json.dumps(payload)}
    if error:
        block["is_error"] = True
    return json.dumps({"type": "user", "message": {"role": "user", "content": [block]},
                       "toolUseResult": json.dumps(payload)})


def _start(job_id: str, tool: str = "instance_build", tid: str | None = None,
           prefix: str = PREFIX) -> list[str]:
    tid = tid or f"toolu_start_{job_id[-8:]}"
    call = _assistant({"type": "tool_use", "id": tid, "name": prefix + tool, "input": {"op": "init"}})
    return [call, _result(tid, {"job_id": job_id, "pid": 1, "op": "init"})]


def _wait(job_id: str, state: str = "running", tid: str | None = None) -> list[str]:
    tid = tid or f"toolu_wait_{job_id[-8:]}_{state}"
    call = _assistant({"type": "tool_use", "id": tid, "name": PREFIX + "job_wait",
                       "input": {"job_id": job_id, "timeout_s": 540}})
    result = "timeout" if state == "running" else "success"
    return [call, _result(tid, {"job_id": job_id, "state": state, "result": result})]


def _refused_start(other_job: str) -> list[str]:
    tid = "toolu_busy"
    call = _assistant({"type": "tool_use", "id": tid, "name": PREFIX + "instance_build", "input": {}})
    err = {"error": {"code": "DATABASE_BUSY", "message": "busy", "details": {"job_id": other_job}}}
    return [call, _result(tid, err, error=True)]


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
def _run(tmp_path: Path, home: Path, lines: list[str], *, event: str = "SubagentStop",
         active: bool = False, extra: dict | None = None) -> dict | None:
    tpath = tmp_path / "agent.jsonl"
    tpath.write_text("\n".join(lines) + "\n", encoding="utf-8")
    session = tmp_path / "session.jsonl"
    payload = {"hook_event_name": event, "stop_hook_active": active}
    if event == "SubagentStop":
        session.write_text("", encoding="utf-8")
        payload.update({"transcript_path": str(session), "agent_transcript_path": str(tpath)})
    else:
        payload["transcript_path"] = str(tpath)
    payload.update(extra or {})
    proc = subprocess.run(["bash", str(HOOK)], input=json.dumps(payload), capture_output=True,
                          text=True, timeout=30, env=_env(home))
    assert proc.returncode == 0
    out = proc.stdout.strip()
    return json.loads(out) if out else None


def _blocks(out: dict | None) -> bool:
    return bool(out) and out.get("decision") == "block"


EVENTS = pytest.mark.parametrize("event", ["Stop", "SubagentStop"])


# =========================================================================== #
# The refusal
# =========================================================================== #
@EVENTS
def test_a_turn_ending_with_its_own_running_job_is_stopped(tmp_path, home, event):
    """The main conversation (Stop) and a dispatched agent (SubagentStop) alike."""
    job = _running_job(home)
    out = _run(tmp_path, home, [brief_record(), *_start(job)], event=event)
    assert _blocks(out) and job in out["reason"], out


@EVENTS
def test_a_job_whose_last_wait_timed_out_is_still_running(tmp_path, home, event):
    job = _running_job(home)
    out = _run(tmp_path, home, [brief_record(), *_start(job), *_wait(job, "running")], event=event)
    assert _blocks(out) and job in out["reason"], out


def test_a_translation_export_job_counts_too(tmp_path, home):
    job = _running_job(home)
    out = _run(tmp_path, home, [brief_record(), *_start(job, "instance_i18n_export")])
    assert _blocks(out), out


def test_only_the_running_jobs_are_named(tmp_path, home):
    running, finished = _running_job(home), _finished_job(home)
    out = _run(tmp_path, home, [brief_record(), *_start(finished), *_start(running)])
    assert _blocks(out) and running in out["reason"] and finished not in out["reason"], out


def test_the_reason_lists_a_bounded_number_of_jobs(tmp_path, home):
    """The harness cuts a hook output over 10,000 characters: at most five jobs are named."""
    jobs = [_running_job(home) for _ in range(8)]
    lines = [brief_record()]
    for j in jobs:
        lines += _start(j)
    out = _run(tmp_path, home, lines)
    assert _blocks(out) and len(out["reason"]) < 8000
    assert sum(1 for j in jobs if j in out["reason"]) == 5


# =========================================================================== #
# Never a false stop
# =========================================================================== #
@EVENTS
def test_a_job_that_finished_is_never_stopped_for(tmp_path, home, event):
    job = _finished_job(home)
    assert not _blocks(_run(tmp_path, home, [brief_record(), *_start(job)], event=event))


def test_a_job_whose_terminal_result_was_read_is_never_nominated(tmp_path, home):
    """The agent read the job to a terminal state; the transcript alone settles it (the store
    here still holds a running process, which only the transcript rule keeps from being asked)."""
    job = _running_job(home)
    lines = [brief_record(), *_start(job), *_wait(job, "running"), *_wait(job, "exited")]
    assert not _blocks(_run(tmp_path, home, lines))


def test_a_job_another_agent_started_is_never_stopped_for(tmp_path, home):
    """The store holds a running job, but this transcript never started it: it only waits on it."""
    job = _running_job(home)
    assert not _blocks(_run(tmp_path, home, [brief_record(), *_wait(job, "running")]))
    assert not _blocks(_run(tmp_path, home, [brief_record(), _text("nothing started here")]))


def test_a_busy_refusal_naming_another_job_is_not_a_start(tmp_path, home):
    other = _running_job(home)
    assert not _blocks(_run(tmp_path, home, [brief_record(), *_refused_start(other)]))


def test_a_tool_of_another_server_with_the_same_name_is_not_a_start(tmp_path, home):
    """The transcript does hold a genuine odoo-local job (collected), so it is parsed; a tool of
    another server that happens to share the name nominates nothing."""
    mine, theirs = _finished_job(home), _running_job(home)
    lines = [brief_record(), *_start(mine), *_wait(mine, "exited"),
             *_start(theirs, prefix="mcp__some-other-server__")]
    assert not _blocks(_run(tmp_path, home, lines))


def test_a_record_whose_process_is_gone_is_not_a_running_job(tmp_path, home):
    job = _lost_job(home)
    assert not _blocks(_run(tmp_path, home, [brief_record(), *_start(job)]))


def test_a_recycled_pid_is_not_a_running_job(tmp_path, home):
    job = _recycled_job(home)
    assert not _blocks(_run(tmp_path, home, [brief_record(), *_start(job)]))


def test_a_job_the_store_does_not_know_passes(tmp_path, home):
    assert not _blocks(_run(tmp_path, home, [brief_record(), *_start("job-20990101000000-deadbeef")]))


def test_a_stop_a_hook_already_continued_passes(tmp_path, home):
    job = _running_job(home)
    lines = [brief_record(), *_start(job)]
    assert _blocks(_run(tmp_path, home, lines))
    assert not _blocks(_run(tmp_path, home, lines, active=True))


def test_an_unreadable_transcript_passes(tmp_path, home):
    assert _run(tmp_path, home, ["not json", "{also not"]) is None
    assert _run(tmp_path, home, [], extra={"agent_transcript_path": str(tmp_path / "nope")}) is None


def test_a_subagent_stop_without_its_own_transcript_passes(tmp_path, home):
    """The session transcript is never read in place of the agent's own."""
    job = _running_job(home)
    session = tmp_path / "session-only.jsonl"
    session.write_text("\n".join([brief_record(), *_start(job)]) + "\n", encoding="utf-8")
    payload = {"hook_event_name": "SubagentStop", "stop_hook_active": False,
               "transcript_path": str(session)}
    proc = subprocess.run(["bash", str(HOOK)], input=json.dumps(payload), capture_output=True,
                          text=True, timeout=30, env=_env(home))
    assert proc.returncode == 0 and proc.stdout.strip() == ""


# =========================================================================== #
# Registration, the starter set, cost
# =========================================================================== #
def test_the_gate_is_registered_under_stop_and_subagent_stop():
    reg = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))["hooks"]
    cmds = {ev: [h["command"] for g in groups for h in g.get("hooks", [])] for ev, groups in reg.items()}
    assert any(HOOK.name in c for c in cmds["Stop"])
    assert any(HOOK.name in c for c in cmds["SubagentStop"])
    assert not any(HOOK.name in c for ev, cs in cmds.items()
                   if ev not in ("Stop", "SubagentStop") for c in cs)


def test_the_starter_set_is_the_servers_job_starting_tools(tmp_path):
    """The hook names the odoo-local tools that start a job; the server's own tool list is the
    SSOT: every tool with a job_id in its result other than job_wait must be one of them."""
    script = HOOK.read_text(encoding="utf-8")
    declared = set(re.search(r"^JOB_STARTERS='([^']+)'", script, re.M).group(1).split("|"))
    collector = re.search(r"^JOB_COLLECTOR='([^']+)'", script, re.M).group(1)
    home = tmp_path / "h"
    home.mkdir()
    client = harness.McpClient(harness.hermetic_env(home), home)
    try:
        client.initialize()
        tools = client.request("tools/list", {})["result"]["tools"]
    finally:
        client.close()

    def has_job_id(schema) -> bool:
        if isinstance(schema, dict):
            if "job_id" in (schema.get("properties") or {}):
                return True
            return any(has_job_id(v) for v in schema.values())
        if isinstance(schema, list):
            return any(has_job_id(v) for v in schema)
        return False

    emitting = {t["name"] for t in tools if has_job_id(t.get("outputSchema"))}
    assert collector in emitting
    assert emitting - {collector} == declared


def test_a_long_transcript_that_holds_a_collected_job_is_cleared_well_inside_the_timeout(tmp_path, home):
    """The gate's worst no-stop path: the transcript names a starter, so it is parsed, and is
    thousands of calls long. A gate the harness cancels for running too long decides nothing."""
    job = _running_job(home)
    filler = []
    for i in range(6000):
        tid = f"toolu_f{i:06d}"
        filler.append(_assistant({"type": "tool_use", "id": tid, "name": "Bash",
                                  "input": {"command": f"echo {i}"}}))
        filler.append(json.dumps({"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": tid, "content": f"step {i} " + "x" * 6000}]}}))
    lines = [brief_record(), *_start(job), *_wait(job, "exited"), *filler]
    reg = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))["hooks"]
    budget = next(float(h["timeout"]) for g in reg["SubagentStop"] for h in g["hooks"]
                  if h["command"].endswith('/hooks/enforce-job-wait.sh"'))
    t0 = time.monotonic()
    out = _run(tmp_path, home, lines)
    elapsed = time.monotonic() - t0
    assert not _blocks(out)
    assert elapsed < budget / 4, (
        f"the job-wait gate took {elapsed:.1f}s on a long dispatch; hooks.json gives it {budget:.0f}s")
