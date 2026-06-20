#!/usr/bin/env bash
# 50-instance-spinup.sh - Start a declared Odoo instance and wait for HTTP 200.
#
# Reads an instance profile written by 40-instance-profile.sh from
# .odoo-ai/instances.toml, generates a temporary odoo.conf with the correct
# addons_path ordering, launches Odoo (source via odoo-bin OR docker compose),
# then polls /web/login until it answers HTTP 200 (or times out).
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
# HARD RULES:
#   - Reads db_password ONLY from env (ODOO_PG_PASSWORD) - never from the TOML.
#   - The generated odoo.conf goes in a temp dir; no project files are mutated.
#   - No sudo. docker mode uses `docker compose` (must already be installed).
#
# CONFIG:
#   ODOO_AI_DIR        project artifacts dir  ${ODOO_AI_DIR:-$PWD/.odoo-ai}
#   ODOO_AI_HOME       machine-global dir     ${ODOO_AI_HOME:-$HOME/.odoo-ai}
#   ODOO_AI_INSTANCES  full-path override for instances.toml
#   ODOO_BIN           path to odoo-bin (source mode). Auto-detected from
#                      the 'core' addons_path entry if unset.
#   ODOO_PG_PASSWORD   postgres password (env only; optional for trust auth).
#   SPINUP_TIMEOUT     poll timeout seconds (default 120).
#   ODOO_AI_ALLOCATOR  path to allocator.py (default ../lib/allocator.py). Set it
#                      empty to skip shared-lease registration (plain spin-up).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ODOO_AI_DIR="${ODOO_AI_DIR:-$PWD/.odoo-ai}"
# instances.toml is machine-global; resolve it (global-wins) via the shared helper.
# shellcheck source=../lib/resolve_instances.sh
source "$SCRIPT_DIR/../lib/resolve_instances.sh"
INSTANCES_TOML="$(_resolve_instances)"
INSTANCES_IO="$SCRIPT_DIR/../lib/instances_io.py"
SPINUP_TIMEOUT="${SPINUP_TIMEOUT:-120}"

# ---------------------------------------------------------------------------
# arg parse: subcommand first, then optional --version X.Y
# ---------------------------------------------------------------------------
SUBCMD="${1:-}"
shift || true
VERSION=""
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
        *) echo "Unknown arg: $1" >&2; exit 2 ;;
    esac
done

# ---------------------------------------------------------------------------
# describe
# ---------------------------------------------------------------------------
cmd_describe() {
    echo "Spin up a declared Odoo instance (source or docker) and wait for HTTP 200 on /web/login"
}

# ---------------------------------------------------------------------------
# TOML reader - emit shell-eval-able KEY=VALUE lines for one instance.
# Delegates to lib/instances_io.py (tomllib on py3.11+, text-scan fallback on
# older Python). Selects by --version, else the highest valid X.Y series.
# ---------------------------------------------------------------------------
_read_instance() {
    # $1 = series (may be empty -> highest valid series).
    # Prints shell-safe KEY=VALUE lines (values shlex.quote'd) so the caller can
    # `eval` them even when a path contains spaces or shell metacharacters.
    [[ -f "$INSTANCES_TOML" ]] || return 1
    python3 "$INSTANCES_IO" read "$INSTANCES_TOML" "${1:-}"
}

# ---------------------------------------------------------------------------
# HTTP probe - returns the status code on /web/login (000 on connection fail)
# ---------------------------------------------------------------------------
_http_status() {
    # $1 = port
    curl -s -o /dev/null -w "%{http_code}" "http://localhost:$1/web/login" 2>/dev/null || echo "000"
}

