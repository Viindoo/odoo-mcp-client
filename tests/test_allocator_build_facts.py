"""Behavior tests: the lease row carries the build facts the build and serve tools apply.

Contracts protected (scripts/lib/allocator.py):
  - every acquire that writes a lease copies the catalog row's DECLARED `server_wide_modules` onto
    it ([] when the row declares none) and echoes ALLOC_SERVER_WIDE_MODULES, so a build and a
    later serve of the same lease load the same set even if the catalog changes in between;
  - a shared lease gets it too; re-registering a shared lease WITHOUT a (re)launched server keeps
    the set the running server was started with, a registration WITH --pid refreshes it, and a row
    an older allocator wrote gains it;
  - `record-build` records what a build put into the database: `built.demo` is sticky-true (demo
    data never leaves a database), `built.languages` only grows; an unknown token is
    LEASE_NOT_FOUND, a call recording nothing is USAGE.

CPU-only: no Postgres, no Odoo (every acquire here passes --no-create or is shared).
"""

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ALLOC = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "lib" / "allocator.py"

CATALOG = """\
[[instance]]
series = "17.0"
addons_path = ["/srv/odoo/addons"]
http_port = 8069
http_port_base = 8170
db_name = "odoo_17_0"
db_user = "odoo"
server_wide_modules = ["to_base", "viin_brand"]

[[instance]]
series = "16.0"
addons_path = ["/srv/odoo16/addons"]
http_port = 8079
http_port_base = 8180
db_name = "odoo_16_0"
"""


@pytest.fixture
def env(tmp_path):
    catalog = tmp_path / "instances.toml"
    catalog.write_text(CATALOG, encoding="utf-8")
    e = dict(os.environ)
    e.update({"ODOO_AI_HOME": str(tmp_path / "home"), "ODOO_AI_INSTANCES": str(catalog),
              "HOME": str(tmp_path)})
    return e


def _run(env, *args):
    return subprocess.run([sys.executable, str(ALLOC), *args], capture_output=True, text=True,
                          env=env, timeout=60, cwd=env["HOME"])


def _json(env, *args):
    proc = _run(env, *args, "--format", "json")
    return json.loads(proc.stdout)


def _rows(env):
    path = Path(env["ODOO_AI_HOME"]) / "runtime" / "leases.json"
    return {lz["token"]: lz for lz in json.loads(path.read_text())["leases"]}


@pytest.mark.parametrize("mode", ["ephemeral", "exclusive"])
def test_an_acquire_records_the_catalogs_declared_server_wide_modules(env, mode):
    out = _json(env, "acquire", "--series", "17.0", "--mode", mode, "--run-id", "r1", "--no-create")
    assert out["ok"], out
    token = out["fields"]["ALLOC_TOKEN"]
    assert out["fields"]["ALLOC_SERVER_WIDE_MODULES"] == ["to_base", "viin_brand"]
    assert _rows(env)[token]["server_wide_modules"] == ["to_base", "viin_brand"]


def test_a_row_that_declares_none_records_an_empty_list_not_nothing(env):
    out = _json(env, "acquire", "--series", "16.0", "--mode", "ephemeral", "--run-id", "r1",
                "--no-create")
    token = out["fields"]["ALLOC_TOKEN"]
    assert out["fields"]["ALLOC_SERVER_WIDE_MODULES"] == []
    assert _rows(env)[token]["server_wide_modules"] == []


def test_the_shell_protocol_echoes_the_set_too(env):
    proc = _run(env, "acquire", "--series", "17.0", "--mode", "ephemeral", "--run-id", "r1",
                "--no-create")
    facts = dict(line.split("=", 1) for line in proc.stdout.splitlines() if "=" in line)
    assert shlex.split(facts["ALLOC_SERVER_WIDE_MODULES"]) == ["to_base viin_brand"]


def test_a_shared_lease_keeps_the_set_its_server_started_with_until_a_relaunch(env, tmp_path):
    first = _json(env, "acquire", "--series", "17.0", "--mode", "shared", "--run-id", "r1")
    token = first["fields"]["ALLOC_TOKEN"]
    assert _rows(env)[token]["server_wide_modules"] == ["to_base", "viin_brand"]
    # The operator changes the catalog while the server runs.
    Path(env["ODOO_AI_INSTANCES"]).write_text(
        CATALOG.replace('["to_base", "viin_brand"]', '["to_base"]'), encoding="utf-8")
    _json(env, "acquire", "--series", "17.0", "--mode", "shared", "--run-id", "r1")
    assert _rows(env)[token]["server_wide_modules"] == ["to_base", "viin_brand"], \
        "an attach without a launch must not rewrite what the running server loaded"
    server = subprocess.Popen(["sleep", "60"])
    try:
        _json(env, "acquire", "--series", "17.0", "--mode", "shared", "--run-id", "r1",
              "--pid", str(server.pid))
        assert _rows(env)[token]["server_wide_modules"] == ["to_base"], \
            "a registration carrying the relaunched server's pid records the set it was launched with"
    finally:
        server.kill()
        server.wait()


def test_a_shared_row_written_before_the_key_existed_gains_it_on_attach(env):
    token = _json(env, "acquire", "--series", "17.0", "--mode", "shared",
                  "--run-id", "r1")["fields"]["ALLOC_TOKEN"]
    path = Path(env["ODOO_AI_HOME"]) / "runtime" / "leases.json"
    doc = json.loads(path.read_text())
    for lz in doc["leases"]:
        lz.pop("server_wide_modules", None)
    path.write_text(json.dumps(doc), encoding="utf-8")
    _json(env, "acquire", "--series", "17.0", "--mode", "shared", "--run-id", "r1")
    assert _rows(env)[token]["server_wide_modules"] == ["to_base", "viin_brand"]


def _lease(env):
    return _json(env, "acquire", "--series", "17.0", "--mode", "ephemeral", "--run-id", "r1",
                 "--no-create")["fields"]["ALLOC_TOKEN"]


def test_demo_once_loaded_stays_recorded_whatever_a_later_build_says(env):
    token = _lease(env)
    off = _json(env, "record-build", token, "--demo", "off")
    assert off["ok"] and off["fields"]["ALLOC_BUILT_DEMO"] == "false"
    assert _rows(env)[token]["built"]["demo"] is False
    _json(env, "record-build", token, "--demo", "on")
    later = _json(env, "record-build", token, "--demo", "off")
    assert later["fields"]["ALLOC_BUILT_DEMO"] == "true"
    assert _rows(env)[token]["built"]["demo"] is True, "demo data never leaves a database"


def test_proven_languages_accumulate_and_never_shrink(env):
    token = _lease(env)
    _json(env, "record-build", token, "--languages", "en_US,vi_VN")
    out = _json(env, "record-build", token, "--languages", "fr_BE,en_US")
    assert out["fields"]["ALLOC_BUILT_LANGUAGES"] == ["en_US", "vi_VN", "fr_BE"]
    built = _rows(env)[token]["built"]
    assert built["languages"] == ["en_US", "vi_VN", "fr_BE"]
    assert "demo" not in built, "a languages-only record says nothing about demo"


def test_record_build_refuses_an_unknown_token_and_an_empty_record(env):
    token = _lease(env)
    missing = _json(env, "record-build", "f" * 32, "--demo", "on")
    assert missing["ok"] is False and missing["error"]["code"] == "LEASE_NOT_FOUND"
    for args in ((token,), (token, "--demo", "maybe")):
        bad = _json(env, "record-build", *args)
        assert bad["ok"] is False and bad["error"]["code"] == "USAGE", args
    assert "built" not in _rows(env)[token], "a refused record writes nothing"
