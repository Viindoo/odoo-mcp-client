<!-- Reference for odoo-forward-port/SKILL.md § Model triage. Loaded as needed.
     Two deterministic tables: EXTRACT (P0/P1) and ADAPT (P8). -->

# Forward-Port Model Triage - full tables

Triage is INLINE and deterministic. The orchestrator decides the tier itself
(reading `git show --stat <sha>` for every commit involved plus, when the override depth matters, a
single `find_override_point` probe) - it never dispatches an agent to decide a dispatch. Table 1
(EXTRACT) resolves per MODULE BUNDLE (every commit touching that module, grouped by P0); Table 2
(ADAPT) resolves per COMMIT within a module, as before. Resolve a tier by walking the relevant
table TOP-DOWN and stopping at the FIRST match. Record the chosen tier in `plan.md`; the tier is
part of the approved plan, not a runtime improvisation.

---

## Table 1 - EXTRACT tier (P0 triage -> P1 intent extraction)

> **SHORT-CIRCUIT GATE (check FIRST, before walking any tier row - executable AT P0, P2 has not
> run yet):**
> If the module's `installable` field is `False` at the TARGET clean tip -> this module is on the
> **lint-only lane**. Resolve this yourself, right now, via the SAME disk-read Discriminator
> `[[fp-installable-false]]` § Discriminator defines: read `<module>/__manifest__.py` at the target
> ref through `git-toolkit:git-ops` (read-only) - an absent key means installable, an absent FILE
> means the module is not on the clean tip. OSM does NOT carry this flag (`module_inspect` /
> `describe_module` / `check_module_exists` all omit it) - a disk read is the only path. Do NOT wait
> for P2's `manifest_path` artifact (a later phase; it independently re-reads the SAME ref into its
> own file, then records `installable_false` in `merge-log.md` for the module-keyed record - the
> two reads agree because they read the identical target-ref manifest).
> Do NOT walk the tier rows below. Do NOT dispatch extract or adapt logic.
> Only dispatch a haiku lint-fix agent if CI is red due to a syntax error.
> See [[fp-installable-false]] for the full lint-only lane specification.

Intent extraction is read-only analysis: read the commit message, PR/issue, tests, and
OSM-ground the touched symbols at the SOURCE version. fable is not available for this phase.

