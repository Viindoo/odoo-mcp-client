#!/usr/bin/env bash
# state_reclaim.sh - Source-only helper: the ONE reclamation mechanism for
# Tier-1 run artifacts under $ODOO_AI_HOME (logs and generated instance confs).
#
# Why this file exists: the sweeper, its retention bound and its lease-registry
# reachability guard used to live inside 55-instance-ops.sh, where
# 50-instance-spinup.sh could not reach them (neither script sources the other),
# and the state-root expression was re-spelled in both. That is how a second
# artifact family - the generated odoo.conf - ended up with no reclamation at
# all. Moving the mechanism into a lib gives it TWO named callers instead of
# one, and collapses the duplicated root expression into one resolver.
#
# There is deliberately ONE sweeper, ONE retention bound and ONE lease guard
# here. A second, parallel cleanup keyed on bare mtime is exactly what this file
# exists to prevent: an artifact whose instance is still leased must survive
# regardless of its age (see _leased_db_names below), so age alone is never a
# sufficient reason to unlink.
#
# Tier-1 placement: both swept families (`logs/`, `conf/`) are flat under
# $ODOO_AI_HOME, never namespaced per project/worktree - a conf keyed by
# (db_name, http port) is host-level state for the same reason `runtime/` is.
# SSOT for the tier tables: snippets/state-root-resolution.md.
#
# Source-only: defines functions + no top-level side effects apart from the
# retention constant. Matches the sibling libs' idiom (resource_limits.sh,
# pg_mode.sh): unprefixed names are the public API, `_`-prefixed names are
# internal.
#
# Public API:
#   odoo_ai_state_root                        -> prints the Tier-1 state root
#   validate_db_name <name>                   -> gate a db_name BEFORE it keys
#                                                any of the three artifact
#                                                families below; refuses
#                                                (prints to stderr, returns 1)
#                                                rather than sanitizing
#   prune_stale_run_artifacts <dir> <glob>... -> sweep one dir, lease-guarded
#   _prune_stale_logs <logs-dir>              -> the log-family wrapper (kept as
#                                                a named alias for the existing
#                                                call site in 55-instance-ops.sh)

# ---------------------------------------------------------------------------
# odoo_ai_state_root - the Tier-1 flat state root, printed on stdout.
#
#   ODOO_AI_HOME IS the .odoo-ai dir (allocator semantic); `.odoo-ai` is
#   appended ONLY in the HOME fallback so the path stays consistent with
#   allocator.py _home(), which returns ODOO_AI_HOME directly. This is the ONE
#   place this expression is spelled for the setup steps - 50-instance-spinup.sh
#   and 55-instance-ops.sh both call this instead of re-deriving it, so the two
#   can never drift apart.
#
#   The `${HOME:-/tmp}` inner default is a path-resolution last resort for a
#   HOME-less environment (it writes nothing by itself), and is the only
#   sanctioned mention of that path in this plugin's shell.
# ---------------------------------------------------------------------------
odoo_ai_state_root() {
    printf '%s\n' "${ODOO_AI_HOME:-${HOME:-/tmp}/.odoo-ai}"
}

