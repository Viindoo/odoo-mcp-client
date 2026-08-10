<!-- Reference material for snippets/dispatch-brief.md. This file is for humans and authors doing
     repo archaeology - it is never cited from any consumer-facing skill/agent/snippet body (see
     docs/authoring-skills-and-agents.md). Explanation and worked examples only; every decidable
     rule (including the field skeleton table and the Brief self-check code blocks, which are
     copied verbatim into agent bodies) stays in the main file. -->

# Dispatch Brief - rationale

## Why the SURVEY field closes a real, measured gap

Before this fix, the literal token `SURVEY` appeared 0 times in dispatch-brief.md: absent from
field 4 `INPUTS`'s canonical reuse-key list, absent from the Coder family delta, and absent from
all 3 Coder-family `## Brief self-check` sections. A brief carrying `INPUTS: DESIGN_DOC=...`
(every OTHER field present) passed every checked gate while silently dropping deep-survey findings
a human handed over - the caller had no textual reason to know the field even existed. The
"key must be present even at its safe value" rule (same as skeleton field 4 `INPUTS` itself) closes
this: omitting the key entirely, not just omitting a value, is the STOP condition.

## Why the skeleton carries no reply-address field

Earlier revisions carried an eleventh, always-required address field so a dispatched agent could
push its report back. No such address exists at runtime: a launch call cannot name the agent it
starts, and the roster an agent is shown contains neither itself nor its launcher, so the field
could only ever be filled with a guess. The return path the runtime already provides - the launch
call's own return value - made the field redundant as well as unfillable, so it was removed rather
than re-specified.
