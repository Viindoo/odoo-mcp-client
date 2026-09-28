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

Checkout facts: every series-dependent option fact is READ from the lease's own Odoo checkout
(`lease_checkout`: the lease row's odoo_root, else the core repo on its addons_path), never keyed on
the series number - scripts/lib/odoo_source_facts.py reads the checkout's tools/config.py. The main
HTTP port's option is read the same way by 55-instance-ops.sh (odoo-bin flag) and
50-instance-spinup.sh (odoo.conf key) from the launcher's checkout; the second (gevent/longpolling)
port key, the demo default and the short options are read here (`_checkout_fact`). A fact the
checkout does not state is refused (ODOO_SOURCE_FACT_UNKNOWN), never guessed.

Build ports: instance_build hands 55-instance-ops.sh the lease's reserved port(s) (`_build_port_args`),
since a test build binds the main port on every series; a test build on a lease without a port is
refused (LEASE_HAS_NO_PORT) rather than left to bind Odoo's default.

Build facts the TOOL applies (instance_build), never the agent:
  server-wide modules  `--load` = the series' core default (read from the lease's checkout,
                       instances_io.effective_server_wide_modules -> odoo_source_facts) + the
                       catalog row's declared `server_wide_modules` (recorded on the lease at
                       acquire). --load REPLACES Odoo's default, so when modules are declared but the
                       core default cannot be read the build is refused (SERVER_WIDE_CORE_UNKNOWN)
                       rather than guessed; nothing declared -> no --load at all. instance_serve
                       gets the same set from 50-instance-spinup.sh, which reads the same lease row.
  languages            `--load-language=en_US[,...]` on every build (en_US always unioned), so every
                       build proves en_US and job_wait can report languages_loaded.
  demo                 `demo on|off`, required for op init, spelled from the checkout by
                       55-instance-ops.sh (_demo_args; both states stated explicitly, and the
                       operator's own Odoo config file is never read - the script hands odoo-bin
                       a generated one). op update takes NO demo argument (INVALID_ARGUMENTS):
                       demo data loads when a module is installed, and an update never adds it to
                       installed modules, so a value there would only be misrecorded on the
                       lease. op test takes NO demo argument either (any value is
                       INVALID_ARGUMENTS): it always runs with the series DEFAULT read from the
                       lease's checkout (odoo_source_facts.demo_opt_in) - `on` where demo loads by
                       default (no --with-demo declared), `off` where it is opt-in - so an
                       automation test runs exactly as the series runs its own tests, and the
                       resolved value is what is recorded and reported. Where the checkout makes
                       demo opt-in a test build never runs on a database that holds demo data
                       (TEST_DB_HAS_DEMO).
                       Demo and the active languages are facts of the DATABASE, read from the
                       database itself (tools_lease.database_facts -> odoo_db.py db-facts:
                       ir_module_module.demo of the installed modules, res_lang.active) by the demo
                       check and every INSTANCE_HANDLE, once per tool call. instance_build returns
                       no handle: at its start the database still holds its pre-build facts;
                       job_wait returns it once the build finished. Every gate that reads the
                       database runs AFTER the DATABASE_BUSY check (refuse_if_busy): while a job
                       runs on it, the database is a moment of that job. Only when it cannot be
                       read do the build records answer: every build that states demo records it on
                       the lease (`allocator.py record-build`, sticky), job_wait records the
                       languages a finished build proved loaded, and the records of every lease on
                       the same database are merged (tools_lease.database_built). facts_source
                       (handle) / diagnostics.facts_source (refusal) names who answered.

Extra odoo-bin flags (instance_build extra_args) may not set anything the tool itself controls - the
database and its connection, the addons path, the config file and --save, the data dir, the module
ops, the stop-after-init switch, the test switches, a listening port, the log destination, or the
build facts above (--load, --load-language, -l/--language, --with-demo, --without-demo):
`refused_extra_flag` below, which parses a short-option cluster the way optparse does (`-sdother`
is -s then -d), with the short options the lease's checkout declares. Odoo takes the LAST occurrence of a flag, so an extra `--database=other` would
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

import contextlib
import datetime
import fcntl
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
                 "TESTS_RUN", "TEST_TAGS_USED", "FINDINGS_PATH", "BUILD_SERVER_WIDE_MODULES",
                 "BUILD_LANGUAGES", "BUILD_DEMO", "BUILD_MODULES_LOADED", "EXPORT_COUNT")

DEMO_VALUES = ("on", "off")
# Odoo's source language: always active, unioned into every build's --load-language.
BASE_LANGUAGE = "en_US"
# res.lang codes: ll, ll_CC, lll_CC, es_419, sr@latin ...
_LANG_RE = re.compile(r"^[A-Za-z]{2,3}(?:_[A-Za-z0-9]{2,4})?(?:@[A-Za-z]+)?$")
# A language-install log line, every series 8.0-20.0 (ir_translation / ir_module / tools/translate):
# "module <m>: loading translation file <f> for language <code>", "module <m>: no translation for
# language <code>", "loading [base ]translation file ... for language <code>" - all emitted while
# Odoo loads that language's terms, i.e. only for an ACTIVE language.
_LANG_EVIDENCE_RE = re.compile(r"translation\b.*\bfor language "
                               r"([A-Za-z]{2,3}(?:_[A-Za-z0-9]{2,4})?(?:@[A-Za-z]+)?)\s*$")
