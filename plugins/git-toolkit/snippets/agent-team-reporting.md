<!-- SSOT snippet. The single home for the team-mode completion-report contract: how a git-toolkit
     agent that is spawned as a NAMED TEAMMATE must end its turn (push a report to the lead) versus
     how a COLD-SPAWNED agent ends (return its result as the final message). Self-contained and
     provider-agnostic - it names no specific consumer. Referenced via
     ${CLAUDE_PLUGIN_ROOT}/snippets/agent-team-reporting.md. Edit here only. -->

# Agent Team Reporting (SSOT)

git-toolkit agents run in two spawn modes, and the END of your turn differs between them. Cold-spawn
(see `${CLAUDE_PLUGIN_ROOT}/snippets/git-nesting-protocol.md`) is the default and always-correct
baseline. A caller MAY instead spawn you as a NAMED TEAMMATE (an "Agent Team" run, where you persist
in the background and the lead waits on a message from you). In that mode you MUST additionally push
a completion report, or the lead is stranded on a content-less idle notification.

Detect the mode from your OWN toolset - do not assume:

## T1 - Detect: is `SendMessage` in your toolset?

- `SendMessage` PRESENT -> you are running as a named teammate (team mode). Apply T2.
- `SendMessage` ABSENT -> you were cold-spawned. Behave as the nesting protocol already says:
  return your structured result block as your final message and stop. No report push, nothing else
  to do here.

## T2 - Team mode: the terminal action is a report push

When `SendMessage` is present, completing your op is NOT enough. Your turn's TERMINAL action - the
last thing you do before yielding - MUST be:

`SendMessage({to: "main", text: <report>})`

- `<report>` = your normal structured result/findings block (the same compact summary + status you
  would otherwise return) PLUS the absolute path of the findings file you produced. Keep it compact:
  a summary, the status, and the findings-file path - never diff hunks or file contents.
- This is IN ADDITION to writing your findings file, not instead of it. Always write the findings
  file first, then push the report that points at it.
- `to: "main"` addresses the lead that dispatched the team. Use that recipient unless your brief
  names a different recipient explicitly.

NEVER end a team-mode turn on a bare tool call or on plain text only - either one leaves the lead
parked on an empty idle notification with no result to read. The `SendMessage` push is what closes
the loop.

If a `TaskUpdate` tool is present you MAY emit intermediate progress with it during a long op, but
that is optional and is NOT a substitute for the terminal `SendMessage` report.

## T3 - Frame the payload as shared team context

Frame the report as SHARED TEAM CONTEXT for the lead. NEVER describe it as "secret", "confidential",
"hidden", "private", or "restricted": the delivery substrate refuses a payload framed as
confidential, which silently drops your report and re-strands the lead. State the result plainly - it
is a teammate handing results to its lead, nothing sensitive.

## T4 - Mode does not change WHAT you do

Team mode only changes how your turn ENDS - it never relaxes any other contract. You still obey your
safety, scale, and read-only boundaries exactly as in cold-spawn mode; you still do only your one
scoped job; and (for the leaves) you still cannot fan out, because you hold no subagent-spawning
tool. The report is a delivery step layered on top of the same work, not new authority.
