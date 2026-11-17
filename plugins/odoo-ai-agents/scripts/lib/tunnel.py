#!/usr/bin/env python3
"""tunnel.py - a temporary public HTTPS address for a leased local Odoo server.

The address is a Cloudflare Quick Tunnel: the `cloudflared` binary opens it from this machine, needs
no account, no login and no domain, and prints a https://<words>.trycloudflare.com address that
carries a publicly trusted certificate. This module owns everything about the tunnel PROCESS; the
odoo-local tools (instance_expose / instance_unexpose) decide when to start and stop it and set the
database's base URL. Standard library only; syntax stays Python 3.8 compatible.

What lives where
  <state root>/tools/cloudflared/cloudflared    the binary this module fetched (a copy on PATH wins)
  <state root>/runtime/tunnels/<sha256(token)[:32]>.json
                                                one record per exposed lease: the address, the
                                                supervisor's pid + fingerprint, the server's pid +
                                                fingerprint, the log path. The lease registry is
                                                never touched, so a plugin version that predates
                                                tunnels reads and writes its rows exactly as before.
  <state root>/logs/tunnel-<db>-<time>.log      cloudflared's own output (the address is read from it)

The tunnel never outlives the server it fronts, whoever stops that server
  cloudflared runs under a SUPERVISOR (`tunnel.py supervise`, its own session and process group)
  that watches the server's pid and fingerprint and stops cloudflared the moment the server is gone.
  A release, a park, a gc, an owner session that ended, or a plugin version that has never heard of
  tunnels all stop the server by signalling its process group, and none of them needs to know the
  supervisor exists. (Joining the server's own group is not possible: setpgid() refuses a group of
  another session, and the server leads its own session.) The supervisor also stops when it is
  signalled, so `stop()` is one group signal, and cloudflared itself is told to die with its parent.

A record is trusted only while its supervisor is alive (pid + fingerprint): a tunnel that died, or a
record an older plugin version's release left behind, reads as "not exposed".

CLI (the supervisor, started by `start()`):
  tunnel.py supervise --server-pid N [--server-fp FP] --log PATH -- <cloudflared command line>
"""

import contextlib
import hashlib
import json
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import session_anchor  # noqa: E402  (pid liveness + fingerprints, the allocator's own)

RELEASE_URL_ENV = "ODOO_AI_CLOUDFLARED_RELEASE_URL"
DEFAULT_RELEASE_URL = "https://github.com/cloudflare/cloudflared/releases/latest/download"
# A fetched binary older than this is fetched again (Cloudflare retires old cloudflared versions);
# when the fresh fetch fails the old one keeps serving.
MAX_BINARY_AGE_S = 120 * 86400
FETCH_TIMEOUT_S = 180
START_TIMEOUT_S = 60
STOP_GRACE_S = 5.0
WATCH_POLL_S = 0.5
START_TIMEOUT_ENV = "ODOO_AI_TUNNEL_START_TIMEOUT_S"      # tuning knobs (tests shorten them)
REACHABLE_WAIT_ENV = "ODOO_AI_TUNNEL_REACHABLE_WAIT_S"
REACHABLE_WAIT_S = 45.0

# The address cloudflared prints for a Quick Tunnel. `api.trycloudflare.com` is the service that
# hands addresses out and appears in its own error lines; it is never a tunnel.
_URL_RE = re.compile(r"https://([a-z0-9][a-z0-9-]*)\.trycloudflare\.com\b")
_NOT_A_TUNNEL = frozenset(("api",))

CODE_UNAVAILABLE = "CLOUDFLARED_UNAVAILABLE"
CODE_FAILED = "TUNNEL_FAILED"


class TunnelError(Exception):
    """A failure with a stable code; the odoo-local tools turn it into error.code + error.remedy."""

    def __init__(self, code, message, diagnostics=None):
        Exception.__init__(self, message)
        self.code = code
        self.message = message
        self.diagnostics = diagnostics or {}


