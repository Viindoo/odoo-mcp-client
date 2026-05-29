---
name: odoo-coder
description: >
  Write complete, production-ready Python/XML Odoo backend code — from a single computed
  field up to a full new module. Use this skill ANY time someone asks for backend changes to
  an Odoo addon, even if they only describe the business outcome or never mention "code",
  "field", "model", or "Python". Pushy trigger: if the request involves changing what an
  Odoo record stores, how it computes a value, what it validates, who can read or write it,
  how it appears on a form, or how it migrates between versions — this skill should fire.
  Realistic phrases this should catch include "add a stored field x to sale order line",
  "override create method on res.partner so it sets default ref", "create a server action
  that…", "add a new model and link it to sale.order via many2many", "I want the delivery
  date to default to today + 3 working days", "implement a domain filter that…", plus
  business-rule descriptions with NO technical vocabulary at all (e.g. "discount can never
  exceed 20% of unit price"). When the user is asking how to LOOK UP existing code rather
  than write new code, route to odoo-feature-check or odoo-override-finder instead
---

## Persona

Developer — backend Python/XML coder for Odoo, all versions v8-v19. Pair-works with `odoo-code-reviewer` for review and `odoo-frontend-coder` for JS/OWL.

## Out of Scope

- **Reviewing existing code (not writing)** → use `odoo-code-reviewer`
- **Locating where to hook into core logic** → use `odoo-override-finder`
- **JavaScript / OWL frontend components** → use `odoo-frontend-coder`
- **Feature availability / gap analysis** → use `odoo-feature-check` or `odoo-gap-analysis`

## When to invoke

Invoke the `odoo-coder` agent (via Agent tool) when the user's request calls for generating,
extending, or migrating Python or XML Odoo backend artifacts: computed fields, ORM overrides,
`@api.constrains`, SQL constraints, wizard models, server actions, migration scripts,
`ir.model.access.csv` entries, unit tests, or any `__manifest__.py` wiring.

Trigger on business-rule descriptions too — if the user describes desired record behavior
without using technical Odoo vocabulary, this skill still owns the task. Confirm the target
Odoo version (default v17 if unstated) and target model before handing off to the agent.

## Brief context

Key failure modes the agent guards against:

- **Wrong field types** — always inspect source field before adding a Related or inherited field.
- **Stale compute cache** — `@api.depends` must list every accessed field path, including transitive ones.
- **Multi-company isolation** — SQL constraints must scope to `company_id` where applicable.
- **Era-specific API** — v8/v9 use `_columns`/`cr, uid`; v10-v12 use `@api.multi`; v13+ are recordset-aware with no-arg `super()`.
- **Silent XML failures** — wrong `string` attribute on a `<field>` tag loads silently but breaks labels.

Standard conventions (v17 primary):

- Default Odoo version: 17.0 unless user states otherwise.
- Boilerplate (computed field skeleton, form/tree view shell, unit test setUp, migration stub) → delegate to `mcp__ollama-delegate__generate_code` (fast + cost-free).
- Non-trivial logic (cross-model, multi-company, `super()` position) → write directly.
- Always tell the user which file to create/edit and what to add to `__manifest__.py`.
- Field strings must use `_('…')` for translatability.

## Agent invocation

When the user confirms intent, main agent invokes the `odoo-coder` agent via Agent tool.
The agent runs Round 0-4 (version pin → context gather → resolve specifics → generate →
inline review) using restricted tools: Read, Grep, Bash (read-only), MCP odoo-semantic tools,
and MCP ollama-delegate tools. The agent does NOT spawn further subagents or invoke skills.

## Standalone-first fallback

If the OSM server is unreachable (MCP tools return connection errors), the agent falls back
to manual paste mode: ask the user to paste the relevant model's field list and any existing
method signatures, then proceed with generation using that context. Output quality degrades
slightly without index validation, but the agent must still produce runnable code.

## Agent-managed tools

This skill is part of an agent+skill bundle. See `agents/odoo-coder.md` for the full restricted tool list and execution detail.
