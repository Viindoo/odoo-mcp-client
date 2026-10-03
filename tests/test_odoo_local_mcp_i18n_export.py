"""Behavior tests for the odoo-local `instance_i18n_export` tool: translation files exported from
a lease's database by Odoo's own exporter, with the command line the lease's checkout declares.

Driven over stdio against the REAL server, allocator and 55-instance-ops.sh, in the stubbed world
of test_odoo_local_mcp_instance.py. The stub odoo-bin records its argv and, when asked to export,
writes a file whose bytes the test chose (with a line far past any wrap width), so "Odoo's export
is never reformatted" is observable byte for byte. The stub venv python answers
`odoo_db.py i18n-state` from a file the test writes (what the database holds).

Contracts protected:
  - per module the `.pot` template is exported FIRST, then one `.po` per requested language, all
    from the lease's one database, into the module's own i18n/ directory (or output_dir/<module>),
    named `<module>.pot` and, per language, the name the module already uses: `<code>.po` when
    it ships that and no `<iso_code>.po` (Odoo loads the full-code file LAST, so a `<iso>.po`
    written beside it would be overridden), else `<iso_code>.po`; a module holding both names is
    refused before any file is written; job_wait reports every file in that order;
  - the command line is the one the checkout declares: the server's --i18n-export / --modules /
    --language through 18.0, the `i18n export` subcommand (--config / --database / --output /
    --languages, connection facts in a config file) from 19.0 - both forms with a config file the
    tool wrote, so the operator's ~/.odoorc is never read;
  - a module found in more than one addons directory is refused (MODULE_SHADOWED): Odoo's export
    would read every copy;
  - the files are exactly the bytes Odoo wrote; a failed export leaves no partial or temporary
    file and reports the files already written;
  - the export is refused unless the DATABASE's build facts show demo loaded - for every exported
    module itself, not merely somewhere in the database - and en_US plus every requested language
    loaded (from any lease on that database); a module not installed or installed without its demo
    data, or a language not active in the database itself fails the job before any file is
    written;
  - a job already running on the database answers DATABASE_BUSY before any gate reads the
    database (test_odoo_local_mcp_db_busy.py);
  - Odoo exports on the server-wide set a build on the lease loads: core default + the declared
    server_wide_modules (--load on the server form, the config file's server_wide_modules on the
    subcommand form, which takes no --load), adjusted for the call by `server_wide` with the
    build's refusals; nothing declared passes no set at all, as for a build.
"""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import odoo_tree_fixtures as trees  # noqa: E402
from odoo_local_mcp_harness import McpClient  # noqa: E402
from test_odoo_local_mcp_instance import (RUN, SERIES, _build, _declare_series, _err, _lease,  # noqa: E402,F401
                                          _ok, _stub, _wait, client, world)
from test_odoo_local_mcp_build_facts import _declare_server_wide  # noqa: E402

LONG_MSGID = "A " + "very " * 40 + "long source string"
STATE_DEFAULT = ("LANG=vi_VN ISO=vi ACTIVE=1\nLANG=fr_BE ISO=fr_BE ACTIVE=1\n"
                 "MODULE=my_mod STATE=installed DEMO=1\nMODULE=other_mod STATE=installed DEMO=1\n")


def _exported_bytes(label):
    """The exact file the stub exporter writes for `label` (a language code or 'template')."""
    return ('# Translation of Odoo Server.\n#\t* %s\nmsgid ""\nmsgstr ""\n\n#. module: my_mod\n'
            'msgid "%s"\nmsgstr ""\n' % (label, LONG_MSGID))