# --------------------------------------------------------------------------- #
# the binary
# --------------------------------------------------------------------------- #
def release_asset(system=None, machine=None):
    """(asset name, is_archive) of the official release for a platform, or None when there is none.
    Linux and macOS, x86-64 and arm64."""
    system = (system or platform.system()).lower()
    machine = (machine or platform.machine()).lower()
    arch = {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64"}.get(machine)
    if arch is None:
        return None
    if system == "linux":
        return "cloudflared-linux-%s" % arch, False
    if system == "darwin":
        return "cloudflared-darwin-%s.tgz" % arch, True
    return None


def tools_dir(home):
    return os.path.join(home, "tools", "cloudflared")


def tools_binary(home):
    return os.path.join(tools_dir(home), "cloudflared")


def _usable(path):
    return bool(path) and os.path.isfile(path) and os.access(path, os.X_OK)


def _new_file(directory, prefix):
    """(fd, path) of a new, uniquely named file (mode 0600) inside `directory`: created with
    O_EXCL, so two fetches at once never share one and a file is never reused."""
    while True:
        path = os.path.join(directory, "%s%s-%s" % (prefix, os.getpid(), uuid.uuid4().hex))
        try:
            return os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), path
        except FileExistsError:
            continue


def _download(url, dest_dir, timeout):
    """Download `url` into a new file under `dest_dir`; the path. A refusal (an HTTP error, no
    route, a stalled transfer) is a TunnelError."""
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "odoo-ai-agents"})
        with contextlib.closing(urllib.request.urlopen(request, timeout=timeout)) as resp:
            fd, path = _new_file(dest_dir, "download-")
            try:
                with os.fdopen(fd, "wb") as out:
                    shutil.copyfileobj(resp, out)
            except BaseException:
                with contextlib.suppress(OSError):
                    os.unlink(path)
                raise
    except urllib.error.HTTPError as exc:
        raise TunnelError(CODE_UNAVAILABLE, "the download of %s was refused: HTTP %s" % (url, exc.code),
                          {"url": url, "http_status": exc.code})
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise TunnelError(CODE_UNAVAILABLE, "could not download %s: %s" % (url, exc), {"url": url})
    return path


def _extract_tgz(archive, dest_dir):
    """The `cloudflared` file of a release archive, written under `dest_dir`; its path."""
    with tarfile.open(archive, "r:gz") as tar:
        member = next((m for m in tar.getmembers() if m.isfile() and os.path.basename(m.name) == "cloudflared"),
                      None)
        if member is None:
            raise TunnelError(CODE_UNAVAILABLE, "the downloaded archive holds no cloudflared file")
        fd, path = _new_file(dest_dir, "extract-")
        with os.fdopen(fd, "wb") as out:
            shutil.copyfileobj(tar.extractfile(member), out)
    return path


