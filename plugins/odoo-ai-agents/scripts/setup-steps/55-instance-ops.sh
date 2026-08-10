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
#                  --stop-after-init --log-level=info
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
#             --log-handler flag is a FLOOR, not a workaround: it keeps the
#             "Modules loaded." completion line on the log at ANY level a
#             caller may pass in <extra>, including a quieter one.
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
#             completion, only on the process actually exiting. The launch is
#             ALSO wrapped in a `ulimit -Sv`+`--limit-memory-hard=` resource-limit
#             guard (see below and snippets/odoo-bin-resource-limits.md).
#   update  --db <db> --python <venv_py> --addons <path> --modules <a,b>
#             [--version <X.Y>] [--extra "<resolved flags>"]
#             Same as init but with -u instead of -i; identical completion contract.
#   test    --db <db> --python <venv_py> --addons <path> --modules <a,b>
#             [--test-tags <tags>] [--mode fresh|reuse] [--log-mode info|debug|sql]
#             [--version <X.Y>] [--extra "<resolved flags>"]
#             Run with <-i|-u> <modules> --test-enable [--test-tags <tags>]
#             --stop-after-init. --mode fresh (default) -> -i (new DB / modules not yet
#             installed; init+test in one pass); --mode reuse -> -u (DB already has the
#             modules; re-running tests, where -i would be a no-op). --log-mode maps to
#             the odoo log flag (debug -> --log-level=debug, sql -> --log-handler=
#             odoo.sql_db:DEBUG); omitted keeps the shared $_DEFAULT_LOG_LEVEL default.
#             `warn` is REFUSED (exit 2): it suppresses the pass summary, so every
#             green run under it would parse as inconclusive.
#             Parses result and emits TEST_RESULT=passed|failed|inconclusive plus the
#             TEST_FAILED/TEST_ERROR/TEST_WARNING/TEST_SKIPPED counts and FINDINGS_PATH
#             (a file holding the failing-test names + traceback heads, the warning
#             lines, and any skipped-test names). TEST_RESULT=failed also covers an
#             INSTALL failure inside the build (no test could run). inconclusive fires
#             when TEST_SKIPPED>0 and no failure occurred, AND whenever the log carries
#             no era-correct "the suite ran" marker at all: "0 failed, 0 error(s) of 1
#             tests" can mean the sole test was SKIPPED (never ran), and an exit-0 run
#             whose tag filter matched nothing produces no marker at all - a bare
#             TEST_RESULT=passed would falsely certify both. Skips are NOT fatal
#             (legitimate via @tagged filters or missing external deps): they are
#             reported, never swallowed into an unqualified pass, and never force a
#             non-zero exit on their own. --version picks the era-correct marker
#             (v8-v13 "Ran <N> tests in <X>s" vs v14+ "<F> failed, <E> error(s) of <T>
#             tests"); omitted, EITHER wording is accepted.
#             Also emits MODULES_LOADED=<n> and TESTS_RUN=<n> - the SCOPE the run
#             actually covered, as machine output rather than something a caller
#             has to grep for and retype. EMPTY means the log carried no such
#             marker (unmeasured), never 0. The whole summary block is ALSO
#             appended to the log, so `wait-log` can surface the verdict.
#   drop    --db <db> --python <venv_py> [--db-host H] [--db-user U] [--db-port P]
#             [--odoo-root R] [--run-id ID] [--force]
#             Invoke scripts/lib/odoo_db.py drop <db> via the instance venv python.
#             --db-port threads to odoo_db.py when non-empty (empty -> omit).
#             --odoo-root threads the instance's declared odoo_root the same way:
#             a source checkout needs it for `import odoo` to resolve at all.
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
#
# RESOURCE LIMITS (init/update/test only - Problem 1 hardening): the odoo-bin
# launch runs in a scoped subshell `( ulimit -Sv <kib> ...; <odoo-bin cmd> ...
# --limit-memory-hard=<bytes> ... ${arg_extra} )` - both driven by
# scripts/lib/resource_limits.sh, overridable via ODOO_AI_LIMIT_MEMORY_HARD.
# Full policy (why both mechanisms, the v12.0 enforcement boundary, the
# uncapped escape hatch): snippets/odoo-bin-resource-limits.md.
#   wait-log --log <logf> [--timeout <secs>] [--interval <secs>]
#             Blocks in the FOREGROUND until a terminal marker appears or the
#             bound elapses, then prints BUILD_RESULT=success|failure|timeout.
#             The DEFAULT bound is deliberately below the harness's per-call
#             ceiling (see _WAIT_LOG_DEFAULT_TIMEOUT_S) so ONE call always
#             returns a verdict; for a longer build, re-invoke it.
#             Deterministic build-completion detector for a build launched in the
#             BACKGROUND (Bash run_in_background). Polls <logf> for a TERMINAL marker
#             so the caller (odoo-instance-ops agent) never idle-stalls on a long
#             -i/-u/--test-enable build that would exceed the foreground tool timeout.
#             Emits BUILD_RESULT=success|failure|timeout plus BUILD_MARKER=<line> and
#             LOG_PATH=<logf>. Exit 0 (success), 1 (failure), 2 (timeout). The build's
#             own exit code stays authoritative; this is a completion + diagnostics
#             signal, NOT the running-server readiness probe (that is 50-instance-spinup.sh's
#             HTTP-200 probe). Markers are version-stable v8-v19.
#             The terminal predicate is resolved from the log's OWN run-verb stamp
#             (_RUN_VERB_STAMP, written by _open_log):
#               init/update - "Modules loaded." plus the silent-skip failure-marker
#                 regex, the SAME SSOT constants _install_confirmed applies, so this
#                 background verdict can NEVER disagree with the script's own
#                 STATUS=ok|error line; a log showing both "Modules loaded." and a
#                 silent-skip marker (e.g. "invalid module names, ignored") reports
#                 BUILD_RESULT=failure, never success.
#               test - the run's own TEST_RESULT= line (appended to the log by the
#                 `test` verb, and echoed back here) or, before that lands, the
#                 era-correct "the suite ran" marker; the failure set additionally
#                 unions _TEST_FAIL_RE. "Modules loaded." is only PROGRESS for a
#                 test run: Odoo logs it before the post-install suite starts, so
#                 certifying there would stop the wait while the tests have not
#                 begun. BUILD_RESULT answers "has it finished"; TEST_RESULT (echoed
#                 when the log carries it) is the pass/fail verdict.
#
# LOG convention (mirrors 50-instance-spinup.sh):
#   Dir:  ${ODOO_AI_HOME:-$HOME/.odoo-ai}/logs/
#     ODOO_AI_HOME IS the .odoo-ai dir (allocator semantic); .odoo-ai is appended
#     ONLY in the HOME fallback so the path is consistent with allocator.py _home().
#   File: <db>-<UTC-ts>.log  (e.g. mydb-20260620T153012Z.log)
#   Line: LOG_PATH=<absolute-path>   (parseable; one per operation)
#   The log's FIRST line is the run-verb stamp (_RUN_VERB_STAMP=<verb> SERIES=<X.Y>),
#   which is what lets `wait-log` pick the era- and verb-correct terminal predicate
#   from the log alone. Every writer APPENDS after that line.
#
# STATUS line:  STATUS=ok|error        (parseable; always emitted)
# TEST_RESULT:  TEST_RESULT=passed|failed|inconclusive  (parseable; only for `test` verb;
#               failed means a non-zero exit, a test-failure marker, or an install
#               failure; inconclusive means TEST_SKIPPED>0 with no failure, or no
#               era-correct "the suite ran" marker at all - tests were never proven to
#               have run; NEVER reported as a bare `passed`)
# TEST counts:  TEST_FAILED=<n> TEST_ERROR=<n> TEST_WARNING=<n> TEST_SKIPPED=<n>
#               (parseable; `test` verb only; best-effort from the log)
# TEST scope:   MODULES_LOADED=<n> TESTS_RUN=<n>  (parseable; `test` verb only;
#               EMPTY when the log carries no marker for it - unmeasured, not zero)
# FINDINGS_PATH: FINDINGS_PATH=<path>  (`test` verb only; a file written next to the log
#               holding the FAIL/ERROR test names + traceback heads, the WARNING lines
#               (in-scope warnings - mentioning a --modules name - listed separately),
#               and any SKIPPED-test names)
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
# Resource-limit SSOT (Problem 1 hardening) - resolves the memory HARD cap
# for the ulimit/--limit-memory-hard wrapper on all 3 odoo-bin verbs below.
# Policy: snippets/odoo-bin-resource-limits.md. Values: scripts/lib/resource_limits.sh.
# shellcheck source=../lib/resource_limits.sh
source "$LIB_DIR/resource_limits.sh"
# addons_path separator SSOT mirror (_addons_path_to_array) - see
# scripts/lib/instances_io.py's join_addons_path/split_addons_path docstring.
# shellcheck source=../lib/resolve_instances.sh
source "$LIB_DIR/resolve_instances.sh"

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
    _addons_path_to_array _paths "${addons_path}"
    for p in "${_paths[@]}"; do
        [[ -n "$p" ]] || continue
        if [[ -x "$p/odoo-bin" ]]; then echo "$p/odoo-bin"; return 0; fi
        if [[ -x "$(dirname "$p")/odoo-bin" ]]; then echo "$(dirname "$p")/odoo-bin"; return 0; fi
    done
    return 1
}

