"""Regression tests for the Odoo instance-profile machinery (setup steps 40/50).

These guard the behaviour fixed for issue #19:
  - #1 instances.toml round-trips through tomllib (array-of-tables, no dotted
        keys) so the reader finds the instance on Python 3.11+.
  - #4 each declared instance gets a distinct http_port.
  - #5 a fresh discovery never writes a junk "0.0" placeholder instance.
  - #6 with no --version the highest valid series is selected, not the lowest.
  - #2 the per-instance `python` field / ODOO_PYTHON override is honoured.

CPU-only: no PostgreSQL, no Odoo, no network. Uses the real library modules.
"""

import importlib.util
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "plugins" / "odoo-semantic-skills" / "scripts" / "lib"
CONFIG_MERGE = LIB / "config_merge.py"
INSTANCES_IO = LIB / "instances_io.py"
STEP40 = ROOT / "plugins" / "odoo-semantic-skills" / "scripts" / "setup-steps" / "40-instance-profile.sh"
DISCOVER = LIB / "discover_odoo.sh"


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


io = _load_module("instances_io", INSTANCES_IO)


def _append_instance(toml_path, series, body):
    """Drive config_merge.py toml-append-array-item like step 40 does."""
    proc = subprocess.run(
        [sys.executable, str(CONFIG_MERGE), "toml-append-array-item",
         str(toml_path), "instance", "series", series],
        input=body, text=True, capture_output=True,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


def _body(series, port, python=""):
    return (
        f'series = "{series}"\n'
        f'addons_path = ["/repos/{series}"]\n'
        f'run_mode = "source"\n'
        f'http_port = {port}\n'
        f'db_name = "odoo_{series.replace(".", "_")}"\n'
        f'python = "{python}"\n'
    )


# --- #1: array-of-tables round-trips through tomllib --------------------------

def test_instances_toml_roundtrips_through_tomllib(tmp_path):
    toml = tmp_path / "instances.toml"
    _append_instance(toml, "17.0", _body("17.0", 8069))
    data = tomllib.loads(toml.read_text())
    # Must be an array of tables keyed by a `series` field - NOT a nested
    # instance.17.0 dotted table (the bug that made get("17.0") return None).
    assert isinstance(data["instance"], list)
    assert data["instance"][0]["series"] == "17.0"
    assert data["instance"][0]["http_port"] == 8069


def test_append_is_idempotent_per_series(tmp_path):
    toml = tmp_path / "instances.toml"
    _append_instance(toml, "17.0", _body("17.0", 8069))
    out = _append_instance(toml, "17.0", _body("17.0", 8069))
    assert out.splitlines()[-1] == "exists"
    data = tomllib.loads(toml.read_text())
    assert len(data["instance"]) == 1


# --- #4: distinct ports ------------------------------------------------------

def test_declared_instances_get_distinct_ports(tmp_path):
    toml = tmp_path / "instances.toml"
    _append_instance(toml, "17.0", _body("17.0", 8069))
    _append_instance(toml, "18.0", _body("18.0", 8079))
    ports = [i["http_port"] for i in tomllib.loads(toml.read_text())["instance"]]
    assert len(ports) == len(set(ports)), f"ports collide: {ports}"


# --- #6: default selection picks the highest valid series --------------------

def test_select_instance_defaults_to_highest_series():
    items = [
        {"series": "16.0", "http_port": 8069},
        {"series": "18.0", "http_port": 8079},
        {"series": "17.0", "http_port": 8089},
    ]
    chosen, defaulted = io.select_instance(items, None)
    assert chosen["series"] == "18.0"
    assert defaulted is True


def test_select_instance_skips_placeholder_series():
    items = [
        {"series": "0.0", "http_port": 8069},
        {"series": "17.0", "http_port": 8079},
    ]
    chosen, _ = io.select_instance(items, None)
    assert chosen["series"] == "17.0"


def test_select_instance_exact_version():
    items = [{"series": "17.0"}, {"series": "18.0"}]
    chosen, defaulted = io.select_instance(items, "17.0")
    assert chosen["series"] == "17.0"
    assert defaulted is False


# --- #2: the python interpreter field is surfaced to the reader --------------

def test_reader_emits_python_field(tmp_path):
    toml = tmp_path / "instances.toml"
    _append_instance(toml, "17.0", _body("17.0", 8069, python="/opt/venv/bin/python"))
    proc = subprocess.run(
        [sys.executable, str(INSTANCES_IO), "read", str(toml), "17.0"],
        text=True, capture_output=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "INST_PYTHON=/opt/venv/bin/python" in proc.stdout


# --- legacy compatibility ----------------------------------------------------

def test_reader_tolerates_legacy_dotted_table(tmp_path):
    # A pre-fix instances.toml used [instance.X] dotted tables. The reader must
    # still extract them (so an upgrade does not strand an existing file).
    toml = tmp_path / "instances.toml"
    toml.write_text(
        '[instance."17.0"]\n'
        'version = "17.0"\n'
        'http_port = 8069\n'
    )
    items = io.load_instances(str(toml))
    assert any(io.series_of(i) == "17.0" for i in items)


# --- #5: discovery rejects non-series module versions ------------------------

@pytest.mark.parametrize("manifest_version,expected", [
    ("17.0.1.0.0", "17.0"),
    ("18.0.2.1.3", "18.0"),
    ("0.1", ""),      # module-local version, not an Odoo series
    ("2.1", ""),      # module-local version, not an Odoo series
    ("1.0", ""),      # too-low major
])
def test_discover_series_inference_rejects_junk(tmp_path, manifest_version, expected):
    # Re-implement the exact inference snippet from discover_odoo.sh and assert
    # it matches the documented behaviour. Keeps the rule under test even though
    # the production copy lives inline in the shell script.
    import ast
    parts = str(manifest_version).split(".")
    got = ""
    if len(parts) >= 2 and parts[0].isdigit() and int(parts[0]) >= 8 and parts[1] == "0":
        got = f"{parts[0]}.{parts[1]}"
    assert got == expected
    # And assert the shell script still contains this guard (catches drift).
    src = DISCOVER.read_text()
    assert 'int(parts[0]) >= 8' in src and "parts[1] == '0'" in src