def _runs(path):
    """True when `path --version` exits 0: the file is a program this machine can run."""
    try:
        proc = subprocess.run([path, "--version"], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


@contextlib.contextmanager
def _fetch_lock(directory):
    """One fetch at a time on this machine (every odoo-local server shares the state root)."""
    import fcntl
    os.makedirs(directory, exist_ok=True)
    fd = os.open(os.path.join(directory, ".fetch.lock"), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def fetch_cloudflared(home, timeout=FETCH_TIMEOUT_S):
    """Fetch the official release for this platform into the tools directory and return the
    binary's path. The release is the LATEST one (`<base>/<asset>`; the base is
    DEFAULT_RELEASE_URL, or $ODOO_AI_CLOUDFLARED_RELEASE_URL for a mirror): there is no version to
    keep in step with. The file is placed only after it ran (`--version`), by an atomic rename."""
    asset = release_asset()
    if asset is None:
        raise TunnelError(CODE_UNAVAILABLE, "no official cloudflared release for %s/%s" % (
            platform.system(), platform.machine()), {"system": platform.system(), "machine": platform.machine()})
    name, archive = asset
    base = (os.environ.get(RELEASE_URL_ENV) or DEFAULT_RELEASE_URL).rstrip("/")
    target = tools_binary(home)
    directory = tools_dir(home)
    with _fetch_lock(directory):
        # Another call may have fetched while this one waited for the lock.
        if _usable(target) and not _stale(target):
            return target
        downloaded = _download("%s/%s" % (base, name), directory, timeout)
        extracted = None
        try:
            candidate = downloaded
            if archive:
                extracted = candidate = _extract_tgz(downloaded, directory)
            os.chmod(candidate, 0o755)
            if not _runs(candidate):
                raise TunnelError(CODE_UNAVAILABLE, "the downloaded %s does not run on this machine" % name,
                                  {"url": "%s/%s" % (base, name)})
            os.replace(candidate, target)
            if candidate == extracted:
                extracted = None
        finally:
            for leftover in (downloaded, extracted):
                if leftover:
                    with contextlib.suppress(OSError):
                        os.unlink(leftover)
    return target


def _stale(path):
    try:
        return time.time() - os.stat(path).st_mtime > MAX_BINARY_AGE_S
    except OSError:
        return True


def obtain_cloudflared(home, timeout=FETCH_TIMEOUT_S):
    """The cloudflared to run: PATH, else the tools directory (fetched again when older than
    MAX_BINARY_AGE_S, the old copy kept when that fails), else fetched now. TunnelError
    CLOUDFLARED_UNAVAILABLE when none can be had."""
    on_path = shutil.which("cloudflared")
    if on_path:
        return on_path
    own = tools_binary(home)
    if _usable(own):
        if not _stale(own):
            return own
        try:
            return fetch_cloudflared(home, timeout)
        except TunnelError:
            return own
    return fetch_cloudflared(home, timeout)


# --------------------------------------------------------------------------- #
# processes
# --------------------------------------------------------------------------- #
def _zombie(pid):
    _comm, fields = session_anchor._proc_stat(pid)
    return bool(fields) and fields[0] == "Z"


def process_alive(pid, fingerprint=None):
    """True while `pid` is the live process the fingerprint recorded: running (a zombie is not),
    and not a recycled number."""
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 1:
        return False
    if not session_anchor.pid_alive(pid) or _zombie(pid):
        return False
    if fingerprint and session_anchor.fp_verdict(fingerprint, pid) == session_anchor.VERDICT_MISMATCH:
        return False
    return True


def _die_with_parent():
    """Child setup: SIGTERM this process when its parent dies (Linux). A supervisor killed with
    SIGKILL then still takes cloudflared with it. Best effort - other systems skip it."""
    try:
        import ctypes
        ctypes.CDLL(None).prctl(1, signal.SIGTERM)   # PR_SET_PDEATHSIG
    except Exception:
        pass


def _terminate(child, grace=2.0):
    if child.poll() is not None:
        return
    with contextlib.suppress(OSError):
        child.terminate()
    deadline = time.time() + grace
    while time.time() < deadline and child.poll() is None:
        time.sleep(0.05)
    if child.poll() is None:
        with contextlib.suppress(OSError):
            child.kill()
        with contextlib.suppress(Exception):
            child.wait(timeout=5)


def supervise(argv):
    """The supervisor: run the cloudflared command line after `--`, and stop it when the server
    (pid + fingerprint) is gone, when it exits by itself, or when this process is signalled.
    Exit code: cloudflared's own when it exited first, else 0."""
    server_pid, server_fp, log_path, cmd = None, None, None, None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--":
            cmd = argv[i + 1:]
            break
        if a == "--server-pid" and i + 1 < len(argv):
            server_pid = int(argv[i + 1])
            i += 2
        elif a == "--server-fp" and i + 1 < len(argv):
            server_fp = argv[i + 1]
            i += 2
        elif a == "--log" and i + 1 < len(argv):
            log_path = argv[i + 1]
            i += 2
        else:
            sys.stderr.write("tunnel.py supervise: unknown argument %r\n" % a)
            return 2
    if server_pid is None or not log_path or not cmd:
        sys.stderr.write("usage: tunnel.py supervise --server-pid N [--server-fp FP] --log PATH -- CMD...\n")
        return 2
    stopping = []
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, lambda *_a: stopping.append(1))
    log = open(log_path, "ab")
    try:
        child = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                 preexec_fn=_die_with_parent)
    except OSError as exc:
        log.write(("tunnel.py supervise: cannot run %s: %s\n" % (cmd[0], exc)).encode("utf-8"))
        return 127
    finally:
        log.close()
    try:
        while not stopping:
            code = child.poll()
            if code is not None:
                return code
            if not process_alive(server_pid, server_fp):
                break
            time.sleep(WATCH_POLL_S)
    finally:
        _terminate(child)
    return 0


