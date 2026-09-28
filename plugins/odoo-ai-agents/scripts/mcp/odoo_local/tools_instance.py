"""tools_instance.py - instance tools (build / serve / status) and job waiting.

  instance_build  starts `55-instance-ops.sh <init|update|test>` DETACHED through jobs.start, with
                  every connection fact read from the lease row (never from the agent), and returns
                  at once. The build log path is chosen here and handed to the script through
                  ODOO_AI_OPS_LOG_PATH, so it is known before the script prints anything.
  job_wait        waits (bounded) for the job's PROCESS to exit - the build's exit code is
                  authoritative - then asks `55-instance-ops.sh wait-log --timeout 0` for the log
                  verdict. No Odoo log marker is parsed here: that logic stays in the script.
  instance_serve  runs `50-instance-spinup.sh apply` synchronously (bounded); bind/resume of the
                  launched pid onto the lease happen inside that script. Its KEY=value stdout facts
                  are the result.
  instance_status `50-instance-spinup.sh check` + the allocator's shared/parked lookups; when the
                  declared server is up, its declared port (the same catalog row the check read,
                  via instances_io.select_instance) is reported as http_port/url.

Which interpreter serves a lease: the lease row, never the catalog's first row for the series. The
server passes the lease's own catalog profile (lease.profile) as --profile, and
50-instance-spinup.sh takes python / odoo_root / db_host / db_user / db_port from the --alloc-token
lease row when it records them - exactly the facts instance_build hands 55-instance-ops.sh - so a
series declaring several profiles is served with the venv it was built with.

Port option names: derived from the lease's series, never asked of the agent. The main HTTP port's
name is scripts/lib/odoo_port_keys.sh (the one copy, sourced by both 50-instance-spinup.sh for the
odoo.conf key and 55-instance-ops.sh for the odoo-bin flag); the second (gevent/longpolling) port key
is `second_port_key` below. Both rules were read from each series' odoo/tools/config.py option dests
(xmlrpc_port -> http_port at 11.0; longpolling_port -> gevent_port at 16.0).

Build ports: instance_build hands 55-instance-ops.sh the lease's reserved port(s) (`_build_port_args`),
since a test build binds the main port on every series; a test build on a lease without a port is
refused (LEASE_HAS_NO_PORT) rather than left to bind Odoo's default.

Extra odoo-bin flags (instance_build extra_args) may not set anything the tool itself controls - the
database and its connection, the addons path, the config file and --save, the data dir, the module
ops, the stop-after-init switch, the test switches, a listening port, or the log destination:
`refused_extra_flag` below, which parses a short-option cluster the way optparse does (`-sdother`
is -s then -d). Odoo takes the LAST occurrence of a flag, so an extra `--database=other` would
silently retarget the build at another database.

Disclosure (instance_serve): serving by series hands back the shared lease's token and owner run
only when this call LAUNCHED the server or the lease is disclosed to this caller under lease_find's
rule (tools_lease module docstring); a parked lease anchored to another session is refused
(LEASE_NOT_ADOPTED) until lease_adopt re-anchors it - instance_serve takes no run id to check.

Build pid and the lease: the build pid is NOT bound onto the lease (`allocator.py bind`). A
`--stop-after-init` process exits within minutes, and a bound pid is read as the lease's SERVER: a
shared row is judged by that pid alone (it would turn condemnable the moment the build exits),
`park` would treat a finished build as a running server, and a later bind by instance_serve would
race it. The session anchor already protects the lease for as long as the session lives. The pid is
kept in the job record instead, and lease_release stops a still-running build job of that lease
before it drops the database.

ODOO_AI_OPS_SCRIPT (TEST-ONLY): absolute path of a stand-in for 55-instance-ops.sh, used for both
the build and wait-log. Never set it outside the test suite.
"""

import datetime
import os
import re
import signal
import time
import uuid

from . import cli, jobs, protocol, tools_lease
from .errors import ToolError
from .tools_lease import (HANDLE_SCHEMA, NO_RUN_ID, NULLABLE_FOUND_LEASE_SCHEMA, PROFILE_PROP, SERIES_PROP,
                          _obj)

OPS_SCRIPT_REL = "scripts/setup-steps/55-instance-ops.sh"
SPINUP_SCRIPT_REL = "scripts/setup-steps/50-instance-spinup.sh"
OPS_SCRIPT_ENV = "ODOO_AI_OPS_SCRIPT"  # test-only override, see module docstring
OPS_LOG_ENV = "ODOO_AI_OPS_LOG_PATH"   # read by 55-instance-ops.sh _open_log

WAIT_MAX_S = 540
WAIT_DEFAULT_S = 300
WAIT_POLL_S = 1.0
WAIT_LOG_TIMEOUT_S = 60
SERVE_TIMEOUT_S = 180
SERVE_POLL_S = 150   # SPINUP_TIMEOUT handed to the spin-up, inside SERVE_TIMEOUT_S
STATUS_TIMEOUT_S = 60
TAIL_LINES = 20
_TAIL_BYTES = 256 * 1024

_MODULE_RE = re.compile(r"^[A-Za-z0-9_]+$")
# Odoo's -i/-u/--load take a comma-separated MODULE list - a different fact from the addons_path
# separator (directories, owned by instances_io), so it carries its own name (the bash twin is
# SERVER_WIDE_MODULES_SEP in 50-instance-spinup.sh).
MODULE_LIST_SEP = ","

