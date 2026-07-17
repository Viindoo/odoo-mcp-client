#!/usr/bin/env bash
# migrate_project_state.sh - Tier-2 state-root migration helper (Problem 3 -
# namespaced ~/.odoo-ai/ state root, two-axis convention). Full policy:
# snippets/state-root-resolution.md (LOCKED SSOT for the classification
# tables this helper consumes verbatim - it does not decide tiers itself).
#
# One-time, idempotent COPY (NEVER move, NEVER clobber) of each legacy
# project-local ./.odoo-ai/<subpath> artifact into its resolved Tier-2 home:
#   SHARE subpaths   -> scripts/lib/resolve_project_dir.sh share
#   ISOLATE subpaths -> scripts/lib/resolve_project_dir.sh isolate
# Mirrors resolve_instances.sh's `_migrate_local_instances_to_global` idiom
# exactly: COPY not move (the legacy tree keeps working as an inert fallback,
# safe to delete once callers converge on the Tier-2 path), NEVER overwrite an
# already-migrated Tier-2 target, one log line per subpath actually copied.
#
# Dual-read / Tier-2-wins semantics: this helper only SEEDS the Tier-2 side
# once. It does not implement a merged reader itself - every consumer that
# follows the resolve-capture-substitute protocol (state-root-resolution.md)
# already reads ONLY the resolved Tier-2 path, never the legacy one, so once a
# subpath is migrated here the Tier-2 copy is what every future read sees
# (the same "global wins, project copy becomes an inert override" property
# resolve_instances.sh's own migration has for instances.toml).
#
# Tier-1 subpaths (instances.toml, runtime/, logs/, i18n.json) are explicitly
# OUT OF SCOPE - already migrated by resolve_instances.sh's own eager call
# (see 40-instance-profile.sh). Re-migrating them here would be redundant and
# would risk violating the Tier-1 "never map to a project/worktree dir"
# invariant if ever miswired. `venvs/` and `tools/pylint-<series>/` are ALSO
# out of scope here (state-root-resolution.md: explicitly not part of the
# Tier-2 SHARE/ISOLATE tables, and potentially large - a bulk copy would be
# wasteful; 45-venv.sh converges venvs/ onto the resolver's SHARE dir at the
# point of use instead, not via a bulk migration).
#
# `visual/` is NOT a tier by its top-level name alone (state-root-resolution.md
# "Note the split inside visual/"): `visual/baselines/` and `visual/doc/` are
# SHARE; every OTHER immediate child of `visual/` (screenshots/, videos/, a
# run_id staging dir, ...) is ISOLATE. This helper dispatches visual/'s
# immediate children individually rather than migrating visual/ as one unit.
#
# An unrecognized top-level entry (not in either exhaustive table, and not
# `visual`) is left in place with a stderr note - NEVER guessed into a tier
# (state-root-resolution.md "The rule": never default to SHARE "to be safe").
#
# Source-only: defines functions, runs nothing at source time. A guarded CLI
# stanza at the bottom (mirrors resolve_project_dir.sh) provides a MANUAL
# entrypoint (`bash migrate_project_state.sh run [PROJECT_DIR]`) for ad-hoc use.
# It is ALSO wired as a guarded, always-exit-0 SessionStart hook -
# hooks/migrate-project-state.sh sources this file and calls
# migrate_project_state() once per session; that wrapper is registered in
# hooks/hooks.json. The fast no-op path above (single -d test) keeps the hook
# from ever slowing a session that has no legacy .odoo-ai/ tree to migrate.
#
# Portable to bash 3.2 (macOS): no mapfile, no ${var,,}, no associative
# arrays; POSIX `[ ]` test, not `[[ ]]`; `cp -R` (not GNU-only `cp -r --...`).
#
# Usage:
#   Source-only:  source migrate_project_state.sh
#                 migrate_project_state [PROJECT_DIR]   # default: $PWD
#   Runnable:     bash migrate_project_state.sh run [PROJECT_DIR]

