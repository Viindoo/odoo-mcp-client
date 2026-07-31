<!-- SSOT snippet. Home for (1) the collision-proof slug-derivation rule shared by every
     skill that mints one of the four sibling visual/*/<slug>/ evidence subpaths, and (2) the
     orphan-sweep GC rule for EVERY run-scoped Tier-2 ISOLATE subpath in the plugin (Clause 3
     generalizes Clause 2 beyond visual/ to the full ISOLATE surface). Edit here only;
     consumers point at ${CLAUDE_PLUGIN_ROOT}/snippets/visual-evidence-lifecycle-contract.md.
     Tier and bucket classification of these paths is owned by
     ${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md - not restated here. -->

# Run-scoped visual evidence: slug + retention (SSOT)

Four skills each mint a per-run `<slug>/` evidence directory under `visual/`:
`odoo-visual-regression` (`visual/current/<slug>/`), `odoo-acceptance` via `odoo-qa-tester`
(`visual/qa/<slug>/<module>/`), `odoo-debug` via `odoo-ui-debugger` (`visual/debug/<slug>/`),
and `odoo-ui-review` via `odoo-ui-reviewer` (`visual/screenshots/<slug>/`). Both the slug
ITSELF and the directory's LIFETIME are the same defect class stated twice - a bare intent
slug collides under concurrency, and an evidence directory nobody ever deletes leaks disk
forever - so this file states both rules once for all four. Clause 3 below generalizes the
retention half (only) of this rule to every OTHER run-scoped ISOLATE subpath in the plugin -
the same leak, one directory per run, is not unique to `visual/`.

## Clause 1 - collision-proof slug derivation

Mint the slug ONCE, at the start of the run (before any path that embeds it is touched):

```
<intent-slug>-<YYYYMMDD>-<4 random chars>
```

The IDENTICAL suffix mechanism `${CLAUDE_PLUGIN_ROOT}/skills/odoo-intake/references/phase-p-run-dag.md:43`
uses for its `run-<id>.json` id ("so concurrent runs never collide") - do not invent a
second algorithm. Use the `SLUG:` value from your dispatch brief when a caller supplies one;
derive fresh only on a standalone invocation with no caller-supplied slug. Mint it exactly
once per run and reuse that SAME value for every artifact path the run touches - never
improvise a fresh one per screen/module/step, never re-mint the random suffix mid-run, never
leave the literal `<slug>` token itself in a path.

**Worked example - two concurrent same-intent runs.** Intent "compare before/after the v17
upgrade" fired twice concurrently:

`compare-v17-upgrade-20260731-a1b2` and `compare-v17-upgrade-20260731-9f3d`

Same intent-slug and date, different random suffix - the two runs write to different
directories and neither overwrites the other's evidence.

**Why the random suffix, not just the date.** `<ISOLATE_DIR>` is worktree-keyed, not
run-keyed (`state-root-resolution.md`), and any of these four skills may run standalone
(exempt from wider run/worktree provisioning) - date alone still collides when two callers
fire the identical intent the same day. The 4-character random suffix is the disambiguator.

## Clause 2 - orphan-sweep retention (GC)

**Eligible:** ONLY the four `visual/*/<slug>/` ISOLATE subpaths this file names (bucket 2,
run-scoped evidence, per `state-root-resolution.md` § Where a captured artifact goes). NEVER
a SHARE reusable cache (`visual/baselines/`, `visual/doc/`) - its whole value IS surviving
across runs, so sweeping it on a TTL would destroy the thing it exists to provide. NEVER a
committed module deliverable (bucket 3) - it is reached only by an explicit copy into the
module tree and thereafter lives under git, entirely outside this sweep's reach.

**Bound.** `visual/current/<slug>/` already self-deletes at its own run's terminal status
(`odoo-visual-regression/SKILL.md` § Retention); its TTL backstop stays the existing 24h
(mtime), for the crash-only case. The other three (`qa/`, `debug/`, `screenshots/`) are
deliberately RETAINED past their own run's terminal status - they are the cited evidence
behind a PASS/FAIL verdict, a diagnosed root cause, or a review finding - so a 24h sweep
would delete evidence a human or a later phase still needs. Their bound is **30 days
(43200 minutes, mtime)**: long enough that the evidence outlives the run that produced it
and any immediate follow-up, short enough that disk growth stays bounded to roughly one
month of runs rather than forever.

**Who sweeps, when.** The skill that owns each subpath sweeps its OWN sibling directories,
unconditionally, at its own Phase/Round 0 - BEFORE minting its own run's `<slug>` (Clause 1)
- exactly the pattern `odoo-visual-regression`'s Round 0 already applies to `visual/current/`:

```
find <ISOLATE_DIR>/visual/<subdir>/ -mindepth 1 -maxdepth 1 -type d -mmin +<bound-in-minutes> -exec rm -rf {} +
```

`odoo-acceptance` sweeps `visual/qa/` (mmin +43200), `odoo-debug` sweeps `visual/debug/`
(mmin +43200), `odoo-ui-review` sweeps `visual/screenshots/` (mmin +43200) - each at its own
Phase/Round 0, each scoped to only its OWN subdirectory, never a sibling it does not own.
Enforcer: whoever executes that skill next, unconditionally, every run - not a separate
cleanup agent or cron; no hook tracks a filesystem directory the way the allocator ledger
tracks an instance lease.

**Concurrency protection (the dangerous failure mode).** The sweep can NEVER delete a
concurrent run's live directory, for two independent reasons, either one sufficient alone:
(1) `-mmin +<bound>` matches only a directory UNTOUCHED for the full bound - a live run keeps
writing into its own `<slug>/` dir throughout its execution, continuously refreshing its
mtime, so it never ages past the threshold while still running; (2) the sweep runs BEFORE
this run mints its OWN new slug (Clause 1), so it can never match the directory THIS run is
about to create. A directory only matches the sweep once its owning run reached a terminal
status (and stopped writing) and then sat untouched for the FULL bound - by which point every
terminal-status path (DONE/BLOCKED/NEEDS_CONTEXT/NEEDS_NEXT) has already had 30 days to have
its evidence consumed.

## Clause 3 - generalized ISOLATE-tier orphan sweep (every OTHER run-scoped subpath)

Clause 2's leak is not unique to `visual/`. Every Tier-2 ISOLATE subpath in
`state-root-resolution.md`'s ISOLATE table is, BY DEFINITION of that tier ("run/session-scoped
active state" - see that file's § The rule), a candidate for the identical leak: nothing has
ever deleted any of them. This clause enumerates the FULL ISOLATE table (exhaustive per that
file's own claim) and classifies each row once, so a later reader never has to re-derive it.

### 3.1 - Eligible (bucket 2, run-scoped evidence/working-state - swept)

| Subpath | Owner | Bound | Why this bound |
|---|---|---|---|
| `worklog/<run-or-slug>/` | every multi-agent run (via `worklog-contract.md`) | 30d | decision log stays useful after the run for the next resume/audit; no self-cleanup step exists |
| `wave/<slug>/` | `run-harness` (between-wave) | 24h | ALREADY self-deletes at its own post-merge cleanup (`wave-integration.md` § Cleanup) - the TTL is a crash-only backstop, same class as `visual/current/<slug>/` |
| `git-rebase/<slug>/` | `odoo-git-rebase` | 30d | checkpoint/commit-dump working state; retained as evidence of what the rebase did, no self-cleanup step |
| `forward-port/<slug>/` | `odoo-forward-port` | 30d | same reasoning as `git-rebase/<slug>/` |
| `modules-upgrade/<slug>/` (+ `checkpoint.json`) | `odoo-modules-upgrade` | 30d | same reasoning as `git-rebase/<slug>/` |
| `coding/<slug>-<date>/` (`plan.md`) | `odoo-coding` | 30d | a later review/fix/resume step reads it to avoid recomputing the graph; no self-cleanup step |
| `reviews/<slug>-<date>/` | `odoo-code-review` | 30d | tied to one diff/branch/PR; retained as the review's own evidence |
| `pr-monitoring/<id>.md` | `odoo-pr-monitoring` | 30d | rewritten on every poll tick while monitoring is active - only goes stale once monitoring has genuinely concluded (merged/abandoned) |
| `followups/<slug>.md` | `odoo-draft-followup` command | 30d | terminal deliverable - the run concludes the instant this file is written, so there is no "still alive" window to protect against |
| `visual/videos/<feature>-<timestamp>/` (actually written as the FILE `visual/videos/<feature>-<timestamp>.{mp4,gif}` - the ISOLATE table's trailing `/` is loose notation, not a real directory) | `odoo-demo-recording` | 30d | terminal deliverable, same class as `followups/<slug>.md` |
| `visual/<run_id>/<module>_staging/` | `odoo-doc-illustration` | 24h | ALREADY self-deletes at its own end-of-run staging cleanup (`odoo-doc-illustration/SKILL.md` § End-of-run staging cleanup) - the TTL is a crash-only backstop, same class as `wave/<slug>/` and `visual/current/<slug>/` |
| `i18n/<slug>-<date>/` | `odoo-i18n` | 30d | the i18n recipe already mandates a fresh export on every invocation and forbids reusing a prior run's artifacts (`i18n-mandate-contract.md`) - anything past the very next run is already-superseded, but 30d still gives grace for a delayed review of the translation report |
| the 13 workflow `output_dir` trees (`bids/`, `content/`, `debug/`, `discovery/`, `implement/`, `packaging/`, `positioning/`, `qa/`, `research/`, `sales/`, `support/`, `upgrade-plans/`, `video/`) | `workflow-chaining` (the single runner for all 13) | 30d | same retained-evidence reasoning; swept ONCE generically at Phase 0 for whichever `output_dir` the active workflow declares, rather than thirteen separate call sites |
| `visual/current/<slug>/`, `visual/qa/<slug>/<module>/`, `visual/debug/<slug>/`, `visual/screenshots/<slug>/` | see Clause 2 | 24h / 30d | already covered above - listed here only for completeness of the full ISOLATE enumeration |

No third bound was needed: every eligible row is either (a) already self-deleted at its own
terminal status, in which case it reuses the 24h crash-backstop, or (b) deliberately retained
with no self-cleanup step, in which case it reuses the 30-day bound. A row needing neither
pattern did not arise.

**Sweeping a shared parent directory - exclude siblings by name.** `visual/<run_id>/<module>_staging/`'s
own 24h crash-backstop cannot blindly sweep every immediate child of `visual/` the way the other
rows sweep their OWN dedicated subdir - `visual/` is the shared parent of `baselines/`, `doc/`
(SHARE) AND `current/`, `qa/`, `debug/`, `screenshots/`, `videos/` (four other skills' OWN ISOLATE
trees), none of which are `<run_id>/` dirs. A naive `find <ISOLATE_DIR>/visual/ -mindepth 1
-maxdepth 1 -type d -mmin +1440 -exec rm -rf {} +` would delete those ENTIRE sibling trees the
moment their own top-level directory goes 24h without a NEW child being created inside it - far
worse than the leak this contract exists to close. The sweep MUST exclude all seven known
siblings by name (`! -name baselines ! -name doc ! -name current ! -name qa ! -name debug ! -name
screenshots ! -name videos`) so only an actual `<run_id>/` leftover matches
(`odoo-doc-illustration/SKILL.md` § the exact command). Any future skill adding an EIGHTH named
child directly under `visual/` must add itself to this exclusion list, or `odoo-doc-illustration`'s
crash-backstop would delete that new sibling's tree the same way.

### 3.2 - Not eligible / never eligible / not applicable (excluded, with reasons)

| Subpath | Classification | Reason excluded |
|---|---|---|
| `recon/<slug>-<date>/` (`findings.md`) | Retention-protected, not swept | `scouting-persistence-contract.md` Clause 1 already states "Retention: keep it, never delete" and bounds the file to ~4 KB/run by its own line/char cap - a competing, already-tested SSOT governs this path; sweeping it here would silently contradict that contract instead of reconciling with it |
| `run-<id>.json` | Excluded - mtime is not a reliable liveness signal here | see § 3.3 below |
| `brainstorm/state.json` | Not applicable - no leak | a SINGLE overwritten file with no `<slug>` in its name (unlike every other row in this table) - it does not accumulate one directory per run, so there is nothing to sweep |
| bucket-1 reusable caches (`visual/baselines/`, `visual/doc/`, `designs/`, `plans/`, `gap-analysis/`, `survey/<slug>-<date>/`, `brl/<job-id>/`, `documentation/...`, `brand-tokens.json`, `mockups/`, `glossary.yml`, `cost-config.json`) | NEVER eligible - SHARE tier | see § 3.4 below; not part of the ISOLATE table at all |
| a committed module deliverable (bucket 3) | NEVER eligible | reached only by an explicit copy into the module tree and thereafter lives under git - never resides under `.odoo-ai/` at all, so it is structurally outside this sweep's reach; no ISOLATE row is actually a bucket-3 item (confirmed by inspection - every ISOLATE row is either an agent-authored artifact or a staging area that PRECEDES a bucket-3 copy, never the deliverable itself) |

Every ISOLATE-table row not listed in § 3.2 is covered by § 3.1 - the enumeration is exhaustive
against `state-root-resolution.md`'s own exhaustive ISOLATE table.

### 3.3 - `run-<id>.json`: the write-once-while-still-alive failure mode

`run-<id>.json` is rewritten after every COMPLETED phase (`workflow-chaining` § Resume logic /
`run-harness` §8.3) - so far, the same mtime argument as every other row above would apply.
But a run legitimately PAUSES at a gate ("approve / refine / cancel", an L2 human-confirm, a
`/schedule` cron waiting on an external event) for an UNBOUNDED period while still alive and
resumable - nothing touches the file during that pause, so its mtime goes stale while the run
is NOT abandoned, only slow. Sweeping this file on ANY TTL risks deleting a legitimately-paused,
still-resumable run's ENTIRE blackboard - exactly the "GC worse than the leak" failure mode this
contract exists to prevent, and for the ONE file the workflow resume promise depends on most.
**Decision: `run-<id>.json` is EXCLUDED from this generalized sweep.** A correct fix needs a
non-mtime signal - e.g. only sweeping a `run-<id>.json` whose OWN recorded status is already a
terminal one (DONE/BLOCKED/NEEDS_CONTEXT), never one still mid-flight regardless of mtime - which
this pass does not implement. Recorded here as a known gap, not silently dropped.

### 3.4 - SHARE tier: deliberately out of scope, not merely unaddressed

Every SHARE-tier row in `state-root-resolution.md`'s own table is valuable PRECISELY BECAUSE it
survives across runs/worktrees (a reusable cache or knowledge artifact - bucket 1, by that
file's own "Why" column for each row). A TTL sweep would destroy the exact property that
justifies placing something in SHARE rather than ISOLATE in the first place - "the cache went
stale" is a CONTENT-correctness problem (solved by an explicit staleness/invalidation check,
the same shape as `scouting-persistence-contract.md`'s `target_ref:` staleness clause for
`recon/`, or "pick the most recently modified `designs/*.md`"), never a disk-leak problem (this
contract's actual subject). **Decision: SHARE is OUT OF SCOPE for this GC rule, by design.**
No SHARE row gets a TTL sweep from this contract; a future staleness concern for a specific
SHARE cache belongs in that cache's OWN consumer contract, not here.

### 3.5 - Where the sweep for each § 3.1 row lives

Same pattern as Clause 2, generalized: the owning skill sweeps its OWN subpath, unconditionally,
at its own Phase/Round 0 - BEFORE minting its own run's slug (or, for `workflow-chaining`,
before resolving/using the active workflow's `output_dir` slug) - citing this file rather than
restating the command. Two rows are wired ONCE at a shared chokepoint that already fans out to
many consumers, instead of once per consumer: `worklog/<run-or-slug>/` at `worklog-contract.md`
§ Where it lives (every worklog writer follows that contract, so one edit covers all of them),
and the 13 workflow `output_dir` trees at `workflow-chaining/SKILL.md` Phase 0 (the single
runner for all 13 workflows). Every other § 3.1 row is wired at its own owning skill.
