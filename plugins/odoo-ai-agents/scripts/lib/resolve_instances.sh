#!/usr/bin/env bash
# resolve_instances.sh - Source-only helper: resolve WHERE instances.toml lives.
#
# instances.toml declares the local Odoo instances on THIS host (series, ports,
# db, addons_path, python). It is Tier-1 - flat under $ODOO_AI_HOME - the same
# machine-global tier as the allocator runtime/ registry, logs/, and i18n.json.
# Every OTHER former .odoo-ai/ artifact (context.md, survey/, worklog/, ...) is
# now namespaced Tier-2 under $ODOO_AI_HOME/projects/<repo-key>/[worktrees/<wt-key>/]
# (SSOT: snippets/state-root-resolution.md), NEVER a project-relative $PWD/.odoo-ai/.
# Keeping instances.toml machine-global (not per-cwd) means an execute-agent in
# repo X still sees an instance declared while in repo Y. This helper is the
# single source of truth for the path so the setup steps (40/45/50) and any
# consumer resolve it the same way from any working directory.
#
# Resolution order (READ; first existing file with >=1 [[instance]] wins):
#   1. $ODOO_AI_INSTANCES                                  explicit full-path override
#   2. ${ODOO_AI_HOME:-$HOME/.odoo-ai}/instances.toml      machine-global (canonical)
#   3. $PWD/.odoo-ai/instances.toml                        transitional project fallback
# WRITE target is ALWAYS the global path (slot 1 override else slot 2) so new
# entries land in the single machine-global SSOT - this keeps the writer (40)
# and the readers (45/50) pointed at the same file.
#
# Source-only: defines functions, runs nothing. Portable to bash 3.2 (macOS):
# no mapfile, no ${var,,}, no associative arrays; grep runs on a file, never
# piped under `set -o pipefail`.

# SSOT mirror of scripts/lib/instances_io.py's ADDONS_PATH_SEP/join_addons_path/
# split_addons_path - keep the two in lockstep (T/test_addons_path_separator_parity.py
# enforces this). Odoo's --addons-path CLI flag and its addons_path config-file key
# are COMMA-separated, uniformly, across every indexed series 8.0-19.0.
ADDONS_PATH_SEP=','

# Populate the NAMED array $1 by splitting addons-path string $2 on the SSOT
# separator (tolerates a stray legacy colon so an old caller degrades, never
# hard-fails). Every setup-step that scans addons_path entries for odoo-bin or
# a repo dir MUST call this instead of its own `IFS=... read -ra`.
#
# $1 is a variable NAME (not a nameref): `read -ra "$1"` assigns into whatever
# variable that name resolves to in the caller's scope, exactly like the
# `IFS=... read -ra _paths` lines this replaces - no `local -n` (bash 4.3+),
# so this stays portable to bash 3.2 like the rest of this file.
_addons_path_to_array() {
    local _aptoa_norm="${2//:/,}"
    IFS="$ADDONS_PATH_SEP" read -ra "$1" <<<"$_aptoa_norm"
}

# Echo the machine-global instances.toml path. Fails (returns 1 + stderr
# diagnostic) ONLY when HOME, ODOO_AI_HOME and ODOO_AI_INSTANCES are all unset -
# we refuse to silently target /.odoo-ai.
_odoo_ai_global_instances() {
    if [ -n "${ODOO_AI_HOME:-}" ]; then
        printf '%s\n' "${ODOO_AI_HOME%/}/instances.toml"
        return 0
    fi
    if [ -n "${HOME:-}" ]; then
        printf '%s\n' "${HOME%/}/.odoo-ai/instances.toml"
        return 0
    fi
    printf 'resolve_instances: HOME, ODOO_AI_HOME and ODOO_AI_INSTANCES are all unset - cannot resolve a machine-global instances.toml. Set ODOO_AI_INSTANCES to an explicit path.\n' >&2
    return 1
}

# Echo the machine-global runtime dir (the allocator's lease registry lives here:
# runtime/leases.json + runtime/registry.lock). Same root as the instances.toml
# SSOT - ${ODOO_AI_HOME:-$HOME/.odoo-ai}/runtime - and deliberately NOT affected by
# $ODOO_AI_INSTANCES (that overrides only the catalog file, not the runtime root).
# Mirrors scripts/lib/allocator.py's _home()/_runtime_dir() so shell and Python
# resolve the same directory. See docs/reference/INSTANCE-ALLOCATION.md.
_odoo_ai_runtime_dir() {
    if [ -n "${ODOO_AI_HOME:-}" ]; then
        printf '%s\n' "${ODOO_AI_HOME%/}/runtime"
        return 0
    fi
    if [ -n "${HOME:-}" ]; then
        printf '%s\n' "${HOME%/}/.odoo-ai/runtime"
        return 0
    fi
    printf 'resolve_instances: HOME and ODOO_AI_HOME are both unset - cannot resolve a runtime dir.\n' >&2
    return 1
}

# True if $1 is a file that declares at least one [[instance]] table.
_instances_nonempty() {
    [ -f "$1" ] && grep -qE '^\[\[instance\]\]' "$1" 2>/dev/null
}

# Echo the WRITE target: explicit override, else the machine-global path.
_write_instances_target() {
    if [ -n "${ODOO_AI_INSTANCES:-}" ]; then
        printf '%s\n' "$ODOO_AI_INSTANCES"
        return 0
    fi
    _odoo_ai_global_instances
}

# Echo the READ path (global-wins). When neither the global nor a project file
# exists yet, echo the global path (the canonical default a caller creates/tests).
_resolve_instances() {
    if [ -n "${ODOO_AI_INSTANCES:-}" ]; then
        printf '%s\n' "$ODOO_AI_INSTANCES"
        return 0
    fi
    local global proj
    global="$(_odoo_ai_global_instances)" || return 1
    proj="$PWD/.odoo-ai/instances.toml"
    if _instances_nonempty "$global"; then printf '%s\n' "$global"; return 0; fi
    if _instances_nonempty "$proj";   then printf '%s\n' "$proj";   return 0; fi
    printf '%s\n' "$global"
}

# Ensure the machine-global instances dir exists with a defensive .gitignore
# ($HOME may itself be a dotfiles git repo; instances.toml carries machine-local
# paths and must never be committed there). Idempotent.
_ensure_global_instances_dir() {
    local global dir
    global="$(_write_instances_target)" || return 1
    dir="$(dirname "$global")"
    mkdir -p "$dir"
    if [ ! -f "$dir/.gitignore" ]; then
        printf '*\n' >"$dir/.gitignore"
    fi
}

# One-time migration: seed the machine-global instances.toml from an existing
# project-local file. COPY (not move) so the project file keeps working as a
# fallback; NEVER clobber an existing global. Idempotent.
_migrate_local_instances_to_global() {
    local global proj
    global="$(_write_instances_target)" || return 1
    proj="$PWD/.odoo-ai/instances.toml"
    _ensure_global_instances_dir || return 1
    [ -f "$proj" ] || return 0
    [ "$proj" = "$global" ] && return 0   # already the same file
    if [ -f "$global" ]; then
        printf '  Note: both %s and %s exist - the machine-global file wins; the project copy is kept as an inert override.\n' "$proj" "$global"
        return 0
    fi
    cp "$proj" "$global"
    printf '  Migrated %s -> %s (machine-global; the project copy is now an inert override, safe to delete).\n' "$proj" "$global"
}
