---
name: odoo-forward-port
argument-hint: "[from-series] [to-series] [module/range]"
description: >-
  This skill orchestrates a continuous or one-shot Odoo forward-port - porting fixes
  and features from a lower-series source repo or branch up to a higher-series target -
  as an ordered agentic pipeline that forwards INTENT, not code text. It runs a parallel
  read-only intent sweep, a 4-outcome classification, an installable probe, a conditional
  design route-out, a Plan Mode gate, an SHA-preserving git merge, a symbol-survival check
  that catches autosilent field breaks, test-first adapt, per-batch verify-by-behavior, a
  human-confirm gate, and a PR. Invoked when asked to
  "forward-port", "port commits to a
  newer Odoo version", "merge a fix forward", "continuous forward-port", "one-shot
  back-of-port", or in Vietnamese "forward-port Odoo", "port fix lên phiên bản mới",
  "đẩy commit lên series cao", "forward-port liên tục". Do NOT use to write one isolated
  change (use odoo-coding), to diff two versions only (use odoo-version-diff), or to
  review a PR (use odoo-code-review)
model: opus
---

## Role

Forward-port conductor: own the git topology, the per-commit SEMANTIC pipeline, and the subagent
lifecycle. Decide which commit at which model tier, which outcome bucket, when to gate.
**The semantic work is per-commit; the git operation is NOT.** Intent, bucket, and adapt are
reasoned per source commit; the range is absorbed by ONE merge closed by ONE merge commit.
Delegate leaf tasks to specialist agents and read-only delegates: intent extraction, code adapt,
test forwarding, AND every gate P6 / P6-TEST / P7 runs - the conflict-marker scan and range file
list, the OSM symbol grounding, the static lint lanes, and the test-collection gate (WHO takes
which: `[[fp-symbol-survival-check]]` - Who runs this check). You record verdicts and finding
lines; you do not produce them.
Core invariant: a forward-port is a SEMANTIC translation, not a git operation. A green
merge + lint + install does NOT prove the feature works on the target platform; only an
intent test that goes red-then-green, plus a symbol-survival check, proves it. SHA is sacred -
continuous forward-port absorbs the source RANGE into the target DAG with a single merge of its
tip, so every source SHA is preserved and the merge-base advances in one step; never squash,
never cherry-pick, and never merge the range one commit at a time.

## Out of Scope

- One isolated change with no source commit to port -> use `odoo-coding`
- A version-to-version API/feature delta only (no merge, no adapt) -> use `odoo-version-diff`
- Reviewing or auditing an existing PR or diff -> use `odoo-code-review`
- A pre-upgrade deprecation sweep of one codebase -> use `odoo-deprecation-audit`
- Same-series single-commit replay (no version jump) -> use `odoo-git-rebase`
- Whole-cluster upgrade to a higher series (not one commit) -> use `odoo-modules-upgrade`
- A STANDALONE design request with no commits to port -> use `odoo-solution-design` directly.
  A bucket-(c) commit INSIDE a forward-port run that requires non-trivial design is handled by
  the P3 conditional route-out (which delegates to odoo-solution-design and returns) - that is
  IN scope of this skill, not a hand-off boundary
- Parallelizing N disjoint WIs with cherry-pick + squash semantics -> use `odoo-planning` (the
  USER-facing choice; it plans the node execution for `run-harness`, which lands each node by
  cherry-pick - whereas forward-port keeps SHA by merge: a different git contract)

> **Route in (Odoo forward-port lands HERE, not bare git-ops):** an Odoo forward-port routes to
> this skill - it wraps git-toolkit's generic `git-ops` front door with the Odoo intent-forwarding
> pipeline (intent sweep, symbol-survival, verify-by-behavior). This Odoo skill DRIVES the pipeline
> and invokes `git-ops` (via the Skill tool) for each git step.

## Invocation

Fires three ways - all reach the same pipeline: the `/odoo-forward-port` slash command,
a natural-language description match, or a Skill-tool call from an orchestrator (e.g.
`odoo-intake`).

### Arguments

```
/odoo-forward-port <source-ref> <target-branch> [--scope <mod1,mod2>] [--since <sha>] [--one-shot]
```

| Argument | Required | Description |
|---|---|---|
| `<source-ref>` | yes | Source branch or commit range (e.g. `origin/17.0`, `v17-fixes`) |
| `<target-branch>` | yes | Target branch (e.g. `origin/18.0`, `18.0-fp-batch-01`) |
| `--scope <modules>` | no | Comma-separated module list; default = all modified modules in range |
| `--since <sha>` | no | Only commits after this SHA (continuous or incremental FP) |
| `--one-shot` | no | One-time port of a frozen source (or a deliberate sub-range) via ONE staged cherry-pick of the whole range - does NOT preserve SHA. Default: merge mode |

Parsed from `$ARGUMENTS` in P0 (missing `source-ref`/`target-branch` -> ask once, one message,
before any read or git op).

### When to use

- **1-5 commits** - intent-extract + classify + Plan Mode gate + serial adapt + one merge commit.
- **6+ commits** - full plan (commit topology, per-commit tier, buckets) in Plan Mode, recorded
  to `plan.md`. Still ONE merge and ONE merge commit by default; a human may split the run into
  several gated batches at the plan gate, and then each BATCH gets one merge of its own range tip
  - the commit count never sets the merge count.
- **Continuous mode (default)** - recurring; source keeps evolving; every SHA in the range
  preserved so the merge-base advances to the range tip and past conflicts are never re-resolved.

For an upgrade plan (risk + deprecation + diff) instead of an actual port, use `/odoo-plan-upgrade`.

## Hard rules

1. **Target-branch-lock** - NEVER checkout, switch, commit, merge, rebase, reset, or push the
   target branch B directly. Another session may hold B's working tree. All integration happens
   in a dedicated integration worktree branched FROM B (the JOB tier below). Read-only ops on
   B are allowed. Delegate every mutation on the integration worktree to git-toolkit via the
   `git-ops` skill (`${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`). The integration-loop saga (record the
   pre-loop SHA, checkpoint after each integrated commit, clean-abort or resume on failure - never
   leave a half-built integration branch) follows the shared SSOT
   `${CLAUDE_PLUGIN_ROOT}/skills/_shared/integration-loop.md`.

2. **ONE merge, ONE merge commit - the range is the git unit, never the commit.** Continuous
   forward-port opens a SINGLE no-ff no-commit merge of the range's TIP SHA (delegated to
   git-toolkit via `git-ops`; see `[[fp-merge-absorption]]`) and closes it with a SINGLE merge
   commit - exactly the shape an ordinary branch-level merge produces. Every commit in the range
   becomes an ancestor of that merge commit, so every source SHA is preserved and the merge-base
   advances to the tip in one step. **Two shapes are BANNED, both unconditionally:**
   (i) **merging (or committing) one source commit at a time** - it mints N merge commits for one
   logical forward-port and re-resolves every shared hunk once per commit instead of once per run;
   (ii) **cherry-pick per commit** - it mints a fresh SHA, leaves the merge-base behind, and forces
   re-resolving the same conflict on every future run, permanently. Splitting the run into gated
   BATCHES does not reinstate either shape: a batch merges its own range TIP once, so batches -
   never commits - bound the merge-commit count. One-shot mode is the only cherry-pick path, and it
   too is ONE staged cherry-pick of the WHOLE range closed by ONE commit. Full protocol:
   `[[fp-merge-absorption]]`.

3. **Intent before code** - the unit being forwarded is the behavior/purpose, not the diff.
   P1 extracts intent (read-only); P8 re-implements that intent on the target
   idiom. Never paste a source diff hunk forward and call it done. SSOT: `[[fp-intent-4outcome]]`.

4. **Verify by behavior, not by text** - success = the forwarded INTENT test goes RED then
   GREEN on the target, plus confirm-by-toggle (disable the adapt code -> the FP-delta test
   must go red again). A clean merge is necessary, never sufficient.

5. **Symbol-survival before adapt** - after every merge, run the P6 symbol-survival
   check on BOTH conflicted files and merge-clean-but-source-touched files. A source line
   referencing a symbol removed/renamed at the target produces NO conflict marker but breaks
   at runtime. Resolve every broken symbol into a bucket before adapt starts. SSOT:
   `[[fp-symbol-survival-check]]`.

6. **Human-confirm merge** - STOP at the P10 gate. The P4 plan gate runs the shared Plan-Mode gate
   (`${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md` § Plan-Mode enter/exit; user approves
   in the Plan Mode UI). No automated commit of the integration into B, no auto-merge of the PR.
   Present and wait.

7. **Outcome a/d are still ABSORBED** - buckets (a) already-satisfied and (d) no-longer-relevant
   produce no adapt diff, but their SHAs stay inside the merged range: a bucket is a statement
   about adapt work, never about git topology. NEVER narrow or fragment the merge range to exclude
   an (a)/(d) commit - that leaves the merge-base behind it and re-encounters it tomorrow. Record
   the bucket + reason on that commit's `merge-log.md` row and in the single merge commit's message
   body, so reviewers see why those SHAs carry no diff. SSOT: `[[fp-merge-absorption]]`.

8. **Verify subagent claims** - never trust a leaf's self-report of GREEN. Run the verify
   command yourself per batch (P9) before the P10 gate.

