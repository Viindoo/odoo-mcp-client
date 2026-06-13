---
name: odoo-override-finding
description: >
  Find the correct override point and pattern to extend Odoo behavior safely - exact method
  name, module/file location, ready-to-apply `super()` template, existing override chain, and
  version-specific compatibility notes. Use this skill ANY time someone wants to inject
  custom behavior into an existing Odoo flow, even describing only the BEHAVIOR without naming
  a method. Fire on "I want to do X when Y happens in Odoo" — even informal descriptions.
  Trigger on: "where to hook into sale order confirmation", "run my code when an invoice is
  posted", "is there already someone overriding this method?". Also fires on Vietnamese:
  "chèn xử lý khi xác nhận đơn bán", "chạy code khi hoá đơn được vào sổ", "nên override hàm
  nào cho an toàn". Version-aware: pins target
  version when unspecified and applies era-correct pattern. Check existing code → odoo-code-review.
  API diff between versions → odoo-version-diff or odoo-deprecation-audit
---

## Persona
Developer

## Out of Scope

- Code review of existing override → use `odoo-code-review`
- API diff between versions → use `odoo-version-diff`
- Full code generation for override → use `odoo-coding`

## MCP tools

<!-- BEGIN GENERATED TOOLS -->
> **Pick the right tool first.** Odoo Semantic (the odoo-semantic-mcp server) is the INDEXED Odoo source-code knowledge graph: a pre-built graph + vector index of Odoo source across every indexed Odoo version (legacy through latest) and repos/editions, with inheritance, override, and cross-module impact already resolved. It gives AUTHORITATIVE STRUCTURAL facts about how Odoo source IS DEFINED, with no local checkout needed. Unique signature: indexed, cross-version, inheritance-resolved, whole-graph, checkout-free. It is a STATIC index with NO runtime/live data.
>
> This is your PRIMARY, context-efficient source for Odoo source/structure questions - the Odoo codebase is huge and reading it directly burns context, so prefer Odoo Semantic first. Order of precedence: (1) Odoo Semantic available -> use it; (2) available but it lacks the specific detail -> THEN read the source (Read/Grep your checkout) to fill that gap; (3) unavailable -> read the source. Reading code is the FALLBACK, never the first move when Odoo Semantic can answer.
>
> Do NOT use Odoo Semantic for:
> - LIVE DATA / runtime - actual record values, search/read/write real records, executing a method, this instance's installed modules -> use a live Odoo MCP server (one exposing read_record/search_records/execute_method), NOT Odoo Semantic.
>
> Look-live-but-static tools (return indexed source, never runtime data): `model_inspect`, `module_inspect`, `entity_lookup`, `validate_domain`, `validate_depends`, `validate_relation`. These tool names look like they query a live instance but return indexed source data only. If you need live records, Odoo Semantic is the wrong server.

**Session bootstrap** (call once at session start):
- `set_active_version(odoo_version='17.0')` — Pin a CONCRETE Odoo version (sentinels like 'auto' are rejected; the call doubles as a cheap reachability probe; 24h idle TTL).

**Primary tools:**
- `entity_lookup` ★ — Single-entity drill-down by ID: field, method, or view with full inheritance chain and source module.
- `find_override_point` — Show override chain, super() safety guidance, and anti-patterns for a method to find the safest place to inject custom behavior.
- `model_inspect` ★ — Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, extenders, or a summary in one call.
- `suggest_pattern` — Find curated Odoo design patterns from the catalogue with gotchas and anti-patterns.
- `lookup_core_api` — Verify Odoo core API symbol signature, status (stable/deprecated/removed), and replacement.
- `find_examples` — Semantic code search returning real indexed code snippets from the Odoo codebase.
- `api_version_diff` — Structured diff of an API symbol or scope across two Odoo versions: new, changed, removed, deprecated items.
<!-- END GENERATED TOOLS -->

## Context

Getting the override location wrong causes subtle, hard-to-debug issues:
- Overriding at the wrong level (patching internal methods instead of public API)
- Missing `super()` calls in override chains
- Using deprecated override conventions (`@api.multi`, `@api.one`, OpenERP `_constraints`)
- Conflicting with existing overrides in multi-module stacks

**Era-specific override patterns:**

- **v8/v9 (OpenERP):** Use `osv.osv` or `orm.TransientModel`. Constraints via `_constraints` list.
  No `super()` — use `SUPERCLASS._method(self, cr, uid, ids, ...)`. `@api.*` decorators don't exist.
- **v10–v12 (transition):** `models.Model`, `@api.multi`, `@api.one`, `@api.one` deprecated v13.
  `super()` with new API: `super(MyModel, self).method(...)`.
- **v13+ (modern):** `@api.multi` and `@api.one` removed. All methods implicitly recordset-aware.
  `super()` standard Python 3 style: `super().method(...)`.
- **Frontend/JS v14+ (OWL primary):** Override via `patch()` utility: `import { patch } from "@web/core/utils/patch"`.
  Old `web.Widget` `.include()` pattern deprecated in v14, removed completely in v16+.
  In v13, OWL was introduced but `web.Widget` still coexisted — use `patch()` only for v14+.
- **XML/QWeb:** Override via `xpath` in XML with `position="replace|before|after|attributes"` on
  `<template>` or `<record>` with `inherit_id`.

**Data priority:** `find_override_point` and `entity_lookup(kind='method', odoo_version='<version>')` results reflect
the actual indexed codebase. If MCP says a method's override chain has 4 entries but training
knowledge only knows 2, trust MCP — it has the current state of all indexed repos.