@pytest.fixture
def i18n(world, tmp_path):
    """The stubbed world, plus: an installed-module tree on the addons path, an odoo-bin behavior
    that builds (proving each --load-language language in its log) or exports (writing the chosen
    bytes to the file it is told), and a venv python that answers i18n-state from a file."""
    module = world["addons"] / "my_mod"
    module.mkdir()
    (module / "__manifest__.py").write_text("{'name': 'My module'}\n", encoding="utf-8")
    state = tmp_path / "i18n-state.txt"
    state.write_text(STATE_DEFAULT, encoding="utf-8")
    fail_on = tmp_path / "export-fail-on"
    slow = tmp_path / "export-slow"
    conf_copy = tmp_path / "i18n-conf-copy"
    # What `odoo_db.py db-facts` answers (absent file = the database cannot be read), and a record
    # of every such read.
    db_facts = tmp_path / "db-facts.txt"
    db_calls = tmp_path / "db-facts-calls.log"
    world["behavior"].write_text(textwrap.dedent("""\
        out=""; code=""; langs=""
        for a in "$@"; do
            case "$a" in
                --i18n-export=*|--output=*) out="${a#*=}" ;;
                --language=*|--languages=*) code="${a#*=}" ;;
                --config=*) cat "${a#*=}" >> "%(conf)s" ;;
                --load-language=*) langs="${a#*=}" ;;
            esac
        done
        if [[ -n "$out" ]]; then
            if [[ -f "%(slow)s" ]]; then echo "partial" > "$out"; sleep 60; fi
            if [[ -f "%(fail)s" && "$(cat "%(fail)s")" == "${code:-template}" ]]; then
                echo "CRITICAL export crashed"; : > "$out"; exit 1
            fi
            printf '# Translation of Odoo Server.\\n#\\t* %%s\\nmsgid ""\\nmsgstr ""\\n\\n#. module: my_mod\\nmsgid "%%s"\\nmsgstr ""\\n' "${code:-template}" "%(msgid)s" > "$out"
            exit 0
        fi
        for l in ${langs//,/ }; do
            [[ "$l" == en_US ]] || echo "odoo.addons.base.models.ir_module: module base: loading translation file /x/$l.po for language $l"
        done
        echo "odoo.modules.loading: Modules loaded."
        exit 0
        """ % {"conf": conf_copy, "fail": fail_on, "msgid": LONG_MSGID, "slow": slow}), encoding="utf-8")
    _stub(world["python"], textwrap.dedent("""\
        if [[ "${2:-}" == "--version" ]]; then echo "Odoo Server"; exit 0; fi
        case "${1:-}" in
            *odoo_db.py)
                case "${2:-}" in
                    i18n-state) cat "%(state)s" ;;
                    db-facts) echo "$*" >> "%(dbcalls)s"; [[ -f "%(dbfacts)s" ]] && cat "%(dbfacts)s" ;;
                esac
                exit 0 ;;
            %(bin)s) shift; exec bash "%(bin)s" "$@" ;;
        esac
        exec %(real)s "$@"
        """ % {"state": state, "bin": world["odoo_bin"], "real": sys.executable,
               "dbfacts": db_facts, "dbcalls": db_calls}))
    world.update(module=module, state=state, fail_on=fail_on, conf_copy=conf_copy, slow=slow,
                 db_facts=db_facts, db_calls=db_calls)
    return world


def _export(c, world, token, **over):
    args = {"lease_token": token, "modules": ["my_mod"], "languages": ["vi_VN", "fr_BE"],
            "cwd": str(world["work"])}
    args.update(over)
    return c.call("instance_i18n_export", args)


def _ready_lease(c, world, series=SERIES, languages=("vi_VN", "fr_BE"), demo="on"):
    """A lease whose database a finished build filled with demo and the given languages."""
    lease = _lease(c, world, series=series)
    done = _wait(c, _ok(_build(c, world, lease["token"], demo=demo,
                               languages=list(languages)))["job_id"])
    assert done["result"] == "success", done
    return lease


def _export_calls(world):
    lines = world["calls"].read_text().splitlines() if world["calls"].exists() else []
    return [ln.split()[1:] for ln in lines if "--i18n-export=" in ln or " i18n export " in ln]


def _flag(argv, name):
    return next((a.split("=", 1)[1] for a in argv if a.startswith(name + "=")), None)


def _leftovers(directory):
    return [p.name for p in Path(directory).rglob(".odoo-ai-export-*")]


# --------------------------------------------------------------------------- #
# the export, per command-line form
# --------------------------------------------------------------------------- #
SERVER_SERIES = ("8.0", "10.0", "16.0", "18.0")
SUBCOMMAND_SERIES = ("19.0", "20.0")


