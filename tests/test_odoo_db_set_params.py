"""Behavior tests for `odoo_db.py set-params`: write system parameters of one named database and
tell a RUNNING Odoo server about it.

A parameter written by plain SQL stays invisible to a running server: Odoo caches
ir.config_parameter values and drops that cache only when its cache-signalling sequence moves. So
the command writes on ONE connection, commits, and bumps the cache-signalling sequence the
database has (the name differs between series, so it asks the database which exist).

The fake Odoo keeps its "database" in a file: a write that was not committed is not in it.
"""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_odoo_db_lib import EXIT_OK, EXIT_UNREACHABLE, EXIT_USAGE, _run  # noqa: E402


def _fake_odoo(tmp_path, params=None, sequences=None, raise_on_connect=False):
    """A fake Odoo whose sql_db keeps ir_config_parameter and the sequences in db.json, writing the
    file only on commit."""
    root = tmp_path / "fake_odoo"
    pkg = root / "odoo"
    (pkg / "tools").mkdir(parents=True, exist_ok=True)
    (pkg / "service").mkdir(exist_ok=True)
    (pkg / "__init__.py").write_text("from odoo import tools\n", encoding="utf-8")
    (pkg / "service" / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "service" / "db.py").write_text("", encoding="utf-8")
    (pkg / "tools" / "__init__.py").write_text(textwrap.dedent("""\
        class _Config(dict):
            def parse_config(self, args=None):
                pass
        config = _Config()
        """), encoding="utf-8")
    db = tmp_path / "db.json"
    db.write_text(json.dumps({"params": params or {}, "sequences": sequences or {}}), encoding="utf-8")
    (pkg / "sql_db.py").write_text(textwrap.dedent("""\
        import json, os

        RAISE = %r

        class _Cursor(object):
            def __init__(self):
                with open(os.environ["FAKE_DB"]) as fh:
                    self.state = json.load(fh)
                self.rowcount = 0
                self._rows = []

            def execute(self, sql, params=None):
                low = " ".join(sql.split()).lower()
                params = params or ()
                params_t = self.state["params"]
                if low.startswith("update ir_config_parameter set value"):
                    value, key = params
                    self.rowcount = 1 if key in params_t else 0
                    if key in params_t:
                        params_t[key] = value
                elif low.startswith("insert into ir_config_parameter"):
                    key, value = params
                    assert key not in params_t, "an upsert must not insert an existing key"
                    params_t[key] = value
                elif low.startswith("delete from ir_config_parameter"):
                    params_t.pop(params[0], None)
                elif "from pg_sequences" in low:
                    self._rows = [(n,) for n in sorted(params[0]) if n in self.state["sequences"]]
                elif low.startswith("select nextval"):
                    self.state["sequences"][params[0]] += 1
                    self._rows = [(self.state["sequences"][params[0]],)]
                else:
                    raise AssertionError("unexpected SQL: " + sql)

            def fetchall(self):
                return self._rows

            def commit(self):
                with open(os.environ["FAKE_DB"], "w") as fh:
                    json.dump(self.state, fh)

            def close(self):
                pass

        class _Connection(object):
            def cursor(self, *a, **k):
                return _Cursor()

        def db_connect(to, allow_uri=False):
            if RAISE:
                raise RuntimeError("could not connect to server")
            return _Connection()
        """ % (raise_on_connect,)), encoding="utf-8")
    return root, db


def _set(tmp_path, *args, **kw):
    root, db = _fake_odoo(tmp_path, **{k: v for k, v in kw.items() if k != "env"})
    res = _run("set-params", "the_db", *args, env_extra={"FAKE_DB": str(db)}, pythonpath_prepend=root)
    return res, json.loads(db.read_text())


def test_a_parameter_is_created_updated_and_deleted_on_the_named_database(tmp_path):
    res, state = _set(tmp_path, "--set", "web.base.url=https://x.example", "--set", "web.base.url.freeze=True",
                      "--unset", "gone", params={"web.base.url": "http://localhost:8069", "gone": "1", "keep": "2"})
    assert res.returncode == EXIT_OK, res.stderr
    assert state["params"] == {"web.base.url": "https://x.example", "web.base.url.freeze": "True", "keep": "2"}
    assert res.stdout.split() == ["PARAMS_SET=2", "PARAMS_UNSET=1", "CACHE_SIGNALLED="]


def test_a_running_server_is_told_by_bumping_the_cache_signalling_sequence_the_database_has(tmp_path):
    """The sequence is `base_cache_signaling` before the per-cache split and
    `base_cache_signaling_default` after it; a sequence that does not exist is never created, and
    the registry-reload sequence is never touched (it would reload the whole registry)."""
    for existing in ("base_cache_signaling", "base_cache_signaling_default"):
        sequences = {existing: 7, "base_registry_signaling": 3, "base_cache_signaling_assets": 5}
        res, state = _set(tmp_path, "--set", "web.base.url=https://x.example", sequences=sequences)
        assert res.returncode == EXIT_OK, res.stderr
        assert state["sequences"][existing] == 8
        assert state["sequences"]["base_registry_signaling"] == 3
        assert state["sequences"]["base_cache_signaling_assets"] == 5
        assert "CACHE_SIGNALLED=" + existing in res.stdout.split()


def test_a_database_without_a_signalling_sequence_says_so(tmp_path):
    res, _state = _set(tmp_path, "--set", "k=v")
    assert res.returncode == EXIT_OK and "CACHE_SIGNALLED=" in res.stdout.split()


def test_nothing_is_written_when_the_database_cannot_be_reached(tmp_path):
    res, state = _set(tmp_path, "--set", "k=v", params={"a": "1"}, raise_on_connect=True)
    assert res.returncode == EXIT_UNREACHABLE and res.stdout == ""
    assert state["params"] == {"a": "1"}


def test_a_call_that_names_nothing_to_write_or_a_value_without_a_key_is_a_usage_error(tmp_path):
    assert _set(tmp_path)[0].returncode == EXIT_USAGE
    assert _set(tmp_path, "--set", "no_equals_sign")[0].returncode == EXIT_USAGE
    assert _set(tmp_path, "--set", "=value")[0].returncode == EXIT_USAGE


def test_a_value_may_itself_contain_equals_signs(tmp_path):
    res, state = _set(tmp_path, "--set", "web.base.url=https://x.example/?a=b")
    assert res.returncode == EXIT_OK, res.stderr
    assert state["params"]["web.base.url"] == "https://x.example/?a=b"
