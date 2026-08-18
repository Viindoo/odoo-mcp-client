# Run Integration - Reference Templates

On-demand reference for `skills/run-harness/SKILL.md`. Load this file when you need the full
template text for one of the structures below. Do not load it on every invocation.

> `run-harness` is consume-only: it CONSUMES the approved plan's nodes and their `depends_on` edges
> and dispatches each node to the skill the plan named; it never self-derives a plan and never
> chooses an agent or a model. The unit everywhere in this file is the **node**. The modules a node
> touches are a PROPERTY of that node, never a unit of work; the work-item is `odoo-coder`'s
> INTERNAL unit and never appears here. `run-harness` owns the integration branch and the
> cherry-picks onto it directly (there is no separate git-executor skill).

---

## Repo Capability Card Template

Fill ONE card PER REPOSITORY the run touches, at Run start, and embed the card of a node's OWN repo
verbatim in that node's dispatch brief. The cards are the run file's `repos[]` list (harness §8.3):
one entry per repo, `id` + the five fields below. A single-repo run is a one-entry list - same card,
no extra ceremony.

```
Repo Capability Card  (one per repo; serialized as a repos[] entry in run-<id>.json)
  id            : <DERIVED from the repo's `origin` URL - see "id resolution" below; the value
                   every node's `repo` field names>
  base          : <principal branch name>
  verify        : <command that must pass after every cherry-pick, e.g. "make test" or "make gen-check && make deps-check && make test">
  commit        : <resolved by git-toolkit:git-ops at commit time - do not pre-declare a standard>
  confidential  : <public | restricted | internal>
  worktree_root : <parent path for this repo's node worktrees, outside the repo tree>
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
- `worktree_root` should be outside the repo tree to avoid accidental staging of integration files
  by git.

---

## Run start procedure

Expansion of `${CLAUDE_PLUGIN_ROOT}/skills/run-harness/SKILL.md` § Run start. The two steps and the
three lineage invariants are DECIDED there; this section is the recipe.

```
# 1. FIRST action of the run - before this run creates or writes ANYTHING under its own
#    <ISOLATE_DIR>/integration/<slug>/:
sweep_stale_integration_dirs()   # full recipe: § Stale integration-dir sweep below

# 2. ONE branch + worktree pair PER ENTRY in RUN.repos[]. Resolve `base` and `worktree_root` from
#    THAT entry's own card - never from another entry's, and never from the invoking checkout's HEAD.
for each entry in RUN.repos[]:
    existence_precheck(entry)    # MANDATORY, before the add - see below
    if branch and worktree both already present: ADOPT them; do NOT add a second pair
    else: invoke git-toolkit:git-ops (Skill tool) to add a worktree:
        branch   = run-integration-<slug>
        worktree = <that entry's worktree_root>/run-integration
        base     = that entry's `base` / principal
```

**Existence precheck (ALWAYS FIRST, per entry).** The SAME discipline § Squash Tree-Identity Recipe
applies before a push, applied here before a fork and read LOCALLY instead of on the remote: Run
start is re-entered by every crash-resume, and a resume that crashed before node 1 reached `RUNNING`
looks exactly like a first start (`budget.nodes_run == 0`, no `RUNNING` node). DERIVE the two facts
through `git-toolkit:git-ops` bounded reads - never assert them, never read them from memory of what
this run did earlier - and record both in the run file:

| branch `run-integration-<slug>` | worktree at `<worktree_root>/run-integration` | what Run start does |
|---|---|---|
| no | no | the normal path: add the branch + worktree pair. |
| yes | no | ADOPT the branch - do NOT re-create it off `base` (that discards every commit already cherry-picked onto it). Add only the worktree, checked out on that branch. |
| yes | yes | ADOPT both and proceed to node 1. Re-forking here violates Invariant 1 and silently strands every landed commit. |

A branch present with an UNRESOLVABLE tip, or a worktree registered at that path for a DIFFERENT
branch, is not an adoption: STOP BLOCKED naming the entry and what was observed.

**Invariant 2 - the fork gives you the source, not the addons path.** A node's worktree forked from
run-integration CONTAINS its dependencies' committed source, because run-integration already carries
every prior node's cherry-picked commit. That source reaches a verification instance's addons-path
ONLY when the dispatch brief carries `WORKTREE_PATH` + `SELF_PROVISION: worktree-addons`
(`${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md` § Worktree-addons carve-out) - a
POLICY step, not a structural guarantee of the fork. Skipping it reopens the "dependency absent"
BLOCKED path even though the source already sits in the tree.

**Invariant 3 - the cherry-pick is a saga, not a bare pick.** Pick each node's returned commit onto
that repo's run-integration branch in `depends_on` topo order via `git-toolkit:git-ops`, run that
repo's card `verify` after each pick, and checkpoint only on a pass. A semantic conflict follows
§ Conflict Resolver below; a red verify applies the saga rollback in
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/integration-loop.md` (clean-abort to the pre-node SHA, or
resume from the last passing checkpoint). Never leave a half-built run-integration branch.

---

## Single-unit collapse

Unit-agnostic collapse rule. Cited by `${CLAUDE_PLUGIN_ROOT}/skills/run-harness/SKILL.md` and by
`${CLAUDE_PLUGIN_ROOT}/skills/odoo-modules-upgrade/references/upg-phase-detail.md` P4; this section
is its ONE owner - do not restate it, and do not re-derive a local variant.

**When a step has `n <= 1` unit to build, dispatch that one unit DIRECTLY into the
already-provisioned integration worktree and let it commit there.** No child worktree, no child
branch, no cherry-pick, no converge, no per-unit saga checkpoint. The saga reduces to the
integration branch's own history: record the pre-step SHA and clean-abort to it on failure
(`${CLAUDE_PLUGIN_ROOT}/skills/_shared/integration-loop.md` § Saga / rollback).

**COUNT `n`, never infer it.** `n` is the number of units the step actually dispatches, counted from
the caller's own list (for `run-harness`: source-writing nodes whose `repo` is this repo; for
`odoo-modules-upgrade` P4: the classification rows needing a coder). An absent or unreadable count
is NOT a collapse - take the child-worktree path.

