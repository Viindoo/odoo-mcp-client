"""Behavior tests: the odoo-local tools apply the build facts themselves - server-wide modules,
languages and demo - so an agent never composes --load / --load-language / demo flags.

Driven over stdio against the REAL server, allocator and setup-step scripts, in the stubbed world of
test_odoo_local_mcp_instance.py (odoo-bin, the venv python, curl and pg_isready are stubs). The Odoo
checkout the tools read the core --load default from is a fixture tree
(tests/odoo_tree_fixtures.py) written where the stub odoo-bin lives.

Contracts protected:
  - instance_build runs odoo-bin with --load = core default (read from the checkout) + the lease's
    declared server_wide_modules, --load-language = en_US + languages, and the series' own demo
    flag, on every series from 8.0 to 20.0;
  - demo is required for op init and refused for op update (an update never adds demo data); op
    test takes NO demo argument (any value is refused) and runs with the series default read from
    the lease's checkout; BOTH demo states are stated explicitly wherever the checkout can state
    them (--with-demo / --without-demo=True on the command line; `without_demo = False` in the
    run's config file where the only option is --without-demo), and every build runs with a
    config file the tool generated, so the operator's ~/.odoorc can never flip it; where the
    default is no demo, a test
    build on a database any build filled with demo is refused - demo is a fact of the DATABASE, so
    it is seen from every lease on that database (a forwarded one included), never from the one
    lease that ran the build alone;
  - declared server-wide modules with an unreadable core default are refused, never guessed, and
    nothing is started - by instance_build and by instance_serve alike;
  - a lease row an older allocator wrote (no server_wide_modules key) uses the catalog row's set;
  - instance_build's start result carries no INSTANCE_HANDLE (it would state the database before
    the build changed it);
  - job_wait reports the languages the build proved loaded and the ones it did not (en_US once the
    modules loaded, whatever a test suite run afterwards says), turns Odoo's
    "must be loaded server-wide" and "installed without demo data" lines into warnings with a
    remedy, records the proven languages on the lease, and hands back a handle whose demo and
    languages_loaded are real;
  - instance_serve writes the same resolved set into the served conf and takes no load_modules.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import odoo_tree_fixtures as trees  # noqa: E402
from odoo_local_mcp_harness import McpClient  # noqa: E402
from test_odoo_local_mcp_instance import (RUN, SERIES, _build, _declare_series, _err,  # noqa: E402,F401
                                          _lease, _ok, _registry, _wait, client, world)

BUILD_SERIES = ("8.0", "10.0", "11.0", "16.0", "17.0", "18.0", "19.0", "20.0")
# Where the checkout declares --with-demo (demo opt-in) both states have a command-line spelling;
# where it declares only --without-demo, `on` cannot be spelled there (that option takes a string,
# and every string is truthy) and is stated in the run's config file instead.
DEMO_OFF_FLAG = {s: "--without-demo=True" for s in BUILD_SERIES}
DEMO_ON_FLAG = {s: ("--with-demo" if int(s.split(".")[0]) >= 19 else None) for s in BUILD_SERIES}
DEMO_ON_CONF = {s: ([] if int(s.split(".")[0]) >= 19 else ["without_demo = False"])
                for s in BUILD_SERIES}


def _declare_server_wide(world, modules):
    toml = world["home"] / "instances.toml"
    toml.write_text(toml.read_text() + "server_wide_modules = %s\n" % json.dumps(modules),
                    encoding="utf-8")


def _checkout(world, series):
    """The stub world's core dir (odoo-bin + addons/) becomes a checkout of `series`."""
    trees.write_checkout(world["odoo_bin"].parent, series)


def _odoo_calls(world):
    """argv (list) of every recorded odoo-bin build call."""
    if not world["calls"].exists():
        return []
    return [line.split()[1:] for line in world["calls"].read_text().splitlines() if " -d " in line]


def _flags(argv, *prefixes):
    return [a for a in argv if a.startswith(prefixes)]


