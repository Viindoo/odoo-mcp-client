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
# Root cause this fixes: `odoo-planner` / intake Phase P all
# resolve and write under $ODOO_AI_HOME on every planning/run-DAG turn. Without
# this permission pre-grant, a fresh install prompts for the SAME handful of
# Bash/Read/Edit calls on every session - not a Plan-Mode problem (see
# snippets/planning-gate-contract.md § One Plan-Mode gate per request for that fix), a
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
#   - Never writes the Odoo Semantic rule (`mcp__plugin_odoo-semantic-mcp_odoo-semantic`, or `mcp__odoo-semantic` for a hand-registered server) - that permission's owner is
#     plugins/odoo-semantic-mcp/commands/connect.md step 5; `check` below only
#     REPORTS its absence and points there.
#   - The Bash rules name ONE command each: `bash <plugin dir>/scripts/lib/resolve_project_dir.sh`
#     followed by `share` or `isolate`, and one trailing ` *` (see VERSION-KEYED RULES below for
#     why the trailing `*` is there). No other wildcard ever appears in a Bash rule.
#
# VERSION-KEYED RULES (do NOT let this regress into "the current version's pair"): the Bash rules
# embed the plugin DIRECTORY of the session that runs the command, so a rule covers the sessions
# of that directory and no others. Sessions of several plugin versions share one settings file
# and each runs its own step at start, so a rule written as "the current version's" is replaced
# by every other version's start. Instead every rule is keyed to its directory:
#   - `apply` writes the two rules of EVERY installed version directory next to this one (the
#     sibling directories named MAJOR.MINOR.PATCH that hold the script) and of this one
#     (scripts/lib/plugin_version_rules.py `roots`), and removes only the rules of a version
#     directory that no longer holds the script (`prune`). A version never replaces a rule
#     another version wrote, so two versions from this one on never undo each other, and a newer
#     version's start repairs what an older one's pruning removed.
#   - The rule ends in ` *` after the argument: `Bash(bash <dir>/scripts/lib/resolve_project_dir.sh
#     share *)`. Claude Code documents that "A `*` at the end, with a space before it, also matches
#     the bare command" (https://code.claude.com/docs/en/permissions#wildcard-patterns), so it
#     covers `... share` exactly as the earlier exact rule did. The spelling is deliberate: the
#     releases that already shipped prune, at every start, each entry of this plugin's directory
#     that ends exactly with `resolve_project_dir.sh share)` or `... isolate)` and is not their
#     own - they do not recognise an entry that ends in ` *)`, so it survives them. A rule in the
#     earlier exact shape that an older session writes is left alone (it names a directory that
#     exists, and is removed with that directory).
#   - No `*` in the version position: a version-agnostic rule would match any directory under the
#     plugin's parent (not only this plugin's) and, written in the earlier exact shape's ending,
#     would be pruned by the shipped releases.
#   - A `--plugin-dir` dev checkout has no MAJOR.MINOR.PATCH last segment: only its own two rules
#     are written and nothing is pruned for it.
#
# SUBSUMPTION - do NOT add a rule the user already has (do NOT let this
# regress into over-eager clutter, mirroring the earlier over-eager PRUNE
# mistake above): the root cause of the accumulation complaint was never just
# "the Bash rules pile up across versions" - it is that on a machine whose
# `permissions.allow[]` already contains a blanket like `Bash(*)`, `Read`, or
# `Edit`, ALL FOUR of this step's rules were redundant the moment they were
# FIRST written, version-pinning aside. `apply` (below) checks EVERY rule
# against `config_merge.py json-rule-covered` before writing it, and adds
# NOTHING when an existing permission already grants it.
#   The two ways to be wrong here are NOT symmetric, and the bias is
#   deliberately conservative in only ONE direction: wrongly concluding
#   "already covered" silently withholds a needed permission (a missed
#   prompt with no error - BREAKS FUNCTION); wrongly concluding "not
#   covered" only writes one harmless redundant rule (visible, self-
#   correcting clutter - today's complaint, but the LESSER failure). So
#   `json-rule-covered` recognizes coverage ONLY for a small, explicitly
#   enumerated set of forms it can prove from Claude Code's own documented
#   semantics (https://code.claude.com/docs/en/permissions) - see that
#   subcommand's docstring in config_merge.py for the exact list and the
#   citation for each. Anything else, however blanket-looking, is treated as
#   NOT covering and the rule is still added.
#     One documented form was deliberately EXCLUDED despite looking like an
#     obvious blanket: a bare relative `Read(**)` / `Edit(**)` (no `//` or
#     `~/` anchor). Per the docs, "To allow all file access, use only the
#     tool name without parentheses: `Read`, `Edit`, or `Write`" - a
#     parenthesized `(**)` pattern is a gitignore-style path glob anchored at
#     the SESSION's actual working directory at match time, not a filesystem-
#     root blanket, so it cannot be proven ahead of time to contain an
#     absolute target like `$ODOO_AI_HOME` (which is not generally nested
#     under whatever directory a session happens to start in). Treating it as
#     coverage would risk silently withholding the permission on a session
#     started elsewhere - the worse failure mode above. See
#     `test_relative_double_star_is_not_treated_as_coverage_still_added`.
#   Pruning (above) and subsumption (this section) compose independently:
#   `cmd_apply` always removes the rules of removed plugin versions first,
#   REGARDLESS of whether the current rules then turn out to be covered and
#   get skipped - debris grants nothing a broader existing permission does
#   not already cover.
#
# EPHEMERAL STATE ROOTS - a throwaway root never gets rules, and old debris goes
# (decided by scripts/lib/state_root_permissions.py, the SSOT for both questions):
#   - A session whose $ODOO_AI_HOME is ephemeral - under a system temp directory, or
#     under the scratch directory of the default state root ($HOME/.odoo-ai/scratch) -
#     gets NO Read/Edit state-root rule: a test or scratch run used to append a pair per
#     run to the user's settings file, each pointing at a root that later vanished, and
#     nothing ever removed them. The Bash rules (keyed to the plugin directory, not the
#     state root) are unaffected.
#   - `apply` also removes the plugin's OWN earlier Read/Edit state-root pairs whose root
#     directory is gone, or lies under a system temp directory even if it still exists.
#     Only the exact pair shapes written here are recognised, an Edit(//<root>/projects/**)
#     rule being the signature; a user's own rule, and the session's own root, stay.
#   - ODOO_AI_TEMP_DIRS (an os.pathsep list) replaces the built-in system temp list; it
#     exists so tests can place a throwaway root outside the real temp directories.
#   - ODOO_AI_NO_AUTO_PERMS=1 disables all of it (nothing is written or pruned).
#
# LEASE GIVE-BACK RULES - besides the Bash, Read and Edit rules above, `apply` writes the exact allow rules
# `mcp__plugin_<plugin>_odoo-local__lease_release` and `..._lease_park` (listed by
# `scripts/lib/plugin_mcp_servers.py give-back`, the SSOT), so an agent can give back a lease
# its own session acquired without the auto-mode permission classifier deciding. No other
# odoo-local or odoo-media tool is granted. They are written and checked for every state root,
# an ephemeral one included, are skipped when an existing allow entry already grants them
# (the exact name, or the `odoo-local` server rule), and the pruning above never removes them.
#
# PUBLIC-ADDRESS RULES - the same way, `apply` writes the exact allow rules
# `mcp__plugin_<plugin>_odoo-local__instance_expose` and `..._instance_unexpose` (listed by
# `scripts/lib/plugin_mcp_servers.py expose`, the SSOT): giving a leased test instance a
# temporary public https address is routine here, and an auto-mode permission classifier may
# refuse it. Lease ownership stays enforced by hooks/block-unowned-lease-mutation.sh. Same
# handling as the give-back group.
#
# Subcommands:
#   describe   One-line description.
#   check      Exit 0 if every rule is either already present OR already
#              covered by an existing broader permission (config_merge.py
#              json-rule-covered), AND no Bash rule of a removed plugin
#              version remains; exit 1 otherwise - kept
#              consistent with what `apply` would actually do, so a rule
#              `apply` legitimately skips as covered never makes `check`
#              report the setup as incomplete (that mismatch would loop the
#              SessionStart hook). Also reports (non-blocking) whether
#              the Odoo Semantic rule is present, pointing at its real owner.
#   apply      Ask [Y/n] (honors ODOO_AI_NO_AUTO_PERMS=1 opt-out); first
#              removes the Bash rules of removed plugin versions
#              (plugin_version_rules.py prune); then for every rule (the
#              Bash rules of each installed version, the Read/Edit rules, the
#              lease give-back rules and the public-address rules), skips any rule config_merge.py json-rule-
#              covered reports as already granted, and idempotently appends
#              the rest via config_merge.py json-ensure-allow; prints what
#              was added/skipped, instructs one restart, and self-verifies by
#              re-running check.
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
ROOT_LIB="$SCRIPT_DIR/../lib/state_root_permissions.py"
SERVERS_LIB="$SCRIPT_DIR/../lib/plugin_mcp_servers.py"

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

