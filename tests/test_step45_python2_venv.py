"""Behavior tests: `45-venv.sh create-venv` builds a Python 2.7 venv for a series whose checkout
declares Python 2 - with virtualenv, never uv/pip venv - or refuses with NEEDS_CONTEXT.

Contract protected:
  - uv cannot create a Python 2 environment and Python 2 has no `-m venv`, so a Python 2 series
    is built with a virtualenv that can still target 2.7 (`virtualenv<20.22`), run through uv
    when uv is present (`uvx --from 'virtualenv<20.22' virtualenv -p <python2.7> <dir>`), else a
    `virtualenv` on PATH older than 20.22, else virtualenv installed into the Python 2.7 itself;
    its requirements are installed with the venv's own pip (uv pip cannot target Python 2);
  - the Python 2.7 interpreter comes from ODOO_AI_PYTHON2 (which must BE a 2.7), else python2.7 /
    python2 on PATH, else pyenv's versions/2.7*;
  - with no 2.7 interpreter, or no virtualenv able to target it, the step exits 3 (NEEDS_CONTEXT)
    naming how to provide one, builds nothing and records nothing - it never quietly builds a
    Python 3 venv instead (the old `--tool pip` path fell back to python3).

Hermetic: PATH is the suite's farm with every python2 / uv / virtualenv / pyenv dropped, plus this
file's own stubs; HOME is a temp dir. Nothing is downloaded and no real Python 2 is needed.
"""

from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path
from shutil import which

import pytest

import odoo_tree_fixtures as trees
from conftest import farm_path, real_python3

ROOT = Path(__file__).resolve().parent.parent
STEP45 = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "setup-steps" / "45-venv.sh"
DROP = ("python2", "python2.7", "uv", "uvx", "virtualenv", "pyenv")
SPEC = "virtualenv<20.22"

requires_bash = pytest.mark.skipif(which("bash") is None, reason="bash not available")


