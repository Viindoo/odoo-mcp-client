"""Tests for the per-profile API additions to scripts/lib/instances_io.py.

Business rules protected:
  - profile_of / instance_key_of return correct values with and without profile.
  - select_instance with profile= filters to the correct item when two items
    share a series but differ in profile.
  - _cmd_read emits INST_PROFILE and INST_KEY for both profiled and plain instances.
  - The read CLI accepts an optional third positional arg [profile] and uses it.

CPU-only: no PostgreSQL, no Odoo, no network. Uses the real library modules.
"""

import importlib.util
import shlex
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "lib"
INSTANCES_IO = LIB / "instances_io.py"


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


io = _load_module("instances_io", INSTANCES_IO)


# ---------------------------------------------------------------------------
# profile_of / instance_key_of
# ---------------------------------------------------------------------------

def test_profile_of_returns_empty_string_when_no_profile():
    item = {"series": "17.0", "addons_path": ["/a"]}
    assert io.profile_of(item) == ""


def test_profile_of_returns_profile_when_present():
    item = {"series": "17.0", "profile": "minimal_17"}
    assert io.profile_of(item) == "minimal_17"


def test_instance_key_of_no_profile_equals_series():
    item = {"series": "17.0"}
    assert io.instance_key_of(item) == "17.0"


def test_instance_key_of_with_profile_uses_colon_join():
    item = {"series": "17.0", "profile": "minimal_17"}
    assert io.instance_key_of(item) == "17.0:minimal_17"


def test_instance_key_of_with_empty_profile_equals_series():
    item = {"series": "17.0", "profile": ""}
    assert io.instance_key_of(item) == "17.0"


# ---------------------------------------------------------------------------
# select_instance with profile filter
# ---------------------------------------------------------------------------

_ITEMS_TWO_PROFILES = [
    {"series": "17.0", "profile": "minimal_17", "db_name": "odoo_minimal"},
    {"series": "17.0", "profile": "full_17", "db_name": "odoo_full"},
]


def test_select_instance_with_profile_returns_correct_item():
    item, defaulted = io.select_instance(_ITEMS_TWO_PROFILES, "17.0", profile="minimal_17")
    assert item is not None
    assert item["db_name"] == "odoo_minimal"
    assert defaulted is False


def test_select_instance_with_other_profile_returns_other_item():
    item, defaulted = io.select_instance(_ITEMS_TWO_PROFILES, "17.0", profile="full_17")
    assert item is not None
    assert item["db_name"] == "odoo_full"
    assert defaulted is False


def test_select_instance_with_unknown_profile_returns_none():
    item, _ = io.select_instance(_ITEMS_TWO_PROFILES, "17.0", profile="nonexistent")
    assert item is None


def test_select_instance_without_profile_picks_first_match():
    """Without profile filter, select_instance returns the first series match
    (existing behavior for want= is first-match, no profile discrimination)."""
    item, defaulted = io.select_instance(_ITEMS_TWO_PROFILES, "17.0")
    assert item is not None
    assert defaulted is False
    # Either item is valid (first match = minimal_17 by list order).
    assert item["series"] == "17.0"


def test_select_instance_profile_none_preserves_original_behavior():
    """profile=None is the default and must not break callers that pass no profile."""
    items = [{"series": "17.0", "db_name": "odoo_17"}]
    item, defaulted = io.select_instance(items, "17.0", profile=None)
    assert item is not None
    assert item["db_name"] == "odoo_17"


# ---------------------------------------------------------------------------
# _cmd_read emits INST_PROFILE and INST_KEY
# ---------------------------------------------------------------------------

