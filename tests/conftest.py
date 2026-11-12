"""Shared pytest fixtures for the `odoo-ai-agents` test suite.

## The PATH-farm fixture

Three test files (`test_db_local_auth.py`, `test_db_auth_preflight.py`,
`test_step45_50_harden.py`) each grew their own differently-named helper
(`_shadowed_path`, `_hermetic_path`, `_client_free_path`) that constructs a
directory of symlinks re-exposing the ambient PATH with a few binaries left
out - so a test can prove a binary is ABSENT without asserting anything about
the host. All three helpers are a PURE FUNCTION of `(ambient PATH, drop-set)`:
nothing test-specific enters the farm, and no test mutates it once built. That
makes it a session-level CONSTANT - but each helper was anchored to the
per-test `tmp_path` fixture, so it was rebuilt from scratch on every test that
needed one (tens of thousands of symlinks per run, most of them identical
across calls).

`path_farm` fixes this: it is session-scoped and memoizes by drop-set, so the
farm for a given drop-set is built AT MOST ONCE per pytest session no matter
how many tests (or files) ask for it. `farm_path` is the companion helper that
joins a caller's own stub directories in front of the farm - preserving the
"callers prepend their own stubs, never write into the farm" contract every
original helper implemented locally.

This file intentionally contains the ONLY symlink-farm-building loop in the
suite; every call site consumes it through `path_farm` / `farm_path` instead
of re-implementing it.

## Stop / SubagentStop hook output and transcript helpers

`model_context` reads the text a Stop / SubagentStop hook hands the MODEL and
`handback_records` builds a delivered SubagentHandback, so the hook test files
share one reading of the channel contract instead of a copy each.

## The serial set (timing-sensitive tests)

`make test` runs the suite in two passes: every test NOT marked `serial` in parallel
(`pytest -n <workers> --dist loadfile`, one worker per file at a time so a module-scoped fixture is
built once per file), then the marked set alone, one process, nothing else running. A test that
asserts something finishes well inside a time bound is reliable only when the machine is not
loaded by sibling workers, so it belongs in `SERIAL_TESTS` below - the ONE place that list lives.
A plain `python -m pytest tests/` still runs everything in one process and needs no plugin.
"""

from __future__ import annotations

import os
import signal
import shutil
import subprocess
import time
from pathlib import Path
from typing import Callable, Iterable

import pytest

# Session-anchor determinism. `allocator.py` anchors every lease it writes to the
# caller's agent session (CLAUDE_PID, or a `claude`/`codex`/`gemini` ancestor), and an
# alive anchor PROTECTS a lease from every reclaim arm. Run inside a Claude Code session,
# every subprocess this suite spawns would inherit that live anchor; run in CI, none
# would - so a test asserting a reclaim would pass in one place and fail in the other.
# Anchoring is therefore OFF by default for the whole suite (the documented "none"
# value), and a test that exercises anchoring sets ODOO_AI_SESSION_ANCHOR itself.
os.environ.setdefault("ODOO_AI_SESSION_ANCHOR", "none")

# Ambient-value determinism. The production code reads a configured value (a speech key, a YouTube
# credential), the database password and the plugin's own overrides from environment variables of
# fixed names. A test that builds a child environment from `os.environ`, or runs production code in
# this process, would hand a developer's own value to it. The suite therefore starts with those
# variables absent; a test that needs one sets it itself.
from odoo_local_mcp_harness import scrub_ambient_values  # noqa: E402

scrub_ambient_values(os.environ)

# Keyed by the frozen drop-set, so two callers asking for the SAME exclusions
# share the SAME farm within a session, and two callers with DIFFERENT
# exclusions never collide on one directory. Module-level (not fixture-local)
# so the cache also survives across the different scopes that request the
# session fixture.
_FARM_CACHE: dict[frozenset, Path] = {}


# Interpreters a version manager (pyenv, asdf, rbenv, mise) commonly SHIMS. A shim
# is an ordinary executable, so the farm loop symlinks the shim rather than the
# interpreter it dispatches to - and a shim resolves its target by re-searching
# PATH with its own shims directory removed. Under a farm-only PATH there is
# nothing left for it to find, so the farm's `python3` exits 127 with
# "pyenv: python3: command not found". Nothing asserts on that, so the farm looks
# complete while every script that shells out to `python3` silently produces
# nothing - and a setup step that suppresses its interpreter's stderr then reports
# a downstream symptom instead of the missing interpreter. Measured on a pyenv host
# with `pyenv version` = system: 57 tests across three files failed this way, all of
# them green in CI, where no version manager is installed.
_SHIM_PRONE = ("python3", "python")


