<!-- Reference material for snippets/agent-team-protocol.md. This file is for humans and authors
     doing repo archaeology - it is never cited from any consumer-facing skill/agent/snippet body
     (see docs/authoring-skills-and-agents.md). Explanation and worked examples only; every
     decidable rule stays in the main file. -->

# Agent Team Protocol - rationale

## Why the task board never reads a teammate's transcript

A `local_agent`'s `.output` file is a symlink to the full JSONL conversation and would overflow the
lead's context window if read directly; `TaskOutput` is deprecated. `TaskList`/`TaskGet` exist
precisely to give the lead a cheap status surface it CAN afford to poll repeatedly, while the
expensive content only ever arrives once, via the Ask-1 push.

## Why the four channels never overlap

Each channel answering a DIFFERENT question (status / content / why / machine-DAG-state) is what
lets the lead reason about a run without loading any one channel's full history - collapsing two
channels into one would force the lead to filter irrelevant data out of every read.
