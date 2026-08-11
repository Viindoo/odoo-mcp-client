"""odoo_db.py - Ask Postgres every DB question THROUGH Odoo (never a raw client).

This is the SSOT for DB-lifecycle operations that must honour Odoo's own
connection-pool shutdown, filestore cleanup, and registry teardown, AND for
every read-only question about the cluster (may this role CREATE DATABASE, which
databases exist, how old / how big is one). It is a standalone script run
UNDER the target instance's venv python, which supplies psycopg2 and the series'
own dependencies.

Running under that venv is NOT by itself enough to make ``import odoo`` resolve:
a source-only checkout is never pip-installed, and ``odoo-bin`` works only
because it puts the repo root on ``sys.path[0]`` at startup. Pass
``--odoo-root <checkout-root>`` (the DECLARED ``odoo_root`` of the
``[[instance]]``, recorded by 45-venv.sh from the repo whose odoo-bin was proven
runnable) and this script does the same. Without it, a source instance exits 10.

CLI contract
------------
  python3 odoo_db.py drop   <db> [--db-host H] [--db-user U] [--db-port P] [--db-password P]
                                 [--odoo-root R]
      Drop the database through ``odoo.service.db.exp_drop``.
      Threads --db-port into parse_config as --db_port ONLY when non-empty (empty
      -> omit; libpq/PGPORT resolves it - never fabricate 5432).
      Emits an observability line to stderr on every drop naming the RESOLVED
      host:port and whether the drop was performed or the DB was already-absent.
      Exit 0 on success OR if the DB is already absent (idempotent).
      Exit 1 on any Odoo-level failure (message on stderr).
      Exit 2 on usage / argument error (INCLUDING an unrecognized --flag).
      Exit 10 when the Odoo package cannot be imported (``odoo_db: cannot import
               odoo (no venv?)`` on stderr) - "venv unavailable" sentinel for
               callers (e.g. allocator.py) that want to apply their own fallback.

  python3 odoo_db.py exists <db> [--db-host H] [--db-user U] [--db-port P] [--db-password P]
                                 [--odoo-root R]
      Print ``true`` or ``false`` (lowercase) to stdout.
      Exit 0 always (even when the DB does not exist).
      Exit 2 on usage error.
      Exit 10 on venv unavailable (as above).
      A non-zero exit doubles as the cluster-REACHABILITY probe (opening the
      connection IS the probe - no pg_isready needed).

  python3 odoo_db.py preflight [--db-host H] [--db-user U] [--db-port P]
                               [--db-password P] [--odoo-root R]
      CAN ODOO AUTHENTICATE? Opens the maintenance-database connection through
      ``odoo.sql_db.db_connect('postgres')`` - the EXACT route every build takes,
      because Odoo's CLI opens that connection for every ``-d <name>`` run before
      any module loads. So this is a precondition of init / update / test alike,
      not of a create alone.
      stdout (shell-eval-able):
          DB_AUTH=ok|denied|unreachable|unknown
          DB_AUTH_WHY=<one line, never carrying a credential value>
      Exit 0 ok, 8 denied, 9 unreachable, 1 unknown, 10 venv unavailable.
      On any non-ok state it writes the refusal block to stderr. That text is
      OWNED here: every caller forwards these bytes verbatim instead of composing
      a second copy of the verdict.

  python3 odoo_db.py can-createdb [--db-host H] [--db-user U] [--db-port P]
                                  [--db-password P] [--odoo-root R]
      Print ``true`` or ``false``: may the connecting role CREATE DATABASE?
      A LIVE privilege query, never an inference from which binaries are
      installed. Exit 0 when answered, 8 when Odoo was refused authentication,
      9 when the cluster did not answer at all, 1 when the question could not be
      answered for any other reason (no pg_roles row), 10 on venv unavailable.
      Callers MUST keep "answered false" and "could not answer" distinct - see
      allocator.py exits 6 and 7 - and MUST keep 8 and 9 distinct from both:
      they are facts about the CONNECTION, so no other surface may overrule them.

  python3 odoo_db.py list-databases [--db-host H] [--db-user U] [--db-port P]
                                    [--db-password P] [--odoo-root R]
      Print one non-template datname per line. Exit 1 on any failure with
      NOTHING on stdout, so "could not enumerate" is never read as "zero
      databases".

  python3 odoo_db.py db-age-s <db> [conn flags] [--odoo-root R]
      Print the seconds since the database directory's PG_VERSION mtime (the
      only creation-time proxy Postgres offers). Exit 1 when unmeasurable
      (pg_stat_file needs elevated privilege on many builds) - callers MUST
      treat that as unknown, never as "just created".

  python3 odoo_db.py db-size-bytes <db> [conn flags] [--odoo-root R]
      Print pg_database_size in bytes. Exit 1 on any failure. Reporting only.

Password resolution (mirrors allocator._pg_env)
-------------------------------------------------
  1. --db-password CLI flag (highest priority)
  2. ODOO_PG_PASSWORD env var
  3. ``${PGPASSFILE:-~/.pgpass}`` - Odoo omits the password from its connection
     entirely when ``db_password`` is unset, so libpq resolves it from this file
     itself. This script NEVER writes that file; it only READS it, so the
     preflight can decide "no credential is resolvable at all" without parsing a
     libpq message that may be localised.
  4. Nothing set - the connection carries no password (trust / peer auth).

Namespace compatibility
-----------------------
  Odoo >= v10: ``import odoo``            / ``odoo.service.db`` / ``odoo.tools.config``
  Odoo  v8-v9: ``import openerp as odoo`` / ``openerp.service.db`` / ``openerp.tools.config``
  The guard ``config['list_db'] = True`` is set before calling ``exp_drop`` /
  ``exp_db_exist`` so the ``@check_db_management_enabled`` decorator (v10+) is a
  no-op. The flag is harmless on v8/v9 which have no such guard.
  ``.tools``, ``.service.db`` and ``.sql_db`` are imported explicitly (via
  ``importlib``) because a bare base-package import no longer binds them as
  attributes on Odoo 19.0.

NEVER calls raw ``dropdb`` / ``psql`` / ``createdb``. All DB destruction goes
through ``odoo.service.db.exp_drop`` which handles connection-pool teardown,
filestore removal, and registry cleanup in a single atomic step; every read-only
question goes through ``odoo.sql_db.db_connect`` so it resolves the connection
EXACTLY like drop/exists do - one resolution path, never a second hand-rolled
psycopg2 call that could target a different cluster.
"""

