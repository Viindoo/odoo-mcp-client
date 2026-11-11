"""The serial set in `tests/conftest.py` (`SERIAL_TESTS`) names only tests that exist.

`make test` runs the unmarked tests in parallel and the marked ones alone afterwards. An entry
that matches nothing - a test renamed or deleted since it was listed - protects nothing and hides
that the renamed test now runs under load, so a stale entry fails here.
"""
from __future__ import annotations

import subprocess
import sys
from fnmatch import fnmatchcase
from pathlib import Path

from conftest import SERIAL_TESTS

ROOT = Path(__file__).resolve().parent.parent


def test_every_serial_set_entry_matches_a_collected_test():
    out = subprocess.run(
        [sys.executable, "-m", "pytest", "tests", "--collect-only", "-q", "-p", "no:cacheprovider"],
        cwd=ROOT, capture_output=True, text=True, timeout=300,
    ).stdout
    collected = [line for line in out.splitlines() if line.startswith("tests/") and "::" in line]
    assert collected, "collection printed no test ids:\n" + out[-2000:]
    stale = [p for p in SERIAL_TESTS if not any(fnmatchcase(node, p) for node in collected)]
    assert not stale, f"serial-set entries that match no collected test (fix or remove them): {stale}"