def _run_confs(world):
    """[(conf path, [its lines])] for every build/export odoo-bin launch, in order."""
    if not world["confs"].exists():
        return []
    out = []
    for line in world["confs"].read_text().splitlines():
        if line.startswith("== "):
            out.append((line[3:], []))
        elif out:
            out[-1][1].append(line)
    return out


def _conf_of(argv):
    return argv[argv.index("-c") + 1] if "-c" in argv else None


def _jobs(world):
    jobs_dir = world["home"] / "runtime" / "jobs"
    return list(jobs_dir.glob("*.json")) if jobs_dir.is_dir() else []


# --------------------------------------------------------------------------- #
# instance_build: the argv each series receives
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("series", BUILD_SERIES)
@pytest.mark.parametrize("demo", ["off", "on"])
def test_a_build_carries_load_languages_and_the_series_demo_flag(world, series, demo):
    _declare_series(world, series)
    _declare_server_wide(world, ["to_base", "web"])
    _checkout(world, series)
    with McpClient(world["env"](), world["work"]) as c:
        c.initialize()
        lease = _lease(c, world, series=series)
        job = _ok(_build(c, world, lease["token"], demo=demo, languages=["vi_VN", "en_US"]))
        assert _wait(c, job["job_id"])["result"] == "success"
    expected_load = trees.CORE_LOAD[series] + [m for m in ("to_base", "web")
                                               if m not in trees.CORE_LOAD[series]]
    assert job["server_wide_modules"] == expected_load
    assert job["languages"] == ["en_US", "vi_VN"], "en_US first, never twice"
    (argv,) = _odoo_calls(world)
    assert _flags(argv, "--load=") == ["--load=" + ",".join(expected_load)]
    assert _flags(argv, "--load-language") == ["--load-language=en_US,vi_VN"]
    flag = (DEMO_ON_FLAG if demo == "on" else DEMO_OFF_FLAG)[series]
    assert _flags(argv, "--with", "--without") == ([flag] if flag else [])
    ((conf, lines),) = _run_confs(world)
    assert _conf_of(argv) == conf, "odoo-bin reads the tool's config file, never ~/.odoorc"
    assert lines == ["[options]"] + (DEMO_ON_CONF[series] if demo == "on" else []), (
        "the run's config file states only what the build itself states")


def test_no_operator_config_file_reaches_any_build(world, tmp_path):
    """An operator's ~/.odoorc (here: demo off, another data dir) must never decide a build: every
    odoo-bin gets `-c` with the tool's own file, which on every series means no other config file
    is read."""
    home = tmp_path / "operator-home"
    home.mkdir()
    (home / ".odoorc").write_text("[options]\nwithout_demo = True\ndata_dir = /elsewhere\n",
                                  encoding="utf-8")
    with McpClient(world["env"](HOME=str(home)), world["work"]) as c:
        c.initialize()
        lease = _lease(c, world, ports=1)
        for over in ({"op": "init", "demo": "on"}, {"op": "update"},
                     {"op": "test", "test_mode": "reuse", "test_tags": "/my_mod"}):
            _wait(c, _ok(_build(c, world, lease["token"], **over))["job_id"])
    calls = _odoo_calls(world)
    assert len(calls) == 3
    envs = world["rc_env"].read_text().splitlines()
    for argv, (conf, lines), env in zip(calls, _run_confs(world), envs):
        assert _conf_of(argv) == conf and Path(conf).parent == world["home"] / "conf", argv
        assert not any("elsewhere" in ln or "without_demo = True" in ln for ln in lines), lines
        # Before 19.0 Odoo loads its default rc at IMPORT time, before -c is parsed: only
        # $ODOO_RC naming the tool's conf keeps ~/.odoorc's other keys out.
        assert env == conf + "|", env