# ---------------------------------------------------------------------------
# _addons_csv_from - the addons-path value handed to odoo-bin's --addons-path
#   flag: SSOT-normalized (tolerates a stray legacy colon in $1, always
#   returns comma-joined, no injected whitespace). Every real producer
#   (allocator.py's ALLOC_ADDONS_PATH) already emits pure comma, so this is a
#   no-op passthrough in the common case - it exists only so a hand-typed or
#   legacy caller degrades gracefully instead of reaching odoo-bin malformed.
# ---------------------------------------------------------------------------
_addons_csv_from() {
    local -a _acf_arr
    _addons_path_to_array _acf_arr "$1"
    (IFS="$ADDONS_PATH_SEP"; echo "${_acf_arr[*]}")
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
# _series_major - the integer major of a series string ("17.0" -> 17), or
#   EMPTY when --version was omitted or is unparsable. The ONE series gate in
#   this script: _resolve_log_ns and _test_ran_re both read it, so a series
#   boundary is never re-derived a second way.
# ---------------------------------------------------------------------------
_series_major() {
    local major="${1%%.*}"
    [[ "$major" =~ ^[0-9]+$ ]] || return 0
    # 10# forces base 10. Bash reads a 0-prefixed integer literal as OCTAL, so a
    # zero-padded "08"/"09" is invalid octal: every `(( major < N ))` era gate
    # against it errors out and the failed comparison reads FALSE, landing a
    # v8/v9 target on the modern branch (wrong log namespace, wrong era marker).
    printf '%s\n' "$(( 10#$major ))"
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
    local major
    major="$(_series_major "${1:-}")"
    if [[ -n "$major" ]] && (( major < 10 )); then
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
#   completion line kept on the log by --log-handler=<ns>.modules.loading:INFO,
#   a floor that survives any caller-supplied level. A future marker added to
#   the install/update contract is added HERE ONLY - both call sites pick it up
#   automatically.
# ---------------------------------------------------------------------------
_INSTALL_FAIL_RE='CRITICAL|Traceback \(most recent call last\)|invalid module names, ignored|Some modules are not loaded|Unmet dependenc|cannot be installed'
_INSTALL_SUCCESS_MARKER='Modules loaded.'

# ---------------------------------------------------------------------------
# Log-level SSOT - the ONE default every verb passes to odoo-bin. `info` is
# Odoo's own default and a valid --log-level token on every series v8-v19,
# and it is the LOWEST level at which a PASSING test run still emits its own
# summary line: below it a green run is byte-identical to "no tests ran".
# Every setter below reads THIS constant - never a second literal. A caller
# overrides per run with their own --log-level in --extra, which is placed
# AFTER this default (Odoo's parser takes the last occurrence).
# ---------------------------------------------------------------------------
_DEFAULT_LOG_LEVEL='info'

# ---------------------------------------------------------------------------
# Test-outcome marker SSOT (read from Odoo source, all 12 series v8.0-v19.0).
#   _TEST_FAIL_RE - version-GENERAL. `FAIL:`/`ERROR:` message bodies exist on
#     every series; the per-module ERROR line's prefix is byte-identical
#     across the eras ("Module <m>: <F> failures, <E> errors" v8-v13, the same
#     plus " of <T> tests" v14+); loading.py's blanket ERROR line is on all 12.
#     Odoo emits the per-module line ONLY when the run was not successful, so
#     it can never carry "0 failures, 0 errors" - no non-zero guard needed.
#   _TEST_RAN_*_RE - the POSITIVE "tests actually RAN" marker, and the ONLY
#     era-SPLIT one: v8-v13 emit `Ran <N> test(s) in <X>s` (stdlib runner
#     trailer, INFO), v14+ emit `<F> failed, <E> error(s) of <T> tests`
#     (service/server.py's per-database summary). Both REQUIRE a non-zero
#     count, so a tag filter that matched nothing can never certify a pass.
# ---------------------------------------------------------------------------
_TEST_FAIL_RE='(^|[[:space:]])(FAIL|ERROR):|Module [A-Za-z0-9_.]+: [0-9]+ failures?, [0-9]+ errors?|At least one test failed when loading the modules|[1-9][0-9]* (failed|error)'
_TEST_RAN_LEGACY_RE='Ran [1-9][0-9]* tests? in '
_TEST_RAN_MODERN_RE='[0-9]+ failed, [0-9]+ error\(s\) of [1-9][0-9]* tests'

# ---------------------------------------------------------------------------
# _test_ran_re - the era-correct POSITIVE "the suite ran" marker for a series.
#   v8-v13 -> the runner trailer; v14+ -> service/server.py's summary line.
#   Series unknown (--version omitted) -> accept EITHER, so a missing series
#   degrades to permissive, never to a false `inconclusive`.
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# _modules_loaded_count <logf> - how many modules the run actually loaded, from
#   `loading <N> modules...` (INFO, byte-identical v8-v19). Prints NOTHING when
#   the log carries no such line: "not measurable" is a different fact from 0.
# ---------------------------------------------------------------------------
_modules_loaded_count() {
    local logf="$1" line
    line="$(grep -aoE 'loading [0-9]+ modules\.\.\.' "$logf" 2>/dev/null | tail -n 1 || true)"
    [[ -n "$line" ]] || return 0
    printf '%s\n' "$line" | grep -oE '[0-9]+' | head -n 1
}

# ---------------------------------------------------------------------------
# _tests_run_count <logf> [version] - how many tests actually RAN, summed over
#   every era-correct ran-marker in the log (SSOT: _test_ran_re). Both eras put
#   the total in the marker's LAST integer ("Ran <N> tests in", "<F> failed, <E>
#   error(s) of <T> tests"). Prints NOTHING when no marker is present: a run
#   whose tag filter matched nothing is UNMEASURED, not zero.
# ---------------------------------------------------------------------------
_tests_run_count() {
    local logf="$1" version="${2:-}"
    local total=0 hit=0 line n
    while IFS= read -r line; do
        [[ -n "$line" ]] || continue
        n="$(printf '%s\n' "$line" | grep -oE '[0-9]+' | tail -n 1)"
        [[ -n "$n" ]] || continue
        total=$(( total + n ))
        hit=1
    done < <(grep -aoE "$(_test_ran_re "$version")" "$logf" 2>/dev/null || true)
    [[ "$hit" -eq 1 ]] && printf '%s\n' "$total"
    return 0
}

_test_ran_re() {
    local major
    major="$(_series_major "${1:-}")"
    if [[ -z "$major" ]]; then
        printf '%s|%s\n' "$_TEST_RAN_LEGACY_RE" "$_TEST_RAN_MODERN_RE"
    elif (( major < 14 )); then
        printf '%s\n' "$_TEST_RAN_LEGACY_RE"
    else
        printf '%s\n' "$_TEST_RAN_MODERN_RE"
    fi
}

# ---------------------------------------------------------------------------
# _install_confirmed - single-pass positive-install check for a completed
#   (--stop-after-init) install/update job. Returns 0 (confirmed) iff the
#   "Modules loaded." completion marker is present - kept on the log at any
#   caller-chosen level by --log-handler=<ns>.modules.loading:INFO - AND
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
# Log-retention SSOT - how many days a run's log (and its .findings.md
# sibling) survives in the logs dir. A script constant on purpose: there is
# nothing machine-dependent to resolve, so this is NOT a public knob and no
# agent-facing doc mentions it. Raise it here if a longer forensic window is
# wanted.
# ---------------------------------------------------------------------------
_LOG_RETENTION_DAYS=14

# The agent harness's per-call Bash-tool ceiling, in seconds (600000 ms).
# SSOT for the relationship below - a future ceiling change edits this line.
_TOOL_CALL_CEILING_S=600
# wait-log's DEFAULT bound. It MUST stay strictly BELOW _TOOL_CALL_CEILING_S:
# a default EQUAL to the ceiling races the harness, and when the harness wins the
# call returns NO `BUILD_RESULT=` line at all - the caller then has nothing to
# check and reports "still waiting", which is exactly the idle-stall this
# active-wait mechanism exists to prevent. Below the ceiling, one call ALWAYS
# returns a verdict (success | failure | timeout), and a build that legitimately
# needs longer is handled by re-invoking wait-log, not by a longer default.
_WAIT_LOG_DEFAULT_TIMEOUT_S=570

# ---------------------------------------------------------------------------
# _leased_db_names - every db_name the allocator lease registry references
#   (${ODOO_AI_HOME}/runtime/leases.json - scripts/lib/allocator.py's SSOT for
#   which instances exist, live rows AND stale ones). Prints one name per line.
#   Exit 0 + no output when no registry exists yet (nothing was ever leased on
#   this host). Exit 1 means a registry IS there but could not be read - the
#   caller must then prune NOTHING.
#   Live-or-stale on purpose: liveness (owner pid + fingerprint + host) is
#   allocator.py's judgment, and re-deriving it here would only be a second,
#   drifting copy. The superset is strictly safe - it can only DELAY a prune,
#   never unlink a running instance's log - and `allocator.py gc` drops each
#   stale row, after which its logs become sweepable again.
# ---------------------------------------------------------------------------
_leased_db_names() {
    local reg="${ODOO_AI_HOME:-${HOME:-/tmp}/.odoo-ai}/runtime/leases.json"
    [[ -e "$reg" ]] || return 0
    [[ -r "$reg" ]] || return 1
    { grep -oE '"db_name"[[:space:]]*:[[:space:]]*"[^"]*"' "$reg" 2>/dev/null || true; } \
        | sed -E 's/^"db_name"[[:space:]]*:[[:space:]]*"//; s/"$//'
}

# ---------------------------------------------------------------------------
# _prune_stale_logs - delete run artifacts older than _LOG_RETENTION_DAYS from
#   $1, EXCEPT any whose database the lease registry still references.
#
#   50-instance-spinup.sh writes long-lived LISTENING-instance logs
#   (persist: exclusive-running / shared-running) into this SAME shared dir
#   under the same <db>-<UTC-ts>.log convention, and a lease with a
#   verified-alive owner pid is never TTL-reclaimed - so a listening instance
#   that simply goes quiet past the window would have its OPEN log unlinked out
#   from under the server's fd: the server keeps appending to the detached
#   inode while every path-based read reports "no such file".
#
#   Best-effort, never fatal, never touches a live file: a size cap or a
#   truncation is deliberately NOT used, because losing the tail of a log can
#   lose the "Modules loaded." marker _install_confirmed requires and turn a
#   green build into STATUS=error. `-mtime +N` can never match a file written
#   by this run. The .findings.md sibling is swept with its log so the pair
#   never desynchronises. Candidates are enumerated (`-print0`) and removed one
#   by one instead of `find -delete` so the exclusion can be applied by EXACT
#   db-name match; `-maxdepth 1` plus `-type f` (find does not follow symlinks
#   without -L) keeps every removal inside the dir. Flags used are portable
#   across GNU and BSD find.
# ---------------------------------------------------------------------------
_prune_stale_logs() {
    local logs_dir="$1"
    [[ -d "$logs_dir" ]] || return 0
    local leased
    # Fail closed: an unreadable registry means no log can be PROVEN unleased.
    leased="$(_leased_db_names)" || return 0
    local f base db
    while IFS= read -r -d '' f; do
        base="${f##*/}"
        # <db>-<UTC-ts>.log and <db>-<UTC-ts>.findings.md - the timestamp is the
        # last hyphen-delimited field, so the db name is everything before it.
        db="${base%-*}"
        if [[ -n "$leased" ]] && printf '%s\n' "$leased" | grep -Fxq -- "$db"; then
            continue
        fi
        rm -f -- "$f" 2>/dev/null || true
    done < <(find "$logs_dir" -maxdepth 1 -type f \
                  \( -name '*.log' -o -name '*.findings.md' \) \
                  -mtime "+${_LOG_RETENTION_DAYS}" -print0 2>/dev/null || true)
}

# ---------------------------------------------------------------------------
# Run-verb stamp - the FIRST line of every log this script opens.
#
# `wait-log` runs in a DIFFERENT process from the build it waits on - usually a
# different agent turn - so the log is the only thing it can read, and the
# terminal predicate DIFFERS by verb: "Modules loaded." IS completion for an
# install/update build, but on a test run Odoo logs it BEFORE the post-install
# suite starts (loading.py logs it; the post_install position is launched later,
# from the server's preload path). Stamping the log makes it SELF-DESCRIBING, so
# the predicate is resolved from the log itself and no caller can pick the wrong
# one by forgetting a flag.
_RUN_VERB_STAMP='ODOO_AI_RUN_VERB'

# ---------------------------------------------------------------------------
# _log_stamp_field <logf> <VERB|SERIES> - read one field of the run-verb stamp.
#   Empty when the log carries no stamp (a log from an older run): the caller
#   then behaves exactly as it did before the stamp existed.
# ---------------------------------------------------------------------------
_log_stamp_field() {
    local logf="$1" field="$2" line=""
    line="$(grep -aE "^${_RUN_VERB_STAMP}=" "$logf" 2>/dev/null | head -n 1 || true)"
    [[ -n "$line" ]] || return 0
    case "$field" in
        VERB)
            line="${line#"${_RUN_VERB_STAMP}"=}"
            printf '%s\n' "${line%% *}" ;;
        SERIES)
            [[ "$line" == *" SERIES="* ]] || return 0
            line="${line##* SERIES=}"
            printf '%s\n' "${line%% *}" ;;
    esac
}

