"""odoo_db.py - Drop and existence-check an Odoo database THROUGH Odoo (never raw dropdb).

This is the SSOT for DB-lifecycle operations that must honour Odoo's own
connection-pool shutdown, filestore cleanup, and registry teardown. It is
intentionally a standalone script run UNDER the target instance's venv python so
that ``import odoo`` resolves to the correct series.

CLI contract
------------
  python3 odoo_db.py drop   <db> [--db-host H] [--db-user U] [--db-password P]
      Drop the database through ``odoo.service.db.exp_drop``.
      Exit 0 on success OR if the DB is already absent (idempotent).
      Exit 1 on any Odoo-level failure (message on stderr).
      Exit 2 on usage / argument error.
      Exit 10 when the Odoo package cannot be imported (``odoo_db: cannot import
               odoo (no venv?)`` on stderr) - "venv unavailable" sentinel for
               callers (e.g. allocator.py) that want to apply their own fallback.

  python3 odoo_db.py exists <db> [--db-host H] [--db-user U] [--db-password P]
      Print ``true`` or ``false`` (lowercase) to stdout.
      Exit 0 always (even when the DB does not exist).
      Exit 2 on usage error.
      Exit 10 on venv unavailable (as above).

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

NEVER calls raw ``dropdb`` / ``psql`` / ``createdb``. All DB destruction goes
through ``odoo.service.db.exp_drop`` which handles connection-pool teardown,
filestore removal, and registry cleanup in a single atomic step.
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
    "--db-password": "db_password",
}


def _parse(argv):
    """Return (opts: dict, positional: list)."""
    opts, pos = {}, []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in _FLAG_KEYS:
            opts[_FLAG_KEYS[a]] = argv[i + 1] if i + 1 < len(argv) else ""
            i += 2
        else:
            pos.append(a)
            i += 1
    return opts, pos


# ---- Odoo import + config bootstrap ----

def _import_odoo():
    """Import the Odoo package (supports openerp v8/v9 namespace).

    Returns the odoo/openerp module, or raises ImportError if neither is present.
    """
    try:
        import odoo  # noqa: F401 - confirm importability
        return odoo
    except ImportError:
        pass
    try:
        import openerp as odoo  # v8/v9  # noqa: F401
        return odoo
    except ImportError:
        raise ImportError("neither 'odoo' nor 'openerp' is importable")


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


def cmd_drop(db_name, opts):
    try:
        odoo = _import_odoo()
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
    if result is False:
        # DB absent - treat as success (idempotent drop)
        pass
    return EXIT_OK


def cmd_exists(db_name, opts):
    try:
        odoo = _import_odoo()
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
    opts, pos = _parse(rest)

    if cmd == "drop":
        if not pos:
            sys.stderr.write("Usage: odoo_db.py drop <db> [--db-host H] [--db-user U] [--db-password P]\n")
            return EXIT_USAGE
        return cmd_drop(pos[0], opts)

    if cmd == "exists":
        if not pos:
            sys.stderr.write("Usage: odoo_db.py exists <db> [--db-host H] [--db-user U] [--db-password P]\n")
            return EXIT_USAGE
        return cmd_exists(pos[0], opts)

    sys.stderr.write("odoo_db: unknown subcommand {cmd!r}. Use drop|exists.\n".format(cmd=cmd))
    return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