# The build script's own machine-readable summary keys (55-instance-ops.sh header).
_SUMMARY_KEYS = ("STATUS", "TEST_RESULT", "TEST_FAILED", "TEST_ERROR", "TEST_WARNING", "TEST_SKIPPED",
                 "JS_RUNS", "JS_SCOPE", "JS_FAILED_REPORTED", "JS_FAILED_TESTS", "MODULES_LOADED",
                 "TESTS_RUN", "TEST_TAGS_USED", "FINDINGS_PATH")
# The spin-up script's result facts (50-instance-spinup.sh header).
_SERVE_KEYS = ("SERVE_STATE", "SERVE_HTTP_PORT", "SERVE_URL", "SERVER_PID", "SERVE_RESUMED",
               "SERVED_ADDONS_PATH", "SERVED_ADDONS_SOURCE", "SERVED_SERVER_WIDE_MODULES", "LOG_PATH",
               "SHARED_LEASE_TOKEN", "SHARED_LEASE_ERROR")


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _ops_script():
    override = os.environ.get(OPS_SCRIPT_ENV)
    if override:
        return override
    return str(cli.PLUGIN_ROOT / OPS_SCRIPT_REL)


def _spinup_script():
    return str(cli.PLUGIN_ROOT / SPINUP_SCRIPT_REL)


def _kv_lines(text, keys):
    """{KEY: value} for `KEY=value` lines of `text` whose KEY is in `keys`; the LAST one wins."""
    out = {}
    for line in (text or "").splitlines():
        key, sep, value = line.partition("=")
        if sep and key in keys:
            out[key] = value
    return out


def _read_tail(path, max_bytes=_TAIL_BYTES):
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - max_bytes))
            return fh.read().decode("utf-8", "replace")
    except OSError:
        return ""


def _tail_lines(text, n=TAIL_LINES):
    return [ln for ln in (text or "").splitlines() if ln.strip()][-n:]


