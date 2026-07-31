#!/usr/bin/env bash
# 50-instance-spinup.sh - Start a declared Odoo instance and wait for HTTP 200.
#
# Reads an instance profile written by 40-instance-profile.sh from
# $ODOO_AI_HOME/instances.toml, generates a temporary odoo.conf with the correct
# addons_path ordering, launches Odoo (source via odoo-bin OR docker compose),
# then detects READY with a BOUNDED-timeout HTTP poll of /web/database/selector
# (fallback /web/login) - never a log-tail wait (docs/reference/
# INSTANCE-LIFECYCLE.md item 14). /web/database/selector needs no DB and no
# auth and is reliable across v8-v19 (v18+ moved the backend root /web -> /odoo,
# but this route and /web/login are unchanged); /web/login is kept as a
# fallback for a series/build where the selector route is unavailable. On
# timeout the poll BLOCKs with the last probe error - it never waits forever.
#
# Unlike the other steps this one is PARAMETERISED by version:
#   50-instance-spinup.sh apply --version 17.0
#   50-instance-spinup.sh check --version 17.0
# If --version is omitted, the highest valid X.Y [[instance]] in the file is used.
#
# Subcommands:
#   describe   One-line description.
#   check      Exit 0 if the instance's http_port already answers HTTP 200
#              (already running); exit 1 otherwise.
#   apply      Generate conf, spin up, poll until 200 (timeout ~120s), print URL.
#
#              By DEFAULT `apply` spins up (or attaches to) the SHARED declared
#              instance (persist: shared-running) and registers it as a `shared`
#              allocator lease via _register_shared - owner-stamped with
#              --run-id when the caller sets INST_RUN_ID (P5.5).
#
#              Pass --exclusive plus --db-name/--http-port (and, when the
#              series needs one, --gevent-port) to instead spin up the CALLER'S
#              OWN pre-leased instance (persist: exclusive-running - a unique db
#              + an allocator-issued pooled port the caller already acquired via
#              `allocator.py acquire --mode ephemeral --run-id <id>`, per
#              agents/odoo-instance-ops.md operation 1). --exclusive SKIPS
#              _register_shared entirely (the lease already exists and is
#              already owned) and NEVER falls back to the declared/8069 port -
#              --db-name/--http-port are REQUIRED with --exclusive; omitting
#              either is a hard failure (BLOCKED), not a silent 8069 fallback
#              (P5.9). --port-key/--gevent-port-key are the agent-resolved
#              odoo.conf key names (e.g. `http_port`/`xmlrpc_port`,
#              `gevent_port`/`longpolling_port`) from OSM `cli_help` - they
#              override the local version-arithmetic fallback below, which
#              stays in place ONLY for the shared/declared path so existing
#              callers are unaffected (P5.6).
#
# HARD RULES:
#   - Reads db_password ONLY from env (ODOO_PG_PASSWORD) - never from the TOML.
#   - The generated odoo.conf goes in a temp dir; no project files are mutated.
#   - No sudo. docker mode uses `docker compose` (must already be installed).
#
# CONFIG:
#   ODOO_AI_HOME       machine-global dir     ${ODOO_AI_HOME:-$HOME/.odoo-ai}
#   ODOO_AI_INSTANCES  full-path override for instances.toml
#   ODOO_BIN           path to odoo-bin (source mode). Auto-detected from
#                      the 'core' addons_path entry if unset.
#   ODOO_PG_PASSWORD   postgres password (env only; optional for trust auth).
#   SPINUP_TIMEOUT     poll timeout seconds (default 120).
#   SPINUP_STOP_GRACE  seconds to wait for a failed spin-up's process group to
#                      exit on SIGTERM before escalating to a group SIGKILL
#                      (default 10; mirrors allocator.py _stop_group's bound).
#   ODOO_AI_ALLOCATOR  path to allocator.py (default ../lib/allocator.py). Set it
#                      empty to skip shared-lease registration (plain spin-up).
#   INST_RUN_ID        the caller's session/run id (P5.5) - when set, threaded
#                      into _register_shared's `allocator.py acquire --mode
#                      shared` call as --run-id, so the shared lease is
#                      owner-stamped and can no longer be foreign-bare-dropped.
#                      Unset -> the shared lease stays unowned (back-compat).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# instances.toml is machine-global; resolve it (global-wins) via the shared helper.
# shellcheck source=../lib/resolve_instances.sh
source "$SCRIPT_DIR/../lib/resolve_instances.sh"
# Resource-limit SSOT (Problem 1 hardening) - resolves limit_memory_hard/soft +
# limit_time_real for the generated [options] conf block below (A2 - a
# long-running listener, unlike 55-instance-ops.sh's --stop-after-init build
# path). Policy: snippets/odoo-bin-resource-limits.md.
# shellcheck source=../lib/resource_limits.sh
source "$SCRIPT_DIR/../lib/resource_limits.sh"
INSTANCES_TOML="$(_resolve_instances)"
INSTANCES_IO="$SCRIPT_DIR/../lib/instances_io.py"
SPINUP_TIMEOUT="${SPINUP_TIMEOUT:-120}"
SPINUP_STOP_GRACE="${SPINUP_STOP_GRACE:-10}"
# SSOT for the "no declared http_port" fallback (P5.9 8069-fallback
# consolidation) - mirrors instances_io.DEFAULT_HTTP_PORT / allocator.py's
# DEFAULT_HTTP_PORT (bash cannot import the Python constant, so this is the
# bash-side twin of the same literal).
DEFAULT_HTTP_PORT=8069

