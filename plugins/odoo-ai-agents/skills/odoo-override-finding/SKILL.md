---
name: odoo-override-finding
description: >
  Find the correct override point and pattern to extend Odoo behavior safely - exact method
  name, module/file location, ready-to-apply `super()` template, existing override chain, and
  version-specific compatibility notes. Use this skill ANY time someone wants to inject
  custom behavior into an existing Odoo flow, even describing only the BEHAVIOR without naming
  a method. Fire on "I want to do X when Y happens in Odoo" - even informal descriptions.
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
- `set_active_version(odoo_version='17.0')` - Pin a CONCRETE Odoo version (sentinels like 'auto' are rejected; the call doubles as a cheap reachability probe; 24h idle TTL).

**Primary tools:**
- `entity_lookup` ★ - Single-entity drill-down by ID: field, method, or view with full inheritance chain and source module.
- `find_override_point` - Show override chain, super() safety guidance, and anti-patterns for a method to find the safest place to inject custom behavior.
- `model_inspect` ★ - Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, extenders, or a summary in one call.
- `suggest_pattern` - Find curated Odoo design patterns from the catalogue with gotchas and anti-patterns.
- `lookup_core_api` - Verify Odoo core API symbol signature, status (stable/deprecated/removed), and replacement.
- `find_examples` - Semantic code search returning real indexed code snippets from the Odoo codebase.
- `api_version_diff` - Structured diff of an API symbol or scope across two Odoo versions: new, changed, removed, deprecated items.
<!-- END GENERATED TOOLS -->

## Context

Getting the override location wrong causes subtle, hard-to-debug issues: overriding at wrong level (internal vs public API), missing `super()` in override chains, using deprecated conventions, conflicting with existing overrides in multi-module stacks.

Era-specific override patterns and scenario-to-pattern mapping:
`${CLAUDE_PLUGIN_ROOT}/skills/odoo-override-finding/references/era-patterns.md`

## Instructions

### Round 0 - Pin the version

`set_active_version(odoo_version=…)` once.

### Round 1 - Enumerate methods (before drilling in)

Call `model_inspect(model=…, method='methods')` to get the full method list with override counts. Critical when the user describes *behavior* to change (e.g. "when an invoice is confirmed") but hasn't named the exact method - the enumeration surfaces candidate names and shows which already have overrides. A count ≥ 3 is a conflict-risk signal. If the user has already named an exact method, skip this round.

Example:
```
model_inspect(model="account.move", method="methods", odoo_version='<version>')
```

### Round 2 - Parallel

`model_inspect(model=…, method='summary')` + `find_override_point(model=…, method=…)` simultaneously.

### Round 3 - Parallel

`entity_lookup(kind='method', model=…, method_name=…)` + `suggest_pattern` + `lookup_core_api(name=<method_name>, odoo_version='<version>')` + `find_examples(query=<override intent>, odoo_version='<version>')` simultaneously:
- `entity_lookup` - full override chain
- `suggest_pattern` - correct Odoo pattern recommendation
- `lookup_core_api` - target method's API status (stable/deprecated/removed) + replacement, grounded in the index not training memory
- `find_examples` - real indexed override implementations to base the code template on

Present a concrete code snippet template pre-filled with the correct class name, method signature, `super()` call, and proper decorator. Include compatibility note for which Odoo versions this pattern is stable in.

> Resource shortcut: once model + method are known, `odoo://{version}/method/{model}/{method}` returns the override chain directly - cheaper than re-issuing `entity_lookup` when you only need the chain.

**Warn explicitly** when:
- Override chain already has 3+ overrides (high conflict risk)
- Target method is marked as internal/private (`_` prefix but not double-underscore)
- Method has changed signature between versions in the user's range - verify with `api_version_diff(symbol=<method_or_scope>, from_version=<lo>, to_version=<hi>)` rather than asserting from memory

## Standalone-first fallback

When OSM is unreachable, follow `${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md`:

- **Tier 2 - Model name:** If the model name is absent, ask the caller once (it is a business decision, not a code artifact - no Tier-2 source encodes "which model the user meant").
- **Tier 2 - Codebase scan:** `grep -rn "class .*<ModelClass>\|_inherit.*=.*'<model.name>'" --include="*.py" .` to find all override sites; then `Read` relevant Python files to extract existing method signatures and decorator usage. Replaces `find_override_point` / `entity_lookup`.
- **Tier 2 - Version:** Read `.odoo-ai/context.md` for `odoo_version`; derive from manifest if absent.
- Still recommend an override point and apply a code template grounded on actual source.
- Label `grounded: local-source (not OSM-indexed)`. Override chain conflict count is approximate (static grep only); confirm once OSM is online.

## Output format and examples

See `${CLAUDE_PLUGIN_ROOT}/skills/odoo-override-finding/references/era-patterns.md` for the full output template and worked examples.

## Continuation Contract

When you finish, append a Continuation Contract block per `${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next). Additive output for the depth-0 run-driver - it does not change anything produced above.
