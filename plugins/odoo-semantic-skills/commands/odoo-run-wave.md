---
name: odoo-run-wave
description: |
  Kick off a depth-0 multi-subagent git-wave orchestration: integration branch + WI worktrees + cherry-pick + end-of-wave Opus review + PR + squash + tree-identity gate + human-confirm merge
---
# /odoo-run-wave

Thin dispatcher for the `wave` skill. Accepts an optional `$ARGUMENTS` token describing
the set of work items to parallelize. All orchestration logic lives in the skill body -
this command is a recipe shim only, following the 1-orchestration-SSOT rule.

> Named `odoo-run-wave` (not `wave`) because a command name must stay disjoint from the
> skill name `wave`. Describe a wave to intake, or run this command, to start the wave
> skill - one orchestration mechanism, two entry points.

## When to use

Type `/odoo-run-wave` when you want to land a set of related changes via a safe parallel
multi-subagent orchestration:

- **2-3 work items** - planning gate + WI worktrees + sequential cherry-pick + end-of-wave review + PR
- **4+ work items** - full plan artifact at `.odoo-ai/wave/<slug>/plan.md`, topology diagram,
  disjoint ownership map, human-confirm gate at every critical step
- **Single-WI minimal** - skip the plan file, go straight to integration branch + 1 worktree

For a **single-file change** with no parallelism: use `odoo-backend-coding` or `odoo-code-review` instead.
For a **requirement scoping / BRL** task: use `odoo-brl` instead.
For **in-context skill chaining** (no git): use `workflow-chaining` instead.

## Hard rules

1. **Plan gate mandatory.** Wave emits a topology + ownership map + human-merge note and
   stops. No branch is created until you approve.
2. **Principal branch locked.** The skill never commits, rebases, or force-pushes to the
   branch you were on when you started. All work happens on an integration branch and WI
   worktrees.
3. **Human-confirm merge.** The wave skill always stops before the final merge and waits
   for your explicit confirmation. Auto-merge is never allowed.
4. **Depth-0 only.** This command invokes a depth-0 skill (self-spawning). Do not call it
   from inside a subagent.
5. **NL-dispatch only.** This command fires the `wave` skill via a natural-language prompt
   matching the skill's description. The Skill tool is never used.

## Invocation

### Step 0 - Parse arguments + dispatch

1. Extract the work-item description from `$ARGUMENTS`. If absent, ask the user for a
   brief description of the changes to parallelize.
2. Fire the `wave` skill via NL dispatch:

> "Run a git-wave orchestration for these work items: [WORK_ITEMS]. Produce a plan gate
> (topology + disjoint ownership map + human-merge note) before creating any branch.
> Follow all principal-branch-lock and human-confirm-merge hard rules."

The skill handles all phases (Phase 0 discovery + plan gate -> integration branch +
worktrees -> WI dispatch -> cherry-pick -> end-of-wave Opus review -> PR + squash +
tree-identity -> human-confirm merge + cleanup).

## Standalone fallback

If git or worktree ops are unavailable in the current environment, the skill
degrades to producing the plan artifact and ownership map only - no branches are created.
The plan can be executed manually or in a separate session. See skill body
`## Standalone-first fallback` section.

## Examples

```
/odoo-run-wave add wave orchestration skill + wiring + packaging (3 WI)
```
Emits a plan gate: topology, WI ownership map, model tier per WI, human-merge note.
After approval: integration branch -> 3 WI worktrees (parallel Sonnet) -> cherry-pick A->B->C ->
end-of-wave Opus review -> 1 PR -> /code-review -> squash + tree-identity -> stop for human merge.

```
/odoo-run-wave
```
Prompts for work-item description. Same flow.

## What this command does NOT do

- Does NOT create any branch before you approve the plan gate
- Does NOT merge automatically - human confirmation is mandatory
- Does NOT guarantee parallel WI count above 3 (OOM cap enforced by the skill)
- Does NOT replace human review of the squash diff before merge