9. **Acceptance is mandatory (narrow escape only)** - P11 dispatches `odoo-acceptance` ONCE for
   the whole forward-ported batch BEFORE P12 pushes the branch, opens the PR, or runs its
   lint-class review gate - the position the **Terminal stage order** constant assigns it
   (`${CLAUDE_PLUGIN_ROOT}/skills/run-harness/references/run-integration.md` § Pre-PR tail is that
   constant's ONE owner: read the order there, never restate it here),
   mirroring the rigor a new module build gets. This is NOT opt-in: skip it only when the touched
   module set is a true dependency leaf with zero in-repo dependents and no behavioral surface,
   and record that proof - never skip silently. The forward-port is not DONE without an ACCEPTED
   verdict or a recorded narrow-escape.

10. **i18n reconcile is mandatory (narrow escape only)** - 8e COMPUTES the two conditions and P9.5
    DISPATCHES `odoo-i18n` per batch, after the P9 instance exists and before the P10 gate. This is NOT
    opt-in: skip only via an enumerated escape recorded on the module's `merge-log.md` row
    (`${CLAUDE_PLUGIN_ROOT}/snippets/i18n-mandate-contract.md`). The forward-port is not DONE without an
    i18n result or a recorded escape for every module whose row says `i18n_due: yes`.

11. **Descriptor filename resolves ONCE, per side** - a module's descriptor is `__manifest__.py`,
    or `__openerp__.py` on v8.0-v9.0 (SSOT:
    `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-era-boundaries.md` row 6). At P0, resolve it once from each
    side's series and record it in the run's working state: `<tgt-descriptor>` for `target_ref`,
    `<src-descriptor>` for `source_ref` - they DIFFER on a v9.0 -> v10.0 port. Reuse those literals
    for every descriptor read, path, and assertion below: `installable`, `depends`, `version`,
    `manifest_path`, `history_dump_path`, and the P9 addons-coverage assertion. An absent
    `__manifest__.py` on a v8.0-v9.0 side means the WRONG FILENAME was opened - it is never
    evidence that the module is missing from that ref, and a failed descriptor read is never a
    reason to drop the module or to report a guessed `installable` / `depends` / `demo` value.

## Git topology - two tiers of worktree

Forward-port never touches B directly and parallelizes through worktree isolation.

**JOB tier (always):** create `fp/<slug>` integration branch via dedicated worktree (delegated
to git-toolkit via `git-ops`) from B's HEAD. All absorption, adapt, and verify happen inside this integration
worktree. The target branch B is read-only for the whole run; the only thing that ever lands on
B is the final PR merge - P11 acceptance and P12's own review both clear before P12 opens it -
human-confirmed.

**WORK tier - NOT used by P8 adapt (read before assuming otherwise).** A per-module child
worktree (branched off integration, converged back via merge, then removed) is the generic
WORK-tier pattern a fanned-out phase uses for genuinely PARALLEL, filesystem-isolated writers -
each independent writer forks its own child worktree off the integration branch so concurrent
writes never race on the same git index, then lands back by cherry-pick (the same shape
`run-harness` applies to every source-writing plan node's worktree, per
`${CLAUDE_PLUGIN_ROOT}/skills/run-harness/SKILL.md` § The loop). **P8 adapt never qualifies for it,
for two INDEPENDENT reasons that both hold on every P8 call this pipeline makes, in EITHER mode:**

1. **No parallelism to isolate.** P8 is explicitly SERIAL per-module across the batch's whole
   absorbed range (§ P8 header below). Child-worktree filesystem isolation exists to stop
   concurrent writers racing on the same git index (`index.lock`); a serial writer has no
   concurrent sibling to race against, so there is nothing to isolate FROM.
2. **The open-merge window (§ P8 below) never clears before P8 runs.** P5 opens the run's SINGLE
   merge of the range tip (`--no-commit`) immediately before P6/P7/P8, and P10 is the ONLY step
   that commits it - AFTER P8 and P9 finish. So `MERGE_HEAD` (continuous mode) or
   `CHERRY_PICK_HEAD` (one-shot mode) is live in the integration worktree for the ENTIRE P6-P9
   span of the batch, in both modes - P8 never runs against an already-committed integration HEAD.
   Converging a child worktree back is itself a second merge into that SAME worktree, which git
   rejects while the window is open (error: `MERGE_HEAD exists`) - and P9 needs the adapted code
   already sitting IN the integration working tree before it can verify (P9 re-roots onto
   `<path>/fp-integration` - § P9 Worktree re-root), which is itself gated on P8 finishing, before
   P10 ever commits. No mode can satisfy this circular precondition.

**Conclusion (checkable, unconditional): P8 8a/8b always adapt DIRECTLY in the integration
worktree - never a per-module child worktree, in either mode.** § P8 below gives the resulting
brief fields: a single, run-long `Worktree path` naming the integration worktree itself (never a
per-module or per-commit "Child worktree path" that would need re-minting - there is nothing to
re-mint). Both modes behave identically here, because both open exactly ONE window per batch and
hold it across the batch's whole P6-P9 span: continuous keeps `MERGE_HEAD` live, one-shot keeps
`CHERRY_PICK_HEAD` live. Child-worktree isolation would only become reachable once that
merge/cherry-pick is committed, which is the LAST thing either mode does - never something P8
itself can ever observe.

The only serialized point is P10 writing the batch's single merge commit. There is no second
agent-dispatch level here - JOB tier is the only worktree tier this phase (or any phase in this
skill) uses.

## The pipeline

**Dispatch-brief skeleton.** When composing the dispatch prompt for any specialist agent
dispatched across the phases below (`odoo-intent-extractor`, `odoo-diff-comparator`,
`odoo-installable-prober`, `odoo-test-writer`, etc.), fill the caller-side skeleton in
`${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md` (read it by path) plus the target agent's family
delta; never inline that file verbatim into a hard-leaf brief. This pipeline dispatches leaves
(P1/P8a/P8b etc.) that run inside the JOB-tier integration worktree rather than the principal -
P8a/P8b never use a WORK-tier child worktree (§ Git topology above) - the
general rule for resolving/threading `<SHARE_DIR>`/`<ISOLATE_DIR>` across such a target-vs-principal
split is `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md` §Cross-worktree dispatch; this
pipeline's resolve-once-and-pass-the-slug pattern (below, and at each `<ISOLATE_DIR>/forward-port/
<slug>/...` reference) already follows it.

Run phases in order. Intent + classify + design + the Plan Mode gate ALL precede the merge -
the plan is approved against the REAL triaged tiers and REAL buckets, never bucket-guesses.
Concurrency for any fan-out follows
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` (Mode B, model-weighted budget 8) -
do not restate the weight numbers here. Full per-phase dispatch briefs, git commands, and
worklog templates: `references/fp-phase-detail.md`.

**Orphan sweep (do this every run, BEFORE P0 below).** `forward-port/<slug>/` evidence
(checkpoint.json, commit/intent dumps) is never deleted by anything today, so it leaks one
directory per run forever:

`find <ISOLATE_DIR>/forward-port/ -mindepth 1 -maxdepth 1 -type d -mmin +43200 -exec rm -rf {} +`

(any sibling `<slug>/` dir untouched for over 30 days is presumed consumed). Full rule + bound rationale:
`${CLAUDE_PLUGIN_ROOT}/snippets/visual-evidence-lifecycle-contract.md` Clause 3. Enforcer: whoever
executes `odoo-forward-port` next, unconditionally, every run.

**P0 - Recon & triage [read-only, NO stop].** Parse `$ARGUMENTS` (`source-ref` / `target-branch` /
`--scope` / `--since` / `--one-shot`); if `source-ref` or `target-branch` is missing, ask once in a
single brief message before any read or git op. Read any existing worklog
(`${CLAUDE_PLUGIN_ROOT}/snippets/worklog-contract.md`) and `checkpoint.json` (resume per the
Checkpoint section: skip ONLY `status=done`; do NOT re-run design for a `status=designed` commit -
resume it at the P4 plan gate with its recorded `design_doc`; a `status=extracted` commit resumes
at P2; a `status=adapted` commit resumes at P9). Invoke the `git-toolkit:git-ops` skill (via the
Skill tool) to enumerate commits (range `<merge-base>..<source-ref>`, --no-merges; read-only, no
worktree or branch yet); apply `--scope` / `--since` filters to the returned list. Map each
`--scope` module name to its directory path before requesting git-ops to filter by path (module `l10n_vn` ->
`l10n_vn/`; resolve via manifest location, may be at repo root or under an addons subdir).

**Record the range ENDPOINTS, not just the list.** From the filtered, chronologically ordered
list, record `<src-first-SHA>` (oldest) and `<src-tip-SHA>` (newest) in the run's working state.
These two are what P5 absorbs the whole range with in ONE operation (Hard rule 2) and what the P10
commit message spans; every later phase reads them rather than re-deriving a range. A run whose
filters leave the list EMPTY has nothing to absorb - report `DONE` (nothing to forward) and stop,
never open a merge window on an empty range.

**Group by MODULE first, then by commit within that module (R2a - comparison order).** A flat
commit list alone has no whole picture: two commits touching the same module's same file, or a
later commit reverting an earlier one, are invisible to a purely per-commit read. Invoke the
`git-toolkit:git-ops` skill (via the Skill tool; read-only, no worktree) to list touched files
per commit (`--name-only`) for every commit in the range - reusing the SAME per-commit file-list
mechanism P6/P7 already use for a different purpose - and map each touched path to its owning
module (same resolution rule as `--scope` above). Build
`module -> [ordered sha list]` (chronological order, oldest first); a commit touching 3 modules
appears in each of the 3 modules' lists (a shared reference to the same commit, never duplicated
on disk). This map, not the flat commit list, is what P1 dispatches over and what Table 1 (EXTRACT
tier) resolves against below.

TRIAGE each MODULE's commit bundle to an EXTRACT model tier INLINE (`git show --stat` per commit in
the bundle + one `find_override_point` probe when override depth matters - the orchestrator triages
the tier itself; never dispatch an agent to decide a dispatch). This is recon only:
no approval gate, no worktree, no branch yet - the plan gate is P4, after intent + classify +
design. Triage tier table (now module-bundle-scoped, with the R2d opus human-confirm gate):
`references/fp-triage-table.md`.

