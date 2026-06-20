<!-- SSOT snippet. The single source for the dispatched-subagent worker brief: OSM
     grounding + worktree isolation. This is a worker brief, not a spawn guard - the
     two rails it carries are "do the work directly" and "stay in your worktree".
     Referenced via ${CLAUDE_PLUGIN_ROOT}/snippets/worker-brief.md so it has one home. -->

# Worker Brief (OSM grounding + worktree isolation)

A subagent dispatched into an isolated worktree carries this brief. It keeps two rails:
the work is done directly by the specialist, and every git mutation stays out of the
worker's hands.

- **You ARE the specialist - do the work directly.** Write or review the Python, XML, JS,
  OWL, or SCSS yourself, grounding every Odoo claim with the OSM MCP tools
  (`set_active_version`, `model_inspect`, `find_examples`, `validate_*`, `resolve_stylesheet`,
  …). An MCP tool call is never a subagent spawn, so it is always allowed. Follow the same
  conventions the `odoo-coder` / `odoo-frontend-coder` / `odoo-code-reviewer` agents use.
- Stay inside your assigned scope: only `Read/Grep/Glob/Edit/Write/Bash`. Do NOT
  `git branch/checkout/cherry-pick/merge/push`; remain in your assigned worktree.