def test_the_oldest_core_package_is_isolated_through_its_own_variable(world):
    """openerp/ (the oldest series) reads $OPENERP_SERVER, not $ODOO_RC, at import time."""
    _declare_series(world, "8.0")
    with McpClient(world["env"](), world["work"]) as c:
        c.initialize()
        lease = _lease(c, world, series="8.0")
        _wait(c, _ok(_build(c, world, lease["token"], demo="on"))["job_id"])
    ((conf, lines),) = _run_confs(world)
    assert world["rc_env"].read_text().splitlines() == ["%s|%s" % (conf, conf)]
    assert lines == ["[options]", "without_demo = False"]


def test_nothing_declared_passes_no_load_and_en_us_is_always_loaded(client, world):
    _checkout(world, SERIES)
    lease = _lease(client, world)
    job = _ok(_build(client, world, lease["token"]))
    _wait(client, job["job_id"])
    (argv,) = _odoo_calls(world)
    assert _flags(argv, "--load=") == [] and job["server_wide_modules"] == []
    assert _flags(argv, "--load-language") == ["--load-language=en_US"]


def test_a_lease_written_without_the_key_uses_the_catalog_rows_set(client, world):
    """A lease an older allocator wrote carries no server_wide_modules: the catalog row the lease
    was acquired for decides, rather than silently loading nothing."""
    _declare_server_wide(world, ["to_base"])
    _checkout(world, SERIES)
    lease = _lease(client, world)
    reg = world["home"] / "runtime" / "leases.json"
    doc = json.loads(reg.read_text())
    for row in doc["leases"]:
        row.pop("server_wide_modules", None)
    reg.write_text(json.dumps(doc), encoding="utf-8")
    job = _ok(_build(client, world, lease["token"]))
    assert job["server_wide_modules"] == ["base", "web", "to_base"]


def _drop_core_load(world):
    """The checkout's config.py keeps every other option but no longer states its --load default."""
    config = world["odoo_bin"].parent / "odoo" / "tools" / "config.py"
    config.write_text("\n".join(ln for ln in config.read_text().splitlines() if '"--load"' not in ln),
                      encoding="utf-8")


def test_declared_modules_with_an_unreadable_core_are_refused_before_anything_starts(client, world):
    _declare_server_wide(world, ["to_base"])
    _drop_core_load(world)
    lease = _lease(client, world)
    err = _err(_build(client, world, lease["token"]))
    assert err["code"] == "SERVER_WIDE_CORE_UNKNOWN"
    assert "odoo_root" in err["remedy"] and "--load" in err["remedy"]
    assert _jobs(world) == [] and _odoo_calls(world) == []


# --------------------------------------------------------------------------- #
# demo policy
# --------------------------------------------------------------------------- #
def test_demo_is_required_for_init_and_refused_for_update(client, world):
    """Demo data loads when a module is installed; an update never adds it to the modules the
    database holds, so a demo value on an update would only be misrecorded on the lease."""
    lease = _lease(client, world, ports=1)
    err = _err(_build(client, world, lease["token"], op="init", demo=None))
    assert err["code"] == "INVALID_ARGUMENTS" and "arguments.demo" in err["message"]
    for demo in ("on", "off"):
        err = _err(_build(client, world, lease["token"], op="update", demo=demo))
        assert err["code"] == "INVALID_ARGUMENTS" and "arguments.demo" in err["message"], err
        assert "op init" in err["message"], err["message"]
    assert _jobs(world) == []
    row = next(r for r in _registry(world) if r["token"] == lease["token"])
    assert (row.get("built") or {}).get("demo") is None, "a refused update records nothing"
    _ok(_build(client, world, lease["token"], op="update", demo=None))


@pytest.mark.parametrize("checkout,default", [("17.0", "on"), ("8.0", "on"), ("18.0", "on"),
                                              ("19.0", "off"), ("20.0", "off")])
