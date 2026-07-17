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
#             [--version <X.Y>] [--extra "<resolved flags>"]
#             Run: $python $odoo_bin -d <db> -i <modules> --addons-path <addons>
#                  --stop-after-init --log-level=warn
#                  --log-handler=<ns>.modules.loading:INFO <extra>
#             Persistent log + LOG_PATH= + STATUS= lines.
#
#             Deterministic completion contract (never a log-tail wait - see
#             docs/reference/INSTANCE-LIFECYCLE.md item 14): the process ALWAYS
#             runs with --stop-after-init, so completion is PROCESS EXIT, bounded
#             by nothing more than the caller's own foreground timeout. --version
#             resolves <ns> = 'openerp' for series < 10 (v8-v9), else 'odoo' (v10+;
#             also the default when --version is omitted) - the namespace Odoo's
#             module-loading logger lives under changed at the v9->v10 rename. The
#             --log-handler flag forces the "Modules loaded." completion line back
#             onto the log even under the --log-level=warn baseline (a per-logger
#             setLevel is applied AFTER the warn preset and overrides the inherited
#             level; plain `--log-handler=:INFO` on the root logger does NOT work).
#             SUCCESS = exit code 0 AND the "Modules loaded." marker is present AND
#             NONE of these failure markers appear: CRITICAL, Traceback (most
#             recent call last), invalid module names, ignored, Some modules are
#             not loaded, Unmet dependenc(y|ies), cannot be installed. Exit 0 ALONE
#             is NOT proof of install - three source-confirmed SILENT-skip paths
#             stay exit 0: a misspelled/nonexistent module name, an unresolved
#             dependency, and a demo-data failure downgraded to a warning. FAILURE
#             (non-zero exit, OR any failure marker, OR a missing "Modules
#             loaded." marker) -> non-zero return with the log path preserved for
#             diagnosis; this verb NEVER blocks on reading a log line to decide
#             completion, only on the process actually exiting.
#   update  --db <db> --python <venv_py> --addons <path> --modules <a,b>
#             [--version <X.Y>] [--extra "<resolved flags>"]
#             Same as init but with -u instead of -i; identical completion contract.
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
#   drop    --db <db> --python <venv_py> [--db-host H] [--db-user U] [--db-port P]
#             [--run-id ID] [--force]
#             Invoke scripts/lib/odoo_db.py drop <db> via the instance venv python.
#             --db-port threads to odoo_db.py when non-empty (empty -> omit).
#             Unless --force is given, always calls allocator.py assert-droppable first
#             (with whatever --run-id value the caller has, including an empty one for a
#             standalone/one-off caller) and refuses a fresh foreign lease (route via
#             release); --force overrides.
#             Exit 10 from odoo_db.py -> clear venv-unavailable error (NOT a raw dropdb).
#
# init/update/test also accept [--db-host H] [--db-user U] [--db-port P] so the
# CREATE/INIT/UPDATE/TEST connection matches the DROP connection (one declared
# port honored everywhere). All three run a `<python> <odoo-bin> --version`
# preflight and fail loud (no working venv; run 45-venv.sh) BEFORE any real run.
#   wait-log --log <logf> [--timeout <secs>] [--interval <secs>]
#             Deterministic build-completion detector for a build launched in the
#             BACKGROUND (Bash run_in_background). Polls <logf> for a TERMINAL marker
#             so the caller (odoo-instance-ops agent) never idle-stalls on a long
#             -i/-u/--test-enable build that would exceed the foreground tool timeout.
#             Emits BUILD_RESULT=success|failure|timeout plus BUILD_MARKER=<line> and
#             LOG_PATH=<logf>. Exit 0 (success), 1 (failure), 2 (timeout). The build's
#             own exit code stays authoritative; this is a completion + diagnostics
#             signal, NOT the running-server readiness probe (that is 50-instance-spinup.sh's
#             HTTP-200 probe). Markers are version-stable v8-v19. BUILD_RESULT=success/failure
#             share the SAME "Modules loaded." success marker and silent-skip failure-marker
#             regex as _install_confirmed (SSOT constants below) - so this background verdict
#             can NEVER disagree with the init/update script's own STATUS=ok|error line; a log
#             showing both "Modules loaded." and a silent-skip marker (e.g. "invalid module
#             names, ignored") reports BUILD_RESULT=failure, never success.
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
# _preflight_venv - verify `<python> <odoo-bin> --version` runs BEFORE any real
#   init/update/test. Mirrors 50-instance-spinup.sh's preflight so a wrong/stale
#   venv fails loud + early instead of as an opaque mid-run Odoo traceback.
# ---------------------------------------------------------------------------
_preflight_venv() {
    local py="$1" bin="$2"
    if ! "$py" "$bin" --version >/dev/null 2>&1; then
        echo "x PREFLIGHT FAILED: no working venv; run 45-venv.sh" >&2
        echo "  '$py' cannot run '$bin --version'. Fix BEFORE retrying:" >&2
        echo "    - Point --python at a venv with Odoo deps (45-venv.sh create-venv)." >&2
        exit 1
    fi
}

