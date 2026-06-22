<!-- SSOT snippet. Referenced (not copy-pasted) by odoo-git-rebase (Phase 2 classify),
     odoo-intent-extractor (outcome labeling), and any spawned worker that must classify
     a rebase commit before touching the git index.
     Edit here only; consumers point at ${CLAUDE_PLUGIN_ROOT}/snippets/rb-intent-4outcome.md.
     Same-version analogue of [[fp-intent-4outcome]] - no cross-version API removal;
     the hunt is rename/move/already-present on the base HEAD. -->

# Rebase 4-Outcome Classification Contract (Same-Version)

When rebasing onto a new base HEAD in the **same series**, each commit carries an **intent**
(the behavior/purpose/fix). Before touching any code, classify that intent against the
**current base HEAD** into exactly one of four buckets. This is a **business-level decision**
not a merge decision. Get it wrong here and every downstream step is wasted or destructive.

## The four buckets

| # | Name | Signal | Action |
|---|---|---|---|
| (a) | **Already satisfied** | Base HEAD already ships the behavior; re-applying would duplicate it | Skip the commit - `git rebase --skip`; record reason in `rebase-log.md` |
| (b) | **Adapt and apply** | Intent survives; base renamed, moved, or refactored the symbols the commit touches | Replay intent on the new base idiom; do NOT copy-paste the old diff verbatim |
| (c) | **Re-implement** | Base evolution made the original diff irrelevant or unsafe; intent is still needed | Rebuild from scratch using current base idioms; oracle = forwarded source test |
| (d) | **Drop as irrelevant** | Base design superseded the need entirely; the original problem no longer exists | Drop the commit; record reason + evidence in `rebase-log.md` |

## How to classify - grounding via OSM (mandatory)

**Do not classify from memory or by reading the old diff alone.** Inspect the base HEAD
state for every symbol the commit touches:

```
# 1 - pin version to the shared series (same for source and base)
set_active_version(odoo_version='17.0')   # always explicit

# 2 - check existence and signature on base HEAD
model_inspect(model='account.move', method='summary', odoo_version='17.0')

# 3 - check if the intent is already present (behavior already shipped)
entity_lookup(name='<field_or_method>', kind='<field-or-method>', odoo_version='17.0')
```

- Symbol **present with compatible signature** and intent NOT yet applied -> bucket (b).
- Symbol **renamed or moved** on base (path or name changed) -> bucket (b); adapt to new location.
- Base evolution **made the original approach irrelevant** but intent still needed -> bucket (c).
- Base already ships the exact behavior (merged upstream, backport landed, refactored in) -> bucket (a).
- Original need was tied to a base-specific workaround that base HEAD no longer requires -> bucket (d).

**Bucket (a) evidence gate:** grep/OSM each key identifier (field name, method, XML id,
security rule) on base HEAD. If EXACTLY ONE definition already exists and it covers the
intent, confirmed (a). Any code change required = bucket (b) or (c).

**`odoo_version=` is mandatory** in every OSM call - never omit, never rely on a default.

## Absorption-failure-mode catalog

Each mode below produces NO git conflict marker. Git merges cleanly; the bug surfaces at
runtime or test-run.

| Failure mode | Symptom | Why git is silent |
|---|---|---|
| **Feature already present** | Duplicate field/method/rule; behavior fires twice or ORM raises | Base has the code; re-adding creates a second definition that git accepts |
| **Symbol renamed on base** | Clean merge; `NameError` / `AttributeError` at runtime | Git applies the old name; new name is a different token |
| **Code moved on base** | Patch edits a stale path; moved file is untouched | Git patches the old path (still a valid file or applies via rename detection) |
| **Override point refactored** | `super()` call skips or recurses into wrong chain | Mixin order or class hierarchy changed; old `super()` target no longer in MRO |
| **Manifest depends drift** | `ImportError` or missing model at install time | Base added or removed the dep; `__manifest__.py` diff not in the cherry-pick range |
| **Test symbol removed** | `setUpClass` crash misread as green (skip/error != fail) | Test runner marks errored setup as ERROR, CI may count it as non-failure |

## Duplicate-behavior guard

After replaying a commit (outcome (b) or (c)), run this check before `git add`:

1. **OSM inheritance-chain count (AUTHORITATIVE - HARD FAIL if >1):**
   `entity_lookup(name='<identifier>', kind='<field-or-method>', odoo_version='<series>')` - count definitions
   ACROSS THE FULL INHERITANCE CHAIN (all modules). If the count is >1 the commit hit
   outcome (a) silently: the rebase re-added a behavior that base already ships, potentially
   in a DIFFERENT module (classic core-absorption). This is a BLOCKER - do NOT `git add`.
   A single-module grep cannot catch this case because the duplicate definition may live in
   a different module that the inheritance chain resolves at runtime.

2. **Grep within module path (SECONDARY - locator only):**
   - Field / method: `grep -rn "def <method_name>\|'<field_name>'" <module_path>/`
   - XML id: `grep -rn "id=\"<xmlid>\"" <module_path>/`
   - Security rule: `grep -n "<xmlid>" <module_path>/security/`
   Use grep to locate WHERE in the current module files the definition lives - not to
   determine whether a duplicate exists across modules. A grep scoped to one module path
   will MISS a cross-module redefinition caught by step 1.

3. **XML id and security rule:** confirm the single entry found by grep in step 2 matches
   the OSM count of 1 from step 1.

If OSM count > 1 after replay: the commit hit outcome (a) silently. Remove the duplicate,
switch the log row to (a), and record which base commit (and which module) already provides
the behavior.

## Worklog entry - one row per commit

Append to `rebase-log.md` after classifying each commit:

| Commit SHA | Intent summary | Bucket | Reason | Evidence (file:line or OSM citation) |
|---|---|---|---|---|
| `abc1234` | Add domain check on `sale.order.state` | (b) | Field present; method renamed `_check_state` -> `_validate_state` on base | `entity_lookup sale.order._validate_state @17.0` |
| `def5678` | Guard `res.partner.vat` uniqueness | (a) | Base already ships `_check_vat` constraint post-backport | `grep _check_vat - 1 hit on base HEAD` |
| `ghi9012` | Override `account.move._post` for audit log | (c) | `_post` refactored into `_get_reconciled_invoices` chain; old override unsafe | `model_inspect account.move @17.0 - _post signature changed` |

Do not leave Reason or Evidence blank. "No data" is not acceptable - probe until you have
a citation.

## Cross-references

- [[fp-intent-4outcome]] - cross-version analogue (API removal, replaced hooks, version diff)
- [[rb-phase-detail]] - verbatim git commands: merge-base, `rebase --onto`, conflict loop, range-diff
- [[osm-first-contract]] - full grounding protocol (Tier 1/2/3 fallback when OSM is down)
