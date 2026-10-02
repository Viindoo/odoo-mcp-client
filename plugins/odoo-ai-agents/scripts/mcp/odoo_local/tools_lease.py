"""tools_lease.py - lease tools (acquire / release / park / list / find / gc / db preflight / adopt)
and the session heartbeat.

Every tool is a thin shell over `scripts/lib/allocator.py <verb> --format json` (cli.run_allocator):
the allocator owns every rule (ownership, liveness, reclamation, capability probes) and this module
owns only the TRANSLATION into tool vocabulary. Two translation tables live here and nowhere else:

  LEASE_FIELDS   tool field name <- allocator envelope key (ALLOC_*) <- lease-row key. Every lease
                 this server returns - from acquire, from a registry row, from a query - is built
                 by `lease_from_envelope` / `lease_from_row` over this one table. A field with no
                 envelope key (None) exists only on a registry row; an envelope reports its
                 normalized empty value.
  HANDLE_FIELDS  the INSTANCE_HANDLE shape (snippets/instance-handle-contract.md field names),
                 filled from a lease by `instance_handle`.

Token visibility rule. The full token AND the owner run id together are everything lease_release /
lease_park / lease_adopt need, so the pair is handed out only where holding it is already
legitimate; everywhere else a lease is shown by its 8-char token_prefix (enough to recognise it,
useless for mutating it) with token=null and run_id=null. A run id is a guessable slug, so it is
guarded like the token: disclosing it to a foreign session is half of a release.
  lease_acquire   the full token + run id of the lease just acquired (the caller owns it).
  lease_list      token + run_id only for leases anchored to THIS Claude Code session (the session
                  the server belongs to, `allocator.py list --session mine`); every other row shows
                  token=null, run_id=null and its token_prefix.
  lease_find /    token + run_id only when the caller passes a run_id equal to the lease's owner
  instance_status run AND the lease is anchored to this session or the session it records has
                  ended (`discloses_to_this_session`) - how an owner resumes its own parked lease
                  from a new session (lease_adopt needs the full token). A live FOREIGN session's
                  lease is never disclosed, even to a caller naming its run: a shared render server
                  is multi-reader, and a reader needs its URL (served / http_port / url), never the
                  token or the owner's run id.
  instance_serve  by series: the shared lease's token + run id only when THIS call launched the
                  server (and so registered the lease) or the lease is disclosed to this caller as
                  above; an attach to another run's render server is not obtainment.
  lease_gc        never a full token; run_id only for this session's leases.
  NOT_OWNER       never names the owner run (message or diagnostics).
  lease_adopt     echoes the token the caller already passed.

Served facts: every lease object carries served (a server process is bound to the lease, alive on
this host and not parked), http_port and url (non-null only when served; http_port is the lease's
first reserved port, the port 50-instance-spinup.sh binds for it).
"""

import contextlib
import errno
import fcntl
import hashlib
import logging
import os
import socket
import sys
import threading
import time

from . import cli
from .errors import ToolError, remedy_for

log = logging.getLogger("odoo-local")

ACQUIRE_TIMEOUT_S = 120
RELEASE_TIMEOUT_S = 300
GC_TIMEOUT_S = 540
READ_TIMEOUT_S = 60
HEARTBEAT_INTERVAL_S = 600
HEARTBEAT_ENV = "ODOO_LOCAL_MCP_HEARTBEAT_S"  # tuning knob (tests shorten it); default 600s
TOKEN_PREFIX_LEN = 8
MAX_PORTS = 4


# --------------------------------------------------------------------------- #
# the ONE field map: tool name <- ALLOC_* envelope key <- lease-row key
# --------------------------------------------------------------------------- #
def _owner_run(row):
    owner = row.get("owner") or {}
    return owner.get("run_id") or owner.get("session_id") or ""


LEASE_FIELDS = (
    # (tool field, allocator envelope key, lease-row getter)
    ("token", "ALLOC_TOKEN", lambda r: r.get("token")),
    ("mode", "ALLOC_MODE", lambda r: r.get("mode")),
    ("db_name", "ALLOC_DB_NAME", lambda r: r.get("db_name")),
    ("ports", "ALLOC_PORTS", lambda r: r.get("ports")),
    ("series", "ALLOC_SERIES", lambda r: r.get("series")),
    ("profile", "ALLOC_PROFILE", lambda r: r.get("profile")),
    ("addons_path", "ALLOC_ADDONS_PATH", lambda r: r.get("addons_path")),
    ("venv_python", "ALLOC_PYTHON", lambda r: r.get("python")),
    ("db_host", "ALLOC_DB_HOST", lambda r: (r.get("_pg") or {}).get("host") or r.get("db_host")),
    ("db_user", "ALLOC_DB_USER", lambda r: (r.get("_pg") or {}).get("user") or r.get("db_user")),
    ("db_port", "ALLOC_DB_PORT", lambda r: r.get("db_port")),
    ("run_id", "ALLOC_RUN_ID", _owner_run),
    ("server_wide_modules", "ALLOC_SERVER_WIDE_MODULES", lambda r: r.get("server_wide_modules")),
    # What builds put into the database (allocator.py record-build). Never in an acquire envelope:
    # a fresh lease has built nothing yet.
    ("built", None, lambda r: r.get("built")),
)


def _ports(value):
    if value in (None, ""):
        return []
    if not isinstance(value, (list, tuple)):
        value = str(value).replace(",", " ").split()
    out = []
    for p in value:
        try:
            out.append(int(p))
        except (TypeError, ValueError):
            continue
    return out


def _addons_list(value):
    if not value:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value if str(v)]
    io = cli.try_load_lib("instances_io")
    if io is not None and hasattr(io, "split_addons_path"):
        return list(io.split_addons_path(str(value)))
    return [p for p in str(value).split(",") if p]


def join_addons(entries):
    """The Odoo addons_path string for a list of directories - via the SSOT joiner
    (instances_io.join_addons_path), never a separator spelled here."""
    return cli.load_lib("instances_io").join_addons_path(list(entries or []))


def _text(value):
    return "" if value is None else str(value)


def _module_list(value):
    """A module list from a row (a list) or a shell-mode envelope (space- or comma-joined)."""
    if not value:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value if str(v).strip()]
    return [m for m in str(value).replace(",", " ").split() if m]


def _built(value):
    """{demo: true|false|null, languages: [...]} from a row's `built` (absent = nothing recorded:
    demo unknown, no language proved)."""
    value = value if isinstance(value, dict) else {}
    demo = value.get("demo")
    return {"demo": demo if isinstance(demo, bool) else None,
            "languages": _module_list(value.get("languages"))}


_NORMALIZE = {"ports": _ports, "addons_path": _addons_list, "server_wide_modules": _module_list,
              "built": _built}


def _pg_coordinates(row):
    """(host, port) of the Postgres cluster a registry row's database lives on; "" = unstated."""
    pg = row.get("_pg") or {}
    return (str(pg.get("host") or row.get("db_host") or ""),
            str(row.get("db_port") or pg.get("port") or ""))


def same_database(a, b):
    """True when two registry rows name the same database: the same db_name on the same cluster.
    A coordinate one row leaves unstated (a row an older allocator wrote, libpq's default) never
    tells two databases apart; two stated, different ones always do."""
    if not a.get("db_name") or a.get("db_name") != b.get("db_name"):
        return False
    for mine, theirs in zip(_pg_coordinates(a), _pg_coordinates(b)):
        if mine and theirs and mine != theirs:
            return False
    return True