**P1 - Intent extract [PARALLEL, READ-ONLY, MODULE-SCOPED].** Runs BEFORE the plan gate so the plan is built
on extracted intent, not a guess. This is the only true parallel speed-up - and it is honored
fully, ONE PARALLEL UNIT PER MODULE (never per commit). Pre-step: invoke the
`git-toolkit:git-ops` skill (via the Skill tool; read-only, no worktree)
in a single batch pass to write per-commit dump files - for each commit in the range, a full-patch
commit dump (message + diff) written to `<ISOLATE_DIR>/forward-port/<slug>/commits/<sha>.dump`
(resolve `<SHARE_DIR>`/`<ISOLATE_DIR>` once per `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`;
substitute the captured absolute path - never write the placeholder or a bare `.odoo-ai/` into a
Read/Write/Edit); collect the `{ <sha>: <abs-path> }` map. Include `repo: <main-checkout-root>` in the git-ops dispatch for cross-repo ports.

**BAN (R2b, checkable): at most ONE `odoo-intent-extractor` instance per module across the ENTIRE
run.** Dispatch by walking the P0 `module -> [ordered sha list]` map, ONE agent launch per module
- never one launch per commit. Each extractor brief MUST include `commit_dump_paths: { <sha>:
<path>, ... }` (the module's full ordered map from the P0 pre-step, oldest first; the extractor
mandates this field, or the single-SHA `commit_dump_path` only for the narrow re-check/audit uses
documented on the agent itself, and never runs git itself). A second `odoo-intent-extractor`
instance for a module ALREADY dispatched this run, WHILE the first is still live or has already
completed successfully, is a pipeline defect, never a valid retry - the correct retry for a failed
or incomplete module pass under CHP Tier-A is a resume of the SAME instance by the id its own launch
returned, never a fresh dispatch.
**Tier-C retry (no recorded id, or it no longer resolves -
`${CLAUDE_PLUGIN_ROOT}/snippets/context-handoff-protocol.md` § Tier A):** a
Tier-A resume is impossible, so the legal retry is a SUPERSEDING dispatch, never a second
CONCURRENT one. Confirm the failed/incomplete instance's turn has fully ended (never dispatch a
replacement while it might still be running), then launch exactly ONE replacement
`general-purpose` worker carrying the module's FULL, UNCHANGED `commit_dump_paths` plus `PRIOR
ATTEMPT: <what the failed pass returned or omitted>`. The replacement is authoritative for the
whole module bundle; its output supersedes any partial per-module intent record (§ P1 write path
below) the failed instance left behind. R2b's cap bounds the number of SIMULTANEOUSLY
live-or-authoritative workers per module to exactly one, not the lifetime dispatch count across
retries - a sequential supersession after a confirmed failure satisfies the cap exactly as a
Tier-A resume would; a second instance dispatched while the first could still be running would
not.
Dispatch each module's single instance using CHP Tier-B `subagent_type:
"fork"` (see `${CLAUDE_PLUGIN_ROOT}/snippets/context-handoff-protocol.md` - Tier B), with the
module's triaged `model` override (Table 1, resolved per module bundle - see § Model triage), up
to the Mode B budget (rolling window beyond it; the budget counts MODULES in flight, not commits).
A fork worker inherits the parent's full context (slug, source-ref, target-branch, OSM version pin,
profile) and shares the parent's prompt cache, eliminating per-worker re-grounding cost. No
worktree children needed - extraction is read-only; Tier B applies unconditionally here.
Fallback (Tier C): if `subagent_type: "fork"` is unavailable, dispatch a fresh `general-purpose`
spawn with an explicit brief (current behavior) - the worklog is always written regardless of tier.

**Write path is PER-MODULE NAMESPACED (closes the shared-commit write race - B2).** R2a's module
map and R2b's per-module cap together mean a commit shared between modules A and B is
INTENTIONALLY dispatched to BOTH modules' single extractor instances (each module's full ordered
sha list includes it) - so two independent, concurrently-running instances legitimately process
the identical SHA. Without a namespace, both would target the SAME
`intents/<sha>.md` path with no owner or merge rule - a write race. Set the P1 dispatch brief's
`SLUG` field to `<slug>/<module>` (the run `<slug>` plus this module's own name), never the bare
run `<slug>`, for EVERY module's extractor dispatch (full brief:
`references/fp-phase-detail.md` P1). The extractor's own write-path template
(`agents/odoo-intent-extractor.md` Step 3 - `<ISOLATE_DIR>/forward-port/<slug>/intents/<sha>.md`,
substituted verbatim from the brief's `SLUG` field) then resolves PER MODULE with no change needed
to that agent: module A's instance writes `<ISOLATE_DIR>/forward-port/<run-slug>/A/intents/<sha>.md`;
module B's instance writes `.../B/intents/<sha>.md` for the SAME sha - two distinct files, each
module's own perspective on the commit, never a last-write-wins collision. Each worker still writes
one record PER COMMIT in its module bundle, under its own module's namespace (the why + behavioral
contract + OSM-grounded symbols, never the diff) - output granularity stays per-SHA even though
dispatch granularity is per-module, so P2/P3/`plan.md` need no change beyond the path shape above.
Aggregate every returned summary (one per commit, across every module's single dispatch - each
summary's own `intent_file` field already reflects the module-scoped path the extractor actually
wrote to, so a caller reads THAT returned path rather than reconstructing one from the bare run
`<slug>`) into the P2 classify queue.

**P2 - Classify + installable-probe [module-first order, per-commit bucket, OSM].** Walk modules in
the SAME order P0/P1 established (the `module -> [ordered sha list]` map), and within each module
walk its commits in that module's own order (R2a). For each commit, ground its symbols
against the TARGET version (`set_active_version` once, then `api_version_diff` + `model_inspect`)
and assign exactly one bucket a/b/c/d - the bucket decision itself stays per-commit (a commit's
outcome can differ from its module-mates), only the WALK ORDER changes. SSOT: `[[fp-intent-4outcome]]`. Append one row per commit to
`merge-log.md`. `odoo-version-diff` in forward-port mode can supply the per-symbol bucket
suggestion. Every Odoo Semantic call carries `odoo_version=` - never omit it. Once buckets are
known, apply the **bucket-(c) upgrade-scale gate** to each bucket-(c) cluster: estimate its size
and, if it is an upgrade-scale re-implement rather than a mechanical port, RECORD the
`upgrade-scale` flag on that cluster now (`## Model triage`). Do NOT STOP at P2 - the defer-or-do
choice is PRESENTED to the user at the P4 plan gate, where the recorded flag becomes a
defer-or-do line in the plan. A `(b) do now` cluster that ALSO meets the P3 non-trivial criterion
proceeds to P3 design before P4 (the upgrade-scale gate decides WHETHER to proceed; P3 decides
HOW to design it).

In the same phase, resolve each touched module's `installable` status from the TARGET CLEAN-TIP
`<tgt-descriptor>` (Hard rule 11) - the state of the target branch BEFORE the merge, never
post-merge. Invoke the
`git-toolkit:git-ops` skill (read-only) to write that file, then read it: an absent key means
installable (Odoo convention), an absent FILE - `<tgt-descriptor>` being the name that side actually
uses - means the module is not on the clean tip. **Produce
`manifest_path` for EVERY touched module, unconditionally** - it is the prober's required input, and
the prober is a `role: leaf` that cannot fetch it. DISPATCH the read-only sonnet leaf
`odoo-installable-prober` only when the SOURCE HISTORY must ALSO be read to disambiguate category 3 -
the module's manifest was NOT touched by the forwarded commit range yet its target state is unclear. Do NOT
blanket-dispatch: for categories 1-2 the orchestrator's own clean-tip read is sufficient and a probe
adds only the history pass.

Pre-step (now unconditional, for EVERY touched module - not only before a prober dispatch):
invoke the `git-toolkit:git-ops` skill (via the Skill tool; read-only) to write two files - the
clean-tip manifest (`<module>/<tgt-descriptor>`
at `target_ref`) to `manifest_path = <ISOLATE_DIR>/forward-port/<slug>/installable/<module>/manifest.py`,
and the patched manifest history (log-with-patch of manifest modifications against `source_ref`) to
`history_dump_path = <ISOLATE_DIR>/forward-port/<slug>/installable/<module>/history.diff`. Include
`repo: <main-checkout-root>` in the git-ops dispatch for cross-repo ports. Dispatcher inputs
(canonical contract, pass exactly, when the prober IS dispatched for category-3 disambiguation):
`{ module, repo_root, source_ref, target_ref, target_version, manifest_path, history_dump_path }`.
`repo_root` is the MAIN checkout root where git runs - the integration worktree does NOT exist at
P2 (it is created at P4); never reference it here. `source_ref` / `target_ref` are the source /
target git refs. `manifest_path` / `history_dump_path` are absolute paths to the surveyor-written
files (see pre-step above); the prober mandates both, never runs git itself, and BLOCKs if
`manifest_path` is missing.
Whether resolved directly (categories 1-2) or via the prober (category 3), record
`installable_false=yes|no` as the module's OWN row in `merge-log.md`, keyed by module, distinct
from the per-commit intent/bucket/reason/evidence rows - this is the ONE field any later phase
reads for a module's installable state; no other field name is persisted for it. Keep the
installable:False short-circuit (`## Model triage`) and its lint-only lane unchanged. Do not
restate the rule here - SSOT: `[[fp-installable-false]]`.