@pytest.mark.parametrize("series", SERVER_SERIES + SUBCOMMAND_SERIES)
def test_the_pot_then_each_po_is_exported_from_the_one_database_with_the_checkouts_command_line(
        i18n, series):
    _declare_series(i18n, series)
    with McpClient(i18n["env"](), i18n["work"]) as c:
        c.initialize()
        lease = _ready_lease(c, i18n, series=series)
        job = _ok(_export(c, i18n, lease["token"]))
        assert job["destinations"] == [{"module": "my_mod", "directory": str(i18n["module"] / "i18n")}]
        done = _wait(c, job["job_id"])
    assert done["result"] == "success", done
    i18n_dir = i18n["module"] / "i18n"
    assert done["exports"] == [
        {"module": "my_mod", "kind": "pot", "language": None, "path": str(i18n_dir / "my_mod.pot")},
        {"module": "my_mod", "kind": "po", "language": "vi_VN", "path": str(i18n_dir / "vi.po")},
        {"module": "my_mod", "kind": "po", "language": "fr_BE", "path": str(i18n_dir / "fr_BE.po")},
    ], "the template first, then one file per language named by its ISO code"
    for name, label in (("my_mod.pot", "template"), ("vi.po", "vi_VN"), ("fr_BE.po", "fr_BE")):
        assert (i18n_dir / name).read_text(encoding="utf-8") == _exported_bytes(label), (
            "%s must hold exactly the bytes Odoo wrote" % name)
    assert _leftovers(i18n_dir) == []
    calls = _export_calls(i18n)
    assert len(calls) == 3
    template, vi, fr = calls
    if series in SERVER_SERIES:
        for argv in calls:
            assert argv[argv.index("-d") + 1] == lease["db_name"]
            assert _flag(argv, "--modules") == "my_mod" and "--stop-after-init" in argv
            assert argv[argv.index("--addons-path") + 1] == str(i18n["addons"])
            assert _flag(argv, "--i18n-export").endswith(".po"), (
                "the oldest exporters take the format from the extension and know no .pot")
        assert _flag(template, "--language") is None, "no language = the template"
        assert (_flag(vi, "--language"), _flag(fr, "--language")) == ("vi_VN", "fr_BE")
        assert "i18n" not in template[:1]
    else:
        for argv in calls:
            assert argv[:2] == ["i18n", "export"] and argv[-1] == "my_mod"
            assert _flag(argv, "--database") == lease["db_name"]
            assert _flag(argv, "--output").endswith(".po")
            assert "--i18n-export" not in " ".join(argv) and "-d" not in argv
        assert _flag(template, "--languages") is None, "no language = Odoo's default: the template"
        assert (_flag(vi, "--languages"), _flag(fr, "--languages")) == ("vi_VN", "fr_BE")
        conf = i18n["conf_copy"].read_text()
        assert "addons_path = %s" % i18n["addons"] in conf and "db_host = localhost" in conf
        assert "db_user = odoo" in conf and "password" not in conf


def test_output_dir_puts_each_modules_files_in_its_own_subdirectory(i18n, tmp_path):
    out = tmp_path / "isolate"
    with McpClient(i18n["env"](), i18n["work"]) as c:
        c.initialize()
        lease = _ready_lease(c, i18n)
        job = _ok(_export(c, i18n, lease["token"], languages=["vi_VN"], output_dir=str(out)))
        assert job["destinations"] == [{"module": "my_mod", "directory": str(out / "my_mod")}]
        done = _wait(c, job["job_id"])
    assert done["result"] == "success", done
    assert [e["path"] for e in done["exports"]] == [str(out / "my_mod" / "my_mod.pot"),
                                                   str(out / "my_mod" / "vi.po")]
    assert not (i18n["module"] / "i18n").exists(), "the module's own i18n/ dir is left untouched"


def test_several_modules_each_get_their_template_first(i18n):
    other = i18n["addons"] / "other_mod"
    other.mkdir()
    (other / "__openerp__.py").write_text("{}\n", encoding="utf-8")
    with McpClient(i18n["env"](), i18n["work"]) as c:
        c.initialize()
        lease = _ready_lease(c, i18n)
        done = _wait(c, _ok(_export(c, i18n, lease["token"], modules=["my_mod", "other_mod"],
                                    languages=["vi_VN"]))["job_id"])
    assert [(e["module"], e["kind"]) for e in done["exports"]] == [
        ("my_mod", "pot"), ("my_mod", "po"), ("other_mod", "pot"), ("other_mod", "po")]