from __future__ import print_function

import os
import sys

# ---- Exit codes (contract) ----
EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_USAGE = 2
EXIT_NO_VENV = 10  # "venv unavailable" sentinel - callers may detect this
# Facts about the CONNECTION, kept distinct from EXIT_FAILURE so a caller can
# tell "the drop was never attempted" from "the drop was attempted and failed",
# and "this route is unavailable" from "this route works and the cluster refused
# us". Collapsing either pair is what let a capability probe validate a route the
# build never uses.
EXIT_AUTH_DENIED = 8
EXIT_UNREACHABLE = 9

# SQLSTATE class 28 - invalid authorization specification. The server ANSWERED,
# so this verdict holds whatever language its messages are in.
#
# REACHABILITY, measured rather than assumed (psycopg2 2.9.12, PostgreSQL over
# TCP, LC_MESSAGES=C): a failed ``connect()`` produces NO PGresult, so psycopg2
# has no SQLSTATE to attach and the exception arrives as a bare OperationalError
# with ``pgcode is None`` and ``diag.sqlstate is None`` - for a genuine 28P01
# ("password authentication failed for user ...") exactly as for a refused TCP
# connection. This rule therefore fires only for a failure the server reported
# about a STATEMENT (the read-only queries below run after the handshake
# completed), never for the handshake itself. It is kept because that case is
# real, but it is NOT what makes this classifier locale-independent: rule 3 is
# (a fact computed here), while rules 2 and 4 read libpq's own C-locale strings.
_AUTH_PGCODES = frozenset(("28000", "28P01", "28P02"))

# Bounded signature tables over libpq's own UNTRANSLATED strings. LC_MESSAGES is
# pinned to C before connecting (see _pin_c_messages) so these are the strings
# libpq actually emits. Lowercase - matching is case-folded.
_DENIED_SIGNATURES = (
    "password authentication failed",
    "no password supplied",
    "no pg_hba.conf entry",
    "peer authentication failed",
    "ident authentication failed",
)
_UNREACHABLE_SIGNATURES = (
    "could not connect to server",
    "connection refused",
    "could not translate host name",
    "timeout expired",
    "is the server running",
    "server closed the connection unexpectedly",
    "no route to host",
)

# Failures the SERVER raised while accepting the connection that have NOTHING to
# do with credentials. Each row is a tuple of substrings that must ALL be present
# (case-folded), so "database ... does not exist" (SQLSTATE 3D000) can be named
# without also matching `role "x" does not exist`, which IS a credential fact.
#
# This table exists for exactly one reason: rule 3 below infers `denied` from a
# LOCAL fact - that no credential could be offered at all - which on the default
# developer setup (native trust cluster, no --db-password, no $ODOO_PG_PASSWORD,
# no ~/.pgpass) is permanently true. Without this guard every such failure became
# `denied` -> exit 8 -> a BLOCKED build advised to fix an authentication problem
# it does not have, where the previous release let the build run and let Odoo
# report the real error.
_SERVER_REFUSED_SIGNATURES = (
    ("too many connections",),
    ("remaining connection slots",),
    ("connection limit exceeded",),
    ("the database system is starting up",),
    ("the database system is shutting down",),
    ("the database system is in recovery mode",),
    ("out of memory",),
    ("database", "does not exist"),
)


