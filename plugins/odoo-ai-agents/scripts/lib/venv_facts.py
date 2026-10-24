#!/usr/bin/env python3
"""venv_facts.py - the facts and the safe moves of a venv rebuild (45-venv.sh create-venv).

Subcommands (stdlib only, Python 3.8+):
  row-plan <instances.toml> <series> <profile>
      JSON: python (the row's), venv_dir (the venv that python lives in, when
      <python>/../../pyvenv.cfg exists - a bare interpreter is never a rebuild target),
      shared_by (other rows whose python lives in the same venv), extra_requirements (list),
  rows-using <instances.toml> <venv_dir>
      The instance keys whose python lives in that venv (empty = nobody; a split row's old
      shared venv is removed then).
      uv_override (path or null), uv_override_basis (string or null), row_found (bool).
  aside <venv_dir>
      Journal `<venv_dir>.rebuild` (JSON: old path, epoch) then os.rename the directory to
      `<venv_dir>.rebuilding-<epoch>`; prints OLD=<path>. Refuses when a journal already exists
      (a previous rebuild never finished: run `reconcile`).
  restore <venv_dir>
      Remove a partial build at <venv_dir> (if any), os.rename the journaled old directory back
      (never nests: a surviving target is removed first), drop the journal.
  finish <venv_dir>
      Remove the journaled old directory, drop the journal. A failed removal is reported, not fatal.
  reconcile <venv_dir>
      A leftover journal (a kill, a timeout): when <venv_dir> has no working python, restore the
      old one; else report the stray `.rebuilding-*` directories. Prints what it did.
  basis <override_file> <requirements_file> ...
      The hash of the upstream requirement lines that name a package the override file pins -
      recorded with the override, so a later rebuild notices that an upstream pin moved.
  free-space <venv_dir>
      Prints FREE_BYTES=<n> NEED_BYTES=<size of venv_dir>; exit 1 when the free space is lower.
  with-lock <venv_dir> -- <command...>
      Runs the command holding an exclusive lock on `<venv_dir>.lock` (two rebuilds of one venv
      never interleave; macOS has no flock(1), so the lock is taken here).
  stale-comments <instances.toml>
      Prints STALE_COMMENT=<line no>: <text> for a `#` comment naming an absolute path that does
      not exist; exit 2 when any, 0 otherwise.
  lint-extras <addons dir> ...
      Prints SUGGESTED_EXTRA=<dist> for a lint package an addon's tests import optionally
      (pylint-odoo, flake8) - the shape _install_test_deps solves for the core test framework.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time

try:
    import fcntl
except ImportError:  # Windows
    fcntl = None

_LIB = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _LIB)
import instances_io  # noqa: E402

JOURNAL_SUFFIX = ".rebuild"
ASIDE_SUFFIX = ".rebuilding-"
LINT_DISTS = {"pylint_odoo": "pylint-odoo", "pylint": "pylint", "flake8": "flake8"}
_IMPORT_RE = re.compile(r"^\s*(?:from|import)\s+(pylint_odoo|pylint|flake8)\b", re.M)
_REQ_NAME_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def venv_dir_of(python):
    """The venv directory of an interpreter path, or None when it is not inside a venv."""
    if not python:
        return None
    cand = os.path.dirname(os.path.dirname(os.path.abspath(python)))
    return cand if os.path.isfile(os.path.join(cand, "pyvenv.cfg")) else None


def rows_using(path, venv_dir):
    """The instance keys of every row whose python lives in `venv_dir` (the shared venv a split
    row left: removed once this is empty)."""
    try:
        items = instances_io.load_instances(path)
    except FileNotFoundError:
        return []
    target = os.path.abspath(venv_dir)
    return [instances_io.instance_key_of(row) for row in items
            if venv_dir_of(str(row.get("python") or "")) == target]


def row_plan(path, series, profile):
    try:
        items = instances_io.load_instances(path)
    except FileNotFoundError:
        items = []
    row = instances_io.select_row(items, series, profile)[0] if items else None
    out = {"row_found": row is not None, "python": "", "venv_dir": None, "shared_by": [],
           "extra_requirements": [], "uv_override": None, "uv_override_basis": None, "build_tool": None}
    if row is None:
        return out
    python = str(row.get("python") or "")
    out["python"] = python
    out["venv_dir"] = venv_dir_of(python)
    extras = row.get("extra_requirements")
    if isinstance(extras, list):
        out["extra_requirements"] = [str(e) for e in extras if str(e).strip()]
    elif isinstance(extras, str) and extras.strip():
        out["extra_requirements"] = [extras.strip()]
    out["uv_override"] = str(row["uv_override"]) if row.get("uv_override") else None
    out["build_tool"] = str(row["build_tool"]).strip() if row.get("build_tool") else None
    out["uv_override_basis"] = str(row["uv_override_basis"]) if row.get("uv_override_basis") else None
    if out["venv_dir"]:
        for other in items:
            if other is row:
                continue
            if venv_dir_of(str(other.get("python") or "")) == out["venv_dir"]:
                out["shared_by"].append(instances_io.instance_key_of(other))
    return out


def _journal(venv_dir):
    return os.path.abspath(venv_dir).rstrip(os.sep) + JOURNAL_SUFFIX


def cmd_aside(venv_dir):
    venv_dir = os.path.abspath(venv_dir).rstrip(os.sep)
    journal = _journal(venv_dir)
    if os.path.exists(journal):
        print("x a previous rebuild of %s never finished (%s exists): run `venv_facts.py reconcile %s` first"
              % (venv_dir, journal, venv_dir), file=sys.stderr)
        return 1
    if not os.path.isdir(venv_dir):
        print("OLD=")
        return 0
    epoch = int(time.time())
    old = "%s%s%d" % (venv_dir, ASIDE_SUFFIX, epoch)
    with open(journal, "w", encoding="utf-8") as fh:
        json.dump({"venv": venv_dir, "old": old, "epoch": epoch}, fh)
    os.rename(venv_dir, old)
    print("OLD=%s" % old)
    return 0


def _read_journal(venv_dir):
    journal = _journal(venv_dir)
    if not os.path.exists(journal):
        return None
    with open(journal, encoding="utf-8") as fh:
        return json.load(fh)


def cmd_restore(venv_dir):
    venv_dir = os.path.abspath(venv_dir).rstrip(os.sep)
    entry = _read_journal(venv_dir)
    if entry is None:
        print("x no journal for %s - nothing to restore" % venv_dir, file=sys.stderr)
        return 1
    if os.path.isdir(venv_dir):
        shutil.rmtree(venv_dir, ignore_errors=True)
    if os.path.isdir(entry["old"]):
        os.rename(entry["old"], venv_dir)
    os.unlink(_journal(venv_dir))
    print("RESTORED=%s" % venv_dir)
    return 0


def cmd_finish(venv_dir):
    venv_dir = os.path.abspath(venv_dir).rstrip(os.sep)
    entry = _read_journal(venv_dir)
    if entry is None:
        return 0
    rc = 0
    if os.path.isdir(entry["old"]):
        try:
            shutil.rmtree(entry["old"])
            print("REMOVED=%s" % entry["old"])
        except OSError as exc:
            print("  Warning: the old venv could not be removed (%s): remove %s by hand" % (exc, entry["old"]), file=sys.stderr)
            rc = 0
    os.unlink(_journal(venv_dir))
    return rc


def cmd_reconcile(venv_dir):
    venv_dir = os.path.abspath(venv_dir).rstrip(os.sep)
    entry = _read_journal(venv_dir)
    if entry is not None:
        python = os.path.join(venv_dir, "bin", "python")
        if not os.access(python, os.X_OK):
            cmd_restore(venv_dir)
            print("RECONCILED=restored the old venv (the interrupted build left no working python)")
        else:
            print("RECONCILED=kept the new venv; the old one is still at %s - remove it when the new one is proven"
                  % entry["old"])
            os.unlink(_journal(venv_dir))
    parent = os.path.dirname(venv_dir)
    base = os.path.basename(venv_dir) + ASIDE_SUFFIX
    strays = sorted(os.path.join(parent, n) for n in os.listdir(parent) if n.startswith(base)) if os.path.isdir(parent) else []
    for s in strays:
        print("STRAY=%s" % s)
    return 0


def basis(override_file, requirement_files):
    names = set()
    with open(override_file, encoding="utf-8") as fh:
        for line in fh:
            m = _REQ_NAME_RE.match(line)
            if m and not line.lstrip().startswith("#"):
                names.add(m.group(1).lower().replace("_", "-"))
    lines = []
    for req in requirement_files:
        try:
            with open(req, encoding="utf-8") as fh:
                for line in fh:
                    m = _REQ_NAME_RE.match(line)
                    if m and m.group(1).lower().replace("_", "-") in names:
                        lines.append("%s:%s" % (os.path.basename(req), line.strip()))
        except OSError:
            continue
    return hashlib.sha256("\n".join(sorted(lines)).encode("utf-8")).hexdigest()[:16]


def cmd_free_space(venv_dir):
    venv_dir = os.path.abspath(venv_dir)
    need = 0
    if os.path.isdir(venv_dir):
        for root, _dirs, files in os.walk(venv_dir):
            for f in files:
                try:
                    need += os.lstat(os.path.join(root, f)).st_size
                except OSError:
                    pass
    parent = os.path.dirname(venv_dir)
    while parent and not os.path.isdir(parent):
        parent = os.path.dirname(parent)
    st = os.statvfs(parent or "/")
    free = st.f_bavail * st.f_frsize
    print("FREE_BYTES=%d" % free)
    print("NEED_BYTES=%d" % need)
    return 0 if free >= need else 1


def cmd_with_lock(venv_dir, command):
    lock_path = os.path.abspath(venv_dir).rstrip(os.sep) + ".lock"
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        if fcntl is not None:
            fcntl.flock(fd, fcntl.LOCK_EX)
        return subprocess.call(command)
    finally:
        if fcntl is not None:
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def stale_comments(path):
    """The lines cmd_stale_comments prints, as a list (the registry review reads them)."""
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cmd_stale_comments(path)
    return [line for line in buf.getvalue().splitlines() if line.strip()]


def cmd_stale_comments(path):
    found = 0
    try:
        with open(path, encoding="utf-8") as fh:
            for no, line in enumerate(fh, 1):
                if "#" not in line:
                    continue
                comment = line.split("#", 1)[1]
                for token in re.findall(r"(?:~|\$HOME)?/[^\s'\"`,;)]+", comment):
                    expanded = os.path.expanduser(token.replace("$HOME", "~"))
                    if expanded.startswith("/") and not os.path.exists(expanded):
                        print("STALE_COMMENT=%d: %s" % (no, line.strip()))
                        found += 1
                        break
    except OSError as exc:
        print("x %s: %s" % (path, exc), file=sys.stderr)
        return 1
    return 2 if found else 0


def cmd_lint_extras(dirs):
    dists = set()
    for d in dirs:
        for root, _dirs, files in os.walk(d):
            if os.path.basename(root) != "tests":
                continue
            for f in files:
                if not (f.startswith("test_") and f.endswith(".py")):
                    continue
                try:
                    with open(os.path.join(root, f), encoding="utf-8", errors="replace") as fh:
                        for m in _IMPORT_RE.finditer(fh.read()):
                            dists.add(LINT_DISTS[m.group(1)])
                except OSError:
                    continue
    for dist in sorted(dists):
        print("SUGGESTED_EXTRA=%s" % dist)
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd == "row-plan" and len(rest) == 3:
        print(json.dumps(row_plan(rest[0], rest[1], rest[2])))
        return 0
    if cmd == "rows-using" and len(rest) == 2:
        print(" ".join(rows_using(rest[0], rest[1])))
        return 0
    if cmd == "aside" and len(rest) == 1:
        return cmd_aside(rest[0])
    if cmd == "restore" and len(rest) == 1:
        return cmd_restore(rest[0])
    if cmd == "finish" and len(rest) == 1:
        return cmd_finish(rest[0])
    if cmd == "reconcile" and len(rest) == 1:
        return cmd_reconcile(rest[0])
    if cmd == "basis" and len(rest) >= 1:
        print("BASIS=%s" % basis(rest[0], rest[1:]))
        return 0
    if cmd == "free-space" and len(rest) == 1:
        return cmd_free_space(rest[0])
    if cmd == "with-lock" and len(rest) >= 3 and rest[1] == "--":
        return cmd_with_lock(rest[0], rest[2:])
    if cmd == "stale-comments" and len(rest) == 1:
        return cmd_stale_comments(rest[0])
    if cmd == "lint-extras" and rest:
        return cmd_lint_extras(rest)
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