**`n >= 2` keeps the child worktree, and the reason is POISON-CONTAINMENT, not an `index.lock`
race.** A unit whose build fails leaves its partial edits in its own tree, so the integration
branch's prior commits stay clean and the step can abort to the pre-step SHA without unpicking a
half-written sibling. That reason holds even where dispatch is strictly SEQUENTIAL - never justify
the child worktree as a concurrency race, because there is none when units are dispatched one at a
time.

---

## Execution-log Template

run-harness does NOT author the plan - it CONSUMES the approved plan (`odoo-planning` is the
producer). This template is the run-local EXECUTION LOG run-harness writes to
`<ISOLATE_DIR>/integration/<slug>/plan.md` (gitignored; resolve `<SHARE_DIR>`/`<ISOLATE_DIR>` once
per `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`; substitute the captured absolute path -
never write the placeholder or a bare `.odoo-ai/` into a Read/Write/Edit): the node map, the
cherry-pick / saga-checkpoint log, the review log, and the PR/squash result. It records what
run-harness did, not what to do.

```markdown
# Integration Log: <slug>

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

## Nodes

| Node | Modules | Branch | Worktree path | Files in scope | Status |
|---|---|---|---|---|---|
| <node-id> | <m1, m2> | node/<slug>-<node-id> | <path> | <file list> | pending |
| ... | | | | | |

## Ownership Map

```
<node-id-1> owns: [file1, file2, ...]
<node-id-2> owns: [file3, file4, ...]
```
(Sets must be disjoint. A file appearing under two nodes is a blocker - STOP BLOCKED and route back
to `odoo-planning`. The intra-node work-item split is odoo-coder's private concern, not logged here.)

## Cherry-pick Log

| Node | Commit SHA | Verify result | Notes |
|---|---|---|---|
| <node-id-1> | pending | - | |
| <node-id-2> | pending | - | |
| ... | | | |

## Review Log

| Phase | Reviewer | Findings | Fixed |
|---|---|---|---|
| Integration-branch cross-cutting review | <opus inline | escalated subagent> | <summary> | <yes/no + detail> |
| odoo-code-review | odoo-code-review skill | <findings> | <yes/no + detail> |

## PR (ONE per REPO - each opened once at that repo's land tail; one row per repos[] entry)

Repo    : <repos[].id>
URL     : <to be filled by that repo's terminal integrate land-tail>
Squash  : <backup ref> -> tree-identity <confirmed | FAILED>
Status  : <open | merged | closed>

## Cleanup

- [ ] node worktrees removed
- [ ] node branches deleted
- [ ] run-integration branch deleted (after merge)
- [ ] Backup tag deleted
- [ ] <ISOLATE_DIR>/integration/<slug>/ removed
```

---

## Cleanup Checklist

