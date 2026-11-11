---
name: odoo-perf-audit
argument-hint: "[module/path scope]"
description: >-
  Performance-only static audit of Odoo code: N+1, ORM in loops, indexes
model: inherit
---

## Role

Performance-focused Tech Lead / DBA auditing Odoo code with semantic MCP enrichment.

## Out of Scope

- **Applying or writing fixes** - findings report only; route to `odoo-coding` to implement remediation
- **UI / browser-side slowness** (slow page render, LCP, JS bundle size) - route to `odoo-ui-review` (Lighthouse lens)
- **Deprecated API removal** (upgrade blockers) - route to `odoo-deprecation-audit`
- **General code correctness / security review** - route to `odoo-code-review`
- **Live profiling against a running instance** - requires a live Odoo MCP; this skill audits source code statically (with OSM grounding)

## Reactive mode

When `odoo-debug` routes a specific runtime performance symptom here (slow screen/query with reproduction recipe + version), root-cause THAT symptom following the scientific method (`${CLAUDE_PLUGIN_ROOT}/skills/_shared/debug-method.md`). A direct invocation with no specific symptom stays a proactive audit.

## Diff-scope mode (optional)

**Default (no `SCOPE_FILES`/`CHANGED_SET` supplied): whole-module output, UNCHANGED** - a standalone invocation of this skill is unaffected.

When a caller (e.g. `odoo-code-reviewer`'s own Audit escalation step) briefs this skill with `SCOPE_FILES`/`CHANGED_SET` - the diff's touched files - restrict authoritative findings to those files plus their direct callers (blast-radius: reverse-dependency lookup, or a local grep for call-sites when OSM is unavailable). Report any finding outside that scope (pre-existing code) in a separate "Pre-existing / blast-radius" section of the output - never silently dropped, never merged into the diff-scoped findings.

Findings are graded on the shared scale defined in `${CLAUDE_PLUGIN_ROOT}/snippets/review-severity-rubric.md` - one severity scale governs the whole review-plus-audit pipeline.

## MCP tools

<!-- BEGIN GENERATED TOOLS -->
- `set_active_version` ☆ - Pin a CONCRETE Odoo version (sentinels like 'auto' are rejected; the call doubles as a cheap reachability probe; 24h idle TTL).
- `set_active_profile` ☆ - Pin tenant profile for the session so subsequent calls scope to one customer profile.
- `model_inspect` ★ - Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, extenders, or a summary in one call.
- `resolve_orm_chain` ⊕ - Walk a dotted ORM field path hop by hop to the terminal field type or the exact hop where it breaks.
- `find_examples` - Semantic code search returning real indexed code snippets from the Odoo codebase.
- `validate_depends` ⊕ - Validate compute method's `@api.depends('a.b', ...)` paths; flag `id` and suggest typos.
- `entity_lookup` ★ - Single-entity drill-down by kind discriminator: model, field, method, view, module, pattern, or report - with full inheritance chain and source module.
- `suggest_pattern` - Find curated Odoo design patterns from the catalogue with gotchas and anti-patterns.
<!-- END GENERATED TOOLS -->

## Method

Use parallel MCP calls to minimize round trips. Full audit completes in 3-4 rounds.

**Round 0 - resolve project facts + pin the OSM session:** Resolve series, profile, and module scope per `${CLAUDE_PLUGIN_ROOT}/snippets/project-facts-resolution.md`, then `set_active_version` + `set_active_profile` with the resolved values (fire simultaneously).

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
8. **`compute_sudo` set against its default** - a stored compute runs as superuser by default and a non-stored one as the user. Flag a non-stored compute forced to `compute_sudo=True` (it reads past record rules) and a stored one forced to `False` (its stored value then depends on who triggered the recompute) when no reason is stated; the default itself is not a finding

## Output format

See `${CLAUDE_PLUGIN_ROOT}/skills/odoo-perf-audit/references/output-format.md` for the full findings report template, impact-level definitions, and worked examples.

## Standalone-first fallback

When OSM is unreachable, follow `${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md`:

- **Tier 2 - Module discovery:** `find . -maxdepth 4 \( -name "__manifest__.py" -o -name "__openerp__.py" \)` - glob BOTH descriptor names or the v8-v9 series are silently missed
- **Tier 2 - Field index scan:** `grep -rn "index=True\|index = True" --include="*.py" <module_dirs>`; then grep domain strings and ORDER BY patterns to check overlap
- **Tier 2 - N+1 detection:** `grep -n "\.browse\|\.search\|\.read\b\|\.mapped" --include="*.py" -A2 <module_dirs>`; inspect whether calls appear inside a `for` loop body
- **Tier 2 - Depends breadth scan:** `grep -n "@api.depends" --include="*.py" -rn <module_dirs>`; flag any depends path ending at Many2many or One2many without drilling to a specific subfield
- Label output `grounded: local-source - not OSM-indexed`. Re-verify index flags and computed-field storage once OSM is online.
- Return `NEEDS_CONTEXT` only if target file/module is genuinely inaccessible.

## Continuation Contract

When you finish, append a Continuation Contract block per `${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next). Additive output for the plan runner - it does not change anything produced above.
