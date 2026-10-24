#!/usr/bin/env python3
"""venv_holders.py - who is using a virtual environment right now, before it is rebuilt.

A venv rebuild moves the directory aside and builds a new one at the same path; a process that
runs from it keeps its open files but every new import, every spawned worker and every lease
release that runs `python` from it breaks. So the rebuild refuses while a holder exists.

Two sources, both on this machine:
  - allocator leases (scripts/lib/allocator.py `list --with-verdict`): a lease whose `python`
    lives under the venv. State `running` (a server or build is alive) REFUSES; `reserved` and
    `parked` WARN (their release or gc runs that python once more).
  - processes: the command line of every process (`ps -axww -o pid=,args=` on Linux and macOS -
    `exe` resolves to the base interpreter and finds nothing) holding the venv path (literal or
    realpath) and, on Linux, `/proc/<pid>/maps` mapping a file under `<venv>/lib/` (only this
    user's processes are readable). The caller's own process tree is excluded.

CLI:  venv_holders.py check <venv_dir> [--json] [--exclude-pid N ...]
      exit 0 no holder, 1 a refusing holder, 2 only warnings; prints one line per holder
      (HOLDER=<kind> <detail>) or the JSON {"refuse": [...], "warn": [...]}.
stdlib only; Python 3.8+.
"""
import json
import os
import subprocess
import sys

_LIB = os.path.dirname(os.path.abspath(__file__))
ALLOCATOR = os.path.join(_LIB, "allocator.py")
REFUSE_STATES = ("running",)
WARN_STATES = ("reserved", "parked", "orphaned", "reclaiming")


def _under(path, root):
    path = os.path.abspath(path)
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def _roots(venv_dir):
    literal = os.path.abspath(venv_dir)
    real = os.path.realpath(venv_dir)
    return {literal, real}


def lease_holders(venv_dir, env=None):
    """[(state, token_prefix, run_id, python, started_at)] for leases whose python is under venv_dir."""
    roots = _roots(venv_dir)
    try:
        proc = subprocess.run([sys.executable, ALLOCATOR, "list", "--with-verdict"], capture_output=True,
                              text=True, timeout=60, check=False, env=env)
        data = json.loads(proc.stdout or "{}")
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return []
    rows = data.get("leases") if isinstance(data, dict) else data
    out = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        python = (row.get("python") or row.get("venv_python") or "")
        if not python or not any(_under(python, r) for r in roots):
            continue
        verdict = row.get("verdict") if isinstance(row.get("verdict"), dict) else {}
        state = verdict.get("state") or row.get("state") or "unknown"
        owner = row.get("owner") if isinstance(row.get("owner"), dict) else {}
        out.append({"state": state, "token_prefix": (row.get("token") or row.get("token_prefix") or "")[:8],
                    "run_id": owner.get("run_id") or row.get("run_id") or "", "python": python,
                    "started_at": owner.get("started_at") or ""})
    return out


def _own_tree():
    pids = {os.getpid()}
    try:
        pids.add(os.getppid())
    except OSError:
        pass
    return pids


def process_holders(venv_dir, exclude=()):
    roots = _roots(venv_dir)
    skip = _own_tree() | set(int(p) for p in exclude)
    out = []
    try:
        ps = subprocess.run(["ps", "-axww", "-o", "pid=,args="], capture_output=True, text=True, timeout=30,
                            check=False).stdout
    except (OSError, subprocess.TimeoutExpired):
        ps = ""
    for line in ps.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) != 2 or not parts[0].isdigit():
            continue
        pid, args = int(parts[0]), parts[1]
        if pid in skip:
            continue
        if any(r in args for r in roots):
            out.append({"pid": pid, "command": args[:200], "via": "args"})
    if os.path.isdir("/proc"):
        seen = {h["pid"] for h in out}
        for name in os.listdir("/proc"):
            if not name.isdigit() or int(name) in skip or int(name) in seen:
                continue
            try:
                with open("/proc/%s/maps" % name, encoding="utf-8", errors="replace") as fh:
                    for line in fh:
                        p = line.split(None, 5)
                        if len(p) == 6 and any(_under(p[5].strip(), os.path.join(r, "lib")) for r in roots):
                            cmd = open("/proc/%s/cmdline" % name, "rb").read().replace(b"\0", b" ").decode("utf-8", "replace")
                            out.append({"pid": int(name), "command": cmd.strip()[:200], "via": "maps"})
                            break
            except OSError:
                continue
    return out


def holders(venv_dir, exclude=(), env=None):
    refuse, warn = [], []
    for lease in lease_holders(venv_dir, env=env):
        (refuse if lease["state"] in REFUSE_STATES else warn).append(dict(lease, kind="lease"))
    for proc in process_holders(venv_dir, exclude):
        refuse.append(dict(proc, kind="process"))
    return {"refuse": refuse, "warn": warn}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] != "check" or len(argv) < 2:
        print(__doc__)
        return 2
    venv_dir = argv[1]
    as_json = "--json" in argv
    exclude = []
    i = 2
    while i < len(argv):
        if argv[i] == "--exclude-pid" and i + 1 < len(argv):
            exclude.append(argv[i + 1]); i += 2
        else:
            i += 1
    result = holders(venv_dir, exclude)
    if as_json:
        print(json.dumps(result))
    else:
        for h in result["refuse"]:
            if h["kind"] == "lease":
                print("HOLDER=lease %s run=%s state=%s since=%s" % (h["token_prefix"], h["run_id"], h["state"], h["started_at"]))
            else:
                print("HOLDER=process pid=%d %s" % (h["pid"], h["command"]))
        for h in result["warn"]:
            print("WARN=lease %s run=%s state=%s" % (h["token_prefix"], h["run_id"], h["state"]))
    return 1 if result["refuse"] else (2 if result["warn"] else 0)


if __name__ == "__main__":
    sys.exit(main())