# Source resolve_project_dir.sh for resolve_project_dir_share/_isolate. Uses a
# uniquely-namespaced temp var (never SCRIPT_DIR - every setup-step script
# that may source THIS file already defines its OWN SCRIPT_DIR, and clobbering
# it would be a real bug) so this file is safe to source into any caller.
_migrate_project_state_lib_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./resolve_project_dir.sh
. "$_migrate_project_state_lib_dir/resolve_project_dir.sh"
unset _migrate_project_state_lib_dir

# Classify a TOP-LEVEL .odoo-ai/ entry name against the LOCKED tables in
# snippets/state-root-resolution.md. Echoes one of: tier1 | share | isolate |
# visual | unknown. "visual" is special-cased by the caller (a second-level
# dispatch - see the file header); every other name is decided by this table
# alone, per the doc's exhaustive top-level subpath lists.
_tier2_classify_top() {
    case "$1" in
        instances.toml | runtime | logs | i18n.json)
            printf 'tier1\n' ;;
        venvs | tools)
            # Deliberately out of scope (see file header) - same "leave it,
            # do not migrate" outcome as tier1, kept as a distinct case only
            # for the comment above; behaves identically to tier1 below.
            printf 'tier1\n' ;;
        context.md | coordination | designs | plans | gap-analysis | \
        documentation | survey | brl | brand-tokens.json | mockups | \
        glossary.yml | cost-config.json)
            printf 'share\n' ;;
        worklog | wave | brainstorm | git-rebase | forward-port | \
        modules-upgrade | pr-monitoring | coding | reviews | followups | \
        i18n | bids | content | debug | discovery | implement | packaging | \
        positioning | qa | research | sales | support | upgrade-plans | \
        video | run-*.json)
            printf 'isolate\n' ;;
        visual)
            printf 'visual\n' ;;
        *)
            printf 'unknown\n' ;;
    esac
}

# Copy ONE subpath (file or dir) from the legacy tree to its resolved Tier-2
# destination. Idempotent + copy-not-clobber: a pre-existing FINAL destination
# is left completely untouched (the legacy copy stays in place as an inert
# fallback) - this is the ONLY guard against re-migrating/overwriting.
#
# Atomic + resumable: the copy never writes directly to $dest. It stages into
# a sibling temp dir in the SAME parent as $dest (guaranteed same filesystem,
# so the final step is one atomic `mv`/rename) and only `mv`s it into place
# on full success. This makes `[ -e "$dest" ]` a genuine "fully migrated"
# signal: an interruption (SessionStart's 8s timeout on a large legacy tree,
# a concurrent same-worktree session, OOM-kill, a plain crash) can only ever
# leave behind the *staging* temp, never a half-written $dest. Any staging
# temp found left over from a prior attempt is therefore NOT "already done" -
# it is retry-able: removed, then the copy is redone from scratch.
#   $1 = source absolute path   $2 = destination absolute path
#   $3 = relative subpath (for the log line, e.g. "visual/baselines")
#   $4 = tier label for the log line ("SHARE" | "ISOLATE")
_tier2_copy_one() {
    local src="$1" dest="$2" rel="$3" label="$4"
    if [ -e "$dest" ]; then
        printf '  .odoo-ai/%s: %s target already exists at %s - skip (legacy copy at %s kept as inert fallback).\n' \
            "$rel" "$label" "$dest" "$src"
        return 0
    fi
    mkdir -p "$(dirname "$dest")" 2>/dev/null || {
        printf '  .odoo-ai/%s: could not create the parent dir for %s - skip.\n' "$rel" "$dest" >&2
        return 1
    }
    # Clean up any staging leftover from an interrupted PRIOR attempt (glob,
    # not just our own $$ - a bash-3.2-safe pattern: with no match the glob
    # stays literal and `[ -e ]` on it is false, so the loop body no-ops).
    local stale
    for stale in "$dest".migrating.*; do
        [ -e "$stale" ] || continue
        printf '  .odoo-ai/%s: found a partial/interrupted copy at %s from a previous run - removing and retrying.\n' \
            "$rel" "$stale" >&2
        rm -rf "$stale" 2>/dev/null
    done
    local tmp="$dest.migrating.$$"
    rm -rf "$tmp" 2>/dev/null
    if [ -d "$src" ]; then
        cp -R "$src" "$tmp" 2>/dev/null || {
            printf '  .odoo-ai/%s: copy to %s failed - skip.\n' "$rel" "$tmp" >&2
            rm -rf "$tmp" 2>/dev/null
            return 1
        }
    else
        cp "$src" "$tmp" 2>/dev/null || {
            printf '  .odoo-ai/%s: copy to %s failed - skip.\n' "$rel" "$tmp" >&2
            rm -rf "$tmp" 2>/dev/null
            return 1
        }
    fi
    mv -f "$tmp" "$dest" 2>/dev/null || {
        printf '  .odoo-ai/%s: atomic move of the staged copy into %s failed - skip.\n' "$rel" "$dest" >&2
        rm -rf "$tmp" 2>/dev/null
        return 1
    }
    printf '  Migrated .odoo-ai/%s -> %s (%s)\n' "$rel" "$dest" "$label"
}