# ---------------------------------------------------------------------------
# _build_db_conn_args - populate the global array DB_CONN_ARGS with the odoo-bin
#   server flags for the declared connection, from the caller-scope
#   arg_db_host/arg_db_user/arg_db_port. Each flag is emitted ONLY when non-empty
#   (empty-omit -> ambient PG env / libpq / PGPORT resolves it). Flags are stable
#   `server` options across v8-v19.
# ---------------------------------------------------------------------------
_build_db_conn_args() {
    DB_CONN_ARGS=()
    [[ -n "${arg_db_host:-}" ]] && DB_CONN_ARGS+=("--db_host" "$arg_db_host")
    [[ -n "${arg_db_user:-}" ]] && DB_CONN_ARGS+=("--db_user" "$arg_db_user")
    [[ -n "${arg_db_port:-}" ]] && DB_CONN_ARGS+=("--db_port" "$arg_db_port")
    # Explicit success: the last [[ -n ... ]] is false when the port is empty, and
    # a bare-call function returning that non-zero status would trip `set -e`.
    return 0
}

# ---------------------------------------------------------------------------
# _resolve_log_ns - series -> the logger namespace Odoo's module-loading
#   logger lives under: 'openerp' for series < 10 (v8-v9), else 'odoo' (v10+ -
#   the openerp->odoo rename landed at the v9->v10 boundary). Empty/unparsable
#   series (e.g. --version omitted) defaults to 'odoo', the modern majority -
#   a caller that cares about v8-v9 must pass --version explicitly.
# ---------------------------------------------------------------------------
_resolve_log_ns() {
    local series="${1:-}" major
    major="${series%%.*}"
    if [[ "$major" =~ ^[0-9]+$ ]] && (( major < 10 )); then
        echo "openerp"
    else
        echo "odoo"
    fi
}

# ---------------------------------------------------------------------------
# Completion-marker SSOT - shared by _install_confirmed (foreground init/
#   update verdict) AND _scan_build_markers (background wait-log verdict) so
#   the two paths can NEVER diverge again. _INSTALL_FAIL_RE is the exact
#   silent-skip + hard-failure marker set; _INSTALL_SUCCESS_MARKER is the
#   completion line forced onto the log by --log-handler=<ns>.modules.
#   loading:INFO. A future marker added to the install/update contract is
#   added HERE ONLY - both call sites pick it up automatically.
# ---------------------------------------------------------------------------
_INSTALL_FAIL_RE='CRITICAL|Traceback \(most recent call last\)|invalid module names, ignored|Some modules are not loaded|Unmet dependenc|cannot be installed'
_INSTALL_SUCCESS_MARKER='Modules loaded.'

