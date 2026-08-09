# Wave Integration - Reference Templates

On-demand reference for `skills/run-harness/SKILL.md` § Between-wave integration. Load this file
when you need the full template text for any of the structures below. Do not load it on every
invocation.

> "wave" in this file is the integration-topology CONCEPT (wave-batch, wave-templates), not a
> user-invocable skill. run-harness is consume-only: it CONSUMES the plan's MODULE list +
> wave-batched module-DAG + topology + **Block 2W** worktree lineage and INVOKES `odoo-coding` per
> module; it never self-derives a plan and never chooses agent/model. The outer unit is the MODULE;
> the work-item is `odoo-coder`'s INTERNAL unit and never appears here. `odoo-coding` MAY group
> modules that must change together into one `odoo-coder` scope - that grouping is internal to
> `odoo-coding` and does not change the MODULE nodes run-harness reasons about. run-harness
> owns the between-wave integration directly (there is no separate git-executor skill).

---

## Repo Capability Card Template

Fill ONE card PER REPOSITORY the run touches, at the start of the coding waves, and embed the card
of a module's OWN repo verbatim in that module's `odoo-coding` brief. The cards are the run file's
`repos[]` list (harness §8.3): one entry per repo, `id` + the five fields below. A single-repo run is
a one-entry list - same card, no extra ceremony.

```
Repo Capability Card  (one per repo; serialized as a repos[] entry in run-<id>.json)
  id            : <DERIVED from the repo's `origin` URL - see "id resolution" below; the value
                   every node's `repo` field names>
  base          : <principal branch name>
  verify        : <command that must pass after every cherry-pick, e.g. "make test" or "make gen-check && make deps-check && make test">
  commit        : <resolved by git-toolkit:git-ops at commit time - do not pre-declare a standard>
  confidential  : <public | restricted | internal>
  worktree_root : <parent path for wave worktrees, outside the repo tree>
```