def test_a_test_build_without_demo_runs_with_the_series_default(world, checkout, default):
    """Automation tests run as the series runs its own: with demo where the series loads it by
    default, without it where demo is opt-in - read from the lease's checkout, stated explicitly
    to odoo-bin (so no config value can flip it), and the value used is reported and recorded (not
    left unstated)."""
    _declare_series(world, checkout)
    with McpClient(world["env"](), world["work"]) as c:
        c.initialize()
        lease = _lease(c, world, series=checkout, ports=1)
        job = _ok(_build(c, world, lease["token"], op="test", demo=None, test_tags="/my_mod"))
        assert job["demo"] == default
        row = next(r for r in _registry(world) if r["token"] == lease["token"])
        assert row["built"]["demo"] is (default == "on"), "recorded on the lease"
        done = _wait(c, job["job_id"])
    assert done["demo"] == default
    (argv,) = _odoo_calls(world)
    flag = {"on": DEMO_ON_FLAG, "off": DEMO_OFF_FLAG}[default].get(checkout) if checkout in BUILD_SERIES \
        else None
    assert _flags(argv, "--with", "--without") == ([flag] if flag else [])
    ((_conf, lines),) = _run_confs(world)
    assert lines == ["[options]"] + (DEMO_ON_CONF.get(checkout, []) if default == "on" else [])


@pytest.mark.parametrize("series", ["8.0", "17.0", "18.0", "19.0", "20.0"])
@pytest.mark.parametrize("demo", ["on", "off"])
def test_a_test_build_refuses_any_demo_argument_on_every_series(world, series, demo):
    """An automation test build always runs with the series default, so the default is the only
    path: an explicit demo - even one equal to the default - is refused before anything starts,
    and the message says to omit it."""
    _declare_series(world, series)
    with McpClient(world["env"](), world["work"]) as c:
        c.initialize()
        lease = _lease(c, world, series=series, ports=1)
        err = _err(_build(c, world, lease["token"], op="test", demo=demo, test_tags="/my_mod"))
    assert err["code"] == "INVALID_ARGUMENTS", err
    assert "arguments.demo" in err["message"] and "omit demo" in err["message"], err["message"]
    assert _jobs(world) == [] and _odoo_calls(world) == []


@pytest.mark.parametrize("series,refused", [("19.0", True), ("20.0", True), ("17.0", False),
                                            ("8.0", False)])
def test_a_test_build_on_a_database_filled_with_demo_is_refused_where_demo_is_opt_in(
        world, series, refused):
    _declare_series(world, series)
    with McpClient(world["env"](), world["work"]) as c:
        c.initialize()
        lease = _lease(c, world, series=series, ports=1)
        init = _ok(_build(c, world, lease["token"], demo="on"))
        assert _wait(c, init["job_id"])["instance_handle"]["demo"] is True, (
            "the build's demo is recorded on the lease")
        res = _build(c, world, lease["token"], op="test", test_mode="reuse", test_tags="/my_mod")
        if refused:
            err = _err(res)
            assert err["code"] == "TEST_DB_HAS_DEMO" and "lease_acquire" in err["remedy"]
            assert "omit demo" in err["remedy"] and "demo off" not in err["remedy"].split(
                "op init")[0], "the remedy must not tell a test build to pass demo"
        else:
            _ok(res)


@pytest.mark.parametrize("series,checkout,default", [("17.0", "19.0", "off"), ("19.0", "17.0", "on")])
def test_the_demo_policy_follows_the_leases_checkout_not_the_catalog_series(world, series, checkout,
                                                                            default):
    """Whether demo is opt-in is what the lease's checkout declares (--with-demo in its config.py);
    the catalog's series label never decides it - neither the default a test build runs with nor
    whether a demo database is refused."""
    _declare_series(world, series, checkout=checkout)
    with McpClient(world["env"](), world["work"]) as c:
        c.initialize()
        lease = _lease(c, world, series=series, ports=1)
        job = _ok(_build(c, world, lease["token"], op="test", test_tags="/my_mod"))
        assert job["demo"] == default
        _wait(c, job["job_id"])
        (argv,) = _odoo_calls(world)
        assert _flags(argv, "--with", "--without") == (
            ["--without-demo=True"] if default == "off" else []), "the default, stated explicitly"
        _wait(c, _ok(_build(c, world, lease["token"], demo="on"))["job_id"])
        res = _build(c, world, lease["token"], op="test", test_mode="reuse", test_tags="/my_mod")
        if default == "off":
            assert _err(res)["code"] == "TEST_DB_HAS_DEMO"
        else:
            _ok(res)