def test_no_language_exports_only_the_template(i18n):
    with McpClient(i18n["env"](), i18n["work"]) as c:
        c.initialize()
        lease = _ready_lease(c, i18n, languages=())
        done = _wait(c, _ok(_export(c, i18n, lease["token"], languages=[]))["job_id"])
    assert done["result"] == "success"
    assert [e["kind"] for e in done["exports"]] == ["pot"]


# --------------------------------------------------------------------------- #
# the .po name follows the module
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("ships,written", [((), "vi.po"), (("vi.po",), "vi.po"),
                                           (("vi_VN.po",), "vi_VN.po")])
def test_each_po_is_written_under_the_name_the_module_already_uses(i18n, ships, written):
    """Odoo loads vi.po then vi_VN.po, so a module that ships vi_VN.po reads its Vietnamese terms
    from THAT file: exporting into vi.po beside it would leave every edit overridden."""
    i18n_dir = i18n["module"] / "i18n"
    i18n_dir.mkdir()
    for name in ships:
        (i18n_dir / name).write_text("committed %s\n" % name, encoding="utf-8")
    with McpClient(i18n["env"](), i18n["work"]) as c:
        c.initialize()
        lease = _ready_lease(c, i18n)
        done = _wait(c, _ok(_export(c, i18n, lease["token"], languages=["vi_VN"]))["job_id"])
    assert done["result"] == "success", done
    assert [e["path"] for e in done["exports"]] == [str(i18n_dir / "my_mod.pot"),
                                                   str(i18n_dir / written)]
    assert (i18n_dir / written).read_text(encoding="utf-8") == _exported_bytes("vi_VN")
    other = {"vi.po": "vi_VN.po", "vi_VN.po": "vi.po"}[written]
    assert not (i18n_dir / other).exists(), "no second file for the language is created"


def test_output_dir_uses_the_name_the_module_itself_uses(i18n, tmp_path):
    i18n_dir = i18n["module"] / "i18n"
    i18n_dir.mkdir()
    (i18n_dir / "vi_VN.po").write_text("committed\n", encoding="utf-8")
    out = tmp_path / "isolate"
    with McpClient(i18n["env"](), i18n["work"]) as c:
        c.initialize()
        lease = _ready_lease(c, i18n)
        done = _wait(c, _ok(_export(c, i18n, lease["token"], languages=["vi_VN"],
                                    output_dir=str(out)))["job_id"])
    assert done["result"] == "success", done
    assert done["exports"][-1]["path"] == str(out / "my_mod" / "vi_VN.po")
    assert (i18n_dir / "vi_VN.po").read_text() == "committed\n"


def test_a_module_holding_both_names_for_a_language_is_refused_before_any_file_is_written(i18n):
    i18n_dir = i18n["module"] / "i18n"
    i18n_dir.mkdir()
    for name in ("vi.po", "vi_VN.po"):
        (i18n_dir / name).write_text("committed %s\n" % name, encoding="utf-8")
    with McpClient(i18n["env"](), i18n["work"]) as c:
        c.initialize()
        lease = _ready_lease(c, i18n)
        done = _wait(c, _ok(_export(c, i18n, lease["token"]))["job_id"])
    assert done["result"] == "failure"
    assert done["exports"] == [] and _export_calls(i18n) == [], "not even the template"
    line = next(ln for ln in done["output_tail"] if "I18N_PO_FILE_AMBIGUOUS" in ln)
    assert "vi.po" in line and "vi_VN.po" in line and "operator" in line, line
    assert sorted(p.name for p in i18n_dir.iterdir()) == ["vi.po", "vi_VN.po"]
    for name in ("vi.po", "vi_VN.po"):
        assert (i18n_dir / name).read_text() == "committed %s\n" % name


