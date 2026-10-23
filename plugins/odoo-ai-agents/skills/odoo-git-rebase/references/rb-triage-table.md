<!-- Reference for `odoo-git-rebase` § Model triage. Loaded as needed.
     Two deterministic tables: EXTRACT (P1) and ADAPT (P8) + bucket-(c) upgrade-scale gate. -->

# Git-Rebase Model Triage - full tables

**Contents:** Table 1 - EXTRACT tier (P1 intent extraction) - Table 2 - ADAPT tier (P8 conflict resolution) - How the two tables interact per commit - Bucket-(c) upgrade-scale defer-or-do gate - Design-trigger table

This table is a REFERENCE used BY the P1 recon step (git-ops, read-only). That recon pass
reads the change statistics of each commit and emits `extract_tier`
in `recon.md`. The orchestrator ONLY records the recon tier verdicts - it does NOT read
diffs or full commit content inline. Resolve a tier by walking the relevant table TOP-DOWN and stopping at the FIRST
match. Record the chosen tier in `plan.md`; the tier is part of the approved plan, not a
runtime improvisation.

The two tiers are decided INDEPENDENTLY. Run the EXTRACT table at P1 against each commit's
complexity as read-only recon; run the ADAPT table at P8 against each commit's adapt
complexity in the worktree. A docstring-only commit may be haiku to EXTRACT but sonnet to ADAPT
if the new-base idiom for that construct changed significantly. Never reuse one tier as the other.

---

## Table 1 - EXTRACT tier (P1 intent extraction)

> **SHORT-CIRCUIT (check FIRST):**
> If a commit only touches files that are outcome-(a) (patch-id match on new-base) ->
> mark `already_on_base: true`, set extract_tier = haiku (test-forward only), skip
> intent extraction for this commit.

Intent extraction is READ-ONLY analysis: read the commit message, PR/issue, tests, and
OSM-ground the touched symbols at the new-base HEAD (same-version grounding). fable is NOT
available for this phase - intent extraction is never worth fable cost.

| # | Condition (first match wins) | Tier |
|---|---|---|
| 1 | Commit carries logic that needs reasoning - a migration script, a method override, computed/onchange/constraint, ORM hook, a cross-module change (>=2 modules, an inheritance axis, a cross-module API contract), a multi-file behavioral change, or a non-obvious bug fix whose "why" requires reasoning across diff + tests | **sonnet** |
| 2 | Commit states its intent by its message / PR / tests and stays inside ONE module (a straightforward fix or small feature), OR is docstring / comment / translation-string / label-only, a one-line config flip, or a pure rename with no behavior change | **haiku** |

