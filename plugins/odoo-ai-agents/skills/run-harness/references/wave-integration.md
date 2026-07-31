# Wave Integration - Reference Templates

On-demand reference for `skills/run-harness/SKILL.md` § Between-wave integration. Load this file
when you need the full template text for any of the structures below. Do not load it on every
invocation.

> "wave" in this file is the integration-topology CONCEPT (wave-batch, wave-templates), not a
> user-invocable skill. run-harness is consume-only: it CONSUMES the plan's MODULE list +
> wave-batched module-DAG + topology + **Block 2W** worktree lineage and INVOKES `odoo-coding` per
> module; it never self-derives a plan and never chooses agent/model. The outer unit is the MODULE;
> the work-item is `odoo-coder`'s INTERNAL intra-module unit and never appears here. run-harness
> owns the between-wave integration directly (there is no separate git-executor skill).

---

## Repo Capability Card Template

Fill this once at the start of the coding waves and embed it verbatim in every per-module
`odoo-coding` brief.

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

## Topology values (five)

Choose from the plan's Block-2 module-DAG (independent / linear / mixed / diamond / single). run-harness does
NOT re-derive the topology - `odoo-planning` produces it; this is the reference for reading it. The
nodes are MODULES (the outer unit); the intra-module work-item split is `odoo-coder`'s PRIVATE
concern and never a topology node here.

### Independent (most common)

All modules touch disjoint files with no ordering dependency.
Cherry-pick in any order. Maximum parallelism.

```
base ────────────────────────────────────────────► (unchanged)
             │
             └─► run-integration ─── cherry-pick A ─── cherry-pick B ─── cherry-pick C ──► close wave
                     │
                 mod-A ──► commit-A
                 mod-B ──► commit-B    (all parallel)
                 mod-C ──► commit-C
```

### Linear

module-B depends on module-A output (e.g., module-B's code calls a function module-A introduces).
Dispatch sequentially; cherry-pick A before dispatching B.

```
base ──────────────────────────────────────────────► (unchanged)
             │
             └─► run-integration ─── cherry-pick A ─── cherry-pick B ──► close wave
                     │
                 mod-A ──► commit-A
                              └─► (mod-B dispatched after mod-A commits)
                                  mod-B ──► commit-B
```

### Mixed

Some modules are independent, some sequential. Cherry-pick independent modules first,
then the sequential group.

```
base ────────────────────────────────────────────────────────────► (unchanged)
             │
             └─► run-integration ─── cherry-pick A ─── cherry-pick C ─── cherry-pick B ──► close wave
                     │
                 mod-A ──► commit-A   (independent)
                 mod-C ──► commit-C   (independent, parallel with A)
                              └─► (mod-B depends on A+C; dispatched after both commit)
                                  mod-B ──► commit-B
```

### Diamond

module-B and module-C both depend on module-A but are independent of each other.
Cherry-pick A first, then dispatch B and C in parallel.

```
base ──────────────────────────────────────────────────────────────► (unchanged)
             │
             └─► run-integration ─── cherry-pick A ─── cherry-pick B ─── cherry-pick C ──► close wave
                     │
                 mod-A ──► commit-A
                              ├─► mod-B ──► commit-B   (parallel after A)
                              └─► mod-C ──► commit-C   (parallel after A)
```

### Single (the collapse case)

`n <= 1`, where `n` is the number of modules THIS wave dispatches. There is nothing to integrate
against a sibling, so the WORK tier buys nothing: dispatch the one module DIRECTLY into the
already-provisioned JOB-tier integration worktree.

- NO child worktree, NO branch, NO cherry-pick, NO converge, NO per-module saga checkpoint.
- The commit lands on the integration branch itself; the wave's close-gate and AUTO-ADVANCE are
  unchanged.
- The saga reduces to the integration branch's own history - record the pre-wave SHA, skip the
  per-module checkpoint (`${CLAUDE_PLUGIN_ROOT}/skills/_shared/integration-loop.md` § Saga / rollback).

```
base --------------------------------------------------> (unchanged)
             |
             +--> run-integration --- mod-A committed in place --> close wave
```

**Why the threshold is 1 and not "when parallelism is low".** For `n >= 2` the child worktree buys
POISON-CONTAINMENT: a module whose adapt fails leaves its partial edits in its own tree, so prior
no-ff merges on integration stay clean and the wave can abort to the pre-wave SHA without unpicking a
half-written sibling. That is the reason even where dispatch is SEQUENTIAL - do NOT justify the WORK
tier as an `index.lock` race, which does not exist when modules are dispatched one at a time.

**Absent field -> today's fan-out.** A wave node with no `topology` value takes the child-worktree
path. Never infer `single` from a missing field.

> Cross-WAVE lineage (Block 2W): there is ONE **run-integration** branch, forked from base/principal
> ONCE at run start; every wave's module worktrees fork from IT (not from base, not from a per-wave
> branch). Of the five topology values above, the four multi-module topologies (independent / linear /
> mixed / diamond) describe the module ordering INSIDE one wave; `single` collapses the wave to one
> module and has no internal ordering to describe. Each wave ends at
> the cumulative close-gate and AUTO-ADVANCES (no per-wave PR - the "close wave" terminal above). The
> run opens exactly ONE PR after the FINAL wave (the terminal `integrate` land-tail). Because
> run-integration already carries all PRIOR waves' cherry-picked code, a dependent module's worktree
> already carries its dependencies' committed code (the fork-from-integrated-parent property, now on
> ONE branch). SSOT for the lineage:
> `${CLAUDE_PLUGIN_ROOT}/skills/odoo-intake/references/plan-mode-schema.md` § Block 2W.

