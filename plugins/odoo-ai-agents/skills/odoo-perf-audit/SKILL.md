---
name: odoo-perf-audit
argument-hint: "[module/path scope]"
description: >
  Audit Odoo Python/XML/QWeb code for performance problems - findings report with file:line,
  estimated impact, and remediation steps. Does NOT rewrite code. Covers: N+1 queries
  (search/browse/read/mapped inside Python loops), missing prefetch, unindexed fields in search
  domains or ORDER BY, expensive stored computed fields with overly broad depends, read_group
  misuse, ORM-in-loop, and heavy t-foreach in QWeb. Triggers on: "why is my Odoo slow", "N+1
  in this model", "perf audit", "optimize this code", "list view takes forever", "computed field
  is slow", "should I add index=True", "t-foreach performance", "batch this query". Vietnamese
  triggers: "code này bị N+1 không", "audit hiệu năng Odoo", "tối ưu truy vấn", "field này có
  nên index không", "vòng lặp ORM", "computed field chậm". Does not apply fixes - route to
  odoo-coding after audit
model: inherit
---

## Persona

Performance-focused Tech Lead / DBA auditing Odoo code with semantic MCP enrichment.

## Out of Scope

- **Applying or writing fixes** - findings report only; route to `odoo-coding` to implement remediation
- **UI / browser-side slowness** (slow page render, LCP, JS bundle size) - route to `chrome-devtools-mcp:debug-optimize-lcp` or `odoo-debug`
- **Deprecated API removal** (upgrade blockers) - route to `odoo-deprecation-audit`
- **General code correctness / security review** - route to `odoo-code-review`
- **Live profiling against a running instance** - requires a live Odoo MCP; this skill audits source code statically (with OSM grounding)

## When to use

When the user shares Odoo Python, XML, or QWeb source and wants performance analysis, or when a list view / scheduled action / report is known slow and wants source-code root-cause analysis.

**Reactive mode (dispatched by `odoo-debug`).** When `odoo-debug` routes a specific runtime performance symptom here (slow screen/query with reproduction recipe + version), root-cause THAT symptom following the scientific method (`${CLAUDE_PLUGIN_ROOT}/skills/_shared/debug-method.md`). A direct invocation with no specific symptom stays a proactive audit.

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

**Primary tools:**
- `model_inspect` ★ - Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, extenders, or a summary in one call.
- `resolve_orm_chain` ⊕ - Walk a dotted ORM field path hop by hop to the terminal field type or the exact hop where it breaks.
- `find_examples` - Semantic code search returning real indexed code snippets from the Odoo codebase.
- `validate_depends` ⊕ - Validate compute method's `@api.depends('a.b', ...)` paths; flag `id` and suggest typos.
<!-- END GENERATED TOOLS -->

## Method

Use parallel MCP calls to minimize round trips. Full audit completes in 3-4 rounds.

**Round 0 - Pin version + profile:** `set_active_version` + `set_active_profile` simultaneously. Read `.odoo-ai/context.md` if present for module scope.

**Round 1 - Structural scan (parallel):** For each model in scope, fire simultaneously:
- `model_inspect(model=<name>, method='fields', odoo_version='<version>')` - collect `store`, `index`, `compute`, `depends`, `related`, `comodel_name` for fields used in domain/order
- `model_inspect(model=<name>, method='methods', odoo_version='<version>')` - enumerate methods for loop detection

**Round 2 - Deep-dive (parallel):** For each suspicious field/method from Round 1:
- `entity_lookup(kind='field', ...)` for fields with `related=` or dotted `depends`
- `resolve_orm_chain` for every `related=` chain or `mapped('a.b.c')` call
- `validate_depends` for every `@api.depends` on stored computed fields

**Round 3 - Pattern confirmation (parallel, selective):**
- `find_examples(query='read_group instead of loop', odoo_version='<version>')` when ORM-in-loop detected
- `find_examples(query='prefetch_ids batch search', odoo_version='<version>')` when N+1 browse pattern detected
- `suggest_pattern(intent='replace ORM loop with read_group', odoo_version='<version>')` when applicable

**Static analysis pass (always):** Scan source for these anti-patterns:

1. **N+1 queries** - `search(`, `browse(`, `.read(`, `.mapped(` inside a `for` loop body
2. **Loop-triggered writes** - `rec.write(`, `rec.sudo().write(` inside a `for` loop
3. **Missing prefetch** - sequential `rec.field_a`, `rec.field_b` access in a loop without prior `self.mapped('field_a')` prefetch warm-up
4. **Unindexed domain fields** - field names in `domain=[...]` or `order='field_name'` strings; verify `index=True` via `model_inspect`
5. **Overly broad depends** - `@api.depends('line_ids')` on a stored field where `@api.depends('line_ids.price_unit', 'line_ids.qty')` would limit recompute scope
6. **ORM-in-loop vs read_group** - `for rec in recs: total += rec.line_ids...` that could be a single `read_group` call
7. **Heavy QWeb t-foreach** - `<t t-foreach="objects" t-as="o">` blocks calling `o.partner_id.name`, `o.currency_id.symbol`, etc. without prefetch warm-up
8. **compute_sudo=True on heavy computations** - stored computed fields using `compute_sudo=True` bypass record rules and can mask access-pattern costs

## Output format

See `${CLAUDE_PLUGIN_ROOT}/skills/odoo-perf-audit/references/output-format.md` for the full findings report template, impact-level definitions, and worked examples.

## Standalone-first fallback

When OSM is unreachable, follow `${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md`:

- **Tier 2 - Module discovery:** `find . -maxdepth 4 -name "__manifest__.py"`
- **Tier 2 - Field index scan:** `grep -rn "index=True\|index = True" --include="*.py" <module_dirs>`; then grep domain strings and ORDER BY patterns to check overlap
- **Tier 2 - N+1 detection:** `grep -n "\.browse\|\.search\|\.read\b\|\.mapped" --include="*.py" -A2 <module_dirs>`; inspect whether calls appear inside a `for` loop body
- **Tier 2 - Depends breadth scan:** `grep -n "@api.depends" --include="*.py" -rn <module_dirs>`; flag any depends path ending at Many2many or One2many without drilling to a specific subfield
- Label output `grounded: local-source (not OSM-indexed)`. Re-verify index flags and computed-field storage once OSM is online.
- Return `NEEDS_CONTEXT` only if target file/module is genuinely inaccessible.

## Continuation Contract

When you finish, append a Continuation Contract block per `${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next). Additive output for the run-harness - it does not change anything produced above.