# --------------------------------------------------------------------------- #
# demo facts belong to the DATABASE: every lease on it sees them
# --------------------------------------------------------------------------- #
def _second_lease_on(c, world, db_name, series, **over):
    """An exclusive, no-create lease on a database another lease built - what an agent holding a
    forwarded INSTANCE_HANDLE takes to run its own build on that database."""
    args = dict(series=series, mode="exclusive", db_name=db_name, ports=1)
    args.update(over)
    return _lease(c, world, **args)


def _edit_row(world, token, **fields):
    reg = world["home"] / "runtime" / "leases.json"
    doc = json.loads(reg.read_text())
    for row in doc["leases"]:
        if row["token"] == token:
            row.update(fields)
    reg.write_text(json.dumps(doc), encoding="utf-8")


@pytest.mark.parametrize("series", ["19.0", "20.0"])
def test_a_test_build_on_a_forwarded_database_built_with_demo_is_refused(world, series):
    """The provider built the database with demo on its own lease; the consumer takes an exclusive
    lease on the same database to run tests. Demo data is a fact of the DATABASE, so the consumer's
    fresh lease - which recorded no build - must still see it, and the test build is refused."""
    _declare_series(world, series)
    with McpClient(world["env"](), world["work"]) as c:
        c.initialize()
        provider = _lease(c, world, series=series)
        _wait(c, _ok(_build(c, world, provider["token"], demo="on", languages=["vi_VN"]))["job_id"])
        consumer = _second_lease_on(c, world, provider["db_name"], series)
        assert consumer["built"] == {"demo": None, "languages": []}, "the consumer's own lease built nothing"
        err = _err(_build(c, world, consumer["token"], op="test", test_mode="reuse", test_tags="/my_mod"))
        assert err["code"] == "TEST_DB_HAS_DEMO", err
        assert err["diagnostics"]["token_prefix"] == consumer["token"][:8]
        assert len(_odoo_calls(world)) == 1, "only the provider's build ran"


def test_the_handle_of_a_second_lease_on_a_database_carries_that_databases_build_facts(world):
    """A consumer that reads the handle of its own lease on a forwarded database learns what the
    database holds (demo, proven languages), not an empty 'nothing recorded'."""
    with McpClient(world["env"](), world["work"]) as c:
        c.initialize()
        provider = _lease(c, world)
        _wait(c, _ok(_build(c, world, provider["token"], demo="on"))["job_id"])
        _record_languages(world, provider["token"], ["en_US", "vi_VN"])
        acquired = _ok(c.call("lease_acquire", {"series": SERIES, "run_id": RUN, "mode": "exclusive",
                                                "db_name": provider["db_name"], "no_create": True,
                                                "cwd": str(world["work"])}))
        assert acquired["instance_handle"]["demo"] is True
        assert acquired["instance_handle"]["languages_loaded"] == ["en_US", "vi_VN"]
        job = _ok(_build(c, world, acquired["lease"]["token"], op="update"))
        done = _wait(c, job["job_id"])
        assert done["instance_handle"]["demo"] is True
        assert done["instance_handle"]["languages_loaded"] == ["en_US", "vi_VN"]


def _record_languages(world, token, languages):
    """Record proven languages on a lease the way job_wait does (allocator record-build)."""
    import subprocess
    alloc = Path(__file__).resolve().parent.parent / "plugins" / "odoo-ai-agents" / "scripts" / "lib" / "allocator.py"
    subprocess.run([sys.executable, str(alloc), "record-build", token, "--languages", ",".join(languages)],
                   env=world["env"](), check=True, capture_output=True, timeout=60)


