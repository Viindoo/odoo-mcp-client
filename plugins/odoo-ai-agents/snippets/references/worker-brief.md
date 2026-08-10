<!-- Reference material for snippets/worker-brief.md. This file is for humans and authors doing
     repo archaeology - it is never cited from any consumer-facing skill/agent/snippet body (see
     docs/authoring-skills-and-agents.md). Explanation and worked examples only; every decidable
     rule stays in the main file. -->

# Worker Brief - rationale

## Why a leaf is told it holds no send target at all

Earlier revisions told a leaf to push its report to an address its brief carried. A leaf launches
nothing, so the only address any agent can hold - the id its own launch call returned for a child -
never exists for it. Stating the absence positively ("you hold no legal send target") is what stops
a leaf from reading a messaging tool's presence in its toolset as permission to look for one.
