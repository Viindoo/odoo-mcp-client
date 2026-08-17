#!/usr/bin/env bash
# block-nested-background-spawn.sh - PreToolUse HARD DENY. The plugin's FIRST PreToolUse refusal,
# and the only runtime mechanism behind the R0/R1 dispatch-physics rule in
# ${CLAUDE_PLUGIN_ROOT}/snippets/spawner-completion-contract.md.
#
# WHAT IT REFUSES: a SUBAGENT launching a child in the BACKGROUND. That is the one unrecoverable
# dispatch move in this harness - measured, not assumed: only the ROOT conversation is ever resumed
# when a background child finishes; a child holds no address for its launcher; and a child's
# fallback message aimed at the root is ACCEPTED and delivered there, while the launcher that WAS
# waiting stays parked forever. The failure is silent - no error, no output, no one aware it stopped.
# Prose alone could not stop it (a coordinator that ignores the contract still stalls), so this hook
# makes the mistake impossible to EXPRESS rather than merely forbidden to make.
#
# DENY iff ALL THREE hold:
#   (a) the tool is a subagent spawn - `Agent` (the name this harness emits) or `Task` (the same
#       call's historical name in earlier CLI versions; matched defensively, costs nothing);
#   (b) the CALLER is itself a subagent - ANY of agent_id / agentId / agent_type / agentType is
#       populated. Same identity signal, same V-52 rule, as hooks/remind-delegate.sh: ANY populated
#       value means "in a subagent", with no `!= general-purpose` carve-out;
#   (c) the launch would be BACKGROUNDED - `run_in_background` is `true` OR ABSENT.
#
# (c) IS THE SUBTLE ONE. Background is the spawn tool's DEFAULT ("Agents run in the background by
# default ... Set to false to run this agent synchronously"), so an ABSENT flag means background,
# and it is the COMMON shape, not the rare one. A hook keyed on an explicit `true` alone would let
# through the majority of the calls it exists to stop while looking perfectly green.
#
# NEVER DENIES THE ROOT. No agent-identity field = the root conversation, the one context that IS
# resumed on a background child's completion. Backgrounding there is correct, and this plugin's
# whole drive-to-done fan-out depends on it - denying it would turn a fix into an outage.
#
# SCOPED TO THE SPAWN TOOL, never to the flag. `Bash` with `run_in_background: true` is exactly how
# agents/odoo-instance-ops.md launches every long Odoo build before its FOREGROUND wait-log call; a
# hook that keyed on the flag rather than on the TOOL would break that active-wait contract.
#
# SCHEMA: PreToolUse's own documented shape - hookSpecificOutput.permissionDecision = "deny" with a
# permissionDecisionReason. NOT the `{"decision":"block","reason":...}` shape hooks/enforce-teardown.sh
# emits: that is SubagentStop, a different event with a different schema, and emitting it here would
# produce a refusal the harness silently ignores. The plugin's other PreToolUse hook
# (remind-delegate.sh) is ADVISORY and always emits "defer" - that HARD CONTRACT is its own and is
# NOT weakened here; this is a separate, narrower hook whose entire purpose is to decide.
#
# THE REASON IS ACTIONABLE, NOT A SCOLDING. A refusal that only says "no" strands the caller, so it
# names the exact remedy (re-issue with run_in_background: false, whose result lands inside the
# caller's own turn), states that concurrency survives (several blocking launches in ONE message
# still run concurrently), and states the consequence being prevented.
#
# FAILS OPEN ON EVERY UNCERTAINTY (the _pass convention this plugin's hooks share): no jq, empty or
# unparseable stdin, a tool name outside the spawn set, a non-object tool_input, or a
# run_in_background value that is neither boolean nor boolean-ish -> silent pass, exit 0. A
# guardrail that breaks a working run is worse than the stall it prevents. Reads NOTHING off disk -
# no SSOT, no state root, no run file - so it has no CLAUDE_PLUGIN_ROOT dependency to degrade on.
#
# KNOWN RESIDUAL (deliberately not denied): `subagent_type: "fork"` is documented to run in the
# background regardless of the flag, so a nested fork with an explicit `false` still passes here.
# The harness already refuses fork-inside-fork on its own, and denying on an unmeasured assumption
# would violate the fail-open rule above; revisit only with a measurement.

set -uo pipefail
_pass() { exit 0; }

command -v jq >/dev/null 2>&1 || _pass
INPUT="$(cat 2>/dev/null || true)"
[[ -n "$INPUT" ]] || _pass
printf '%s' "$INPUT" | jq -e . >/dev/null 2>&1 || _pass   # unparseable stdin -> silent pass

# (a) is this a subagent spawn?
TOOL="$(printf '%s' "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || true)"
case "$TOOL" in
  Agent|Task) ;;
  *) _pass ;;
esac

# (b) is the CALLER a subagent? (empty/absent on both casings = the root -> always allowed)
AGENT_ID="$(printf '%s' "$INPUT" | jq -r '.agent_id // .agentId // empty' 2>/dev/null || true)"
AGENT_TYPE="$(printf '%s' "$INPUT" | jq -r '.agent_type // .agentType // empty' 2>/dev/null || true)"
[[ -n "$AGENT_ID" || -n "$AGENT_TYPE" ]] || _pass

# (c) would the launch be backgrounded? Resolved to exactly one of true / false / __UNKNOWN__.
# NOTE: `.tool_input.run_in_background // "x"` would be WRONG here - jq's `//` treats `false` as
# unset, collapsing the one value that must PASS into the absent case that must DENY.
BG="$(printf '%s' "$INPUT" | jq -r '
  if (.tool_input | type) != "object" then "__UNKNOWN__"
  elif (.tool_input | has("run_in_background") | not) then "true"
  else (.tool_input.run_in_background) as $v
    | if   $v == null  then "true"
      elif $v == true  or $v == "true"  then "true"
      elif $v == false or $v == "false" then "false"
      else "__UNKNOWN__" end
  end' 2>/dev/null || true)"
[[ "$BG" == "true" ]] || _pass    # explicit false, or a shape we cannot read -> fail open

REASON="REFUSED: you are a subagent, and this launch would run in the BACKGROUND (run_in_background is true, or omitted - omitted means background, it is the default). Nothing can wake you. Only the ROOT conversation is ever resumed when a background child finishes, so the child's result would be delivered to the root while you - the one context actually waiting - stay parked forever, and the run would stop right here with no error and no output.

DO THIS INSTEAD: re-issue this SAME call with run_in_background: false. A blocking launch returns the child's full report as this call's own return value, inside your current turn.

You do not lose concurrency: emit several blocking launches as separate tool calls in ONE message and they still run concurrently.

If you cannot block at all, do the work inline via the Skill tool, or end your turn with status NEEDS_NEXT naming the dispatch that must happen above you (snippets/spawner-completion-contract.md R0/R1)."

jq -cn --arg reason "$REASON" \
  '{hookSpecificOutput:{hookEventName:"PreToolUse", permissionDecision:"deny", permissionDecisionReason:$reason}}'
exit 0