Post-merge cleanup is owned by `odoo-pr-monitoring` (it runs AFTER the merge approval gate's merge);
run-harness itself stops at "PR opened" (drive-to-done) and never merges or cleans up the
run-integration branch. This checklist is the one the post-merge owner runs; it covers the ONE
run-integration branch per repo plus every node worktree/branch the run created.

Invoke the **`git-toolkit:git-ops`** skill (via the Skill tool) in one request
(op=integration-cleanup):

```
[ ] remove worktree <path>/node-<node-id>   (and every other node worktree in this run)
[ ] remove worktree <path>/run-integration
[ ] delete branch node/<slug>-<node-id>     (and every other node branch in this run)
[ ] delete branch run-integration-<slug>    (after merge confirmed on remote)
[ ] delete tag run-integration-backup-<slug>
[ ] worktree-prune                          (clean stale worktree refs)
```

Local (run inline): `rm -rf <ISOLATE_DIR>/integration/<slug>/` (gitignored; safe to delete)

---

## Stale integration-dir sweep (24h crash-backstop, fail-closed)

The Cleanup Checklist above deletes `integration/<slug>/` on the NORMAL path (post-merge). This
section is the BACKSTOP for the abnormal path - a run that crashed, was killed, or was abandoned
before ever reaching that checklist leaks its `integration/<slug>/` dir forever unless a later run
reaps it (`snippets/visual-evidence-lifecycle-contract.md` § 3.1 `integration/<slug>/` row + § 3.6).

**Why a bare mtime sweep is UNSAFE here (do not use Clause 2's generic one-liner).** `run-harness`
can pause at an L2 human-confirm gate for an UNBOUNDED period mid-run (`SKILL.md` Hard rule 2 /
§ Gate-tier resolution: emit gate, end turn, resume after a human `continue`) - during that pause
nothing touches `integration/<slug>/plan.md`, so its mtime goes stale while the run is PAUSED, not
abandoned. A directory's age alone can never distinguish "abandoned" from "waiting on a human" -
the criterion MUST also positively correlate against the run's OWN status before deleting anything.

**The criterion: age is necessary but never sufficient - the correlating run's OWN top-level
`status` must independently prove TERMINAL.** `integration/<slug>/` and `run-<slug>.json` share ONE
id (`state-root-resolution.md`: "per active run"), so the correlating file is trivially locatable.
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
  find <ISOLATE_DIR>/integration/ -mindepth 1 -maxdepth 1 -type d -mmin +1440 -print0 |
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
§ Run start - before this run creates or writes anything under `integration/<own-slug>/` for the
first time (the same "before minting/creating your own state" placement every other § 3.1 sweep
site uses; a live run's own directory does not exist yet at this point, so it can never be the
accidental target). `find`'s `-mmin +1440` guarantees the same protection a second, independent
way: a directory a live run is actively writing into never ages 24h untouched while that writing
continues. Whoever executes `run-harness` next, every run - not a separate cleanup agent or cron.

Verify after cleanup (bounded reads inline):
`git worktree list` should show only the principal worktree.
Confirm the node branches are gone (git-ops reports deletion success).

---

## Squash Tree-Identity Recipe (git-ops delegation)

Runs ONCE per repo, at that repo's terminal `integrate` land-tail - NOT per node. All mutation steps
are delegated to git-toolkit via the **`git-ops`** skill
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

## Gate-tier node classes

Expansion of `${CLAUDE_PLUGIN_ROOT}/skills/run-harness/SKILL.md` § Gate-tier resolution, which owns
the tier FUNCTION and points here for the per-class detail. Nothing here computes a tier.

**Source-writing node.** The BINDING human gate is the driver's, emitted before dispatch. A skill's
own Phase-0 gate can never substitute for it: a spawner's worker subagent has no channel to pause a
turn on, so that inner gate is a safety-net only. A spawner writing solely under `$ODOO_AI_HOME`
(`odoo-code-review`, `odoo-ui-review`) writes no source and needs no gate beyond its registry tier.

**Static node.** It is in the Plan-Mode-approved DAG, so the human already approved it: at L0/L1 it
auto-passes under `--auto`, and no second gate is emitted for it.

**Dynamic node - the preview block.** A node materialized at runtime from a `next[]` / `on_complete`
suggestion was never in the approved plan, so the tier function returns L2 for it unconditionally
(GATE E-4 all-dynamic-L2). Emit this block, then END YOUR TURN and wait for the reply:

```
Proposed : <what this node would do>
Files    : <what it would write>
OSM      : backed | standalone
Gate     : approve / refine: [feedback] / cancel
```

Spell OSM out on first use in the session - Odoo Semantic, the indexed Odoo source; `backed` = the
node's facts are checked against it, `standalone` = it is not reachable and the node works from local
files only. The reply set is the PLAN gate set and
`${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md` owns it - never invent a fourth reply.
Write the prose in the USER'S language, keeping node ids, module names, paths, skill names and the
reply keywords verbatim (`${CLAUDE_PLUGIN_ROOT}/snippets/language-mirroring.md`).

**`confidence` resolution - an ABSENT value is `0.0`, never a default of "confident".** Before the
`next[]` admission test in `${CLAUDE_PLUGIN_ROOT}/skills/run-harness/SKILL.md` § The loop compares
anything, RESOLVE the field: a number stays itself; ABSENT, `null`, or a non-numeric value resolves to
`0.0`. `(nx.confidence or 0)` on that line is that resolution in code for every shape an emitter
actually produces. `0.0` is below the bar the same line sets, so an UNSCORED hop takes the
`note_as_suggestion(nx)` branch: a human sees it, and it NEVER auto-materializes into a live node.
Two reasons, both load-bearing. (1) An emitter that OMITS the field has expressed NO confidence at
all, and `${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` makes `confidence` the
advisory-vs-auto-run lever, so an omitted value is not a default - unscored hops are what real
emitters ship (`agents/odoo-code-reviewer.md` § Continuation Contract emits `next:
odoo-modules-upgrade` carrying no `confidence` field at all). (2) Reading the absence as consent
inserts a node the human never approved into a Plan-Mode-approved plan; reading it as `0.0` costs one
suggestion a human glances at. A number PRESENT but outside `0.0..1.0` is a malformed entry, not a
special case: nothing clamps it, so it still compares as written (`1.7` lands above the bar, `-0.2`
below) - record the malformation as a finding on that entry, and never silently rewrite the value.

**Neither class may be a DESIGN node - there is no tier for one, because it never gets dispatched.**
`odoo-solution-design` (and the `odoo-solution-architect` agent) is an INPUT to the plan, never a node
of it; the plan schema forbids it outright
(`${CLAUDE_PLUGIN_ROOT}/skills/odoo-intake/references/plan-mode-schema.md` § Design is an INPUT to
this plan). The plan this run is executing was DERIVED from an already-approved design, so a design
that ran DURING the run would either invalidate the ordering the human approved or be
reverse-engineered to justify it. Enforce it on BOTH classes, at the two places a node can enter a run:

- **STATIC node** (the plan named it): STOP the run BLOCKED with `blocked_reason` naming the node id
  and its `approach`, and route back to `odoo-planning` to amend the plan - the same disagreement path
  every § Plan agreement check takes. Never dispatch it and never re-tier it into legality.
- **`next[]` / `on_complete` suggestion** naming it: NEVER materialize it, and never emit the preview
  block above for it, at ANY `confidence` (§ `confidence` resolution above changes nothing here - this
  refusal is unconditional on the value). Record it as a finding naming `odoo-planning` as the owner
  who must amend the plan, then carry on with the remaining ready nodes - a design is not a step this
  driver may insert into a plan it did not author.

**Refusing the hop must not leave its EMITTER hanging: a YIELDING emitter is `BLOCKED`, never `DONE`.**
Refusal is the driver's call, so the stall it can cause is the driver's to close - here, once, for
every skill shaped this way, not skill by skill. The shape: the node returned `NEEDS_NEXT`, the
refused design hop was its ONLY forward move, and its own contract says it re-enters by reading the
design artifact out of that hop's returned `inputs`
(`${CLAUDE_PLUGIN_ROOT}/skills/odoo-modules-upgrade/SKILL.md` § P2b is exactly this - its mandatory
route-out verdicts emit the Continuation Contract and YIELD, then expect `design_doc` back on
re-entry). Such a node has nothing left to wait for, so `SKILL.md` § The loop's `NEEDS_NEXT -> DONE`
mapping does NOT reach it: that mapping holds only for a node whose `next[]` actually materialized,
and here nothing did. Calling it `DONE` and moving on parks it on a re-entry that can never arrive -
a node that silently never finishes, the same silent stop this contract exists to prevent. Instead set
THAT node to `BLOCKED` with `blocked_reason` naming (a) the node id, (b) the refused design hop, and
(c) `odoo-planning` as the owner who must amend the plan; the three-part `blocked_reason` grounding
rule in `${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` ("waiting" is never a bare
statement) applies verbatim. `BLOCKED` + `blocked_reason` are the EXISTING vocabulary - invent no
fifth status and no new field for what the node was waiting on. Nothing else about the run changes:
carry on with the remaining ready nodes exactly as in the bullet above, and BLOCK only the node that
was waiting. A refused hop from a node that was NOT waiting on it (it returned `DONE`, or
`NEEDS_NEXT` with another hop that did materialize) stays a finding and nothing more.

"Plan it, then design it" is the one ordering this driver may never run. The converse costs nothing and
is the norm: a design that ran BEFORE the plan is simply the plan's input pointer.

---

## Node Invocation Brief Template

The concrete brief `run-harness` composes when it dispatches a coding node to `odoo-coding`. Pass
**inputs only** - `odoo-coding`'s own body owns every procedure (design-doc resolution, model-tier
choice, test-first dispatch); never restate `odoo-coding`'s internals here, only the fields it needs
to CONSUME the plan's already-computed slice for one node (SSOT for the full field-by-field
contract: `${CLAUDE_PLUGIN_ROOT}/skills/odoo-coding/SKILL.md` § Plan-provided fast-path).