# The version directories the Bash rules are written for come from
# scripts/lib/plugin_version_rules.py (see VERSION-KEYED RULES above): this plugin directory,
# plus - when its last path segment is a MAJOR.MINOR.PATCH version - every sibling version
# directory that holds the script. A `--plugin-dir` dev checkout has no version segment and gets
# its own two rules only.
VERSIONS_LIB="$SCRIPT_DIR/../lib/plugin_version_rules.py"

# Resolve the state root exactly like scripts/lib/resolve_project_dir.sh's own
# Tier-1 root convention: $ODOO_AI_HOME, defaulting to $HOME/.odoo-ai.
ODOO_AI_HOME="${ODOO_AI_HOME:-$HOME/.odoo-ai}"
ODOO_AI_HOME="${ODOO_AI_HOME%/}"

# The state-root rules (SSOT for this step). Read/Edit use the `//<abs-path>`
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

# The Bash rules: `share` and `isolate` for every version directory (own directory first). The
# trailing ` *` is the spelling documented to cover the bare command and unknown to the pruning of
# earlier releases (VERSION-KEYED RULES above). Without the helper only this directory is granted.
BASH_ROOTS=()
if [[ -f "$VERSIONS_LIB" ]]; then
    while IFS= read -r _root; do
        [[ -n "$_root" ]] && BASH_ROOTS+=("$_root")
    done < <(python3 "$VERSIONS_LIB" roots "$PLUGIN_ROOT" "$RESOLVE_SCRIPT_REL" 2>/dev/null || true)
