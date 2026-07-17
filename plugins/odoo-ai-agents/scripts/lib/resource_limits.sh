#!/usr/bin/env bash
# resource_limits.sh - Source-only helper: resolve the odoo-bin memory/time
# resource-limit values (Problem 1 - memory/time hardening). Policy is
# documented in snippets/odoo-bin-resource-limits.md; this file is the ONLY
# place the numeric resolution logic lives (SSOT) - callers source it and
# call the helper functions below, never re-derive the formula themselves.
#
# Why this exists: on the `--stop-after-init` build path (init/update/test),
# only a memory HARD cap can ever fire, and Odoo's own default (2.5 GiB) is
# either the exact cause of an OOM (v12+, where Odoo applies it) or silently
# absent (v8-v11, where Odoo applies no cap at all and the OS can kernel-OOM
# the process). The fix is a version-general, overridable cap: a shell
# `ulimit -Sv` (KiB) wrapper PLUS `--limit-memory-hard=<bytes>` on the odoo-bin
# invocation - see snippets/odoo-bin-resource-limits.md for the full policy.
#
# Source-only: defines functions + no top-level side effects. Portable to
# bash 3.2 (macOS): no mapfile, no ${var,,}, no associative arrays; POSIX
# `[ ]` test, not `[[ ]]`. Depends only on awk (already used elsewhere in
# this plugin, e.g. 55-instance-ops.sh) - no python required.
#
# Public API (all print the resolved value on stdout; callers capture via
# command substitution):
#   resource_limit_hard_bytes    -> resolved memory HARD cap, in BYTES
#                                    (for --limit-memory-hard=<bytes>)
#   resource_limit_hard_kib      -> the SAME cap, in KiB (for `ulimit -Sv`,
#                                    which takes a KiB argument)
#   resource_limit_is_uncapped   -> exit 0 (true) iff the resolved hard cap is
#                                    0/empty - the deliberate escape hatch;
#                                    callers must then SKIP `ulimit` entirely
#                                    AND still pass --limit-memory-hard=0 (so
#                                    Odoo's `if limit_memory_hard:` is falsy)
#   resource_limit_soft_bytes    -> memory SOFT value, in BYTES (A2 long-
#                                    running listener conf only - inert on
#                                    the --stop-after-init build path)
#   resource_limit_time_real     -> limit_time_real value, in SECONDS (A2
#                                    long-running listener conf only)
#
# CONFIG env (all optional; unset -> the documented default formula):
#   ODOO_AI_LIMIT_MEMORY_HARD   bytes. Set (even to "" or "0") to EXPLICITLY
#                                override the default - an explicit "" or "0"
#                                is the uncapped escape hatch. Unset (the
#                                common case) -> default = floor(MemTotal_kib
#                                * 1024 * 0.5), floored at 4294967296 (4 GiB).
#   ODOO_AI_LIMIT_MEMORY_SOFT   bytes. Default: floor(hard * 0.75).
#   ODOO_AI_LIMIT_TIME_REAL     seconds. Default: 14000.

# ---------------------------------------------------------------------------
# internal helpers
# ---------------------------------------------------------------------------

# True (exit 0) iff $1 is a non-negative base-10 integer literal.
_resource_limit_is_uint() {
    case "$1" in
        '' | *[!0-9]*) return 1 ;;
        *) return 0 ;;
    esac
}

# Echo MemTotal in KiB from /proc/meminfo, or nothing if unreadable (e.g.
# macOS, which has no /proc - the caller falls back to the 4 GiB floor).
# _RESOURCE_LIMIT_MEMINFO_PATH is a TEST-ONLY override (defaults to the real
# /proc/meminfo in production) so the default-formula behavior can be tested
# hermetically against a synthetic meminfo-shaped file, without root or a
# mount namespace.
_resource_limit_memtotal_kib() {
    local meminfo="${_RESOURCE_LIMIT_MEMINFO_PATH:-/proc/meminfo}"
    if [ -r "$meminfo" ]; then
        awk '/^MemTotal:/ { print $2; exit }' "$meminfo" 2>/dev/null
    fi
}

# The 4 GiB floor, in bytes - both the absolute minimum default cap AND the
# fallback when MemTotal cannot be read at all.
_RESOURCE_LIMIT_FLOOR_BYTES=4294967296