# odoo/modules/loading.py from 12.0: a module whose demo data raised is installed WITHOUT it.
_DEMO_FAILED_RE = re.compile(r"Module ([A-Za-z0-9_]+) demo data failed to install, installed without "
                             r"demo data")
# The spin-up script's result facts (50-instance-spinup.sh header).
_SERVE_KEYS = ("SERVE_STATE", "SERVE_HTTP_PORT", "SERVE_URL", "SERVER_PID", "SERVE_RESUMED",
               "SERVED_ADDONS_PATH", "SERVED_ADDONS_SOURCE", "SERVED_SERVER_WIDE_MODULES", "LOG_PATH",
               "SHARED_LEASE_TOKEN", "SHARED_LEASE_ERROR", "SERVE_REFUSED")


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
                        "pidfile", "load", "load-language", "language", "with-demo", "without-demo")

# The build facts among them, and the tool input that sets each instead (named in the refusal).
_BUILD_FACT_OWNER = {
    "load": "server-wide modules are applied by the tool (core default + the catalog's "
            "server_wide_modules; change the catalog via /odoo-ai-agents:odoo-setup)",
    "load-language": "use the languages argument",
    "language": "use the languages argument to load a language (-l/--language only selects an "
                "i18n export/import file)",
    "with-demo": "use the demo argument",
    "without-demo": "use the demo argument",
}

def is_short_option_token(token):
    """True for a short-option token (`-d`, `-sdother`), whose meaning depends on the checkout."""
    return token.startswith("-") and not token.startswith("--") and len(token) >= 2


def refused_extra_flag(token, shorts=None):
    """The tool-controlled option `token` would set (e.g. '--database', '-d'), or None when it is
    free. `shorts` is the checkout's short-option map (odoo_source_facts.short_options: char ->
    {"long", "takes_value"}); a short-option token needs it (ValueError without). A short-option
    token is parsed the way optparse parses it: `-sdother` is -s then -d with value `other`,
    because each character is its own option until one that takes a value consumes the rest of the
    token (or the next argument) - so every option character before the first value-taking one is
    checked, not only the first. A character the checkout does not declare is skipped (odoo-bin
    rejects it itself)."""
    if token.startswith("--"):
        name = token[2:].split("=", 1)[0].replace("_", "-")
        for flag in TOOL_CONTROLLED_LONG:
            if flag.startswith(name):
                return "--" + flag
        return None
    if not is_short_option_token(token):
        return None  # a value, or optparse's positional "-"
    if shorts is None:
        raise ValueError("short option %r needs the checkout's short-option map" % token)
    for char in token[1:]:
        entry = shorts.get(char)
        if entry is None:
            continue
        if entry["long"] in TOOL_CONTROLLED_LONG:
            return "-" + char
        if entry["takes_value"]:
            return None  # this option takes a value: the rest of the token is that value
    return None


def lease_checkout(row, lease):
    """The Odoo checkout this lease builds and serves: the lease row's odoo_root, else the core repo
    on its addons_path (odoo_source_facts.locate_odoo_root - the one locator). None when none."""
    facts = cli.load_lib("odoo_source_facts")
    return facts.locate_odoo_root(row.get("odoo_root") or "", lease.get("addons_path") or [])


def _checkout_fact(row, lease, token, fact, reader):
    """odoo_source_facts.<reader>(the lease's checkout), or ODOO_SOURCE_FACT_UNKNOWN naming `fact`
    when the checkout does not state it - a series-dependent option fact is never guessed."""
    root = lease_checkout(row, lease)
    value = getattr(cli.load_lib("odoo_source_facts"), reader)(root) if root else None
    if value is None:
        raise ToolError("ODOO_SOURCE_FACT_UNKNOWN",
                        "lease %s: %s cannot be read from its Odoo checkout (%s)" % (
                            token[:8], fact, root or "none found from its odoo_root or addons_path"),
                        {"token_prefix": token[:8], "fact": fact, "odoo_root": root or ""})
    return value


def _second_port_key(row, lease, token):
    return _checkout_fact(row, lease, token, "the second port option (--gevent-port / "
                          "--longpolling-port in odoo/tools/config.py)", "second_port_key")


# --------------------------------------------------------------------------- #
# one live job per DATABASE
# --------------------------------------------------------------------------- #
# Kinds of job that write a database: instance_build's and instance_i18n_export's (tools_i18n).
# Two at once on one database race inside Odoo (module states, registry, translations), whether
# they came through one lease or two leases of the same database.
BUILD_JOB_KIND = "build"
EXPORT_JOB_KIND = "i18n_export"
DATABASE_JOB_KINDS = (BUILD_JOB_KIND, EXPORT_JOB_KIND)
_JOB_START_LOCK = ".database-jobs.lock"


def job_target(lease):
    """The database a job on `lease` targets, as job meta: db_name + its cluster coordinates."""
    return {"db_name": lease.get("db_name") or "", "db_host": lease.get("db_host") or "",
            "db_port": lease.get("db_port") or ""}