def _runs_under(binary: Path, path_value: str) -> bool:
    """True when `binary` executes at all with PATH set to `path_value`."""
    try:
        return subprocess.run(
            [str(binary), "-c", ""],
            capture_output=True,
            env={**os.environ, "PATH": path_value},
            timeout=60,
        ).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


_CONCRETE_CACHE: dict[str, "Path | None"] = {}


def _concrete_interpreter(name: str) -> Path | None:
    """The real executable `name` runs as under the AMBIENT PATH, or None.

    Asked of the interpreter itself rather than derived from the shim's text, so
    it stays correct for every version manager instead of one this file happens
    to know the layout of.
    """
    if name in _CONCRETE_CACHE:
        return _CONCRETE_CACHE[name]
    _CONCRETE_CACHE[name] = _resolve_concrete(name)
    return _CONCRETE_CACHE[name]


def _resolve_concrete(name: str) -> Path | None:
    try:
        done = subprocess.run(
            [name, "-c", "import sys; print(sys.executable)"],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    target = Path(done.stdout.strip())
    return target if target.is_file() and os.access(target, os.X_OK) else None


def real_python3() -> str:
    """The CONCRETE `python3` a test may hand to a stub that re-execs it.

    `shutil.which("python3")` is the wrong answer on any host running a version
    manager: it returns the SHIM, and a shim resolves its target by re-searching
    PATH with its own shims directory removed. A test that puts its own `python3`
    stub on PATH - which several do, to record what a step asked - then gets an
    exec loop: stub -> shim -> PATH search -> the same stub, forever. Measured on
    a pyenv host: two tests in `test_step45_50_harden.py` hung until their
    subprocess timeout fired, on every run, while CI stayed green because no
    version manager is installed there.

    Falls back to `shutil.which` and then to the conventional absolute path, so a
    host with no resolvable interpreter behaves exactly as it did before.
    """
    concrete = _concrete_interpreter("python3")
    if concrete is not None:
        return str(concrete)
    return shutil.which("python3") or "/usr/bin/python3"


def _relink_version_manager_shims(farm: Path, drop: frozenset) -> None:
    """Repoint any farm entry that is a shim at the interpreter it dispatches to.

    Only entries that PROVABLY do not run under a farm-only PATH are touched, so
    on a host with no version manager this is a no-op and the farm keeps the
    ambient binary verbatim.
    """
    for name in _SHIM_PRONE:
        link = farm / name
        if name in drop or not link.exists():
            continue
        if _runs_under(link, str(farm)):
            continue
        concrete = _concrete_interpreter(name)
        if concrete is None:
            continue  # the ambient interpreter is broken too - let the assert below say so
        link.unlink()
        link.symlink_to(concrete)


def _build_farm(tmp_path_factory: "pytest.TempPathFactory", drop: frozenset) -> Path:
    """Return the memoized farm for `drop`, building it at most once per session.

    The body is the three original helpers' loop, verbatim: iterate the
    ambient PATH, skip names in `drop`, first-hit-wins, require
    `os.access(src, os.X_OK)` and `not src.is_dir()`, tolerate `OSError`.
    """
    cached = _FARM_CACHE.get(drop)
    if cached is not None:
        return cached
    farm = tmp_path_factory.mktemp("path_farm", numbered=True)
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if not entry:
            continue
        try:
            names = os.listdir(entry)
        except OSError:
            continue  # a PATH entry that does not exist or is unreadable
        for name in names:
            if name in drop:
                continue
            link = farm / name
            if link.is_symlink() or link.exists():
                continue  # first hit wins - ambient PATH precedence is preserved
            src = Path(entry) / name
            try:
                if src.is_dir() or not os.access(src, os.X_OK):
                    continue
            except OSError:
                continue
            try:
                link.symlink_to(src)
            except OSError:
                continue
    _relink_version_manager_shims(farm, drop)
    # Self-validating, once per farm (per drop-set) instead of once per test:
    # if this construction ever stops working, fail LOUDLY here rather than
    # quietly falling back to whatever the host or CI image happens to ship.
    for name in drop:
        found = shutil.which(name, path=str(farm))
        assert found is None, (
            f"the constructed PATH must not reach a dropped binary, but "
            f"{name!r} resolved to {found!r} - the absence this farm needs is "
            f"no longer guaranteed"
        )
    assert shutil.which("bash", path=str(farm)), (
        "the constructed PATH dropped bash - it must keep everything a script "
        "legitimately needs, or a test built on this farm stops exercising the "
        "real code path"
    )
    # Reachable is not the same as runnable, and the difference is what a shim
    # hides. Assert EXECUTION, so a farm that re-exposes an interpreter it cannot
    # actually run fails here - loudly, once - instead of turning every script
    # that calls it into a silent no-op somewhere downstream.
    for name in _SHIM_PRONE:
        link = farm / name
        if name in drop or not link.exists():
            continue
        assert _runs_under(link, str(farm)), (
            f"the constructed PATH re-exposes {name!r} but it does not RUN under "
            f"that PATH: {link} -> {os.path.realpath(link)}. On a host using a "
            "version manager this is the shim, which cannot resolve its target "
            "once the ambient PATH is replaced. Every script the farm hands this "
            "interpreter to would silently produce nothing."
        )
    _FARM_CACHE[drop] = farm
    return farm


@pytest.fixture(scope="session")
def path_farm(tmp_path_factory: "pytest.TempPathFactory") -> Callable[..., Path]:
    """Session-scoped factory: `path_farm(drop=(...))` -> Path to a PATH farm.

    Returns the SAME `Path` for the same drop-set across the whole session
    (built once), and a different `Path` per distinct drop-set. `drop` may be
    any iterable of binary names; it is frozen before use as the cache key.
    """

    def _get(drop: Iterable[str] = ()) -> Path:
        return _build_farm(tmp_path_factory, frozenset(drop))

    return _get


def farm_path(farm: Path, *stub_dirs: Path) -> str:
    """Join `stub_dirs` (a caller's own stubs) in front of `farm` into a PATH string.

    `stub_dirs` are prepended so a test's own stubs still shadow the ambient
    ones the farm re-exposes - the exact contract each original per-file
    helper implemented locally.
    """
    return os.pathsep.join([*(str(d) for d in stub_dirs), str(farm)])


# ---------------------------------------------------------------------------
# Reaping what a step leaves behind
#
# `50-instance-spinup.sh` launches a background server and polls it - correct for a real daemon,
# and the step rightly leaves it running. The step-50 fixtures never reaped it, so the stub
# survived the test, the pytest session, and the deletion of its own `tmp_path`.
#
# That is not a tidiness point. Two such orphans were found alive 48 minutes after their run,
# each holding a 2.5 GB DELETED log file: once their tmp dir went away the PATH farm went with
# it, `sleep` stopped resolving, and `while : ; do sleep 1; done` became a hot loop writing an
# error line per iteration into a log whose file descriptor was still open. On a host whose
# temp filesystem is memory-backed and quota-limited, ~5 GB of unreclaimable RAM made every
# agent session on the machine fail on a two-byte write.
#
# Two mechanisms, deliberately both: `run_and_reap` kills promptly and precisely, and the
# session-end sweep is the backstop for any spawner nobody has routed through it yet.
# ---------------------------------------------------------------------------


def _kill_group(pgid: int) -> None:
    """SIGTERM a process group, then SIGKILL whatever ignored it. Never raises."""
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(pgid, sig)
        except (ProcessLookupError, PermissionError, OSError):
            return
        for _ in range(20):
            try:
                os.killpg(pgid, 0)
            except (ProcessLookupError, OSError):
                return
            time.sleep(0.05)


def run_and_reap(cmd, *, timeout=None, **kwargs) -> subprocess.CompletedProcess:
    """`subprocess.run` for a command that may leave a daemon behind.

    The command runs in its OWN process group, so anything it starts and does not stop can be
    killed as a group once it returns - which `subprocess.run` cannot do, because it exposes no
    pid after the fact. Use this for every invocation of a step that spins something up.
    """
    kwargs.setdefault("start_new_session", True)
    kwargs.pop("capture_output", None)
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, **kwargs
    )
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_group(proc.pid)
        out, err = proc.communicate()
        raise
    finally:
        _kill_group(proc.pid)
    return subprocess.CompletedProcess(cmd, proc.returncode, out, err)


