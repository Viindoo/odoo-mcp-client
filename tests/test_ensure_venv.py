"""Behavior tests for the repo's venv setup (`make setup` -> `scripts/ensure-venv.sh`).

These protect what a contributor depends on, not how the script is written:

    - the venv is rebuilt only when the CONTENT of requirements.txt changed (a fresh git worktree
      always has a newer requirements.txt than a venv shared through VENV=..., and that must not
      cost a rebuild);
    - a rebuild that fails never removes or damages the venv that was already there;
    - a rebuild that succeeds is swapped in whole, and works from its final location;
    - a Python whose `-m venv` cannot bootstrap pip still yields a venv when uv is on PATH.

Each test copies the real Makefile and script into a throwaway project under `tmp_path` and drives
`make setup VENV=<dir>` with STUB `python3.12` and `uv` executables in front of a PATH farm that
hides every real interpreter and uv, so no real venv is built and nothing depends on the host. The
stubs record what they were asked to do in a log file the test reads back. stdlib + subprocess.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

from conftest import farm_path

ROOT = Path(__file__).resolve().parent.parent

# Real interpreters and uv are hidden so only the stubs can be found.
_HIDDEN = ("uv", "python", "python3", "python3.12", "python3.13", "python3.14", "python3.15")

# Shell that lays out what a created venv looks like: a python, a console script and an activate
# script that each embed the path the venv was built at, a pyvenv.cfg, and a built-by marker.
_MAKE_VENV = textwrap.dedent(
    """
    make_venv() {  # make_venv <dir> <built-by> <has-pip: 1|0>
      mkdir -p "$1/bin"
      cat > "$1/bin/python" <<'PY'
    #!/usr/bin/env bash
    here="$(cd "$(dirname "$0")/.." && pwd)"
    case "$1" in
      -c) exit 0 ;;
      -m) shift
          [ "$1" = pip ] || exit 1
          shift
          [ -e "$here/has-pip" ] || { echo "No module named pip" >&2; exit 1; }
          [ "$1" = install ] && echo "pip-install $here $*" >> "$STUB_LOG"
          [ -z "${STUB_FAIL_INSTALL:-}" ] || { echo "simulated install failure" >&2; exit 1; }
          exit 0 ;;
    esac
    PY
      chmod +x "$1/bin/python"
      printf '#!%s/bin/python\\n' "$1" > "$1/bin/tool"
      printf 'VIRTUAL_ENV="%s"\\n' "$1" > "$1/bin/activate"
      printf 'command = python -m venv %s\\n' "$1" > "$1/pyvenv.cfg"
      printf '%s\\n' "$2" > "$1/built-by"
      if [ "$3" = 1 ]; then : > "$1/has-pip"; fi
    }
    """
)

_PYTHON_STUB = (
    "#!/usr/bin/env bash\n"
    + _MAKE_VENV
    + textwrap.dedent(
        """
        case "$1" in
          --version) echo "Python 3.12.0"; exit 0 ;;
          -c) exit 0 ;;
          -m) [ "$2" = venv ] || exit 1
              target="${@: -1}"
              echo "venv-module $target" >> "$STUB_LOG"
              if [ -n "${STUB_VENV_FAILS:-}" ]; then
                make_venv "$target" venv 0   # ensurepip died half way: a dir without pip is left
                echo "No module named ensurepip" >&2; exit 1
              fi
              if [ -n "${STUB_NO_PIP:-}" ]; then make_venv "$target" venv 0; else make_venv "$target" venv 1; fi
              exit 0 ;;
        esac
        exit 1
        """
    )
)

_UV_STUB = (
    "#!/usr/bin/env bash\n"
    + _MAKE_VENV
    + textwrap.dedent(
        """
        case "$1 $2" in
          "venv "*)
            target="${@: -1}"
            echo "uv-venv $target" >> "$STUB_LOG"
            make_venv "$target" uv 0
            exit 0 ;;
          "pip install")
            echo "uv-pip-install $*" >> "$STUB_LOG"
            [ -z "${STUB_FAIL_INSTALL:-}" ] || { echo "simulated uv failure" >&2; exit 1; }
            exit 0 ;;
        esac
        exit 1
        """
    )
)


def _write_exe(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)


class Project:
    """A throwaway copy of the Makefile + script with stub tools in front of the PATH."""

    def __init__(self, tmp_path: Path, path_farm, *, with_uv: bool = True):
        if shutil.which("make") is None:
            pytest.skip("make is not installed")
        self.root = tmp_path / "proj"
        (self.root / "scripts").mkdir(parents=True)
        shutil.copy(ROOT / "Makefile", self.root / "Makefile")
        shutil.copy(ROOT / "scripts" / "ensure-venv.sh", self.root / "scripts" / "ensure-venv.sh")
        self.req = self.root / "requirements.txt"
        self.req.write_text("alpha==1\n", encoding="utf-8")
        self.venv = tmp_path / "shared" / ".venv"
        self.venv.parent.mkdir()
        self.log = tmp_path / "stub.log"
        self.log.write_text("", encoding="utf-8")
        stubs = tmp_path / "stubs"
        stubs.mkdir()
        _write_exe(stubs / "python3.12", _PYTHON_STUB)
        if with_uv:
            _write_exe(stubs / "uv", _UV_STUB)
        self.path = farm_path(path_farm(drop=_HIDDEN), stubs)

    def make(self, **flags: str) -> subprocess.CompletedProcess:
        env = {**os.environ, "PATH": self.path, "STUB_LOG": str(self.log), **flags}
        return subprocess.run(
            ["make", "setup", f"VENV={self.venv}"],
            cwd=self.root, env=env, capture_output=True, text=True, timeout=60,
        )

    def calls(self) -> list[str]:
        return self.log.read_text(encoding="utf-8").splitlines()

    def clear_calls(self) -> None:
        self.log.write_text("", encoding="utf-8")

    def set_requirements(self, text: str) -> None:
        self.req.write_text(text, encoding="utf-8")

    def make_requirements_newer(self) -> None:
        stamp = (self.venv / ".stamp").stat().st_mtime
        os.utime(self.req, (stamp + 100, stamp + 100))

    def seed(self) -> dict:
        """Build a first venv through the real rule, mark it, and return what must survive."""
        first = self.make()
        assert first.returncode == 0, first.stdout + first.stderr
        (self.venv / "keep-me").write_text("old venv\n", encoding="utf-8")
        self.clear_calls()
        return self.snapshot()

    def snapshot(self) -> dict:
        return {
            "inode": self.venv.stat().st_ino,
            "stamp": (self.venv / ".stamp").read_text(encoding="utf-8"),
            "marker": (self.venv / "keep-me").exists(),
            "built_by": (self.venv / "built-by").read_text(encoding="utf-8"),
        }

    def siblings(self) -> list[str]:
        return sorted(p.name for p in self.venv.parent.iterdir() if p.name != self.venv.name)


@pytest.fixture
def project(tmp_path, path_farm):
    return Project(tmp_path, path_farm)


def test_first_build_creates_a_venv_and_installs_requirements(project):
    result = project.make()
    assert result.returncode == 0, result.stdout + result.stderr
    assert (project.venv / "bin" / "python").exists()
    assert any(c.startswith("pip-install") for c in project.calls())
    assert project.siblings() == []


def test_newer_requirements_mtime_with_same_content_does_not_rebuild(project):
    before = project.seed()
    project.make_requirements_newer()
    result = project.make()
    assert result.returncode == 0, result.stdout + result.stderr
    assert project.calls() == [], "nothing may be built or installed when the content is unchanged"
    assert project.snapshot() == before, "the existing venv must be left exactly as it was"
    assert project.siblings() == []


def test_failed_build_leaves_the_old_venv_and_stamp_intact(project):
    before = project.seed()
    project.set_requirements("alpha==2\n")
    result = project.make(STUB_FAIL_INSTALL="1")
    assert result.returncode != 0, "a failed install must fail the make"
    assert project.snapshot() == before, "the working venv and its stamp must survive a failed build"
    assert project.siblings() == [], "the partial build directory must be cleaned up"


def test_failed_build_is_retried_on_the_next_run(project):
    """A stamp that still names the old content means the next run tries again."""
    project.seed()
    project.set_requirements("alpha==2\n")
    assert project.make(STUB_FAIL_INSTALL="1").returncode != 0
    project.clear_calls()
    retry = project.make()
    assert retry.returncode == 0, retry.stdout + retry.stderr
    assert any(c.startswith("pip-install") for c in project.calls())
    assert not (project.venv / "keep-me").exists(), "the retry replaced the old venv"


def test_no_way_to_build_leaves_the_old_venv_and_says_why(tmp_path, path_farm):
    proj = Project(tmp_path, path_farm, with_uv=False)
    before = proj.seed()
    proj.set_requirements("alpha==2\n")
    result = proj.make(STUB_VENV_FAILS="1")
    assert result.returncode != 0
    assert "uv" in result.stdout + result.stderr, "the message must say what to install"
    assert proj.snapshot() == before
    assert proj.siblings() == []


@pytest.mark.parametrize("old_stamp", ["a-stale-hash\n", ""], ids=["stale-hash", "legacy-empty-stamp"])
def test_changed_content_rebuilds_swaps_in_and_restamps(project, old_stamp):
    before = project.seed()
    (project.venv / ".stamp").write_text(old_stamp, encoding="utf-8")
    result = project.make()
    assert result.returncode == 0, result.stdout + result.stderr
    assert not (project.venv / "keep-me").exists(), "the old venv must have been replaced"
    assert (project.venv / "bin" / "python").exists()
    stamp = (project.venv / ".stamp").read_text(encoding="utf-8")
    assert stamp.strip() and stamp != old_stamp and stamp == before["stamp"], (
        "the new stamp must describe the unchanged requirements content"
    )
    assert project.siblings() == []

    # The stamp now records the content: touching the file again is a no-op ...
    project.clear_calls()
    project.make_requirements_newer()
    assert project.make().returncode == 0
    assert project.calls() == []
    # ... and changing it again rebuilds with a different stamp.
    project.set_requirements("alpha==3\n")
    assert project.make().returncode == 0
    assert any(c.startswith("pip-install") for c in project.calls())
    assert (project.venv / ".stamp").read_text(encoding="utf-8") != stamp


def test_rebuilt_venv_refers_to_its_final_path_not_the_build_directory(project):
    project.seed()
    project.set_requirements("alpha==2\n")
    assert project.make().returncode == 0
    final = str(project.venv)
    for name in ("tool", "activate"):
        text = (project.venv / "bin" / name).read_text(encoding="utf-8")
        assert final in text, f"bin/{name} must name the venv's real location"
        assert final + ".new" not in text, f"bin/{name} still names the build directory"
    assert final + ".new" not in (project.venv / "pyvenv.cfg").read_text(encoding="utf-8")


def test_venv_without_a_working_python_is_rebuilt_even_when_content_is_unchanged(project):
    project.seed()
    (project.venv / "bin" / "python").unlink()
    result = project.make()
    assert result.returncode == 0, result.stdout + result.stderr
    assert (project.venv / "bin" / "python").exists()
    assert any(c.startswith("pip-install") for c in project.calls())


@pytest.mark.parametrize(
    "flag", ["STUB_NO_PIP", "STUB_VENV_FAILS"],
    ids=["venv-created-without-pip", "venv-module-fails-no-ensurepip"],
)
def test_python_that_cannot_bootstrap_pip_falls_back_to_uv(project, flag):
    result = project.make(**{flag: "1"})
    assert result.returncode == 0, result.stdout + result.stderr
    calls = project.calls()
    assert any(c.startswith("uv-venv") for c in calls), calls
    assert any(c.startswith("uv-pip-install") for c in calls), calls
    assert (project.venv / "built-by").read_text(encoding="utf-8").strip() == "uv"
    assert project.siblings() == []
