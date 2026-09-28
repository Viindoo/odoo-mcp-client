# teardown-check.sh - SOURCED helper (not a hook): the ONE implementation of the instance-teardown
# check - "does this agent still hold a LIVE, non-shared lease it obtained itself, and what must it
# do about it". Two gates run it and must never disagree:
#   - enforce-teardown.sh (SubagentStop): blocks the subagent's turn end.
#   - block-handback-with-live-lease.sh (PreToolUse on SubagentHandback): denies delivering the
#     report while the lease is held. The report is delivered the moment SubagentHandback runs,
#     BEFORE SubagentStop, so a SubagentStop block alone arrives after the caller already acted on
#     a report whose lease was never given back.
# Which leases the agent OBTAINED is hooks/lease-correlation.sh's question; which of them its report
# forwards (per lease, in next.inputs) is hooks/final-report.sh's. This file only asks the allocator.
#
# Ground truth is the allocator's own VERDICT (`allocator.py list --with-verdict`), never the
# transcript and never a liveness rule copied here: the verdict is the SSOT for "would anything
# reclaim this lease", and a second copy is what drifted before (a hard-coded TTL fallback that
# silently disagreed with the allocator the day its default changed).
#
# Fails open: no python3, no CLAUDE_PLUGIN_ROOT/scripts/lib/allocator.py, an allocator error, a
# row with no verdict - every one prints nothing and returns non-zero.

# One `allocator.py list` call, JSON envelope in, the lease array out ("" on any failure).
_alloc_list_json() {
  local alloc="${CLAUDE_PLUGIN_ROOT:-}/scripts/lib/allocator.py" out
  out="$(timeout 5 python3 "$alloc" list --with-verdict --show-tokens --format json "$@" \
         2>/dev/null || true)"
  printf '%s' "$out" | jq -c 'select(.ok == true) | (.fields.leases // [])' 2>/dev/null || true
}

