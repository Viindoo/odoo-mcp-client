"""Behavior tests for the two questions odoo_db.py asks ONE named database:

`i18n-state` - what an i18n export needs to know before it writes any file: which requested
languages exist there, whether each is active and its ISO code (the name Odoo gives that
language's `.po`), and which requested modules are installed and whether each has its demo data
loaded (ir_module_module.demo - an export of a module without it misses its demo records' terms).

`db-facts` - what the database holds, the source of truth the build tools prefer over lease
records: whether any installed module has demo data loaded (ir_module_module.demo) and which
languages are active (res_lang.active), plus - asked with --modules, on the same connection -
each named module's state and demo flag. A database that does not exist holds nothing
(DB_EXISTS=0); one that cannot be read prints nothing.

Contracts protected:
  - the question is asked of the NAMED database through Odoo's own connection layer (never the
    maintenance database, never a raw client), under both core namespaces (`odoo`, `openerp`);
  - a language or module the database does not know prints NO line - absence is never reported
    as a value, and the caller refuses it;
  - a query that could not be asked prints nothing and exits with the classified code, so "could
    not ask" is never read as "no language active".
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_odoo_db_lib import EXIT_OK, EXIT_UNREACHABLE, EXIT_USAGE, _run  # noqa: E402

LANGS = [("en_US", "en", True), ("vi_VN", "vi", True), ("fr_BE", "fr_BE", False)]
MODULES = [("base", "installed", True), ("my_mod", "installed", True),
           ("bare_mod", "installed", False), ("other", "uninstalled", False)]


def _fake_odoo(tmp_path, pkg_name="odoo", raise_on_connect=False, demo=True,
               active="en_US,vi_VN", unreachable_dbs=(), existing_dbs=("the_db", "postgres")):
    """A fake Odoo whose sql_db.db_connect records the database it was asked to open and answers
    the res_lang / ir_module_module queries from LANGS / MODULES."""
    root = tmp_path / ("fake_" + pkg_name)
    pkg = root / pkg_name
    (pkg / "service").mkdir(parents=True)
    (pkg / "tools").mkdir()
    (pkg / "__init__.py").write_text("from %s import tools, service\n" % pkg_name, encoding="utf-8")
    (pkg / "tools" / "__init__.py").write_text(textwrap.dedent("""\
        class _Config(dict):
            def parse_config(self, args=None):
                pass
        config = _Config()
        """), encoding="utf-8")
    (pkg / "service" / "__init__.py").write_text("from %s.service import db\n" % pkg_name,
                                                 encoding="utf-8")
    (pkg / "service" / "db.py").write_text("", encoding="utf-8")
    (pkg / "sql_db.py").write_text(textwrap.dedent("""\
        import os
        LANGS = %r
        MODULES = %r
        RAISE = %r
        DEMO = %r
        ACTIVE = %r
        UNREACHABLE = %r
        EXISTING = %r

        class _Cursor(object):
            def execute(self, sql, params=None):
                low = " ".join(sql.split()).lower()
                if "bool_or(demo)" in low:
                    assert "ir_module_module" in low and "res_lang where active" in low
                    self._rows = [(DEMO, ACTIVE)]
                    return
                if "from pg_database" in low:
                    self._rows = [(1,)] if params[0] in EXISTING else []
                    return
                wanted = set(params[0])
                if "from res_lang" in low:
                    self._rows = [r for r in LANGS if r[0] in wanted]
                elif "from ir_module_module" in low:
                    self._rows = [r for r in MODULES if r[0] in wanted]
                else:
                    raise AssertionError("unexpected SQL: " + sql)
            def fetchall(self):
                return self._rows
            def close(self):
                pass

        class _Connection(object):
            def cursor(self, *a, **k):
                return _Cursor()

        def db_connect(to, allow_uri=False):
            with open(os.environ["FAKE_CONNECT_LOG"], "a") as fh:
                fh.write(to + "\\n")
            if RAISE:
                raise RuntimeError("could not connect to server")
            if to in UNREACHABLE:
                raise RuntimeError('FATAL:  la base de donnees "%%s" n existe pas' %% to)
            return _Connection()
        """ % (LANGS, MODULES, raise_on_connect, demo, active, list(unreachable_dbs),
               list(existing_dbs))), encoding="utf-8")
    return root


def _state(tmp_path, *args, verb="i18n-state", **kw):
    log = tmp_path / "connect.log"
    res = _run(verb, *args, env_extra={"FAKE_CONNECT_LOG": str(log)},
               pythonpath_prepend=_fake_odoo(tmp_path, **kw))
    return res, (log.read_text().split() if log.exists() else [])


def test_it_reports_each_known_language_with_its_iso_code_and_each_known_modules_state(tmp_path):
    res, opened = _state(tmp_path, "the_db", "--languages", "en_US,vi_VN,fr_BE,xx_XX",
                         "--modules", "my_mod,other,ghost")
    assert res.returncode == EXIT_OK, res.stderr
    assert res.stdout.splitlines() == [
        "LANG=en_US ISO=en ACTIVE=1",
        "LANG=vi_VN ISO=vi ACTIVE=1",
        "LANG=fr_BE ISO=fr_BE ACTIVE=0",
        "MODULE=my_mod STATE=installed DEMO=1",
        "MODULE=other STATE=uninstalled DEMO=0",
    ], "an unknown language or module prints no line at all"
    assert opened and set(opened) == {"the_db"}, "the NAMED database is asked, never 'postgres'"


def test_each_module_says_whether_its_own_demo_data_is_loaded(tmp_path):
    """Demo is a fact of each MODULE: a database where some module has demo data can still hold
    the exported module without its own, and only the per-module flag tells them apart."""
    res, _opened = _state(tmp_path, "the_db", "--modules", "my_mod,bare_mod")
    assert res.returncode == EXIT_OK, res.stderr
    assert res.stdout.splitlines() == ["MODULE=my_mod STATE=installed DEMO=1",
                                       "MODULE=bare_mod STATE=installed DEMO=0"]


def test_it_works_under_the_openerp_namespace(tmp_path):
    res, _opened = _state(tmp_path, "the_db", "--languages", "vi_VN", "--modules", "my_mod",
                          pkg_name="openerp")
    assert res.returncode == EXIT_OK, res.stderr
    assert "LANG=vi_VN ISO=vi ACTIVE=1" in res.stdout.splitlines()


def test_a_database_it_cannot_reach_prints_nothing_and_exits_classified(tmp_path):
    res, _opened = _state(tmp_path, "the_db", "--languages", "vi_VN", "--modules", "my_mod",
                          raise_on_connect=True)
    assert res.returncode == EXIT_UNREACHABLE
    assert res.stdout == ""


def test_it_needs_a_database_and_something_to_ask(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    assert _state(tmp_path / "a", "--modules", "my_mod")[0].returncode == EXIT_USAGE
    assert _state(tmp_path / "b", "the_db")[0].returncode == EXIT_USAGE


# --------------------------------------------------------------------------- #
# db-facts
# --------------------------------------------------------------------------- #
def test_db_facts_reads_demo_and_active_languages_from_the_named_database(tmp_path):
    res, opened = _state(tmp_path, "the_db", verb="db-facts")
    assert res.returncode == EXIT_OK, res.stderr
    assert res.stdout.splitlines() == ["DB_EXISTS=1", "DEMO=1", "LANGUAGES=en_US,vi_VN"]
    assert opened == ["the_db"], "ONE connection, to the named database"


def test_db_facts_asked_for_modules_adds_each_known_modules_state_and_demo_on_one_connection(
        tmp_path):
    res, opened = _state(tmp_path, "the_db", "--modules", "bare_mod,my_mod,ghost", verb="db-facts")
    assert res.returncode == EXIT_OK, res.stderr
    assert res.stdout.splitlines() == ["DB_EXISTS=1", "DEMO=1", "LANGUAGES=en_US,vi_VN",
                                       "MODULE=bare_mod STATE=installed DEMO=0",
                                       "MODULE=my_mod STATE=installed DEMO=1"], (
        "a module the database does not know prints no line")
    assert opened == ["the_db"], "ONE connection, to the named database"


def test_db_facts_without_demo_says_so_and_never_invents_a_language(tmp_path):
    res, _ = _state(tmp_path, "the_db", verb="db-facts", demo=None, active=None)
    assert res.stdout.splitlines() == ["DB_EXISTS=1", "DEMO=0", "LANGUAGES="]


def test_db_facts_works_under_the_openerp_namespace(tmp_path):
    res, _ = _state(tmp_path, "the_db", verb="db-facts", pkg_name="openerp", demo=False)
    assert res.returncode == EXIT_OK and "DEMO=0" in res.stdout.splitlines()


def test_a_database_that_does_not_exist_holds_nothing(tmp_path):
    """Told apart from "could not ask" by the maintenance database, never by the server's message
    (it arrives in the server's own language - here not English)."""
    res, opened = _state(tmp_path, "gone_db", verb="db-facts", unreachable_dbs=("gone_db",))
    assert res.returncode == EXIT_OK, res.stderr
    assert res.stdout.splitlines() == ["DB_EXISTS=0"]
    assert opened == ["gone_db", "postgres"]


def test_a_database_that_exists_but_cannot_be_read_prints_nothing(tmp_path):
    res, _ = _state(tmp_path, "the_db", verb="db-facts", unreachable_dbs=("the_db",))
    assert res.returncode != EXIT_OK and res.stdout == ""


def test_an_unreachable_cluster_prints_nothing_and_exits_classified(tmp_path):
    res, _ = _state(tmp_path, "the_db", verb="db-facts", raise_on_connect=True)
    assert res.returncode == EXIT_UNREACHABLE and res.stdout == ""


def test_db_facts_needs_a_database(tmp_path):
    assert _state(tmp_path, verb="db-facts")[0].returncode == EXIT_USAGE


# --------------------------------------------------------------------------- #
# the operator's own Odoo config file never answers
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("pkg_name,var", [("odoo", "ODOO_RC"), ("openerp", "OPENERP_SERVER")])
def test_odoo_is_imported_reading_no_config_file_of_the_operator(tmp_path, pkg_name, var):
    """Before 19.0 Odoo loads its default config file (~/.odoorc) when its config module is
    IMPORTED, and every key it states - db_host, db_port, db_password - then answers wherever no
    flag is given. The builds never read that file, so the questions asked about their databases
    must not either: the import reads a config file holding nothing."""
    root = _fake_odoo(tmp_path, pkg_name=pkg_name)
    seen = tmp_path / "rc-at-import.txt"
    tools = root / pkg_name / "tools" / "__init__.py"
    tools.write_text(textwrap.dedent("""\
        import os
        _rc = os.environ.get(%r) or ""
        with open(%r, "w") as fh:
            fh.write(_rc + "\\n" + (open(_rc).read() if _rc and os.path.isfile(_rc) else "<none>"))
        class _Config(dict):
            def parse_config(self, args=None):
                pass
        config = _Config()
        """ % (var, str(seen))), encoding="utf-8")
    log = tmp_path / "connect.log"
    operator_rc = tmp_path / "operator.odoorc"
    operator_rc.write_text("[options]\ndb_port = 1\n", encoding="utf-8")
    res = _run("db-facts", "the_db", env_extra={"FAKE_CONNECT_LOG": str(log), var: str(operator_rc)},
               pythonpath_prepend=root)
    assert res.returncode == EXIT_OK, res.stderr
    rc_path, content = seen.read_text().split("\n", 1)
    assert rc_path and rc_path != str(operator_rc), "the operator's config file was named"
    assert "=" not in content, "the config file Odoo reads states no option: %r" % content
