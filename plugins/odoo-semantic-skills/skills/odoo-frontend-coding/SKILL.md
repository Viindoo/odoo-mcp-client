---
name: odoo-frontend-coding
description: >
  Write complete, production-ready Odoo frontend JS for any supported version — auto-gates
  to legacy `web.Widget`/`AbstractField`/`odoo.define()` (v8–v14) or OWL 2.x
  `patch()`/`useState`/`useService` (v15+) so callers never choose between frameworks.
  Dispatches to the odoo-frontend-coder agent for multi-round MCP enrichment.
  Trigger on: "AbstractField subclass", "Widget.include / odoo.define()", "patch
  FormController / extend ListController", "OWL lifecycle hook / useService", "dashboard
  client action", "register field widget via registry.category", "QWeb template override".
  Also fires on Vietnamese requests: "viết widget OWL", "sửa giao diện form", "thêm field
  widget", "override JS", "viết / sửa SCSS theme đúng design-system Odoo".
  Infer framework from version or API keywords even without "legacy"/"OWL". After generation,
  suggest odoo-debug / odoo-ui-review / odoo-visual-regression to verify (depth rule: do
  not auto-invoke). Backend Python/XML → odoo-backend-coding. Code review → odoo-code-review
---

## Persona

Developer (Odoo frontend, all supported versions). Pair-works with `odoo-backend-coding` for backend
Python/XML and `odoo-code-review` for review.

## Out of Scope

- **Backend Python / XML** (models, views, wizards, security, ORM) → use `odoo-backend-coding`
- **Code review / audit of existing frontend code** → use `odoo-code-review`
- **Deprecation analysis or upgrade planning** → use `odoo-deprecation-audit` or `odoo-version-diff`
- **Verifying the rendered UI / debugging a runtime render error / image regression** → use `odoo-ui-review` / `odoo-debug` / `odoo-visual-regression`

## Phase 0 — Scope preview (1-turn gate)

Before invoking the agent, emit a concise **patch preview** of what you intend to do, then
**stop** for confirmation. The preview names the files the coder will write/modify — the agent
locates the correct module and files itself (via `module_inspect` / Read / Grep) — plus the
`__manifest__.py` assets wiring:

```
Proposed: <brief description of the component / view / asset to be created or modified>.
Files: <module>/static/src/js/<file>.js, <module>/static/src/xml/<file>.xml, __manifest__.py (assets)
OSM: backed | standalone
Proceed? (yes / refine: [feedback] / cancel)
```

- **backed** — the OSM semantic index is reachable and will be used for validation (and is
  **required for any styling/theme work** to ground design tokens); after confirmation the agent
  **writes/applies** the code to those files.
- **standalone** — OSM is unreachable; the agent falls back to disk-grounded mode (Read/Grep
  local source) and still writes files. Say so and lower confidence rather than inventing token names.

Wait for the user's reply before proceeding. This gate applies even if the request arrived
directly (e.g. intake bypass) — it is the single mandatory confirmation checkpoint. On `yes`,
hand off to the agent; on `refine: …`, update the scope and re-emit; on `cancel`, stop.

## When to invoke

Main agent invokes the `odoo-frontend-coder` **agent** (via Agent tool) when the request calls
for writing, extending, or porting Odoo frontend artifacts: legacy `web.Widget` /
`AbstractField` / `Widget.include`, OWL components, `patch()` overrides, QWeb templates, field
widgets registered via `registry.category`, client actions, or asset-bundle entries. The code
may arrive as a pasted block, a `file_path` the agent reads itself, or a business description —
the agent obtains the context accordingly. Because frontend codegen requires version-gating plus
multiple sequential+parallel MCP round-trips (and, for styling, design-token grounding), it runs
as an autonomous agent rather than inline in main.

**Full-stack handoff (do not silently skip the backend).** Many frontend requests pair with a
Python/XML backend piece (a new field the widget displays, a model the dashboard reads). This
skill owns the JS/OWL/SCSS/QWeb only; for the Python/XML side engage `odoo-backend-coding`. Flag the
backend portion in the Phase 0 scope block rather than attempting it.

## Brief context — frontend pitfalls the agent guards against

1. **Wrong era** — `web.Widget`/`odoo.define()` are removed in v16+; OWL `patch()` form changed
   v15→v16 (prototype + name args dropped). The agent version-gates before writing.
2. **OWL reactivity** — `useService` must be reactivity-preserved per version; no bare
   free-identifier arrow handlers; no raw `contenteditable`.
3. **Design-system fidelity** — no hardcoded hex for themeable colors; no self-referential
   `--bs-*` shim. The agent grounds tokens against
   `${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-frontend-fidelity.md` and the runtime computed style.
4. **Indexed examples over memory** — internal hook names and import paths shift between minor
   releases; the agent trusts `find_examples`/`find_override_point` over training knowledge.

## Agent invocation — prompt template

When the user confirms intent (Phase 0 gate passed), the main agent invokes the
`odoo-frontend-coder` agent via the Agent tool. Use the following template **verbatim** as the
agent prompt, filling in the bracketed placeholders:

```
You are the odoo-frontend-coder agent. Produce production-ready Odoo frontend code (JS / OWL /
QWeb / SCSS) for the following request:

REQUEST: [full user request, with target module, Odoo version, and any constraints stated]

Step 0 (ONLY if mcp__odoo-semantic__* tools are available): read .odoo-ai/context.md for the
version, call set_active_version('<version>'), then proceed through the version gate and rounds.
If OSM is unavailable, use the Standalone-first fallback (disk-grounded: Read/Grep the repo,
still write files). Do NOT generate code from memory when OSM is reachable.

Follow the version gate + rounds as defined in your system prompt. Do not spawn subagents or
invoke skills.
```

The agent runs the version gate then Rounds 0-6 (read context → pin version → gather examples →
generate → static verify gate) using its restricted tool allowlist. The agent does NOT spawn
further subagents or invoke skills.

## Standalone-first fallback

When OSM is unreachable, the agent follows the three-tier grounding in
`${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md` — deriving the version from
`.odoo-ai/context.md` or a manifest, locating existing source via Grep/Read, and still writing
the output files. It labels output `grounded: local-source (not OSM-indexed)` when built from
disk, or `OSM unavailable — ungrounded` only when neither OSM nor local source is available.

## Agent-managed tools

This skill is part of an agent+skill bundle. See `agents/odoo-frontend-coder.md` for the full
restricted tool list (including the styling tools `resolve_stylesheet` / `find_style_override`)
and the complete execution detail (version gate, rounds, design-system fidelity gate, output
format, examples).

## Continuation Contract

When you finish, append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next). Additive
output for the depth-0 run-driver - it does not change anything produced above.
