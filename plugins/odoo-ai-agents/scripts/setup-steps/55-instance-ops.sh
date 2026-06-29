#!/usr/bin/env bash
# 55-instance-ops.sh - Mechanical runner for Odoo module operations and tests.
#
# This script is the EXECUTION layer: it receives fully-resolved flags from its
# caller (the odoo-instance-ops agent, which resolves per-version flags via OSM
# cli_help) and runs the appropriate odoo-bin command with a persistent log.
#
# It does NOT resolve version-specific flags; those arrive pre-resolved via
# --extra. It does NOT read instances.toml; all connection parameters are
# passed explicitly.
#
# Subcommands:
#   describe  - one-line purpose (step-script contract)
#   check     - lightweight; always exits 0 (on-demand ops script, not installer)
#   apply     - alias for init (for step-runner compat; same args as init)
#   init    --db <db> --python <venv_py> --addons <path> --modules <a,b>
#             [--extra "<resolved flags>"]
#             Run: $python $odoo_bin -d <db> -i <modules> --addons-path <addons>
#                  --stop-after-init <extra>
#             Persistent log + LOG_PATH= + STATUS= lines.
#   update  --db <db> --python <venv_py> --addons <path> --modules <a,b>
#             [--extra "<resolved flags>"]
#             Same as init but with -u instead of -i.
#   test    --db <db> --python <venv_py> --addons <path> --modules <a,b>
#             [--test-tags <tags>] [--mode fresh|reuse] [--log-mode warn|info|debug|sql]
#             [--extra "<resolved flags>"]
#             Run with <-i|-u> <modules> --test-enable [--test-tags <tags>]
#             --stop-after-init. --mode fresh (default) -> -i (new DB / modules not yet
#             installed; init+test in one pass); --mode reuse -> -u (DB already has the
#             modules; re-running tests, where -i would be a no-op). --log-mode maps to
#             the odoo log flag (warn/info/debug -> --log-level=<v>, sql ->
#             --log-handler=odoo.sql_db:DEBUG); omitted keeps --log-level=test. The log
#             flag is placed before --extra so --extra can still override it.
#             Parses result and emits TEST_RESULT=passed|failed plus the TEST_FAILED/
#             TEST_ERROR/TEST_WARNING counts and FINDINGS_PATH (a file holding the
#             failing-test names + traceback heads and the warning lines).
#   drop    --db <db> --python <venv_py> [--db-host H] [--db-user U]
#             Invoke scripts/lib/odoo_db.py drop <db> via the instance venv python.
#             Exit 10 from odoo_db.py -> clear venv-unavailable error (NOT a raw dropdb).
#
# LOG convention (mirrors 50-instance-spinup.sh):
#   Dir:  ${ODOO_AI_HOME:-$HOME/.odoo-ai}/logs/
#     ODOO_AI_HOME IS the .odoo-ai dir (allocator semantic); .odoo-ai is appended
#     ONLY in the HOME fallback so the path is consistent with allocator.py _home().
#   File: <db>-<UTC-ts>.log  (e.g. mydb-20260620T153012Z.log)
#   Line: LOG_PATH=<absolute-path>   (parseable; one per operation)
#
# STATUS line:  STATUS=ok|error        (parseable; always emitted)
# TEST_RESULT:  TEST_RESULT=passed|failed  (parseable; only for `test` verb)
# TEST counts:  TEST_FAILED=<n> TEST_ERROR=<n> TEST_WARNING=<n>
#               (parseable; `test` verb only; best-effort from the log)
# FINDINGS_PATH: FINDINGS_PATH=<path>  (`test` verb only; a file written next to the log
#               holding the FAIL/ERROR test names + traceback heads and the WARNING lines,
#               with in-scope warnings - mentioning a --modules name - listed separately)
#
# odoo-bin location:
#   Env ODOO_BIN wins; else scan addons entries one-level-up for odoo-bin.
#
# CONFIG env:
#   ODOO_AI_HOME   machine-global dir  (default $HOME/.odoo-ai)
#   ODOO_BIN       path to odoo-bin (override; auto-detected otherwise)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="$SCRIPT_DIR/../lib"
ODOO_DB_PY="$LIB_DIR/odoo_db.py"

# ---------------------------------------------------------------------------
# describe
# ---------------------------------------------------------------------------
cmd_describe() {
    echo "Run Odoo module init/update/test/drop operations with a persistent log"
}

