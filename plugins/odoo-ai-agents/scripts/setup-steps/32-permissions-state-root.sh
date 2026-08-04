#!/usr/bin/env bash
# 32-permissions-state-root.sh - Auto-allow the narrow set of Bash/Read/Edit
# rules the planning + intake pipeline needs to resolve and write under the
# machine-global state root ($ODOO_AI_HOME) without a per-call approval prompt.
#
# WHY this is a SIBLING of 30-permissions.sh, not folded into it: 30 owns the
# browser-MCP tool-permission surface (its docstring, cmd_describe, and the V-19
# three-way sync with browser_prefixes.py / browser-mcp-servers.sh are all
# browser-specific). This step owns a DIFFERENT, narrower surface - state-root
# Bash/Read/Edit rules - so it gets its own numbered script per the repo's
# "one capability, one step script" convention (see commands/odoo-setup.md).
#
# WHY NO `Write(<path>)` RULE (do NOT re-add one): Claude Code's file-permission
# check matches PATH rules on `Edit(path)` ONLY - an `Edit(path)` rule already
# covers EVERY file-editing tool, Write included. A `Write(<path>)` rule matches
# nothing, and the CLI emits a startup warning for it on every session:
#   "Permission allow rule (.claude/settings.json): Write(<path>) is not matched
#    by file permission checks - only Edit(path) rules are."
# Because this step's `check` is re-run by hooks/ensure-state-root-permissions.sh
# on every SessionStart, a `Write(...)` entry in RULES below made the warning
# SELF-HEALING against the user: deleting it by hand failed `check`, the hook
# re-`apply`ed, and the warning returned next launch. Tool-name rules
# (`Bash(...)`, `Read(...)`) are unaffected - this constraint is specific to the
# path-matching file-permission layer.
#
# Root cause this fixes: `odoo-planner` / `odoo-doc-planner` / intake Phase P all
# resolve and write under $ODOO_AI_HOME on every planning/run-DAG turn. Without
# this permission pre-grant, a fresh install prompts for the SAME handful of
# Bash/Read/Edit calls on every session - not a Plan-Mode problem (see
# snippets/planning-gate-contract.md § Plan-Mode enter/exit for that fix), a
# permissions-onboarding problem. This step is the out-of-the-box experience for
# a fresh install; it does not (and cannot) change Plan Mode's own inheritance
# behavior.
#
# HARD SAFETY CONTRACT (enforced by tests/test_state_root_permissions.py -
# do NOT loosen without updating that test):
#   - Writes ONLY to permissions.allow[] - NEVER permissions.deny[]/ask[], and
#     NEVER additionalDirectories (that would widen READ scope across every
#     project's state tree for every session; Read(//$ODOO_AI_HOME/**) below
#     already achieves the needed effect with a narrower blast radius).
#   - The Edit rule covers ONLY `projects/**` under the state root - that
#     ONE surface is sufficient: the plan (SHARE, `<repo-key>/plans/`) AND the
#     per-worktree worklog (ISOLATE, `<repo-key>/worktrees/<wt-key>/worklog/`)
#     both resolve NESTED under `projects/**` (see
#     snippets/state-root-resolution.md) - there is no separate top-level
#     `worklog/` directory to grant, so no separate rule is added for one. It
#     EXCLUDES `bin/`, `venvs/`, `node_tools/`, `setup-scripts/`, `runtime/`, and
#     `instances.toml`. A sitecustomize.py under venvs/ or an edited
#     setup-scripts/*.sh is deferred code execution, not scratch data -
#     granting blanket Edit(//$ODOO_AI_HOME/**) would auto-approve that too.
#   - Never writes `mcp__odoo-semantic` - that permission's owner is
#     plugins/odoo-semantic-mcp/commands/connect.md step 5; `check` below only
#     REPORTS its absence and points there.
#   - Bash rules are EXACT, wildcard-free command strings (the script this
#     grants takes exactly two argument values - `share` or `isolate` - so a
#     trailing `:*` wildcard would only widen the surface for no benefit).
#
# VERSION-PINNED RULE CONVERGENCE (do NOT let this regress into unbounded
# growth): the two Bash rules below embed `${PLUGIN_ROOT}`, which resolves to
# the INSTALLED plugin version's own directory. A naive re-apply on every
# plugin upgrade would therefore keep ADDING a new pair of rules - one per
# version ever installed - and never remove the previous pair. That is not
# cosmetic: a rule that stops matching anything (because its version's
# directory was later cleaned from the plugin cache) makes the CLI warn at
# every launch. `apply` (below) prunes this class instead of just adding to
# it: writing the CURRENT version's Bash rule for `resolve_project_dir.sh`
# also REMOVES any other allow[] entry that BOTH (a) starts with THIS
# plugin's own stable path prefix (`$PLUGIN_ROOT` with the version segment
# stripped - see `PRUNE_ANCHOR`/`STABLE_PLUGIN_PREFIX` below) AND (b) ends in
# the same trailing `.../scripts/lib/resolve_project_dir.sh share)` /
# `.../isolate)` suffix - i.e. a PRIOR VERSION OF THIS SAME PLUGIN's absolute
# path pinned by an earlier `apply`. The prefix check is load-bearing, not
# optional: a suffix-only match would ALSO delete a DIFFERENT plugin's rule
# for an identically-suffixed script (two plugins can each ship their own
# scripts/lib/resolve_project_dir.sh) - an earlier revision of this fix made
# exactly that mistake and deleted an unrelated plugin's permission in
# testing; `test_prune_never_prunes_different_plugin_same_script` guards
# against a regression. Nothing outside the anchored class is ever touched: a
# different plugin's rule, a rule for a different script under THIS plugin, a
# different tool, or a user's own hand-written rule is left alone.
#   A version-agnostic wildcard rule (one stable `Bash(...)` entry matching
#   every version) was considered and rejected: Claude Code's Bash rules do
#   support `*` at any position (see https://code.claude.com/docs/en/permissions
#   "Wildcard patterns" - a single `*` matches any run of characters,
#   including `/`), so a rule such as
#   `Bash(bash <plugin-name-dir>/*/scripts/lib/resolve_project_dir.sh share)`
#   IS syntactically possible. It was rejected because (a) it would violate
#   the "Bash rules are EXACT, wildcard-free" contract directly above and its
#   test (test_bash_rules_are_exact_no_wildcard); (b) it assumes the segment
#   immediately above `scripts/` is always a bare version number, which holds
#   for a marketplace-cache install but not for a `--plugin-dir` dev
#   checkout (no version segment at all - the wildcard would instead swallow
#   the plugin-name segment itself and could match a DIFFERENT plugin's
#   identically-named script under the same parent directory); and (c) even
#   the narrower anchored form matches any run of characters (not just one
#   path segment), so it auto-approves more than a version substitution.
#   Pruning keeps every live rule exact while still converging - see
#   `cmd_apply`'s use of `config_merge.py json-ensure-allow-pruning` and
#   `cmd_check`'s `_stale_bash_present` guard, and
#   tests/test_state_root_permissions.py's
#   `test_apply_prunes_prior_version_bash_rules` /
#   `test_apply_across_three_versions_stays_at_two_bash_rules` /
#   `test_prune_never_prunes_different_plugin_same_script` for the proof.
#   The SAME concern (b) above - "which path segment IS the version?" -
#   applies to pruning too, not just to the rejected wildcard: `PRUNE_ANCHOR`
#   (below) only enables pruning when `$PLUGIN_ROOT`'s own last path segment
#   is a real MAJOR.MINOR.PATCH version (the exact pattern
#   scripts/bump-version.sh already enforces as this repo's version-format
#   SSOT). A `--plugin-dir` dev checkout has no such segment, so pruning is
#   skipped for that run - plain add-only, never a guess - see
#   `test_dev_checkout_without_version_segment_skips_pruning_safely`.
#
# Subcommands:
#   describe   One-line description.
#   check      Exit 0 if all 4 rules already in permissions.allow[] AND no
#              stale prior-version Bash rule remains for the same script;
#              exit 1 if either is true. Also reports (non-blocking) whether
#              mcp__odoo-semantic is present, pointing at its real owner.
#   apply      Ask [Y/n] (honors ODOO_AI_NO_AUTO_PERMS=1 opt-out), then
#              idempotently append the 4 rules via config_merge.py
#              json-ensure-allow (Read/Edit) / json-ensure-allow-pruning
#              (the two version-pinned Bash rules - also removes any stale
#              prior-version Bash rule for the same script), print them,
#              instruct one restart, and self-verify by re-running check.
#
# CONFIG PATH:
#   CLAUDE_SETTINGS  permissions file  ${CLAUDE_SETTINGS:-$HOME/.claude/settings.json}
#
# HARD RULES:
#   - Writes to ~/.claude/settings.json (permissions) - NOT ~/.claude.json
#     (the MCP registry).
#   - Never echoes secrets (there are none here).
#   - Idempotent: re-running adds nothing.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB="$SCRIPT_DIR/../lib/config_merge.py"

