"""Behavioral + contract tests for the browser-deps setup step.

`scripts/setup-steps/20-browser-deps.sh` installs the Playwright Chromium
browser AND, on apt-based Linux, its shared system libraries. The business
rules this step must protect (and which previously broke on current Ubuntu):

  - Playwright is PINNED (>= the first release that supports current Ubuntu),
    never resolved loosely from whatever sits in the local npx cache.
  - On apt-based Linux the system libraries are installed too - automatically
    only when passwordless sudo exists, otherwise the EXACT manual command is
    printed (the script never runs sudo silently).
  - macOS / Windows / non-apt Linux take a binary-only path and never fail on
    the apt-specific machinery.

The apt/sudo behavior is exercised with a stub PATH so the test is offline and
deterministic on any host (it does NOT touch the network or the real machine's
package state). Stdlib + bash only, so it runs wherever pytest + bash do.
"""
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = (
    ROOT
    / "plugins"
    / "odoo-ai-agents"
    / "scripts"
    / "setup-steps"
    / "20-browser-deps.sh"
)

PIN = "1.61.0"  # default PLAYWRIGHT_PIN; the floor that supports current Ubuntu

requires_bash = pytest.mark.skipif(
    shutil.which("bash") is None, reason="bash not available"
)


@pytest.fixture(scope="module")
def script_text():
    assert SCRIPT.is_file(), f"missing setup step: {SCRIPT}"
    return SCRIPT.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# contract: the pin is real and not accidentally dropped
# ---------------------------------------------------------------------------
def test_playwright_version_is_pinned(script_text):
    assert "PLAYWRIGHT_PIN" in script_text, "pin must be an env-overridable var"
    assert PIN in script_text, f"default pin {PIN} must be present"
    assert 'playwright@${PW_PIN}' in script_text, "installs must use the pinned var"


def test_no_unpinned_playwright_install(script_text):
    # A bare `npx -y playwright install` (no @version) is the regression we are
    # guarding against - it resolves to whatever the local cache holds.
    assert not re.search(r"npx\s+-y\s+playwright\s+install", script_text), (
        "found an unpinned `npx -y playwright install` - every call must pin "
        "playwright@${PW_PIN}"
    )


def test_os_guard_present(script_text):
    # Branches for the non-apt platforms + the apt-specific system-deps path.
    assert "Darwin" in script_text
    assert "apt-get" in script_text
    assert "install-deps" in script_text
    assert "_is_apt_linux" in script_text


# ---------------------------------------------------------------------------
# contract: subcommands behave
# ---------------------------------------------------------------------------
@requires_bash
def test_describe_is_nonblank():
    res = subprocess.run(
        ["bash", str(SCRIPT), "describe"],
        capture_output=True, text=True,
    )
    assert res.returncode == 0
    assert res.stdout.strip(), "describe must print a one-liner"


@requires_bash
def test_check_does_not_crash():
    # check legitimately returns 0 (all present) or 1 (something missing); it
    # must never crash with a usage/other error code.
    res = subprocess.run(
        ["bash", str(SCRIPT), "check"],
        capture_output=True, text=True,
    )
    assert res.returncode in (0, 1), res.stderr


@requires_bash
def test_unknown_subcommand_is_usage_error():
    res = subprocess.run(
        ["bash", str(SCRIPT), "definitely-not-a-subcommand"],
        capture_output=True, text=True,
    )
    assert res.returncode == 2


# ---------------------------------------------------------------------------
# behavior: apt-based Linux, stubbed PATH (offline + deterministic)
# ---------------------------------------------------------------------------
def _write_stub(path: Path, body: str):
    path.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8")
    path.chmod(0o755)


# Real ldconfig -p output format for the chromium libs the probe checks. Used
# to prove the probe matches actual SONAMES (e.g. package libasound2 ships
# libasound.so.2 - a "libasound2" substring would wrongly report it missing).
#
# The real sonames come FIRST, then thousands of padding lines: a real
# `ldconfig -p` lists ~1-2k libs. This size matters - a `printf | grep -q`
# implementation closes the pipe on the early match and printf dies with
# SIGPIPE, which under `set -o pipefail` falsely reports the lib missing. A
# small stub would NOT reproduce that, so we pad to guard the pipefail-safe
# implementation against regression.
_REAL_SONAMES = ("libnss3.so", "libnspr4.so", "libatk-1.0.so.0",
                 "libgbm.so.1", "libasound.so.2")
