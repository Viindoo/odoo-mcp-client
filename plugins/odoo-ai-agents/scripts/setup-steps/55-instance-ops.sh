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
#                  --unaccent --stop-after-init --log-level=info
#                  --log-handler=<ns>.modules.loading:INFO <extra>
#             Persistent log + LOG_PATH= + STATUS= lines.
#
#             Deterministic completion contract (never a log-tail wait - see
#             docs/reference/INSTANCE-LIFECYCLE-BUILD-CONTRACT.md item 14): the process ALWAYS
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
#             TEST_FAILED/TEST_ERROR/TEST_WARNING/TEST_SKIPPED counts, the
#             JS_RUNS/JS_SCOPE/JS_FAILED_REPORTED/JS_FAILED_TESTS counts, and
#             FINDINGS_PATH (a file naming the failing tests it could resolve -
#             Python markers with traceback heads, JS failures per run - plus the
#             warning lines and any skipped-test names). A --test-enable build runs
#             TWO test frameworks that publish two unrelated vocabularies, so the
#             Python figures are never the run's whole failure count and the JS
#             figures are never the Python one: read both. The counts and the
#             findings file are resolved to AGREE with the verdict: a run whose only
#             failure signal is an AGGREGATE line (the per-module "Module <m>: <F>
#             failures, <E> errors[ of <T> tests]" wording, or v14+'s per-database
#             "<F> failed, <E> error(s) of <T> tests") reports THAT line's
#             figures, and the findings file names the line rather than answering
#             "no failing tests" for a failed build. TEST_FAILED/TEST_ERROR are
#             EMPTY when the log published no figure at all (e.g. the numberless
#             "At least one test failed when loading the modules.") - unmeasured,
#             never 0, the same rule the JS and scope fields below follow.
#             TEST_RESULT=failed also covers an
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
# port honored everywhere). All three run TWO preflights BEFORE any real run and
# BEFORE any log is opened, so a refusal costs no log file and no odoo-bin:
#   1. `<python> <odoo-bin> --version` - fail loud (no working venv; run 45-venv.sh).
#   2. `odoo_db.py preflight` - PROVE Odoo can authenticate to the cluster. Odoo
#      opens its maintenance-database connection for every `-d <name>` run before
#      any module loads, so a refused connection kills update and test exactly as
#      it kills a create. Exits 8 (authentication refused) / 9 (cluster did not
#      answer) with odoo_db.py's own refusal text forwarded verbatim; an
#      UNDETERMINABLE state never blocks.
#
# RESOURCE LIMITS (init/update/test only - Problem 1 hardening): the odoo-bin
# launch runs in a scoped subshell `( ulimit -Sv <kib> ...; <odoo-bin cmd> ...
# --limit-memory-hard=<bytes> ... ${arg_extra} )` - both driven by
# scripts/lib/resource_limits.sh, overridable via ODOO_AI_LIMIT_MEMORY_HARD.
# Full policy (why both mechanisms, the v12.0 enforcement boundary, the
# uncapped escape hatch): snippets/odoo-bin-resource-limits.md.
#   wait-log --log <logf> [--timeout <secs>] [--interval <secs>]
#             Blocks in the FOREGROUND until a terminal marker appears or the
#             bound elapses, then prints
#             BUILD_RESULT=success|failure|inconclusive|timeout.
#             The DEFAULT bound is deliberately below the harness's per-call
#             ceiling (see _WAIT_LOG_DEFAULT_TIMEOUT_S) so ONE call always
#             returns a verdict; for a longer build, re-invoke it.
#             Deterministic build-completion detector for a build launched in the
#             BACKGROUND (Bash run_in_background). Polls <logf> for a TERMINAL marker
#             so the caller (odoo-instance-ops agent) never idle-stalls on a long
#             -i/-u/--test-enable build that would exceed the foreground tool timeout.
#             Emits BUILD_RESULT plus BUILD_MARKER=<line>,
#             BUILD_PROGRESS=<reading> and LOG_PATH=<logf>. Exit 0 (success),
#             1 (failure), 2 (timeout), 3 (inconclusive). Only exit 2 means
#             "keep waiting"; 0, 1 and 3 are all FINISHED, and only 0 is a pass.
#             The build's
#             own exit code stays authoritative; this is a completion + diagnostics
#             signal, NOT the running-server readiness probe (that is 50-instance-spinup.sh's
#             HTTP-200 probe). Markers are version-stable v8-v19.
#             BUILD_PROGRESS is the ADVANCING field, emitted on EVERY path so a
#             caller can diff two consecutive polls. It is ONE COMPOSITE reading,
#             `markers:<n>|bytes:<m>`, with BOTH components always present:
#             `markers` counts the run's own progress lines (SSOT:
#             _BUILD_PROGRESS_RE) and `bytes` is the log's length. Compare the
#             WHOLE string - either half alone freezes on a healthy run (markers
#             through a browser suite that is one long test; bytes never, unless
#             the process wrote nothing). EMPTY means there is no log to measure.
#             It NEVER feeds BUILD_RESULT: progress is not a verdict in either
#             direction, and a build whose log carries nothing but progress lines
#             stays BUILD_RESULT=timeout. Two polls with an IDENTICAL non-empty
#             reading mean the process appended zero bytes in between - the
#             strongest in-log stall evidence available, still not proof of death;
#             BUILD_MARKER quotes the newest progress line so the reading has a
#             human-readable form, but the composite is what a stall rule
#             compares.
#             The terminal predicate is resolved from the log's OWN run-verb stamp
#             (_RUN_VERB_STAMP, written by _open_log). An UNSTAMPED log resolves
#             to the `test` predicate - the NARROWER one in both directions, so an
#             unknown verb can never be certified green by a marker that is only
#             progress for it, nor failed by one that is only per-test evidence:
#               init/update - "Modules loaded." plus _INSTALL_FAIL_RE, the SAME two
#                 SSOT constants _install_confirmed applies and nothing besides, so
#                 this background verdict can NEVER disagree with the script's own
#                 STATUS=ok|error line; a log showing both "Modules loaded." and a
#                 silent-skip marker (e.g. "invalid module names, ignored") reports
#                 BUILD_RESULT=failure, never success.
#               test - the run's own TEST_RESULT= line (appended to the log by the
#                 `test` verb, echoed back here, and the ONLY line on a test log
#                 computed AFTER the run exited) decides it, value by value:
#                 passed -> success, failed -> failure, inconclusive ->
#                 inconclusive, anything unrecognized -> failure. Each value has
#                 its own arm and NONE falls through to success: the run emits
#                 `inconclusive` exactly when it refuses to claim a pass without
#                 positive proof the suite ran, so relaying that as a successful
#                 build would tell a caller the tests passed when zero tests ran.
#                 Before that line lands, ONLY a
#                 HARD ABORT (_BUILD_ABORT_RE - the run died and will never
#                 publish a verdict) is a failure, and the era-correct "the suite
#                 ran" marker certifies success ONLY while neither a failure
#                 marker nor a SKIP marker contradicts it. A per-test FAIL:/ERROR:, its traceback, and the
#                 per-MODULE failure aggregate are all MID-RUN and report
#                 BUILD_RESULT=timeout: the suite keeps running, so preempting the
#                 run's own verdict there both stops the wait early and hands the
#                 caller a verdict the run never published. "Modules loaded." is
#                 only PROGRESS for a test run: Odoo logs it before the
#                 post-install suite starts, so certifying there would stop the
#                 wait while the tests have not begun. BUILD_RESULT answers "has it
#                 finished"; TEST_RESULT (echoed when the log carries it) is the
#                 pass/fail verdict.
#             NEVER key a marker scan on the log-LEVEL column: Odoo logs at ERROR
#             for reasons unrelated to the build, so a delimited ` ERROR ` match
#             fires on lines that carry no verdict (measured: 30 ERROR-level lines
#             / 1 test-failure marker on one real run). Key on MESSAGE TEXT.
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
#               (parseable; `test` verb only; from the log). TEST_FAILED/TEST_ERROR
#               count PYTHON unittest cases only - the browser suite has its own
#               vocabulary and its own fields below; neither set is a subset of the
#               other, so neither figure may be read as the run's whole failure
#               count. They are EMPTY when the log published no figure at all -
#               unmeasured, never 0, so they can never read `0` beside a `failed`
#               verdict)
# JS counts:    JS_RUNS=<n> JS_SCOPE=scoped|unscoped
#               JS_FAILED_REPORTED=<n> JS_FAILED_TESTS=<n>
#               (parseable; `test` verb only; the Hoot/QUnit half). A RUN is one
#               browser-suite logger scope, not the file - one log holds several.
#               JS_FAILED_REPORTED sums each run's OWN published figure (QUnit
#               publishes failed ASSERTIONS, Hoot failed TESTS - mixed units, as
#               reported); JS_FAILED_TESTS counts distinct failing test NAMES.
#               Neither derives from the other. JS_SCOPE=unscoped means the log
#               published only an aggregate with no logger prefix, so
#               JS_FAILED_TESTS is unavailable. All four EMPTY together when the
#               log carries no JS marker - unmeasured, never 0)
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
#   ODOO_AI_HOME       machine-global dir  (default $HOME/.odoo-ai)
#   ODOO_BIN           path to odoo-bin (override; auto-detected otherwise)
#   ODOO_PG_PASSWORD   the escape hatch for a cluster that cannot be reconfigured.
#                      Exported to libpq as PGPASSWORD for the launch only, never
#                      written to a file and never placed on argv. A local
#                      developer cluster needs no password at all - run
#                      /odoo-ai-agents:odoo-setup instead.

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
# The bounded-probe helper (pg_bounded_run + PG_MODE_PROBE_TIMEOUT). Sourced for
# ONE reason: _preflight_db_auth opens a Postgres connection BEFORE any log
# exists, and psycopg2 opens it with no libpq connect timeout - so an unbounded
# call against a host whose SYN is dropped (firewall DROP, a paused container, a
# VPN-gated remote) hangs forever with no LOG_PATH= ever emitted, leaving the
# dispatching agent's `wait-log --timeout` nothing to bind to. Every sibling
# bounds this same call; this script was the only one that did not.
# shellcheck source=../lib/pg_mode.sh
source "$LIB_DIR/pg_mode.sh"
# Tier-1 run-artifact reclamation SSOT - odoo_ai_state_root (the ONE spelling of
# the state root, previously re-derived in this file twice) plus the single
# lease-guarded sweeper (prune_stale_run_artifacts / _prune_stale_logs) and its
# retention bound, all of which used to live in this file where
# 50-instance-spinup.sh could not reach them.
# shellcheck source=../lib/state_reclaim.sh
source "$LIB_DIR/state_reclaim.sh"

