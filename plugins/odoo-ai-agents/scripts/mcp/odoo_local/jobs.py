"""jobs.py - background jobs that outlive the tool call AND the server process.

A job is a command started detached (its own session / process group) under a tiny wrapper that
records the command's exit code next to the job record when it finishes. The record lives at
$ODOO_AI_HOME/runtime/jobs/<job_id>.json, so status() answers the same question after the MCP server
restarts: it re-reads the record, then either reads the exit file or proves the process is still
the SAME one (pid + start fingerprint), never a recycled pid.

$ODOO_AI_HOME is resolved by scripts/lib/paths.py `_home()` - the Python member of the documented
home-resolution parity family (allocator.py `_home()` mirrors it; a test asserts they agree), so
the jobs dir always sits under the same runtime/ root as the allocator's lease registry.

States:
  running - the process is alive and is the one recorded (or its fingerprint cannot be read and
            the pid is alive - reported with fingerprint_verified=false).
  exited  - the command finished; exit_code is its return code (negative = killed by that signal).
  lost    - the process is gone without an exit record (the wrapper itself was killed), or the pid
            now belongs to a different process.

Retention: finished records (exited / lost) are pruned by `prune_finished()` - opportunistically at
server start and on every job start - on the SAME bound the build-log sweeper uses, read from its
single declaration in scripts/lib/state_reclaim.sh (`RETENTION_CONST`), never restated here. A
running job is never pruned, and an unreadable bound prunes nothing.

Odoo log-marker parsing is NOT here: a caller that needs a build verdict reads log_path with the
existing `55-instance-ops.sh wait-log` logic.
"""

import datetime
import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid

from . import cli

JOB_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

# The retention bound's ONE declaration (the build-log sweeper's lib) and the name it is declared
# under. Read, never copied: a second constant here would drift on the first change.
RETENTION_SOURCE = cli.LIB_DIR / "state_reclaim.sh"
RETENTION_CONST = "_LOG_RETENTION_DAYS"
_RETENTION_RE = re.compile(r"^\s*" + re.escape(RETENTION_CONST) + r"=([0-9]+)\s*(?:#.*)?$", re.MULTILINE)
_DAY_S = 86400

# The wrapper: run the command, then atomically publish its exit code. Kept inline (argv of
# `python -c`) so a job never depends on this package being importable later.
_WRAPPER = (
    "import os, subprocess, sys\n"
    "rc_path = sys.argv[1]\n"
    "try:\n"
    "    rc = subprocess.call(sys.argv[2:])\n"
    "except OSError as exc:\n"
    "    sys.stderr.write('odoo-local job: cannot start %r: %s\\n' % (sys.argv[2:], exc))\n"
    "    rc = 127\n"
    "tmp = rc_path + '.tmp'\n"
    "with open(tmp, 'w') as fh:\n"
    "    fh.write(str(rc))\n"
    "os.replace(tmp, rc_path)\n"
    "sys.exit(rc if 0 <= rc < 256 else 128 + (-rc % 128))\n"
)

_children_lock = threading.Lock()
_children = {}  # job_id -> Popen, for jobs THIS process started (reaped here; else they zombie)


def jobs_dir():
    home = cli.load_lib("paths")._home()
    path = os.path.join(home, "runtime", "jobs")
    os.makedirs(path, exist_ok=True)
    return path


def _record_path(job_id):
    return os.path.join(jobs_dir(), job_id + ".json")


def _rc_path(job_id):
    return os.path.join(jobs_dir(), job_id + ".rc")


def _now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fingerprint(pid):
    mod = cli.try_load_lib("session_anchor")
    if mod is None or not hasattr(mod, "fingerprint"):
        return None
    try:
        return mod.fingerprint(pid) or None
    except Exception:
        return None


def _fp_verdict(expected, pid):
    """session_anchor.fp_verdict ("match" | "mismatch" | "unknown"); "unknown" when absent."""
    mod = cli.try_load_lib("session_anchor")
    if not expected or mod is None or not hasattr(mod, "fp_verdict"):
        return "unknown"
    try:
        return mod.fp_verdict(expected, pid)
    except Exception:
        return "unknown"


def _pid_alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _write_json_atomic(path, obj):
    tmp = "%s.%d.tmp" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)


