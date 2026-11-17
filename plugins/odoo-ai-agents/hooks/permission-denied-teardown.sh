#!/usr/bin/env bash
# permission-denied-teardown.sh - PermissionDenied ADVISORY. Fires when the harness refuses a
# tool call; it speaks only when the refused call was a LEASE GIVE-BACK, and shows the user what
# the dispatch does instead. Two shapes of give-back are recognized, branching on tool_name:
#   - Bash: `allocator.py park` / `allocator.py release` (the CLI fallback path), matched against
#     tool_input.command; the path may be bare or double-quoted.
#   - MCP: `mcp__plugin_odoo-ai-agents_odoo-local__lease_release` / `..._lease_park` - the
#     tool_name alone identifies the give-back.
# Both get the same advice.
#
# A release stops a server process group and drops a database, and the call text (a hex token and
# a run id) proves neither that the lease is throwaway nor that this session acquired it, so the
# auto-mode classifier can refuse it. The MCP give-back is kept out of the classifier by the allow
# rules scripts/setup-steps/32-permissions-state-root.sh writes; this hook covers the calls that
# still reach it.
#
# It grants nothing and never sets `retry`: a refused give-back is not re-issued or reworded
# (snippets/resource-teardown-contract.md T4). Lease ownership is block-unowned-lease-mutation.sh's
# question, not this hook's.
#
# CONTRACT: stdin JSON carries tool_name, tool_input.command (Bash) / tool_input (MCP),
# denial_reason, has_classifier_verdict, and (in a subagent) agent_id / agent_type. Output is
# `systemMessage` alone: a line on the user's display - the harness reads nothing else from this
# event's output but hookSpecificOutput.retry, so no field of it reaches the model. The dispatch
# reads the same advice in the reason of the SubagentStop teardown block and of the
# SubagentHandback gate (hooks/teardown-check.sh), which fire while a lease it obtained is live.
# Exit is always 0 and stderr is ignored for this event.
#
# Not covered: a give-back issued through an interpreter this matcher does not see (a wrapper
# script, `xargs`); a refused acquisition (nothing is leaked); the main agent, which no
# model-facing gate reminds - a lease it still holds at session end is parked when it records a
# run and a build, reclaimed otherwise (hooks/session-end-gc.sh).
set -uo pipefail

_input="$(cat)"

# Parse with python3 (stdlib json, no jq dependency - same choice as auto-approve-browser.sh).
# Emits "<tool>\x1f<command>" or nothing at all on any error.
_parsed="$(printf '%s' "${_input}" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
    tool = d.get("tool_name") or ""
    cmd = (d.get("tool_input") or {}).get("command") or ""
    if isinstance(tool, str) and isinstance(cmd, str):
        sys.stdout.write(tool + "\x1f" + cmd)
except Exception:
    pass
' 2>/dev/null)"

[ -n "${_parsed}" ] || exit 0

_tool="${_parsed%%$'\x1f'*}"
_cmd="${_parsed#*$'\x1f'}"

# Branch on tool_name: the Bash CLI fallback path inspects tool_input.command; the MCP
# odoo-local path is identified by tool_name alone (lease_release / lease_park carry no
# separate "command" string to match against).
case "${_tool}" in
  Bash)
    [ -n "${_cmd}" ] || exit 0
    # Only speak for a refused LEASE GIVE-BACK. `allocator.py` plus a park/release verb must
    # both be present. Read-only verbs (list/query/heartbeat) are not give-backs and are not
    # this hook's business even on the rare occasion they are refused. The path may be bare
    # (`allocator.py park`) or double-quoted (`".../allocator.py" park`) - the optional `"?`
    # right after `allocator.py` covers the closing quote of the quoted form.
    printf '%s' "${_cmd}" | grep -Eq 'allocator\.py"?[[:space:]]+(park|release)([[:space:]]|$)' || exit 0
    ;;
  mcp__plugin_odoo-ai-agents_odoo-local__lease_release|mcp__plugin_odoo-ai-agents_odoo-local__lease_park)
    # The MCP give-back: tool_name alone is the whole signal - no command text to inspect.
    ;;
  *)
    exit 0
    ;;
esac

read -r -d '' _MSG <<'EOF'
Your allocator LEASE GIVE-BACK was refused by the harness before it ran, so the lease is still
open and the instance is still yours. Two things follow, and the second is the one that matters.

1) Do NOT re-issue this command, and do NOT reword, re-encode, or re-route it to get past the
   refusal. An obfuscated retry is itself a blocked action, and the refusal is an answer, not an
   obstacle. Quote it verbatim in your report.

2) Do NOT end on a bare `BLOCKED` / `NEEDS_CONTEXT`. The SubagentStop resource-teardown gate is
   STATUS-BLIND: it reads the allocator ledger and your forwarded handle, never your status
   value, so a stopped-run report will NOT carry a still-live lease past it. Being unable to
   RELEASE is not being unable to NAME A CATCHER - and naming one is always available to you: it
   is text in your own continuation fence, needing no tool, no permission and no live process.

DO THIS: forward `INSTANCE_HANDLE` in your continuation `next.inputs`, including `lease_token`
and `run_id`, naming your DISPATCHING CALLER as the catcher (when teardown is what failed, the
caller is the catcher - it dispatched you, it outlives you, and it can release what you cannot).
Keep whatever terminal status is honest, and state that teardown was denied and why. That is the
T4 named handoff, it clears the gate, and it is what keeps the database from outliving the run.
When you deliver your report through SubagentHandback, that continuation block goes INSIDE its
message: the report is delivered the moment the tool runs, so a handback whose message does not
forward the handle is refused while the lease is live.
EOF

python3 -c '
import json, sys
msg = sys.stdin.read().strip()
print(json.dumps({"systemMessage": msg}))
' <<<"${_MSG}" 2>/dev/null

exit 0
