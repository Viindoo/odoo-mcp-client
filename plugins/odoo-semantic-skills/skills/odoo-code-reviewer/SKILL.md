---
name: odoo-code-reviewer
description: >
  Review Odoo code (Python, JavaScript, XML, OWL) for bugs, convention violations, security,
  and performance — severity-graded findings, suggested fixes, corrected version. Dispatches
  to the odoo-code-reviewer agent. Fire whenever code is shared with feedback intent, even
  without the word "review". Trigger on: "does this look correct?", "audit this PR",
  "should I worry about N+1?", "before I merge". Also fires on Vietnamese requests: "review
  giúp đoạn này", "kiểm tra code Odoo", "code này có bug không", "có bị N+1 không", "soát
  trước khi merge", "đánh giá PR". Trigger especially on model overrides,
  write/create overrides, computed fields, OWL components, or XML view overrides —
  Odoo-specific failure modes a generic reviewer misses. A false positive is cheap; a missed
  CRITICAL bug in production is expensive. Static analysis only — live render errors →
  odoo-ui-debug. Write new code → odoo-coder. Pre-upgrade audit → odoo-deprecation-audit.
  Override safety → odoo-override-finder
---

## Persona

Developer / Tech Lead reviewing Odoo code with semantic MCP enrichment.

## Out of Scope

- **Writing new code** → route to `odoo-coder`
- **Module-level pre-upgrade audit** → route to `odoo-deprecation-audit`
- **Override safety analysis** → route to `odoo-override-finder`
- **Verifying a render error in a real browser** → route to `odoo-ui-debug`

## When to invoke

Main agent invokes the `odoo-code-reviewer` **agent** (via Agent tool) when Odoo code needs
review. The code may arrive as a pasted block, a `file_path` the agent reads itself, or the
output of a prior tool/step - the agent obtains the code accordingly, it does not require a
human to paste it. The agent runs a multi-step parallel analysis - an immediate self-review first-pass, then
MCP-verified existence and pattern checks - and returns a severity-graded findings table plus
a corrected version. Because review requires multiple sequential+parallel
MCP round-trips, it runs as an autonomous agent rather than inline in main.

## Brief context — Odoo review pitfalls

Key failure modes the agent is aware of:

1. **ORM / N+1** — field reads or `search()` inside `for rec in self` loops; use `mapped()` or prefetch outside loop.
2. **Inheritance breaks** — missing `super()` in `create`/`write`/`unlink` breaks tracking, compute triggers, and downstream module overrides (always CRITICAL).
3. **`@api.depends` errors** — stale or wrong dotted paths; `id` in depends list; constraint on relational field (silently skipped).
4. **Deprecated API** — `@api.multi`, `@api.one` removed in v13/v14; raise at call time, not import.
5. **OWL reactivity** — direct `this.state.items.push()` bypasses OWL reactivity; `position="replace"` in XML views breaks other override chains. These render-level defects should be confirmed visually on a live instance with `odoo-ui-debug` once the static review flags them.
6. **Design-system fidelity (SCSS/OWL styling)** — hardcoded `hex`/`rgba` for themeable colors, or surface tokens chained into Bootstrap `--bs-*` custom properties the target version does not emit at runtime (often via a self-referential shim — a CSS var whose value references itself, a cycle that resolves to empty and flattens the theme). Flag per `${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-frontend-fidelity.md`; confirm at runtime with `odoo-ui-debug`/`odoo-ui-reviewer`, and route the fix to `odoo-frontend-coder` (this reviewer does not write frontend source).

## Agent invocation

When review intent is present (a pasted block, a file path, or code from a prior step), main
invokes the `odoo-code-reviewer` agent via Agent tool. The agent runs review rounds with restricted
tools. The agent does NOT spawn further subagents and does NOT invoke any Skill tool.

## Standalone-first fallback

When OSM (the odoo-semantic-mcp server) is unreachable, the agent falls back to its own static
analysis - reading the code and pattern-matching against internalized Odoo conventions. MCP-enriched
findings (existence verification, `validate_depends`, etc.) are skipped and the output notes
"MCP unavailable — static analysis only".

## Agent-managed tools

This skill is part of an agent+skill bundle. See `agents/odoo-code-reviewer.md` for the full restricted tool list and execution detail.