def database_built(row, rows=None):
    """What builds put into the DATABASE `row` names, from the `built` of EVERY registry row on that
    database (`rows`: the registry, read when omitted) - not only this lease's own. Build facts
    belong to the database: an agent handed an INSTANCE_HANDLE takes its own lease on the same
    database, and that fresh lease recorded no build, yet the demo data the provider loaded is
    there. demo: true when any row says true (demo data never leaves a database), false when a
    row says false and none says true, null when none recorded it; languages: the union, this
    row's first. Rows that predate the key contribute nothing."""
    if rows is None:
        rows = list_rows([])
    demo, languages = None, []
    for other in [row] + [r for r in rows if r.get("token") != row.get("token") and same_database(row, r)]:
        built = _built(other.get("built"))
        if built["demo"] is True:
            demo = True
        elif built["demo"] is False and demo is None:
            demo = False
        languages += [lang for lang in built["languages"] if lang not in languages]
    return {"demo": demo, "languages": languages}


DB_FACTS_TIMEOUT_S = 60
FACTS_FROM_DATABASE = "database"
FACTS_FROM_LEASES = "leases"
_UNREAD = object()


def read_database(row, cwd=None, modules=None):
    """{demo, languages} read from the database `row` names ITSELF - `odoo_db.py db-facts` under
    the lease's venv python (ir_module_module.demo of the installed modules, the active res_lang
    codes; a database that does not exist holds nothing) - or None when it cannot be read (no
    venv on the row, e.g. a shared lease; the venv cannot import Odoo; the cluster refused or did
    not answer; the bound elapsed). One connection. With `modules`, also "modules":
    {name: {"state", "demo"}} for each of them the database knows (its OWN demo flag - the
    database-wide `demo` says nothing about one module); a module it does not know is absent."""
    python, db = row.get("python"), row.get("db_name")
    if not python or not db:
        return None
    argv = [python, str(cli.LIB_DIR / "odoo_db.py"), "db-facts", db]
    if modules:
        argv += ["--modules", ",".join(modules)]
    host, port = _pg_coordinates(row)
    user = (row.get("_pg") or {}).get("user") or row.get("db_user") or ""
    for flag, value in (("--db-host", host), ("--db-user", user), ("--db-port", port)):
        if value:
            argv += [flag, str(value)]
    facts = cli.try_load_lib("odoo_source_facts")
    root = facts.locate_odoo_root(row.get("odoo_root") or "", _addons_list(row.get("addons_path"))) \
        if facts is not None else None
    if root:
        argv += ["--odoo-root", root]
    try:
        rc, out, _err = cli.run(argv, cwd or os.getcwd(), DB_FACTS_TIMEOUT_S)
    except (cli.SubprocessTimeout, OSError):
        return None
    lines = (out or "").splitlines()
    kv = dict(line.split("=", 1) for line in lines if "=" in line and not line.startswith("MODULE="))
    if rc != 0:
        return None
    if kv.get("DB_EXISTS") == "0":
        return dict({"demo": False, "languages": []}, **({"modules": {}} if modules else {}))
    if kv.get("DB_EXISTS") != "1" or kv.get("DEMO") not in ("0", "1") or "LANGUAGES" not in kv:
        return None
    out_facts = {"demo": kv["DEMO"] == "1", "languages": _module_list(kv["LANGUAGES"])}
    if modules:
        out_facts["modules"] = _module_facts(lines)
    return out_facts


def _module_facts(lines):
    """{name: {"state", "demo"}} from db-facts' `MODULE=<name> STATE=<state> DEMO=1|0` lines."""
    found = {}
    for line in lines:
        if not line.startswith("MODULE="):
            continue
        fields = dict(part.split("=", 1) for part in line.split() if "=" in part)
        if fields.get("MODULE"):
            found[fields["MODULE"]] = {"state": fields.get("STATE") or "",
                                       "demo": fields.get("DEMO") == "1"}
    return found


def database_facts(row, rows=None, cwd=None, db=_UNREAD, modules=None):
    """What the database `row` names holds: {demo, languages, source} (+ "modules" when asked with
    `modules` and the database itself answered - see read_database). The DATABASE is the source
    of truth (read_database; `db` = a read the caller already made, so one tool call reads it
    once); only when it cannot be read do the lease records answer (database_built: every lease on
    that database; they record nothing per module). `source` says which: "database" | "leases"."""
    if db is _UNREAD:
        db = read_database(row, cwd, modules=modules)
    if db is not None:
        return dict(db, source=FACTS_FROM_DATABASE)
    return dict(database_built(row, rows), source=FACTS_FROM_LEASES)


def database_handle(row, lease=None, rows=None, facts=None, cwd=None, **kwargs):
    """instance_handle for the lease `row` describes, with demo / languages_loaded the DATABASE's
    facts (database_facts, or `facts` already read) and facts_source naming who answered."""
    facts = facts if facts is not None else database_facts(row, rows, cwd)
    lease = dict(lease if lease is not None else lease_from_row(row),
                 built={"demo": facts["demo"], "languages": facts["languages"]},
                 facts_source=facts["source"])
    return instance_handle(lease, **kwargs)


def _normalized(name, value):
    if name == "token":
        return value or None
    return _NORMALIZE.get(name, _text)(value)


def serve_url(port):
    """The URL of a server listening on `port` on this host. Same spelling as the SERVE_URL fact
    50-instance-spinup.sh prints (_emit_serve_facts), which is what instance_serve returns."""
    return "http://localhost:%d" % port


def _unserved(lease):
    lease.update({"served": False, "http_port": None, "url": None})
    return lease


def _served_pid(row):
    """The row's bound server pid when that process is provably the lease's live server on THIS
    host (alive, not a recycled pid, lease neither parked nor being reclaimed), else None."""
    state = (row.get("verdict") or {}).get("state")
    if state in ("parked", "reclaiming") or row.get("parked_at") is not None:
        return None
    owner = row.get("owner") or {}
    pid = owner.get("pid")
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 1:
        return None
    if owner.get("host") and owner.get("host") != socket.gethostname():
        return None
    sa = cli.try_load_lib("session_anchor")
    if sa is None or not sa.pid_alive(pid):
        return None
    # The ONE rule for which recorded fingerprint still speaks for THIS pid is the allocator's own
    # `_recorded_fingerprint` (scripts/lib/allocator.py): owner.pid_fp is trusted only while
    # owner.pid_fp_pid == pid; otherwise it falls back to the legacy owner.pid_started. Re-deriving
    # that by hand here (e.g. `pid_fp or pid_started`, ignoring pid_fp_pid) reads a STALE pid_fp - one
    # an older allocator's bind/resume left behind after rewriting pid + pid_started but not pid_fp -
    # as this pid's fingerprint, and fp_verdict then reports a false MISMATCH against a server that is
    # actually alive. Importing the allocator's helper (pure, no I/O, no registry access) keeps this
    # one rule in one place instead of a second copy that can drift from it.
    alloc = cli.try_load_lib("allocator")
    if alloc is not None and hasattr(alloc, "_recorded_fingerprint"):
        expected, _key = alloc._recorded_fingerprint(owner, pid)
    else:
        expected = owner.get("pid_fp") or owner.get("pid_started")
    if expected and sa.fp_verdict(expected, pid) == sa.VERDICT_MISMATCH:
        return None
    return pid


def lease_from_envelope(fields):
    """A lease dict from an allocator envelope's `fields` (acquire / query output). The envelope
    carries no server facts, so it is reported unserved."""
    return _unserved({name: _normalized(name, fields.get(key) if key else None)
                      for name, key, _row in LEASE_FIELDS})


