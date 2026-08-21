#!/usr/bin/env bash
# block-unowned-lease-mutation.sh - PreToolUse HARD DENY. The enforcement half of the allocator's
# ownership guard (${CLAUDE_PLUGIN_ROOT}/docs/reference/INSTANCE-ALLOCATION-GUARDS.md §6.3) and of
# ${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md T1 ("teardown belongs to whoever
# ACQUIRED the resource").
#
# THE INCIDENT IT EXISTS FOR: a dispatched agent given a purely documentary brief - no instance, no
# lease token handed to it, no execution asked for - ended its turn by running
# `allocator.py release <token>` on a live acceptance lease belonging to the run that had dispatched
# it. `drop_on_release: true` fired and a freshly built database was destroyed. Its stated reasoning
# was that the lease "looked orphaned"; the question it never asked was DID I ACQUIRE THIS. The
# agent's own definition called it read-only and a HARD LEAF - but that prohibition was PROSE, with
# no gate under it, exactly like the coordinator-authoring breach that
# hooks/block-coordinator-code-write.sh was written for.
#
# WHAT IT REFUSES - two arms, both scoped to a SUBAGENT caller:
#   A1  `allocator.py release ...` in a command segment that names NO `--run-id` (nor its
#       `--session` alias). A release must NAME the run that owns the lease; an absent run id is not
#       "the owner forgot a flag", it is ownership not established. A rightful owner always has the
#       value - `ALLOC_RUN_ID` from its own acquire, `INSTANCE_HANDLE.run_id` downstream - so this
#       arm costs a legitimate release nothing and refuses the incident's exact shape.
#   A2  `--force` / `--force-forget` on `release`, or `--yes` on `reap-orphans`, from a subagent.
#       The allocator's own refusal names `--force` as the override, so without this arm a
#       dispatched agent that reads that refusal is ONE FLAG away from the same data loss, by the
#       same "it looked orphaned" reasoning. `--force` overrides a human's ownership decision; it is
#       a human's call, and a dispatched agent's route is to report the refusal upward instead.
#
# WHY IDENTITY-FREE (no per-agent allow-list): the agent-role SSOT
# (generator/skill_tool_deps.json `.agents.<name>.role`) has exactly two live values here, `leaf`
# and `coordinator`, and the agents that legitimately drive the allocator (`odoo-instance-ops`,
# `odoo-qa-tester`, `odoo-coder`) sit on BOTH sides of that line - so `role` cannot separate "may
# mutate a lease" from "may not", and a new per-agent classification would be 26 hand-made
# judgements, each one an outage on the pipeline it mis-marks. This gate instead asserts the ONE
# property every legitimate caller can satisfy and the incident's caller could not: name the owner.
# It therefore also covers agents that do not exist yet.
#
# WHY A SUBAGENT ONLY: the ROOT is never denied (the same rule remind-delegate.sh and
# block-coordinator-code-write.sh follow). A human is present in the main context to read the
# allocator's own refusal and decide; a dispatched agent is not, and the incident happened in a
# dispatch. The allocator refuses a foreign or un-named release for EVERY caller regardless - this
# hook is the earlier, explanatory layer, and the layer that still holds if the allocator predicate
# is ever loosened again.
#
# EXECUTION POSITION, NOT A MENTION. The token bearing `allocator.py` must be the segment's first
# token, or be preceded by a python interpreter. A read-only reference to the script - `grep -rn
# 'allocator.py release' scripts/`, `sed -n '/allocator.py release/p'`, an echoed remediation line,
# a `python3 -c` string - is therefore never mistaken for a call. This rule was added after this
# gate's own test caught the first detector DENYING a plain `grep`: a guard that blocks reading the
# code it guards is an outage, not a safeguard, and it would have blocked the very investigation
# that diagnoses an incident. The verb is read as the NEXT token, so a verb spelled inside a quoted
# pattern can never stand in for one on a command line.
#
# WHAT IT PROVABLY DOES NOT CATCH - stated, not papered over:
#   - `park`, `resume`, `heartbeat` and `bind` on a lease the caller does not own. Those verbs
#     accept no `--run-id`, so there is nothing to require; `park` in particular is one of the THREE
#     EXITS the SubagentStop teardown gate accepts, and making it refusable could deadlock a
#     subagent between a refused release and a refused park. That is separate scope, named in the
#     report rather than half-fixed here.
#   - a run id that is present but WRONG or empty (`--run-id ""`, `--run-id $UNSET`): this arm is
#     lexical. The allocator's own comparison under flock is what catches those.
#   - a command whose verb or flags are COMPUTED (`$VERB`, `"$FLAGS"`), assembled inside a script
#     the command only invokes (`bash teardown.sh`), or backgrounded outside the Bash tool.
#   - an invocation whose interpreter is not spelled literally (`"$PY" .../allocator.py release`):
#     the execution-position test needs a `python`-shaped token before the script path, and an
#     unresolvable one reads as "cannot classify" -> pass, per this file's fail-open rule.
#   - a release issued through some tool other than Bash, or from the root context.
#   - `gc` and `reap-orphans` without `--yes`: both are janitors whose predicate is "provably
#     abandoned" / "no lease references this database at all", not "not mine", so neither needs an
#     ownership check. They are deliberately not refused.
#
# FAILS OPEN ON EVERY UNCERTAINTY (the _pass convention this plugin's hooks share): no jq, empty or
# unparseable stdin, a tool outside the matcher, a command that never names `allocator.py`, or a
# caller that is not identifiably a subagent -> silent pass, exit 0.
#
# SCHEMA: PreToolUse's documented shape - hookSpecificOutput.permissionDecision = "deny" with a
# permissionDecisionReason. Exit code is ALWAYS 0; a PreToolUse hook that hard-fails is an outage.