# ---------------------------------------------------------------------------
# _DB_NAME_RE - the ONE spelling of the accepted db_name character class.
#   It MIRRORS Odoo's own database-manager gate rather than inventing (or
#   near-copying) a class of its own: addons/web/controllers/database.py
#   DBNAME_PATTERN is the SOURCE of this rule, verified unchanged across
#   v9-v19 - read the reasoning there, and copy any future change from there
#   rather than re-deriving one here. Shape: the FIRST character must be
#   alphanumeric, every later character may also be underscore, hyphen or
#   dot, and a name under two characters is refused. (v8 ships no such gate -
#   createdb-through-Odoo there accepts whatever a quoted Postgres identifier
#   accepts - so v8 is, if anything, MORE permissive than this class, never
#   less.) This is the SSOT both validate_db_name and
#   prune_stale_run_artifacts read; do not re-spell the class anywhere else.
#
#   Why exactly this class: db_name comes from a CLI arg, instances.toml, or
#   the literal default "odoo" (50-instance-spinup.sh, where it is resolved)
#   - operator-supplied config, not attacker-controlled input - but nothing
#   downstream validates it, and it keys THREE artifact-filename families
#   (<db>-<UTC-ts>.log, <db>-<UTC-ts>.findings.md, <db>-<port>.conf, all
#   `<db>-<discriminator>` with the db name being everything before the LAST
#   hyphen in the basename - see prune_stale_run_artifacts below). A hyphen
#   or an underscore inside db_name is therefore always SAFE - the split is
#   on the LAST hyphen, so any number of internal hyphens/underscores still
#   round-trips - and both must stay accepted or every existing instance
#   using one would break. A dot is accepted for the same reason Odoo accepts
#   one, and it is never the sweep's split character either. What Odoo's
#   pattern refuses, this gate refuses too - a leading '-', '.' or '_', and
#   any one-character name - because a name that clears this gate and then
#   fails at database creation is a gate that only moved the failure later.
#   Everything else is refused, in particular:
#     '/'      - makes a `<conf_dir>/<db_name>-<port>.conf` path escape
#                conf_dir entirely (a nested or `..`-relative path). The
#                sweep only ever looks `-maxdepth 1` inside conf_dir, so an
#                artifact that lands outside it is invisible to the sweep
#                forever - permanently and unreclaimably leaked, the exact
#                class of leak this file exists to close.
#     newline  - `prune_stale_run_artifacts` recovers db_name from a real
#                filename with a LINE-oriented `grep -Fxq`; a db_name
#                carrying an embedded newline splits that fixed-string
#                pattern into multiple OR'd whole-line alternatives, so the
#                match against the lease list is no longer a match against
#                the FULL name - it can miss a name that IS leased and let
#                the sweep unlink a live instance's open conf.
#     space / shell-glob chars (`*?[]` etc.) / anything else - no artifact
#                family needs them, and each is one more way a downstream
#                consumer (a glob, a shell word-split, a URL, an ini value)
#                could misparse the name. Reject rather than guess which of
#                those a given caller can tolerate.
# ---------------------------------------------------------------------------
_DB_NAME_RE='^[a-zA-Z0-9][a-zA-Z0-9_.-]+$'

# ---------------------------------------------------------------------------
# validate_db_name <name> - the ONE gate for db_name before it becomes part
#   of any of the three artifact-filename families this file owns. Prints
#   nothing and returns 0 on an acceptable name. On refusal it prints a
#   multi-line explanation to stderr - matching 50-instance-spinup.sh's
#   existing "x BLOCKED: ..." refusal idiom (see its --exclusive and
#   --gevent-port gates) rather than inventing a new exit shape - and
#   returns 1; the caller must return/exit immediately, before any file is
#   written, any lease acquired, or any database created.
#
#   REJECTS, never sanitizes/slugs: slugging db_name to fit the class would
#   make the artifact filename diverge from the REAL database name, and two
#   distinct database names can slug to the SAME filename (e.g. a naive
#   '/' -> '_' mapping collapses "a/b" and "a_b" onto one conf path) - the
#   sweep would then delete one instance's artifact while attributing it to
#   the other, or a live launch would silently overwrite a different live
#   instance's conf. Trading an unreclaimable leak for a silent
#   cross-instance collision is a regression, not a fix, so an unusable name
#   is refused outright and the caller must supply a different one.
# ---------------------------------------------------------------------------
validate_db_name() {
    local name="${1:-}"
    if [[ -z "$name" ]]; then
        echo "" >&2
        echo "x BLOCKED: db_name is empty." >&2
        echo "  Refusing to key a conf/log/findings filename on an empty name -" >&2
        echo "  set db_name (--db-name, or db_name in instances.toml)." >&2
        return 1
    fi
    if [[ ! "$name" =~ $_DB_NAME_RE ]]; then
        echo "" >&2
        echo "x BLOCKED: db_name '$name' is not an accepted database name: it" >&2
        echo "  must start with a letter or digit, be at least two characters" >&2
        echo "  long, and use only [A-Za-z0-9_.-] (letters, digits, underscore," >&2
        echo "  hyphen, dot) after that - the same shape Odoo's own database" >&2
        echo "  manager accepts (addons/web/controllers/database.py" >&2
        echo "  DBNAME_PATTERN, v9-v19), so a name this refuses would fail at" >&2
        echo "  database creation anyway." >&2
        echo "  Refusing rather than sanitizing: a slugged name would diverge from" >&2
        echo "  the real database name, and two distinct names could then slug to" >&2
        echo "  the SAME artifact filename - a silent cross-instance collision is" >&2
        echo "  worse than this refusal. In particular a '/' makes the generated" >&2
        echo "  conf escape the state-root conf dir (an unreclaimable leak) and a" >&2
        echo "  newline breaks the sweep's lease-name match (it can delete a live" >&2
        echo "  instance's conf). Rename the database - or fix db_name in" >&2
        echo "  instances.toml / --db-name - to match that shape and retry." >&2
        return 1
    fi
    return 0
}

