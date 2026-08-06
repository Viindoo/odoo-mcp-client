<!-- Reference material for snippets/worker-brief.md. This file is for humans and authors doing
     repo archaeology - it is never cited from any consumer-facing skill/agent/snippet body (see
     docs/authoring-skills-and-agents.md). Explanation and worked examples only; every decidable
     rule stays in the main file. -->

# Worker Brief - rationale

## Why REPLY_TO must never be framed as team-mode-only

An earlier revision grouped `REPLY_TO` under a heading literally titled "present only when team
mode is on", alongside the genuinely conditional `TASK_ID`/`NOTIFY` keys. That directly
contradicted `dispatch-brief.md` field 11's ALWAYS classification and was the real, textual root
cause of dispatch-composing skills treating `REPLY_TO` as Tier-A-only (only supplying it when Agent
Team mode was active). Only the DELIVERY MECHANISM is tier-conditional; the obligation to state
`REPLY_TO` is not.
