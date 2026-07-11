<!-- SSOT snippet. The single source for the dispatched-subagent worker brief: OSM
     grounding + worktree isolation. This is a worker brief, not a spawn guard - the
     two rails it carries are "do the work directly" and "stay in your worktree".
     Referenced via ${CLAUDE_PLUGIN_ROOT}/snippets/worker-brief.md so it has one home. -->

# Worker Brief (OSM grounding + worktree isolation)

A HARD-LEAF subagent dispatched into an isolated worktree carries this brief - the coding workers
`odoo-backend-coder` and `odoo-frontend-coder`, plus the other leaf specialists. It keeps two rails:
the work is done directly by the specialist, and ALL git stays out of the worker's hands -
the worker writes files and returns them; the orchestrator commits via git-ops (see below). A hard
leaf launches NO sub-agent and invokes NO spawner skill.

See also: the caller-side field schema (`OBJECTIVE`/`SCOPE`/`ACCEPTANCE`/... ) you were briefed
against is `${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md` - this file covers only your
worker-side behavior once dispatched, not how the caller composed your brief.

**The `odoo-coder` per-module coordinator is NOT a leaf and does NOT carry this brief.** It is a
sanctioned nested spawner (one agent level below `odoo-coding`, launched for EVERY module) that
launches the two hard-leaf workers above, tests the integrated module via `Skill(odoo-instance)`
inline, and - once the integrated test is green - COMMITS its module by invoking `git-toolkit:git-ops`
via the Skill tool (it can launch agents, so it is a spawner, not a leaf - the Nesting rule lets a
spawner invoke git-ops inline), then returns the SHA to `odoo-coding` (which collects it and no longer
re-commits). See `${CLAUDE_PLUGIN_ROOT}/agents/odoo-coder.md`.

- **You ARE the specialist - do the work directly.** Write or review the Python, XML, JS,
  OWL, or SCSS yourself, grounding every Odoo claim with the OSM MCP tools
  (`set_active_version`, `model_inspect`, `find_examples`, `validate_*`, `resolve_stylesheet`,
  …). An MCP tool call is never a subagent spawn, so it is always allowed. Follow your own
  agent conventions.
- **You do NOT run git - at all.** Not even git add / git commit / git stash in your own
  worktree. You do not own the project's git/commit conventions, so git is never your job. Write
  and edit your files directly in your assigned worktree (`WORKTREE_PATH`), then RETURN the list of
  files you touched to the orchestrator. Do NOT stage, commit, stash, branch, checkout, switch,
  cherry-pick, merge, rebase, reset, tag, push, force-push, fetch, pull, or add/remove worktrees.
  The orchestrator commits your output for you by invoking `git-toolkit:git-ops`. You cannot launch
  agents and cannot delegate to git-toolkit yourself; just return your files (or BLOCKED with the
  reason) and let the orchestrator handle every git step. Full policy:
  `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`. Stay in your assigned worktree. A leaf never
  invokes git-ops even via the Skill tool - see `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`.
- **Carve-out - self-provisioning an Odoo instance is permitted for the instance-touching leaves.**
  Unlike git-ops, `odoo-backend-coder` (for its bounded `/test_lint` gate) and the other
  instance-touching leaves MAY invoke `Skill(odoo-instance)` to self-provision a live Odoo instance
  when handed NO `INSTANCE_HANDLE`. This is allowed because `odoo-instance` applies the instance
  HARD RULES (`en_US` union, Viindoo `to_base`, lint-module install, per-version `cli_help`
  grounding); do NOT call `scripts/lib/allocator.py` directly, which would bypass them. A provided
  `INSTANCE_HANDLE` always wins: consume it, never re-provision.
  `odoo-frontend-coder` is INSTANCE-FREE - it never self-provisions; its only gate is the static
  `verify-frontend.sh`, and any live check is owned by the `odoo-coder` coordinator's integrated
  test or a delegated `odoo-instance` run. Contract:
  `${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md`.

## Agent Team mode keys (present only when team mode is on)

When the orchestrator dispatches you as a named TEAMMATE (Agent Team mode), the brief carries these
keys; absent keys mean team mode is off and you behave as today (final message + Continuation
Contract):

```
TASK_ID: <id>          # the task-board id for your work-item; TaskUpdate it in_progress -> completed|blocked.
REPLY_TO: <lead>       # who to SendMessage your completion report to. For a coding worker (odoo-backend-coder/odoo-frontend-coder) this is ALWAYS the `odoo-coder` coordinator that launched you - never `main`, since every module now routes through the coordinator. Other leaf specialists report to whichever orchestrator dispatched them (often `main`).
NOTIFY: <names>        # peer teammate names that depend on your output; SendMessage each too. `none` if no dependents.
```

End your turn with a `SendMessage` completion report to `REPLY_TO` (and each `NOTIFY` peer) per
`${CLAUDE_PLUGIN_ROOT}/snippets/agent-team-protocol.md` - never end on a bare tool call or
plain-text-only output. This coordinator<->worker completion report works WITHOUT any experimental
agent-teams flag; when `SendMessage` is absent, return the report as your final message instead.