# ---------------------------------------------------------------------------
# Retention SSOT - how many days a run artifact (a log, its .findings.md
# sibling, a generated conf) survives in its Tier-1 dir. A script constant on
# purpose: there is nothing machine-dependent to resolve, so this is NOT a
# public knob and no agent-facing doc mentions it. Raise it here if a longer
# forensic window is wanted.
#
# ONE bound for every swept family, deliberately. A conf whose lease is gone is
# dead sooner than 14 days, but a second constant would need its own
# justification and its own drift story; a caller that genuinely wants a tighter
# bound should take it as an explicit argument rather than introduce one.
# ---------------------------------------------------------------------------
_LOG_RETENTION_DAYS=14

# ---------------------------------------------------------------------------
# _leased_db_names - every db_name the allocator lease registry references
#   ($(odoo_ai_state_root)/runtime/leases.json - scripts/lib/allocator.py's SSOT
#   for which instances exist, live rows AND stale ones). Prints one name per
#   line. Exit 0 + no output when no registry exists yet (nothing was ever
#   leased on this host). Exit 1 means a registry IS there but could not be
#   read - the caller must then prune NOTHING.
#   Live-or-stale on purpose: liveness (owner pid + fingerprint + host) is
#   allocator.py's judgment, and re-deriving it here would only be a second,
#   drifting copy. The superset is strictly safe - it can only DELAY a prune,
#   never unlink a running instance's log or its open conf - and
#   `allocator.py gc` drops each stale row, after which its artifacts become
#   sweepable again.
# ---------------------------------------------------------------------------
_leased_db_names() {
    local reg
    reg="$(odoo_ai_state_root)/runtime/leases.json"
    [[ -e "$reg" ]] || return 0
    [[ -r "$reg" ]] || return 1
    { grep -oE '"db_name"[[:space:]]*:[[:space:]]*"[^"]*"' "$reg" 2>/dev/null || true; } \
        | sed -E 's/^"db_name"[[:space:]]*:[[:space:]]*"//; s/"$//'
}