---

## Execution-log Template

run-harness does NOT author the plan - it CONSUMES the approved plan (`odoo-planning` is the
producer). This template is the run-local EXECUTION LOG run-harness writes to
`<ISOLATE_DIR>/wave/<slug>/plan.md` (gitignored; resolve `<SHARE_DIR>`/`<ISOLATE_DIR>` once per
`${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`; substitute the captured absolute path -
never write the placeholder or a bare `.odoo-ai/` into a Read/Write/Edit): the consumed topology +
module map, the cherry-pick / saga-checkpoint log, the review log, and the PR/squash result. It
records what run-harness did, not what to do.

```markdown
# Wave Integration Log: <slug>

Generated: <ISO datetime>
Principal branch: <name>
Run-integration branch: run-integration-<slug>

## Repo Capability Card

  base          : <principal>
  verify        : <command>
  commit        : <convention>
  confidential  : <level>
  worktree_root : <path>

## Topology

<independent | linear | mixed | diamond | single>

<Paste the relevant ASCII diagram from above, filled in with module names>

## Modules

| Module | Branch | Worktree path | Files in scope | Status |
|---|---|---|---|---|
| mod-A | wave/mod-<slug>-a | <path> | <file list> | pending |
| mod-B | wave/mod-<slug>-b | <path> | <file list> | pending |
| ... | | | | |

## Ownership Map

```
mod-A owns: [file1, file2, ...]
mod-B owns: [file3, file4, ...]
mod-C owns: [file5, ...]
```
(Sets must be disjoint. File appearing in two modules = blocker. The intra-module work-item split is
odoo-coder's private concern, not logged here.)

## Cherry-pick Log

| Module | Commit SHA | Verify result | Notes |
|---|---|---|---|
| mod-A | pending | - | |
| mod-B | pending | - | |
| ... | | | |

## Review Log

| Phase | Reviewer | Findings | Fixed |
|---|---|---|---|
| Integrated cross-cutting review | Opus | <summary> | <yes/no + detail> |
| odoo-code-review | odoo-code-review skill | <findings> | <yes/no + detail> |

## PR (ONE per run - opened once after the final wave)

URL     : <to be filled by the terminal integrate land-tail>
Squash  : <backup ref> -> tree-identity <confirmed | FAILED>
Status  : <open | merged | closed>

## Cleanup

- [ ] per-module worktrees removed (all waves)
- [ ] per-module branches deleted (all waves)
- [ ] run-integration branch deleted (after merge)
- [ ] Backup tag deleted
- [ ] <ISOLATE_DIR>/wave/<slug>/ removed
```

