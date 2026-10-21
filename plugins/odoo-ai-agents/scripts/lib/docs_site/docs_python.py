#!/usr/bin/env python3
"""docs_python.py - which Python a Sphinx docs repo builds on, and the venv made from it.

  docs_python.py facts --worktree W [--json]
  docs_python.py venv  --worktree W --venv V [--requirements R] [--json]

`facts` reads (never executes) what the repo states about its Python, strongest source first:

  .python-version, runtime.txt, .tool-versions        a pinned version
  .readthedocs.y(a)ml                                 build.tools.python / python.version
  .github/workflows/*.y(a)ml, .gitlab-ci.yml,
  .circleci/config.yml, .travis.yml, tox.ini,
  Dockerfile*                                         the version the CI or image runs
  pyproject.toml, setup.cfg, setup.py                 requires-python / python_requires (a RANGE)
  README*                                             "Python 3.8", "Python 3.7 or 3.8" (prose, last)

Report keys: `stated` (ordered entries `{kind: version|range, value, source}`) and `python` (the
first stated version, else the string "UNKNOWN" - a fact the repo does not state is never guessed).

`venv` builds the docs venv with `uv`, trying interpreters in this order, each one a real attempt
(create the venv, install the requirements into it) until one installs them:

  1. the versions `facts` reports, in order (a range expands to the available minors it admits,
     newest first);
  2. then every other stable CPython minor `uv` can provide, newest first.

A failed attempt is recorded (`interpreter-unavailable` or `requirements-failed`) and the next one
runs; nothing is hardcoded, so a new Python release is tried first without an edit here.
Every attempt is built in the sibling `<venv>.new` and swapped in only once it installed the
requirements, so a rebuild that fails everywhere leaves an existing venv as it was. An existing
`--venv` path with no `pyvenv.cfg` is not a virtualenv and is refused (exit 2), never cleared.
Report keys: `ok`, `python` (the venv interpreter), `version`, `source` (`stated:<file>` or
`newest-installing`), `tried` (each attempt and why it failed).
Exit: `facts` 0, 2 (worktree is not a directory); `venv` 0 (a venv was built), 2 (also: --venv
exists and is not a virtualenv), 3 (no interpreter installs the requirements), 4 (uv missing).
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from docs_site import UNKNOWN, emit, read_text  # noqa: E402

_VER = r"(\d+\.\d+)(?:\.\d+)?"
INSTALL_TIMEOUT_S = 1800
VENV_TIMEOUT_S = 600


def _minor(text):
    m = re.match(r"\s*v?%s" % _VER, text or "")
    return m.group(1) if m else None


def _versions(*values):
    out = []
    for value in values:
        minor = _minor(value)
        if minor and minor not in out:
            out.append(minor)
    return out


def _newest_first(versions):
    return sorted(set(versions), key=lambda v: tuple(int(p) for p in v.split(".")), reverse=True)


# --------------------------------------------------------------------------- readers

def _pinned_files(worktree):
    """(source, [versions]) from the files that pin one interpreter."""
    text = read_text(os.path.join(worktree, ".python-version"))
    if text is not None:
        lines = [ln.split("#", 1)[0].strip() for ln in text.splitlines()]
        yield ".python-version", _newest_first(v for ln in lines for v in _versions(*ln.split()))
    text = read_text(os.path.join(worktree, "runtime.txt"))
    if text is not None:
        yield "runtime.txt", _versions(*re.findall(r"python-%s" % _VER, text, re.I))
    text = read_text(os.path.join(worktree, ".tool-versions"))
    if text is not None:
        yield ".tool-versions", _versions(*re.findall(r"^python\s+%s" % _VER, text, re.M))


def _readthedocs(worktree):
    for name in (".readthedocs.yaml", ".readthedocs.yml"):
        text = read_text(os.path.join(worktree, name))
        if text is None:
            continue
        found = re.findall(r"^\s+python:\s*[\"']?%s" % _VER, text, re.M)
        found += re.findall(r"^python:\s*\n(?:[ \t]+.*\n)*?[ \t]+version:\s*[\"']?%s" % _VER, text, re.M)
        yield name, _versions(*found)


def _ci_files(worktree):
    """The interpreter versions a CI config or an image names."""
    paths = sorted(glob.glob(os.path.join(worktree, ".github", "workflows", "*.y*ml")))
    for name in (".gitlab-ci.yml", ".circleci/config.yml", ".travis.yml", "tox.ini"):
        paths.append(os.path.join(worktree, name))
    paths += sorted(glob.glob(os.path.join(worktree, "Dockerfile*")))
    for path in paths:
        text = read_text(path)
        if text is None:
            continue
        found = []
        # `python-version: 3.11`, `python-version: ["3.10", "3.11"]`, or a block list under it
        # (a GitHub matrix); a Travis `python:` block list.
        for m in re.finditer(r"(?:python-version|^python):[ \t]*(.*)\n((?:[ \t]*-[ \t]*.*\n)*)", text, re.M):
            if m.group(1).strip():
                found += re.findall(_VER, m.group(1))
            else:  # a block list: only entries that are a bare version count
                found += re.findall(r"^[ \t]*-[ \t]*[\"']?%s[\"']?[ \t]*$" % _VER, m.group(2), re.M)
        found += re.findall(r"\bpython:%s" % _VER, text)                 # image: python:3.11, FROM python:3.11
        found += ["%s.%s" % ab for ab in re.findall(r"\bpy(3)(\d{1,2})\b", text)]  # tox: py311
        yield os.path.relpath(path, worktree), _versions(*found)


_SPEC = re.compile(r"(>=|<=|==|~=|!=|>|<)\s*%s" % _VER)


def _ranges(worktree):
    for name, pattern in (("pyproject.toml", r"requires-python\s*=\s*[\"']([^\"']+)[\"']"),
                          ("setup.cfg", r"python_requires\s*=\s*(.+)"),
                          ("setup.py", r"python_requires\s*=\s*[\"']([^\"']+)[\"']")):
        text = read_text(os.path.join(worktree, name))
        m = re.search(pattern, text) if text is not None else None
        if m and _SPEC.search(m.group(1)):
            yield name, m.group(1).strip()


def _readme(worktree):
    for path in sorted(glob.glob(os.path.join(worktree, "README*"))):
        text = read_text(path)
        if text is None:
            continue
        found = []
        for m in re.finditer(r"\bPython\s+(%s(?:\s*(?:,|/|or|and|to|-)\s*%s)*)" % (_VER, _VER), text):
            found += re.findall(_VER, m.group(1))
        if found:
            yield os.path.basename(path), _versions(*found)
            return


def collect(worktree):
    stated = []
    for producer in (_pinned_files, _readthedocs, _ci_files):
        for source, versions in producer(worktree):
            for version in _newest_first(versions):
                stated.append({"kind": "version", "value": version, "source": source})
    for source, spec in _ranges(worktree):
        stated.append({"kind": "range", "value": spec, "source": source})
    for source, versions in _readme(worktree):
        for version in _newest_first(versions):
            stated.append({"kind": "version", "value": version, "source": source})
    first = next((s for s in stated if s["kind"] == "version"), None)
    return {"stated": stated, "python": first["value"] if first else UNKNOWN,
            "source": first["source"] if first else UNKNOWN}


def admits(spec, version):
    """True when the X.Y `version` satisfies the comma-separated specifier `spec` (>=, >, <=, <,
    ==, !=, ~= on X.Y)."""
    key = tuple(int(p) for p in version.split("."))
    for op, ver in _SPEC.findall(spec):
        want = tuple(int(p) for p in ver.split("."))
        ok = {">=": key >= want, ">": key > want, "<=": key <= want, "<": key < want,
              "==": key == want, "!=": key != want,
              "~=": want <= key < (want[0] + 1, 0)}[op]
        if not ok:
            return False
    return True


# --------------------------------------------------------------------------- venv

def available_minors(uv="uv"):
    """Stable CPython minors `uv` can provide (installed or downloadable), newest first."""
    try:
        res = subprocess.run([uv, "python", "list", "--output-format", "json"], capture_output=True,
                             text=True, timeout=120)
        entries = json.loads(res.stdout) if res.returncode == 0 else []
    except (OSError, subprocess.SubprocessError, ValueError):
        entries = []
    minors = []
    for entry in entries:
        version = entry.get("version") or ""
        if (entry.get("implementation") == "cpython" and entry.get("variant") == "default"
                and re.fullmatch(r"\d+\.\d+\.\d+", version)):
            minors.append(".".join(version.split(".")[:2]))
    return _newest_first(minors)


def plan(stated, available):
    """The ordered (version, source) attempts: the stated versions (a range expands to what it
    admits), then every other available minor newest first."""
    order, seen = [], set()

    def add(version, source):
        if version not in seen:
            seen.add(version)
            order.append((version, source))

    for entry in stated:
        source = "stated:%s" % entry["source"]
        if entry["kind"] == "version":
            add(entry["value"], source)
        else:
            for version in available:
                if admits(entry["value"], version):
                    add(version, source)
    for version in available:
        add(version, "newest-installing")
    return order


def _run(argv, timeout):
    try:
        res = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, "timed out after %ss" % timeout
    except OSError as exc:
        return 127, str(exc)
    return res.returncode, (res.stderr or res.stdout or "").strip()[-400:]


def venv_refusal(venv):
    """Why `venv` may not be built over, else None. An existing path that is not a virtualenv
    (no pyvenv.cfg) is somebody's directory: replacing it would destroy it."""
    if os.path.lexists(venv) and not os.path.isfile(os.path.join(venv, "pyvenv.cfg")):
        return "%s exists and is not a virtualenv (no pyvenv.cfg); it was not touched" % venv
    return None


