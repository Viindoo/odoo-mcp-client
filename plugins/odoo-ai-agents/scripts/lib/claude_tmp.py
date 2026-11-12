#!/usr/bin/env python3
"""claude_tmp.py - move Claude Code's temp directory into the state root and keep it small.

Claude Code writes per-session working files (scratchpads, task output, images) and its
bash-edit-diff files under one temp root and never deletes any of them. The root is the
environment variable CLAUDE_CODE_TMPDIR when set, else the system temp directory (often
memory-backed); Claude Code appends `claude-<uid>` itself. This module owns the three halves of
the setup step `36-claude-tmpdir`:

  measure          KEY=VALUE facts and the decision (read-only)
  set <settings> <dir>
                   create <dir> with mode 0700 and merge env.CLAUDE_CODE_TMPDIR=<dir> into the
                   USER settings file (lock, backup, atomic replace). Exit 0 ok, 1 OS error,
                   2 refused (the file or its `env` is not a JSON object)
  sweep            delete what the managed directory (<state root>, subfolder `tmp`, then
                   `claude-<uid>`) holds and nobody touched for SWEEP_MAX_AGE_S. Never fails.

Only CLAUDE_CODE_TMPDIR is ever set: moving the variable every child process reads would move far
more than Claude Code's own files. The setting is honoured from the user settings file and the
launching shell, not from project or local settings, so only the user file is read and written.

Decision (`measure` ACTION): opted-out (ODOO_AI_NO_CLAUDE_TMP=1), set-in-environment,
set-in-settings (a user-set value is never changed, whatever it is), settings-invalid (the user
file cannot be edited safely) or propose.

Stdlib only; imports of the sibling libs are local so a SessionStart hook stays fast.
"""
import os
import re
import shutil
import sys

_LIB_DIR = os.path.dirname(os.path.abspath(__file__))
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
import config_merge  # noqa: E402  (lock, backup and atomic write shared by settings writers)
from claude_settings import config_dir_path, user_settings_path  # noqa: E402

ENV_NAME = "CLAUDE_CODE_TMPDIR"
OPT_OUT_ENV = "ODOO_AI_NO_CLAUDE_TMP"
# Test seam: a file in /proc/self/mountinfo format that replaces the real mount table.
MOUNTINFO_ENV = "ODOO_AI_MOUNTINFO"

TARGET_SUBDIR = "tmp"
EDIT_DIFF_DIR = "bash-edit-diff"
SWEEP_MAX_AGE_S = 30 * 24 * 3600

# Claude Code gives sandboxed shell children a short fallback temp dir when the per-uid root is
# longer than this many bytes (unix-socket path limit); its own files stay on the override.
SOCKET_PATH_LIMIT = 44

MEMORY_FILESYSTEMS = frozenset({"tmpfs", "ramfs"})


# --------------------------------------------------------------------------- #
# facts
# --------------------------------------------------------------------------- #
def state_root():
    import paths  # noqa: E402  (sibling lib; the one state-root resolver)
    return paths.state_root()


def target_dir(root=None):
    return os.path.join(root or state_root(), TARGET_SUBDIR)


def per_uid_dir(target):
    """The directory Claude Code creates under a temp root, or None where there is no uid."""
    getuid = getattr(os, "getuid", None)
    return os.path.join(target, "claude-%d" % getuid()) if getuid else None


def system_temp_root():
    """The system temp root as the standard library resolves it, without probing: the usual
    resolver writes a trial file into the directory, which fails on a full one - the very case
    this step exists for. Empty when it cannot be told."""
    try:
        import tempfile
        return tempfile._candidate_tempdir_list()[0]
    except Exception:
        return ""


def _mount_entries():
    path = os.environ.get(MOUNTINFO_ENV) or "/proc/self/mountinfo"
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return None
    entries = []
    for line in lines:
        head, sep, tail = line.partition(" - ")
        fields = head.split()
        if not sep or len(fields) < 5 or not tail.split():
            continue
        mount_point = re.sub(r"\\([0-7]{3})", lambda m: chr(int(m.group(1), 8)), fields[4])
        entries.append((mount_point, tail.split()[0]))
    return entries


def memory_backed(path):
    """'yes' / 'no' / 'unknown' for whether `path` lives on a memory filesystem (tmpfs, ramfs),
    from the mount table; unknown where there is no table or no path."""
    entries = _mount_entries()
    if not path or not entries:
        return "unknown"
    real = os.path.realpath(path)
    best = None
    for mount_point, fstype in entries:
        base = mount_point.rstrip("/")
        if real == mount_point or real.startswith(base + "/"):
            if best is None or len(mount_point) >= len(best[0]):
                best = (mount_point, fstype)
    if best is None:
        return "unknown"
    return "yes" if best[1] in MEMORY_FILESYSTEMS else "no"


def _read_settings(path):
    """(state, data): 'absent' ({}), 'ok' (the object), or 'invalid' (None) when the file is not
    a JSON object or its `env` is not an object."""
    import json
    if not os.path.exists(path):
        return "absent", {}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return "invalid", None
    if not isinstance(data, dict) or ("env" in data and not isinstance(data["env"], dict)):
        return "invalid", None
    return "ok", data