# Dispatch every immediate child of a legacy visual/ dir individually (Tier
# depends on the FULL subpath, not the visual/ top-level name alone - see the
# file header). $1 = legacy visual/ abs path, $2 = SHARE dir, $3 = ISOLATE dir.
_tier2_migrate_visual() {
    local legacy_visual="$1" share_dir="$2" isolate_dir="$3" vchild vname
    for vchild in "$legacy_visual"/*; do
        [ -e "$vchild" ] || continue
        vname="$(basename "$vchild")"
        case "$vname" in
            baselines | doc)
                _tier2_copy_one "$vchild" "$share_dir/visual/$vname" "visual/$vname" "SHARE" ;;
            *)
                _tier2_copy_one "$vchild" "$isolate_dir/visual/$vname" "visual/$vname" "ISOLATE" ;;
        esac
    done
}

# Idempotent, GUARDED, one-shot-per-subpath migration of every legacy
# project-local ./.odoo-ai/<subpath> artifact into its resolved Tier-2 home.
# $1 = project dir (default $PWD). Fast no-op (single -d test, no resolver
# call, no mkdir) when no legacy .odoo-ai/ exists - the common case once a
# project has fully converged on Tier-2, and the expected state for a
# never-migrated fresh checkout.
migrate_project_state() {
    local project_dir="${1:-$PWD}"
    local legacy="${project_dir%/}/.odoo-ai"
    [ -d "$legacy" ] || return 0

    local share_dir isolate_dir
    share_dir="$(cd "$project_dir" && resolve_project_dir_share)" || return 1
    isolate_dir="$(cd "$project_dir" && resolve_project_dir_isolate)" || return 1

    local entry name tier
    for entry in "$legacy"/*; do
        [ -e "$entry" ] || continue
        name="$(basename "$entry")"
        tier="$(_tier2_classify_top "$name")"
        case "$tier" in
            tier1)
                continue ;;
            share)
                _tier2_copy_one "$entry" "$share_dir/$name" "$name" "SHARE" ;;
            isolate)
                _tier2_copy_one "$entry" "$isolate_dir/$name" "$name" "ISOLATE" ;;
            visual)
                _tier2_migrate_visual "$entry" "$share_dir" "$isolate_dir" ;;
            *)
                printf '  .odoo-ai/%s: unrecognized top-level entry - not in the LOCKED Tier-2 tables (snippets/state-root-resolution.md). Left in place; classify it there before migrating.\n' "$name" >&2
                ;;
        esac
    done
}

# ---------------------------------------------------------------------------
# CLI (only when EXECUTED, never when sourced) - a MANUAL entrypoint for
# ad-hoc use (`bash migrate_project_state.sh run [PROJECT_DIR]`). The
# session-start path is separate and does NOT go through this stanza: it is
# reached only when this file is EXECUTED directly, and the SessionStart hook
# always sources it instead - see the file header (lines ~47-51) for the
# hooks/migrate-project-state.sh + hooks.json wiring.
# ---------------------------------------------------------------------------
if [ "${BASH_SOURCE[0]:-$0}" = "$0" ]; then
    set -eu
    case "${1:-run}" in
        run)
            migrate_project_state "${2:-$PWD}"
            ;;
        *)
            printf 'Usage: migrate_project_state.sh [run] [PROJECT_DIR]\n' >&2
            exit 2
            ;;
    esac
fi