# ---- Arg parsing (stdlib only, no argparse to mirror allocator/instances_io style) ----
_FLAG_KEYS = {
    "--db-host": "db_host",
    "--db-user": "db_user",
    "--db-port": "db_port",
    "--db-password": "db_password",
    "--odoo-root": "odoo_root",
}


def _parse(argv):
    """Return (opts: dict, positional: list, unknown: list).

    An unrecognized ``--``-prefixed token is collected into ``unknown`` (the
    caller turns that into a hard usage error) instead of being silently
    swallowed as a positional - a database name never starts with ``--``, so no
    legitimate positional is rejected.
    """
    opts, pos, unknown = {}, [], []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in _FLAG_KEYS:
            opts[_FLAG_KEYS[a]] = argv[i + 1] if i + 1 < len(argv) else ""
            i += 2
        elif a.startswith("--"):
            unknown.append(a)
            i += 1
        else:
            pos.append(a)
            i += 1
    return opts, pos, unknown


# ---- Odoo import + config bootstrap ----

def _apply_odoo_root(opts):
    """Make ``import odoo`` resolve for a SOURCE checkout, the way odoo-bin does.

    A venv built for a source checkout does NOT pip-install the package: odoo-bin
    only works because it puts the repo root on ``sys.path[0]`` at startup. This
    script is not odoo-bin, so without this the import fails on every source
    instance and the caller takes a fallback it should never have needed. The
    root is a DECLARED fact (``odoo_root`` on the ``[[instance]]``, recorded by
    45-venv.sh from the very repo whose odoo-bin was proven runnable); absent ->
    behave exactly as before (bare import, EXIT_NO_VENV when it fails).
    """
    root = opts.get("odoo_root")
    if root and os.path.isdir(root) and root not in sys.path:
        sys.path.insert(0, root)


def _import_odoo(opts=None):
    """Import the Odoo package (supports the openerp v8/v9 namespace) AND the
    submodules this script dereferences.

    A bare ``import odoo`` does NOT guarantee ``odoo.tools`` / ``odoo.service``
    are bound as attributes (Odoo 19.0 no longer binds them transitively), so we
    import the submodules EXPLICITLY, via the RESOLVED package name so the
    ``openerp`` (v8/v9) namespace is handled too. Returns the odoo/openerp
    module, or raises ImportError if the base package is not present.

    ``opts`` is threaded in so ``--odoo-root`` is applied here, at the SINGLE
    place the import happens - every subcommand present and future gets the
    source-checkout sys.path insert with no second call site to keep in sync.
    """
    _apply_odoo_root(opts or {})
    try:
        import odoo
    except ImportError:
        try:
            import openerp as odoo  # v8/v9
        except ImportError:
            raise ImportError("neither 'odoo' nor 'openerp' is importable")
    # Base package resolved. Bind the submodules this script uses so
    # ``odoo.tools.config`` (line ~104) and ``odoo.service.db`` (line ~131) are
    # always available on every series v8-v19.
    import importlib
    pkg = odoo.__name__  # 'odoo' or 'openerp'
    importlib.import_module(pkg + ".tools")       # ensures <pkg>.tools.config  (fixes #154)
    importlib.import_module(pkg + ".service.db")  # hardens the sibling <pkg>.service.db deref
    return odoo


def _bootstrap_config(odoo, opts):
    """Call parse_config with the PG connection flags present in opts.

    After parse_config we force ``config['list_db'] = True`` so that
    @check_db_management_enabled (v10+) does not block exp_drop/exp_db_exist.
    """
    config = odoo.tools.config

    # Build the minimal arg list accepted by Odoo's option parser.
    # Odoo uses --db_host / --db_user / --db_password (underscore, not hyphen).
    args = []
    if opts.get("db_host"):
        args += ["--db_host", opts["db_host"]]
    if opts.get("db_user"):
        args += ["--db_user", opts["db_user"]]
    # Postgres port: thread through ONLY when declared. Empty -> omit the flag so
    # libpq / PGPORT / the compiled default resolve it (Odoo's own default is
    # "omit", not 5432 - fabricating 5432 would override a legit PGPORT setup).
    if opts.get("db_port"):
        args += ["--db_port", str(opts["db_port"])]

    # Password: CLI flag wins over env var
    pw = opts.get("db_password") or os.environ.get("ODOO_PG_PASSWORD")
    if pw:
        args += ["--db_password", pw]

    # parse_config sets up the logger, sys-path, etc.
    config.parse_config(args)

    # Bypass @check_db_management_enabled (v10+); no-op on v8/v9.
    config["list_db"] = True


