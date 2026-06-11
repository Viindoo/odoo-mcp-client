<!-- SSOT snippet. The single source for the subagent nesting/depth guard. Previously
     copy-pasted verbatim into wave WI briefs, the wave conflict-resolver line, and the
     workflow-chaining fan-out worker prefix — consolidate here and reference via
     ${CLAUDE_PLUGIN_ROOT}/snippets/nesting-guard.md so the rule has one home. -->

# Subagent Nesting Guard (depth ceiling)

You are a **leaf worker (depth-2)** — the bottom of the allowed spawn tree
(main = depth-0 → orchestrator subagent = depth-1 → you = depth-2). Spawning anything
deeper risks a nested-context crash. Therefore:

- **You ARE the specialist — do the work directly.** Write or review the Python, XML, JS,
  OWL, or SCSS yourself, grounding every Odoo claim with the OSM MCP tools
  (`set_active_version`, `model_inspect`, `find_examples`, `validate_*`, `resolve_stylesheet`,
  …). An MCP tool call is never a subagent spawn, so it is always allowed at your depth.
  Follow the same conventions the `odoo-coder` / `odoo-frontend-coder` / `odoo-code-reviewer`
  agents use — but **do NOT invoke those bundles** (next bullet).
- **Do NOT invoke any depth0-only skill** — `odoo-coding`, `odoo-code-review`,
  `odoo-ui-review`, `wave`, `intake`, `odoo-brl`, `workflow-chaining`,
  `run-driver`, `/code-review`, `skill-creator`. Each dispatches a fresh agent (depth0→1) and may ONLY be
  invoked from the main agent. See `docs/reference/ORCHESTRATION-MAP.md` for the authoritative
  spawn-class of every skill.
- You **MAY** NL-dispatch a genuinely **non-spawning** (`leaf`, any-depth) skill — e.g.
  `odoo-feature-check`, `odoo-override-finding`, `odoo-deprecation-audit` — for a read-only
  lookup if it helps. Do NOT invoke the Skill tool to trigger a **spawner**, and do NOT spawn a
  sub-agent yourself. (This Skill-tool-on-a-spawner prohibition binds you because you are at
  depth≥1; the **depth-0 main agent** and depth-0 orchestrators DO use the Skill tool to launch
  spawner skills — that is their canonical dispatch, see `docs/reference/workflow-harness.md`
  § Dispatch method.)
- Stay inside your assigned scope: only `Read/Grep/Glob/Edit/Write/Bash`. Do NOT
  `git branch/checkout/cherry-pick/merge/push`; remain in your assigned worktree.
