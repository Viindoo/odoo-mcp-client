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
launches the three hard-leaf teammates - `odoo-test-writer` (RED test, first), `odoo-backend-coder`
and/or `odoo-frontend-coder` (code to green) - per R0
(`${CLAUDE_PLUGIN_ROOT}/snippets/spawner-completion-contract.md`: its own launch capability exposes a
blocking switch (`run_in_background: false`), so it blocks on each teammate it needs an answer from),
tests the integrated module via `Skill(odoo-instance)` inline, and - once the integrated test is
green - COMMITS its module by invoking `git-toolkit:git-ops` via the Skill tool, then
returns the SHA to `odoo-coding` (which collects it and no longer re-commits). See
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
  Unlike git-ops, `odoo-backend-coder` (for its bounded `/test_lint` gate) and the other
  instance-touching leaves MAY invoke `Skill(odoo-instance)` to self-provision a live Odoo instance
  when handed NO `INSTANCE_HANDLE`, or when your brief carries `SELF_PROVISION: worktree-addons`.
  This is allowed because `odoo-instance` applies the instance HARD RULES (`en_US` union, Viindoo
  `to_base`, lint-module install, per-version `cli_help` grounding) AND resolves addons provenance -
  it re-roots the addons list onto your `WORKTREE_PATH` so the instance loads YOUR code, not the
  principal checkout; do NOT call `scripts/lib/allocator.py` directly, which would bypass all of
  that. A provided `INSTANCE_HANDLE` always wins: consume it, never re-provision - unless your brief
  carries `SELF_PROVISION: worktree-addons`
  (`${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md` § Worktree-addons carve-out). Because
  you are a declared HARD LEAF, `odoo-instance` runs INLINE for you (never launches
  `odoo-instance-ops`) - this is a MUST, not a judgment call. `odoo-frontend-coder` is
  INSTANCE-FREE - it never self-provisions; its only gate is the static `verify-frontend.sh`, and
  any live check is owned by the `odoo-coder` coordinator's integrated test or a delegated
  `odoo-instance` run. Contract: `${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md`.
  **Self-provisioning carries teardown:** what you acquire under this carve-out you release
  before your terminal status - `${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md`
  T1/T3.

## Agent Team mode keys

`CALLER_ID`/`REPLY_TO` is **NOT** conditional on team mode, unlike the other two keys below:
`${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md` field 11 classifies it ALWAYS - every caller
composing a brief states it in EVERY dispatch, regardless of CHP tier. Only the DELIVERY
MECHANISM for your own completion report is tier-conditional (`SendMessage` push under Tier-A,
final-message transcript-return under Tier-C - Transport rule owned by
`${CLAUDE_PLUGIN_ROOT}/snippets/spawner-completion-contract.md`), never whether the caller had to
state the field. `TASK_ID` and `NOTIFY` ARE genuinely conditional - present only when the
orchestrator dispatches you as a named TEAMMATE (Agent Team mode); their absence means team mode
is off and you behave as today (final message + Continuation Contract). `REPLY_TO` is also listed
as a POINTER on the caller-side skeleton (`dispatch-brief.md` field 11, `CALLER_ID`) so a caller
composing a brief from that file alone still learns the obligation exists - this file stays the
one place the field's worker-side semantics are defined:

```
TASK_ID: <id>          # Agent Team mode ONLY - the task-board id for your work-item (Ask 2, ${CLAUDE_PLUGIN_ROOT}/snippets/agent-team-protocol.md owns the TaskUpdate lifecycle - do not re-derive it here). Whatever terminal label your task-list tool exposes, mark it the instant you have a terminal Continuation Contract status to report - the task-board label is a coarse MIRROR of that status, never the authority (${CLAUDE_PLUGIN_ROOT}/snippets/spawner-completion-contract.md R1): the real outcome (DONE/BLOCKED/NEEDS_NEXT/NEEDS_CONTEXT) rides ONLY the Ask-1 SendMessage push below. Absent when team mode is off.
REPLY_TO: <launcher>  # present in EVERY brief (dispatch-brief.md field 11), regardless of tier - ALWAYS the agent that launched you, supplied by that launcher; `main` ONLY when the main context launched you directly. A coding worker's `REPLY_TO` is ALWAYS its `odoo-coder` coordinator, never `main`. Report to `REPLY_TO`, never a higher ancestor, and if this field is ABSENT from your brief, do NOT guess or default to `main` - `${CLAUDE_PLUGIN_ROOT}/snippets/spawner-completion-contract.md` R3 is the ONE place both the addressing rule and the absent-REPLY_TO fallback are defined (do not restate either here - read R3 by path). Do NOT hardcode `main` in your body; defer to this field.
NOTIFY: <names>        # Agent Team mode ONLY - peer teammate names that depend on your output; SendMessage each too. `none` if no dependents; absent when team mode is off.
```

End your turn with a `SendMessage` completion report to `REPLY_TO` (and each `NOTIFY` peer) per
`${CLAUDE_PLUGIN_ROOT}/snippets/agent-team-protocol.md` when `SendMessage` is in your toolset -
never end on a bare tool call or plain-text-only output. When `SendMessage` is absent, return the
report as your final message instead (Tier-C transcript-return) - `REPLY_TO` still names who that
transcript is FOR even though no explicit push is possible.

**A failed or unaddressable send means RETURN INLINE - never wait.** If `REPLY_TO` is absent or
unroutable, or `SendMessage` fails, return your completion report as your final message. Never guess
an address, never broadcast to `main`, never end on a bare tool call or on plain text with no report.
