<!-- SSOT snippet. Home for the collision-proof slug-derivation rule AND the orphan-sweep
     retention rule shared by every skill that mints one of the four sibling
     visual/*/<slug>/ evidence subpaths (visual/current/<slug>/, visual/qa/<slug>/,
     visual/debug/<slug>/, visual/screenshots/<slug>/). Edit here only; consumers point at
     ${CLAUDE_PLUGIN_ROOT}/snippets/visual-evidence-lifecycle-contract.md. Tier and bucket
     classification of these paths is owned by
     ${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md - not restated here. -->

# Run-scoped visual evidence: slug + retention (SSOT)

Four skills each mint a per-run `<slug>/` evidence directory under `visual/`:
`odoo-visual-regression` (`visual/current/<slug>/`), `odoo-acceptance` via `odoo-qa-tester`
(`visual/qa/<slug>/<module>/`), `odoo-debug` via `odoo-ui-debugger` (`visual/debug/<slug>/`),
and `odoo-ui-review` via `odoo-ui-reviewer` (`visual/screenshots/<slug>/`). Both the slug
ITSELF and the directory's LIFETIME are the same defect class stated twice - a bare intent
slug collides under concurrency, and an evidence directory nobody ever deletes leaks disk
forever - so this file states both rules once for all four.

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
