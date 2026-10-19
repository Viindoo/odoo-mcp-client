"""Behavior tests: `45-venv.sh` gives a venv the packages the checkout's test framework imports
optionally.

Contract protected:
  - Odoo's test framework imports some packages only when present and SKIPS every browser, tour
    and Hoot test without them; no requirements.txt lists them. `create-venv` reads them from the
    checkout (`tests/common.py`), checks each one against the new venv, and installs a missing one
    with the SAME tool that built the venv, one line per package;
  - a package the venv already imports is not reinstalled; a checkout that declares none installs
    nothing;
  - a failed install never costs the venv: it is still recorded, and the line says the browser,
    tour and Hoot tests will skip;
  - `record-env` reports a missing one and installs nothing.

Hermetic: PATH is the suite's farm with uv dropped, plus this file's own `uv` stub; HOME is a temp
dir. Nothing is downloaded. The venv's python is a stub whose imports are what the stub `uv`
installed (a `provides` file maps each distribution to the import it brings).
"""

from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path
from shutil import which

import pytest

import odoo_tree_fixtures as trees
from conftest import farm_path

ROOT = Path(__file__).resolve().parent.parent
STEP45 = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "setup-steps" / "45-venv.sh"
DROP = ("uv", "uvx", "pyenv")
SERIES = "17.0"
FAIL_LINE = "install FAILED - browser, tour and Hoot tests will SKIP"

requires_bash = pytest.mark.skipif(which("bash") is None, reason="bash not available")


