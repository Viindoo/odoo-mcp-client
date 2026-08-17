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
from pathlib import Path
from typing import Callable, Iterable

import pytest

# Keyed by the frozen drop-set, so two callers asking for the SAME exclusions
# share the SAME farm within a session, and two callers with DIFFERENT
# exclusions never collide on one directory. Module-level (not fixture-local)
# so the cache also survives across the different scopes that request the
# session fixture.
_FARM_CACHE: dict[frozenset, Path] = {}


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
