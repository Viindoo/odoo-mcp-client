<!-- SSOT snippet. The single source for the dispatched-subagent worker brief: OSM
     grounding + worktree isolation. This is a worker brief, not a spawn guard - the
     two rails it carries are "do the work directly" and "stay in your worktree".
     Referenced via ${CLAUDE_PLUGIN_ROOT}/snippets/worker-brief.md so it has one home. -->

# Worker Brief (OSM grounding + worktree isolation)

A subagent dispatched into an isolated worktree carries this brief. It keeps two rails:
the work is done directly by the specialist, and integration / history-rewrite git ops
stay out of the worker's hands (own-worktree add/commit/stash are allowed - see below).

- **You ARE the specialist - do the work directly.** Write or review the Python, XML, JS,
  OWL, or SCSS yourself, grounding every Odoo claim with the OSM MCP tools
  (`set_active_version`, `model_inspect`, `find_examples`, `validate_*`, `resolve_stylesheet`,
  …). An MCP tool call is never a subagent spawn, so it is always allowed. Follow your own
  agent conventions.
- **Git in your worktree - narrow allowance.** You may run `git add` and `git commit`
  to stage and commit your OWN work in your assigned worktree, then return the commit SHA
  to the orchestrator. You may also `git stash` if you need to park in-progress work.
  Do NOT run integration or history-rewrite ops - `branch`, `checkout`, `switch`,
  `cherry-pick`, `merge`, `rebase`, `reset`, `tag`, `push`, `force-push`, `fetch`,
  `pull`, or `worktree add/remove`. You have no Agent tool and cannot delegate to
  git-toolkit; if you need one of these, return BLOCKED with the reason so the
  orchestrator can delegate. Full policy:
  `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`. Stay in your assigned worktree.

## Agent Team mode keys (present only when team mode is on)

When the orchestrator dispatches you as a named TEAMMATE (Agent Team mode), the brief carries these
keys; absent keys mean team mode is off and you behave as today (final message + Continuation
Contract):

```
TASK_ID: <id>          # the task-board id for your work-item; TaskUpdate it in_progress -> completed|blocked.
REPLY_TO: main         # who to SendMessage your completion report to (the team lead).
NOTIFY: <names>        # peer teammate names that depend on your output; SendMessage each too. `none` if no dependents.
```

End your turn with a `SendMessage` completion report to `REPLY_TO` (and each `NOTIFY` peer) per
`${CLAUDE_PLUGIN_ROOT}/snippets/agent-team-protocol.md` - never end on a bare tool call or
plain-text-only output.