# Toolchain env for Odoo's own lint test families (eslint / pylint / flake8 /
# po). Sourced here but APPLIED only inside each odoo-bin launch subshell below,
# so it never leaks past one invocation. Only this file sources it:
# 50-instance-spinup.sh never passes --test-enable (measured: 0 occurrences), so
# no lint test ever runs on its path and wiring it there would be a mechanism
# nothing reaches.
# shellcheck source=../lib/lint_toolchain.sh
source "$LIB_DIR/lint_toolchain.sh"

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
# _preflight_db_auth - PROVE Odoo can authenticate BEFORE anything is launched.
#   Odoo's CLI opens a connection to the maintenance database for EVERY `-d
#   <name>` run, before any registry and before any module loads. A cluster that
#   refuses that connection therefore kills init, update and test alike - not
#   only a create - and it does so mid-build, with a raw traceback and a log that
#   documents nothing. So this runs BEFORE _open_log: on a refusal no log is
#   opened and no odoo-bin is launched.
#   The verdict and its remedy text are OWNED by odoo_db.py preflight. This
#   function forwards the child's stderr verbatim and exits with the child's own
#   code (8 denied, 9 unreachable, 1 undeterminable) - it never re-words a
#   diagnosis, because a second copy of a verdict is how two layers came to
#   contradict each other.
#   Uses the flags this script was GIVEN: it deliberately reads no catalog.
#   BOUNDED (pg_bounded_run): it runs BEFORE _open_log, so an unbounded hang here
#   emits no LOG_PATH= at all and the caller's own `wait-log --timeout` has nothing
#   to bind to - one silent forever-stall instead of a logged failure. psycopg2
#   opens the connection with no libpq connect timeout, so a host that silently
#   drops the SYN never replies; the bound is the only thing that ends the wait.
# ---------------------------------------------------------------------------
_preflight_db_auth() {
    local py="$1" host="${2:-}" user="${3:-}" port="${4:-}" root="${5:-}"
    [[ -f "$ODOO_DB_PY" ]] || return 0
    local -a args=("$ODOO_DB_PY" preflight)
    [[ -n "$host" ]] && args+=(--db-host "$host")
    [[ -n "$user" ]] && args+=(--db-user "$user")
    [[ -n "$port" ]] && args+=(--db-port "$port")
    [[ -n "$root" ]] && args+=(--odoo-root "$root")
    local rc=0
    pg_bounded_run "$PG_MODE_PROBE_TIMEOUT" "$py" "${args[@]}" >/dev/null || rc=$?
    case "$rc" in
        0) return 0 ;;
        # UNDETERMINABLE never blocks a build: this script is handed its
        # connection flags rather than a declared catalog, so a venv that cannot
        # import odoo (10), a question that could not be asked (1), a bound that
        # elapsed (124) or a bound that could not be applied (125) all say nothing
        # about the cluster. Odoo itself then reports the real outcome - and it
        # does so ON A LOG, which is strictly better than stalling before one
        # exists. Exactly the rule 50-instance-spinup.sh applies to 124/125.
        1|10|124|125) return 0 ;;
    esac
    echo "STATUS=error"
    exit "$rc"
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
# Completion-marker SSOT - ONE definition per fact, read by EVERY verdict path
#   in this script: _install_confirmed (foreground init/update verdict),
#   _parse_test_result (foreground test verdict) and _scan_build_markers
#   (background wait-log verdict). Two paths holding their own copy of "what
#   counts as failure" is what let them answer opposite things about the same
#   log, so a new marker is added HERE ONLY and every call site picks it up.
#
#   NEVER key any of these on the log-LEVEL column. Odoo logs at ERROR for
#   reasons that have nothing to do with the build (a scheduled job raising, a
#   mail send, a deprecated call), so a delimited ` ERROR ` match fires on
#   lines that carry no verdict at all. MEASURED on two real run logs: an 18.0
#   run held 30 ERROR-level lines of which 1 was a test-failure marker, and a
#   19.0 run held 100 of which 98 were - the level column predicts nothing.
#   Every scan below keys on MESSAGE TEXT, the same rule the ` INFO ` /
#   `RUNBOT` level drift already forces.
#
#   _BUILD_ABORT_RE - the run DIED or was never able to start: after any of
#     these it will never publish a verdict of its own, so waiting for one is a
#     guaranteed stall and they are TERMINAL for every verb, tests included.
#     odoo-bin's preload_registries wraps ANY load-time exception in a CRITICAL
#     line, so a broken XML data file or a refused Postgres connection during a
#     --test-enable build lands here through CRITICAL.
#   _PER_TEST_TRACEBACK_RE - a failure signal ONLY for a build that runs no
#     tests, and it is in _INSTALL_FAIL_RE for exactly that reason. Under -i/-u
#     nothing but the build itself can raise, so a traceback there IS the
#     failure. On a --test-enable run it is NOT: odoo/tests/result.py logError()
#     logs "<FAIL|ERROR>: <test>" followed by
#     traceback.TracebackException.format(), so every failing test writes one -
#     every failing PYTHON test, that is; a Hoot/QUnit failure writes none -
#     but so does any logged exception the run recovers from, ir_http's routing
#     errors, sql_db, and every HttpCase 500 the test asserts on. MEASURED
#     across every real run log on disk: the traceback count matches the
#     FAIL:/ERROR: marker count in only three quarters of them, and the
#     divergence is large and one-directional (96 tracebacks against 4 markers;
#     13 against 3; 12 against 9; 17 against 16), including a run with one
#     traceback and no failure marker at all whose own summary reported nothing
#     failed. So on a test run it is per-test/incidental evidence, never a
#     verdict - ruling on it is the same false-RED bug as keying on the level
#     column. EVERY test-verb path below therefore rules on
#     _TEST_FAIL_RE|_BUILD_ABORT_RE and never on _INSTALL_FAIL_RE; a genuinely
#     failing test is still caught because result.py logs its FAIL:/ERROR:
#     marker BEFORE the traceback, so the marker set loses nothing - the set
#     being _TEST_FAIL_RE, which carries the Hoot/QUnit vocabulary too, not the
#     Python pair alone.
#   _INSTALL_SUCCESS_MARKER - the completion line kept on the log by
#     --log-handler=<ns>.modules.loading:INFO, a floor that survives any
#     caller-supplied level.
# ---------------------------------------------------------------------------
_BUILD_ABORT_RE='CRITICAL|invalid module names, ignored|Some modules are not loaded|Unmet dependenc|cannot be installed|Failed to load registry|psycopg2\.|ParseError'
_PER_TEST_TRACEBACK_RE='Traceback \(most recent call last\)'
_INSTALL_FAIL_RE="${_BUILD_ABORT_RE}|${_PER_TEST_TRACEBACK_RE}"
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
# JS test-outcome marker SSOT - the SECOND per-test vocabulary. A --test-enable
#   build runs Python unittest AND a browser JS suite, and the two publish
#   COMPLETELY DIFFERENT wordings. The Python set below matches none of these:
#   the numeric catch-all `[1-9][0-9]* (failed|error)` fails on
#   `1876 / 34338 tests failed` (a word sits between the digit and `failed`) and
#   on `ended (passed: 5530 / failed: 481)` (a colon does). Without this block a
#   JS run's failures are represented by the ONE `FAIL:` line the Python wrapper
#   method raises, whatever the true magnitude.
#
#   THE RUN BOUNDARY IS THE LOGGER SCOPE, NOT THE FILE. One log file holds
#   SEVERAL JS runs: Odoo logs each browser suite under its own
#   `<ns>.addons.<module>.tests.test_js.<Suite>[.<method>].browser` logger, and
#   one `test` verb can drive several. Every figure below is therefore read PER
#   SCOPE and summed; de-duplicating across the whole file merges runs that
#   share test names and destroys real failures.
#
#   _JS_SCOPE_RE - the run boundary AND the echo filter. Odoo prints the failing
#     `browser_js(...)` SOURCE LINE inside its traceback, so the log contains
#     `success_signal="[HOOT] Test suite succeeded"` verbatim in runs that
#     FAILED. That echo carries no logger prefix; a real marker always does,
#     and the prefix it carries is what binds it to one run - every marker
#     below is read per scope only.
#     The suite/method segment is deliberately unconstrained: the wrapper method
#     is renamed three times across the supported series (`test_01_js`/
#     `test_02_js` at v11-v12, `test_js` at v13-v17, `test_unit_desktop`/
#     `test_hoot`/`test_qunit_desktop` at v18-v19 - read from
#     web/tests/test_js.py per series), so keying on it would gate the counter
#     to one era.
#   _JS_HOOT_TEST_FAIL_RE - ONE failing Hoot test. Unit: TESTS.
#   _JS_HOOT_SUITE_END_RE / _JS_HOOT_SUITE_FAILED_RE - a Hoot suite's own
#     trailer. A suite name with no `/` is a ROOT suite; roots are disjoint by
#     construction (nesting is a tree), so summing the roots' failed values
#     cannot double count while summing every `ended` line would. A fully green
#     suite omits the `/ failed:` half entirely, which is why the two forms are
#     separate: the shorter one still proves a JS run happened.
#   _JS_QUNIT_TEST_FAIL_RE - ONE failing QUnit test line. Echoed within its own
#     scope, and also re-printed with no scope at all, so it is used for NAMES
#     (de-duplicated) and never as a count.
#   _JS_QUNIT_AGG_RE - QUnit's own published aggregate. Unit: failed
#     ASSERTIONS, not tests - 4 distinct failing tests report `8 / 422`
#     (measured on the real corpus). It is the only figure a QUnit run publishes
#     for itself and it is NOT derivable from the test names, which is why both
#     quantities are emitted under separate names rather than reconciled.
#   _JS_GREEN_RE - the positive markers. Scope-anchored like every other one: a
#     green marker is a verdict for ITS OWN SCOPE ONLY. A log can carry a
#     genuine `[HOOT] Test suite succeeded` for one run and hundreds of failures
#     in another run of the SAME file.
#   _JS_FAIL_RE - "some JS test failed". Joined into _TEST_FAIL_RE below so a
#     JS-only failure can never be certified green if Odoo ever stops raising in
#     the Python wrapper. The aggregate alternative requires a NON-ZERO count
#     here; the count-parsing form allows zero.
#   _JS_MARKER_RE - "this log contains a JS run at all", failing or green. The
#     union is what makes EMPTY (unmeasured) distinguishable from a measured 0.
#
#   Marker WORDING is corpus-verified on 17.0 / 18.0 / 19.0 only (the run logs
#   that exist). For 11.0-16.0 OSM grounds the FRAMEWORK (QUnit only, no Hoot
#   suite indexed before 18.0) and the wrapper method names, but not the browser
#   console wording - so those series are covered by the same QUnit patterns
#   without a runtime witness. 8.0-10.0 index no JS suite at all; there the
#   fields are legitimately EMPTY, never 0.
#
#   LEVEL SENSITIVITY: the failing halves (`[HOOT] Test ... failed:`,
#   `QUnit test failed:`, the QUnit aggregate) are logged at ERROR, so they
#   survive any level this script emits. The Hoot suite trailers and both green
#   markers are INFO. A caller who forces a level above INFO through --extra
#   therefore loses the root-suite sum (the count falls back to the per-test
#   line count, which is <= it) and loses green-run detection - never a false
#   green, but a possible undercount. The shared default is `info` and `warn` is
#   refused outright, so the default path is unaffected.
# ---------------------------------------------------------------------------
_JS_SCOPE_RE='(openerp|odoo)\.addons\.[A-Za-z0-9_.]*tests\.test_js\.[A-Za-z0-9_.]+\.browser:'
_JS_HOOT_TEST_FAIL_RE='\[HOOT\] Test "[^"]+" failed:'
_JS_HOOT_SUITE_END_RE='\[HOOT\] "[^"]+" ended \(passed: [0-9]+'
_JS_HOOT_SUITE_FAILED_RE="${_JS_HOOT_SUITE_END_RE} / failed: [0-9]+"
_JS_QUNIT_TEST_FAIL_RE='QUnit test failed: '
_JS_QUNIT_AGG_TAIL=' / [0-9]+ tests failed'
_JS_QUNIT_AGG_RE="[0-9]+${_JS_QUNIT_AGG_TAIL}"
# Positive markers: a verdict for its own scope only, never for the file.
_JS_GREEN_RE='\[HOOT\] Test suite succeeded|QUnit test suite done'
_JS_FAIL_RE="${_JS_HOOT_TEST_FAIL_RE}|${_JS_QUNIT_TEST_FAIL_RE}|[1-9][0-9]*${_JS_QUNIT_AGG_TAIL}"
_JS_MARKER_RE="${_JS_FAIL_RE}|${_JS_HOOT_SUITE_END_RE}|${_JS_QUNIT_AGG_RE}|${_JS_GREEN_RE}"