---

## Cleanup Checklist

Post-merge cleanup is owned by `odoo-pr-monitoring` (it runs AFTER the `L2-merge-gate` merge);
run-harness's between-wave integration itself stops at "PR opened" (drive-to-done) and never merges
or cleans up the run-integration branch. This checklist is the one the post-merge owner runs; it
covers the ONE run-integration branch plus every per-module worktree/branch across all waves.

Invoke the **`git-toolkit:git-ops`** skill (via the Skill tool) in one request (op=wave-cleanup):

```
[ ] remove worktree <path>/mod-a        (and all other per-module worktrees, all waves)
[ ] remove worktree <path>/run-integration
[ ] delete branch wave/mod-<slug>-a     (and all other per-module branches, all waves)
[ ] delete branch run-integration-<slug>    (after merge confirmed on remote)
[ ] delete tag run-integration-backup-<slug>
[ ] worktree-prune                     (clean stale worktree refs)
```

Local (run inline): `rm -rf <ISOLATE_DIR>/wave/<slug>/` (gitignored; safe to delete)

Verify after cleanup (bounded reads inline):
`git worktree list` should show only the principal worktree.
Confirm wave branches are gone (git-ops reports deletion success).

---

## Squash Tree-Identity Recipe (git-ops delegation)

Runs ONCE, at the terminal `integrate` land-tail after the FINAL wave closes green - NOT per wave.
All mutation steps are delegated to git-toolkit via the **`git-ops`** skill
(see `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`).

**git-ops request - squash + first-push operation:**

```
op                 : squash-push
worktree           : <path>/run-integration
principal          : <principal-branch-name>
backup-ref         : run-integration-backup-<slug>
commit-msg         : <conventional commit message>
integration-branch : run-integration-<slug>
first-push         : yes - the run-integration branch was NEVER pushed before, so this is a fresh
                     FIRST push (initial upstream push), NOT a force-with-lease; no history is
                     rewritten on any remote branch, so no git-toolkit destructive-op confirm gate fires
```

git-ops executes the `squash-push` recipe (stale-base guard -> S1 backup -> reset-soft squash-to-one -> S6 tree-identity gate -> FIRST push, non-force), owned by git-toolkit per its git-safety-contract S1/S6. Because this is a first push of a never-pushed branch, the S2 force-with-lease step is not exercised and no `confirmed:` field is required (branch-push is drive-to-done, not L2).

After git-ops returns, confirm its reported tree-identity exit code is 0. This is run-harness's
terminal RUN-level land step - it STOPS at "PR opened" (drive-to-done) and does NOT merge; the merge
is owned by `odoo-pr-monitoring` at the L2-merge-gate.

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

## Per-module Invocation Brief Template

Concrete brief `module_invocation_brief(mod)` in the pseudocode below resolves to. Pass **inputs
only** - `odoo-coding`'s own body owns every procedure (design-doc resolution, model-tier choice,
test-first dispatch); this skill never restates `odoo-coding`'s internals here, only the fields it
needs to CONSUME the plan's already-computed slice for one module (SSOT for the full field-by-field
contract: `${CLAUDE_PLUGIN_ROOT}/skills/odoo-coding/SKILL.md` § Plan-provided fast-path).