# ---------------------------------------------------------------------------
# _install_confirmed - single-pass positive-install check for a completed
#   (--stop-after-init) install/update job. Returns 0 (confirmed) iff the
#   "Modules loaded." completion marker is present - forced onto the log even
#   under --log-level=warn by --log-handler=<ns>.modules.loading:INFO - AND
#   NONE of the SILENT-skip failure markers appear. Exit code 0 from odoo-bin
#   is NOT proof of install on its own: a misspelled/nonexistent module name,
#   an unresolved dependency, or a demo-data failure can all leave the process
#   at exit 0 while silently skipping the requested install (see
#   docs/reference/INSTANCE-LIFECYCLE.md item 14). Never blocks - two grep
#   passes over the already-closed log file, no polling. Uses the shared
#   _INSTALL_FAIL_RE / _INSTALL_SUCCESS_MARKER SSOT above - _scan_build_markers
#   applies the SAME two constants so the background wait-log verdict can
#   never disagree with this one.
# ---------------------------------------------------------------------------
_install_confirmed() {
    local logf="$1"
    if grep -aqE "$_INSTALL_FAIL_RE" "$logf" 2>/dev/null; then
        return 1
    fi
    grep -aqF "$_INSTALL_SUCCESS_MARKER" "$logf" 2>/dev/null
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
# _scan_build_markers - single-pass terminal-marker scan of a build log.
#   Echoes BUILD_MARKER=<matched line> (best-effort) and returns:
#     0 -> the "Modules loaded." completion marker present AND no failure
#          marker seen - the SAME verdict _install_confirmed would reach on
#          this log (shared _INSTALL_FAIL_RE / _INSTALL_SUCCESS_MARKER SSOT
#          above), so BUILD_RESULT can never disagree with the script's own
#          STATUS=ok|error line for an init/update build.
#     1 -> a FAILURE marker present (wins over success: a silent-skip marker
#          such as "invalid module names, ignored" appearing alongside
#          "Modules loaded." is STILL a failed build, exactly as
#          _install_confirmed rules it - and a Traceback after "Registry
#          loaded" is still a failed build)
#     2 -> no terminal marker yet (build still in flight)
#   The failure set is a SUPERSET of _INSTALL_FAIL_RE (adds psycopg2./
#   ParseError/"Failed to load registry"/a bare ERROR line - broader build
#   failures outside _install_confirmed's narrower install-only scope, e.g. a
#   DB-connectivity error or an XML ParseError during a run-tests build).
#   "Registry loaded"/"Initiating shutdown"/a bare process exit 0 remain named
#   as progress/heartbeat signals in agents/odoo-instance-ops.md's
#   "Active-wait on long builds" section, but are NOT independently
#   sufficient for BUILD_RESULT=success here - only "Modules loaded." is,
#   matching _install_confirmed exactly. Markers are version-stable v8-v19;
#   the caller's own process exit code stays authoritative - this is the
#   in-log completion signal.
# ---------------------------------------------------------------------------
_scan_build_markers() {
    local logf="$1"
    [[ -f "$logf" ]] || return 2

    # FAILURE first - a failure marker anywhere means the build did not succeed,
    # even if an earlier line looked like progress. _INSTALL_FAIL_RE (SSOT,
    # shared with _install_confirmed) is unioned with broader generic build-
    # failure signals below.
    local fail_re="${_INSTALL_FAIL_RE}|[[:space:]]ERROR[[:space:]]|Failed to load registry|psycopg2\.|ParseError"
    local fail_line
    fail_line="$(grep -aE "$fail_re" "$logf" 2>/dev/null | head -n 1 || true)"
    if [[ -n "$fail_line" ]]; then
        echo "BUILD_MARKER=$fail_line"
        return 1
    fi

    # SUCCESS - the SAME completion marker _install_confirmed requires (SSOT:
    # _INSTALL_SUCCESS_MARKER). Never treat "Registry loaded" or "Initiating
    # shutdown" alone as success - see docstring above.
    local ok_line
    ok_line="$(grep -aF "$_INSTALL_SUCCESS_MARKER" "$logf" 2>/dev/null | head -n 1 || true)"
    if [[ -n "$ok_line" ]]; then
        echo "BUILD_MARKER=$ok_line"
        return 0
    fi

    return 2
}

# ---------------------------------------------------------------------------
# cmd_wait_log - bounded poll of a build log for a terminal marker.
# ---------------------------------------------------------------------------
cmd_wait_log() {
    local logf="" timeout=600 interval=5
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --log)
                [[ $# -ge 2 ]] || { echo "$(basename "$0"): --log requires a value" >&2; exit 2; }
                logf="$2"; shift 2 ;;
            --timeout)
                [[ $# -ge 2 ]] || { echo "$(basename "$0"): --timeout requires a value" >&2; exit 2; }
                timeout="$2"; shift 2 ;;
            --interval)
                [[ $# -ge 2 ]] || { echo "$(basename "$0"): --interval requires a value" >&2; exit 2; }
                interval="$2"; shift 2 ;;
            *)
                echo "$(basename "$0"): unknown argument for wait-log: $1" >&2; exit 2 ;;
        esac
    done
    [[ -n "$logf" ]] || { echo "$(basename "$0"): --log is required for wait-log" >&2; exit 2; }

    echo "LOG_PATH=$logf"

    local waited=0 rc=2 marker=""
    while :; do
        # _scan_build_markers returns non-zero for failure(1)/none(2); capture its
        # status without tripping `set -e` on the command substitution.
        set +e
        marker="$(_scan_build_markers "$logf")"
        rc=$?
        set -e
        if [[ "$rc" -ne 2 ]]; then
            break
        fi
        if [[ "$waited" -ge "$timeout" ]]; then
            rc=2
            break
        fi
        sleep "$interval"
        waited=$(( waited + interval ))
    done

    case "$rc" in
        0) echo "${marker:-BUILD_MARKER=}"; echo "BUILD_RESULT=success" ;;
        1) echo "${marker:-BUILD_MARKER=}"; echo "BUILD_RESULT=failure" ;;
        *) echo "BUILD_MARKER="; echo "BUILD_RESULT=timeout"
           echo "x wait-log timed out after ${timeout}s with no terminal marker; see $logf" >&2 ;;
    esac
    return "$rc"
}

