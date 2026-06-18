<!-- Reference for odoo-run-forward-port/SKILL.md § Model triage. Loaded as needed.
     Two deterministic tables: EXTRACT (Phase 0/1) and ADAPT (Phase 4). -->

# Forward-Port Model Triage - full tables

Triage is INLINE and deterministic. The orchestrator decides each commit's tier itself
(reading `git show --stat <sha>` plus, when the override depth matters, a single
`find_override_point` probe) - it never dispatches an agent to decide a dispatch. Resolve a
tier by walking the relevant table TOP-DOWN and stopping at the FIRST match. Record the chosen
tier in `plan.md`; the tier is part of the approved plan, not a runtime improvisation.

There are TWO tables because the two phases do different work: Phase 1 reads and analyzes a
commit (EXTRACT), Phase 4 writes adapted code (ADAPT). A commit can be opus-to-extract and
sonnet-to-adapt, or vice-versa.

---

## Table 1 - EXTRACT tier (Phase 0 triage -> Phase 1 intent extraction)

Intent extraction is read-only analysis: read the commit message, PR/issue, tests, and
OSM-ground the touched symbols at the SOURCE version. **fable is intentionally absent** -
read-only intent work is never worth fable's ~2x-opus cost.

| # | Condition (first match wins) | Tier |
|---|---|---|
| 1 | Commit touches a migration script, OR spans >=3 modules, OR changes an inheritance axis / a cross-module API contract | **opus** |
| 2 | Commit carries non-trivial logic - a method override, computed/onchange/constraint, ORM hook, a multi-file behavioral change, or a non-obvious bug fix whose "why" needs reasoning across the diff + tests | **sonnet** (default) |
| 3 | Commit is docstring / comment / translation-string / label-only, a one-line config flip, or a pure rename with no behavior change | **haiku** |

Constraints:
- **sonnet is the ambiguous-case default.** If two rows seem to apply, the higher row (smaller
  #) wins; if no row clearly applies, use sonnet.
- A large diff that is mechanically simple (mass rename, generated-file churn) can still be
  haiku - judge by the COMPLEXITY OF THE INTENT, not the line count.
- The EXTRACT tier sets the `model` override passed to each `odoo-intent-extractor` Agent-tool
  dispatch in Phase 1 (the agent's own default is sonnet; the override wins).

---

## Table 2 - ADAPT tier (Phase 4 code adapt)

Code adapt WRITES production code on the target platform. It reuses the `odoo-coding`
deterministic tier table verbatim (SSOT - do not fork it). The condition set, summarized:

| # | Condition (first match wins) | Tier |
|---|---|---|
| 1 | Custom-XL: work-item spans >=3 modules AND is full-stack AND estimated >800 LOC; OR it changes an inheritance axis across modules | **fable** |
| 2 | Extension-L: overrides core `create`/`write`/`unlink`; OR override chain has >=3 entries (`find_override_point`); OR cross-model computed chain / multi-company logic; OR a migration with >1 viable strategy; OR full-stack module with >5 intended files | **opus** |
| 3 | Standard / Config: single-stack AND <=2 intended files AND ~<=50 LOC AND no method override - one field/attr, boilerplate XML view shell, label/string change, security CSV row, a bucket (a)/(d) test-only forward | **haiku** |
| 4 | Everything else - Extension-M, normal computed/onchange/constraint, single-method override, standard OWL widget, mid-size single-stack module - and ANY case not confidently classified | **sonnet** (default) |

Constraints:
- **fable is never a default and ALWAYS needs explicit human confirmation** (~2x opus). When a
  row resolves to fable, the Phase 0 plan gate must call it out on its own line (tier, cost,
  one-line why); the human's yes covers it. If the human declines fable, downgrade that
  work-item to **opus** and record `<m>: opus (fable declined)` in `plan.md`. Fable-grade work
  with no approved design doc -> recommend `odoo-solution-design` first.
- A fullstack work-item gets ONE tier applied to both legs by default; a lower frontend tier is
  allowed when the design splits effort, never a higher one.
- A bucket (a)/(d) commit needs no adapt code - only the test forward - so it lands at haiku
  even if the source commit was opus-grade.

---

## How the two tables interact per commit

Each commit in `plan.md` carries two tier columns:

| Commit SHA | Intent summary | Bucket | EXTRACT tier | ADAPT tier |
|---|---|---|---|---|
| `abc1234` | double-post guard on `account.move` | (b) | sonnet | sonnet |
| `def5678` | rename field across 4 modules | (b) | opus | fable (confirm) |
| `ghi9012` | fix typo in docstring | (a) | haiku | haiku (test-only) |

The EXTRACT tier drives the Phase 1 dispatch; the ADAPT tier drives the Phase 4 dispatch.
Buckets are assigned in Phase 2 (after extraction), so the ADAPT tier may be refined once the
bucket is known - a commit triaged opus-to-adapt that classifies as bucket (a) drops to haiku
(test-only). Re-record any refinement in `plan.md`.
