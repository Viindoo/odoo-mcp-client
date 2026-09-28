"""cli.py - plugin paths, the session anchor, and the subprocess boundary of the odoo-local server.

Everything the server runs out-of-process goes through `run()`: it always passes an explicit cwd, a
timeout, and the anchor environment (ODOO_AI_SESSION_ANCHOR, ODOO_AI_VIA=mcp), so a child the
server spawns is attributed to the Claude Code session that owns this server.

Plugin root is derived from THIS file's location, never from the environment, so the server works
from any install path (marketplace cache, --plugin-dir checkout, worktree).
"""

import importlib.util
import json
import logging
import os
import signal
import subprocess
import sys
import threading
from pathlib import Path

log = logging.getLogger("odoo-local")

# odoo_local/cli.py -> parents: [0] odoo_local, [1] mcp, [2] scripts, [3] <plugin root>
PACKAGE_DIR = Path(__file__).resolve().parent
PLUGIN_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = PLUGIN_ROOT / "scripts"
LIB_DIR = SCRIPTS_DIR / "lib"
SETUP_STEPS_DIR = SCRIPTS_DIR / "setup-steps"
PLUGIN_MANIFEST = PLUGIN_ROOT / ".claude-plugin" / "plugin.json"
ALLOCATOR = LIB_DIR / "allocator.py"

ANCHOR_ENV = "ODOO_AI_SESSION_ANCHOR"
VIA_ENV = "ODOO_AI_VIA"
VIA_VALUE = "mcp"
SESSION_ID_ENV = "CLAUDE_CODE_SESSION_ID"

DEFAULT_TIMEOUT_S = 120
_TAIL = 4000  # chars of stdout/stderr carried into diagnostics


def plugin_version():
    """serverInfo.version - read from the plugin manifest (the version SSOT), never hardcoded."""
    try:
        with open(str(PLUGIN_MANIFEST), encoding="utf-8") as fh:
            version = json.load(fh).get("version")
        if isinstance(version, str) and version:
            return version
    except (OSError, ValueError) as exc:
        log.warning("cannot read plugin version from %s: %s", PLUGIN_MANIFEST, exc)
    return "0.0.0+unknown"


# --------------------------------------------------------------------------- #
# in-process access to scripts/lib modules
# --------------------------------------------------------------------------- #
_lib_lock = threading.Lock()
_lib_cache = {}


def load_lib(name):
    """Import scripts/lib/<name>.py under a private module name (no sys.path mutation, so a generic
    lib name like `paths` can never shadow or be shadowed by another package). Cached.
    Raises ImportError when the file is absent."""
    with _lib_lock:
        if name in _lib_cache:
            return _lib_cache[name]
        path = LIB_DIR / (name + ".py")
        if not path.is_file():
            raise ImportError("scripts/lib/%s.py not found at %s" % (name, path))
        spec = importlib.util.spec_from_file_location("odoo_local_lib_" + name, str(path))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        try:
            spec.loader.exec_module(mod)
        except BaseException:
            sys.modules.pop(spec.name, None)
            raise
        _lib_cache[name] = mod
        return mod


def try_load_lib(name):
    """load_lib, or None (with a logged reason) when the module is absent or fails to import."""
    try:
        return load_lib(name)
    except Exception as exc:
        log.info("scripts/lib/%s.py unavailable: %s: %s", name, type(exc).__name__, exc)
        return None


# --------------------------------------------------------------------------- #
# session anchor
# --------------------------------------------------------------------------- #
class Anchor(object):
    """The Claude Code session this server belongs to: the agent CLI process that spawned this
    stdio server (the nearest `claude`/`codex`/`gemini` ancestor, else the parent pid), that pid's
    fingerprint, and the session id."""

    def __init__(self, pid, fingerprint, session_id, source):
        self.pid = pid
        self.fingerprint = fingerprint
        self.session_id = session_id
        self.source = source

    @property
    def env_value(self):
        """"<pid>:<fingerprint>" (session_anchor.format_anchor spelling), or None when the
        fingerprint is unknown - a pid alone cannot prove the same process later (pid recycling),
        so a partial anchor is never exported."""
        if not self.fingerprint:
            return None
        mod = try_load_lib("session_anchor")
        if mod is not None and hasattr(mod, "format_anchor"):
            return mod.format_anchor(self.pid, self.fingerprint)
        return "%d:%s" % (self.pid, self.fingerprint)

    def as_dict(self):
        return {
            "pid": self.pid,
            "fingerprint": self.fingerprint or "",
            "session_id": self.session_id or "",
            "source": self.source,
            "exported": self.env_value is not None and not anchoring_disabled(),
        }