@pytest.fixture(scope="session", autouse=True)
def _reap_processes_left_under_basetemp(tmp_path_factory: "pytest.TempPathFactory"):
    """Session-end backstop: kill anything still running out of this session's temp tree.

    One `/proc` scan at the very end, not per test - a per-test scan over thousands of tests
    would cost more than the leak it prevents. Scoped by cmdline match on this session's own
    basetemp, so it can never reach a process that belongs to somebody else.
    """
    yield
    try:
        base = str(tmp_path_factory.getbasetemp().resolve())
    except (OSError, AttributeError):
        return
    if not Path("/proc").is_dir():
        return
    # Our OWN process group is excluded, and that is not a nicety: pytest's command line carries
    # `--basetemp=<path>`, so the first version of this sweep matched the runner itself and killed
    # the group it was running in. A sweep that can reach its own caller is a worse defect than
    # the leak it cleans up.
    own_pgid = os.getpgrp()
    own_pid = os.getpid()
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            raw = (entry / "cmdline").read_bytes()
        except (OSError, PermissionError):
            continue
        # argv[0] ONLY - the program being RUN, never the whole command line. Matching anywhere
        # in the command line looked equivalent and was not: pytest's own invocation carries
        # `--basetemp=<path>`, and so does the shell that typed it, so the first two versions of
        # this sweep killed the runner and its wrapper instead of the leak. A process whose
        # EXECUTABLE lives under this session's temp tree is, by construction, something the
        # session created and nobody else can own.
        argv0 = raw.split(b"\0", 1)[0].decode("utf-8", "replace")
        if not argv0.startswith(base):
            continue
        try:
            pid = int(entry.name)
            if pid == own_pid:
                continue
            pgid = os.getpgid(pid)
            if pgid == own_pgid:
                continue
            _kill_group(pgid)
        except (ProcessLookupError, PermissionError, OSError, ValueError):
            continue