def _repoint(tree, built_at, final):
    """Rewrite the path a venv was built at to the path it will live at, in every regular text
    file under bin/ and in pyvenv.cfg (script shebangs, activate scripts). The sibling's bare
    name is rewritten too, so the shell prompt does not carry the staging suffix."""
    swaps = [(built_at.encode(), final.encode()),
             (os.path.basename(built_at).encode(), os.path.basename(final).encode())]
    names = [os.path.join(tree, "pyvenv.cfg")]
    bindir = os.path.join(tree, "bin")
    if os.path.isdir(bindir):
        names += [os.path.join(bindir, n) for n in sorted(os.listdir(bindir))]
    for name in names:
        if os.path.islink(name) or not os.path.isfile(name):
            continue
        with open(name, "rb") as fh:
            data = fh.read()
        if b"\0" in data:
            continue
        out = data
        for src, dst in swaps:
            out = out.replace(src, dst)
        if out != data:
            with open(name, "wb") as fh:
                fh.write(out)


def _swap_in(built, venv):
    """Put `built` at `venv`, keeping the previous venv until the move has succeeded. Both paths
    are siblings, so each step is a rename on one filesystem."""
    old = venv + ".old"
    shutil.rmtree(old, ignore_errors=True)
    had = os.path.lexists(venv)
    if had:
        os.rename(venv, old)
    try:
        os.rename(built, venv)
    except OSError:
        if had:
            os.rename(old, venv)
        raise
    shutil.rmtree(old, ignore_errors=True)