**P3 - Design [conditional route-out].** When a bucket-(c) "do now" commit touches a NON-TRIVIAL
module (reuse the non-trivial criterion from `skills/odoo-solution-design/SKILL.md` § When to
invoke - do NOT invent a third definition), route OUT to `odoo-solution-design` instead of
adapting blind. A deferred or `installable:False` module needs no design - skip it. Mechanism:
emit the Continuation Contract and YIELD - forward-port only EMITS the next hop; the run-harness
advances it. The payload is `next: odoo-solution-design` with `return_to: odoo-forward-port` and
the rest of the `inputs` block printed in `references/fp-phase-detail.md` P3, which is that block's
SSOT - read it there and match it exactly, field for field, including `design_proposals`. The field
list is not restated here.
`odoo-solution-design` under `return_to` runs its own design + design-approval gate, then emits
`next: odoo-forward-port` with `design_doc`; it does NOT enter a code Plan Mode and does NOT
dispatch a coder. On re-entry, read `design_doc` from the returned contract's `inputs`, record it
against the commit, set checkpoint `status=designed`, and proceed to the P4 plan gate with the
design linked - do not re-run design. If `design_doc` is ABSENT from the returned inputs (design
crashed before producing it), set the commit back to `status=extracted` and re-enter P3 next run
rather than advancing to P4 with no design. SSOT for the full contract:
`references/fp-phase-detail.md` P3.