def measure(environ=None, settings_path=None):
    environ = os.environ if environ is None else environ
    settings_path = settings_path or user_settings_path(config_dir_path())
    target = target_dir()
    uid_dir = per_uid_dir(target)
    out = {"action": None, "settings_file": settings_path, "target": target}
    state, data = _read_settings(settings_path)
    in_env = environ.get(ENV_NAME) or ""
    in_settings = (data or {}).get("env", {}).get(ENV_NAME) if state == "ok" else None
    if environ.get(OPT_OUT_ENV) == "1":
        out["action"] = "opted-out"
    elif in_env:
        out["action"] = "set-in-environment"
    elif state == "ok" and ENV_NAME in data.get("env", {}):
        out["action"] = "set-in-settings"
    elif state == "invalid":
        out["action"] = "settings-invalid"
    else:
        out["action"] = "propose"
    effective = in_env or (in_settings if isinstance(in_settings, str) else "")
    if effective:
        out["current_value"] = effective
    root = effective or system_temp_root()
    out["current_temp_root"] = root
    out["current_temp_memory_backed"] = memory_backed(root)
    if uid_dir:
        out["per_uid_path"] = uid_dir
        out["per_uid_path_bytes"] = len(uid_dir.encode("utf-8"))
        out["sandbox_tmp_fallback"] = (
            "yes" if len(uid_dir.encode("utf-8")) > SOCKET_PATH_LIMIT else "no")
    out["socket_path_limit"] = SOCKET_PATH_LIMIT
    out["sweep_max_age_days"] = SWEEP_MAX_AGE_S // 86400
    return out


# --------------------------------------------------------------------------- #
# write
# --------------------------------------------------------------------------- #
def _ensure_private_dir(path):
    os.makedirs(path, mode=0o700, exist_ok=True)
    if hasattr(os, "getuid") and os.stat(path).st_uid != os.getuid():
        raise OSError("%s is not owned by this user" % path)
    os.chmod(path, 0o700)


def set_tmp_env(settings_path, target):
    """Merge env.CLAUDE_CODE_TMPDIR=<target> into one settings file; a value already there is
    never replaced. Prints RESULT=written|unchanged (+ BACKUP=)."""
    with config_merge.locked_target(settings_path):
        state, data = _read_settings(settings_path)
        if state == "invalid":
            print("refusing to edit %s: not a JSON object, or its env is not one" % settings_path,
                  file=sys.stderr)
            return 2
        if ENV_NAME in data.get("env", {}):
            print("RESULT=unchanged")
            return 0
        _ensure_private_dir(target)
        backup = config_merge._backup(settings_path) if state == "ok" else None
        data.setdefault("env", {})[ENV_NAME] = target
        config_merge._write_json(settings_path, data)
        print("RESULT=written")
        if backup:
            print("BACKUP=%s" % backup)
    return 0


# --------------------------------------------------------------------------- #
# sweep
# --------------------------------------------------------------------------- #
def _lmtime(path):
    try:
        return os.lstat(path).st_mtime
    except OSError:
        return None


def _entries(path):
    try:
        with os.scandir(path) as it:
            return list(it)
    except OSError:
        return []


def _is_real_dir(entry):
    try:
        return entry.is_dir(follow_symlinks=False)
    except OSError:
        return False


def newest_change(path):
    """When anything inside `path` last changed: the newest mtime of any file (a symlink counts as
    the link itself), or - when it holds no file - of any directory in it. Infinity when the tree
    cannot be read in full, so an unreadable session is never judged idle."""
    unreadable = []
    files, dirs = [], []
    for dirpath, dirnames, filenames in os.walk(path, onerror=unreadable.append):
        dirs.append(_lmtime(dirpath))
        for name in filenames + [d for d in dirnames if os.path.islink(os.path.join(dirpath, d))]:
            files.append(_lmtime(os.path.join(dirpath, name)))
    if unreadable:
        return float("inf")
    known = [t for t in (files or dirs) if t is not None]
    return max(known) if known else float("inf")


def _sweep_old_files(directory, cutoff):
    removed = 0
    for entry in _entries(directory):
        if _is_real_dir(entry):
            continue
        mtime = _lmtime(entry.path)
        if mtime is not None and mtime < cutoff:
            try:
                os.unlink(entry.path)
                removed += 1
            except OSError:
                pass
    return removed


def sweep(root=None, now=None, max_age_s=SWEEP_MAX_AGE_S):
    """Delete idle session directories and old bash-edit-diff files under the managed directory
    only. Returns (session directories, files) removed."""
    import time
    base = target_dir(root)
    uid_dir = per_uid_dir(base)
    if not uid_dir or os.path.islink(base) or os.path.islink(uid_dir) or not os.path.isdir(uid_dir):
        return 0, 0
    cutoff = (time.time() if now is None else now) - max_age_s
    sessions = files = 0
    for slug in _entries(uid_dir):
        if not _is_real_dir(slug):
            continue
        if slug.name == EDIT_DIFF_DIR:
            files += _sweep_old_files(slug.path, cutoff)
            continue
        removed_here = 0
        for session in _entries(slug.path):
            if _is_real_dir(session) and newest_change(session.path) < cutoff:
                shutil.rmtree(session.path, ignore_errors=True)
                removed_here += 0 if os.path.lexists(session.path) else 1
        sessions += removed_here
        slug_mtime = _lmtime(slug.path)
        if not _entries(slug.path) and (removed_here or (slug_mtime or cutoff) < cutoff):
            try:
                os.rmdir(slug.path)
            except OSError:
                pass
    return sessions, files


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv):
    if argv[:1] == ["measure"] and len(argv) == 1:
        for key, val in measure().items():
            print("%s=%s" % (key.upper(), val))
        return 0
    if argv[:1] == ["set"] and len(argv) == 3:
        try:
            return set_tmp_env(argv[1], argv[2])
        except OSError as exc:
            print("claude_tmp.py: %s" % exc, file=sys.stderr)
            return 1
    if argv[:1] == ["sweep"] and len(argv) == 1:
        try:
            sessions, files = sweep()
            if sessions or files:
                print("claude-tmp: removed %d idle session dir(s) and %d old file(s)"
                      % (sessions, files))
        except Exception:
            pass
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
