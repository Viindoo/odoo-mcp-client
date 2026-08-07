#!/usr/bin/env bash
# resolve_project_dir.sh - Resolve WHERE Tier-2 project-scoped .odoo-ai/ state
# lives (Problem 3 - namespaced ~/.odoo-ai/, two-axis root). Full policy:
# snippets/state-root-resolution.md (SSOT for the classification tables and
# the mandatory resolve-capture-substitute prose protocol).
#
# Two axes under one machine-global root $ODOO_AI_HOME (default $HOME/.odoo-ai,
# same convention as resolve_instances.sh / allocator.py's _home()):
#
#   SHARE   - $ODOO_AI_HOME/projects/<repo-key>/
#             <repo-key> = sha256(realpath(git rev-parse --git-common-dir))[:12]
#             SAME for every linked worktree of one repo (git-common-dir is the
#             one shared .git dir); DIFFERENT across separate repos. Cross-run/
#             cross-worktree reusable knowledge (design, coordination, cache)
#             belongs here.
#   ISOLATE - $ODOO_AI_HOME/projects/<repo-key>/worktrees/<wt-key>/
#             <wt-key> = sha256(realpath(git rev-parse --show-toplevel))[:12]
#             DISTINCT per worktree (including the principal checkout, which is
#             just one worktree-key among others). Per-run/session active state
#             that a hook or resume treats as "the one active thing" belongs
#             here - two concurrent runs must never interleave on it.
#
# Explicit overrides (both honored verbatim, mkdir -p'd, never re-hashed):
#   ODOO_AI_PROJECT_DIR    overrides the SHARE dir
#   ODOO_AI_WORKTREE_DIR   overrides the ISOLATE dir
#
# Non-git fallback (C-9): NEVER hash bare $PWD (cwd-unstable - `/proj` and
# `/proj/sub` must resolve to the SAME project). Instead walk UP from CWD to
# the nearest project marker and hash ITS realpath. Two marker kinds, with a
# STRICT priority order (C-2): an explicit `.odoo-ai-root` sentinel file has
# GLOBAL priority - the walk scans the ENTIRE chain up to `/` for it FIRST;
# only when no sentinel exists ANYWHERE in the chain does it fall back to the
# NEAREST directory containing `__manifest__.py` (v10.0+) or `__openerp__.py`
# (v8.0-v9.0). This priority matters because real Odoo addons layouts nest a
# module descriptor under EVERY module dir, so "nearest marker, either kind,
# wins" would mis-root: two modules of the same project would resolve to two
# DIFFERENT module-level dirs instead of the shared project root, and a
# `.odoo-ai-root` placed at the project root to fix that would be defeated by
# the nearer module descriptor. A repo has no
# separate "worktree" concept outside git, so the ISOLATE key degrades to the
# SAME marker key as the SHARE key in this case (one project == one worktree).
# If no marker of EITHER kind is found by the time the walk reaches `/`,
# REFUSE with a clear stderr diagnostic and a non-zero exit rather than ever
# keying on $PWD.
#
# Usage:
#   Source-only:  source resolve_project_dir.sh
#                 resolve_project_dir_share    # prints the absolute SHARE dir
#                 resolve_project_dir_isolate  # prints the absolute ISOLATE dir
#                 resolve_project_dir_share   "<abs-root>"  # resolve AS IF cwd were <abs-root>
#                 resolve_project_dir_isolate "<abs-root>"  # same, ISOLATE
#   Runnable:     bash resolve_project_dir.sh [--root <abs-path>] share|isolate
#                 (prints ONE absolute path on stdout; exit 0, or non-zero +
#                 stderr diagnostic on failure)
#
# Shell/Python parity is an INVARIANT (tested in tests/test_project_dir_resolution.py):
# scripts/lib/paths.py implements the exact same algorithm for Python callers.
# Any change here MUST be mirrored there.
#
# Portable to bash 3.2 (macOS): no mapfile, no ${var,,}, no associative
# arrays; POSIX `[ ]` test, not `[[ ]]`; `${var:0:N}` substring expansion is
# bash builtin since 2.0 so it is safe here. Directory realpath is resolved
# via `cd DIR && pwd -P` (portable; no dependency on GNU coreutils `realpath`
# or GNU `readlink -f`, neither of which ships by default on macOS). The
# sha256 tool is picked deterministically: `sha256sum` (GNU coreutils, Linux)
# first, else `shasum -a 256` (macOS/BSD); refuse loudly if neither exists.

