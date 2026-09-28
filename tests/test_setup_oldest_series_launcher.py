"""The oldest Odoo series ship `openerp-server`, not `odoo-bin` - every setup path must find it.

Business rule protected: a source instance of a series whose core package is `openerp/` (the
checkout carries `openerp-server` and `openerp/release.py`, no `odoo-bin`) is as usable as any
other. Before this rule, every setup step located the core ONLY by an executable `odoo-bin`, so on
those series `45-venv.sh record-env` / `create-venv` recorded nothing, the prerequisite gate
failed a working venv, repo discovery missed the core repo, and spin-up / instance ops found no
launcher.

ONE locator answers everywhere: `scripts/lib/odoo_source_facts.py locate-launcher`, reached from
shell through `resolve_instances.sh`'s `_odoo_find_launcher`. A second hand-rolled `odoo-bin`
scan is how the oldest series got lost, so a guard pins that no script carries one.

Fixture trees are built under tmp_path; real checkouts are used when present
(`$ODOO_SOURCE_CHECKOUTS/odoo_<series>`, default a `git` directory under the home directory).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import textwrap
import tomllib
from pathlib import Path

import pytest

from conftest import real_python3

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
SCRIPTS = PLUGIN / "scripts"
STEPS = SCRIPTS / "setup-steps"
RESOLVE = SCRIPTS / "lib" / "resolve_instances.sh"
DISCOVER = SCRIPTS / "lib" / "discover_odoo.sh"
STEP05 = STEPS / "05-prereq-check.sh"
STEP45 = STEPS / "45-venv.sh"
CHECKOUTS = Path(os.environ.get("ODOO_SOURCE_CHECKOUTS") or (Path.home() / "git"))

requires_bash = pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")


def _exe(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)
    return path


def _oldest_core(base: Path, series: str = "8.0", name: str = "odoo8") -> Path:
    """A checkout shaped like the oldest series: openerp-server + openerp/ package, no odoo-bin."""
    root = base / name
    major = series.split(".")[0]
    _exe(root / "openerp-server", "#!/usr/bin/env python\nimport openerp\n")
    (root / "openerp").mkdir(parents=True, exist_ok=True)
    (root / "openerp" / "release.py").write_text(
        "version_info = (%s, 0, 0, 'final', 0)\n" % major, encoding="utf-8")
    (root / "openerp" / "addons").mkdir(parents=True, exist_ok=True)
    (root / "addons").mkdir(parents=True, exist_ok=True)
    (root / "requirements.txt").write_text("", encoding="utf-8")
    return root


def _newer_core(base: Path, name: str = "odoo17") -> Path:
    root = base / name
    _exe(root / "odoo-bin", "#!/usr/bin/env python3\n")
    (root / "odoo").mkdir(parents=True, exist_ok=True)
    (root / "odoo" / "release.py").write_text("version_info = (17, 0, 0, 'final', 0, '')\n",
                                              encoding="utf-8")
    (root / "addons").mkdir(parents=True, exist_ok=True)
    return root


def _find(addons_path: str, odoo_root: str = "", env_extra=None):
    env = dict(os.environ)
    env.pop("ODOO_BIN", None)
    env.update(env_extra or {})
    return subprocess.run(
        ["bash", "-c", 'source "$1"; _odoo_find_launcher "$2" "$3"', "_", str(RESOLVE),
         addons_path, odoo_root],
        capture_output=True, text=True, env=env, timeout=60)


def _venv(base: Path) -> Path:
    """A venv python that answers `<py> <launcher> --version` and delegates the rest."""
    return _exe(base / "venv" / "bin" / "python", textwrap.dedent(f"""\
        #!/usr/bin/env bash
        if [[ "$2" == "--version" ]]; then echo "OpenERP Server 8.0"; exit 0; fi
        exec {real_python3()} "$@"
        """))


# ============================================================ the shared shell locator

@requires_bash
@pytest.mark.parametrize("entry", ["addons", "openerp/addons"])
def test_locator_finds_openerp_server_from_an_oldest_series_addons_path(tmp_path, entry):
    core = _oldest_core(tmp_path)
    res = _find("%s,%s" % (tmp_path / "custom", core / entry))
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == str(core / "openerp-server")


@requires_bash
def test_locator_still_finds_odoo_bin_and_honours_the_explicit_override(tmp_path):
    core = _newer_core(tmp_path)
    assert _find(str(core / "addons")).stdout.strip() == str(core / "odoo-bin")
    override = _exe(tmp_path / "elsewhere" / "odoo-bin", "#!/bin/sh\n")
    res = _find(str(core / "addons"), env_extra={"ODOO_BIN": str(override)})
    assert res.stdout.strip() == str(override)


@requires_bash
def test_locator_uses_the_declared_root_when_the_addons_path_has_no_core(tmp_path):
    core = _oldest_core(tmp_path)
    res = _find(str(tmp_path / "custom"), str(core))
    assert res.stdout.strip() == str(core / "openerp-server")


@requires_bash
def test_locator_refuses_a_non_executable_launcher_and_an_empty_path(tmp_path):
    core = _oldest_core(tmp_path)
    (core / "openerp-server").chmod(0o644)
    assert _find(str(core / "addons")).returncode == 1
    assert _find("").returncode == 1


def test_no_script_scans_for_the_launcher_on_its_own():
    """One locator. A step that tests `-x .../odoo-bin` itself cannot see `openerp-server`."""
    own_scan = re.compile(r"""-[xf]\s+"[^"\n]*/odoo-bin"|\bodoo-bin"\s*\]\]""")
    offenders = []
    for path in sorted(SCRIPTS.rglob("*.sh")):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            if own_scan.search(line):
                offenders.append("%s:%d: %s" % (path.relative_to(PLUGIN), n, line.strip()))
    assert not offenders, "locate the launcher through _odoo_find_launcher:\n" + "\n".join(offenders)


# ============================================================ the steps that use it

@requires_bash
def test_record_env_records_python_and_root_on_an_oldest_series_checkout(tmp_path):
    core = _oldest_core(tmp_path)
    venv_py = _venv(tmp_path)
    catalog = tmp_path / "instances.toml"
    catalog.write_text('[[instance]]\nseries = "8.0"\naddons_path = ["%s"]\npython = "%s"\n'
                       % (core / "addons", venv_py), encoding="utf-8")
    env = dict(os.environ)
    env.pop("ODOO_BIN", None)
    env.update({"ODOO_AI_INSTANCES": str(catalog), "ODOO_AI_HOME": str(tmp_path / "home"),
                "PG_MODE_PROBE_TIMEOUT": "2"})
    res = subprocess.run(["bash", str(STEP45), "record-env", "--series", "8.0"],
                         capture_output=True, text=True, env=env, timeout=180)
    row = tomllib.loads(catalog.read_text())["instance"][0]
    assert row.get("odoo_root") == str(core), res.stdout + res.stderr
    assert row["python"] == str(venv_py)
    assert "failed - python and odoo_root were NOT" not in res.stderr


@requires_bash
def test_prereq_gate_passes_a_working_venv_and_sees_the_repo_on_an_oldest_series(tmp_path):
    base = tmp_path / "repos"
    core = _oldest_core(base)
    venv_py = _venv(tmp_path)
    catalog = tmp_path / "instances.toml"
    catalog.write_text(
        '[[instance]]\nseries = "8.0"\nrun_mode = "source"\naddons_path = ["%s"]\npython = "%s"\n'
        % (core / "addons", venv_py), encoding="utf-8")
    stubs = tmp_path / "bin05"
    _exe(stubs / "curl", '#!/usr/bin/env bash\necho "200"\n')
    _exe(stubs / "pg_isready", "#!/usr/bin/env bash\nexit 0\n")
    env = dict(os.environ)
    env.pop("ODOO_BIN", None)
    env.pop("ODOO_AI_ALLOW_NO_VENV", None)
    env.update({"PATH": "%s:%s" % (stubs, env.get("PATH", "")), "SETUP_FILTER": "instance",
                "ODOO_AI_INSTANCES": str(catalog), "ODOO_GIT_BASE": str(base),
                "ODOO_AI_HOME": str(tmp_path / "home")})
    res = subprocess.run(["bash", str(STEP05), "check"], capture_output=True, text=True, env=env,
                         timeout=180)
    out = res.stdout + res.stderr
    assert "FAILED" not in out, out
    assert res.returncode == 0, out


@requires_bash
def test_discovery_classifies_an_oldest_series_core_repo_as_core(tmp_path):
    base = tmp_path / "repos"
    core = _oldest_core(base, series="9.0", name="odoo9")
    env = dict(os.environ)
    env["ODOO_GIT_BASE"] = str(base)
    res = subprocess.run(["bash", str(DISCOVER)], capture_output=True, text=True, env=env,
                         timeout=120)
    rows = [ln.split("\t") for ln in res.stdout.splitlines() if ln and not ln.startswith("#")]
    assert ["core", "9.0", str(core)] in [r[:3] for r in rows], res.stdout + res.stderr


# ============================================================ real checkouts

@requires_bash
@pytest.mark.parametrize("series, launcher", [
    ("8.0", "openerp-server"), ("9.0", "openerp-server"), ("10.0", "odoo-bin"), ("17.0", "odoo-bin"),
])
def test_real_checkout_launcher(series, launcher):
    root = CHECKOUTS / ("odoo_%s" % series)
    if not root.is_dir():
        pytest.skip("no Odoo %s checkout at %s" % (series, root))
    res = _find(str(root / "addons"))
    assert res.stdout.strip() == str(root / launcher), res.stderr