def _live_job_on(target):
    """The newest job record whose job writes the database `target` names and whose process is
    alive (jobs.status running); None when there is none. A finished job (exit recorded) or a
    dead one (lost) never counts. A record a server that predates the coordinates wrote carries
    db_name alone and matches by name (tools_lease.same_database)."""
    for rec in jobs.list_records():
        meta = rec.get("meta") or {}
        if meta.get("kind") not in DATABASE_JOB_KINDS:
            continue
        if not tools_lease.same_database(target, meta):
            continue
        st = jobs.status(rec["job_id"])
        if st is not None and st["state"] == "running":
            return rec
    return None


def refuse_if_busy(lease):
    """DATABASE_BUSY - naming the blocking job - when a live job already targets the lease's
    database. A tool calls it FIRST, before any gate that reads the database: while a build runs,
    what the database holds is a moment of that build (e.g. no demo yet), so a gate reading it
    would answer with a wrong refusal instead of "busy". database_job_slot checks again under the
    start lock, which is what makes the start itself race-free."""
    busy = _live_job_on(job_target(lease))
    if busy is None:
        return
    meta = busy.get("meta") or {}
    owner = (meta.get("lease_token") or "")[:8]
    raise ToolError("DATABASE_BUSY",
                    "database %s: job %s (%s, lease %s) is still running on it; one job "
                    "runs on a database at a time" % (
                        lease.get("db_name") or "?", busy["job_id"],
                        meta.get("op") or "?", owner or "?"),
                    {"job_id": busy["job_id"], "op": meta.get("op") or "",
                     "db_name": lease.get("db_name") or "",
                     "lease_token_prefix": owner,
                     "started_at": busy.get("started_at") or ""})


@contextlib.contextmanager
def database_job_slot(lease):
    """Start a database-writing job inside this block: it holds the machine-wide job-start lock
    (every odoo-local server on the machine shares $ODOO_AI_HOME's jobs dir), so two concurrent
    starts cannot both see the database free, and it refuses DATABASE_BUSY (refuse_if_busy) when a
    live job already targets the lease's database."""
    path = os.path.join(jobs.jobs_dir(), _JOB_START_LOCK)
    with open(path, "a") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            refuse_if_busy(lease)
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


# --------------------------------------------------------------------------- #
# instance_build
# --------------------------------------------------------------------------- #
def _build_port_args(op, row, lease, token):
    """`--http-port <leased port>` for 55-instance-ops.sh, which spells it with the series' own flag.

    op test needs a reserved port: Odoo spawns its HTTP server whenever test mode is on, even with
    --stop-after-init (odoo/service/server.py, every series), so a test build without the lease's
    port binds the default 8069 and collides with whatever already listens there. init/update get
    the port too when the lease reserved one. A second reserved port goes with its series key
    (read from the lease's checkout), so a prefork build (--workers in extra_args) does not bind the default
    gevent/longpolling port either."""
    ports = lease.get("ports") or []
    if not ports:
        if op == "test":
            raise ToolError("LEASE_HAS_NO_PORT", "lease %s reserved no port, and a test build binds one "
                            "(Odoo spawns its HTTP server in test mode)" % token[:8],
                            {"token_prefix": token[:8], "op": op})
        return []
    out = ["--http-port", str(ports[0])]
    if len(ports) > 1:
        out += ["--gevent-port", str(ports[1]), "--gevent-port-key", _second_port_key(row, lease, token)]
    return out


def activation_languages(languages):
    """The --load-language set for `languages`: en_US first (always), then the rest in order,
    deduplicated."""
    out = [BASE_LANGUAGE]
    for lang in languages or []:
        if lang not in out:
            out.append(lang)
    return out


def _demo_opt_in(row, lease, token):
    """True when the lease's checkout declares --with-demo (no demo unless asked), False when it
    declares only --without-demo; ODOO_SOURCE_FACT_UNKNOWN otherwise."""
    return _checkout_fact(row, lease, token, "the demo default (--with-demo / --without-demo in "
                          "odoo/tools/config.py)", "demo_opt_in")


def _declared_server_wide(row, lease, cwd):
    """The declared server-wide modules for this lease: the lease row's own copy (recorded at
    acquire), else - a row an allocator that predates the key wrote - the catalog row the lease
    was acquired for, else none."""
    if "server_wide_modules" in row:
        return list(lease.get("server_wide_modules") or [])
    from . import tools_catalog
    io = cli.load_lib("instances_io")
    try:
        items, _exists = tools_catalog._load(io, tools_catalog._resolve_catalog_path(cwd))
    except ToolError:
        return []
    item, _defaulted = io.select_instance(items, lease.get("series") or None,
                                          profile=lease.get("profile") or "")
    return io.server_wide_modules_of(item) if item is not None else []


def server_wide_for(row, lease, cwd, token):
    """The complete --load set a build on this lease uses ([] = no --load: Odoo's own default)."""
    io = cli.load_lib("instances_io")
    declared = _declared_server_wide(row, lease, cwd)
    try:
        effective, _core = io.effective_server_wide_modules(declared, row.get("odoo_root") or "",
                                                            lease.get("addons_path") or [])
    except io.ServerWideCoreUnknown as exc:
        raise ToolError("SERVER_WIDE_CORE_UNKNOWN", "lease %s: %s" % (token[:8], exc),
                        {"token_prefix": token[:8], "declared": declared,
                         "odoo_root": row.get("odoo_root") or ""})
    return effective