**P4 - Plan gate [Plan Mode].** This is where the user approves - AFTER intent + classify +
design, so the plan carries the REAL triaged tiers and REAL buckets, not guesses. Forward-port
runs from the MAIN context, so it MAY drive Plan Mode (a subagent cannot). The enter/exit
mechanics are the SHARED SSOT `${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md` § Plan-Mode
enter/exit + plan_mode_active - forward-port REUSES them for its own approval gate rather than
defining its own: `EnterPlanMode` iff `plan_mode_active` is absent/false (skip iff a caller already
opened Plan Mode), present the plan, `ExitPlanMode` on approve so the user approves in the Plan Mode
UI. The plan CONTENT is forward-port-specific and stays authored here - it is NOT routed through
`odoo-planning`, and it is MODULE-FIRST (R2a - the whole picture the flat commit list cannot give):
module topology (each module's own ordered commit list, from the P0 map); per-module EXTRACT tier
[the real triaged tier, gated per § Model triage when it resolves to opus]; per-commit bucket [the
real classification] and ADAPT tier within that module; installable routing per module; design-doc
link for any commit P3 designed; and the ABSORPTION topology - how many batches, each batch's
`<src-first-SHA>..<src-tip-SHA>` range, and therefore how many merge commits the run will produce. State
that number explicitly: it is the human's ONLY chance to choose a multi-batch split, the default is
ONE batch = ONE merge commit for the whole range, and it is NEVER derived from the commit count
(Hard rule 2). Red flags: a text-gate "approve" is NOT Plan Mode
approval - they are two separate steps; `EnterPlanMode` MUST come before any branch, worktree, or
file touch.

After Plan Mode approval, invoke the `git-toolkit:git-ops` skill (via the Skill tool) to create the
JOB-tier integration worktree branched from B (Hard rule 1; dispatch contract: `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`).
Supply the branch name `fp/<slug>`, path `<path>/fp-integration`, and base `<target-branch>` in the
brief. No branch is created before this point - everything up to and including the plan gate is read-only.

THEN write `<ISOLATE_DIR>/forward-port/<slug>/plan.md` (module-first: one block per module carrying
its EXTRACT tier + its ordered commits, each with bucket + ADAPT tier + installable routing +
design-doc link + merge batch) as the resume RECORD - the SSOT-of-record
that later phases and the checkpoint/continuation read. plan.md is now a RECORD, not the gate;
the gate is Plan Mode above. plan.md template: `references/fp-phase-detail.md` P4.

**P5 - Merge --no-commit [critical section, in integration; ABSORB-ALL - runs ONCE per batch].**
Invoke the `git-toolkit:git-ops` skill (via the Skill tool) ONCE for the whole batch, absorbing
its ENTIRE commit range in one operation. Continuous: no-ff no-commit merge of `<src-tip-SHA>`
(the batch's LAST/newest source commit - absorbing every earlier commit in the range as an
ancestor). One-shot: no-commit cherry-pick of the WHOLE range `<src-first-SHA>^..<src-tip-SHA>` in one
staged sequencer run. **Never iterate P5 per source commit in either mode** - that is Hard rule 2's
banned shape (N merge commits, or N fresh SHAs, for one logical forward-port). For semantic
conflicts, use the stateless-resume recipe in
`${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`. Only one merge in flight at a time
(shared git index). Do NOT commit yet - the working tree is now the absorption zone for the whole
range (P6 -> P8 -> P9 all happen before the single commit). SSOT: `[[fp-merge-absorption]]`.

**P6 - Symbol-survival check [MUST].** Before any adapt, every source-side symbol in conflicted
AND merge-clean-but-source-touched files is OSM-grounded against the target surface - by a
DISPATCHED read-only delegate, never in this context; you record the verdict and the finding lines
only (WHO runs it: `[[fp-symbol-survival-check]]` § Who runs this check). Any symbol absent/changed
at target FORCES the commit into bucket b/c/d and BANS leaving the auto-merged line unchanged. This
catches the autosilent field-break (no conflict marker, runtime crash).
SSOT: `[[fp-symbol-survival-check]]`.

**P6 TEST-survival sub-check [MUST - after the production symbol check].**
Also ground test coverage to detect test code referencing a field/model symbol removed at target
(git auto-merge leaves no conflict marker, so the break is autosilent at test time). **Dispatched to
`Explore` (read-only)** - the same delegate P6 uses for OSM grounding, assigned by
`[[fp-symbol-survival-check]]` § Who runs this check. Every call named below is CONTENT OF THAT
DELEGATE'S BRIEF, never a call you issue in this context; the paragraph reads as tool syntax only
because it is the brief text. Brief it to: for each model/field touched, call
`tests_covering(model='<model>', odoo_version='<target_version>')`
(optional `field='<field>'` narrows); for a whole-module commit, supplement with
`test_coverage_audit(module='<module>', odoo_version='<target_version>')` (field-level only; for
per-method coverage use `tests_covering(model='<model>', method='<method>', odoo_version='<version>')`,
which is sparse); and, because `tests_covering` does not compare cross-version, before concluding a
test is broken CONFIRM the symbol is absent at target via
`model_inspect(model='<model>', method='fields', odoo_version='<target_version>')`. Test methods
referencing a symbol absent at target MUST be triaged into the same bucket (not forwarded
verbatim). Record every broken test-symbol reference in the `merge-log.md` per-commit row; the
P8a adapt brief MUST include this list.

**P7 - Pre-adapt drift scan [MUST, before the behavioral loop].** Distinct from P6:
P6 catches OSM-indexed symbol-graph breaks (cross-version via index); P7 catches static
grep / import / AST breaks via two lanes: classes (d)(e)(g) run over ALL merged-touched `.py`
(production AND `tests/`) - (d)(e) catch runtime NameError and (g) catches an autosilent
ORM Invalid-field key before P9; the remaining classes (a)(b)(c)(f) and the collection
ACCEPTANCE GATE apply over `tests/` only.
DISPATCH the two lanes as read-only delegates and record only their verdict - the enumeration,
the `pyflakes`/`py_compile` runs and the collection gate never run in this context
(`[[fp-symbol-survival-check]]` § Who runs this check). The delegate enumerates every symbol, file
path, import, and test-base-class the merged code touches (Lane 1 production AND tests; Lane 2 tests
only); you triage each returned finding into a bucket (b adapt / c re-implement / d drop) - never
leave an auto-merged line referencing a dead symbol.
**ACCEPTANCE GATE:** merged test files MUST import and collect cleanly on the target
(`python -m pytest --collect-only` or `odoo-bin ... --test-enable` collection) before any
red-then-green adapt starts. A `setUpClass` crash means tests never ran, so a green count from
P9 is a false pass (`0 failed, N error(s)` is NOT a passing result). Record findings in
`merge-log.md`; P8a brief consumes them. SSOT: `[[fp-symbol-survival-check]]`.
Full commands: `references/fp-phase-detail.md` P7.

P7 is also where the VIEW-TOPOLOGY sub-check surfaces: once a bucket-(b) OR bucket-(c) commit's
own adapt step lands or modifies an `ir.ui.view` record - the bucket-(c) re-implement leg, or the
bucket-(b) 3-way-merge-and-adapt leg (INCLUDING a clean auto-merge with no conflict marker at all,
e.g. an alias-preserving module fold at target that leaves the old base `xml_id` still resolving,
so P6 finds nothing broken and P2 classifies bucket-(b) instead of (c) even though the resulting
view shape is identical to the canonical bucket-(c) defect) - confirm it is not an unconditional
same-module inherit stack on its own base view - a re-implementation (or a clean-merged carryover)
that carries the SOURCE module-split idiom forward instead of the target's. Buckets (a)/(d) land no
new adapt content (Hard rule 7) and stay out of scope - only (b) and (c) can produce this shape.
A HIT is a PROPOSAL, not a decision: it routes out through the P3 design gate above to
`odoo-solution-design`, and is applied only if the returned `design_doc` adopts it - never merged
or deleted on the predicate alone.
Predicate, the two non-defect exceptions (different-module base;
a conditional child via `mode="primary"` / `active=False` / `groups`), and the merge-unsafe
escape: `references/fp-triage-table.md` § Bucket-(c) same-module inherit-view check.

**P8 - Adapt [test-first; SERIAL per-module; runs INSIDE the batch's single open merge window].**
The batch's whole range is already absorbed into the working tree by P5, so P8 adapts the MERGED
RESULT, module by module, driven by the per-commit intent records - it does NOT re-open, re-merge,
or re-stage anything per source commit. For each touched module/WI,
adapt DIRECTLY in the integration worktree (`<path>/fp-integration`, the SAME JOB-tier worktree
created at P4) - P8 NEVER uses a per-module child worktree, in either mode. Two
independent reasons, both unconditional (full derivation: `## Git topology` § WORK tier - NOT used
by P8 adapt, above): (1) P8 is SERIAL, so there is no concurrent writer to filesystem-isolate;
(2) the open-merge window below never clears before P8 runs, so a child worktree could never
converge back in time even if one were created.

**CRITICAL - open merge window (why (2) above is unconditional, not a special case):** For the
ENTIRE span from P5 (`--no-commit`) through P10 (`commit`) - which is the batch's whole P6/P7/P8/P9
- `MERGE_HEAD` (continuous mode) or `CHERRY_PICK_HEAD` (one-shot mode) is
live in the integration worktree. Git rejects any second merge in that worktree until the first is
committed or aborted, so a child worktree could never converge back into integration during P8, in
EITHER mode. There is no gap to exploit: absorb-all opens exactly ONE window per batch and holds it
until P10 closes it, and a module whose files were touched by several source commits in the range is
adapted ONCE against the combined merged result - never once per commit. Adapt all modules SERIALLY,
DIRECTLY in the integration worktree, always. SSOT for the
in-window adapt protocol: `[[fp-merge-absorption]]` §Absorption-window.

**Per-module agent-id registry (this run's plan.md).** You run inline in ONE context for the whole
run, so the id each of your own launches returns is yours to keep. Record it in `plan.md` keyed by
module - one id per module for the WHOLE run, never one per commit. That registry is what R2b (at
most one agent per module across the run) rests on; it is never a name anyone invented, and the
resumed agent holds no address for you (`${CLAUDE_PLUGIN_ROOT}/snippets/context-handoff-protocol.md`
Tier A).

CHP Tier-A applies to the P8a test-forward worker (`odoo-test-writer`, which
authors by invoking the `odoo-test-writing` skill inline) both WITHIN one commit's P9 verify cycle
AND ACROSS commits for the SAME module (R2b for the 8a leg): after 8a+8b and the merge back to
integration, P9 may reveal a failing test - instead of spawning a cold fresh one for the re-adapt,
resume the SAME `odoo-test-writer` worker by its recorded id, sending it the P9 failure
output. **Cross-commit reuse (R2b - at most one `odoo-test-writer` instance per module across the
WHOLE run):** record the id its FIRST launch for that module returned; when a LATER source commit in
this run also touches the module, RESUME that SAME id (never a fresh dispatch) - the brief for the
resume carries the NEW commit's own intent record and bucket; the Worktree path field (below) never
changes across a resume (§ Git topology above). The worker keeps
its full prior context (earlier commits' intent records, bucket history) - far
cheaper than rebuilding from a brief, and this is what lets the SAME module's test-authoring see
its own whole picture across commits, not just within one commit's retry loop.
A resume is reachable at ANY depth, and it is reachable on exactly one condition: you STOP after
sending (CHP § Async park-and-be-resumed semantics). Structure the exchange as async
park-and-be-resumed - send the P9 failure output (or the next commit's brief), END YOUR TURN, and
consume the worker's result when you are woken with it. Emitting anything after the send, or carrying
on with the next commit in the same turn, is what strands it: there is then no point at which the
worker's answer can be handed back, and the run continues without it. If the worker's id no longer
resolves, cold-spawn a replacement (CHP Tier C) rather than pressing on. On
resume the worker MUST immediately `cd` to the integration worktree path before any Bash command (the
shell cwd is NOT guaranteed to be restored across resume - see the CHP snippet "Tier-A workers in
a git worktree - cd on resume").

**8b CODE adapt - closing R2b's remaining gap: launch the coder once, resume it across commits.**
`agents/odoo-coder.md` § Cross-round resume confirms the coordinator is ROUND-scoped, not
single-shot-forever: nothing in its own contract stops a caller from resuming the SAME
coordinator for a LATER round (a subsequent source commit touching the same module) instead of
cold-spawning a fresh one - the identical mechanism already proven above for the 8a
`odoo-test-writer` leg. **Same field shape as 8a - an ID your own launch returned, never a name:**
on the module's FIRST commit in this run, invoke the `odoo-coding` skill (via the Skill tool)
without the field; it runs INLINE in your context, so the coordinator id that launch returns is
yours to keep - record it for that module in `plan.md`; on every LATER commit touching this module, carry that recorded value as
`WORKER_AGENT_ID: <id>` in the FP-ENRICHED brief. One registry, one field label, one shape for both
legs - never a second, differently-shaped field for the same purpose.

**R2b is CLOSED at the 8b leg: `odoo-coding`'s brief-consumption contract (`skills/odoo-coding/SKILL.md`
§ Dispatch loop step 0/3) recognizes `WORKER_AGENT_ID` and resumes that id instead of cold-spawning
a fresh coordinator.** R2b (at most one agent per module) holds at 8b exactly as it already
does at 8a and at P1: the module's `odoo-coder` coordinator is launched once on the module's first
commit, its returned id recorded, and it is resumed by that SAME id
on every later commit touching that module - never cold-spawned a second time.
Hard rule 2 is NOT in conflict with this design: resuming the AGENT is a context-economy decision
and has NO effect on git topology. The batch's whole range is already absorbed by P5's single
merge before any coder runs, so N commits' worth of adapt work lands inside that ONE open window
and closes as ONE merge commit - a resumed coordinator neither adds nor removes a merge commit.
Fallback (Tier C): when no id is recorded for the module (its first commit), the recorded id no
longer resolves, or no messaging tool is present, re-invoke the `odoo-coding` skill (code re-adapt)
and/or spawn a fresh `odoo-test-writer` agent (test re-adapt) with an explicit brief containing
the P9 failure output - in Tier C, EVERY dispatch is a fresh spawn (no resume available), so the
R2b module cap above rests on the id registry, not on the fallback. Tier C is always correct; the
worklog is always written regardless of tier.

- **8a forward the test FIRST** by launching the `odoo-test-writer` agent (adapt mode; it invokes the `odoo-test-writing` skill inline). Adapt the MERGED SOURCE
  TEST to run on the target - translate API to the target idiom (base class, imports, helper
  signatures per P7), strip implementation-coupled assertions, confirm it goes RED. Do NOT
  author a brand-new test from scratch: the forwarded source test IS the oracle; 8a adapts it
  to run. Only when the source commit shipped NO test does the agent write one - anchored to
  the source intent record, not improvised.
  Build an FP-ENRICHED brief carrying a named **Worktree path: `<path>/fp-integration`** field
  (the SAME JOB-tier integration worktree for the WHOLE run - P8 never uses a per-module child
  worktree, § Git topology above - so this value never changes across a resume), plus:
  (0) **cd-on-resume (HARD RULE - Tier-A):** On resume, immediately `cd` to the
  Worktree path listed in this brief before running any Bash command. Shell cwd is NOT
  guaranteed to be restored across a resume; the explicit `cd` makes Tier-A re-adapt
  safe regardless of runtime behavior. Apply this on every resume, not only the first;
  (i) **base class grounding** - call `test_base_classes(odoo_version='<target_version>')` to
  confirm the correct base class, applying the ADAPT RULE in
  `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-era-boundaries.md` row 3 (test base-class windows +
  `SavepointCase` adapt boundary) - do not restate the windows here. `cr.commit()` FORBIDDEN in all
  test cases. Attach the raw output so the agent uses target-native idiom for every OTHER base
  class in the menu;
  (ii) **test examples at target** - call `find_test_examples(query='<feature_or_model>', odoo_version='<target_version>')`
  (optional `model='<model>'`; for kind: `'transaction'`|`'http'`|`'form'`; `kind='js'` only
  for JS tests - `kind='python'` is NOT valid) and attach the top examples as concrete templates;
  (iii) **broken test-symbol list** from P6 test-survival - adapt agent must rewrite or drop
  every test assertion referencing a symbol removed at target;
- **8b adapt the code** per bucket by invoking the `odoo-coding` skill (via the Skill tool) -
  `odoo-coding` owns the backend/frontend split, coder fan-out (via its `odoo-coder` per-node
  coordinator), model, and synthesis (do NOT dispatch raw `odoo-coder`, `odoo-backend-coder`, or
  `odoo-frontend-coder`) -
  with an FP-ENRICHED brief = the named **Worktree path: `<path>/fp-integration`** field (same
  JOB-tier integration worktree as 8a - never a per-module child worktree, § Git topology above)
  + the same **cd-on-resume (HARD RULE - Tier-A)** item as 8a + intent record + bucket + the failing
  test + the installable:False checklist + `WORKER_AGENT_ID: <id recorded for this module on its
  first dispatch this run>` (per the R2b rule above - omit on the module's first commit) +
  `DESIGN_DOC: <path from plan.md's design_doc column for this commit | none>` (P3's route-out
  result, so 8b never adapts blind - `none` when P3 never routed this commit to design; same
  sentinel shape `odoo-coding`'s own brief-resolution already uses, `skills/odoo-coding/SKILL.md`
  "DESIGN_DOC: <child TDD path | none>") +
  `MANIFEST/MIGRATION/PROVENANCE: apply C1 (keep TARGET
  version on conflict, never bump), C2 (migration-dir retarget), C3 (carry pre-existing source bugs
  faithfully, do not inline-fix) - [[fp-merge-absorption]]`. Bucket (a)/(d): no adapt code.
  Bucket (b): 3-way merge + adapt. Bucket (c): re-implement on the target idiom. The frontend leg
  additionally grounds any ported OWL/QWeb/SCSS against `skills/_shared/odoo-frontend-fidelity.md`
  so the forwarded UI stays on-theme and design-system-correct for the target version.
- **8c installable:False modules** - two sub-cases, same manifest action:
  (i) **New module** (absent at target): set `installable: False` + comment `auto_install`/
      `application`, lint-fix only.
  (ii) **Upgraded-then-forwarded** (pre-existing at target with `installable:False` at clean-tip,
      but merge carries `installable:True`): re-set to False + re-comment `auto_install`/
      `application` with breadcrumb - then lint-fix only.
  Both land in the LINT-ONLY lane. SSOT: `[[fp-installable-false]]`.
- **8d migration script**: retarget a forwarded `migrations/<src-series>.a.b.c/` dir to the target
  series per C2 (default: name it FULL `<tgt-series>.V` so it fires on a deployed target DB at manifest
  `M`; bump the manifest only in the `S<=M` case; legacy source-only data fix keeps `<src-series>.a.b.c`).
  This is a migration-threshold action, NOT a conflict-resolution version bump (C1). Full rule +
  `adapt_version` silent-skip WHY: `[[fp-merge-absorption]]`.
There is no child worktree to converge back or remove: 8a/8b already wrote directly into the
integration worktree (§ Git topology above), so nothing merges INTO integration here beyond the
adapt edits already sitting in its working tree - P10 is what commits them. This is also why a
Tier-A resume is always safe: the worker's `cd`-on-resume target (the integration worktree) is the
SAME long-lived path for the WHOLE run, never a per-module path created and removed per cycle.

**P9 - Verify by behavior [PER-BATCH, in integration].** DELEGATE the run - do NOT allocate a DB +
port and run the full suite inline. A full per-batch suite is exactly the case the test-execution
handoff contract reserves for the executor: its output is large (test log, tracebacks) and would flood
this orchestrator's context, and running it here folds the executor role into the conductor. SSOT:
`${CLAUDE_PLUGIN_ROOT}/snippets/test-execution-handoff.md`. Dispatch `odoo-instance` (via the Skill tool;
L2 human gate applies) - the same delegation `odoo-modules-upgrade` P5 and `odoo-git-rebase` P10 use:
provision the cluster ONCE, PASSING `WORKTREE_PATH: <path>/fp-integration` (the SAME P4 JOB-tier
integration worktree the merge/adapt phases wrote to) in that first dispatch, so `odoo-instance`
re-roots the addons list onto it via `--addons-path-override`
(`odoo-instance/SKILL.md` § WORKTREE_PATH substitution) instead of loading the principal checkout -
without this, a "GREEN" result here proves nothing, since it would verify un-adapted code. Then per
batch dispatch init for the N affected modules followed by run-tests of the target suite, relaying the
returned `INSTANCE_HANDLE` so later batches reuse the same instance instead of self-provisioning
(`odoo-instance-ops` resolves odoo-bin flags per series via `cli_help`, performs Odoo create-on-init,
and drops the DB through Odoo on release). The executor returns a structured result block (per-test
pass/fail + the instance log path), NOT the raw firehose. From that block THIS skill stays the
adjudicator of FP intent: RED-then-GREEN for the whole module + confirm-by-toggle for FP-delta tests
only, triaging each red test as FP-delta vs pre-existing (re-run it on clean target tip via the same
executor). Never relax an assertion to hide a pre-existing failure. Full per-batch protocol +
§ Ephemeral isolation: `[[fp-merge-absorption]]`. Instance lifecycle and test invocation conventions:
`docs/reference/INSTANCE-LIFECYCLE-BUILD-CONTRACT.md` and `docs/reference/ODOO-TESTING.md`.

**P9.5 - i18n reconcile [MANDATORY, per batch, reuses the P9 instance].** For every module in this
batch whose 8e record says `i18n_due: yes`, invoke the `odoo-i18n` skill (via the Skill tool) ONCE.
Pass the four caller obligations from
`${CLAUDE_PLUGIN_ROOT}/snippets/i18n-mandate-contract.md`: `WORKTREE_PATH` (this batch's integration
worktree), the P9 `INSTANCE_HANDLE` (its addons path now genuinely covers that worktree - P9 re-roots
it via `WORKTREE_PATH`, above), `TARGET LANGUAGES` (best-effort: the codes inferred from the
source-side `<lang>.po` filenames - deliverable languages only, never `en_US` - when any exist; a
module gaining its FIRST-EVER translatable string in this batch has none to infer, so OMIT the field
rather than block on it - `odoo-i18n`'s own P0 still tries tiers 2-4 itself and records escape E3,
non-blocking, if all four come up empty), and `GATE: fold into P10`. `odoo-i18n` owns the
non-destructive recipe and the isolated-DB export; this pipeline forwards only the intent. An
`i18n_due: escape:<E-id>` module is skipped with its recorded reason. Present every result -
reconciled or escaped - at the P10 gate, so the human sees ONE combined decision. Note `odoo-i18n`
needs a FRESH DB per pass (existing `<lang>.po` loaded before re-export), so reusing the P9 server
lease does not make this free.

**P10 - Gate merge [STOP, per batch].** Emit `merge-log.md`, present it, wait for human-confirm.
On confirm: invoke the `git-toolkit:git-ops` skill (via the Skill tool) to close the batch's single
open merge window with ONE commit - the batch's whole range lands as ONE merge commit, and every
SHA in the range is marked `done` in `checkpoint.json` by that one commit (buckets a/d are absorbed
by it too, carrying no diff - Hard rule 7).

**There is no P5 loop.** A single-batch run (the default) reaches P10 exactly once and then goes on
to P11. Only when the human split the run into several gated batches at the P4 plan gate does the
pipeline return to P5 - once PER BATCH, never per commit - and that next pass merges the NEXT
batch's range TIP in one operation, then runs P6 symbol-survival -> P7 drift -> P8 adapt (directly
in the integration worktree, as always - § Git topology) -> P9 verify -> P10 gate for that whole
batch. Re-entering P5 for a single source commit, or committing part-way through a batch's range,
is Hard rule 2's banned shape and produces the merge-commit sprawl this pipeline exists to avoid.

**P11 - End-to-end acceptance (odoo-acceptance) stage [MANDATORY, cluster-wide, narrow escape
only, BEFORE the P12 PR opens or reviews].** Runs immediately after the P10 loop closes (every
commit/batch this run covers has reached `status=done`) and BEFORE P12 pushes the branch, opens
the PR, or runs its lint-class review gate - the position the **Terminal stage order** constant
assigns it (`${CLAUDE_PLUGIN_ROOT}/skills/run-harness/references/run-integration.md` § Pre-PR tail
is that constant's ONE owner: read the order there, never restate it here). Acceptance and the i18n
reconcile (P9.5, already mandatory per batch, ahead of every P10 gate) both land ahead of the PR and
its review for the reason the constant states: a stage that can force a CODE CHANGE runs before the
PR opens, so the PR does not churn and regression testing is not chasing a moving target. Goal: prove the forward-ported batch works end-to-end on a real running
instance/UI across its blast-radius - the SAME acceptance rigor new-module development applies. P9's per-batch
verify-by-behavior proves RED-then-GREEN + confirm-by-toggle for the ported intent tests; it does
NOT prove the touched cluster behaves correctly for a real user across roles/state/search -
closing that gap is this stage's job. This is a DIFFERENT concept from the P7 pre-adapt drift-scan
**ACCEPTANCE GATE** (the test-collection sanity check that merged test files import and collect
cleanly, `references/fp-phase-detail.md:335`) - deliberately named differently so the two are never
conflated.
Compute the verify scope by invoking `${CLAUDE_PLUGIN_ROOT}/snippets/acceptance-scope.md` over
every module touched across the batch (from `merge-log.md`) - forward-port has no pre-built
dependency DAG file the way `odoo-modules-upgrade` does, so this pass derives the reverse-closure
directly via OSM `impact_analysis` per that snippet's Step 1.
Invoke the `odoo-acceptance` skill (via the Skill tool) ONCE for the whole batch (never per commit
or per module). Fill the dispatch brief per `${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md`
(read it by path): `INPUTS` = the touched module set from `merge-log.md`, `scope_hint` =
`merge-log.md` + each touched module's own `<module>/intents/<sha>.md` (§ P1 write path), `odoo_version`
= target series; `INSTANCE_HANDLE` from P9 if
still live (reuse - never re-provision; else pass `none provisioned` and `odoo-acceptance` still
scopes + plans its oracle, then emits `NEEDS_NEXT -> odoo-instance`). `ACCEPTANCE` (by pointer) =
each ported commit's behavioral contract recorded in the touched module's own `<module>/intents/<sha>.md`
and any P3 design doc's §9
- NEVER a pre-built oracle: `odoo-acceptance` authors its OWN independent oracle at its own
Phase 1 from that intent, the same oracle-independence guarantee the new-module lifecycle
protects. Do NOT hand it the implementation.
**MANDATORY - narrow escape only.** A forward-ported batch's touched modules have in-cluster
dependents by construction whenever they carry shared/depended-on symbols, so the blast-radius
bar this stage exists for is met almost always - this is NOT an opt-in hand-off. Skip it ONLY when
the touched set is a true dependency leaf with ZERO in-repo dependents AND no behavioral surface
(no views, no models any other module consumes) - record that proof explicitly in `merge-log.md`;
never skip silently. **The forward-port is not DONE until this stage returns ACCEPTED (PASS), or
the narrow-escape condition above is explicitly met and recorded.**
Gate tier: L2 (human) - carry the acceptance verdict (or the recorded narrow-escape) forward and
present it ALONGSIDE the P12 human-merge decision below, so the human sees ONE combined gate (PR,
review findings, and acceptance verdict together), not a surprise extra step after merge is
already requested.
Output: `<ISOLATE_DIR>/qa/<slug>-acceptance-report.md` (`odoo-acceptance`'s own artifact), referenced
from `merge-log.md`.

**P12 - PR + review [runs AFTER P11 acceptance clears].** Push `fp/<slug>` (invoke
`git-toolkit:git-ops`; resolve origin URL via `git remote get-url origin`). Run `odoo-code-review`
inline (via the Skill tool, from this orchestrating context) passing `TARGET: worktree:<path>/fp-integration` (the
JOB-tier integration worktree created at P4 - `<path>` is the base path passed to git-ops at P4)
so the skill reviews the fp integration tree, not the principal tree - this lint-class review gate
runs BEFORE the PR is opened, at the position the **Terminal stage order** constant assigns it
(`${CLAUDE_PLUGIN_ROOT}/skills/run-harness/references/run-integration.md` § Pre-PR tail). It can
force code changes, so it must precede the PR, not follow it. It is OPTIONAL for a trivial port
(docstring/string/comment-only buckets), but
**MANDATORY whenever the batch grafts a new engine or mechanism** (a shared report engine, a
group-by/total/drill computation, an export/print path, a wizard, any multi-path component) -
a clean merge of one path proves nothing about the others. For a mandatory review:

1. **Enumerate EVERY code path of the grafted mechanism and confirm each was adapted.** A report
   or compute engine typically fans out into: total, sub-total/group-by, expand/collapse, drill
   -down, export (xlsx/csv), and print (PDF/QWeb). List each path and verify the forward-port
   adapted it - a path the source touched but the adapt missed is a silent partial port that
   passes the headline test while a sibling path renders wrong. The review is not done until
   every enumerated path is accounted for (adapted, or explicitly N/A with a reason).
2. **Attribution diff before rating any finding.** A finding only belongs to THIS port if
   it sits on a line this port changed. Invoke the `git-toolkit:git-ops` skill (via the Skill tool) for a three-dot diff
   (`origin/<target-branch>...fp/<slug>`) and attribute each finding to either a
   forward-ported line (in scope, fix now) or a pre-existing target line (out of scope, do not
   re-rate the target's own debt as a port regression). Rate findings only after this attribution.

A module that is `installable:False` at the target is in the lint-only lane (`[[fp-installable-false]]`):
the reviewer rates ONLY lint/syntax for it and MUST NOT raise a business-logic finding (its
behavior is intentionally not forward-ported - see `## Model triage`).

**Acceptance hand-off (consumption clause).** The `odoo-code-review` dispatch above may itself
carry a `next: odoo-acceptance` entry in its own Continuation Contract (Phase A.5 emits this
whenever `render_check_set` reaches beyond the reviewed modules). READ it, but do NOT act on it -
the cluster-wide `odoo-acceptance` dispatch for this batch already ran at P11 ABOVE; acting on this
entry would re-run acceptance a second time for the same batch.

NEVER squash (keeps SHA). Only once the review above is addressed does B get anything at all:
open PR now (invoke `git-toolkit:git-ops`). B stays LOCKED - the PR carries the run's merge commit
(one per gated batch; one in total for a default single-batch run), nothing else.

**Cross-check every static-review bot comment on the PR (post-PR, informational only - the ONE
sub-step in this phase that genuinely needs the PR to already exist).** Once the PR above is open
and CI has had a chance to run, read the bot (CI linter / review bot) comments and resolve or
consciously waive each - a bot comment on a forward-ported line is signal that an auto-merged
construct did not survive the target. Bot comments cannot predate the PR they are posted on, so
this sub-step runs after PR creation, never before, and it never gates PR creation itself - every
other review item above is diff-based and already cleared before the PR opened.

Present the PR URL, the review findings, and the P11 acceptance verdict together, and wait for the
human to merge.

## Model triage - two tier tables

**installable:False short-circuit.** Before assigning ANY tier, resolve each touched module's
`installable` flag at the target clean tip by reading `<module>/<tgt-descriptor>` at `target_ref` (the
file P2 already wrote to `manifest_path`; an absent key means installable). A module that is
`installable:False` at the target - a brand-new module not yet landed, OR a pre-existing dormant
one - is NOT forward-ported for behavior: route it to the **lint-only lane** (flake8 / pylint /
eslint / prettier / ruff to green CI, minimum fix only) and SKIP the extract/adapt/review logic
tiers entirely. Its business logic is not adapted and P12 review rates only its lint/syntax, never
a business finding. SSOT: `[[fp-installable-false]]`.

**Bucket-(c) upgrade-scale gate.** Bucket (c) is "re-implement on the target idiom" - but
that one bucket covers a 3-line call-site fix and a 500-line component rewrite alike, and the
ADAPT tier below only picks the MODEL, not whether the work is even a mechanical port. After P2
classify, estimate each bucket-(c) cluster's adapt size (source LOC delta + framework-migration
flag). If it exceeds ~200 LOC of new OWL/JS OR is a full component/framework rewrite, it is an
upgrade-scale RE-IMPLEMENT, not a mechanical port: RECORD the `upgrade-scale` flag at P2 and
PRESENT the defer-or-do choice at the P4 plan gate - (a) defer (carry `installable:False`,
lint-only lane) or (b) do now (estimate effort, adapt at the ADAPT-table tier). Never silently
absorb unbounded re-implement work; default on no answer is defer. SSOT:
`references/fp-triage-table.md` § Bucket-(c) upgrade-scale gate.

Triage is INLINE and deterministic, run twice with different tables, and is now resolved PER
MODULE BUNDLE for EXTRACT (R2a/R2c/R2d - see `references/fp-triage-table.md` Table 1):

- **EXTRACT tier (P0 -> P1 intent extraction, per MODULE bundle):** haiku for a bundle whose every
  commit is docstring/comment/string-only, sonnet for a bundle with a logic commit (the default -
  R2c preference), opus for a bundle with a migration/cross-module/inheritance-axis commit -
  resolved as the HIGHEST-priority row ANY commit in the module's bundle matches, never an
  average. **fable is NOT in the EXTRACT band.** **Opus at this step needs explicit human
  confirmation (R2d)** - not a silent auto-assign; full gate wording in
  `references/fp-triage-table.md` Table 1.
- **ADAPT tier (P8 code adapt, per commit within a module):** follow the `odoo-coding` deterministic
  tier table (haiku/sonnet/opus/fable, sonnet default, fable always needs explicit human
  confirmation - unchanged, still per-commit since a module's own commits can differ in ADAPT
  complexity).

Resolve a tier by walking each table top-down, first match wins. Full both-table detail with
per-row conditions: `references/fp-triage-table.md`. Record every chosen tier in `plan.md` - a
tier is part of the approved plan, not a runtime improvisation.

The two tiers are decided INDEPENDENTLY - never reuse one tier as the other. Run the EXTRACT
table at P0->P1 against the MODULE's whole commit bundle and the ADAPT table at P8 against each
commit's own conditions; a module whose bundle is haiku-grade to EXTRACT may still have one commit
that is opus-grade to ADAPT if that commit's target re-implementation is cross-module.

## Absorb-all - the one git shape both modes use

**Absorb-all** is this pipeline's name for its ONLY git shape: P5 takes the batch's ENTIRE commit
range in ONE operation, P6-P9 work inside that one open window, and P10 closes it with ONE commit.
It is not a mode, an option, or a large-run optimization - it is what BOTH modes below do, on every
batch, always. Its opposite - stepping the range one source commit at a time - is banned by Hard
rule 2 in both modes.

Read it against the pipeline's other axis, which is deliberately the opposite: the SEMANTIC work
stays strictly per-commit (P1 intent, P2 bucket, per-commit ADAPT tier and `merge-log.md` rows),
because each source commit carries its own purpose. Per-commit REASONING plus absorb-all GIT
topology is the whole design; a per-commit git operation is never a consequence of per-commit
reasoning.

- **Continuous (default).** Recurring; the range merge keeps every source SHA and advances the
  merge-base to the range tip; `checkpoint.json` skips commits already absorbed by an earlier run
  and no past conflict is ever re-resolved.
- **One-shot (`--one-shot`).** Port one frozen batch once via a no-commit cherry-pick of the WHOLE
  range in one staged sequencer run (delegated to git-toolkit via `git-ops`); every other phase is
  identical. It does NOT preserve SHA and does NOT advance the merge-base, so the run is not
  repeatable - use it only when the source is frozen, or when a deliberate sub-range must land
  without dragging the rest of the source branch in.

## Checkpoint / resume

`<ISOLATE_DIR>/forward-port/<slug>/checkpoint.json` maps
`{<sha>: extracted | designed | adapted | verified | done}`, with `designed` carrying the
`design_doc` path for any commit P3 routed to `odoo-solution-design`. P0 reads it and skips
`status=done` commits (and resumes a `status=designed` commit at the P4 plan gate with its
recorded `design_doc`, so a crash between design-approval and re-entry resumes correctly). A
crash mid-batch is recovered by re-reading the checkpoint + the on-disk `<module>/intents/`
per-module subdirectories, `plan.md`, and `merge-log.md` (file existence is the source of truth,
the JSON is the fast index).

**Resuming a crash INSIDE the absorption window.** Because a batch commits only at P10, a crash
during P6-P9 leaves the integration worktree with its merge window still OPEN - `MERGE_HEAD` (or
`CHERRY_PICK_HEAD`) live, partial adapt on disk. That state IS the resume point: check for it
FIRST (`git -C <path>/fp-integration rev-parse -q --verify MERGE_HEAD`, a bounded read), and when
it is live, RESUME the existing window at the phase `checkpoint.json` last recorded - never re-run
P5 on top of it (git refuses while a window is open) and never abort it in order to restart the
range commit-by-commit. Abort and re-open the WHOLE range only when the window is already gone or
the working tree is unrecoverable, and record that decision in `merge-log.md`. Record the executor's
`INSTANCE_HANDLE` (and its instance log path) in the batch worklog so a resumed run reuses the same
instance or asks `odoo-instance` to release it instead of orphaning the DB - since P9 delegates the run,
the instance lifecycle is owned by `odoo-instance-ops`, not held as an allocator lease in this skill.

## Frontend / i18n / data-XML caveats

Forward-port adds platform-drift classes a pure-Python port misses - flag and route each:

- **Frontend (JS/OWL/SCSS).** Asset-bundle keys drift across series and OWL moved from the legacy
  `web.Widget` / `odoo.define()` era to OWL 2.x `patch()` / `useState` / `useService`. Route a
  frontend adapt commit to `odoo-coding` (its frontend leg owns both eras) - never hand-translate
  OWL from memory.
- **i18n (.pot / .po).** Do NOT hand-port or re-export translation files in this pipeline. The i18n
  reconcile is MANDATORY, narrow-escape only, per `${CLAUDE_PLUGIN_ROOT}/snippets/i18n-mandate-contract.md`:
  8e COMPUTES the trigger + already-upgraded conditions per module, P9.5 DISPATCHES `odoo-i18n` once
  the P9 instance exists - it owns the non-destructive `.pot`/`.po` recipe and validates the result.
  Full wiring: `references/fp-phase-detail.md` § 8e, SKILL.md § P9.5.
- **Data XML (`noupdate` records).** A source data record may reference an external-id that does
  not resolve at the target. After merge, verify every external-id in touched data XML resolves
  on the target (P6 covers `ref()` / `xml_id`); a `noupdate="1"` record will not be
  re-written, so a broken ref is permanent until fixed here.

Three more cross-cutting checks apply per batch:

- **Multi-repo env bootstrap.** When source and target live in different repos/clones, bring
  the source ref into reach (invoke `git-toolkit:git-ops`: add source remote + fetch) BEFORE computing
  the merge-base or merging; a forward-port across repos that skips this silently merges against a
  stale local ref. Detail: `references/fp-phase-detail.md`.
- **Manifest version & migration dir.** Forward-port carries the source manifest AS-IS and NEVER
  auto-bumps `version`: on a `<tgt-descriptor>` conflict keep the TARGET file's value (C1). A forwarded
  `migrations/` dir is RETARGETED to the target series (C2) - a dir rename with a threshold-driven
  version, NOT a "diff-touched-a-file" bump. C1 and C2 are distinct; apply both. SSOT:
  `[[fp-merge-absorption]]`.
- **Field-label grounding.** When the port renames or re-labels a field, confirm the
  target's canonical label before adapting -
  `entity_lookup(kind='field', model='<model>', field='<field>', odoo_version='<target>')` - so the
  forwarded string matches the target's own term. Detail: `references/fp-phase-detail.md`.

## MCP tools

<!-- BEGIN GENERATED TOOLS -->
> **Pick the right tool first.** Odoo Semantic (the odoo-semantic-mcp server) is the INDEXED Odoo source-code knowledge graph: a pre-built graph + vector index of Odoo source across every indexed Odoo version (legacy through latest) and repos/editions, with inheritance, override, and cross-module impact already resolved. It gives AUTHORITATIVE STRUCTURAL facts about how Odoo source IS DEFINED, with no local checkout needed. Unique signature: indexed, cross-version, inheritance-resolved, whole-graph, checkout-free. It is a STATIC index with NO runtime/live data.
>
> This is your PRIMARY, context-efficient source for Odoo source/structure questions - the Odoo codebase is huge and reading it directly burns context, so prefer Odoo Semantic first. Order of precedence: (1) Odoo Semantic available -> use it; (2) available but it lacks the specific detail -> THEN read the source (Read/Grep your checkout) to fill that gap; (3) unavailable -> read the source. Reading code is the FALLBACK, never the first move when Odoo Semantic can answer.
>
> Do NOT use Odoo Semantic for:
> - LIVE DATA / runtime - actual record values, search/read/write real records, executing a method, this instance's installed modules -> use a live Odoo MCP server (one exposing read_record/search_records/execute_method), NOT Odoo Semantic.
>
> Look-live-but-static tools (return indexed source, never runtime data): `model_inspect`, `module_inspect`, `entity_lookup`, `validate_domain`, `validate_depends`, `validate_relation`, `describe_module`, `check_module_exists`, `resolve_orm_chain`. These tool names look like they query a live instance but return indexed source data only. If you need live records, Odoo Semantic is the wrong server.

**Session bootstrap** (call once at session start):
- `set_active_version(odoo_version='17.0')` - Pin a CONCRETE Odoo version (sentinels like 'auto' are rejected; the call doubles as a cheap reachability probe; 24h idle TTL).

**Primary tools:**

> **Listing a tool here does NOT license every context to call it.** A bullet carrying a **Caller:** clause is QUALIFIED: that clause names who may issue the call and where, and it overrides this list. Where a phase of this skill assigns the call to a dispatched delegate, the delegate issues it and the orchestrating context records only what comes back.

- `api_version_diff` - Structured diff of an API symbol or scope across two Odoo versions: new, changed, removed, deprecated items. **Caller:** orchestrator-inline ONLY where a phase explicitly assigns it (P2 classification, and the 8a/8b adapt-brief grounding); at P6 / P6-TEST / P7 the same call belongs to the dispatched read-only delegate, so never issue it in the orchestrating context there (`snippets/fp-symbol-survival-check.md` - Who runs this check).
- `model_inspect` ★ - Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, extenders, or a summary in one call. **Caller:** orchestrator-inline ONLY where a phase explicitly assigns it (P2 classification, and the 8a/8b adapt-brief grounding); at P6 / P6-TEST / P7 the same call belongs to the dispatched read-only delegate, so never issue it in the orchestrating context there (`snippets/fp-symbol-survival-check.md` - Who runs this check).
- `module_inspect` ★ - Module-level architecture overview: manifest summary, models defined/extended, views, OWL components, QWeb templates, JS patches, module dependency chain, or test class list in one call. **Caller:** orchestrator-inline ONLY where a phase explicitly assigns it (P2 classification, and the 8a/8b adapt-brief grounding); at P6 / P6-TEST / P7 the same call belongs to the dispatched read-only delegate, so never issue it in the orchestrating context there (`snippets/fp-symbol-survival-check.md` - Who runs this check).
- `entity_lookup` ★ - Single-entity drill-down by kind discriminator: model, field, method, view, module, pattern, or report - with full inheritance chain and source module. **Caller:** orchestrator-inline ONLY where a phase explicitly assigns it (P2 classification, and the 8a/8b adapt-brief grounding); at P6 / P6-TEST / P7 the same call belongs to the dispatched read-only delegate, so never issue it in the orchestrating context there (`snippets/fp-symbol-survival-check.md` - Who runs this check).
- `find_override_point` - Show override chain, super() safety guidance, and anti-patterns for a method to find the safest place to inject custom behavior.
- `find_test_examples` - Semantic search for Odoo test code examples (test_method, test_class, js_test chunks only - never returns production code). **Caller:** orchestrator-inline ONLY where a phase explicitly assigns it (P2 classification, and the 8a/8b adapt-brief grounding); at P6 / P6-TEST / P7 the same call belongs to the dispatched read-only delegate, so never issue it in the orchestrating context there (`snippets/fp-symbol-survival-check.md` - Who runs this check).
- `test_base_classes` - Menu of official Odoo test framework base classes (TransactionCase, HttpCase, SavepointCase, Form, etc.) for the given version, with test_type and cursor contract. **Caller:** orchestrator-inline ONLY where a phase explicitly assigns it (P2 classification, and the 8a/8b adapt-brief grounding); at P6 / P6-TEST / P7 the same call belongs to the dispatched read-only delegate, so never issue it in the orchestrating context there (`snippets/fp-symbol-survival-check.md` - Who runs this check).
- `test_coverage_audit` - Audit an entire module for test coverage gaps: lists fields/methods with zero COVERS_* edges (never referenced by any test). **Caller:** delegate only - the P6-TEST test-survival sweep runs inside the dispatched read-only `Explore` delegate; the orchestrating context records its verdict and never issues this call (`snippets/fp-symbol-survival-check.md` - Who runs this check).
- `tests_covering` - List test methods that have COVERS_MODEL/COVERS_FIELD/COVERS_METHOD edges to the target model or field (static reference coverage, not runtime executed coverage). **Caller:** delegate only - the P6-TEST test-survival sweep runs inside the dispatched read-only `Explore` delegate; the orchestrating context records its verdict and never issues this call (`snippets/fp-symbol-survival-check.md` - Who runs this check).
- `cli_help` - Look up odoo-bin subcommand flags, their status, and replacement for deprecated flags.
- `impact_analysis` - Risk assessment of changing or removing a field, method, or model: blast radius, dependent modules, and downstream fields.
<!-- END GENERATED TOOLS -->

## Standalone-first fallback

When Odoo Semantic (the odoo-semantic-mcp server) is unreachable, the pipeline degrades but
does not stop. P1 intent extractors fall back to local-source reads
(`${CLAUDE_PLUGIN_ROOT}/snippets/osm-first-contract.md`), labelling each record
`grounded: local-source (not OSM-indexed)`. P2 classify and P6 symbol-survival
fall back to disk reads of the target checkout per
`${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md` (read each `<tgt-descriptor>`
`depends` and the model/field source) - the symbol-survival guarantee still holds via grep on
the target source, only the grounding citation changes. `odoo-version-diff` standalone mode
supplies the version delta from GitHub release notes when the index is down. Never ask a human
to paste code, field lists, or manifests; the merge SHA-preservation and verify-by-behavior
contracts are unchanged - only the grounding source degrades.

## Continuation Contract

When the run finishes (or pauses at a gate), append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next).
`produced` lists `plan.md`, each touched module's own `<module>/intents/<sha>.md` (§ P1 write path -
never the bare `intents/<sha>.md`), `merge-log.md`,
`<ISOLATE_DIR>/qa/<slug>-acceptance-report.md`, `checkpoint.json`, and the PR
URL; `next` is the human-confirm gate (P10 per-batch merge, P11 acceptance L2 gate, or P12 final
PR/merge gate). When P3 routes a commit out to design,
`next: odoo-solution-design` with the `inputs` block whose SSOT is
`references/fp-phase-detail.md` P3 (read the field list there - it is not copied here), and the
run YIELDS - the run-harness advances the hop and re-enters forward-port with the returned
`design_doc`. Additive output for the run-harness - it does not change anything produced above.