# ---------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------
cmd_check() {
    # Non-zero exit OR empty output from the loader = no instance to check.
    local kv port rc=0
    kv="$(_read_instance "$VERSION")" || rc=$?
    [[ "$rc" -eq 0 && -n "$kv" ]] || return 1
    eval "$kv"
    port="${INST_HTTP_PORT:-8069}"
    [[ "$(_http_status "$port")" == "200" ]]
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
    IFS=':' read -ra _paths <<<"${INST_ADDONS_PATH:-}"
    for p in "${_paths[@]}"; do
        [[ -n "$p" ]] || continue
        if [[ -x "$p/odoo-bin" ]]; then echo "$p/odoo-bin"; return 0; fi
        if [[ -x "$(dirname "$p")/odoo-bin" ]]; then echo "$(dirname "$p")/odoo-bin"; return 0; fi
    done
    return 1
}

_poll_until_up() {
    # $1 = port. Poll /web/login until 200 or timeout. Returns 0 on success.
    local port="$1" elapsed=0 status
    echo "  Polling http://localhost:$port/web/login (timeout ${SPINUP_TIMEOUT}s)..."
    while (( elapsed < SPINUP_TIMEOUT )); do
        status="$(_http_status "$port")"
        if [[ "$status" == "200" ]]; then
            echo "  ok HTTP 200 after ${elapsed}s"
            return 0
        fi
        sleep 3
        elapsed=$((elapsed + 3))
    done
    echo "  x timed out after ${SPINUP_TIMEOUT}s (last status: ${status:-000})" >&2
    return 1
}

