---
name: odoo-perf-audit
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

- **Applying or writing fixes** - this skill produces a findings report only; route to
  `odoo-coding` to implement remediation
- **UI / browser-side slowness** (slow page render, LCP, JS bundle size) - route to
  `chrome-devtools-mcp:debug-optimize-lcp` or `odoo-debug`
- **Deprecated API removal** (upgrade blockers) - route to `odoo-deprecation-audit`
- **General code correctness / security review** - route to `odoo-code-review`
- **Live profiling against a running instance** - requires a live Odoo MCP; this skill
  audits source code statically (with OSM grounding)

## When to use

Use this skill when the user shares Odoo Python, XML, or QWeb source and wants to know
whether it has performance problems, or when a list view / scheduled action / report is
known to be slow and the user wants a root-cause analysis on the source code. The input
may be a pasted block, a file path, a module name, or the output of a prior tool step.

**Reactive mode (dispatched by `odoo-debug`).** When `odoo-debug` routes a specific runtime
performance symptom here (a slow screen/query with a reproduction recipe + version), focus on
root-causing THAT symptom following the scientific method
(`${CLAUDE_PLUGIN_ROOT}/skills/_shared/debug-method.md`) instead of a full module sweep, and emit
the same findings report. A direct invocation with no specific symptom stays a proactive audit.

Do NOT use this skill for live query explain-plans or real-time profiling - those require
a live Odoo instance and a different toolset.

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
- `model_inspect` ★ — Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, extenders, or a summary in one call.
- `resolve_orm_chain` ⊕ — Walk a dotted ORM field path hop by hop to the terminal field type or the exact hop where it breaks.
- `find_examples` — Semantic code search returning real indexed code snippets from the Odoo codebase.
- `validate_depends` ⊕ — Validate compute method's `@api.depends('a.b', ...)` paths; flag `id` and suggest typos.
<!-- END GENERATED TOOLS -->

## Method

Use parallel MCP calls to minimize round trips. Full audit completes in 3-4 rounds.

**Round 0 - Pin version + profile:** `set_active_version` + `set_active_profile`
simultaneously. Then read `.odoo-ai/context.md` if present for module scope.

**Round 1 - Structural scan (parallel):** For each model class in scope:
- `model_inspect(model=<name>, method='fields', odoo_version='17.0')` to collect field `store`, `index`,
  `compute`, `depends`, `related`, `comodel_name` for every field used in domain / order
- `model_inspect(model=<name>, method='methods', odoo_version='17.0')` to enumerate methods for loop detection

Fire all `model_inspect` calls simultaneously - they are independent.

**Round 2 - Deep-dive (parallel):** For each suspicious field or method found in Round 1:
- `entity_lookup(kind='field', ...)` for fields with `related=` or dotted `depends` paths
- `resolve_orm_chain` for every `related=` chain or `mapped('a.b.c')` call
- `validate_depends` for every `@api.depends` declaration on stored computed fields

Fire all Round 2 calls simultaneously.

**Round 3 - Pattern confirmation (parallel, selective):**
- `find_examples(query='read_group instead of loop', odoo_version='17.0')` when ORM-in-loop is detected
- `find_examples(query='prefetch_ids batch search', odoo_version='17.0')` when N+1 browse pattern is detected
- `suggest_pattern(intent='replace ORM loop with read_group', odoo_version='17.0')` when applicable

**Static analysis pass (always):** Regardless of OSM availability, scan the provided
source text for these anti-patterns using inline analysis:

1. **N+1 queries** - `search(`, `browse(`, `.read(`, `.mapped(` inside a `for` loop body
   (indented under a `for rec in ...` line)
2. **Loop-triggered writes** - `rec.write(`, `rec.sudo().write(` inside a `for` loop
3. **Missing prefetch** - sequential `rec.field_a`, `rec.field_b` access in a loop without
   a prior `self.mapped('field_a')` prefetch warm-up call
4. **Unindexed domain fields** - field names appearing in `domain=[...]` or
   `order='field_name'` strings; verify `index=True` via `model_inspect`
5. **Overly broad depends** - `@api.depends('line_ids')` on a stored field where
   `@api.depends('line_ids.price_unit', 'line_ids.qty')` would limit recompute scope
6. **ORM-in-loop vs read_group** - pattern: `for rec in recs: total += rec.line_ids...`
   that could be a single `read_group` call
7. **Heavy QWeb t-foreach** - `<t t-foreach="objects" t-as="o">` blocks that call
   `o.partner_id.name`, `o.currency_id.symbol`, etc. without prefetch warm-up
8. **compute_sudo=True on heavy computations** - stored computed fields using
   `compute_sudo=True` bypass record rules and can mask access-pattern costs

