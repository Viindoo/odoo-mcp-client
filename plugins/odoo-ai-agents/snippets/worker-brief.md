<!-- SSOT snippet. The single source for the dispatched-subagent worker brief: OSM
     grounding + worktree isolation. This is a worker brief, not a spawn guard - the
     two rails it carries are "do the work directly" and "no git, write only in WORKTREE_PATH".
     Referenced via ${CLAUDE_PLUGIN_ROOT}/snippets/worker-brief.md so it has one home. -->

# Worker Brief (OSM grounding + worktree isolation)

A HARD-LEAF subagent dispatched into an isolated worktree carries this brief - `odoo-frontend-coder`,
`odoo-test-writer`, `odoo-impact-recon` and the other leaf specialists. Two rails: do the work
directly, and run no git mutation - write files in your worktree and return them; your launcher
commits. A hard leaf launches NO sub-agent and invokes NO spawner skill.

**Who this brief does NOT bind: any agent the registry declares `role: spawner`**
(`generator/skill_tool_deps.json` -> `agents.<name>.role`) **or `role: node-owner`** (`odoo-coder`).
Such an agent launches its own children under
`${CLAUDE_PLUGIN_ROOT}/snippets/spawner-completion-contract.md` and the
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` cap, and takes its rails from its OWN
agent body.

- **You ARE the specialist - do the work directly.** Write or review the Python, XML, JS,
  OWL, or SCSS yourself, grounding every Odoo claim with the OSM MCP tools
  (`set_active_version`, `model_inspect`, `find_examples`, `validate_*`, `resolve_stylesheet`,
  …). An MCP tool call is never a subagent spawn, so it is always allowed. Follow your own
  agent conventions.
- **OSM version/profile pin - never `'auto'`.** `set_active_version` / `set_active_profile` are
  session-scoped server state. Pass the CONCRETE version (and profile) on EVERY OSM
  call; call the setters once at Round 0 only, as the reachability probe. Full rule: `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md`
  § OSM session-pin race.
- **You run no git mutation - in any form.** None of `add rm mv restore commit stash branch
  checkout switch cherry-pick rebase merge reset revert tag push pull fetch am apply worktree
  clean`, including `git -C <dir> <verb>`, a wrapper (`bash -c`, `$(...)`, a heredoc) and a script
  that runs one. Read-only git (`status diff log show rev-parse blame ls-files`, `worktree list`)
  is allowed. Return the list of files you touched (or BLOCKED with the reason); the node owner or
  spawner that launched you commits them through `Skill(git-toolkit:git-ops)`. A leaf never
  invokes git-ops, not even through the Skill tool. Full policy:
  `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`.
- **Write only inside your `WORKTREE_PATH`** (and `ISOLATE_DIR` for scratch). Resolve every path
  you write against `WORKTREE_PATH`, never against your cwd or another worktree under
  `<SHARE>/worktrees/`. A change another node's tree needs is reported upward (file + change) for
  that node's owner.
- **Carve-out - self-provisioning an Odoo instance is permitted for the instance-touching leaves.**
  Unlike git-ops, an instance-touching leaf (e.g. `odoo-qa-tester`) MAY invoke
  `Skill(odoo-instance)` to self-provision a live Odoo instance when handed NO `INSTANCE_HANDLE`,
  or when your brief carries `SELF_PROVISION: worktree-addons`.
  It re-roots the addons list onto your `WORKTREE_PATH`; do NOT call `lease_acquire` +
  `instance_build` bare. A provided `INSTANCE_HANDLE` always wins: consume it, never re-provision - unless your brief
  carries `SELF_PROVISION: worktree-addons`
  (`${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md` § Worktree-addons carve-out). As a
  declared HARD LEAF you launch nothing: `odoo-instance` runs INLINE for you. `odoo-frontend-coder` is
  INSTANCE-FREE - it never self-provisions and runs only its static `verify-frontend.sh` gate.
  `odoo-test-writer` never self-provisions:
  it runs its break-checks through `odoo-instance` inline on the forwarded handle
  (`${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md` § Test build on a forwarded handle).
  **Self-provisioning carries teardown:** what you acquire under this carve-out you
  `lease_release` (or `lease_park`) before your terminal status -
  `${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T1.

  **It also requires a `RUN_ID`.** Acquire under the `RUN_ID` your brief carries (the `run_id` of
  every lease call you make). If it carries none, STOP with `NEEDS_CONTEXT(RUN_ID)` - do not invent
  one and do not acquire without one.

## How your turn ends

Hand your completion report to your launcher ONCE, as the last act of your dispatch - the 3-part
shape owned by `${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md`, handed back after teardown
through `SubagentHandback` - alone in its own message, after every other result is read - when you
have it, else as your final text
(`${CLAUDE_PLUGIN_ROOT}/snippets/spawner-completion-contract.md` R3). Never send it to anyone,
never look for a reply address, and never use a messaging tool: you launch nothing, so you hold no
send target. A failed send is never answered by a different name; hand the report back as above.