cmd_apply() {
    # The loader (lib/instances_io.py read) prints guidance to STDERR and exits
    # non-zero with EMPTY stdout when no valid instance exists. Capture the exit
    # status separately (`|| rc=$?` keeps `set -e` from aborting here) and treat
    # BOTH a non-zero exit AND empty output as "nothing to spin up" so we never
    # proceed with empty INST_* vars.
    local kv rc=0
    kv="$(_read_instance "$VERSION")" || rc=$?
    if [[ "$rc" -ne 0 || -z "$kv" ]]; then
        echo "x No usable Odoo instance found in $INSTANCES_TOML." >&2
        echo "  Declare one first: run the instance-profile step" >&2
        echo "  (40-instance-profile.sh apply) or edit instances.toml by hand." >&2
        return 1
    fi
    eval "$kv"
    local port="${INST_HTTP_PORT:-8069}"

    # Register this spin-up as the SHARED, NON-exclusive render target so other
    # sessions discover it (allocator.py query) and gc reclaims it when it dies.
    # Best-effort only: an absent allocator/python degrades to plain spin-up,
    # exactly as before. We register AFTER the server answers (never before), so
    # a failed start leaves NO stale lease and we never need a teardown release.
    local alloc_py="${ODOO_AI_ALLOCATOR-$SCRIPT_DIR/../lib/allocator.py}"
    _register_shared() {
        # $1 = optional live server pid. The pid is recorded only when it is
        # still alive, so a concurrent loser (whose odoo-bin lost the port bind
        # and exited) cannot overwrite the live winner's pid. created_db is
        # always False on a shared lease, so gc never drops the declared DB.
        [[ -n "$alloc_py" && -f "$alloc_py" ]] || return 0
        local args=(acquire --series "${INST_VERSION:-}" --mode shared
                    --port "$port" --db-name "${INST_DB_NAME:-odoo}")
        if [[ -n "${1:-}" ]] && kill -0 "$1" 2>/dev/null; then
            args+=(--pid "$1")
        fi
        python3 "$alloc_py" "${args[@]}" >/dev/null 2>&1 || true
    }

    if [[ "$(_http_status "$port")" == "200" ]]; then
        _register_shared
        echo "ok Instance ${INST_VERSION} already up at http://localhost:$port/web/login"
        return 0
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

            # ---- PREFLIGHT: verify python can import odoo BEFORE launching ----
            # Catching this here produces a clear actionable error instead of
            # launch-then-poll-timeout which wastes 120s and hides the real cause.
            if ! "$py" -c "import odoo" 2>/dev/null; then
                echo "" >&2
                echo "x PREFLIGHT FAILED: '$py' cannot import odoo." >&2
                echo "  Odoo will not start. Fix this BEFORE retrying:" >&2
                echo "    - Confirm the 'python' field in instances.toml points to a venv" >&2
                echo "      that has Odoo installed (run step 45 create-venv first)." >&2
                echo "    - Or set ODOO_PYTHON=/path/to/venv/bin/python." >&2
                echo "    - Or install Odoo in the active Python environment." >&2
                return 1
            fi

            # Determine the config key for the HTTP port: v8/9/10 use xmlrpc_port;
            # v11+ renamed it to http_port. Derive from INST_VERSION which carries
            # the full series string (e.g. "17.0", "10.0"). The major version is
            # the integer before the first dot.
            local _ver_major
            _ver_major="${INST_VERSION%%.*}"
            local _port_key
            if [[ "$_ver_major" =~ ^[0-9]+$ ]] && (( _ver_major < 11 )); then
                _port_key="xmlrpc_port"
            else
                _port_key="http_port"
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
            local db_name="${INST_DB_NAME:-odoo}"
            if command -v pg_isready >/dev/null 2>&1; then
                if ! pg_isready -h "$db_host" -U "$db_user" -d "$db_name" -q 2>/dev/null; then
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
                echo "addons_path = $(printf '%s' "${INST_ADDONS_PATH:-}" | tr ':' ',')"
                echo "$_port_key = $port"
                echo "db_name = ${INST_DB_NAME:-odoo}"
                echo "db_host = ${INST_DB_HOST:-localhost}"
                echo "db_user = ${INST_DB_USER:-odoo}"
                # Password ONLY from env - never echoed from a stored file.
                if [[ -n "${ODOO_PG_PASSWORD:-}" ]]; then
                    echo "db_password = ${ODOO_PG_PASSWORD}"
                fi
            } >"$conf"
            echo "  Generated temp conf: $conf"
            echo "  Launching: $py '$bin' -c '$conf' -d '${INST_DB_NAME:-odoo}' --dev=all"
            # Run in background so we can poll. Logs to a temp file.
            # Capture the PID directly (no subshell `( )`, which would hide it)
            # so a poll timeout can terminate the orphaned process.
            local logf _logs_dir _db_slug _ts
            # Write log to a stable, named path so a calling agent can capture it
            # across invocations. Dir: ${ODOO_AI_HOME:-$HOME}/.odoo-ai/logs/
            # File: <db>-<UTC-timestamp>.log (e.g. odoo_test-20260620T153012Z.log)
            _logs_dir="${ODOO_AI_HOME:-${HOME:-/tmp}}/.odoo-ai/logs"
            mkdir -p "$_logs_dir"
            _db_slug="${INST_DB_NAME:-odoo}"
            _ts="$(date -u +%Y%m%dT%H%M%SZ 2>/dev/null || date -u +%Y%m%d%H%M%S)"
            logf="$_logs_dir/${_db_slug}-${_ts}.log"
            echo "LOG_PATH=$logf"
            "$py" "$bin" -c "$conf" -d "${INST_DB_NAME:-odoo}" --dev=all >"$logf" 2>&1 &
            odoo_pid=$!
            echo "  Odoo starting (pid: $odoo_pid, log: $logf)"
            ;;
        *)
            echo "x Unknown run_mode: ${INST_RUN_MODE}. Use 'source' or 'docker'." >&2
            return 1
            ;;
    esac

    if _poll_until_up "$port"; then
        _register_shared "$odoo_pid"
        echo "ok Odoo ${INST_VERSION} is up: http://localhost:$port/web/login"
        return 0
    fi

    # Poll timed out - tear down what we started so we leave no orphan.
    echo "x Odoo did not become ready. Check the launch log above." >&2
    if [[ "$run_mode" == "source" ]]; then
        if [[ -n "$odoo_pid" ]]; then
            echo "  Stopping background Odoo (pid $odoo_pid)" >&2
            kill "$odoo_pid" 2>/dev/null || true
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
