#!/usr/bin/env bash
# lint_toolchain.sh - Source-only helper: resolve the TOOLCHAIN environment an
# odoo-bin launch needs for Odoo's own lint test families to actually run.
# This file is the ONLY place that resolution lives (SSOT) - the odoo-bin
# launch sites source it and call the helpers, never re-derive the logic.
#
# WHY THIS EXISTS
# Odoo's lint tests shell out to external tools and resolve them through the
# PROCESS ENVIRONMENT, not through the venv that runs odoo-bin:
#
#   - `test_eslint` does `eslint = tools.misc.find_in_path('eslint')`, i.e. a
#     bare PATH lookup. On a stock Debian/Ubuntu box PATH resolves the OS
#     package, which is eslint 6.4.0 (2019). That version cannot even PARSE a
#     modern `web/tooling/_eslintrc.json`: it exits 2 with
#     `Environment key "es2022" is unknown` BEFORE reading a single JS file.
#     The test is `@skipIf(eslint is None, ...)`, so a PRESENT-but-ancient
#     eslint does NOT skip - it FAILS, and the failure message renders the
#     parse error as if it were a lint result. That is the trap: it reads like
#     a finding about your code while zero files were examined.
#   - `test_pylint` / `test_flake8` import their tool from the interpreter, so
#     they need the VENV's bin on PATH for the tool's own console script, and
#     they skip (quietly, correctly) when it is absent.
#   - A `test_pylint`-style module resolves WHICH repo to lint from
#     `repo_to_check_quality`. Unset, it skips with "No repo to check". The
#     value is a DIRECTORY BASENAME, not a path: the test matches it with
#     `adp.endswith(f"/{repo}")` against each `odoo.addons.__path__` entry, so
#     passing an absolute path silently matches nothing and the gate keeps
#     skipping.
#
#     WHERE that value is read from is NOT uniform across series, and this is
#     the trap to know about: newer variants resolve it from the config file,
#     ELSE the REPO_TO_CHECK_QUALITY env var, ELSE the cwd - but older ones read
#     ONLY `tools.config['repo_to_check_quality']` and have no env branch at
#     all. Exporting the variable is therefore best-effort: it configures the
#     variants that read the environment and is inert on the ones that do not.
#     Deliberately NOT gated on a version number - the boundary belongs to the
#     lint module's own history, not to an Odoo series this plugin could
#     hardcode. What keeps that honest is the log line: it reports the value we
#     EXPORTED (a fact we control), never that the gate is now configured (a
#     claim we cannot make from here).
#
#     If a run still skips with "No repo to check" while LINT_TOOLCHAIN_REPO= is
#     in the log, that variant is config-file-only. Set the key in THAT
#     INSTANCE's own generated odoo.conf - the one 50-instance-spinup.sh writes
#     under the state root - and NOT in the shared `~/.odoorc`. Per-instance
#     conf is deliberate isolation ("never the user's default odoo.conf; no
#     project files are mutated"); putting a per-run lint target in the shared
#     default would apply it to every other instance on the host. That is also
#     why this file only ever touches the ENVIRONMENT of one launch subshell and
#     writes no config file of its own.
#
# So a repo can pin a correct, modern eslint in its own package.json and STILL
# be linted by the 2019 OS binary, because nothing ever put the repo-local
# `node_modules/.bin` in front of `/usr/bin`. Prepending it at the launch site
# is what makes the local gate agree with what CI enforces.
#
# SCOPE / LIMITS (stated, not hidden):
#   - Only runs that go through this plugin's launch sites are covered. A human
#     typing `odoo-bin` by hand still gets the OS toolchain.
#   - This installs NOTHING. If a repo pins eslint but never ran its package
#     manager, `node_modules/.bin` does not exist; `lint_toolchain_diagnostics`
#     reports exactly that instead of letting the run fail deceptively.
#   - The lint test families only EXIST when their module is installed, which
#     this plugin reserves for the pre-PR gate. On an ordinary node-verify run
#     these exports change nothing observable.
#
# Source-only: defines functions + no top-level side effects. Portable to
# bash 3.2 (macOS): no mapfile, no ${var,,}, no associative arrays, POSIX `[ ]`
# tests. Depends only on coreutils - no python required.
#
# Public API:
#   lint_toolchain_path_prefix <python-bin> <addons-csv>
#       -> prints the colon-joined PATH prefix (venv bin + every repo-local
#          node_modules/.bin found), or nothing when there is none to add.
#          Pure: prints, exports nothing.
#   lint_toolchain_repo_to_check <addons-csv> <modules-csv>
#       -> prints the DIRECTORY BASENAME to hand REPO_TO_CHECK_QUALITY, only
#          when exactly ONE addons entry owns the named modules. Ambiguous or
#          unresolvable -> prints nothing (caller leaves the var unset, and the
#          lint test keeps its current honest skip).
#   lint_toolchain_export <python-bin> <addons-csv> <modules-csv>
#       -> the one call a launch site makes: applies both of the above to the
#          CURRENT shell. Intended to be called INSIDE the launch subshell so
#          it never leaks past that one invocation.
#   lint_toolchain_diagnostics <addons-csv>
#       -> prints zero or more `allocator: LINT_TOOLCHAIN_*=` lines for the log.
#          Never fails, never blocks.

# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

# _lt_split_csv <csv> - print one entry per line, skipping empties.
# The trailing newline in the printf is load-bearing: without it `tr` emits a
# final field with no line terminator, and `while read` DROPS that last field
# (read returns non-zero at EOF even though it filled the variable). That bug
# silently truncated every CSV this file parses - the last addons entry was
# never scanned and a single-module list resolved to nothing at all.
_lt_split_csv() {
    printf '%s\n' "${1:-}" | tr ',' '\n' | while IFS= read -r _e; do
        # strip surrounding whitespace without ${var// } (bash 3.2 safe)
        _e="$(printf '%s' "$_e" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
        [ -n "$_e" ] && printf '%s\n' "$_e"
    done
}

# _lt_repo_root_for <addons-entry> - the directory holding a REPO-LOCAL
# node_modules. An addons entry is either the repo root itself (modules sit
# directly under it) or a subdir of it (odoo/addons), so entry-then-parent is
# the right search - but the parent step is only safe with a repo-root proof.
#
# MEASURED TRAP: a bare "does the parent have node_modules?" check (the shape
# _find_odoo_bin uses, which is correct for odoo-bin because odoo-bin really
# does sit beside the addons dir) matched `$HOME/git/node_modules` - a stray
# install in the SHARED parent of every checkout on this machine. Every addons
# entry then resolved to that same directory, so one unrelated node_modules
# would have been injected ahead of PATH for all of them.
#
# `.git` is the discriminator, and package.json is NOT: the shared parent has a
# package.json and no `.git`, while a real addons repo has `.git` and no
# package.json until someone installs the tooling. `-e` (not `-d`) is
# deliberate - a git WORKTREE's `.git` is a file, and worktrees are the normal
# shape here.
_lt_repo_root_for() {
    _d="${1:-}"
    [ -n "$_d" ] || return 1
    if [ -d "$_d/node_modules/.bin" ] && [ -e "$_d/.git" ]; then printf '%s\n' "$_d"; return 0; fi
    _p="$(dirname "$_d")"
    if [ -d "$_p/node_modules/.bin" ] && [ -e "$_p/.git" ]; then printf '%s\n' "$_p"; return 0; fi
    return 1
}

# --------------------------------------------------------------------------- #
# public API
# --------------------------------------------------------------------------- #

lint_toolchain_path_prefix() {
    _py="${1:-}"
    _addons="${2:-}"
    _prefix=""

    # 1. the venv bin dir that owns the interpreter running odoo-bin.
    if [ -n "$_py" ] && [ -x "$_py" ]; then
        _vbin="$(dirname "$_py")"
        [ -d "$_vbin" ] && _prefix="$_vbin"
    fi

    # 2. every repo-local node_modules/.bin reachable from the addons path, in
    #    addons-path order (deterministic), de-duplicated.
    #
    # Collected via command substitution and consumed from a HERE-DOC, never a
    # pipeline and never a scratch file. A `... | while read` loop runs its body
    # in a subshell, so `_prefix` built inside it would vanish at the pipe - the
    # reason the first cut reached for a scratch file. This plugin writes
    # NOTHING outside its state root (guard: tests/test_no_tmp_scratch.py,
    # written after a generated conf landed in the ambient scratch dir with no
    # exit path owning it), so the here-doc is the correct shape: same result,
    # no file, nothing to clean up, and safe under concurrent launches.
    _bins="$(_lt_split_csv "$_addons" | while IFS= read -r _entry; do
        _root="$(_lt_repo_root_for "$_entry" 2>/dev/null)" || continue
        printf '%s\n' "$_root/node_modules/.bin"
    done)"

    while IFS= read -r _b; do
        [ -n "$_b" ] || continue
        case ":$_prefix:" in *":$_b:"*) continue ;; esac
        if [ -z "$_prefix" ]; then _prefix="$_b"; else _prefix="$_prefix:$_b"; fi
    done <<_LT_EOF
$_bins
_LT_EOF

    printf '%s' "$_prefix"
}

lint_toolchain_repo_to_check() {
    _addons="${1:-}"
    _modules="${2:-}"
    [ -n "$_modules" ] || return 0        # nothing named -> stay silent

    # Same here-doc discipline as above: no pipeline for the accumulator, no
    # scratch file anywhere.
    _owners="$(_lt_split_csv "$_addons" | while IFS= read -r _entry; do
        [ -d "$_entry" ] || continue
        _inner="$(_lt_split_csv "$_modules")"
        for _m in $_inner; do
            if [ -f "$_entry/$_m/__manifest__.py" ]; then basename "$_entry"; break; fi
        done
    done)"

    _uniq=""
    _n=0
    while IFS= read -r _o; do
        [ -n "$_o" ] || continue
        case " $_uniq " in *" $_o "*) continue ;; esac
        _uniq="${_uniq}${_uniq:+ }$_o"
        _n=$((_n + 1))
    done <<_LT_EOF
