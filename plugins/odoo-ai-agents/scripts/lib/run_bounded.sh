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
#
# MEMORY CAP (same file, beside the wall-clock bound):
#
#   run_memory_capped [--scope-only] <cmd> [args...]
#
# Runs <cmd> so that exceeding the plugin's memory limit kills <cmd> ALONE. Every process the
# plugin starts otherwise shares the terminal's systemd scope with `claude`, and systemd's default
# policy stops the whole unit when the kernel OOM-kills any member - Claude, its subagents and
# every Odoo server die with the one heavy child. The cap is the value resource_limits.sh already
# resolves (ODOO_AI_LIMIT_MEMORY_HARD; "0" or empty = uncapped, <cmd> then runs as it is). There is
# no other knob.
#   - Where the systemd USER manager can enforce a memory cap (probed on every launch, never
#     assumed), <cmd> runs in its own transient scope: MemoryMax=<cap>, no swap. A memory kill ends
#     <cmd> with SIGKILL, so the caller sees status 137 and keeps running. <cmd> keeps its process
#     group and session, so signalling its group still reaches it.
#   - Elsewhere (macOS, containers, no user manager, cgroup v1) <cmd> gets an address-space limit
#     (`ulimit -Sv`). That limit is PER PROCESS (a child tree can add up to N times the cap) and
#     measures address space, not resident memory; hitting it makes an allocation FAIL inside <cmd>
#     (MemoryError, malloc failure) - an ordinary non-zero exit, not a signal. --scope-only skips
#     that fallback: with no usable scope <cmd> runs uncapped.
# Exit: <cmd>'s own status; 127 when <cmd> cannot be found. stdin, stdout, stderr pass through.
#
# From a shell that has not sourced this file (an agent running one heavy command):
#   bash <plugin>/scripts/lib/run_bounded.sh capped [--scope-only] <cmd> [args...]
#   bash <plugin>/scripts/lib/run_bounded.sh bounded <seconds> <cmd> [args...]
# In that form (and through exec_memory_capped, the same thing as a shell function) the command
# REPLACES the launcher process, so `$!` of a background launch is the command's own pid.

_RUN_BOUNDED_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd)" || true

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

# True (exit 0) iff the systemd user manager enforces a MemoryMax scope here. Asked of the real
# thing: start a throwaway scope with the cap and read the cap back from the cgroup it landed in.
# A scope the manager accepts but whose memory controller is not delegated reports "max" there, and
# counts as unusable. Bounded, and cheap to fail: no systemd-run, no probe.
#
# The same probe learns how this systemd-run treats `$` in the command's arguments: recent versions
# (measured on 259) apply service-style expansion to a scope's command line - `$$` becomes `$`,
# `${NAME}` is replaced by systemd-run's own environment - which would silently rewrite the
# command's arguments. _RUN_CAPPED_DOLLAR is set to "double" when `$` must be sent as `$$`, else "".
_run_capped_scope_usable() {
    command -v systemd-run >/dev/null 2>&1 || return 1
    local got first rest
    got="$(run_bounded 5 systemd-run --user --scope --quiet -p "MemoryMax=$1" -p MemorySwapMax=0 \
        sh -c 'echo "$0"; cat "/sys/fs/cgroup$(sed -n "s/^0:://p" /proc/self/cgroup)/memory.max"' '$$' \
        </dev/null 2>/dev/null)" || return 1
    first="${got%%
*}"
    rest="${got#*
}"
    case "$rest" in '' | *[!0-9]*) return 1 ;; esac
    case "$first" in
        '$') _RUN_CAPPED_DOLLAR=double ;;
        '$$') _RUN_CAPPED_DOLLAR="" ;;
        *) return 1 ;;
    esac
    return 0
}

# Run "$@" (foreground), or replace this process with it when _RUN_CAPPED_EXEC is set.
_run_capped_go() {
    if [ -n "${_RUN_CAPPED_EXEC:-}" ]; then
        exec "$@"
    fi
    "$@"
}

run_memory_capped() {
    local scope_only=""
    if [ "${1:-}" = "--scope-only" ]; then
        scope_only=1
        shift
    fi
    [ "$#" -gt 0 ] || { echo "run_memory_capped: no command given" >&2; return 2; }
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "run_memory_capped: command not found: $1" >&2
        return 127
    fi
    command -v resource_limit_hard_bytes >/dev/null 2>&1 || . "$_RUN_BOUNDED_DIR/resource_limits.sh"
    local bytes
    bytes="$(resource_limit_hard_bytes)"
    if [ -z "$bytes" ] || [ "$bytes" = "0" ]; then
        _run_capped_go "$@"
        return
    fi
    local _RUN_CAPPED_DOLLAR=""
    if _run_capped_scope_usable "$bytes"; then
        local -a _cmd=()
        local _arg
        for _arg in "$@"; do
            [ "$_RUN_CAPPED_DOLLAR" = "double" ] && _arg="${_arg//\$/\$\$}"
            _cmd+=("$_arg")
        done
        _run_capped_go systemd-run --user --scope --quiet -p "MemoryMax=$bytes" -p MemorySwapMax=0 -- "${_cmd[@]}"
        return
    fi
    if [ -n "$scope_only" ]; then
        _run_capped_go "$@"
        return
    fi
    if [ -n "${_RUN_CAPPED_EXEC:-}" ]; then
        ulimit -Sv "$(( bytes / 1024 ))" 2>/dev/null || true
        exec "$@"
    fi
    ( ulimit -Sv "$(( bytes / 1024 ))" 2>/dev/null || true; exec "$@" )
}

# Like run_memory_capped, but the command REPLACES the calling process (no extra process, so a
# pid taken from a background launch is the command's own). Use it as the last command of a
# subshell; it returns only when the command cannot be started.
exec_memory_capped() {
    _RUN_CAPPED_EXEC=1 run_memory_capped "$@"
}

# Executed rather than sourced: the shell front door of the two helpers above.
if [ -n "${BASH_SOURCE[0]:-}" ] && [ "${BASH_SOURCE[0]}" = "$0" ]; then
    _mode="${1:-}"
    [ "$#" -gt 0 ] && shift
    case "$_mode" in
        capped) exec_memory_capped "$@" ;;
        bounded)
            [ "$#" -ge 2 ] || { echo "usage: run_bounded.sh bounded <seconds> <cmd> [args...]" >&2; exit 2; }
            run_bounded "$@" ;;
        *)
            echo "usage: run_bounded.sh capped [--scope-only] <cmd> [args...] | bounded <seconds> <cmd> [args...]" >&2
            exit 2 ;;
    esac
    exit $?
fi
