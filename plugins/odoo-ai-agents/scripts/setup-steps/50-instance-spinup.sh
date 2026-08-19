#!/usr/bin/env bash
# 50-instance-spinup.sh - Start a declared Odoo instance and wait for HTTP 200.
#
# Reads an instance profile written by 40-instance-profile.sh from
# $ODOO_AI_HOME/instances.toml, generates a per-instance odoo.conf with the
# correct addons_path ordering under $ODOO_AI_HOME/conf/ (deterministic path,
# keyed <db_name>-<http-port> - see the conf block in cmd_apply for why it is
# NOT a temp file), launches Odoo (source via odoo-bin OR docker compose),
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
#              WHICH TREE gets served is resolved, never assumed - highest
#              precedence first: --addons-path <list> (the caller states the
#              tree), then the BOUND LEASE named by --alloc-token (its
#              `addons_path`, which is what an `allocator.py acquire
#              --addons-path-override` recorded), then the instances.toml
#              catalog row. The lease rung needs NO extra flag: a lease is
#              acquired against a worktree precisely so the launch serves that
#              worktree, and an override the caller has to remember to re-pass
#              is an override that gets forgotten. When --alloc-token names a
#              lease this run cannot read, or one whose addons_path names a real
#              tree that is not on this host, apply BLOCKS instead of falling
#              back to the catalog row - a loud refusal beats a silently wrong
#              tree, which is the one failure direction that still goes green.
#              (A lease row whose addons_path is not a directory list at all
#              states no tree, so the catalog row stands and the reported
#              SERVED_ADDONS_SOURCE says `catalog` - see _addons_path_verdict.)
#              --load <modules> forwards a server-wide module set into the
#              generated conf's `server_wide_modules` key (Odoo's --load dest,
#              comma-separated on every indexed series); omitted -> the key is
#              not written at all and Odoo's own default applies.
#              apply prints the resolution as machine-readable stdout facts -
#              SERVED_ADDONS_PATH / SERVED_ADDONS_SOURCE /
#              SERVED_SERVER_WIDE_MODULES - so a caller can verify the served
#              tree without parsing Odoo's own startup log.
#
# HARD RULES:
#   - Never writes a password into the generated conf. A local developer cluster is
#     reached with passwordless authentication (run /odoo-ai-agents:odoo-setup); a
#     cluster that cannot be reconfigured is reached with PGPASSWORD exported from
#     $ODOO_PG_PASSWORD for this launch only. No secret is written anywhere.
#   - Never launches until Odoo's OWN connection has been probed: `pg_isready`
#     answers whatever the credentials are, so only `odoo_db.py preflight` can
#     prove this launch will get past its first connection.
#   - The generated odoo.conf goes under the Tier-1 state root
#     ($ODOO_AI_HOME/conf/), never $ODOO_RC and never a project-committed or
#     default odoo.conf; no project files are mutated.
#   - No sudo. docker mode uses `docker compose` (must already be installed).
#
# CONFIG:
#   ODOO_AI_HOME       machine-global dir     ${ODOO_AI_HOME:-$HOME/.odoo-ai}
#   ODOO_AI_INSTANCES  full-path override for instances.toml
#   ODOO_BIN           path to odoo-bin (source mode). Auto-detected from
#                      the 'core' addons_path entry if unset.
#   ODOO_PG_PASSWORD   the escape hatch for a cluster that cannot be reconfigured
#                      (managed or remote). Exported to libpq as PGPASSWORD for the
#                      launch only, never written to a file.
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
# Postgres client dispatch (pg_run_client) + db_run_mode vocabulary SSOT.
# shellcheck source=../lib/pg_mode.sh
source "$SCRIPT_DIR/../lib/pg_mode.sh"
# Tier-1 run-artifact reclamation SSOT - odoo_ai_state_root (the ONE spelling of
# the state root) plus the single lease-guarded sweeper
# (prune_stale_run_artifacts), shared with 55-instance-ops.sh. This script is one
# of the sweeper's TWO named callers: cmd_apply sweeps $ODOO_AI_HOME/conf/ on
# every spin-up, just before it writes this instance's conf.
# shellcheck source=../lib/state_reclaim.sh
source "$SCRIPT_DIR/../lib/state_reclaim.sh"
INSTANCES_TOML="$(_resolve_instances)"
INSTANCES_IO="$SCRIPT_DIR/../lib/instances_io.py"
ODOO_DB_PY="$SCRIPT_DIR/../lib/odoo_db.py"
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
# script can bind the launched server pid onto that lease (see _bind_exclusive)
# AND so this script can read WHICH TREE that lease reserved (see
# _lease_addons_path / the served-tree resolution in cmd_apply).
ARG_ALLOC_TOKEN=""
# Explicit served-tree override: the addons_path this launch must serve, when
# the caller states it rather than leaving it to the lease/catalog. Highest
# precedence of the three rungs.
ARG_ADDONS_PATH=""
# Server-wide module set (Odoo's --load / `server_wide_modules`). Empty ->
# the conf key is not written and Odoo's own per-series default applies.
ARG_LOAD=""
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
        --addons-path)
            [[ $# -ge 2 ]] || { echo "$(basename "$0") --addons-path requires a value" >&2; exit 2; }
            ARG_ADDONS_PATH="$2"; shift 2 ;;
        --load)
            [[ $# -ge 2 ]] || { echo "$(basename "$0") --load requires a value" >&2; exit 2; }
            ARG_LOAD="$2"; shift 2 ;;
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
# _addons_csv - canonicalize an addons_path string onto the SSOT separator:
#   split with the SSOT splitter (_addons_path_to_array, resolve_instances.sh -
#   tolerates a stray legacy colon) and rejoin on $ADDONS_PATH_SEP. This is the
#   ONLY place THIS file joins an addons path; every consumer here calls it (the
#   identity token, the lease-vs-catalog comparison, the value written into the
#   generated conf), so the separator is never spelled twice inside one script.
#   (55-instance-ops.sh has its own twin, _addons_csv_from - the two scripts do
#   not source each other; the shared SSOT they both call is the splitter.)
# ---------------------------------------------------------------------------
_addons_csv() {
    local -a _ac_arr=()
    _addons_path_to_array _ac_arr "${1:-}"
    (IFS="$ADDONS_PATH_SEP"; echo "${_ac_arr[*]:-}")
}

# Odoo's `--load` flag and its `server_wide_modules` conf key take a COMMA-
# separated MODULE list on every indexed series (verified via OSM cli_help:
# `--load`, "Comma-separated list of server-wide modules", stable 8.0-19.0).
# Same delimiter CHARACTER as addons_path but a DIFFERENT fact - module names,
# not directories - so it carries its own name instead of borrowing
# $ADDONS_PATH_SEP from resolve_instances.sh.
SERVER_WIDE_MODULES_SEP=','

# ---------------------------------------------------------------------------
# _module_list_csv - normalize a caller-supplied server-wide module list: trim
#   each entry, drop empties, rejoin on $SERVER_WIDE_MODULES_SEP. So
#   `--load "mod_a, mod_b,"` reaches the conf as `mod_a,mod_b` instead of asking
#   Odoo to import a module named " mod_b". Prints the EMPTY string when the
#   argument names no module at all - cmd_apply BLOCKs on that rather than
#   writing a key that says nothing.
# ---------------------------------------------------------------------------
_module_list_csv() {
    local -a _mlc_in=() _mlc_out=()
    IFS="$SERVER_WIDE_MODULES_SEP" read -ra _mlc_in <<<"${1:-}"
    local m
    for m in "${_mlc_in[@]:-}"; do
        # Trim leading/trailing whitespace (bash-only, no external tool).
        m="${m#"${m%%[![:space:]]*}"}"
        m="${m%"${m##*[![:space:]]}"}"
        [[ -n "$m" ]] && _mlc_out+=("$m")
    done
    (IFS="$SERVER_WIDE_MODULES_SEP"; echo "${_mlc_out[*]:-}")
}

# ---------------------------------------------------------------------------
# _addons_path_verdict - is this addons_path SERVABLE? Prints one line:
#     ok                       every entry is an existing directory.
#     missing <entries...>      every entry that is absent is an ABSOLUTE path,
#                               so the value states a real tree that is not on
#                               this host (a deleted/moved worktree).
#     malformed <entries...>    at least one absent entry is not even an
#                               absolute path, so the value is not a path list
#                               at all - the signature of a producer that
#                               joined a STRING character-by-character rather
#                               than joining a list of directories.
#   The two failure verdicts are deliberately DISTINCT because they deserve
#   opposite treatment: a real-but-absent tree cannot be substituted (refuse),
#   while a value that is not a path list makes no claim about any tree at all
#   (fall back, loudly). Absoluteness is the discriminator because every
#   addons_path this toolkit produces is absolute (40-instance-profile.sh
#   records absolute checkout paths; allocator.py refuses an override entry
#   that is not an existing directory).
# ---------------------------------------------------------------------------
_addons_path_verdict() {
    local -a _apv=()
    _addons_path_to_array _apv "${1:-}"
    local p missing="" relative=0
    for p in "${_apv[@]:-}"; do
        [[ -n "$p" ]] || continue
        [[ -d "$p" ]] && continue
        missing+="${missing:+ }$p"
        [[ "$p" == /* ]] || relative=1
    done
    if [[ -z "$missing" ]]; then
        echo "ok"
        return 0
    fi
    if (( relative )); then
        echo "malformed $missing"
    else
        echo "missing $missing"
    fi
}

# ---------------------------------------------------------------------------
# _lease_addons_path - the addons_path RESERVED by an allocator lease.
#   $1 = allocator.py path, $2 = lease token. Prints that lease row's
#   `addons_path` (the allocator writes it comma-joined) and returns 0 when the
#   token names a row in the registry; prints nothing and returns NON-ZERO when
#   the registry cannot be read or holds no such token - which cmd_apply treats
#   as "the tree to serve is unresolved" and BLOCKS on, never as "use the
#   catalog row".
#
#   Read-only, and through the allocator's OWN command surface (`list
#   --show-tokens`) rather than by reaching into leases.json: the registry path
#   and schema stay the allocator's business, exactly as _register_shared /
#   _bind_exclusive already do for the write side.
# ---------------------------------------------------------------------------
_lease_addons_path() {
    local alloc="${1:-}" token="${2:-}" registry=""
    [[ -n "$alloc" && -f "$alloc" && -n "$token" ]] || return 1
    registry="$(python3 "$alloc" list --show-tokens 2>/dev/null)" || return 1
    [[ -n "$registry" ]] || return 1
    printf '%s' "$registry" | python3 -c '
import json, sys
try:
    registry = json.load(sys.stdin)
except Exception:
    sys.exit(1)
for lease in registry.get("leases") or []:
    if lease.get("token") == sys.argv[1]:
        print(lease.get("addons_path") or "")
        sys.exit(0)
sys.exit(1)
' "$token"
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
#
#   Separator-independence: the token is a hash of a CANONICALIZED addons_path
#   (see _identity_token), so the same real path list always hashes the same
#   regardless of which separator character produced the string - a future
#   wire-format change cannot recur this bug. A marker written before this fix
#   (when this function hashed the raw string with no canonicalization) is
#   still recognised via _identity_token_legacy, a one-time backward-compat
#   bridge _identity_ok checks after the canonical token - see both functions.
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
    # $1 = addons_path (any separator format). CANONICALIZED before hashing via
    # _addons_csv (this file's one join site - folds a stray legacy colon to the
    # SSOT comma and rejoins on $ADDONS_PATH_SEP): the SAME
    # real path list always hashes to the SAME token no matter which separator
    # character produced the string. This is what makes identity
    # separator-INDEPENDENT for good - a future producer flipping the wire
    # format again (comma<->colon) cannot change any instance's recorded
    # identity, because both forms canonicalize to one string before the hash
    # ever sees it. (A prior version of this function hashed $1 raw, with no
    # canonicalization, which is exactly how instances_io.py's _emit switching
    # from colon- to comma-joining silently changed every recorded token - see
    # _identity_token_legacy below for the one-time bridge that covers markers
    # already written under that raw-hash behavior.)
    local canon
    canon="$(_addons_csv "$1")"
    python3 -c '
import hashlib, sys
print(hashlib.sha256(sys.argv[1].encode()).hexdigest()[:16])
' "$canon"
}

_identity_token_legacy() {
    # $1 = addons_path (any separator format). Reproduces the PRE-FIX token: a
    # raw colon-joined string hashed WITHOUT canonicalization - exactly what
    # this script computed before instances_io.py's _emit silently switched
    # from colon- to comma-joining the value it writes as INST_ADDONS_PATH.
    # Used ONLY by _identity_ok, as a one-time backward-compat bridge so a
    # marker file written by an older checkout of this script is still
    # recognised as the SAME instance instead of a false COLLISION. Every
    # marker _write_identity_marker writes from now on carries the canonical
    # token above, so this legacy path fades out on its own as instances get
    # re-spun-up (same self-healing shape as the rest of this guard).
    local _idtok_paths legacy
    _addons_path_to_array _idtok_paths "$1"
    legacy="$(IFS=':'; echo "${_idtok_paths[*]}")"
    python3 -c '
import hashlib, sys
print(hashlib.sha256(sys.argv[1].encode()).hexdigest()[:16])
' "$legacy"
}

_write_identity_marker() {
    # $1 = port, $2 = expected (canonical) token, $3 = db_name (debug context only).
    local path
    path="$(_identity_marker_path "$1")" || return 0
    { printf '%s\n%s\n' "$2" "$3" >"$path"; } 2>/dev/null || true
}

_identity_ok() {
    # $1 = port, $2 = this invocation's expected (canonical) token, $3 = the
    # addons_path this invocation resolved (used ONLY to recompute the LEGACY
    # token below - see _identity_token_legacy). Returns 0 (pass) when no
    # marker is recorded yet (cannot disprove - see the docstring above), the
    # recorded token matches the canonical expected token, OR it matches the
    # legacy (pre-separator-fix) token for the SAME addons_path - a marker
    # written before this fix must not read as a false COLLISION for an
    # unchanged real instance. Returns 1 only on a CONFIRMED mismatch (a live
    # server on this port was launched by this guard for a DIFFERENT project).
    local port="$1" expected="$2" addons_path="$3" path have
    path="$(_identity_marker_path "$port")" || return 0
    [[ -f "$path" ]] || return 0
    have="$(head -n1 "$path" 2>/dev/null || true)"
    [[ -z "$have" || "$have" == "$expected" ]] && return 0
    [[ "$have" == "$(_identity_token_legacy "$addons_path")" ]]
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
    _identity_ok "$port" "$(_identity_token "${INST_ADDONS_PATH:-}")" "${INST_ADDONS_PATH:-}"
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
    # Gate db_name BEFORE anything else touches it (no file written, no lease
    # acquired, no database created past this point): it keys all THREE
    # artifact-filename families this script and state_reclaim.sh's sweep
    # share (the generated conf below, plus the log/.findings.md pair further
    # down), and nothing downstream validates it. validate_db_name is the ONE
    # gate (lib/state_reclaim.sh) - it prints its own "x BLOCKED: ..." refusal
    # to stderr, so this just propagates the failure.
    validate_db_name "$db_name" || return 1

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
    _alloc_diag_target() {
        # The ONE place this script resolves where an allocator call's STDERR is
        # kept - the Tier-1 log the SessionEnd hook appends to too
        # (hooks/session-end-gc.sh ALLOC_DIAG_BASENAME carries the full rationale,
        # incl. why `allocator-reclaimed.jsonl` does not already cover it and why
        # this stream must NOT be passed through to this script's own stderr: a
        # best-effort warning printed one line before `ok Odoo ... is up` reads as
        # a spin-up failure to the agent parsing this output).
        # /dev/null is the fallback on every failure rung, and the writability
        # probe is load-bearing: `mkdir -p` succeeds on an existing-but-unwritable
        # dir, and a redirect bash cannot open makes it skip the command outright -
        # which would trade a lost log line for a lost lease operation.
        local _diag_log
        _diag_log="$(odoo_ai_state_root)/logs/allocator-stderr.log"
        if mkdir -p "${_diag_log%/*}" 2>/dev/null && ( : >>"$_diag_log" ) 2>/dev/null; then
            printf '%s\n' "$_diag_log"
        else
            printf '%s\n' /dev/null
        fi
    }
    _register_shared() {
        # $1 = optional live server pid. The pid is recorded only when it is
        # still alive, so a concurrent loser (whose odoo-bin lost the port bind
        # and exited) cannot overwrite the live winner's pid. created_db is
        # always False on a shared lease, so gc never drops the declared DB.
        [[ -n "$alloc_py" && -f "$alloc_py" ]] || return 0
        local args=(acquire --series "${INST_SERIES:-}" --mode shared
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
        # This acquire runs the allocator's DESTRUCTIVE gc sweep as a side effect
        # (cmd_acquire -> _gc over the whole shared registry), so it is one of the
        # plugin's two largest reclaimers - and it used to discard the only
        # account of what it destroyed. STDOUT stays /dev/null (acquire's stdout
        # is the `eval $(allocator.py acquire ...)` PROTOCOL, and this call site
        # evals nothing); STDERR is APPENDED to the Tier-1 log the SessionEnd hook
        # writes too - see _alloc_diag_target above for where it goes and why.
        local _diag
        _diag="$(_alloc_diag_target)"
        python3 "$alloc_py" "${args[@]}" >/dev/null 2>>"$_diag" || true
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
        # A PARKED lease takes `resume`, not `bind`: resume is the ATOMIC
        # compare-and-set that also DELETES the park budget, so the revived
        # instance is judged by the owner-pid arms again instead of staying
        # governed by park_ttl_s (a live server whose only governor is a park
        # budget gets its database dropped under it when that budget lapses).
        # `resume` exits 3 - and ONLY 3 - for "this lease is not parked", which
        # is the ordinary first spin-up, so that one code is the branch back to
        # `bind`. Every OTHER non-zero is a real resume failure (the database
        # was dropped while parked, the pid is not corroborated as this lease's
        # server) and must NOT fall through: binding a pid onto a still-parked
        # lease is exactly the half-transitioned state resume exists to prevent.
        [[ -n "$alloc_py" && -f "$alloc_py" ]] || return 0
        [[ -n "${ARG_ALLOC_TOKEN:-}" ]] || return 0
        # `resume`'s STDERR is KEPT, not discarded: its refusals are the only
        # account of a lease that stayed PARKED while a server came up on its
        # port - a state whose budget can still lapse and drop that database
        # underneath the live server. Same target as _register_shared's.
        if [[ -n "${1:-}" ]] && kill -0 "$1" 2>/dev/null; then
            local _resume_rc=0 _diag
            _diag="$(_alloc_diag_target)"
            python3 "$alloc_py" resume "${ARG_ALLOC_TOKEN}" --pid "$1" >/dev/null 2>>"$_diag" \
                || _resume_rc=$?
            if [[ "$_resume_rc" -eq 3 ]]; then
                python3 "$alloc_py" bind "${ARG_ALLOC_TOKEN}" --pid "$1" >/dev/null 2>>"$_diag" || true
            elif [[ "$_resume_rc" -ne 0 ]]; then
                echo "x the allocator refused to resume this parked lease (exit $_resume_rc); the server is UP but the lease is still parked - see the allocator stderr log named by state-root-resolution.md" >&2
            fi
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

    # ---- WHICH TREE does this launch serve? ------------------------------
    # The catalog row is a STATIC declaration of the PRINCIPAL checkout. A
    # caller that acquired its lease with `allocator.py acquire
    # --addons-path-override <worktree list>` is serving a DIFFERENT tree, and
    # the LEASE is where that decision is recorded - so the lease outranks the
    # catalog here. Getting it wrong is silent in the one direction that
    # destroys the result: the server comes up, the port answers 200, and every
    # test run, QA acceptance pass and visual check goes GREEN against code
    # that is not the code under verification.
    #
    # Precedence, highest first:
    #   1. --addons-path <list>  - the caller states the tree explicitly.
    #   2. the BOUND LEASE named by --alloc-token (its `addons_path`). No extra
    #      flag: a lease acquired against a worktree exists precisely so the
    #      launch serves that worktree, and an override the caller must
    #      remember to re-pass is an override that gets forgotten.
    #   3. the catalog row (INST_ADDONS_PATH) - the declared/shared default;
    #      with no lease and no argument this is byte-for-byte the old behavior.
    # The resolved value REPLACES INST_ADDONS_PATH, so every downstream
    # consumer - the instance-identity token, _find_odoo_bin, the generated
    # conf - reads ONE resolved value and there is no second spelling to drift.
    local _catalog_addons _served_addons _served_from="catalog"
    _catalog_addons="$(_addons_csv "${INST_ADDONS_PATH:-}")"
    _served_addons="$_catalog_addons"
    if [[ -n "${ARG_ADDONS_PATH:-}" ]]; then
        # An explicitly stated tree is checked before anything is launched: a
        # mistyped path would otherwise start a server that finds no module
        # there and reports the resulting emptiness as a code problem. Same rule
        # allocator.py applies to --addons-path-override, applied at the other
        # end of the same handoff.
        local _arg_verdict
        _arg_verdict="$(_addons_path_verdict "$ARG_ADDONS_PATH")"
        if [[ "$_arg_verdict" != "ok" ]]; then
            echo "" >&2
            echo "x BLOCKED: --addons-path names entries that are not existing directories." >&2
            echo "  Not found: ${_arg_verdict#* }" >&2
            echo "  Given: ${ARG_ADDONS_PATH}" >&2
            echo "  NOTHING was launched. Serving a tree that is not there produces a server" >&2
            echo "  with no modules under it, which reads as broken code rather than as a" >&2
            echo "  mistyped path." >&2
            return 1
        fi
        _served_addons="$ARG_ADDONS_PATH"
        _served_from="argument"
    elif [[ -n "${ARG_ALLOC_TOKEN:-}" ]]; then
        local _lease_addons="" _lease_rc=0
        _lease_addons="$(_lease_addons_path "$alloc_py" "$ARG_ALLOC_TOKEN")" || _lease_rc=$?
        if (( _lease_rc != 0 )); then
            # The caller HOLDS a lease but this run cannot read which tree it
            # reserved, so the two candidate trees cannot be told apart. A loud
            # refusal is strictly better than a quiet wrong tree: nothing is
            # launched, no conf is written, and the caller learns immediately.
            echo "" >&2
            echo "x BLOCKED: --alloc-token names a lease this run cannot read, so WHICH TREE" >&2
            echo "  to serve is unresolved. NOTHING was launched." >&2
            echo "  Token: ${ARG_ALLOC_TOKEN}" >&2
            echo "  Probed with: python3 '${alloc_py}' list --show-tokens" >&2
            echo "  A lease acquired with --addons-path-override reserves a DIFFERENT tree" >&2
            echo "  than the instances.toml catalog row ('${_catalog_addons}'). Serving the" >&2
            echo "  catalog row here would launch the WRONG checkout while every test, QA" >&2
            echo "  pass and visual check still reported green - so this refuses instead of" >&2
            echo "  guessing. Fix: re-acquire the lease and pass the token it printed, keep" >&2
            echo "  \$ODOO_AI_HOME pointing at the state root that acquire used, or state the" >&2
            echo "  tree explicitly with --addons-path <list>." >&2
            return 1
        fi
        # A lease row that records NO addons_path (a pre-override or hand-written
        # row) makes no statement about the tree - the catalog row stands, and
        # SERVED_ADDONS_SOURCE below says so out loud.
        if [[ -n "$_lease_addons" ]]; then
            _lease_addons="$(_addons_csv "$_lease_addons")"
            local _lease_verdict="ok"
            # A lease that AGREES with the catalog row needs no check: the two
            # rungs name the same tree, so honouring the lease cannot change
            # what is served, and a check here would newly refuse catalogs that
            # have always been allowed to name a not-yet-created directory.
            if [[ "$_lease_addons" != "$_catalog_addons" ]]; then
                _lease_verdict="$(_addons_path_verdict "$_lease_addons")"
            fi
            case "$_lease_verdict" in
                ok)
                    _served_addons="$_lease_addons"
                    _served_from="lease"
                    ;;
                missing*)
                    # The lease names a REAL tree that is not on this host. The
                    # catalog row is NOT a substitute for it - that substitution
                    # is exactly the wrong-tree green this resolution exists to
                    # end - so refuse before launching anything.
                    echo "" >&2
                    echo "x BLOCKED: the lease reserves an addons_path that is not on this host, so" >&2
                    echo "  WHICH TREE to serve is unresolved. NOTHING was launched." >&2
                    echo "  Lease addons_path:   ${_lease_addons}" >&2
                    echo "  Not found:           ${_lease_verdict#* }" >&2
                    echo "  Catalog addons_path: ${_catalog_addons}" >&2
                    echo "  The catalog row is NOT a substitute: serving it would launch a" >&2
                    echo "  DIFFERENT checkout than the one this lease was acquired for, and every" >&2
                    echo "  test, QA pass and visual check would still report green. Restore the" >&2
                    echo "  tree the lease names, re-acquire the lease against a tree that exists," >&2
                    echo "  or state the tree explicitly with --addons-path <list>." >&2
                    return 1
                    ;;
                *)
                    # malformed: the row is not a path list at all, so it makes
                    # no claim about any tree and cannot be served. The catalog
                    # row stands - and SERVED_ADDONS_SOURCE below reports
                    # `catalog`, so no caller is told it got the lease's tree.
                    echo "" >&2
                    echo "  Warning: the lease's recorded addons_path is not a directory list, so it" >&2
                    echo "  states no tree to serve; SERVING THE CATALOG ROW instead." >&2
                    echo "  Lease addons_path:   ${_lease_addons}" >&2
                    echo "  Not even paths:      ${_lease_verdict#* }" >&2
                    echo "  Catalog addons_path: ${_catalog_addons}" >&2
                    echo "  Verify the served tree from SERVED_ADDONS_PATH/SERVED_ADDONS_SOURCE" >&2
                    echo "  below before trusting this instance, and pass --addons-path <list> to" >&2
                    echo "  state the tree explicitly." >&2
                    ;;
            esac
        fi
    fi
    INST_ADDONS_PATH="$(_addons_csv "$_served_addons")"

    # Server-wide modules (Odoo's --load / `server_wide_modules`). Normalized
    # once here; the conf line below is the only writer.
    local _served_load=""
    if [[ -n "${ARG_LOAD:-}" ]]; then
        _served_load="$(_module_list_csv "$ARG_LOAD")"
        if [[ -z "$_served_load" ]]; then
            echo "" >&2
            echo "x BLOCKED: --load names no module ('${ARG_LOAD}')." >&2
            echo "  Refusing to launch with an EMPTY server-wide module set: a caller that" >&2
            echo "  resolved a server-wide module and then silently got Odoo's default is" >&2
            echo "  exactly the drop this passthrough exists to prevent. Pass a" >&2
            echo "  comma-separated module list, or omit --load to accept Odoo's default." >&2
            return 1
        fi
    fi

    # run_mode=docker cannot honour EITHER of the two facts above: the conf this
    # script generates is only handed to odoo-bin on the source path, so a
    # compose-launched server serves whatever its own compose file mounts and
    # loads. Claiming a served tree it does not serve would re-create the same
    # silent wrong-tree green, so refuse before `docker compose up`.
    if [[ "${INST_RUN_MODE:-source}" == "docker" ]] \
            && { [[ "$INST_ADDONS_PATH" != "$_catalog_addons" ]] || [[ -n "$_served_load" ]]; }; then
        echo "" >&2
        echo "x BLOCKED: run_mode=docker cannot honour a served-tree override." >&2
        echo "  Resolved addons_path ($_served_from): ${INST_ADDONS_PATH}" >&2
        echo "  Catalog addons_path:                  ${_catalog_addons}" >&2
        echo "  server_wide_modules requested:        ${_served_load:-<none>}" >&2
        echo "  This step only generates an odoo.conf for the SOURCE run mode; a" >&2
        echo "  compose-launched server serves whatever its compose file mounts, so" >&2
        echo "  honouring the override here is impossible and reporting it would be a" >&2
        echo "  lie. Declare the tree in the compose file, or run this instance in" >&2
        echo "  run_mode=source." >&2
        return 1
    fi

    # Make the served tree OBSERVABLE. Same stdout KEY=value channel this
    # command already uses for LOG_PATH, so a caller verifies what was served
    # without parsing Odoo's own `addons paths: [...]` startup log line.
    # Emitted BEFORE the "already up" pre-check below, so it is present on every
    # successful path - attach as well as fresh launch. An EMPTY
    # SERVED_SERVER_WIDE_MODULES means no key is written and Odoo's own
    # per-series default applies (nothing is fabricated here).
    echo "SERVED_ADDONS_PATH=${INST_ADDONS_PATH}"
    echo "SERVED_ADDONS_SOURCE=${_served_from}"
    echo "SERVED_SERVER_WIDE_MODULES=${_served_load}"

    local _last_ready_status="" _last_ready_path=""
    # Instance-identity token this invocation EXPECTS to see recorded on
    # $port (see the guard block above _probe_ready_fallback). Computed once
    # here and reused both by the "already up" pre-check below and by the
    # marker write after a fresh launch succeeds.
    local _id_expected
    _id_expected="$(_identity_token "${INST_ADDONS_PATH:-}")"
    if _probe_ready "$port"; then
        if _identity_ok "$port" "$_id_expected" "${INST_ADDONS_PATH:-}"; then
            [[ "$ARG_EXCLUSIVE" != "1" ]] && _register_shared
            echo "ok Instance ${INST_SERIES} already up at http://localhost:$port$_last_ready_path"
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

    # Tracked so a poll timeout can kill the orphaned process instead of leaking
    # a port-holding Odoo. The conf itself needs no teardown: it lives at a
    # deterministic path under the Tier-1 state root ($ODOO_AI_HOME/conf/), keyed
    # by this instance's db_name + http port, so the next attempt overwrites it
    # rather than adding to a pile.
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
            _ver_major="${INST_SERIES%%.*}"
            local _port_key
            if [[ -n "$ARG_PORT_KEY" ]]; then
                # Agent-resolved conf key from OSM cli_help (P5.6) - the
                # persist: exclusive-running caller ALWAYS passes this, so the
                # local arithmetic below never runs for that path.
                _port_key="$ARG_PORT_KEY"
            else
                # FALLBACK for the shared/declared spin-up path only (no
                # --port-key override): v8/9/10 use xmlrpc_port; v11+ renamed
                # it to http_port. Derive from INST_SERIES (the full series
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

            # ---- PREFLIGHT: PostgreSQL, per declared surface -----------------
            # TWO rungs with DIFFERENT authority, and the difference is the whole
            # point. pg_isready reports a cluster as accepting connections whatever
            # the credentials are, so it can prove UNREACHABLE and can never prove
            # that this launch will work. The connection Odoo itself opens is the
            # only rung that answers the question the launch depends on, so it runs
            # ALWAYS when a python is declared - never as an `elif` shadowed by a
            # cheaper rung that cannot see the failure.
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
            local _pg_probe="" _pg_rc=0
            # Rung 1, cheap and BOUNDED (a preflight must never outlive the launch
            # it gates). Dispatched on the DECLARED db_run_mode (lib/pg_mode.sh):
            # `native` or an UNDECLARED surface (nothing recorded yet, so a locally
            # installed client is exactly the pre-declaration behavior), else the
            # declared container. NOT for `tcp-only`: that declaration states this
            # cluster has no client surface, and a client that answers for a
            # DIFFERENT cluster is the wrong-cluster hazard.
            # pg_isready is not one of pg_mode.sh's PG_MODE_NATIVE_BINS, so a
            # native host may still lack it; skipping is then mandatory, because a
            # missing binary must NEVER be reported as a down cluster.
            if [[ "${INST_DB_RUN_MODE:-}" == "native" || -z "${INST_DB_RUN_MODE:-}" ]] \
                    && command -v pg_isready >/dev/null 2>&1; then
                _pg_probe="pg_isready -h $db_host -U $db_user -d $db_name"
                pg_bounded_run "$PG_MODE_PROBE_TIMEOUT" \
                    pg_isready -h "$db_host" "${_pgr_port_args[@]}" -U "$db_user" \
                    -d "$db_name" -q 2>/dev/null || _pg_rc=$?
            elif [[ "${INST_DB_RUN_MODE:-}" == "docker" && -n "${INST_DB_CONTAINER:-}" ]] \
                    && command -v docker >/dev/null 2>&1; then
                _pg_probe="pg_isready in container ${INST_DB_CONTAINER}"
                pg_bounded_run "$PG_MODE_PROBE_TIMEOUT" \
                    pg_run_client docker "${INST_DB_CONTAINER}" "$db_host" "$db_user" \
                    "$db_port" pg_isready -d "$db_name" -q >/dev/null 2>&1 || _pg_rc=$?
            fi
            # 124 = the bound elapsed, 125 = the bound itself could not be applied
            # (pg_mode.sh's contract). Neither says anything about the cluster, so
            # neither may become a verdict - the same rule 05-prereq-check.sh's
            # `_pg_probe_declared` applies on all of its rungs.
            if [[ "$_pg_rc" -eq 124 || "$_pg_rc" -eq 125 ]]; then
                echo "  Warning: PostgreSQL was NOT probed - the probe ($_pg_probe) did" >&2
                echo "  not answer (exit $_pg_rc). This is NOT evidence that the cluster is" >&2
                echo "  down." >&2
                _pg_probe=""
                _pg_rc=0
            fi
            if [[ -n "$_pg_probe" && "$_pg_rc" -ne 0 ]]; then
                echo "" >&2
                echo "x PREFLIGHT FAILED: PostgreSQL is not reachable." >&2
                echo "  $_pg_probe reported failure (exit $_pg_rc)." >&2
                echo "  Odoo will not start until the database is reachable. Fix:" >&2
                echo "    - Start / check your PostgreSQL service." >&2
                echo "    - Verify db_host/db_user/db_name/db_port in instances.toml." >&2
                echo "    - If Postgres runs in a container, start it and re-run" >&2
                echo "      '45-venv.sh record-env --series ${INST_SERIES}' to re-derive db_container." >&2
                return 1
            fi
            [[ -z "$_pg_probe" ]] || \
                echo "  ok PostgreSQL is accepting connections ($_pg_probe)"

            # Rung 2, ALWAYS RUN when a python is declared: the connection Odoo
            # itself opens, through Odoo's own resolution. This is the route the
            # launch takes, so it is the only rung whose green means anything - and
            # the only one that can see an authentication refusal at all. It needs
            # no client binary and no privilege. odoo_db.py OWNS the verdict text;
            # its stderr is forwarded verbatim rather than re-worded here.
            if [[ -n "${INST_PYTHON:-}" && -f "$ODOO_DB_PY" ]]; then
                local -a _pf=("$ODOO_DB_PY" preflight
                    --db-host "$db_host" --db-user "$db_user")
                [[ -n "${INST_ODOO_ROOT:-}" ]] && _pf+=(--odoo-root "${INST_ODOO_ROOT}")
                [[ -n "$db_port" ]] && _pf+=(--db-port "$db_port")
                local _pf_rc=0
                pg_bounded_run "$PG_MODE_PROBE_TIMEOUT" \
                    "${INST_PYTHON}" "${_pf[@]}" >/dev/null || _pf_rc=$?
                case "$_pf_rc" in
                    0) echo "  ok Odoo can authenticate to PostgreSQL" ;;
                    8|9)
                        echo "" >&2
                        echo "x PREFLIGHT FAILED: see the refusal above. NOTHING was launched." >&2
                        return 1 ;;
                    *)
                        # 10 = this venv cannot import odoo; 124/125 = no answer; 1 =
                        # undeterminable. None is a cluster fact, so none blocks the
                        # launch - and none is reported as a green verdict either.
                        # The RUNG is named, so a cut-off probe is distinguishable
                        # from a ladder that never reached one (the branch below).
                        echo "  Warning: odoo_db.py preflight was NOT probed (exit $_pf_rc)." >&2
                        echo "  Run '45-venv.sh record-env --series ${INST_SERIES}' to declare" >&2
                        echo "  odoo_root and db_run_mode, then retry." >&2 ;;
                esac
            else
                echo "  Warning: Odoo's own connection was NOT probed - this instance" >&2
                echo "  declares no python. Run '45-venv.sh record-env --series" >&2
                echo "  ${INST_SERIES}' to declare it." >&2
            fi

            # The conf is DETERMINISTIC, keyed by the instance identity the
            # allocator already guarantees is exclusive: db_name + http port
            # (both resolved from the lease above). `-c "$conf"` keeps this file
            # open for the server's whole lifetime, so it can never be deleted
            # after launch - which is why a per-invocation mktemp name had no
            # owner on the success path and accumulated one file per spin-up
            # forever. Keying the file by the RESOURCE rather than by the
            # INVOCATION makes every re-spin of the same instance overwrite in
            # place, so the set of conf files is bounded by the set of declared
            # instances.
            local _conf_dir
            _conf_dir="$(odoo_ai_state_root)/conf"
            mkdir -p "$_conf_dir"
            prune_stale_run_artifacts "$_conf_dir" '*.conf'
            conf="$_conf_dir/${db_name}-${port}.conf"
            {
                echo "[options]"
                # The tree this launch SERVES: resolved once above (argument >
                # bound lease > catalog row) and already canonicalized onto the
                # SSOT separator by _addons_csv - no conversion here, and no
                # second re-derivation from the catalog that could disagree with
                # the SERVED_ADDONS_PATH fact printed above.
                echo "addons_path = ${INST_ADDONS_PATH:-}"
                # server_wide_modules is Odoo's --load dest (comma-separated on
                # every indexed series). Written ONLY when the caller passed
                # --load; omitted otherwise so Odoo's own per-series default
                # applies rather than a default invented here.
                if [[ -n "$_served_load" ]]; then
                    echo "server_wide_modules = $_served_load"
                fi
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
                # unaccent is a database-CREATION option, not a runtime one:
                # cli/server.py runs Odoo's _create_empty_database for every
                # launch naming a -d database that does not exist yet, so this
                # listener is the creator whenever it is the first thing to
                # touch a declared-but-not-yet-built DB. Written here so that
                # path yields the SAME database as 55-instance-ops.sh's build
                # path - a DB created without unaccent can never be repaired by
                # a later launch, because nothing re-runs the creation path.
                # No runtime effect by design: from v8 to v19 Odoo decides
                # whether to USE unaccent by probing the database
                # (modules/db.py has_unaccent), never by reading this key.
                echo "unaccent = True"
                # NO db_password line, deliberately: `-c "$conf"` keeps this file
                # alive for the server's whole lifetime, so a credential written
                # here outlives every successful spin-up with no owner and no
                # cleanup. Odoo omits the password from its connection entirely
                # when db_password is unset, which is exactly what lets libpq
                # resolve PGPASSWORD from the launch environment instead (exported
                # immediately before setsid below). Nothing is written, so there is
                # nothing to clean up.
            } >"$conf"
            # --dev=all was introduced as a string-valued flag in v10; v9 has a
            # boolean --dev only (no =all), and v8 has no --dev at all.
            # Gate: only append --dev=all for major >= 10.
            local _dev_flag=""
            if [[ "$_ver_major" =~ ^[0-9]+$ ]] && (( _ver_major >= 10 )); then
                _dev_flag="--dev=all"
            fi

            echo "  Generated conf: $conf"
            echo "  Launching: $py '$bin' -c '$conf' -d '$db_name' ${_dev_flag}"
            # Run in background so we can poll. Logs to the named path below.
            # Capture the PID directly (no subshell `( )`, which would hide it)
            # so a poll timeout can terminate the orphaned process.
            local logf _logs_dir _db_slug _ts
            # Write log to a stable, named path so a calling agent can capture it
            # across invocations.
            # Dir: <Tier-1 state root>/logs/ - resolved by odoo_ai_state_root
            #   (scripts/lib/state_reclaim.sh), the ONE place that expression is
            #   spelled. It used to be re-derived here AND twice in
            #   55-instance-ops.sh; both now call the resolver so the three can
            #   never drift.
            # File: <db>-<UTC-timestamp>.log (e.g. odoo_test-20260620T153012Z.log)
            _logs_dir="$(odoo_ai_state_root)/logs"
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
            # The escape-hatch credential is handed to libpq under its OWN variable,
            # for this launch only: Odoo passes no password to psycopg2 when
            # db_password is unset, so libpq resolves PGPASSWORD itself. A local
            # developer cluster needs none of this - passwordless authentication
            # covers it.
            [[ -n "${ODOO_PG_PASSWORD:-}" ]] && export PGPASSWORD="$ODOO_PG_PASSWORD"
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
        echo "ok Odoo ${INST_SERIES} is up: http://localhost:$port/web/login"
        return 0
    fi

    # Poll timed out - tear down what we started so we leave no orphan. The
    # server ran under setsid (its own process group), so stop the WHOLE group
    # (master + workers + gevent/cron + --dev watchdog) with SIGTERM -> bounded
    # wait -> group SIGKILL - not the old bare `kill <pid>` that left children
    # running. For an exclusive lease the pid is already bound (above), so even
    # if this local stop is interrupted, allocator.py release/gc can still reap.
    #
    # The conf is deliberately NOT removed here. The leak this branch used to
    # half-cover was caused by branch-asymmetric ownership - a per-invocation
    # name that only this exit path ever deleted - and the fix removes that whole
    # class by keying the file on the resource instead. The file now sitting at
    # $ODOO_AI_HOME/conf/<db>-<port>.conf is byte-identical to what the next
    # attempt writes, so deleting it buys no space and destroys the failed
    # launch's exact config as evidence. prune_stale_run_artifacts reclaims it
    # once the lease is gone.
    echo "x Odoo did not become ready. Check the launch log above." >&2
    if [[ "$run_mode" == "source" ]]; then
        if [[ -n "$odoo_pid" ]]; then
            echo "  Stopping background Odoo process group (leader pid $odoo_pid)" >&2
            _stop_group_local "$odoo_pid"
        fi
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