$_owners
_LT_EOF

    # EXACTLY one owning repo, or nothing. Two repos both owning a named module
    # is genuine ambiguity: guessing one would lint the wrong tree, and
    # REPO_TO_CHECK_QUALITY takes a single basename with no way to say "both".
    # Staying unset keeps the lint test's own honest skip.
    [ "$_n" = "1" ] && printf '%s' "$_uniq"
    return 0
}

lint_toolchain_export() {
    _py="${1:-}"; _addons="${2:-}"; _modules="${3:-}"

    _pfx="$(lint_toolchain_path_prefix "$_py" "$_addons")"
    if [ -n "$_pfx" ]; then
        PATH="$_pfx:$PATH"
        export PATH
    fi

    # Never override a value the operator set deliberately.
    if [ -z "${REPO_TO_CHECK_QUALITY:-}" ]; then
        _repo="$(lint_toolchain_repo_to_check "$_addons" "$_modules")"
        if [ -n "$_repo" ]; then
            REPO_TO_CHECK_QUALITY="$_repo"
            export REPO_TO_CHECK_QUALITY
            # State the FACT (what we exported), never the conclusion (that the
            # gate is configured) - a config-file-only lint variant ignores it.
            # The remedy named here is the INSTANCE's own generated conf, never
            # the shared default: 50-instance-spinup.sh writes a per-instance
            # odoo.conf under the state root precisely so instances cannot
            # collide, and sending someone to edit ~/.odoorc would undo that by
            # leaking one run's setting into every other instance on the host.
            printf 'allocator: LINT_TOOLCHAIN_REPO=%s (exported; a lint module that reads its config file only will ignore this - set repo_to_check_quality in THIS instance own generated odoo.conf, never in the shared ~/.odoorc)\n' "$_repo"
        fi
    fi
}

lint_toolchain_diagnostics() {
    _addons="${1:-}"
    # Deduped: several addons entries legitimately share ONE repo root (a core
    # checkout contributes both `<root>/addons` and `<root>/odoo/addons`), and
    # repeating the same line once per entry buries the signal in the log.
    _lt_diag_lines "$_addons" | awk '!seen[$0]++'
}

_lt_diag_lines() {
    _addons="${1:-}"
    _found=0
    _lt_split_csv "$_addons" | while IFS= read -r _entry; do
        _root="$(_lt_repo_root_for "$_entry" 2>/dev/null)"
        if [ -n "$_root" ] && [ -x "$_root/node_modules/.bin/eslint" ]; then
            printf 'allocator: LINT_TOOLCHAIN_ESLINT=%s\n' "$_root/node_modules/.bin/eslint"
            continue
        fi
        # A repo that PINS eslint but never installed it is the deceptive case:
        # the pin looks like coverage while the OS binary does the linting. Only
        # a GIT ROOT counts as "a repo" here, for the same reason the PATH
        # resolver requires one - a package.json in a shared parent directory is
        # not this repo's tooling, and naming it would send someone to install
        # in the wrong place.
        for _cand in "$_entry" "$(dirname "$_entry")"; do
            [ -e "$_cand/.git" ] || continue
            if [ -f "$_cand/package.json" ] && grep -q '"eslint"' "$_cand/package.json" 2>/dev/null; then
                printf 'allocator: LINT_TOOLCHAIN_UNINSTALLED=%s (package.json pins eslint but node_modules/.bin is absent - install it INSIDE that repo, or the OS eslint lints instead)\n' "$_cand"
                break
            fi
        done
    done

    # The silence case is the dangerous one: no repo-local eslint anywhere on
    # the addons path means whatever `eslint` PATH offers does the linting, and
    # a stock OS package is old enough to fail on the config before it reads a
    # single file. Say it once, with the binary that will actually be used, so
    # the log never implies coverage that is not there.
    _any="$(_lt_split_csv "$_addons" | while IFS= read -r _e; do
        _r="$(_lt_repo_root_for "$_e" 2>/dev/null)" || continue
        [ -x "$_r/node_modules/.bin/eslint" ] && echo y
    done)"
    if [ -z "$_any" ]; then
        _os="$(command -v eslint 2>/dev/null || true)"
        if [ -n "$_os" ]; then
            printf 'allocator: LINT_TOOLCHAIN_FALLBACK=%s (no repo-local eslint on the addons path - this OS binary will lint, and an old one FAILS on a modern config before reading any JS file)\n' "$_os"
        else
            printf 'allocator: LINT_TOOLCHAIN_FALLBACK=none (no eslint on PATH at all - the eslint gate will SKIP, not pass)\n'
        fi
    fi
}