## Instructions

### Round 0 — Pin the version

`set_active_version(odoo_version=…)` once.

### Round 1 — Enumerate methods (before drilling in)

Call `model_inspect(model=…, method='methods')` to get the full list of methods on the target
model with their override counts. This step is critical when the user describes *behavior*
they want to change (e.g. "when an invoice is confirmed") but hasn't named the exact method
yet — the enumeration surfaces the candidate names and shows which methods already have
overrides in the stack. Pick the best candidate method from this list before proceeding.

Example:
```
model_inspect(model="account.move", method="methods", odoo_version='<version>')
```

Output rows look like `action_post : 6 overrides` — a count ≥ 3 is a conflict-risk signal.

If the user has already named an exact method, you may skip this round and go directly to Round 2.

### Round 2 — Parallel

Call `model_inspect(model=…, method='summary')` + `find_override_point(model=…, method=…)`
simultaneously. Both take the model and method name from the user's request — they are
independent of each other.

### Round 3 — Parallel

Call `entity_lookup(kind='method', model=…, method_name=…)` + `suggest_pattern` +
`lookup_core_api(name=<method_name>, odoo_version='<version>')` + `find_examples(query=<override intent>, odoo_version='<version>')`
simultaneously (all independent once Round 2 is in hand):
- `entity_lookup` reveals the full override chain
- `suggest_pattern` recommends the correct Odoo pattern
- `lookup_core_api` verifies the target method's API status (stable / deprecated / removed) + replacement, so any deprecation warning is grounded in the index rather than training memory
- `find_examples` returns real indexed override implementations to base the code template on, instead of writing it from memory
Different scenarios call for different patterns:
   - Business logic change → `_inherit` + `super()` override
   - New computed value → `@api.depends` compute field
   - Pre/post hook → `create`/`write` override
   - Wizard step injection → `TransientModel` with `target_model_id`
   - JS behavior → OWL `patch()` utility (v14+; v13 introduced OWL but `web.Widget` still primary)

Present a concrete code snippet template pre-filled with the correct class name, method signature,
`super()` call, and proper decorator. Include compatibility note for which Odoo versions this
pattern is stable in.

> Resource shortcut: once the model + method are known, `odoo://{version}/method/{model}/{method}` returns the
override chain directly — cheaper than re-issuing `entity_lookup` when you only need the chain.

**Warn explicitly** when:
- The override chain already has 3+ overrides (high conflict risk)
- The target method is marked as internal/private (`_` prefix but not double-underscore)
- The method has changed signature between versions in the user's range — verify with
  `api_version_diff(symbol=<method_or_scope>, from_version=<lo>, to_version=<hi>)` rather than asserting it from memory

## Standalone-first fallback

When OSM is unreachable, follow the three-tier grounding in
`${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md`:

- **Tier 2 - Model name:** If the model name is already in the request or `.odoo-ai/context.md`,
  proceed directly. If it is truly absent, ask the caller once for the model name (it is a
  business decision, not a code artifact - no Tier-2 source encodes "which model the user meant").
- **Tier 2 - Codebase scan:** Once the model name is known, run
  `grep -rn "class .*<ModelClass>\|_inherit.*=.*'<model.name>'" --include="*.py" .` to find
  all override sites, then `Read` the relevant Python files to extract existing method
  signatures and decorator usage. This replaces the `find_override_point` / `entity_lookup`
  MCP calls.
- **Tier 2 - Version:** Read `.odoo-ai/context.md` for `odoo_version`; derive from manifest
  if absent.
- The skill will still recommend an override point and apply a code template grounded on
  the actual source - e.g. `write()` override for create/update hooks, `action_*()` for
  workflow changes, `@api.depends` + compute field for derived fields.
- **Label:** `grounded: local-source (not OSM-indexed)`. Note that override chain conflict
  count is approximate (static grep only); confirm once OSM is online.

## Output format

```
## Override Point: `<method_name>` in `<model_name>`

**Recommended location:** `<module>/<file>.py` (line ~<N>)
**Pattern:** <pattern name>
**Odoo version compatibility:** <version range>
**Era:** <OpenERP v8-9 / Legacy v10-12 / Modern v13+>

### Code template
```python
from odoo import models, api

class <ClassName>(models.Model):
    _inherit = '<model.name>'

    def <method_name>(self, <args>):
        # <brief comment explaining why this override exists>
        result = super().<method_name>(<args>)
        # <custom logic>
        return result
```

### Existing overrides in chain
| Module | File | Notes |
|--------|------|-------|
| ...    | ...  | ...   |

### Conflict risks
<Any conflicts or call-order issues to watch for>

### Compatibility notes
<Version-specific notes — e.g., "super() syntax differs in v8/v9">
```

## Examples

**Example 1:**
Prompt: "where to hook into sale order confirmation to add custom validation"
Output: `_action_confirm` in `sale.order`, code template with `super()` chain, list of existing
overrides (e.g. `sale_stock`, `sale_payment`), warning if chain is long.

**Example 2:**
Prompt: "I want to add custom tax calculation logic when saving an invoice in Odoo 17"
Output: Override `_compute_tax_id` or `write` on `account.move`, code template with usage
context, note about tax constraints if custom tax modules are installed.

## Continuation Contract

When you finish, append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next). Additive
output for the depth-0 run-driver - it does not change anything produced above.
