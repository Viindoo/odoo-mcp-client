# Forward-Port Pipeline - P9 to P12 (verify, migration dir, conclude, PR, cleanup)

**Contents:** P9 - P9.6 - P10 - P12 - Cleanup (P9.5 is in `references/fp-phase-briefs.md`)

All paths are under the integration worktree unless noted. `<slug>` derives from the
source/target series (`<source-series>-to-<target-series>`). Artifacts live under
`<ISOLATE_DIR>/forward-port/<slug>/` (gitignored; resolve `<SHARE_DIR>`/`<ISOLATE_DIR>` once per
`${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`; substitute the captured absolute path). Every Odoo Semantic call passes a concrete
`odoo_version=` (`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § OSM session-pin race).


---

## P9 - Verify by behavior (PER-BATCH, in integration)

Resolve odoo-bin flags for the TARGET series via `cli_help` (`odoo_version=<target>`) before
dispatching. Conventions: `docs/reference/INSTANCE-LIFECYCLE-BUILD-CONTRACT.md`,
`docs/reference/ODOO-TESTING.md`.

**DELEGATE - never a bare lease tool or `odoo-bin` recipe, and never allocate a database and port
to run the suite inline** (`${CLAUDE_PLUGIN_ROOT}/snippets/test-execution-handoff.md`). Dispatch the `odoo-instance` skill
(via the Skill tool) for every step below; never a bare `lease_acquire` / `instance_build` /
`odoo-bin` call. Everything from here to P10 is CONTENT for that dispatch brief and the
adjudication you perform on the RETURNED `instance-ops` block.

**Env-bootstrap (before the first dispatch).** Resolve the CATALOG (principal-checkout) baseline
from the declared catalog row covering this repo (`addons_path` and `python` from `catalog_locate`
per `${CLAUDE_PLUGIN_ROOT}/snippets/project-facts-resolution.md` rung 2) as a baseline only;
interpreter discovery and addons-path assembly are `odoo-instance-ops`'s job. A multi-repo stack
needs EVERY repo on disk: confirm every root in that entry's `addons_path` exists before
dispatching; a missing repo is `BLOCKED` (NEEDS_CONTEXT), not a test red.

**Worktree re-root (MANDATORY).** The catalog baseline is NEVER the addons_path this phase verifies
against. Dispatch `odoo-instance` with `WORKTREE_PATH: <path>/fp-integration`, which re-roots the
baseline onto that tree before acquiring. Do NOT hand-build the override and do NOT verify against
the catalog `ADDONS_PATH` directly. Before trusting any result below, assert the resolved addons
list contains `<path>/fp-integration/<module>/<tgt-descriptor>` for every module in this batch
(`${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md` § Addons coverage assertion) - on a
miss, `BLOCKED`.

**Install/verify the FULL transitive `depends` closure, not just the module you edited.**
Resolve the closure per module, then install/verify its breadth:

```python
module_inspect(name='account_accountant', method='dependencies', odoo_version='<target_version>')
```

Union the closures of every directly-touched module and pass that whole set as `modules` in the
dispatch below.

**Lint toolchain present BEFORE the lint gate.** Confirm `flake8 --version` and `ruff --version`
(and eslint / prettier for frontend) resolve in the verify env before relying on a green lint.

**Dispatch `odoo-instance` (via the Skill tool) - ONE ephemeral instance per BATCH, not per
commit.** First commit in the batch (fresh DB; install + test in one pass):

```
operation: run-tests
series: <target>
persist: ephemeral
RUN_ID: <this run's id>
SHARE_DIR: <the run's captured absolute SHARE path - substitute it, never re-resolve>
ISOLATE_DIR: <the run's captured absolute ISOLATE path - substitute it, never re-resolve>
WORKTREE_PATH: <path>/fp-integration   # re-root per the Worktree re-root note above
modules: <union of the touched modules' full transitive depends closure, comma-separated>
test_tags: <`/<m>` for every module in that closure, comma-joined (narrowing rule below)>
mode: fresh
GATE_ROLE: node-verify    # a per-batch verify, never the run's pre-PR lint gate
skip_auto_install: true
CONFIRM: "confirm each module in this closure emits a Loading line before reading any test count;
          report per-module install status in modules_installed and the test result in findings_path"
```

Capture the returned `instance-ops` block as this batch's `INSTANCE_HANDLE` (`db_name`,
`lease_token`, `run_id`, `addons_path`) and relay it so later batches reuse the same instance; every
build on that ONE database follows `${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md`
§ One build or export per database. **Pass `test_tags`** (`${CLAUDE_PLUGIN_ROOT}/snippets/test-scope-contract.md`):
`/<m>` for every module in the INSTALL CLOSURE this batch named, comma-joined. NEVER narrow below
that to only the edited module. Record the tag set used in `merge-log.md`.

For a SUBSEQUENT commit in the SAME batch touching only a subset, re-dispatch `odoo-instance` with
the SAME `INSTANCE_HANDLE` forwarded, `mode: reuse` (`-u` semantics) and `GATE_ROLE: node-verify`
on the changed modules only
- skip re-running the full closure. Once a module is installed in this DB, re-running its tests
MUST use `reuse` (`-u`; `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md` § Test run on an
existing database; confirm flags via `cli_help`). Full rule: `${CLAUDE_PLUGIN_ROOT}/docs/reference/ODOO-TESTING.md`.

Relay the returned `instance-ops` block (`log_path`, `findings_path`, `modules_installed`,
`failed`/`errors`/`warnings`/`skipped`) into `merge-log.md` verbatim (Hard rule 8). Reconcile
`modules_installed` against the installable scan (`[[fp-symbol-survival-check]]` section 2.5f): a
module that is `installable: False` at the target is EXPECTED to be absent from
`modules_installed` - route it to the 8c-bis lint-only lane and do NOT count its absence as a
break. A module that IS installable and absent from `modules_installed` is a real failure -
investigate via `log_path` before reading any test count.

**Recover a batch stuck mid-run.** Do NOT `pkill` an `odoo-bin` process. The batch's lease was
provisioned for THIS run, so you are its run-level owner
(`${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T1): call `lease_release` with the
batch's cached `lease_token`/`run_id` - it stops the bound process group FIRST, then drops the DB.
Re-dispatch the Step above for a clean retry.

- **Whole module green:** the target suite must be green.
- **Every FP-delta test proven:** each newly-forwarded or adapted test was proven by its node's test leg -
  the report recorded on the module's `merge-log.md` row says what it broke and how the test failed
  (`${CLAUDE_PLUGIN_ROOT}/snippets/test-sensitivity-contract.md`); a bucket-(a) commit's source test is
  instead confirmed absorbed (green on the target with the commit's own code out of play). A test with
  neither is unverified - resume the module's coder through `odoo-coding` (8b, `WORKER_AGENT_ID`) to
  produce it; never run a break of your own here.
- **Database freshness.** Never hand this handle to a P8 invocation; if a break ever ran on it,
  rebuild fresh when the break touched data files or schema.
- **Triage red:** Triage EVERY red against a clean-tip baseline before calling it a
  regression. Re-dispatch `odoo-instance` (same shape as above) against a clean checkout of
  the target tip - no `WORKTREE_PATH` override, no absorption - running the SAME closure. Red
  there too = pre-existing: record it in merge-log.md and, once its cause is proven, fix it in
  this PR per `[[fp-merge-absorption]]` § C3 (its exceptions are listed there). Green on clean /
  red only after absorption = FP-delta (fix before committing: it goes back to the module's coder
  through `odoo-coding`, 8b `WORKER_AGENT_ID`, with the P9 failure output). Never widen an assertion to hide a pre-existing failure.
- **Baseline a failed INSTALL the same way.** If a module fails to install, re-dispatch
  `odoo-instance` against clean `origin/<target-branch>` (no `WORKTREE_PATH`, no absorption).
  Fails there too = a PRE-EXISTING break in the target series, NOT FP-introduced - record it in
  `merge-log.md` and do NOT block the forward-port on it. Only an install that is green on clean
  origin/target and red after absorption is an FP-delta to fix.
- **CREATEDB role:** on any acquire refusal follow `[[fp-merge-absorption]]` § Ephemeral isolation.

Full per-batch protocol: `[[fp-merge-absorption]]`. Mark `status=verified`.

---

## P9.6 - Migration dir (C2) (PER-BATCH, after P9 is green)

Only for a module whose range forwards a `migrations/<src-series>.a.b.c/` dir; none -> skip the phase.
Resume that module's coder through `odoo-coding` (8b, `WORKER_AGENT_ID`) with `CONSTRAINTS` = C2
(`${CLAUDE_PLUGIN_ROOT}/snippets/fp-merge-absorption.md`) and the dir list. The coder decides each dir
per C2, and after a rename sweeps the migration body for source-series literals still in log strings
or version constants:

```bash
grep -rn '<src-series>' migrations/<tgt-series>/
```

Store the files it moved on the module's `merge-log.md` row (`files:`) with the per-dir outcome.

---

## P10 - Conclude the merge (self-decided, per batch) - ONE commit closes the whole range

No human confirmation (a local merge on `fp/<slug>`; P12 presents it). Before the commit, build the FULL file list:
the union of every module row's `files:` (8b, P9.6) plus the files P9.5's `odoo-i18n` result names.
Compare it with the `dirty.entries` of a `repo_facts` call on `<path>/fp-integration`: a modified or
untracked path in neither the list nor the merge's own staged set is work no step accounted for -
attribute it to its module (or remove it) before you continue. Then invoke the
`git-toolkit:git-ops` skill (via the Skill tool) ONCE:

```
op: stage these files, then conclude the merge with one commit
files: <the FULL file list above>
message: |
  fp: absorb <src-first-SHA>..<src-tip-SHA> - <one-line summary>

  <sha> <bucket x> <one-line reason>      # one body line per absorbed commit
  ...
worktree: <path>/fp-integration
```

After it returns, confirm the tree is clean: a `repo_facts` call on `<path>/fp-integration` reports
`dirty.is_dirty` false and `operation_in_progress` = `none`. A leftover path is a file the list missed - record it with the path in `merge-log.md` for P12;
never amend the merge commit.

That single commit lands the whole range; every SHA in the range is marked `done` in
`checkpoint.json`. Buckets (a)/(d) are absorbed by it too (Hard rule 7); their body line records the
bucket + reason.

**There is no P5 loop.** A single-batch run reaches P10 once, then P11. Only a human-approved
multi-batch split at the P4 plan gate returns to P5, once PER BATCH, never per commit, with the NEXT
batch's range TIP, then P6 -> P7 -> P8 -> P9 -> P10 for that whole batch. Never skip P5/P6/P7 for a
later batch.

---

## P12 - PR + review

Runs AFTER P11 (`SKILL.md` § The pipeline, P11): acceptance, then this review gate, THEN the PR opens
(`SKILL.md` Hard rule 9; `${CLAUDE_PLUGIN_ROOT}/skills/odoo-intake/references/plan-mode-schema.md` § Default tail).

Invoke the `git-toolkit:git-ops` skill (via the Skill tool) to push (resolve the origin URL from the `origin_url` of a `repo_facts` call):

```
op: push fp/<slug> to origin (NOT B)
scope: branch fp/<slug>
worktree: <path>/fp-integration
remote: origin (`origin_url` of repo_facts)
```

Run `odoo-code-review` inline (via the Skill tool, from this orchestrating context) passing
`TARGET: worktree:<path>/fp-integration` (the JOB-tier integration worktree created at P4) so it
reviews the fp integration tree, not the principal tree, for the forward-port pitfall (a forwarded
test still coupled to the source API) on the pushed branch BEFORE the PR is created (lint-class gate:
`${CLAUDE_PLUGIN_ROOT}/skills/odoo-intake/references/plan-mode-schema.md` § Default tail). OPTIONAL
for a trivial port (docstring/string/comment-only buckets); **MANDATORY whenever the batch grafts a
new engine or mechanism** (a shared report engine, a group-by/total/drill computation, an
export/print path, a wizard, any multi-path component) - a clean merge of one path proves nothing
about the others. A mandatory review:

1. **Enumerate EVERY code path of the grafted mechanism and confirm each was adapted** (for a report
   or compute engine: total, sub-total/group-by, expand/collapse, drill-down, export (xlsx/csv),
   print (PDF/QWeb)). It is not done until every enumerated path is accounted for (adapted, or
   explicitly N/A with a reason).
2. **Attribute every finding to the FP diff before rating it.** Invoke the `git-toolkit:git-ops` skill
   (via the Skill tool) for the diff of `<file>` that shows only what the FP added to it (the changes
   on `fp/<slug>` since it left `origin/<target-branch>`). A finding on a line this port changed is
   in scope (fix now); a finding on a line NOT in this diff is pre-existing - rate it separately
   and handle it per C3 below. Rate findings only after this attribution.

**Acceptance hand-off.** The `odoo-code-review` dispatch may carry a `next: odoo-acceptance` entry in
its own Continuation Contract (Phase A.5 emits it whenever `render_check_set` reaches beyond the
reviewed modules). Do NOT act on it - P11 already ran acceptance for this batch.

**Per pre-existing finding, apply C3** (`[[fp-merge-absorption]]` § C3): a proven defect in a
module this port touches is fixed in this PR, in that module's commit, with a guarding test. When
the same defect exists at the source series, also open a source-series issue (git-ops when a
source remote resolves from `repo_facts` `remotes`, else record it in `merge-log.md` and the
Continuation Contract). Record `<sha> | C3 | fixed in <module commit> | <evidence>`.

**Field-existence question:** query that field directly instead of re-dumping the model:

```python
entity_lookup(kind='field', model='account.move', field='payment_state', odoo_version='<target_version>')
```

**installable:False modules get a LINT-ONLY review.** For any module that is
`installable: False` at the target (8c-bis lane), the reviewer rates ONLY syntax / lint findings - raise no business-logic findings against it; mark such findings out-of-scope.

Only once the review above is addressed, invoke the `git-toolkit:git-ops` skill (via the Skill
tool) to create the PR:

```
op: create PR
base: <target-branch>
head: fp/<slug>
title: "..."
body: "..."
remote: origin (`origin_url` of repo_facts)
```

**Cross-check every static-review bot comment on the PR (post-PR, informational only).** Once the PR
is open and CI has run, read the bot (CI linter / review bot) comments and resolve or consciously
waive each; this never gates PR creation.

NEVER squash. B stays LOCKED - the PR adds only the merge commits. Present the PR URL, the review findings, and the P11 acceptance verdict
together, and wait for the human to merge.

---

## Cleanup (after human merge)

Invoke the `git-toolkit:git-ops` skill (via the Skill tool) to remove the integration worktree and delete the integration branch.

Requests (each `confirmed: yes - forward-port is merged`):

- remove the integration worktree `<path>/fp-integration`;
- delete the integration branch `fp/<slug>`;
- confirm that no dangling `fp/<slug>-*` child worktrees remain (git-ops reports them in its reply).

Confirm no instance of this run is still leased: call `mcp__plugin_odoo-ai-agents_odoo-local__lease_list`
with scope `run` and this run's `run_id`, and `lease_release` any lease the P9 verify lease left
behind - you are its run-level owner (`${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T1).

Leave `<ISOLATE_DIR>/forward-port/<slug>/` for the next run's resume.

---