def recorded_session_state(row):
    """"alive" | "dead" | "unknown" for the session anchor lease `row` records (owner.session),
    or None when it records none. Measured HERE (session_anchor.anchor_state, the allocator's own
    probe) for EVERY anchored row, rather than read from verdict.anchor_alive: the allocator's
    verdict never measures the anchor of a parked row (judged by its park budget) or a shared row
    (judged by its server pid) and leaves anchor_alive null for both - exactly the rows an owner
    resuming from a new session must tell apart. "unknown" = not provable either way (the anchor
    was recorded on another host, or its fingerprint cannot be matched)."""
    owner = row.get("owner") or {}
    session = owner.get("session")
    if not session:
        return None
    sa = cli.try_load_lib("session_anchor")
    if sa is None:
        return "unknown"
    return sa.anchor_state(session, owner.get("host") or None)


def _session_alive(row):
    state = recorded_session_state(row)
    return {"alive": True, "dead": False}.get(state) if state else None


def lease_from_row(row):
    """A lease dict from one registry row (`allocator.py list` output)."""
    lease = {name: _normalized(name, getter(row)) for name, _key, getter in LEASE_FIELDS}
    lease["session_alive"] = _session_alive(row)
    _unserved(lease)
    if _served_pid(row) is not None and lease["ports"]:
        port = lease["ports"][0]
        lease.update({"served": True, "http_port": port, "url": serve_url(port)})
    return lease


# --------------------------------------------------------------------------- #
# INSTANCE_HANDLE (field names: snippets/instance-handle-contract.md)
# --------------------------------------------------------------------------- #
HANDLE_FIELDS = ("db_name", "http_port", "gevent_port", "db_port", "addons_path", "venv_python",
                 "demo", "languages_loaded", "facts_source", "log_path", "lease_token", "run_id",
                 "server_pid")


def instance_handle(lease, log_path=None, server_pid=None, http_port=None):
    """The INSTANCE_HANDLE a lease can fill. demo / languages_loaded come from lease.built; the
    tools hand it the DATABASE's facts (database_handle: read from the database itself, else from
    the builds every lease on it recorded - facts_source says which), so a handle on a forwarded
    database states what that database holds. demo null = nothing known; languages_loaded null =
    no language known active. http_port/gevent_port are the lease's reserved ports unless a bound
    port is given."""
    ports = lease.get("ports") or []
    built = lease.get("built") or {}
    return {
        "db_name": lease.get("db_name") or "",
        "http_port": http_port if http_port is not None else (ports[0] if ports else None),
        "gevent_port": ports[1] if len(ports) > 1 else None,
        "db_port": lease.get("db_port") or "",
        "addons_path": join_addons(lease.get("addons_path")),
        "venv_python": lease.get("venv_python") or "",
        "demo": built.get("demo"),
        "languages_loaded": list(built["languages"]) if built.get("languages") else None,
        "facts_source": lease.get("facts_source") or FACTS_FROM_LEASES,
        "log_path": log_path,
        "lease_token": lease.get("token"),
        "run_id": lease.get("run_id") or "",
        "server_pid": server_pid,
    }


# --------------------------------------------------------------------------- #
# schemas
# --------------------------------------------------------------------------- #
_NULLABLE_STR = {"type": ["string", "null"]}
_NULLABLE_INT = {"type": ["integer", "null"]}

# The ONE lease object schema: every tool that returns a lease (acquire, list, find, adopt, status)
# uses it or extends it, so a consumer reads the same field names everywhere.
LEASE_SCHEMA = {
    "type": "object",
    "required": ["token", "mode", "db_name", "ports", "series", "profile", "addons_path",
                 "venv_python", "db_host", "db_user", "db_port", "run_id", "server_wide_modules",
                 "built", "session_alive", "served", "http_port", "url"],
    "properties": {
        "token": dict(_NULLABLE_STR, description="Full lease token, or null when this caller may not "
                                                 "hold it (see token_prefix)."),
        "mode": {"type": "string", "description": "ephemeral | exclusive | shared | readonly."},
        "db_name": {"type": "string"},
        "ports": {"type": "array", "items": {"type": "integer"},
                  "description": "Ports the lease reserved (first = HTTP)."},
        "series": {"type": "string"},
        "profile": {"type": "string", "description": "Catalog profile the lease was acquired for; "
                                                     "empty = the unprofiled row."},
        "addons_path": {"type": "array", "items": {"type": "string"}},
        "venv_python": {"type": "string", "description": "Interpreter builds and serves run with; "
                                                         "empty = the catalog declares none."},
        "db_host": {"type": "string"},
        "db_user": {"type": "string"},
        "db_port": {"type": "string", "description": "Postgres port; empty = libpq default."},
        "run_id": dict(_NULLABLE_STR, description="Owner run id; null when not disclosed to this "
                                                  "caller (another session's lease)."),
        "server_wide_modules": {"type": "array", "items": {"type": "string"},
                                "description": "Server-wide modules the catalog row declared when the "
                                               "lease was acquired (empty = none). instance_build and "
                                               "instance_serve load them together with the series' "
                                               "core default; you never pass --load."},
        "built": {"type": "object", "required": ["demo", "languages"],
                  "description": "What builds on THIS lease put into its database. Another lease "
                                 "on the same database may have built more: the "
                                 "INSTANCE_HANDLE's demo / languages_loaded state the database's "
                                 "facts, from every lease on it.",
                  "properties": {
                      "demo": {"type": ["boolean", "null"],
                               "description": "true = a build ran with demo on (demo data stays "
                                              "once loaded); false = every recorded build ran "
                                              "with demo off; null = no build recorded it."},
                      "languages": {"type": "array", "items": {"type": "string"},
                                    "description": "Languages a finished build proved loaded "
                                                   "(job_wait languages_loaded), accumulated."}}},
        "session_alive": {"type": ["boolean", "null"],
                          "description": "Whether the Claude Code session the lease records is still "
                                         "running - measured for every anchored lease, parked and "
                                         "shared ones included: true = running, false = ended (a "
                                         "lease of YOUR run from an earlier session: lease_adopt "
                                         "it). null = the lease records no session, or its "
                                         "liveness cannot be proven (e.g. recorded on another "
                                         "host)."},
        "served": {"type": "boolean", "description": "A live server process is bound to this lease "
                                                     "on this host (not parked)."},
        "http_port": dict(_NULLABLE_INT, description="Port the bound server listens on; null unless "
                                                     "served."),
        "url": dict(_NULLABLE_STR, description="Base URL of the bound server (http://localhost:<port>); "
                                               "null unless served."),
    },
}

HANDLE_SCHEMA = {
    "type": "object",
    "required": list(HANDLE_FIELDS),
    "properties": {
        "db_name": {"type": "string"},
        "http_port": _NULLABLE_INT,
        "gevent_port": _NULLABLE_INT,
        "db_port": {"type": "string"},
        "addons_path": {"type": "string"},
        "venv_python": {"type": "string"},
        "demo": {"type": ["boolean", "null"],
                 "description": "Whether the DATABASE holds demo data (a fact of the database, a "
                                "forwarded one included): read from it (any installed module with "
                                "demo loaded), else as the builds of every lease on it recorded "
                                "(see facts_source); null = not known."},
        "languages_loaded": {"type": ["array", "null"], "items": {"type": "string"},
                             "description": "Languages active in the DATABASE: read from it, else "
                                            "those a finished build on it proved loaded (see "
                                            "facts_source); null = none known yet."},
        "facts_source": {"type": "string", "enum": [FACTS_FROM_DATABASE, FACTS_FROM_LEASES],
                         "description": "Who answered demo / languages_loaded: database = read "
                                        "from the database itself; leases = it could not be "
                                        "read, so the build records of every lease on it."},
        "log_path": _NULLABLE_STR,
        "lease_token": _NULLABLE_STR,
        "run_id": {"type": "string"},
        "server_pid": _NULLABLE_INT,
    },
}

