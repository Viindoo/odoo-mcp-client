#!/usr/bin/env bash
# block-handback-with-live-lease.sh - PreToolUse HARD DENY on `SubagentHandback`. The report-time
# half of the instance-teardown gate (snippets/resource-teardown-contract.md T1 "The three exits").
#
# WHY IT EXISTS: a subagent's report can travel in the `SubagentHandback` tool
# ({"message": "<report>"}), and the harness hands that report over the moment the call runs -
# BEFORE the subagent's turn ends, so BEFORE SubagentStop. enforce-teardown.sh's SubagentStop block
# therefore arrived after the caller already held (and could act on) a report whose lease was never
# given back; the subagent then released the lease, found a second SubagentHandback refused
# ("already delivered"), and had no report left to correct it with. Denying
# the handback itself is the only point where "the lease is given back BEFORE the report goes out"
# can still be enforced. A denied SubagentHandback delivers NOTHING - the tool_result is an error
# and the caller receives no message (verified live, see tests/test_handback_gate.py).
#
# WHAT IT REFUSES: a SUBAGENT's SubagentHandback while (a) a lease it OBTAINED itself
# (hooks/lease-correlation.sh _lease_owned_tokens - the SAME correlation the teardown gate and the
# lease-mutation gate use) is (b) LIVE and non-shared per the allocator's own verdict
# (hooks/teardown-check.sh - the SAME check and refusal text enforce-teardown.sh emits), and (c) the
# message being handed back does not forward THAT lease - an INSTANCE_HANDLE carrying its own
# lease_token in the `next.inputs` of its closed `continuation` block (hooks/final-report.sh
# _continuation_unforwarded_tokens - the SAME per-lease fence parse). Forwarding one lease's handle
# never clears a second live lease. The refusal names the three exits and tells
# the agent to call SubagentHandback again once one is taken. Like the SubagentStop gate it is
# STATUS-BLIND: DONE, NEEDS_NEXT, BLOCKED, NEEDS_CONTEXT and no status at all are gated alike.
#
# PAYLOAD: PreToolUse carries agent_id / agent_type and the SESSION transcript_path, but no
# agent_transcript_path (observed live); the subagent's own transcript is resolved by
# lease-correlation.sh _lease_agent_transcript from the harness's on-disk layout.
#
# FAILS OPEN ON EVERY UNCERTAINTY (the _pass convention this plugin's hooks share): no jq, empty or
# unparseable stdin, another tool, a caller that is not identifiably a subagent, an unreadable
# agent transcript or shared helper, no python3 / allocator, an allocator error, a lease with no
# verdict. A false deny traps a finished report, so every branch prefers a false negative;
# enforce-teardown.sh at SubagentStop remains the backstop.
#
# SCHEMA: hookSpecificOutput.permissionDecision = "deny" with a permissionDecisionReason. Exit code
# is ALWAYS 0; a PreToolUse hook that hard-fails is an outage.

set -uo pipefail
_pass() { exit 0; }

command -v jq >/dev/null 2>&1 || _pass
INPUT="$(cat 2>/dev/null || true)"
[[ -n "$INPUT" ]] || _pass
printf '%s' "$INPUT" | jq -e . >/dev/null 2>&1 || _pass

TOOL="$(printf '%s' "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || true)"
[[ "$TOOL" == "SubagentHandback" ]] || _pass

# Caller must be a subagent - ANY populated agent_id/agent_type, the identity signal every
# PreToolUse gate here uses. The ROOT is never denied.
AGENT_ID="$(printf '%s' "$INPUT" | jq -r '.agent_id // .agentId // empty' 2>/dev/null || true)"
AGENT_TYPE="$(printf '%s' "$INPUT" | jq -r '.agent_type // .agentType // empty' 2>/dev/null || true)"
[[ -n "$AGENT_ID" || -n "$AGENT_TYPE" ]] || _pass

_HOOK_DIR="${BASH_SOURCE[0]%/*}"
for _lib in lease-correlation.sh final-report.sh teardown-check.sh; do
  [[ -r "$_HOOK_DIR/$_lib" ]] || _pass
  # shellcheck source=/dev/null
  . "$_HOOK_DIR/$_lib"
done

TRANSCRIPT="$(_lease_agent_transcript "$INPUT")"
if [[ -z "$TRANSCRIPT" ]]; then
  echo "block-handback-with-live-lease: no readable agent transcript; teardown check skipped (fail open)" >&2
  _pass
fi

OWN_TOKENS="$(_lease_owned_tokens "$TRANSCRIPT")"
[[ -n "$OWN_TOKENS" ]] || _pass   # obtained nothing: a pure consumer, whatever it quotes

# The report being handed back IS this call's message: its closed continuation fence is what the
# caller will read. A lease forwarded there in its own INSTANCE_HANDLE is the named-catcher handoff
# (exit 3) - for that lease only.
MESSAGE="$(printf '%s' "$INPUT" | jq -r '.tool_input.message // empty | if type == "string" then . else tojson end' 2>/dev/null || true)"
CONT_BLOCK="$(_continuation_block "$MESSAGE")"
# Per lease: only a token the message forwards in its OWN INSTANCE_HANDLE (next.inputs) has a
# named catcher; forwarding one lease never clears a second one.
UNFWD_TOKENS="$(_continuation_unforwarded_tokens "$CONT_BLOCK" "$OWN_TOKENS")"
[[ -n "$UNFWD_TOKENS" ]] || _pass
STATUS_KEY="$(_continuation_status_key "$(_continuation_status "$CONT_BLOCK")")"

if [[ -n "$STATUS_KEY" ]]; then
  CLAIM="called SubagentHandback with a report on \`status: $STATUS_KEY\` and no \`INSTANCE_HANDLE\` forwarded for the lease(s) below"
else
  CLAIM='called SubagentHandback with a report that has NO `status` in a closed `continuation` block and no `INSTANCE_HANDLE` forwarded for the lease(s) below'
fi
CLOSING='This SubagentHandback was NOT delivered - your caller has received nothing yet. Take one of the three exits, put the closed `continuation` block (for exit 3: one INSTANCE_HANDLE per lease you hand off, each carrying the lease_token of that lease, in next.inputs) inside the message itself, and then call SubagentHandback again with your full report.'

REASON="$(_teardown_block_reason "$UNFWD_TOKENS" "$CLAIM" "$CLOSING")" || _pass
[[ -n "$REASON" ]] || _pass

jq -cn --arg reason "$REASON" \
  '{hookSpecificOutput:{hookEventName:"PreToolUse", permissionDecision:"deny", permissionDecisionReason:$reason}}'
exit 0