```
## MODULE <name> -> odoo-coding (Plan-provided fast-path: CONSUME, do not re-derive)
WORKTREE_PATH    : <absolute path> - author + commit ALL work inside this worktree; do NOT touch the
                   principal checkout and do NOT cherry-pick/merge/push (run-harness integrates)
MODULE / FILES   : <name> / <files-in-scope for this module>
STACK            : <backend | frontend | fullstack - this module's stack split, from the plan (lets the
                   odoo-coding fast-path consume the stack instead of re-inferring; omit only when the
                   plan did not tag it, then odoo-coding infers from files). The intra-module work-item
                   split is odoo-coder's job, not a run-harness input.>
MODULE-DAG SLICE : <this module's node + in-wave depends_on (already cherry-picked) + downstream impact>
TOPOLOGY         : <independent | linear | mixed | diamond | single - this module's place>
DESIGN_DOC       : <child TDD for this module | none>
MASTER_DESIGN_DOC: <master TDD path | none>
SHARE_DIR        : <captured absolute path - resolved ONCE by run-harness against the run root>
ISOLATE_DIR      : <captured absolute path - resolved ONCE by run-harness against the run root>
design_index     : <absolute path under SHARE_DIR, e.g. <SHARE_DIR-literal>/designs/<slug>/index.yaml | none>
ODOO VERSION     : <one resolved version for the run>
REQUEST          : <precise description of what this module implements>
Repo Capability Card: base=<principal> verify=<command> commit=<convention> confidential=<level>
WORKLOG          : <runSlug> - read it, then append significant decisions
Return: the commit SHA(s) on the module's branch (REQUIRED - a DONE with no SHA is a failed contract;
        the odoo-coder coordinator obtains the SHA by committing its coders' files via
        git-toolkit:git-ops, NOT via a raw coder commit) so run-harness can cherry-pick them onto
        integration.
```

---

## Per-module Integration Loop (Pseudocode)

Pseudocode for the between-wave integration loop. Referenced from SKILL.md § Between-wave
integration. Key property: run-harness does NOT dispatch anonymous workers and owns no weighted
budget - it INVOKES the `odoo-coding` SKILL per MODULE (which owns its own coder count + Mode-B
budget), and the `odoo-coder` coordinator COMMITS its module via `git-toolkit:git-ops` and returns
the SHA, which run-harness cherry-picks. Because a Skill invocation loads in the single orchestrating
context, MODULES are processed SEQUENTIALLY in module-DAG order; the parallel fan-out (and the
intra-module work-item split) lives INSIDE each `odoo-coding` invocation.