def test_a_module_found_in_two_addons_directories_is_refused(i18n, tmp_path):
    """Odoo's code-term walk reads the source of every copy it finds, so a shadowed module's
    export would carry the other copy's references and resurrect its terms."""
    second = tmp_path / "second-addons"
    (second / "my_mod").mkdir(parents=True)
    (second / "my_mod" / "__manifest__.py").write_text("{}\n", encoding="utf-8")
    toml = i18n["home"] / "instances.toml"
    toml.write_text(toml.read_text().replace('addons_path = ["%s"]' % i18n["addons"],
                                             'addons_path = ["%s", "%s"]' % (i18n["addons"], second)),
                    encoding="utf-8")
    with McpClient(i18n["env"](), i18n["work"]) as c:
        c.initialize()
        lease = _ready_lease(c, i18n)
        err = _err(_export(c, i18n, lease["token"]))
    assert err["code"] == "MODULE_SHADOWED", err
    assert err["diagnostics"]["paths"] == [str(i18n["addons"] / "my_mod"), str(second / "my_mod")]
    assert _export_calls(i18n) == []


def test_the_exporter_never_reads_the_operators_config_file(i18n, tmp_path):
    home = tmp_path / "operator-home"
    home.mkdir()
    (home / ".odoorc").write_text("[options]\naddons_path = /elsewhere\n", encoding="utf-8")
    with McpClient(i18n["env"](HOME=str(home)), i18n["work"]) as c:
        c.initialize()
        lease = _ready_lease(c, i18n)
        done = _wait(c, _ok(_export(c, i18n, lease["token"], languages=["vi_VN"]))["job_id"])
    assert done["result"] == "success", done
    for argv in _export_calls(i18n):
        assert "-c" in argv or any(a.startswith("--config=") for a in argv), argv
    conf = i18n["confs"].read_text() if i18n["confs"].exists() else ""
    conf += i18n["conf_copy"].read_text() if i18n["conf_copy"].exists() else ""
    assert "addons_path = %s" % i18n["addons"] in conf and "/elsewhere" not in conf
    exports = [ln for ln in i18n["rc_env"].read_text().splitlines() if ".i18n.conf|" in ln]
    assert len(exports) == 2, "the import-time rc load of every export reads the tool's conf"


# --------------------------------------------------------------------------- #
# the build must be fit for an export
# --------------------------------------------------------------------------- #
def test_a_database_built_without_demo_is_refused_before_anything_starts(i18n):
    with McpClient(i18n["env"](), i18n["work"]) as c:
        c.initialize()
        lease = _ready_lease(c, i18n, demo="off")
        before = len(_export_calls(i18n))
        err = _err(_export(c, i18n, lease["token"]))
    assert err["code"] == "I18N_EXPORT_NEEDS_DEMO", err
    assert "demo" in err["remedy"] and "op init" in err["remedy"]
    assert len(_export_calls(i18n)) == before


def test_a_language_the_build_did_not_prove_loaded_is_refused_naming_it(i18n):
    with McpClient(i18n["env"](), i18n["work"]) as c:
        c.initialize()
        lease = _ready_lease(c, i18n, languages=("vi_VN",))
        err = _err(_export(c, i18n, lease["token"]))
    assert err["code"] == "I18N_LANGUAGE_NOT_LOADED", err
    assert "fr_BE" in err["message"]
    assert err["diagnostics"]["missing"] == ["fr_BE"], "only the language not proved loaded"
    assert "languages" in err["remedy"]


def test_a_module_installed_without_its_own_demo_is_refused_though_the_database_has_demo(i18n):
    """Demo is a fact of each module: another module's demo data says nothing about this one's,
    so the export is judged by the EXPORTED module's own flag."""
    i18n["db_facts"].write_text("DB_EXISTS=1\nDEMO=1\nLANGUAGES=en_US,vi_VN,fr_BE\n"
                                "MODULE=my_mod STATE=installed DEMO=0\n", encoding="utf-8")
    with McpClient(i18n["env"](), i18n["work"]) as c:
        c.initialize()
        lease = _ready_lease(c, i18n)
        err = _err(_export(c, i18n, lease["token"]))
    assert err["code"] == "I18N_EXPORT_NEEDS_DEMO", err
    assert err["diagnostics"]["modules_without_demo"] == ["my_mod"]
    assert "my_mod" in err["message"] and err["diagnostics"]["facts_source"] == "database"
    calls = i18n["db_calls"].read_text()
    assert "--modules my_mod" in calls, "the exported modules are asked about, per module"
    assert _export_calls(i18n) == []


