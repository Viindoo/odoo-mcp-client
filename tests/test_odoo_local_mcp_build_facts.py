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
  - instance_serve writes the same resolved set into the served conf and takes no complete set
    from the agent (no load_modules, no --load);
  - `server_wide` adjusts the set for ONE call (instance_build, and instance_serve on a lease of
    the caller's own): core default + (declared - exclude) + include, core first, passed as --load;
    a core or undeclared exclude, a module in both lists and an include Odoo cannot find are
    refused before anything starts; the lease and the catalog keep the default for the next call;
    a running server cannot be re-set by an attach.
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
# Demo OFF is spelled --without-demo=True on every series, so it is checked on one series of each
# option era (before 19.0 the checkout declares only --without-demo; from 19.0 --with-demo too).
DEMO_OFF_SERIES = ("8.0", "19.0")


@pytest.mark.parametrize("series", BUILD_SERIES)
def test_a_build_carries_load_languages_and_the_series_demo_flag(world, series):
    _declare_series(world, series)
    _declare_server_wide(world, ["to_base", "web"])
    _checkout(world, series)
    expected_load = trees.CORE_LOAD[series] + [m for m in ("to_base", "web")
                                               if m not in trees.CORE_LOAD[series]]
    with McpClient(world["env"](), world["work"]) as c:
        c.initialize()
        lease = _lease(c, world, series=series)
        for demo in ("on", "off") if series in DEMO_OFF_SERIES else ("on",):
            job = _ok(_build(c, world, lease["token"], demo=demo, languages=["vi_VN", "en_US"]))
            assert _wait(c, job["job_id"])["result"] == "success"
            assert job["server_wide_modules"] == expected_load
            assert job["languages"] == ["en_US", "vi_VN"], "en_US first, never twice"
            argv = _odoo_calls(world)[-1]
            assert _flags(argv, "--load=") == ["--load=" + ",".join(expected_load)], (series, demo)
            assert _flags(argv, "--load-language") == ["--load-language=en_US,vi_VN"], (series, demo)
            flag = (DEMO_ON_FLAG if demo == "on" else DEMO_OFF_FLAG)[series]
            assert _flags(argv, "--with", "--without") == ([flag] if flag else []), (series, demo)
            conf, lines = _run_confs(world)[-1]
            assert _conf_of(argv) == conf, "odoo-bin reads the tool's config file, never ~/.odoorc"
            assert lines == ["[options]"] + (DEMO_ON_CONF[series] if demo == "on" else []), (
                "the run's config file states only what the build itself states", series, demo)
            if series == "8.0":
                # openerp/ (the oldest series) reads $OPENERP_SERVER, not $ODOO_RC, at import time.
                assert world["rc_env"].read_text().splitlines()[-1] == "%s|%s" % (conf, conf)


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


def _drop_core_load(world):
    """The checkout's config.py keeps every other option but no longer states its --load default."""
    config = world["odoo_bin"].parent / "odoo" / "tools" / "config.py"
    config.write_text("\n".join(ln for ln in config.read_text().splitlines() if '"--load"' not in ln),
                      encoding="utf-8")


def test_the_server_wide_set_is_what_the_catalog_declares_and_never_guessed(client, world):
    _checkout(world, SERIES)
    lease = _lease(client, world)
    job = _ok(_build(client, world, lease["token"]))
    _wait(client, job["job_id"])
    (argv,) = _odoo_calls(world)
    assert _flags(argv, "--load=") == [] and job["server_wide_modules"] == []
    assert _flags(argv, "--load-language") == ["--load-language=en_US"], "nothing declared: no --load"

    # A lease an older allocator wrote carries no server_wide_modules: the catalog row the lease
    # was acquired for decides, rather than silently loading nothing.
    _declare_server_wide(world, ["to_base"])
    lease = _lease(client, world)
    reg = world["home"] / "runtime" / "leases.json"
    doc = json.loads(reg.read_text())
    for row in doc["leases"]:
        row.pop("server_wide_modules", None)
    reg.write_text(json.dumps(doc), encoding="utf-8")
    job = _ok(_build(client, world, lease["token"]))
    assert job["server_wide_modules"] == ["base", "web", "to_base"]
    _wait(client, job["job_id"])  # the checkout is read by the build: let it finish before editing it

    # Declared modules with an unreadable core default are refused, and nothing is started.
    _drop_core_load(world)
    before = len(_odoo_calls(world))
    lease = _lease(client, world)
    err = _err(_build(client, world, lease["token"]))
    assert err["code"] == "SERVER_WIDE_CORE_UNKNOWN"
    assert "odoo_root" in err["remedy"] and "--load" in err["remedy"]
    assert len(_odoo_calls(world)) == before


# --------------------------------------------------------------------------- #
# demo policy
# --------------------------------------------------------------------------- #
def test_the_demo_argument_is_required_for_init_and_refused_everywhere_else(client, world):
    """Demo data loads when a module is installed; an update never adds it to the modules the
    database holds, so a demo value on an update would only be misrecorded on the lease. An
    automation test build always runs with the series default, so the default is the only path: an
    explicit demo - even one equal to the default - is refused on every series, and the message
    says to omit it. A checkout that states no demo option cannot spell either."""
    lease = _lease(client, world, ports=1)
    err = _err(_build(client, world, lease["token"], op="init", demo=None))
    assert err["code"] == "INVALID_ARGUMENTS" and "arguments.demo" in err["message"]
    for demo in ("on", "off"):
        err = _err(_build(client, world, lease["token"], op="update", demo=demo))
        assert err["code"] == "INVALID_ARGUMENTS" and "arguments.demo" in err["message"], err
    row = next(r for r in _registry(world) if r["token"] == lease["token"])
    assert (row.get("built") or {}).get("demo") is None, "a refused update records nothing"
    for series in ("8.0", "17.0", "18.0", "19.0", "20.0"):
        _declare_series(world, series)
        leased = _lease(client, world, series=series, ports=1)
        for demo in ("on", "off"):
            err = _err(_build(client, world, leased["token"], op="test", demo=demo, test_tags="/my_mod"))
            assert err["code"] == "INVALID_ARGUMENTS", (series, demo, err)
            assert "arguments.demo" in err["message"], err["message"]
        _ok(client.call("lease_release", {"lease_token": leased["token"], "run_id": RUN}))
    config = world["odoo_bin"].parent / "odoo" / "tools" / "config.py"
    config.write_text("\n".join(ln for ln in config.read_text().splitlines() if "demo" not in ln),
                      encoding="utf-8")
    for over in ({"op": "init", "demo": "off"}, {"op": "test", "test_tags": "/my_mod"}):
        err = _err(_build(client, world, lease["token"], **over))
        assert err["code"] == "ODOO_SOURCE_FACT_UNKNOWN" and "demo" in err["message"], over
        assert "odoo_root" in err["remedy"]
    assert _jobs(world) == [] and _odoo_calls(world) == [], "every refusal came before anything started"


# The demo policy is what the lease's CHECKOUT declares (--with-demo in its config.py), never the
# catalog's series label: (catalog series, checkout, the demo a test build runs with).
DEMO_CASES = [("8.0", "8.0", "on"), ("18.0", "18.0", "on"), ("19.0", "19.0", "off"),
              ("20.0", "20.0", "off"), ("17.0", "19.0", "off"), ("19.0", "17.0", "on")]


@pytest.mark.parametrize("series,checkout,default", DEMO_CASES)
def test_the_demo_a_test_build_runs_with_and_refuses_follows_the_leases_checkout(world, series, checkout,
                                                                               default):
    """Automation tests run as the series runs its own: with demo where the checkout loads it by
    default, without it where demo is opt-in - stated explicitly to odoo-bin (so no config value
    can flip it), reported and recorded. Where demo is opt-in a test build on a database any build
    filled with demo is refused (and told to omit demo); elsewhere it runs."""
    _declare_series(world, series, checkout=checkout)
    with McpClient(world["env"](), world["work"]) as c:
        c.initialize()
        lease = _lease(c, world, series=series, ports=1)
        job = _ok(_build(c, world, lease["token"], op="test", demo=None, test_tags="/my_mod"))
        assert job["demo"] == default
        row = next(r for r in _registry(world) if r["token"] == lease["token"])
        assert row["built"]["demo"] is (default == "on"), "recorded on the lease"
        done = _wait(c, job["job_id"])
        assert done["demo"] == default
        (argv,) = _odoo_calls(world)
        flag = ({"on": DEMO_ON_FLAG, "off": DEMO_OFF_FLAG}[default].get(checkout)
                if checkout in BUILD_SERIES else None)
        assert _flags(argv, "--with", "--without") == ([flag] if flag else [])
        ((_conf, lines),) = _run_confs(world)
        assert lines == ["[options]"] + (DEMO_ON_CONF.get(checkout, []) if default == "on" else [])

        init = _ok(_build(c, world, lease["token"], demo="on"))
        assert _wait(c, init["job_id"])["instance_handle"]["demo"] is True, (
            "the build's demo is recorded on the lease")
        res = _build(c, world, lease["token"], op="test", test_mode="reuse", test_tags="/my_mod")
        if default == "off":
            err = _err(res)
            assert err["code"] == "TEST_DB_HAS_DEMO" and "lease_acquire" in err["remedy"]
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


def _record_languages(world, token, languages):
    """Record proven languages on a lease the way job_wait does (allocator record-build)."""
    import subprocess
    alloc = Path(__file__).resolve().parent.parent / "plugins" / "odoo-ai-agents" / "scripts" / "lib" / "allocator.py"
    subprocess.run([sys.executable, str(alloc), "record-build", token, "--languages", ",".join(languages)],
                   env=world["env"](), check=True, capture_output=True, timeout=60)


def test_demo_and_languages_are_facts_of_the_database_every_lease_on_it_sees(world):
    """The provider built the database with demo on its own lease; the consumer takes an exclusive
    lease on the same database. Demo data is a fact of the DATABASE, so the consumer's fresh lease -
    which recorded no build - must still see it: its test build is refused, its handle states what
    the database holds, and demo once loaded stays on the handle. A database of the same name on
    another cluster is another database, and one built without demo refuses nothing."""
    _declare_series(world, "19.0")
    with McpClient(world["env"](), world["work"]) as c:
        c.initialize()
        provider = _lease(c, world, series="19.0")
        _wait(c, _ok(_build(c, world, provider["token"], demo="on", languages=["vi_VN"]))["job_id"])
        later = _wait(c, _ok(_build(c, world, provider["token"], demo="off"))["job_id"])
        assert later["instance_handle"]["demo"] is True, "demo once loaded stays on the handle"
        assert next(r for r in _registry(world) if r["token"] == provider["token"])["built"]["demo"] is True

        _record_languages(world, provider["token"], ["en_US", "vi_VN"])
        acquired = _ok(c.call("lease_acquire", {"series": "19.0", "run_id": RUN, "mode": "exclusive",
                                                "db_name": provider["db_name"], "no_create": True,
                                                "ports": 1, "cwd": str(world["work"])}))
        consumer = acquired["lease"]
        assert consumer["built"] == {"demo": None, "languages": []}, "the consumer's own lease built nothing"
        err = _err(_build(c, world, consumer["token"], op="test", test_mode="reuse", test_tags="/my_mod"))
        assert err["code"] == "TEST_DB_HAS_DEMO", err
        assert err["diagnostics"]["token_prefix"] == consumer["token"][:8]
        assert len(_odoo_calls(world)) == 2, "only the provider's two builds ran"

        # The handle of a lease taken on that database learns what the database holds.
        assert acquired["instance_handle"]["demo"] is True
        assert acquired["instance_handle"]["languages_loaded"] == ["en_US", "vi_VN"]
        done = _wait(c, _ok(_build(c, world, consumer["token"], op="update"))["job_id"])
        assert done["instance_handle"]["demo"] is True
        assert done["instance_handle"]["languages_loaded"] == ["en_US", "vi_VN"]

        # Rows naming the same database on DIFFERENT Postgres coordinates describe two databases:
        # the demo one build loaded on one cluster never refuses a test build on the other.
        _edit_row(world, provider["token"], db_port="5999")
        _edit_row(world, consumer["token"], db_port="5433")
        _ok(_build(c, world, consumer["token"], op="test", test_mode="reuse", test_tags="/my_mod"))

        # A database built without demo by another lease is not refused.
        plain = _lease(c, world, series="19.0")
        _wait(c, _ok(_build(c, world, plain["token"], demo="off"))["job_id"])
        reader = _second_lease_on(c, world, plain["db_name"], "19.0")
        _ok(_build(c, world, reader["token"], op="test", test_mode="reuse", test_tags="/my_mod"))


# --------------------------------------------------------------------------- #
# extra_args may not carry a build fact
# --------------------------------------------------------------------------- #
BUILD_FACT_TOKENS = [("--load=base,web", "server_wide argument"),
                     ("--load-language=fr_FR", "languages argument"),
                     ("-lfr_FR", "languages argument"),
                     ("--without-demo=all", "demo argument"),
                     ("--with-demo", "demo argument")]


def test_a_build_fact_in_extra_args_is_refused_naming_the_input_that_sets_it(client, world):
    lease = _lease(client, world)
    for token, points_at in BUILD_FACT_TOKENS:
        err = _err(_build(client, world, lease["token"], extra_args=[token]))
        assert err["code"] == "INVALID_ARGUMENTS" and points_at in err["message"], (token, err["message"])


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


def _lang_line(code):
    return ('echo "odoo.addons.base.models.ir_module: module base: loading translation file '
            '/x/base/i18n/%s.po for language %s"\n' % (code.split("_")[0], code))


def test_job_wait_reports_proven_languages_warnings_and_a_real_handle(world):
    """The remedy of a server-wide warning must select THE row the lease came from: a series may
    declare several profiles, so "series 17.0" alone sends the operator to the wrong one."""
    toml = world["home"] / "instances.toml"
    toml.write_text(toml.read_text() + 'profile = "std_17"\n', encoding="utf-8")
    world["behavior"].write_text("".join('echo "%s"\n' % ln.replace("`", "\\`") for ln in LOG_LINES)
                                 + 'echo "odoo.modules.loading: Modules loaded."\nexit 0\n',
                                 encoding="utf-8")
    gate = world["work"] / "build-gate"
    with McpClient(world["env"](), world["work"]) as c:
        c.initialize()
        lease = _lease(c, world, profile="std_17")
        job = _ok(_build(c, world, lease["token"], languages=["vi_VN", "xx_XX"]))
        done = _wait(c, job["job_id"])
        assert done["result"] == "success"
        assert done["languages_loaded"] == ["en_US", "vi_VN"]
        assert done["languages_failed"] == ["xx_XX"], "a language with no load evidence is not loaded"
        (wide,) = [w for w in done["warnings"] if "viin_brand" in w]
        assert "server_wide_modules" in wide and "odoo-setup" in wide
        assert 'server_wide.include ["viin_brand"]' in wide, (
            "the warning names the per-call route as well as the catalog route")
        assert "17.0:std_17" in wide and "refresh --version 17.0 --profile std_17" in wide, wide
        assert any("my_mod" in w and "WITHOUT demo" in w for w in done["warnings"])
        handle = done["instance_handle"]
        assert handle["demo"] is False and handle["languages_loaded"] == ["en_US", "vi_VN"]
        assert handle["lease_token"] == lease["token"]
        row = next(r for r in _registry(world) if r["token"] == lease["token"])
        assert row["built"] == {"demo": False, "languages": ["en_US", "vi_VN"]}

        # A clean build has no warnings.
        world["behavior"].write_text('echo "odoo.modules.loading: Modules loaded."\nexit 0\n', encoding="utf-8")
        clean = _wait(c, _ok(_build(c, world, lease["token"]))["job_id"])
        assert clean["warnings"] == [] and clean["languages_loaded"] == ["en_US"]

        # A running build reports nothing yet; a failed one proves no en_US.
        world["behavior"].write_text('while [[ ! -f "%s" ]]; do sleep 0.1; done\necho "CRITICAL boom"\nexit 1\n'
                                     % gate, encoding="utf-8")
        job_id = _ok(_build(c, world, lease["token"]))["job_id"]
        running = _wait(c, job_id, timeout_s=1)
        assert running["result"] == "timeout"
        assert running["languages_loaded"] is None and running["instance_handle"] is None
        gate.write_text("go", encoding="utf-8")
        failed = _wait(c, job_id)
        assert failed["result"] == "failure"
        assert failed["languages_loaded"] == [] and failed["languages_failed"] == ["en_US"]

        # The summary schema leaves room for the keys the script may print beyond the documented
        # ones, and names where the languages came from.
        tools = c.request("tools/list")["result"]["tools"]
        (job_wait,) = [t for t in tools if t["name"] == "job_wait"]
        (out,) = [branch["properties"] for branch in job_wait["outputSchema"]["anyOf"]
                  if "job_id" in branch.get("properties", {})]
        assert out["languages_source"]["enum"] == ["database", "log", None]
        assert out["summary"].get("additionalProperties", True) is not False


def test_a_test_builds_proven_languages_are_read_from_the_modules_loading_not_the_suite(world):
    """The languages are activated while the modules load; the test suite runs after that. A
    failed or inconclusive SUITE says nothing about whether en_US and the requested languages were
    loaded - reporting en_US as failed there would be false. A build that stopped before its modules
    loaded proves no en_US; an at_install failure still proves it (Odoo logs "At least one test
    failed when loading the modules." instead of "Modules loaded.")."""
    loaded = ('echo "odoo.addons.base.models.ir_module: module base: loading translation file '
              '/x/base/i18n/vi.po for language vi_VN"\n'
              'echo "odoo.modules.loading: Modules loaded."\n')
    with McpClient(world["env"](), world["work"]) as c:
        c.initialize()
        lease = _lease(c, world, ports=1)

        def test_build(behavior, **over):
            world["behavior"].write_text(behavior, encoding="utf-8")
            return _wait(c, _ok(_build(c, world, lease["token"], op="test", test_tags="/my_mod",
                                       **over))["job_id"])

        for suite, result in (
                ('echo "odoo.tests.result: 1 failed, 0 error(s) of 3 tests when loading database"\nexit 1\n',
                 "failure"),
                ('echo "odoo.tests: skipped test_x"\nexit 0\n', "inconclusive")):
            done = test_build(loaded + suite, languages=["vi_VN", "xx_XX"])
            assert done["result"] == result, done
            assert done["languages_loaded"] == ["en_US", "vi_VN"], suite
            assert done["languages_failed"] == ["xx_XX"], "only the language nothing proved loaded"

        done = test_build('echo "Traceback (most recent call last):"\nexit 1\n')
        assert done["result"] == "failure"
        assert done["languages_loaded"] == [] and done["languages_failed"] == ["en_US"]

        done = test_build('echo "odoo.addons.my_mod.tests.test_x: FAIL: test_y"\n'
                          'echo "odoo.modules.loading: At least one test failed when loading the modules."\n'
                          "exit 1\n")
        assert done["result"] == "failure"
        assert done["summary"]["BUILD_MODULES_LOADED"] == "1"
        assert done["languages_loaded"] == ["en_US"] and done["languages_failed"] == []

        # The database's own active languages win over the log: a test may activate a language
        # inside its own transaction (rolled back), so the log shows Odoo loading its terms yet the
        # database never holds it.
        world["db_facts"].write_text("DB_EXISTS=1\nDEMO=0\nLANGUAGES=vi_VN,en_US\n", encoding="utf-8")
        done = test_build(_lang_line("vi_VN") + _lang_line("de_DE")
                          + 'echo "odoo.modules.loading: Modules loaded."\n' + _lang_line("fr_FR") + "exit 0\n",
                          languages=["vi_VN", "de_DE"])
        assert done["languages_source"] == "database"
        assert done["languages_loaded"] == ["en_US", "vi_VN"], "the database's own active set"
        assert done["languages_failed"] == ["de_DE"]
        assert done["instance_handle"]["facts_source"] == "database"

        # When the database cannot be read, only requested languages count from the log.
        world["db_facts"].unlink()
        done = test_build(_lang_line("vi_VN") + 'echo "odoo.modules.loading: Modules loaded."\n'
                          + _lang_line("fr_FR") + "exit 0\n", languages=["vi_VN"])
        assert done["languages_source"] == "log"
        assert done["languages_loaded"] == ["en_US", "vi_VN"], "fr_FR was never requested"
        assert done["languages_failed"] == []


def test_job_wait_names_a_missing_optional_test_import_with_its_remedy(client, world):
    """The checkout's test framework imports a package only when present (a fictional one here, so
    the venv can never import it); without it every browser, tour and Hoot test skips. job_wait
    names the package, the tests that skipped for it, and how to install it into the lease's venv -
    and warns nothing when the venv has every optional import."""
    dist = "fictional-browser-driver"
    trees.write_test_common(world["odoo_bin"].parent, SERIES,
                            imports=(("fictional_browser_driver", dist),))
    world["behavior"].write_text(
        'echo "odoo.modules.loading: Modules loaded."\n'
        'echo "INFO 1 insttest odoo.addons.web.tests.test_js: skipped test_qunit_desktop : %s module is not installed"\n'
        'echo "INFO 1 insttest odoo.tests.result: 0 failed, 0 error(s) of 3 tests"\nexit 0\n' % dist,
        encoding="utf-8")
    lease = _lease(client, world, ports=1)
    done = _wait(client, _ok(_build(client, world, lease["token"], op="test",
                                    test_tags="/my_mod"))["job_id"])
    assert done["summary"]["TEST_DEPS_MISSING"] == dist
    assert done["summary"]["TEST_DEPS_SKIPPED"] == dist
    (warning,) = [w for w in done["warnings"] if dist in w]
    assert "/odoo-ai-agents:odoo-setup" in warning and "create-venv" in warning
    assert str(world["python"]) in warning, "the remedy names the venv to install it into"

    trees.write_test_common(world["odoo_bin"].parent, SERIES, imports=(("json", None),))
    world["behavior"].write_text(
        'echo "odoo.modules.loading: Modules loaded."\n'
        'echo "INFO 1 insttest odoo.tests.result: 0 failed, 0 error(s) of 3 tests"\nexit 0\n',
        encoding="utf-8")
    done = _wait(client, _ok(_build(client, world, lease["token"], op="test",
                                    test_tags="/my_mod"))["job_id"])
    assert done["summary"]["TEST_DEPS_MISSING"] == ""
    assert not [w for w in done["warnings"] if "test framework" in w]


# --------------------------------------------------------------------------- #
# instance_serve
# --------------------------------------------------------------------------- #
def _served_conf(world):
    return "\n".join(p.read_text() for p in (world["home"] / "conf").glob("*.conf"))


def _no_conf_written(world):
    return not (world["home"] / "conf").is_dir() or not list((world["home"] / "conf").glob("*.conf"))


# --------------------------------------------------------------------------- #
# server_wide: the set adjusted for ONE call
# --------------------------------------------------------------------------- #
DECLARED = ["to_base", "viin_brand"]


def _addon(base, name):
    """A module directory Odoo would find: `<base>/<name>/__manifest__.py`."""
    (base / name).mkdir(parents=True, exist_ok=True)
    (base / name / "__manifest__.py").write_text("{'name': %r}\n" % name, encoding="utf-8")


def _load_of_last_build(world):
    return _flags(_odoo_calls(world)[-1], "--load=")


def _declared_world(world):
    _declare_server_wide(world, DECLARED)
    _checkout(world, SERIES)  # core default base,web


def test_serving_writes_the_resolved_and_the_adjusted_server_wide_set_into_the_conf(client, world):
    _declared_world(world)
    _addon(world["addons"], "my_wide")
    lease = _lease(client, world, ports=1)
    # The facts are visible where agents read leases and the catalog.
    assert lease["server_wide_modules"] == DECLARED
    assert lease["built"] == {"demo": None, "languages": []}
    rows = _ok(client.call("catalog_read", {"cwd": str(world["work"])}))["rows"]
    assert [r["server_wide_modules"] for r in rows] == [DECLARED]
    listed = next(r for r in _ok(client.call("lease_list", {}))["leases"] if r["token"] == lease["token"])
    assert listed["server_wide_modules"] == DECLARED

    out = _ok(client.call("instance_serve", {"lease_token": lease["token"], "cwd": str(world["work"])},
                          timeout=120))
    assert out["served_server_wide_modules"] == ["base", "web", "to_base", "viin_brand"]
    assert "server_wide_modules = base,web,to_base,viin_brand" in _served_conf(world)
    _ok(client.call("lease_release", {"lease_token": lease["token"], "run_id": RUN}))
    for conf in (world["home"] / "conf").glob("*.conf"):
        conf.unlink()
    (world["home"].parent / "curl-count").unlink(missing_ok=True)  # nothing listens yet again

    # An adjusted set is written as it is, and an attach cannot change the set of the server
    # already running: asking for the same set again attaches; asking for no adjustment reports the
    # set really serving; asking for another set is refused rather than reported as applied.
    lease = _lease(client, world, ports=1)
    wide = {"exclude": ["viin_brand"], "include": ["my_wide"]}
    serve = dict(lease_token=lease["token"], cwd=str(world["work"]))
    first = _ok(client.call("instance_serve", dict(serve, server_wide=wide), timeout=120))
    assert first["state"] == "launched"
    assert first["served_server_wide_modules"] == ["base", "web", "to_base", "my_wide"]
    assert first["server_wide_adjustment"] == {"exclude": ["viin_brand"], "include": ["my_wide"]}
    assert "server_wide_modules = base,web,to_base,my_wide" in _served_conf(world)
    again = _ok(client.call("instance_serve", dict(serve, server_wide=wide), timeout=120))
    assert again["state"] == "attached" and again["server_pid"] == first["server_pid"]
    plain = _ok(client.call("instance_serve", serve, timeout=120))
    assert plain["served_server_wide_modules"] == ["base", "web", "to_base", "my_wide"], (
        "an attach reports the set the running server was launched with")
    err = _err(client.call("instance_serve", dict(serve, server_wide={"exclude": ["to_base"]}),
                           timeout=120))
    assert err["code"] == "SERVER_WIDE_NOT_APPLIED", err
    assert err["diagnostics"]["running"] == ["base", "web", "to_base", "my_wide"]
    assert "lease_park" in err["remedy"]
    _ok(client.call("lease_release", {"lease_token": lease["token"], "run_id": RUN}))

    # The tool composes the --load set; an agent states only what to leave out or add. A complete
    # set under any name - the removed load_modules input, or a key server_wide does not define -
    # is refused before anything is launched; so is a declared set over an unreadable core.
    for conf in (world["home"] / "conf").glob("*.conf"):
        conf.unlink()
    lease = _lease(client, world, ports=1)
    for args in ({"load_modules": ["base", "web"]}, {"server_wide": {"set": ["base", "web"]}}):
        err = _err(client.call("instance_serve", dict(args, lease_token=lease["token"])))
        assert err["code"] == "INVALID_ARGUMENTS", args
        assert ("load_modules" if "load_modules" in args else "set") in err["message"], err["message"]
    assert _no_conf_written(world)
    _drop_core_load(world)
    err = _err(client.call("instance_serve", {"lease_token": lease["token"], "cwd": str(world["work"])},
                           timeout=120))
    assert err["code"] == "SERVER_WIDE_CORE_UNKNOWN"
    assert _no_conf_written(world)
    row = next(r for r in _registry(world) if r["token"] == lease["token"])
    assert (row.get("owner") or {}).get("pid") is None, "nothing was launched or bound"


def test_serving_by_series_resolves_the_catalog_rows_set_and_takes_no_adjustment(client, world):
    _declare_server_wide(world, ["viin_brand"])
    _checkout(world, "19.0")
    # The shared render server's set is the catalog row's for every reader.
    err = _err(client.call("instance_serve", {"series": SERIES, "run_id": RUN, "cwd": str(world["work"]),
                                              "server_wide": {"exclude": ["viin_brand"]}}))
    assert err["code"] == "INVALID_ARGUMENTS" and "arguments.server_wide" in err["message"]
    assert _no_conf_written(world)
    out = _ok(client.call("instance_serve", {"series": SERIES, "run_id": RUN, "cwd": str(world["work"])},
                          timeout=120))
    assert out["served_server_wide_modules"] == ["base", "rpc", "web", "viin_brand"]


def test_exclude_leaves_a_declared_module_out_for_that_build_only(client, world):
    """A database without the deployment's branding module: the build loads everything else, and
    the next build without server_wide is back on the deployment's set (nothing was recorded)."""
    _declared_world(world)
    lease = _lease(client, world)
    job = _ok(_build(client, world, lease["token"], server_wide={"exclude": ["viin_brand"]}))
    done = _wait(client, job["job_id"])
    assert _load_of_last_build(world) == ["--load=base,web,to_base"]
    assert job["server_wide_modules"] == done["server_wide_modules"] == ["base", "web", "to_base"]
    assert done["server_wide_adjustment"] == {"exclude": ["viin_brand"], "include": []}
    nxt = _ok(_build(client, world, lease["token"], op="update"))
    assert nxt["server_wide_adjustment"] is None
    _wait(client, nxt["job_id"])
    assert _load_of_last_build(world) == ["--load=base,web,to_base,viin_brand"]
    row = next(r for r in _registry(world) if r["token"] == lease["token"])
    assert row["server_wide_modules"] == DECLARED, "the lease keeps the catalog's set"
    # With an adjustment --load is always passed, so the core modules must be in it.
    _wait(client, _ok(_build(client, world, lease["token"], server_wide={"exclude": DECLARED}))["job_id"])
    assert _load_of_last_build(world) == ["--load=base,web"]


def test_include_adds_a_module_and_every_bad_adjustment_is_refused_before_anything_starts(client, world):
    """A new module that must load server-wide is found on the lease's addons path - or in the
    checkout's core addons, which Odoo always searches."""
    _declared_world(world)
    _addon(world["addons"], "my_wide")
    _addon(world["odoo_bin"].parent / "odoo" / "addons", "core_wide")
    lease = _lease(client, world)
    job = _ok(_build(client, world, lease["token"],
                     server_wide={"include": ["my_wide", "core_wide", "web"]}))
    _wait(client, job["job_id"])
    assert _load_of_last_build(world) == ["--load=base,web,to_base,viin_brand,my_wide,core_wide"], (
        "core first; an include already in the set is a no-op")
    calls_before = len(_odoo_calls(world))
    jobs_before = len(_jobs(world))

    for exclude, named in ((["web"], "core"), (["viin_brnd"], "not in the declared")):
        err = _err(_build(client, world, lease["token"], server_wide={"exclude": exclude}))
        assert err["code"] == "INVALID_ARGUMENTS", err
        assert "arguments.server_wide.exclude" in err["message"] and named in err["message"], err
    err = _err(_build(client, world, lease["token"],
                      server_wide={"exclude": ["to_base"], "include": ["to_base"]}))
    assert err["code"] == "INVALID_ARGUMENTS" and "arguments.server_wide" in err["message"]
    err = _err(_build(client, world, lease["token"], server_wide={"include": ["no_such_module"]}))
    assert err["code"] == "SERVER_WIDE_MODULE_NOT_FOUND", err
    assert "no_such_module" in err["message"] and err["diagnostics"]["modules"] == ["no_such_module"]
    assert str(world["addons"]) in err["diagnostics"]["searched"]
    assert "check_module_exists" in err["remedy"]

    # An include makes --load necessary - and --load without the core modules would drop them.
    _drop_core_load(world)
    err = _err(_build(client, world, lease["token"], server_wide={"include": ["my_wide"]}))
    assert err["code"] == "SERVER_WIDE_CORE_UNKNOWN" and "server_wide" in err["remedy"]
    assert len(_odoo_calls(world)) == calls_before and len(_jobs(world)) == jobs_before


# --------------------------------------------------------------------------- #
# conf_options: extra [options] keys of the build's own generated conf
# --------------------------------------------------------------------------- #
# The checkout's own dest for --database (a fixture config.py may name it anything): refused
# because the option is one the tool owns, whatever its dest spells.
CHECKOUT_DB_DEST = "fixture_database_dest"


def test_conf_options_land_in_the_generated_conf_and_the_tools_own_keys_are_refused(client, world):
    lease = _lease(client, world)
    job = _ok(_build(client, world, lease["token"],
                     conf_options={"lint_scope_repo": "a/src", "lint_strict": True, "lint_level": 2}))
    assert job["conf_options"] == {"lint_level": "2", "lint_scope_repo": "a/src",
                                   "lint_strict": "True"}
    done = _wait(client, job["job_id"])
    assert done["result"] == "success", done
    ((_conf, lines),) = _run_confs(world)
    assert lines[0] == "[options]"
    assert [ln for ln in lines if ln.startswith("lint_")] == [
        "lint_level = 2", "lint_scope_repo = a/src", "lint_strict = True"]
    (argv,) = _odoo_calls(world)
    assert not [a for a in argv if "lint_" in a], "the keys go into the conf only"
    assert done["summary"]["BUILD_CONF_KEYS"] == "lint_level,lint_scope_repo,lint_strict"

    config = world["odoo_bin"].parent / "odoo" / "tools" / "config.py"
    text = config.read_text(encoding="utf-8")
    assert '"--database", dest="database"' in text
    config.write_text(text.replace('"--database", dest="database"',
                                   '"--database", dest="%s"' % CHECKOUT_DB_DEST), encoding="utf-8")
    for key in ("db_name", "addons_path", "server_wide_modules", "log_level", "http_port",
                "admin_passwd", CHECKOUT_DB_DEST):
        err = _err(_build(client, world, lease["token"], conf_options={key: "x"}))
        assert err["code"] == "INVALID_ARGUMENTS", (key, err)
        assert "arguments.conf_options.%s" % key in err["message"], key
    for options in ({"Bad-Key": "x"}, {"lint_scope": "two\nlines"}, {"lint_scope": ["a", "b"]}):
        assert _build(client, world, lease["token"], conf_options=options)["isError"] is True, options
    assert len(_odoo_calls(world)) == 1 and len(_jobs(world)) == 1, "nothing may start"