# ---------------------------------------------------------------------------
# arg parse: subcommand first, then optional --version X.Y [exclusive-running
# overrides]
# ---------------------------------------------------------------------------
SUBCMD="${1:-}"
shift || true
VERSION=""
PROFILE=""
# persist: exclusive-running overrides (P5.6) - all empty/0 by default, which
# keeps every existing (persist: shared-running) caller byte-for-byte unchanged.
ARG_EXCLUSIVE=0
ARG_DB_NAME=""
ARG_HTTP_PORT=""
ARG_PORT_KEY=""
ARG_GEVENT_PORT=""
ARG_GEVENT_PORT_KEY=""
# The allocator lease token for an --exclusive spin-up. The caller
# (odoo-instance-ops) acquires the lease, then forwards its token here so this
# script can bind the launched server pid onto that lease (see _bind_exclusive).
ARG_ALLOC_TOKEN=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --version)
            # Guard: a bare trailing `--version` leaves only 1 arg, so `shift 2`
            # would return 1 and (under set -e) abort the script silently.
            if [[ $# -lt 2 ]]; then
                echo "$(basename "$0") --version requires a value (e.g. --version 17.0)" >&2
                exit 2
            fi
            VERSION="$2"; shift 2 ;;
        --profile)
            if [[ $# -lt 2 ]]; then
                echo "$(basename "$0") --profile requires a value (e.g. --profile minimal)" >&2
                exit 2
            fi
            PROFILE="$2"; shift 2 ;;
        --exclusive)
            ARG_EXCLUSIVE=1; shift ;;
        --db-name)
            [[ $# -ge 2 ]] || { echo "$(basename "$0") --db-name requires a value" >&2; exit 2; }
            ARG_DB_NAME="$2"; shift 2 ;;
        --http-port)
            [[ $# -ge 2 ]] || { echo "$(basename "$0") --http-port requires a value" >&2; exit 2; }
            ARG_HTTP_PORT="$2"; shift 2 ;;
        --port-key)
            [[ $# -ge 2 ]] || { echo "$(basename "$0") --port-key requires a value" >&2; exit 2; }
            ARG_PORT_KEY="$2"; shift 2 ;;
        --gevent-port)
            [[ $# -ge 2 ]] || { echo "$(basename "$0") --gevent-port requires a value" >&2; exit 2; }
            ARG_GEVENT_PORT="$2"; shift 2 ;;
        --gevent-port-key)
            [[ $# -ge 2 ]] || { echo "$(basename "$0") --gevent-port-key requires a value" >&2; exit 2; }
            ARG_GEVENT_PORT_KEY="$2"; shift 2 ;;
        --alloc-token)
            [[ $# -ge 2 ]] || { echo "$(basename "$0") --alloc-token requires a value" >&2; exit 2; }
            ARG_ALLOC_TOKEN="$2"; shift 2 ;;
        *) echo "Unknown arg: $1" >&2; exit 2 ;;
    esac
done

# ---------------------------------------------------------------------------
# describe
# ---------------------------------------------------------------------------
cmd_describe() {
    echo "Spin up a declared Odoo instance (source or docker) and wait for a bounded HTTP-200 poll of /web/database/selector (fallback /web/login)"
}

# ---------------------------------------------------------------------------
# TOML reader - emit shell-eval-able KEY=VALUE lines for one instance.
# Delegates to lib/instances_io.py (tomllib on py3.11+, text-scan fallback on
# older Python). Selects by --version, else the highest valid X.Y series.
# ---------------------------------------------------------------------------
_read_instance() {
    # $1 = series (may be empty -> highest valid series).
    # $2 = profile (optional; empty -> match any profile / no-profile items).
    # Prints shell-safe KEY=VALUE lines (values shlex.quote'd) so the caller can
    # `eval` them even when a path contains spaces or shell metacharacters.
    [[ -f "$INSTANCES_TOML" ]] || return 1
    python3 "$INSTANCES_IO" read "$INSTANCES_TOML" "${1:-}" "${2:-}"
}

# ---------------------------------------------------------------------------
# HTTP probe - returns the status code on the given path (000 on connection
# fail). $2 defaults to /web/login for back-compat; callers that care about
# readiness use _probe_ready below instead of calling this directly.
# ---------------------------------------------------------------------------
_http_status() {
    # $1 = port, $2 = path (default /web/login)
    local port="$1" path="${2:-/web/login}"
    curl -s -o /dev/null -w "%{http_code}" "http://localhost:$port$path" 2>/dev/null || echo "000"
}

# ---------------------------------------------------------------------------
# _probe_ready - the deterministic READY signal (docs/reference/
#   INSTANCE-LIFECYCLE.md item 14): the PRIMARY endpoint is
#   /web/database/selector (auth=none, no DB required, reliable v8-v19). ONE
#   curl call per invocation - the bounded retry loop (_poll_until_up) is what
#   provides repeated attempts, so this function never blocks past a single
#   curl connect. Sets _last_ready_status/_last_ready_path in the CALLER's
#   scope (bash dynamic scoping, same pattern as _open_log/_build_db_conn_args
#   elsewhere in this toolkit) so a timeout caller can report the last error.
# ---------------------------------------------------------------------------
_probe_ready() {
    local port="$1"
    _last_ready_path="/web/database/selector"
    _last_ready_status="$(_http_status "$port" "$_last_ready_path")"
    [[ "$_last_ready_status" == "200" ]]
}

# ---------------------------------------------------------------------------
# _probe_ready_fallback - the FALLBACK endpoint /web/login. ONE curl call.
#   Used only as a last resort - see _poll_until_up - for a series/build where
#   /web/database/selector is unavailable; never tried on every iteration
#   (that would double the probe cost of every poll for no benefit, since the
#   primary is reliable v8-v19 - docs/reference/INSTANCE-LIFECYCLE.md item 14).
# ---------------------------------------------------------------------------
_probe_ready_fallback() {
    local port="$1"
    _last_ready_path="/web/login"
    _last_ready_status="$(_http_status "$port" "$_last_ready_path")"
    [[ "$_last_ready_status" == "200" ]]
}

# ---------------------------------------------------------------------------
# Instance-identity attach guard (P2 bootstrap-race BACKSTOP -
#   49-solution-final.md §2.4.2): "the port answers 200" alone is NOT proof
#   that the server behind it is THIS instance - two same-series projects can
#   (in the narrow race window the eager migration in 40-instance-profile.sh
#   shrinks but does not eliminate) end up sharing a declared port before the
#   catalog converges. The launcher records an identity token (a hash of
#   addons_path - unique per project checkout, unlike db_name/series alone)
#   in a small marker file keyed by port under the machine-global runtime dir
#   at the moment it confirms ITS OWN server is up; a later "already up" check
#   compares the port's recorded token against what THIS invocation expects.
#
#   MINIMAL/backstop scope (documented residual, not a registry-schema
#   change): a port with NO recorded marker yet (nothing has ever spun up
#   through this guard, e.g. a pre-existing server, or the very first launch)
#   is treated as a pass-through - it cannot be disproven, so it is allowed,
#   same as before this guard existed. Markers are never actively cleaned up
#   on release/gc/teardown, so a port legitimately repurposed later keeps its
#   old token until the NEXT successful spin-up through this script rewrites
#   it; the failure mode this produces is "an old marker blocks a legitimate
#   reattach until a fresh spin-up rewrites it" - i.e. it fails CLOSED
#   (refuses to treat a mismatched live server as attachable), which is the
#   safe direction for a collision-detection backstop.
# ---------------------------------------------------------------------------
_identity_marker_path() {
    # $1 = port. Lives under the SAME machine-global runtime root the
    # allocator/resolver use (_odoo_ai_runtime_dir, sourced from
    # resolve_instances.sh above) - not a new root, not the leases.json schema.
    local dir
    dir="$(_odoo_ai_runtime_dir)/identity" || return 1
    mkdir -p "$dir" 2>/dev/null || true
    printf '%s/%s.token\n' "$dir" "$1"
}

_identity_token() {
    # $1 = addons_path (comma-separated - see resolve_instances.sh's
    # ADDONS_PATH_SEP). Separator-agnostic hash input: deterministic per
    # project checkout - two different projects/repos never share addons_path,
    # even when they share series, profile, db_name, and (in the race window) port.
    python3 -c '
import hashlib, sys
print(hashlib.sha256(sys.argv[1].encode()).hexdigest()[:16])
' "$1"
}

_write_identity_marker() {
    # $1 = port, $2 = expected token, $3 = db_name (debug context only).
    local path
    path="$(_identity_marker_path "$1")" || return 0
    { printf '%s\n%s\n' "$2" "$3" >"$path"; } 2>/dev/null || true
}

_identity_ok() {
    # $1 = port, $2 = this invocation's expected token. Returns 0 (pass) when
    # no marker is recorded yet (cannot disprove - see the docstring above) OR
    # the recorded token matches; returns 1 on a CONFIRMED mismatch (a live
    # server on this port was launched by this guard for a DIFFERENT project).
    local port="$1" expected="$2" path have
    path="$(_identity_marker_path "$port")" || return 0
    [[ -f "$path" ]] || return 0
    have="$(head -n1 "$path" 2>/dev/null || true)"
    [[ -z "$have" || "$have" == "$expected" ]]
}

# ---------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------
cmd_check() {
    # Non-zero exit OR empty output from the loader = no instance to check.
    local kv port rc=0
    local _last_ready_status="" _last_ready_path=""
    kv="$(_read_instance "$VERSION" "$PROFILE")" || rc=$?
    [[ "$rc" -eq 0 && -n "$kv" ]] || return 1
    eval "$kv"
    port="${INST_HTTP_PORT:-$DEFAULT_HTTP_PORT}"
    _probe_ready "$port" || return 1
    _identity_ok "$port" "$(_identity_token "${INST_ADDONS_PATH:-}")"
}

# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------
_find_odoo_bin() {
    # Locate odoo-bin: explicit env wins, else search the addons_path entries
    # one level up for an odoo-bin (the 'core' repo root).
    if [[ -n "${ODOO_BIN:-}" && -x "${ODOO_BIN}" ]]; then
        echo "$ODOO_BIN"; return 0
    fi
    local p
    _addons_path_to_array _paths "${INST_ADDONS_PATH:-}"
    for p in "${_paths[@]}"; do
        [[ -n "$p" ]] || continue
        if [[ -x "$p/odoo-bin" ]]; then echo "$p/odoo-bin"; return 0; fi
        if [[ -x "$(dirname "$p")/odoo-bin" ]]; then echo "$(dirname "$p")/odoo-bin"; return 0; fi
    done
    return 1
}

_poll_until_up() {
    # $1 = port. BOUNDED-timeout READY poll (docs/reference/
    # INSTANCE-LIFECYCLE.md item 14): repeatedly probe the PRIMARY
    # /web/database/selector endpoint (one curl call per iteration) until it
    # answers 200 or the bound is reached. Only once the primary has exhausted
    # its whole timeout budget without ever answering 200 does this make ONE
    # additional attempt against the FALLBACK /web/login - covering a
    # series/build where the selector route is unavailable, without doubling
    # the probe cost of every iteration for the (reliable v8-v19) common case.
    # Returns 0 on success. On timeout, BLOCKs (returns 1) with the last
    # probe's endpoint + status - it NEVER waits forever and NEVER falls back
    # to tailing a log.
    local port="$1" elapsed=0
    local _last_ready_status="" _last_ready_path=""
    echo "  Polling http://localhost:$port/web/database/selector (fallback /web/login; timeout ${SPINUP_TIMEOUT}s)..."
    while (( elapsed < SPINUP_TIMEOUT )); do
        if _probe_ready "$port"; then
            echo "  ok ready at $_last_ready_path after ${elapsed}s"
            return 0
        fi
        sleep 3
        elapsed=$((elapsed + 3))
    done
    if _probe_ready_fallback "$port"; then
        echo "  ok ready at $_last_ready_path after ${elapsed}s (fallback)"
        return 0
    fi
    echo "  x timed out after ${SPINUP_TIMEOUT}s (last: $_last_ready_path -> ${_last_ready_status:-000})" >&2
    return 1
}

cmd_apply() {
    # The loader (lib/instances_io.py read) prints guidance to STDERR and exits
    # non-zero with EMPTY stdout when no valid instance exists. Capture the exit
    # status separately (`|| rc=$?` keeps `set -e` from aborting here) and treat
    # BOTH a non-zero exit AND empty output as "nothing to spin up" so we never
    # proceed with empty INST_* vars.
    local kv rc=0
    kv="$(_read_instance "$VERSION" "$PROFILE")" || rc=$?
    if [[ "$rc" -ne 0 || -z "$kv" ]]; then
        echo "x No usable Odoo instance found in $INSTANCES_TOML." >&2
        echo "  Declare one first: run the instance-profile step" >&2
        echo "  (40-instance-profile.sh apply) or edit instances.toml by hand." >&2
        return 1
    fi
    eval "$kv"
    # Effective db_name/port: the agent's exclusive-running overrides win when
    # given (P5.6); otherwise this is the declared/shared instance, unchanged.
    local port="${ARG_HTTP_PORT:-${INST_HTTP_PORT:-$DEFAULT_HTTP_PORT}}"
    local db_name="${ARG_DB_NAME:-${INST_DB_NAME:-odoo}}"

    # persist: exclusive-running (--exclusive) NEVER falls back to the
    # declared/DEFAULT_HTTP_PORT port - the caller MUST have already acquired
    # its own unique db + pooled port via allocator.py and pass both explicitly.
    # Gate the six-8069-fallbacks class of bug at its source (P5.9): BLOCK
    # loudly here instead of silently converging on the shared port/db.
    if [[ "$ARG_EXCLUSIVE" == "1" ]]; then
        if [[ -z "$ARG_DB_NAME" || -z "$ARG_HTTP_PORT" ]]; then
            echo "" >&2
            echo "x BLOCKED: --exclusive requires --db-name AND --http-port (both allocator-issued)." >&2
            echo "  Refusing to fall back to the declared/\$DEFAULT_HTTP_PORT port for an" >&2
            echo "  exclusive-running spin-up - that would collide with the shared render target." >&2
            echo "  Acquire a pooled port first: allocator.py acquire --mode ephemeral --ports 1" >&2
            echo "  [--ports 2] --run-id <run_id> (see agents/odoo-instance-ops.md operation 1," >&2
            echo "  persist: exclusive-running)." >&2
            return 1
        fi
    fi

    # --gevent-port and --gevent-port-key are a PAIR (P5.6): a series that needs a
    # second listening port (gevent/longpolling) requires BOTH the port AND its
    # resolved conf key to emit that conf line. Half-specifying either one used to
    # degrade silently to "no second listening port" with no error - BLOCK loudly
    # instead, mirroring the --exclusive-without-overrides gate above, so a caller
    # bug is caught here rather than shipping a single-port conf on a series that
    # needs two.
    if [[ ( -n "${ARG_GEVENT_PORT:-}" && -z "${ARG_GEVENT_PORT_KEY:-}" ) || \
          ( -z "${ARG_GEVENT_PORT:-}" && -n "${ARG_GEVENT_PORT_KEY:-}" ) ]]; then
        echo "" >&2
        echo "x BLOCKED: --gevent-port and --gevent-port-key must be given TOGETHER." >&2
        echo "  Got --gevent-port='${ARG_GEVENT_PORT:-}' --gevent-port-key='${ARG_GEVENT_PORT_KEY:-}'." >&2
        echo "  Refusing to silently omit the second listening port - a series that" >&2
        echo "  needs one would otherwise start with no error and no gevent/longpolling" >&2
        echo "  port bound. Pass BOTH (resolve the key via OSM cli_help; see" >&2
        echo "  agents/odoo-instance-ops.md operation 1, persist: exclusive-running)." >&2
        return 1
    fi

    # Register this spin-up as the SHARED, NON-exclusive render target so other
    # sessions discover it (allocator.py query) and gc reclaims it when it dies.
    # Best-effort only: an absent allocator/python degrades to plain spin-up,
    # exactly as before. We register AFTER the server answers (never before), so
    # a failed start leaves NO stale lease and we never need a teardown release.
    # SKIPPED entirely for --exclusive (persist: exclusive-running): that DB is
    # the caller's OWN pre-leased instance, already owned - registering it as a
    # second, SHARED lease would be both redundant and wrong (shared leases are
    # never exclusive-DB, but this DB genuinely is).
    local alloc_py="${ODOO_AI_ALLOCATOR-$SCRIPT_DIR/../lib/allocator.py}"
    _register_shared() {
        # $1 = optional live server pid. The pid is recorded only when it is
        # still alive, so a concurrent loser (whose odoo-bin lost the port bind
        # and exited) cannot overwrite the live winner's pid. created_db is
        # always False on a shared lease, so gc never drops the declared DB.
        [[ -n "$alloc_py" && -f "$alloc_py" ]] || return 0
        local args=(acquire --series "${INST_VERSION:-}" --mode shared
                    --port "$port" --db-name "$db_name")
        [[ -n "${INST_PROFILE:-}" ]] && args+=(--profile "${INST_PROFILE}")
        # P5.5: owner-stamp the shared lease with the caller's run id (sourced
        # from INST_RUN_ID, the same INST_* convention every other field here
        # follows) so a foreign session can no longer bare-drop it. Unset ->
        # the lease stays unowned, exactly as before (back-compat).
        [[ -n "${INST_RUN_ID:-}" ]] && args+=(--run-id "${INST_RUN_ID}")
        if [[ -n "${1:-}" ]] && kill -0 "$1" 2>/dev/null; then
            args+=(--pid "$1")
        fi
        python3 "$alloc_py" "${args[@]}" >/dev/null 2>&1 || true
    }

    _bind_exclusive() {
        # $1 = the live server pid. For an --exclusive spin-up the lease was
        # already acquired by the caller (odoo-instance-ops) and its token
        # forwarded via --alloc-token; bind the just-launched server pid onto THAT
        # lease so `allocator.py release`/`gc` can stop the whole process group
        # (master + workers + gevent/longpolling + --dev watchdog) BEFORE dropping
        # the DB, instead of leaking a listening server against a dropped DB.
        # Same liveness guard as _register_shared: only record a pid that kill -0
        # confirms alive, so a fast-failing server never binds a dead pid.
        [[ -n "$alloc_py" && -f "$alloc_py" ]] || return 0
        [[ -n "${ARG_ALLOC_TOKEN:-}" ]] || return 0
        if [[ -n "${1:-}" ]] && kill -0 "$1" 2>/dev/null; then
            python3 "$alloc_py" bind "${ARG_ALLOC_TOKEN}" --pid "$1" >/dev/null 2>&1 || true
        fi
    }

    _stop_group_local() {
        # $1 = the setsid-launched leader pid (pgid == pid). Tear down the WHOLE
        # process group of a FAILED spin-up - master + HTTP workers + cron +
        # gevent/longpolling + any --dev watchdog - not just the leader. Mirrors
        # allocator.py _stop_group's pattern: SIGTERM the group, wait a bounded
        # grace, then escalate to a group SIGKILL; fall back to a single-pid
        # signal when the group id cannot be resolved (getpgid-equivalent fails).
        # Replaces the old bare `kill <pid>` (SIGTERM-only, leader-only), which
        # left forked children running against a DB the caller may then drop.
        local pid="${1:-}"
        [[ -n "$pid" ]] || return 0
        local pgid
        pgid="$(ps -o pgid= -p "$pid" 2>/dev/null | tr -d ' ')"
        # Graceful SIGTERM: prefer the group (negative pgid), fall back to the pid.
        if [[ -n "$pgid" ]]; then
            kill -TERM "-${pgid}" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
        else
            kill -TERM "$pid" 2>/dev/null || true
        fi
        # Bounded wait for the leader to exit (poll the leader pid, like _stop_group).
        local waited=0
        while (( waited < SPINUP_STOP_GRACE )); do
            kill -0 "$pid" 2>/dev/null || return 0
            sleep 1
            waited=$((waited + 1))
        done
        # Escalate: SIGKILL the group (fall back to the single pid).
        if [[ -n "$pgid" ]]; then
            kill -KILL "-${pgid}" 2>/dev/null || kill -KILL "$pid" 2>/dev/null || true
        else
            kill -KILL "$pid" 2>/dev/null || true
        fi
    }

    local _last_ready_status="" _last_ready_path=""
    # Instance-identity token this invocation EXPECTS to see recorded on
    # $port (see the guard block above _probe_ready_fallback). Computed once
    # here and reused both by the "already up" pre-check below and by the
    # marker write after a fresh launch succeeds.
    local _id_expected
    _id_expected="$(_identity_token "${INST_ADDONS_PATH:-}")"
    if _probe_ready "$port"; then
        if _identity_ok "$port" "$_id_expected"; then
            [[ "$ARG_EXCLUSIVE" != "1" ]] && _register_shared
            echo "ok Instance ${INST_VERSION} already up at http://localhost:$port$_last_ready_path"
            return 0
        fi
        echo "" >&2
        echo "x COLLISION: port $port answers HTTP 200, but its recorded instance-identity" >&2
        echo "  does NOT match this project's addons_path. A DIFFERENT Odoo server (most" >&2
        echo "  likely another project/session caught in the P2 bootstrap-race window - see" >&2
        echo "  snippets/instance-handle-contract.md) is bound to this port. Refusing to" >&2
        echo "  treat it as this instance being up - investigate before retrying, or" >&2
        echo "  declare a distinct http_port for this project." >&2
        return 1
    fi

    # Tracked so a poll timeout can kill the orphaned process / remove temp conf
    # instead of leaking a port-holding Odoo and a /tmp conf file.
    local run_mode="${INST_RUN_MODE:-source}"
    local odoo_pid="" conf=""

    case "$run_mode" in
        docker)
            if ! command -v docker >/dev/null 2>&1; then
                echo "x run_mode=docker but 'docker' not found in PATH." >&2
                return 1
            fi
            echo "  Starting via 'docker compose up -d' in $PWD..."
            docker compose up -d
            ;;
        source)
            local bin
            bin="$(_find_odoo_bin)" || {
                echo "x Could not locate odoo-bin. Set ODOO_BIN=/path/to/odoo-bin and retry." >&2
                return 1
            }
            # Resolve the Python interpreter: the instance's own `python` field
            # (a venv with Odoo deps) wins, then $ODOO_PYTHON, else system python3.
            local py
            py="${INST_PYTHON:-}"
            [[ -z "$py" ]] && py="${ODOO_PYTHON:-}"
            [[ -z "$py" ]] && py="python3"
            if ! command -v "$py" >/dev/null 2>&1 && [[ ! -x "$py" ]]; then
                echo "x Python interpreter '$py' not found. Set 'python' in" \
                     "instances.toml (a venv with Odoo deps) or ODOO_PYTHON, or" \
                     "install python3." >&2
                return 1
            fi

            # ---- PREFLIGHT: verify python can run Odoo BEFORE launching ----
            # Use `<py> <odoo-bin> --version` instead of `<py> -c "import odoo"`:
            #   - odoo-bin inserts the repo root into sys.path[0] at startup, so
            #     this works with source-only checkouts (no pip install -e needed).
            #   - Catches missing deps (lxml, psycopg2, ...) that bare import hides.
            #   - Compatible with Odoo v19 namespace packages (no odoo/__init__.py).
            #   - Uses the venv's own python, so python2 venvs (v8-v10) work too.
            # Catching this here produces a clear actionable error instead of
            # launch-then-poll-timeout which wastes 120s and hides the real cause.
            if ! "$py" "$bin" --version >/dev/null 2>&1; then
                echo "" >&2
                echo "x PREFLIGHT FAILED: '$py $bin --version' failed - Odoo will not start." >&2
                echo "  Fix this BEFORE retrying:" >&2
                echo "    - Confirm the 'python' field in instances.toml points to a venv" >&2
                echo "      that has Odoo's deps installed (run step 45 create-venv first)." >&2
                echo "    - Or set ODOO_PYTHON=/path/to/venv/bin/python." >&2
                echo "    - Or install Odoo deps in the active Python environment." >&2
                return 1
            fi

            local _ver_major
            _ver_major="${INST_VERSION%%.*}"
            local _port_key
            if [[ -n "$ARG_PORT_KEY" ]]; then
                # Agent-resolved conf key from OSM cli_help (P5.6) - the
                # persist: exclusive-running caller ALWAYS passes this, so the
                # local arithmetic below never runs for that path.
                _port_key="$ARG_PORT_KEY"
            else
                # FALLBACK for the shared/declared spin-up path only (no
                # --port-key override): v8/9/10 use xmlrpc_port; v11+ renamed
                # it to http_port. Derive from INST_VERSION (the full series
                # string, e.g. "17.0", "10.0") - the major version is the
                # integer before the first dot. NOT the authoritative SSOT
                # (that is OSM cli_help - agents/odoo-instance-ops.md); kept
                # here only so existing callers that never pass --port-key are
                # unaffected (P5 §6 risk-4 mitigation: no behavior change
                # until a caller opts in).
                if [[ "$_ver_major" =~ ^[0-9]+$ ]] && (( _ver_major < 11 )); then
                    _port_key="xmlrpc_port"
                else
                    _port_key="http_port"
                fi
            fi

            # ---- PREFLIGHT: warn when ODOO_PG_PASSWORD is unset ---------------
            # An unauthenticated conf works only with trust auth; warn so the user
            # does not silently get a connection-refused or role-missing error at
            # runtime with no indication of why.
            if [[ -z "${ODOO_PG_PASSWORD:-}" ]]; then
                echo "  Warning: ODOO_PG_PASSWORD is unset - generated conf will omit" \
                     "db_password. This works only when pg is configured for trust auth." >&2
            fi

            # ---- PREFLIGHT: pg_isready check when available ------------------
            # Skipped silently when pg_isready is not on PATH (Docker-only envs
            # may not have the postgres client tools installed).
            local db_host="${INST_DB_HOST:-localhost}"
            local db_user="${INST_DB_USER:-odoo}"
            # db_name is already computed above (effective: ARG_DB_NAME override
            # or the declared INST_DB_NAME) - do NOT re-declare `local db_name`
            # here, that would reset the exclusive-running override back to the
            # declared name.
            local db_port="${INST_DB_PORT:-}"
            # -p only when a non-default port is declared (empty-omit): let libpq /
            # PGPORT resolve it otherwise, matching the drop/create surface.
            local _pgr_port_args=()
            [[ -n "$db_port" ]] && _pgr_port_args=(-p "$db_port")
            if command -v pg_isready >/dev/null 2>&1; then
                if ! pg_isready -h "$db_host" "${_pgr_port_args[@]}" -U "$db_user" -d "$db_name" -q 2>/dev/null; then
                    echo "" >&2
                    echo "x PREFLIGHT FAILED: PostgreSQL is not reachable." >&2
                    echo "  pg_isready -h $db_host -U $db_user -d $db_name reported failure." >&2
                    echo "  Odoo will not start until the database is reachable. Fix:" >&2
                    echo "    - Start / check your PostgreSQL service." >&2
                    echo "    - Verify db_host/db_user/db_name in instances.toml." >&2
                    echo "    - If using docker-compose for postgres, start it first." >&2
                    return 1
                fi
                echo "  ok pg_isready: PostgreSQL reachable at $db_host"
            fi

            # Portable mktemp: `mktemp -t PREFIX.XXXXXX.conf` is GNU-specific.
            # On BSD/macOS `-t` treats the arg as a prefix only, a suffix after
            # the X's is not honored, and ${INST_VERSION} contains a dot. Create
            # a bare temp file with a trailing-X template, then rename to add the
            # .conf suffix - works on both GNU and BSD/macOS.
            conf="$(mktemp "${TMPDIR:-/tmp}/odoo-spinup-XXXXXX")" && mv "$conf" "$conf.conf" && conf="$conf.conf"
            {
                echo "[options]"
                # INST_ADDONS_PATH is already comma-joined (the SSOT separator -
                # see resolve_instances.sh's ADDONS_PATH_SEP) - no conversion needed.
                echo "addons_path = ${INST_ADDONS_PATH:-}"
                echo "$_port_key = $port"
                # Second listening port (gevent/longpolling) - emitted when the
                # agent passed both the port AND its resolved conf key (P5.6).
                # A half-specified pair is BLOCKED earlier (see the
                # --gevent-port/--gevent-port-key pairing gate above) - by this
                # point both are set or both are empty, never one without the
                # other.
                if [[ -n "${ARG_GEVENT_PORT:-}" && -n "${ARG_GEVENT_PORT_KEY:-}" ]]; then
                    echo "$ARG_GEVENT_PORT_KEY = $ARG_GEVENT_PORT"
                fi
                # Resource limits (Problem 1 hardening - snippets/odoo-bin-
                # resource-limits.md): this is a REAL long-running listener
                # (unlike 55-instance-ops.sh's --stop-after-init build path),
                # so limit_memory_hard/soft AND limit_time_real all actually
                # fire here (ThreadedServer.process_limit()). Do NOT add
                # limit_time_cpu - it is a DEAD key while workers=0 (this
                # script never passes --workers).
                echo "limit_memory_hard = $(resource_limit_hard_bytes)"
                echo "limit_memory_soft = $(resource_limit_soft_bytes)"
                echo "limit_time_real = $(resource_limit_time_real)"
                echo "db_name = $db_name"
                echo "db_host = ${INST_DB_HOST:-localhost}"
                echo "db_user = ${INST_DB_USER:-odoo}"
                # db_port ONLY when a non-default port is declared (empty-omit) so
                # libpq/PGPORT resolves it otherwise - never fabricate 5432.
                if [[ -n "${INST_DB_PORT:-}" ]]; then
                    echo "db_port = ${INST_DB_PORT}"
                fi
                # Password ONLY from env - never echoed from a stored file.
                if [[ -n "${ODOO_PG_PASSWORD:-}" ]]; then
                    echo "db_password = ${ODOO_PG_PASSWORD}"
                fi
            } >"$conf"
            # --dev=all was introduced as a string-valued flag in v10; v9 has a
            # boolean --dev only (no =all), and v8 has no --dev at all.
            # Gate: only append --dev=all for major >= 10.
            local _dev_flag=""
            if [[ "$_ver_major" =~ ^[0-9]+$ ]] && (( _ver_major >= 10 )); then
                _dev_flag="--dev=all"
            fi

            echo "  Generated temp conf: $conf"
            echo "  Launching: $py '$bin' -c '$conf' -d '$db_name' ${_dev_flag}"
            # Run in background so we can poll. Logs to a temp file.
            # Capture the PID directly (no subshell `( )`, which would hide it)
            # so a poll timeout can terminate the orphaned process.
            local logf _logs_dir _db_slug _ts
            # Write log to a stable, named path so a calling agent can capture it
            # across invocations.
            # Dir: ${ODOO_AI_HOME:-$HOME/.odoo-ai}/logs/
            #   ODOO_AI_HOME IS the .odoo-ai dir (allocator semantic); .odoo-ai is
            #   appended ONLY in the HOME fallback so the path stays consistent with
            #   allocator.py _home() which returns ODOO_AI_HOME directly.
            # File: <db>-<UTC-timestamp>.log (e.g. odoo_test-20260620T153012Z.log)
            _logs_dir="${ODOO_AI_HOME:-${HOME:-/tmp}/.odoo-ai}/logs"
            mkdir -p "$_logs_dir"
            _db_slug="$db_name"
            _ts="$(date -u +%Y%m%dT%H%M%SZ 2>/dev/null || date -u +%Y%m%d%H%M%S)"
            logf="$_logs_dir/${_db_slug}-${_ts}.log"
            echo "LOG_PATH=$logf"
            # v8-v11 listener guard (Problem 1 hardening - snippets/odoo-bin-
            # resource-limits.md): Odoo applies NO memory cap of its own pre-
            # v12 on ANY run mode - the generated limit_memory_hard/soft conf
            # keys above are inert there too. A shell `ulimit -Sv` is the ONLY
            # protection for a v8-v11 listener. Applied to the CURRENT shell
            # immediately before backgrounding (the fork at `&` inherits it)
            # and restored right after capturing `$!` - `ulimit` is a process
            # rlimit, not a subshell, so it never disturbs setsid's process-
            # group-leader invariant below. v12+ already gets the conf-key
            # enforcement, so this guard is scoped to major < 12 only.
            local _prev_lim_v=""
            if ! resource_limit_is_uncapped && [[ "$_ver_major" =~ ^[0-9]+$ ]] && (( _ver_major < 12 )); then
                _prev_lim_v="$(ulimit -Sv 2>/dev/null || echo unlimited)"
                ulimit -Sv "$(resource_limit_hard_kib)" 2>/dev/null || true
            fi
            # setsid: the server becomes its OWN session/process-group leader
            # (pgid == its own pid), so allocator.py can later stop the whole
            # group (master + HTTP workers + cron + gevent/longpolling + any
            # --dev=reload watchdog) in one os.killpg before dropping the DB.
            # A bare `&` would leave the server in the launching shell's group,
            # which has no clean target to kill. `$!` is still the leader's pid.
            # shellcheck disable=SC2086
            setsid "$py" "$bin" -c "$conf" -d "$db_name" ${_dev_flag} >"$logf" 2>&1 &
            odoo_pid=$!
            [[ -n "$_prev_lim_v" ]] && { ulimit -Sv "$_prev_lim_v" 2>/dev/null || true; }
            echo "  Odoo starting (pid: $odoo_pid, log: $logf)"
            # Bind the pid onto the caller's exclusive lease IMMEDIATELY - BEFORE
            # the readiness poll - so allocator.py release/gc can stop this
            # server's whole process group even if the poll below TIMES OUT (a
            # slow/failed start still forks workers that would otherwise leak).
            # No-op for shared leases (their lease is registered only on success);
            # the kill -0 liveness guard lives inside _bind_exclusive.
            [[ "$ARG_EXCLUSIVE" == "1" ]] && _bind_exclusive "$odoo_pid"
            ;;
        *)
            echo "x Unknown run_mode: ${INST_RUN_MODE}. Use 'source' or 'docker'." >&2
            return 1
            ;;
    esac

    if _poll_until_up "$port"; then
        # Record THIS launch's instance-identity token on the port BEFORE
        # anything else touches it, so the next "already up" check (this
        # session or a foreign one) can tell a genuine re-attach from a
        # collision (see the guard block above _probe_ready_fallback).
        _write_identity_marker "$port" "$_id_expected" "$db_name"
        # The exclusive lease was already bound immediately after launch above;
        # the shared render target registers its lease only after readiness.
        [[ "$ARG_EXCLUSIVE" != "1" ]] && _register_shared "$odoo_pid"
        echo "ok Odoo ${INST_VERSION} is up: http://localhost:$port/web/login"
        return 0
    fi

    # Poll timed out - tear down what we started so we leave no orphan. The
    # server ran under setsid (its own process group), so stop the WHOLE group
    # (master + workers + gevent/cron + --dev watchdog) with SIGTERM -> bounded
    # wait -> group SIGKILL - not the old bare `kill <pid>` that left children
    # running. For an exclusive lease the pid is already bound (above), so even
    # if this local stop is interrupted, allocator.py release/gc can still reap.
    echo "x Odoo did not become ready. Check the launch log above." >&2
    if [[ "$run_mode" == "source" ]]; then
        if [[ -n "$odoo_pid" ]]; then
            echo "  Stopping background Odoo process group (leader pid $odoo_pid)" >&2
            _stop_group_local "$odoo_pid"
        fi
        [[ -n "$conf" && -f "$conf" ]] && rm -f "$conf"
    elif [[ "$run_mode" == "docker" ]]; then
        echo "  Tip: run 'docker compose down' to stop the containers started above." >&2
    fi
    return 1
}

# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------
case "$SUBCMD" in
    describe) cmd_describe ;;
    check)    cmd_check ;;
    apply)    cmd_apply ;;
    *) echo "Usage: $(basename "$0") {describe|check|apply} [--version X.Y]" >&2; exit 2 ;;
esac