```text
# Run start (ONCE): run_integration = fork(base). Then per wave N, per module: ensure worktree ->
# INVOKE odoo-coding -> cherry-pick onto run_integration (saga). Sequential.
# SSOT for the saga/rollback + checkpoint contract: skills/_shared/integration-loop.md (do not restate).
# SSOT for the coder fan-out + Mode-B OOM budget: odoo-coding + skills/_shared/concurrency-guard.md.
# SSOT for the single-run-integration lineage: plan-mode-schema.md § Block 2W.

# run_integration was forked from base ONCE at run start; it is NOT re-forked per wave.
pre_wave_sha = tip(run_integration)         # saga anchor (integration-loop.md step 1)
cherry_picked = {}                          # module -> True once ON run_integration + verified

for mod in topological_order(modules):      # module-DAG / wave order; dependents after deps
    if any(not cherry_picked.get(d) for d in mod.depends_on):
        record(mod, "upstream blocked"); apply_saga_rollback(); return  # terminate the WHOLE wave

    ensure_worktree(mod)                    # git-ops worktree-add per Block 2W lineage (forks
                                            # run_integration, which already holds prior waves' code)

    # INVOKE odoo-coding via the Skill tool from THIS orchestrating context (legal: spawner ban is
    # leaf-only). Pass inputs only so odoo-coding's Plan-provided fast-path consumes them. odoo-coding
    # owns count+model; it dispatches ONE odoo-coder for the module (which owns the module's INTERNAL
    # work-item split); its coders author files INSIDE mod.worktree (no raw git), the odoo-coder
    # coordinator COMMITS them via git-toolkit:git-ops and returns the commit SHA(s). NO cherry-pick
    # here (run-harness integrates).
    result = Skill("odoo-coding", module_invocation_brief(mod))   # synchronous, in-context
                                                                   # brief SSOT: § Per-module Invocation Brief Template above
    if result.status != "DONE" or not result.shas:
        # Cross-run coordination is owned by odoo-coding, NOT run-harness. odoo-coding classifies a
        # dependency-unresolved BLOCKED against the module-coordination ledger
        # (snippets/module-coordination-ledger.md) AND performs the bounded N-barrier WAIT for a
        # concurrent build INTERNALLY. By the time it returns BLOCKED, that wait is already exhausted
        # (clean case-6 BLOCKED) or the cause is terminal (cases 4-6). run-harness does NOT
        # re-implement a barrier wait and reads no ledger case here - it treats the BLOCKED like any other.
        record(mod, result); apply_saga_rollback(); return    # DONE with no SHA = failed contract

    # cherry-pick: orchestrator-side CRITICAL SECTION, one at a time, topology order.
    mod_failed = False
    for sha in result.shas:
        cherry_pick(sha, into=run_integration)  # invoke git-ops in the run-integration worktree
        if conflict: resolve_conflict(mod)  # Sonnet resolver + cherry-pick --continue - full brief: § Conflict Resolver below
        if not run_verify():                # Repo Capability Card verify after each pick
            mod_failed = True; break         # stop picking THIS module's commits (inner loop only)

    if mod_failed:                          # verify failed mid-module -> terminate the WHOLE wave:
        record(mod, "verify failed")         #   do NOT checkpoint and do NOT mark this module cherry-picked
        apply_saga_rollback(); return        #   clean-abort/resume; never build on a rolled-back branch

    checkpoint(mod, tip(run_integration), "PASS")  # integration-loop.md step 2 (ONLY on full module success)
    cherry_picked[mod] = True                 # unblock dependents ONLY after cherry-picked + verified

# close the wave: integrated cross-cutting review -> cumulative regression close-gate (GREEN) ->
# AUTO-ADVANCE to the next wave (NO per-wave PR). The next wave forks its worktrees from the SAME
# run_integration branch (now carrying this wave's code). After the FINAL wave: the terminal
# `integrate` land-tail squashes run_integration + fresh FIRST-push + opens ONE PR (drive-to-done).
#
# apply_saga_rollback(): clean-abort (reset-hard to pre_wave_sha) OR resume from last passing
# checkpoint; never leave a half-built run_integration branch. Full contract: integration-loop.md.
# `return` ends the wave loop entirely (matches integration-loop.md clean-abort): a failed/blocked module
# is never recorded PASS and the loop never continues onto a rolled-back run_integration branch.
```

---

## Conflict Resolver (Sonnet subagent)

When a cherry-pick reports a semantic conflict (`resolve_conflict(mod)` in the pseudocode above),
dispatch a brief Sonnet resolver subagent - never resolve the conflict inline in run-harness's own
context, and never push the resolution down to the module's `odoo-coder`/coder workers.

Worker brief (SSOT: `${CLAUDE_PLUGIN_ROOT}/snippets/worker-brief.md`): "Resolve the semantic
conflict by editing the conflicting files in the worktree. Ground any Odoo claim via OSM MCP tools
(never a spawn). Do NOT run any git mutation yourself - no stage, no commit, no cherry-pick
continue, no integration ops. Edit the files and return; the orchestrator continues the cherry-pick
via git-toolkit:git-ops. Only Read/Grep/Glob/Edit/Write/Bash."

**MANDATORY.** When the conflict touches Odoo code (a model/field/method/view/OWL component - not a
pure prose/config file), hand the resolver the **OSM-First Grounding Contract**
(`${CLAUDE_PLUGIN_ROOT}/snippets/osm-first-contract.md`) alongside the brief above: the resolver
must ground every Odoo structural claim it makes while editing via an OSM call, never from memory.