# ---------------------------------------------------------------------------
# internal helpers
# ---------------------------------------------------------------------------

# Echo ${ODOO_AI_HOME:-$HOME/.odoo-ai} (Tier-1 root), trailing slashes FULLY
# normalised. Mirrors resolve_instances.sh's `_odoo_ai_global_instances` /
# allocator.py's + paths.py's `_home()` so all four converge on the same root.
# Fails only when both HOME and ODOO_AI_HOME are unset.
#
# A doubled/tripled trailing slash on $ODOO_AI_HOME denotes the SAME directory
# as a single one (POSIX: "/a/b//" == "/a/b/" == "/a/b"), so it must
# canonicalize identically here and in paths.py's `_home()` - the prior form
# (`${ODOO_AI_HOME%/}`, strips exactly ONE) left a stray slash on a
# doubled-or-more input, which the caller's OWN trailing `${home%/}` strip
# only partially cancels (two single-strips, still short for a triple slash),
# while paths.py's `_home()` did ZERO stripping before `os.path.join` - the two
# sides diverged on a >=2-trailing-slash $ODOO_AI_HOME. Measured:
# tests/test_project_dir_resolution.py's `odoo_ai_home` trailing-slash parity
# cases. Uses `_project_dir_rstrip_slashes` (defined below) - full-rstrip,
# all-slashes -> "/" fallback, exactly like the override handling above.
_project_dir_home() {
    if [ -n "${ODOO_AI_HOME:-}" ]; then
        local h
        h="$(_project_dir_rstrip_slashes "$ODOO_AI_HOME")"
        [ -n "$h" ] || h="/"
        printf '%s\n' "$h"
        return 0
    fi
    if [ -n "${HOME:-}" ]; then
        printf '%s\n' "${HOME%/}/.odoo-ai"
        return 0
    fi
    printf 'resolve_project_dir: HOME and ODOO_AI_HOME are both unset - cannot resolve $ODOO_AI_HOME.\n' >&2
    return 1
}

# Echo the canonical (symlink-resolved) absolute path of directory $1.
# Portable `realpath` for a DIRECTORY (git rev-parse always emits a dir path
# here, never a file), without depending on the `realpath`/`readlink -f`
# binaries.
_project_dir_realpath_dir() {
    ( cd "$1" 2>/dev/null && pwd -P )
}

# Strip ALL trailing "/" from $1 - mirrors paths.py's `override.rstrip("/")`
# EXACTLY (parity invariant, see file header). A doubled or tripled trailing
# slash denotes the SAME directory as a single one (POSIX: "/a/b//" == "/a/b/"
# == "/a/b"), so the state-dir key must canonicalize all of them the same way;
# collapsing them is not lossy because they were never distinct paths to begin
# with. `${var%/}` alone strips only ONE, which would leave a stray trailing
# slash on a doubled-or-more input and diverge from paths.py - hence the loop.
# An all-slashes input (e.g. "/", "///") reduces to "" here; callers apply the
# `[ -n ] || override="/"` fallback, mirroring paths.py's `.rstrip("/") or "/"`.
_project_dir_rstrip_slashes() {
    local s="$1"
    while [ "${s%/}" != "$s" ]; do
        s="${s%/}"
    done
    printf '%s' "$s"
}