def _stub(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8")
    path.chmod(0o755)
    return path


def _venv_python(venv: Path) -> str:
    """A venv python stub: passes the launcher gate, and imports a name only when it is listed in
    the venv's `imports` file (what the stub uv / pip installed, or what the test pre-seeded)."""
    return textwrap.dedent(f"""\
        mkdir -p "{venv}/bin"
        touch "{venv}/imports"
        cat > "{venv}/bin/python" <<'PYSTUB'
        #!/usr/bin/env bash
        if [[ "$2" == "--version" ]]; then echo "Odoo Server {SERIES}"; exit 0; fi
        if [[ "$1" == "-c" ]]; then grep -qxF -- "$3" "{venv}/imports"; exit $?; fi
        exit 0
        PYSTUB
        chmod +x "{venv}/bin/python"
        """)


@pytest.fixture
def world(tmp_path, path_farm):
    core = trees.write_checkout(tmp_path / "core", SERIES)
    launcher = core / "odoo-bin"
    launcher.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    launcher.chmod(0o755)
    toml = tmp_path / "instances.toml"
    venv = tmp_path / "venv"
    toml.write_text(textwrap.dedent(f"""\
        [[instance]]
        series = "{SERIES}"
        python = ""
        db_name = "odoo17"
        run_mode = "source"
        addons_path = "{core / 'addons'}"
        """), encoding="utf-8")
    stubs = tmp_path / "stubs"
    record = tmp_path / "uv.log"
    provides = tmp_path / "provides"   # "<distribution> <import>" per line
    failing = tmp_path / "failing"     # distributions whose install fails
    provides.write_text("", encoding="utf-8")
    failing.write_text("", encoding="utf-8")
    _stub(stubs / "uv", textwrap.dedent(f"""\
        printf '%s\\n' "uv $*" >> "{record}"
        if [[ "$1" == "venv" ]]; then
        """) + _venv_python(venv) + textwrap.dedent(f"""\
            exit 0
        fi
        if [[ "$1" == "pip" && "$2" == "install" ]]; then
            last="${{@: -1}}"
            [[ "$3" == "--python" && "$*" != *" -r "* ]] || exit 0
            grep -qxF -- "$last" "{failing}" && {{ echo "no matching distribution $last" >&2; exit 1; }}
            imp="$(awk -v d="$last" '$1 == d {{ print $2 }}' "{provides}")"
            venv_dir="$(dirname "$(dirname "$4")")"
            echo "${{imp:-$last}}" >> "$venv_dir/imports"
            exit 0
        fi
        exit 0
        """))
    home = tmp_path / "home"
    home.mkdir()

    def run(*args):
        env = dict(os.environ)
        env.update(PATH=farm_path(path_farm(drop=DROP), stubs), HOME=str(home),
                   ODOO_AI_INSTANCES=str(toml), ODOO_AI_HOME=str(tmp_path / "odoo-ai-home"))
        return subprocess.run(["bash", str(STEP45), *args], capture_output=True, text=True,
                              env=env, timeout=120)

    def create():
        return run("create-venv", "--series", SERIES, "--tool", "uv", "--path", str(venv))

    return {"tmp": tmp_path, "core": core, "toml": toml, "venv": venv, "record": record,
            "provides": provides, "failing": failing, "run": run, "create": create}


def _installs(world) -> list[str]:
    lines = world["record"].read_text().splitlines() if world["record"].exists() else []
    return [ln for ln in lines if ln.startswith("uv pip install") and " -r " not in ln]


def _recorded_python(world) -> str:
    for line in world["toml"].read_text().splitlines():
        if line.strip().startswith("python ="):
            return line.split("=", 1)[1].strip().strip('"')
    return ""


@requires_bash
def test_create_venv_installs_each_optional_test_import_with_the_venvs_own_tool(world):
    trees.write_test_common(world["core"], SERIES, imports=(("websocket", "websocket-client"),
                                                           ("fictional_driver", None)))
    world["provides"].write_text("websocket-client websocket\n", encoding="utf-8")
    res = world["create"]()
    assert res.returncode == 0, (res.stdout, res.stderr)
    py = world["venv"] / "bin" / "python"
    assert _installs(world) == ["uv pip install --python %s websocket-client" % py,
                                "uv pip install --python %s fictional_driver" % py]
    assert "websocket-client (import websocket): installed" in res.stdout
    assert "fictional_driver (import fictional_driver): installed" in res.stdout
    assert _recorded_python(world) == str(py)


@requires_bash
def test_an_optional_test_import_the_venv_already_has_is_not_reinstalled(world):
    trees.write_test_common(world["core"], SERIES)
    # requirements.txt already brought it: the stub records it as importable on venv creation.
    (world["core"] / "requirements.txt").write_text("websocket-client\n", encoding="utf-8")
    seed = world["tmp"] / "stubs" / "uv"
    seed.write_text(seed.read_text().replace(
        'if [[ "$1" == "pip" && "$2" == "install" ]]; then',
        'if [[ "$1" == "pip" && "$*" == *" -r "* ]]; then echo websocket >> "%s/imports"; exit 0; fi\n'
        'if [[ "$1" == "pip" && "$2" == "install" ]]; then' % world["venv"]), encoding="utf-8")
    res = world["create"]()
    assert res.returncode == 0, (res.stdout, res.stderr)
    assert _installs(world) == []
    assert "websocket-client (import websocket): present" in res.stdout


@requires_bash
def test_a_checkout_that_declares_no_optional_import_installs_nothing(world):
    trees.write_test_common(world["core"], SERIES, imports=())
    res = world["create"]()
    assert res.returncode == 0, (res.stdout, res.stderr)
    assert _installs(world) == []
    assert "imports no optional package" in res.stdout


@requires_bash
def test_a_checkout_without_a_test_framework_file_states_none_and_installs_nothing(world):
    res = world["create"]()
    assert res.returncode == 0, (res.stdout, res.stderr)
    assert _installs(world) == []
    assert "the checkout states none" in res.stdout


@requires_bash
def test_a_failed_install_still_records_the_venv_and_says_tests_will_skip(world):
    trees.write_test_common(world["core"], SERIES)
    world["failing"].write_text("websocket-client\n", encoding="utf-8")
    res = world["create"]()
    assert res.returncode == 0, (res.stdout, res.stderr)
    py = world["venv"] / "bin" / "python"
    assert "websocket-client (import websocket): %s; install it into %s by hand" % (FAIL_LINE, py) \
        in res.stdout
    assert _recorded_python(world) == str(py)
    assert "ok venv ready" in res.stdout


@requires_bash
def test_record_env_reports_a_missing_optional_import_and_installs_nothing(world):
    trees.write_test_common(world["core"], SERIES)
    exec_lines = _venv_python(world["venv"])
    subprocess.run(["bash", "-c", exec_lines], check=True)
    py = world["venv"] / "bin" / "python"
    world["toml"].write_text(world["toml"].read_text().replace('python = ""', 'python = "%s"' % py),
                             encoding="utf-8")
    res = world["run"]("record-env", "--series", SERIES)
    assert "the venv lacks websocket-client (import websocket)" in res.stderr, (res.stdout, res.stderr)
    assert str(py) in res.stderr and "create-venv --series %s" % SERIES in res.stderr
    assert _installs(world) == []
    assert "websocket" not in (world["venv"] / "imports").read_text()