def _run_read(toml_path: Path, *extra_args) -> dict:
    """Run `instances_io.py read <toml> [args...]` and parse emitted KEY=VALUE."""
    result = subprocess.run(
        [sys.executable, str(INSTANCES_IO), "read", str(toml_path), *extra_args],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        f"instances_io.py read exited {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    out = {}
    for line in result.stdout.splitlines():
        if "=" not in line:
            continue
        key, _, raw = line.partition("=")
        vals = shlex.split(raw)
        out[key] = vals[0] if vals else ""
    return out


def _make_toml(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "instances.toml"
    p.write_text(content, encoding="utf-8")
    return p


def test_cmd_read_emits_inst_profile_empty_for_plain_instance(tmp_path):
    toml = _make_toml(tmp_path, textwrap.dedent("""\
        [[instance]]
        series = "17.0"
        db_name = "odoo_17"
        http_port = 8069
        db_host = "localhost"
        db_user = "odoo"
        run_mode = "source"
        addons_path = ["/fake/addons"]
    """))
    out = _run_read(toml, "17.0")
    assert "INST_PROFILE" in out, "INST_PROFILE must be emitted"
    assert out["INST_PROFILE"] == "", f"Expected empty profile, got {out['INST_PROFILE']!r}"


def test_cmd_read_emits_inst_key_equals_series_for_plain_instance(tmp_path):
    toml = _make_toml(tmp_path, textwrap.dedent("""\
        [[instance]]
        series = "17.0"
        db_name = "odoo_17"
        http_port = 8069
        db_host = "localhost"
        db_user = "odoo"
        run_mode = "source"
        addons_path = ["/fake/addons"]
    """))
    out = _run_read(toml, "17.0")
    assert "INST_KEY" in out, "INST_KEY must be emitted"
    assert out["INST_KEY"] == "17.0", f"Expected INST_KEY='17.0', got {out['INST_KEY']!r}"


def test_cmd_read_emits_inst_profile_for_profiled_instance(tmp_path):
    toml = _make_toml(tmp_path, textwrap.dedent("""\
        [[instance]]
        series = "17.0"
        profile = "minimal_17"
        db_name = "odoo_minimal"
        http_port = 8069
        db_host = "localhost"
        db_user = "odoo"
        run_mode = "source"
        addons_path = ["/fake/addons"]
    """))
    out = _run_read(toml, "17.0", "minimal_17")
    assert out.get("INST_PROFILE") == "minimal_17", (
        f"Expected INST_PROFILE='minimal_17', got {out.get('INST_PROFILE')!r}"
    )
    assert out.get("INST_KEY") == "17.0:minimal_17", (
        f"Expected INST_KEY='17.0:minimal_17', got {out.get('INST_KEY')!r}"
    )


def test_cmd_read_profile_arg_selects_correct_item_among_two(tmp_path):
    """With two [[instance]] blocks of the same series but different profile,
    the third CLI arg [profile] must select the right one."""
    toml = _make_toml(tmp_path, textwrap.dedent("""\
        [[instance]]
        series = "17.0"
        profile = "minimal_17"
        db_name = "odoo_minimal"
        http_port = 8069
        db_host = "localhost"
        db_user = "odoo"
        run_mode = "source"
        addons_path = ["/fake/addons"]

        [[instance]]
        series = "17.0"
        profile = "full_17"
        db_name = "odoo_full"
        http_port = 8079
        db_host = "localhost"
        db_user = "odoo"
        run_mode = "source"
        addons_path = ["/fake/addons"]
    """))
    # Select minimal_17
    out_min = _run_read(toml, "17.0", "minimal_17")
    assert out_min["INST_DB_NAME"] == "odoo_minimal", (
        f"Expected odoo_minimal but got {out_min['INST_DB_NAME']!r}"
    )
    assert out_min["INST_PROFILE"] == "minimal_17"
    assert out_min["INST_KEY"] == "17.0:minimal_17"

    # Select full_17
    out_full = _run_read(toml, "17.0", "full_17")
    assert out_full["INST_DB_NAME"] == "odoo_full", (
        f"Expected odoo_full but got {out_full['INST_DB_NAME']!r}"
    )
    assert out_full["INST_PROFILE"] == "full_17"
    assert out_full["INST_KEY"] == "17.0:full_17"