def _explicit_anchor(env):
    """An Anchor from a well-formed ODOO_AI_SESSION_ANCHOR="<pid>:<fingerprint>" the server was
    STARTED with, or None. Same precedence as session_anchor.discover_anchor (explicit first): an
    operator or harness that states the session process is believed over the parent-pid guess.
    A bare pid (no fingerprint) or a malformed value is ignored - it cannot prove identity later."""
    raw = (env.get(ANCHOR_ENV) or "").strip()
    if not raw or raw.lower() == ANCHOR_DISABLED:
        return None
    mod = try_load_lib("session_anchor")
    if mod is None or not hasattr(mod, "parse_anchor"):
        return None
    parsed = mod.parse_anchor(raw)
    if parsed is None or not parsed[1]:
        log.warning("ignoring malformed %s=%r (need <pid>:<fingerprint>)", ANCHOR_ENV, raw)
        return None
    return Anchor(parsed[0], parsed[1], env.get(SESSION_ID_ENV) or None, "env")


def _session_pid(anchor_mod, ppid):
    """The pid of the agent CLI that owns this server: the nearest ancestor, starting at the
    parent, whose comm/exe is an agent CLI (session_anchor._ancestor_anchor - the ONE ancestor
    walk, not re-implemented here), else the parent itself. The walk matters when the server is
    started through a wrapper (`sh -c`, a sandbox launcher): anchoring on the wrapper would tie
    every lease to a process that is not the session. Returns (pid, source)."""
    walk = getattr(anchor_mod, "_ancestor_anchor", None) if anchor_mod is not None else None
    if walk is not None:
        try:
            found = walk(ppid)
        except Exception as exc:
            log.warning("session_anchor ancestor walk from %d failed: %s: %s", ppid, type(exc).__name__, exc)
            found = None
        if found is not None:
            return found, ("mcp-ppid" if found == ppid else "mcp-ancestor")
    return ppid, "mcp-ppid"


def compute_anchor(env=None):
    env = os.environ if env is None else env
    explicit = _explicit_anchor(env)
    if explicit is not None:
        return explicit
    anchor_mod = try_load_lib("session_anchor")
    pid, source = _session_pid(anchor_mod, os.getppid())
    fingerprint = None
    if anchor_mod is not None and hasattr(anchor_mod, "fingerprint"):
        try:
            fingerprint = anchor_mod.fingerprint(pid)
        except Exception as exc:
            log.warning("session_anchor.fingerprint(%d) failed: %s: %s", pid, type(exc).__name__, exc)
    if not fingerprint:
        log.warning("session anchor fingerprint unavailable for pid %d; %s is not exported", pid, ANCHOR_ENV)
    claude_pid = env.get("CLAUDE_PID")
    if claude_pid and claude_pid != str(pid):
        log.warning("CLAUDE_PID=%s differs from the session pid %d (%s); anchoring on %d",
                    claude_pid, pid, source, pid)
    return Anchor(pid, fingerprint or None, env.get(SESSION_ID_ENV) or None, source)


_anchor_lock = threading.Lock()
_anchor = []


def anchor():
    """The process-wide anchor, computed once at first use (the server calls this at startup)."""
    with _anchor_lock:
        if not _anchor:
            _anchor.append(compute_anchor())
        return _anchor[0]


ANCHOR_DISABLED = "none"  # session_anchor.ANCHOR_DISABLED: an operator opt-out, propagated untouched


def anchoring_disabled(env=None):
    env = os.environ if env is None else env
    return (env.get(ANCHOR_ENV) or "").strip().lower() == ANCHOR_DISABLED


def child_env(extra=None):
    env = dict(os.environ)
    if not anchoring_disabled(env):
        value = anchor().env_value
        if value:
            env[ANCHOR_ENV] = value
        else:
            env.pop(ANCHOR_ENV, None)
    env[VIA_ENV] = VIA_VALUE
    if extra:
        env.update(extra)
    return env


# --------------------------------------------------------------------------- #
# subprocess boundary
# --------------------------------------------------------------------------- #
class SubprocessTimeout(Exception):
    def __init__(self, argv, timeout_s, stdout, stderr):
        Exception.__init__(self, "%s timed out after %ss" % (argv[0], timeout_s))
        self.argv = argv
        self.timeout_s = timeout_s
        self.stdout = stdout
        self.stderr = stderr


def tail(text, limit=_TAIL):
    text = text or ""
    return text if len(text) <= limit else "..." + text[-limit:]


