"""session_anchor.py - process identity + the session LIVENESS ANCHOR (stdlib only).

Two questions the allocator must answer about a process it did not start and
cannot hold a handle on, both of them on a kill/drop path:

  1. "Is the process at pid P still the one I recorded?" - `fingerprint(pid)` +
     `fp_verdict(expected, pid)`. A bare `os.kill(pid, 0)` only proves SOME
     process holds that number; pids are recycled.
  2. "Is the agent SESSION that owns a lease still alive?" - `discover_anchor()`
     + `anchor_state()`. A lease is anchored to the long-lived agent CLI process
     (claude / codex / gemini) of the session that acquired it. Every Bash tool
     subprocess of a Claude Code session - including every subagent's - carries
     `CLAUDE_PID` (that long-lived process) and the SAME `CLAUDE_CODE_SESSION_ID`,
     and a plugin stdio MCP server is a direct child of it. So "the session is
     alive" is observable without heartbeats, TTLs or any cooperation from the
     many short-lived processes a run is made of.

Fingerprint schemes (the recorded string names its own scheme):
    proc:<boot_id>:<starttime>   Linux. `starttime` is field 22 of
                                 /proc/<pid>/stat (clock ticks since boot) and
                                 `boot_id` scopes it to one boot - both are
                                 kernel facts, independent of TZ and locale.
    ps:<lstart>                  Elsewhere. `ps -o lstart=` run with TZ=UTC and
                                 LC_ALL=C, so the string does not depend on the
                                 caller's timezone or locale.
    <bare lstart>                LEGACY: the caller's-TZ `ps -o lstart=`
                                 (`legacy_lstart`). It cannot be re-measured
                                 reliably - the TZ it was taken under is not
                                 recorded - so it is compared in BOTH the local
                                 TZ and UTC and never yields "mismatch": a false
                                 mismatch is how a live server was condemned as
                                 "recycled" and killed. The allocator still
                                 WRITES it (owner.pid_started) beside the
                                 TZ-free one (owner.pid_fp), because an older
                                 allocator sharing the registry compares
                                 pid_started with `==` against exactly this
                                 shape.

Anchor precedence (`discover_anchor`):
    ODOO_AI_SESSION_ANCHOR="<pid>:<fingerprint>"   explicit (an MCP server
                                                   exports its own); the value
                                                   "none" DISABLES anchoring
    CLAUDE_PID                                     every Claude Code Bash tool
    an ancestor (<= MAX_ANCESTOR_LEVELS) whose comm or exe basename is one of
    ANCHOR_COMMS                                   any other launch shape
    None                                           unanchored (CI, a human shell)

Deliberately syntax-compatible with Python 3.8 and free of third-party imports:
it is imported by allocator.py and by the stdio MCP server, both of which run
under whatever `python3` the host has.
"""

import os
import socket
import subprocess

ANCHOR_ENV = "ODOO_AI_SESSION_ANCHOR"
ANCHOR_DISABLED = "none"
SESSION_ID_ENV = "CLAUDE_CODE_SESSION_ID"
CLAUDE_PID_ENV = "CLAUDE_PID"
ANCHOR_COMMS = ("claude", "codex", "gemini")
MAX_ANCESTOR_LEVELS = 6
BOOT_ID_PATH = "/proc/sys/kernel/random/boot_id"
PS_TIMEOUT_S = 10

SCHEME_PROC = "proc:"
SCHEME_PS = "ps:"

VERDICT_MATCH = "match"
VERDICT_MISMATCH = "mismatch"
VERDICT_UNKNOWN = "unknown"

STATE_ALIVE = "alive"
STATE_DEAD = "dead"
STATE_UNKNOWN = "unknown"


# --------------------------------------------------------------------------- #
# Kernel facts
# --------------------------------------------------------------------------- #
def boot_id():
    """This boot's kernel-issued identity, or None when it cannot be read
    (not Linux). None is "could not look", never a value."""
    try:
        with open(BOOT_ID_PATH, "r", encoding="utf-8") as fh:
            return fh.read().strip() or None
    except OSError:
        return None


def _proc_stat(pid):
    """(comm, fields) from /proc/<pid>/stat, or (None, None).

    `comm` (field 2) is wrapped in parentheses and may itself contain spaces
    and ')' - so the record is split at the LAST ')'. `fields[0]` is then
    field 3 (state), i.e. field N lives at fields[N - 3]."""
    try:
        with open("/proc/%d/stat" % int(pid), "rb") as fh:
            raw = fh.read().decode("utf-8", "replace")
    except (OSError, ValueError, TypeError):
        return None, None
    open_at = raw.find("(")
    close_at = raw.rfind(")")
    if open_at < 0 or close_at < open_at:
        return None, None
    return raw[open_at + 1:close_at], raw[close_at + 1:].split()