# --------------------------------------------------------------------------- #
# records
# --------------------------------------------------------------------------- #
def token_hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:32]


def records_dir(home):
    return os.path.join(home, "runtime", "tunnels")


def record_path(home, token):
    return os.path.join(records_dir(home), token_hash(token) + ".json")


def read_record(home, token):
    """The stored record of a lease's tunnel, alive or not; None when there is none."""
    try:
        with open(record_path(home, token), "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get("public_url") else None


def _write_record(home, token, record):
    os.makedirs(records_dir(home), exist_ok=True)
    path = record_path(home, token)
    tmp = "%s.%d.tmp" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(record, fh)
    os.replace(tmp, path)


def remove_record(home, token):
    with contextlib.suppress(OSError):
        os.unlink(record_path(home, token))


def is_alive(record):
    return bool(record) and process_alive(record.get("supervisor_pid"), record.get("supervisor_fp"))


def live_record(home, token):
    """The record of a lease's tunnel while its supervisor runs; None otherwise (never exposed, the
    tunnel died, or a release by an older plugin version stopped the server and with it the
    supervisor)."""
    record = read_record(home, token)
    return record if is_alive(record) else None


def public_url(home, token):
    """The public address of the lease's live tunnel, else None. Cheap: one small file read."""
    if not token:
        return None
    record = live_record(home, token)
    return record["public_url"] if record else None


def sweep(home, live_tokens):
    """Delete the records of dead tunnels whose lease is gone (`live_tokens`: every token of the
    registry). The record of a lease that still exists stays: instance_serve restores that lease's
    base URL from it, and a live tunnel's record is never removed here."""
    try:
        names = os.listdir(records_dir(home))
    except OSError:
        return
    kept = set(token_hash(t) for t in live_tokens if t)
    for name in names:
        if not name.endswith(".json") or name[:-5] in kept:
            continue
        path = os.path.join(records_dir(home), name)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                record = json.load(fh)
        except (OSError, ValueError):
            record = None
        if not is_alive(record):
            with contextlib.suppress(OSError):
                os.unlink(path)


# --------------------------------------------------------------------------- #
# start / stop
# --------------------------------------------------------------------------- #
def find_public_url(text):
    """The first Quick Tunnel address in cloudflared's output, else None."""
    for m in _URL_RE.finditer(text or ""):
        if m.group(1) not in _NOT_A_TUNNEL:
            return m.group(0)
    return None


def _read_text(path, limit=65536):
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - limit))
            return fh.read().decode("utf-8", "replace")
    except OSError:
        return ""


def log_tail(path, lines=20):
    return "\n".join(_read_text(path, 16384).splitlines()[-lines:])


def kill_group(pid, fingerprint=None, grace=STOP_GRACE_S):
    """Stop the process group a supervisor leads (the supervisor and cloudflared): SIGTERM, a
    bounded wait, SIGKILL. Does nothing for a pid that is no longer the recorded process."""
    if not process_alive(pid, fingerprint):
        return
    with contextlib.suppress(OSError):
        os.killpg(pid, signal.SIGTERM)
    deadline = time.time() + grace
    while time.time() < deadline and process_alive(pid, fingerprint):
        time.sleep(0.05)
    if process_alive(pid, fingerprint):
        with contextlib.suppress(OSError):
            os.killpg(pid, signal.SIGKILL)
        deadline = time.time() + grace
        while time.time() < deadline and process_alive(pid, fingerprint):
            time.sleep(0.05)


def stop(home, token):
    """Stop the lease's tunnel and delete its record. Returns the record that was stored (alive or
    not), None when there was none."""
    record = read_record(home, token)
    if record:
        kill_group(record.get("supervisor_pid"), record.get("supervisor_fp"))
    remove_record(home, token)
    return record