# ---------------------------------------------------------------------------
# _parse_common_args - parse --db/--python/--addons/--modules/--extra plus the
#   optional --test-tags/--mode/--log-mode/--version flags.
# Sets: arg_db, arg_python, arg_addons, arg_modules, arg_extra, arg_test_tags,
#       arg_mode (default 'fresh'), arg_log_mode (default ''), arg_version
#       (default '' - init/update only; resolves the --log-handler namespace
#       via _resolve_log_ns; empty defaults to the v10+ 'odoo' namespace).
#   --mode/--log-mode/--version are optional (NOT added to the required-args
#   check).
# ---------------------------------------------------------------------------
_parse_common_args() {
    arg_db=""
    arg_python=""
    arg_addons=""
    arg_modules=""
    arg_extra=""
    arg_mode="fresh"
    arg_log_mode=""
    arg_version=""
    # Optional DB-connection flags (empty -> omitted so ambient PG env is preserved).
    # These make CREATE/INIT/UPDATE/TEST connect to the SAME cluster DROP uses.
    arg_db_host=""
    arg_db_user=""
    arg_db_port=""

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
            --db-port)
                [[ $# -ge 2 ]] || { echo "$(basename "$0"): --db-port requires a value" >&2; exit 2; }
                arg_db_port="$2"; shift 2 ;;
            --addons)
                [[ $# -ge 2 ]] || { echo "$(basename "$0"): --addons requires a value" >&2; exit 2; }
                arg_addons="$2"; shift 2 ;;
            --modules)
                [[ $# -ge 2 ]] || { echo "$(basename "$0"): --modules requires a value" >&2; exit 2; }
                arg_modules="$2"; shift 2 ;;
            --extra)
                [[ $# -ge 2 ]] || { echo "$(basename "$0"): --extra requires a value" >&2; exit 2; }
                arg_extra="$2"; shift 2 ;;
            --version)
                [[ $# -ge 2 ]] || { echo "$(basename "$0"): --version requires a value" >&2; exit 2; }
                arg_version="$2"; shift 2 ;;
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
    local arg_db arg_python arg_addons arg_modules arg_extra arg_test_tags arg_mode arg_log_mode arg_version
    local arg_db_host arg_db_user arg_db_port
    _parse_common_args "$@"

    local odoo_bin
    odoo_bin="$(_find_odoo_bin "$arg_addons")" || {
        echo "x Could not locate odoo-bin. Set ODOO_BIN=/path/to/odoo-bin and retry." >&2
        exit 1
    }
    _preflight_venv "$arg_python" "$odoo_bin"

    local logf
    _open_log "$arg_db"

    # Odoo expects comma-separated addons paths; the allocator/instances_io
    # hands them over as colon-delimited (shell PATH convention).  Convert here.
    local addons_csv="${arg_addons//:/, }"
    # Normalise: remove spaces after commas for Odoo's option parser.
    addons_csv="${addons_csv//,  /,}"
    addons_csv="${addons_csv//,  /,}"  # second pass for edge-case double spaces

    local DB_CONN_ARGS
    _build_db_conn_args

    # Deterministic completion contract (docs/reference/INSTANCE-LIFECYCLE.md
    # item 14): --log-handler=<ns>.modules.loading:INFO forces the "Modules
    # loaded." completion line back onto the log even under the --log-level=warn
    # baseline below (a per-logger setLevel wins over the inherited warn level).
    # <ns> is version-resolved via _resolve_log_ns (openerp v8-v9, odoo v10+).
    # Both flags are placed BEFORE ${arg_extra} so a caller-supplied
    # --log-level/--log-handler in --extra still overrides them (Odoo's arg
    # parser takes the last occurrence) - mirrors the `test` verb.
    local log_ns
    log_ns="$(_resolve_log_ns "${arg_version:-}")"

    local rc=0
    # shellcheck disable=SC2086
    # --stop-after-init is correct HERE by design: cmd_init is the EPHEMERAL
    # mutation-build mechanism (persist: ephemeral) - a throwaway install/init
    # that never listens. A LISTENING instance (persist: exclusive-running /
    # shared-running) never routes through this verb - it goes through
    # 50-instance-spinup.sh, the sole listening mechanism (P5.7). Do NOT try to
    # make this verb long-running; add a new op instead if that is ever needed.
    # Completion is PROCESS EXIT (this call blocks until odoo-bin exits) - never
    # a log-tail wait; the log is consulted ONLY afterward, to CONFIRM the exit
    # actually installed something (see _install_confirmed).
    "$arg_python" "$odoo_bin" \
        -d "$arg_db" \
        -i "$arg_modules" \
        --addons-path "$addons_csv" \
        "${DB_CONN_ARGS[@]}" \
        --stop-after-init \
        --log-level=warn \
        --log-handler="${log_ns}.modules.loading:INFO" \
        ${arg_extra} \
        >"$logf" 2>&1 || rc=$?

    if [[ "$rc" -eq 0 ]] && _install_confirmed "$logf"; then
        echo "STATUS=ok"
    else
        if [[ "$rc" -eq 0 ]]; then
            rc=1
            echo "STATUS=error"
            echo "x init reported exit 0 but no positive install confirmation (missing 'Modules loaded.' or a failure marker present); see $logf" >&2
        else
            echo "STATUS=error"
            echo "x init failed (exit $rc); see $logf" >&2
        fi
        exit "$rc"
    fi
}

# ---------------------------------------------------------------------------
# cmd_update - update modules (-u)
# ---------------------------------------------------------------------------
cmd_update() {
    local arg_db arg_python arg_addons arg_modules arg_extra arg_test_tags arg_mode arg_log_mode arg_version
    local arg_db_host arg_db_user arg_db_port
    _parse_common_args "$@"

    local odoo_bin
    odoo_bin="$(_find_odoo_bin "$arg_addons")" || {
        echo "x Could not locate odoo-bin. Set ODOO_BIN=/path/to/odoo-bin and retry." >&2
        exit 1
    }
    _preflight_venv "$arg_python" "$odoo_bin"

    local logf
    _open_log "$arg_db"

    # Odoo expects comma-separated addons paths; convert from colon-delimited.
    local addons_csv="${arg_addons//:/, }"
    addons_csv="${addons_csv//,  /,}"
    addons_csv="${addons_csv//,  /,}"

    local DB_CONN_ARGS
    _build_db_conn_args

    # Deterministic completion contract - identical to cmd_init (see its
    # comments above and docs/reference/INSTANCE-LIFECYCLE.md item 14):
    # --log-handler=<ns>.modules.loading:INFO forces "Modules loaded." back onto
    # the log under --log-level=warn; both flags precede ${arg_extra} so a
    # caller override still wins. `warn` is stable v8-v19.
    local log_ns
    log_ns="$(_resolve_log_ns "${arg_version:-}")"

    local rc=0
    # shellcheck disable=SC2086
    # Completion is PROCESS EXIT (this call blocks until odoo-bin exits) - never
    # a log-tail wait; the log is consulted ONLY afterward to CONFIRM the exit
    # actually updated something (see _install_confirmed).
    "$arg_python" "$odoo_bin" \
        -d "$arg_db" \
        -u "$arg_modules" \
        --addons-path "$addons_csv" \
        "${DB_CONN_ARGS[@]}" \
        --stop-after-init \
        --log-level=warn \
        --log-handler="${log_ns}.modules.loading:INFO" \
        ${arg_extra} \
        >"$logf" 2>&1 || rc=$?

    if [[ "$rc" -eq 0 ]] && _install_confirmed "$logf"; then
        echo "STATUS=ok"
    else
        if [[ "$rc" -eq 0 ]]; then
            rc=1
            echo "STATUS=error"
            echo "x update reported exit 0 but no positive confirmation (missing 'Modules loaded.' or a failure marker present); see $logf" >&2
        else
            echo "STATUS=error"
            echo "x update failed (exit $rc); see $logf" >&2
        fi
        exit "$rc"
    fi
}

# ---------------------------------------------------------------------------
# cmd_test - run tests (-i + --test-enable [--test-tags ...] --stop-after-init)
# ---------------------------------------------------------------------------
cmd_test() {
    local arg_db arg_python arg_addons arg_modules arg_extra arg_test_tags="" arg_mode arg_log_mode
    local arg_db_host arg_db_user arg_db_port
    _parse_common_args "$@"

    local odoo_bin
    odoo_bin="$(_find_odoo_bin "$arg_addons")" || {
        echo "x Could not locate odoo-bin. Set ODOO_BIN=/path/to/odoo-bin and retry." >&2
        exit 1
    }
    _preflight_venv "$arg_python" "$odoo_bin"

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

    local DB_CONN_ARGS
    _build_db_conn_args

    local rc=0
    # shellcheck disable=SC2086
    "$arg_python" "$odoo_bin" \
        -d "$arg_db" \
        "$mode_flag" "$arg_modules" \
        --addons-path "$addons_csv" \
        "${DB_CONN_ARGS[@]}" \
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
#
# This is the bare-UNMANAGED-DB path: NO allocator lease, NO server pid tracked.
# There is no process group to stop here (a LEASED, listening instance is torn
# down via `allocator.py release`, which stops the server's process group FIRST -
# see scripts/lib/allocator.py _stop_group - THEN drops). For an unmanaged DB,
# odoo_db.py's own pg_terminate_backend (session-terminate) before DROP DATABASE
# suffices; do NOT add stop-group logic here (SSOT stays in the allocator).
# ---------------------------------------------------------------------------
cmd_drop() {
    local arg_db="" arg_python="" arg_db_host="" arg_db_user="" arg_db_port="" arg_run_id="" arg_force=""

    # Parse drop-specific args (subset of common + optional db-host/db-user/db-port
    # + ownership guard --run-id/--force).
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
            --db-port)
                [[ $# -ge 2 ]] || { echo "$(basename "$0"): --db-port requires a value" >&2; exit 2; }
                arg_db_port="$2"; shift 2 ;;
            --run-id)
                [[ $# -ge 2 ]] || { echo "$(basename "$0"): --run-id requires a value" >&2; exit 2; }
                arg_run_id="$2"; shift 2 ;;
            --force)
                arg_force="1"; shift ;;
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

    # Ownership guard: a bare-name drop is for UNMANAGED DBs only. Unless --force is
    # given, always confirm the DB is not held by a FRESH lease owned by a DIFFERENT
    # run (route that through the allocator's race-free `release`) - this MUST also
    # run when arg_run_id is empty, since a standalone/one-off caller (the caller most
    # likely to be nuking a DB it does not own) always has an empty run id. assert-
    # droppable treats an empty caller run as "no run of mine" - it still refuses a
    # DB with a fresh lease owned by any non-empty run, and still passes cleanly for
    # an unmanaged DB (no lease at all) - so this is safe to make unconditional.
    if [[ -z "$arg_force" ]]; then
        local alloc_py="$LIB_DIR/allocator.py"
        if [[ -f "$alloc_py" ]]; then
            if ! python3 "$alloc_py" assert-droppable --db-name "$arg_db" --run-id "$arg_run_id" >/dev/null 2>&1; then
                echo "x drop refused: '$arg_db' is held by a FRESH lease owned by a different run." >&2
                echo "  Route the drop through 'allocator.py release <token>' (race-free ownership check)," >&2
                echo "  or pass --force to reap a foreign/stale lease." >&2
                exit 1
            fi
        fi
    fi

    local drop_args=("$ODOO_DB_PY" "drop" "$arg_db")
    [[ -n "$arg_db_host" ]] && drop_args+=("--db-host" "$arg_db_host")
    [[ -n "$arg_db_user" ]] && drop_args+=("--db-user" "$arg_db_user")
    [[ -n "$arg_db_port" ]] && drop_args+=("--db-port" "$arg_db_port")

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
    wait-log) cmd_wait_log "$@" ;;
    *)
        echo "Usage: $(basename "$0") {describe|check|init|update|test|drop|wait-log|apply} [args...]" >&2
        exit 2
        ;;
esac
