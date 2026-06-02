---
name: odoo-coder
description: >
  Write complete, production-ready Python/XML Odoo backend code — from a single computed
  field up to a full new module. Dispatches to the odoo-coder agent for multi-round MCP
  enrichment. Use this skill ANY time someone asks for backend changes to an Odoo addon,
  even if they only describe the business outcome. Fire when the request involves changing
  what an Odoo record stores, how it computes a value, what it validates, who can read or
  write it, how it appears on a form, or how it migrates between versions — including
  business-rule descriptions with NO technical vocabulary at all (e.g. "discount can never
  exceed 20% of unit price" or "add a field to sale order line"). Also fires on Vietnamese
  requests: "thêm trường vào model", "tính tự động / computed field", "thêm ràng buộc /
  constraint", "override hàm create/write", "phân quyền đọc ghi", "viết migration",
  "thêm onchange". When the user is asking how to LOOK UP
  existing code rather than write new code, route to odoo-feature-check or
  odoo-override-finder instead
disallowed-tools: Write Edit
---

## Phase 0 — Scope confirm (1-turn gate)

Before invoking the agent or writing any code, emit the following confirmation block and
**stop**. Do not write or edit any file in this turn.

```
Proposed: <short description of what will be created or modified>.
OSM: backed | standalone
Proceed? (yes / refine: [feedback] / cancel)
```

- **backed** — the OSM semantic index is reachable and will be used for validation.
- **standalone** — OSM is unreachable; will proceed via user-paste fallback.

Wait for the user's reply before proceeding. This gate applies even if the request arrived
directly (e.g. intake bypass) — it is the single mandatory confirmation checkpoint.

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

**Full-stack handoff (do not silently skip the frontend).** Many "add a field / module"
requests also need a UI piece — a custom widget, an OWL component, a QWeb/template override, or
an asset-bundle entry. `odoo-coder` owns the Python/XML backend only; it does **not** write
JS/OWL/SCSS. When the task touches the frontend, say so explicitly and engage
`odoo-frontend-coder` for that part (theme/styling work there follows the design-system fidelity
contract). A full-stack change needs **both** specialists — backend here, frontend there — not
one or the other. Flag the frontend portion in your Phase 0 scope block rather than attempting it.

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

## Agent invocation — prompt template (P1)

When the user confirms intent (Phase 0 gate passed), the main agent invokes the `odoo-coder`
agent via the Agent tool. Use the following template **verbatim** as the agent prompt, filling
in the bracketed placeholders:

```
You are the odoo-coder agent. Produce production-ready Python/XML Odoo code for the
following request:

REQUEST: [full user request, with target model, Odoo version, and any constraints stated]

Step 0 (ONLY if mcp__odoo-semantic__* tools are available): call
set_active_version('<version>'), then proceed Rounds 1-4. If OSM is unavailable, use
the Standalone-first fallback. Do NOT generate code from memory when OSM is reachable.

Follow Rounds 1-4 as defined in your system prompt. Do not spawn subagents or invoke skills.
```

The agent runs Rounds 0-4 (version pin → context gather → resolve specifics → generate →
inline review) using its restricted tool allowlist. The agent does NOT spawn further
subagents or invoke skills.

## Standalone-first fallback

If the OSM server is unreachable (MCP tools return connection errors), the agent falls back
to manual paste mode: ask the user to paste the relevant model's field list and any existing
method signatures, then proceed with generation using that context. Output quality degrades
slightly without index validation, but the agent must still produce runnable code.

## Agent-managed tools

This skill is part of an agent+skill bundle. See `agents/odoo-coder.md` for the full restricted tool list and execution detail.
