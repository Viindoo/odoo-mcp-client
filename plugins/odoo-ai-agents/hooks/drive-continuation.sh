#!/usr/bin/env bash
# drive-continuation.sh - Stop ADVISORY nudge for the drive-to-done loop.
#
# WHY: if the main agent ends its turn while a run is still NEEDS_NEXT, remind it (and the
# human) that the run is unfinished and can be advanced. This keeps drive-to-done resilient
# WITHOUT coercion.
#
# HARD CONTRACT: this hook NEVER blocks the main agent's turn-end. It emits
#   {continue:true, systemMessage:...} only - an advisory line. (Using {decision:"block"} here
#   would trap the main agent, which is forbidden.) The human + main agent keep the right to
#   stop at any time. Self-gates to silence when no run is active; loop-safe via stop_hook_active.
#   Said ONCE per run state per context window: while the same run sits on the same node, the
#   reminder already in the transcript since the last compaction is not repeated on every later
#   turn end (hooks/advice-once.sh); a run that moves to another node is a new reminder.

set -uo pipefail
_pass() { exit 0; }

command -v jq >/dev/null 2>&1 || _pass
INPUT="$(cat 2>/dev/null || true)"
[[ -n "$INPUT" ]] || _pass

# Loop-safe: if we already nudged on this stop cycle, stay quiet.
STOP_ACTIVE="$(printf '%s' "$INPUT" | jq -r '.stop_hook_active // false' 2>/dev/null || echo false)"
[[ "$STOP_ACTIVE" == "true" ]] && _pass

CWD="$(printf '%s' "$INPUT" | jq -r '.cwd // empty' 2>/dev/null || true)"
PROJ_DIR="${CWD:-${CLAUDE_PROJECT_DIR:-.}}"
# ISOLATE state dir (Problem 3 - snippets/state-root-resolution.md), resolved FROM the
# hook's own project cwd so the run-*.json glob below is scoped per worktree (cnt==1
# holds independently in each worktree - the C-1 regression fix). CRITICAL RESILIENCE:
# this hook must NEVER hard-fail or block a session - a resolver refusal (non-git, no
# marker) or any error (missing script, no CLAUDE_PLUGIN_ROOT) silently falls back to
# the legacy project-relative path. This fallback is the SANCTIONED "Advisory-glob
# exception" (V-50, state-root-resolution.md) - a read-only glob that only ever degrades
# to silence, never a write; do not copy this pattern into a call site that writes.
RUN_DIR="$(cd "$PROJ_DIR" 2>/dev/null && bash "${CLAUDE_PLUGIN_ROOT:-}/scripts/lib/resolve_project_dir.sh" isolate 2>/dev/null || true)"
[[ -n "$RUN_DIR" ]] || RUN_DIR="${PROJ_DIR}/.odoo-ai"
active_run=""; run_id=""; cursor=""; cnt=0
shopt -s nullglob
for rf in "$RUN_DIR"/run-*.json; do
  st="$(jq -r '.status // empty' "$rf" 2>/dev/null || true)"
  if [[ "$st" == "NEEDS_NEXT" ]]; then
    active_run="$rf"; cnt=$((cnt+1))
    # A run record without run_id is still named: by its file, run-<id>.json (the run-harness
    # naming), never as '?' - a reminder that cannot say WHICH run is unfinished is noise.
    _file_id="${rf##*/run-}"; _file_id="${_file_id%.json}"
    run_id="$(jq -r --arg f "$_file_id" '.run_id // $f' "$rf" 2>/dev/null || printf '%s' "$_file_id")"
    cursor="$(jq -r '.cursor // "?"' "$rf" 2>/dev/null || echo '?')"
  fi
done
shopt -u nullglob
# 0 -> no active run; >1 -> ambiguous which to name, stay silent (degrade-safe). Only nudge on exactly one.
[[ "$cnt" -eq 1 ]] || _pass

MSG="Run '$run_id' is still NEEDS_NEXT (next node: $cursor). If you intend to keep going, advance it via run-harness (read $RUN_DIR/run-*.json). To stop, say so - this is only a reminder, not a block."

# Already in the context (the same run on the same node) -> stay quiet. Helper unreadable -> emit.
_HOOK_DIR="${BASH_SOURCE[0]%/*}"
if [[ -r "$_HOOK_DIR/advice-once.sh" ]]; then
  # shellcheck source=/dev/null
  . "$_HOOK_DIR/advice-once.sh"
  TRANSCRIPT="$(printf '%s' "$INPUT" | jq -r '.transcript_path // empty' 2>/dev/null || true)"
  _advice_seen "$TRANSCRIPT" "$MSG" && _pass
fi

jq -cn --arg m "$MSG" '{continue:true, systemMessage:$m}'
exit 0
