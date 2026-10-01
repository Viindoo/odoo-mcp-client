"""Behaviour of scripts/mcp/browser_mcp_launch.py and its SSOT scripts/lib/browser_mcp_servers.py.

Why the launcher exists: chrome-devtools-mcp writes a file only inside the client's roots (the
session cwd), the OS temp dir and `--workspace` dirs; playwright-mcp only inside `--output-dir`
and the cwd; pagecast only into RECORDING_OUTPUT_DIR (default ./recordings). An absolute capture
path under the state root was refused, agents retried with a relative path, and the file landed
in the user's repository. A static .mcp.json cannot spell the state root, so the launcher
resolves it and starts `npx -y <exact pin> <flags> <state-root flags>`.

Every test runs the launcher against a stub `npx` that records its argv and environment, with a
temporary $ODOO_AI_HOME - no network, no browser, no machine-specific path.
"""
import ast
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
LAUNCHER = PLUGIN / "scripts" / "mcp" / "browser_mcp_launch.py"
SSOT_PY = PLUGIN / "scripts" / "lib" / "browser_mcp_servers.py"
CAPTURE_PY = PLUGIN / "scripts" / "lib" / "capture_paths.py"
CODEX_MANIFEST = PLUGIN / ".codex-plugin" / "mcp.json"

EXACT_PIN = re.compile(r"@\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")
EXACT_VERSION = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")

posix_only = pytest.mark.skipif(os.name == "nt", reason="stub npx is a POSIX script")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ssot = _load("browser_mcp_servers_under_test", SSOT_PY)
launcher = _load("browser_mcp_launch_under_test", LAUNCHER)

FAMILIES = list(ssot.ALL_SERVERS)


def _stub_npx(tmp_path) -> tuple:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    record = tmp_path / "npx-call.json"
    stub = bin_dir / "npx"
    stub.write_text(
        f"#!{sys.executable}\nimport json, os, sys\n"
        f"open({str(record)!r}, 'w').write(json.dumps({{'argv': sys.argv[1:], "
        f"'env': dict(os.environ)}}))\n",
        encoding="utf-8",
    )
    stub.chmod(0o755)
    return bin_dir, record


def _launch(tmp_path, family, **env_over):
    bin_dir, record = _stub_npx(tmp_path)
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("BROWSER_MCP_") and k not in (
               "ODOO_AI_PROJECT_DIR", "ODOO_AI_WORKTREE_DIR", "PLAYWRIGHT_MCP_OUTPUT_MAX_SIZE")}
    env.update(PATH=f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
               ODOO_AI_HOME=str(tmp_path / "state"))
    env.update(env_over)
    proc = subprocess.run([sys.executable, str(LAUNCHER), family], env=env,
                          capture_output=True, text=True, timeout=30)
    call = json.loads(record.read_text(encoding="utf-8")) if record.exists() else None
    return proc, call


# --------------------------------------------------------------------------- #
# argv per family
# --------------------------------------------------------------------------- #
@posix_only
@pytest.mark.parametrize("family", FAMILIES)
def test_each_family_starts_its_exact_pin_and_base_flags(tmp_path, family):
    proc, call = _launch(tmp_path, family)
    assert proc.returncode == 0, proc.stderr
    argv = call["argv"]
    assert argv[0] == "-y"
    assert EXACT_PIN.search(argv[1]), f"{family}: not an exact version: {argv[1]!r}"
    headed = family.endswith("-headed")
    assert ("--headless" in argv) is (not headed), argv
    assert ("--isolated" in argv) is (not family.startswith("pagecast")), argv


@posix_only
@pytest.mark.parametrize("family", ["chrome-devtools", "chrome-devtools-headed"])
def test_chrome_devtools_gets_the_state_root_as_workspace(tmp_path, family):
    proc, call = _launch(tmp_path, family)
    assert proc.returncode == 0, proc.stderr
    assert f"--workspace={tmp_path / 'state'}" in call["argv"], call["argv"]


@posix_only
@pytest.mark.parametrize("family", ["playwright", "playwright-headed"])
def test_playwright_gets_the_projects_output_dir_and_an_idle_timeout(tmp_path, family):
    proc, call = _launch(tmp_path, family)
    assert proc.returncode == 0, proc.stderr
    argv = call["argv"]
    assert f"--output-dir={tmp_path / 'state' / 'projects'}" in argv, argv
    assert any(a.startswith("--idle-timeout=") and a.split("=", 1)[1].isdigit() for a in argv), argv