def _int_or_none(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _logs_dir():
    return os.path.join(cli.load_lib("paths")._home(), "logs")


def _cwd(args):
    return tools_lease._cwd(args)


def _require_row(token):
    return tools_lease._require_row(token)


def _lease_field(lease, field, token):
    value = lease.get(field)
    if not value:
        if field == "venv_python":
            raise ToolError("VENV_MISSING", "lease %s records no venv python (series %s%s declares none)" % (
                token[:8], lease.get("series") or "?",
                (" profile %s" % lease["profile"]) if lease.get("profile") else ""),
                {"token_prefix": token[:8], "series": lease.get("series") or "",
                 "profile": lease.get("profile") or ""})
        raise ToolError("LEASE_INCOMPLETE", "lease %s (mode %s) records no %s" % (
            token[:8], lease.get("mode") or "?", field),
            {"token_prefix": token[:8], "field": field, "mode": lease.get("mode") or ""})
    return value


# Long options instance_build controls itself, or that would move what it reads (odoo-bin option
# names; `_` and `-` are one spelling here, as Odoo spells some with `_`): the database and its
# connection (db_replica_* from 19.0 routes read cursors to another server), the template a
# database is created from, the addons path, the config file and -s/--save (which WRITES the
# resolved options into it), the data dir, the module ops, the stop-after-init and test switches,
# the listening ports, and the log destination (--logfile / --syslog move the log the tool hands
# back as log_path and job_wait reads its verdict from; --pidfile writes a file for the tool's
# own process). Odoo's optparse also accepts any unambiguous PREFIX of a long option, so a token
# naming a prefix of one of these is refused too (a bare `--` - "end of options" - is a prefix of
# every name, and would turn the tool's own flags that follow into positional arguments).
TOOL_CONTROLLED_LONG = ("database", "db-filter", "db-host", "db-port", "db-user", "db-password",
                        "db-template", "db-replica-host", "db-replica-port",
                        "addons-path", "config", "save", "data-dir", "init", "update",
                        "stop-after-init", "test-enable", "test-tags", "test-file", "http-port",
                        "xmlrpc-port", "gevent-port", "longpolling-port", "logfile", "syslog",
                        "pidfile")

# odoo-bin's SHORT options, read from each series' odoo/tools/config.py (openerp/ on 8.0/9.0),
# 8.0 through 20.0: char -> the long option it abbreviates. Every one takes a value except the
# store_true flags in _SHORT_FLAGS (-s/--save up to 19.0, optparse's own -h/--help). -p exists from
# 11.0; -t is --timezone on 8.0, absent 9.0-16.0, and --test-tags from 17.0 (`_short_long`).
_SHORT_LONG = {"c": "config", "s": "save", "i": "init", "u": "update", "P": "import-partial",
               "D": "data-dir", "p": "http-port", "d": "database", "r": "db-user",
               "w": "db-password", "l": "language", "h": "help"}
_SHORT_FLAGS = ("s", "h")


def _short_long(char, series):
    """The long option short option -`char` stands for on `series` (None when it has none there).
    An unknown series gets the newest meaning of -t, so the refusal errs on the safe side."""
    if char != "t":
        return _SHORT_LONG.get(char)
    major = _series_major(series)
    if major is None or major >= 17:
        return "test-tags"
    return "timezone" if major <= 8 else None


def refused_extra_flag(token, series=None):
    """The tool-controlled option `token` would set on `series` (e.g. '--database', '-d'), or None
    when it is free. A short-option token is parsed the way optparse parses it: `-sdother` is -s
    then -d with value `other`, because each character is its own option until one that takes a
    value consumes the rest of the token (or the next argument) - so every option character before
    the first value-taking one is checked, not only the first."""
    if token.startswith("--"):
        name = token[2:].split("=", 1)[0].replace("_", "-")
        for flag in TOOL_CONTROLLED_LONG:
            if flag.startswith(name):
                return "--" + flag
        return None
    if not token.startswith("-") or len(token) < 2:
        return None  # a value, or optparse's positional "-"
    for char in token[1:]:
        long_name = _short_long(char, series)
        if long_name in TOOL_CONTROLLED_LONG:
            return "-" + char
        if long_name is not None and char not in _SHORT_FLAGS:
            return None  # this option takes a value: the rest of the token is that value
    return None


def _series_major(series):
    head = (series or "").split(".", 1)[0]
    return int(head) if head.isdigit() else None


def second_port_key(series):
    """odoo.conf key of the second listening port: longpolling_port before 16.0, gevent_port from
    16.0 on (odoo/tools/config.py option dests). None when the series is not X.Y."""
    major = _series_major(series)
    if major is None:
        return None
    return "gevent_port" if major >= 16 else "longpolling_port"


# --------------------------------------------------------------------------- #
# instance_build
# --------------------------------------------------------------------------- #
def _build_port_args(op, lease, token):
    """`--http-port <leased port>` for 55-instance-ops.sh, which spells it with the series' own flag.

    op test needs a reserved port: Odoo spawns its HTTP server whenever test mode is on, even with
    --stop-after-init (odoo/service/server.py, every series), so a test build without the lease's
    port binds the default 8069 and collides with whatever already listens there. init/update get
    the port too when the lease reserved one. A second reserved port goes with its series key
    (second_port_key), so a prefork build (--workers in extra_args) does not bind the default
    gevent/longpolling port either."""
    ports = lease.get("ports") or []
    if not ports:
        if op == "test":
            raise ToolError("LEASE_HAS_NO_PORT", "lease %s reserved no port, and a test build binds one "
                            "(Odoo spawns its HTTP server in test mode)" % token[:8],
                            {"token_prefix": token[:8], "op": op})
        return []
    if _series_major(lease.get("series")) is None:
        raise ToolError("LEASE_INCOMPLETE", "lease %s records no X.Y series, so the flag for its port "
                        "cannot be derived" % token[:8], {"token_prefix": token[:8], "field": "series"})
    out = ["--http-port", str(ports[0])]
    if len(ports) > 1:
        out += ["--gevent-port", str(ports[1]), "--gevent-port-key", second_port_key(lease["series"])]
    return out


def _build(args, ctx):
    op, token = args["op"], args["lease_token"]
    cwd = _cwd(args)
    modules = args["modules"]
    for m in modules:
        if not _MODULE_RE.match(m):
            raise ToolError("INVALID_ARGUMENTS", "arguments.modules: %r is not a module name" % m)
    if op != "test":
        for key in ("test_tags", "test_mode", "log_mode"):
            if key in args:
                raise ToolError("INVALID_ARGUMENTS", "arguments.%s: only valid with op test" % key)
    extra = args.get("extra_args") or []
    for a in extra:
        if not a or any(c.isspace() for c in a):
            raise ToolError("INVALID_ARGUMENTS",
                            "arguments.extra_args: %r - one token per item, no whitespace (use --flag=value)" % a)
    row = _require_row(token)
    lease = tools_lease.lease_from_row(row)
    for a in extra:
        refused = refused_extra_flag(a, lease.get("series"))
        if refused:
            raise ToolError("INVALID_ARGUMENTS",
                            "arguments.extra_args: %r sets %s, which instance_build controls itself "
                            "(database, connection, addons path, config file and --save, data dir, "
                            "module ops, test switches, ports, log destination) - drop it; use the "
                            "tool's own arguments or another lease" % (a, refused),
                            {"flag": refused, "token": a})
    db = _lease_field(lease, "db_name", token)
    python = _lease_field(lease, "venv_python", token)
    addons = _lease_field(lease, "addons_path", token)

    argv = [op, "--db", db, "--python", python, "--addons", tools_lease.join_addons(addons),
            "--modules", MODULE_LIST_SEP.join(modules)]
    if lease.get("series"):
        argv += ["--version", lease["series"]]
    for flag, key in (("--db-host", "db_host"), ("--db-user", "db_user"), ("--db-port", "db_port")):
        if lease.get(key):
            argv += [flag, lease[key]]
    argv += _build_port_args(op, lease, token)
    if op == "test":
        if args.get("test_tags"):
            argv += ["--test-tags", args["test_tags"]]
        if args.get("test_mode"):
            argv += ["--mode", args["test_mode"]]
        if args.get("log_mode"):
            argv += ["--log-mode", args["log_mode"]]
    if extra:
        argv += ["--extra", " ".join(extra)]

    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = os.path.join(_logs_dir(), "%s-%s_%s" % (db, stamp, uuid.uuid4().hex[:4]))
    log_path, output_path = base + ".log", base + ".ops.log"
    meta = {"kind": "build", "op": op, "lease_token": token, "log_path": log_path,
            "output_path": output_path, "db_name": db, "series": lease.get("series") or "",
            "modules": list(modules)}
    try:
        rec = jobs.start(cli.interpreter_for(_ops_script()) + argv, cwd,
                         env={OPS_LOG_ENV: log_path}, log_path_hint=output_path, meta=meta)
    except (OSError, ValueError) as exc:
        raise ToolError("BUILD_START_FAILED", "cannot start %s: %s" % (op, exc), {"op": op})
    return {"job_id": rec["job_id"], "pid": rec["pid"], "op": op, "log_path": log_path,
            "output_path": output_path, "lease_token": token,
            "instance_handle": tools_lease.instance_handle(lease, log_path=log_path)}


# --------------------------------------------------------------------------- #
# job_wait
# --------------------------------------------------------------------------- #
def _wait_log_verdict(log_path, cwd):
    """One non-blocking pass of `55-instance-ops.sh wait-log` over log_path -> {KEY: value}."""
    if not log_path or not os.path.isfile(log_path):
        return {}
    try:
        _rc, out, _err = cli.run(cli.interpreter_for(_ops_script()) +
                                 ["wait-log", "--log", log_path, "--timeout", "0", "--interval", "1"],
                                 cwd, WAIT_LOG_TIMEOUT_S)
    except cli.SubprocessTimeout:
        return {}
    return _kv_lines(out, ("BUILD_RESULT", "BUILD_MARKER", "BUILD_PROGRESS", "TEST_RESULT"))


def _decide(state, exit_code, verdict, test_result):
    """The job result from process state + the script's own verdicts (never from log parsing)."""
    if state == "running":
        return "timeout"
    if state == "lost":
        return "lost"
    build = verdict.get("BUILD_RESULT") or ""
    if test_result == "failed" or build == "failure" or exit_code != 0:
        return "failure"
    if test_result == "inconclusive" or build == "inconclusive":
        return "inconclusive"
    if build == "success" and test_result in ("", "passed"):
        return "success"
    return "inconclusive"  # exit 0 but no terminal marker: never certified as a pass


def _job_wait(args, ctx):
    job_id = args["job_id"]
    rec = jobs.read_record(job_id)
    if rec is None:
        raise ToolError("JOB_NOT_FOUND", "no job %r on this machine" % job_id, {"job_id": job_id})
    deadline = time.monotonic() + args["timeout_s"]
    cancel = protocol.cancel_event()  # set when the client cancels this call or disconnects
    while True:
        st = jobs.status(job_id)
        if st["state"] != "running" or time.monotonic() >= deadline or cancel.is_set():
            break
        cancel.wait(min(WAIT_POLL_S, max(0.0, deadline - time.monotonic())))
    meta = rec.get("meta") or {}
    log_path = meta.get("log_path") or rec.get("log_path")
    output_path = meta.get("output_path") or rec.get("log_path")
    cwd = rec.get("cwd") if os.path.isdir(rec.get("cwd") or "") else os.getcwd()
    verdict = _wait_log_verdict(log_path, cwd)
    output = _read_tail(output_path)
    summary = _kv_lines(output, _SUMMARY_KEYS)
    test_result = summary.get("TEST_RESULT") or verdict.get("TEST_RESULT") or ""
    result = _decide(st["state"], st.get("exit_code"), verdict, test_result)
    return {
        "job_id": job_id,
        "result": result,
        "state": st["state"],
        "exit_code": st.get("exit_code"),
        "op": meta.get("op") or "",
        "marker": verdict.get("BUILD_MARKER") or "",
        "progress": verdict.get("BUILD_PROGRESS") or "",
        "test_result": test_result or None,
        "summary": summary,
        "log_path": log_path,
        "output_path": output_path,
        "log_tail": _tail_lines(_read_tail(log_path, 64 * 1024)),
        "output_tail": _tail_lines(output),
        "detail": st.get("detail") or "",
    }


# --------------------------------------------------------------------------- #
# instance_serve
# --------------------------------------------------------------------------- #
def _serve(args, ctx):
    token, series = args.get("lease_token"), args.get("series")
    if bool(token) == bool(series):
        raise ToolError("INVALID_ARGUMENTS",
                        "arguments: pass exactly one of lease_token (serve your lease) or series "
                        "(attach to / start the shared declared instance)")
    cwd = _cwd(args)
    extra_env = {"SPINUP_TIMEOUT": os.environ.get("SPINUP_TIMEOUT") or str(SERVE_POLL_S)}
    argv = ["apply"]
    lease = None
    if token:
        row = _require_row(token)
        lease = tools_lease.lease_from_row(row)
        _refuse_unadopted_park(row, token, cwd)
        argv += ["--version", lease["series"]]
        # The lease's own profile picks the catalog row: the first row of a multi-profile series is
        # another venv. A different explicit profile would serve a build with the wrong venv.
        profile = lease.get("profile") or ""
        if args.get("profile") and profile and args["profile"] != profile:
            raise ToolError("PROFILE_MISMATCH", "lease %s was acquired for profile %r, not %r" % (
                token[:8], profile, args["profile"]),
                {"token_prefix": token[:8], "lease_profile": profile, "profile": args["profile"]})
        profile = profile or args.get("profile") or ""
        if profile:
            argv += ["--profile", profile]
        if lease["mode"] == "shared":
            run_id = args.get("run_id") or lease.get("run_id")
            if run_id:
                extra_env["INST_RUN_ID"] = run_id
        else:
            _lease_field(lease, "venv_python", token)
            ports = lease.get("ports") or []
            if not ports:
                raise ToolError("LEASE_HAS_NO_PORT", "lease %s reserved no port" % token[:8],
                                {"token_prefix": token[:8]})
            argv += ["--exclusive", "--db-name", lease["db_name"], "--http-port", str(ports[0]),
                     "--alloc-token", token]
            if len(ports) > 1:
                key = second_port_key(lease["series"])
                if key is None:
                    raise ToolError("LEASE_INCOMPLETE", "lease %s records no X.Y series, so its second "
                                    "port's conf key cannot be derived" % token[:8],
                                    {"token_prefix": token[:8], "field": "series"})
                argv += ["--gevent-port", str(ports[1]), "--gevent-port-key", key]
    else:
        argv += ["--version", series]
        if args.get("profile"):
            argv += ["--profile", args["profile"]]
        if args.get("run_id"):
            extra_env["INST_RUN_ID"] = args["run_id"]
    if args.get("load_modules"):
        argv += ["--load", MODULE_LIST_SEP.join(args["load_modules"])]
    addons = args.get("addons_path")
    if addons:
        argv += ["--addons-path", tools_lease.join_addons(addons if isinstance(addons, list) else tools_lease._addons_list(addons))]
    try:
        rc, out, err = cli.run(cli.interpreter_for(_spinup_script()) + argv, cwd, SERVE_TIMEOUT_S, extra_env)
    except cli.SubprocessTimeout as exc:
        raise ToolError("SUBPROCESS_TIMEOUT", "instance_serve exceeded %ss" % SERVE_TIMEOUT_S,
                        {"stdout": cli.tail(exc.stdout), "stderr": cli.tail(exc.stderr)})
    facts = _kv_lines(out, _SERVE_KEYS)
    if rc != 0 or "SERVE_STATE" not in facts:
        diagnostics = {"rc": rc, "stdout": cli.tail(out), "stderr": cli.tail(err)}
        if series:
            _raise_if_undeclared(series, args.get("profile"), cwd, diagnostics)
        raise ToolError("SERVE_FAILED", "50-instance-spinup.sh apply exited %s" % rc, diagnostics)
    lease_token = token or facts.get("SHARED_LEASE_TOKEN") or None
    row = None
    if lease_token:  # re-read: serve may have resumed/bound the row
        row = tools_lease.read_row(lease_token)
        if row is not None:
            lease = tools_lease.lease_from_row(row)
    if series and lease_token and not _obtained_shared(facts, row, args.get("run_id") or "", cwd):
        # Attaching to a render server another run registered is READING it, not obtaining it:
        # its token + owner run id are everything lease_release needs to stop it under every
        # other reader. The URL, port and served facts are all a reader needs.
        lease_token = None
        if lease is not None:
            lease = dict(lease, token=None, run_id="")
    http_port = _int_or_none(facts.get("SERVE_HTTP_PORT"))
    server_pid = _int_or_none(facts.get("SERVER_PID"))
    if token and lease is not None and lease.get("mode") != "shared":
        server_pid = _verified_lease_server(token, row, facts, server_pid, out, err)
    served = tools_lease._addons_list(facts.get("SERVED_ADDONS_PATH"))
    handle_src = dict(lease or {})
    if not handle_src:
        handle_src = {"token": lease_token, "addons_path": served}
    handle = tools_lease.instance_handle(handle_src, log_path=facts.get("LOG_PATH") or None,
                                         server_pid=server_pid, http_port=http_port)
    handle["addons_path"] = tools_lease.join_addons(served) if served else handle["addons_path"]
    return {
        "state": facts.get("SERVE_STATE"),
        "url": facts.get("SERVE_URL") or "",
        "http_port": http_port,
        "server_pid": server_pid,
        "resumed": facts.get("SERVE_RESUMED") == "1",
        "served_addons_path": served,
        "served_addons_source": facts.get("SERVED_ADDONS_SOURCE") or "",
        "served_server_wide_modules": [m for m in (facts.get("SERVED_SERVER_WIDE_MODULES") or "").split(",") if m],
        "log_path": facts.get("LOG_PATH") or None,
        "lease_token": lease_token,
        "shared_lease_error": facts.get("SHARED_LEASE_ERROR") or None,
        "instance_handle": handle,
    }


def _refuse_unadopted_park(row, token, cwd):
    """A PARKED lease is resumed only from the session it is anchored to: serving it re-anchors it
    onto whoever serves it, so a parked lease recorded by another session must be lease_adopt-ed
    first - which checks the owner run (instance_serve takes no run id). The owner's resume path
    is lease_find(parked, run_id) -> lease_adopt when it came from an earlier session ->
    instance_serve."""
    if row.get("parked_at") is None and ((row.get("verdict") or {}).get("state") != "parked"):
        return
    if token in tools_lease.my_tokens(cwd):
        return
    raise ToolError("LEASE_NOT_ADOPTED",
                    "lease %s is parked by another session; it was not served" % token[:8],
                    {"token_prefix": token[:8]})


def _obtained_shared(facts, row, caller_run, cwd):
    """True when this instance_serve(series) call may hand back the shared lease's token and owner
    run: it LAUNCHED the server (and so registered the lease), or the lease is disclosed to this
    caller under lease_find's rule (tools_lease.discloses_to_this_session)."""
    if facts.get("SERVE_STATE") == "launched":
        return True
    if row is None:
        return False
    return tools_lease.discloses_to_this_session(row, caller_run, tools_lease.my_tokens(cwd))


def _raise_if_undeclared(series, profile, cwd, diagnostics):
    """A failed instance_serve(series) whose cause is the catalog itself - no catalog at all, or no
    row for that series/profile - is raised by that name (NO_INSTANCE_CATALOG / NO_INSTANCE), read
    from the same catalog the spin-up resolves (tools_catalog), never a bare SERVE_FAILED."""
    from . import tools_catalog
    io = cli.load_lib("instances_io")
    try:
        path = tools_catalog._resolve_catalog_path(cwd)
        items, exists = tools_catalog._load(io, path)
    except ToolError:
        return
    if not exists or not items:
        raise ToolError("NO_INSTANCE_CATALOG", "no instance catalog declares any instance (%s)" % path,
                        dict(diagnostics, catalog_path=path, series=series))
    item, _defaulted = io.select_instance(items, series, profile=profile or None)
    if item is None:
        raise ToolError("NO_INSTANCE", "the catalog declares no instance for series %s%s" % (
            series, (" profile %s" % profile) if profile else ""),
            dict(diagnostics, catalog_path=path, series=series, profile=profile or ""))


def _stop_group(pid):
    """SIGTERM then SIGKILL the process group a failed serve launched (pgid == pid: setsid)."""
    for sig, wait_s in ((signal.SIGTERM, 10.0), (signal.SIGKILL, 2.0)):
        try:
            os.killpg(pid, sig)
        except OSError:
            return
        deadline = time.monotonic() + wait_s
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except OSError:
                return
            time.sleep(0.2)


def _verified_lease_server(token, row, facts, launched_pid, out, err):
    """The pid of the server now bound to lease `token`, proven from the registry row - never from
    the script's word alone. A serve that reports success while the lease has no live bound server
    (an attach to a port some other process answers, a bind/resume that did not land, a parked row
    left parked) is SERVE_FAILED; a server this call launched that the lease does not own is stopped
    first, so nothing is left running outside every lease."""
    bound = tools_lease._served_pid(row) if row is not None else None
    if bound is not None and (launched_pid is None or bound == launched_pid):
        return bound
    if launched_pid is not None and launched_pid != bound:
        _stop_group(launched_pid)
    state = ((row or {}).get("verdict") or {}).get("state") or ("gone" if row is None else "")
    raise ToolError("SERVE_FAILED",
                    "50-instance-spinup.sh reported %s but no live server is bound to lease %s (lease "
                    "state %s)%s" % (facts.get("SERVE_STATE"), token[:8], state,
                                     "; the server it launched was stopped" if launched_pid else ""),
                    {"serve_state": facts.get("SERVE_STATE"), "lease_state": state,
                     "reported_pid": launched_pid, "bound_pid": bound,
                     "stdout": cli.tail(out), "stderr": cli.tail(err)})


# --------------------------------------------------------------------------- #
# instance_status
# --------------------------------------------------------------------------- #
def _declared_port(series, profile, cwd):
    """The declared http_port of the catalog row `50-instance-spinup.sh check` probes (the same
    instances_io.select_instance pick), or None when no row is declared."""
    from . import tools_catalog
    io = cli.load_lib("instances_io")
    try:
        items, _exists = tools_catalog._load(io, tools_catalog._resolve_catalog_path(cwd))
    except ToolError:
        return None
    item, _defaulted = io.select_instance(items, series, profile=profile or None)
    if item is None:
        return None
    return _int_or_none(item.get("http_port", io.DEFAULT_HTTP_PORT))


def _status(args, ctx):
    cwd = _cwd(args)
    argv = ["check", "--version", args["series"]]
    if args.get("profile"):
        argv += ["--profile", args["profile"]]
    try:
        rc, _out, _err = cli.run(cli.interpreter_for(_spinup_script()) + argv, cwd, STATUS_TIMEOUT_S)
    except cli.SubprocessTimeout:
        rc = None
    found = {}
    for state in ("shared", "parked"):
        query = {"series": args["series"], "state": state, "cwd": cwd}
        if args.get("run_id"):
            query["run_id"] = args["run_id"]
        res = tools_lease._find(query, ctx)
        found[state] = res["lease"] if res["found"] else None
    up = rc == 0
    port = _declared_port(args["series"], args.get("profile"), cwd) if up else None
    return {"series": args["series"], "up": up, "http_port": port,
            "url": tools_lease.serve_url(port) if port is not None else None,
            "shared_lease": found["shared"], "parked_lease": found["parked"]}


# --------------------------------------------------------------------------- #
# registration
# --------------------------------------------------------------------------- #
_CWD_PROP = {"type": "string", "minLength": 1,
             "description": "Absolute path of your working tree (the process cwd for the script). "
                            "Omit to use the server's working directory."}
_ADDONS_PROP = {"type": ["string", "array"], "items": {"type": "string"},
                "description": "Addons directories to SERVE (absolute; a list or one comma-joined "
                               "string). Omit: the lease's addons_path, else the catalog's."}

JOB_WAIT_OUTPUT = _obj({
    "job_id": {"type": "string"},
    "result": {"type": "string", "enum": ["success", "failure", "inconclusive", "timeout", "lost"]},
    "state": {"type": "string"},
    "exit_code": {"type": ["integer", "null"]},
    "op": {"type": "string"},
    "marker": {"type": "string"},
    "progress": {"type": "string"},
    "test_result": {"type": ["string", "null"]},
    "summary": {"type": "object"},
    "log_path": {"type": ["string", "null"]},
    "output_path": {"type": ["string", "null"]},
    "log_tail": {"type": "array", "items": {"type": "string"}},
    "output_tail": {"type": "array", "items": {"type": "string"}},
    "detail": {"type": "string"},
}, ["job_id", "result", "state", "exit_code", "op", "marker", "progress", "test_result", "summary",
    "log_path", "output_path", "log_tail", "output_tail", "detail"])


def register(registry, ctx):
    registry.add(
        "instance_build",
        "Start an Odoo build on a lease you hold or were handed: op init (-i, install modules into the "
        "lease's database - creating it on first use), update (-u), or test (install/update + run the "
        "tests). Database, venv python, addons path, Postgres coordinates and listening port(s) are "
        "read FROM THE LEASE - never pass them; the build binds the lease's reserved port. op test "
        "needs a lease with a port (lease_acquire ports 1): a test build always starts Odoo's HTTP "
        "server, so on a lease without one it is refused with LEASE_HAS_NO_PORT. Returns within seconds with job_id; the build runs in the background and "
        "survives this server restarting. Then call job_wait(job_id) until its result is not timeout. "
        "Version-specific Odoo flags go in extra_args, one token per item (--flag=value form), resolved "
        "for the lease's series with Odoo Semantic cli_help - never guessed; a flag the tool sets itself "
        "or that would move what it reads (database / db connection, addons path, config and --save, "
        "data dir, -i/-u, stop-after-init, test switches, any port, --logfile/--syslog/--pidfile) is "
        "refused with INVALID_ARGUMENTS naming it - short flags are read the way Odoo reads them, so "
        "a combined -sd... is refused for its -d. VENV_MISSING = the lease has "
        "no venv python: follow the remedy. Install en_US together "
        "with any other language you load. For op test pass test_tags to select whose tests run "
        "(omitted = every loaded module's tests) and test_mode reuse when the modules are already "
        "installed. log_path is the Odoo log to read for diagnosis; instance_handle carries it for "
        "forwarding.",
        _obj({
            "lease_token": {"type": "string", "minLength": 8,
                            "description": "Full token of the lease to build on (lease.token or "
                                           "INSTANCE_HANDLE.lease_token)."},
            "op": {"type": "string", "enum": ["init", "update", "test"],
                   "description": "init (-i) | update (-u) | test (-i/-u plus --test-enable)."},
            "modules": {"type": "array", "minItems": 1, "items": {"type": "string", "minLength": 1},
                        "description": "Technical module names to install/update (test: the modules "
                                       "whose registry is built)."},
            "extra_args": {"type": "array", "items": {"type": "string"},
                           "description": "Extra odoo-bin flags for this series, one token each, e.g. "
                                          "[\"--load=base,web\", \"--without-demo=all\"], resolved via "
                                          "Odoo Semantic cli_help. Never a flag the tool controls (-d/"
                                          "--database, --db-filter, -r/--db_user, -w/--db_password, "
                                          "--db_host/--db_port/--db-template/--db_replica_*, "
                                          "--addons-path, -c/--config, -s/--save, -D/--data-dir, -i/-u, "
                                          "--stop-after-init, --test-enable/--test-tags/--test-file "
                                          "(and -t where it means --test-tags), any port flag, "
                                          "--logfile/--syslog/--pidfile), alone or inside a combined "
                                          "short-flag token: refused."},
            "test_tags": {"type": "string", "minLength": 1,
                          "description": "op test only: the --test-tags selection (e.g. /my_module)."},
            "test_mode": {"type": "string", "enum": ["fresh", "reuse"],
                          "description": "op test only: fresh (default, -i) for a new database; reuse "
                                         "(-u) when the modules are already installed."},
            "log_mode": {"type": "string", "enum": ["info", "debug", "sql"],
                         "description": "op test only: log verbosity; omit for info."},
            "cwd": _CWD_PROP,
        }, ["lease_token", "op", "modules"]),
        _obj({
            "job_id": {"type": "string"},
            "pid": {"type": "integer"},
            "op": {"type": "string"},
            "log_path": {"type": "string"},
            "output_path": {"type": "string"},
            "lease_token": {"type": "string"},
            "instance_handle": HANDLE_SCHEMA,
        }, ["job_id", "pid", "op", "log_path", "output_path", "lease_token", "instance_handle"]),
        _build, title="Start an Odoo build/test job", destructive=True,
    )
    registry.add(
        "job_wait",
        "Wait up to timeout_s for a job started by instance_build, then report it. result: success "
        "(passed/installed), failure, inconclusive (finished but NOT a pass - e.g. no test proven to "
        "run; read the log), lost (the job process vanished without an exit record), or timeout "
        "(still running). While result is timeout, call job_wait again with the same job_id - never "
        "end your turn waiting on a build without a tool call. The process exit code is "
        "authoritative; marker/progress come from the build script's own log reading, and progress "
        "changing between two waits shows the build is advancing. For op test read test_result and "
        "summary (TEST_FAILED, TEST_ERROR, FINDINGS_PATH...). On failure read output_tail first (a "
        "refused preflight is reported there), then log_tail and log_path. Read-only.",
        _obj({
            "job_id": {"type": "string", "minLength": 1,
                      "description": "job_id returned by instance_build (valid across server restarts)."},
            "timeout_s": {"type": "integer", "minimum": 1, "maximum": WAIT_MAX_S, "default": WAIT_DEFAULT_S,
                          "description": "Seconds to wait before returning result timeout (1-540)."},
        }, ["job_id"]),
        JOB_WAIT_OUTPUT,
        _job_wait, title="Wait for an Odoo build/test job", read_only=True, long_running=True,
    )
    registry.add(
        "instance_serve",
        "Make an Odoo instance LISTEN and return its URL. Pass lease_token to serve your own leased "
        "database (it must have been built with instance_build first and have a reserved port: "
        "lease_acquire ports 1); a PARKED lease is resumed (resumed=true) - one parked by an earlier or "
        "other session is refused (LEASE_NOT_ADOPTED) until you lease_adopt it. Or pass series (no "
        "token) to attach to, or start, the shared declared instance. state launched = this call "
        "started it and registered the shared lease under your run_id (its token is returned). state "
        "attached = it was already running: you get url / http_port to read it, and lease_token is "
        "null unless the lease is your run's in this session. The shared server is multi-reader and "
        "needs no teardown from anyone: never lease_release or lease_park it when you finish (a "
        "release stops it under every reader; lease_gc reclaims it once its server is gone) - "
        "release it only when the user explicitly asks to stop that render server "
        "(shared_lease_error set = the server is up but NOT leased - tell the user). A series the catalog does not declare is NO_INSTANCE (no catalog at all: "
        "NO_INSTANCE_CATALOG). "
        "Blocks up to ~3 minutes until HTTP answers. A leased database is served with the lease's own "
        "venv, catalog profile and Postgres coordinates, and its odoo.conf port keys are derived from "
        "the lease's series - pass none of them. Success on a lease means a live server is verified "
        "bound to it; otherwise SERVE_FAILED (anything this call launched is stopped). Returns url, "
        "server_pid, the addons path actually served (verify it covers your module before trusting a "
        "result), and instance_handle to forward. A server on your own lease keeps running until you "
        "lease_park or lease_release that lease.",
        _obj({
            "lease_token": {"type": "string", "minLength": 8,
                            "description": "Full token of YOUR lease to serve. Exactly one of lease_token "
                                           "or series."},
            "series": dict(SERIES_PROP, description="Series (X.Y) of the shared declared instance to attach "
                                                    "to or start. Exactly one of lease_token or series."),
            "run_id": {"type": "string", "minLength": 1,
                       "description": "Your run id; stamps the shared lease's owner when serving by "
                                      "series starts the server, and decides whether an attach may "
                                      "return the lease token (only your own run's). " + NO_RUN_ID},
            "profile": dict(PROFILE_PROP, description="With series: the catalog profile to serve when the "
                                                      "series declares several; omit for the first/"
                                                      "unprofiled one. With lease_token: omit - the lease's "
                                                      "own profile is used (a different one is refused, "
                                                      "PROFILE_MISMATCH)."),
            "load_modules": {"type": "array", "items": {"type": "string", "minLength": 1},
                             "description": "Server-wide modules (Odoo --load); omit for Odoo's default."},
            "addons_path": _ADDONS_PROP,
            "cwd": _CWD_PROP,
        }),
        _obj({
            "state": {"type": "string", "enum": ["attached", "launched"]},
            "url": {"type": "string"},
            "http_port": {"type": ["integer", "null"]},
            "server_pid": {"type": ["integer", "null"]},
            "resumed": {"type": "boolean"},
            "served_addons_path": {"type": "array", "items": {"type": "string"}},
            "served_addons_source": {"type": "string"},
            "served_server_wide_modules": {"type": "array", "items": {"type": "string"}},
            "log_path": {"type": ["string", "null"]},
            "lease_token": {"type": ["string", "null"],
                            "description": "Your lease's token; with series, non-null only when this "
                                           "call launched the server or the shared lease is your "
                                           "run's in this session."},
            "shared_lease_error": {"type": ["string", "null"]},
            "instance_handle": HANDLE_SCHEMA,
        }, ["state", "url", "http_port", "server_pid", "resumed", "served_addons_path",
            "served_addons_source", "served_server_wide_modules", "log_path", "lease_token",
            "shared_lease_error", "instance_handle"]),
        _serve, title="Serve an Odoo instance", long_running=True, destructive=False,
    )
    registry.add(
        "instance_status",
        "Report whether the declared instance of a series is up (its declared port answers and is the "
        "same project) and, when up, its http_port and base url; plus the live shared lease and the "
        "resumable parked lease for that series, if any (each with served / http_port / url / "
        "session_alive, and a full token only when your run_id owns it and it is this session's or "
        "its session ended - same rule as lease_find). Call it before "
        "instance_serve(series) to see whether a server already runs and where, or to find a parked "
        "instance to resume. Read-only.",
        _obj({"series": SERIES_PROP, "profile": PROFILE_PROP, "cwd": _CWD_PROP,
              "run_id": {"type": "string", "minLength": 1,
                         "description": "Your run id: a lease your run owns (anchored to this session, "
                                        "or to one that has ended) is returned with its full "
                                        "token. " + NO_RUN_ID}}, ["series"]),
        _obj({"series": {"type": "string"}, "up": {"type": "boolean"},
              "http_port": {"type": ["integer", "null"],
                            "description": "Declared port of the up instance; null when not up."},
              "url": {"type": ["string", "null"],
                      "description": "Base URL of the up instance; null when not up."},
              "shared_lease": NULLABLE_FOUND_LEASE_SCHEMA, "parked_lease": NULLABLE_FOUND_LEASE_SCHEMA},
             ["series", "up", "http_port", "url", "shared_lease", "parked_lease"]),
        _status, title="Odoo instance status", read_only=True, long_running=True,
    )