# ---------------------------------------------------------------------------
# _open_log <db_slug> [verb] [version]
#   set $logf, mkdir, prune stale runs, write the run-verb stamp, emit LOG_PATH=
#   The stamp is written HERE, at the single place that owns the log file, so a
#   future verb cannot forget it. Every caller appends (>>) to $logf afterwards -
#   a truncating redirect would wipe the stamp.
# ---------------------------------------------------------------------------
_open_log() {
    local db_slug="$1" verb="${2:-}" version="${3:-}"
    local logs_dir
    logs_dir="${ODOO_AI_HOME:-${HOME:-/tmp}/.odoo-ai}/logs"
    mkdir -p "$logs_dir"
    _prune_stale_logs "$logs_dir"
    local ts
    ts="$(date -u +%Y%m%dT%H%M%SZ 2>/dev/null || date -u +%Y%m%d%H%M%S)"
    logf="$logs_dir/${db_slug}-${ts}.log"
    printf '%s=%s SERIES=%s\n' "$_RUN_VERB_STAMP" "$verb" "$version" >"$logf"
    echo "LOG_PATH=$logf"
}

# ---------------------------------------------------------------------------
# _parse_test_result - read $logf + $1 (exit code) -> emit TEST_RESULT= plus the
#   TEST_FAILED/TEST_ERROR/TEST_WARNING/TEST_SKIPPED counts and a FINDINGS_PATH
#   file. TEST_RESULT is inconclusive (never a bare passed) whenever
#   TEST_SKIPPED>0 and no failure occurred, and whenever no era-correct
#   "the suite ran" marker is present - `passed` is a POSITIVE finding here,
#   never a fallthrough.
#   Reads $logf and (best-effort) $arg_modules / $arg_version from the caller's
#   scope (bash dynamic scope) to mark in-scope warnings and pick the era gate.
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

    # --- Skip detection -----------------------------------------------------
    # Bug: exit 0 + "0 failed, 0 error(s) of 1 tests" reads as green even when
    # the sole test was SKIPPED (never ran) - e.g. "skipped . : Failed to
    # detect chrome devtools port after 10.0s." A skip is not a failure (it is
    # frequently legitimate: @tagged filters, an optional external dependency
    # missing) but it also is NOT proof the suite ran clean, so it must be
    # counted and surfaced as its own field rather than silently folded into
    # "passed".
    #
    # SKIP_RE catches both version-era log shapes (validated against the
    # issue's real repro), and BOTH alternatives are anchored on a real
    # test-package PATH SEGMENT, never a bare substring match - an earlier
    # draft matched `test` as a substring anywhere, which false-positived on
    # ordinary model/module names that merely CONTAIN "test" (e.g.
    # hr_attestation, website_testimonial, contest) and on an unrelated
    # `\.\.\.[[:space:]]+skipped` business message (e.g. a stock reservation
    # retry log line "... skipped (insufficient qty, will retry)"). Both
    # alternatives below require a literal `.` immediately before the
    # "test(s)" token (so it is a whole dot-delimited segment, not a
    # substring) and a literal `.`/`:` immediately after it (so a longer word
    # like "testimonial" cannot satisfy it either):
    #   1. v14+ modern Odoo test-runner logger name: `(openerp|odoo)\.<pkg
    #      path>.tests?[.:]<...>: skip[ped] <name>` (<ns> = openerp v8-v9 /
    #      odoo v10+, matching _resolve_log_ns).
    #   2. Older Python-stdlib unittest verbose runner line (bypasses the
    #      Odoo logger, so no <ns> prefix): `test_name (<module path
    #      containing a .tests. or .test. segment>) ... skipped`.
    # The exact per-series wording is Odoo framework-internal (not indexed by
    # OSM), so this is deliberately a two-shape, case-insensitive regex rather
    # than a single hardcoded string - but never a bare `grep -i skip`, which
    # would reopen both false-positive classes above.
    local SKIP_RE='(^|[[:space:]])(openerp|odoo)\.[a-z0-9_.]*\.tests?[.:][a-z0-9_.]*:[[:space:]]*skip|(^|[[:space:]])test_[a-z0-9_]+[[:space:]]+\([a-z0-9_.]*\.tests?\.[a-z0-9_.]+\)[[:space:]]+\.\.\.[[:space:]]+skip'
    local n_skip
    n_skip="$(grep -icE "$SKIP_RE" "$logf" 2>/dev/null || true)"
    n_skip="${n_skip:-0}"

    # Skip NAMES for the findings file. Extraction runs over the plain
    # (non-line-numbered) matches - unlike the `grep -icE` count above, the
    # stdlib-shape sed pattern below anchors at line-start (^...), so a `-n`
    # line-number prefix would break it; the modern-shape pattern is
    # unanchored and unaffected either way. Each matched line satisfies at
    # most one of the two shapes, so both sed passes run over the same input
    # and are merged + de-duplicated.
    local skip_lines skip_names=""
    skip_lines="$(grep -aiE "$SKIP_RE" "$logf" 2>/dev/null || true)"
    if [[ -n "$skip_lines" ]]; then
        skip_names="$(
            {
                printf '%s\n' "$skip_lines" \
                    | sed -nE 's/.*:[[:space:]]*skip[a-z]*[[:space:]]+([A-Za-z0-9_.]+).*/\1/p'
                printf '%s\n' "$skip_lines" \
                    | sed -nE 's/^([A-Za-z0-9_]+)[[:space:]]+\(([A-Za-z0-9_.]+)\)[[:space:]]+\.\.\..*/\2.\1/p'
            } | awk '!seen[$0]++'
        )"
    fi

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
        echo "Counts: failed=$n_fail error=$n_error warning=$n_warn skipped=$n_skip"
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
        echo "## Skipped tests (capped at $warn_cap) - NOT a failure, but NOT proof the suite ran clean either"
        echo
        if [[ "$n_skip" -gt 0 ]]; then
            echo '```'
            printf '%s\n' "$skip_names" | head -n "$warn_cap"
            echo '```'
        else
            echo "_No skipped tests detected in the log._"
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
    echo "TEST_SKIPPED=$n_skip"
    echo "FINDINGS_PATH=$findings"
    # SCOPE the run actually covered, as machine output. The alternative is an
    # agent hand-running two greps and hand-writing both figures into free text -
    # the same discretion that produced the original silent cover-up. An EMPTY
    # value means "no marker in the log", never 0: a tag filter that matched
    # nothing leaves the count unmeasured, and reporting that as zero would be a
    # fabricated fact rather than an absent one.
    echo "MODULES_LOADED=$(_modules_loaded_count "$logf")"
    echo "TESTS_RUN=$(_tests_run_count "$logf" "${arg_version:-}")"

    # --- Pass/fail verdict (unchanged decision logic, plus the skip branch) ---
    if [[ "$exit_code" -ne 0 ]]; then
        echo "TEST_RESULT=failed"
        return
    fi
    # FAILURE first - the three-era test-marker set (SSOT: _TEST_FAIL_RE above)
    # UNIONED with the install/silent-skip marker set (SSOT: _INSTALL_FAIL_RE).
    # The v8-v13 per-module wording ("Module <m>: N failures, M errors") is a
    # DIFFERENT string from the v14+ one and was previously unmatched, so a
    # failures-only run on those six series was reported GREEN. An INSTALL
    # failure inside a --test-enable build (misspelled module, unmet dependency)
    # writes no fail-, skip- OR ran-marker at all, so it used to fall through to
    # `inconclusive`; it is a FAILED run - the suite could not run - and the
    # union also stops a module that DID install from certifying the build green
    # while a named module was silently skipped. Same verdict _scan_build_markers
    # already reaches on this same log, so the two can never disagree.
    if grep -aqE "$_TEST_FAIL_RE|$_INSTALL_FAIL_RE" "$logf" 2>/dev/null; then
        echo "TEST_RESULT=failed"
        return
    fi
    # Skip verdict - MUST precede the positive-pass check below: a skip-only
    # run still emits a ran-marker with a non-zero count. Skips are not fatal
    # (never force a non-zero exit; exit_code above already governs
    # failed/error - they are legitimately produced by @tagged filters or a
    # missing optional external dependency) but are never silently certified
    # as a bare `passed`.
    if [[ "$n_skip" -gt 0 ]]; then
        echo "TEST_RESULT=inconclusive"
        return
    fi
    # POSITIVE pass marker, era-resolved. Mirrors _install_confirmed exactly:
    # the ABSENCE of a positive "the suite ran" line is itself the finding,
    # never a fallthrough to success - exit 0 with no ran-marker means the tag
    # filter matched nothing, not that the suite passed. arg_version comes from
    # the caller's scope (bash dynamic scope); when it is absent the era gate
    # degrades to accepting EITHER wording.
    if grep -qE "$(_test_ran_re "${arg_version:-}")" "$logf" 2>/dev/null; then
        echo "TEST_RESULT=passed"
        return
    fi
    echo "TEST_RESULT=inconclusive"
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
#          _install_confirmed rules it - and a Traceback after a progress
#          line is still a failed build)
#     2 -> no terminal marker yet (build still in flight; the last
#          "loading <N> modules..." progress line is echoed as evidence)
#   The failure set is a SUPERSET of _INSTALL_FAIL_RE (adds psycopg2./
#   ParseError/"Failed to load registry"/a bare ERROR line - broader build
#   failures outside _install_confirmed's narrower install-only scope, e.g. a
#   DB-connectivity error or an XML ParseError during a run-tests build).
#   "loading <N> modules..."/"Initiating shutdown"/a bare process exit 0 remain
#   named as progress/heartbeat signals in agents/odoo-instance-ops.md's
#   "Active-wait on long builds" section, but are NOT independently
#   sufficient for BUILD_RESULT=success here - only "Modules loaded." is,
#   matching _install_confirmed exactly. Markers are version-stable v8-v19;
#   the caller's own process exit code stays authoritative - this is the
#   in-log completion signal.
# ---------------------------------------------------------------------------
_scan_build_markers() {
    local logf="$1"
    [[ -f "$logf" ]] || return 2

    # The VERB decides the terminal predicate, read from the log's own run-verb
    # stamp (_open_log) so this works in a process that knows nothing else about
    # the run. An unstamped log (an older run) resolves to the install predicate -
    # exactly the pre-stamp behavior.
    local verb series
    verb="$(_log_stamp_field "$logf" VERB)"
    series="$(_log_stamp_field "$logf" SERIES)"

    # FAILURE first - a failure marker anywhere means the build did not succeed,
    # even if an earlier line looked like progress. _INSTALL_FAIL_RE (SSOT,
    # shared with _install_confirmed) is unioned with broader generic build-
    # failure signals below; a TEST run adds the test-failure marker set (SSOT:
    # _TEST_FAIL_RE, shared with _parse_test_result) so a suite that failed can
    # never be reported as a successful build.
    local fail_re="${_INSTALL_FAIL_RE}|[[:space:]]ERROR[[:space:]]|Failed to load registry|psycopg2\.|ParseError"
    [[ "$verb" == "test" ]] && fail_re="${fail_re}|${_TEST_FAIL_RE}"
    local fail_line
    fail_line="$(grep -aE "$fail_re" "$logf" 2>/dev/null | head -n 1 || true)"
    if [[ -n "$fail_line" ]]; then
        echo "BUILD_MARKER=$fail_line"
        return 1
    fi

    if [[ "$verb" == "test" ]]; then
        # A test run's OWN verdict line, appended to the log by cmd_test when the
        # run finished, is the strongest terminal signal there is - and echoing it
        # is what puts TEST_RESULT within reach of a polling caller at all.
        local verdict
        verdict="$(grep -aE '^TEST_RESULT=' "$logf" 2>/dev/null | head -n 1 || true)"
        if [[ -n "$verdict" ]]; then
            echo "BUILD_MARKER=$verdict"
            printf '%s\n' "$verdict"
            return 0
        fi
        # Otherwise the era-correct POSITIVE "the suite ran" marker (SSOT:
        # _test_ran_re - v8-v13 runner trailer, v14+ per-database summary).
        # "Modules loaded." is NOT terminal here: Odoo logs it BEFORE the
        # post-install suite starts, so certifying there stops the wait while the
        # tests have not begun.
        local ran_line
        ran_line="$(grep -aE "$(_test_ran_re "$series")" "$logf" 2>/dev/null | head -n 1 || true)"
        if [[ -n "$ran_line" ]]; then
            echo "BUILD_MARKER=$ran_line"
            return 0
        fi
    else
        # SUCCESS - the SAME completion marker _install_confirmed requires (SSOT:
        # _INSTALL_SUCCESS_MARKER). Never treat a progress line or "Initiating
        # shutdown" alone as success - see docstring above.
        local ok_line
        ok_line="$(grep -aF "$_INSTALL_SUCCESS_MARKER" "$logf" 2>/dev/null | head -n 1 || true)"
        if [[ -n "$ok_line" ]]; then
            echo "BUILD_MARKER=$ok_line"
            return 0
        fi
    fi

    # PROGRESS (never terminal, never success) - `loading <N> modules...` is
    # INFO and byte-identical v8-v19, so an in-flight poll reports real forward
    # progress instead of an empty marker on every series. For a test run
    # "Modules loaded." is the LATER of the two progress signals: the modules are
    # in, the suite has not finished.
    local prog_line=""
    if [[ "$verb" == "test" ]]; then
        prog_line="$(grep -aF "$_INSTALL_SUCCESS_MARKER" "$logf" 2>/dev/null | head -n 1 || true)"
    fi
    if [[ -z "$prog_line" ]]; then
        prog_line="$(grep -aE 'loading [0-9]+ modules\.\.\.' "$logf" 2>/dev/null | tail -n 1 || true)"
    fi
    [[ -n "$prog_line" ]] && echo "BUILD_MARKER=$prog_line"
    return 2
}