def test_the_job_refuses_a_module_the_database_holds_without_demo(i18n):
    """When the database could not be read up front (lease records answered), the job asks the
    database per module itself before any file is written."""
    i18n["state"].write_text(STATE_DEFAULT.replace("MODULE=my_mod STATE=installed DEMO=1",
                                                   "MODULE=my_mod STATE=installed DEMO=0"),
                             encoding="utf-8")
    with McpClient(i18n["env"](), i18n["work"]) as c:
        c.initialize()
        lease = _ready_lease(c, i18n)
        done = _wait(c, _ok(_export(c, i18n, lease["token"]))["job_id"])
    assert done["result"] == "failure"
    assert done["exports"] == [] and _export_calls(i18n) == []
    assert any("I18N_EXPORT_NEEDS_DEMO" in ln and "my_mod" in ln for ln in done["output_tail"])


def test_a_lease_with_no_recorded_build_is_refused(i18n):
    with McpClient(i18n["env"](), i18n["work"]) as c:
        c.initialize()
        lease = _lease(c, i18n)
        assert _err(_export(c, i18n, lease["token"]))["code"] == "I18N_EXPORT_NEEDS_DEMO"


def test_a_forwarded_database_is_judged_by_the_build_its_provider_ran(i18n):
    """The export runs on a lease an agent took on a database another lease built: the database's
    facts decide, so a fit database exports and nothing is re-built."""
    with McpClient(i18n["env"](), i18n["work"]) as c:
        c.initialize()
        provider = _ready_lease(c, i18n)
        consumer = _lease(c, i18n, mode="exclusive", db_name=provider["db_name"])
        done = _wait(c, _ok(_export(c, i18n, consumer["token"]))["job_id"])
    assert done["result"] == "success", done
    assert all(_flag(argv, "--i18n-export") for argv in _export_calls(i18n))


@pytest.mark.parametrize("over,needle", [
    ({"languages": ["en_US"]}, "en_US"),
    ({"languages": ["vi VN"]}, "arguments.languages"),
    ({"modules": ["no_such_module"]}, "no_such_module"),
    ({"modules": ["bad-name"]}, "arguments.modules"),
    ({"output_dir": "relative/dir"}, "arguments.output_dir"),
])
def test_bad_arguments_are_refused_before_anything_starts(i18n, over, needle):
    with McpClient(i18n["env"](), i18n["work"]) as c:
        c.initialize()
        lease = _ready_lease(c, i18n)
        err = _err(_export(c, i18n, lease["token"], **over))
    assert err["code"] == "INVALID_ARGUMENTS" and needle in err["message"], err
    assert _export_calls(i18n) == []


def test_a_checkout_declaring_no_export_command_line_is_refused(i18n):
    config = i18n["odoo_bin"].parent / "odoo" / "tools" / "config.py"
    config.write_text("\n".join(ln for ln in config.read_text().splitlines()
                                if "--i18n-export" not in ln), encoding="utf-8")
    with McpClient(i18n["env"](), i18n["work"]) as c:
        c.initialize()
        lease = _ready_lease(c, i18n)
        err = _err(_export(c, i18n, lease["token"]))
    assert err["code"] == "ODOO_SOURCE_FACT_UNKNOWN" and "i18n" in err["message"], err
    assert _export_calls(i18n) == []