# Default hard-cap formula: floor(MemTotal_bytes * 0.5), floored at 4 GiB.
# Pure integer arithmetic (bash has no floating point): halving via /2 is
# exactly floor(x * 0.5) for a non-negative integer.
_resource_limit_default_hard_bytes() {
    local memtotal_kib mem_bytes half
    memtotal_kib="$(_resource_limit_memtotal_kib)"
    if ! _resource_limit_is_uint "$memtotal_kib" || [ -z "$memtotal_kib" ]; then
        printf '%s\n' "$_RESOURCE_LIMIT_FLOOR_BYTES"
        return 0
    fi
    mem_bytes=$(( memtotal_kib * 1024 ))
    half=$(( mem_bytes / 2 ))
    if [ "$half" -lt "$_RESOURCE_LIMIT_FLOOR_BYTES" ]; then
        printf '%s\n' "$_RESOURCE_LIMIT_FLOOR_BYTES"
    else
        printf '%s\n' "$half"
    fi
}

# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------

# Resolved memory HARD cap, in bytes. `${ODOO_AI_LIMIT_MEMORY_HARD+set}` (not
# `-n`) is used deliberately: a caller who EXPLICITLY sets the var to "" is
# opting into the uncapped escape hatch, distinct from leaving it unset
# entirely (which resolves the default formula). A set-but-non-numeric value
# is treated as the uncapped escape hatch too (fail safe toward "no crash",
# never toward silently capping at a garbage number).
resource_limit_hard_bytes() {
    if [ "${ODOO_AI_LIMIT_MEMORY_HARD+set}" = "set" ]; then
        if [ -z "${ODOO_AI_LIMIT_MEMORY_HARD}" ] || ! _resource_limit_is_uint "${ODOO_AI_LIMIT_MEMORY_HARD}"; then
            printf '%s\n' 0
        else
            printf '%s\n' "${ODOO_AI_LIMIT_MEMORY_HARD}"
        fi
        return 0
    fi
    _resource_limit_default_hard_bytes
}

# The SAME cap, in KiB (floor(bytes / 1024)) - the unit `ulimit -Sv` expects.
resource_limit_hard_kib() {
    local bytes
    bytes="$(resource_limit_hard_bytes)"
    printf '%s\n' "$(( bytes / 1024 ))"
}

# True (exit 0) iff the resolved hard cap is the uncapped sentinel (0).
# Callers MUST branch on this BEFORE calling `ulimit -Sv` - see
# snippets/odoo-bin-resource-limits.md.
resource_limit_is_uncapped() {
    local bytes
    bytes="$(resource_limit_hard_bytes)"
    [ -z "$bytes" ] || [ "$bytes" = "0" ]
}

# Resolved memory SOFT value, in bytes. A2 (long-running listener conf) only -
# inert on the --stop-after-init build path. Default: floor(hard * 0.75);
# 0 when the hard cap itself is uncapped (no soft ceiling without a hard one).
resource_limit_soft_bytes() {
    if [ "${ODOO_AI_LIMIT_MEMORY_SOFT+set}" = "set" ]; then
        if [ -z "${ODOO_AI_LIMIT_MEMORY_SOFT}" ] || ! _resource_limit_is_uint "${ODOO_AI_LIMIT_MEMORY_SOFT}"; then
            printf '%s\n' 0
        else
            printf '%s\n' "${ODOO_AI_LIMIT_MEMORY_SOFT}"
        fi
        return 0
    fi
    local hard
    hard="$(resource_limit_hard_bytes)"
    if [ -z "$hard" ] || [ "$hard" = "0" ]; then
        printf '%s\n' 0
        return 0
    fi
    printf '%s\n' "$(( hard * 3 / 4 ))"
}

# Resolved limit_time_real, in seconds. A2 (long-running listener conf) only -
# inert on the --stop-after-init build path. Default: 14000 (a generous
# runaway ceiling, not a request timeout).
resource_limit_time_real() {
    if [ "${ODOO_AI_LIMIT_TIME_REAL+set}" = "set" ] && _resource_limit_is_uint "${ODOO_AI_LIMIT_TIME_REAL}" && [ -n "${ODOO_AI_LIMIT_TIME_REAL}" ]; then
        printf '%s\n' "${ODOO_AI_LIMIT_TIME_REAL}"
        return 0
    fi
    printf '%s\n' 14000
}
