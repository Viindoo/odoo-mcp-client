"""Behavioral + contract tests for the browser-deps setup step.

`scripts/setup-steps/20-browser-deps.sh` pre-installs, ON DISK ONLY, the 3
pinned browser MCP server npm packages (chrome-devtools-mcp, @playwright/mcp,
@mcpware/pagecast - see `scripts/lib/browser-mcp-servers.sh`), the Playwright
Chromium browser, and, on apt-based Linux, Chromium's shared system libraries.
The business rules this step must protect:

  - INSTALL vs REGISTER/RUN separation: this step warms npm's cache (and the
    Playwright browser cache) so a later real spawn has no download latency,
    but it NEVER runs `claude mcp add` (or any registration command) and NEVER
    executes/launches a downloaded package - that stays the exclusive job of
    steps 10/12. Idle-RAM cost is zero because nothing is registered here.
  - The 3 MCP packages are pre-installed via a throwaway `npm install
    --ignore-scripts` (never `npx`, which would execute the package) and the
    check is idempotent (`--offline --dry-run` - a cache hit is a no-op skip).
  - Playwright is PINNED (>= the first release that supports current Ubuntu),
    never resolved loosely from whatever sits in the local npx cache.
  - On apt-based Linux the system libraries are installed too - automatically
    only when passwordless sudo exists, otherwise the EXACT manual command is
    printed (the script never runs sudo silently).
  - macOS / Windows / non-apt Linux take a binary-only path and never fail on
    the apt-specific machinery.

The apt/sudo/npm behavior is exercised with a stub PATH so the test is offline
and deterministic on any host (it does NOT touch the network or the real
machine's package state). Stdlib + bash only, so it runs wherever pytest +
bash do.
"""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from conftest import farm_path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = (
    ROOT
    / "plugins"
    / "odoo-ai-agents"
    / "scripts"
    / "setup-steps"
    / "20-browser-deps.sh"
)
LIB = (
    ROOT
    / "plugins"
    / "odoo-ai-agents"
    / "scripts"
    / "lib"
    / "browser-mcp-servers.sh"
)

