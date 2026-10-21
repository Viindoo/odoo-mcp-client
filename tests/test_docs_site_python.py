"""Behavior tests for scripts/lib/docs_site/docs_python.py - which Python a docs repo builds on.

A docs repo pins old packages (a libsass that does not build on the newest Python), so the venv
must come from the interpreter the repo itself names, and when it names none, from the newest
interpreter that really installs its requirements. Each test builds a fake docs repo that makes
one statement and a stub `uv` that can create a venv for some versions and install the
requirements on a subset of those, then asserts which interpreter the venv ended up on.

Run with: python3 -m pytest tests/test_docs_site_python.py -q
"""
import json
import stat
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "lib"
sys.path.insert(0, str(LIB))

from docs_site import docs_python  # noqa: E402

SCRIPT = LIB / "docs_site" / "docs_python.py"


def write(root, rel, text):
    path = Path(root) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "docs"
    write(root, "requirements.txt", "libsass==0.18.0\n")
    return root


def facts(root):
    return docs_python.collect(str(root))


# ------------------------------------------------------------------ what the repo states

def test_a_pinned_version_file_names_the_python(repo):
    write(repo, ".python-version", "3.11.4\n")
    assert facts(repo)["python"] == "3.11" and facts(repo)["source"] == ".python-version"


def test_a_ci_matrix_and_the_runtime_config_are_read_as_stated_versions(repo):
    write(repo, ".github/workflows/docs.yml", textwrap.dedent("""\
        jobs:
          build:
            strategy:
              matrix:
                python-version: ["3.9", "3.10"]
            steps:
              - uses: actions/setup-python@v4.7
              - uses: actions/checkout@v3.1
        """))
    write(repo, ".readthedocs.yaml", 'build:\n  tools:\n    python: "3.12"\n')
    got = facts(repo)
    values = [(s["value"], s["source"]) for s in got["stated"]]
    assert ("3.12", ".readthedocs.yaml") in values
    assert ("3.10", ".github/workflows/docs.yml") in values and ("3.9", ".github/workflows/docs.yml") in values
    assert not any(v in ("4.7", "3.1") for v, _ in values), "an action's own version is not a Python"
    assert got["python"] == "3.12", "the runtime config outranks the CI matrix"


def test_readme_prose_is_the_weakest_source_and_a_range_is_kept_as_a_range(repo):
    write(repo, "README.md", "Requirements:\n- Python 3.7 or 3.8\n")
    got = facts(repo)
    assert [s["value"] for s in got["stated"]] == ["3.8", "3.7"] and got["python"] == "3.8"
    write(repo, ".python-version", "3.10\n")
    assert facts(repo)["python"] == "3.10"
    write(repo, "pyproject.toml", '[project]\nrequires-python = ">=3.8,<3.12"\n')
    assert {"kind": "range", "value": ">=3.8,<3.12", "source": "pyproject.toml"} in facts(repo)["stated"]


def test_a_repo_that_states_nothing_is_unknown_never_guessed(repo):
    got = facts(repo)
    assert got["python"] == "UNKNOWN" and got["stated"] == []


# ------------------------------------------------------------------ the venv

@pytest.fixture
def uv(tmp_path):
    """A stub uv. Behaviour is data in files: available.json (what `uv python list` offers),
    no_interpreter (versions `uv venv` cannot create), breaks (versions the requirements do not
    install on); calls.log records each venv/pip call."""
    state = tmp_path / "uvstate"
    state.mkdir()
    (state / "available.json").write_text("[]")
    (state / "no_interpreter").write_text("")
    (state / "breaks").write_text("")
    stub = tmp_path / "uv"
    stub.write_text(textwrap.dedent("""\
        #!/usr/bin/env bash
        S="%s"
        case "$1" in
          python) cat "$S/available.json" ;;
          venv)   # uv venv --clear --python V DIR
                  v="$4"; d="$5"; echo "venv $v" >> "$S/calls.log"
                  grep -qx "$v" "$S/no_interpreter" && { echo "no interpreter $v" >&2; exit 2; }
                  mkdir -p "$d/bin"; echo "$v" > "$d/bin/python" ;;
          pip)    # uv pip install --python PY -r REQ
                  v="$(cat "$4")"; echo "pip $v" >> "$S/calls.log"
                  grep -qx "$v" "$S/breaks" && { echo "libsass failed on $v" >&2; exit 1; }
                  exit 0 ;;
        esac
        """ % state))
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)

    class Uv:
        path = str(stub)

        @staticmethod
        def offer(*minors):
            (state / "available.json").write_text(json.dumps(
                [{"implementation": "cpython", "variant": "default", "version": m + ".1"}
                 for m in minors] +
                [{"implementation": "cpython", "variant": "freethreaded", "version": "3.99.0"},
                 {"implementation": "cpython", "variant": "default", "version": "3.99.0a1"}]))

        @staticmethod
        def cannot_create(*versions):
            (state / "no_interpreter").write_text("\n".join(versions) + "\n")

        @staticmethod
        def breaks_on(*versions):
            (state / "breaks").write_text("\n".join(versions) + "\n")

        @staticmethod
        def calls():
            f = state / "calls.log"
            return f.read_text().splitlines() if f.exists() else []

    return Uv