def test_a_database_with_the_same_name_on_another_cluster_is_another_database(world):
    """Rows naming the same database on DIFFERENT Postgres coordinates describe two databases:
    the demo one build loaded on one cluster never refuses a test build on the other."""
    _declare_series(world, "19.0")
    with McpClient(world["env"](), world["work"]) as c:
        c.initialize()
        provider = _lease(c, world, series="19.0")
        _wait(c, _ok(_build(c, world, provider["token"], demo="on"))["job_id"])
        consumer = _second_lease_on(c, world, provider["db_name"], "19.0")
        _edit_row(world, provider["token"], db_port="5999")
        _edit_row(world, consumer["token"], db_port="5433")
        _ok(_build(c, world, consumer["token"], op="test", test_mode="reuse", test_tags="/my_mod"))


def test_a_database_built_without_demo_by_another_lease_is_not_refused(world):
    _declare_series(world, "19.0")
    with McpClient(world["env"](), world["work"]) as c:
        c.initialize()
        provider = _lease(c, world, series="19.0")
        _wait(c, _ok(_build(c, world, provider["token"], demo="off"))["job_id"])
        consumer = _second_lease_on(c, world, provider["db_name"], "19.0")
        _ok(_build(c, world, consumer["token"], op="test", test_mode="reuse", test_tags="/my_mod"))


def test_a_checkout_stating_no_demo_option_is_refused_before_anything_starts(client, world):
    config = world["odoo_bin"].parent / "odoo" / "tools" / "config.py"
    config.write_text("\n".join(ln for ln in config.read_text().splitlines() if "demo" not in ln),
                      encoding="utf-8")
    lease = _lease(client, world, ports=1)
    for over in ({"op": "init", "demo": "off"}, {"op": "test", "test_tags": "/my_mod"}):
        err = _err(_build(client, world, lease["token"], **over))
        op = over["op"]
        assert err["code"] == "ODOO_SOURCE_FACT_UNKNOWN" and "demo" in err["message"], op
        assert "odoo_root" in err["remedy"]
    assert _jobs(world) == [] and _odoo_calls(world) == []


def test_demo_once_loaded_stays_on_the_handle(client, world):
    lease = _lease(client, world)
    _wait(client, _ok(_build(client, world, lease["token"], demo="on"))["job_id"])
    later = _wait(client, _ok(_build(client, world, lease["token"], demo="off"))["job_id"])
    assert later["instance_handle"]["demo"] is True
    row = next(r for r in _registry(world) if r["token"] == lease["token"])
    assert row["built"]["demo"] is True


# --------------------------------------------------------------------------- #
# extra_args may not carry a build fact
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("token,points_at", [("--load=base,web", "server-wide"),
                                             ("--load-language=fr_FR", "languages argument"),
                                             ("-lfr_FR", "languages argument"),
                                             ("--without-demo=all", "demo argument"),
                                             ("--with-demo", "demo argument")])
def test_a_build_fact_in_extra_args_is_refused_naming_the_input_that_sets_it(client, world, token,
                                                                             points_at):
    lease = _lease(client, world)
    err = _err(_build(client, world, lease["token"], extra_args=[token]))
    assert err["code"] == "INVALID_ARGUMENTS" and points_at in err["message"], err["message"]


# --------------------------------------------------------------------------- #
# job_wait: languages, warnings, the handle
# --------------------------------------------------------------------------- #
LOG_LINES = (
    "odoo.addons.base.models.ir_module: module base: loading translation file /x/base/i18n/vi.po "
    "for language vi_VN ",
    "odoo.addons.base.models.ir_module: module web: no translation for language vi_VN",
    "WARNING db odoo.addons.viin_brand: The module `viin_brand` should be loaded in server wide mode "
    "using `--load` option when starting Odoo server (e.g. --load=base,web,viin_brand).",
    "WARNING db odoo.modules.loading: Module my_mod demo data failed to install, installed without "
    "demo data",
)