# ---- Commands ----

def _get_service_db(odoo):
    """Return odoo.service.db (or openerp.service.db for v8/v9) using the already-
    imported namespace object returned by _import_odoo()."""
    return odoo.service.db


def _sql_connect_postgres(odoo):
    """A connection to the maintenance database through Odoo's OWN connection
    layer (odoo.sql_db, openerp.sql_db on v8-v9), so every question asked here
    resolves the connection EXACTLY like drop/exists do - one resolution path,
    never a second psycopg2 call with hand-rolled parameters. Imported via the
    RESOLVED package name (importlib) for the same reason ``.tools`` and
    ``.service.db`` are: a bare base-package import does not bind submodules."""
    import importlib
    return importlib.import_module(odoo.__name__ + ".sql_db").db_connect("postgres")


def _pin_c_messages():
    """Pin message translation to C for THIS process before any connection is
    opened.

    libpq translates its own diagnostics, so the signature tables above would only
    match on an English host - and the classification a build depends on would
    then be decided by the operator's locale. Pinning makes the untranslated
    strings the ones that arrive.

    All THREE variables are needed, because LC_MESSAGES alone is not the top of
    the precedence chain: LC_ALL outranks it in POSIX and in glibc, and LANGUAGE
    outranks both whenever the resolved locale is not C. With `LC_ALL=de_DE.UTF-8
    LC_MESSAGES=C` the resolved LC_MESSAGES is de_DE.UTF-8 and the pin does
    nothing at all.
    LC_ALL is overwritten only when it is ALREADY set: setting it unconditionally
    would additionally pin LC_NUMERIC / LC_CTYPE for a process that asked for
    neither. LANGUAGE affects message translation ONLY, so clearing it is exactly
    scoped to the thing being pinned.
    """
    os.environ["LC_MESSAGES"] = "C"
    if os.environ.get("LC_ALL"):
        os.environ["LC_ALL"] = "C"
    os.environ["LANGUAGE"] = ""


def _pgpass_path():
    return os.environ.get("PGPASSFILE") or os.path.join(
        os.path.expanduser("~"), ".pgpass")


def _pgpass_fields(line):
    """Split ONE pgpass line into its 5 fields, honouring backslash escaping.

    libpq escapes a literal ``:`` or ``\\`` inside a field with a backslash, so a
    naive split misreads such a line and would report a matching entry as absent.
    """
    fields, cur, esc = [], [], False
    for ch in line:
        if esc:
            cur.append(ch)
            esc = False
        elif ch == "\\":
            esc = True
        elif ch == ":":
            fields.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    fields.append("".join(cur))
    return fields


def _pgpass_has_entry(host, port, user):
    """Does ``${PGPASSFILE:-~/.pgpass}`` carry a line that could serve this
    connection? READ-ONLY: this script never writes that file.

    Consulted only so the classifier can decide "no credential is resolvable at
    all" from a FACT it computed itself, rather than from a libpq message whose
    wording is not a contract. A missing or unreadable file is False - never an
    exception, and never a guess in the other direction.

    An empty host means the connection carries no host at all (libpq resolves it),
    so a loopback entry is accepted for it; anything wider than that would have to
    be guessed.
    """
    path = _pgpass_path()
    try:
        with open(path, "r") as fh:
            lines = fh.read().splitlines()
    except (IOError, OSError):
        return False
    host_ok = (host,) if host else ("localhost", "127.0.0.1", "::1")
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        fields = _pgpass_fields(line)
        if len(fields) < 5:
            continue
        f_host, f_port, _f_db, f_user = fields[0], fields[1], fields[2], fields[3]
        if f_host != "*" and f_host not in host_ok:
            continue
        if f_port != "*" and port and f_port != str(port):
            continue
        if f_user != "*" and f_user != user:
            continue
        return True
    return False


def _credential_resolvable(opts):
    """Can ANY credential reach libpq for this connection?

    The three rungs are the whole of the resolution order: the flag, the plugin's
    own env knob, then the file libpq reads by itself. None of them present means
    the connection is offered no password at all - which is why a server that
    demands one rejects it with a message carrying no SQLSTATE.
    """
    if opts.get("db_password") or os.environ.get("ODOO_PG_PASSWORD"):
        return True
    return _pgpass_has_entry(
        opts.get("db_host") or "", opts.get("db_port") or "",
        opts.get("db_user") or "")


