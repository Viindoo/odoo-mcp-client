---
name: odoo-forward-port
description: |
  Forward-port Odoo commits from a source branch or series to a target branch using
  continuous merge (SHA-preserving, not cherry-pick) or one-shot cherry-pick. Extracts
  the INTENT of each commit, runs OSM-grounded symbol-survival checks, adapts code and
  tests to the target platform, verifies behavior via red-then-green test toggle, and
  produces one merge commit per batch. Gates: plan (commit list + model tier + scope)
  before any branch or git op; human-confirm before each merge commit. Module-new at
  source lands as installable:False. Invoke for "forward port these fixes to v18",
  "port PR to target", "continuous FP from v17 to v18", "port commit lên series cao"
---
# /odoo-forward-port

Thin dispatcher for the `odoo-run-forward-port` skill. Accepts `$ARGUMENTS` in the form:
`<source-ref> <target-branch> [--scope <modules>] [--since <sha>] [--one-shot]`

All orchestration logic - intent extraction, model dispatch, OSM API checks, symbol-survival,
adaptation, behavior verification, merge commit assembly - lives in the skill body.
This command is a recipe shim only, following the 1-orchestration-SSOT rule.

> Named `odoo-forward-port` (not `odoo-run-forward-port`) to keep the command name disjoint
> from the skill name. One orchestration mechanism, two entry points (this command and NL
> description matching the skill).

## When to use

Type `/odoo-forward-port` when you want to continuously port a set of commits from a
lower-version source branch to a higher-version target branch:

- **1-5 commits** - plan gate + intent-extract per commit (parallel) + adapt each commit
  serially (one module at a time per commit) + behavior verify + one merge commit
- **6+ commits** - full plan artifact at `.odoo-ai/forward-port/<slug>/plan.md`,
  commit topology, model tier per commit, human-confirm gate per merge batch
- **Continuous mode (default)** - recurring; source keeps evolving; SHA preserved so
  merge-base advances and past conflicts are never re-resolved

For a **single file hotfix** with no version gap: use `odoo-coding` instead.
For an **upgrade plan** (risk + deprecation + diff): use `/odoo-plan-upgrade` instead.
For **version-to-version API delta only** (no merge, no adapt): use `odoo-version-diff` instead.

## Hard rules

1. **Plan gate mandatory.** Skill emits commit list + model tier + scope summary and
   stops. No branch, no intent extraction, no git op until explicit user approval.
2. **Merge strategy only (continuous).** The skill uses `git merge --no-ff --no-commit`
   to preserve SHA and advance merge-base. Cherry-pick and squash are disallowed for
   continuous mode. One-shot mode (`--one-shot`) uses cherry-pick only when explicitly stated.
3. **Human-confirm merge.** Skill stops before every merge commit and waits for
   explicit user confirmation. Auto-merge is never allowed.
4. **Target-branch lock.** Never checkout, commit, rebase, or force-push directly on the
   target branch. All work happens in a dedicated integration worktree branched from the target.
5. **Module-new lands as installable: False.** Any module first seen at the source side
   is ported with `installable: False`. Lint fixes are allowed; no lateral upgrades.
6. **Forward INTENT, not code.** Each adaptation subagent receives the extracted intent
   (business behavior, purpose), not the diff. Code is the translation artifact.
7. **Symbol-survival before adapt.** After every merge, OSM-ground every source-side symbol
   in conflicted AND merge-clean-but-source-touched files against the target surface before
   any adapt starts. This catches autosilent field breaks (no conflict marker, runtime crash).
8. **NL-dispatch only.** This command fires the `odoo-run-forward-port` skill via NL.
   NL-dispatch keeps this shim minimal (a Skill-tool call is equally valid for a depth-0
   caller per nesting-guard; either path reaches the skill).
9. **Depth-0 only.** Do not call this command from inside a subagent.

## $ARGUMENTS schema

```
/odoo-forward-port <source-ref> <target-branch> [--scope <mod1,mod2>] [--since <sha>] [--one-shot]
```

