---
name: odoo-code-reviewer
description: >
  Review Odoo code (Python, JavaScript, XML, OWL) for bugs, convention violations, security
  issues, and performance problems — with severity-graded findings, suggested fixes, and a
  corrected version. Use this skill ANY time someone shares Odoo code and wants feedback —
  even if they don't say "review". Pushy trigger: if the user pastes code AND any of these
  signals appear, fire this skill — "review this", "why isn't this working?", "is this the
  right way?", "does this look correct?", "I'm not sure about this implementation", "check my
  Odoo code", "audit this PR", "convention check", "performance review", "is this the canonical
  Odoo pattern?", "OWL component review", "QWeb template check", "smell test this method",
  "before I merge this…", "should I worry about N+1 here?". Trigger especially aggressively
  when the code has model overrides, write/create overrides, computed fields, OWL components,
  or XML view overrides — these have specific Odoo failure modes a generic reviewer will miss.
  A false positive trigger here is cheap; missing a CRITICAL bug in production Odoo is expensive.
  When the user asks how to WRITE new code rather than review existing code, route to odoo-coder
  instead. When they ask for a module-level pre-upgrade audit, route to odoo-deprecation-audit
  instead. When they ask whether a method is safe to override at all, route to odoo-override-finder
---

## Persona

Developer / Tech Lead reviewing Odoo code with semantic MCP enrichment.

## Out of Scope

- **Writing new code** → route to `odoo-coder`
- **Module-level pre-upgrade audit** → route to `odoo-deprecation-audit`
- **Override safety analysis** → route to `odoo-override-finder`

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
5. **OWL reactivity** — direct `this.state.items.push()` bypasses OWL reactivity; `position="replace"` in XML views breaks other override chains.

## Agent invocation

When user confirms intent (or main detects a code paste with review intent), main invokes
the `odoo-code-reviewer` agent via Agent tool. The agent runs review rounds with restricted
tools. The agent does NOT spawn further subagents and does NOT invoke any Skill tool.

## Standalone-first fallback

When OSM (odoo-semantic MCP) is unreachable, the agent falls back to static analysis only
using `mcp__ollama-delegate__review_code` plus manual pattern matching from the context
window. MCP-enriched findings (existence verification, `validate_depends`, etc.) are skipped
and the output notes "MCP unavailable — static analysis only".

## Agent-managed tools

This skill is part of an agent+skill bundle. See `agents/odoo-code-reviewer.md` for the full restricted tool list and execution detail.