```
## NODE <id> -> odoo-coding (Plan-provided fast-path: CONSUME, do not re-derive)
WORKTREE_PATH    : <absolute path> - author + commit ALL work inside this worktree; do NOT touch the
                   principal checkout and do NOT cherry-pick/merge/push (run-harness integrates)
MODULES          : <this node's `modules` list, comma-separated, in dependency order - may be one
                   module, part of one, or several; omit only when the node touches no Odoo module>
FILES            : <this node's files-in-scope globs - disjoint from every other node's by schema>
STACK            : <backend | frontend | fullstack - this node's stack split, from the plan (lets the
                   odoo-coding fast-path consume the stack instead of re-inferring; omit only when the
                   plan did not tag it, then odoo-coding infers from files). The intra-node work-item
                   split is odoo-coder's job, not a run-harness input.>
DEPENDS_ON       : <the node ids this node depends on (already cherry-picked onto run-integration) +
                   downstream impact>
CROSS-MODULE ASSERTIONS : <the plan's Block 3 one-liner naming which of this node's assertions cross a
                   module boundary, so odoo-coder stages them post-install; `none` when it has none>
DESIGN_DOC       : <child TDD for this node | none>
MASTER_DESIGN_DOC: <master TDD path | none>
SURVEY           : <deep-survey synthesis.md path | none - forwarded from the node's
                   inputs.survey (phase-p-run-dag.md § Survey pointer); ALWAYS an explicit
                   value, never omitted - none means no deep survey ran this session>
SHARE_DIR        : <captured absolute path - resolved ONCE by run-harness against the run root>
ISOLATE_DIR      : <captured absolute path - resolved ONCE by run-harness against the run root>
design_index     : <absolute path under SHARE_DIR, e.g. <SHARE_DIR-literal>/designs/<slug>/index.yaml | none>
ODOO VERSION     : <the plan's run-header odoo_version - one resolved version for the run>
REQUEST          : <precise description of the behaviour this node delivers>
Repo Capability Card: id=<this node's repo> base=<principal> verify=<command> commit=<resolved by git-ops> confidential=<level>
                   (the repos[] entry whose id equals this node's `repo` - never another repo's card)
WORKLOG          : <runSlug> - read it, then append significant decisions
Return: the commit SHA on the node's branch (REQUIRED - a DONE with no SHA is a failed contract;
        the odoo-coder coordinator obtains the SHA by committing its coders' files via
        git-toolkit:git-ops, NOT via a raw coder commit) so run-harness can cherry-pick it onto
        run-integration.
```

---

## Verification Brief Template

The brief `run-harness` composes ITSELF for a node whose `approach` is `odoo-instance`
(`${CLAUDE_PLUGIN_ROOT}/skills/run-harness/SKILL.md` § Verification dispatch, which owns the
decision and the GREEN-only DONE rule). Composing it yourself is what makes the touch EPHEMERAL and
is the basis of that section's tier ceiling - never delegate the composition and never drop
`MODE: fresh` / `PERSIST: ephemeral`. `WORKTREE_PATH` names a root other than your own cwd, so
resolve `SHARE_DIR`/`ISOLATE_DIR` ONCE against THAT root and pass the captured absolute strings
(`${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md` § Cross-worktree dispatch); a leaf that
re-resolves them from its own cwd writes into the wrong worktree.

```
OPERATION        : run-tests
SERIES           : <the plan's run-header odoo_version>
MODULES          : <node.modules, comma-separated, in the order the plan wrote them>
MODE             : fresh
PERSIST          : ephemeral
SELF_PROVISION   : worktree-addons
WORKTREE_PATH    : <this repo's run-integration worktree>
SHARE_DIR        : <the run's captured absolute SHARE path - substitute it, never re-resolve>
ISOLATE_DIR      : <the run's captured absolute ISOLATE path - substitute it, never re-resolve; the
                   agent appends the run worklog and must not key it on WORKTREE_PATH's own toplevel>
WORKLOG          : <runSlug> - read it, then append significant decisions
GATE_ROLE        : node-verify
TEST_TAGS        : <series 12.0+: `/<m>` per module in MODULES, comma-joined, so BOTH the at-install
                   and the post-install stage run for exactly those modules. Series 8.0-11.0: `none` -
                   no tag filter exists there, so `--test-enable` runs every installed module's
                   suite including the core dependency closure; slower, and expected.>
```

---

## Conflict Resolver (Sonnet subagent)

When a cherry-pick onto `run-integration` reports a semantic conflict, dispatch a brief Sonnet
resolver subagent - never resolve the conflict inline in run-harness's own context, and never push
the resolution down to the node's `odoo-coder`/coder workers.