## Output format

```
## Performance Audit Report

**Module / file scope:** <module or file list>
**Odoo version:** <version>
**Grounding:** osm-indexed | local-source (not OSM-indexed) | OSM unavailable - ungrounded
**Issues found:** <N total> (<N> HIGH / <N> MEDIUM / <N> LOW)

### Findings

| # | File | Line | Anti-pattern | Impact | Remediation |
|---|------|------|--------------|--------|-------------|
| 1 | ... | L42 | N+1: browse() inside for-loop | HIGH - O(n) queries | Collect IDs first, single browse(ids) outside loop |
| 2 | ... | L87 | Unindexed field in domain | MEDIUM - full table scan | Add index=True to field definition |
| 3 | ... | ... | ... | ... | ... |

### Finding details

#### #1 - N+1: browse() inside for-loop (HIGH)
**File:** `module/models/sale_order.py` L42
**Pattern:**
```python
for order in self:
    partner = self.env['res.partner'].browse(order.partner_id.id)  # N+1
```
**Why it matters:** Each loop iteration fires a separate SQL SELECT. For 500 records
this is 500 queries vs 1.
**Remediation:** Pre-fetch all partner records outside the loop:
```python
partners = {p.id: p for p in self.mapped('partner_id')}
for order in self:
    partner = partners[order.partner_id.id]
```
**Estimated impact:** HIGH - eliminates O(n) queries; critical for list views and reports.

#### #2 - Unindexed field in domain (MEDIUM)
...

### Summary

- **Highest risk:** <describe the 1-2 findings most likely to cause production incidents>
- **Quick wins:** <findings fixable in < 1 hour>
- **Requires refactor:** <findings needing structural change>

### Estimated total query reduction
<Quantitative estimate where possible, e.g. "N+1 fix alone reduces queries by ~80% for
list view with 100+ records">
```

Impact levels:
- **HIGH** - O(n) query multiplication, mass recompute on every write, full-table scan on
  a large model, or QWeb loop with per-record RPC
- **MEDIUM** - unindexed field on medium-sized model, overly broad depends on frequently
  written model, stored compute without `store=True` stability check
- **LOW** - style-level (redundant `mapped` call, minor prefetch gap on small recordsets)

## Standalone-first fallback

When OSM is unreachable, follow the three-tier grounding in
`${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md`:

- **Tier 2 - Module discovery:** Run `find . -maxdepth 4 -name "__manifest__.py"` to
  discover all modules in scope.
- **Tier 2 - Field index scan:** Run
  `grep -rn "index=True\|index = True" --include="*.py" <module_dirs>` to find indexed
  fields; then grep for domain strings and ORDER BY patterns to check overlap.
- **Tier 2 - N+1 detection:** Run
  `grep -n "\.browse\|\.search\|\.read\b\|\.mapped" --include="*.py" -A2 <module_dirs>`
  and manually inspect whether the calls appear inside a `for` loop body (look for
  consistent indentation one level deeper than a preceding `for` statement).
- **Tier 2 - Depends breadth scan:** Run
  `grep -n "@api.depends" --include="*.py" -rn <module_dirs>` and flag any depends path
  that ends at a Many2many or One2many field without drilling to a specific subfield.
- **Caveat:** Label output `grounded: local-source (not OSM-indexed)`. Index flags and
  computed-field storage confirmation should be re-verified once OSM is online.
- Return `NEEDS_CONTEXT` only if the target file / module is genuinely inaccessible - never
  ask the user to re-supply source code or field definitions that can be grepped.

## Examples

**Example 1:**
Prompt: "This invoice list view takes 30 seconds to load - here is the model code"
Output: Findings table with N+1 browse in `_compute_payment_state`, missing `index=True`
on `invoice_date` used in default domain, and overly broad `@api.depends('line_ids')`
instead of `@api.depends('line_ids.price_subtotal')`. Each finding includes file:line,
impact estimate, and concrete remediation snippet. Does NOT rewrite the file.

**Example 2:**
Prompt: "code này bị N+1 không?" (with a QWeb report template pasted)
Output: Detects `<t t-foreach="docs" t-as="doc">` with `doc.order_line` accessed in inner
loop without prefetch; flags as HIGH impact for reports with > 50 lines. Suggests calling
`docs.mapped('order_line')` before the foreach to warm the prefetch cache.

**Example 3:**
Prompt: "should I add index=True to this field used in search domain?"
Output: Calls `model_inspect` to check current index flag, checks model record volume
estimate from OSM, and recommends index=True if the field is used in user-facing search
domains on models expected to grow beyond ~10k records.

## Continuation Contract

When you finish, append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next). Additive
output for the depth-0 run-driver - it does not change anything produced above.