CLAUDE_SETTINGS="${CLAUDE_SETTINGS:-$HOME/.claude/settings.json}"

# Resolve the plugin root: prefer the harness-provided $CLAUDE_PLUGIN_ROOT (set
# when this step is dispatched from within the plugin's own command/hook
# context - mirrors commands/odoo-setup.md's own STEPS_DIR resolution); fall
# back to computing it from this script's own location so a direct/standalone
# invocation (tests, manual `bash 32-....sh apply`) still resolves correctly.
if [[ -n "${CLAUDE_PLUGIN_ROOT:-}" ]]; then
    PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT%/}"
else
    PLUGIN_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
fi

# PRUNE_ANCHOR: is $PLUGIN_ROOT's OWN last path segment a real MAJOR.MINOR.PATCH
# version (the exact SSOT pattern scripts/bump-version.sh enforces for
# VERSION/plugin.json - see its own `^[0-9]+\.[0-9]+\.[0-9]+$` check)? Only
# then do we know which segment of the path IS the version, so only then is
# it safe to compute a STABLE_PLUGIN_PREFIX (everything above that segment,
# i.e. $PLUGIN_ROOT with the version stripped) to anchor pruning to THIS
# plugin's own directory.
#   - A marketplace-cache install (`.../<marketplace>/odoo-ai-agents/4.20.0`)
#     matches: PRUNE_ANCHOR=1, STABLE_PLUGIN_PREFIX=`.../odoo-ai-agents`.
#   - A `--plugin-dir` dev checkout (`.../worktrees/<wt-key>/plugins/odoo-ai-agents`,
#     no version directory at all) does NOT match: PRUNE_ANCHOR=0. Pruning is
#     then skipped entirely for the Bash rules this run (see cmd_apply/
#     cmd_check below) - falling back to plain add-only. This is deliberately
#     conservative: without a real version segment we cannot tell which path
#     component to strip, so guessing would either strip the WRONG segment
#     (e.g. the plugin-name directory itself) and widen the anchor to match
#     sibling plugins/scripts it must never touch, or do nothing useful -
#     "no pruning this run" is the only option that is always safe and never
#     crashes. A dev checkout's own path is stable across repeated runs of
#     the SAME checkout anyway, so plain add-only is already idempotent for
#     it; any stale marketplace-version rule from a prior REAL install is
#     left alone until a run with a real version segment prunes it.
VERSION_SEGMENT="${PLUGIN_ROOT##*/}"
if [[ "$VERSION_SEGMENT" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    PRUNE_ANCHOR=1
    STABLE_PLUGIN_PREFIX="${PLUGIN_ROOT%/*}"
else
    PRUNE_ANCHOR=0
    STABLE_PLUGIN_PREFIX=""
fi

# Resolve the state root exactly like scripts/lib/resolve_project_dir.sh's own
# Tier-1 root convention: $ODOO_AI_HOME, defaulting to $HOME/.odoo-ai.
ODOO_AI_HOME="${ODOO_AI_HOME:-$HOME/.odoo-ai}"
ODOO_AI_HOME="${ODOO_AI_HOME%/}"

# The 4 exact rules (SSOT for this step). Read/Edit use the `//<abs-path>`
# form (one extra leading slash over the already-absolute $ODOO_AI_HOME) so the
# rule matches an ABSOLUTE filesystem path, not a project-relative one.
# `Edit(...)` covers ONLY `projects/**` - both the SHARE plan
# (`<repo-key>/plans/`) and the ISOLATE worklog
# (`<repo-key>/worktrees/<wt-key>/worklog/`) resolve nested under it
# (snippets/state-root-resolution.md), so a separate `worklog/**` rule would
# target a path that never exists - deliberately not added.
# NO `Write(<path>)` rule belongs here: `Edit(path)` already covers every
# file-editing tool, and a `Write(<path>)` rule matches nothing while making the
# CLI warn at every launch (see the WHY NO `Write(<path>)` RULE note above).
RESOLVE_SCRIPT_REL="scripts/lib/resolve_project_dir.sh"

RULES=(
    "Bash(bash ${PLUGIN_ROOT}/${RESOLVE_SCRIPT_REL} share)"
    "Bash(bash ${PLUGIN_ROOT}/${RESOLVE_SCRIPT_REL} isolate)"
    "Read(/${ODOO_AI_HOME}/**)"
    "Edit(/${ODOO_AI_HOME}/projects/**)"
)

# Stale-detection suffixes, index-aligned with RULES[0] and RULES[1] (the two
# Bash rules only - Read/Edit above key off $ODOO_AI_HOME, not $PLUGIN_ROOT,
# so they never drift across plugin versions and need no pruning). An allow[]
# entry is stale for RULES[i] only if it BOTH starts with
# BASH_STABLE_PREFIX_MATCH AND ends with STALE_BASH_SUFFIXES[i], and is NOT
# equal to the corresponding current RULES[] entry - i.e. THIS plugin's own
# script, pinned to a DIFFERENT (stale) version of THIS plugin's path. The
# prefix requirement is load-bearing: a suffix match alone would also catch a
# DIFFERENT plugin's identically-named/argued script - see "VERSION-PINNED
# RULE CONVERGENCE" above.
STALE_BASH_SUFFIXES=(
    "/${RESOLVE_SCRIPT_REL} share)"
    "/${RESOLVE_SCRIPT_REL} isolate)"
)

# The literal string prefix every pruned entry must start with. Built the
# same way the RULES[] Bash entries themselves are ("Bash(bash <path>") so it
# lines up exactly. Only meaningful when PRUNE_ANCHOR=1 (see above) - left
# empty otherwise and never consulted (pruning is skipped in that case).
BASH_STABLE_PREFIX_MATCH="Bash(bash ${STABLE_PLUGIN_PREFIX}/"

# ---------------------------------------------------------------------------
# describe
# ---------------------------------------------------------------------------
cmd_describe() {
    echo "Auto-allow the state-root Bash/Read/Edit rules (planning + intake Phase P) in Claude permissions"
}

# ---------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------
_allow_has() {
    # $1 = rule string. Exit 0 if present in permissions.allow[].
    [[ -f "$CLAUDE_SETTINGS" ]] || return 1
    python3 - "$CLAUDE_SETTINGS" "$1" <<'PY'
import json, sys
try:
    with open(sys.argv[1]) as f:
        data = json.load(f)
except Exception:
    sys.exit(1)
allow = (data.get("permissions") or {}).get("allow") or []
sys.exit(0 if sys.argv[2] in allow else 1)
PY
}

_odoo_semantic_present() {
    [[ -f "$CLAUDE_SETTINGS" ]] || return 1
    python3 - "$CLAUDE_SETTINGS" <<'PY'
import json, sys
try:
    with open(sys.argv[1]) as f:
        data = json.load(f)
except Exception:
    sys.exit(1)
allow = (data.get("permissions") or {}).get("allow") or []
sys.exit(0 if any(a == "mcp__odoo-semantic" or a.startswith("mcp__odoo-semantic__") for a in allow) else 1)
PY
}

_stale_bash_present() {
    # Exit 0 iff permissions.allow[] contains a Bash(...) rule that BOTH
    # starts with BASH_STABLE_PREFIX_MATCH (THIS plugin's own directory,
    # version stripped) AND ends in one of STALE_BASH_SUFFIXES (same
    # resolve_project_dir.sh + argument), but is NOT exactly one of the
    # current-version RULES - i.e. a prior version of THIS SAME plugin's
    # pinned path for the same script that `apply` has not yet pruned. Only
    # meaningful when PRUNE_ANCHOR=1 (see "PRUNE_ANCHOR" above): without a
    # real version segment to anchor on, staleness cannot be judged safely,
    # so this always reports "none" (exit 1) rather than guess - the same
    # conservative choice cmd_apply's write path makes.
    [[ "$PRUNE_ANCHOR" -eq 1 ]] || return 1
    [[ -f "$CLAUDE_SETTINGS" ]] || return 1
    python3 - "$CLAUDE_SETTINGS" "${RULES[0]}" "${RULES[1]}" "${STALE_BASH_SUFFIXES[0]}" "${STALE_BASH_SUFFIXES[1]}" "$BASH_STABLE_PREFIX_MATCH" <<'PY'
import json, sys
path, current_share, current_isolate, suf_share, suf_isolate, prefix = sys.argv[1:7]
try:
    with open(path) as f:
        data = json.load(f)
except Exception:
    sys.exit(1)
allow = (data.get("permissions") or {}).get("allow") or []
current = {current_share, current_isolate}
suffixes = (suf_share, suf_isolate)
for a in allow:
    if a in current:
        continue
    if a.startswith(prefix) and a.endswith(suffixes):
        sys.exit(0)
sys.exit(1)
PY
}

cmd_check() {
    local missing=0
    for r in "${RULES[@]}"; do
        _allow_has "$r" || missing=1
    done
    # A stale same-plugin, prior-version rule also counts as "not converged
    # yet" so the SessionStart hook re-triggers `apply` (which prunes it) on
    # the very next session, rather than only after the NEXT version bump
    # ever fires `apply` again. (No-op when PRUNE_ANCHOR=0 - see above.)
    if _stale_bash_present; then
        missing=1
    fi
    # Informational only - mcp__odoo-semantic is NOT this step's rule to write
    # or require; its owner is odoo-semantic-mcp's connect command.
    if ! _odoo_semantic_present; then
        echo "i  mcp__odoo-semantic is not in permissions.allow[] - that is NOT this step's job; run /odoo-semantic-mcp:connect (step 5) to add it." >&2
    fi
    return "$missing"
}

# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------
cmd_apply() {
    # Opt-out: respect a user who turned auto-permissioning off (same escape
    # hatch as hooks/ensure-browser-permissions.sh).
    if [[ "${ODOO_AI_NO_AUTO_PERMS:-0}" == "1" ]]; then
        echo "Skipped state-root permission auto-allow (ODOO_AI_NO_AUTO_PERMS=1). Re-run: /odoo-ai-agents:odoo-setup permissions"
        return 0
    fi

    if [[ ! -f "$LIB" ]]; then
        echo "x lib not found at $LIB - cannot edit permissions. Install the plugin fully." >&2
        return 1
    fi

    # Confirmation gate (mirrors 30-permissions.sh / connect.md step 5). Honour
    # non-interactive mode: if stdin is not a TTY, proceed (the calling agent
    # gates upstream).
    local reply="Y"
    if [[ -t 0 ]]; then
        printf 'Auto-allow state-root planning permissions in %s? [Y/n] ' "$CLAUDE_SETTINGS"
        read -r reply || reply="Y"
        reply="${reply:-Y}"
    fi
    case "$reply" in
        n|N|no|No|NO|skip)
            echo "Skipped state-root permission auto-allow. You can re-run: /odoo-ai-agents:odoo-setup permissions"
            return 0
            ;;
    esac

    local i r rc had_io_error=0
    for i in "${!RULES[@]}"; do
        r="${RULES[$i]}"
        # The two Bash(...) rules are version-pinned (embed $PLUGIN_ROOT). When
        # PRUNE_ANCHOR=1 (a real MAJOR.MINOR.PATCH version segment was found -
        # see above), writing them also PRUNES any stale rule for a PRIOR
        # version of THIS SAME plugin (json-ensure-allow-pruning, anchored to
        # BASH_STABLE_PREFIX_MATCH so it can never touch a different plugin's
        # rule for an identically-suffixed script). When PRUNE_ANCHOR=0 (a
        # --plugin-dir dev checkout with no version segment to anchor on),
        # pruning is skipped and this falls back to plain add-only - see the
        # PRUNE_ANCHOR comment above for why that is the safe choice. The
        # Read/Edit rules key off $ODOO_AI_HOME (not $PLUGIN_ROOT) and never
        # drift across versions, so plain json-ensure-allow is always
        # sufficient for them. Exit contract for both calls: 0 = success /
        # already converged, 1 = general I/O error, 2 = invalid JSON.
        set +e
        if [[ "$r" == Bash\(* && "$PRUNE_ANCHOR" -eq 1 ]]; then
            python3 "$LIB" json-ensure-allow-pruning "$CLAUDE_SETTINGS" "$r" "${STALE_BASH_SUFFIXES[$i]}" "$BASH_STABLE_PREFIX_MATCH"
        else
            python3 "$LIB" json-ensure-allow "$CLAUDE_SETTINGS" "$r"
        fi
        rc=$?
        set -e
        if [[ "$rc" -eq 2 ]]; then
            echo "x $CLAUDE_SETTINGS is not valid JSON. Fix it by hand (or restore a .bak.*) and re-run." >&2
            return 2
        elif [[ "$rc" -eq 1 ]]; then
            echo "x failed to add '$r' to $CLAUDE_SETTINGS (I/O error). Skipping this rule." >&2
            had_io_error=1
        fi
    done
    if [[ "$had_io_error" -eq 1 ]]; then
        echo "! some state-root permission rules could not be written - re-run after fixing the cause." >&2
        return 1
    fi

    echo "ok state-root planning permissions allow-listed in $CLAUDE_SETTINGS:"
    for r in "${RULES[@]}"; do
        echo "   $r"
    done
    echo "i  because permissions are finalized BEFORE SessionStart hooks run, RESTART Claude Code once (or start a new session) for them to take effect this session."

    # Self-verify.
    if cmd_check >/dev/null; then
        echo "ok self-verify: all state-root permission rules confirmed present."
    else
        echo "x self-verify failed - re-run '$(basename "$0") check' to see what is still missing." >&2
        return 1
    fi
}

# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------
case "${1:-}" in
    describe) cmd_describe ;;
    check)    cmd_check ;;
    apply)    cmd_apply ;;
    *) echo "Usage: $(basename "$0") {describe|check|apply}" >&2; exit 2 ;;
esac