_LDCONFIG_PRESENT = "\n".join(
    [f"\t{so} (libc6,x86-64) => /usr/lib/x86_64-linux-gnu/{so}" for so in _REAL_SONAMES]
    + [f"\tlibpad{i}.so.0 (libc6,x86-64) => /usr/lib/x86_64-linux-gnu/libpad{i}.so.0"
       for i in range(5000)]
)


def _apt_stub_bin(
    tmp_path: Path, *, sudo_nopasswd: bool, sudo_log: Path | None = None,
    libs_present: bool = False, install_deps_fails: bool = False,
):
    """Build a stub bin dir that makes the script believe it is on apt-based
    Linux with chromium already downloaded. `libs_present` toggles whether the
    chromium system libraries look installed (ldconfig reports them)."""
    bind = tmp_path / "bin"
    bind.mkdir()

    # Reports Linux for `uname -s`.
    _write_stub(bind / "uname", 'if [ "$1" = "-s" ]; then echo Linux; else echo Linux; fi\n')
    # Node >= 20 for both probes (`node -v` and `node -e <major>`).
    _write_stub(bind / "node", 'case "$1" in -v) echo v22.0.0 ;; -e) printf 22 ;; esac\n')
    # apt-get just needs to exist for `command -v apt-get`.
    _write_stub(bind / "apt-get", "exit 0\n")
    # ldconfig -p: either the real-format library listing, or nothing (missing).
    if libs_present:
        _write_stub(bind / "ldconfig", f"cat <<'EOF'\n{_LDCONFIG_PRESENT}\nEOF\n")
    else:
        _write_stub(bind / "ldconfig", "exit 0\n")
    # npx: chromium already installed (dry-run), install-deps no-op. No network.
    _write_stub(
        bind / "npx",
        'args="$*"\n'
        'case "$args" in\n'
        '  *--dry-run*) echo "chromium is already installed" ; exit 0 ;;\n'
        '  *install-deps*) exit 0 ;;\n'
        '  *) exit 0 ;;\n'
        'esac\n',
    )
    # ffmpeg present so its guidance does not muddy assertions.
    _write_stub(bind / "ffmpeg", "exit 0\n")

    if sudo_nopasswd:
        log = str(sudo_log) if sudo_log else "/dev/null"
        # When install_deps_fails, the recorded install-deps invocation exits
        # non-zero so the test can assert the script surfaces the failure.
        fail_line = 'case "$*" in *install-deps*) exit 7 ;; esac\n' if install_deps_fails else ""
        _write_stub(
            bind / "sudo",
            '# `sudo -n true` -> success (passwordless available)\n'
            'if [ "$1" = "-n" ] && [ "$2" = "true" ]; then exit 0; fi\n'
            f'echo "$@" >> "{log}"\n'
            f'{fail_line}'
            "exit 0\n",
        )
    else:
        _write_stub(
            bind / "sudo",
            '# `sudo -n true` -> failure (no passwordless sudo)\n'
            'if [ "$1" = "-n" ] && [ "$2" = "true" ]; then exit 1; fi\n'
            "exit 1\n",
        )
    return bind


def _run_apply(bind: Path):
    env = dict(os.environ)
    # Stubs first; keep the rest of PATH for grep/printf/sed/etc.
    env["PATH"] = f"{bind}:{env.get('PATH', '')}"
    return subprocess.run(
        ["bash", str(SCRIPT), "apply"],
        capture_output=True, text=True, env=env,
    )


@requires_bash
def test_apply_prints_manual_guidance_without_passwordless_sudo(tmp_path):
    bind = _apt_stub_bin(tmp_path, sudo_nopasswd=False)
    res = _run_apply(bind)
    out = res.stdout + res.stderr
    # Must surface the exact manual command, and must NOT claim it installed them.
    assert f"sudo npx -y playwright@{PIN} install-deps chromium" in out, out
    assert "system libraries installed" not in out


