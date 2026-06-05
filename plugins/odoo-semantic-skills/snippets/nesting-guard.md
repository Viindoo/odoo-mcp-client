<!-- SSOT snippet. The single source for the subagent nesting/depth guard. Previously
     copy-pasted verbatim into wave WI briefs, the wave conflict-resolver line, and the
     workflow-runner fan-out worker prefix — consolidate here and reference via
     ${CLAUDE_PLUGIN_ROOT}/snippets/nesting-guard.md so the rule has one home. -->

# Subagent Nesting Guard (depth ceiling)

You are a **leaf worker (depth-2)** — the bottom of the allowed spawn tree
(main = depth-0 → orchestrator subagent = depth-1 → you = depth-2). Spawning anything
deeper risks a nested-context crash. Therefore:

- You **MAY** NL-dispatch a **non-spawning** specialist skill (e.g. `odoo-coder`,
  `odoo-code-reviewer`, `odoo-frontend-coding`) if it helps — but **do NOT** invoke the
  Skill tool directly, and **do NOT** spawn a sub-agent.
- **Do NOT** call self-spawning / depth0-only skills (`wave`, `intake`, `odoo-brl`,
  `workflow-runner`, `/code-review`, `skill-creator`). See
  `docs/reference/ORCHESTRATION-MAP.md` for the authoritative spawn-class of each skill.
- Stay inside your assigned scope: only `Read/Grep/Glob/Edit/Write/Bash`. Do NOT
  `git branch/checkout/cherry-pick/merge/push`; remain in your assigned worktree.