def record_build(token, cwd, demo=None, languages=None):
    """allocator.py record-build: what a build put into the lease's database (sticky demo, union of
    languages). Returns nothing; an unknown token raises LEASE_NOT_FOUND."""
    argv = [token]
    if demo:
        argv += ["--demo", demo]
    if languages:
        argv += ["--languages", MODULE_LIST_SEP.join(languages)]
    if len(argv) > 1:
        cli.run_allocator("record-build", argv, cwd, tools_lease.READ_TIMEOUT_S)


def _validate_build_facts(op, args):
    demo = args.get("demo")
    if op == "init" and not demo:
        raise ToolError("INVALID_ARGUMENTS",
                        "arguments.demo: required for op init - pass on (demo data loaded into the new "
                        "modules) or off")
    if op == "update" and demo:
        raise ToolError("INVALID_ARGUMENTS",
                        "arguments.demo: only op init takes demo - demo data loads when a module is "
                        "installed, and an update never adds it to the modules the database already "
                        "holds (on recent series the flag only concerns new databases). Omit demo; "
                        "for a database with demo data, build op init demo on on a new lease")
    if op == "test" and demo:
        raise ToolError("INVALID_ARGUMENTS",
                        "arguments.demo: test builds always use the series default; omit demo (the "
                        "tool reads the default from the lease's Odoo checkout and reports it). A "
                        "demo instance for manual or acceptance use is an op init demo on build on "
                        "its own lease, never a test build")
    for lang in args.get("languages") or []:
        if not _LANG_RE.match(lang):
            raise ToolError("INVALID_ARGUMENTS",
                            "arguments.languages: %r is not a language code (e.g. vi_VN, fr_BE, "
                            "sr@latin)" % lang)


def _refuse_demo_test(op, args, facts, lease, token, opt_in):
    """Where the checkout makes demo opt-in (`opt_in`) a test build never runs with demo, so a test
    build on a database that holds demo data is refused. `facts` are the DATABASE's
    (tools_lease.database_facts: read from it, else the builds every lease on it recorded), so a
    lease taken on a forwarded database sees the demo data its provider's build loaded."""
    if op != "test" or not opt_in:
        return
    if facts["demo"] is True:
        raise ToolError("TEST_DB_HAS_DEMO",
                        "lease %s: its database %s holds demo data (a build on it ran with demo on), "
                        "and on series %s tests never run on a demo database" % (
                            token[:8], lease.get("db_name") or "?", lease.get("series")),
                        {"token_prefix": token[:8], "series": lease.get("series") or "",
                         "db_name": lease.get("db_name") or "", "facts_source": facts["source"],
                         "test_mode": args.get("test_mode") or "fresh"})


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
    _validate_build_facts(op, args)
    extra = args.get("extra_args") or []
    for a in extra:
        if not a or any(c.isspace() for c in a):
            raise ToolError("INVALID_ARGUMENTS",
                            "arguments.extra_args: %r - one token per item, no whitespace (use --flag=value)" % a)
    row = _require_row(token)
    lease = tools_lease.lease_from_row(row)
    shorts = None
    if any(is_short_option_token(a) for a in extra):
        shorts = _checkout_fact(row, lease, token, "the short options (odoo/tools/config.py)",
                                "short_options")
    for a in extra:
        refused = refused_extra_flag(a, shorts)
        if refused:
            name = refused[2:] if refused.startswith("--") else shorts[refused[1:]]["long"]
            owner = _BUILD_FACT_OWNER.get(name)
            raise ToolError("INVALID_ARGUMENTS",
                            "arguments.extra_args: %r sets %s, which instance_build controls itself "
                            "(%s) - drop it" % (a, refused, owner or
                                                "database, connection, addons path, config file and "
                                                "--save, data dir, module ops, test switches, ports, "
                                                "log destination; use the tool's own arguments or "
                                                "another lease"),
                            {"flag": refused, "token": a})
    db = _lease_field(lease, "db_name", token)
    python = _lease_field(lease, "venv_python", token)
    addons = _lease_field(lease, "addons_path", token)
    # Busy FIRST: while another job runs on the database, what it holds is a moment of that job,
    # and the demo gate below would read it.
    refuse_if_busy(lease)
    demo = args.get("demo")
    opt_in = _demo_opt_in(row, lease, token) if (demo or op == "test") else None
    if op == "test":
        demo = "off" if opt_in else "on"  # the series default, read from the lease's checkout
        if opt_in:
            _refuse_demo_test(op, args, tools_lease.database_facts(row, cwd=cwd), lease, token,
                              opt_in)
    load = server_wide_for(row, lease, cwd, token)
    languages = activation_languages(args.get("languages"))

    argv = [op, "--db", db, "--python", python, "--addons", tools_lease.join_addons(addons),
            "--modules", MODULE_LIST_SEP.join(modules)]
    if lease.get("series"):
        argv += ["--version", lease["series"]]
    for flag, key in (("--db-host", "db_host"), ("--db-user", "db_user"), ("--db-port", "db_port")):
        if lease.get(key):
            argv += [flag, lease[key]]
    argv += _build_port_args(op, row, lease, token)
    if load:
        argv += ["--load", MODULE_LIST_SEP.join(load)]
    argv += ["--languages", MODULE_LIST_SEP.join(languages)]
    if demo:
        argv += ["--demo", demo]
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
    meta = dict(job_target(lease), **{
            "kind": BUILD_JOB_KIND, "op": op, "lease_token": token, "log_path": log_path,
            "output_path": output_path, "series": lease.get("series") or "",
            "profile": lease.get("profile") or "",
            "modules": list(modules), "server_wide_modules": load, "languages": languages,
            "demo": demo or ""})
    with database_job_slot(lease):
        # Recorded BEFORE the build starts: a build that fails half-way may already have loaded
        # demo data, and demo is sticky (record-build), so recording early can only over-state it.
        if demo:
            record_build(token, cwd, demo=demo)
        try:
            rec = jobs.start(cli.interpreter_for(_ops_script()) + argv, cwd,
                             env={OPS_LOG_ENV: log_path}, log_path_hint=output_path, meta=meta)
        except (OSError, ValueError) as exc:
            raise ToolError("BUILD_START_FAILED", "cannot start %s: %s" % (op, exc), {"op": op})
    # No INSTANCE_HANDLE here: the database is what the build is about to change, so any handle
    # read now would state its pre-build facts. job_wait returns the handle once the job finished.
    return {"job_id": rec["job_id"], "pid": rec["pid"], "op": op, "log_path": log_path,
            "output_path": output_path, "lease_token": token, "server_wide_modules": load,
            "languages": languages, "demo": demo or None}


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