def run(argv, cwd, timeout_s=DEFAULT_TIMEOUT_S, extra_env=None, stdin_text=None):
    """Run argv with an explicit cwd and the anchor env. Returns (rc, stdout, stderr).

    The child is a session leader, so on timeout its WHOLE process group is killed (a helper that
    forked a grandchild cannot outlive the bound). Raises SubprocessTimeout on timeout,
    FileNotFoundError / NotADirectoryError for a bad executable or cwd."""
    if not cwd or not os.path.isdir(str(cwd)):
        raise NotADirectoryError("cwd is not a directory: %r" % (cwd,))
    argv = [str(a) for a in argv]
    proc = subprocess.Popen(
        argv,
        cwd=str(cwd),
        env=child_env(extra_env),
        stdin=subprocess.PIPE if stdin_text is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        start_new_session=True,
    )
    try:
        out, err = proc.communicate(input=stdin_text, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass
        out, err = proc.communicate()
        raise SubprocessTimeout(argv, timeout_s, out, err)
    return proc.returncode, out, err


def interpreter_for(script):
    script = str(script)
    if script.endswith(".py"):
        return [sys.executable, script]
    if script.endswith(".sh"):
        return ["bash", script]
    return [script]


def run_plugin_script(rel_path, args, cwd, timeout_s=DEFAULT_TIMEOUT_S, extra_env=None):
    """Run a script shipped in this plugin (path relative to the plugin root) with the matching
    interpreter. Returns (rc, stdout, stderr)."""
    script = (PLUGIN_ROOT / rel_path).resolve()
    if PLUGIN_ROOT not in script.parents:
        raise ValueError("script outside the plugin root: %s" % rel_path)
    if not script.is_file():
        raise FileNotFoundError(str(script))
    return run(interpreter_for(script) + [str(a) for a in args], cwd, timeout_s, extra_env)


# --------------------------------------------------------------------------- #
# allocator (JSON envelope contract)
# --------------------------------------------------------------------------- #
class AllocatorEnvelopeError(Exception):
    pass


def parse_allocator_envelope(rc, stdout, stderr):
    """Parse the allocator's `--format json` output into its envelope
    {"ok": bool, "rc": int, "error": {"code","message"} | null, "fields": {...}}.

    The envelope is the whole stdout, or failing that the LAST stdout line that is a JSON object
    carrying "ok" (tolerates stray lines printed before it). Raises AllocatorEnvelopeError when no
    well-formed envelope is present."""
    text = (stdout or "").strip()
    candidates = [text] + [ln.strip() for ln in reversed(text.splitlines())]
    for cand in candidates:
        if not cand.startswith("{"):
            continue
        try:
            obj = json.loads(cand)
        except ValueError:
            continue
        if isinstance(obj, dict) and "ok" in obj:
            if not isinstance(obj.get("ok"), bool):
                raise AllocatorEnvelopeError("envelope 'ok' is not a boolean")
            fields = obj.get("fields")
            if fields is None:
                obj["fields"] = {}
            elif not isinstance(fields, dict):
                raise AllocatorEnvelopeError("envelope 'fields' is not an object")
            err = obj.get("error")
            if not obj["ok"]:
                if not isinstance(err, dict) or not isinstance(err.get("code"), str):
                    raise AllocatorEnvelopeError("failed envelope carries no error.code")
            obj.setdefault("rc", rc)
            return obj
    raise AllocatorEnvelopeError("no JSON envelope on stdout (rc=%s)" % rc)


def run_allocator(verb, args, cwd, timeout_s=DEFAULT_TIMEOUT_S, script=None):
    """Run `allocator.py <verb> <args> --format json` and return its parsed envelope.

    A failed envelope (ok=false) raises ToolError with the allocator's own error code, so its remedy
    comes from the merged table in errors.py. Anything else unexpected is ALLOCATOR_OUTPUT_INVALID
    or SUBPROCESS_TIMEOUT - never a guessed success."""
    from .errors import ToolError  # local import keeps cli.py importable on its own

    argv = interpreter_for(script or ALLOCATOR) + [verb] + [str(a) for a in args] + ["--format", "json"]
    try:
        rc, out, err = run(argv, cwd, timeout_s)
    except SubprocessTimeout as exc:
        raise ToolError("SUBPROCESS_TIMEOUT", "allocator %s exceeded %ss" % (verb, timeout_s),
                        {"verb": verb, "stdout": tail(exc.stdout), "stderr": tail(exc.stderr)})
    try:
        env = parse_allocator_envelope(rc, out, err)
    except AllocatorEnvelopeError as exc:
        raise ToolError("ALLOCATOR_OUTPUT_INVALID", "allocator %s: %s" % (verb, exc),
                        {"verb": verb, "rc": rc, "stdout": tail(out), "stderr": tail(err)})
    if not env["ok"]:
        e = env["error"]
        raise ToolError(e["code"], str(e.get("message") or e["code"]),
                        {"verb": verb, "rc": env.get("rc", rc), "fields": env["fields"], "stderr": tail(err)})
    return env