SERIES_PROP = {"type": "string", "minLength": 1,
               "description": "Odoo series as X.Y (e.g. 17.0). Required: nothing is picked for you. "
                              "catalog_read lists the declared series."}
LEASE_TOKEN_PROP = {"type": "string", "minLength": 8,
                    "description": "The FULL lease token (never the 8-char token_prefix): lease.token "
                                   "from your lease_acquire, INSTANCE_HANDLE.lease_token, or a "
                                   "lease_list(scope mine) row."}
NO_RUN_ID = ("If nobody gave you a run id, OMIT this field - the call then fails with RUN_ID_REQUIRED, "
             "whose remedy is to report NEEDS_CONTEXT(RUN_ID); never invent one.")
RUN_ID_PROP = {"type": "string", "minLength": 1,
               "description": "The run id that owns the lease: the run_id you were given "
                              "(INSTANCE_HANDLE.run_id, or the run_id you passed to lease_acquire). "
                              "If you have none, the lease is not yours to change: do not call this "
                              "tool, report NEEDS_CONTEXT(RUN_ID); never invent one."}
CWD_OPT_PROP = {"type": "string", "minLength": 1,
                "description": "Absolute path of your working tree. Decides which project-local "
                               "catalog is the fallback when no machine-global catalog declares an "
                               "instance. Omit to use the server's working directory."}
PROFILE_PROP = {"type": "string",
                "description": "Catalog profile name when the series declares several instances; "
                               "omit for the unprofiled one."}


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _cwd(args, key="cwd"):
    cwd = args.get(key) or os.getcwd()
    if not os.path.isabs(cwd):
        raise ToolError("INVALID_ARGUMENTS", "arguments.%s: must be an absolute path, got %r" % (key, cwd))
    if not os.path.isdir(cwd):
        raise ToolError("PATH_NOT_DIRECTORY", "arguments.%s is not a directory: %s" % (key, cwd), {key: cwd})
    return cwd


def list_rows(extra_args, cwd=None):
    """Registry rows from `allocator.py list --show-tokens --with-verdict <extra>`."""
    env = cli.run_allocator("list", ["--show-tokens", "--with-verdict"] + list(extra_args),
                            cwd or os.getcwd(), READ_TIMEOUT_S)
    return env["fields"].get("leases") or []


def read_row(token, cwd=None):
    """The registry row whose token is EXACTLY `token`, or None."""
    for row in list_rows(["--tokens", token], cwd):
        if row.get("token") == token:
            return row
    return None


def my_tokens(cwd=None):
    """Full tokens of every lease anchored to this server's session."""
    return set(r.get("token") for r in list_rows(["--session", "mine"], cwd) if r.get("token"))


def _redact(token):
    return (token or "")[:TOKEN_PREFIX_LEN]


def _require_row(token, cwd=None):
    row = read_row(token, cwd)
    if row is None:
        raise ToolError("LEASE_NOT_FOUND", "no lease has token %s" % _redact(token),
                        {"token_prefix": _redact(token)})
    return row


def _not_owner(token, run_id):
    """NOT_OWNER without the owner's run id: naming it would hand a stranger the second half of
    what a release needs (see the module docstring's visibility rule)."""
    return ToolError("NOT_OWNER", "lease %s is owned by another run, not %r" % (_redact(token), run_id),
                     {"token_prefix": _redact(token)})


def _require_owner(row, run_id):
    owner_run = _owner_run(row)
    if owner_run and owner_run != run_id:
        raise _not_owner(row.get("token"), run_id)


def _owned_allocator_call(verb, token, run_id, argv, cwd, timeout_s):
    """cli.run_allocator for a verb the allocator gates on ownership (park, adopt): its NOT_OWNER
    refusal names the owner run in its message and stderr, so it is re-raised redacted."""
    try:
        return cli.run_allocator(verb, argv, cwd, timeout_s)
    except ToolError as exc:
        if exc.code == "NOT_OWNER":
            raise _not_owner(token, run_id)
        raise


def discloses_to_this_session(row, caller_run, mine):
    """True when lease `row`'s full token and owner run may be shown to this caller: the caller
    names the owner run (`caller_run`), AND the lease is anchored to THIS session (its token is in
    `mine`, the `list --session mine` set) or the session it records has ended
    (`_recorded_session_ended` - an owner resuming its run from a new session). A live FOREIGN
    session's lease is never disclosed, even to a caller naming its run: a run id is a guessable
    slug, and token + run id is everything lease_release needs."""
    token = row.get("token") or ""
    if not caller_run or not token or _owner_run(row) != caller_run:
        return False
    if token in mine:
        return True
    return _recorded_session_ended(row)


def _recorded_session_ended(row):
    """True when no live session vouches for `row`: it records no session anchor at all, or the
    anchor it records is PROVABLY dead (`recorded_session_state`). An anchor whose state cannot be
    proven either way (off-host, unmatchable fingerprint) is NOT ended."""
    return recorded_session_state(row) in (None, "dead")


# --------------------------------------------------------------------------- #
# handlers
# --------------------------------------------------------------------------- #
def _acquire(args, ctx):
    mode = args["mode"]
    run_id = args.get("run_id") or ""
    if not run_id and mode != "readonly":
        raise ToolError("RUN_ID_REQUIRED", "mode %s needs run_id (only readonly is lease-free)" % mode)
    if args.get("ports") and mode in ("shared", "readonly"):
        # The allocator ignores --ports for these modes: a shared lease is the declared render
        # server on the catalog's declared port, and readonly reserves nothing. Passing ports would
        # otherwise read as a reservation that silently never happened.
        raise ToolError("INVALID_ARGUMENTS",
                        "arguments.ports: mode %s reserves no pooled port - %s; omit ports (or use "
                        "mode ephemeral/exclusive to reserve one)" % (
                            mode, "the shared render server listens on the catalog's declared port"
                            if mode == "shared" else "readonly holds no lease"),
                        {"mode": mode, "ports": args["ports"]})
    cwd = _cwd(args)
    argv = ["--series", args["series"], "--mode", mode]
    if run_id:
        argv += ["--run-id", run_id]
    if args.get("ports"):
        argv += ["--ports", str(args["ports"])]
    addons = args.get("addons_path")
    if addons:
        entries = addons if isinstance(addons, list) else _addons_list(addons)
        for entry in entries:
            if not os.path.isabs(entry):
                raise ToolError("INVALID_ARGUMENTS", "arguments.addons_path: %r is not an absolute path" % entry)
        argv += ["--addons-path-override", join_addons(entries)]
    if args.get("db_name"):
        argv += ["--db-name", args["db_name"]]
    if args.get("profile"):
        argv += ["--profile", args["profile"]]
    if args.get("no_create"):
        argv.append("--no-create")
    env = cli.run_allocator("acquire", argv, cwd, ACQUIRE_TIMEOUT_S)
    lease = lease_from_envelope(env["fields"])
    lease["session_alive"] = None
    row, rows = None, []
    if lease["token"]:
        rows = list_rows([], cwd)
        row = next((r for r in rows if r.get("token") == lease["token"]), None)
        if row is not None:
            fresh = lease_from_row(row)
            for key in ("session_alive", "served", "http_port", "url"):
                lease[key] = fresh[key]
    warnings = []
    venv_missing = not lease["venv_python"]
    if venv_missing:
        warnings.append(
            "venv_missing: the catalog row for series %s%s declares no python, so this lease has no "
            "venv_python and instance_build / instance_serve will refuse it (VENV_MISSING). Build and "
            "record the venv for that series/profile (/odoo-ai-agents:odoo-setup), then lease_release "
            "this lease and lease_acquire again." % (
                lease["series"] or args["series"],
                (" profile %s" % lease["profile"]) if lease["profile"] else ""))
    handle = database_handle(row, lease, rows, cwd=cwd) if row is not None else instance_handle(lease)
    return {"lease": lease, "instance_handle": handle,
            "attached": bool(env["fields"].get("ALLOC_ATTACHED")),
            "venv_missing": venv_missing, "warnings": warnings}