def proc_starttime(pid):
    """Field 22 of /proc/<pid>/stat (start time in clock ticks since boot) as a
    string, or None when /proc cannot answer."""
    _comm, fields = _proc_stat(pid)
    if not fields or len(fields) < 20:
        return None
    value = fields[22 - 3]
    return value if value.isdigit() else None


def _proc_ppid(pid):
    _comm, fields = _proc_stat(pid)
    if not fields or len(fields) < 2 or not fields[1].lstrip("-").isdigit():
        return None
    return int(fields[1])


def pid_alive(pid):
    """True when SOME process holds `pid` (it may belong to another user)."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _ps(args, utc):
    """stdout of `ps <args>` stripped, or None. `utc` pins TZ=UTC and LC_ALL=C;
    otherwise the ambient environment is used (the LEGACY recording shape)."""
    env = dict(os.environ)
    if utc:
        env["TZ"] = "UTC"
        env["LC_ALL"] = "C"
    try:
        proc = subprocess.run(["ps"] + list(args), capture_output=True, text=True,
                              env=env, timeout=PS_TIMEOUT_S)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def _ps_lstart(pid, utc):
    return _ps(["-o", "lstart=", "-p", str(int(pid))], utc)


def legacy_lstart(pid):
    """The LEGACY fingerprint of the process at `pid`: bare `ps -o lstart=` in
    the caller's ambient TZ and locale, byte-for-byte what allocators before
    this module recorded (and still compare with `==`). None when it cannot be
    measured. It is written ONLY so an older allocator sharing the registry can
    still recognise a live server; it is never trusted by this module's own
    comparisons beyond `fp_verdict`'s legacy rung."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return None
    return _ps_lstart(pid, utc=False)