**Resolved PER MODULE BUNDLE, not per commit (R2a/R2b).** P0 groups commits by module first
(`module -> [ordered sha list]`); walk this table against EVERY commit in ONE module's bundle and
take the HIGHEST-priority row (smallest #) ANY commit in that bundle matches - the bundle's tier is
the worst case across its own commits, never an average and never one row per commit. This is the
SAME table applied to a wider unit; the row conditions below are unchanged.

| # | Condition (first match wins, evaluated against every commit in the module's bundle) | Tier |
|---|---|---|
| 1 | Any commit in the bundle touches a migration script, OR spans >=3 modules, OR changes an inheritance axis / a cross-module API contract | **opus** |
| 2 | Any commit in the bundle carries non-trivial logic - a method override, computed/onchange/constraint, ORM hook, a multi-file behavioral change, or a non-obvious bug fix whose "why" needs reasoning across the diff + tests (and no commit in the bundle matches row 1) | **sonnet** (default) |
| 3 | Every commit in the bundle is docstring / comment / translation-string / label-only, a one-line config flip, or a pure rename with no behavior change | **haiku** |

Constraints:
- **sonnet is the ambiguous-case default (R2c preference: sonnet or haiku when purely
  mechanical).** If two rows seem to apply, the higher row (smaller #) wins; if no row clearly
  applies, use sonnet.
- A large diff that is mechanically simple (mass rename, generated-file churn) can still be
  haiku - judge by the COMPLEXITY OF THE INTENT, not the line count.
- The EXTRACT tier sets the `model` override passed to the ONE `odoo-intent-extractor` subagent
  launch per module in P1 (the agent's own default is sonnet; the override wins).

**Opus human-confirm gate (R2d - Table 1 has no fable band, so opus is the ONLY tier this table can
reach above sonnet/haiku; it is NOT a silent auto-assign.)** When a module's bundle resolves to
row 1 (**opus**), the P4 Plan Mode gate MUST call it out on its own line - module name, tier, and
a one-line why (the SAME format Table 2's fable gate below already uses) - and the human's Plan
Mode approval covers it. If the human declines, downgrade that module's EXTRACT tier to **sonnet**
(fable is not in the EXTRACT band, so there is no intermediate step down from opus) and record
`<module>: sonnet (opus declined)` in `plan.md`. **Suppressed-gate auto-downgrade** (same pattern
`skills/odoo-coding/SKILL.md` § Model triage already uses for its own fable gate - reused here by
pointer, not re-derived): when Plan Mode itself is suppressed (an active `run-<id>` node or a
`WORKTREE_PATH` between-wave context with no interactive human available), AUTO-DOWNGRADE to
sonnet and record `<module>: sonnet (opus auto-downgraded - gate suppressed)` in `plan.md` -
never silently proceed at opus, and never deadlock waiting on a human who is not there.

---

## Table 2 - ADAPT tier (P8 code adapt)

> **SHORT-CIRCUIT GATE (check FIRST, before walking any tier row):**
> If the module's `installable` field is `False` at the TARGET clean tip
> (read `<module>/__manifest__.py` at the target ref - the value P2 resolved into `manifest_path`;
> an absent key means installable) -> this module is on the **lint-only lane**.
> Do NOT walk the tier rows below. Do NOT dispatch adapt logic or business-logic review.
> Only dispatch a haiku lint-fix agent if CI is red due to a syntax error.
> See [[fp-installable-false]] for the full lint-only lane specification.

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
  row resolves to fable, the P4 plan gate must call it out on its own line (tier, cost,
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

The EXTRACT tier drives the P1 dispatch; the ADAPT tier drives the P8 dispatch.
Buckets are assigned in P2 (after extraction), so the ADAPT tier may be refined once the
bucket is known - a commit triaged opus-to-adapt that classifies as bucket (a) drops to haiku
(test-only). Re-record any refinement in `plan.md`.

---

## Bucket-(c) upgrade-scale defer-or-do gate

The ADAPT table picks a MODEL; it does NOT decide whether a cluster is even a mechanical port.
A large bucket-(c) cluster that is really an upgrade-scale RE-IMPLEMENT (a framework migration,
not a port) MUST be surfaced as an explicit choice, never silently adapted inside a "mechanical"
forward-port run.

**When the gate fires.** After P2 classify (buckets known), estimate each bucket-(c) cluster's
adapt size: source-side LOC delta + a framework-migration flag (e.g. v16 legacy widget -> v17+
OWL, QUnit -> Hoot, an API removed wholesale at the target). The gate trips if EITHER holds:
- estimated > ~200 LOC of new OWL/JS (or backend) on the target, OR
- it is a full component / framework rewrite (the source idiom no longer exists at the target).

**What to do when it fires - STOP and present (at the P4 plan gate, or mid-run if discovered
late):**

```
This cluster (<modules>) looks like an upgrade-scale re-implement, not a mechanical port
(~<LOC> LOC / <framework-migration>). Options:
  (a) defer  - carry as installable:False now, re-implement in a dedicated later effort
               (lint-only lane meanwhile - see [[fp-installable-false]])
  (b) do now - estimate ~<X> hours; proceed at the ADAPT tier from Table 2
Choose (a) or (b).
```

Record the choice in `plan.md`. On **(a)**, the cluster moves to the lint-only lane - its modules
go `installable:False` and B2 deferral mode = CARRY (`[[fp-installable-false]]`). On **(b)**,
proceed normally at the Table-2 tier. Default when the user does not answer: **(a) defer** - never
silently sink unbounded re-implement effort into a run the user expected to be mechanical.

---

## Bucket-(c) same-module inherit-view check (view-topology)

A bucket-(c) re-implement (mechanism gone at target - see [[fp-intent-4outcome]]) sometimes has to
land an `ir.ui.view` record. When the record it forwards is itself an INHERITED view (`inherit_id`
set) and the base it inherits from turns out to live in the SAME module as the new record, the
inheritance may be pure indirection carried over from a source-series module split that no longer
exists at the target - the same result would be expressible directly in the base view. This check
catches that shape. It runs at the SAME choke point the 8b bucket-(c) leg already passes through -
once the re-implement lands or modifies the view record, before that module's child worktree
converges back into integration - and is reconfirmed clean at the P10 gate. It mirrors the P7
pre-adapt drift scan's SHAPE exactly (a finding line, triaged into `merge-log.md`, checked before
the gate) rather than inventing a new kind of step; it is a DIFFERENT discriminator
(`VIEW-TOPOLOGY`, not `SYMBOL-BROKEN`) because the defect here is structural redundancy, not a
broken reference.

**Predicate - flag the record V as a defect only when ALL SIX hold:**

1. V has `inherit_id` set, and V's base view B (resolved via `inherit_id`) is declared in the SAME
   module as V. Ground the module comparison with
   `entity_lookup(kind='view', xmlid='<xml_id of B>', odoo_version='<target>')` - its `Module:` line
   is B's owning module; compare against V's own module (already known - it is the module the
   bucket-(c) commit is landing in).
2. V's `mode` is NOT `"primary"`. Grounded: `ir.ui.view.mode`'s own help text - "if extension
   (default), if this view is requested the closest primary view is looked up ... then all views
   inheriting from it ... are applied" vs "if primary, the closest primary view is fully resolved
   ..., and the result is used as if it were this view's actual arch." A `mode="primary"` child is
   a structurally independent resolved view (often referenced by its OWN xml_id elsewhere, e.g. a
   different `view_id` on an action), not a simple patch on the base - out of this predicate
   entirely, not merely spared as an exception.
3. V's `active` field is not explicitly `False`. Grounded: `ir.ui.view.active`'s help text - "if
   this view is inherited: if True, the view always extends its parent; if False, the view
   currently does not extend its parent but CAN be enabled" - a deliberate toggle-off-by-default,
   never a candidate to merge away.
4. V carries no group restriction, checked BOTH ways a restriction can be expressed: (a) V's own
   `groups_id` field is empty - and structurally almost always is, because Odoo's own
   `ir.ui.view._check_groups` ORM constraint (`base` module, `ir_ui_view.py`) RAISES a
   `ValidationError` the moment `groups_id` is set on a view that has `inherit_id` with
   `mode != "primary"`, so a well-formed `mode="extension"` child can never legally carry a
   record-level `groups_id` in the first place; AND (b) no `groups="<module>.<xml_id>"` XML
   ATTRIBUTE appears on the xpath-inserted content inside V's own arch - this arch-level attribute
   (confirmed in core, e.g. `res.groups._update_user_groups_view` builds
   `E.separator(..., groups='base.group_no_one')`) is the ACTUAL mechanism an extension-mode child
   uses for conditional visibility, since (a) is unavailable to it. Do not check only (a) - a check
   that only looks at `groups_id` will never fire on a real extension-mode conditional child, since
   (a) is always empty for one by construction.
5. V's `priority` is either the Odoo default, OR non-default but INERT for this base. Ground with
   `entity_lookup(kind='view', xmlid='<xml_id of B>', odoo_version='<target>')` and read its
   "Extended by" list: if V is the ONLY entry inheriting B, a non-default `priority` has no
   observable ordering effect (nothing to order against) and does not count as conditional; if ONE
   OR MORE other views (any module) also inherit B, a deliberately non-default `priority` IS a
   legitimate exception - it governs xpath-application order among siblings.
6. The commit is bucket (c) per [[fp-intent-4outcome]] and V is what the RE-IMPLEMENT produced or
   modified this run (not a pre-existing same-module inherit stack the run never touched - this
   check scopes to what THIS re-implement lands, not a whole-module retroactive audit).

**Two exceptions this predicate must never fire on (both already covered above, restated for
clarity because a future edit narrowing the predicate to only condition 1 would wrongly flag
both):**

- Base view in a DIFFERENT module - condition 1 excludes it outright; that is the correct and only
  way to extend another module's view, never a defect.
- Same-module inherit view that IS conditional - conditions 2-5 exclude every legitimate
  conditional shape (`mode="primary"`, `active=False`, arch-level `groups="..."`, or a
  multi-sibling `priority`); merging one of these would change behavior, so it must survive
  stacked.

**On a HIT (all six hold) - action: MERGE, unless unsafe (below).** Fold V's xpath-inserted content
into B's arch directly (the same result the two records produce today, expressed in one view),
then DELETE V's record. Never the reverse - never delete B (the PRIMARY/base view): actions,
menus, and other modules' xpaths address it by its OWN `xml_id`, and it must stay addressable
under that id whether or not V survives.

**Merge-unsafe guard - when either holds, do NOT auto-merge or auto-delete; instead KEEP the stack
as-is and flag it for the human at the P10 gate:**

- **External reference exists.** Confirm nothing outside V's own defining file references V's
  `xml_id`: (a) `entity_lookup(kind='view', xmlid='<xml_id of V>', odoo_version='<target>')` - a
  non-empty "Extended by" list means some OTHER view inherits FROM V, so deleting V breaks that
  chain; (b) `impact_analysis` does NOT cover `entity_type='view'` (field/method/model only), so
  for an action `view_id`, a menu, or an `env.ref(...)` call referencing V, invoke
  `git-toolkit:git-ops` (read-only) for a repo-wide grep of V's qualified `xml_id` string outside
  V's own file - any hit means merging is unsafe.
- **Target series is already released.** Deleting a shipped view `xml_id` is a stable-branch-policy
  decision, not a mechanical one - flag for the human rather than deciding it silently, the same
  discipline [[fp-installable-false]] applies to a released module's manifest state.

**Finding-line format (mirrors `SYMBOL-BROKEN`'s shape, distinct discriminator):**

```
VIEW-TOPOLOGY | <V xml_id> inherit_id -> <B xml_id> (same module: <module>) | <file>:<line>
              | action: merge-into-base | evidence: entity_lookup(kind='view', xmlid='<B>',
                odoo_version='<target>') Module match
```

or, when the merge-unsafe guard fires:

```
VIEW-TOPOLOGY | <V xml_id> inherit_id -> <B xml_id> (same module: <module>) | <file>:<line>
              | action: NEEDS-HUMAN (external-reference | target-already-released)
              | evidence: <entity_lookup / git-ops grep result>
```

A clean pass is a valid, desirable result - document it as
`VIEW-TOPOLOGY: clean (0 same-module unconditional inherit stacks found)`.

**Where recorded.** Append the finding as its OWN row in `merge-log.md`, module+commit-keyed and
distinct from the per-commit intent/bucket rows (the same placement discipline the P2
Installable-probe row already uses) - place it under a `## View-topology` heading. Surface every
`merge-into-base` and every `NEEDS-HUMAN` row as an explicit line at the P10 gate presentation, so
the human sees it BEFORE the merge is committed, never only in a findings file read a week later.