def build(repo, tmp_path, uv):
    return docs_python.build_venv(str(repo), str(tmp_path / "venv"), str(repo / "requirements.txt"),
                                  uv=uv.path)


def test_the_venv_uses_the_python_the_repo_states_not_the_newest(repo, tmp_path, uv):
    """The failure this guards: a bare `uv venv` picked the newest Python, on which the docs
    requirements do not build."""
    write(repo, ".python-version", "3.11\n")
    uv.offer("3.14", "3.13", "3.12", "3.11")
    uv.breaks_on("3.14", "3.13", "3.12")
    got = build(repo, tmp_path, uv)
    assert got["ok"] and got["version"] == "3.11" and got["source"] == "stated:.python-version"
    assert uv.calls() == ["venv 3.11", "pip 3.11"], "the newest Python is not even tried"


def test_with_nothing_stated_the_newest_interpreter_that_installs_the_requirements_wins(repo, tmp_path, uv):
    uv.offer("3.11", "3.14", "3.12", "3.13")
    uv.breaks_on("3.14", "3.13")
    got = build(repo, tmp_path, uv)
    assert got["ok"] and got["version"] == "3.12" and got["source"] == "newest-installing"
    assert [(t["version"], t["failed"]) for t in got["tried"]] == [
        ("3.14", "requirements-failed"), ("3.13", "requirements-failed")]
    assert "libsass failed on 3.14" in got["tried"][0]["detail"]
    assert (tmp_path / "venv" / "bin" / "python").read_text().strip() == "3.12"


def test_a_stated_python_that_cannot_be_had_or_cannot_install_falls_back_to_older_ones(repo, tmp_path, uv):
    write(repo, "README.md", "Python 3.7 or 3.8\n")
    uv.offer("3.13", "3.10", "3.9", "3.8")
    uv.cannot_create("3.7")
    uv.breaks_on("3.8", "3.13")
    got = build(repo, tmp_path, uv)
    assert got["ok"] and got["version"] == "3.10", "stated 3.8 failed, so the newest that installs"
    assert [(t["version"], t["failed"]) for t in got["tried"]] == [
        ("3.8", "requirements-failed"), ("3.7", "interpreter-unavailable"), ("3.13", "requirements-failed")]


def test_a_stated_range_expands_to_the_available_versions_it_admits_newest_first(repo, tmp_path, uv):
    write(repo, "pyproject.toml", '[project]\nrequires-python = ">=3.8,<3.12"\n')
    uv.offer("3.14", "3.12", "3.11", "3.9", "3.7")
    got = build(repo, tmp_path, uv)
    assert got["ok"] and got["version"] == "3.11" and got["source"] == "stated:pyproject.toml"
    assert uv.calls() == ["venv 3.11", "pip 3.11"]


def test_no_interpreter_installing_the_requirements_is_a_failure_that_lists_every_attempt(repo, tmp_path, uv):
    uv.offer("3.13", "3.12")
    uv.breaks_on("3.13", "3.12")
    got = build(repo, tmp_path, uv)
    assert got["ok"] is False and got["python"] is None
    assert [t["version"] for t in got["tried"]] == ["3.13", "3.12"]


def test_the_cli_reports_the_python_and_exits_3_when_none_installs(repo, tmp_path, uv, monkeypatch):
    uv.offer("3.12")
    uv.breaks_on("3.12")
    monkeypatch.setenv("PATH", str(Path(uv.path).parent) + ":" + __import__("os").environ["PATH"])
    res = subprocess.run([sys.executable, str(SCRIPT), "venv", "--worktree", str(repo), "--venv",
                          str(tmp_path / "v"), "--json"], capture_output=True, text=True)
    assert res.returncode == 3 and json.loads(res.stdout)["ok"] is False
    uv.breaks_on()
    res = subprocess.run([sys.executable, str(SCRIPT), "venv", "--worktree", str(repo), "--venv",
                          str(tmp_path / "v"), "--json"], capture_output=True, text=True)
    assert res.returncode == 0 and json.loads(res.stdout)["version"] == "3.12"