# --------------------------------------------------------------------------- #
# what the database itself says, and a failing exporter
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("state,code", [
    (STATE_DEFAULT.replace("MODULE=my_mod STATE=installed", "MODULE=my_mod STATE=uninstalled"),
     "I18N_MODULE_NOT_INSTALLED"),
    (STATE_DEFAULT.replace("LANG=fr_BE ISO=fr_BE ACTIVE=1", "LANG=fr_BE ISO=fr_BE ACTIVE=0"),
     "I18N_LANGUAGE_NOT_ACTIVE"),
    (STATE_DEFAULT.replace("LANG=vi_VN ISO=vi ACTIVE=1\n", ""), "I18N_LANGUAGE_NOT_ACTIVE"),
])
def test_what_the_database_does_not_hold_fails_the_job_before_any_file_is_written(i18n, state, code):
    i18n["state"].write_text(state, encoding="utf-8")
    with McpClient(i18n["env"](), i18n["work"]) as c:
        c.initialize()
        lease = _ready_lease(c, i18n)
        done = _wait(c, _ok(_export(c, i18n, lease["token"]))["job_id"])
    assert done["result"] == "failure"
    assert done["exports"] == [] and _export_calls(i18n) == []
    assert any(code in line for line in done["output_tail"]), done["output_tail"]
    assert not (i18n["module"] / "i18n").exists()


def test_a_failing_export_stops_the_run_keeps_what_was_written_and_leaves_no_partial_file(i18n):
    i18n["fail_on"].write_text("vi_VN", encoding="utf-8")
    with McpClient(i18n["env"](), i18n["work"]) as c:
        c.initialize()
        lease = _ready_lease(c, i18n)
        done = _wait(c, _ok(_export(c, i18n, lease["token"]))["job_id"])
    i18n_dir = i18n["module"] / "i18n"
    assert done["result"] == "failure"
    assert [e["kind"] for e in done["exports"]] == ["pot"], "the template was written before the failure"
    assert sorted(p.name for p in i18n_dir.iterdir()) == ["my_mod.pot"]
    assert len(_export_calls(i18n)) == 2, "nothing is exported after a failed file"
    assert any("vi_VN" in line and "failed" in line for line in done["output_tail"])


def test_an_existing_file_is_replaced_only_by_a_finished_export(i18n):
    i18n_dir = i18n["module"] / "i18n"
    i18n_dir.mkdir()
    (i18n_dir / "vi.po").write_text("committed translation\n", encoding="utf-8")
    i18n["fail_on"].write_text("vi_VN", encoding="utf-8")
    with McpClient(i18n["env"](), i18n["work"]) as c:
        c.initialize()
        lease = _ready_lease(c, i18n)
        _wait(c, _ok(_export(c, i18n, lease["token"]))["job_id"])
    assert (i18n_dir / "vi.po").read_text() == "committed translation\n", (
        "a failed export must not truncate the file it was going to replace")


def test_releasing_the_lease_stops_a_running_export(i18n):
    """An export is a job of the lease: releasing the lease stops it mid-write, and neither the
    half-written file nor a final one is left in the module."""
    with McpClient(i18n["env"](), i18n["work"]) as c:
        c.initialize()
        lease = _ready_lease(c, i18n)
        i18n["slow"].write_text("1", encoding="utf-8")
        job = _ok(_export(c, i18n, lease["token"]))
        assert _wait(c, job["job_id"], timeout_s=3)["result"] == "timeout"
        _ok(c.call("lease_release", {"lease_token": lease["token"], "run_id": RUN}, timeout=120))
        done = _wait(c, job["job_id"], timeout_s=20)
    assert done["state"] != "running" and done["result"] != "success"
    assert done["exports"] == []
    assert not (i18n["module"] / "i18n" / "my_mod.pot").exists()
    assert _leftovers(i18n["module"]) == [], "the interrupted export's temporary file is removed"


def test_job_wait_of_a_build_reports_no_exports(i18n):
    with McpClient(i18n["env"](), i18n["work"]) as c:
        c.initialize()
        lease = _lease(c, i18n)
        done = _wait(c, _ok(_build(c, i18n, lease["token"], demo="on"))["job_id"])
    assert done["exports"] == []