def model_context(out: dict | None, event: str) -> str:
    """The text a Stop / SubagentStop hook's output hands the MODEL: hookSpecificOutput
    .additionalContext for `event` - the one channel the stopping agent reads (it runs one more turn
    with it). Asserts it neither blocks nor rides systemMessage, which reaches no model. "" when the
    hook was silent."""
    if out is None:
        return ""
    assert "systemMessage" not in out, f"a model-facing text rode systemMessage: {out!r}"
    assert "decision" not in out and out.get("continue") is not False, f"advisory blocked: {out!r}"
    hso = out.get("hookSpecificOutput") or {}
    assert hso.get("hookEventName") == event, out
    return hso.get("additionalContext", "")


def handback_records(message: str, *, tid: str = "toolu_hb",
                     outcome: dict | None = None, denied: bool = False) -> list[str]:
    """A SubagentHandback call and the harness's answer as two transcript records: delivered (the
    default), another outcome (e.g. refused as a second call), or denied by a PreToolUse hook (an
    error tool_result - nothing was sent)."""
    import json
    outcome = outcome or {"success": True, "message": "Report delivered to your caller."}
    call = {"type": "tool_use", "id": tid, "name": "SubagentHandback", "input": {"message": message}}
    use = {"type": "assistant", "message": {"role": "assistant", "content": [call]}}
    if denied:
        block = {"type": "tool_result", "tool_use_id": tid, "is_error": True,
                 "content": "PreToolUse:SubagentHandback hook error: denied"}
        res = {"type": "user", "message": {"role": "user", "content": [block]}}
    else:
        block = {"type": "tool_result", "tool_use_id": tid,
                 "content": [{"type": "text", "text": json.dumps(outcome)}]}
        res = {"type": "user", "message": {"role": "user", "content": [block]},
               "toolUseResult": outcome}
    return [json.dumps(use), json.dumps(res)]


def block_feedback_record(reason: str) -> str:
    """How the harness records a Stop / SubagentStop block reason in the agent's own transcript: a
    meta "Stop hook feedback:" user record (measured on Claude Code 2.1.288; a hook_blocking_error
    attachment carries the same reason)."""
    import json
    return json.dumps({"type": "user", "isMeta": True,
                       "message": {"role": "user", "content": "Stop hook feedback:\n" + reason}})


def resume_record(text: str = "Take this up again and report.") -> str:
    """How a caller's SendMessage resume of a stopped subagent lands in its own transcript: a meta
    user string with origin kind `coordinator` (measured on Claude Code 2.1.288)."""
    import json
    return json.dumps({"type": "user", "isMeta": True, "origin": {"kind": "coordinator"},
                       "message": {"role": "user", "content": "The coordinator sent a message "
                                   "while you were working:\n" + text}})


def brief_record(text: str = "Do the task and report.") -> str:
    """A dispatched agent's first prompt, the record its first turn starts at."""
    import json
    return json.dumps({"type": "user", "message": {"role": "user", "content": text}})


