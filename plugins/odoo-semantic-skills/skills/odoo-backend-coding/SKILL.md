---
name: odoo-backend-coding
description: >
  Write complete, production-ready Python/XML Odoo backend code — from a single computed
  field up to a full new module. Dispatches to the odoo-coder agent for multi-round MCP
  enrichment. Use this skill ANY time someone asks for backend changes to an Odoo addon,
  even if they only describe the business outcome. Fire when the request involves changing
  what an Odoo record stores, how it computes a value, what it validates, who can read or
  write it, how it appears on a form, or how it migrates between versions — including
  business-rule descriptions with NO technical vocabulary (e.g. "discount can never
  exceed 20% of unit price" or "add a field to sale order line"). Also fires on Vietnamese
  requests: "thêm trường vào model", "tính tự động / computed field", "thêm ràng buộc /
  constraint", "override hàm create/write", "phân quyền đọc ghi", "viết migration",
  "thêm onchange". When the user is asking how to LOOK UP
  existing code rather than write new code, route to odoo-feature-check or
  odoo-override-finding instead
---

## Phase 0 — Scope preview (1-turn gate)

Before invoking the agent, emit a concise **patch preview** of what you intend to do, then
**stop** for confirmation. The preview names the files you will write/modify — the coder
locates the correct module and files itself (via Read/Grep) — plus the `__manifest__.py`
wiring:

```
Proposed: <short description of what will be created or modified>.
Files: <module>/<path>.py, <module>/views/<file>.xml, __manifest__.py (data/depends)
OSM: backed | standalone
Proceed? (yes / refine: [feedback] / cancel)
```

- **backed** — the OSM semantic index is reachable and will be used for validation; after
  confirmation the coder **writes/applies** the code to those files.
- **standalone** - OSM is unreachable; falls back to disk-grounded mode per the
  Standalone-first fallback below (agent reads source itself, then still writes files).

Wait for the user's reply before proceeding. This gate applies even if the request arrived
directly (e.g. intake bypass) — it is the single mandatory confirmation checkpoint. It is a
**preview, not a write-block**: once the user confirms, the coder writes the files to their
correct locations.

---

## Persona

Developer — backend Python/XML coder for Odoo, all versions (v8 onward). Pair-works with `odoo-code-review` for review and `odoo-frontend-coding` for JS/OWL.

## Out of Scope

- **Reviewing existing code (not writing)** → use `odoo-code-review`
- **Locating where to hook into core logic** → use `odoo-override-finding`
- **JavaScript / OWL frontend components** → use `odoo-frontend-coding`
- **Feature availability / gap analysis** → use `odoo-feature-check` or `odoo-gap-analysis`

## When to invoke

Invoke the `odoo-coder` agent (via Agent tool) when the user's request calls for generating,
extending, or migrating Python or XML Odoo backend artifacts: computed fields, ORM overrides,
`@api.constrains`, SQL constraints, wizard models, server actions, migration scripts,
`ir.model.access.csv` entries, unit tests, or any `__manifest__.py` wiring.

Trigger on business-rule descriptions too — if the user describes desired record behavior
without using technical Odoo vocabulary, this skill still owns the task. Resolve the target
Odoo version from `.odoo-ai/context.md` (Round 0 bootstrap) before handing off to the agent;
fall back to v17 only if both the context file and disk manifests yield nothing.

**Full-stack handoff (do not silently skip the frontend).** Many "add a field / module"
requests also need a UI piece — a custom widget, an OWL component, a QWeb/template override, or
an asset-bundle entry. `odoo-backend-coding` owns the Python/XML backend only; it does **not** write
JS/OWL/SCSS. When the task touches the frontend, say so explicitly and engage
`odoo-frontend-coding` for that part (theme/styling work there follows the design-system fidelity
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
- Boilerplate (computed field skeleton, form/tree view shell, unit test setUp, migration stub) → write directly, using `find_examples` output as the template.
- Non-trivial logic (cross-model, multi-company, `super()` position) → write directly, reasoning step by step first.
- Locate the correct module/file yourself (Read/Grep), write the code to those files, and
  report which files you wrote/edited and what you added to `__manifest__.py`.
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
the Standalone-first fallback (disk-grounded: Read/Grep the repo, still write files).
Do NOT generate code from memory when OSM is reachable.

Follow Rounds 1-4 as defined in your system prompt. Do not spawn subagents or invoke skills.
```

The agent runs Rounds 0-4 (version pin → context gather → resolve specifics → generate →
inline review) using its restricted tool allowlist. The agent does NOT spawn further
subagents or invoke skills.

## Standalone-first fallback

When OSM is unreachable, follow the three-tier grounding in
`${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md`:

- **Tier 2 - Disk:** Use `Grep`/`Read` on the module directory to obtain the field list and
  existing method signatures yourself (`grep -rn "class .*models.Model" --include=*.py`;
  `Read models/*.py`). Locate the correct module dir first with
  `find . -maxdepth 4 -name __manifest__.py`. Then write files to those locations exactly as
  in the backed path - do NOT fall back to copy-pasteable blocks unless the repo is genuinely
  inaccessible.
- **Tier 2 - Disk (version fallback):** If `.odoo-ai/context.md` is absent, derive the Odoo
  version from any discovered manifest's `version` field (first two dotted components).
- **Copy-pasteable-only mode** (last resort): emit standalone blocks only when the repo
  itself is unreachable (no read access, no manifest found). Label output
  `grounded: local-source (not OSM-indexed)` when built from disk; use
  `OSM unavailable - ungrounded` only when neither OSM nor local source is available.
- Escalate to the caller (`NEEDS_CONTEXT`) only for secrets/credentials or business decisions
  that no source encodes - never ask a human to paste code, field lists, or manifests.

## Agent-managed tools

This skill is part of an agent+skill bundle. See `agents/odoo-coder.md` for the full restricted tool list and execution detail.