# ---------------------------------------------------------------------------
# check - always satisfied (on-demand ops, not an idempotent installer)
# ---------------------------------------------------------------------------
cmd_check() {
    return 0
}

# ---------------------------------------------------------------------------
# _find_odoo_bin - locate odoo-bin via ODOO_BIN env or addons-path scan
# ---------------------------------------------------------------------------
_find_odoo_bin() {
    local addons_path="$1"
    if [[ -n "${ODOO_BIN:-}" && -x "${ODOO_BIN}" ]]; then
        echo "$ODOO_BIN"
        return 0
    fi
    local p
    IFS=':' read -ra _paths <<< "${addons_path}"
    for p in "${_paths[@]}"; do
        [[ -n "$p" ]] || continue
        if [[ -x "$p/odoo-bin" ]]; then echo "$p/odoo-bin"; return 0; fi
        if [[ -x "$(dirname "$p")/odoo-bin" ]]; then echo "$(dirname "$p")/odoo-bin"; return 0; fi
    done
    return 1
}

# ---------------------------------------------------------------------------
# _open_log - set $logf, mkdir, emit LOG_PATH=
# ---------------------------------------------------------------------------
_open_log() {
    local db_slug="$1"
    local logs_dir
    logs_dir="${ODOO_AI_HOME:-${HOME:-/tmp}/.odoo-ai}/logs"
    mkdir -p "$logs_dir"
    local ts
    ts="$(date -u +%Y%m%dT%H%M%SZ 2>/dev/null || date -u +%Y%m%d%H%M%S)"
    logf="$logs_dir/${db_slug}-${ts}.log"
    echo "LOG_PATH=$logf"
}

# ---------------------------------------------------------------------------
# _parse_test_result - read $logf + $1 (exit code) -> emit TEST_RESULT= plus the
#   TEST_FAILED/TEST_ERROR/TEST_WARNING counts and a FINDINGS_PATH file.
#   Reads $logf and (best-effort) $arg_modules from the caller's scope (bash
#   dynamic scope) to mark in-scope warnings.
# ---------------------------------------------------------------------------
_parse_test_result() {
    local exit_code="$1"

    # --- Counts + findings file (always; independent of the pass/fail verdict) ---
    # Odoo logs each failing test as a "FAIL:" line and each errored test as an
    # "ERROR:" line (the message body, distinct from the " ERROR " log level);
    # warning log lines carry the " WARNING " level token. These markers are the
    # most version-stable signal, so counts are derived from them best-effort.
    local n_fail n_error n_warn
    n_fail="$(grep -cE '(^|[[:space:]])FAIL:' "$logf" 2>/dev/null || true)"
    n_error="$(grep -cE '(^|[[:space:]])ERROR:' "$logf" 2>/dev/null || true)"
    n_warn="$(grep -cE '[[:space:]]WARNING[[:space:]]' "$logf" 2>/dev/null || true)"
    n_fail="${n_fail:-0}"; n_error="${n_error:-0}"; n_warn="${n_warn:-0}"

    # Per-volume contract: the DETAIL goes to a file next to the log; stdout
    # carries only the counts + the pointer.
    local findings="${logf%.log}.findings.md"
    local tb_head=20 warn_cap=50
    local mod_regex=""
    [[ -n "${arg_modules:-}" ]] && mod_regex="${arg_modules//,/|}"

    {
        echo "# Test findings"
        echo
        echo "Log: $logf"
        echo "Counts: failed=$n_fail error=$n_error warning=$n_warn"
        echo
        echo "## Failures and errors (marker line + first $tb_head lines)"
        echo
        if [[ "$n_fail" -gt 0 || "$n_error" -gt 0 ]]; then
            echo '```'
            grep -E -A "$tb_head" '(^|[[:space:]])(FAIL|ERROR):' "$logf" 2>/dev/null || true
            echo '```'
        else
            echo "_No failing or errored tests detected in the log._"
        fi
        echo
        echo "## In-scope warnings (mention a --modules name, capped at $warn_cap)"
        echo
        echo '```'
        if [[ -n "$mod_regex" ]]; then
            grep -E '[[:space:]]WARNING[[:space:]]' "$logf" 2>/dev/null \
                | grep -E "$mod_regex" 2>/dev/null | head -n "$warn_cap" || true
        fi
        echo '```'
        echo
        echo "## All warnings (capped at $warn_cap)"
        echo
        echo '```'
        grep -E '[[:space:]]WARNING[[:space:]]' "$logf" 2>/dev/null | head -n "$warn_cap" || true
        echo '```'
    } >"$findings" 2>/dev/null || true

    echo "TEST_FAILED=$n_fail"
    echo "TEST_ERROR=$n_error"
    echo "TEST_WARNING=$n_warn"
    echo "FINDINGS_PATH=$findings"

    # --- Pass/fail verdict (unchanged decision logic) ---
    if [[ "$exit_code" -ne 0 ]]; then
        echo "TEST_RESULT=failed"
        return
    fi
    # Odoo prints summary lines like:
    #   Ran N test(s) in Xs: 0 failed, 0 error(s) (at_install)
    #   FAIL: ...
    #   ERROR: ...
    if grep -qE 'FAIL:|ERROR:' "$logf" 2>/dev/null; then
        echo "TEST_RESULT=failed"
        return
    fi
    # Check for failure summary: "N failed" or "N error" (non-zero counts)
    if grep -qE '[1-9][0-9]* (failed|error)' "$logf" 2>/dev/null; then
        echo "TEST_RESULT=failed"
        return
    fi
    # Explicit pass marker: "0 failed, 0 error"
    if grep -qE '0 failed, 0 error' "$logf" 2>/dev/null; then
        echo "TEST_RESULT=passed"
        return
    fi
    # Exit 0 with no failure markers -> passed
    echo "TEST_RESULT=passed"
}