@posix_only
@pytest.mark.parametrize("family", ["pagecast", "pagecast-headed"])
def test_pagecast_records_into_the_state_root_scratch(tmp_path, family):
    proc, call = _launch(tmp_path, family)
    assert proc.returncode == 0, proc.stderr
    assert call["env"]["RECORDING_OUTPUT_DIR"] == str(tmp_path / "state" / "scratch" / "pagecast")
    assert not any(a.startswith(("--workspace", "--output-dir")) for a in call["argv"])


@posix_only
def test_the_directories_the_servers_write_into_exist_before_start(tmp_path):
    """chrome-devtools silently drops a --workspace root that does not exist, so the launcher
    creates the tree first."""
    proc, _call = _launch(tmp_path, "chrome-devtools")
    assert proc.returncode == 0, proc.stderr
    assert (tmp_path / "state" / "projects").is_dir()
    assert (tmp_path / "state" / "scratch" / "pagecast").is_dir()


@posix_only
@pytest.mark.parametrize("family", FAMILIES)
def test_stdout_stays_empty_because_it_is_the_mcp_channel(tmp_path, family):
    proc, _call = _launch(tmp_path, family)
    assert proc.stdout == "", f"launcher wrote to the MCP channel: {proc.stdout!r}"


@posix_only
@pytest.mark.parametrize("family", ["playwright", "playwright-headed"])
def test_output_eviction_is_never_enabled(tmp_path, family):
    """--output-max-size evicts files recursively under the output dir (the state root's
    projects tree here): never passed, and the env spelling is removed from the child."""
    proc, call = _launch(tmp_path, family, PLAYWRIGHT_MCP_OUTPUT_MAX_SIZE="1000")
    assert proc.returncode == 0, proc.stderr
    assert not any("output-max-size" in a for a in call["argv"])
    assert "PLAYWRIGHT_MCP_OUTPUT_MAX_SIZE" not in call["env"]


@posix_only
def test_an_override_dir_outside_the_root_becomes_another_workspace(tmp_path):
    outside = tmp_path / "elsewhere" / "wt"
    proc, call = _launch(tmp_path, "chrome-devtools", ODOO_AI_WORKTREE_DIR=str(outside) + "/")
    assert proc.returncode == 0, proc.stderr
    workspaces = [a for a in call["argv"] if a.startswith("--workspace=")]
    assert workspaces == [f"--workspace={tmp_path / 'state'}", f"--workspace={outside}"]


@posix_only
def test_an_override_dir_inside_the_root_adds_nothing(tmp_path):
    inside = tmp_path / "state" / "projects" / "abc"
    proc, call = _launch(tmp_path, "chrome-devtools", ODOO_AI_PROJECT_DIR=str(inside))
    assert proc.returncode == 0, proc.stderr
    assert [a for a in call["argv"] if a.startswith("--workspace=")] == [
        f"--workspace={tmp_path / 'state'}"]


@posix_only
def test_a_pin_override_from_the_environment_wins(tmp_path):
    proc, call = _launch(tmp_path, "pagecast", BROWSER_MCP_PAGECAST_PIN="@mcpware/pagecast@9.9.9")
    assert proc.returncode == 0, proc.stderr
    assert call["argv"][1] == "@mcpware/pagecast@9.9.9"