# ---------------------------------------------------------------------------
# Test-outcome marker SSOT (read from Odoo source, all 12 series v8.0-v19.0).
#   Split by WHAT EACH MARKER PROVES, not merely by wording, because the two
#   verdict paths need different questions answered from the same set:
#   _parse_test_result asks "did this FINISHED run fail?" (any of them), while
#   _scan_build_markers asks "is this RUNNING build's outcome decided yet?"
#   (none of them - only the run's own verdict line or a _BUILD_ABORT_RE hit).
#
#   _TEST_FAIL_PER_TEST_*_RE - ONE failing test. `FAIL:`/`ERROR:` message
#     bodies (distinct from the ERROR log LEVEL) exist on every series. MID-RUN
#     by construction: the suite carries on to the next test afterwards.
#   _TEST_FAIL_MODULE_RE - the per-MODULE aggregate, byte-identical across the
#     eras apart from a suffix ("Module <m>: <F> failures, <E> errors" v8.0-v13.0
#     modules/module.py; the same plus " of <T> tests" v14.0-v19.0
#     modules/loading.py). Also MID-RUN: it is logged inside the module loop, so
#     the run still has later modules to load. Odoo emits it ONLY for a module
#     whose suite was not successful, so it can never carry "0 failures, 0
#     errors" - no non-zero guard needed, and it never contributes a false zero
#     to a count.
#   _TEST_FAIL_BLANKET_RE - loading.py's numberless line, on all 12 series. It
#     states THAT something failed and never how much.
#   _TEST_SUMMARY_RE - v14.0-v19.0's per-database total: tests/result.py's
#     OdooTestResult.__str__ rendered by service/server.py's "%s when loading
#     database %r". The run-level figure, so it WINS over the per-module lines
#     when a count is being read (a v14+ run logs both wordings; summing across
#     them would double-count).
#   _TEST_FAIL_PY_RE - the PYTHON half of "this finished run failed". Named
#     separately because the findings file quotes it as the aggregate/abort
#     evidence a run left when it named no individual Python test; quoting the
#     JS half there would duplicate the per-run JS section.
#   _TEST_FAIL_RE - the union: "this finished run failed". _parse_test_result's
#     verdict input, and the gate _scan_build_markers puts in front of a
#     completion marker so a summary reporting its own non-zero counts can never
#     be certified as a successful build. It unions the Python wordings above
#     with _JS_FAIL_RE (SSOT block immediately above): the per-test vocabulary
#     of a --test-enable build is TWO vocabularies, and neither is a subset of
#     the other.
#   _TEST_RAN_*_RE - the POSITIVE "tests actually RAN" marker, and the ONLY
#     era-SPLIT one: v8.0-v13.0 emit `Ran <N> test(s) in <X>s` (stdlib runner
#     trailer, INFO), v14.0-v19.0 emit the _TEST_SUMMARY_RE wording. Both
#     REQUIRE a non-zero total, so a tag filter that matched nothing can never
#     certify a pass.
#   _TEST_SKIP_RE - a test the runner SKIPPED. Not a failure (a @tagged filter
#     or a missing optional external dependency produces one legitimately) and
#     not a pass either, so it is the one marker that turns an otherwise-clean
#     ran-marker into `inconclusive`. BOTH verdict paths read it: it is why
#     _parse_test_result refuses `passed`, and why _scan_build_markers refuses
#     to certify SUCCESS from a bare ran-marker. Held here rather than inside
#     one function because a skip-aware verdict path and a skip-blind one
#     answering opposite things about one log is precisely the disagreement
#     this SSOT block exists to prevent.
#     BOTH alternatives anchor on a real test-package PATH SEGMENT, never a
#     bare substring: a literal `.` immediately before the "test(s)" token (so
#     it is a whole dot-delimited segment) and a literal `.`/`:` immediately
#     after it (so a longer word cannot satisfy it). Without those anchors it
#     false-positives on ordinary model/module names that merely CONTAIN
#     "test" and on unrelated `... skipped` business messages.
#       1. v14+ modern Odoo test-runner logger name: `(openerp|odoo).<pkg
#          path>.tests?[.:]<...>: skip[ped] <name>` (<ns> = openerp v8-v9 /
#          odoo v10+, matching _resolve_log_ns).
#       2. Older Python-stdlib unittest verbose runner line (bypasses the Odoo
#          logger, so no <ns> prefix): `test_name (<module path containing a
#          .tests. or .test. segment>) ... skipped`.
#     The exact per-series wording is Odoo framework-internal, so this is
#     deliberately a two-shape, case-insensitive regex - but never a bare
#     `grep -i skip`, which reopens both false-positive classes above.
# ---------------------------------------------------------------------------
_TEST_FAIL_PER_TEST_FAIL_RE='(^|[[:space:]])FAIL:'
_TEST_FAIL_PER_TEST_ERROR_RE='(^|[[:space:]])ERROR:'
_TEST_FAIL_PER_TEST_RE="${_TEST_FAIL_PER_TEST_FAIL_RE}|${_TEST_FAIL_PER_TEST_ERROR_RE}"
_TEST_FAIL_MODULE_RE='Module [A-Za-z0-9_.]+: [0-9]+ failures?, [0-9]+ errors?'
_TEST_FAIL_BLANKET_RE='At least one test failed when loading the modules'
_TEST_SUMMARY_RE='[0-9]+ failed, [0-9]+ error\(s\) of [0-9]+ tests'
_TEST_FAIL_PY_RE="${_TEST_FAIL_PER_TEST_RE}|${_TEST_FAIL_MODULE_RE}|${_TEST_FAIL_BLANKET_RE}|[1-9][0-9]* (failed|error)"
_TEST_FAIL_RE="${_TEST_FAIL_PY_RE}|${_JS_FAIL_RE}"
_TEST_RAN_LEGACY_RE='Ran [1-9][0-9]* tests? in '
_TEST_RAN_MODERN_RE='[0-9]+ failed, [0-9]+ error\(s\) of [1-9][0-9]* tests'
_TEST_SKIP_RE='(^|[[:space:]])(openerp|odoo)\.[a-z0-9_.]*\.tests?[.:][a-z0-9_.]*:[[:space:]]*skip|(^|[[:space:]])test_[a-z0-9_]+[[:space:]]+\([a-z0-9_.]*\.tests?\.[a-z0-9_.]+\)[[:space:]]+\.\.\.[[:space:]]+skip'