def _running_jobs_for(token):
    from . import jobs
    out = []
    for rec in jobs.list_records():
        if (rec.get("meta") or {}).get("lease_token") == token:
            st = jobs.status(rec["job_id"])
            if st is not None and st["state"] == "running":
                out.append(rec["job_id"])
    return out


RELEASE_LOCK_DIR = ("runtime", "mcp-locks")
_RELEASE_LOCK_POLL_S = 0.2
# Allocator `release` outcome keys, when the allocator reports them: ALLOC_RELEASED = THIS call
# deleted the row; ALLOC_ALREADY_ABSENT = there was no such row when the allocator looked.
_RELEASED_KEY, _ABSENT_KEY = "ALLOC_RELEASED", "ALLOC_ALREADY_ABSENT"


@contextlib.contextmanager
def release_lock(token, timeout_s=RELEASE_TIMEOUT_S):
    """Serialize lease_release calls on ONE token across every odoo-local server on the machine
    (they share $ODOO_AI_HOME), so the read-then-release below is atomic: of two concurrent
    releases, exactly one sees the row and reports released, the other sees it gone (absent).

    An flock on runtime/mcp-locks/release-<sha(token)>.lock; the holder unlinks the file before
    unlocking, and a waiter that wakes on an unlinked inode retries on the fresh file - so no lock
    file outlives its release. Raises RECLAIM_IN_PROGRESS when the lock is not free in timeout_s."""
    home = cli.load_lib("paths")._home()
    lock_dir = os.path.join(home, *RELEASE_LOCK_DIR)
    os.makedirs(lock_dir, exist_ok=True)
    path = os.path.join(lock_dir, "release-%s.lock" % hashlib.sha256(token.encode("utf-8")).hexdigest()[:32])
    deadline = time.monotonic() + timeout_s
    while True:
        fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError as exc:
                    if exc.errno not in (errno.EAGAIN, errno.EACCES):
                        raise
                    if time.monotonic() >= deadline:
                        raise ToolError("RECLAIM_IN_PROGRESS",
                                        "lease %s is being released by another call right now" % _redact(token),
                                        {"token_prefix": _redact(token)})
                    time.sleep(_RELEASE_LOCK_POLL_S)
            try:
                same = os.stat(path).st_ino == os.fstat(fd).st_ino
            except FileNotFoundError:
                same = False
            if not same:
                continue  # the previous holder unlinked this inode: lock the current file instead
            try:
                yield
            finally:
                try:
                    os.unlink(path)
                except OSError:
                    pass
            return
        finally:
            os.close(fd)


def _absent(token):
    return {"status": "absent", "token_prefix": _redact(token), "stopped_jobs": [], "details": {}}


def _release(args, ctx):
    token = args["lease_token"]
    with release_lock(token):
        return _release_locked(token, args["run_id"], _cwd(args))


def _release_locked(token, run_id, cwd):
    from . import jobs
    row = read_row(token, cwd)
    if row is None:
        return _absent(token)
    _require_owner(row, run_id)
    if (row.get("verdict") or {}).get("state") == "reclaiming":
        # Checked BEFORE stopping any build job: a release/gc already owns this row.
        raise ToolError("RECLAIM_IN_PROGRESS", "lease %s is being released or reclaimed right now" % _redact(token),
                        {"token_prefix": _redact(token)})
    stopped = []
    for job_id in _running_jobs_for(token):
        ok, detail = jobs.stop(job_id)
        stopped.append({"job_id": job_id, "stopped": ok, "detail": detail})
    env = cli.run_allocator("release", [token, "--run-id", run_id], cwd, RELEASE_TIMEOUT_S)
    fields = env["fields"]
    if fields.get(_ABSENT_KEY) and not fields.get(_RELEASED_KEY):
        # The row vanished between our read and the allocator's (a Bash-CLI release or a gc).
        out = _absent(token)
        out["stopped_jobs"] = stopped
        return out
    # ALLOC_FORGOTTEN_DB -> forgotten_db, ...: what the release left behind, in tool vocabulary.
    details = {(k[len("ALLOC_"):] if k.startswith("ALLOC_") else k).lower(): v
               for k, v in fields.items() if k not in ("notes", _RELEASED_KEY, _ABSENT_KEY)}
    return {"status": "released", "token_prefix": _redact(token), "stopped_jobs": stopped,
            "details": details}


def _park(args, ctx):
    token, run_id = args["lease_token"], args["run_id"]
    cwd = os.getcwd()
    # Ownership (NOT_OWNER) and an unknown token (LEASE_NOT_FOUND) are decided by the allocator
    # itself, under its registry lock and before any signal - the ONE implementation release shares.
    # A pre-check here would only be a second copy with a race window between it and the stop.
    argv = [token, "--run-id", run_id]
    if args.get("park_ttl_s"):
        argv += ["--park-ttl", str(args["park_ttl_s"])]
    f = _owned_allocator_call("park", token, run_id, argv, cwd, RELEASE_TIMEOUT_S)["fields"]
    return {
        "token": token,
        "db_name": _text(f.get("ALLOC_DB_NAME")),
        "ports": _ports(f.get("ALLOC_PORTS")),
        "parked_at": f.get("ALLOC_PARKED_AT"),
        "park_ttl_s": int(f.get("ALLOC_PARK_TTL_S") or 0),
        "drop_on_release": str(f.get("ALLOC_DROP_ON_RELEASE")).lower() == "true",
    }


def _list_entry(row, mine):
    lease = lease_from_row(row)
    token = row.get("token") or ""
    ours = token in mine
    lease["token"] = token if ours else None
    lease["run_id"] = lease["run_id"] if ours else None
    verdict = row.get("verdict") or {}
    owner = row.get("owner") or {}
    lease.update({
        "token_prefix": _redact(token),
        "mine": ours,
        "state": _text(verdict.get("state")),
        "protected_by": _text(verdict.get("protected_by")),
        "condemn": verdict.get("condemn"),
        "condemn_auto": verdict.get("condemn_auto"),
        "server_pid": owner.get("pid") if isinstance(owner.get("pid"), int) else None,
        "parked_at": row.get("parked_at"),
        "drop_on_release": bool(row.get("drop_on_release")),
    })
    return lease


def _list(args, ctx):
    scope = args["scope"]
    run_id = args.get("run_id") or ""
    if scope == "run" and not run_id:
        raise ToolError("INVALID_ARGUMENTS", "arguments.run_id: required when scope is run")
    mine_rows = list_rows(["--session", "mine"])
    mine = set(r.get("token") for r in mine_rows if r.get("token"))
    if scope == "mine":
        rows = [r for r in mine_rows if not run_id or _owner_run(r) == run_id]
    else:
        rows = list_rows(["--run-id", run_id] if scope == "run" else [])
    return {"scope": scope, "leases": [_list_entry(r, mine) for r in rows]}