def _scan_build_log(path):
    """(languages the log proves active, modules Odoo says must be server-wide, modules installed
    without their demo data) - read from the WHOLE build log, streamed line by line (a build log
    can be large; only lines carrying a cheap byte marker are decoded)."""
    langs, wide_lines, no_demo = [], [], []
    try:
        with open(path, "rb") as fh:
            for raw in fh:
                if b"for language" in raw:
                    m = _LANG_EVIDENCE_RE.search(raw.decode("utf-8", "replace").rstrip("\r\n"))
                    if m and m.group(1) not in langs:
                        langs.append(m.group(1))
                elif b"server wide" in raw or b"server-wide" in raw:
                    wide_lines.append(raw.decode("utf-8", "replace"))
                elif b"demo data failed to install" in raw:
                    m = _DEMO_FAILED_RE.search(raw.decode("utf-8", "replace"))
                    if m and m.group(1) not in no_demo:
                        no_demo.append(m.group(1))
    except OSError:
        return [], [], []
    facts = cli.try_load_lib("odoo_source_facts")
    wide = facts.server_wide_warning_modules("".join(wide_lines)) if facts and wide_lines else []
    return langs, list(wide), no_demo


def _catalog_row_words(meta):
    """How a server-wide remedy names the lease's catalog row: its instance_key (instances_io, the
    one spelling: `<series>:<profile>`, or `<series>` for an unprofiled row) and the odoo-setup
    refresh narrowing that selects exactly that row."""
    series, profile = meta.get("series") or "", meta.get("profile") or ""
    io = cli.try_load_lib("instances_io")
    key = io.instance_key_of({"series": series, "profile": profile}) if io is not None else (
        "%s:%s" % (series, profile) if profile else series)
    refresh = "refresh --version %s" % (series or "?")
    if profile:
        refresh += " --profile %s" % profile
    return key or "?", refresh


def _build_warnings(wide, no_demo, meta):
    out = []
    if wide:
        key, refresh = _catalog_row_words(meta)
        out.append("Odoo logged that %s must be loaded server-wide (--load), and this build did not "
                   "load %s: add %s to server_wide_modules of this lease's catalog row %s via "
                   "/odoo-ai-agents:odoo-setup %s, then lease_release this lease, lease_acquire a "
                   "new one and rebuild - a lease keeps the set it was acquired with." % (
                       ", ".join(wide), "them" if len(wide) > 1 else "it",
                       "them" if len(wide) > 1 else "it", key, refresh))
    if no_demo:
        out.append("demo data of %s failed to install; Odoo installed %s WITHOUT demo data - read "
                   "the log for the demo-data error before relying on demo records." % (
                       ", ".join(no_demo), "them" if len(no_demo) > 1 else "it"))
    return out


def _languages_verdict(state, modules_loaded, requested, seen):
    """(languages_loaded, languages_failed) for a finished job; (None, None) while it runs. A
    language is loaded when the log shows Odoo loading its terms (an unknown code logs nothing and
    loads nothing, while the build still succeeds); en_US - whose terms Odoo never logs - when it
    was requested and the build's module loading finished (`modules_loaded`: the script's
    BUILD_MODULES_LOADED - Odoo activates --load-language before its "Modules loaded." line on
    every series), whatever a test suite that runs afterwards reports."""
    if state == "running" or not requested:
        return None, None
    loaded = [lang for lang in seen]
    if modules_loaded and BASE_LANGUAGE in requested and BASE_LANGUAGE not in loaded:
        loaded.insert(0, BASE_LANGUAGE)
    return loaded, [lang for lang in requested if lang not in loaded]


