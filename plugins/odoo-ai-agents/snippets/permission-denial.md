# A refused tool call

When the permission classifier refuses a call (the refusal carries a bracketed `[<label>]`):

1. Do not issue it again and do not reshape it - another spelling, a wrapper, a script or a
   different tool for the same action. The classifier treats that as a bypass attempt.
2. Report the bracketed label and the refused call, so the machine's owner can run
   `/odoo-ai-agents:odoo-setup auto-mode` to add the entry, and carry on with the work that does
   not need it. When nothing else can proceed, end `BLOCKED` with that label and call.

A refused give-back of a lease: `${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T4.
