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

set -uo pipefail
_pass() { exit 0; }

command -v jq >/dev/null 2>&1 || _pass
INPUT="$(cat 2>/dev/null || true)"
[[ -n "$INPUT" ]] || _pass

# Loop-safe: if we already nudged on this stop cycle, stay quiet.
STOP_ACTIVE="$(printf '%s' "$INPUT" | jq -r '.stop_hook_active // false' 2>/dev/null || echo false)"
[[ "$STOP_ACTIVE" == "true" ]] && _pass

CWD="$(printf '%s' "$INPUT" | jq -r '.cwd // empty' 2>/dev/null || true)"
RUN_DIR="${CWD:-${CLAUDE_PROJECT_DIR:-.}}/.odoo-ai"
active_run=""; run_id=""; cursor=""; cnt=0
shopt -s nullglob
for rf in "$RUN_DIR"/run-*.json; do
  st="$(jq -r '.status // empty' "$rf" 2>/dev/null || true)"
  if [[ "$st" == "NEEDS_NEXT" ]]; then
    active_run="$rf"; cnt=$((cnt+1))
    run_id="$(jq -r '.run_id // "?"' "$rf" 2>/dev/null || echo '?')"
    cursor="$(jq -r '.cursor // "?"' "$rf" 2>/dev/null || echo '?')"
  fi
done
shopt -u nullglob
# 0 → no active run; >1 → ambiguous which to name, stay silent (degrade-safe). Only nudge on exactly one.
[[ "$cnt" -eq 1 ]] || _pass

jq -cn --arg m "Run '$run_id' is still NEEDS_NEXT (next node: $cursor). If you intend to keep going, advance it via run-harness (read .odoo-ai/run-*.json). To stop, say so - this is only a reminder, not a block." \
  '{continue:true, systemMessage:$m}'
exit 0