# Echo the first 12 hex chars of sha256(<raw bytes of $1>) - NO trailing
# newline is hashed (must match paths.py's hashlib.sha256(s.encode()) exactly,
# which hashes the bare string with no added newline).
_project_dir_hash12() {
    local input="$1" full=""
    if command -v sha256sum >/dev/null 2>&1; then
        full="$(printf '%s' "$input" | sha256sum | awk '{print $1}')" || return 1
    elif command -v shasum >/dev/null 2>&1; then
        full="$(printf '%s' "$input" | shasum -a 256 | awk '{print $1}')" || return 1
    else
        printf 'resolve_project_dir: neither sha256sum nor shasum found on PATH - cannot compute a repo/worktree key.\n' >&2
        return 1
    fi
    [ -n "$full" ] || return 1
    printf '%s\n' "${full:0:12}"
}

# Walk UP from directory $1 looking for a project marker. `.odoo-ai-root` has
# GLOBAL priority over a module descriptor (C-2): the walk scans the WHOLE
# chain up to `/` for a sentinel first (returning immediately the moment one
# is found, since sentinels are rare and the nearest one - walking bottom-up -
# is the intended root); only if NO sentinel exists anywhere in the chain does
# it fall back to the NEAREST `__manifest__.py` (v10.0+) or `__openerp__.py`
# (v8.0-v9.0) dir recorded along the way. This single pass does both: a
# sentinel check every level (immediate win) plus an opportunistic "nearest
# descriptor seen so far" capture used only if the walk reaches `/` with no
# sentinel. Echoes the winning dir's realpath, or returns 1 if the walk
# reaches `/` with NEITHER marker found anywhere.
_project_dir_marker_root() {
    local dir nearest_manifest=""
    dir="$(_project_dir_realpath_dir "$1")" || return 1
    [ -n "$dir" ] || return 1
    while :; do
        if [ -f "$dir/.odoo-ai-root" ]; then
            printf '%s\n' "$dir"
            return 0
        fi
        if [ -z "$nearest_manifest" ] && { [ -f "$dir/__manifest__.py" ] || [ -f "$dir/__openerp__.py" ]; }; then
            nearest_manifest="$dir"
        fi
        if [ "$dir" = "/" ]; then
            [ -n "$nearest_manifest" ] || return 1
            printf '%s\n' "$nearest_manifest"
            return 0
        fi
        dir="$(dirname "$dir")"
    done
}

# Non-git fallback key: hash the walk-up marker root found from $PWD.
# Returns 1 (no stderr - the CALLER emits the one clear diagnostic) when no
# marker exists, so callers can attribute the failure to the right override
# var (ODOO_AI_PROJECT_DIR vs ODOO_AI_WORKTREE_DIR).
_project_dir_nongit_key() {
    local marker
    marker="$(_project_dir_marker_root "$PWD")" || return 1
    _project_dir_hash12 "$marker"
}

# repo-key: sha256(realpath(git rev-parse --git-common-dir))[:12]. Falls back
# to the non-git marker key when there is no git-common-dir (outside any repo,
# or git itself is unavailable) - `git rev-parse --git-common-dir` prints the
# SAME shared .git dir for every linked worktree of one repo, so this key
# converges across worktrees and isolates across repos.
_project_dir_repo_key() {
    local common real
    common="$(git rev-parse --git-common-dir 2>/dev/null)" || { _project_dir_nongit_key; return; }
    real="$(_project_dir_realpath_dir "$common")" || return 1
    [ -n "$real" ] || return 1
    _project_dir_hash12 "$real"
}

# wt-key: sha256(realpath(git rev-parse --show-toplevel))[:12]. Falls back to
# the SAME non-git marker key as the repo-key (no git means no distinct
# worktree concept - one project IS one worktree).
_project_dir_wt_key() {
    local top real
    top="$(git rev-parse --show-toplevel 2>/dev/null)" || { _project_dir_nongit_key; return; }
    real="$(_project_dir_realpath_dir "$top")" || return 1
    [ -n "$real" ] || return 1
    _project_dir_hash12 "$real"
}

