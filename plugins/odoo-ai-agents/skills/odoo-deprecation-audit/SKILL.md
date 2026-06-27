---
name: odoo-deprecation-audit
description: >
  Systematic audit of deprecated Odoo API usage in a codebase before a version upgrade -
  finds `@api.multi`, `osv.osv`, `_columns`, `web.Widget`, `fields.Html` and other
  era-specific APIs that break or warn in the target version, grouped by file with the exact
  replacement and urgency (BREAKING / WARN / STYLE). Resolve the target version from context;
  if unstated, confirm it. Pushy trigger: "upgrade", "migration", "is our code ready for vN",
  "what will break when we move from X to Y", "audit before upgrade", deprecated-symbol
  mentions ("we still have @api.multi everywhere", "ir.values is still used", "OWL migration
  needed"). Also fires on Vietnamese: "rà API lỗi thời trước khi nâng cấp", "code chạy được
  trên vN không", "cái gì sẽ vỡ khi nâng cấp". Trigger even without the word "deprecation". When the user asks ONLY what changed
  between two versions (without auditing their code), route to odoo-version-diff instead. When
  they want to write fresh upgrade-safe code in the target version, route to odoo-coding
---

## Persona
Developer / Tech Lead

## Out of Scope

- Version API diff without code scan → use `odoo-version-diff`
- Fresh code generation in target version → use `odoo-coding`
- Executive risk dashboard → use `odoo-risk-overview`

**Reactive mode (dispatched by `odoo-debug`).** When `odoo-debug` routes a deprecated-API-at-runtime symptom here (removed/changed symbol breaking after upgrade, with reproduction + two versions), root-cause THAT symptom following `${CLAUDE_PLUGIN_ROOT}/skills/_shared/debug-method.md` and point at the replacement. A direct invocation stays a full pre-upgrade deprecation sweep.

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
- `set_active_profile(profile_name='<viindoo_profile from .odoo-ai/context.md>')` - Pin tenant profile for the session so subsequent calls scope to one customer profile.

**Primary tools:**
- `api_version_diff` - Structured diff of an API symbol or scope across two Odoo versions: new, changed, removed, deprecated items.
- `entity_lookup` ★ - Single-entity drill-down by ID: field, method, or view with full inheritance chain and source module.
- `find_deprecated_usage` - Scan the indexed codebase for usages of deprecated API patterns.
- `js_test_inspect` - List JsTestSuite nodes in a module: framework mix (hoot/qunit/tour), file paths, suite sizes, describe/test sample, mounts, tags.
- `lookup_core_api` - Verify Odoo core API symbol signature, status (stable/deprecated/removed), and replacement.
- `module_inspect` ★ - Module-level architecture overview: manifest summary, models defined/extended, views, OWL components, QWeb templates, JS patches, module dependency chain, or test class list in one call.
- `test_base_classes` - Menu of official Odoo test framework base classes (TransactionCase, HttpCase, SavepointCase, Form, etc.) for the given version, with test_type and cursor contract.
<!-- END GENERATED TOOLS -->

## Context

Era-specific deprecation patterns and data priority guidance:
`${CLAUDE_PLUGIN_ROOT}/skills/odoo-deprecation-audit/references/era-reference.md`

**Prioritization:**
- BREAKING (target version removes symbol) → must fix before upgrade
- WARN (deprecated in target, removed in next) → fix in same sprint
- STYLE (old patterns that still work) → fix in follow-up

## Instructions

Use parallel MCP calls - full audit completes in 3 rounds.

**Round 0 - Pin the source version + customer profile:** `set_active_version(odoo_version=<source_version>)`, then `set_active_profile(profile_name=<viindoo_profile from .odoo-ai/context.md>)`. `find_deprecated_usage` honours the session profile, so pinning scopes the scan to the customer's own modules instead of the default Odoo CE scope - otherwise the report is polluted with standard-Odoo deprecations irrelevant to this codebase.

**Round 1 - Parallel:** Call `find_deprecated_usage` + `api_version_diff` simultaneously. These
are completely independent: one scans the codebase, the other fetches the version spec. No
dependency between them.

When the target version is v16 or later, also call `test_base_classes` in the same parallel batch
to get the authoritative base-class mapping for the target version:

```python
test_base_classes(odoo_version='17.0')   # replace with actual target version
```

Use the result to audit test files for legacy base classes. Specifically flag:
- `SavepointCase` used in test files (deprecated alias from v16+, still runs; migrate for
  cleanliness to `TransactionCase` idiom) - WARN
- `cr.commit()` inside `TransactionCase` or `SavepointCase` test bodies - always BREAKING
  (isolation is savepoint rollback; `cr.commit()` is forbidden in the test transaction)
- `SingleTransactionCase` if the target version changed its semantics - WARN

These are deprecated TEST API patterns that `find_deprecated_usage` does not cover directly.
Add them to the output table under a "Test API" group.

**Round 1b - TARGET-version survival pass (upgrade audits only - when a target version is set).**
`find_deprecated_usage` scans for patterns deprecated AT THE SOURCE version; it is BLIND to a
symbol that is stable at source but deprecated/removed at the target (the class that breaks an
upgrade). Ground every own-source ORM symbol at the TARGET:
1. Grep own-source for ORM call-sites (the corpus, not Odoo core):
   `grep -rnE "\.(check_access_rights|check_access_rule|flush|invalidate_cache|get_xml_id|fields_get_keys|_check_recursion|_filter_access_rules|user_has_groups|name_get)\b|@api\.(one|multi)|_columns|fields\.function" --include="*.py" <module_dirs>`
   plus model `_inherit` targets, method overrides, and `env.ref` xml_ids the modules touch.
2. For EACH symbol found, resolve it AT THE TARGET: `lookup_core_api(name='<sym>', odoo_version='<target>')`
   + `api_version_diff(symbol='<sym>', from_version='<source>', to_version='<target>')`. Classify
   `stable-at-source / deprecated-at-target` (WARN) or `stable-at-source / removed-at-target` (BREAKING).
This is the same "ground every symbol at target" principle as
`${CLAUDE_PLUGIN_ROOT}/snippets/fp-symbol-survival-check.md` § 2 - cross-ref it, do not re-derive the mechanism.

**OSM blind-spot fallback (version-range, until the server re-index lands).** OSM currently fails
to resolve the v18 underscore-rename family (`_has_cycle` <- `_check_recursion`, `_filtered_access`
<- `_filter_access_rules*`, `check_access` <- `check_access_rights`+`check_access_rule`) and
`res.users.has_group`/`has_groups`. For these KNOWN renames, fall back to
`${CLAUDE_PLUGIN_ROOT}/skills/odoo-deprecation-audit/references/era-reference.md` (authoritative
version-range table) rather than trusting an OSM MISS as "symbol absent". Scan AT the target.

**Round 2 - Parallel:** Merge symbol lists from Round 1. Call `lookup_core_api` for ALL deprecated/removed symbols in one batch. Every call is independent - fire them all together.

**Round 3 - Parallel:** Call `entity_lookup(kind='method', …)` for ALL changed-signature methods simultaneously. Independent of each other and of Round 2.

**Round 3b - JS patch audit (when migrating from v8-v13 or from v17 to v18+):** Call
`module_inspect(name=<scope>, method='js', odoo_version='<version>')` to enumerate all legacy
`web.Widget`-based patches. Era1 (v8-v13) patches require manual OWL rewrites because the Widget
API was removed in v16. Flag each patch as BREAKING if target version is v14+ and the patch still
references `AbstractField`, `FieldWidget`, or `web.Widget`. Fire in parallel with Round 3 if both
apply.

When the target version is v18 or later, also audit JS test files for framework migration. Call
`js_test_inspect` for each module that has JS tests:

```python
js_test_inspect(module='account', odoo_version='18.0')   # replace with actual module + target version
```

`js_test_inspect` returns the framework mix (hoot / qunit / tour), file paths, and sample
describe/test blocks. Flag any module still running QUnit suites when the target version ships
Hoot as the default framework (v18+) - these require migration to Hoot's `describe/test/expect`
API and `mock_models` convention. Severity: WARN (the tests still execute under a compatibility
shim in early v18 but will break when the shim is removed). Group findings under "JS Test
Framework" in the output table.

Capture file, line, symbol name, and deprecation message from Round 1; merge with Round 2 replacement info before building the output table. Group findings by file so developers can batch-fix one file at a time. Include the exact replacement API with a one-line migration note.

**Era upgrade note:** If migrating from v8/v9, add a separate section "OpenERP Era Rewrites" listing modules requiring full Python 2→3 syntax migration, not just API replacements.

## Standalone-first fallback

When OSM is unreachable, follow `${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md`:

- **Tier 2 - Module discovery:** `find . -maxdepth 4 -name "__manifest__.py"`
- **Tier 2 - Deprecated pattern scan:** `grep -rn "@api.multi\|@api.one\|_columns\|osv\.osv\|orm\.TransientModel\|web\.Widget\|fields\.function\|ir\.values" --include="*.py" <module_dirs>` and `grep -rn "odoo\.define\|AbstractField\|FieldWidget" --include="*.js" <module_dirs>`
- **Tier 2 - Version resolution:** Read `.odoo-ai/context.md` for `odoo_version`. If absent, derive source version from manifest `version` fields.
- Label output `grounded: local-source (not OSM-indexed)`. Confirm exact removal vs. deprecation status once OSM is online.
- Escalate (`NEEDS_CONTEXT`) only if the target upgrade version is genuinely unresolvable from context.

## Output format and examples

See `${CLAUDE_PLUGIN_ROOT}/skills/odoo-deprecation-audit/references/era-reference.md` for the full output table template, migration notes format, and worked examples.

## Continuation Contract

Append a Continuation Contract block per `${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next) - additive run-driver output, changes nothing above.