def _exc_detail(exc):
    """One line naming the exception type and its first message line.

    First line only: a psycopg2 diagnostic can carry several, and DB_AUTH_WHY is a
    single shell-eval-able line.
    """
    text = str(exc).strip()
    first = text.splitlines()[0] if text else ""
    return "{etype}: {msg}".format(etype=type(exc).__name__, msg=first)


def _server_refused_for_another_reason(low):
    """Does this message name a SERVER-reported failure that is not about
    credentials? `low` is the case-folded exception text.

    True means the server answered and said WHY, and the reason was not a
    credential - so no inference about credentials may be drawn from it.
    """
    for row in _SERVER_REFUSED_SIGNATURES:
        if all(part in low for part in row):
            return True
    return False


def _classify_conn_error(exc, opts):
    """('denied'|'unreachable'|'unknown', detail) for a failed connection.

    Ordered, and the order is the contract:
      1. SQLSTATE class 28 -> denied. The server answered; no message is read.
         Reachable only for a STATEMENT failure - see _AUTH_PGCODES.
      2. A PROVEN transport failure -> unreachable. Positive evidence about the
         connection outranks the inference in rule 3: both states refuse, so the
         only thing at stake is which remedy the reader is handed, and naming an
         authentication fix for a cluster that never answered is false.
      3. No credential is resolvable at all AND the failure carries no SQLSTATE,
         IS an OperationalError, and names no other server-reported cause ->
         denied. The same three-conjunct guard _classify_drop_error uses, plus the
         non-credential table: the local fact "no password could be offered" is
         permanently true on a trust cluster, so on its own it turned EVERY
         failure that reached this rule into a refusal whose only remedy is an
         authentication fix. `not pgcode` and `_is_operational_error` keep a
         statement-level failure out; _server_refused_for_another_reason keeps out
         the connect-time FATALs (full connection slots, a cluster still starting,
         an absent maintenance database) that arrive with no SQLSTATE at all.
      4. A denial signature -> denied.
      5. Anything else -> unknown. NEVER ok, and never a factual no.

    Rules 2, 4 and 5 read libpq's own strings, which is why LC_MESSAGES (and
    LC_ALL / LANGUAGE) are pinned to C before any connection is opened; a
    SERVER-side message is emitted in the SERVER's lc_messages, which no client
    setting controls, and rule 3 is the belt for exactly that case.
    """
    detail = _exc_detail(exc)
    pgcode = getattr(exc, "pgcode", None)
    if pgcode and str(pgcode) in _AUTH_PGCODES:
        return "denied", "the server rejected the credentials (SQLSTATE {c})".format(
            c=pgcode)
    low = str(exc).lower()
    for sig in _UNREACHABLE_SIGNATURES:
        if sig in low:
            return "unreachable", detail
    if (not pgcode and _is_operational_error(exc)
            and not _server_refused_for_another_reason(low)
            and not _credential_resolvable(opts)):
        return "denied", (
            "no credential is resolvable for this connection: no --db-password, "
            "$ODOO_PG_PASSWORD unset, and no matching line in {f}".format(
                f=_pgpass_path()))
    for sig in _DENIED_SIGNATURES:
        if sig in low:
            return "denied", detail
    return "unknown", detail


def _is_operational_error(exc):
    """Is this psycopg2's OperationalError (or a subclass)?

    The type is checked by NAME across the MRO rather than by importing psycopg2:
    this script runs under the instance's venv and must not add an import of its
    own to a path Odoo already resolved. OperationalError is the class libpq
    connection and handshake failures arrive as; a statement that the SERVER
    rejected arrives with a SQLSTATE instead.
    """
    for cls in type(exc).__mro__:
        if cls.__name__.lower() == "operationalerror":
            return True
    return False


def _classify_drop_error(exc, opts):
    """('denied'|'unreachable'|'', detail) - a CONNECTION failure ONLY.

    Deliberately STRICTER than _classify_conn_error: it demands positive evidence
    that the connection itself failed, because an exp_drop that failed for any
    other reason (an active backend, a missing privilege on the database) was
    genuinely ATTEMPTED, and reporting that as "never attempted" would let a
    caller paper it over with a client-side drop. Empty state means exactly that:
    the drop was attempted and failed.
    """
    detail = _exc_detail(exc)
    pgcode = getattr(exc, "pgcode", None)
    if pgcode and str(pgcode) in _AUTH_PGCODES:
        return "denied", "the server rejected the credentials (SQLSTATE {c})".format(
            c=pgcode)
    low = str(exc).lower()
    for sig in _UNREACHABLE_SIGNATURES:
        if sig in low:
            return "unreachable", detail
    for sig in _DENIED_SIGNATURES:
        if sig in low:
            return "denied", detail
    # The locale-independent belt, scoped to a handshake that never completed: a
    # failure the server itself reported carries a SQLSTATE, so its ABSENCE on an
    # OperationalError is what says the connection never got that far.
    if not pgcode and _is_operational_error(exc) and not _credential_resolvable(opts):
        return "denied", (
            "no credential is resolvable for this connection: no --db-password, "
            "$ODOO_PG_PASSWORD unset, and no matching line in {f}".format(
                f=_pgpass_path()))
    return "", detail


