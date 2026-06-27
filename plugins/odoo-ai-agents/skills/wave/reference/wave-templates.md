# Wave Orchestration - Reference Templates

On-demand reference for `skills/wave/SKILL.md`. Load this file when you need the full
template text for any of the structures below. Do not load it on every invocation.

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

## Plan Artifact Full Template (>=4 WI)

Write to `.odoo-ai/wave/<slug>/plan.md` (gitignored). This is the SSOT for the wave.

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

Run after Phase 6 human-confirm merge:

Delegate to **git-operator** in one brief (op=wave-cleanup):

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
Confirm wave branches are gone (git-operator reports deletion success).

---

## Squash Tree-Identity Recipe (git-operator delegation)

All mutation steps are delegated to **git-operator**
(see `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`).

**Brief to git-operator - squash-push operation:**

```
op           : wave-squash-push
worktree     : <path>/integration
principal    : <principal-branch-name>
slug         : <slug>
commit-msg   : <conventional commit message>
steps:
  0a  fetch origin/<principal-branch-name>      # stale-base guard - MUST run first
  0b  ancestry-check: origin/<principal-branch-name> is ancestor of HEAD?
      no -> ABORT: rebase integration onto origin/<principal-branch-name>,
            re-run verify command, then retry from step 0a
  1   tag wave-backup-<slug> at HEAD            # create backup BEFORE squash
  2   reset-soft to origin/<principal-branch-name>
  3   commit with <conventional commit message>
  4a  tree-identity: diff --quiet wave-backup-<slug>
      exit 0 -> tree matches, proceed to step 5
      exit non-zero -> ABORT: restore from wave-backup-<slug>, report mismatch, do NOT push
  5   push --force-with-lease origin wave/integration-<slug>
confirmed    : yes - <human approval text from Phase 6 gate>
```

After git-operator returns, confirm tree-identity passed inline:
`git diff --quiet wave-backup-<slug>` must have exited 0 (git-operator reports this).

**Stale-base hazard**: The reset-soft operation silently squashes onto wherever the local
ref points. If commits landed on the principal AFTER integration was branched, the local
ref is stale and those commits are reverted even though the tree-identity check passes
(tree matches backup but commit graph is wrong). The Step 0a fetch + Step 0b ancestry
check (`git merge-base --is-ancestor origin/<principal-branch-name> HEAD`) is the only guard.

**Empty-tree SHA note**: When checking if a tree is completely empty (rare edge case),
the git empty-tree SHA is `4b825dc642cb6eb9a060e54bf8d69288fbee4904` (this is the SHA of
the empty tree object, not the empty string). Prefer `git diff --quiet <backup-ref>` exit
code over SHA comparison for tree-identity checks - it is the canonical method used in step
4a above. This SHA is only relevant if debugging a squash that produces an unexpected empty
commit.

**Why `git diff --quiet` not `--exit-code`**: Both work for tree comparison but `--quiet`
suppresses all output, which is what we want in the gate check. The exit code is the signal.

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

## Mode B Dispatch Loop (Pseudocode)

Full JS pseudocode for the Phase 2 rolling-window orchestration. Referenced from SKILL.md Phase 2.