def build_venv(worktree, venv, requirements, uv="uv"):
    """Build the docs venv. Every attempt is made in the sibling `<venv>.new` (same filesystem,
    never a temp dir) and only a venv that installed the requirements is swapped into place, so a
    rebuild that fails everywhere leaves the existing venv exactly as it was."""
    refused = venv_refusal(venv)
    if refused:
        return {"ok": False, "python": None, "version": None, "source": None, "tried": [],
                "refused": refused}
    venv = os.path.abspath(venv)
    staging = venv + ".new"
    old = venv + ".old"
    if not os.path.lexists(venv) and os.path.isdir(old):
        os.rename(old, venv)  # a run that died between its two renames
    tried = []
    attempts = plan(collect(worktree)["stated"], available_minors(uv))
    try:
        for version, source in attempts:
            shutil.rmtree(staging, ignore_errors=True)
            rc, tail = _run([uv, "venv", "--clear", "--python", version, staging], VENV_TIMEOUT_S)
            if rc != 0:
                tried.append({"version": version, "source": source,
                              "failed": "interpreter-unavailable", "detail": tail})
                continue
            rc, tail = _run([uv, "pip", "install", "--python", os.path.join(staging, "bin", "python"),
                             "-r", requirements], INSTALL_TIMEOUT_S)
            if rc != 0:
                tried.append({"version": version, "source": source, "failed": "requirements-failed",
                              "detail": tail})
                continue
            _repoint(staging, staging, venv)
            _swap_in(staging, venv)
            return {"ok": True, "python": os.path.join(venv, "bin", "python"), "version": version,
                    "source": source, "tried": tried}
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return {"ok": False, "python": None, "version": None, "source": None, "tried": tried}


def main(argv=None):
    ap = argparse.ArgumentParser(description="The Python a Sphinx docs repo builds on.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("facts", "venv"):
        p = sub.add_parser(name)
        p.add_argument("--worktree", required=True)
        p.add_argument("--json", action="store_true")
        if name == "venv":
            p.add_argument("--venv", required=True)
            p.add_argument("--requirements")
    args = ap.parse_args(argv)
    if not os.path.isdir(args.worktree):
        sys.stderr.write("worktree is not a directory: %s\n" % args.worktree)
        return 2
    if args.cmd == "facts":
        report = collect(args.worktree)
        lines = ["python: %s (%s)" % (report["python"], report["source"])]
        lines += ["stated: %s %s (%s)" % (s["kind"], s["value"], s["source"]) for s in report["stated"]]
        emit(report, args.json, lines)
        return 0
    requirements = args.requirements or os.path.join(args.worktree, "requirements.txt")
    if not os.path.isfile(requirements):
        sys.stderr.write("requirements file not found: %s\n" % requirements)
        return 2
    refused = venv_refusal(args.venv)
    if refused:
        sys.stderr.write(refused + "\n")
        return 2
    if shutil.which("uv") is None:
        sys.stderr.write("uv is not installed\n")
        return 4
    report = build_venv(args.worktree, args.venv, requirements)
    if report.get("refused"):
        sys.stderr.write(report["refused"] + "\n")
        return 2
    lines = ["DOCS PYTHON: %s (%s, %s)" % (report["python"], report["version"], report["source"])
             if report["ok"] else "no interpreter installs %s" % requirements]
    lines += ["tried %s (%s): %s" % (t["version"], t["source"], t["failed"]) for t in report["tried"]]
    emit(report, args.json, lines)
    return 0 if report["ok"] else 3


if __name__ == "__main__":
    sys.exit(main())