_STATE_EXITS = {
    "ok": EXIT_OK,
    "denied": EXIT_AUTH_DENIED,
    "unreachable": EXIT_UNREACHABLE,
    "unknown": EXIT_FAILURE,
}


def _query_postgres_ex(opts, sql, params=None):
    """(rows, exit_code, state, detail): run one read-only query on the
    maintenance database, CLASSIFYING any failure.

    `state` is "ok" when the query ran, "no-venv" when the package could not be
    imported, else one of _classify_conn_error's three states. Every caller that
    only needs the pair uses _query_postgres below.
    """
    try:
        odoo = _import_odoo(opts)
    except ImportError as exc:
        sys.stderr.write("odoo_db: cannot import odoo (no venv?) - {exc}\n".format(exc=exc))
        return None, EXIT_NO_VENV, "no-venv", str(exc)

    _bootstrap_config(odoo, opts)
    _pin_c_messages()
    cr = None
    try:
        cr = _sql_connect_postgres(odoo).cursor()
        cr.execute(sql, params or ())
        rows = cr.fetchall()
    except Exception as exc:
        state, detail = _classify_conn_error(exc, opts)
        sys.stderr.write(
            "odoo_db: query failed on {host}:{port} - {etype}: {exc}\n".format(
                host=opts.get("db_host") or "libpq-default",
                port=opts.get("db_port") or "libpq-default",
                etype=type(exc).__name__, exc=exc)
        )
        return None, _STATE_EXITS[state], state, detail
    finally:
        if cr is not None:
            try:
                cr.close()
            except Exception:
                pass
    return rows, EXIT_OK, "ok", ""


def _query_postgres(opts, sql, params=None):
    """(rows, exit_code): run one read-only query on the maintenance database.

    Returns (rows, EXIT_OK) when the query ran, or (None, <non-zero>) with a
    diagnostic on stderr naming the RESOLVED host:port when it did not. A failure
    here means "could not answer" - callers must never read it as a factual
    negative answer - and the code says WHICH failure: 8 authentication refused,
    9 cluster unreachable, 10 venv unavailable, 1 anything else.
    """
    rows, code, _state, _detail = _query_postgres_ex(opts, sql, params)
    return rows, code


def _conn_label(opts):
    """`role <user> on <host>:<port>` with every unresolved part named as such."""
    return "role {user} on {host}:{port}".format(
        user=opts.get("db_user") or "libpq-default",
        host=opts.get("db_host") or "libpq-default",
        port=opts.get("db_port") or "libpq-default")


def _refusal_denied(opts, why):
    return (
        "odoo_db: BLOCKED - DB_AUTH=denied. Odoo cannot authenticate to PostgreSQL as\n"
        "  {label}. Every odoo-bin run opens this connection before any module\n"
        "  loads, so no build, install, update or test can start until this is fixed.\n"
        "  NOTHING was created and NOTHING was dropped.\n"
        "  Reason: {why}\n"
        "  Choose ONE:\n"
        "    run /odoo-ai-agents:odoo-setup - for a local developer cluster it enables\n"
        "    passwordless authentication for this role from this machine's address\n"
        "    only, and verifies it by reconnecting; or\n"
        "    export ODOO_PG_PASSWORD=... - for a cluster that cannot be reconfigured\n"
        "    (managed or remote). Applies to THIS shell only.\n".format(
            label=_conn_label(opts), why=why))


def _refusal_unreachable(opts, why):
    return (
        "odoo_db: BLOCKED - DB_AUTH=unreachable. The PostgreSQL cluster for\n"
        "  {label} did not accept a connection: {why}\n"
        "  This is NOT a credential problem and NOT a capability problem - the\n"
        "  cluster did not answer at all.\n"
        "  Start the cluster (or correct db_host/db_port on the [[instance]]). If it\n"
        "  runs in a container, start it and then run /odoo-ai-agents:odoo-setup so\n"
        "  db_run_mode/db_container are re-derived.\n".format(
            label=_conn_label(opts), why=why))


