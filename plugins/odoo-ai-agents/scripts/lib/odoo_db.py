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

  python3 odoo_db.py can-createdb [--db-host H] [--db-user U] [--db-port P]
                                  [--db-password P] [--odoo-root R]
      Print ``true`` or ``false``: may the connecting role CREATE DATABASE?
      A LIVE privilege query, never an inference from which binaries are
      installed. Exit 0 when answered, 1 when the question could not be
      answered (unreachable cluster, auth failure, no pg_roles row), 10 on
      venv unavailable. Callers MUST keep "answered false" and "could not
      answer" distinct - see allocator.py exits 6 and 7.

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
  3. Nothing set -> Odoo uses its own default (peer auth, .pgpass, etc.)

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


def _query_postgres(opts, sql, params=None):
    """(rows, exit_code): run one read-only query on the maintenance database.

    Returns (rows, EXIT_OK) when the query ran, or (None, EXIT_NO_VENV /
    EXIT_FAILURE) with a diagnostic on stderr naming the RESOLVED host:port when
    it did not. A failure here means "could not answer" - callers must never
    read it as a factual negative answer.
    """
    try:
        odoo = _import_odoo(opts)
    except ImportError as exc:
        sys.stderr.write("odoo_db: cannot import odoo (no venv?) - {exc}\n".format(exc=exc))
        return None, EXIT_NO_VENV

    _bootstrap_config(odoo, opts)
    cr = None
    try:
        cr = _sql_connect_postgres(odoo).cursor()
        cr.execute(sql, params or ())
        rows = cr.fetchall()
    except Exception as exc:
        sys.stderr.write(
            "odoo_db: query failed on {host}:{port} - {etype}: {exc}\n".format(
                host=opts.get("db_host") or "libpq-default",
                port=opts.get("db_port") or "libpq-default",
                etype=type(exc).__name__, exc=exc)
        )
        return None, EXIT_FAILURE
    finally:
        if cr is not None:
            try:
                cr.close()
            except Exception:
                pass
    return rows, EXIT_OK


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
    service_db = _get_service_db(odoo)

    try:
        result = service_db.exp_drop(db_name)
    except Exception as exc:
        sys.stderr.write(
            "odoo_db: exp_drop({db!r}) raised {etype}: {exc}\n".format(
                db=db_name, etype=type(exc).__name__, exc=exc)
        )
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
        "odoo_db: unknown subcommand {cmd!r}. Use drop|exists|can-createdb|"
        "list-databases|db-age-s|db-size-bytes.\n".format(cmd=cmd)
    )
    return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
