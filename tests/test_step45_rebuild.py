"""`45-venv.sh create-venv --rebuild` and its helpers: a rebuild happens in the row's own venv,
never relocates it, refuses while something uses it, keeps the old venv until the new one is
proven, and records extras / override on the row in one write. Everything runs on a throwaway
state root with a stub `uv` on PATH and a stub Odoo checkout; no network, no real build.
"""
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from conftest import farm_path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
LIB = PLUGIN / "scripts" / "lib"
STEP = PLUGIN / "scripts" / "setup-steps" / "45-venv.sh"
sys.path.insert(0, str(LIB))
import venv_facts  # noqa: E402

SERIES = "17.0"

# The step ends by asking whether Postgres answers. A client installed on the host would
# question whatever cluster it finds there (a password prompt on a pipe sits out the whole probe
# bound), so the world is built WITHOUT any client: the answer then comes from the stub python.
_PG_CLIENT_BINS = ("pg_isready", "psql", "createdb", "dropdb", "pg_dump", "pg_restore", "docker")


def _write_exec(path: Path, text: str):
    path.write_text(textwrap.dedent(text), encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _fake_venv(path: Path, python_ok=True):
    """A directory shaped like a venv: pyvenv.cfg + bin/python that answers `odoo-bin --version`."""
    (path / "bin").mkdir(parents=True, exist_ok=True)
    (path / "pyvenv.cfg").write_text("home = /usr/bin\n", encoding="utf-8")
    (path / "lib").mkdir(exist_ok=True)
    _write_exec(path / "bin" / "python", "#!/usr/bin/env bash\nexit %d\n" % (0 if python_ok else 1))
    (path / "MARKER").write_text("old", encoding="utf-8")


@pytest.fixture()
def world(tmp_path, path_farm):
    """state root + a stub Odoo checkout + a declared row whose python lives in a fake venv."""
    home = tmp_path / "state"; home.mkdir()
    odoo = tmp_path / "odoo"; (odoo / "addons").mkdir(parents=True)
    _write_exec(odoo / "odoo-bin", "#!/usr/bin/env bash\nexit 0\n")   # the launcher the step runs with the new python
    (odoo / "requirements.txt").write_text("lxml==5.0.0\nwerkzeug>=2.0,<3\n", encoding="utf-8")
    addons = tmp_path / "myaddons"; (addons / "mod" / "tests").mkdir(parents=True)
    (addons / "mod" / "__manifest__.py").write_text("{}", encoding="utf-8")
    (addons / "mod" / "tests" / "test_pylint.py").write_text("import pylint_odoo\n", encoding="utf-8")
    (addons / "requirements.txt").write_text("requests\n", encoding="utf-8")
    venv = tmp_path / "venvs" / "17.0-std"
    _fake_venv(venv)
    (home / "instances.toml").write_text(textwrap.dedent('''\
        [[instance]]
        series = "17.0"
        profile = "std"
        addons_path = ["%s", "%s"]
        python = "%s"
        # old note: see %s
        ''' % (addons, odoo / "addons", venv / "bin" / "python", tmp_path / "gone" / "override-18.0.txt")), encoding="utf-8")
    # a stub uv that creates the venv shape and logs every call
    bindir = tmp_path / "bin"; bindir.mkdir()
    log = tmp_path / "uv.log"
    _write_exec(bindir / "uv", '''\
        #!/usr/bin/env bash
        echo "$@" >> "%s"
        [ "${UV_FAIL:-}" = "1" ] && { echo "boom" >&2; exit 1; }
        if [ "$1" = "venv" ]; then
          d="$2"; mkdir -p "$d/bin" "$d/lib"; echo "home = /usr/bin" > "$d/pyvenv.cfg"
          printf '#!/usr/bin/env bash\\nexit 0\\n' > "$d/bin/python"; chmod +x "$d/bin/python"; echo new > "$d/MARKER"
        fi
        exit 0
        ''' % log)
    env = {k: v for k, v in os.environ.items() if not k.startswith("ODOO_AI_")}
    env.update({"ODOO_AI_HOME": str(home), "ODOO_AI_INSTANCES": str(home / "instances.toml"),
                "PATH": farm_path(path_farm(drop=_PG_CLIENT_BINS), bindir), "ODOO_AI_PROJECT_DIR": str(tmp_path / "share"),
                "ODOO_BIN": str(odoo / "odoo-bin")})
    return {"home": home, "venv": venv, "odoo": odoo, "addons": addons, "env": env, "log": log, "tmp": tmp_path}


def _run(world, *args, env_extra=None, timeout=120):
    env = dict(world["env"]); env.update(env_extra or {})
    return subprocess.run(["bash", str(STEP), *args], capture_output=True, text=True, env=env, timeout=timeout)


def _row(world):
    out = subprocess.run([sys.executable, str(LIB / "instances_io.py"), "read-row", str(world["home"] / "instances.toml"),
                          SERIES, "std", "--json"], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def test_the_row_plan_names_the_venv_the_python_lives_in_and_never_a_bare_interpreter(world):
    plan = venv_facts.row_plan(str(world["home"] / "instances.toml"), SERIES, "std")
    assert plan["row_found"] and plan["venv_dir"] == str(world["venv"]) and plan["shared_by"] == []
    assert venv_facts.venv_dir_of("/usr/bin/python3") is None


def test_an_existing_venv_is_refused_without_rebuild_and_the_path_comes_from_the_row(world):
    proc = _run(world, "create-venv", "--series", SERIES, "--profile", "std")
    assert proc.returncode == 1 and "--rebuild" in proc.stderr
    assert "VENV_PATH=%s" % world["venv"] in proc.stdout and "PATH_SOURCE=row" in proc.stdout
    assert (world["venv"] / "MARKER").read_text() == "old" and not world["log"].exists()


def test_rebuild_replaces_the_venv_in_place_records_extras_and_override_and_drops_the_old_one(world, tmp_path):
    override = tmp_path / "ovr.txt"; override.write_text("werkzeug==2.0.3\n", encoding="utf-8")
    proc = _run(world, "create-venv", "--series", SERIES, "--profile", "std", "--rebuild",
                "--extra", "pylint-odoo==9.0.5", "--extra", "werkzeug>=2.0,<2.1", "--override", str(override))
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert (world["venv"] / "MARKER").read_text().strip() == "new"
    assert not list(tmp_path.glob("venvs/17.0-std.rebuilding-*")) and not (tmp_path / "venvs" / "17.0-std.rebuild").exists()
    calls = world["log"].read_text()
    assert "--override %s.override.txt" % world["venv"] in calls and "-r %s" % (world["odoo"] / "requirements.txt") in calls
    assert "pylint-odoo==9.0.5 werkzeug>=2.0,<2.1" in calls
    row = _row(world)
    assert row["python"] == str(world["venv"] / "bin" / "python")
    assert row["extra_requirements"] == ["pylint-odoo==9.0.5", "werkzeug>=2.0,<2.1"]  # the comma survived
    assert row["uv_override"] == "%s.override.txt" % world["venv"] and len(row["uv_override_basis"]) == 16
    assert "SUGGESTED_EXTRA=pylint-odoo" in proc.stdout


def test_a_later_rebuild_reapplies_the_recorded_extras_and_override_unless_told_otherwise(world, tmp_path):
    override = tmp_path / "ovr.txt"; override.write_text("werkzeug==2.0.3\n", encoding="utf-8")
    assert _run(world, "create-venv", "--series", SERIES, "--profile", "std", "--rebuild", "--extra", "requests",
                "--override", str(override)).returncode == 0
    world["log"].unlink()
    again = _run(world, "create-venv", "--series", SERIES, "--profile", "std", "--rebuild")
    assert again.returncode == 0, again.stderr
    assert "EXTRA_FROM_ROW=requests" in again.stdout and "OVERRIDE_FROM_ROW=" in again.stdout
    assert "--override" in world["log"].read_text() and "requests" in world["log"].read_text()
    world["log"].unlink()
    dropped = _run(world, "create-venv", "--series", SERIES, "--profile", "std", "--rebuild", "--no-recorded", "--no-override")
    assert dropped.returncode == 0, dropped.stderr
    assert "--override" not in world["log"].read_text()
    row = _row(world)
    assert row["extra_requirements"] == [] and not row.get("uv_override")


def test_a_failed_build_restores_the_old_venv_and_records_nothing(world):
    before = _row(world)
    proc = _run(world, "create-venv", "--series", SERIES, "--profile", "std", "--rebuild", env_extra={"UV_FAIL": "1"})
    assert proc.returncode == 1 and "restored" in proc.stderr
    assert (world["venv"] / "MARKER").read_text() == "old"
    assert not (world["tmp"] / "venvs" / "17.0-std.rebuild").exists()
    assert _row(world) == before


def test_a_process_using_the_venv_blocks_the_rebuild_until_force(world):
    holder = subprocess.Popen(["sleep", "30"], env=dict(os.environ, SOME_PATH=str(world["venv"])))
    try:
        # a process whose COMMAND LINE names the venv (the detector matches args, exe resolves to the base python)
        sleeper = subprocess.Popen(["bash", "-c", "exec -a '%s/bin/python odoo-bin' sleep 30" % world["venv"]])
        try:
            proc = _run(world, "create-venv", "--series", SERIES, "--profile", "std", "--rebuild")
            assert proc.returncode == 1 and "in use" in proc.stderr and "HOLDER=process" in proc.stderr
            assert (world["venv"] / "MARKER").read_text() == "old"
            forced = _run(world, "create-venv", "--series", SERIES, "--profile", "std", "--rebuild", "--force")
            assert forced.returncode == 0, forced.stderr
        finally:
            sleeper.kill(); sleeper.wait()
    finally:
        holder.kill(); holder.wait()


def test_a_venv_shared_by_two_rows_is_split_one_venv_per_profile_and_the_orphan_is_removed_last(world):
    """One venv per profile: rebuilding a row that shares its venv gives that row its own venv at
    the per-profile path and leaves the shared one (and whatever runs on it) alone; when the last
    row has left, the shared venv is removed."""
    toml = world["home"] / "instances.toml"
    toml.write_text(toml.read_text() + textwrap.dedent('''\

        [[instance]]
        series = "17.0"
        profile = "other"
        addons_path = ["%s"]
        python = "%s"
        ''' % (world["odoo"] / "addons", world["venv"] / "bin" / "python")), encoding="utf-8")
    shared = world["venv"]
    proc = _run(world, "create-venv", "--series", SERIES, "--profile", "std", "--rebuild")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "SPLIT_FROM=%s" % shared in proc.stdout and "SHARED_BY=17.0:other" in proc.stdout
    assert "PATH_SOURCE=split" in proc.stdout and "--force" not in proc.stderr
    own = world["home"] / "venvs" / "17.0-std"
    assert own.is_dir() and (own / "MARKER").read_text().strip() == "new"
    assert (shared / "MARKER").read_text().strip() == "old"             # untouched for the other row
    assert _row(world)["python"] == str(own / "bin" / "python")
    assert "SHARED_VENV_KEPT=%s" % shared in proc.stdout and "17.0:other" in proc.stdout
    # the other row is now the only user of the old venv: it rebuilds there in place, no split
    proc = _run(world, "create-venv", "--series", SERIES, "--profile", "other", "--rebuild")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "PATH_SOURCE=row" in proc.stdout and "SPLIT_FROM" not in proc.stdout
    assert (shared / "MARKER").read_text().strip() == "new" and (own / "MARKER").read_text().strip() == "new"


def test_check_flags_a_dead_python_a_missing_override_and_a_stale_comment(world):
    proc = _run(world, "check")
    assert proc.returncode == 0 and "STALE_COMMENT" in proc.stderr and "override-18.0.txt" in proc.stderr
    toml = world["home"] / "instances.toml"
    toml.write_text(toml.read_text().replace('python = "', 'uv_override = "/nonexistent/o.txt"\npython = "'), encoding="utf-8")
    proc = _run(world, "check")
    assert proc.returncode == 1 and "override file is missing" in proc.stderr
    os.chmod(world["venv"] / "bin" / "python", 0o644)
    proc = _run(world, "check")
    assert "not executable" in proc.stderr


def test_the_override_basis_changes_when_an_overridden_upstream_pin_moves(tmp_path):
    ovr = tmp_path / "o.txt"; ovr.write_text("gevent==21.8.0\ngreenlet==1.1.2\n", encoding="utf-8")
    req = tmp_path / "r.txt"; req.write_text("gevent==21.8.0 ; python_version == '3.10'\nlxml==5\n", encoding="utf-8")
    a = venv_facts.basis(str(ovr), [str(req)])
    req.write_text("gevent==22.10.2 ; python_version == '3.10'\nlxml==5\n", encoding="utf-8")
    b = venv_facts.basis(str(ovr), [str(req)])
    req.write_text("gevent==22.10.2 ; python_version == '3.10'\nlxml==6\n", encoding="utf-8")
    c = venv_facts.basis(str(ovr), [str(req)])
    assert a != b and b == c  # only the overridden package's lines count


def test_the_catalog_upsert_keeps_a_comma_inside_an_array_item(tmp_path):
    toml = tmp_path / "instances.toml"
    toml.write_text('[[instance]]\nseries = "17.0"\naddons_path = ["/a"]\n', encoding="utf-8")
    subprocess.run([sys.executable, str(LIB / "config_merge.py"), "toml-upsert-instance-keys", str(toml), "17.0", "",
                    "extra_requirements[]+=", "extra_requirements[]+=werkzeug>=2.0,<2.1", "extra_requirements[]+=requests"],
                   check=True, capture_output=True)
    row = json.loads(subprocess.run([sys.executable, str(LIB / "instances_io.py"), "read-row", str(toml), "17.0", "", "--json"],
                                    capture_output=True, text=True, check=True).stdout)
    assert row["extra_requirements"] == ["werkzeug>=2.0,<2.1", "requests"]


def test_a_build_script_that_wants_pip_makes_the_build_fall_back_to_pip_and_the_row_remembers_it(world):
    """fasttext's setup.py runs `pip install pybind11` inside uv's isolated build, where there is
    no pip. The build must not stop at "check system build deps": pip is added to the venv uv
    created, the requirements are installed with it, the row records build_tool = uv+pip and the
    next rebuild goes straight to that path."""
    uv_log = world["log"]
    _write_exec(world["tmp"] / "bin" / "uv", '''\
        #!/usr/bin/env bash
        echo "$@" >> "%s"
        if [ "$1" = "venv" ]; then
          d="$2"; mkdir -p "$d/bin" "$d/lib"; echo "home = /usr/bin" > "$d/pyvenv.cfg"
          printf '#!/usr/bin/env bash\\necho "$@" >> "%s"\\nexit 0\\n' > "$d/bin/python"; chmod +x "$d/bin/python"; echo new > "$d/MARKER"
          exit 0
        fi
        case "$*" in
          *"pip install"*" -r "*)
            echo "  x Failed to build \\`fasttext==0.9.2\\`" >&2
            echo "  ModuleNotFoundError: No module named 'pip'" >&2
            exit 1 ;;
        esac
        exit 0
        ''' % (uv_log, world["tmp"] / "python.log"))
    proc = _run(world, "create-venv", "--series", SERIES, "--profile", "std", "--rebuild")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "BUILD_FALLBACK=pip reason=" in proc.stdout and "No module named 'pip'" in proc.stdout
    assert "check system build deps" not in proc.stdout + proc.stderr
    python_calls = (world["tmp"] / "python.log").read_text()
    assert "-m pip install -r" in python_calls                      # pip, inside the venv uv created
    assert "pip install --python" in uv_log.read_text() and " pip\n" in uv_log.read_text()   # pip was added by uv
    assert _row(world)["build_tool"] == "uv+pip"
    # the next rebuild honours the recorded tool: no uv install of the requirements, no fallback message
    uv_log.write_text("")
    (world["tmp"] / "python.log").write_text("")
    proc = _run(world, "create-venv", "--series", SERIES, "--profile", "std", "--rebuild")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "BUILD_TOOL=uv+pip" in proc.stdout and "TOOL_SOURCE=row" in proc.stdout
    assert "BUILD_FALLBACK" not in proc.stdout
    assert " -r " not in uv_log.read_text() and "-m pip install -r" in (world["tmp"] / "python.log").read_text()


def test_a_build_that_fails_for_another_reason_names_the_error_line_and_the_log(world):
    _write_exec(world["tmp"] / "bin" / "uv", '''\
        #!/usr/bin/env bash
        if [ "$1" = "venv" ]; then
          d="$2"; mkdir -p "$d/bin" "$d/lib"; echo "home = /usr/bin" > "$d/pyvenv.cfg"
          printf '#!/usr/bin/env bash\\nexit 0\\n' > "$d/bin/python"; chmod +x "$d/bin/python"; exit 0
        fi
        echo "error: Failed to build \\`psycopg2==2.9.9\\`: pg_config executable not found" >&2
        exit 1
        ''')
    proc = _run(world, "create-venv", "--series", SERIES, "--profile", "std", "--rebuild")
    assert proc.returncode != 0
    assert "pg_config executable not found" in proc.stderr and ".build.log" in proc.stderr
    assert "check system build deps" not in proc.stderr
    assert (world["venv"] / "MARKER").read_text() == "old"       # the old venv came back


def _dist(venv: Path, name: str, version: str):
    d = venv / "lib" / "python3.12" / "site-packages" / ("%s-%s.dist-info" % (name.replace("-", "_"), version))
    d.mkdir(parents=True, exist_ok=True)
    (d / "METADATA").write_text("Metadata-Version: 2.1\nName: %s\nVersion: %s\n\nBody: ignored\n" % (name, version), encoding="utf-8")


def test_a_new_venv_without_a_recorded_python_lands_under_the_global_state_root_from_any_cwd(world, tmp_path):
    """venvs/ is host-global: the path is $ODOO_AI_HOME/venvs/<series>-<profile>, whatever the cwd
    (a directory that is not inside any git repository included)."""
    toml = world["home"] / "instances.toml"
    toml.write_text("".join(l for l in toml.read_text().splitlines(True) if not l.startswith("python = ")), encoding="utf-8")
    outside = tmp_path / "not-a-repo"; outside.mkdir()
    env = dict(world["env"]); env.pop("ODOO_AI_PROJECT_DIR", None)
    proc = subprocess.run(["bash", str(STEP), "create-venv", "--series", SERIES, "--profile", "std"],
                          capture_output=True, text=True, env=env, cwd=str(outside), timeout=120)
    expected = world["home"] / "venvs" / "17.0-std"
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "VENV_PATH=%s" % expected in proc.stdout and (expected / "pyvenv.cfg").is_file()
    assert not (world["home"] / "projects").exists()


def test_a_rebuild_names_the_packages_the_new_venv_lost_or_moved_before_removing_the_old_one(world):
    _dist(world["venv"], "lxml", "5.0.0"); _dist(world["venv"], "pylint-odoo", "9.0.5"); _dist(world["venv"], "requests", "2.31.0")
    _write_exec(world["tmp"] / "bin" / "uv", '''\
        #!/usr/bin/env bash
        if [ "$1" = "venv" ]; then
          d="$2"; mkdir -p "$d/bin" "$d/lib/python3.12/site-packages/lxml-5.2.0.dist-info" "$d/lib/python3.12/site-packages/requests-2.31.0.dist-info"
          printf 'Name: lxml\\nVersion: 5.2.0\\n' > "$d/lib/python3.12/site-packages/lxml-5.2.0.dist-info/METADATA"
          printf 'Name: requests\\nVersion: 2.31.0\\n' > "$d/lib/python3.12/site-packages/requests-2.31.0.dist-info/METADATA"
          echo "home = /usr/bin" > "$d/pyvenv.cfg"; printf '#!/usr/bin/env bash\\nexit 0\\n' > "$d/bin/python"; chmod +x "$d/bin/python"
        fi
        exit 0
        ''')
    proc = _run(world, "create-venv", "--series", SERIES, "--profile", "std", "--rebuild")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "DROPPED=pylint-odoo==9.0.5" in proc.stdout and "CHANGED=lxml 5.0.0->5.2.0" in proc.stdout
    assert "requests" not in proc.stdout.replace("--extra", "")      # unchanged: not reported
    assert "--extra" in proc.stdout
    assert not list(world["tmp"].glob("venvs/17.0-std.rebuilding-*"))   # the old venv is gone afterwards


def test_diff_venvs_is_never_fatal_for_a_missing_venv(tmp_path, capsys):
    assert venv_facts.cmd_diff_venvs(str(tmp_path / "nope"), str(tmp_path / "nada")) == 0
    assert capsys.readouterr().out == ""


def _stale(tmp_path, capsys, comment):
    f = tmp_path / "c.toml"; f.write_text("a = 1  # %s\n" % comment, encoding="utf-8")
    rc = venv_facts.cmd_stale_comments(str(f)); capsys.readouterr()
    return rc


def test_a_comment_is_stale_only_when_it_names_a_missing_path_under_a_directory_that_exists(tmp_path, capsys):
    assert _stale(tmp_path, capsys, "see %s" % (tmp_path / "gone" / "x.txt")) == 2      # a path claim, missing file
    assert _stale(tmp_path, capsys, "see %s." % (tmp_path / "gone")) == 2                # trailing "." stripped
    assert _stale(tmp_path, capsys, "see %s" % tmp_path) == 0                            # exists
    for prose in ("needs debian/control", "ports 8129/8139/8149", "Ephemeral/exclusive acquires",
                  "run /odoo-ai-agents:odoo-setup", "see (/odoo-ai-agents:odoo-setup)",
                  "Authentication to the cluster is set up by /odoo-ai-agents:odoo-setup.",
                  "see /nonexistent-root/x.txt"):
        assert _stale(tmp_path, capsys, prose) == 0, prose
