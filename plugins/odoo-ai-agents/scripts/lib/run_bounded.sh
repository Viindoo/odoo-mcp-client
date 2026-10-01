# run_bounded.sh - SOURCED helper: run a command under a wall-clock bound on every host.
#
# `timeout` is GNU coreutils, not POSIX: stock macOS has none (Homebrew's coreutils installs it as
# `gtimeout`). A bare `timeout 5 cmd` there fails with "command not found" before cmd ever runs,
# and behind `|| true` that silently turns the call into a no-op - a gate that never checks, a
# reclaim that never runs. Hooks and scripts bound a command through `run_bounded` instead.
#
#   run_bounded <seconds> <cmd> [args...]
#
# Ladder: `timeout`, else `gtimeout`, else a python3 stdlib bound (the child runs in its own
# session and the whole group is killed when the bound elapses), else the command runs unbounded
# (a host with no python3 cannot run the plugin's python commands either).
# Exit: the command's own status; 124 when the bound elapsed (what `timeout` reports); 127 when
# the command cannot be started. stdin, stdout and stderr pass through untouched.
# A shell FUNCTION cannot be bounded this way (no external process can run it): pass a binary.

_RUN_BOUNDED_PY='
import os, signal, subprocess, sys
secs = float(sys.argv[1])
posix = os.name == "posix"
try:
    child = subprocess.Popen(sys.argv[2:], start_new_session=posix)
except OSError:
    sys.exit(127)
try:
    rc = child.wait(timeout=secs)
except subprocess.TimeoutExpired:
    try:
        if posix:
            os.killpg(child.pid, signal.SIGKILL)
        else:
            child.kill()
    except OSError:
        pass
    child.wait()
    sys.exit(124)
sys.exit(128 - rc if rc < 0 else rc)
'

run_bounded() {
    local secs="$1"
    shift
    if command -v timeout >/dev/null 2>&1; then
        timeout "$secs" "$@"
    elif command -v gtimeout >/dev/null 2>&1; then
        gtimeout "$secs" "$@"
    elif command -v python3 >/dev/null 2>&1; then
        python3 -c "$_RUN_BOUNDED_PY" "$secs" "$@"
    else
        "$@"
    fi
}