Notes:
- `id` is what ties nodes to a repo: a node's `repo` names one `id`. Each `id` gets its OWN
  run-integration branch+worktree, its own `integrate` node, and its own PR - N repos = N PRs.
  When a node may carry `repo: null` instead: `${CLAUDE_PLUGIN_ROOT}/docs/reference/workflow-harness.md`
  §8.3 § `repo: null` legality (that rule's ONE owner).

- **`id` resolution (deterministic - the SAME repository must always resolve to the SAME id).**
  Resolve it from the repository's `origin` remote URL, read through the `git-toolkit:git-ops`
  skill (a bounded read) - never from the directory name, the worktree path, the checked-out
  branch, or the Odoo series. Normalize that URL to `<host>/<owner>/<name>`: drop the scheme and
  any credentials, drop a trailing `.git` and any trailing slash, lowercase the whole triple. The
  id is `<name>`. Two entries whose normalized triples DIFFER but whose `<name>` is the same
  (two different repos that happen to share a name) both extend to `<owner>-<name>` - still
  origin-derived, still deterministic. A repository whose `origin` cannot be resolved gets NO
  invented id: report `NEEDS_CONTEXT` naming the checkout, and let a human supply the remote.
  Because the id is a property of the REMOTE, every checkout, worktree, branch, and series of one
  repository lands on one id by construction - which is what makes "one PR per repo" checkable.

- **Two entries that resolve to the SAME id ARE one repository.** Collapse them into ONE card
  before the run forks anything: one `repos[]` entry, one run-integration branch+worktree, one
  `integrate` node, one PR. If the colliding entries disagree on any card field (`base`, `verify`,
  `commit`, `confidential`, `worktree_root`), do NOT guess a winner - STOP BLOCKED, name the two
  entries and the field they disagree on, and route back to intake Phase P to re-serialize. Both
  the serializer (Phase P) and the driver (run-harness at Run start) apply this same rule, so a
  hand-edited or stale `repos[]` cannot smuggle a second PR into the run.
- `base` is resolved per `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md` § Base-branch
  resolution - never inherited from the invoking checkout's HEAD/current branch.
- Discover `verify` from Makefile targets, CI config, or README. If multiple commands
  are required, chain them with `&&`.
- `confidential: restricted` triggers the 8-group ban check on every artifact.
- `worktree_root` should be outside the repo tree to avoid accidental staging of wave files by git.

---

## Topology values (five)

Choose from the plan's Block-2 module-DAG (independent / linear / mixed / diamond / single). run-harness does
NOT re-derive the topology - `odoo-planning` produces it; this is the reference for reading it. The
nodes are MODULES (the outer unit); the work-item split is `odoo-coder`'s PRIVATE
concern and never a topology node here.

### Independent (most common)

All modules touch disjoint files with no ordering dependency: cherry-pick in ANY order - the build
ORDER is unconstrained.

**Does mean:** dispatch order is free - the loop below may pick mod-A, mod-B, mod-C in any sequence
without violating a dependency.
**Does NOT mean:** concurrent execution. The between-wave loop dispatches modules ONE AT A TIME via
a synchronous `Skill("odoo-coding", ...)` call per module (§ Per-module Integration Loop
(Pseudocode) below) - a Skill invocation runs IN the caller's own context
(`${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md` § Nesting), so run-harness never has two
`odoo-coding` invocations in flight at once, `independent` topology or not. The only real
concurrency inside a wave is the intra-module work-item fan-out INSIDE each `odoo-coder`
coordinator - a PRIVATE concern of that one module's own build, invisible at this layer.

```
base ────────────────────────────────────────────► (unchanged)
             │
             └─► run-integration ─── cherry-pick A ─── cherry-pick B ─── cherry-pick C ──► close wave
                     │
                 mod-A ──► commit-A
                 mod-B ──► commit-B    (order unconstrained - dispatched ONE AT A TIME, sequentially)
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
already-provisioned JOB-tier integration worktree - created ONCE, by an explicit step, at
`run-harness/SKILL.md` § Between-wave integration's "Run start" (never inferred here).

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

## Repo Capability Cards (one block per repo in repos[])

  id            : <repo>
  base          : <principal>
  verify        : <command>
  commit        : <resolved by git-toolkit:git-ops at commit time>
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

## PR (ONE per REPO - each opened once after the final wave; one row per repos[] entry)

Repo    : <repos[].id>
URL     : <to be filled by that repo's terminal integrate land-tail>
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

Post-merge cleanup is owned by `odoo-pr-monitoring` (it runs AFTER the merge approval gate's merge);
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

---

## Stale wave-dir sweep (24h crash-backstop, fail-closed)

The Cleanup Checklist above deletes `wave/<slug>/` on the NORMAL path (post-merge). This section
is the BACKSTOP for the abnormal path - a run that crashed, was killed, or was abandoned before
ever reaching that checklist leaks its `wave/<slug>/` dir forever unless a later run reaps it
(`snippets/visual-evidence-lifecycle-contract.md` § 3.1 `wave/<slug>/` row + § 3.6).

**Why a bare mtime sweep is UNSAFE here (do not use Clause 2's generic one-liner).** `run-harness`
can pause at an L2 human-confirm gate for an UNBOUNDED period mid-run (`SKILL.md` Hard rule 2 /
§ Gate-tier resolution: emit gate, end turn, resume after a human `continue`) - during that pause
nothing touches `wave/<slug>/plan.md`, so its mtime goes stale while the run is PAUSED, not
abandoned. A directory's age alone can never distinguish "abandoned" from "waiting on a human" -
the criterion MUST also positively correlate against the run's OWN status before deleting anything.

**The criterion: age is necessary but never sufficient - the correlating run's OWN top-level
`status` must independently prove TERMINAL.** `wave/<slug>/` and `run-<slug>.json` share ONE id
(`state-root-resolution.md`: "per active run"), so the correlating file is trivially locatable.
Read its status with `jq`, never `grep` - `run-<id>.json`'s schema
(`docs/reference/workflow-harness.md` §8.3) nests a SECOND, differently-scoped `"status"` key
inside EVERY entry of its own `nodes[]` array (`"PENDING"`/`"READY"`/`"RUNNING"`/`"DONE"`/... - a
per-NODE progress flag, not the run's own state); an unanchored `grep -q '"status".*"DONE"'`
against the raw file would match the routine, EARLY, common case of the run's FIRST node reaching
`"DONE"` while the run itself is still very much alive and `NEEDS_NEXT` - reaping a live run's
directory out from under it, the exact "GC worse than the leak" failure this contract exists to
prevent. `jq -r '.status // empty'` reads ONLY the JSON root's `status` field, never a nested one:

```bash
if command -v jq >/dev/null 2>&1; then
  find <ISOLATE_DIR>/wave/ -mindepth 1 -maxdepth 1 -type d -mmin +1440 -print0 |
  while IFS= read -r -d '' d; do
    slug="$(basename "$d")"
    run_file="<ISOLATE_DIR>/run-${slug}.json"
    status="$(jq -r '.status // empty' "$run_file" 2>/dev/null || true)"
    case "$status" in
      DONE|BLOCKED|NEEDS_CONTEXT)
        rm -rf "$d"   # the correlating run's OWN top-level status positively proved terminal
        ;;
      *)
        : # absent run_file, unreadable/malformed JSON, empty, or NEEDS_NEXT (still mid-flight,
          # possibly paused at an L2 gate right now) - skip, unconditionally, never delete
        ;;
    esac
  done