| Argument | Required | Description |
|---|---|---|
| `<source-ref>` | yes | Source branch or commit range (e.g. `origin/17.0`, `v17-fixes`) |
| `<target-branch>` | yes | Target branch (e.g. `origin/18.0`, `18.0-fp-batch-01`) |
| `--scope <modules>` | no | Comma-separated module list; default = all modified modules in range |
| `--since <sha>` | no | Only commits after this SHA (for continuous or incremental FP) |
| `--one-shot` | no | Cherry-pick mode for a single one-time port (default: merge mode) |

## Invocation

### Step 0 - Parse arguments

1. Extract `source-ref`, `target-branch`, optional `--scope`, `--since`, `--one-shot` from
   `$ARGUMENTS`. If `source-ref` or `target-branch` is absent, ask in a single brief message.
2. Check for an existing checkpoint at `.odoo-ai/forward-port/<slug>/checkpoint.json`.
   If found, ask: "Resume previous FP job [slug] from [last-completed-commit]? (yes / new)"

### Step 1 - Dispatch

Fire the `odoo-run-forward-port` skill via NL (substitute real values, never leave placeholders):

> "Run a continuous forward-port from [SOURCE_REF] to [TARGET_BRANCH].
> Scope: [SCOPE or 'all modified modules'].
> Commits since: [SINCE_SHA or 'branch divergence point'].
> Mode: [merge | one-shot cherry-pick].
> Produce a plan gate (commit list + model tier per commit + scope summary) before
> any branch or git op. Follow all hard rules: no auto-merge, target-branch-lock,
> symbol-survival check after each merge, installable:False for new modules,
> forward INTENT not code, human-confirm before each merge commit.
> Write checkpoint.json after each commit batch."

The skill handles all phases:
```
P0 PLAN GATE -> P1 intent-extract (parallel) -> P2 4-outcome classify ->
P3 git merge --no-commit -> P3.5 symbol-survival check ->
P4 adapt+verify (test-first) -> P5 verify-by-behavior (per batch) ->
P6 GATE MERGE -> P7 PR + review
```

## Resume

If a previous FP job was interrupted:

> "Resume forward-port job [slug] for [SOURCE_REF]->[TARGET_BRANCH] from last checkpoint."

The skill reads `checkpoint.json`, skips commits with `status=done`, and continues from the
last incomplete batch.

## Standalone fallback

If the odoo-semantic-mcp server is unreachable, the skill degrades but does not stop: API
compatibility checks are marked `[unverified - OSM offline]`, symbol-survival falls back to
grep on the target checkout, adaptation proceeds with LLM reasoning only. The merge commit
message notes degraded mode. See skill body `## Standalone-first fallback` section.

## Examples

```
/odoo-forward-port origin/17.0 origin/18.0 --scope l10n_vn,l10n_vn_viin --since abc1234
```
Emits plan gate: 3 commits, scope 2 modules, model tier Sonnet (medium complexity).
After approval: 3 intent-extraction agents in parallel (read-only) -> symbol-survival check ->
adapt each commit serially (one module at a time per commit, worktree per module for isolation)
-> verify-by-behavior (red-then-green) -> GATE MERGE -> merge commit -> checkpoint.

```
/odoo-forward-port origin/17.0 origin/18.0 --one-shot
```
One-shot cherry-pick mode for a single frozen batch. Same intent-extract -> classify ->
symbol-survival -> adapt -> verify -> gate flow; cherry-pick instead of merge.

```
/odoo-forward-port
```
Prompts for source-ref and target-branch. Same flow.

## Output

| Artifact | Path |
|---|---|
| Plan | `.odoo-ai/forward-port/<slug>/plan.md` |
| Intent extracts | `.odoo-ai/forward-port/<slug>/intents/<sha>.md` |
| Checkpoint | `.odoo-ai/forward-port/<slug>/checkpoint.json` |
| Merge log | `.odoo-ai/forward-port/<slug>/merge-log.md` |

All paths are gitignored. The only git artifact is the merge commit on the integration
branch, which lands on the target via a human-confirmed PR.

## What this command does NOT do

- Does NOT create any branch or extract any intent before plan gate approval
- Does NOT merge automatically - human confirmation is required per batch
- Does NOT force-push or rebase the target branch
- Does NOT upgrade modules new at source beyond installable:False + lint fix
- Does NOT guarantee OSM availability - degrades gracefully when unreachable
- Does NOT squash merge commits (SHA preservation is non-negotiable for continuous mode)
