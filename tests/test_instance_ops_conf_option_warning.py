"""Odoo's unknown-option warning for a key the run itself passed is not a test warning."""

import textwrap

from test_instance_ops_script import (
    _base_env, _make_fake_odoo_bin, _make_fake_python, _run, requires_bash,
)

SUMMARY = (
    "2026-01-01 00:00:00,000 1 INFO testdb odoo.tests.result: "
    "0 failed, 0 error(s) of 3 tests when loading database 'testdb'"
)


def _unknown(key: str) -> str:
    return (
        f"2026-01-01 00:00:00,000 1 WARNING ? odoo.tools.config: unknown option '{key}' "
        "in the config file at /tmp/x.conf, option stored as-is, without parsing"
    )


def _run_with(tmp_path, *log_lines: str):
    out = "\n".join(f'echo "{l}"' for l in (*log_lines, SUMMARY))
    fake_bin = _make_fake_odoo_bin(tmp_path, exit_code=0, extra_output=textwrap.dedent(out))
    fake_py = _make_fake_python(tmp_path, odoo_bin_path=fake_bin)
    (tmp_path / "addons").mkdir()
    env = _base_env(tmp_path)
    env["ODOO_BIN"] = str(fake_bin)
    return _run("test", "--db", "testdb", "--python", str(fake_py),
                "--addons", str(tmp_path / "addons"), "--modules", "sale",
                "--conf-option", "modules_to_check_quality=sale", env=env)


@requires_bash
def test_an_unknown_option_warning_for_a_key_the_run_passed_is_not_counted(tmp_path):
    res = _run_with(tmp_path, _unknown("modules_to_check_quality"))
    assert "TEST_WARNING=0" in res.stdout, res.stdout
    assert "TEST_RESULT=passed" in res.stdout, res.stdout


@requires_bash
def test_an_unknown_option_warning_for_another_key_is_counted(tmp_path):
    res = _run_with(tmp_path, _unknown("some_other_key"))
    assert "TEST_WARNING=1" in res.stdout, res.stdout


@requires_bash
def test_an_ordinary_warning_is_still_counted_beside_the_passed_key_warning(tmp_path):
    res = _run_with(
        tmp_path, _unknown("modules_to_check_quality"),
        "2026-01-01 00:00:00,000 1 WARNING testdb odoo.modules.loading: something else",
    )
    assert "TEST_WARNING=1" in res.stdout, res.stdout