fi
if [[ "${#BASH_ROOTS[@]}" -eq 0 ]]; then
    BASH_ROOTS=("$PLUGIN_ROOT")
fi
BASH_RULES=()
for _root in "${BASH_ROOTS[@]}"; do
    BASH_RULES+=("Bash(bash ${_root}/${RESOLVE_SCRIPT_REL} share *)"
                 "Bash(bash ${_root}/${RESOLVE_SCRIPT_REL} isolate *)")
done

RULES=(
    "${BASH_RULES[@]}"
    "Read(/${ODOO_AI_HOME}/**)"
    "Edit(/${ODOO_AI_HOME}/projects/**)"
)

# Whether this session's state root may hold permission rules at all (see EPHEMERAL STATE
# ROOTS above). An unusable helper counts as "not ephemeral": a missing helper must never
# withhold the rules.
_root_is_ephemeral() {
    [[ -f "$ROOT_LIB" ]] || return 1
    python3 "$ROOT_LIB" ephemeral "$ODOO_AI_HOME" >/dev/null 2>&1
}

# The lease give-back rules: the full tool-call names of `lease_release` and `lease_park` of
# the `odoo-local` server, written as exact allow rules so that returning a lease the agent's
# own session acquired never depends on the auto-mode permission classifier (the plugin's
# PermissionRequest hook does not run in auto mode). Lease ownership stays enforced by the
# PreToolUse hook block-unowned-lease-mutation.sh and by the allocator. The names come from
# scripts/lib/plugin_mcp_servers.py (SSOT). They are a group of their own: written and checked
# whatever the state root is (an ephemeral root included), never pruned, and skipped when an
# existing allow entry already grants them (the exact name or the whole `odoo-local` server).
GIVE_BACK_RULES=()
if [[ -f "$SERVERS_LIB" ]]; then
    while IFS= read -r _gb_rule; do
        [[ -n "$_gb_rule" ]] && GIVE_BACK_RULES+=("$_gb_rule")
    done < <(python3 "$SERVERS_LIB" give-back 2>/dev/null || true)
fi

# The public-address rules: the full tool-call names of `instance_expose` and `instance_unexpose`
# (a leased test instance gets a temporary https address through a Cloudflare Quick Tunnel and
# loses it again), written as exact allow rules for the same reason as the give-back group: an
# auto-mode permission classifier may refuse "expose a local server to the internet". Same
# handling as the give-back group (every state root, never pruned, skipped when covered). The
# names come from scripts/lib/plugin_mcp_servers.py (`expose`, SSOT).
EXPOSE_RULES=()
if [[ -f "$SERVERS_LIB" ]]; then
    while IFS= read -r _ex_rule; do
        [[ -n "$_ex_rule" ]] && EXPOSE_RULES+=("$_ex_rule")
    done < <(python3 "$SERVERS_LIB" expose 2>/dev/null || true)