def _finished_handle(meta, cwd, loaded, log_path):
    """Record the languages a finished build proved loaded onto its lease and return the lease's
    INSTANCE_HANDLE; None when the lease is gone."""
    token = meta.get("lease_token") or ""
    if not token:
        return None
    if loaded:
        try:
            record_build(token, cwd, languages=loaded)
        except ToolError as exc:
            if exc.code != "LEASE_NOT_FOUND":
                raise
            return None
    try:
        row = tools_lease.read_row(token)
    except ToolError:
        return None
    if row is None:
        return None
    return tools_lease.database_handle(row, log_path=log_path, cwd=cwd)


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
    output = _read_tail(output_path)
    summary = _kv_lines(output, _SUMMARY_KEYS)
    exporting = is_export_job(meta)
    if exporting:
        # An export's verdict is its exit code and STATUS line; no build marker applies.
        verdict, test_result = {}, ""
        result = _decide_export(st["state"], st.get("exit_code"), summary)
    else:
        verdict = _wait_log_verdict(log_path, cwd)
        test_result = summary.get("TEST_RESULT") or verdict.get("TEST_RESULT") or ""
        result = _decide(st["state"], st.get("exit_code"), verdict, test_result)
    finished = st["state"] != "running"
    seen, wide, no_demo = (_scan_build_log(log_path) if (finished and log_path and not exporting)
                           else ([], [], []))
    loaded, failed = _languages_verdict(st["state"], summary.get("BUILD_MODULES_LOADED") == "1",
                                        meta.get("languages") or [], seen)
    handle = _finished_handle(meta, cwd, loaded, log_path) if finished else None
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
        "server_wide_modules": list(meta.get("server_wide_modules") or []),
        "demo": meta.get("demo") or None,
        "languages_loaded": loaded,
        "languages_failed": failed,
        "warnings": _build_warnings(wide, no_demo, meta),
        "exports": _exports_from(output) if exporting else [],
        "instance_handle": handle,
    }


# --------------------------------------------------------------------------- #
# job_wait's reading of an instance_i18n_export job (tools_i18n starts it)
# --------------------------------------------------------------------------- #
_EXPORTED_RE = re.compile(r"^EXPORTED=([^|]*)\|([^|]*)\|(.+)$")

EXPORTS_SCHEMA = {
    "type": "array",
    "description": "Files an instance_i18n_export job wrote, in export order: per module its .pot "
                   "template first, then one .po per language. Reported as each finished, so a "
                   "failed job lists the files written before the failure. Empty for a build.",
    "items": _obj({
        "module": {"type": "string"},
        "kind": {"type": "string", "enum": ["pot", "po"]},
        "language": {"type": ["string", "null"],
                     "description": "The language code of a .po; null for the .pot."},
        "path": {"type": "string", "description": "Absolute path of the file Odoo wrote."},
    }, ["module", "kind", "language", "path"]),
}


def is_export_job(meta):
    return (meta or {}).get("kind") == EXPORT_JOB_KIND


def _exports_from(output):
    """The EXPORTED=<module>|<language>|<path> lines of an export job's output, in order."""
    out = []
    for line in (output or "").splitlines():
        m = _EXPORTED_RE.match(line)
        if m:
            out.append({"module": m.group(1), "kind": "po" if m.group(2) else "pot",
                        "language": m.group(2) or None, "path": m.group(3)})
    return out


def _decide_export(state, exit_code, summary):
    """An export job's result: the process state, then exit 0 with STATUS=ok is the only pass."""
    if state == "running":
        return "timeout"
    if state == "lost":
        return "lost"
    return "success" if exit_code == 0 and summary.get("STATUS") == "ok" else "failure"


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
                argv += ["--gevent-port", str(ports[1]), "--gevent-port-key",
                         _second_port_key(row, lease, token)]
    else:
        argv += ["--version", series]
        if args.get("profile"):
            argv += ["--profile", args["profile"]]
        if args.get("run_id"):
            extra_env["INST_RUN_ID"] = args["run_id"]
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
        if facts.get("SERVE_REFUSED") == "SERVER_WIDE_CORE_UNKNOWN":
            raise ToolError("SERVER_WIDE_CORE_UNKNOWN",
                            "the catalog declares server_wide_modules for this instance, but Odoo's "
                            "core --load default could not be read from its checkout; nothing was "
                            "launched", diagnostics)
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
    if row is not None:
        db_facts = tools_lease.database_facts(row, cwd=cwd)
        handle_src["built"] = {"demo": db_facts["demo"], "languages": db_facts["languages"]}
        handle_src["facts_source"] = db_facts["source"]
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
    "server_wide_modules": {"type": "array", "items": {"type": "string"},
                            "description": "The complete --load set the build ran with (empty = "
                                           "none passed: Odoo's own default)."},
    "demo": {"type": ["string", "null"], "enum": ["on", "off", None],
             "description": "The demo value the build ran with (op test: the series default the "
                            "tool read); null = not stated (op update, or a job that is not a "
                            "build)."},
    "languages_loaded": {"type": ["array", "null"], "items": {"type": "string"},
                         "description": "Languages the finished build proved active: a language "
                                        "whose terms the log shows Odoo loading, and en_US once "
                                        "the build's module loading finished - whatever a test "
                                        "suite run after it reports (null while running)."},
    "languages_failed": {"type": ["array", "null"], "items": {"type": "string"},
                         "description": "Requested languages the finished build did NOT prove "
                                        "active - an unknown code, or a build that stopped before "
                                        "its modules loaded (null while running)."},
    "warnings": {"type": "array", "items": {"type": "string"},
                 "description": "Problems a finished build logged without failing, each with its "
                                "remedy; act on every one before trusting the instance."},
    "exports": EXPORTS_SCHEMA,
    "instance_handle": {"anyOf": [HANDLE_SCHEMA, {"type": "null"}],
                        "description": "The lease's INSTANCE_HANDLE once the job finished (demo and "
                                       "languages_loaded: its database's facts, see facts_source); "
                                       "null while running or when the lease is gone."},
}, ["job_id", "result", "state", "exit_code", "op", "marker", "progress", "test_result", "summary",
    "log_path", "output_path", "log_tail", "output_tail", "detail", "server_wide_modules", "demo",
    "languages_loaded", "languages_failed", "warnings", "exports", "instance_handle"])


