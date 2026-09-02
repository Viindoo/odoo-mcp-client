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
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Iterable

import pytest

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
            if src.is_dir() or not os.access(src, os.X_OK):
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
