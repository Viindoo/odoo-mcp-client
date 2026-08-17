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
    invoke git-toolkit:git-ops (Skill tool) to add a worktree:
        branch   = run-integration-<slug>
        worktree = <that entry's worktree_root>/run-integration
        base     = that entry's `base` / principal
```

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
- **ONE PR per REPO.** The PR stage opens exactly one PR for each repo the run touched, once that
  repo's readiness predicate holds (`${CLAUDE_PLUGIN_ROOT}/skills/run-harness/SKILL.md`
  § integrate readiness - a predicate the driver evaluates over the LIVE node set, for which the
  plan's `integrate.depends_on` is only a floor).
- **A pipeline that has no stage at some position SKIPS that position - it never reorders the
  rest.** A run with no user-guide/App-Store goal has no doc node (`odoo-planning` P1b fast-path
  `doc: none`); a forward-port has no doc stage at all. Both still run (1) -> (2) -> (3) -> (4).

The stage blocks below are the execution detail for (1), (2), (2b), (3), (4) in that order.

**1 - i18n reconcile (MANDATORY, narrow-escape only, ONCE for the whole run).** Dispatch the
`odoo-i18n` skill exactly ONCE, over the run-integration branch's aggregate diff (every module the
run touched) - never per module and never per node. Mandate wording, the four caller obligations,
and the enumerated escape hatches (E1-E6) are owned by
`${CLAUDE_PLUGIN_ROOT}/snippets/i18n-mandate-contract.md` - not restated here; run-harness is a
THIRD caller of that contract alongside `odoo-modules-upgrade` and `odoo-forward-port`.
`odoo-i18n`'s registry `default_gate_tier` is L2 (`generator/skill_tool_deps.json`
`orchestration.odoo-i18n` - `instance_touching: true`) and this driver does NOT compose its instance
brief, so the tier function (`SKILL.md` § Gate-tier resolution) returns L2 and the ephemeral ceiling
does not reach it: expect a DECLARED human gate here (the ENUMERATED stop conditions in
`SKILL.md` Hard rule 2), not an incidental pause. `odoo-coding`'s own per-node Continuation Contract
does NOT also suggest `odoo-i18n` - that would fire once per node for the same run-level obligation;
see `${CLAUDE_PLUGIN_ROOT}/skills/odoo-coding/SKILL.md` § Continuation Contract.

**2 - Acceptance (conditional, L2, ONCE for the whole run - fires BEFORE the PR, not after it).**
When ANY review node's blast-radius render-check (§ Review Escalation above) reached BEYOND that
node's own modules (the `render_check_set` binds dependents), materialize an `odoo-acceptance` node -
the SAME condition and shape `odoo-code-review` uses for its own acceptance hand-off
(`${CLAUDE_PLUGIN_ROOT}/skills/odoo-code-review/SKILL.md` § Emit the acceptance hand-off; shared
render_check_set SSOT: `${CLAUDE_PLUGIN_ROOT}/snippets/acceptance-scope.md`) - but depending on
stage 1 above (i18n) and the repo's last verification node, NEVER on the run's PR. Do NOT auto-run
acceptance and do NOT auto-merge/auto-block on it; do NOT dispatch it once per triggering node -
coalesce every trigger into ONE cluster-wide `odoo-acceptance` invocation covering the UNION
of every widened `render_check_set`, mirroring `odoo-modules-upgrade`'s "ONCE for the whole
cluster, never per module":

```
next:
  - skill: odoo-acceptance
    reason: one or more nodes changed a UI/behavior surface with dependents (render_check_set beyond the changed modules); run blast-radius acceptance over the affected cluster BEFORE the PR opens
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
carve-out). When no review node ever widened its `render_check_set`, this stage does not fire and the
tail proceeds straight to stage 2b.

**2b - Doc (conditional, L1, ONCE for the whole run - after acceptance, before the lint gate).**
Fires when the approved plan carries a doc node (user guide `doc/index.rst` and/or App-Store landing
`static/description/index.html`); an internal-only run has none (`odoo-planning` P1b fast-path
`doc: none`) and the tail proceeds straight to stage 3. Position is fixed by the Terminal stage
order constant above: doc CAPTURES the live UI, so it must see the accepted (stage 2) and translated
(stage 1) state, and it WRITES committed files plus `__manifest__.py` image/store-key wiring, so it
must land before the single full-diff lint pass at stage 3 reads them.

Dispatch the `odoo-doc-illustration` skill ONCE for the whole run, over the run-integration branch's
aggregate module set (every module the run touched) - never per module and never per node.
`odoo-doc-illustration`'s registry `default_gate_tier` is L1
(`generator/skill_tool_deps.json` `orchestration.odoo-doc-illustration`), so the tier function
returns L1 and it auto-passes under `--auto`.
State `WORKTREE_PATH: <path>/run-integration` on the dispatch, and `SELF_PROVISION: worktree-addons`
when a bounded subagent carries it - the SAME two fields stages 2 and 3 and § Node Invocation
Brief Template already use, for the SAME reason
(`${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md` § Worktree-addons carve-out): without
them the capture instance loads the CATALOG addons path and every screenshot documents the principal
checkout instead of the tree the PR ships.

**The doc output must reach `run-integration` before stage 3 (mandatory - docs do not ship
otherwise).** `run-integration` is the ONLY branch the terminal land-tail squashes and pushes.
Commit the authored doc files via the `git-toolkit:git-ops` skill; when they were authored in a
worktree other than `<path>/run-integration`, bring the returned SHA onto `run-integration` with the
SAME `cherry_pick(sha, into = repos[node.repo].run_integration)` step
`${CLAUDE_PLUGIN_ROOT}/skills/run-harness/SKILL.md` § The loop performs for every node SHA, via
`git-toolkit:git-ops` - never a raw git command inline. A semantic conflict follows the SAME
§ Conflict Resolver path as any other cherry-pick.

**3 - Pre-PR lint-class gate (L0/L1 - ephemeral instance, not a SHARED-instance L2 case).** Run the
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

**4 - Terminal land-tail PR.** Only after stages 1, 2, 2b, and 3 above clear does run-harness
dispatch the `integrate` node (`SKILL.md` § `integrate` node dispatch (the land tail)): run § Squash
Tree-Identity Recipe's Existence precheck, then squash `run-integration`, push, and open ONE PR - per
REPO, and UPDATE the PR rather than open a second one if the precheck finds this repo's PR already
open. The driver evaluates § integrate readiness (`SKILL.md`) over the LIVE node set here and treats
the plan's `integrate.depends_on` as a floor, so an under-specified plan cannot open the PR ahead of
a doc / review / acceptance node. Everything after this point (CI-failure triage and fix, review/approval polling,
the merge, post-merge cleanup) is `odoo-pr-monitoring`'s, per the Terminal stage order constant
above.

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