def _refusal_unknown(opts, why):
    return (
        "odoo_db: BLOCKED - DB_AUTH=unknown. The question could not be asked: {why}\n"
        "  Undeterminable is never read as a yes and never as a no.\n"
        "  Run /odoo-ai-agents:odoo-setup to declare the missing environment facts\n"
        "  (python, odoo_root, db_run_mode/db_container), then retry.\n".format(why=why))


_REFUSALS = {
    "denied": _refusal_denied,
    "unreachable": _refusal_unreachable,
    "unknown": _refusal_unknown,
}


def cmd_preflight(opts):
    """Can Odoo AUTHENTICATE to this cluster? Emit the verdict and own the refusal.

    The connection is opened through Odoo's own resolution
    (``odoo.sql_db.db_connect('postgres')``), which is the exact route every build
    verb takes: Odoo's CLI opens the maintenance database for every ``-d <name>``
    run before any registry is built, so a probe over any OTHER surface can answer
    confidently about a connection the build never makes.

    The refusal text lives HERE and nowhere else. Callers forward these bytes.
    """
    _pin_c_messages()
    rows, code, state, detail = _query_postgres_ex(opts, "SELECT 1")
    if state == "no-venv":
        state, detail = "unknown", (
            "the interpreter could not import odoo: for a source checkout that means "
            "`odoo_root` is not declared. " + detail)
        code = EXIT_NO_VENV
    elif state == "ok" and not rows:
        # A connection that answered nothing is not a connection that answered.
        state, detail = "unknown", "the maintenance database returned no row for SELECT 1"
        code = EXIT_FAILURE
    print("DB_AUTH={state}".format(state=state))
    print("DB_AUTH_WHY={why}".format(why=detail or "the connection succeeded"))
    if state != "ok":
        sys.stderr.write(_REFUSALS[state](opts, detail or "no detail reported"))
    return code


def cmd_can_createdb(opts):
    """Print 'true'/'false': may the connecting role CREATE DATABASE?

    The SSOT answer for the allocator's ephemeral-mode gate. A LIVE privilege
    query, never an inference from which binaries are installed: a host with no
    libpq client at all (Postgres in a container) still has a role that may or
    may not create databases, and conflating the two is a FALSE NEGATIVE that
    silently destroys ephemeral isolation.
    """
    rows, rc = _query_postgres(
        opts, "SELECT rolcreatedb FROM pg_roles WHERE rolname = current_user")
    if rc != EXIT_OK:
        return rc
    if not rows:
        sys.stderr.write("odoo_db: current_user has no pg_roles row - cannot answer\n")
        return EXIT_FAILURE
    print("true" if rows[0][0] else "false")
    return EXIT_OK


def cmd_list_databases(opts):
    """Print one non-template datname per line; exit 1 (nothing on stdout) on any
    failure, so a caller can never mistake "could not enumerate" for "empty"."""
    rows, rc = _query_postgres(
        opts, "SELECT datname FROM pg_database WHERE datistemplate = false")
    if rc != EXIT_OK:
        return rc
    for row in rows:
        if row[0]:
            print(row[0])
    return EXIT_OK


def cmd_db_age_s(db_name, opts):
    """Print the database's age in seconds - the PG_VERSION mtime proxy a human
    operator uses by hand, since Postgres records no creation time. Exit 1 when
    unmeasurable (pg_stat_file needs elevated privilege on many builds); callers
    MUST treat that as unknown, never as "0 / just created"."""
    rows, rc = _query_postgres(
        opts,
        "SELECT extract(epoch FROM (now() - "
        "(pg_stat_file('base/'||oid||'/PG_VERSION')).modification)) "
        "FROM pg_database WHERE datname = %s",
        (db_name,),
    )
    if rc != EXIT_OK:
        return rc
    if not rows or rows[0][0] is None:
        sys.stderr.write(
            "odoo_db: db-age-s {db!r}: no measurable age\n".format(db=db_name))
        return EXIT_FAILURE
    print(float(rows[0][0]))
    return EXIT_OK


def cmd_db_size_bytes(db_name, opts):
    """Print pg_database_size in bytes; exit 1 on any failure. Reporting only -
    it never gates a drop decision."""
    rows, rc = _query_postgres(opts, "SELECT pg_database_size(%s)", (db_name,))
    if rc != EXIT_OK:
        return rc
    if not rows or rows[0][0] is None:
        sys.stderr.write(
            "odoo_db: db-size-bytes {db!r}: no size reported\n".format(db=db_name))
        return EXIT_FAILURE
    print(int(rows[0][0]))
    return EXIT_OK