def _ssot_value(cmd: str) -> str:
    """One value from the launch SSOT (scripts/lib/browser_mcp_servers.py) - never hardcoded
    here, so a pin bump needs no test edit."""
    res = subprocess.run([sys.executable, str(LIB.parent / "browser_mcp_servers.py"), cmd],
                         capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    return res.stdout.strip()


# The playwright whose Chromium pagecast launches - and this step installs.
PIN = _ssot_value("browser-playwright-version")

requires_bash = pytest.mark.skipif(
    shutil.which("bash") is None, reason="bash not available"
)


def _mcp_pin(var: str) -> str:
    """Read one pin var out of the shared SSOT lib (never hardcode the pinned
    package strings here - that would duplicate the SSOT and drift on bump)."""
    assert LIB.is_file(), f"missing SSOT lib: {LIB}"
    res = subprocess.run(
        ["bash", "-c", f'. "{LIB}"; printf "%s" "${{{var}}}"'],
        capture_output=True, text=True,
    )
    assert res.returncode == 0, res.stderr
    return res.stdout


MCP_PKG_PINS = [
    _mcp_pin("BROWSER_MCP_CHROME_PIN"),
    _mcp_pin("BROWSER_MCP_PLAYWRIGHT_PIN"),
    _mcp_pin("BROWSER_MCP_PAGECAST_PIN"),
]
# The narrated-video recorder's own copy of the playwright library, at the Chromium pin.
RECORDER_LIB_PIN = "playwright@" + _mcp_pin("BROWSER_MCP_BROWSER_PLAYWRIGHT_VERSION")


# ---------------------------------------------------------------------------
# contract: the pin is real and not accidentally dropped
# ---------------------------------------------------------------------------
def test_playwright_pin_is_an_exact_release():
    assert re.fullmatch(r"\d+\.\d+\.\d+", PIN), f"not an exact release: {PIN!r}"


def _code_commands():
    """The step's executable commands: comment lines dropped, backslash continuations joined."""
    lines = [ln for ln in SCRIPT.read_text(encoding="utf-8").splitlines()
             if not ln.strip().startswith("#")]
    return re.sub(r"\\\n\s*", " ", "\n".join(lines)).splitlines()


def test_every_npm_install_of_the_step_skips_lifecycle_scripts():
    """Supply chain: the step only pre-installs packages it never runs, so no install may execute
    a dependency's pre/postinstall script."""
    installs = [c for c in _code_commands() if re.search(r"\bnpm\s+install\b", c)]
    assert installs, "the step no longer runs `npm install` - this guard scans nothing"
    assert [c.strip() for c in installs if "--ignore-scripts" not in c] == []


def test_every_playwright_install_of_the_step_is_version_pinned():
    """An unpinned `playwright install` resolves to whatever the local cache holds."""
    installs = [c for c in _code_commands()
                if re.search(r"\bplaywright\b", c) and re.search(r"\binstall(-deps)?\b", c)
                and re.search(r"\bnpx\b|\bnpm\s+install\b", c)]
    assert installs, "the step no longer installs playwright - this guard scans nothing"
    assert [c.strip() for c in installs if "playwright@${PW_PIN}" not in c] == []


def _pagecast_launch(env):
    res = subprocess.run([sys.executable, str(LIB.parent / "browser_mcp_servers.py"), "spec",
                          "pagecast"], capture_output=True, text=True, env=env, check=True)
    return json.loads(res.stdout)["args"]


def _chromium_probe_pin(tmp_path, env):
    """Run the step's `check` against stub node/npm/npx and return the playwright version the
    Chromium probe asks npx for."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log = tmp_path / "npx.log"
    stubs = {"node": "#!/bin/sh\necho 22\n", "npm": "#!/bin/sh\nexit 0\n",
             "npx": f'#!/bin/sh\necho "$@" >> "{log}"\necho "chromium is already installed"\n'}
    for name, body in stubs.items():
        (bin_dir / name).write_text(body, encoding="utf-8")
        (bin_dir / name).chmod(0o755)
    run_env = dict(env, PATH=f"{bin_dir}{os.pathsep}{env.get('PATH', '')}",
                   ODOO_AI_HOME=str(tmp_path / "state"))
    subprocess.run(["bash", str(SCRIPT), "check"], env=run_env, capture_output=True, text=True,
                   timeout=120)
    calls = [line.split() for line in log.read_text().splitlines() if "install" in line]
    pins = {a.split("@", 1)[1] for c in calls for a in c if a.startswith("playwright@")}
    assert len(pins) == 1, calls
    return pins.pop()


@requires_bash
@pytest.mark.parametrize("override", [None, "1.60.0"])
def test_the_chromium_installed_is_the_one_pagecast_launches(tmp_path, override):
    """pagecast runs the Chromium bundled with the `playwright` it resolves. Left to its range
    (^1.52.0) that is whatever release is newest on the day, so the launch pins playwright beside
    pagecast and this step installs the Chromium of that same version - with or without the
    PLAYWRIGHT_PIN override."""
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("BROWSER_MCP_") and k != "PLAYWRIGHT_PIN"}
    if override:
        env["PLAYWRIGHT_PIN"] = override
    args = _pagecast_launch(env)
    launched = [a.split("@", 1)[1] for a in args if a.startswith("playwright@")]
    assert len(launched) == 1, args
    i = args.index("playwright@" + launched[0])
    assert args[i - 1] == "-p" and "pagecast" in args[i + 1:], args
    assert _chromium_probe_pin(tmp_path, env) == launched[0]
    if override:
        assert launched[0] == override


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
def test_unknown_subcommand_is_usage_error():
    res = subprocess.run(
        ["bash", str(SCRIPT), "definitely-not-a-subcommand"],
        capture_output=True, text=True,
    )
    assert res.returncode == 2


# ---------------------------------------------------------------------------
# behavior: the step run against stub PATHs (offline + deterministic). Each scenario runs the
# step ONCE (a bash + python startup per launch, several per scenario); the tests below read it.
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


def _pw_dry_run(tmp_path: Path, *, complete: bool = True) -> str:
    """What `playwright install chromium --dry-run` prints: an `Install location:` per browser it
    would install (revision-exact dirs). `complete` writes Playwright's INSTALLATION_COMPLETE
    marker into each, as a finished download does."""
    cache = tmp_path / "pw-cache"
    lines = []
    for name in ("chromium-9999", "chromium_headless_shell-9999", "ffmpeg-9999"):
        d = cache / name
        d.mkdir(parents=True, exist_ok=True)
        if complete:
            (d / "INSTALLATION_COMPLETE").write_text("", encoding="utf-8")
        lines += [f"Browser {name}", f"  Install location:    {d}", "  Download url: https://x", ""]
    return "\n".join(lines)


def _dry_run_case(tmp_path: Path, *, complete: bool = True) -> str:
    """A bash `case` arm answering the dry-run with _pw_dry_run's listing."""
    listing = tmp_path / "dry-run.txt"
    listing.write_text(_pw_dry_run(tmp_path, complete=complete), encoding="utf-8")
    return f'  *--dry-run*) cat "{listing}" ; exit 0 ;;\n'


def _write_npm_stub(bind: Path, *, cached=(), fail=(), log: Path | None = None):
    """Stub `npm` for the MCP-package pre-install probe/apply calls this step
    makes, mirroring real npm's `--offline` semantics we rely on: the check
    call (`install --offline --dry-run ...`) succeeds ONLY for a spec listed
    in `cached`; the real install call (no `--offline`) succeeds unless the
    spec is listed in `fail`. Every invocation is appended to `log` (if given)
    so a test can assert exactly which specs were (not) (re)installed."""
    cached_joined = " ".join(cached)
    fail_joined = " ".join(fail)
    log_line = f'printf "%s\\n" "$*" >> "{log}"\n' if log is not None else ""
    body = (
        f'{log_line}'
        'spec="${@: -1}"\n'
        'case " $* " in\n'
        '  *" --offline "*)\n'
        f'    case " {cached_joined} " in\n'
        '      *" $spec "*) exit 0 ;;\n'
        '      *) exit 1 ;;\n'
        '    esac\n'
        '    ;;\n'
        '  *)\n'
        f'    case " {fail_joined} " in\n'
        '      *" $spec "*) exit 1 ;;\n'
        '      *) exit 0 ;;\n'
        '    esac\n'
        '    ;;\n'
        'esac\n'
    )
    _write_stub(bind / "npm", body)


def _apt_stub_bin(
    tmp_path: Path, *, sudo_nopasswd: bool, sudo_log: Path | None = None,
    libs_present: bool = False, install_deps_fails: bool = False,
    mcp_cached: bool = True, npm_log: Path | None = None, chromium_complete: bool = True,
):
    """Build a stub bin dir that makes the script believe it is on apt-based
    Linux with chromium already downloaded. `libs_present` toggles whether the
    chromium system libraries look installed (ldconfig reports them).
    `mcp_cached` (default True, so unrelated tests stay offline/deterministic
    regardless of the real machine's npm cache state) toggles whether the 3
    pinned MCP packages report as already cached on disk."""
    bind = tmp_path / "bin"
    bind.mkdir()

    # Reports Linux for `uname -s`.
    _write_stub(bind / "uname", 'if [ "$1" = "-s" ]; then echo Linux; else echo Linux; fi\n')
    # Node >= 20 for both probes (`node -v` and `node -e <major>`).
    _write_stub(bind / "node", 'case "$1" in -v) echo v22.0.0 ;; -e) printf 22 ;; esac\n')
    # apt-get just needs to exist for `command -v apt-get`.
    _write_stub(bind / "apt-get", "exit 0\n")
    # npm: the 3 pinned MCP packages - cached (skip) or not (pre-install runs).
    _write_npm_stub(
        bind, cached=(MCP_PKG_PINS if mcp_cached else ()), log=npm_log,
    )
    # The recorder library under the state root: installed at the pin when everything is cached
    # (a re-run installs nothing), absent otherwise (apply installs it once).
    if mcp_cached:
        marker = tmp_path / "state" / "recorder" / "node_modules" / "playwright" / "package.json"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(
            json.dumps({"name": "playwright", "version": RECORDER_LIB_PIN.split("@")[-1]}),
            encoding="utf-8",
        )
    # ldconfig -p: either the real-format library listing, or nothing (missing).
    if libs_present:
        _write_stub(bind / "ldconfig", f"cat <<'EOF'\n{_LDCONFIG_PRESENT}\nEOF\n")
    else:
        _write_stub(bind / "ldconfig", "exit 0\n")
    # npx: the dry-run lists revision-exact install dirs (complete unless told otherwise); every
    # other call is logged and succeeds. No network.
    _write_stub(
        bind / "npx",
        f'echo "$*" >> "{tmp_path / "npx.log"}"\n'
        'args="$*"\n'
        'case "$args" in\n'
        + _dry_run_case(tmp_path, complete=chromium_complete) +
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
        'case "$*" in\n' + _dry_run_case(tmp_path) + 'esac\nexit 0\n',
    )
    # All 3 pinned MCP packages report cached - macOS path is not exercising
    # the pre-install branch here, this test is about apt/sudo isolation.
    _write_npm_stub(bind, cached=MCP_PKG_PINS)
    _write_stub(bind / "ffmpeg", "exit 0\n")
    # apt-get / sudo exist but must stay untouched on macOS; they log if invoked.
    _write_stub(bind / "apt-get", f'echo "$@" >> "{apt_log}"\nexit 0\n')
    _write_stub(bind / "sudo", f'echo "$@" >> "{sudo_log}"\nexit 0\n')
    return bind


# ---------------------------------------------------------------------------
# Google Chrome: chrome-devtools-mcp (puppeteer channel "chrome") and @playwright/mcp (channel
# "chrome") launch the INSTALLED Google Chrome from fixed locations and fail to start without it;
# Playwright's Chromium (installed above, for pagecast) does not satisfy them.
# ---------------------------------------------------------------------------
def _ssot_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("bms_for_chrome",
                                                  LIB.parent / "browser_mcp_servers.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("platform,environ,expected", [
    ("linux", {}, "/opt/google/chrome/chrome"),
    ("darwin", {}, "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
    ("win32", {"LOCALAPPDATA": "C:\\Users\\u\\AppData\\Local"},
     "C:\\Users\\u\\AppData\\Local\\Google\\Chrome\\Application\\chrome.exe"),
    ("win32", {"PROGRAMFILES": "E:\\Apps"}, "E:\\Apps\\Google\\Chrome\\Application\\chrome.exe"),
    ("win32", {}, "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"),
])
def test_chrome_is_found_where_the_browser_servers_look_for_it(platform, environ, expected):
    mod = _ssot_module()
    assert expected in mod.chrome_locations(environ, platform)
    assert mod.find_chrome(environ, platform, exists=lambda p: p == expected) == expected
    assert mod.find_chrome(environ, platform, exists=lambda p: False) is None


def test_a_chrome_on_path_elsewhere_does_not_count():
    """Neither server consults PATH: a google-chrome binary in /usr/local/bin starts nothing."""
    mod = _ssot_module()
    assert mod.find_chrome({}, "linux", exists=lambda p: p == "/usr/local/bin/google-chrome") is None


def _chrome_env(tmp_path: Path, present: bool) -> dict:
    """PYTHONPATH carrying a sitecustomize that makes every Chrome location exist (or not) for
    the step's python3 calls, whatever this host has installed."""
    site = tmp_path / "site-chrome"
    site.mkdir(exist_ok=True)
    (site / "sitecustomize.py").write_text(
        "import os.path\n"
        "_real = os.path.isfile\n"
        "def _isfile(p):\n"
        "    s = str(p)\n"
        "    if s.endswith(('/opt/google/chrome/chrome', 'MacOS/Google Chrome', 'chrome.exe')):\n"
        f"        return {present!r}\n"
        "    return _real(p)\n"
        "os.path.isfile = _isfile\n", encoding="utf-8")
    return {"PYTHONPATH": str(site)}


def _run_step(bind: Path, verb: str, extra: dict):
    env = dict(os.environ)
    env["PATH"] = f"{bind}:{env.get('PATH', '')}"
    env["ODOO_AI_HOME"] = str(bind.parent / "state")
    env.update(extra)
    return subprocess.run(["bash", str(SCRIPT), verb], capture_output=True, text=True, env=env,
                          timeout=120)


HOOK = SCRIPT.parent.parent.parent / "hooks" / "check-setup-deps.sh"


def _record(tmp_path):
    path = tmp_path / "state" / "runtime" / "browser-deps.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _hint(tmp_path, home=None):
    """Run the SessionStart probe against the step's state root; return its stderr."""
    env = dict(os.environ, ODOO_AI_HOME=str(tmp_path / "state"),
               HOME=str(home or tmp_path / "home"))
    env.pop("PLAYWRIGHT_PIN", None)
    res = subprocess.run(["bash", str(HOOK)], input="{}", env=env, capture_output=True,
                         text=True, timeout=60)
    assert res.returncode == 0
    return res.stderr


def _scenario(factory, name, verb, *, chrome=None, extra_env=None, macos=False, **stub):
    """Run the step once under a stub PATH. `chrome` forces Google Chrome present (True) or absent
    (False) for the step's python3 calls; None leaves the host's own answer."""
    tmp = factory.mktemp(name)
    sudo_log, npm_log, apt_log = tmp / "sudo.log", tmp / "npm.log", tmp / "apt.log"
    if macos:
        bind = _macos_stub_bin(tmp, sudo_log=sudo_log, apt_log=apt_log)
    else:
        bind = _apt_stub_bin(tmp, sudo_log=sudo_log, npm_log=npm_log, **stub)
    extra = dict(_chrome_env(tmp, present=chrome)) if chrome is not None else {}
    extra.update(extra_env or {})
    res = _run_step(bind, verb, extra)
    return SimpleNamespace(
        res=res, out=res.stdout + res.stderr, tmp=tmp, bind=bind, sudo_log=sudo_log,
        npm_log=npm_log, apt_log=apt_log, npx_log=tmp / "npx.log",
    )


def _lines(path: Path):
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def _real_installs(npm_log: Path):
    """The npm calls that installed something (the `--offline` ones only ask the cache)."""
    return [ln for ln in _lines(npm_log) if ln and "--offline" not in ln]


# --- apt Linux, nothing of Chromium's system libraries, no passwordless sudo -----------------
@pytest.fixture(scope="module")
def no_sudo(tmp_path_factory):
    return _scenario(tmp_path_factory, "no-sudo", "apply", chrome=False,
                     sudo_nopasswd=False, libs_present=False)


def test_apply_without_passwordless_sudo_prints_the_manual_commands_and_runs_no_sudo(no_sudo):
    assert no_sudo.res.returncode == 0, no_sudo.out
    # The exact commands a human must run - never run silently on their behalf.
    assert f"sudo npx -y playwright@{PIN} install-deps chromium" in no_sudo.out, no_sudo.out
    assert f"sudo npx -y playwright@{PIN} install chrome" in no_sudo.res.stderr, no_sudo.out


# --- apt Linux, passwordless sudo, libs missing, Chrome missing, everything cached -----------
@pytest.fixture(scope="module")
def sudo_libs_missing(tmp_path_factory):
    return _scenario(tmp_path_factory, "sudo-libs-missing", "apply", chrome=False,
                     sudo_nopasswd=True, libs_present=False, mcp_cached=True)


def test_apply_auto_installs_system_deps_and_chrome_with_passwordless_sudo(sudo_libs_missing):
    sc = sudo_libs_missing
    assert sc.res.returncode == 0, sc.out
    assert sc.sudo_log.is_file(), sc.out
    logged = _lines(sc.sudo_log)
    assert any("install-deps" in ln and f"playwright@{PIN}" in ln for ln in logged), logged
    assert any(f"playwright@{PIN} install chrome" in ln for ln in logged), logged
    # Every sudo-run playwright call is pinned: left unpinned it resolves to whatever sits in
    # the local cache.
    assert all(f"playwright@{PIN}" in ln for ln in logged if "install" in ln), logged


def test_apply_installs_nothing_for_packages_that_are_already_cached(sudo_libs_missing):
    """Idempotency: every pinned package already on disk -> no real `npm install` (no redundant
    downloads on a re-run), the recorder library included."""
    sc = sudo_libs_missing
    assert sc.res.returncode == 0, sc.out
    assert _real_installs(sc.npm_log) == []


# --- apt Linux, passwordless sudo, libs present, Chrome and Chromium present ------------------
@pytest.fixture(scope="module")
def everything_present(tmp_path_factory):
    return _scenario(tmp_path_factory, "present", "apply", chrome=True,
                     sudo_nopasswd=True, libs_present=True)


def test_apply_skips_system_deps_when_libs_already_present(everything_present):
    # The probe matches real SONAMES (package libasound2 ships libasound.so.2): no manual
    # guidance, no sudo install-deps. A substring match would wrongly report it missing.
    sc = everything_present
    assert sc.res.returncode == 0, sc.out
    assert "install-deps" not in sc.out and not any("install-deps" in ln for ln in _lines(sc.sudo_log))


@requires_bash
def test_a_verified_chromium_is_recorded_for_the_pinned_playwright_by_apply(everything_present):
    _assert_recorded(everything_present.tmp)


# --- apt Linux, the system libs install fails ----------------------------------------------
@requires_bash
def test_apply_fails_when_auto_system_deps_install_fails(tmp_path_factory):
    # With passwordless sudo the step actively runs install-deps; a failure is a real error and
    # must fail the step - never swallowed as a warning.
    sc = _scenario(tmp_path_factory, "deps-fail", "apply", chrome=True,
                   sudo_nopasswd=True, libs_present=False, install_deps_fails=True)
    assert sc.res.returncode != 0, sc.out


# --- pre-install of the 3 pinned MCP packages -------------------------------------------------
@pytest.fixture(scope="module")
def preinstall(tmp_path_factory):
    return _scenario(tmp_path_factory, "preinstall", "apply", chrome=True,
                     sudo_nopasswd=True, libs_present=True, mcp_cached=False)


@pytest.fixture(scope="module")
def preinstall_with_claude_on_path(tmp_path_factory):
    """The same pre-install, with a `claude` CLI on PATH that records every call."""
    tmp = tmp_path_factory.mktemp("preinstall-claude")
    bind = _apt_stub_bin(tmp, sudo_nopasswd=True, libs_present=True, mcp_cached=False,
                         npm_log=tmp / "npm.log")
    claude_log = tmp / "claude.log"
    _write_stub(bind / "claude", f'echo "$@" >> "{claude_log}"\nexit 0\n')
    res = _run_step(bind, "apply", _chrome_env(tmp, present=True))
    return SimpleNamespace(res=res, out=res.stdout + res.stderr, claude_log=claude_log,
                           npm_log=tmp / "npm.log", npx_log=tmp / "npx.log", tmp=tmp)


def test_apply_preinstalls_each_pinned_package_once_without_running_it(preinstall):
    sc = preinstall
    assert sc.res.returncode == 0, sc.out
    calls = _real_installs(sc.npm_log)
    for pin in MCP_PKG_PINS:
        installs = [ln for ln in calls if ln.rstrip().endswith(pin)]
        assert len(installs) == 1, f"expected exactly one real `npm install` for {pin}, got {installs}"
        # `npm install` never executes a package's bin, and --ignore-scripts keeps lifecycle
        # scripts of its dependency tree from running too.
        assert "--ignore-scripts" in installs[0], installs
    # The packages are never launched: npx (which would execute them) never sees one.
    assert not any(pin in ln for pin in MCP_PKG_PINS for ln in _lines(sc.npx_log)), _lines(sc.npx_log)


def test_apply_installs_the_recorder_library_once_under_the_state_root(preinstall):
    sc = preinstall
    recorder = [ln for ln in _real_installs(sc.npm_log) if ln.rstrip().endswith(RECORDER_LIB_PIN)]
    assert len(recorder) == 1, recorder
    assert f"--prefix {sc.tmp / 'state' / 'recorder'}" in recorder[0], recorder
    assert "--ignore-scripts" in recorder[0], recorder


def test_apply_never_registers_an_mcp_server(preinstall_with_claude_on_path):
    """Registering is steps 10/12's job: this step stays disk-only, so the `claude` CLI is never
    called even though one is on PATH."""
    sc = preinstall_with_claude_on_path
    assert sc.res.returncode == 0, sc.out
    assert _real_installs(sc.npm_log), "premise: the pre-install ran"
    assert not sc.claude_log.exists(), sc.claude_log.read_text()


@requires_bash
def test_apply_surfaces_mcp_preinstall_failure(tmp_path):
    # One package is neither cached nor installable (e.g. registry/network down) -> apply must
    # fail loud, never swallow the error.
    bind = _apt_stub_bin(tmp_path, sudo_nopasswd=True, libs_present=True, mcp_cached=False)
    # Re-write the npm stub so this one spec also fails the real install call.
    _write_npm_stub(bind, cached=(), fail=(MCP_PKG_PINS[0],))
    res = _run_step(bind, "apply", _chrome_env(tmp_path, present=True))
    assert res.returncode != 0, res.stdout + res.stderr


@requires_bash
def test_check_fails_when_an_mcp_package_is_not_cached(tmp_path):
    # Everything else present/ready, but the pinned packages are not yet cached on disk ->
    # check must report "needs apply" (exit 1).
    bind = _apt_stub_bin(tmp_path, sudo_nopasswd=True, libs_present=True, mcp_cached=False)
    res = _run_step(bind, "check", _chrome_env(tmp_path, present=True))
    assert res.returncode == 1, res.stdout + res.stderr


# --- macOS ----------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def macos_apply(tmp_path_factory):
    return _scenario(tmp_path_factory, "macos", "apply", chrome=False, macos=True)


def test_apply_on_macos_installs_the_browser_binary_and_touches_no_apt_or_sudo(macos_apply):
    # macOS users are first-class: the apply path installs the browser binary and skips ALL
    # apt/sudo system-deps machinery (those exist only on apt Linux), and never installs Chrome
    # itself - it tells the user the command.
    sc = macos_apply
    assert sc.res.returncode == 0, sc.out
    assert "install-deps" not in sc.out, sc.out
    assert not sc.sudo_log.exists(), f"sudo must not run on macOS: {_lines(sc.sudo_log)}"
    assert not sc.apt_log.exists(), f"apt-get must not run on macOS: {_lines(sc.apt_log)}"
    assert f"npx -y playwright@{PIN} install chrome" in sc.res.stderr



@pytest.fixture(scope="module")
def chrome_absent_check(tmp_path_factory):
    return _scenario(tmp_path_factory, "chrome-absent", "check", chrome=False,
                     sudo_nopasswd=False, libs_present=True)


def test_check_reports_a_missing_chrome_with_the_install_command(chrome_absent_check):
    sc = chrome_absent_check
    assert sc.res.returncode == 1, sc.out
    assert f"npx -y playwright@{PIN} install chrome" in sc.res.stderr


# ---------------------------------------------------------------------------
# Playwright Chromium: installed means the pinned revision, finished. The record the SessionStart
# hint reads (no npx there) is written by check/apply, revision-exact, re-checked against the
# markers.
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def verified_check(tmp_path_factory):
    """`check` with Chrome and every listed Chromium location complete."""
    return _scenario(tmp_path_factory, "verified", "check", chrome=True,
                     sudo_nopasswd=False, libs_present=True)


@pytest.fixture(scope="module")
def unverified_check(tmp_path_factory):
    """`check` where a listed location lacks its completion marker (a half-finished download),
    while the standard cache holds ANOTHER release's complete chromium-1000."""
    home = tmp_path_factory.mktemp("decoy-home")
    other = home / ".cache" / "ms-playwright" / "chromium-1000"
    other.mkdir(parents=True)
    (other / "INSTALLATION_COMPLETE").write_text("", encoding="utf-8")
    return _scenario(tmp_path_factory, "unverified", "check", chrome=True,
                     extra_env={"HOME": str(home),
                                "PLAYWRIGHT_BROWSERS_PATH": str(home / ".cache" / "ms-playwright")},
                     sudo_nopasswd=False, libs_present=True, chromium_complete=False)


@pytest.fixture(scope="module")
def chromium_missing_apply(tmp_path_factory):
    return _scenario(tmp_path_factory, "chromium-missing", "apply", chrome=True,
                     sudo_nopasswd=False, libs_present=True, chromium_complete=False)


def test_check_accepts_the_pinned_chromium_when_every_listed_location_is_complete(verified_check):
    assert verified_check.res.returncode == 0, verified_check.out


def test_check_refuses_a_listed_location_without_its_completion_marker(unverified_check):
    # A half-finished download leaves the directory but not INSTALLATION_COMPLETE, and another
    # revision's chromium-* in the cache cannot start pagecast's playwright.
    assert unverified_check.res.returncode == 1, unverified_check.out


def test_apply_installs_the_pinned_chromium_when_its_revision_is_missing(chromium_missing_apply):
    sc = chromium_missing_apply
    assert sc.res.returncode == 0, sc.out
    calls = _lines(sc.npx_log)
    assert f"-y playwright@{PIN} install chromium" in calls, calls
    # No playwright install ever runs unpinned: it would resolve to whatever the cache holds.
    assert all(f"playwright@{PIN}" in ln for ln in calls if " install" in ln), calls


def _assert_recorded(tmp):
    record = _record(tmp)
    assert record is not None, "a verified Chromium must be recorded"
    assert record["playwright"] == PIN
    listed = [line.split("Install location:", 1)[1].strip()
              for line in _pw_dry_run(tmp).splitlines() if "Install location:" in line]
    assert record["locations"] == listed


@requires_bash
def test_a_verified_chromium_is_recorded_for_the_pinned_playwright_by_check(verified_check):
    _assert_recorded(verified_check.tmp)


@requires_bash
def test_an_unverified_chromium_is_never_recorded(unverified_check):
    assert _record(unverified_check.tmp) is None


@requires_bash
def test_the_hint_is_silent_when_the_record_matches_and_every_location_is_complete(verified_check):
    assert "playwright-browsers" not in _hint(verified_check.tmp)


@requires_bash
def test_the_hint_asks_for_setup_when_there_is_no_record(tmp_path):
    """Another revision's chromium-* in the cache no longer satisfies the hint."""
    home = tmp_path / "home"
    (home / ".cache" / "ms-playwright" / "chromium-1000").mkdir(parents=True)
    err = _hint(tmp_path, home=home)
    assert "playwright-browsers (missing" in err, err


def _copy_of_the_verified_state(verified_check, tmp_path):
    """The verified record in a state root of this test's own, its locations copied beside it, so
    a test can break the copy and leave the shared scenario alone."""
    record = _record(verified_check.tmp)
    moved = []
    for i, loc in enumerate(record["locations"]):
        dest = tmp_path / "locations" / str(i)
        shutil.copytree(loc, dest)
        moved.append(str(dest))
    record["locations"] = moved
    return record


def _write_record(tmp_path, record):
    path = tmp_path / "state" / "runtime" / "browser-deps.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(record), encoding="utf-8")


@requires_bash
def test_the_hint_asks_for_setup_when_the_pinned_playwright_moved(verified_check, tmp_path):
    record = _copy_of_the_verified_state(verified_check, tmp_path)
    record["playwright"] = "0.0.1"
    _write_record(tmp_path, record)
    assert "playwright-browsers (outdated" in _hint(tmp_path)


@requires_bash
def test_the_hint_asks_for_setup_when_a_recorded_location_lost_its_marker(verified_check, tmp_path):
    record = _copy_of_the_verified_state(verified_check, tmp_path)
    _write_record(tmp_path, record)
    assert "playwright-browsers" not in _hint(tmp_path), "premise: the copy is a clean record"
    (Path(record["locations"][0]) / "INSTALLATION_COMPLETE").unlink()
    assert "playwright-browsers (incomplete" in _hint(tmp_path)


@requires_bash
def test_the_hint_stays_silent_about_chromium_when_it_cannot_check(tmp_path, path_farm):
    """No python3 on PATH: the probe says nothing about Chromium rather than guessing."""
    path = farm_path(path_farm(drop=("python3",)))
    assert shutil.which("python3", path=path) is None, "premise: python3 is unreachable"
    env = dict(os.environ, PATH=path, ODOO_AI_HOME=str(tmp_path / "state"),
               HOME=str(tmp_path / "home"))
    res = subprocess.run(["bash", str(HOOK)], input="{}", env=env,
                         capture_output=True, text=True, timeout=60)
    assert res.returncode == 0
    assert "playwright-browsers" not in res.stderr
