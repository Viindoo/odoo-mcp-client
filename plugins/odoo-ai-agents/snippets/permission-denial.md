<!-- SSOT snippet: what an agent does when the permission classifier refuses a tool call.
     Consumers point at ${CLAUDE_PLUGIN_ROOT}/snippets/permission-denial.md. -->

# A refused tool call

When the permission classifier refuses a call (the refusal carries a bracketed `[<label>]`):

1. Do not reshape the command to get past it - another spelling, a wrapper, a script or a
   different tool for the same action. The classifier treats that as a bypass attempt.
2. Restate the specific intent in your next turn: the exact action, the path or ref it touches,
   and why the task needs it. A soft block clears for that exact action once the intent is clear.
3. When the refusal repeats for routine work, stop retrying and report the bracketed label and the
   refused command, so the machine's owner can run `/odoo-ai-agents:odoo-setup auto-mode` to add
   the entry.

The only actions that need a human are a direct push to a protected branch and merging a pull
request; every other refusal is resolved by steps 2 and 3, never by waiting for a person.
