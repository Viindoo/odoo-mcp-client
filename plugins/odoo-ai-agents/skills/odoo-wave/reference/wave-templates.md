# Wave Orchestration - Reference Templates

On-demand reference for `skills/odoo-wave/SKILL.md` (the git-executor). Load this file when you need
the full template text for any of the structures below. Do not load it on every invocation.

> "wave" in this file is the integration-topology CONCEPT (wave-batch, wave-templates), not a
> user-invocable skill. The executor `odoo-wave` is consume-only: it CONSUMES the plan's WI list +
> wave-batched module-DAG + topology and INVOKES `odoo-coding` per WI; it never self-derives a plan
> and never chooses agent/model.

---

## Repo Capability Card Template

Fill this once at Phase 0 and embed it verbatim in every WI subagent brief.

```
Repo Capability Card
  base          : <principal branch name>
  verify        : <command that must pass after every cherry-pick, e.g. "make test" or "make gen-check && make deps-check && make test">
  commit        : <conventional commit style, e.g. "conventional: feat(scope): ..., fix(scope): ...">
  confidential  : <public | restricted | internal>
  worktree_root : <parent path for wave worktrees, outside the repo tree>
```

Notes:
- Discover `verify` from Makefile targets, CI config, or README. If multiple commands
  are required, chain them with `&&`.
- `confidential: restricted` triggers the 8-group ban check on every artifact.
- `worktree_root` should be outside the repo tree to avoid accidental staging of wave files by git.

---

## Four Topology Patterns

Choose at Phase 0 based on file-ownership and dependency analysis.

### Independent (most common)

All WIs modify disjoint files with no ordering dependency.
Cherry-pick in any order. Maximum parallelism.

```
principal ──────────────────────────────────────────► (unchanged)
             │
             └─► integration ─── cherry-pick A ─── cherry-pick B ─── cherry-pick C ──► PR
                     │
                 WI-A ──► commit-A
                 WI-B ──► commit-B    (all parallel)
                 WI-C ──► commit-C
```

### Linear