set -uo pipefail
_pass() { exit 0; }

command -v jq >/dev/null 2>&1 || _pass
INPUT="$(cat 2>/dev/null || true)"
[[ -n "$INPUT" ]] || _pass
printf '%s' "$INPUT" | jq -e . >/dev/null 2>&1 || _pass

TOOL="$(printf '%s' "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || true)"
[[ "$TOOL" == "Bash" ]] || _pass

# Caller must be a subagent - ANY populated agent_id/agent_type. Same identity signal, same V-52
# rule, as hooks/remind-delegate.sh and hooks/block-coordinator-code-write.sh. The ROOT is never
# denied.
AGENT_ID="$(printf '%s' "$INPUT" | jq -r '.agent_id // .agentId // empty' 2>/dev/null || true)"
AGENT_TYPE="$(printf '%s' "$INPUT" | jq -r '.agent_type // .agentType // empty' 2>/dev/null || true)"
[[ -n "$AGENT_ID" || -n "$AGENT_TYPE" ]] || _pass

CMD="$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || true)"
[[ -n "$CMD" ]] || _pass
printf '%s' "$CMD" | grep -q 'allocator\.py' || _pass

AGENT_NAME="${AGENT_TYPE##*:}"
[[ -n "$AGENT_NAME" ]] || AGENT_NAME="this subagent"

# The allocator verb this segment RUNS, or nothing. Pure bash token walk - no awk, no second
# quoting layer to get wrong.
_alloc_verb() {
  local -a toks=()
  read -r -a toks <<< "$1"
  local n=${#toks[@]} i cur prev nxt
  for (( i = 0; i < n; i++ )); do
    cur="${toks[i]//[\"\']/}"
    [[ "$cur" == *allocator.py ]] || continue
    (( i + 1 < n )) || return 0          # nothing after the script path: no verb
    if (( i > 0 )); then
      prev="${toks[i-1]//[\"\']/}"
      case "$prev" in
        python|python[0-9]*|*/python|*/python[0-9]*) ;;
        *) continue ;;                   # a MENTION, not an invocation
      esac
    fi
    nxt="${toks[i+1]//[\"\']/}"
    printf '%s\n' "$nxt"
    return 0
  done
}