# ---------------------------------------------------------------------------
# _parse_common_args - parse --db/--python/--addons/--modules/--extra plus the
#   optional --test-tags/--mode/--log-mode flags.
# Sets: arg_db, arg_python, arg_addons, arg_modules, arg_extra, arg_test_tags,
#       arg_mode (default 'fresh'), arg_log_mode (default '').
#   --mode and --log-mode are optional (NOT added to the required-args check).
# ---------------------------------------------------------------------------
_parse_common_args() {
    arg_db=""
    arg_python=""
    arg_addons=""
    arg_modules=""
    arg_extra=""
    arg_mode="fresh"
    arg_log_mode=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --db)
                [[ $# -ge 2 ]] || { echo "$(basename "$0"): --db requires a value" >&2; exit 2; }
                arg_db="$2"; shift 2 ;;
            --python)
                [[ $# -ge 2 ]] || { echo "$(basename "$0"): --python requires a value" >&2; exit 2; }
                arg_python="$2"; shift 2 ;;
            --addons)
                [[ $# -ge 2 ]] || { echo "$(basename "$0"): --addons requires a value" >&2; exit 2; }
                arg_addons="$2"; shift 2 ;;
            --modules)
                [[ $# -ge 2 ]] || { echo "$(basename "$0"): --modules requires a value" >&2; exit 2; }
                arg_modules="$2"; shift 2 ;;
            --extra)
                [[ $# -ge 2 ]] || { echo "$(basename "$0"): --extra requires a value" >&2; exit 2; }
                arg_extra="$2"; shift 2 ;;
            --test-tags)
                [[ $# -ge 2 ]] || { echo "$(basename "$0"): --test-tags requires a value" >&2; exit 2; }
                arg_test_tags="$2"; shift 2 ;;
            --mode)
                [[ $# -ge 2 ]] || { echo "$(basename "$0"): --mode requires a value" >&2; exit 2; }
                case "$2" in
                    fresh|reuse) arg_mode="$2" ;;
                    *) echo "$(basename "$0"): --mode must be 'fresh' or 'reuse' (got '$2')" >&2; exit 2 ;;
                esac
                shift 2 ;;
            --log-mode)
                [[ $# -ge 2 ]] || { echo "$(basename "$0"): --log-mode requires a value" >&2; exit 2; }
                case "$2" in
                    warn|info|debug|sql) arg_log_mode="$2" ;;
                    *) echo "$(basename "$0"): --log-mode must be one of warn|info|debug|sql (got '$2')" >&2; exit 2 ;;
                esac
                shift 2 ;;
            *)
                echo "$(basename "$0"): unknown argument: $1" >&2; exit 2 ;;
        esac
    done

    [[ -n "$arg_db" ]]      || { echo "$(basename "$0"): --db is required" >&2; exit 2; }
    [[ -n "$arg_python" ]]  || { echo "$(basename "$0"): --python is required" >&2; exit 2; }
    [[ -n "$arg_addons" ]]  || { echo "$(basename "$0"): --addons is required" >&2; exit 2; }
    [[ -n "$arg_modules" ]] || { echo "$(basename "$0"): --modules is required" >&2; exit 2; }
}

# ---------------------------------------------------------------------------
# cmd_init - install modules (-i)
# ---------------------------------------------------------------------------
cmd_init() {
    local arg_db arg_python arg_addons arg_modules arg_extra arg_test_tags arg_mode arg_log_mode
    _parse_common_args "$@"

    local odoo_bin
    odoo_bin="$(_find_odoo_bin "$arg_addons")" || {
        echo "x Could not locate odoo-bin. Set ODOO_BIN=/path/to/odoo-bin and retry." >&2
        exit 1
    }

    local logf
    _open_log "$arg_db"

    # Odoo expects comma-separated addons paths; the allocator/instances_io
    # hands them over as colon-delimited (shell PATH convention).  Convert here.
    local addons_csv="${arg_addons//:/, }"
    # Normalise: remove spaces after commas for Odoo's option parser.
    addons_csv="${addons_csv//,  /,}"
    addons_csv="${addons_csv//,  /,}"  # second pass for edge-case double spaces

    local rc=0
    # shellcheck disable=SC2086
    "$arg_python" "$odoo_bin" \
        -d "$arg_db" \
        -i "$arg_modules" \
        --addons-path "$addons_csv" \
        --stop-after-init \
        ${arg_extra} \
        >"$logf" 2>&1 || rc=$?

    if [[ "$rc" -eq 0 ]]; then
        echo "STATUS=ok"
    else
        echo "STATUS=error"
        echo "x init failed (exit $rc); see $logf" >&2
        exit "$rc"
    fi
}

# ---------------------------------------------------------------------------
# cmd_update - update modules (-u)
# ---------------------------------------------------------------------------
cmd_update() {
    local arg_db arg_python arg_addons arg_modules arg_extra arg_test_tags arg_mode arg_log_mode
    _parse_common_args "$@"

    local odoo_bin
    odoo_bin="$(_find_odoo_bin "$arg_addons")" || {
        echo "x Could not locate odoo-bin. Set ODOO_BIN=/path/to/odoo-bin and retry." >&2
        exit 1
    }

    local logf
    _open_log "$arg_db"

    # Odoo expects comma-separated addons paths; convert from colon-delimited.
    local addons_csv="${arg_addons//:/, }"
    addons_csv="${addons_csv//,  /,}"
    addons_csv="${addons_csv//,  /,}"

    local rc=0
    # shellcheck disable=SC2086
    "$arg_python" "$odoo_bin" \
        -d "$arg_db" \
        -u "$arg_modules" \
        --addons-path "$addons_csv" \
        --stop-after-init \
        ${arg_extra} \
        >"$logf" 2>&1 || rc=$?

    if [[ "$rc" -eq 0 ]]; then
        echo "STATUS=ok"
    else
        echo "STATUS=error"
        echo "x update failed (exit $rc); see $logf" >&2
        exit "$rc"
    fi
}

# ---------------------------------------------------------------------------
# cmd_test - run tests (-i + --test-enable [--test-tags ...] --stop-after-init)
# ---------------------------------------------------------------------------
cmd_test() {
    local arg_db arg_python arg_addons arg_modules arg_extra arg_test_tags="" arg_mode arg_log_mode
    _parse_common_args "$@"

    local odoo_bin
    odoo_bin="$(_find_odoo_bin "$arg_addons")" || {
        echo "x Could not locate odoo-bin. Set ODOO_BIN=/path/to/odoo-bin and retry." >&2
        exit 1
    }

    local logf
    _open_log "$arg_db"

    local test_tags_args=()
    if [[ -n "${arg_test_tags:-}" ]]; then
        test_tags_args=("--test-tags" "$arg_test_tags")
    fi

    # Odoo expects comma-separated addons paths; convert from colon-delimited.
    local addons_csv="${arg_addons//:/, }"
    addons_csv="${addons_csv//,  /,}"
    addons_csv="${addons_csv//,  /,}"

    # mode: fresh (default) -> -i (new DB / modules not yet installed; init+test in
    # one pass); reuse -> -u (DB already has the modules; re-running tests, where -i
    # would be a no-op). Confirm -i/-u semantics via OSM cli_help.
    local mode_flag="-i"
    [[ "${arg_mode:-fresh}" == "reuse" ]] && mode_flag="-u"

    # Resolve the log verbosity flag. Omitted -> --log-level=test (default). Placed
    # before ${arg_extra} so a --log-level/--log-handler in --extra still overrides.
    local log_flag_args=()
    case "${arg_log_mode:-}" in
        warn)  log_flag_args=("--log-level=warn") ;;
        info)  log_flag_args=("--log-level=info") ;;
        debug) log_flag_args=("--log-level=debug") ;;
        sql)   log_flag_args=("--log-handler=odoo.sql_db:DEBUG") ;;
        *)     log_flag_args=("--log-level=test") ;;
    esac

    local rc=0
    # shellcheck disable=SC2086
    "$arg_python" "$odoo_bin" \
        -d "$arg_db" \
        "$mode_flag" "$arg_modules" \
        --addons-path "$addons_csv" \
        --test-enable \
        "${test_tags_args[@]}" \
        --stop-after-init \
        "${log_flag_args[@]}" \
        ${arg_extra} \
        >"$logf" 2>&1 || rc=$?

    _parse_test_result "$rc"

    if [[ "$rc" -eq 0 ]]; then
        echo "STATUS=ok"
    else
        echo "STATUS=error"
        # Note: TEST_RESULT=failed already emitted above; do NOT exit early so
        # both TEST_RESULT and STATUS lines are always printed before exiting.
        exit "$rc"
    fi
}