# --------------------------------------------------------------------------- #
# Fingerprints
# --------------------------------------------------------------------------- #
def fingerprint(pid):
    """A TZ- and locale-independent identity for the process CURRENTLY at `pid`,
    or None when the pid is not running or nothing could measure it. Callers
    MUST treat None as "cannot verify", never as a match or a mismatch."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return None
    boot = boot_id()
    start = proc_starttime(pid)
    if boot and start:
        return "%s%s:%s" % (SCHEME_PROC, boot, start)
    lstart = _ps_lstart(pid, utc=True)
    if lstart:
        return SCHEME_PS + lstart
    return None


def fp_verdict(expected, pid):
    """"match" | "mismatch" | "unknown": is the process at `pid` the one whose
    fingerprint `expected` recorded?

    "mismatch" is a PROOF that the recorded process is gone (the pid was
    recycled, or it was recorded in a previous boot) and is only ever returned
    when both sides were measured under the SAME scheme. Anything that could not
    be measured - and every legacy fingerprint that matches neither timezone -
    is "unknown"."""
    if not expected:
        return VERDICT_UNKNOWN
    expected = str(expected)
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return VERDICT_UNKNOWN
    if expected.startswith(SCHEME_PROC):
        recorded_boot, _sep, recorded_start = expected[len(SCHEME_PROC):].rpartition(":")
        if not recorded_boot or not recorded_start:
            return VERDICT_UNKNOWN
        current_boot = boot_id()
        if current_boot is None:
            return VERDICT_UNKNOWN
        if current_boot != recorded_boot:
            # Recorded in another boot: whatever holds the number now is not it.
            return VERDICT_MISMATCH
        current_start = proc_starttime(pid)
        if current_start is None:
            return VERDICT_UNKNOWN
        return VERDICT_MATCH if current_start == recorded_start else VERDICT_MISMATCH
    if expected.startswith(SCHEME_PS):
        current = _ps_lstart(pid, utc=True)
        if current is None:
            return VERDICT_UNKNOWN
        return VERDICT_MATCH if current == expected[len(SCHEME_PS):] else VERDICT_MISMATCH
    # LEGACY bare lstart, recorded in some caller's TZ that was never written down.
    for utc in (False, True):
        if _ps_lstart(pid, utc=utc) == expected:
            return VERDICT_MATCH
    return VERDICT_UNKNOWN


# --------------------------------------------------------------------------- #
# The session anchor
# --------------------------------------------------------------------------- #
def format_anchor(pid, started):
    """The exported `<pid>:<fingerprint>` spelling of an anchor."""
    return "%d:%s" % (int(pid), started or "")


def parse_anchor(value):
    """(pid, fingerprint-or-None) from `<pid>:<fingerprint>` (or a bare pid), or
    None when `value` is empty, "none" or malformed."""
    value = (value or "").strip()
    if not value or value.lower() == ANCHOR_DISABLED:
        return None
    head, _sep, tail = value.partition(":")
    if not head.isdigit() or int(head) <= 0:
        return None
    return int(head), (tail or None)


def _comm_and_exe(pid):
    """(comm, exe basename) of `pid`, each possibly None."""
    comm, _fields = _proc_stat(pid)
    exe = None
    try:
        exe = os.path.basename(os.readlink("/proc/%d/exe" % int(pid)))
    except (OSError, ValueError, TypeError):
        exe = None
    if comm is None:
        out = _ps(["-o", "comm=", "-p", str(int(pid))], utc=True)
        comm = os.path.basename(out) if out else None
    return comm, exe


def _parent(pid):
    ppid = _proc_ppid(pid)
    if ppid is not None:
        return ppid
    out = _ps(["-o", "ppid=", "-p", str(int(pid))], utc=True)
    return int(out) if out and out.isdigit() else None


def _ancestor_anchor(start_pid):
    """The nearest ancestor (up to MAX_ANCESTOR_LEVELS, starting at `start_pid`)
    whose comm or exe basename is an agent CLI, or None."""
    pid = start_pid
    for _level in range(MAX_ANCESTOR_LEVELS):
        if pid is None or pid <= 1:
            return None
        comm, exe = _comm_and_exe(pid)
        if comm in ANCHOR_COMMS or exe in ANCHOR_COMMS:
            return pid
        pid = _parent(pid)
    return None


def discover_anchor(env=None):
    """The caller's session anchor as {pid, started, session_id, source}, or None
    when the caller is not inside an agent session (or anchoring is disabled).

    `source` names the rung that answered: "env" | "claude-pid" | "ancestor"."""
    env = os.environ if env is None else env
    session_id = env.get(SESSION_ID_ENV, "") or ""
    raw = env.get(ANCHOR_ENV)
    if raw is not None and raw.strip():
        if raw.strip().lower() == ANCHOR_DISABLED:
            return None
        parsed = parse_anchor(raw)
        if parsed is not None:
            pid, started = parsed
            return {"pid": pid, "started": started or fingerprint(pid),
                    "session_id": session_id, "source": "env"}
        # A malformed explicit value is ignored (falls through), not trusted.
    claude_pid = (env.get(CLAUDE_PID_ENV) or "").strip()
    if claude_pid.isdigit() and pid_alive(int(claude_pid)):
        pid = int(claude_pid)
        return {"pid": pid, "started": fingerprint(pid),
                "session_id": session_id, "source": "claude-pid"}
    pid = _ancestor_anchor(os.getppid())
    if pid is not None:
        return {"pid": pid, "started": fingerprint(pid),
                "session_id": session_id, "source": "ancestor"}
    return None


def anchor_state(anchor, host=None, this_host=None):
    """"alive" | "dead" | "unknown" for a recorded anchor {pid, started, ...}.

    `host` is the host the anchor was recorded on (`this_host` defaults to this
    machine's hostname); a pid means nothing on any other host, so an off-host
    anchor is "unknown". "dead" requires PROOF: the
    pid is gone, or it is held by a different process (fingerprint mismatch).
    A live pid whose fingerprint cannot be matched is "unknown", never alive."""
    if not anchor or not isinstance(anchor, dict):
        return STATE_UNKNOWN
    if host is not None:
        if (this_host or socket.gethostname()) != host:
            return STATE_UNKNOWN
    try:
        pid = int(anchor.get("pid"))
    except (TypeError, ValueError):
        return STATE_UNKNOWN
    if not pid_alive(pid):
        return STATE_DEAD
    verdict = fp_verdict(anchor.get("started"), pid)
    if verdict == VERDICT_MATCH:
        return STATE_ALIVE
    if verdict == VERDICT_MISMATCH:
        return STATE_DEAD
    return STATE_UNKNOWN


def same_anchor(a, b):
    """True when two anchors name the same process (pid AND fingerprint)."""
    if not a or not b:
        return False
    try:
        return (int(a.get("pid")) == int(b.get("pid"))
                and bool(a.get("started")) and a.get("started") == b.get("started"))
    except (TypeError, ValueError):
        return False
