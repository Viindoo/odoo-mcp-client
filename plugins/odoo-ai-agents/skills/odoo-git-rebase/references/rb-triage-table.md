<!-- Reference for odoo-git-rebase/SKILL.md § Model triage. Loaded as needed.
     Two deterministic tables: EXTRACT (P1) and ADAPT (P8) + bucket-(c) upgrade-scale gate. -->

# Git-Rebase Model Triage - full tables

This table is a REFERENCE used BY the P1 `Explore` subagent (Recon phase). That subagent
reads `git show --stat <sha>` per commit and emits `extract_tier` in `recon.md`. The
orchestrator ONLY records the subagent's tier verdicts - it does NOT read diffs or `git show`
output inline. Resolve a tier by walking the relevant table TOP-DOWN and stopping at the FIRST
match. Record the chosen tier in `plan.md`; the tier is part of the approved plan, not a
runtime improvisation.

The two tiers are decided INDEPENDENTLY. Run the EXTRACT table at P1 against each commit's
complexity as read-only recon; run the ADAPT table at P8 against each commit's adapt
complexity in the worktree. A docstring-only commit may be haiku to EXTRACT but opus to ADAPT
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
| 1 | Commit touches a migration script OR spans >=3 modules OR changes an inheritance axis / a cross-module API contract | **opus** |
| 2 | Commit carries non-trivial logic - a method override, computed/onchange/constraint, ORM hook, a multi-file behavioral change, or a non-obvious bug fix whose "why" requires reasoning across diff + tests | **sonnet** (default) |
| 3 | Commit is docstring / comment / translation-string / label-only, a one-line config flip, or a pure rename with no behavior change | **haiku** |

Constraints:
- **sonnet is the ambiguous-case default.** If two rows seem to apply, the higher row
  (smaller #) wins; if no row clearly applies, use sonnet.
- A large diff that is mechanically simple (mass rename, generated-file churn) can still be
  haiku - judge by the COMPLEXITY OF THE INTENT, not the line count.
- The EXTRACT tier sets the `model` override passed to each `odoo-intent-extractor` launch
  in P2 (the agent's own default is sonnet; the override wins).

---

## Table 2 - ADAPT tier (P8 conflict resolution)

> **SHORT-CIRCUIT (check FIRST):**
> If the commit's outcome is (a) -> `git rebase --skip`; no adapt, no test-forward.
> ADAPT tier for outcome-(a) is recorded as "skip" in `plan.md`.
>
> If the commit's outcome is (d) -> no adapt code; test-forward only at haiku.

Code adapt WRITES and resolves conflicts on the same-version target. It reuses the `odoo-coding`
deterministic tier table (SSOT - do not fork it). Conditions summarized:

| # | Condition (first match wins) | Tier |
|---|---|---|
| 1 | Work-item spans >=3 modules AND is full-stack AND estimated >800 LOC; OR changes an inheritance axis across modules | **fable** |
| 2 | Overrides core `create` / `write` / `unlink`; OR override chain has >=3 entries (`find_override_point`); OR cross-model computed chain / multi-company logic; OR a migration with >1 viable strategy; OR full-stack module with >5 intended files | **opus** |
| 3 | Single-stack AND <=2 intended files AND ~<=50 LOC AND no method override - one field/attr, boilerplate XML view shell, label/string change, security CSV row, or a bucket (a)/(d) test-only forward | **haiku** |
| 4 | Everything else - Extension-M, normal computed/onchange/constraint, single-method override, standard OWL widget, mid-size single-stack module - and ANY case not confidently classified | **sonnet** (default) |

Constraints:
- **fable is NEVER a default and ALWAYS needs explicit human confirmation** (~2x opus cost).
  When a row resolves to fable, the P6 plan gate must call it out on its own line
  (tier, cost estimate, one-line why); the human's plan-gate approval covers it. If the human
  declines fable, downgrade that commit to **opus** and record `<sha>: opus (fable declined)`
  in `plan.md`.
- A bucket (a)/(d) commit needs no adapt code - only test-forward - so it lands at haiku
  even if the source commit was opus-grade.
- A full-stack work-item gets ONE tier applied to both legs by default; a lower frontend
  tier is allowed when the design splits effort, never a higher one.

---

## How the two tables interact per commit

Each commit in `plan.md` carries two tier columns:

| sha | subject | outcome | EXTRACT tier | ADAPT tier | notes |
|-----|---------|---------|-------------|-----------|-------|
| abc1234 | add double-post guard | (b) | sonnet | sonnet | symbol renamed |
| def5678 | rename field across 4 modules | (b) | opus | fable (CONFIRM) | cross-module rename |
| ghi9012 | fix typo in docstring | (a) | haiku | skip | already on base |
| jkl3456 | OWL ListRenderer -> ListController | (c) | sonnet | opus | override-refactored |

The EXTRACT tier drives the P2 dispatch; the ADAPT tier drives the P8 dispatch. The ADAPT
tier MAY be refined once the P3 outcome is known - a commit triaged opus-to-adapt that
classifies as outcome-(a) drops to "skip". Re-record any refinement in `plan.md`.

---

## Bucket-(c) upgrade-scale defer-or-do gate

The ADAPT table picks a MODEL; it does NOT decide whether a cluster is even a mechanical
same-series resolution. A large bucket-(c) cluster that is really an upgrade-scale
RE-IMPLEMENT (a framework component rewrite, not a conflict resolution) MUST be surfaced as
an explicit choice, never silently adapted inside a "mechanical" rebase run.

**When the gate fires.** After P4 classify (outcomes known), estimate each bucket-(c)
cluster's adapt size: source-side LOC delta + a framework-migration flag (e.g. a component
that was refactored wholesale at the new-base, so the source code no longer has a valid
re-apply surface). The gate trips if EITHER holds:
- Estimated >~200 LOC of new OWL/JS (or backend) on the target, OR
- It is a full component / framework rewrite (the source idiom no longer exists at the
  new-base tip, or the override point was removed).

**What to do when it fires - STOP and present (at the P6 plan gate, or mid-run if discovered late):**

```
This cluster (<modules>) looks like an upgrade-scale re-implement, not a mechanical
conflict resolution (~<LOC> LOC / <framework-migration-reason>). Options:
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
| 3 | (b) adapt | The adapt is a multi-file refactor: spans **> 3 files** OR **>= 2 modules** | YES |
| 4 | (b) adapt | The adapt is a full-stack change (touches backend Python/XML AND frontend JS/OWL/SCSS for the same intent) OR moves an OWL component across the legacy<->OWL-2 boundary | YES |
| 5 | (a) already-present / (d) no-longer-relevant | never (no adapt code is written) | NO |
| 6 | (b) adapt | none of rows 2-4 match - a single-file, single-symbol, signature-preserving rename/move resolved to intent | NO (skip - trivial) |

Threshold rationale (roundable): **> 3 files** and **>= 2 modules** are the same magnitude
forward-port and solution-design already treat as the small/large boundary; a model-field or
method-signature change is the "changes public model surface" line; the override-point/full-stack
rows mirror solution-design § When to invoke verbatim. Row 6 is the explicit "very small scale
skips design" the reviewer asked for.
