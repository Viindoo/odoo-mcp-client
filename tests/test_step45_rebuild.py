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

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
LIB = PLUGIN / "scripts" / "lib"
STEP = PLUGIN / "scripts" / "setup-steps" / "45-venv.sh"
sys.path.insert(0, str(LIB))
import venv_facts  # noqa: E402

SERIES = "17.0"


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
def world(tmp_path):
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
        # old note: see /nonexistent/override-18.0.txt
        ''' % (addons, odoo / "addons", venv / "bin" / "python")), encoding="utf-8")
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
                "PATH": "%s:%s" % (bindir, env.get("PATH", "")), "ODOO_AI_PROJECT_DIR": str(tmp_path / "share"),
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


def test_a_venv_shared_by_two_rows_is_refused_unless_forced(world):
    toml = world["home"] / "instances.toml"
    toml.write_text(toml.read_text() + textwrap.dedent('''\

        [[instance]]
        series = "17.0"
        profile = "other"
        addons_path = ["%s"]
        python = "%s"
        ''' % (world["odoo"] / "addons", world["venv"] / "bin" / "python")), encoding="utf-8")
    proc = _run(world, "create-venv", "--series", SERIES, "--profile", "std", "--rebuild")
    assert proc.returncode == 1 and "17.0:other" in proc.stderr and "--force" in proc.stderr


def test_check_flags_a_dead_python_a_missing_override_and_a_stale_comment(world):
    proc = _run(world, "check")
    assert proc.returncode == 0 and "STALE_COMMENT" in proc.stderr and "/nonexistent/override-18.0.txt" in proc.stderr
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