Constraints:
- **sonnet is the ambiguous-case default.** If two rows seem to apply, the higher row
  (smaller #) wins; if no row clearly applies, use sonnet.
- A large diff that is mechanically simple (mass rename, generated-file churn) can still be
  haiku - judge by the COMPLEXITY OF THE INTENT, not the line count.
- Intent extraction is never raised on size, file count or module count alone; this table has no
  opus band.
- The EXTRACT tier sets the `model` override passed to each `odoo-intent-extractor` launch
  in P2 (the agent's own default is sonnet; the override wins).

---

## Table 2 - ADAPT tier (P8 conflict resolution)

> **SHORT-CIRCUIT (check FIRST):**
> If the commit's outcome is (a) -> git-ops skips that commit; no adapt, no test-forward.
> ADAPT tier for outcome-(a) is recorded as "skip" in `plan.md`.
>
> If the commit's outcome is (d) -> no adapt code; test-forward only at haiku.

Code adapt WRITES and resolves conflicts on the same-version target. Its tier comes from
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § Model-tier selection (5.1 checklist, 5.2 opus conditions) - read it there; it is not restated here. Only the
rebase-specific rules follow:

- A bucket (a)/(d) commit needs no adapt code - only test-forward - so it lands at **haiku**
  even if the source commit was opus-grade.
- Every other commit takes the tier the guard resolves for its adapt unit. Size, file count, LOC
  and module count alone never raise it.
- **fable is NEVER a default and ALWAYS needs explicit human confirmation** (about 2x the price of
  the tier below). When the guard resolves a commit to fable, the P6 plan gate must
  call out the TRADEOFF on its own line in plain words, never by tier name - which commit, why it
  needs the deepest reasoning, the cost; the plan-gate approval covers it. On a decline, downgrade
  that commit to **opus** and record `<sha>: opus (fable declined)` in `plan.md`.
- A full-stack adapt unit gets ONE tier applied to both legs by default; a lower frontend
  tier is allowed when the design splits effort, never a higher one.

---

## How the two tables interact per commit

Each commit in `plan.md` carries two tier columns:

| sha | subject | outcome | EXTRACT tier | ADAPT tier | notes |
|-----|---------|---------|-------------|-----------|-------|
| abc1234 | add double-post guard | (b) | sonnet | sonnet | symbol renamed |
| def5678 | rename field across 4 modules | (b) | sonnet | sonnet | cross-module rename |
| ghi9012 | fix typo in docstring | (a) | haiku | skip | already on base |
| jkl3456 | OWL ListRenderer -> ListController | (c) | sonnet | sonnet | override-refactored |

The EXTRACT tier drives the P2 dispatch; the ADAPT tier drives the P8 dispatch. The ADAPT
tier MAY be refined once the P3 outcome is known - a commit triaged sonnet-to-adapt that
classifies as outcome-(a) drops to "skip". Re-record any refinement in `plan.md`.

---

## Bucket-(c) upgrade-scale defer-or-do gate

The ADAPT table picks a MODEL; it does NOT decide whether a cluster is even a mechanical
same-series resolution. A large bucket-(c) cluster that is really an upgrade-scale
RE-IMPLEMENT (a framework component rewrite, not a conflict resolution) MUST be surfaced as
an explicit choice, never silently adapted inside a "mechanical" rebase run.

**When the gate fires.** After P4 classify (outcomes known), estimate each bucket-(c)
cluster's adapt size: source-side LOC delta + a framework-modernisation flag (e.g. a component
that was refactored wholesale at the new-base, so the source code no longer has a valid
re-apply surface). The gate trips if EITHER holds:
- Estimated >~200 LOC of new OWL/JS (or backend) on the target, OR
- It is a full component / framework rewrite (the source idiom no longer exists at the
  new-base tip, or the override point was removed).

**What to do when it fires - STOP and present (at the P6 plan gate, or mid-run if discovered late):**

```
This cluster (<modules>) looks like an upgrade-scale re-implement, not a mechanical
conflict resolution (~<LOC> LOC / <framework-modernisation-reason>). Options:
  (a) defer  - carry as installable:False now; re-implement in a dedicated later effort
               (skip this cluster from the rebase; note in PR that it is deferred)
  (b) do now - estimate ~<X> hours; proceed at the ADAPT tier from Table 2
Choose (a) or (b).
```

Record the choice in `plan.md`. On **(a)**, the cluster is excluded from the rebase range -
mark the relevant commits as `status=deferred` in `rebase-log.md` and note in the PR body.
On **(b)**, proceed normally at the Table-2 tier. Default when the user does not answer:
**(a) defer** - never silently sink unbounded re-implement effort into a run the user
expected to be a mechanical same-series replay.

---

## Design-trigger table

Route a commit to `odoo-solution-design` (P5) when ANY row matches. Evaluate top-down; first
match routes. Genuinely tiny/mechanical commits fall through and skip design.

| # | Outcome bucket | Condition (decidable) | Route to design? |
|---|---|---|---|
| 1 | (c) "do now" | ALWAYS (unchanged from current P5) | YES |
| 2 | (b) adapt | The adapt touches a model FIELD add/remove/type-change, OR changes a method signature, OR overrides/relocates an override point (`create`/`write`/`unlink` or a method whose `find_override_point` chain has >=3 entries) | YES |
| 3 | (b) adapt | The adapt is a REFACTOR in the sense `odoo-solution-design` § When to invoke defines one (mixin extraction, module split/merge, inheritance-axis change) - not the same mechanical edit repeated across several files | YES |
| 4 | (b) adapt | The adapt is a full-stack change (touches backend Python/XML AND frontend JS/OWL/SCSS for the same intent) OR moves an OWL component across the legacy<->OWL-2 boundary | YES |
| 5 | (a) already-present / (d) no-longer-relevant | never (no adapt code is written) | NO |
| 6 | (b) adapt | none of rows 2-4 match - a single-file, single-symbol, signature-preserving rename/move resolved to intent | NO (skip - trivial) |

Where the row conditions come from: rows 2-4 mirror the SAME non-trivial criterion
`odoo-solution-design` applies for its own dispatch - apply it as written. It is qualitative
on purpose: do NOT invent a file-count or module-count threshold here, and do NOT restate the
criterion inline - a second definition is exactly what this skill forbids. A model-field or method-signature
change is the "changes public model surface" line. Row 6 is the explicit "very small scale
skips design".