def register(registry, ctx):
    registry.add(
        "instance_build",
        "Start an Odoo build on a lease you hold or were handed: op init (-i, install modules into the "
        "lease's database - creating it on first use), update (-u), or test (install/update + run the "
        "tests). Database, venv python, addons path, Postgres coordinates and listening port(s) are "
        "read FROM THE LEASE - never pass them; the build binds the lease's reserved port. op test "
        "needs a lease with a port (lease_acquire ports 1): a test build always starts Odoo's HTTP "
        "server, so on a lease without one it is refused with LEASE_HAS_NO_PORT. "
        "The tool applies three build facts itself - never put them in extra_args: "
        "(1) server-wide modules: --load = the series' core default read from the lease's Odoo "
        "checkout + the catalog row's server_wide_modules recorded on the lease; declared modules "
        "whose core default cannot be read are refused (SERVER_WIDE_CORE_UNKNOWN), never guessed; "
        "(2) languages: en_US plus every code in languages is loaded (--load-language) on every "
        "build; (3) demo: required for op init - pass on or off, the tool spells the flag the "
        "lease's Odoo checkout declares; op update takes NO demo (an update never adds demo data "
        "to installed modules; any value is refused with INVALID_ARGUMENTS); op test takes NO demo "
        "either (refused likewise): a test build always runs with the series default read from that "
        "checkout (demo loaded where the series loads it by default, none where demo is opt-in) "
        "and reports the value used. Where the checkout loads no demo data by default (it "
        "declares --with-demo), op test refuses a database that holds demo data - read from the "
        "database itself (else from the builds recorded on any lease of it, e.g. the one a "
        "forwarded INSTANCE_HANDLE came from) (TEST_DB_HAS_DEMO); build a demo instance on its own lease "
        "with op init demo on. One build or export runs on a database at a time: while another "
        "job still runs on this lease's database (through any lease), the call is refused with "
        "DATABASE_BUSY naming that job_id - job_wait it, then call again. Returns within seconds "
        "with job_id; the build runs in the background and "
        "survives this server restarting. Then call job_wait(job_id) until its result is not timeout; "
        "job_wait reports languages_loaded / languages_failed and warnings. "
        "Other version-specific Odoo flags go in extra_args, one token per item (--flag=value form), "
        "resolved for the lease's series with Odoo Semantic cli_help - never guessed; a flag the tool "
        "sets itself or that would move what it reads (database / db connection, addons path, config "
        "and --save, data dir, -i/-u, stop-after-init, test switches, any port, "
        "--logfile/--syslog/--pidfile, --load, --load-language, -l/--language, --with-demo, "
        "--without-demo) is refused with INVALID_ARGUMENTS naming it - long flags are matched by any "
        "prefix Odoo would accept, and short flags are read the way Odoo reads them, so a combined "
        "-sd... is refused for its -d. The demo default, the second port option and the short "
        "options are read from the lease's Odoo checkout; one it does not state is refused with "
        "ODOO_SOURCE_FACT_UNKNOWN. VENV_MISSING = the lease has no venv python: follow the "
        "remedy. For op test pass test_tags to select whose tests run (omitted = every loaded "
        "module's tests); test_mode fresh (-i) for modules not yet installed in the lease's "
        "database, reuse (-u) for modules already installed - -u is right for that on every series, "
        "while on recent series -i skips an installed module and runs none of its tests. log_path is the Odoo log to read for diagnosis. "
        "Every odoo-bin the tool launches reads a config file the tool generates, never the "
        "operator's ~/.odoorc. The start result carries no INSTANCE_HANDLE (the database is what "
        "the build changes): job_wait returns it, with the database's post-build facts, once the "
        "job finished - forward that one.",
        _obj({
            "lease_token": {"type": "string", "minLength": 8,
                            "description": "Full token of the lease to build on (lease.token or "
                                           "INSTANCE_HANDLE.lease_token)."},
            "op": {"type": "string", "enum": ["init", "update", "test"],
                   "description": "init (-i) | update (-u) | test (-i/-u plus --test-enable)."},
            "modules": {"type": "array", "minItems": 1, "items": {"type": "string", "minLength": 1},
                        "description": "Technical module names to install/update (test: the modules "
                                       "whose registry is built)."},
            "demo": {"type": "string", "enum": list(DEMO_VALUES),
                     "description": "Required for op init, REFUSED for op update and op test: on "
                                    "= load demo data into the modules this build installs, off = "
                                    "do not. Choose by purpose: acceptance, demo and i18n-export "
                                    "instances on. op update: never pass it - demo data loads "
                                    "only when a module is installed. op test: never pass it - "
                                    "automation tests always use the series default, which the "
                                    "tool reads from the lease's checkout (on where the series "
                                    "loads demo by default, off where demo is opt-in). Demo data "
                                    "never leaves a database once loaded, and the lease records "
                                    "it."},
            "languages": {"type": "array", "items": {"type": "string", "minLength": 2},
                          "description": "Language codes to load besides en_US (always loaded), "
                                         "e.g. [\"vi_VN\", \"fr_BE\"]. Omit when only en_US is "
                                         "needed."},
            "extra_args": {"type": "array", "items": {"type": "string"},
                           "description": "Other odoo-bin flags for this series, one token each, e.g. "
                                          "[\"--workers=2\"], resolved via Odoo Semantic cli_help. "
                                          "Never a flag the tool controls (-d/--database, "
                                          "--db-filter, -r/--db_user, -w/--db_password, "
                                          "--db_host/--db_port/--db-template/--db_replica_*, "
                                          "--addons-path, -c/--config, -s/--save, -D/--data-dir, -i/-u, "
                                          "--stop-after-init, --test-enable/--test-tags/--test-file "
                                          "(and -t where it means --test-tags), any port flag, "
                                          "--logfile/--syslog/--pidfile, --load, --load-language, "
                                          "-l/--language, --with-demo, --without-demo), alone, as an "
                                          "accepted prefix, or inside a combined short-flag token: "
                                          "refused."},
            "test_tags": {"type": "string", "minLength": 1,
                          "description": "op test only: the --test-tags selection (e.g. /my_module)."},
            "test_mode": {"type": "string", "enum": ["fresh", "reuse"],
                          "description": "op test only: fresh (default, -i) when the modules are not "
                                         "installed in the lease's database yet; reuse (-u) when they "
                                         "are - correct on every series (recent series skip an "
                                         "installed module under -i)."},
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
            "server_wide_modules": {"type": "array", "items": {"type": "string"},
                                    "description": "The complete --load set this build runs with "
                                                   "(empty = none passed: Odoo's own default)."},
            "languages": {"type": "array", "items": {"type": "string"},
                          "description": "The --load-language set requested (en_US first)."},
            "demo": {"type": ["string", "null"], "enum": ["on", "off", None],
                     "description": "The demo value this build runs with (op test: the series "
                                    "default read from the checkout); null = not stated (op "
                                    "update)."},
        }, ["job_id", "pid", "op", "log_path", "output_path", "lease_token", "server_wide_modules",
            "languages", "demo"]),
        _build, title="Start an Odoo build/test job", destructive=True,
    )
    registry.add(
        "job_wait",
        "Wait up to timeout_s for a job started by instance_build or instance_i18n_export, then "
        "report it. result: success (passed/installed/every file exported), failure, inconclusive (finished but NOT a pass - e.g. no test proven to "
        "run; read the log), lost (the job process vanished without an exit record), or timeout "
        "(still running). While result is timeout, call job_wait again with the same job_id - never "
        "end your turn waiting on a build without a tool call. The process exit code is "
        "authoritative; marker/progress come from the build script's own log reading, and progress "
        "changing between two waits shows the build is advancing. For op test read test_result and "
        "summary (TEST_FAILED, TEST_ERROR, FINDINGS_PATH...). On failure read output_tail first (a "
        "refused preflight is reported there), then log_tail and log_path. Once the job finished: "
        "languages_loaded / languages_failed say which requested languages the build proved active "
        "(a failed one is an unknown code or a build that stopped before its modules loaded - never "
        "report it as loaded; a test suite's own verdict does not change them); warnings "
        "lists problems the build logged without failing - e.g. a module Odoo says must be loaded "
        "server-wide, whose remedy is a catalog change through /odoo-ai-agents:odoo-setup and a new "
        "lease - act on each before trusting the instance; instance_handle is the lease's handle "
        "with demo and languages_loaded read from its database (facts_source), the one to forward. "
        "For an instance_i18n_export job read exports: every file written, in order (.pot first); "
        "on failure output_tail names the cause. It records a build's proven languages on the "
        "lease and changes nothing else.",
        _obj({
            "job_id": {"type": "string", "minLength": 1,
                      "description": "job_id returned by instance_build or instance_i18n_export "
                                     "(valid across server restarts)."},
            "timeout_s": {"type": "integer", "minimum": 1, "maximum": WAIT_MAX_S, "default": WAIT_DEFAULT_S,
                          "description": "Seconds to wait before returning result timeout (1-540)."},
        }, ["job_id"]),
        JOB_WAIT_OUTPUT,
        _job_wait, title="Wait for an Odoo build/test job", long_running=True, destructive=False,
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
        "lease_park or lease_release that lease. Server-wide modules are applied by the tool, as for "
        "instance_build: the series' core default read from the Odoo checkout + the lease's (with "
        "series: the catalog row's) server_wide_modules, reported as served_server_wide_modules; "
        "declared modules whose core default cannot be read are refused "
        "(SERVER_WIDE_CORE_UNKNOWN) and nothing is launched.",
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
            "served_server_wide_modules": {"type": "array", "items": {"type": "string"},
                                           "description": "The resolved server-wide module set "
                                                          "(core default + declared) the served conf "
                                                          "carries; empty = none declared, Odoo's "
                                                          "own default applies."},
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