def test_the_export_hands_the_script_the_declared_odoo_root(i18n, tmp_path):
    """The export script locates the Odoo launcher on the served addons_path and falls back to the
    instance's declared odoo_root - which instance_i18n_export must therefore hand it, or an
    export from a worktree-only addons_path cannot find the launcher."""
    from test_odoo_local_mcp_instance import _ops_recorder

    core = i18n["addons"].parent
    toml = i18n["home"] / "instances.toml"
    toml.write_text(toml.read_text() + 'odoo_root = "%s"\n' % core, encoding="utf-8")
    with McpClient(i18n["env"](), i18n["work"]) as c:
        c.initialize()
        lease = _ready_lease(c, i18n)
    stand_in, record = _ops_recorder(tmp_path)
    with McpClient(i18n["env"](ODOO_AI_OPS_SCRIPT=str(stand_in)), i18n["work"]) as c:
        c.initialize()
        _wait(c, _ok(_export(c, i18n, lease["token"]))["job_id"])
    argv = json.loads(record.read_text())["argv"]
    assert argv[0] == "i18n-export"
    assert dict(zip(argv[1::2], argv[2::2])).get("--odoo-root") == str(core), argv


# --------------------------------------------------------------------------- #
# the server-wide set: the one the database's builds load
# --------------------------------------------------------------------------- #
DECLARED_WIDE = ["to_base", "viin_brand"]


def _loads(world):
    """The --load value of every export call (None where the call carries none)."""
    return [_flag(argv, "--load") for argv in _export_calls(world)]


@pytest.mark.parametrize("series", ["17.0", "19.0"])
def test_an_export_runs_on_the_core_default_plus_the_declared_server_wide_modules(i18n, series):
    """The database was built with the deployment's server-wide set; exporting from it without
    that set runs Odoo differently from every build and serve of the deployment."""
    _declare_series(i18n, series)
    _declare_server_wide(i18n, DECLARED_WIDE)
    expected = ",".join(trees.CORE_LOAD[series] + DECLARED_WIDE)
    with McpClient(i18n["env"](), i18n["work"]) as c:
        c.initialize()
        lease = _ready_lease(c, i18n, series=series)
        job = _ok(_export(c, i18n, lease["token"], languages=["vi_VN"]))
        done = _wait(c, job["job_id"])
    assert done["result"] == "success", done
    assert ",".join(job["server_wide_modules"]) == ",".join(done["server_wide_modules"]) == expected
    assert job["server_wide_adjustment"] is None
    if series == "17.0":
        assert _loads(i18n) == [expected, expected], "the template and the .po alike"
    else:
        assert _loads(i18n) == [None, None], "the i18n export subcommand takes no --load"
        conf = i18n["conf_copy"].read_text()
        assert conf.count("server_wide_modules = %s\n" % expected) == 2, conf


def test_an_export_honours_an_exclude_of_a_declared_module(i18n):
    _declare_server_wide(i18n, DECLARED_WIDE)
    with McpClient(i18n["env"](), i18n["work"]) as c:
        c.initialize()
        lease = _ready_lease(c, i18n)
        job = _ok(_export(c, i18n, lease["token"], languages=[],
                          server_wide={"exclude": ["viin_brand"]}))
        done = _wait(c, job["job_id"])
    assert done["result"] == "success", done
    assert _loads(i18n) == ["base,web,to_base"]
    assert done["server_wide_adjustment"] == {"exclude": ["viin_brand"], "include": []}


def test_an_export_excluding_a_core_default_module_is_refused_before_anything_starts(i18n):
    _declare_server_wide(i18n, DECLARED_WIDE)
    with McpClient(i18n["env"](), i18n["work"]) as c:
        c.initialize()
        lease = _ready_lease(c, i18n)
        err = _err(_export(c, i18n, lease["token"], server_wide={"exclude": ["web"]}))
    assert err["code"] == "INVALID_ARGUMENTS", err
    assert "arguments.server_wide.exclude" in err["message"] and "core" in err["message"], err
    assert _export_calls(i18n) == []


def test_an_export_with_nothing_declared_passes_no_server_wide_set(i18n):
    """As for a build: with nothing declared Odoo's own default applies, so no --load is passed."""
    with McpClient(i18n["env"](), i18n["work"]) as c:
        c.initialize()
        lease = _ready_lease(c, i18n)
        job = _ok(_export(c, i18n, lease["token"], languages=["vi_VN"]))
        done = _wait(c, job["job_id"])
    assert done["result"] == "success", done
    assert _loads(i18n) == [None, None]
    assert job["server_wide_modules"] == done["server_wide_modules"] == []
