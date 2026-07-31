"""Cross-language parity: the Python addons_path SSOT (scripts/lib/instances_io.py's
join_addons_path/split_addons_path) and its bash mirror (scripts/lib/resolve_instances.sh's
_addons_path_to_array) must agree on the SAME multi-entry round trip.

Business rule protected: Odoo's --addons-path CLI flag and its addons_path config-file
key are COMMA-separated, uniformly across every indexed series (verified via OSM
cli_help on 8.0/17.0/19.0). This repo has at least one Python producer (instances_io.py)
and five shell consumers; if the two languages ever disagree on the separator, a
2+-entry addons_path silently breaks odoo-bin resolution. This is the one test that
proves the two homes actually agree with EACH OTHER, not just that each looks correct
in isolation - the exact class of test that would have caught allocator.py's
producer-side flip to comma leaving 55-instance-ops.sh's consumer-side IFS=':' stranded
on colon for weeks.

CPU-only: no PostgreSQL, no Odoo, no network.
"""
import importlib.util
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "lib"
INSTANCES_IO = LIB / "instances_io.py"
RESOLVE_INSTANCES_SH = LIB / "resolve_instances.sh"

requires_bash = pytest.mark.skipif(
    shutil.which("bash") is None, reason="bash not available"
)


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


io = _load_module("instances_io", INSTANCES_IO)

# A path with a space is included deliberately - the join/split round trip must
# survive a non-trivial directory name, not just simple slash-only paths.
_THREE_ENTRIES = ["/a/b", "/c d", "/e-f"]


def test_join_addons_path_produces_odoos_own_comma_wire_format():
    """join_addons_path must comma-join with no injected whitespace - the exact
    syntax Odoo's own --addons-path/addons_path parser expects."""
    assert io.join_addons_path(_THREE_ENTRIES) == "/a/b,/c d,/e-f"


def test_split_addons_path_reverses_join_addons_path():
    """split_addons_path(join_addons_path(paths)) must return the original list -
    the round trip a caller relies on when re-parsing its own emitted value."""
    joined = io.join_addons_path(_THREE_ENTRIES)
    assert io.split_addons_path(joined) == _THREE_ENTRIES


def test_split_addons_path_tolerates_a_legacy_colon_joined_value():
    """A stale colon-joined caller must degrade gracefully (never silently
    mis-split into one bogus entry) - this is what makes a leftover legacy
    producer safe to migrate incrementally instead of a flag-day cutover."""
    assert io.split_addons_path("/a/b:/c/d") == ["/a/b", "/c/d"]


@requires_bash
def test_python_join_and_bash_split_round_trip_the_same_three_entry_value():
    """The Python join and the bash split (_addons_path_to_array) must agree on
    the SAME value. Fails if the two homes' separators (or their tolerance for
    a legacy colon) ever drift apart from each other."""
    joined = io.join_addons_path(_THREE_ENTRIES)
    script = textwrap.dedent("""\
        set -euo pipefail
        source "$1"
        _addons_path_to_array arr "$2"
        printf '%s\\n' "${arr[@]}"
    """)
    result = subprocess.run(
        ["bash", "-c", script, "bash", str(RESOLVE_INSTANCES_SH), joined],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        f"bash side failed (rc={result.returncode}):\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert result.stdout.splitlines() == _THREE_ENTRIES, (
        f"bash _addons_path_to_array did not reproduce the original list.\n"
        f"joined value: {joined!r}\ngot: {result.stdout.splitlines()!r}"
    )
