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

**The `odoo-coder` node coordinator is NOT a leaf and does NOT carry this brief.** It is a
sanctioned nested spawner (one agent level below `odoo-coding`, launched once per work node) that
launches the three hard-leaf teammates - `odoo-test-writer` (RED test, first), `odoo-backend-coder`
and/or `odoo-frontend-coder` (code to green) - per R0
(`${CLAUDE_PLUGIN_ROOT}/snippets/spawner-completion-contract.md`: it dispatches, ENDS ITS TURN, and
is woken with each teammate's result), tests the integrated node via `Skill(odoo-instance)` inline,
and - once the integrated test is green - COMMITS its node by invoking `git-toolkit:git-ops` via the
Skill tool, then returns the SHA to `odoo-coding` (which collects it and no longer re-commits). It
NEVER authors the node's source itself: every source file is written by a teammate. See
`${CLAUDE_PLUGIN_ROOT}/agents/odoo-coder.md`.

- **You ARE the specialist - do the work directly.** Write or review the Python, XML, JS,
  OWL, or SCSS yourself, grounding every Odoo claim with the OSM MCP tools
  (`set_active_version`, `model_inspect`, `find_examples`, `validate_*`, `resolve_stylesheet`,
  …). An MCP tool call is never a subagent spawn, so it is always allowed. Follow your own
  agent conventions.
- **OSM version/profile pin - never `'auto'`.** `set_active_version` / `set_active_profile` are
  session-scoped server state (keyed to this MCP session); ANY other actor sharing that session
  can overwrite the pin between your calls. Pass the CONCRETE version (and profile) on EVERY OSM
  call; call the setters once at Round 0 only, as the reachability probe, and never rely on the
  ambient pin afterward. Full rule: `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md`
  § OSM session-pin race.
- **You do NOT run git - at all.** Not even git add / git commit / git stash in your own
  worktree. Write and edit your files directly in your assigned worktree (`WORKTREE_PATH`), then
  RETURN the list of files you touched to the orchestrator. Do NOT stage, commit, stash, branch,
  checkout, switch, cherry-pick, merge, rebase, reset, tag, push, force-push, fetch, pull, or
  add/remove worktrees. The orchestrator commits your output for you by invoking
  `git-toolkit:git-ops`. You cannot launch agents and cannot delegate to git-toolkit yourself; just
  return your files (or BLOCKED with the reason) and let the orchestrator handle every git step.
  Full policy: `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`. Stay in your assigned worktree.
  A leaf never invokes git-ops even via the Skill tool - see
  `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`.
- **Carve-out - self-provisioning an Odoo instance is permitted for the instance-touching leaves.**
  Unlike git-ops, an instance-touching leaf (e.g. `odoo-qa-tester`) MAY invoke
  `Skill(odoo-instance)` to self-provision a live Odoo instance when handed NO `INSTANCE_HANDLE`,
  or when your brief carries `SELF_PROVISION: worktree-addons`.
  `odoo-instance` applies the instance HARD RULES (`en_US` union, Viindoo
  `to_base`, lint-module install, per-version `cli_help` grounding) AND resolves addons provenance -
  it re-roots the addons list onto your `WORKTREE_PATH` so the instance loads YOUR code, not the
  principal checkout; do NOT call `scripts/lib/allocator.py` directly, which would bypass all of
  that. A provided `INSTANCE_HANDLE` always wins: consume it, never re-provision - unless your brief
  carries `SELF_PROVISION: worktree-addons`
  (`${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md` § Worktree-addons carve-out). Because
  you are a declared HARD LEAF, `odoo-instance` runs INLINE for you (never launches
  `odoo-instance-ops`) - this is a MUST, not a judgment call. `odoo-backend-coder` and
  `odoo-frontend-coder` are BOTH INSTANCE-FREE - neither self-provisions; each runs only its own
  static gate (ORM-validation for the backend leg, `verify-frontend.sh` for the frontend leg), and
  any live check is owned by the `odoo-coder` coordinator's integrated test or a delegated
  `odoo-instance` run - the `/test_lint`/`/test_pylint` lint-class gate runs ONCE at
  `run-harness`'s pre-PR tail, never inside either leaf. Contract:
  `${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md`.
  **Self-provisioning carries teardown:** what you acquire under this carve-out you release
  before your terminal status - `${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md`
  T1/T3.

## How your turn ends

Your completion report is the FINAL TEXT of your turn - the 3-part shape owned by
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md`. Emit it and stop. Never send it to
anyone, never look for a reply address, and never treat a messaging tool's presence in your toolset
as an instruction to use one: you launch nothing, so you hold no legal send target at all. Rule:
`${CLAUDE_PLUGIN_ROOT}/snippets/spawner-completion-contract.md` R3.
