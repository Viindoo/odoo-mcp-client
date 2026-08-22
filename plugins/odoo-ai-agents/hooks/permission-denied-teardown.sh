#!/usr/bin/env bash
# permission-denied-teardown.sh - PermissionDenied ADVISORY. Fires when the harness refuses a
# tool call; this hook speaks up only when the refused call was an allocator LEASE GIVE-BACK
# (`allocator.py park` / `allocator.py release`), and tells the dispatch what to do instead.
#
# WHY THIS EXISTS
# A dispatched agent can ACQUIRE an instance but the auto-mode classifier may refuse to let it
# GIVE THE INSTANCE BACK: `release` stops a server process group and drops a database, which the
# built-in `Irreversible Local Destruction` / `Irreversible Deletion (general)` rules read as
# destroying a stateful resource. Those rules have escape clauses this situation genuinely meets
# ("unless clearly ephemeral"; "a stateful resource the agent did not create this session"), but
# the classifier cannot SEE them in `python3 allocator.py release <32-hex> --run-id <id>` - a hex
# token proves neither ephemerality nor provenance. Closing that gap for good is the operator's
# job, in `autoMode.environment` (user settings or managed settings; the classifier deliberately
# does NOT read a project's `.claude/settings.json`, so this plugin CANNOT ship it). Until then,
# and whenever teardown fails for any other reason, this hook stops the denial from becoming a
# LEAKED LEASE.
#
# Observed failure this closes: a dispatched `odoo-instance-ops` had `park` refused, then later
# `release` refused, reported a bare `BLOCKED`, and left a live ephemeral database plus its lease
# behind. Its report was honest and it correctly refused to work around the denial - it simply had
# nothing telling it that naming a catcher was still available to it, and the SubagentStop gate
# used to let a stop report past unconditionally.
#
# WHAT IT DOES NOT DO
# - It does NOT grant, widen, or route around any permission. `PermissionDenied` cannot change the
#   decision, and this hook never sets `retry` - re-issuing the same refused command is pointless,
#   and re-issuing a REWORDED one is itself the classifier's `Auto-Mode Bypass` rule. The advice
#   it emits is the opposite of a bypass: stop trying, hand the lease over by name.
# - It does NOT decide who owns the lease; `block-unowned-lease-mutation.sh` owns that question.
#
# CONTRACT: stdin JSON carries tool_name, tool_input.command, denial_reason,
# has_classifier_verdict, and (in a subagent) agent_id / agent_type. Output is the universal
# advisory pair `systemMessage` + `additionalContext`. Exit is ALWAYS 0 and stderr is ignored for
# this event; a hook failure must never be louder than the denial it is annotating.
#
# RESIDUALS it provably cannot catch:
# - A give-back issued through an interpreter this matcher never sees (a wrapper script, a
#   `$PY`-style indirection, `xargs`): the command text will not match and the hook stays silent.
# - A denial of the SPIN-UP path rather than the give-back: out of scope by design; nothing is
#   leaked when acquisition itself fails.
# - The main agent: it is advised too (the event carries no reliable main/subagent split beyond
#   agent_id, and the advice is harmless there), but the SubagentStop gate that makes the advice
#   binding is subagent-only, exactly as before.
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

[ "${_tool}" = "Bash" ] || exit 0
[ -n "${_cmd}" ] || exit 0

# Only speak for a refused LEASE GIVE-BACK. `allocator.py` plus a park/release verb must both be
# present. Read-only verbs (list/query/heartbeat) are not give-backs and are not this hook's
# business even on the rare occasion they are refused.
printf '%s' "${_cmd}" | grep -Eq 'allocator\.py[[:space:]]+(park|release)([[:space:]]|$)' || exit 0

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
EOF

python3 -c '
import json, sys
msg = sys.stdin.read().strip()
print(json.dumps({
    "systemMessage": msg,
    "additionalContext": msg,
}))
' <<<"${_MSG}" 2>/dev/null

exit 0