```js
// Phase 2 - Mode B rolling-window dispatch + cherry-pick serialized in the orchestrating context.
const WEIGHT = { haiku: 1, sonnet: 2, opus: 4, fable: 8 };
const BUDGET = 8; // SSOT: skills/_shared/concurrency-guard.md (Mode B) - do not restate

// validate tiers up front: a typo'd/missing tier must fail the whole run at t=0,
// before any worker or worktree exists, not silently book the wrong weight
for (const wi of wis) {
  if (!WEIGHT[wi.model]) throw new Error(`WI ${wi.id}: unknown model tier '${wi.model}'`);
}

// weighted semaphore (plain JS - no per-model runtime knob). release() admits
// strictly FIFO so a heavy (fable/opus) waiter is never starved by lighter waiters.
let used = 0; const waiters = [];
const acquire = (w) => new Promise((res) => {
  const attempt = () => (used + w <= BUDGET ? ((used += w), res(), true) : false);
  if (!attempt()) waiters.push(attempt);
});
const release = (w) => { used -= w; while (waiters.length && waiters[0]()) waiters.shift(); };

// CRITICAL SECTION for cherry-pick: one in-flight at a time, in the orchestrator only.
// The promise chain serializes every cherry-pick onto integration -> no branch race.
let cpChain = Promise.resolve();
const cherryPickSerial = (fn) => (cpChain = cpChain.then(fn, fn));

// per-WI CHERRY-PICKED promise (NOT merely committed). Dependents fork from
// integration, so a dependent must wait until its deps are ON integration.
const cpResolvers = {}; const cherry_picked = {};
for (const wi of wis) cherry_picked[wi.id] = new Promise((r) => { cpResolvers[wi.id] = r; });

const runWI = async (wi) => {
  // gate on deps being CHERRY-PICKED (not merely committed in their own worktree).
  // any dep that resolved false (blocked upstream) blocks this WI too.
  const depsOk = (await Promise.all(
    (wi.depends_on || []).map((d) => cherry_picked[d] ?? Promise.resolve(true))
  )).every(Boolean);
  if (!depsOk) { cpResolvers[wi.id](false); return { id: wi.id, upstreamBlocked: true }; }

  // lazy worktree: create the dependent's worktree NOW, after the gate, so it forks
  // from an up-to-date integration that already holds the dep commits (root WIs were
  // created in Phase 1 via git-operator: branch=wave/wi-<slug>-<id>, from=wave/integration-<slug>).
  ensureWorktree(wi);   // delegate to git-operator (worktree-add)

  const w = WEIGHT[wi.model];
  await acquire(w);                       // wait for weight budget (rolling window)
  let workerResult;
  try {
    // WI worker: write + commit in its OWN worktree, return SHA(s). NO cherry-pick.
    workerResult = await agent(wiBrief(wi), {
      label: wi.id, phase: 'implement', model: wi.model, schema: WI_RESULT_SCHEMA,
    });
  } finally { release(w); }               // free weight as soon as the worker returns

  if (!ok(workerResult)) { cpResolvers[wi.id](false); return { id: wi.id, result: workerResult }; }

  // cherry-pick: serialized in the orchestrating context, topology order enforced by the dep gate above.
  await cherryPickSerial(async () => {
    for (const sha of workerResult.committed_shas) {
      cherryPick(sha);                    // delegate cherry-pick of <sha> to git-operator in the INTEGRATION worktree
      runVerify();                        // Repo Capability Card verify after each pick (Phase 3)
      // on conflict -> dispatch the Phase 3 Sonnet resolver subagent (unchanged) and re-verify
    }
  });
  cpResolvers[wi.id](true);               // unblock dependents ONLY after cherry-picked + verified
  return { id: wi.id, result: workerResult };
};

await Promise.all(wis.map(runWI));        // rolling window; deps enforced per-WI, no batch barrier
```

---

## Examples

**Example 1 - Standard 3-WI wave:**
Prompt: "Parallelize these 3 changes: add computed field to sale.order, add OWL widget, update unit tests. Land them safely without touching main."
Action: Phase 0 discovers disjoint files, selects independent topology. Gate shows ownership
map. On approve: integration branch + 3 worktrees. Dispatch the 3 Sonnet WI subagents under the
Mode B rolling window (3 x sonnet = weight 6, within BUDGET=8, so all three run at once).
Serialize each cherry-pick in the orchestrating context as its worker returns. Opus review + odoo-code-review. 1 PR.
Squash + tree-identity. Wait for human-confirm.

**Example 2 - 1-WI edge case:**
Prompt: "Do this as a wave: fix the typo in account.move description."
Action: Phase 0 sees 1 WI. Standalone-first fallback: "This is a single-file fix -
wave overhead is not needed. Run odoo-coding directly? Or confirm you want a wave."

**Example 3 - Ownership conflict detected:**
Prompt: "Parallelize WI-A (edits models.py + tests.py) and WI-B (edits models.py + views.py)."
Action: Phase 0 ownership audit finds models.py in both scopes. STOP: "models.py appears
in both WI-A and WI-B. Resolve the overlap before I can create worktrees. Options:
(a) move models.py changes to one WI, (b) split the models.py change into a WI-0 prerequisite."

**Example 4 - Squash mismatch abort:**
Prompt context: squash step on 4-WI integration branch.
Action: `git diff --quiet wave-backup-<slug>` exits 1 (tree mismatch). Abort:
"Squash tree-identity FAILED - the squashed commit does not match the pre-squash tree.
Restoring from wave-backup-<slug>. Do NOT force-push. Investigate the mismatch before
proceeding." Report the differing files.

**Example 5 - Conflict resolver path:**
WI-A and WI-B unexpectedly both touch `__init__.py` (missed in Phase 0 audit):
Cherry-pick of WI-B fails with conflict. Dispatch Sonnet resolver subagent with the conflict
diff + both WI briefs. Resolver edits the conflicting files (conflict markers removed). Wave
re-dispatches a fresh git-operator (cherry-pick --continue) to complete the cherry-pick.
Re-run verify. Continue.