def test_job_wait_reports_proven_languages_warnings_and_a_real_handle(client, world):
    world["behavior"].write_text("".join('echo "%s"\n' % ln.replace("`", "\\`") for ln in LOG_LINES)
                                 + 'echo "odoo.modules.loading: Modules loaded."\nexit 0\n',
                                 encoding="utf-8")
    lease = _lease(client, world)
    job = _ok(_build(client, world, lease["token"], languages=["vi_VN", "xx_XX"]))
    done = _wait(client, job["job_id"])
    assert done["result"] == "success"
    assert done["languages_loaded"] == ["en_US", "vi_VN"]
    assert done["languages_failed"] == ["xx_XX"], "a language with no load evidence is not loaded"
    wide = [w for w in done["warnings"] if "viin_brand" in w]
    assert wide and "server_wide_modules" in wide[0] and "odoo-setup" in wide[0]
    assert any("my_mod" in w and "WITHOUT demo" in w for w in done["warnings"])
    handle = done["instance_handle"]
    assert handle["demo"] is False and handle["languages_loaded"] == ["en_US", "vi_VN"]
    assert handle["lease_token"] == lease["token"]
    row = next(r for r in _registry(world) if r["token"] == lease["token"])
    assert row["built"] == {"demo": False, "languages": ["en_US", "vi_VN"]}


def test_a_failed_build_proves_no_en_us_and_a_running_one_reports_nothing_yet(client, world):
    world["behavior"].write_text('sleep 3\necho "CRITICAL boom"\nexit 1\n', encoding="utf-8")
    lease = _lease(client, world)
    job_id = _ok(_build(client, world, lease["token"]))["job_id"]
    running = _wait(client, job_id, timeout_s=1)
    assert running["result"] == "timeout"
    assert running["languages_loaded"] is None and running["instance_handle"] is None
    done = _wait(client, job_id)
    assert done["result"] == "failure"
    assert done["languages_loaded"] == [] and done["languages_failed"] == ["en_US"]


@pytest.mark.parametrize("suite,result", [
    ('echo "odoo.tests.result: 1 failed, 0 error(s) of 3 tests when loading database"\nexit 1\n',
     "failure"),
    ('echo "odoo.tests: skipped test_x"\nexit 0\n', "inconclusive"),
])
def test_a_test_build_whose_modules_loaded_proves_its_languages_whatever_the_suite_says(
        world, suite, result):
    """The languages are activated while the modules load; the test suite runs after that. A
    failed or inconclusive SUITE says nothing about whether en_US and the requested languages were
    loaded - reporting en_US as failed there would be false."""
    world["behavior"].write_text(
        'echo "odoo.addons.base.models.ir_module: module base: loading translation file '
        '/x/base/i18n/vi.po for language vi_VN"\n'
        'echo "odoo.modules.loading: Modules loaded."\n' + suite, encoding="utf-8")
    with McpClient(world["env"](), world["work"]) as c:
        c.initialize()
        lease = _lease(c, world, ports=1)
        done = _wait(c, _ok(_build(c, world, lease["token"], op="test", test_tags="/my_mod",
                                   languages=["vi_VN", "xx_XX"]))["job_id"])
    assert done["result"] == result, done
    assert done["languages_loaded"] == ["en_US", "vi_VN"]
    assert done["languages_failed"] == ["xx_XX"], "only the language nothing proved loaded"


def test_a_build_that_stopped_before_its_modules_loaded_proves_no_en_us(client, world):
    world["behavior"].write_text('echo "Traceback (most recent call last):"\nexit 1\n',
                                 encoding="utf-8")
    lease = _lease(client, world, ports=1)
    done = _wait(client, _ok(_build(client, world, lease["token"], op="test",
                                    test_tags="/my_mod"))["job_id"])
    assert done["result"] == "failure"
    assert done["languages_loaded"] == [] and done["languages_failed"] == ["en_US"]