After the resolver returns (conflict markers removed), re-invoke `git-toolkit:git-ops` (a fresh
invocation) with `op=cherry-pick-continue`, listing the resolved files. Cherry-pick state persists on
disk across cold-spawns, so git-ops resumes exactly where it stopped.

---

## Review Escalation (close-the-wave cross-cutting review)

Full detail for SKILL.md § Between-wave integration step 3 ("Close the wave"). The end-of-wave
cross-cutting review runs in run-harness's OWN context (not a subagent by default) over the whole
integration worktree - distinct from `odoo-coding`'s per-module code -> review+test loop
(intra-module scope); both run (double-review). This review is NEVER a flat inline review
regardless of wave size - measure the wave and escalate when it is large:

Measure: `git diff <principal>...HEAD --shortstat` (changed lines) and module count N.

- **Large wave** (>~1500 changed lines OR N >= 8 modules): escalate to a **fable** review subagent
  dispatched from run-harness's own context. fable costs ~2x opus - ALWAYS needs explicit
  confirmation: state the tier, the cost, and a one-line why; wait for an explicit human `yes`. If
  declined or unavailable, fall back to **opus inline review** and note the downgrade.
- **Otherwise** (the common case): **opus inline review**, in run-harness's own context.

Invoke the **`git-toolkit:git-ops`** skill (via the Skill tool) to produce the full diff
(`scope=<principal>...HEAD`) and review for:

- Plan adherence, correctness, simplicity, self-containment, confidentiality.
- **Coverage lens** (when any module touches tests or adds behavior that should be tested): for
  each changed model/module, verify via `tests_covering(model='<model>', odoo_version='<version>')`
  that the module did not introduce untested behavior paths, and via
  `test_coverage_audit(module='<module>', odoo_version='<version>')` that the module coverage gap
  did not widen. Flag any behavior-change module with no corresponding test addition.
- **Blast-radius render-check (widen to dependents)** (when any module changes a
  field/method/view/OWL component/template that dependents bind): derive the widened scope per
  `${CLAUDE_PLUGIN_ROOT}/snippets/acceptance-scope.md` (reverse-closure -> risk rank -> affected
  screens). This stays a STATIC review lens here; it does not execute CRUD/role flows in this context.

Fix findings inline or via a targeted subagent (Tier-C fresh spawn is always correct), or re-invoke
`odoo-coding` for the affected module with the AUTONOMOUS FIX (review-driven) sentinel + that
module's worktree path. Re-run verify after any fix. Only once this review is clean does the
cumulative regression close-gate (SKILL.md step 3) run.