Worker brief (SSOT: `${CLAUDE_PLUGIN_ROOT}/snippets/worker-brief.md`): "Resolve the semantic
conflict by editing the conflicting files in the `run-integration` worktree at
`<path>/run-integration` (the cherry-pick target - NEVER the node's own worktree). Ground
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

## Review Escalation (integration-branch cross-cutting review)

The brief for a REVIEW NODE the plan places over a repo's integration branch. The plan wires that
node to `odoo-code-review`, which applies this section whenever it is invoked on an
integration-branch aggregate diff. It is distinct from the per-node code -> review+test loop
`odoo-coding` runs inside a coding node (narrower scope); both run (double-review). This review is
NEVER a flat inline review regardless of the diff's size - measure the diff and escalate when it is
large:

Measure: `git diff <principal>...HEAD --shortstat` (changed lines) and the module count N over the
integration branch.

- **Large diff** (>~1500 changed lines OR N >= 8 modules): escalate to a **fable** review subagent
  dispatched from the review node's own context. ALWAYS confirm with the human first, and ask as a
  TRADEOFF, never by tier name - how big the diff is, that the review runs on the deepest-reasoning
  setting, and that it costs about 2x - with the reply set `approve / skip / cancel`. On `skip` or
  when the setting is unavailable, fall back to **opus inline review** and note the downgrade.
- **Otherwise** (the common case): **opus inline review**, in the review node's own context.

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
affected node's OWN worktree (the SAME worktree `run-harness` provisioned for that node at dispatch,
where its original code was authored) plus the AUTONOMOUS FIX (review-driven) sentinel. This third
path uses a SEPARATE tree from `run-integration`, so it is not done until the returned SHA is
cherry-picked back onto `run-integration` - the SAME
`cherry_pick(sha, into = repos[node.repo].run_integration)` step
`${CLAUDE_PLUGIN_ROOT}/skills/run-harness/SKILL.md` § The loop performs for every node SHA, via the
`git-toolkit:git-ops` skill, never a raw git command inline. **Re-run verify against
`run-integration`'s current tip specifically** (never the node's own worktree, and never a
worker's bare DONE self-report) after ANY of the fix paths above. The review node returns DONE only
once that re-verification is clean.

## Pre-PR tail (mandatory sequence, after the repo's last verification node closes GREEN)

### Terminal stage order (THE constant - this section is its ONE owner)

Cite this constant by name. Do NOT restate the order in another file, and do NOT reorder it
locally. Every orchestrator with a terminal tail (`odoo-forward-port`, `odoo-git-rebase`,
`odoo-modules-upgrade`) and every `writes-files` plan
(`${CLAUDE_PLUGIN_ROOT}/skills/odoo-intake/references/plan-mode-schema.md` Block 2) resolves its
terminal stage order HERE.

```text
  the repo's last verification node closes GREEN
    +--> (1)  review      [skill: odoo-code-review]      integration-branch aggregate diff
    +--> (2)  i18n        [skill: odoo-i18n]             reconcile translations
    +--> (3)  acceptance  [skill: odoo-acceptance]       live blast-radius oracle
    +--> (4)  doc         [skill: odoo-doc-illustration] user guide + App-Store landing
    +--> (5)  lint        pre-PR lint-class gate over the aggregate diff  [DRIVER STEP, not a node]
    +--> (6)  PR          [node: integrate]  ONE PR per REPO, opened ONCE - the only land step
    |
    +-------> monitor     [skill: odoo-pr-monitoring]    CI triage, review polling  [post-PR]
    +-------> merge       [skill: odoo-pr-monitoring]    the single outward L2 gate [post-PR]
```

**SEVEN of these eight positions are ORDINARY PLAN NODES, so this constant is an ORDERING RULE, not
an execution step.** `review`, `i18n`, `acceptance`, `doc`, the PR itself (`approach_kind:
integrate`), `monitor` and `merge` are each authored as their OWN node by `odoo-planning`, wired to
the skill named above, and dispatched ONE AT A TIME by `run-harness`'s `pick_ready` loop exactly like
a coding node. The PLAN copies this order into its `depends_on` edges; nothing here dispatches a
position, and no tail may re-drive one. `integrate` readiness clause (i)
(`${CLAUDE_PLUGIN_ROOT}/skills/run-harness/SKILL.md`) already requires every pre-PR node of that repo
DONE-or-SKIPPED before the PR can open, so a tail that drove them again would double a DECLARED human
gate (i18n and acceptance are registry-L2 - `generator/skill_tool_deps.json`, `instance_touching:
true` - and the ephemeral ceiling does not reach them, because the driver does not write their
briefs) and execute a side-effecting stage twice.

**The ONE exception - do not delete it when trimming this section. Position (5), the pre-PR
LINT-CLASS GATE, is NOT a plan node.** No node carries it; it is a DRIVER step the `integrate` land
tail runs itself over the integration branch's aggregate diff. It keeps its caller
(`${CLAUDE_PLUGIN_ROOT}/skills/run-harness/SKILL.md` § `integrate` node dispatch, step 1) and it
keeps `GATE_ROLE: pre-pr-lint-gate`. Stage blocks (5) and (6) below are the only execution detail
this section still owns.

**Every terminal NODE's brief carries the integration worktree.** When the loop dispatches a review /
i18n / acceptance / doc node, state `WORKTREE_PATH: <path>/run-integration` on that dispatch, plus
`SELF_PROVISION: worktree-addons` when a bounded subagent carries it
(`${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md` § Worktree-addons carve-out). Same for
an `odoo-acceptance` node the loop MATERIALIZES from a review node's `next[]`: thread
`worktree_path: <path>/run-integration` into its `inputs` before dispatch, because
`odoo-acceptance`'s own Inputs resolves its live instance from a caller-supplied `INSTANCE_HANDLE` or
the catalog default (`${CLAUDE_PLUGIN_ROOT}/snippets/instance-resolution.md`) and NEITHER path is
worktree-aware. Without the field the stage's instance loads the CATALOG addons path and reviews,
translates, accepts or screenshots the PRINCIPAL checkout instead of the tree the PR ships - the same
false-green stage (5)'s Worktree-targeting paragraph closes. Anything such a node authors outside
`<path>/run-integration` reaches the PR only through the SAME
`cherry_pick(sha, into = repos[node.repo].run_integration)` step the loop performs for every node SHA
(via `git-toolkit:git-ops`, never raw git; a semantic conflict follows § Conflict Resolver):
`run-integration` is the ONLY branch the land tail squashes and pushes, so a doc file or a .po left
on another branch never ships.

Each edge is a dependency, not a style preference:

- **review first.** Its findings are fixed by EDITING SOURCE, so it belongs ahead of everything the
  edit would invalidate; and its blast-radius render-check is what makes the acceptance position fire
  at all - `odoo-code-review` emits that hand-off itself whenever a `render_check_set` reaches beyond
  the changed modules (`${CLAUDE_PLUGIN_ROOT}/skills/odoo-code-review/SKILL.md` § Emit the acceptance
  hand-off; shared `render_check_set` SSOT:
  `${CLAUDE_PLUGIN_ROOT}/snippets/acceptance-scope.md`), and that hand-off is a
  BEFORE-the-PR obligation, never a post-merge one. A review placed after i18n would also re-read the
  whole translated `.po` churn for nothing.
- **i18n before acceptance.** i18n MUTATES what the live UI renders (translated labels/messages, per
  `${CLAUDE_PLUGIN_ROOT}/snippets/i18n-mandate-contract.md` "The mandate" - the contract the i18n
  NODE carries, ONCE for the whole run over the integration branch's aggregate diff, never per module
  and never per node; `run-harness` is a THIRD caller of that contract alongside
  `odoo-modules-upgrade` and `odoo-forward-port`), and acceptance's evidence (screenshots, asserted
  UI text) must reflect that FINAL, translated state - acceptance first would capture pre-i18n
  evidence that i18n then invalidates.
- **doc after acceptance.** The doc stage CAPTURES the live UI (screenshots for `doc/index.rst`
  and `static/description/index.html`), so it consumes exactly what acceptance may still change: an
  acceptance FAIL routes a code fix, and every screenshot taken before that fix is stale. Placing
  doc after acceptance also puts it after i18n, so captures show the translated strings.
- **doc before lint.** The doc stage WRITES committed files and wires `__manifest__.py` (images,
  store keys). The single full-diff lint-class pass at (5) must see those edits, or the run's ONE
  PR ships manifest changes no gate ever read.
- **Anything that can force a CODE CHANGE runs at or before (5), i.e. before the PR opens.** A
  review, oracle, capture, or gate whose findings are fixed by editing source belongs BEFORE the PR
  opens. Running it after makes the PR churn and makes regression testing chase a moving target - the
  exact failure this order exists to prevent. Every such edit re-opens § Verdict currency below.
- **Only work that must OBSERVE the opened PR runs after (6).** CI-failure triage and fix,
  static-review-bot comment cross-check, review/approval polling, the MERGE itself, and post-merge
  cleanup - all owned by `${CLAUDE_PLUGIN_ROOT}/skills/odoo-pr-monitoring/SKILL.md`. A bot comment
  cannot predate the PR it is posted on; a worktree diff review can, and therefore must.
- **ONE PR per REPO.** The PR stage opens exactly one PR for each repo the run touched, once that
  repo's readiness predicate holds (`${CLAUDE_PLUGIN_ROOT}/skills/run-harness/SKILL.md`
  § integrate readiness - a predicate the driver evaluates over the LIVE node set, for which the
  plan's `integrate.depends_on` is only a floor).
- **A pipeline that has no stage at some position SKIPS that position - it never reorders the
  rest.** A run with no user-guide/App-Store goal has no doc node (`odoo-planning` P1b fast-path
  `doc: none`); a forward-port has no doc stage at all. Both still run every position they DO carry,
  in this order, ending at the lint gate and then the PR.

### Verdict currency (a CONDITION the driver evaluates, not a caution)

`integrate` readiness clause (iii) (`${CLAUDE_PLUGIN_ROOT}/skills/run-harness/SKILL.md`
§ integrate readiness) owns the rule; this is how to evaluate it. **ANY mutation of repo `R`'s
`run-integration` branch after that repo's last verification node closed GREEN INVALIDATES that
verdict.** Every terminal position can mutate it - a review node's fix, an i18n node's `.po`/`.pot`
rewrite, an acceptance FAIL routing a code fix, a doc node's committed files and `__manifest__.py`
image/store-key wiring, and the lint gate's own containment-loop cherry-pick - and a manifest edit
alone can break module install.

Compare the `run-integration` tip recorded in the clause-(ii) node's `produced` against `R`'s LIVE
`run-integration` tip, through a bounded `git-toolkit:git-ops` read. They differ -> clause (ii) is
UNSATISFIED: RE-DISPATCH that verification node (§ Verification dispatch, same `node.modules` suite
scope) and require a fresh GREEN over the current tip before the PR opens. Re-running only the
lint-class suite does NOT restore the verdict - lint proves style, not behavior, and the tree the PR
ships would carry code no suite ever exercised. This is the same discipline § Review Escalation
already applies to its own fixes ("Re-run verify against `run-integration`'s current tip
specifically"), applied to every other mutator.

Evaluate it at `pick_ready` (before `integrate` becomes READY) AND again inside the land tail, after
stage (5)'s containment loop cherry-picks a fix and before stage (6)'s Existence precheck.

**5 - Pre-PR lint-class gate (L0/L1 - ephemeral instance, not a SHARED-instance L2 case).** Run the
FULL CI-parity lint-class suite ONCE, over the run-integration branch's aggregate diff (every module
the run touched): `/test_lint` (+ `/test_pylint` on v16+ Viindoo profiles) and the Tier-1 eslint
leg of `verify-frontend.sh`. Invocation mechanics (commands, flags, PASS/CANNOT-VERIFY semantics)
are owned by `${CLAUDE_PLUGIN_ROOT}/docs/reference/odoo-code-quality.md` +
`${CLAUDE_PLUGIN_ROOT}/docs/reference/ODOO-TESTING.md` - not restated here. This REPLACES every
per-work-item / per-node lint-class self-check and re-verification - see
`${CLAUDE_PLUGIN_ROOT}/skills/odoo-coding/SKILL.md` and its hard-leaf workers for what
stays per-node instead (OSM-grounded ORM validation, inline review, zero-toolchain static OWL/SCSS
checks - none of these are lint-class and none run here).