# One simple command per line, so `--run-id` can never be borrowed from a NEIGHBOURING command
# (`allocator.py release $T && echo --run-id`). Same segmentation as
# block-coordinator-code-write.sh.
SEGS="$(printf '%s' "$CMD" | sed -E 's/(\|\||&&|[;|&])/\n/g')"

ARM=""
while IFS= read -r seg; do
  [[ -n "$seg" ]] || continue
  VERB="$(_alloc_verb "$seg")"
  [[ -n "$VERB" ]] || continue

  # A2 first: an override flag is refused whatever else the segment says, so threading a run id
  # cannot buy a --force.
  if [[ "$VERB" == "release" ]] \
     && printf '%s' "$seg" | grep -qE '(^|[[:space:]])--force(-forget)?([[:space:]]|$)'; then
    ARM=A2; break
  fi
  if [[ "$VERB" == "reap-orphans" ]] \
     && printf '%s' "$seg" | grep -qE '(^|[[:space:]])--yes([[:space:]]|$)'; then
    ARM=A2; break
  fi
  # A1: a release that names no owner.
  if [[ "$VERB" == "release" ]] \
     && ! printf '%s' "$seg" | grep -qE '(^|[[:space:]])--(run-id|session)([[:space:]]|=)'; then
    ARM=A1; break
  fi
done <<< "$SEGS"

[[ -n "$ARM" ]] || _pass

if [[ "$ARM" == "A1" ]]; then
  REASON="REFUSED: you are \`$AGENT_NAME\`, and this \`allocator.py release\` names no owner - no --run-id (nor its --session alias) anywhere in the command.

A release stops a server's process group and, for a \`drop_on_release\` lease, DROPS ITS DATABASE. It belongs to the run that ACQUIRED the lease, so the release must name that run. An absent run id is not \"the owner forgot a flag\" - it is ownership not established, and this is the exact shape that destroyed a live acceptance database (see docs/reference/INSTANCE-ALLOCATION-GUARDS.md section 6.3).

DO THIS INSTEAD:
- If YOU acquired this lease: re-run it as \`allocator.py release <token> --run-id <id>\`, using the run id your own acquire echoed as ALLOC_RUN_ID (INSTANCE_HANDLE.run_id when a handle was forwarded to you).
- If you did NOT acquire it: LEAVE IT ALONE. Holding a token is not ownership, an absent owner.pid means liveness-not-verifiable rather than abandoned, and a lease from an earlier phase of the SAME run belongs to that run. Report it in your terminal status and let its owner - or allocator gc - deal with it.
- If your brief forwarded an INSTANCE_HANDLE to you, you are the CONSUMER, never the releaser (snippets/resource-teardown-contract.md T1).
- If you are trying to free the RAM but the database is still wanted, that is \`allocator.py park <token>\`, not a release."
else
  REASON="REFUSED: you are \`$AGENT_NAME\`, and this \`allocator.py\` call carries an override flag (--force / --force-forget / --yes). A dispatched agent may not override the allocator's ownership decision.

Those flags exist to let a HUMAN reap a lease or database the ownership guard is protecting - which is exactly the judgement a dispatch cannot make: it cannot see the other sessions on this host, and the failure mode is irreversible (a dropped database, an abandoned one).

DO THIS INSTEAD: run the operation WITHOUT the override. If the allocator then refuses it, that refusal is your ANSWER, not an obstacle - end your turn with status BLOCKED (or NEEDS_NEXT naming who should decide) and quote the refusal, including the owning run it named. Never re-issue the same call with an override to get past it."
fi

jq -cn --arg reason "$REASON" \
  '{hookSpecificOutput:{hookEventName:"PreToolUse", permissionDecision:"deny", permissionDecisionReason:$reason}}'
exit 0