def _stub(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8")
    path.chmod(0o755)
    return path


def _venv_maker(record: Path) -> str:
    """Shell that turns "$dir" into a venv whose python passes the step's odoo-bin gate and whose
    pip records its argv."""
    return textwrap.dedent(f"""\
        mkdir -p "$dir/bin"
        cat > "$dir/bin/python" <<'PYSTUB'
        #!/usr/bin/env bash
        if [[ "$2" == "--version" ]]; then echo "Odoo Server 10.0"; exit 0; fi
        exec {real_python3()} "$@"
        PYSTUB
        printf '#!/usr/bin/env bash\\necho "pip $*" >> "{record.parent / 'pip.log'}"\\n' > "$dir/bin/pip"
        chmod +x "$dir/bin/python" "$dir/bin/pip"
        """)


def _python2(path: Path, record: Path, version: str = "2.7", has_virtualenv: bool = False) -> Path:
    """A stub interpreter reporting `version`; optionally with `-m virtualenv` installed."""
    venv = ""
    if has_virtualenv:
        venv = textwrap.dedent(f"""\
            if [[ "$1" == "-m" && "$2" == "virtualenv" ]]; then
                if [[ "$3" == "--version" ]]; then echo "virtualenv 16.7.12"; exit 0; fi
                echo "py2-virtualenv $0 ${{*:3}}" >> "{record}"
                dir="${{@: -1}}"
            """) + _venv_maker(record) + "    exit 0\nfi\n"
    return _stub(path, venv + textwrap.dedent(f"""\
        if [[ "$1" == "-c" ]]; then printf '{version}\\n'; exit 0; fi
        exit 1
        """))


@pytest.fixture
def world(tmp_path, path_farm):
    core = trees.write_checkout(tmp_path / "core", "10.0")
    # The 10.0 launcher's own shebang is the checkout's statement that it runs on Python 2.
    launcher = core / "odoo-bin"
    launcher.write_text("#!/usr/bin/env python2\n", encoding="utf-8")
    launcher.chmod(0o755)
    (core / "requirements.txt").write_text("psycopg2==2.7.3.1\n", encoding="utf-8")
    toml = tmp_path / "instances.toml"
    toml.write_text(textwrap.dedent(f"""\
        [[instance]]
        series = "10.0"
        python = ""
        db_name = "odoo10"
        run_mode = "source"
        addons_path = "{core / 'addons'}"
        """), encoding="utf-8")
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    record = tmp_path / "calls.log"
    home = tmp_path / "home"
    home.mkdir()

    def run(*extra, env_over=None):
        env = {k: v for k, v in os.environ.items()
               if k not in ("PYENV_ROOT", "ODOO_AI_PYTHON2", "ODOO_AI_PYTHON3")}
        env.update(PATH=farm_path(path_farm(drop=DROP), stubs), HOME=str(home),
                   ODOO_AI_INSTANCES=str(toml), ODOO_AI_HOME=str(tmp_path / "odoo-ai-home"))
        env.update(env_over or {})
        return subprocess.run(["bash", str(STEP45), "create-venv", "--series", "10.0",
                               "--path", str(tmp_path / "venv"), *extra],
                              capture_output=True, text=True, env=env, timeout=60)

    return {"tmp": tmp_path, "core": core, "toml": toml, "stubs": stubs, "record": record,
            "home": home, "venv": tmp_path / "venv", "run": run}


def _uvx(world) -> Path:
    return _stub(world["stubs"] / "uvx", textwrap.dedent(f"""\
        printf '%s\\n' "uvx $*" >> "{world['record']}"
        dir="${{@: -1}}"
        """) + _venv_maker(world["record"]))


def _calls(world) -> list[str]:
    return world["record"].read_text().splitlines() if world["record"].exists() else []


def _recorded_python(world) -> str:
    for line in world["toml"].read_text().splitlines():
        if line.strip().startswith("python ="):
            return line.split("=", 1)[1].strip().strip('"')
    return ""


def _assert_nothing_built(world, res):
    assert res.returncode == 3, (res.stdout, res.stderr)
    assert "NEEDS_CONTEXT" in res.stderr
    assert not world["venv"].exists(), "nothing may be built"
    assert _recorded_python(world) == "", "nothing may be recorded"


@requires_bash
def test_a_python2_series_is_built_by_a_python2_capable_virtualenv_through_uv(world):
    py2 = _python2(world["stubs"] / "python2.7", world["record"])
    _uvx(world)
    res = world["run"]()
    assert res.returncode == 0, (res.stdout, res.stderr)
    assert _calls(world) == ["uvx --from %s virtualenv -p %s %s" % (SPEC, py2, world["venv"])]
    pip = (world["tmp"] / "pip.log").read_text()
    assert "pip install -r %s" % (world["core"] / "requirements.txt") in pip, (
        "requirements go through the venv's own pip: uv pip cannot target Python 2")
    assert _recorded_python(world) == str(world["venv"] / "bin" / "python")


@requires_bash
@pytest.mark.parametrize("tool", ["uv", "pip"])
def test_no_python2_interpreter_is_needs_context_never_a_python3_venv(world, tool):
    """The old `--tool pip` path printed a note and built the venv with python3."""
    _uvx(world)
    res = world["run"]("--tool", tool)
    _assert_nothing_built(world, res)
    assert "ODOO_AI_PYTHON2" in res.stderr and "python2.7" in res.stderr
    assert _calls(world) == [], "no builder may run"


@requires_bash
def test_odoo_ai_python2_names_the_interpreter(world):
    chosen = _python2(world["tmp"] / "elsewhere" / "py27", world["record"])
    _python2(world["stubs"] / "python2.7", world["record"])
    _uvx(world)
    res = world["run"](env_over={"ODOO_AI_PYTHON2": str(chosen)})
    assert res.returncode == 0, (res.stdout, res.stderr)
    assert _calls(world) == ["uvx --from %s virtualenv -p %s %s" % (SPEC, chosen, world["venv"])]


@requires_bash
def test_an_odoo_ai_python2_that_is_not_2_7_is_refused_not_skipped(world):
    wrong = _python2(world["tmp"] / "elsewhere" / "py3", world["record"], version="3.12")
    _python2(world["stubs"] / "python2.7", world["record"])
    _uvx(world)
    res = world["run"](env_over={"ODOO_AI_PYTHON2": str(wrong)})
    _assert_nothing_built(world, res)
    assert "3.12" in res.stderr


@requires_bash
def test_a_pyenv_python27_is_found_when_path_has_none(world):
    py2 = _python2(world["home"] / ".pyenv" / "versions" / "2.7.18" / "bin" / "python2.7",
                   world["record"])
    _uvx(world)
    res = world["run"]()
    assert res.returncode == 0, (res.stdout, res.stderr)
    assert _calls(world) == ["uvx --from %s virtualenv -p %s %s" % (SPEC, py2, world["venv"])]


@requires_bash
def test_a_python2_that_reports_another_version_on_path_is_not_used(world):
    _python2(world["stubs"] / "python2", world["record"], version="3.11")
    _uvx(world)
    _assert_nothing_built(world, world["run"]())


@requires_bash
def test_without_uv_an_old_enough_virtualenv_on_path_builds_it(world):
    py2 = _python2(world["stubs"] / "python2.7", world["record"])
    _stub(world["stubs"] / "virtualenv", textwrap.dedent(f"""\
        if [[ "$1" == "--version" ]]; then echo "virtualenv 20.21.1 from /x/virtualenv/__init__.py"; exit 0; fi
        printf '%s\\n' "virtualenv $*" >> "{world['record']}"
        dir="${{@: -1}}"
        """) + _venv_maker(world["record"]))
    res = world["run"]()
    assert res.returncode == 0, (res.stdout, res.stderr)
    assert _calls(world) == ["virtualenv -p %s %s" % (py2, world["venv"])]


@requires_bash
def test_a_virtualenv_too_new_to_target_python2_is_not_used(world):
    _python2(world["stubs"] / "python2.7", world["record"])
    _stub(world["stubs"] / "virtualenv", textwrap.dedent(f"""\
        if [[ "$1" == "--version" ]]; then echo "virtualenv 20.26.6 from /x"; exit 0; fi
        printf '%s\\n' "virtualenv $*" >> "{world['record']}"
        exit 0
        """))
    res = world["run"]()
    _assert_nothing_built(world, res)
    assert SPEC in res.stderr and "uv" in res.stderr, "the refusal names how to provide one"
    assert _calls(world) == []


@requires_bash
def test_without_uv_the_python2s_own_virtualenv_builds_it(world):
    py2 = _python2(world["stubs"] / "python2.7", world["record"], has_virtualenv=True)
    res = world["run"]()
    assert res.returncode == 0, (res.stdout, res.stderr)
    assert _calls(world) == ["py2-virtualenv %s %s" % (py2, world["venv"])]
    assert _recorded_python(world) == str(world["venv"] / "bin" / "python")