**Worktree targeting is explicit, never inferred from cwd (mandatory).** This gate's ephemeral
instance MUST load `run-integration`'s tree, not the principal checkout - the SAME requirement
Example 3 below states for a cross-node verification instance ("the allocator emits the CATALOG
addons list, which points at the principal checkout"). State `WORKTREE_PATH: <path>/run-integration`
on the provisioning dispatch: when this gate runs INLINE in run-harness's own context, pass
`WORKTREE_PATH: <path>/run-integration` directly on the `odoo-instance` skill dispatch (the field
`${CLAUDE_PLUGIN_ROOT}/skills/odoo-instance/SKILL.md` § Dispatch already defines); when run-harness
instead dispatches a bounded subagent for this gate, carry `WORKTREE_PATH: <path>/run-integration`
PLUS `SELF_PROVISION: worktree-addons` in that subagent's brief - the SAME two fields § Node
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
in particular the integrated node test `odoo-coder` runs for every coding node
(`${CLAUDE_PLUGIN_ROOT}/agents/odoo-coder.md` § Own the integrated node verification), and the
driver's own § Verification dispatch for an `odoo-instance` node
(`${CLAUDE_PLUGIN_ROOT}/skills/run-harness/SKILL.md`) - states `GATE_ROLE: node-verify` instead, so
the SAME operation name (`run-tests`) never collapses the two into one gate again: a node's
integrated test surfaces ONLY that node's behavior failures, never a lint-class failure, and
lint-class failures surface ONLY here. Omitting `GATE_ROLE` on this dispatch is not a safe default -
the agent refuses with `NEEDS_CONTEXT` rather than silently guess, exactly like an omitted
`WORKTREE_PATH` above must never be inferred from cwd.

**A `tests-inconclusive` verdict from THIS dispatch is treated as a non-pass too, not only
`tests-failed` (mandatory).** `agents/odoo-instance-ops.md` § Verdict contract resolves this
`GATE_ROLE: pre-pr-lint-gate` dispatch to `tests-inconclusive` on ANY `TEST_RESULT=inconclusive`
(skips, or no proof the suite ran), and on the "Checker-load coverage confirmation" case (a custom
checker - e.g. an SQL-injection rule - that failed to load, or a log with no checker-coverage
statement to confirm at all). No case is a `tests-passed` in disguise, and this is the ONE dispatch in the whole
run authorized to trigger the lint-class union at all - there is no LATER gate to catch a miss
here. An unattended `--auto` drive-to-done run has nothing else guaranteed to perform the "human
reviewing `findings_path`" step that dispatch's own contract text demands for `tests-inconclusive`
in general, so for this ONE gate specifically, `tests-inconclusive` enters the SAME containment
loop below as `tests-failed` - never a silent pass-through to the terminal PR.

**Containment for tail-only lint (mandatory prose, not optional).** Moving lint to the tail trades
"catch it while the authoring context is warm" for "catch it once, cheaply, over the full diff" -
this trade is intentional (the owner's instruction), but it must not become a worse failure than what
it replaces:
- **On a FAILURE OR a `tests-inconclusive` verdict (any `TEST_RESULT=inconclusive` reason, or coverage-shortfall/unconfirmed -
  see the paragraph above), do not flat-BLOCK the run.** For a FAILURE, the lint tool's own output
  names the exact file/line; for a coverage gap, `findings_path`/`notes` names which lint-class
  module's checker coverage could not be confirmed and why (per the coverage rule cited above) -
  either way, that is the evidence to hand off. Re-invoke `odoo-coding` with `WORKTREE_PATH` set to
  the failing node's OWN worktree (the SAME worktree `run-harness` provisioned for that node at
  dispatch, still live at this point - node worktrees are torn down only by the post-merge
  § Cleanup Checklist above, never mid-run) - never an undefined "slice." Hand it the concrete lint
  output as evidence (the SAME "AUTONOMOUS FIX (review-driven)" sentinel pattern `odoo-code-review`
  already uses, `${CLAUDE_PLUGIN_ROOT}/skills/odoo-code-review/SKILL.md` § Autonomous fix loop).
  `odoo-coding` commits the fix there and returns the SHA exactly as any node dispatch does
  (§ Node Invocation Brief Template above, "Return: the commit SHA").
- **Cherry-pick the fix back onto `run-integration` (mandatory - the fix does not ship until this
  runs).** `run-integration` is the ONLY branch the terminal land-tail squashes and pushes; a fix
  left on the node's own worktree branch never reaches the PR. Bring the returned SHA onto
  `run-integration` the SAME way `${CLAUDE_PLUGIN_ROOT}/skills/run-harness/SKILL.md` § The loop
  brings every other node SHA onto it - `cherry_pick(sha, into = repos[node.repo].run_integration)`
  via the `git-toolkit:git-ops` skill. This loop never runs raw git mutations inline; the repo's
  git-delegation rule binds it exactly as it binds every other mutation in this file. A semantic
  conflict here follows the SAME § Conflict Resolver path as any other cherry-pick.
- **Re-run the lint-class suite against `run-integration`'s new tip - never trust the coder's own
  DONE alone.** A `DONE` from `odoo-coding` proves the fix is clean on ITS OWN worktree; it does not
  prove `run-integration` - the tree that actually ships - is clean, since the fix has not landed
  there until the cherry-pick above completes. Re-run the full lint-class suite (as above) against
  `run-integration` HEAD after the cherry-pick, every iteration.
- **Lint alone does NOT re-open the door to the PR.** The cherry-pick above just MUTATED
  `run-integration` after the repo's verification node closed GREEN, so § Verdict currency now holds
  that verdict INVALID: re-dispatch the verification node and require a fresh GREEN over the new tip
  as well. A green lint suite over a tree whose behavior suite predates the fix is exactly the
  PR-on-unverified-tree the readiness predicate exists to refuse.
- **Bound the fix-loop to 3 iterations** (the SAME bounded-iteration convention as every other chain
  in this file - `${CLAUDE_PLUGIN_ROOT}/snippets/test-first-contract.md` § The loop, bounded; one
  iteration = the three bullets above: dispatch fix -> cherry-pick onto run-integration -> re-verify
  against run-integration). Still red OR still `tests-inconclusive` after 3 -> BLOCKED with the
  failure/coverage evidence - one of the ENUMERATED, legitimate stop conditions (`SKILL.md` Hard
  rule 2), not an incidental pause.
- **The single full-diff pass is also a net gain, not only a cost:** because every node's commit has
  already landed on the ONE `run-integration` branch by this point, this ONE pass sees the FULL
  aggregate diff and catches CROSS-MODULE lint issues (two modules that individually pass but
  jointly trip a repo-wide rule) that per-module lint structurally could never see.
- **Teardown, unchanged contract.** Whoever runs this gate (run-harness inline, or a dispatched
  bounded subagent) self-provisions its OWN ephemeral instance - rooted on
  `WORKTREE_PATH: <path>/run-integration` per the paragraph above, never the catalog/principal
  checkout - and RELEASES it before the `integrate` node's own terminal signal, per
  `${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md`
  T0-T4 - the SAME contract every other self-provisioning step in this file already follows.
  Removing the per-work-item lint self-checks does not orphan anything: each was a self-contained
  acquire-run-release cycle (`agents/odoo-backend-coder.md` "Backend code-quality gate"), so removing
  the call removes the acquisition and its paired release together - no lease is left dangling, and
  the `odoo-coder` coordinator's OWN integrated-node-test instance cycle (a DIFFERENT, non-lint-class
  obligation) is untouched and continues exactly as before. Net effect across a run is FEWER
  acquire/release cycles overall, not a wash.

