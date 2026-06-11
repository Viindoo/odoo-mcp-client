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
import shlex
import subprocess
import sys
import tomllib
from pathlib import Path
from shutil import which

import pytest

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "lib"
CONFIG_MERGE = LIB / "config_merge.py"
INSTANCES_IO = LIB / "instances_io.py"
STEP40 = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "setup-steps" / "40-instance-profile.sh"
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

def _discover_versions_by_repo(base_dir):
    """Drive the REAL discover_odoo.sh against *base_dir* and map repo -> version.

    Runs the shipped script end-to-end (via --base, so it never scans $HOME),
    parses its TSV, and returns {repo_basename: version_column}. discover_odoo.sh
    reports the repo root (one level above the addon module dir); the version
    column is the inferred Odoo series, or "unknown" when the script rejected the
    manifest version as junk.
    """
    proc = subprocess.run(
        ["bash", str(DISCOVER), "--base", str(base_dir)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, f"discover_odoo.sh failed: {proc.stderr}"
    mapping = {}
    for line in proc.stdout.splitlines():
        if line.startswith("#") or "\t" not in line:
            continue
        cols = line.split("\t")
        if len(cols) >= 3:
            _role, version, path = cols[0], cols[1], cols[2]
            mapping[Path(path).name] = version
    return mapping


@pytest.mark.skipif(which("bash") is None, reason="bash not available")
def test_discover_real_script_infers_series_for_valid_manifest(tmp_path):
    """The shipped discover_odoo.sh infers 17.0 from a real X.Y.z.a.b manifest.

    Builds a repo tree with a single addon whose manifest declares
    'version': '17.0.1.0.0' and drives the actual script. Fails if the real
    inference path stops extracting the leading Odoo series from a well-formed
    manifest (the accept case).
    """
    repo = tmp_path / "good_repo"
    addon = repo / "good_module"
    addon.mkdir(parents=True)
    (addon / "__manifest__.py").write_text(
        "{\n  'name': 'Good',\n  'version': '17.0.1.0.0',\n}\n", encoding="utf-8"
    )
    versions = _discover_versions_by_repo(tmp_path)
    assert versions.get("good_repo") == "17.0"


@pytest.mark.skipif(which("bash") is None, reason="bash not available")
@pytest.mark.parametrize("junk_version", ["0.1", "2.1", "1.0", "garbage"])
def test_discover_real_script_rejects_junk_versions(tmp_path, junk_version):
    """The shipped discover_odoo.sh does NOT infer a series from junk versions.

    Module-local versions ('0.1'/'2.1'/'1.0') and non-numeric junk must NOT be
    surfaced as an Odoo series; the script leaves the version column "unknown".
    Drives the real script (no Python re-implementation). Fails if the real
    inference starts accepting junk as a valid series.
    """
    repo = tmp_path / "junk_repo"
    addon = repo / "junk_module"
    addon.mkdir(parents=True)
    (addon / "__manifest__.py").write_text(
        "{\n  'name': 'Junk',\n  'version': '%s',\n}\n" % junk_version,
        encoding="utf-8",
    )
    versions = _discover_versions_by_repo(tmp_path)
    assert versions.get("junk_repo") == "unknown"


def test_discover_inference_not_reimplemented_drift_guard():
    """Backstop: the series inference still lives inside discover_odoo.sh.

    Guards against a refactor that deletes the inline inference from the shell
    script and silently moves the rule back into Python test code.
    """
    src = DISCOVER.read_text()
    assert "int(parts[0]) >= 8" in src and "parts[1] == '0'" in src


# --- CONTRACT-1: no-valid-series selection + `read` CLI exit contract --------

def test_select_instance_all_garbage_returns_none_false():
    """No valid X.Y series + no explicit request -> (None, False).

    Fails if select_instance falls back to a garbage/placeholder item (e.g.
    picks the first entry) instead of signalling "nothing selectable".
    """
    items = [{"series": "garbage"}, {"series": ""}, {"root": "/x"}]
    chosen, defaulted = io.select_instance(items, None)
    assert chosen is None
    assert defaulted is False


def test_select_instance_mixed_valid_and_garbage_picks_highest_valid():
    """Mixed valid + garbage -> highest VALID series, garbage ignored.

    Fails if a garbage 'series' poisons the comparison or is chosen over a real
    series.
    """
    items = [
        {"series": "garbage"},
        {"series": "16.0", "http_port": 8069},
        {"series": "18.0", "http_port": 8079},
        {"series": ""},
    ]
    chosen, defaulted = io.select_instance(items, None)
    assert defaulted is True
    assert chosen["series"] == "18.0"


def test_read_cli_all_garbage_exits_1_empty_stdout(tmp_path):
    """`read` over an all-garbage registry exits 1, errors to stderr, EMPTY stdout.

    Fails if the CLI exits 0 or prints a phantom INST_* block when there is no
    selectable instance (a downstream `eval` would then act on empty values).
    """
    toml = tmp_path / "instances.toml"
    toml.write_text(
        '[[instance]]\nseries = "garbage"\n\n[[instance]]\nseries = "nope"\n',
        encoding="utf-8",
    )
    proc = subprocess.run(
        [sys.executable, str(INSTANCES_IO), "read", str(toml)],
        text=True, capture_output=True,
    )
    assert proc.returncode == 1
    assert proc.stdout == ""
    assert proc.stderr.strip() != ""


def test_read_cli_exact_match_picks_requested_series(tmp_path):
    """`read <file> 16.0` returns the 16.0 instance even when a higher exists.

    Fails if exact-match selection regresses to "always highest" and ignores
    the requested series.
    """
    toml = tmp_path / "instances.toml"
    toml.write_text(
        '[[instance]]\nseries = "16.0"\naddons_path = ["/repos/16"]\n\n'
        '[[instance]]\nseries = "18.0"\naddons_path = ["/repos/18"]\n',
        encoding="utf-8",
    )
    proc = subprocess.run(
        [sys.executable, str(INSTANCES_IO), "read", str(toml), "16.0"],
        text=True, capture_output=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "INST_VERSION=16.0" in proc.stdout
    assert "INST_VERSION=18.0" not in proc.stdout


# --- CONTRACT-3: py<3.11 text-scan parses BOTH schemas -----------------------

def test_textscan_parses_legacy_dict_of_tables(tmp_path):
    """_load_textscan (the py<3.11 path) parses legacy [instance."X"] tables.

    Simulates an interpreter without tomllib by calling the text-scan path
    directly. Fails if the fallback only understands [[instance]] and silently
    drops the legacy dict-of-tables form (older registries become invisible).
    """
    toml = tmp_path / "legacy.toml"
    toml.write_text(
        '[instance."17.0"]\nroot = "/srv/odoo17"\n\n'
        '[instance.16.0]\nroot = "/srv/odoo16"\n',
        encoding="utf-8",
    )
    instances = io._load_textscan(str(toml))["instance"]
    series = sorted(io.series_of(i) for i in instances)
    assert len(instances) == 2
    assert series == ["16.0", "17.0"]


def test_textscan_matches_tomllib_for_array_of_tables(tmp_path):
    """_load_textscan and the tomllib path agree for array-of-tables.

    Fails if the fallback diverges from tomllib on the preferred schema (it
    must be a faithful stand-in when tomllib is unavailable).
    """
    toml = tmp_path / "instances.toml"
    toml.write_text(
        '[[instance]]\nseries = "16.0"\nhttp_port = 8069\n\n'
        '[[instance]]\nseries = "17.0"\nhttp_port = 8079\n',
        encoding="utf-8",
    )
    textscan = io._load_textscan(str(toml))["instance"]
    tomllib_path = io._load_tomllib(str(toml))["instance"]
    assert [io.series_of(d) for d in textscan] == [io.series_of(d) for d in tomllib_path]


# --- H1 regression: port-index seed must yield a single integer --------------

def _extract_port_seed_lines():
    """Pull the SHIPPED port-seed lines out of 40-instance-profile.sh.

    Captures the line that counts [[instance]] tables into a variable and any
    immediately following default-expansion line, so the regression test runs
    the real seeding logic (cannot drift from a re-implemented copy). Returns
    (count_line, default_line) where default_line may be "" if the count line
    already guarantees a single integer on its own.
    """
    text = STEP40.read_text(encoding="utf-8")
    lines = text.splitlines()
    count_idx = next(
        (i for i, ln in enumerate(lines)
         if "grep -cE '^\\[\\[instance\\]\\]'" in ln and "=" in ln),
        None,
    )
    assert count_idx is not None, "could not locate the grep -cE port-seed line"
    count_line = lines[count_idx].strip()
    # Identify the variable the count is assigned to (e.g. port_idx / existing_count).
    var = count_line.split("=", 1)[0].strip()
    default_line = ""
    nxt = lines[count_idx + 1].strip() if count_idx + 1 < len(lines) else ""
    if nxt.startswith(f"{var}=") and ":-" in nxt:
        default_line = nxt
    return var, count_line, default_line


@pytest.mark.skipif(which("bash") is None, reason="bash not available")
@pytest.mark.parametrize("scenario,expected", [
    ("absent", 0),  # registry file does not exist
    ("zero", 0),    # file exists but has zero [[instance]] (the H1 crash case)
    ("two", 2),     # file exists with two [[instance]]
])
def test_port_seed_yields_single_integer(tmp_path, scenario, expected):
    """The shipped port-seed yields ONE integer and never crashes $(( )).

    Builds a `set -euo pipefail` snippet from the REAL seeding line(s) and feeds
    the resulting count into arithmetic, against three registries. Fails
    (non-zero exit / "arithmetic syntax error") if the count ever becomes the
    two-line string "0\\n0" and breaks the arithmetic, or if the computed index
    is wrong.
    """
    var, count_line, default_line = _extract_port_seed_lines()

    toml = tmp_path / "instances.toml"
    if scenario == "zero":
        toml.write_text("# registry with no instances yet\n", encoding="utf-8")
    elif scenario == "two":
        toml.write_text(
            '[[instance]]\nseries = "16.0"\n\n[[instance]]\nseries = "17.0"\n',
            encoding="utf-8",
        )
    # "absent" -> do not create the file.

    snippet_lines = [
        "set -euo pipefail",
        f"INSTANCES_TOML={shlex.quote(str(toml))}",
        f"{var}=0",
        'if [ -f "$INSTANCES_TOML" ]; then',
        f"  {count_line}",
    ]
    if default_line:
        snippet_lines.append(f"  {default_line}")
    snippet_lines += [
        "fi",
        # Exercise the same arithmetic the shipped script performs downstream.
        f'computed=$(( 8069 + {var} * 10 ))',
        f'printf "%s" "${var}"',
    ]
    snippet = "\n".join(snippet_lines) + "\n"

    proc = subprocess.run(["bash", "-c", snippet], capture_output=True, text=True)
    assert proc.returncode == 0, (
        f"shipped port-seed crashed for scenario={scenario}: {proc.stderr.strip()}"
    )
    assert proc.stdout == str(expected), (
        f"scenario={scenario} expected {var}={expected} got {proc.stdout!r}"
    )