# ---------------------------------------------------------------------------
# cmd_drop - drop a database through Odoo (odoo_db.py); never raw dropdb
# ---------------------------------------------------------------------------
cmd_drop() {
    local arg_db="" arg_python="" arg_db_host="" arg_db_user="" arg_addons="" arg_modules="" arg_extra="" arg_test_tags="" arg_mode="" arg_log_mode=""

    # Parse drop-specific args (subset of common + optional db-host/db-user).
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --db)
                [[ $# -ge 2 ]] || { echo "$(basename "$0"): --db requires a value" >&2; exit 2; }
                arg_db="$2"; shift 2 ;;
            --python)
                [[ $# -ge 2 ]] || { echo "$(basename "$0"): --python requires a value" >&2; exit 2; }
                arg_python="$2"; shift 2 ;;
            --db-host)
                [[ $# -ge 2 ]] || { echo "$(basename "$0"): --db-host requires a value" >&2; exit 2; }
                arg_db_host="$2"; shift 2 ;;
            --db-user)
                [[ $# -ge 2 ]] || { echo "$(basename "$0"): --db-user requires a value" >&2; exit 2; }
                arg_db_user="$2"; shift 2 ;;
            *)
                echo "$(basename "$0"): unknown argument for drop: $1" >&2; exit 2 ;;
        esac
    done

    [[ -n "$arg_db" ]]     || { echo "$(basename "$0"): --db is required for drop" >&2; exit 2; }
    [[ -n "$arg_python" ]] || { echo "$(basename "$0"): --python is required for drop" >&2; exit 2; }

    [[ -f "$ODOO_DB_PY" ]] || {
        echo "x scripts/lib/odoo_db.py not found at $ODOO_DB_PY" >&2
        exit 1
    }

    local drop_args=("$ODOO_DB_PY" "drop" "$arg_db")
    [[ -n "$arg_db_host" ]] && drop_args+=("--db-host" "$arg_db_host")
    [[ -n "$arg_db_user" ]] && drop_args+=("--db-user" "$arg_db_user")

    local rc=0
    "$arg_python" "${drop_args[@]}" || rc=$?

    if [[ "$rc" -eq 10 ]]; then
        echo "x drop failed: venv unavailable - '$arg_python' cannot import odoo." >&2
        echo "  Ensure the venv python has Odoo installed (run step 45 first)." >&2
        echo "  Do NOT fall back to raw dropdb here; that is the allocator's decision." >&2
        exit 10
    elif [[ "$rc" -ne 0 ]]; then
        echo "x drop failed (exit $rc); odoo_db.py reported an error above." >&2
        exit "$rc"
    fi

    echo "STATUS=ok"
}

# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------
SUBCMD="${1:-}"
shift || true

case "$SUBCMD" in
    describe) cmd_describe ;;
    check)    cmd_check ;;
    apply)    cmd_init "$@" ;;
    init)     cmd_init "$@" ;;
    update)   cmd_update "$@" ;;
    test)     cmd_test "$@" ;;
    drop)     cmd_drop "$@" ;;
    *)
        echo "Usage: $(basename "$0") {describe|check|init|update|test|drop|apply} [args...]" >&2
        exit 2
        ;;
esac