**6 - Terminal land-tail PR.** The `integrate` node is dispatched by `pick_ready` once § integrate
readiness holds - positions (1)-(4) are its own DONE-or-SKIPPED plan nodes, and position (5) is the
first thing its dispatch runs (`SKILL.md` § `integrate` node dispatch (the land tail)). Then: run
§ Squash Tree-Identity Recipe's Existence precheck, squash `run-integration`, push, and open ONE PR -
per REPO, and UPDATE the PR rather than open a second one if the precheck finds this repo's PR
already open. The driver evaluates § integrate readiness (`SKILL.md`) over the LIVE node set and
treats the plan's `integrate.depends_on` as a floor, so an under-specified plan cannot open the PR
ahead of a doc / review / acceptance node. Do NOT materialize an `odoo-pr-monitoring` node from here:
`monitor` and `merge` are plan nodes that depend on `integrate`, and `pick_ready` takes them next.
Everything after this point (CI-failure triage and fix, review/approval polling, the merge,
post-merge cleanup) is `odoo-pr-monitoring`'s, per the Terminal stage order constant above.

---

## Examples

> These examples start from run-harness picking a node off the RUN-DAG (never from a user phrase - a
> user's parallel/multi-module request routes to `odoo-planning`, which authors the nodes).

**Example 1 - Standard 3-node run:**
The plan carries 3 independent coding nodes (each e.g. a computed field + its OWL widget + its unit
tests), then a verification node, then the terminal chain.
Action: at Run start, sweep stale integration dirs and fork ONE `run-integration` branch + worktree
for the repo. Per node, in `depends_on` order: verify plan agreement (disjoint file scopes), fork the
node's worktree FROM run-integration, INVOKE `odoo-coding` (which dispatches one `odoo-coder`, which
commits the node and returns the SHA), cherry-pick that SHA onto run-integration, verify and
checkpoint. Then the verification node runs the suites GREEN, the review node reviews the aggregate
diff, and the terminal `integrate` node runs the pre-PR tail, its existence precheck, squashes
run-integration, pushes, and opens ONE PR (tree-identity verified); STOP at "PR opened". No merge.

**Example 2 - Dependency edge consumed:**
Node B `depends_on` node A.
Action: A is dispatched and cherry-picked first; then B's worktree is forked from the UPDATED
run-integration, so it already contains A's committed source. run-harness never recomputes the edge -
it consumes it from the plan.

**Example 3 - A dependency's source is in the tree but not on the addons path:**
A later node depends on an earlier node's module.
Action: the earlier node's cherry-picked code is already on the single run-integration branch, so the
later node's worktree - forked from run-integration - CONTAINS the dependency's source. It is NOT on
the verification instance's addons-path by default: the allocator emits the CATALOG addons list,
which points at the principal checkout. The node's brief therefore carries `WORKTREE_PATH` and
`SELF_PROVISION: worktree-addons` so the coordinator provisions an instance rooted on its own
worktree (`${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md` § Worktree-addons carve-out).
With that in place there is no intermediate PR and no "dependency absent" BLOCKED path.

**Example 4 - Ownership conflict (plan agreement catches a bad plan):**
The plan puts `models.py` in two nodes' `files-in-scope`.
Action: `verify_plan_agreement`'s file-scope disjointness check finds `models.py` in both. STOP
BLOCKED: report the overlap and route back to `odoo-planning` to re-partition. No worktree is
created.

**Example 5 - Squash mismatch abort (terminal land-tail):**
Terminal squash of the run-integration branch: `git diff --quiet run-integration-backup-<slug>` exits
1 (tree mismatch). Abort: "Squash tree-identity FAILED - the squashed commit does not match the
pre-squash tree. Restoring from run-integration-backup-<slug>. Do NOT push." Report the differing
files. (No branch was pushed yet, so there is nothing to force-push or revert on the remote.)

**Example 6 - Conflict resolver path:**
Two nodes unexpectedly both touch a shared file (missed by the plan; caught at cherry-pick): the
second node's cherry-pick fails with a conflict. Dispatch a Sonnet resolver subagent
(worker-brief.md) with the conflict diff + both node briefs. Resolver edits the conflicting files
(markers removed). run-harness re-invokes git-ops (cherry-pick --continue). Re-run verify,
checkpoint, continue.

**Example 7 - Mid-node failure (saga rollback):**
A cherry-pick verify cannot be made green within the loop's bound. Apply the
`integration-loop.md` saga: clean-abort (abandon the run-integration worktree and re-fork it at the
pre-node SHA) or resume from the last passing checkpoint; report the failing node. Never a
`reset --hard` against a live worktree, and never leave a half-built run-integration branch - this
is why the mid-run stop stays autonomous (no destructive-confirm gate fires).