# ---------------------------------------------------------------------------
# The serial set: tests that assert "finishes well inside a time bound" (or drive a real browser
# with long waits) and so are reliable only when the machine is not loaded by parallel workers.
#
# ADD AN ENTRY HERE AND NOWHERE ELSE. Each entry is an fnmatch pattern over the pytest node id
# (`tests/<file>.py::<test name>[<param id>]`); end a name with `*` to take every parametrized
# case or every test with that prefix, and never write `[` in a pattern (it is a character class).
# `tests/<file>.py::*` serializes a whole file. `tests/test_serial_set.py` fails when a pattern
# matches no collected test, so a renamed or deleted test cannot silently leave the set.
# ---------------------------------------------------------------------------
SERIAL_TESTS = (
    # Elapsed-time bound tests of the bounded runner.
    "tests/test_pg_mode.py::test_bounded_run_*",
    "tests/test_pg_mode.py::test_pg_hba_file_path_is_bounded_*",
    # Real Chromium; the module-scoped `unmet_waits` fixture holds two 30 s waits.
    "tests/test_video_recorder.py::test_a_selector_wait_gives_up_after_30_seconds_by_default",
    "tests/test_video_recorder.py::test_an_unmet_selector_exits_3_naming_the_step",
    "tests/test_video_recorder.py::test_network_idle_ignores_the_long_lived_bus_connection_of_a_web_client",
    "tests/test_video_recorder.py::test_ui_user_signs_in_off_camera_and_the_clip_starts_at_the_scene",
    "tests/test_video_recorder.py::test_language_switch_runs_off_camera_before_the_take",
    # Readiness, spin-up and probe time bounds.
    "tests/test_step45_50_harden.py::test_step50_readiness_poll_is_bounded_never_hangs",
    "tests/test_step45_50_harden.py::test_step50_a_timed_out_exclusive_spinup_binds_its_pid_and_reaps_the_whole_group",
    "tests/test_step45_50_harden.py::test_step50_a_probe_that_does_not_answer_is_never_a_reachability_verdict*",
    "tests/test_step45_50_harden.py::test_step50_falls_back_to_web_login_when_selector_never_ready",
    # A hook or tool refusal that must land well inside its timeout on a long input.
    "tests/test_unowned_lease_mutation_gate.py::test_a_forwarded_lease_release_is_refused_well_inside_the_timeout_on_a_long_dispatch",
    "tests/test_enforce_teardown.py::test_a_live_lease_on_a_long_transcript_is_blocked_well_inside_the_timeout",
    "tests/test_job_wait_hook.py::test_a_long_transcript_that_holds_a_collected_job_is_cleared_well_inside_the_timeout",
    # Port and row timing of the two-phase release; failed once each under five-way load.
    "tests/test_allocator_release_two_phase.py::*",
    "tests/test_report_terminal_status.py::*",
    "tests/test_enforce_grounding.py::*",
    # A hook returning at once from a detached session; a bound that elapses and kills its group.
    "tests/test_enforce_teardown.py::test_session_end_gc_returns_at_once_and_reaps_from_a_detached_session",
    "tests/test_run_bounded.py::test_the_bound_elapses_with_124_and_kills_the_whole_group",
    # Elapsed bounds, a 1 s grace and a 60000-line flood.
    "tests/test_instance_ops_test_shutdown.py::*",
    # The local MCP server answers promptly while long waits block, and stops its waits when cancelled.
    "tests/test_odoo_local_mcp_protocol.py::test_short_calls_answer_promptly_while_more_long_waits_than_workers_block",
    "tests/test_odoo_local_mcp_protocol.py::test_a_lease_mutation_answers_promptly_while_forty_long_waits_block",
    "tests/test_odoo_local_mcp_protocol.py::test_a_cancelled_call_stops_waiting_and_gets_no_response",
    "tests/test_odoo_local_mcp_protocol.py::test_stdin_eof_stops_cancellable_waits_so_the_server_exits_promptly",
    "tests/test_odoo_local_mcp_protocol.py::test_job_wait_returns_early_when_its_call_is_cancelled",
    "tests/test_odoo_local_mcp_protocol.py::test_run_timeout_kills_the_whole_process_group",
    # Allocates 900 MB inside 256 MB capped scopes, plus a wall-clock bound.
    "tests/test_memory_capped_launch.py::*",
    # Probe bounds of the allocator.
    "tests/test_allocator.py::test_the_probe_bound_is_the_same_knob_the_shell_half_uses",
    "tests/test_allocator.py::test_ephemeral_acquire_returns_a_verdict_when_the_createdb_probe_hangs",
)


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config, items):
    """Mark every test in `SERIAL_TESTS` `serial`, before `-m` selects by mark."""
    from fnmatch import fnmatchcase
    for item in items:
        if any(fnmatchcase(item.nodeid, pattern) for pattern in SERIAL_TESTS):
            item.add_marker(pytest.mark.serial)
