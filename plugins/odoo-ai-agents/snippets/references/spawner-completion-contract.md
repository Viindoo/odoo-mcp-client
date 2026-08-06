<!-- Reference material for snippets/spawner-completion-contract.md. This file is for humans and
     authors doing repo archaeology - it is never cited from any consumer-facing skill/agent/snippet
     body (see docs/authoring-skills-and-agents.md). Explanation and worked examples only; every
     decidable rule stays in the main file. -->

# Spawner Completion Contract - rationale

## Why the unroutable/missing-REPLY_TO fallback is always "return inline"

Never an inferred guess at an address - a guessed address can silently misdeliver to a context that
is not blocking on the worker (R1), which is worse than the honest transcript-return fallback. The
main file states the WHY (a worker does not know its own `agentId`, per
`context-handoff-protocol.md` "Lead is the address authority") inline, not as a pointer, because a
prior regression let an earlier, undecidable two-step framing of this same fallback survive
unnoticed once it was only cited rather than stated in full.

## Why reporting to `main` when a coordinator launched you strands the coordinator

A spawner coordinator (e.g. `odoo-coder`) blocks on its launched children per R1 - it is actively
waiting for their completion reports. If a worker it launched reports to `main` instead (skipping
the coordinator), the coordinator never sees the report and sits blocked forever while `main`
receives a report addressed to the wrong recipient's context.

## Why the task-list tool's native status field is a mirror, not the authority

Concrete task-list tool labels are runtime-dependent: some harnesses expose only `pending`/
`in_progress`/`completed`, others add more states, and some expose no dedicated task-list tool at
all. The four-value Continuation Contract vocabulary (`DONE`/`BLOCKED`/`NEEDS_NEXT`/
`NEEDS_CONTEXT`) is therefore tracked separately (worklog or equivalent) rather than assumed to map
1:1 onto whatever labels a given tool happens to expose.