# $1 = the tokens the agent obtained and has NOT forwarded (newline-separated - the caller drops each
# token its report hands to a named catcher, final-report.sh _continuation_unforwarded_tokens), $2 =
# what the agent just did (a clause completing "this subagent ..."), $3 = an optional closing
# sentence for the gate's own situation, $4 = which exits are still open: `all` (the default - the
# report has not reached the caller yet) or `give-back` (the report was ALREADY delivered through
# SubagentHandback, so its fence is final and only release or park can still clear a lease).
# Prints the refusal and returns 0 when at least one of those leases is LIVE per the verdict;
# prints nothing and returns 1 otherwise.
_teardown_block_reason() {
  local own_tokens="$1" claim="$2" closing="${3:-}" exits="${4:-all}"
  [[ -n "$own_tokens" ]] || return 1
  command -v python3 >/dev/null 2>&1 || return 1
  command -v jq >/dev/null 2>&1 || return 1
  [[ -n "${CLAUDE_PLUGIN_ROOT:-}" && -f "${CLAUDE_PLUGIN_ROOT}/scripts/lib/allocator.py" ]] || return 1

  # Candidate rows: exactly the leases named by the tokens this agent obtained.
  local cand="[]" part
  part="$(_alloc_list_json --tokens "$(printf '%s\n' "$own_tokens" | paste -sd, -)")"
  [[ -n "$part" ]] && cand="$part"

  # LIVE, per the allocator's verdict: running or reserved (never parked / orphaned /
  # reclaiming), not a shared render server (cross-session by design, never one consumer's to
  # drop - which is also why the lease a LAUNCHING series-mode instance_serve registers never
  # reaches this list: that path only ever registers a `shared` lease; the correlation still counts
  # it for block-unowned-lease-mutation.sh arm A4, so its launcher may stop it on an explicit user
  # request), and not something the AUTOMATIC reclaim would take anyway (`condemn_auto` set: a dead
  # or recycled server pid, an ended session past its grace) - such a lease leaks nothing a
  # dispatch could still fix. A PARKED lease is skipped on purpose, not as a hole: park already did
  # the RAM half of teardown, and blocking it would refuse the very exit this gate permits. A row
  # with no verdict at all (an allocator too old to give one) is uncertainty -> not blocked.
  local rows
  rows="$(printf '%s' "$cand" | jq -r '
      unique_by(.token) | .[]
      | select((.mode // "") != "shared")
      | select(.verdict != null)
      | select((.verdict.state // "") == "running" or (.verdict.state // "") == "reserved")
      | select(.verdict.condemn_auto == null)
      | [(.token // ""), ((.owner.run_id // .owner.session_id // "") | tostring),
         (.verdict.state // ""), (.verdict.protected_by // "none")]
      | map(if . == "" then "-" else . end) | @tsv' 2>/dev/null || true)"
  [[ -n "$rows" ]] || return 1

  # NOTE on the TSV shape: every field is forced NON-EMPTY ("-" stands for empty). `read` with a
  # whitespace IFS (tab included) silently SQUASHES an empty middle field into its neighbour.
  local lines="" n=0 token rid state prot rid_arg mcp_rid
  while IFS=$'\t' read -r token rid state prot; do
    [[ -n "$token" && "$token" != "-" ]] || continue
    n=$(( n + 1 ))
    if [[ "$rid" == "-" ]]; then rid_arg=""; mcp_rid=""; else rid_arg=" --run-id $rid"; mcp_rid=", run_id: \"$rid\""; fi
    lines="$lines"$'\n'"  lease token $token (owner run ${rid/#-/<none>}, $state, protected by $prot)"
    lines="$lines"$'\n'"    release: mcp__plugin_odoo-ai-agents_odoo-local__lease_release {lease_token: \"$token\"$mcp_rid}   |   park instead: mcp__plugin_odoo-ai-agents_odoo-local__lease_park {lease_token: \"$token\"$mcp_rid}"
    lines="$lines"$'\n'"    CLI fallback (only when the odoo-local tools are unavailable): python3 \"\${CLAUDE_PLUGIN_ROOT}/scripts/lib/allocator.py\" release $token$rid_arg   |   python3 \"\${CLAUDE_PLUGIN_ROOT}/scripts/lib/allocator.py\" park $token$rid_arg"
  done <<< "$rows"
  [[ "$n" -gt 0 ]] || return 1

  # THREE exits satisfy this gate, and all three are named here on purpose. The set is the one
  # declared in snippets/resource-teardown-contract.md T1 section "The three exits" (SSOT); this is a
  # SECOND COPY of it, kept in lockstep by tests/test_enforce_teardown.py rather than rendered from
  # the markdown at hook time. Naming only `release` would tell an agent that preserving a
  # just-built database is impossible, which is how instances got destroyed and rebuilt every
  # dispatch.
  #
  # AFTER A DELIVERED HANDBACK only the first two remain (`give-back`). The handoff is text in the
  # report's continuation fence, and that report already reached the caller: a second
  # SubagentHandback is refused, and no other message may carry a report
  # (snippets/spawner-completion-contract.md R3), so offering exit 3 or "report a continuation block"
  # there sends the agent after a report nobody will receive.
  local head give_back rest
  head="$(printf 'Resource-teardown gate: this subagent %s, but %d LIVE, non-shared instance lease(s) that THIS subagent obtained itself (acquired or adopted by your own calls - read from your own tool calls and their results, never from a run id and never from a lease_token you were handed and merely served or resumed, so a lease of your parent or a sibling is never listed here and is not yours to release) are still held in the allocator ledger. Each is a detached Odoo server process or database that outlives this dispatch until reclaimed.' "$claim" "$n")"
  give_back='1) release - stops the whole server process group, then drops the DB. 2) park the lease (`lease_park`, or `allocator.py park`; NOT the turn-parking discipline of the same name) - stops the same process group (so the RAM is freed) but KEEPS the database, filestore and ports, so a later dispatch resumes it instead of rebuilding; use it when the DB is still wanted - park DEFERS the eventual drop, it never cancels it, and it reports the drop_on_release flag it left untouched so you can see whether the final release will still destroy that DB.'
  if [[ "$exits" == "give-back" ]]; then
    rest="Clear EACH before you stop, by ONE of the two exits still open to you:$lines"$'\n'"$give_back"
  else
    rest="Clear EACH before your terminal status, by ONE of the three exits:$lines"$'\n'"$give_back"' 3) handoff - forward INSTANCE_HANDLE (that lease'"'"'s own lease_token + run_id) in your continuation `next.inputs` to a NAMED catcher, which leaves the instance running for it; forwarding one lease'"'"'s handle clears only that lease. Then report a `continuation` block whose `status` is one of the contract values. If exits 1 and 2 are UNAVAILABLE to you - the allocator errored, a process refuses to die, or the HARNESS DENIED the give-back call before it ran - do NOT fall back to a bare stopped-run report. Exit 3 is always available: it is text in your own continuation fence, needs no tool, no permission and no live process, and when teardown is what failed the named catcher is your DISPATCHING CALLER. Forward INSTANCE_HANDLE (lease_token + run_id) in next.inputs to it, state in your report that teardown was denied and quote the exact refusal, and keep your BLOCKED or NEEDS_CONTEXT status - the status is not what this gate reads.'
  fi
  printf '%s %s%s' "$head" "$rest" "${closing:+ $closing}"
  return 0
}
