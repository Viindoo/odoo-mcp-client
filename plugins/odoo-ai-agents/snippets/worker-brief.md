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
against is `${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md` § Universal skeleton - this file covers only your
worker-side behavior once dispatched, not how the caller composed your brief.

**Who this brief does NOT bind: any agent the registry declares `role: spawner|coordinator`**
(`generator/skill_tool_deps.json` -> `agents.<name>.role` is the SSOT - read the role, do not
infer it from a name list here). Today that is `odoo-coder` and `odoo-solution-architect`; a
third promoted tomorrow is covered by the same sentence. Such an agent launches its own
children under `${CLAUDE_PLUGIN_ROOT}/snippets/spawner-completion-contract.md` and the
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` cap, and takes its worker-side
rails from its OWN agent body instead of the leaf rails above. `odoo-solution-architect` is
the read-only case: it launches grounding workers only, writes no source, and runs no git.

`odoo-coder` is the WRITING case, and the rest of this section is its detail. It is a sanctioned
nested spawner (one agent level below `odoo-coding`, launched once per work node) that
launches its hard-leaf teammates - `odoo-backend-coder` and/or `odoo-frontend-coder` (the code)
first, then ONE `odoo-test-writer` per node (the tests and their break-checks,
`${CLAUDE_PLUGIN_ROOT}/snippets/test-sensitivity-contract.md` § Code first, then the test leg) -
per R0 (`${CLAUDE_PLUGIN_ROOT}/snippets/spawner-completion-contract.md`: it collects each
teammate's result by its R0 move), tests the integrated node via
`Skill(odoo-instance)` inline, and - once the integrated test is green - COMMITS its node by
invoking `git-toolkit:git-ops` via the Skill tool, then returns the SHA to `odoo-coding`, which
collects it and never re-commits (under `COMMIT: caller` it commits nothing and returns the file
list). It NEVER authors the node's source itself: every source file is written by a teammate.

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
  `odoo-instance` applies the instance HARD RULES (demo by build purpose, lint-module install,
  per-version `cli_help` grounding) AND resolves addons provenance -
  it re-roots the addons list onto your `WORKTREE_PATH` so the instance loads YOUR code, not the
  principal checkout; do NOT call `lease_acquire` + `instance_build` bare, which would bypass all
  of that. A provided `INSTANCE_HANDLE` always wins: consume it, never re-provision - unless your brief
  carries `SELF_PROVISION: worktree-addons`
  (`${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md` § Worktree-addons carve-out). Because
  you are a declared HARD LEAF, `odoo-instance` runs INLINE for you (never launches
  `odoo-instance-ops`) - this is a MUST, not a judgment call. `odoo-backend-coder` and
  `odoo-frontend-coder` are BOTH INSTANCE-FREE - neither self-provisions; each runs only its own
  static gate (ORM-validation for the backend leg, `verify-frontend.sh` for the frontend leg), and
  any live check is owned by the `odoo-coder` coordinator's integrated test or a delegated
  `odoo-instance` run - the lint-class gate runs ONCE at
  `run-harness`'s pre-PR tail, never inside either leaf. `odoo-test-writer` never self-provisions:
  it runs its baseline and break-checks through `odoo-instance` inline on the forwarded handle's
  database, on ONE lease of its own that it releases before returning
  (`${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md` § Test build on a forwarded handle). Contract:
  `${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md`.
  **Self-provisioning carries teardown:** what you acquire under this carve-out you
  `lease_release` (or `lease_park`) before your terminal status -
  `${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T1.

  **It also requires a `RUN_ID`, and no handle does not mean no owner.** Acquire under the
  `RUN_ID` your brief carries (the `run_id` of every lease call you make). If it carries none,
  STOP with `NEEDS_CONTEXT(RUN_ID)` - do not invent one and do not acquire without one. An
  invented id is worse than none: the lease looks owned to the registry while being invisible to
  the only run that could release it, so it survives every audit and every janitor until a human
  finds it.

## How your turn ends

Your launcher receives your completion report ONCE, as the last act of your dispatch - the 3-part
shape owned by `${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md`, handed back after teardown
through `SubagentHandback` when you have it, else as your final text
(`${CLAUDE_PLUGIN_ROOT}/snippets/spawner-completion-contract.md` R3). Never send it to anyone,
never look for a reply address, and never treat a messaging tool's presence in your toolset as an
instruction to use one: you launch nothing, so you hold no legal send target at all.

**Three things will look like a way back up. None is** - spelled out here because you are a leaf
and the contract that argues it is addressed to spawners; a rule without its reason is the one a
model talks itself out of. (a) Nothing to answer: your launch handed you a BRIEF, not an envelope,
so you hold no `from`. (b) Nothing to look up: no listing or name-to-address lookup exists for you,
at any depth - a messaging tool is not an address book. (c) `main` does NOT fail, and that is the
trap: from a nested position the send succeeds into the ROOT conversation, which is not waiting for
you, while your launcher still receives only your report.

So a failed send is never answered by a different name. Guessing - a plugin id, a skill name, an
agent type, a label from a worklog - costs turns and resolves nothing. Hand the report back as above.