# ---------------------------------------------------------------------------
# prune_stale_run_artifacts <dir> <glob> [<glob>...] - delete run artifacts
#   older than _LOG_RETENTION_DAYS from <dir>, EXCEPT any whose database the
#   lease registry still references. <glob>... are `find -name` patterns, OR'd
#   together; at least one is required (no glob means no candidates, never
#   "everything").
#
#   Both swept families name their files `<db>-<discriminator>.<ext>`
#   (`<db>-<UTC-ts>.log`, `<db>-<UTC-ts>.findings.md`, `<db>-<port>.conf`), so
#   the db name is everything before the LAST hyphen in the basename. That
#   shared shape is what lets one sweeper serve both.
#
#   Why the lease guard, not a bare age TTL: 50-instance-spinup.sh writes
#   long-lived LISTENING-instance artifacts (persist: exclusive-running /
#   shared-running) into these SAME shared dirs, and a lease with a
#   verified-alive owner pid is never TTL-reclaimed - so a listening instance
#   that simply goes quiet past the window would have its OPEN file unlinked out
#   from under the server's fd. For a log the server keeps appending to the
#   detached inode while every path-based read reports "no such file"; for a
#   conf, `-c <conf>` holds the file for the server's whole lifetime, so the
#   same hazard applies to it.
#
#   Best-effort, never fatal, never touches a live file: a size cap or a
#   truncation is deliberately NOT used, because losing the tail of a log can
#   lose the "Modules loaded." marker _install_confirmed requires and turn a
#   green build into STATUS=error. `-mtime +N` can never match a file written by
#   this run. A log's .findings.md sibling is swept with it (both globs passed
#   together) so the pair never desynchronises. Candidates are enumerated
#   (`-print0`) and removed one by one instead of `find -delete` so the
#   exclusion can be applied by EXACT db-name match; `-maxdepth 1` plus
#   `-type f` (find does not follow symlinks without -L) keeps every removal
#   inside the dir. Flags used are portable across GNU and BSD find.
# ---------------------------------------------------------------------------
prune_stale_run_artifacts() {
    local dir="${1:-}"
    shift || true
    [[ -n "$dir" && -d "$dir" ]] || return 0
    # No pattern means no candidate set. Returning here rather than letting
    # `find` run pattern-less is the difference between sweeping nothing and
    # sweeping every file in the dir.
    [[ "$#" -gt 0 ]] || return 0
    local leased
    # Fail closed: an unreadable registry means no artifact can be PROVEN
    # unleased.
    leased="$(_leased_db_names)" || return 0
    # Build the OR'd name group: \( -name g1 -o -name g2 ... \).
    local -a name_args=('(')
    local g first=1
    for g in "$@"; do
        if [[ "$first" -eq 1 ]]; then
            first=0
        else
            name_args+=(-o)
        fi
        name_args+=(-name "$g")
    done
    name_args+=(')')
    local f base db
    while IFS= read -r -d '' f; do
        base="${f##*/}"
        # <db>-<UTC-ts>.log, <db>-<UTC-ts>.findings.md and <db>-<port>.conf all
        # carry their discriminator as the last hyphen-delimited field, so the
        # db name is everything before it.
        db="${base%-*}"
        # validate_db_name (above) refuses a new db_name outside _DB_NAME_RE
        # before any file is ever written, but a file already on disk from
        # before that gate existed (or from any other write path) can still
        # carry one - most dangerously an embedded newline, which would turn
        # the `grep -Fxq` lease check below into a multi-line OR'd match
        # against a FRAGMENT of the real name rather than the whole name, and
        # could therefore misjudge a still-leased database as unleased. Skip
        # rather than trust that comparison: the artifact just survives one
        # more sweep cycle, which is the same "never touches a live file
        # unless proven safe" posture the lease guard right below already
        # applies to a name it CAN parse.
        if [[ ! "$db" =~ $_DB_NAME_RE ]]; then
            continue
        fi
        if [[ -n "$leased" ]] && printf '%s\n' "$leased" | grep -Fxq -- "$db"; then
            continue
        fi
        rm -f -- "$f" 2>/dev/null || true
    done < <(find "$dir" -maxdepth 1 -type f \
                  "${name_args[@]}" \
                  -mtime "+${_LOG_RETENTION_DAYS}" -print0 2>/dev/null || true)
}

# ---------------------------------------------------------------------------
# _prune_stale_logs <logs-dir> - the log-family wrapper. Kept as a named alias
#   so the existing call site in 55-instance-ops.sh's _open_log (and anything
#   that names it) keeps working: the log family is the pair
#   `<db>-<UTC-ts>.log` + `<db>-<UTC-ts>.findings.md`, always swept together.
# ---------------------------------------------------------------------------
_prune_stale_logs() {
    prune_stale_run_artifacts "$1" '*.log' '*.findings.md'
}