# ---------------------------------------------------------------------------
# Progress-marker SSOT - the ADVANCING evidence a polling caller diffs across
#   two waits. NEVER a verdict: nothing here may promote a build to success or
#   demote it to failure, in any branch. A marker that decides an outcome is a
#   terminal marker and belongs in one of the sets above.
#
#   Why a separate set at all: the only in-flight evidence this scan used to
#   report was `loading <N> modules...`, which Odoo logs ONCE per registry load.
#   During a test suite it therefore never changes, so "the same evidence twice
#   means the build stopped" was false for every long test run - a healthy suite
#   and an odoo-bin that had been killed mid-suite produced byte-identical
#   output. The markers below advance while the suite runs, which is what makes
#   that rule true.
#
#   MEASURED by reading the Odoo source of all 12 supported series (8.0-19.0)
#   for the literal format string AND the level it is logged at - the level
#   matters because the shared default is `info`, so a DEBUG line is invisible.
#   Applied era-BLIND on purpose: a rendered log only ever holds its OWN
#   series' wording, and every wording below means the SAME thing ("one more
#   unit of work finished"), so a cross-era match cannot mislead. That is the
#   opposite of _test_ran_re, which MUST gate by series because there the two
#   wordings certify a pass and accepting the wrong era's would be a false
#   green.
#
#   _PROGRESS_DATAFILE_RE - modules/loading.py logs `loading <module>/<file>`
#     at INFO once per data file it converts. Present on ALL 12 series and the
#     only progress wording that is; covers the module-install phase of every
#     verb, including the install phase of a --test-enable build.
#   _PROGRESS_TEST_START_RE - the test result class logs `Starting
#     <Class>.<method> ...` at INFO once per test STARTED, from 13.0 onward
#     (modules/module.py at 13.0, tests/runner.py at 14.0-15.0, tests/result.py
#     from 16.0). Per-test granularity, so it advances throughout a long suite.
#   _PROGRESS_TEST_MODULE_RE - 8.0-13.0 modules/module.py logs `<test module>
#     running tests.` at INFO once per test MODULE entered. This is the only
#     test-phase progress wording 8.0-12.0 emit at all, so on those five series
#     progress advances per test FILE rather than per test - coarser, still
#     advancing, and it is why a stall reading is weaker (not absent) there.
#
#   Deliberately NOT used, each for a measured reason:
#     `Loading module <name> (<i>/<n>)` - DEBUG on 10.0-13.0 and absent before
#       10.0, so invisible at the `info` floor across half the range.
#     `Modules loaded.` - loading.py logs it XOR `At least one test failed when
#       loading the modules.` on all 12 series, so a --test-enable build with
#       any at_install failure never emits it. It is a terminal marker for
#       init/update regardless and must not be counted as progress.
# ---------------------------------------------------------------------------
_PROGRESS_DATAFILE_RE='loading [A-Za-z0-9_.]+/[^[:space:]]+'
_PROGRESS_TEST_START_RE='Starting .+ \.\.\.'
_PROGRESS_TEST_MODULE_RE='[A-Za-z0-9_.]+ running tests\.'
_BUILD_PROGRESS_RE="${_PROGRESS_DATAFILE_RE}|${_PROGRESS_TEST_START_RE}|${_PROGRESS_TEST_MODULE_RE}"

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
# _build_progress <logf> - one comparable reading of HOW FAR the build has got.
#   Two consecutive readings that DIFFER prove the build did work in between;
#   two that are IDENTICAL and non-empty prove it wrote NOTHING AT ALL in
#   between. It answers nothing about pass/fail and no caller may derive an
#   outcome from it.
#
#   BOTH components are emitted ALWAYS, as `markers:<n>|bytes:<m>` - never one
#   OR the other. An either/or reading is what froze this field on real runs:
#   every build publishes hundreds of install-phase progress lines, so `markers`
#   is permanently non-zero long before the test phase starts, which permanently
#   suppressed a byte fallback that only ever fired at `markers:0`. The byte
#   count was therefore unavailable in the ONE state where it is the only signal
#   left - a test phase spent inside a single long test.
#
#   `markers:<n>` - n progress lines the run published (SSOT:
#     _BUILD_PROGRESS_RE). The STRONG component: n rises only when the build
#     actually finished another data file, test module, or test, so a rise is
#     proof of a completed unit of work. It CAN sit still through a healthy run:
#     a browser/JS suite is one test that streams thousands of console lines
#     under a logger no progress wording matches, and on the earliest series the
#     finest granularity is one test FILE.
#   `bytes:<m>` - the log's own length. The WEAK component, and weak in one
#     direction only: a rise proves only that something was appended, not that
#     the build advanced - but it is what makes the reading MOVE for any run
#     that is still writing, including one inside a single long test and one at
#     a caller-chosen level that suppresses every progress wording. Both
#     components carry their own prefix so a reader can always tell which fact
#     moved.
#   Composed, the reading is FROZEN only when the process appended zero bytes
#   for the whole comparison window - which is the strongest in-log evidence of
#   a stopped build available without signalling the process, and is still not
#   proof of death (a hung browser suite writes nothing either, until its own
#   timeout fires). The caller's stall rule must stay worded accordingly.
#   EMPTY - there is no log file to measure. Absence of a reading is NOT a
#     stall; it is the absence of evidence either way, and the caller must not
#     resolve it as success, failure, or a stopped build.
# ---------------------------------------------------------------------------
_build_progress() {
    local logf="$1" n bytes
    [[ -f "$logf" ]] || return 0
    bytes="$(wc -c <"$logf" 2>/dev/null || true)"
    bytes="${bytes//[[:space:]]/}"
    [[ "$bytes" =~ ^[0-9]+$ ]] || return 0
    n="$(grep -acE "$_BUILD_PROGRESS_RE" "$logf" 2>/dev/null || true)"
    [[ "$n" =~ ^[0-9]+$ ]] || n=0
    printf 'markers:%s|bytes:%s\n' "$n" "$bytes"
}

# ---------------------------------------------------------------------------
# _aggregate_fail_counts <logf> - "<failures> <errors>" as the run itself
#   REPORTED them, or NOTHING when the log carries no numeric aggregate at all.
#   Era-BLIND on purpose: a log only ever holds its own series' wording, so a
#   version gate here would buy nothing and could only mis-fire on a log whose
#   --version was never threaded through.
#   The per-DATABASE total (_TEST_SUMMARY_RE) WINS when present - a v14+ run
#   logs the per-module wording too, so summing across the two would report
#   double the real figure. Otherwise the per-MODULE lines are summed, one row
#   per failing module, which is the only wording v8.0-v13.0 has.
#   The blanket "At least one test failed" line carries no number and therefore
#   yields nothing here: that run's counts are UNMEASURABLE, which the caller
#   must report as EMPTY rather than invent a zero for.
#   Prints nothing and returns 0 when there is nothing to read - "no aggregate"
#   is not an error.
# ---------------------------------------------------------------------------
_aggregate_fail_counts() {
    local logf="$1" line f e total_f=0 total_e=0 hit=0
    line="$(grep -aoE "$_TEST_SUMMARY_RE" "$logf" 2>/dev/null | tail -n 1 || true)"
    if [[ -n "$line" ]]; then
        f="$(printf '%s\n' "$line" | sed -nE 's/^([0-9]+) failed, ([0-9]+) error.*/\1/p')"
        e="$(printf '%s\n' "$line" | sed -nE 's/^([0-9]+) failed, ([0-9]+) error.*/\2/p')"
        if [[ "$f" =~ ^[0-9]+$ && "$e" =~ ^[0-9]+$ ]]; then
            printf '%s %s\n' "$f" "$e"
            return 0
        fi
    fi
    while IFS= read -r line; do
        [[ -n "$line" ]] || continue
        f="$(printf '%s\n' "$line" | sed -nE 's/.*: ([0-9]+) failures?, ([0-9]+) errors?.*/\1/p')"
        e="$(printf '%s\n' "$line" | sed -nE 's/.*: ([0-9]+) failures?, ([0-9]+) errors?.*/\2/p')"
        [[ "$f" =~ ^[0-9]+$ && "$e" =~ ^[0-9]+$ ]] || continue
        total_f=$(( total_f + f ))
        total_e=$(( total_e + e ))
        hit=1
    done < <(grep -aoE "$_TEST_FAIL_MODULE_RE" "$logf" 2>/dev/null || true)
    [[ "$hit" -eq 1 ]] && printf '%s %s\n' "$total_f" "$total_e"
    return 0
}