def test_a_server_wide_warning_names_the_leases_catalog_row_by_its_key(world):
    """The remedy must select THE row the lease came from: a series may declare several
    profiles, so "series 17.0" alone sends the operator to the wrong one."""
    toml = world["home"] / "instances.toml"
    toml.write_text(toml.read_text() + 'profile = "std_17"\n', encoding="utf-8")
    world["behavior"].write_text("".join('echo "%s"\n' % ln.replace("`", "\\`") for ln in LOG_LINES)
                                 + 'echo "odoo.modules.loading: Modules loaded."\nexit 0\n',
                                 encoding="utf-8")
    with McpClient(world["env"](), world["work"]) as c:
        c.initialize()
        lease = _lease(c, world, profile="std_17")
        done = _wait(c, _ok(_build(c, world, lease["token"]))["job_id"])
    (wide,) = [w for w in done["warnings"] if "viin_brand" in w]
    assert "17.0:std_17" in wide, wide
    assert "refresh --version 17.0 --profile std_17" in wide, wide


def test_a_clean_build_has_no_warnings(client, world):
    lease = _lease(client, world)
    done = _wait(client, _ok(_build(client, world, lease["token"]))["job_id"])
    assert done["warnings"] == [] and done["languages_loaded"] == ["en_US"]


# --------------------------------------------------------------------------- #
# instance_serve
# --------------------------------------------------------------------------- #
def _served_conf(world):
    return "\n".join(p.read_text() for p in (world["home"] / "conf").glob("*.conf"))


def test_serve_writes_the_resolved_server_wide_set_into_the_conf(client, world):
    _declare_server_wide(world, ["to_base"])
    _checkout(world, SERIES)
    lease = _lease(client, world, ports=1)
    out = _ok(client.call("instance_serve", {"lease_token": lease["token"], "cwd": str(world["work"])},
                          timeout=120))
    assert out["served_server_wide_modules"] == ["base", "web", "to_base"]
    assert "server_wide_modules = base,web,to_base" in _served_conf(world)
    _ok(client.call("lease_release", {"lease_token": lease["token"], "run_id": RUN}))


def test_serve_by_series_resolves_the_catalog_rows_set(client, world):
    _declare_server_wide(world, ["viin_brand"])
    _checkout(world, "19.0")
    out = _ok(client.call("instance_serve", {"series": SERIES, "run_id": RUN, "cwd": str(world["work"])},
                          timeout=120))
    assert out["served_server_wide_modules"] == ["base", "rpc", "web", "viin_brand"]


def test_serve_refuses_declared_modules_with_an_unreadable_core_and_launches_nothing(client, world):
    _declare_server_wide(world, ["to_base"])
    _drop_core_load(world)
    lease = _lease(client, world, ports=1)
    err = _err(client.call("instance_serve", {"lease_token": lease["token"], "cwd": str(world["work"])},
                           timeout=120))
    assert err["code"] == "SERVER_WIDE_CORE_UNKNOWN"
    assert not (world["home"] / "conf").is_dir() or not list((world["home"] / "conf").glob("*.conf"))
    row = next(r for r in _registry(world) if r["token"] == lease["token"])
    assert (row.get("owner") or {}).get("pid") is None, "nothing was launched or bound"


def test_serve_takes_no_agent_supplied_load(client, world):
    lease = _lease(client, world, ports=1)
    err = _err(client.call("instance_serve", {"lease_token": lease["token"],
                                              "load_modules": ["base", "web"]}))
    assert err["code"] == "INVALID_ARGUMENTS" and "load_modules" in err["message"]


# --------------------------------------------------------------------------- #
# the facts are visible where agents read leases and the catalog
# --------------------------------------------------------------------------- #
def test_lease_and_catalog_expose_the_declared_set(client, world):
    _declare_server_wide(world, ["to_base"])
    lease = _lease(client, world)
    assert lease["server_wide_modules"] == ["to_base"]
    assert lease["built"] == {"demo": None, "languages": []}
    rows = _ok(client.call("catalog_read", {"cwd": str(world["work"])}))["rows"]
    assert [r["server_wide_modules"] for r in rows] == [["to_base"]]
    listed = next(r for r in _ok(client.call("lease_list", {}))["leases"] if r["token"] == lease["token"])
    assert listed["server_wide_modules"] == ["to_base"]