# Run the cwd-based resolver as if the cwd were $1. $1 = target root (abs path),
# $2 = share|isolate. Exists so there is exactly ONE resolution algorithm: the
# root is applied by a subshell `cd`, never by a second key-derivation path.
_resolve_project_dir_at() {
    local root="$1" verb="$2"
    if [ ! -d "$root" ]; then
        printf 'resolve_project_dir: --root %s is not a directory.\n' "$root" >&2
        return 1
    fi
    ( cd "$root" || exit 1; "resolve_project_dir_${verb}" )
}

# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------

# Echo the absolute SHARE dir ($ODOO_AI_HOME/projects/<repo-key>/), creating it
# (mkdir -p) first. Honors an explicit $ODOO_AI_PROJECT_DIR override verbatim
# (still mkdir -p'd, never re-hashed).
resolve_project_dir_share() {
    if [ -n "${1:-}" ]; then _resolve_project_dir_at "$1" share; return $?; fi
    if [ -n "${ODOO_AI_PROJECT_DIR:-}" ]; then
        local override
        override="$(_project_dir_rstrip_slashes "$ODOO_AI_PROJECT_DIR")"
        [ -n "$override" ] || override="/"
        mkdir -p "$override" || return 1
        printf '%s\n' "$override"
        return 0
    fi
    local home key dir
    home="$(_project_dir_home)" || return 1
    key="$(_project_dir_repo_key)" || {
        printf 'resolve_project_dir: not inside a git repo and no project marker (__manifest__.py, __openerp__.py, or .odoo-ai-root) found walking up from %s. Set $ODOO_AI_PROJECT_DIR to an explicit absolute path.\n' "$PWD" >&2
        return 1
    }
    dir="${home%/}/projects/${key}"
    mkdir -p "$dir" || return 1
    printf '%s\n' "$dir"
}

# Echo the absolute ISOLATE dir (<SHARE>/worktrees/<wt-key>/), creating it
# (mkdir -p) first. Honors an explicit $ODOO_AI_WORKTREE_DIR override verbatim.
# When unset, resolves the SHARE dir first (so an ODOO_AI_PROJECT_DIR override
# is respected for the SHARE half of the path too) and nests under it.
resolve_project_dir_isolate() {
    if [ -n "${1:-}" ]; then _resolve_project_dir_at "$1" isolate; return $?; fi
    if [ -n "${ODOO_AI_WORKTREE_DIR:-}" ]; then
        local override
        override="$(_project_dir_rstrip_slashes "$ODOO_AI_WORKTREE_DIR")"
        [ -n "$override" ] || override="/"
        mkdir -p "$override" || return 1
        printf '%s\n' "$override"
        return 0
    fi
    local share key dir
    share="$(resolve_project_dir_share)" || return 1
    key="$(_project_dir_wt_key)" || {
        printf 'resolve_project_dir: not inside a git repo and no project marker (__manifest__.py, __openerp__.py, or .odoo-ai-root) found walking up from %s. Set $ODOO_AI_WORKTREE_DIR to an explicit absolute path.\n' "$PWD" >&2
        return 1
    }
    dir="${share%/}/worktrees/${key}"
    mkdir -p "$dir" || return 1
    printf '%s\n' "$dir"
}

# ---------------------------------------------------------------------------
# CLI (only when EXECUTED, never when sourced)
# ---------------------------------------------------------------------------
if [ "${BASH_SOURCE[0]:-$0}" = "$0" ]; then
    set -euo pipefail
    _rpd_root=""
    if [ "${1:-}" = "--root" ]; then
        _rpd_root="${2:-}"
        if [ -z "$_rpd_root" ]; then
            printf 'resolve_project_dir: --root needs an absolute path\n' >&2
            exit 2
        fi
        shift 2
    fi
    case "${1:-}" in
        share)   resolve_project_dir_share "$_rpd_root" ;;
        isolate) resolve_project_dir_isolate "$_rpd_root" ;;
        *)
            printf 'Usage: resolve_project_dir.sh [--root <abs-path>] share|isolate\n' >&2
            exit 2
            ;;
    esac
fi