_REAPERS = []


def start(home, token, server_pid, http_port, db_name, cloudflared, env=None, timeout=None):
    """Start the tunnel of the lease's server and return its record once the address is known.

    The supervisor is a session of its own (a signal to the server's group never reaches it, and its
    own group is one `kill_group` away). The record is written as soon as the address is printed.
    TunnelError TUNNEL_FAILED, with the end of cloudflared's output, when it exits first or prints
    no address within `timeout`; nothing is left running then."""
    if timeout is None:
        try:
            timeout = float(os.environ.get(START_TIMEOUT_ENV, START_TIMEOUT_S))
        except ValueError:
            timeout = START_TIMEOUT_S
    logs = os.path.join(home, "logs")
    os.makedirs(logs, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    log_path = os.path.join(logs, "tunnel-%s-%s.log" % (re.sub(r"[^A-Za-z0-9_.-]", "_", db_name or "db"), stamp))
    server_fp = session_anchor.fingerprint(server_pid)
    cmd = [cloudflared, "tunnel", "--no-autoupdate", "--url", "http://127.0.0.1:%d" % int(http_port)]
    argv = [sys.executable, os.path.abspath(__file__), "supervise", "--server-pid", str(server_pid)]
    if server_fp:
        argv += ["--server-fp", server_fp]
    argv += ["--log", log_path, "--"] + cmd
    proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            env=env, start_new_session=True)
    # The supervisor is this process's child: reap it when it exits, or it would stay a zombie.
    import threading
    reaper = threading.Thread(target=proc.wait, daemon=True)
    reaper.start()
    _REAPERS.append(reaper)
    _REAPERS[:] = [t for t in _REAPERS if t.is_alive()]
    supervisor_fp = session_anchor.fingerprint(proc.pid)
    deadline = time.time() + timeout
    url = None
    while time.time() < deadline:
        url = find_public_url(_read_text(log_path))
        if url or proc.poll() is not None:
            break
        time.sleep(0.2)
    if not url:
        kill_group(proc.pid, supervisor_fp)
        raise TunnelError(CODE_FAILED, "cloudflared %s" % (
            "exited before it printed an address" if proc.poll() is not None
            else "printed no address within %gs" % timeout),
            {"log_path": log_path, "log_tail": log_tail(log_path)})
    record = {"public_url": url, "supervisor_pid": proc.pid, "supervisor_fp": supervisor_fp,
              "server_pid": server_pid, "server_fp": server_fp, "http_port": int(http_port),
              "db_name": db_name, "cloudflared": cloudflared, "log_path": log_path,
              "started_at": time.time()}
    _write_record(home, token, record)
    return record


def wait_reachable(url, timeout=None):
    """True when `url` answers with anything below HTTP 500 within `timeout` seconds (default:
    REACHABLE_WAIT_S, or $ODOO_AI_TUNNEL_REACHABLE_WAIT_S; 0 = no probe, False). A new Quick Tunnel's
    name needs a moment to resolve and connect; a 5xx from the edge means the tunnel is not
    connected yet."""
    if timeout is None:
        try:
            timeout = float(os.environ.get(REACHABLE_WAIT_ENV, REACHABLE_WAIT_S))
        except ValueError:
            timeout = REACHABLE_WAIT_S
    if timeout <= 0:
        return False   # a zero wait is "do not probe" (tests, offline machines)
    deadline = time.time() + timeout
    while True:
        try:
            with contextlib.closing(urllib.request.urlopen(
                    urllib.request.Request(url.rstrip("/") + "/web/login", headers={"User-Agent": "odoo-ai-agents"}),
                    timeout=10)):
                return True
        except urllib.error.HTTPError as exc:
            if exc.code < 500:
                return True
        except (urllib.error.URLError, OSError, ValueError):
            pass
        if time.time() >= deadline:
            return False
        time.sleep(1.5)


def main(argv):
    if argv and argv[0] == "supervise":
        return supervise(argv[1:])
    sys.stderr.write("usage: tunnel.py supervise --server-pid N [--server-fp FP] --log PATH -- CMD...\n")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