WI-B depends on WI-A output (e.g., WI-B's code calls a function WI-A introduces).
Dispatch sequentially; cherry-pick A before dispatching B.

```
principal ────────────────────────────────────────────► (unchanged)
             │
             └─► integration ─── cherry-pick A ─── cherry-pick B ──► PR
                     │
                 WI-A ──► commit-A
                              └─► (WI-B dispatched after WI-A commits)
                                  WI-B ──► commit-B
```

### Mixed

Some WIs are independent, some sequential. Cherry-pick independent WIs first,
then the sequential group.

```
principal ──────────────────────────────────────────────────────────► (unchanged)
             │
             └─► integration ─── cherry-pick A ─── cherry-pick C ─── cherry-pick B ──► PR
                     │
                 WI-A ──► commit-A   (independent)
                 WI-C ──► commit-C   (independent, parallel with A)
                              └─► (WI-B depends on A+C; dispatched after both commit)
                                  WI-B ──► commit-B
```

### Diamond

WI-B and WI-C both depend on WI-A but are independent of each other.
Cherry-pick A first, then dispatch B and C in parallel.

```
principal ────────────────────────────────────────────────────────────► (unchanged)
             │
             └─► integration ─── cherry-pick A ─── cherry-pick B ─── cherry-pick C ──► PR
                     │
                 WI-A ──► commit-A
                              ├─► WI-B ──► commit-B   (parallel after A)
                              └─► WI-C ──► commit-C   (parallel after A)
```

---

## Execution-log Template

odoo-wave does NOT author the plan - it CONSUMES the approved plan (`odoo-planning` is the producer).
This template is the run-local EXECUTION LOG odoo-wave writes to `.odoo-ai/wave/<slug>/plan.md`
(gitignored): the consumed topology + WI map, the cherry-pick / saga-checkpoint log, the review log,
and the PR/squash result. It records what odoo-wave did, not what to do.

```markdown
# Wave Plan: <slug>

Generated: <ISO datetime>
Principal branch: <name>
Integration branch: wave/integration-<slug>

## Repo Capability Card

  base          : <principal>
  verify        : <command>
  commit        : <convention>
  confidential  : <level>
  worktree_root : <path>

## Topology

<independent | linear | mixed | diamond>

<Paste the relevant ASCII diagram from above, filled in with WI IDs>

## Work Items

| ID | Branch | Worktree path | Files in scope | Status |
|---|---|---|---|---|
| WI-A | wave/wi-<slug>-a | <path> | <file list> | pending |
| WI-B | wave/wi-<slug>-b | <path> | <file list> | pending |
| ... | | | | |

## Ownership Map

```
WI-A owns: [file1, file2, ...]
WI-B owns: [file3, file4, ...]
WI-C owns: [file5, ...]
```
(Sets must be disjoint. File appearing in two WIs = blocker.)

## Cherry-pick Log

| WI | Commit SHA | Verify result | Notes |
|---|---|---|---|
| WI-A | pending | - | |
| WI-B | pending | - | |
| ... | | | |

## Review Log

| Phase | Reviewer | Findings | Fixed |
|---|---|---|---|
| 4.1 Opus review | Opus | <summary> | <yes/no + detail> |
| 4.2 odoo-code-review | odoo-code-review skill | <findings> | <yes/no + detail> |

## PR

URL     : <to be filled>
Squash  : <backup ref> -> tree-identity <confirmed | FAILED>
Status  : <open | merged | closed>

## Cleanup

- [ ] WI worktrees removed
- [ ] WI branches deleted
- [ ] Integration branch deleted (after merge)
- [ ] Backup tag deleted
- [ ] .odoo-ai/wave/<slug>/ removed
```

---

## Cleanup Checklist

Post-merge cleanup is owned by `odoo-pr-monitoring` (it runs AFTER the `L2-merge-gate` merge);
odoo-wave itself stops at the `L2-squash-gate` and never merges or cleans up the integration branch.
This checklist is the one the post-merge owner runs.

Invoke the **`git-toolkit:git-ops`** skill (via the Skill tool) in one request (op=wave-cleanup):

```
[ ] remove worktree <path>/wi-a        (and all other WI worktrees)
[ ] remove worktree <path>/integration
[ ] delete branch wave/wi-<slug>-a     (and all other WI branches)
[ ] delete branch wave/integration-<slug>   (after merge confirmed on remote)
[ ] delete tag wave-backup-<slug>
[ ] worktree-prune                     (clean stale worktree refs)
```

Local (run inline): `rm -rf .odoo-ai/wave/<slug>/` (gitignored; safe to delete)

Verify after cleanup (bounded reads inline):
`git worktree list` should show only the principal worktree.
Confirm wave branches are gone (git-ops reports deletion success).

---

## Squash Tree-Identity Recipe (git-ops delegation)

All mutation steps are delegated to git-toolkit via the **`git-ops`** skill
(see `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`).

**git-ops request - squash-push operation:**

```
op                 : squash-push
worktree           : <path>/integration
principal          : <principal-branch-name>
backup-ref         : wave-backup-<slug>
commit-msg         : <conventional commit message>
integration-branch : wave/integration-<slug>
confirmed          : yes - <human approval covering the L2-squash-gate force-push (run-harness L2 + git-toolkit confirm backstop)>
```

git-ops executes the `squash-push` recipe (stale-base guard -> S1 backup -> reset-soft squash-to-one -> S6 tree-identity gate -> S2 force-with-lease), owned by git-toolkit per its git-safety-contract S1/S6/S2.

After git-ops returns, confirm its reported tree-identity exit code is 0. This is odoo-wave's
terminal step (the L2-squash-gate) - it STOPS here and does NOT merge; the merge is owned by
`odoo-pr-monitoring` at the L2-merge-gate.

---

## Confidentiality Long-Form - 8 Banned Groups

When `confidential: restricted` or `confidential: internal` in the Repo Capability Card,
enforce these 8 groups in ALL artifacts, commit messages, and subagent outputs:

1. **CEO personal info** - salary, personal decisions, personal health, personal comms
2. **Customer PII / contracts** - names (use Customer-A), deal sizes, contract terms, SLAs
3. **Internal pricing** - VND rates, discount structures, partner margins, cost basis
4. **Competitor intelligence** - non-public analysis, win/loss data, internal benchmarks
5. **Product roadmap** - unannounced features, internal milestones, R&D directions
6. **Marketing in-draft** - unreleased campaigns, launch dates, messaging that is not public
7. **OKR / targets** - revenue targets, growth metrics, internal KPIs
8. **Internal-tooling paths** - any absolute machine path (user home dirs, temp dirs) or
   note-store reference that reveals internal infrastructure

For each group: if the user prompt contains such data, acknowledge the intent but do not
echo the data into any committed file. Use abstract placeholders instead.

For public repos (confidential: public): standard open-source caution applies. No machine
paths, no personal info. Groups 1-3 and 5-8 still apply to avoid accidental leakage.

---

## Per-WI Integration Loop (Pseudocode)

Pseudocode for the Phase 2/3 integration loop. Referenced from SKILL.md Phase 2. Key shift from the
legacy design: odoo-wave does NOT dispatch anonymous WI workers and owns no weighted budget - it
INVOKES the `odoo-coding` SKILL per WI (which owns its own coder count + Mode-B budget), then
cherry-picks the returned SHA(s). Because a Skill invocation loads in the single orchestrating
context, WIs are processed SEQUENTIALLY in module-DAG order; the parallel fan-out lives INSIDE each
`odoo-coding` invocation.

```text
# Phase 2/3 - per-WI: ensure worktree -> INVOKE odoo-coding -> cherry-pick (saga). Sequential.
# SSOT for the saga/rollback + checkpoint contract: skills/_shared/integration-loop.md (do not restate).
# SSOT for the coder fan-out + Mode-B OOM budget: odoo-coding + skills/_shared/concurrency-guard.md.

pre_wave_sha = tip(integration)            # saga anchor (integration-loop.md step 1)
cherry_picked = {}                          # WI id -> True once ON integration + verified

for wi in topological_order(wis):           # module-DAG / wave order; dependents after deps
    if any(not cherry_picked.get(d) for d in wi.depends_on):
        record(wi, "upstream blocked"); apply_saga_rollback(); return  # terminate the WHOLE wave

    ensure_worktree(wi)                     # git-ops worktree-add (lazy for dependents,
                                            # forking an up-to-date integration that holds dep commits)

    # INVOKE odoo-coding via the Skill tool from THIS orchestrating context (legal: spawner ban is
    # leaf-only). Pass inputs only so odoo-coding's Plan-provided fast-path consumes them. odoo-coding
    # owns count+model and authors+commits INSIDE wi.worktree; it returns the commit SHA(s). NO cherry-pick.
    result = Skill("odoo-coding", wi_invocation_brief(wi))   # synchronous, in-context
    if result.status != "DONE" or not result.shas:
        record(wi, result); apply_saga_rollback(); return    # DONE with no SHA = failed contract

    # cherry-pick: orchestrator-side CRITICAL SECTION, one at a time, topology order.
    wi_failed = False
    for sha in result.shas:
        cherry_pick(sha, into=integration)  # invoke git-ops in the INTEGRATION worktree
        if conflict: resolve_conflict(wi)   # Phase 3 Sonnet resolver (worker-brief.md) + cherry-pick --continue
        if not run_verify():                # Repo Capability Card verify after each pick
            wi_failed = True; break          # stop picking THIS WI's commits (inner loop only)

    if wi_failed:                           # verify failed mid-WI -> terminate the WHOLE wave:
        record(wi, "verify failed")          #   do NOT checkpoint and do NOT mark this WI cherry-picked
        apply_saga_rollback(); return        #   clean-abort/resume; never build on a rolled-back branch

    checkpoint(wi, tip(integration), "PASS")  # integration-loop.md step 2 (ONLY on full WI success)
    cherry_picked[wi] = True                  # unblock dependents ONLY after cherry-picked + verified

# apply_saga_rollback(): clean-abort (reset-hard to pre_wave_sha) OR resume from last passing
# checkpoint; never leave a half-built integration branch. Full contract: integration-loop.md.
# `return` ends the wave loop entirely (matches integration-loop.md clean-abort): a failed/blocked WI
# is never recorded PASS and the loop never continues onto a rolled-back integration branch.
```

---

## Examples

> odoo-wave is consume-only and `user-invocable: false` - it is dispatched by run-harness with an
> APPROVED plan, never by a user prompt. These examples start from the dispatch, not a user phrase.

**Example 1 - Standard 3-WI wave-layer:**
Dispatch: run-harness dispatches odoo-wave with 3 independent WIs (computed field on sale.order, an
OWL widget, a unit-test update) + their module-DAG + `independent` topology.
Action: Phase 0 verifies disjoint ownership (safety audit) and consumes the DAG/topology. Phase 1
creates the integration branch + 3 worktrees. Phase 2 INVOKES `odoo-coding` per WI sequentially
(each odoo-coding owns its own coder count/model). Phase 3 serializes each cherry-pick onto
integration, verifying + checkpointing after each. Phase 4 opus cross-cutting review + odoo-code-review
inline. Phase 5 opens 1 PR, squashes (tree-identity verified), STOPS at the L2-squash-gate. No merge.

**Example 2 - Dependency edge consumed (linear):**
Dispatch: plan's module-DAG has WI-B `depends_on` WI-A.
Action: cherry-pick A first; then lazily fork WI-B's worktree from the updated integration; INVOKE
`odoo-coding` for B; cherry-pick B. odoo-wave never recomputes the edge - it consumes it from the plan.

**Example 3 - Ownership conflict (safety audit catches a bad plan):**
Dispatch: the plan maps models.py to both WI-A and WI-B.
Action: Phase 0.2 disjoint-ownership audit finds models.py in both scopes. STOP BLOCKED: report the
overlap and route back to `odoo-planning` to re-partition. No worktree is created.

**Example 4 - Squash mismatch abort:**
Context: squash step on a 4-WI integration branch.
Action: `git diff --quiet wave-backup-<slug>` exits 1 (tree mismatch). Abort: "Squash tree-identity
FAILED - the squashed commit does not match the pre-squash tree. Restoring from wave-backup-<slug>.
Do NOT force-push." Report the differing files.

**Example 5 - Conflict resolver path:**
WI-A and WI-B unexpectedly both touch `__init__.py` (missed by the plan; caught at cherry-pick):
Cherry-pick of WI-B fails with conflict. Dispatch a Sonnet resolver subagent (worker-brief.md) with
the conflict diff + both WI briefs. Resolver edits the conflicting files (markers removed). odoo-wave
re-invokes git-ops (cherry-pick --continue). Re-run verify, checkpoint, continue.

**Example 6 - Mid-wave failure (saga rollback):**
A cherry-pick verify cannot be made green within the loop's bound. Apply the
`integration-loop.md` saga: clean-abort (reset-hard to the pre-wave SHA) or resume from the last
passing checkpoint; report the failing WI. Never leave a half-built integration branch.
