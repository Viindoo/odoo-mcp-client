<!-- Reference material for snippets/spawner-completion-contract.md. This file is for humans and
     authors doing repo archaeology - it is never cited from any consumer-facing skill/agent/snippet
     body (see docs/authoring-skills-and-agents.md). Explanation and worked examples only; every
     decidable rule stays in the main file. -->

# Spawner Completion Contract - rationale

## Why R3 states the whole return path inline rather than citing it

Every earlier revision of this rule assumed a reply address the runtime never provides, and each
repair re-specified the address instead of removing it. R3 now states the one action in full, in
the SSOT itself (hand the report over once, after teardown - as the `SubagentHandback` message when
that tool exists, else as the final text of the turn), because a rule that is only cited drifts the
moment a consumer restates it - which is exactly how the address-shaped versions survived repeated
corrections.

## Why SubagentHandback is called last, and once

The harness hands the report over the moment `SubagentHandback` runs - before the subagent's turn
ends, so before any SubagentStop gate can inspect it. A report delivered while a lease is still
live leaves the caller acting on a handle that is about to disappear, and a second handback is
refused, so there is no way to correct the report afterwards. The PreToolUse gate
(hooks/block-handback-with-live-lease.sh) therefore refuses the call while an obtained lease is
live and unforwarded; a refused call delivers nothing, which is why the rule says to take a
teardown exit and call again rather than to send a follow-up.

## Why R3 (a) rests on the ABSENCE of an envelope

R3's "nothing inbound to answer" is stated as the absence of an envelope - a launch hands over a
brief, so there is no `from` at all - not as "`from` is a type label". That older reason was false
on the mechanism, and a rule resting on a checkable falsehood is overturned by the first reader who
checks.

## Why an inferred send target is worse than no send at all

A guessed address either fails to resolve or silently misdelivers to a context that is not waiting
on the sender (R1). The wake that follows a child's completion already delivers the report to the
launcher that stopped for it, so a send adds a failure mode and no capability.

## Why the task-list tool's native status field is a mirror, not the authority

Concrete task-list tool labels are runtime-dependent: some harnesses expose only `pending`/
`in_progress`/`completed`, others add more states, and some expose no dedicated task-list tool at
all. The four-value Continuation Contract vocabulary (`DONE`/`BLOCKED`/`NEEDS_NEXT`/
`NEEDS_CONTEXT`) is therefore tracked separately (worklog or equivalent) rather than assumed to map
1:1 onto whatever labels a given tool happens to expose.
