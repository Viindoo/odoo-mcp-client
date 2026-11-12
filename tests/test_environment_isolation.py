"""The suite's result does not depend on the variables a developer's shell exports.

The production code reads a configured value (a speech key, a YouTube credential), the database
password and the plugin's own overrides from environment variables of fixed names. A test that
builds a child environment from `os.environ`, or runs production code in this process, would hand
a developer's own value to it, and a test about a MISSING value would fail on that developer's
machine only. `tests/conftest.py` starts the suite without those variables; these tests pin that
the list of names covers every configured value and that the start-up scrub is in effect.
"""
import os
import subprocess
import sys
from pathlib import Path

from odoo_local_mcp_harness import (
    LIB_DIR, MCP_DIR, ambient_value_names, import_package, scrub_ambient_values,
)


def _names_production_reads() -> set:
    import_package()
    for directory in (MCP_DIR, LIB_DIR):
        if str(directory) not in sys.path:
            sys.path.insert(0, str(directory))
    from odoo_media import values
    import speech_client
    import upgrade_values
    import youtube_upload
    return (set(values.OPTION) | {speech_client.VALUE_ENV, youtube_upload.CLIENT_ID_ENV,
                                  youtube_upload.CLIENT_SECRET_ENV} | set(youtube_upload.TOKEN_ENV.values())
            | set(upgrade_values.YOUTUBE_LEGACY_DEFAULTS.values()))


def test_every_variable_name_production_reads_for_a_configured_value_is_scrubbed():
    assert _names_production_reads() <= ambient_value_names()


def test_scrubbing_removes_the_ambient_values_and_keeps_everything_else():
    environ = {name: "value" for name in ambient_value_names()}
    environ.update({"PATH": "/usr/bin", "HOME": "/home/someone"})
    removed = scrub_ambient_values(environ)
    assert sorted(removed) == sorted(ambient_value_names())
    assert environ == {"PATH": "/usr/bin", "HOME": "/home/someone"}


def test_the_suite_starts_without_an_ambient_value_variable():
    assert not ambient_value_names() & set(os.environ)


def test_a_value_exported_by_the_developer_never_reaches_the_suite():
    env = dict(os.environ, **{name: "exported-by-the-developer" for name in ambient_value_names()})
    probe = "%s::test_the_suite_starts_without_an_ambient_value_variable" % Path(__file__)
    proc = subprocess.run([sys.executable, "-m", "pytest", probe, "-q", "-p", "no:cacheprovider"],
                          capture_output=True, text=True, env=env, cwd=str(Path(__file__).resolve().parent))
    assert proc.returncode == 0, proc.stdout + proc.stderr