@requires_bash
def test_apply_auto_installs_system_deps_with_passwordless_sudo(tmp_path):
    sudo_log = tmp_path / "sudo.log"
    bind = _apt_stub_bin(tmp_path, sudo_nopasswd=True, sudo_log=sudo_log)
    res = _run_apply(bind)
    out = res.stdout + res.stderr
    # The script invoked sudo to run playwright install-deps for the libs.
    assert sudo_log.is_file(), out
    logged = sudo_log.read_text(encoding="utf-8")
    assert "install-deps" in logged, logged
    assert f"playwright@{PIN}" in logged, logged


def _macos_stub_bin(tmp_path: Path, *, sudo_log: Path, apt_log: Path):
    """Stub bin dir that makes the script believe it runs on macOS, with apt-get
    and sudo present-but-recording so the test can prove they are NEVER called on
    the macOS path (no system-package machinery off apt-based Linux)."""
    bind = tmp_path / "bin"
    bind.mkdir()
    _write_stub(bind / "uname", "echo Darwin\n")
    _write_stub(bind / "node", 'case "$1" in -v) echo v22.0.0 ;; -e) printf 22 ;; esac\n')
    _write_stub(
        bind / "npx",
        'case "$*" in *--dry-run*) echo "chromium is already installed" ;; esac\nexit 0\n',
    )
    _write_stub(bind / "ffmpeg", "exit 0\n")
    # apt-get / sudo exist but must stay untouched on macOS; they log if invoked.
    _write_stub(bind / "apt-get", f'echo "$@" >> "{apt_log}"\nexit 0\n')
    _write_stub(bind / "sudo", f'echo "$@" >> "{sudo_log}"\nexit 0\n')
    return bind


@requires_bash
def test_apply_macos_path_never_touches_apt_or_sudo(tmp_path):
    # macOS users are first-class: the apply path must install the browser binary
    # and skip ALL apt/sudo system-deps machinery (those exist only on apt Linux).
    sudo_log, apt_log = tmp_path / "sudo.log", tmp_path / "apt.log"
    bind = _macos_stub_bin(tmp_path, sudo_log=sudo_log, apt_log=apt_log)
    res = _run_apply(bind)
    out = res.stdout + res.stderr
    assert res.returncode == 0, out
    assert "install-deps" not in out, out
    assert "system librar" not in out, out  # neither "present" nor "missing" path
    assert not sudo_log.exists(), f"sudo must not run on macOS: {sudo_log.read_text()}"
    assert not apt_log.exists(), f"apt-get must not run on macOS: {apt_log.read_text()}"


@requires_bash
def test_apply_fails_when_auto_system_deps_install_fails(tmp_path):
    # When we HAVE passwordless sudo and actively run install-deps, a failure is
    # a real error and must fail the step - never swallowed as a warning.
    sudo_log = tmp_path / "sudo.log"
    bind = _apt_stub_bin(
        tmp_path, sudo_nopasswd=True, sudo_log=sudo_log, install_deps_fails=True
    )
    res = _run_apply(bind)
    out = res.stdout + res.stderr
    assert res.returncode != 0, out
    assert "Failed to install Chromium system libraries" in out, out


@requires_bash
def test_apply_skips_system_deps_when_libs_already_present(tmp_path):
    # When ldconfig reports the real chromium SONAMEs, the probe must recognise
    # them and skip - no manual guidance, no sudo. This guards the soname match
    # (package libasound2 -> libasound.so.2) against a substring regression.
    sudo_log = tmp_path / "sudo.log"
    bind = _apt_stub_bin(
        tmp_path, sudo_nopasswd=True, sudo_log=sudo_log, libs_present=True
    )
    res = _run_apply(bind)
    out = res.stdout + res.stderr
    assert "system libraries present - skip" in out, out
    assert not sudo_log.exists() or "install-deps" not in sudo_log.read_text(), out