def cmd_drop(db_name, opts):
    try:
        odoo = _import_odoo(opts)
    except ImportError as exc:
        sys.stderr.write("odoo_db: cannot import odoo (no venv?) - {exc}\n".format(exc=exc))
        return EXIT_NO_VENV

    _bootstrap_config(odoo, opts)
    _pin_c_messages()
    service_db = _get_service_db(odoo)

    try:
        result = service_db.exp_drop(db_name)
    except Exception as exc:
        sys.stderr.write(
            "odoo_db: exp_drop({db!r}) raised {etype}: {exc}\n".format(
                db=db_name, etype=type(exc).__name__, exc=exc)
        )
        # A CONNECTION failure necessarily precedes any DROP DATABASE, so 8 and 9
        # are a POSITIVE statement that nothing was attempted - which is what lets
        # a caller consult another surface without ever papering over a real
        # exp_drop failure. Any other exception keeps EXIT_FAILURE: the drop WAS
        # attempted and failed, and no client may retry it.
        state, _detail = _classify_drop_error(exc, opts)
        if state == "denied":
            return EXIT_AUTH_DENIED
        if state == "unreachable":
            return EXIT_UNREACHABLE
        return EXIT_FAILURE

    # exp_drop returns False when the DB is not in the list (already absent) -> idempotent.
    # Returns True on successful drop. Raises on actual failure (caught above).
    # Emit an observability line on EVERY drop naming the RESOLVED connection so a
    # no-op ("already-absent on the cluster we connected to") is distinguishable
    # from a real drop, and so it is always clear which cluster the drop actually hit.
    host = opts.get("db_host") or "libpq-default"
    port = opts.get("db_port") or "libpq-default"
    outcome = "performed" if result else "already-absent"
    sys.stderr.write(
        "odoo_db: drop {db!r} on {host}:{port} -> {outcome}\n".format(
            db=db_name, host=host, port=port, outcome=outcome)
    )
    return EXIT_OK


def cmd_exists(db_name, opts):
    try:
        odoo = _import_odoo(opts)
    except ImportError as exc:
        sys.stderr.write("odoo_db: cannot import odoo (no venv?) - {exc}\n".format(exc=exc))
        return EXIT_NO_VENV

    _bootstrap_config(odoo, opts)
    service_db = _get_service_db(odoo)

    try:
        exists = service_db.exp_db_exist(db_name)
    except Exception as exc:
        sys.stderr.write(
            "odoo_db: exp_db_exist({db!r}) raised {etype}: {exc}\n".format(
                db=db_name, etype=type(exc).__name__, exc=exc)
        )
        return EXIT_FAILURE

    print("true" if exists else "false")
    return EXIT_OK


# ---- Main ----

def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return EXIT_OK

    cmd = argv[0]
    rest = argv[1:]
    opts, pos, unknown = _parse(rest)

    if unknown:
        sys.stderr.write(
            "odoo_db: unrecognized flag(s): {flags}\n".format(flags=" ".join(unknown))
        )
        sys.stderr.write(
            "Usage: odoo_db.py {cmd} <db> [--db-host H] [--db-user U] "
            "[--db-port P] [--db-password P] [--odoo-root R]\n".format(cmd=cmd)
        )
        return EXIT_USAGE

    if cmd == "drop":
        if not pos:
            sys.stderr.write("Usage: odoo_db.py drop <db> [--db-host H] [--db-user U] "
                             "[--db-password P] [--odoo-root R]\n")
            return EXIT_USAGE
        return cmd_drop(pos[0], opts)

    if cmd == "exists":
        if not pos:
            sys.stderr.write("Usage: odoo_db.py exists <db> [--db-host H] [--db-user U] "
                             "[--db-password P] [--odoo-root R]\n")
            return EXIT_USAGE
        return cmd_exists(pos[0], opts)

    if cmd == "preflight":
        return cmd_preflight(opts)

    if cmd == "can-createdb":
        return cmd_can_createdb(opts)

    if cmd == "list-databases":
        return cmd_list_databases(opts)

    if cmd == "db-age-s":
        if not pos:
            sys.stderr.write("Usage: odoo_db.py db-age-s <db> [--db-host H] [--db-user U] "
                             "[--db-port P] [--db-password P] [--odoo-root R]\n")
            return EXIT_USAGE
        return cmd_db_age_s(pos[0], opts)

    if cmd == "db-size-bytes":
        if not pos:
            sys.stderr.write("Usage: odoo_db.py db-size-bytes <db> [--db-host H] [--db-user U] "
                             "[--db-port P] [--db-password P] [--odoo-root R]\n")
            return EXIT_USAGE
        return cmd_db_size_bytes(pos[0], opts)

    sys.stderr.write(
        "odoo_db: unknown subcommand {cmd!r}. Use preflight|drop|exists|can-createdb|"
        "list-databases|db-age-s|db-size-bytes.\n".format(cmd=cmd)
    )
    return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