fi

# Every rule this step manages: the Bash, Read and Edit rules, then the give-back group, then the
# public-address group.
ALL_RULES=("${RULES[@]}" ${GIVE_BACK_RULES[@]+"${GIVE_BACK_RULES[@]}"} ${EXPOSE_RULES[@]+"${EXPOSE_RULES[@]}"})

# Index range of the Read/Edit state-root rules in ALL_RULES (the Bash rules come first; the
# give-back and public-address groups follow). Only this range is withheld for an ephemeral state root.
STATE_RULES_FROM=${#BASH_RULES[@]}
STATE_RULES_TO=${#RULES[@]}

_is_state_rule_index() {
    [[ "$1" -ge "$STATE_RULES_FROM" && "$1" -lt "$STATE_RULES_TO" ]]
}

# ---------------------------------------------------------------------------
# describe
# ---------------------------------------------------------------------------
cmd_describe() {
    echo "Auto-allow the state-root Bash/Read/Edit rules (planning + intake Phase P) in Claude permissions"
}

# ---------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------
_rule_satisfied() {
    # $1 = rule string. Exit 0 if EITHER it is already exactly in
    # permissions.allow[] OR an existing entry already provably covers it
    # (config_merge.py json-rule-covered - see the SUBSUMPTION section
    # above for the exact enumerated forms and the conservative bias).
    # Replaces a bare exact-membership check so `check` stays consistent
    # with what `apply` would actually do: a rule `apply` legitimately
    # skips as covered must not make `check` report incompleteness.
    _rule_covered "$1"
}

# Exit 0 if the settings file already grants rule $1 (an MCP rule of the plugin's local server is judged by
# plugin_mcp_servers.py, every other rule by config_merge.py json-rule-covered).
_rule_covered() {
    if [[ "$1" == mcp__* ]]; then
        [[ -f "$SERVERS_LIB" ]] || return 1
        python3 "$SERVERS_LIB" give-back-covered "$CLAUDE_SETTINGS" "$1" >/dev/null 2>&1
    else
        [[ -f "$LIB" ]] || return 1
        python3 "$LIB" json-rule-covered "$CLAUDE_SETTINGS" "$1" >/dev/null 2>&1
    fi
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
PREFIXES = ("mcp__plugin_odoo-semantic-mcp_odoo-semantic", "mcp__odoo-semantic")
sys.exit(0 if any(a == p or a.startswith(p + "__") for a in allow for p in PREFIXES) else 1)
PY
}

_removed_versions_present() {
    # Exit 0 iff permissions.allow[] holds a Bash rule of this plugin's script that names a version
    # directory which no longer holds the script (plugin_version_rules.py prune --check).
    [[ -f "$VERSIONS_LIB" && -f "$CLAUDE_SETTINGS" ]] || return 1
    python3 "$VERSIONS_LIB" prune "$CLAUDE_SETTINGS" "$PLUGIN_ROOT" "$RESOLVE_SCRIPT_REL" --check >/dev/null 2>&1
}

_stale_roots_present() {
    [[ -f "$ROOT_LIB" && -f "$CLAUDE_SETTINGS" ]] || return 1
    python3 "$ROOT_LIB" prune "$CLAUDE_SETTINGS" "$ODOO_AI_HOME" --check >/dev/null 2>&1
}

cmd_check() {
    local missing=0 i ephemeral=0
    _root_is_ephemeral && ephemeral=1
    for i in "${!ALL_RULES[@]}"; do
        # An ephemeral state root is never granted Read/Edit rules, so it cannot lack them.
        if [[ "$ephemeral" -eq 1 ]] && _is_state_rule_index "$i"; then
            continue
        fi
        _rule_satisfied "${ALL_RULES[$i]}" || missing=1
    done
    # Debris of an earlier ephemeral or vanished root also counts as "not converged".
    if _stale_roots_present; then
        missing=1
    fi
    # A rule of a removed plugin version also counts as "not converged yet", so the SessionStart
    # hook re-triggers `apply` (which prunes it) on the next session.
    if _removed_versions_present; then
        missing=1
    fi
    # Informational only - mcp__odoo-semantic is NOT this step's rule to write
    # or require; its owner is odoo-semantic-mcp's connect command.
    if ! _odoo_semantic_present; then
        echo "i  mcp__plugin_odoo-semantic-mcp_odoo-semantic is not in permissions.allow[] - that is NOT this step's job; run /odoo-semantic-mcp:connect (step 5) to add it." >&2
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

    local i r rc out had_io_error=0 added=0 ephemeral=0
    _root_is_ephemeral && ephemeral=1

    # Remove the plugin's own Read/Edit rules of roots that are gone or ephemeral
    # (see EPHEMERAL STATE ROOTS above). Unconditional.
    if [[ -f "$ROOT_LIB" ]]; then
        set +e
        python3 "$ROOT_LIB" prune "$CLAUDE_SETTINGS" "$ODOO_AI_HOME"
        rc=$?
        set -e
        if [[ "$rc" -eq 2 ]]; then
            echo "x $CLAUDE_SETTINGS is not valid JSON. Fix it by hand (or restore a .bak.*) and re-run." >&2
            return 2
        elif [[ "$rc" -ne 0 ]]; then
            echo "x failed to prune stale state-root rules in $CLAUDE_SETTINGS." >&2
            had_io_error=1
        fi
    fi

    # Remove the Bash rules of plugin versions that are no longer installed (VERSION-KEYED
    # RULES above). Unconditional, whether or not the rules below turn out to be covered.
    if [[ -f "$VERSIONS_LIB" ]]; then
        set +e
        python3 "$VERSIONS_LIB" prune "$CLAUDE_SETTINGS" "$PLUGIN_ROOT" "$RESOLVE_SCRIPT_REL"
        rc=$?
        set -e
        if [[ "$rc" -eq 2 ]]; then
            echo "x $CLAUDE_SETTINGS is not valid JSON. Fix it by hand (or restore a .bak.*) and re-run." >&2
            return 2
        elif [[ "$rc" -ne 0 ]]; then
            echo "x failed to prune rules of removed plugin versions in $CLAUDE_SETTINGS." >&2
            had_io_error=1
        fi
    fi

    for i in "${!ALL_RULES[@]}"; do
        r="${ALL_RULES[$i]}"

        if [[ "$ephemeral" -eq 1 ]] && _is_state_rule_index "$i"; then
            echo "i  $ODOO_AI_HOME is an ephemeral state root - not adding $r."
            continue
        fi

        # Subsumption check: skip the add entirely when an existing
        # allow[] entry already provably covers this rule (see the
        # SUBSUMPTION section above for the exact enumerated forms and why
        # the bias only ever runs toward "add", never toward "skip", on
        # anything not in that small list).
        if _rule_covered "$r"; then
            echo "i  $r already covered by an existing permission - not adding."
            continue
        fi

        # Add (idempotent).
        set +e
        out="$(python3 "$LIB" json-ensure-allow "$CLAUDE_SETTINGS" "$r")"
        rc=$?
        set -e
        printf '%s\n' "$out"
        [[ "$out" == *"Added "* ]] && added=1
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

    # Only a run that really added a rule needs the restart; a prune-only or
    # ephemeral-root run changes nothing this session depends on.
    if [[ "$added" -eq 1 ]]; then
        echo "ok state-root planning permissions allow-listed in $CLAUDE_SETTINGS:"
        for r in "${ALL_RULES[@]}"; do
            echo "   $r"
        done
        echo "i  because permissions are finalized BEFORE SessionStart hooks run, RESTART Claude Code once (or start a new session) for them to take effect this session."
    fi

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
# --- interpreter preflight ------------------------------------------------------------------
# Same shape as 30-permissions.sh: the settings file is parsed and rewritten through python,
# so a broken interpreter silently produces an unchanged file rather than an error.
# SSOT: scripts/lib/require_python.sh. `describe` and the usage arm are pure text and stay
# runnable on a host with no python at all.
_REQ_PY="$SCRIPT_DIR/../lib/require_python.sh"
if [[ -r "$_REQ_PY" ]]; then
    # shellcheck source=/dev/null
    . "$_REQ_PY"
    case "${1:-}" in
        describe|-h|--help|"") ;;
        *) require_python3 "$(basename "$0") ${1:-}" json || exit 2 ;;
    esac
fi

case "${1:-}" in
    describe) cmd_describe ;;
    check)    cmd_check ;;
    apply)    cmd_apply ;;
    *) echo "Usage: $(basename "$0") {describe|check|apply}" >&2; exit 2 ;;
esac