# --------------------------------------------------------------------------- #
# degradation: the server still starts, and the reason is said
# --------------------------------------------------------------------------- #
@posix_only
def test_an_unusable_state_root_still_starts_the_server_and_says_why(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    proc, call = _launch(tmp_path, "chrome-devtools", ODOO_AI_HOME=str(blocker / "state"))
    assert proc.returncode == 0, proc.stderr
    assert call is not None, "the server must start even when the state root cannot be used"
    assert call["argv"][:2] == ["-y", ssot.pin("chrome-devtools", {})]
    assert not any(a.startswith("--workspace") for a in call["argv"])
    assert "without state-root flags" in proc.stderr
    assert proc.stdout == ""


def test_a_python_below_the_floor_falls_back_to_the_base_launch(monkeypatch, tmp_path):
    """An Odoo venv's interpreter can shadow python3. Below 3.8 the launcher must not try the
    state-root half (paths.py needs 3.8) and must still produce a runnable launch."""
    monkeypatch.setenv("ODOO_AI_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("VIRTUAL_ENV", str(tmp_path / "odoo-venv"))
    argv, env, reason = launcher.plan_launch("chrome-devtools", (3, 6, 15))
    assert argv == ["npx", "-y"] + ssot.npx_args("chrome-devtools")
    assert reason and "3.8" in reason
    assert not (tmp_path / "state").exists(), "nothing may be created on the fallback path"


@posix_only
def test_missing_npx_is_reported_not_silent(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    env = dict(os.environ, PATH=str(empty), ODOO_AI_HOME=str(tmp_path / "state"))
    proc = subprocess.run([sys.executable, str(LAUNCHER), "chrome-devtools"], env=env,
                          capture_output=True, text=True, timeout=30)
    assert proc.returncode == 127
    assert "npx" in proc.stderr and proc.stdout == ""


def test_an_unknown_family_is_refused_with_a_reason(tmp_path):
    proc = subprocess.run([sys.executable, str(LAUNCHER), "firefox"], capture_output=True,
                          text=True, timeout=30)
    assert proc.returncode == 2
    assert "unknown browser MCP family" in proc.stderr


def test_windows_runs_npx_found_on_path_as_a_child_and_passes_its_exit_code(monkeypatch):
    """execvp on Windows ends the process the client waits on; the launcher runs npx (npx.cmd,
    as shutil.which finds it) as a child with inherited stdio and exits with its code."""
    calls = []
    monkeypatch.setattr(launcher.os, "name", "nt")
    monkeypatch.setattr(launcher.shutil, "which", lambda name: "C:\\node\\npx.CMD")
    monkeypatch.setattr(launcher.subprocess, "call",
                        lambda argv, env=None: calls.append(argv) or 3)
    with pytest.raises(SystemExit) as exc:
        launcher._exec(["npx", "-y", "chrome-devtools-mcp@1.10.1", "--headless"], {})
    assert exc.value.code == 3
    assert calls == [["C:\\node\\npx.CMD", "-y", "chrome-devtools-mcp@1.10.1", "--headless"]]


# --------------------------------------------------------------------------- #
# exact pins everywhere they are spelled
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("family", FAMILIES)
def test_ssot_pins_are_exact_versions(family):
    assert EXACT_PIN.search(ssot.pin(family, {})), ssot.pin(family, {})


def test_the_playwright_core_version_is_exact():
    assert EXACT_VERSION.match(ssot.PLAYWRIGHT_CORE_VERSION), ssot.PLAYWRIGHT_CORE_VERSION


def test_generated_codex_manifest_pins_are_exact():
    data = json.loads(CODEX_MANIFEST.read_text(encoding="utf-8"))
    pkgs = [a for entry in data.values() for a in entry["args"] if "@" in a]
    assert pkgs, "premise: the Codex manifest launches at least one pinned package"
    for pkg in pkgs:
        assert EXACT_PIN.search(pkg), f"generated manifest pin is not exact: {pkg!r}"


# --------------------------------------------------------------------------- #
# grammar: these files run before any interpreter check
# --------------------------------------------------------------------------- #
def _oldest_parse_version():
    for minor in range(4, 9):
        try:
            ast.parse("x = 1", feature_version=(3, minor))
            return (3, minor)
        except ValueError:
            continue
    return (3, 8)


@pytest.mark.parametrize("path", [LAUNCHER, SSOT_PY, CAPTURE_PY], ids=lambda p: p.name)
def test_pre_version_check_files_parse_on_the_oldest_grammar(path):
    text = path.read_text(encoding="utf-8")
    ast.parse(text, filename=str(path), feature_version=_oldest_parse_version())
    tree = ast.parse(text)
    assert not any(isinstance(n, ast.JoinedStr) for n in ast.walk(tree)), f"f-string in {path.name}"
    assert not any(isinstance(n, ast.AnnAssign) or (isinstance(n, ast.FunctionDef) and (
        n.returns is not None or any(a.annotation is not None for a in n.args.args)))
        for n in ast.walk(tree)), f"annotation in {path.name}"