**Acceptance hand-off (opt-in, L2).** When the blast-radius render-check above reaches BEYOND the
wave's own modules (the wave changed a UI/behavior surface whose `render_check_set` binds
dependents), surface a recommended acceptance pass over the affected cluster instead of letting
dependent UI go unverified - the SAME condition and shape `odoo-code-review` uses for its acceptance
hand-off (`${CLAUDE_PLUGIN_ROOT}/skills/odoo-code-review/SKILL.md` § Emit the acceptance hand-off;
shared render_check_set SSOT: `${CLAUDE_PLUGIN_ROOT}/snippets/acceptance-scope.md`). Do NOT auto-run
acceptance and do NOT auto-merge/auto-block on it: materialize an `odoo-acceptance` node in the
RUN-DAG (a `next` entry run-harness's driver loop picks up) at `gate_tier: L2` (human), depending on
the run's PR so the cluster is verified before merge:

```
next:
  - skill: odoo-acceptance
    reason: wave changed a UI/behavior surface with dependents (render_check_set beyond the changed modules); run blast-radius acceptance over the affected cluster before merge
    inputs: {changed_set: [<modules|model.field|model.method>], scope_hint: "<ISOLATE_DIR>/qa/<slug>-scope.md", odoo_version: "<version>"}
    confidence: 0.7
    risk_level: L2
```

`scope_hint` is advisory - `odoo-acceptance` Phase 0 regenerates the verify-scope manifest from the
changed set.

---

## Examples

> These examples start from run-harness picking a coding wave node off the RUN-DAG (never from a user
> phrase - a user's parallel/multi-module request routes to `odoo-planning`, which plans the waves).

**Example 1 - Standard 3-module wave (a single-wave run):**
run-harness picks a wave node with 3 independent MODULES (each e.g. a computed field + its OWL widget
+ its unit tests) + their module-DAG + `independent` topology + the Block-2W lineage slice.
Action: verify disjoint module ownership (safety audit) + plan-staleness; the run-integration branch
was forked once at run start; fork 3 worktrees from it; INVOKE `odoo-coding` per module sequentially
(each odoo-coding dispatches one odoo-coder, which commits its module and returns the SHA); cherry-pick
each SHA onto run-integration, verifying + checkpointing after each; run the integrated cross-cutting
review + `odoo-code-review` inline + the cumulative close-gate. This being the FINAL (only) wave, the
terminal `integrate` land-tail then squashes run-integration + fresh FIRST-push + opens ONE PR
(tree-identity verified); STOP at "PR opened". No merge.

**Example 2 - Dependency edge consumed (linear):**
The wave's module-DAG has module-B `depends_on` module-A.
Action: cherry-pick A first; then lazily fork module-B's worktree from the updated run-integration;
INVOKE `odoo-coding` for B; cherry-pick B. run-harness never recomputes the edge - it consumes it from
the plan.

**Example 3 - Cross-wave dependency (Block 2W lineage):**
A wave-2 module depends on a wave-1 module.
Action: wave-1's cherry-picked code is already on the single run-integration branch, so wave-2's
module worktree - forked from run-integration - CONTAINS the dependency's source. It is NOT on the
verification instance's addons-path by default: the allocator emits the CATALOG addons list, which
points at the principal checkout. The per-module brief therefore carries `WORKTREE_PATH` and
`SELF_PROVISION: worktree-addons` so the coordinator provisions an instance rooted on its own
worktree (`${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md` § Worktree-addons carve-out).
With that in place there is NO per-wave PR between the waves and no case-4 BLOCKED.

**Example 4 - Ownership conflict (safety audit catches a bad plan):**
The plan maps models.py to two module scopes.
Action: the disjoint-module-ownership audit finds models.py in both scopes. STOP BLOCKED: report the
overlap and route back to `odoo-planning` to re-partition. No worktree is created.

**Example 5 - Squash mismatch abort (terminal land-tail):**
Terminal squash of the run-integration branch: `git diff --quiet run-integration-backup-<slug>` exits
1 (tree mismatch). Abort: "Squash tree-identity FAILED - the squashed commit does not match the
pre-squash tree. Restoring from run-integration-backup-<slug>. Do NOT push." Report the differing
files. (No branch was pushed yet, so there is nothing to force-push or revert on the remote.)

**Example 6 - Conflict resolver path:**
module-A and module-B unexpectedly both touch a shared file (missed by the plan; caught at cherry-pick):
cherry-pick of module-B fails with conflict. Dispatch a Sonnet resolver subagent (worker-brief.md) with
the conflict diff + both module briefs. Resolver edits the conflicting files (markers removed). run-harness
re-invokes git-ops (cherry-pick --continue). Re-run verify, checkpoint, continue.

**Example 7 - Mid-wave failure (saga rollback):**
A cherry-pick verify cannot be made green within the loop's bound. Apply the
`integration-loop.md` saga: clean-abort (reset-hard to the pre-wave SHA) or resume from the last
passing checkpoint; report the failing module. Never leave a half-built run-integration branch.
