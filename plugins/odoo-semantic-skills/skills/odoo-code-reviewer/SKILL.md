---
name: odoo-code-reviewer
description: >
  Review Odoo code (Python, JavaScript, XML, OWL) for bugs, convention violations, security,
  and performance — severity-graded findings, suggested fixes, corrected version. Dispatches
  to the odoo-code-reviewer agent. Fire whenever code is shared with feedback intent, even
  without the word "review". Trigger on: "does this look correct?", "audit this PR",
  "should I worry about N+1?", "before I merge". Trigger especially on model overrides,
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

Main agent invokes the `odoo-code-reviewer` **agent** (via Agent tool) when the user shares
existing Odoo code for review. The agent runs a multi-step parallel analysis — first-pass
via Ollama, then MCP-verified existence and pattern checks — and returns a severity-graded
findings table plus a corrected version. Because review requires multiple sequential+parallel
MCP round-trips, it runs as an autonomous agent rather than inline in main.

## Brief context — Odoo review pitfalls

Key failure modes the agent is aware of:

1. **ORM / N+1** — field reads or `search()` inside `for rec in self` loops; use `mapped()` or prefetch outside loop.
2. **Inheritance breaks** — missing `super()` in `create`/`write`/`unlink` breaks tracking, compute triggers, and downstream module overrides (always CRITICAL).
3. **`@api.depends` errors** — stale or wrong dotted paths; `id` in depends list; constraint on relational field (silently skipped).
4. **Deprecated API** — `@api.multi`, `@api.one` removed in v13/v14; raise at call time, not import.
5. **OWL reactivity** — direct `this.state.items.push()` bypasses OWL reactivity; `position="replace"` in XML views breaks other override chains. These render-level defects should be confirmed visually on a live instance with `odoo-ui-debug` once the static review flags them.

## Agent invocation

When user confirms intent (or main detects a code paste with review intent), main invokes
the `odoo-code-reviewer` agent via Agent tool. The agent runs review rounds with restricted
tools. The agent does NOT spawn further subagents and does NOT invoke any Skill tool.

## Standalone-first fallback

When OSM (the odoo-semantic-mcp server) is unreachable, the agent falls back to static analysis only
using `mcp__ollama-delegate__review_code` plus manual pattern matching from the context
window. MCP-enriched findings (existence verification, `validate_depends`, etc.) are skipped
and the output notes "MCP unavailable — static analysis only".

## Agent-managed tools

This skill is part of an agent+skill bundle. See `agents/odoo-code-reviewer.md` for the full restricted tool list and execution detail.