fi
# jq unavailable -> skip the ENTIRE sweep this run rather than fall back to a raw-text match -
# an unprovable status is the SAME "do not delete" outcome § 3.6 already mandates for an absent
# or unreadable run file, extended to "the tool needed to read it correctly is itself absent".
```

Fail-closed on every axis, all collapsing to "skip, never delete": no correlating `run-<id>.json`
at all, the file exists but is not valid JSON, `.status` is absent/empty, `.status` is
`NEEDS_NEXT` (mid-flight, possibly mid-pause), or `jq` itself is unavailable. Only a POSITIVELY
confirmed terminal top-level status (`DONE`/`BLOCKED`/`NEEDS_CONTEXT`) on the run whose id matches
the candidate directory's own name authorizes deletion - mirroring `reap-orphans`'
age-unknown-means-not-reaped convention (`scripts/lib/allocator.py` `_reap_candidates`) and the
resolve-or-refuse discipline this contract already applies to `run-<id>.json` itself (§ 3.3).

**Enforcer and placement.** Run this ONCE, unconditionally, as the FIRST action inside `SKILL.md`
§ Between-wave integration's "Run start" step - before this run creates or writes anything under
`wave/<own-slug>/` for the first time (the same "before minting/creating your own state" placement
every other § 3.1 sweep site uses; a live run's own directory does not exist yet at this point, so
it can never be the accidental target). `find`'s `-mmin +1440` guarantees the same protection a
second, independent way: a directory a live run is actively writing into never ages 24h untouched
while that writing continues. Whoever executes `run-harness` next, every run - not a separate
cleanup agent or cron.

Verify after cleanup (bounded reads inline):
`git worktree list` should show only the principal worktree.
Confirm wave branches are gone (git-ops reports deletion success).

---

## Squash Tree-Identity Recipe (git-ops delegation)

Runs ONCE, at the terminal `integrate` land-tail after the FINAL wave closes green - NOT per wave.
All mutation steps are delegated to git-toolkit via the **`git-ops`** skill
(see `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`).

**Existence precheck (ALWAYS FIRST - before any push, before any PR-open).** This tail must be safe
to run twice: a resumed, retried, or re-entered run arrives here with work possibly already on the
remote (`SKILL.md` § Resume). Through `git-ops`, read TWO facts about this repo and record both in
the node's `produced` so the next reader sees what was OBSERVED, not what was assumed:

1. Is `run-integration-<slug>` present on the fork?
2. Is there an OPEN PR whose head is that branch, against this repo's `base`?

Resolve the request from the answers - never from memory of what this run did earlier:

| branch on fork | open PR | what the land tail does |
|---|---|---|
| no | no | the normal path: squash, `first-push: yes`, then open the ONE PR. |
| yes | no | do NOT re-squash what is already pushed. Push only the commits the remote lacks (`first-push: no`), then open the ONE PR. |
| yes | yes | **that PR IS this repo's ONE PR - UPDATE it, never open a second.** Push the missing commits to the SAME branch (an open PR updates itself from its head branch), then carry that PR's URL forward in `produced` as the node's result. |

`first-push` is DERIVED from fact 1 on every invocation. If landing the current tree would REWRITE
history already on the fork (a re-squash after a push), that is a history rewrite: hand it to
`git-ops` as such and let git-toolkit's destructive-op human-confirm gate fire - never bypass it,
and never delete and re-open the PR to dodge it.

**git-ops request - squash + push operation:**

```
op                 : squash-push
worktree           : <path>/run-integration
principal          : <principal-branch-name>
backup-ref         : run-integration-backup-<slug>
commit-msg         : <none - business outcome only (the run's modules + what changed); let
                     git-toolkit:git-ops compose the message from its own detected convention -
                     do not pre-declare a standard or pass a literal message>
integration-branch : run-integration-<slug>
first-push         : <DERIVED from the Existence precheck above, never asserted: `yes` when the
                     branch is absent from the fork (an initial upstream push - no history is
                     rewritten anywhere, so no git-toolkit destructive-op confirm gate fires);
                     `no` when the branch is already there and this push only adds the commits the
                     remote lacks>
```

git-ops executes the `squash-push` recipe (stale-base guard -> S1 backup -> reset-soft squash-to-one -> S6 tree-identity gate -> push), owned by git-toolkit per its git-safety-contract S1/S6. On `first-push: yes` the S2 force-with-lease step is not exercised and no `confirmed:` field is required (branch-push is drive-to-done, not L2). On `first-push: no` the push is still non-force as long as it only ADDS commits; only a rewrite of already-pushed history reaches S2, and that one is human-confirmed by git-toolkit.

After git-ops returns, confirm its reported tree-identity exit code is 0. This is run-harness's
terminal RUN-level land step - it STOPS at "PR opened" (drive-to-done) and does NOT merge; the merge
is owned by `odoo-pr-monitoring` at the merge approval gate.

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
SURVEY           : <deep-survey synthesis.md path | none - forwarded from the wave node's
                   inputs.survey (phase-p-run-dag.md § Survey pointer); ALWAYS an explicit
                   value, never omitted - none means no deep survey ran this session>
SHARE_DIR        : <captured absolute path - resolved ONCE by run-harness against the run root>
ISOLATE_DIR      : <captured absolute path - resolved ONCE by run-harness against the run root>
design_index     : <absolute path under SHARE_DIR, e.g. <SHARE_DIR-literal>/designs/<slug>/index.yaml | none>
ODOO VERSION     : <one resolved version for the run>
REQUEST          : <precise description of what this module implements>
Repo Capability Card: id=<this module's repo> base=<principal> verify=<command> commit=<resolved by git-ops> confidential=<level>
                   (the repos[] entry whose id equals this wave node's `repo` - never another repo's card)
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
budget), and the `odoo-coder` coordinator COMMITS its scope via `git-toolkit:git-ops` and returns
the SHA plus the modules that SHA covers, which run-harness cherry-picks. When a returned SHA covers
SEVERAL modules (`odoo-coding` grouped them because the change is atomic across them), cherry-pick
that SHA ONCE and treat every module it covers as integrated - never dispatch `odoo-coding` a
SECOND time for a module an integrated SHA already covers, and never split such a commit per module. Because a Skill invocation loads in the single orchestrating
context, MODULES are processed SEQUENTIALLY in module-DAG order; the parallel fan-out (and the
intra-module work-item split) lives INSIDE each `odoo-coding` invocation.

```text
# Run start (ONCE): create the JOB-tier run_integration worktree via git-toolkit:git-ops
# (worktree add, branch forked from base). Then per wave N, per module: ensure worktree ->
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
# `integrate` land-tail runs its existence precheck, squashes run_integration, pushes, and opens
# ONE PR - or updates this repo's already-open PR (drive-to-done).
#
# apply_saga_rollback(): clean-abort (worktree abandon + re-fork at pre_wave_sha) OR resume from
# last passing checkpoint; never a reset --hard against a live worktree (fires no destructive
# gate, by construction); never leave a half-built run_integration branch. Full contract:
# integration-loop.md.
# `return` ends the wave loop entirely (matches integration-loop.md clean-abort): a failed/blocked module
# is never recorded PASS and the loop never continues onto a rolled-back run_integration branch.
```

---

## Conflict Resolver (Sonnet subagent)

When a cherry-pick reports a semantic conflict (`resolve_conflict(mod)` in the pseudocode above),
dispatch a brief Sonnet resolver subagent - never resolve the conflict inline in run-harness's own
context, and never push the resolution down to the module's `odoo-coder`/coder workers.

Worker brief (SSOT: `${CLAUDE_PLUGIN_ROOT}/snippets/worker-brief.md`): "Resolve the semantic
conflict by editing the conflicting files in the `run-integration` worktree at
`<path>/run-integration` (the cherry-pick target - NEVER the module's own per-wave worktree). Ground
any Odoo claim via OSM MCP tools (never a spawn). Do NOT run any git mutation yourself - no stage, no
commit, no cherry-pick continue, no integration ops. Edit the files and return; the orchestrator
continues the cherry-pick via git-toolkit:git-ops. Only Read/Grep/Glob/Edit/Write/Bash."

**MANDATORY.** When the conflict touches Odoo code (a model/field/method/view/OWL component - not a
pure prose/config file), hand the resolver the **OSM-First Grounding Contract**
(`${CLAUDE_PLUGIN_ROOT}/snippets/osm-first-contract.md`) alongside the brief above: the resolver
must ground every Odoo structural claim it makes while editing via an OSM call, never from memory.

After the resolver returns (conflict markers removed), re-invoke `git-toolkit:git-ops` against the
SAME `run-integration` worktree (`<path>/run-integration`) named above (a fresh invocation) with
`op=cherry-pick-continue`, listing the resolved files. Cherry-pick state persists on disk across
cold-spawns, so git-ops resumes exactly where it stopped.

---

## Review Escalation (close-the-wave cross-cutting review)

Full detail for SKILL.md § Between-wave integration step 3 ("Close the wave"). The end-of-wave
cross-cutting review runs in run-harness's OWN context (not a subagent by default) over the whole
integration worktree - distinct from `odoo-coding`'s per-module code -> review+test loop
(intra-module scope); both run (double-review). This review is NEVER a flat inline review
regardless of wave size - measure the wave and escalate when it is large:

Measure: `git diff <principal>...HEAD --shortstat` (changed lines) and module count N.

- **Large wave** (>~1500 changed lines OR N >= 8 modules): escalate to a **fable** review subagent
  dispatched from run-harness's own context. ALWAYS confirm with the human first, and ask as a
  TRADEOFF, never by tier name - how big the wave is, that the review runs on the deepest-reasoning
  setting, and that it costs about 2x - with the reply set `approve / skip / cancel`. On `skip` or
  when the setting is unavailable, fall back to **opus inline review** and note the downgrade.
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

Fix findings inline or via a targeted subagent (Tier-C fresh spawn is always correct) - both paths
edit directly in `run-integration` (`<path>/run-integration`, the SAME tree this review is already
scoped to - no cherry-pick needed), or re-invoke `odoo-coding` with `WORKTREE_PATH` set to the
affected module's OWN worktree from this wave (`mod.worktree`, the SAME worktree § Per-module
Integration Loop above authored the module's original code in) plus the AUTONOMOUS FIX
(review-driven) sentinel. This third path uses a SEPARATE tree from `run-integration`, so it is not
done until the returned SHA is cherry-picked back onto `run-integration` - the SAME
`cherry_pick(sha, into=run_integration)` step § Per-module Integration Loop performs for every
module, via the `git-toolkit:git-ops` skill, never a raw git command inline. **Re-run verify against
`run-integration`'s current tip specifically** (never the module's own worktree, and never a
worker's bare DONE self-report) after ANY of the fix paths above. Only once that re-verification is
clean does the cumulative regression close-gate (SKILL.md step 3) run.

## Pre-PR tail (mandatory sequence, after the final wave closes green)

### Terminal stage order (THE constant - this section is its ONE owner)

Cite this constant by name. Do NOT restate the order in another file, and do NOT reorder it
locally. Every orchestrator with a terminal tail (`odoo-forward-port`, `odoo-git-rebase`,
`odoo-modules-upgrade`) and every `writes-files` plan
(`${CLAUDE_PLUGIN_ROOT}/skills/odoo-intake/references/plan-mode-schema.md` Block 2) resolves its
terminal stage order HERE.

```text
  final coding wave closes GREEN
    +--> (1)  i18n        [skill: odoo-i18n]             reconcile translations
    +--> (2)  acceptance  [skill: odoo-acceptance]       live blast-radius oracle
    +--> (2b) doc         [skill: odoo-doc-illustration] user guide + App-Store landing
    +--> (3)  lint        pre-PR lint-class gate over the aggregate diff
    +--> (4)  PR          ONE PR per REPO, opened ONCE - the run's only land step
    |
    +-------> monitor     [skill: odoo-pr-monitoring]    CI triage, review polling  [post-PR]
    +-------> merge       [skill: odoo-pr-monitoring]    the single outward L2 gate [post-PR]
```

Each edge is a dependency, not a style preference:

- **i18n before acceptance.** i18n MUTATES what the live UI renders (translated labels/messages,
  per `${CLAUDE_PLUGIN_ROOT}/snippets/i18n-mandate-contract.md` "The mandate"), and acceptance's
  evidence (screenshots, asserted UI text) must reflect that FINAL, translated state - acceptance
  first would capture pre-i18n evidence that i18n then invalidates.
- **doc after acceptance.** The doc stage CAPTURES the live UI (screenshots for `doc/index.rst`
  and `static/description/index.html`), so it consumes exactly what acceptance may still change: an
  acceptance FAIL routes a code fix, and every screenshot taken before that fix is stale. Placing
  doc after acceptance also puts it after i18n, so captures show the translated strings.
- **doc before lint.** The doc stage WRITES committed files and wires `__manifest__.py` (images,
  store keys). The single full-diff lint-class pass at (3) must see those edits, or the run's ONE
  PR ships manifest changes no gate ever read.
- **Anything that can force a CODE CHANGE runs at or before (3).** A review, oracle, capture, or
  gate whose findings are fixed by editing source belongs BEFORE the PR opens. Running it after
  makes the PR churn and makes regression testing chase a moving target - the exact failure this
  order exists to prevent.
- **Only work that must OBSERVE the opened PR runs after (4).** CI-failure triage and fix,
  static-review-bot comment cross-check, review/approval polling, the MERGE itself, and post-merge
  cleanup - all owned by `${CLAUDE_PLUGIN_ROOT}/skills/odoo-pr-monitoring/SKILL.md`. A bot comment
  cannot predate the PR it is posted on; a worktree diff review can, and therefore must.
- **ONE PR per REPO, never per wave.** The PR stage opens exactly one PR for each repo the run
  touched, after every non-land-tail node in that repo is DONE or SKIPPED (readiness rule:
  `${CLAUDE_PLUGIN_ROOT}/skills/run-harness/SKILL.md` § Gate-tier resolution, `integrate` readiness
  precondition - re-derived by the driver, not trusted from `depends_on`).
- **A pipeline that has no stage at some position SKIPS that position - it never reorders the
  rest.** A run with no user-guide/App-Store goal has no doc node (`odoo-planning` P1b fast-path
  `doc: none`); a forward-port has no doc stage at all. Both still run (1) -> (2) -> (3) -> (4).

The stage blocks below are the execution detail for (1), (2), (2b), (3), (4) in that order.

**1 - i18n reconcile (MANDATORY, narrow-escape only, ONCE for the whole run).** Dispatch the
`odoo-i18n` skill exactly ONCE, over the run-integration branch's aggregate diff (every module,
every wave) - never per module. Mandate wording, the four caller obligations, and the enumerated
escape hatches (E1-E6) are owned by `${CLAUDE_PLUGIN_ROOT}/snippets/i18n-mandate-contract.md` - not
restated here; run-harness is a THIRD caller of that contract alongside `odoo-modules-upgrade` and
`odoo-forward-port`. `gate_tier: L2` per the registry (`generator/skill_tool_deps.json`
`orchestration.odoo-i18n` - `instance_touching: true`); this is a DECLARED human gate (the
ENUMERATED stop conditions in `SKILL.md` Hard rule 2), not an incidental pause. `odoo-coding`'s own
per-module Continuation Contract does NOT also suggest `odoo-i18n` - that would fire once per module
per wave for the same run-level obligation; see `${CLAUDE_PLUGIN_ROOT}/skills/odoo-coding/SKILL.md`
§ Continuation Contract.

**2 - Acceptance (conditional, L2, ONCE for the whole run - fires BEFORE the PR, not after it).**
When ANY wave's blast-radius render-check (§ Review Escalation above) reached BEYOND that wave's own
modules (the `render_check_set` binds dependents), materialize an `odoo-acceptance` node - the SAME
condition and shape `odoo-code-review` uses for its own acceptance hand-off
(`${CLAUDE_PLUGIN_ROOT}/skills/odoo-code-review/SKILL.md` § Emit the acceptance hand-off; shared
render_check_set SSOT: `${CLAUDE_PLUGIN_ROOT}/snippets/acceptance-scope.md`) - but depending on
stage 1 above (i18n) and the FINAL wave's close-gate, NEVER on the run's PR. Do NOT auto-run
acceptance and do NOT auto-merge/auto-block on it; do NOT dispatch it once per triggering wave -
coalesce every wave's trigger into ONE cluster-wide `odoo-acceptance` invocation covering the UNION
of every wave's widened `render_check_set`, mirroring `odoo-modules-upgrade`'s "ONCE for the whole
cluster, never per module":

```
next:
  - skill: odoo-acceptance
    reason: one or more waves changed a UI/behavior surface with dependents (render_check_set beyond the changed modules); run blast-radius acceptance over the affected cluster BEFORE the PR opens
    inputs: {changed_set: [<modules|model.field|model.method>], scope_hint: "<ISOLATE_DIR>/qa/<slug>-scope.md", odoo_version: "<version>", worktree_path: "<path>/run-integration"}
    confidence: 0.7
```

`scope_hint` is advisory - `odoo-acceptance` Phase 0 regenerates the verify-scope manifest from the
changed set. `worktree_path` is NOT advisory: `odoo-acceptance`'s own Inputs section
(`${CLAUDE_PLUGIN_ROOT}/skills/odoo-acceptance/SKILL.md` § Inputs) resolves its live instance from
either a caller-supplied `INSTANCE_HANDLE` or the catalog-default
`${CLAUDE_PLUGIN_ROOT}/snippets/instance-resolution.md` - neither path is worktree-aware, so without
this field its Phase 2 provisioning would silently target the principal checkout instead of
`run-integration`, the SAME false-green shape the stage 3 Worktree-targeting paragraph below closes.
Whoever executes this continuation MUST thread `worktree_path` into `odoo-acceptance`'s Phase 2
`odoo-instance` dispatch as `WORKTREE_PATH` (optionally `SELF_PROVISION: worktree-addons` when
dispatching a bounded subagent for that phase) - the SAME shape stage 3 below and Example 3 below
already use (`${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md` § Worktree-addons
carve-out). When no wave ever widened its `render_check_set`, this stage does not fire and the tail
proceeds straight to stage 2b.

**2b - Doc (conditional, L1, ONCE for the whole run - after acceptance, before the lint gate).**
Fires when the approved plan carries a doc node (user guide `doc/index.rst` and/or App-Store landing
`static/description/index.html`); an internal-only run has none (`odoo-planning` P1b fast-path
`doc: none`) and the tail proceeds straight to stage 3. Position is fixed by the Terminal stage
order constant above: doc CAPTURES the live UI, so it must see the accepted (stage 2) and translated
(stage 1) state, and it WRITES committed files plus `__manifest__.py` image/store-key wiring, so it
must land before the single full-diff lint pass at stage 3 reads them.

Dispatch the `odoo-doc-illustration` skill ONCE for the whole run, over the run-integration branch's
aggregate module set (every module, every wave) - never per module and never per wave.
`gate_tier: L1` per the registry (`generator/skill_tool_deps.json` `orchestration.odoo-doc-illustration`).
State `WORKTREE_PATH: <path>/run-integration` on the dispatch, and `SELF_PROVISION: worktree-addons`
when a bounded subagent carries it - the SAME two fields stages 2 and 3 and § Per-module Invocation
Brief Template already use, for the SAME reason
(`${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md` § Worktree-addons carve-out): without
them the capture instance loads the CATALOG addons path and every screenshot documents the principal
checkout instead of the tree the PR ships.

**The doc output must reach `run-integration` before stage 3 (mandatory - docs do not ship
otherwise).** `run-integration` is the ONLY branch the terminal land-tail squashes and pushes.
Commit the authored doc files via the `git-toolkit:git-ops` skill; when they were authored in a
worktree other than `<path>/run-integration`, bring the returned SHA onto `run-integration` with the
SAME `cherry_pick(sha, into=run_integration)` step § Per-module Integration Loop performs for every
module SHA, via `git-toolkit:git-ops` - never a raw git command inline. A semantic conflict follows
the SAME § Conflict Resolver path as any other cherry-pick.

**3 - Pre-PR lint-class gate (L0/L1 - ephemeral instance, not a SHARED-instance L2 case).** Run the
FULL CI-parity lint-class suite ONCE, over the run-integration branch's aggregate diff (every
module, every wave): `/test_lint` (+ `/test_pylint` on v16+ Viindoo profiles) and the Tier-1 eslint
leg of `verify-frontend.sh`. Invocation mechanics (commands, flags, PASS/CANNOT-VERIFY semantics)
are owned by `${CLAUDE_PLUGIN_ROOT}/docs/reference/odoo-code-quality.md` +
`${CLAUDE_PLUGIN_ROOT}/docs/reference/ODOO-TESTING.md` - not restated here. This REPLACES every
per-work-item / per-module lint-class self-check and re-verification - see
`${CLAUDE_PLUGIN_ROOT}/skills/odoo-coding/SKILL.md` and its per-module hard-leaf workers for what
stays per-module instead (OSM-grounded ORM validation, inline review, zero-toolchain static OWL/SCSS
checks - none of these are lint-class and none run here).

**Worktree targeting is explicit, never inferred from cwd (mandatory).** This gate's ephemeral
instance MUST load `run-integration`'s tree, not the principal checkout - the SAME requirement
Example 3 below states for a cross-wave verification instance ("the allocator emits the CATALOG
addons list, which points at the principal checkout"). State `WORKTREE_PATH: <path>/run-integration`
on the provisioning dispatch: when this gate runs INLINE in run-harness's own context, pass
`WORKTREE_PATH: <path>/run-integration` directly on the `odoo-instance` skill dispatch (the field
`${CLAUDE_PLUGIN_ROOT}/skills/odoo-instance/SKILL.md` § Dispatch already defines); when run-harness
instead dispatches a bounded subagent for this gate, carry `WORKTREE_PATH: <path>/run-integration`
PLUS `SELF_PROVISION: worktree-addons` in that subagent's brief - the SAME two fields § Per-module
Invocation Brief Template above and Example 3 below already use for a worktree-rooted instance
(`${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md` § Worktree-addons carve-out). This is
not cosmetic: `WORKTREE_PATH` is what makes the `acquire` call carry `--addons-path-override`, and
`--addons-path-override` is the ONE thing that satisfies the allocator's
`_addons_path_worktree_mismatch` guard (`scripts/lib/allocator.py`) - the guard engages ONLY when NO
override is passed. Omitting `WORKTREE_PATH` here means one of two failures depending on the
dispatching agent's cwd (never a safe default either way): the instance silently loads the CATALOG
addons path and the gate reports clean regardless of what `run-integration` actually contains, or the
guard refuses the `acquire` outright (rc 5) and the now-sole lint gate hard-blocks every run.

**Gate role is explicit too, never inferred from "this is the last stage" (mandatory).** This
`run-tests` dispatch ALSO carries `GATE_ROLE: pre-pr-lint-gate` - the ONE explicit signal
`agents/odoo-instance-ops.md` § Lint modules HARD RULE reads to decide whether to probe for, install,
and tag `test_lint`/`test_pylint` at all. Every OTHER `run-tests` dispatch anywhere in this plugin -
in particular the per-module integrated-module test `odoo-coder` runs every module, every wave
(`${CLAUDE_PLUGIN_ROOT}/agents/odoo-coder.md` § Own the integrated module verification) - states
`GATE_ROLE: per-module-verify` instead, so the SAME operation name (`run-tests`) never collapses the
two into one gate again: the per-wave integrated test surfaces ONLY its own module's behavior
failures, never a lint-class failure, and lint-class failures surface ONLY here. Omitting `GATE_ROLE`
on this dispatch is not a safe default - the agent refuses with `NEEDS_CONTEXT` rather than silently
guess, exactly like an omitted `WORKTREE_PATH` above must never be inferred from cwd.

**A `tests-inconclusive` verdict from THIS dispatch is treated as a non-pass too, not only
`tests-failed` (mandatory).** `agents/odoo-instance-ops.md` § Verdict contract resolves this
`GATE_ROLE: pre-pr-lint-gate` dispatch to `tests-inconclusive` in two cases: the pre-existing
skip-only case, and the "Checker-load coverage confirmation" case (a custom checker - e.g. an
SQL-injection rule - that failed to load, or a log with no checker-coverage statement to confirm
at all). Neither case is a `tests-passed` in disguise, and this is the ONE dispatch in the whole
run authorized to trigger the lint-class union at all - there is no LATER gate to catch a miss
here. An unattended `--auto` drive-to-done run has nothing else guaranteed to perform the "human
reviewing `findings_path`" step that dispatch's own contract text demands for `tests-inconclusive`
in general, so for this ONE gate specifically, `tests-inconclusive` enters the SAME containment
loop below as `tests-failed` - never a silent pass-through to the terminal PR.

**Containment for tail-only lint (mandatory prose, not optional).** Moving lint to the tail trades
"catch it while the wave's context is warm" for "catch it once, cheaply, over the full diff" - this
trade is intentional (the owner's instruction), but it must not become a worse failure than what it
replaces:
- **On a FAILURE OR a `tests-inconclusive` verdict (skip-only or coverage-shortfall/unconfirmed -
  see the paragraph above), do not flat-BLOCK the run.** For a FAILURE, the lint tool's own output
  names the exact file/line; for a coverage gap, `findings_path`/`notes` names which lint-class
  module's checker coverage could not be confirmed and why (per the coverage rule cited above) -
  either way, that is the evidence to hand off. Re-invoke `odoo-coding` with `WORKTREE_PATH` set to
  the failing module's OWN worktree
  from its wave (the SAME `mod.worktree` the § Per-module Integration Loop pseudocode above
  authored the module's original code in, still live at this point - per-module worktrees are torn
  down only by the post-merge § Cleanup Checklist above, never mid-run) - never an undefined
  "slice." Hand it the concrete lint output as evidence (the SAME "AUTONOMOUS FIX (review-driven)"
  sentinel pattern `odoo-code-review` already uses,
  `${CLAUDE_PLUGIN_ROOT}/skills/odoo-code-review/SKILL.md` § Autonomous fix loop). `odoo-coding`
  commits the fix there and returns the SHA exactly as any per-module dispatch does (§ Per-module
  Invocation Brief Template above, "Return: the commit SHA(s)").
- **Cherry-pick the fix back onto `run-integration` (mandatory - the fix does not ship until this
  runs).** `run-integration` is the ONLY branch the terminal land-tail squashes and pushes; a fix
  left on the module's own worktree branch never reaches the PR. Bring the returned SHA onto
  `run-integration` the SAME way § Per-module Integration Loop brings every other module SHA onto
  it - `cherry_pick(sha, into=run_integration)` via the `git-toolkit:git-ops` skill. This loop never
  runs raw git mutations inline; the repo's git-delegation rule binds it exactly as it binds every
  other mutation in this file. A semantic conflict here follows the SAME § Conflict Resolver path as
  any other cherry-pick.
- **Re-run the lint-class suite against `run-integration`'s new tip - never trust the coder's own
  DONE alone.** A `DONE` from `odoo-coding` proves the fix is clean on ITS OWN worktree; it does not
  prove `run-integration` - the tree that actually ships - is clean, since the fix has not landed
  there until the cherry-pick above completes. Re-run the full lint-class suite (as above) against
  `run-integration` HEAD after the cherry-pick, every iteration.
- **Bound the fix-loop to 3 iterations** (the SAME bounded-iteration convention as every other chain
  in this file - `${CLAUDE_PLUGIN_ROOT}/snippets/test-first-contract.md` § The loop, bounded; one
  iteration = the three bullets above: dispatch fix -> cherry-pick onto run-integration -> re-verify
  against run-integration). Still red OR still `tests-inconclusive` after 3 -> BLOCKED with the
  failure/coverage evidence - one of the ENUMERATED, legitimate stop conditions (`SKILL.md` Hard
  rule 2), not an incidental pause.
- **The single full-diff pass is also a net gain, not only a cost:** because every module across
  every wave has already landed on the ONE `run-integration` branch by this point, this ONE pass
  sees the FULL aggregate diff and catches CROSS-MODULE lint issues (two modules that individually
  pass but jointly trip a repo-wide rule) that per-module lint structurally could never see.
- **Teardown, unchanged contract.** Whoever runs this gate (run-harness inline, or a dispatched
  bounded subagent) self-provisions its OWN ephemeral instance - rooted on
  `WORKTREE_PATH: <path>/run-integration` per the paragraph above, never the catalog/principal
  checkout - and RELEASES it before the `integrate` node's own terminal signal, per
  `${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md`
  T0-T4 - the SAME contract every other self-provisioning step in this file already follows.
  Removing the per-work-item lint self-checks does not orphan anything: each was a self-contained
  acquire-run-release cycle (`agents/odoo-backend-coder.md` "Backend code-quality gate"), so removing
  the call removes the acquisition and its paired release together - no lease is left dangling, and
  the `odoo-coder` coordinator's OWN integrated-module-test instance cycle (a DIFFERENT, non-lint-class
  obligation) is untouched and continues exactly as before. Net effect across a run is FEWER
  acquire/release cycles overall, not a wash.

**4 - Terminal land-tail PR.** Only after stages 1, 2, 2b, and 3 above clear does run-harness
dispatch the `integrate` node (`SKILL.md` § `integrate` node dispatch): run § Squash Tree-Identity
Recipe's Existence precheck, then squash `run-integration`, push, and open ONE PR - per REPO, never
per wave, and UPDATE the PR rather than open a second one if the precheck finds this repo's PR
already open. The driver RE-DERIVES the readiness rule
here (`SKILL.md` § Gate-tier resolution, `integrate` readiness precondition) rather than trusting
`depends_on`, so an under-specified plan cannot open the PR ahead of a doc / review / acceptance
node. Everything after this point (CI-failure triage and fix, review/approval polling, the merge,
post-merge cleanup) is `odoo-pr-monitoring`'s, per the Terminal stage order constant above.

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
terminal `integrate` land-tail then runs its existence precheck, squashes run-integration, pushes,
and opens ONE PR (tree-identity verified); STOP at "PR opened". No merge.

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
`integration-loop.md` saga: clean-abort (abandon the run-integration worktree and re-fork it at the
pre-wave SHA) or resume from the last passing checkpoint; report the failing module. Never a
`reset --hard` against a live worktree, and never leave a half-built run-integration branch - this
is why the mid-wave stop stays autonomous (no destructive-confirm gate fires).