def _find(args, ctx):
    state = args["state"]
    cwd = _cwd(args)
    argv = ["--series", args["series"]]
    if state == "parked":
        argv += ["--state", "parked"]
    if args.get("run_id"):
        argv += ["--run-id", args["run_id"]]
    try:
        f = cli.run_allocator("query", argv, cwd, READ_TIMEOUT_S)["fields"]
    except ToolError as exc:
        if exc.code == "NOT_FOUND":
            return {"found": False, "state": state, "lease": None}
        raise
    return {"found": True, "state": state, "lease": found_lease(f, args.get("run_id") or "", cwd)}


def found_lease(fields, caller_run, cwd):
    """The lease a `query` envelope names, disclosed per the token visibility rule (module
    docstring, `discloses_to_this_session`)."""
    token = fields.get("ALLOC_TOKEN") or ""
    row = read_row(token, cwd) if token else None
    lease = lease_from_row(row) if row is not None else lease_from_envelope(fields)
    yours = False
    if row is not None and caller_run and _owner_run(row) == caller_run:
        yours = discloses_to_this_session(row, caller_run, my_tokens(cwd))
    lease.update({
        "token": token if (yours and token) else None,
        "run_id": caller_run if yours else None,
        "token_prefix": _redact(token),
        "yours": yours,
        "parked_at": fields.get("ALLOC_PARKED_AT"),
    })
    return lease


# The allocator's gc `action` per lease (allocator.py GC_ACTION_*): reclaim = stopped, database
# dropped when throwaway, row deleted; park = a lease resumed or adopted out of a park goes BACK to
# the park (server stopped, database + ports kept). A reclaimed-record spells park "parked".
GC_ACTIONS = ("reclaim", "park")
_GC_ACTION_ALIASES = {"parked": "park", "deleted": "reclaim"}


def _gc_action(item):
    action = _text(item.get("action"))
    return _GC_ACTION_ALIASES.get(action, action) or "reclaim"


def _gc_item(item, mine):
    ours = (item.get("token") or "") in mine
    return {
        "token_prefix": _redact(item.get("token")),
        "reason": _text(item.get("reason")),
        "db_name": _text(item.get("db_name")),
        "mode": _text(item.get("mode")),
        "run_id": _text(item.get("run_id")) if ours else None,
        "action": _gc_action(item),
        "drops_db": bool(item.get("drops_db", item.get("dropped_db"))),
    }


def _gc(args, ctx):
    dry_run = args["dry_run"]
    cwd = _cwd(args)
    argv = ["--scope", args["scope"]]
    if dry_run:
        argv.append("--dry-run")
    mine = my_tokens(cwd)  # read BEFORE a real run deletes the rows it reclaims
    f = cli.run_allocator("gc", argv, cwd, GC_TIMEOUT_S)["fields"]
    items = [i for i in ((f.get("candidates") if dry_run else f.get("reclaimed")) or []) if isinstance(i, dict)]
    # A real run lists the leases it sent back to the park separately (`parked`, tokens only):
    # they are reported as action park, never folded into - or dropped from - the reclaimed list.
    parked = [] if dry_run else [t for t in (f.get("parked") or []) if isinstance(t, str) and t]
    return {"dry_run": dry_run, "scope": args["scope"],
            "leases": [_gc_item(i, mine) for i in items],
            "parked": [_redact(t) for t in parked]}


_PREFLIGHT_VERDICT_CODES = ("NO_CREATEDB", "CREATEDB_UNDETERMINABLE", "DB_AUTH_DENIED", "DB_UNREACHABLE")


def _preflight(args, ctx):
    cwd = _cwd(args)
    argv = ["--series", args["series"]]
    if args.get("profile"):
        argv += ["--profile", args["profile"]]
    code = None
    try:
        f = cli.run_allocator("db-preflight", argv, cwd, READ_TIMEOUT_S)["fields"]
    except ToolError as exc:
        if exc.code not in _PREFLIGHT_VERDICT_CODES:
            raise
        code = exc.code
        f = exc.diagnostics.get("fields") or {}
    return {
        "series": args["series"],
        "ok": code is None,
        "code": code,
        "remedy": remedy_for(code) if code else None,
        "db_auth": _text(f.get("DB_AUTH")) or "unknown",
        "db_auth_why": _text(f.get("DB_AUTH_WHY")),
        "createdb": _text(f.get("CREATEDB")) or "undeterminable",
        "createdb_why": _text(f.get("CREATEDB_WHY")),
    }


def _adopt(args, ctx):
    token, run_id = args["lease_token"], args["run_id"]
    f = _owned_allocator_call("adopt", token, run_id, [token, "--run-id", run_id], os.getcwd(),
                              READ_TIMEOUT_S)["fields"]
    row = read_row(token)
    lease = lease_from_row(row) if row is not None else lease_from_envelope(f)
    lease["token"] = token
    return {"lease": lease, "anchor": _text(f.get(cli.ANCHOR_ENV))}


# --------------------------------------------------------------------------- #
# heartbeat
# --------------------------------------------------------------------------- #
_hb_stop = threading.Event()


def heartbeat_once():
    """`allocator.py heartbeat --session mine`: refresh seen_at on every lease of this session."""
    return cli.run_allocator("heartbeat", ["--session", "mine"], os.getcwd(), READ_TIMEOUT_S)


def _heartbeat_loop(interval_s):
    while not _hb_stop.wait(interval_s):
        try:
            touched = heartbeat_once()["fields"].get("touched") or []
            log.info("heartbeat touched %d lease(s)", len(touched))
        except ToolError as exc:
            sys.stderr.write("odoo-local: heartbeat failed: %s: %s\n" % (exc.code, exc.message))
        except Exception as exc:  # the thread must never die silently or take the server down
            sys.stderr.write("odoo-local: heartbeat crashed: %s: %s\n" % (type(exc).__name__, exc))


def start_heartbeat(interval_s=None):
    """Start the daemon heartbeat thread (never blocks shutdown). Returns the thread."""
    if interval_s is None:
        try:
            interval_s = float(os.environ.get(HEARTBEAT_ENV) or HEARTBEAT_INTERVAL_S)
        except ValueError:
            interval_s = HEARTBEAT_INTERVAL_S
    t = threading.Thread(target=_heartbeat_loop, args=(max(0.5, interval_s),),
                         name="odoo-local-heartbeat", daemon=True)
    t.start()
    return t


# --------------------------------------------------------------------------- #
# registration
# --------------------------------------------------------------------------- #
def _obj(props, required=()):
    return {"type": "object", "properties": props, "required": list(required), "additionalProperties": False}


LIST_ENTRY_SCHEMA = {
    "type": "object",
    "required": LEASE_SCHEMA["required"] + ["token_prefix", "mine", "state", "protected_by",
                                            "condemn", "condemn_auto", "server_pid", "parked_at",
                                            "drop_on_release"],
    "properties": dict(LEASE_SCHEMA["properties"], **{
        "token_prefix": {"type": "string"},
        "mine": {"type": "boolean"},
        "state": {"type": "string"},
        "protected_by": {"type": "string"},
        "condemn": _NULLABLE_STR,
        "condemn_auto": _NULLABLE_STR,
        "server_pid": _NULLABLE_INT,
        "parked_at": {"type": ["number", "null"]},
        "drop_on_release": {"type": "boolean"},
    }),
}

# A lease found by `query` (lease_find, instance_status): LEASE_SCHEMA + disclosure facts.
FOUND_LEASE_SCHEMA = {
    "type": "object",
    "required": LEASE_SCHEMA["required"] + ["token_prefix", "yours", "parked_at"],
    "properties": dict(LEASE_SCHEMA["properties"], **{
        "token_prefix": {"type": "string", "description": "First 8 chars of the token (always shown)."},
        "yours": {"type": "boolean", "description": "The run_id you passed owns this lease AND it is "
                                                    "anchored to this session or its recorded session "
                                                    "has ended - token and run_id are disclosed only "
                                                    "then."},
        "parked_at": {"type": ["number", "null"]},
    }),
}
NULLABLE_FOUND_LEASE_SCHEMA = dict(FOUND_LEASE_SCHEMA, type=["object", "null"])