# ---------------------------------------------------------------------------
# _js_fail_counts <logf> - the JS (Hoot/QUnit) half of the per-test vocabulary,
#   read PER LOGGER SCOPE. Prints a TAB-separated report, or NOTHING when the
#   log carries no JS marker at all (unmeasured - the caller emits EMPTY, never
#   0, exactly as it does for the Python counts):
#
#     SUMMARY <mode> <runs> <reported> <tests>
#     RUN     <scope> <framework> <reported> <tests>
#     TEST    <scope> <failing test name>
#
#   TWO count fields, because the two frameworks count DIFFERENT UNITS and
#   neither derives from the other:
#     <reported> = each run's OWN published figure summed over runs. QUnit's
#       aggregate counts failed ASSERTIONS; Hoot's root trailers count failed
#       TESTS. Mixed units on purpose - it is what the runs themselves said.
#     <tests>    = distinct failing TEST NAMES, always the same unit, and the
#       key the findings file is written on. EMPTY in `unscoped` mode, where no
#       per-test name is recoverable.
#   Reporting only one of them would either discard the run's own figure or
#   claim a test count the run never published; on the real corpus the two
#   differ by up to 2.18x within a single scope.
#
#   Per scope:
#     hoot  = max(per-test failure lines, sum of ROOT suite trailers). The two
#             disagree by ~1 percent on real logs; the max is the safe floor and
#             the root sum is what recovers failures that ended without their
#             own per-test line.
#     qunit = sum over the DISTINCT (failed,total) aggregate pairs. Odoo prints
#             each aggregate twice inside its scope (once at ERROR, once at INFO
#             prefixed "Error received after termination"), so the pair set - not
#             the line count - is the figure.
#
#   UNSCOPED FALLBACK: when the log carries NO scope line at all but does carry
#   a bare `<F> / <T> tests failed` aggregate, that figure is taken and the mode
#   is reported as `unscoped` so the caller knows per-test names are
#   unavailable. Two real 17.0 logs publish their only aggregate that way; the
#   scope anchor alone silently loses both. This cannot pick up the traceback
#   echo: the echo is a `success_signal="..."` source line, never an aggregate.
#   When any scope line exists the unscoped bucket is IGNORED - it holds
#   duplicate copies of the scoped figures.
# ---------------------------------------------------------------------------
_js_fail_counts() {
    local logf="$1"
    [[ -r "$logf" ]] || return 0
    JS_MARKER_RE="$_JS_MARKER_RE" \
    JS_SCOPE_RE="$_JS_SCOPE_RE" \
    JS_HOOT_FAIL_RE="$_JS_HOOT_TEST_FAIL_RE" \
    JS_HOOT_END_RE="$_JS_HOOT_SUITE_END_RE" \
    JS_HOOT_ENDF_RE="$_JS_HOOT_SUITE_FAILED_RE" \
    JS_QUNIT_FAIL_RE="$_JS_QUNIT_TEST_FAIL_RE" \
    JS_QUNIT_AGG_RE="$_JS_QUNIT_AGG_RE" \
    JS_GREEN_RE="$_JS_GREEN_RE" \
    awk '
        # Regexes arrive through the environment, never through -v: awk expands
        # backslash escapes in a -v assignment, which would eat every \[ and \(
        # in the marker SSOT and silently change what is matched.
        function firstnum(s,   n) { if (match(s, /[0-9]+/)) return substr(s, RSTART, RLENGTH) + 0; return 0 }
        function lastnum(s,   n) { n = 0; while (match(s, /[0-9]+/)) { n = substr(s, RSTART, RLENGTH) + 0; s = substr(s, RSTART + RLENGTH) } return n }
        # The first double-quoted run inside a matched marker is the entity it
        # names - the test for a failure line, the suite for a trailer.
        function quoted(s,   a, rest, b) {
            a = index(s, "\""); if (a == 0) return ""
            rest = substr(s, a + 1); b = index(rest, "\""); if (b == 0) return ""
            return substr(rest, 1, b - 1)
        }
        function trim(s) { sub(/^[ \t]+/, "", s); sub(/[ \t:]+$/, "", s); return s }
        function note_scope(sc) { if (!(sc in seen_scope)) { seen_scope[sc] = 1; order[++nscope] = sc } }
        BEGIN {
            MARK   = ENVIRON["JS_MARKER_RE"];   SCOPE  = ENVIRON["JS_SCOPE_RE"]
            HFAIL  = ENVIRON["JS_HOOT_FAIL_RE"]; HEND  = ENVIRON["JS_HOOT_END_RE"]
            HENDF  = ENVIRON["JS_HOOT_ENDF_RE"]; QFAIL = ENVIRON["JS_QUNIT_FAIL_RE"]
            QAGG   = ENVIRON["JS_QUNIT_AGG_RE"]; GREEN = ENVIRON["JS_GREEN_RE"]
            nscope = 0; FS = "\n"; OFS = "\t"
        }
        $0 !~ MARK { next }
        {
            sc = ""
            if (match($0, SCOPE)) {
                tok = substr($0, RSTART, RLENGTH)
                sub(/^.*test_js\./, "", tok); sub(/\.browser:$/, "", tok)
                sc = tok
            }
            if (sc == "") {
                # Only the aggregate survives without a scope; a bare per-test
                # line or green marker here is an echo or a duplicate.
                if (match($0, QAGG)) { span = substr($0, RSTART, RLENGTH); unscoped[firstnum(span) "/" lastnum(span)] = firstnum(span) }
                next
            }
            note_scope(sc)
            # A green marker is a verdict for THIS scope only - never for the
            # file. The same log can carry one here and hundreds of failures in
            # the next scope.
            if (match($0, GREEN)) green[sc] = 1
            if (match($0, HFAIL)) {
                span = substr($0, RSTART, RLENGTH); nm = quoted(span)
                hoot_raw[sc]++
                if (nm != "" && !((sc SUBSEP nm) in seen_test)) { seen_test[sc SUBSEP nm] = 1; tests[sc, ++ntest[sc]] = nm; hoot_named[sc] = 1 }
            }
            if (match($0, HEND)) {
                span = substr($0, RSTART, RLENGTH); suite = quoted(span)
                hoot_named[sc] = 1
                if (suite != "" && index(suite, "/") == 0 && !((sc SUBSEP suite) in seen_root)) {
                    seen_root[sc SUBSEP suite] = 1
                    if (match($0, HENDF)) root_sum[sc] += lastnum(substr($0, RSTART, RLENGTH))
                }
            }
            if (match($0, QFAIL)) {
                nm = trim(substr($0, RSTART + RLENGTH))
                qunit_named[sc] = 1
                if (nm != "" && !((sc SUBSEP nm) in seen_test)) { seen_test[sc SUBSEP nm] = 1; tests[sc, ++ntest[sc]] = nm }
            }
            if (match($0, QAGG)) {
                span = substr($0, RSTART, RLENGTH); key = firstnum(span) "/" lastnum(span)
                qunit_named[sc] = 1
                if (!((sc SUBSEP key) in seen_agg)) { seen_agg[sc SUBSEP key] = 1; qunit[sc] += firstnum(span) }
            }
        }
        END {
            if (nscope == 0) {
                npair = 0; urep = 0
                for (k in unscoped) { npair++; urep += unscoped[k] }
                if (npair == 0) exit 0
                print "SUMMARY", "unscoped", 1, urep, ""
                print "RUN", "unscoped", "qunit", urep, ""
                exit 0
            }
            total_rep = 0; total_tests = 0
            for (i = 1; i <= nscope; i++) {
                sc = order[i]
                h = hoot_raw[sc] + 0; if (root_sum[sc] + 0 > h) h = root_sum[sc] + 0
                rep[sc] = h + (qunit[sc] + 0)
                total_rep += rep[sc]; total_tests += ntest[sc] + 0
                fw = ""
                if (hoot_named[sc]) fw = "hoot"
                if (qunit_named[sc]) fw = (fw == "" ? "qunit" : fw "+qunit")
                if (fw == "" && green[sc]) fw = "passed"
                if (fw == "") fw = "none"
                frame[sc] = fw
            }
            print "SUMMARY", "scoped", nscope, total_rep, total_tests
            for (i = 1; i <= nscope; i++) { sc = order[i]; print "RUN", sc, frame[sc], rep[sc], ntest[sc] + 0 }
            for (i = 1; i <= nscope; i++) { sc = order[i]; for (j = 1; j <= ntest[sc]; j++) print "TEST", sc, tests[sc, j] }
        }
    ' "$logf" 2>/dev/null || true
    return 0
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
#   docs/reference/INSTANCE-LIFECYCLE-BUILD-CONTRACT.md item 14). Never blocks - two grep
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
# _leased_db_names, _prune_stale_logs and _LOG_RETENTION_DAYS now live in
# scripts/lib/state_reclaim.sh (sourced at the top of this file) so
# 50-instance-spinup.sh reaches the SAME mechanism instead of growing a second
# one. `prune_stale_run_artifacts` is the generalised sweeper both call.
# ---------------------------------------------------------------------------

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
#   Empty when the log carries no stamp. That is a REACHABLE state, not a
#   theoretical one - any log written before this stamp existed, and any log a
#   caller points wait-log at that this script did not open, arrives unstamped.
#   Empty means UNKNOWN, and the caller must resolve it to the predicate that
#   cannot certify a wrong answer - never to whichever one happens to be first.
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
#
#   This is one of the sweep's TWO named callers (the other is
#   50-instance-spinup.sh's cmd_apply source branch). It runs on EVERY
#   create/init/update/run-tests build, and it sweeps BOTH Tier-1 run-artifact
#   dirs - `logs/` (this script's own family) and `conf/` (the spin-up script's
#   family) - because a build is the hot path a host actually exercises, while a
#   listener spin-up may be rare on a host that only ever builds. Sweeping only
#   the family the caller writes would leave the other reachable from one script
#   alone, which is exactly the shape that let conf files accumulate.
# ---------------------------------------------------------------------------
_open_log() {
    local db_slug="$1" verb="${2:-}" version="${3:-}"
    local logs_dir
    logs_dir="$(odoo_ai_state_root)/logs"
    mkdir -p "$logs_dir"
    _prune_stale_logs "$logs_dir"
    prune_stale_run_artifacts "$(odoo_ai_state_root)/conf" '*.conf'
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

    # --- Counts (always; independent of the pass/fail verdict) --------------
    # The PYTHON unittest half (the Hoot/QUnit half is counted separately below,
    # under its own fields, and neither figure is the other's): Odoo logs each
    # failing test as a "FAIL:" line and each errored test as an "ERROR:" line
    # (the message body, distinct from the " ERROR " log level); warning log
    # lines carry the " WARNING " level token. Those per-test markers are the
    # most precise signal this suite publishes, so they are read first.
    local n_fail n_error n_warn
    n_fail="$(grep -acE "$_TEST_FAIL_PER_TEST_FAIL_RE" "$logf" 2>/dev/null || true)"
    n_error="$(grep -acE "$_TEST_FAIL_PER_TEST_ERROR_RE" "$logf" 2>/dev/null || true)"
    n_warn="$(grep -acE '[[:space:]]WARNING[[:space:]]' "$logf" 2>/dev/null || true)"
    n_fail="${n_fail:-0}"; n_error="${n_error:-0}"; n_warn="${n_warn:-0}"
    # Whether the log NAMED individual failing tests, kept before the counts can
    # be re-sourced from an aggregate below. The findings file branches on THIS,
    # not on the counts: once a count may legitimately come from an aggregate, a
    # non-zero count no longer implies there is a per-test marker to quote, and
    # branching on the count printed an empty evidence block.
    local per_test_markers=$(( n_fail + n_error ))

    # A run can fail while naming no individual test: the aggregate wordings
    # (SSOT above) are the only figures such a run published. Reading them here
    # is what stops this block emitting `TEST_FAILED=0 TEST_ERROR=0` beside a
    # `TEST_RESULT=failed` verdict - telling the caller the run failed and that
    # nothing failed, in the same breath, and driving the findings file below
    # into printing "no failing tests" for a failed build.
    # When there is no aggregate either, the figure is only a MEASURED zero if
    # the suite is PROVEN to have run (an era-correct ran-marker) and named
    # nothing. Absent that proof it is UNMEASURABLE and reported EMPTY - the
    # same rule MODULES_LOADED/TESTS_RUN follow, because a fabricated zero is a
    # worse answer than an absent one.
    if (( n_fail == 0 && n_error == 0 )); then
        local agg
        agg="$(_aggregate_fail_counts "$logf")"
        if [[ -n "$agg" ]]; then
            n_fail="${agg%% *}"
            n_error="${agg##* }"
        elif ! grep -aqE "$(_test_ran_re "${arg_version:-}")" "$logf" 2>/dev/null; then
            n_fail=""
            n_error=""
        fi
    fi

    # --- JS (Hoot/QUnit) counts, per run ------------------------------------
    # The SECOND per-test vocabulary (SSOT: the _JS_* block above). Kept in its
    # own fields rather than folded into TEST_FAILED: the Python counter counts
    # unittest cases, JS_FAILED_REPORTED mixes QUnit assertions with Hoot tests,
    # and summing three units into one figure is how the run's magnitude got
    # lost in the first place. All four fields are EMPTY - never 0 - when the
    # log carries no JS marker at all, which is the honest answer for a series
    # that ships no JS suite and for a run whose modules have none.
    local js_report="" js_mode="" js_runs="" js_reported="" js_tests=""
    js_report="$(_js_fail_counts "$logf")"
    if [[ -n "$js_report" ]]; then
        local _js_summary
        _js_summary="$(printf '%s\n' "$js_report" | awk -F'\t' '$1=="SUMMARY"{print $2"\t"$3"\t"$4"\t"$5; exit}')"
        IFS=$'\t' read -r js_mode js_runs js_reported js_tests <<<"$_js_summary"
    fi

    # --- Skip detection -----------------------------------------------------
    # Bug: exit 0 + "0 failed, 0 error(s) of 1 tests" reads as green even when
    # the sole test was SKIPPED (never ran) - e.g. "skipped . : Failed to
    # detect chrome devtools port after 10.0s." A skip is not a failure (it is
    # frequently legitimate: @tagged filters, an optional external dependency
    # missing) but it also is NOT proof the suite ran clean, so it must be
    # counted and surfaced as its own field rather than silently folded into
    # "passed".
    #
    # The marker itself is _TEST_SKIP_RE (SSOT above) - shared with
    # _scan_build_markers so a skip cannot mean "not a pass" to one verdict
    # path and nothing at all to the other.
    local n_skip
    n_skip="$(grep -icE "$_TEST_SKIP_RE" "$logf" 2>/dev/null || true)"
    n_skip="${n_skip:-0}"

    # Skip NAMES for the findings file. Extraction runs over the plain
    # (non-line-numbered) matches - unlike the `grep -icE` count above, the
    # stdlib-shape sed pattern below anchors at line-start (^...), so a `-n`
    # line-number prefix would break it; the modern-shape pattern is
    # unanchored and unaffected either way. Each matched line satisfies at
    # most one of the two shapes, so both sed passes run over the same input
    # and are merged + de-duplicated.
    local skip_lines skip_names=""
    skip_lines="$(grep -aiE "$_TEST_SKIP_RE" "$logf" 2>/dev/null || true)"
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

    # --- Pass/fail verdict ---------------------------------------------------
    # Resolved BEFORE the findings file is written, because that file has to
    # AGREE with it: an agent handed `TEST_RESULT=failed` and a findings file
    # saying "no failing tests" has been told the run failed and that nothing
    # failed. Computed into a variable and emitted once, further down, so there
    # is still exactly one TEST_RESULT= line on stdout.
    local verdict=""
    if [[ "$exit_code" -ne 0 ]]; then
        verdict="failed"
    # FAILURE next - the three-era test-marker set (SSOT: _TEST_FAIL_RE above)
    # UNIONED with the install/abort marker set (SSOT: _INSTALL_FAIL_RE). The
    # per-module aggregate wording ("Module <m>: <F> failures, <E> errors",
    # v8.0-v13.0, plus " of <T> tests" from v14.0) has always been part of
    # _TEST_FAIL_RE, so the VERDICT on an aggregate-only run was already
    # `failed`; what was wrong is that the COUNTS beside it read
    # `TEST_FAILED=0 TEST_ERROR=0` and the findings file answered "no failing
    # tests" for it - measured against the pre-change script, not assumed. The
    # counts block above is what fixes that; this branch is unchanged behavior
    # and must stay, because it is the only thing that rules such a run failed
    # at all. An INSTALL
    # failure inside a --test-enable build (misspelled module, unmet dependency)
    # writes no fail-, skip- OR ran-marker at all, so it used to fall through to
    # `inconclusive`; it is a FAILED run - the suite could not run - and the
    # union also stops a module that DID install from certifying the build green
    # while a named module was silently skipped.
    # The abort half is _BUILD_ABORT_RE, NOT the whole _INSTALL_FAIL_RE: this
    # call only ever reads a --test-enable log, where a lone traceback is
    # per-test/incidental evidence rather than a verdict (SSOT above). Ruling on
    # it turned a run whose own summary reported nothing failed into `failed`.
    # _scan_build_markers gates its own completion check on this SAME union, so
    # a log this call rules failed can never be certified a successful build
    # there, and a log it rules passed can never be ruled failed there.
    elif grep -aqE "$_TEST_FAIL_RE|$_BUILD_ABORT_RE" "$logf" 2>/dev/null; then
        verdict="failed"
    # Skip verdict - MUST precede the positive-pass check: a skip-only run still
    # emits a ran-marker with a non-zero count. Skips are not fatal (never force
    # a non-zero exit; exit_code above already governs failed/error - they are
    # legitimately produced by @tagged filters or a missing optional external
    # dependency) but are never silently certified as a bare `passed`.
    elif [[ "$n_skip" -gt 0 ]]; then
        verdict="inconclusive"
    # POSITIVE pass marker, era-resolved. Mirrors _install_confirmed exactly:
    # the ABSENCE of a positive "the suite ran" line is itself the finding,
    # never a fallthrough to success - exit 0 with no ran-marker means the tag
    # filter matched nothing, not that the suite passed. arg_version comes from
    # the caller's scope (bash dynamic scope); when it is absent the era gate
    # degrades to accepting EITHER wording.
    elif grep -aqE "$(_test_ran_re "${arg_version:-}")" "$logf" 2>/dev/null; then
        verdict="passed"
    else
        verdict="inconclusive"
    fi

    # Per-volume contract: the DETAIL goes to a file next to the log; stdout
    # carries only the counts + the pointer.
    local findings="${logf%.log}.findings.md"
    local tb_head=20 warn_cap=50
    local mod_regex=""
    [[ -n "${arg_modules:-}" ]] && mod_regex="${arg_modules//,/|}"
    # The aggregate/abort line(s) that state a failure the log never attributed
    # to an individual test - the ONLY evidence a run like that leaves behind.
    # The PYTHON half only: the JS failures have their own per-run section
    # below, and repeating a thousand browser lines here would bury the one
    # aggregate line this block exists to surface.
    local agg_evidence=""
    agg_evidence="$(grep -aE "$_TEST_FAIL_PY_RE|$_BUILD_ABORT_RE" "$logf" 2>/dev/null \
                        | head -n "$warn_cap" || true)"

    {
        echo "# Test findings"
        echo
        echo "Log: $logf"
        echo "Verdict: TEST_RESULT=$verdict"
        echo "Counts: failed=$n_fail error=$n_error warning=$n_warn skipped=$n_skip"
        echo "(an EMPTY count means the log carried no marker to measure it - never zero)"
        echo
        echo "## Failures and errors (marker line + first $tb_head lines)"
        echo
        if [[ "$per_test_markers" -gt 0 ]]; then
            echo '```'
            grep -aE -A "$tb_head" "$_TEST_FAIL_PER_TEST_RE" "$logf" 2>/dev/null || true
            echo '```'
        elif [[ -n "$js_reported" && "$js_reported" != "0" ]]; then
            # Checked BEFORE the generic failed-run branch, because that branch's
            # sentence ("named no individual test") is FALSE here: the browser
            # suite named every one of them, under the other vocabulary. This is
            # also the branch that stops "no failing tests" being printed for a
            # run whose failures are all JS.
            echo "No Python per-test marker was logged. The individual failures this run"
            echo "recorded are JS (Hoot/QUnit) - named per run in the section below."
            if [[ -n "$agg_evidence" ]]; then
                echo
                echo "The Python-side line(s) that also state a failure:"
                echo
                echo '```'
                printf '%s\n' "$agg_evidence"
                echo '```'
            fi
        elif [[ "$verdict" == "failed" ]]; then
            # A failed run that named no individual test. Its failure is stated
            # by its own aggregate/abort line, or by odoo-bin's exit code alone;
            # either way "no failing tests" is the one answer this section must
            # never give here.
            echo "This run FAILED without naming an individual test."
            if [[ -n "$agg_evidence" ]]; then
                echo "The line(s) that state the failure:"
                echo
                echo '```'
                printf '%s\n' "$agg_evidence"
                echo '```'
            else
                echo "The log carries no failure marker at all: the verdict comes from"
                echo "odoo-bin's non-zero exit code. Read the log tail for the cause."
            fi
        else
            echo "_No failing or errored tests detected in the log._"
        fi
        echo
        echo "## JS test failures (Hoot/QUnit), per run"
        echo
        echo "One block per JS run. A run is one browser-suite logger scope, NOT the file:"
        echo "a single log holds several, and merging them across the file loses failures"
        echo "that share a test name."
        echo
        if [[ -z "$js_report" ]]; then
            echo "_This log carries no JS test marker at all - no JS run was measured (not zero)._"
        elif [[ "$js_mode" == "unscoped" ]]; then
            echo "The only JS figure this log published is an aggregate with no logger scope,"
            echo "so the individual failing test names are NOT recoverable from it."
            echo
            echo "- reported failures (QUnit assertions): $js_reported"
        else
            printf '%s\n' "$js_report" | awk -F'\t' '$1=="RUN"{printf "- run `%s` (%s): reported=%s distinct failing tests=%s\n", $2, $3, $4, $5}'
            echo
            if [[ "$js_reported" != "$js_tests" ]]; then
                echo "Note: reported ($js_reported) and distinct failing tests ($js_tests) count DIFFERENT"
                echo "units - QUnit publishes failed ASSERTIONS, Hoot publishes failed TESTS. Neither"
                echo "is derivable from the other, so both are reported."
                echo
            fi
            local _js_scope _js_prev=""
            while IFS=$'\t' read -r _ _js_scope _js_name; do
                [[ -n "$_js_scope" ]] || continue
                if [[ "$_js_scope" != "$_js_prev" ]]; then
                    [[ -n "$_js_prev" ]] && { echo '```'; echo; }
                    echo "### $_js_scope"
                    echo
                    echo '```'
                    _js_prev="$_js_scope"
                fi
                printf '%s\n' "$_js_name"
            done < <(printf '%s\n' "$js_report" | awk -F'\t' '$1=="TEST"')
            [[ -n "$_js_prev" ]] && echo '```'
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
    # JS (Hoot/QUnit) scope + counts. JS_RUNS is the number of browser-suite
    # logger scopes this log carries, failing or green - the file is NOT the run.
    # JS_SCOPE=unscoped means the log published an aggregate with no logger
    # prefix, so JS_FAILED_TESTS is unavailable rather than zero. All four are
    # EMPTY together when no JS marker exists at all.
    echo "JS_RUNS=$js_runs"
    echo "JS_SCOPE=$js_mode"
    echo "JS_FAILED_REPORTED=$js_reported"
    echo "JS_FAILED_TESTS=$js_tests"

    # The verdict is resolved above, alongside the findings file it has to agree
    # with. Emitted LAST so it stays the final line of the summary block that
    # cmd_test appends to the log - the line `wait-log` keys its own terminal
    # verdict on.
    echo "TEST_RESULT=$verdict"
}

# ---------------------------------------------------------------------------
# _scan_build_markers - terminal-marker scan of a build log for a POLLING
#   caller. It answers ONE question - "is this build's outcome decided yet?" -
#   and it answers it with the SAME marker constants the foreground verdict
#   paths use, so the two can never contradict each other on one log.
#   Echoes BUILD_PROGRESS=<reading> (ALWAYS, on every path - the field a caller
#   diffs across two polls to learn whether the build is still doing work; see
#   _build_progress) and BUILD_MARKER=<matched line>, then returns:
#     0 -> DECIDED as a PASS. init/update: the "Modules loaded."
#          completion marker present AND no _INSTALL_FAIL_RE hit - by
#          construction the verdict _install_confirmed reaches on this same log,
#          so BUILD_RESULT can never disagree with the script's own
#          STATUS=ok|error line. test: the run's own TEST_RESULT= line says
#          passed, or (before that line lands) the era-correct ran-marker is
#          present with NO failure marker and NO skip marker anywhere - which is
#          exactly the state _parse_test_result calls `passed`.
#     1 -> DECIDED as a failure. init/update: any _INSTALL_FAIL_RE hit (a
#          silent-skip marker such as "invalid module names, ignored" alongside
#          "Modules loaded." is STILL a failed build, exactly as
#          _install_confirmed rules it). test: the run's own
#          TEST_RESULT=failed, or a _BUILD_ABORT_RE hit proving odoo-bin died
#          and will therefore never publish a verdict to wait for. ALSO the
#          fail-safe arm for a TEST_RESULT= value this scan does not recognize:
#          a scanner that has fallen behind the emitter may not certify a build
#          green, and a loud wrong RED is recoverable where a silent GREEN is
#          not.
#     2 -> NOT DECIDED yet (build still in flight; the last progress line is
#          echoed as evidence).
#     3 -> DECIDED, and NOT a pass: the run's own TEST_RESULT=inconclusive. The
#          run FINISHED - it is terminal, so a caller must not wait again - but
#          it proved no pass: the suite ran nothing, or everything it matched
#          was skipped. Distinct from 2 for that reason: reporting it as "not
#          finished" would leave a poller waiting forever on a run that is over,
#          and reporting it as 0 hands the caller a pass the run explicitly
#          refused to claim.
#   The verb comes from the log's OWN stamp. UNSTAMPED = UNKNOWN, and UNKNOWN
#   takes the `test` predicate: it is the narrower rule in both directions, so it
#   is the only one that cannot certify a wrong answer on a log whose shape it
#   does not know. See the branch itself for the per-marker reasoning.
#
#   What is deliberately NOT terminal for a `test` run, and why: a per-test
#   FAIL:/ERROR: marker, its traceback, and the per-MODULE failure aggregate.
#   All three are MID-RUN - the suite carries on to the next test and the next
#   module - and cmd_test appends the authoritative TEST_RESULT= line when the
#   run actually finishes. Returning failure at the first of them stops the wait
#   while odoo-bin is still working and hands the caller a verdict the run never
#   published; a caller that learns the wait does that goes back to hand-rolling
#   a poll loop, which is the behavior this mechanism exists to remove. They
#   still keep a completion marker from certifying SUCCESS (the _TEST_FAIL_RE
#   gate below), so the un-decided answer is the only thing they can produce.
#
#   "Initiating shutdown"/a bare process exit 0 remain named as progress/
#   heartbeat signals in agents/odoo-instance-ops.md's "Active-wait on long
#   builds" section, but are NOT independently sufficient for
#   BUILD_RESULT=success here. Markers are version-stable v8.0-v19.0 except
#   where the SSOT blocks above record an era split; the caller's own process
#   exit code stays authoritative - this is the in-log completion signal.
# ---------------------------------------------------------------------------
_scan_build_markers() {
    local logf="$1"
    # BUILD_PROGRESS is emitted FIRST and on EVERY path, terminal ones included,
    # so the caller's stall rule always has the same field to compare and never
    # has to work out which meaning BUILD_MARKER is carrying this time. It is
    # computed before any verdict branch precisely so no branch can turn it into
    # one. A missing log yields BOTH keys EMPTY - no evidence, not a stall.
    if [[ ! -f "$logf" ]]; then
        echo "BUILD_MARKER="
        echo "BUILD_PROGRESS="
        return 2
    fi
    echo "BUILD_PROGRESS=$(_build_progress "$logf")"

    # The VERB decides the terminal predicate, read from the log's own run-verb
    # stamp (_open_log) so this works in a process that knows nothing else about
    # the run.
    #
    # UNKNOWN verb (no stamp - a log written before the stamp existed, or one
    # this script never opened) resolves to the TEST predicate, which is the
    # NARROWER of the two in BOTH directions. This is a safety choice, not a
    # default-to-the-first-branch:
    #   * The install predicate certifies SUCCESS from "Modules loaded.". On a
    #     --test-enable log that line lands BEFORE the post-install suite starts,
    #     so applying it to an unknown log certifies a build whose tests have not
    #     run - a false GREEN, the one error class that must never be reachable.
    #   * The install predicate also rules FAILURE on a lone traceback, which on
    #     a test log is per-test/incidental evidence (SSOT above) - a false RED
    #     on a healthy run.
    #   * The test predicate can produce NEITHER error on an install log: such a
    #     log publishes no TEST_RESULT= line and no ran-marker, so it can never
    #     be certified success, and _BUILD_ABORT_RE stays terminal for every
    #     verb, so a genuine abort is still ruled failure. What it gives up is
    #     ruling a traceback-only install failure terminal; that degrades to "not
    #     decided", which the caller resolves as BLOCKED with the log preserved.
    #     Refusing to certify is the safe direction; a confident wrong verdict is
    #     not.
    # Inferring the verb from the log's own content was rejected: a test log
    # truncated after "Modules loaded." but before its first test line carries no
    # test evidence at all, so inference resolves it to `install` and re-opens
    # the false-GREEN path in exactly the state where it does damage.
    local verb series
    verb="$(_log_stamp_field "$logf" VERB)"
    series="$(_log_stamp_field "$logf" SERIES)"
    [[ -n "$verb" ]] || verb="test"

    if [[ "$verb" == "test" ]]; then
        # The run's OWN verdict line, appended to the log by cmd_test once
        # odoo-bin exited, outranks every other signal: it is the only line on a
        # test log that was computed AFTER the run finished. Echoing it is also
        # what puts TEST_RESULT within reach of a polling caller at all.
        local verdict
        verdict="$(grep -aE '^TEST_RESULT=' "$logf" 2>/dev/null | head -n 1 || true)"
        if [[ -n "$verdict" ]]; then
            echo "BUILD_MARKER=$verdict"
            printf '%s\n' "$verdict"
            # EVERY value _parse_test_result can assign gets its own arm. A
            # fallthrough here is what let `inconclusive` - the verdict that
            # exists precisely BECAUSE the run refused to claim a pass without
            # positive proof the suite ran - be relayed as a successful build:
            # the polling caller was told the module's tests passed while zero
            # tests had run. The default arm is therefore FAILURE, never
            # success: an unrecognized verdict means this scan is out of date
            # with the emitter, and a stale scanner may not certify anything
            # green. tests/test_verdict_paths_agree.py holds the structural
            # guard that a value added above without an arm here fails CI.
            case "${verdict#TEST_RESULT=}" in
                passed)       return 0 ;;
                failed)       return 1 ;;
                inconclusive) return 3 ;;
                *)            return 1 ;;
            esac
        fi
    fi

    # FAILURE - a marker that PROVES the build cannot deliver its own verdict,
    # anywhere in the log, even if an earlier line looked like progress. For a
    # build that runs no tests that is the whole _INSTALL_FAIL_RE set (SSOT,
    # shared with _install_confirmed, so the two agree by construction). For a
    # test build it is _BUILD_ABORT_RE only - the subset no individual failing
    # test can produce (see the marker SSOT above for the measurement) - and
    # _BUILD_ABORT_RE is itself part of _INSTALL_FAIL_RE, so anything ruled a
    # failure here is also a failure to _parse_test_result.
    local fail_re="$_INSTALL_FAIL_RE"
    [[ "$verb" == "test" ]] && fail_re="$_BUILD_ABORT_RE"
    local fail_line
    fail_line="$(grep -aE "$fail_re" "$logf" 2>/dev/null | head -n 1 || true)"
    if [[ -n "$fail_line" ]]; then
        echo "BUILD_MARKER=$fail_line"
        return 1
    fi

    if [[ "$verb" == "test" ]]; then
        # No verdict line yet. The era-correct POSITIVE "the suite ran" marker
        # (SSOT: _test_ran_re - v8.0-v13.0 runner trailer, v14.0-v19.0
        # per-database summary) shows the suite reached its end, but it may only
        # certify SUCCESS when nothing in the log contradicts it: the modern
        # wording carries the run's own failure counts, so reading the wording
        # and ignoring the numbers would certify a FAILING run as a successful
        # build. The gate is the exact union _parse_test_result rules `failed`
        # on - _TEST_FAIL_RE|_BUILD_ABORT_RE, the lone traceback deliberately
        # absent from BOTH (SSOT above) - which makes this branch "the verdict
        # that call would reach". Gating on the wider install union instead left
        # a healthy run that merely logged a traceback stuck at "not decided"
        # while the same log's own summary said nothing failed.
        # "Modules loaded." is NOT terminal here: Odoo logs it BEFORE the
        # post-install suite starts, so certifying there stops the wait while the
        # tests have not begun.
        # A SKIP marker (SSOT: _TEST_SKIP_RE) blocks this branch for the same
        # reason the failure union does. _parse_test_result rules a skip-bearing
        # run `inconclusive`, so certifying SUCCESS from the bare ran-marker
        # here would be this scan answering `success` about a log the run's own
        # verdict calls not-a-pass - the disagreement this whole marker SSOT
        # exists to make impossible. Withholding certification does NOT strand
        # the caller: the run appends its own TEST_RESULT= line moments later
        # and the branch above relays it. If the launching shell is reaped
        # before it can, the wait reports `timeout` and the caller reports
        # BLOCKED with the log preserved - "we never got a verdict" is the
        # honest answer there, and a green one is not.
        if ! grep -aqE "$_TEST_FAIL_RE|$_BUILD_ABORT_RE" "$logf" 2>/dev/null \
           && ! grep -aqiE "$_TEST_SKIP_RE" "$logf" 2>/dev/null; then
            local ran_line
            ran_line="$(grep -aE "$(_test_ran_re "$series")" "$logf" 2>/dev/null | head -n 1 || true)"
            if [[ -n "$ran_line" ]]; then
                echo "BUILD_MARKER=$ran_line"
                return 0
            fi
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

    # PROGRESS (never terminal, never success) - the NEWEST progress line the run
    # published (SSOT: _BUILD_PROGRESS_RE), so this evidence ADVANCES while a
    # suite runs instead of quoting one line that was written before the tests
    # even started. `loading <N> modules...` is the last resort only: Odoo logs
    # it once per registry load, so on its own it is frozen for the whole test
    # phase and cannot distinguish a working build from a dead one.
    # BUILD_PROGRESS above carries the countable form of the same fact; this line
    # is its human-readable companion, never an outcome.
    local prog_line=""
    prog_line="$(grep -aE "$_BUILD_PROGRESS_RE" "$logf" 2>/dev/null | tail -n 1 || true)"
    if [[ -z "$prog_line" && "$verb" == "test" ]]; then
        # For a test run "Modules loaded." means the modules are in and the
        # post-install suite has not finished - later than the registry-load
        # line, and still only progress.
        prog_line="$(grep -aF "$_INSTALL_SUCCESS_MARKER" "$logf" 2>/dev/null | head -n 1 || true)"
    fi
    if [[ -z "$prog_line" ]]; then
        prog_line="$(grep -aE 'loading [0-9]+ modules\.\.\.' "$logf" 2>/dev/null | tail -n 1 || true)"
    fi
    echo "BUILD_MARKER=$prog_line"
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

    # Any status OTHER than 2 is terminal and ends the poll loop below - so a
    # verdict added to _scan_build_markers is decided by construction and can
    # never leave a caller polling a finished run.
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

    # _scan_build_markers emits BOTH keys on every path, so the block below is
    # relayed verbatim: BUILD_MARKER= and BUILD_PROGRESS= are always present,
    # and a caller comparing two waits never has to guess whether a field was
    # dropped or genuinely empty.
    printf '%s\n' "$marker"
    case "$rc" in
        0) echo "BUILD_RESULT=success" ;;
        1) echo "BUILD_RESULT=failure" ;;
        3) echo "BUILD_RESULT=inconclusive"
           echo "! wait-log: the run FINISHED and published TEST_RESULT=inconclusive - it is over, so do not wait again, and it is not a pass; read $logf and its findings file" >&2 ;;
        *) echo "BUILD_RESULT=timeout"
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
    # BEFORE _open_log: a refusal must open no log and launch nothing. odoo_root is
    # DERIVED from the odoo-bin just located - that directory IS the checkout root,
    # which is what makes `import odoo` resolve for a source instance, and it is by
    # construction the same checkout this build is about to run.
    _preflight_db_auth "$arg_python" "${arg_db_host:-}" "${arg_db_user:-}" \
        "${arg_db_port:-}" "$(dirname "$odoo_bin")"

    local logf
    _open_log "$arg_db" init "${arg_version:-}"

    # arg_addons is SSOT-normalized (tolerates a stray legacy colon; every
    # real producer already emits pure comma) - see _addons_csv_from.
    local addons_csv
    addons_csv="$(_addons_csv_from "$arg_addons")"

    local DB_CONN_ARGS
    _build_db_conn_args

    # Deterministic completion contract (docs/reference/INSTANCE-LIFECYCLE-BUILD-CONTRACT.md
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
    # --stop-after-init is correct HERE by design: cmd_init is the BUILD
    # mechanism - it installs the module set and EXITS, it never listens.
    # 50-instance-spinup.sh is the sole LISTENING mechanism (P5.7) and installs
    # nothing (no -i/-u on its launch line), so an ISOLATED listening instance
    # (persist: exclusive-running) is TWO LEGS: this verb builds the database,
    # then that script launches the SAME database listening (the handoff
    # invariants live in agents/odoo-instance-ops.md operation 1).
    # persist: shared-running has no build leg here at all. Do NOT try to
    # make this verb long-running; add a new op instead if that is ever needed.
    # Completion is PROCESS EXIT (this call blocks until odoo-bin exits) - never
    # a log-tail wait; the log is consulted ONLY afterward, to CONFIRM the exit
    # actually installed something (see _install_confirmed).
    # Scoped subshell: `ulimit -Sv` applies only to this one odoo-bin
    # invocation and never leaks past it. --limit-memory-hard sits BEFORE
    # ${arg_extra} so a caller-supplied override in --extra still wins
    # (Odoo's arg parser takes the last occurrence).
    (
        # The escape-hatch credential is handed to libpq under its OWN variable,
        # for this launch only.
        # Odoo omits the password from its connection entirely unless db_password is
        # set, in which case libpq resolves PGPASSWORD itself - so exporting it here
        # is what makes a cluster that cannot be reconfigured reachable, and argv
        # (world-readable in `ps`) never carries it.
        [[ -n "${ODOO_PG_PASSWORD:-}" ]] && export PGPASSWORD="$ODOO_PG_PASSWORD"
        resource_limit_is_uncapped || ulimit -Sv "$_lim_kib" 2>/dev/null || true
        # Toolchain env for Odoo's own lint families, scoped to THIS launch the
        # same way PGPASSWORD above is (SSOT: scripts/lib/lint_toolchain.sh).
        # Without it `test_eslint` resolves whatever `eslint` PATH happens to
        # offer - on a stock Debian box the 2019 OS package, which exits 2 on a
        # config it cannot parse and FAILS the test with a message that reads
        # like a finding about the code while zero JS files were examined.
        lint_toolchain_export "$arg_python" "$addons_csv" "$arg_modules"
        lint_toolchain_diagnostics "$addons_csv"
        # Positive proof of the resolved tree (issue class: Odoo's own module-
        # loading log records only RELATIVE module paths, so a verifier can
        # never grep an absolute addons-path line to confirm which checkout
        # loaded - the ABSENCE of a wrong path is the only signal otherwise).
        # This line makes the RESOLVED addons-path greppable in the log itself.
        echo "allocator: ADDONS_PATH_USED=$addons_csv"
        # --unaccent is consumed ONLY by Odoo's database-CREATION path
        # (service/db.py _create_empty_database), and cli/server.py runs that
        # path for EVERY odoo-bin invocation naming a -d database that does not
        # exist yet - so whichever subcommand reaches a fresh DB first is its
        # creator. That is why init/update/test all carry the flag, not init
        # alone.
        # Without it a new DB gets pg_trgm but NOT unaccent, and the miss is
        # PERMANENT: nothing re-runs the creation path afterwards. Odoo then
        # probes the database at registry build (modules/db.py has_unaccent)
        # and silently DEGRADES - accent-insensitive search is dropped and the
        # trigram indexes that would have been built over unaccent() are not,
        # with no error raised and nothing in the log to grep for. Odoo's own
        # creation path also issues the ALTER FUNCTION unaccent(text) IMMUTABLE
        # those indexes require (has_unaccent returns INDEXABLE only for
        # provolatile='i'), so passing the flag is sufficient - no post-hoc SQL
        # belongs here.
        # Never fails a build: Odoo wraps its CREATE EXTENSION in try/except
        # psycopg2.Error and only logs a warning, so a cluster whose role may
        # not create extensions degrades instead of erroring (PG13+ marks
        # unaccent `trusted`, where a plain DB owner suffices; PG12 and older
        # need a superuser).
        # Stable `server` option across v8-v19 - only its help text changed (at
        # v10), never the flag - so unlike --dev=all this needs NO series gate.
        "$arg_python" "$odoo_bin" \
            -d "$arg_db" \
            -i "$arg_modules" \
            --addons-path "$addons_csv" \
            "${DB_CONN_ARGS[@]}" \
            --unaccent \
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
    # BEFORE _open_log: a refusal must open no log and launch nothing. odoo_root is
    # DERIVED from the odoo-bin just located - that directory IS the checkout root,
    # which is what makes `import odoo` resolve for a source instance, and it is by
    # construction the same checkout this build is about to run.
    _preflight_db_auth "$arg_python" "${arg_db_host:-}" "${arg_db_user:-}" \
        "${arg_db_port:-}" "$(dirname "$odoo_bin")"

    local logf
    _open_log "$arg_db" update "${arg_version:-}"

    # arg_addons is SSOT-normalized (tolerates a stray legacy colon; every
    # real producer already emits pure comma) - see _addons_csv_from.
    local addons_csv
    addons_csv="$(_addons_csv_from "$arg_addons")"

    local DB_CONN_ARGS
    _build_db_conn_args

    # Deterministic completion contract - identical to cmd_init (see its
    # comments above and docs/reference/INSTANCE-LIFECYCLE-BUILD-CONTRACT.md item 14):
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
        # The escape-hatch credential is handed to libpq under its OWN variable,
        # for this launch only.
        # Odoo omits the password from its connection entirely unless db_password is
        # set, in which case libpq resolves PGPASSWORD itself - so exporting it here
        # is what makes a cluster that cannot be reconfigured reachable, and argv
        # (world-readable in `ps`) never carries it.
        [[ -n "${ODOO_PG_PASSWORD:-}" ]] && export PGPASSWORD="$ODOO_PG_PASSWORD"
        resource_limit_is_uncapped || ulimit -Sv "$_lim_kib" 2>/dev/null || true
        # Toolchain env for Odoo's own lint families, scoped to THIS launch the
        # same way PGPASSWORD above is (SSOT: scripts/lib/lint_toolchain.sh).
        # Without it `test_eslint` resolves whatever `eslint` PATH happens to
        # offer - on a stock Debian box the 2019 OS package, which exits 2 on a
        # config it cannot parse and FAILS the test with a message that reads
        # like a finding about the code while zero JS files were examined.
        lint_toolchain_export "$arg_python" "$addons_csv" "$arg_modules"
        lint_toolchain_diagnostics "$addons_csv"
        # Positive proof of the resolved tree - see the identical comment in
        # cmd_init above.
        echo "allocator: ADDONS_PATH_USED=$addons_csv"
        # --unaccent - rationale in cmd_init above. Inert when the database
        # already exists (DatabaseExists short-circuits Odoo's creation path);
        # it earns its place when this subcommand is the first to name a
        # not-yet-existing database, which is the only moment unaccent can
        # still be installed.
        "$arg_python" "$odoo_bin" \
            -d "$arg_db" \
            -u "$arg_modules" \
            --addons-path "$addons_csv" \
            "${DB_CONN_ARGS[@]}" \
            --unaccent \
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
    # BEFORE _open_log: a refusal must open no log and launch nothing. odoo_root is
    # DERIVED from the odoo-bin just located - that directory IS the checkout root,
    # which is what makes `import odoo` resolve for a source instance, and it is by
    # construction the same checkout this build is about to run.
    _preflight_db_auth "$arg_python" "${arg_db_host:-}" "${arg_db_user:-}" \
        "${arg_db_port:-}" "$(dirname "$odoo_bin")"

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
        # The escape-hatch credential is handed to libpq under its OWN variable,
        # for this launch only.
        # Odoo omits the password from its connection entirely unless db_password is
        # set, in which case libpq resolves PGPASSWORD itself - so exporting it here
        # is what makes a cluster that cannot be reconfigured reachable, and argv
        # (world-readable in `ps`) never carries it.
        [[ -n "${ODOO_PG_PASSWORD:-}" ]] && export PGPASSWORD="$ODOO_PG_PASSWORD"
        resource_limit_is_uncapped || ulimit -Sv "$_lim_kib" 2>/dev/null || true
        # Toolchain env for Odoo's own lint families, scoped to THIS launch the
        # same way PGPASSWORD above is (SSOT: scripts/lib/lint_toolchain.sh).
        # Without it `test_eslint` resolves whatever `eslint` PATH happens to
        # offer - on a stock Debian box the 2019 OS package, which exits 2 on a
        # config it cannot parse and FAILS the test with a message that reads
        # like a finding about the code while zero JS files were examined.
        lint_toolchain_export "$arg_python" "$addons_csv" "$arg_modules"
        lint_toolchain_diagnostics "$addons_csv"
        # Positive proof of the resolved tree - see the identical comment in
        # cmd_init above.
        echo "allocator: ADDONS_PATH_USED=$addons_csv"
        # --unaccent - rationale in cmd_init above. Inert when the database
        # already exists (DatabaseExists short-circuits Odoo's creation path);
        # it earns its place when this subcommand is the first to name a
        # not-yet-existing database, which is the only moment unaccent can
        # still be installed.
        "$arg_python" "$odoo_bin" \
            -d "$arg_db" \
            "$mode_flag" "$arg_modules" \
            --addons-path "$addons_csv" \
            "${DB_CONN_ARGS[@]}" \
            --unaccent \
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
                echo "  Route the drop through 'allocator.py release <token> --run-id <id>' (race-free ownership check)," >&2
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