# ---------------------------------------------------------------------------
# cmd_wait_log - bounded poll of a build log for a terminal marker.
# ---------------------------------------------------------------------------
cmd_wait_log() {
    local logf="" timeout="$_WAIT_LOG_DEFAULT_TIMEOUT_S" interval=5
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
        *) echo "${marker:-BUILD_MARKER=}"; echo "BUILD_RESULT=timeout"
           echo "x wait-log timed out after ${timeout}s with no terminal marker; see $logf" >&2 ;;
    esac
    return "$rc"
}

# ---------------------------------------------------------------------------
# _parse_common_args - parse --db/--python/--addons/--modules/--extra plus the
#   optional --test-tags/--mode/--log-mode/--version flags.
# Sets: arg_db, arg_python, arg_addons, arg_modules, arg_extra, arg_test_tags,
#       arg_mode (default 'fresh'), arg_log_mode (default ''), arg_version
#       (default ''; on init/update it resolves the --log-handler namespace via
#       _resolve_log_ns - empty defaults to the v10+ 'odoo' namespace; on test
#       it picks the era-correct ran-marker via _test_ran_re - empty accepts
#       either era's wording).
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
                    info|debug|sql) arg_log_mode="$2" ;;
                    # `warn` is REFUSED, not merely discouraged: it suppresses the
                    # INFO summary that is the only positive proof a suite ran, so
                    # every GREEN run under it parses as TEST_RESULT=inconclusive.
                    warn) echo "$(basename "$0"): --log-mode warn is refused: it suppresses the pass summary, so every green run parses as TEST_RESULT=inconclusive. Use one of info|debug|sql." >&2; exit 2 ;;
                    *) echo "$(basename "$0"): --log-mode must be one of info|debug|sql (got '$2')" >&2; exit 2 ;;
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
    _open_log "$arg_db" init "${arg_version:-}"

    # arg_addons is SSOT-normalized (tolerates a stray legacy colon; every
    # real producer already emits pure comma) - see _addons_csv_from.
    local addons_csv
    addons_csv="$(_addons_csv_from "$arg_addons")"

    local DB_CONN_ARGS
    _build_db_conn_args

    # Deterministic completion contract (docs/reference/INSTANCE-LIFECYCLE.md
    # item 14): --log-handler=<ns>.modules.loading:INFO is a FLOOR, not a
    # workaround - it keeps the "Modules loaded." completion line on the log at
    # ANY level a caller may pass in --extra, including a quieter one, so the
    # contract never depends on the caller's verbosity choice. It also caps that
    # ONE logger at INFO when --extra asks for debug; a caller wanting
    # module-loading DEBUG passes --log-handler=<ns>.modules.loading:DEBUG in
    # --extra. <ns> is version-resolved via _resolve_log_ns (openerp v8-v9,
    # odoo v10+). Both flags are placed BEFORE ${arg_extra} so a caller-supplied
    # --log-level/--log-handler in --extra still overrides them (Odoo's arg
    # parser takes the last occurrence) - mirrors the `test` verb.
    local log_ns
    log_ns="$(_resolve_log_ns "${arg_version:-}")"

    # Resource-limit wrapper (Problem 1 hardening - snippets/odoo-bin-resource-
    # limits.md, SSOT values in resource_limits.sh): `ulimit -Sv` is the
    # version-general spine (Odoo applies NO memory cap on v8-v11's build
    # path); `--limit-memory-hard=<bytes>` raises Odoo's own v12+ default
    # clamp. resource_limit_hard_bytes() already resolves to 0 under the
    # uncapped escape hatch, so the flag is always emitted; only the `ulimit`
    # call is skipped in that case.
    local _lim_bytes _lim_kib
    _lim_bytes="$(resource_limit_hard_bytes)"
    _lim_kib="$(resource_limit_hard_kib)"

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
    # Scoped subshell: `ulimit -Sv` applies only to this one odoo-bin
    # invocation and never leaks past it. --limit-memory-hard sits BEFORE
    # ${arg_extra} so a caller-supplied override in --extra still wins
    # (Odoo's arg parser takes the last occurrence).
    (
        resource_limit_is_uncapped || ulimit -Sv "$_lim_kib" 2>/dev/null || true
        # Positive proof of the resolved tree (issue class: Odoo's own module-
        # loading log records only RELATIVE module paths, so a verifier can
        # never grep an absolute addons-path line to confirm which checkout
        # loaded - the ABSENCE of a wrong path is the only signal otherwise).
        # This line makes the RESOLVED addons-path greppable in the log itself.
        echo "allocator: ADDONS_PATH_USED=$addons_csv"
        "$arg_python" "$odoo_bin" \
            -d "$arg_db" \
            -i "$arg_modules" \
            --addons-path "$addons_csv" \
            "${DB_CONN_ARGS[@]}" \
            --stop-after-init \
            --log-level="$_DEFAULT_LOG_LEVEL" \
            --log-handler="${log_ns}.modules.loading:INFO" \
            --limit-memory-hard="$_lim_bytes" \
            ${arg_extra}
    ) >>"$logf" 2>&1 || rc=$?

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
    _open_log "$arg_db" update "${arg_version:-}"

    # arg_addons is SSOT-normalized (tolerates a stray legacy colon; every
    # real producer already emits pure comma) - see _addons_csv_from.
    local addons_csv
    addons_csv="$(_addons_csv_from "$arg_addons")"

    local DB_CONN_ARGS
    _build_db_conn_args

    # Deterministic completion contract - identical to cmd_init (see its
    # comments above and docs/reference/INSTANCE-LIFECYCLE.md item 14):
    # --log-handler=<ns>.modules.loading:INFO is the FLOOR that keeps "Modules
    # loaded." on the log at any caller-chosen level; both flags precede
    # ${arg_extra} so a caller override still wins.
    local log_ns
    log_ns="$(_resolve_log_ns "${arg_version:-}")"

    # Resource-limit wrapper - see the identical comment block in cmd_init
    # above and snippets/odoo-bin-resource-limits.md for the full policy.
    local _lim_bytes _lim_kib
    _lim_bytes="$(resource_limit_hard_bytes)"
    _lim_kib="$(resource_limit_hard_kib)"

    local rc=0
    # shellcheck disable=SC2086
    # Completion is PROCESS EXIT (this call blocks until odoo-bin exits) - never
    # a log-tail wait; the log is consulted ONLY afterward to CONFIRM the exit
    # actually updated something (see _install_confirmed).
    # Scoped subshell: `ulimit -Sv` applies only to this one odoo-bin
    # invocation and never leaks past it. --limit-memory-hard sits BEFORE
    # ${arg_extra} so a caller-supplied override in --extra still wins.
    (
        resource_limit_is_uncapped || ulimit -Sv "$_lim_kib" 2>/dev/null || true
        # Positive proof of the resolved tree - see the identical comment in
        # cmd_init above.
        echo "allocator: ADDONS_PATH_USED=$addons_csv"
        "$arg_python" "$odoo_bin" \
            -d "$arg_db" \
            -u "$arg_modules" \
            --addons-path "$addons_csv" \
            "${DB_CONN_ARGS[@]}" \
            --stop-after-init \
            --log-level="$_DEFAULT_LOG_LEVEL" \
            --log-handler="${log_ns}.modules.loading:INFO" \
            --limit-memory-hard="$_lim_bytes" \
            ${arg_extra}
    ) >>"$logf" 2>&1 || rc=$?

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
    # arg_version is declared local HERE too (not only in init/update): without
    # it _parse_common_args' assignment would leak a GLOBAL out of every test
    # run, and _parse_test_result reads it by dynamic scope for the era gate.
    local arg_db arg_python arg_addons arg_modules arg_extra arg_test_tags="" arg_mode arg_log_mode arg_version
    local arg_db_host arg_db_user arg_db_port
    _parse_common_args "$@"

    local odoo_bin
    odoo_bin="$(_find_odoo_bin "$arg_addons")" || {
        echo "x Could not locate odoo-bin. Set ODOO_BIN=/path/to/odoo-bin and retry." >&2
        exit 1
    }
    _preflight_venv "$arg_python" "$odoo_bin"

    local logf
    _open_log "$arg_db" test "${arg_version:-}"

    local test_tags_args=()
    if [[ -n "${arg_test_tags:-}" ]]; then
        test_tags_args=("--test-tags" "$arg_test_tags")
    fi

    # arg_addons is SSOT-normalized (tolerates a stray legacy colon; every
    # real producer already emits pure comma) - see _addons_csv_from.
    local addons_csv
    addons_csv="$(_addons_csv_from "$arg_addons")"

    # mode: fresh (default) -> -i (new DB / modules not yet installed; init+test in
    # one pass); reuse -> -u (DB already has the modules; re-running tests, where -i
    # would be a no-op). Confirm -i/-u semantics via OSM cli_help.
    local mode_flag="-i"
    [[ "${arg_mode:-fresh}" == "reuse" ]] && mode_flag="-u"

    # Resolve the log verbosity flag. Omitted -> $_DEFAULT_LOG_LEVEL (SSOT
    # above) - the SAME default init/update use, so there is exactly one default
    # in this script. `info` needs no arm of its own: it falls through to the
    # default and would emit the identical flag. Placed before ${arg_extra} so a
    # --log-level/--log-handler in --extra still overrides.
    local log_flag_args=()
    case "${arg_log_mode:-}" in
        debug) log_flag_args=("--log-level=debug") ;;
        sql)   log_flag_args=("--log-handler=odoo.sql_db:DEBUG") ;;
        *)     log_flag_args=("--log-level=$_DEFAULT_LOG_LEVEL") ;;
    esac

    local DB_CONN_ARGS
    _build_db_conn_args

    # Resource-limit wrapper - see the identical comment block in cmd_init
    # above and snippets/odoo-bin-resource-limits.md for the full policy.
    local _lim_bytes _lim_kib
    _lim_bytes="$(resource_limit_hard_bytes)"
    _lim_kib="$(resource_limit_hard_kib)"

    local rc=0
    # shellcheck disable=SC2086
    # Scoped subshell: `ulimit -Sv` applies only to this one odoo-bin
    # invocation and never leaks past it. --limit-memory-hard sits BEFORE
    # ${arg_extra} so a caller-supplied override in --extra still wins.
    (
        resource_limit_is_uncapped || ulimit -Sv "$_lim_kib" 2>/dev/null || true
        # Positive proof of the resolved tree - see the identical comment in
        # cmd_init above.
        echo "allocator: ADDONS_PATH_USED=$addons_csv"
        "$arg_python" "$odoo_bin" \
            -d "$arg_db" \
            "$mode_flag" "$arg_modules" \
            --addons-path "$addons_csv" \
            "${DB_CONN_ARGS[@]}" \
            --test-enable \
            "${test_tags_args[@]}" \
            --stop-after-init \
            "${log_flag_args[@]}" \
            --limit-memory-hard="$_lim_bytes" \
            ${arg_extra}
    ) >>"$logf" 2>&1 || rc=$?

    # The summary goes to stdout AND into the log. `wait-log` reads nothing but
    # the log, so a verdict that only ever reaches stdout is unreachable by
    # construction - a polling caller could never be shown the TEST_RESULT it is
    # waiting for. Captured first, then written to both, so the appended lines
    # cannot be re-read by the greps that produced them.
    local _test_summary
    _test_summary="$(_parse_test_result "$rc")"
    printf '%s\n' "$_test_summary"
    printf '%s\n' "$_test_summary" >>"$logf"

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
    local arg_odoo_root=""

    # Parse drop-specific args (subset of common + optional db-host/db-user/db-port
    # + odoo-root + ownership guard --run-id/--force).
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
            --odoo-root)
                [[ $# -ge 2 ]] || { echo "$(basename "$0"): --odoo-root requires a value" >&2; exit 2; }
                arg_odoo_root="$2"; shift 2 ;;
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
    # --odoo-root makes `import odoo` resolve for a SOURCE checkout (a venv alone
    # does not - odoo-bin only works because it puts the repo root on sys.path).
    # Forward the instance's declared odoo_root and exit 10 stops being the
    # normal outcome of every through-Odoo drop on a source instance.
    [[ -n "$arg_odoo_root" ]] && drop_args+=("--odoo-root" "$arg_odoo_root")

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