GC_ITEM_SCHEMA = _obj({
    "token_prefix": {"type": "string"},
    "reason": {"type": "string", "description": "Why the allocator condemned the lease."},
    "db_name": {"type": "string"},
    "mode": {"type": "string"},
    "run_id": dict(_NULLABLE_STR, description="Owner run id; null unless the lease is this "
                                              "session's."),
    "action": {"type": "string", "description": "reclaim | park (see the tool description)."},
    "drops_db": {"type": "boolean"},
}, ["token_prefix", "reason", "db_name", "mode", "run_id", "action", "drops_db"])


def register(registry, ctx):
    registry.add(
        "lease_acquire",
        "Reserve a local Odoo database (+ ports) for your work and get the INSTANCE_HANDLE to forward. "
        "Call it ONCE per run before any build/test/serve; never build a db_name or port yourself. "
        "Modes: ephemeral (default) = your own throwaway database, dropped when you release it; "
        "exclusive = the declared database held exclusively (no isolation - say so in your report); "
        "shared = the long-lived render server many readers attach to (never dropped); readonly = "
        "coordinates of the declared instance, no lease, no token. run_id is required for every mode "
        "except readonly: pass the run id you were given; if nobody gave you one, omit it and the "
        "call fails with RUN_ID_REQUIRED (report NEEDS_CONTEXT(RUN_ID)) - never invent one. If you "
        "were forwarded an INSTANCE_HANDLE, do NOT call this - use that handle. Pass ports 1 when the "
        "instance must listen (instance_serve), 2 only for prefork, 0 for build/test only. Pass cwd = "
        "your working tree; when it is a worktree, pass addons_path = the catalog row's addons_path "
        "with the entry that covers this repo replaced by your worktree path, or the call is "
        "refused (ADDONS_PATH_WORKTREE_MISMATCH). Returns lease (keep lease.token and "
        "lease.run_id) and instance_handle (forward it verbatim to downstream agents). "
        "venv_missing=true (explained in warnings) means the catalog declares no python for that "
        "series/profile: builds and serves on this lease will be refused until the venv is built - "
        "release it, build the venv, acquire again. What you acquire you must lease_release (or "
        "lease_park) before you finish - except a shared lease: it is multi-reader, needs no "
        "teardown, and lease_gc reclaims it once its server is gone.",
        _obj({
            "series": SERIES_PROP,
            "mode": {"type": "string", "enum": ["ephemeral", "exclusive", "shared", "readonly"],
                     "default": "ephemeral",
                     "description": "ephemeral (isolated throwaway db, default) | exclusive | shared | "
                                    "readonly. See the tool description for which to choose."},
            "run_id": {"type": "string", "minLength": 1,
                       "description": "Owning run id (required unless mode is readonly): the id you were "
                                      "given. " + NO_RUN_ID},
            "cwd": {"type": "string", "minLength": 1,
                    "description": "Absolute path of YOUR working tree (the tree you build). Used for "
                                   "the worktree/addons_path check and the project catalog fallback."},
            "ports": {"type": "integer", "minimum": 0, "maximum": MAX_PORTS, "default": 0,
                      "description": "Pooled ports to reserve: 0 build/test only, 1 to serve (HTTP), 2 "
                                     "for prefork (HTTP + gevent/longpolling). ephemeral/exclusive "
                                     "only: shared uses the catalog's declared port and readonly "
                                     "reserves nothing, so a non-zero value there is refused."},
            "addons_path": {"type": ["string", "array"], "items": {"type": "string"},
                            "description": "The addons directories to build and serve (absolute paths; a "
                                           "list, or one comma-joined string). Omit to use the catalog's; "
                                           "when working in a worktree, pass the catalog row's "
                                           "addons_path with only the entry that covers this repo "
                                           "replaced by your worktree path - a path that drops the "
                                           "Odoo checkout's core addons is refused."},
            "db_name": {"type": "string", "minLength": 1,
                        "description": "exclusive/shared only: the database to hold; omit for the "
                                       "declared one. Ignored by ephemeral (a unique name is minted)."},
            "profile": PROFILE_PROP,
            "no_create": {"type": "boolean", "default": False,
                          "description": "true when you will create NO database (skips the CREATEDB and "
                                         "authentication probes, and nothing is dropped at release)."},
        }, ["series", "cwd"]),
        _obj({"lease": LEASE_SCHEMA, "instance_handle": HANDLE_SCHEMA, "attached": {"type": "boolean"},
              "venv_missing": {"type": "boolean"},
              "warnings": {"type": "array", "items": {"type": "string"}}},
             ["lease", "instance_handle", "attached", "venv_missing", "warnings"]),
        _acquire, title="Acquire an Odoo instance lease", long_running=True, destructive=False,
    )
    registry.add(
        "lease_release",
        "Release a lease YOU acquired: stops its server process group (and any instance_build job still "
        "running on it), then drops its database when the lease is ephemeral, and deletes the lease. "
        "Call it once you no longer need the instance and before you report your final status. "
        "Never release a shared lease as teardown: that stops the render server under every reader "
        "- only when the user explicitly asks to stop it. "
        "Only the run that acquired a lease may release it (NOT_OWNER otherwise) - a lease that reached "
        "you as a forwarded INSTANCE_HANDLE is NOT yours: leave it for the agent that acquired it. "
        "status 'released' = THIS call released it (details.forgotten_db names a database that was "
        "already gone); 'absent' = no such lease (already released, possibly by a concurrent call), "
        "nothing to do. Concurrent releases of one token are serialized: exactly one reports released. "
        "DROP_FAILED_KEPT means the database survived and the lease was kept: follow the remedy. "
        "To keep the database for later instead of dropping it, call lease_park.",
        _obj({"lease_token": LEASE_TOKEN_PROP, "run_id": RUN_ID_PROP, "cwd": CWD_OPT_PROP},
             ["lease_token", "run_id"]),
        _obj({
            "status": {"type": "string", "enum": ["released", "absent"]},
            "token_prefix": {"type": "string"},
            "stopped_jobs": {"type": "array", "items": {"type": "object"}},
            "details": {"type": "object"},
        }, ["status", "token_prefix", "stopped_jobs", "details"]),
        _release, title="Release an Odoo instance lease", long_running=True, destructive=True,
    )
    registry.add(
        "lease_park",
        "Suspend a lease you acquired: stops its server when one runs (frees RAM) and keeps its "
        "database, filestore, ports and build facts, so a later run can resume it with instance_serve "
        "instead of rebuilding - a lease that was built but never served parks too (nothing to "
        "stop). Use it instead of lease_release when the built database is worth keeping; "
        "lease_find(state parked, run_id yours) finds it again. Only the owning run may park "
        "(NOT_OWNER otherwise); a lease already parked is refused (NOT_RUNNING) and a shared lease "
        "cannot be parked. "
        "drop_on_release=true in the result means the final lease_release still drops the database: "
        "parking defers the drop, it never makes the database permanent.",
        _obj({"lease_token": LEASE_TOKEN_PROP, "run_id": RUN_ID_PROP,
              "park_ttl_s": {"type": "integer", "minimum": 60,
                             "description": "How long the parked lease is kept before gc may reclaim it, "
                                            "in seconds; omit for the default (48h)."}},
             ["lease_token", "run_id"]),
        _obj({
            "token": {"type": "string"},
            "db_name": {"type": "string"},
            "ports": {"type": "array", "items": {"type": "integer"}},
            "parked_at": {"type": ["number", "null"]},
            "park_ttl_s": {"type": "integer"},
            "drop_on_release": {"type": "boolean"},
        }, ["token", "db_name", "ports", "parked_at", "park_ttl_s", "drop_on_release"]),
        _park, title="Park an Odoo instance lease", long_running=True, destructive=True,
    )
    registry.add(
        "lease_list",
        "List leases with their liveness verdict. scope mine (default) = every lease anchored to THIS "
        "Claude Code session (yours and your sibling subagents'); scope run = leases owned by run_id; "
        "scope all = the whole machine. The full token and run_id are returned only for this session's "
        "leases (mine=true); any other lease shows token=null, run_id=null and its 8-char "
        "token_prefix. Being listed as "
        "mine does NOT make a lease yours to release: release/park only leases whose run_id is yours. "
        "session_alive=true means the session the lease records still runs (false = it ended, "
        "null = none recorded or unprovable); "
        "condemn names why an explicit gc would reclaim it (null = protected); served/url give a "
        "running server's address. Read-only; call it to recover your token after losing it, or to "
        "audit what your run still holds before finishing.",
        _obj({
            "scope": {"type": "string", "enum": ["mine", "run", "all"], "default": "mine",
                      "description": "mine (this session) | run (owned by run_id) | all (machine)."},
            "run_id": {"type": "string", "minLength": 1,
                       "description": "Owning run id: required for scope run; with scope mine it narrows "
                                      "to that run's leases. " + NO_RUN_ID},
        }),
        _obj({"scope": {"type": "string"}, "leases": {"type": "array", "items": LIST_ENTRY_SCHEMA}},
             ["scope", "leases"]),
        _list, title="List Odoo instance leases", read_only=True,
    )
    registry.add(
        "lease_find",
        "Find an existing instance to reuse for a series instead of building a new one. state shared "
        "(default) = the live shared render server: read lease.served / lease.url (its base URL) and "
        "attach with instance_serve(series) - a reader never needs its token. state parked = a parked "
        "(suspended) lease: pass YOUR run_id. The full token and run_id come back (yours=true) only "
        "when the lease is your run's AND it is anchored to this session or its session has ended; "
        "then resume it with instance_serve(lease_token), after lease_adopt when it came from an "
        "earlier session (session_alive=false). A lease of another run, or of your run held by "
        "another LIVE session, shows token=null and run_id=null (only its 8-char token_prefix): "
        "serve or read it, never release or park it. found=false is a normal answer: acquire your "
        "own. Read-only.",
        _obj({"series": SERIES_PROP,
              "state": {"type": "string", "enum": ["shared", "parked"], "default": "shared",
                        "description": "shared (live render server) | parked (suspended, resumable)."},
              "run_id": {"type": "string", "minLength": 1,
                         "description": "Your run id: a parked lease of your own run is preferred, and "
                                        "only a lease your run owns (anchored to this session, or "
                                        "to one that has ended) is returned with its full token. "
                                        + NO_RUN_ID},
              "cwd": CWD_OPT_PROP}, ["series"]),
        _obj({"found": {"type": "boolean"}, "state": {"type": "string"},
              "lease": NULLABLE_FOUND_LEASE_SCHEMA}, ["found", "state", "lease"]),
        _find, title="Find a reusable Odoo instance", read_only=True, long_running=True,
    )
    registry.add(
        "lease_gc",
        "Report (dry_run true, the default) or reclaim (dry_run false) leases whose owner is provably "
        "gone. scope dead-sessions (default) = only leases of ended sessions (after a grace window), "
        "dead/recycled server pids, and expired parks - never a live session's lease; scope all also "
        "applies the long TTL arm to leases whose liveness cannot be proven. Reclaiming stops the "
        "server and DROPS throwaway databases: run dry_run first, show the user the list, and call "
        "with dry_run false only when the user asked for the cleanup. Each lease carries action: "
        "reclaim (stopped, throwaway database dropped, lease deleted) or park (a lease resumed out of "
        "a park goes back to the park: server stopped, database and ports kept); a real run lists "
        "the re-parked leases' token prefixes in parked. run_id is shown only for this session's "
        "leases. You never need it to free your own lease - use lease_release.",
        _obj({"dry_run": {"type": "boolean", "default": True,
                          "description": "true (default): list what would be reclaimed, change nothing. "
                                         "false: reclaim them."},
              "scope": {"type": "string", "enum": ["dead-sessions", "all"], "default": "dead-sessions",
                        "description": "dead-sessions (safe default) | all (also the TTL arm)."},
              "cwd": CWD_OPT_PROP}),
        _obj({"dry_run": {"type": "boolean"}, "scope": {"type": "string"},
              "leases": {"type": "array", "items": GC_ITEM_SCHEMA},
              "parked": {"type": "array", "items": {"type": "string"},
                         "description": "Token prefixes a real run sent back to the park (empty on "
                                        "a dry run: those show as action park in leases)."}},
             ["dry_run", "scope", "leases", "parked"]),
        _gc, title="Garbage-collect dead Odoo leases", long_running=True, destructive=True,
    )
    registry.add(
        "db_preflight",
        "Check, without writing anything, whether Odoo can authenticate to the series' Postgres cluster "
        "(db_auth ok|denied|unreachable|unknown) and whether its role may create databases (createdb "
        "true|false|undeterminable) - the same probes lease_acquire gates on. ok=false names the "
        "blocking code (DB_AUTH_DENIED, DB_UNREACHABLE, NO_CREATEDB, CREATEDB_UNDETERMINABLE) and "
        "remedy says how to fix it; db_auth_why / createdb_why carry the probe's own reason. Call it "
        "to diagnose a refused lease_acquire or before provisioning on a new machine. Read-only.",
        _obj({"series": SERIES_PROP, "profile": PROFILE_PROP, "cwd": CWD_OPT_PROP}, ["series"]),
        _obj({
            "series": {"type": "string"},
            "ok": {"type": "boolean"},
            "code": _NULLABLE_STR,
            "remedy": _NULLABLE_STR,
            "db_auth": {"type": "string"},
            "db_auth_why": {"type": "string"},
            "createdb": {"type": "string"},
            "createdb_why": {"type": "string"},
        }, ["series", "ok", "code", "remedy", "db_auth", "db_auth_why", "createdb", "createdb_why"]),
        _preflight, title="Postgres preflight for a series", read_only=True, long_running=True,
    )
    registry.add(
        "lease_adopt",
        "Re-anchor a lease your run owns onto THIS session, so it stays protected while this session "
        "lives. Call it only when you continue a run in a NEW Claude Code process (a resumed session "
        "whose earlier leases show session_alive=false in lease_list, or a hand-over between "
        "processes of the same run); lease_find(state parked, run_id yours) returns the full token of "
        "your run's parked lease once its earlier session has ended. Adopt a parked lease from an "
        "earlier session BEFORE instance_serve resumes it (instance_serve refuses it otherwise, "
        "LEASE_NOT_ADOPTED). Requires the owning run_id (NOT_OWNER otherwise); changes nothing but "
        "who vouches for the lease's liveness.",
        _obj({"lease_token": LEASE_TOKEN_PROP, "run_id": RUN_ID_PROP}, ["lease_token", "run_id"]),
        _obj({"lease": LEASE_SCHEMA, "anchor": {"type": "string"}}, ["lease", "anchor"]),
        _adopt, title="Adopt a lease into this session", destructive=False, idempotent=True,
    )