def start(cmd, cwd, env=None, log_path_hint=None, meta=None):
    """Start `cmd` (argv list) detached in `cwd`; stdout+stderr append to the log. Returns the record.

    `env` is EXTRA variables layered over the anchor environment (cli.child_env), never a
    replacement for it. `log_path_hint` is used as the log path when given (parent dirs created);
    otherwise the log sits beside the record as <job_id>.log. `meta` (a JSON-able dict) is stored
    verbatim in the record, so a later process - a restarted server - knows what the job was."""
    if not isinstance(cmd, (list, tuple)) or not cmd:
        raise ValueError("cmd must be a non-empty argv list")
    if not cwd or not os.path.isdir(str(cwd)):
        raise NotADirectoryError("cwd is not a directory: %r" % (cwd,))
    prune_finished()  # opportunistic, best-effort: a job start is when the store grows
    job_id = "job-%s-%s" % (time.strftime("%Y%m%d%H%M%S", time.gmtime()), uuid.uuid4().hex[:8])
    log_path = os.path.abspath(log_path_hint) if log_path_hint else os.path.join(jobs_dir(), job_id + ".log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    argv = [str(a) for a in cmd]
    with open(log_path, "ab") as log_fh:
        proc = subprocess.Popen(
            [sys.executable, "-c", _WRAPPER, _rc_path(job_id)] + argv,
            cwd=str(cwd),
            env=cli.child_env(env),
            stdin=subprocess.DEVNULL,
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    with _children_lock:
        _children[job_id] = proc
    record = {
        "job_id": job_id,
        "pid": proc.pid,
        "pid_started": _fingerprint(proc.pid) or "",
        "log_path": log_path,
        "started_at": _now_iso(),
        "cmd": argv,
        "cwd": str(cwd),
        "anchor": cli.anchor().as_dict(),
        "meta": dict(meta or {}),
    }
    _write_json_atomic(_record_path(job_id), record)
    return dict(record)


def read_record(job_id):
    """The stored record, or None when job_id is malformed or unknown."""
    if not isinstance(job_id, str) or not JOB_ID_RE.match(job_id):
        return None
    try:
        with open(_record_path(job_id), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _read_rc(job_id):
    try:
        with open(_rc_path(job_id), encoding="utf-8") as fh:
            return int(fh.read().strip())
    except (OSError, ValueError):
        return None


def status(job_id):
    """Record + {state, exit_code, fingerprint_verified, detail}; None for an unknown job."""
    record = read_record(job_id)
    if record is None:
        return None
    with _children_lock:
        proc = _children.get(job_id)
    wrapper_rc = proc.poll() if proc is not None else None  # reaps our own child
    out = dict(record)
    out.update({"state": "running", "exit_code": None, "fingerprint_verified": False, "detail": ""})
    rc = _read_rc(job_id)
    if rc is not None:
        out.update({"state": "exited", "exit_code": rc, "detail": "command finished"})
        with _children_lock:
            _children.pop(job_id, None)
        return out
    pid = int(record.get("pid") or 0)
    if proc is not None and wrapper_rc is not None:
        out.update({"state": "lost", "detail": "job wrapper ended (rc %s) without an exit record" % wrapper_rc})
        return out
    if pid <= 0 or not _pid_alive(pid):
        out.update({"state": "lost", "detail": "process %d is gone and left no exit record" % pid})
        return out
    verdict = _fp_verdict(record.get("pid_started") or "", pid)
    if verdict == "mismatch":
        out.update({"state": "lost", "detail": "pid %d now belongs to a different process" % pid})
    elif verdict == "match":
        out["fingerprint_verified"] = True
    else:
        out["detail"] = "pid alive; start fingerprint unavailable, identity not verified"
    return out


def wait(job_id, timeout_s, interval_s=0.5):
    """Poll status() until the job is no longer running or `timeout_s` elapses.
    Returns the last status plus timed_out (True when still running at the deadline); None for an
    unknown job."""
    deadline = time.monotonic() + max(0.0, float(timeout_s))
    while True:
        st = status(job_id)
        if st is None:
            return None
        if st["state"] != "running":
            st["timed_out"] = False
            return st
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            st["timed_out"] = True
            return st
        time.sleep(min(interval_s, remaining))


def stop(job_id, grace_s=10):
    """Stop a RUNNING job's whole process group (SIGTERM, bounded wait, then SIGKILL).

    Signals only a job whose pid is PROVEN to still be the recorded process (fingerprint match):
    an unverifiable or recycled pid is never signalled. Returns (stopped: bool, detail: str)."""
    import signal

    st = status(job_id)
    if st is None:
        return False, "unknown job"
    if st["state"] != "running":
        return False, "job is %s" % st["state"]
    if not st.get("fingerprint_verified"):
        return False, "pid %s not proven to be this job; not signalled" % st.get("pid")
    pid = int(st["pid"])
    try:
        os.killpg(pid, signal.SIGTERM)
    except OSError as exc:
        return False, "SIGTERM failed: %s" % exc
    deadline = time.monotonic() + grace_s
    while time.monotonic() < deadline:
        if status(job_id)["state"] != "running":
            return True, "stopped (SIGTERM)"
        time.sleep(0.2)
    try:
        os.killpg(pid, signal.SIGKILL)
    except OSError:
        pass
    return True, "stopped (SIGKILL after %ss)" % grace_s


def list_records():
    """Every job record on this machine (unreadable ones skipped), newest first."""
    out = []
    try:
        names = os.listdir(jobs_dir())
    except OSError:
        return out
    for name in names:
        if name.endswith(".json"):
            rec = read_record(name[:-5])
            if rec is not None:
                out.append(rec)
    out.sort(key=lambda r: r.get("started_at") or "", reverse=True)
    return out


# --------------------------------------------------------------------------- #
# retention
# --------------------------------------------------------------------------- #
def retention_days():
    """The build-log retention bound, read from its one declaration; None when it cannot be read
    (the caller must then prune NOTHING - no bound means nothing is provably old enough)."""
    try:
        with open(str(RETENTION_SOURCE), encoding="utf-8") as fh:
            m = _RETENTION_RE.search(fh.read())
    except OSError:
        return None
    return int(m.group(1)) if m else None


def _older_than(paths, days, now):
    """True when the NEWEST of the existing `paths` is older than `days` - `find -mtime +N`
    semantics (whole days elapsed > N), the test the build-log sweeper applies. An `.rc` is written
    when the job finishes, so a finished job's age counts from its finish, not its start."""
    mtimes = []
    for p in paths:
        try:
            mtimes.append(os.stat(p).st_mtime)
        except OSError:
            continue
    if not mtimes:
        return False
    return int((now - max(mtimes)) // _DAY_S) > days


def _unlink(path):
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


def prune_finished(now=None):
    """Delete finished (exited / lost) job records older than the retention bound, with their .rc
    and the default log the store placed beside them. Returns the pruned job ids.

    Never touches: a RUNNING job (whatever its age - status() is re-checked per record), a record
    that cannot be read (it cannot be classified), or a log outside the jobs dir (a hinted build
    log belongs to the lease-guarded log sweeper). An orphan `.rc` (its record already gone) past
    the bound is removed too. Best-effort and never raises: pruning is housekeeping, so a failure
    here must never fail the tool call or server start that triggered it."""
    pruned = []
    try:
        days = retention_days()
        if days is None:
            cli.log.warning("job prune skipped: cannot read %s from %s", RETENTION_CONST, RETENTION_SOURCE)
            return pruned
        now = time.time() if now is None else now
        root = jobs_dir()
        names = set(os.listdir(root))
        for name in sorted(names):
            if not name.endswith(".json"):
                continue
            job_id = name[:-5]
            if not JOB_ID_RE.match(job_id):
                continue
            default_log = os.path.join(root, job_id + ".log")
            if not _older_than([_record_path(job_id), _rc_path(job_id), default_log], days, now):
                continue
            st = status(job_id)
            if st is None or st["state"] not in ("exited", "lost"):
                continue
            if os.path.abspath(st.get("log_path") or "") == default_log:
                _unlink(default_log)
            _unlink(_rc_path(job_id))
            _unlink(_rc_path(job_id) + ".tmp")
            _unlink(_record_path(job_id))
            with _children_lock:
                _children.pop(job_id, None)
            pruned.append(job_id)
        for name in sorted(names):
            if name.endswith(".rc") and (name[:-3] + ".json") not in names:
                path = os.path.join(root, name)
                if _older_than([path], days, now):
                    _unlink(path)
    except Exception as exc:  # housekeeping must never break its trigger
        cli.log.warning("job prune failed: %s: %s", type(exc).__name__, exc)
    return pruned
