<!-- SSOT snippet. Phase 3.5 of /odoo-forward-port pipeline. Referenced by
     odoo-forward-port skill. Edit here only.
     Cross-ref: fp-intent-4outcome.md, fp-merge-absorption.md, osm-first-contract.md -->

# Forward-Port Symbol Survival Check (Phase 3.5)

**When to run:** after `git merge --no-commit` (Phase 3), before any adapt work (Phase 4).
**Why this phase exists:** git auto-merge silently carries source-side lines that reference
a symbol (field, method, model, view-id, external-id) that was REMOVED or RENAMED in the
target version - no conflict marker appears because the target branch never touched that line.
The result: lint + install may remain green, but the feature breaks at runtime when execution
reaches that line. This is the most common silent correctness failure in forward-port work.
Real example: `account.account.company_id` -> `company_ids` at v18 (PR #14070).

---

## 1. Scope: which files to check

Check BOTH categories - do NOT limit to files with conflict markers:

1. **Files with conflict markers** (`git diff --check` or `grep -r "<<<<<<" .`)
2. **Merge-clean-but-source-touched files** - files modified by the source commits being
   merged but with no conflict marker in the result. To enumerate:

```bash
# compute merge-base first (use the result as <merge-base> below):
# Same-repo (both refs on origin): MB=$(git merge-base <target-branch> <source-ref>)
# Cross-repo: git remote add source <source-repo-clone-url>  # then fetch
#             MB=$(git merge-base <target-branch> source/<branch>)

# commits being merged (adjust range to your actual source..target range)
git log --name-only --format="" ${MB}..<source-ref> | sort -u | grep -v '^$'
```

Cross-reference that list against the clean working tree files. Category 2 is where
autosilent breaks hide - a line was never touched on the target side, so merge has no
information that the referenced symbol has moved.

---

## 2. Grounding every symbol via odoo-semantic-mcp

For each file in scope, extract every Odoo symbol the merged code references:
fields (`record.<field>`), methods (`Model._<method>`), model names (string literals in
`_inherit`/`comodel_name`/domain), view `ref()` / `xml_id`, `ir.model.fields` names,
manifest `depends` entries, and ORM chain segments.

For **each symbol** call odoo-semantic-mcp against the **target version** to confirm
existence + correct type. The `odoo_version` parameter is MANDATORY on every call:

```
model_inspect(model='account.account', method='summary', odoo_version='18.0')
entity_lookup(kind='field', model='account.account', field='company_ids', odoo_version='18.0')
api_version_diff(symbol='account.account.company_id', from_version='17.0', to_version='18.0')
check_module_exists(name='sale_management', odoo_version='18.0')  # manifest depends entries (module rename/split)
```

A symbol that OSM does not return for the target version is ABSENT at the target unless
disk-fallback (local source read) confirms it in a customer-local module. Absence = broken
reference = blocker, not a warning.

---

## 3. When a symbol is absent or changed at the target

**NEVER leave the auto-merged line unchanged.** Force the intent into one of the
4-outcome buckets defined in [[fp-intent-4outcome]]:

| Situation | Bucket |
|---|---|
| Replacement exists at target (renamed/restructured) | (b) adapt - rewrite reference to new symbol |
| Behavior must be re-implemented; mechanism gone | (c) re-implement per target idiom |
| Feature was a workaround for a limitation the target no longer has | (d) skip + document |
| Target core already handles this natively | (a) core covers it - remove code |

The rule: the adapt diff (in the merge commit per [[fp-merge-absorption]]) MUST reflect
the bucket decision. An auto-merged reference to a dead symbol is merge-commit debt that
will surface as a runtime exception; resolve it here, not later.

---

## 4. Output contract

Produce a symbol-survival finding list before proceeding to Phase 4. Each entry:

```
SYMBOL-BROKEN | <symbol> | <file>:<line> | target-replacement: <replacement or NONE>
               | bucket: <a|b|c|d> | evidence: <OSM call + result summary>
```

An empty list is a valid (and desirable) result - document it as
`SYMBOL-SURVIVAL: clean (0 broken references found)`.

A non-empty list is a BLOCKER for Phase 4 adapt start on those files - resolve each
entry (apply the bucket action) before the adapt subagent touches those files.

---

## Why not defer this to Phase 5 verify-by-behavior

Phase 5 runs the test suite and catches failures where a test exercises the broken path.
Symbol-survival catches broken references in code paths with **no test coverage** - runtime-rare
paths, configuration-only code, XML view references, and `ir.model.fields` lookups that
never appear in any test fixture. Principle #3 of the forward-port design ("no-conflict but
feature dies") mandates grounding at the SYMBOL level here, not only at the behavior level
in Phase 5. Both gates are required; neither replaces the other.
