<!-- SSOT snippet. Referenced (not copy-pasted) by every skill/agent that writes Odoo
     code or makes an Odoo capability claim, and injected verbatim into every spawned
     worker brief (wave WI workers, workflow-runner fan-out workers, conflict resolver).
     Edit here only; consumers point at ${CLAUDE_PLUGIN_ROOT}/snippets/osm-first-contract.md. -->

# OSM-First Grounding Contract

You are working in an Odoo context. **OSM (the `odoo-semantic` MCP server) and the live
runtime are the ground truth — your training memory is not.** Each Odoo version differs
(models, fields, CLI flags, asset bundles, Bootstrap version, design tokens), so a fact
that is true for one version may be false for another. Obey this contract for any Odoo
code you write or any claim you make about what Odoo does.

## 1. Verify before you claim (every stack)

Any statement that an Odoo model / field / method / module / edition / CLI flag / design
token *exists*, *has a given signature*, or *behaves a certain way* MUST be backed by an
OSM call — never asserted from memory:

- `set_active_version` first (pin the target version), then
- `model_inspect`, `entity_lookup`, `check_module_exists`, `lookup_core_api`,
  `module_inspect` — as appropriate to the claim.

An unverifiable claim is flagged as an assumption, not stated as fact.

## 2. Reuse before you write

Before generating any non-trivial Odoo artifact, find what already exists and prefer it:

- **Backend (Python/XML/ORM):** call `suggest_pattern(intent=…)` **and**
  `find_examples(query=…)` *before* writing. Prefer the indexed pattern/snippet over
  hand-written code. `find_override_point` when hooking into existing behavior.
- **Frontend (JS/OWL/SCSS/QWeb):** call `find_examples(query=…)` for real widget/
  component patterns, and `resolve_stylesheet` / `find_style_override` to discover the
  **real design tokens and style origins for the target version** (see
  `odoo-design-system-fidelity.md`). Never invent token or selector names.

If the index genuinely has nothing relevant, say so explicitly — then write.

## 3. Validate before you declare done

- **Backend:** any generated `@api.depends`, `domain=`, `related=` chain, or relational
  assumption MUST pass `validate_depends` / `validate_domain` / `resolve_orm_chain` /
  `validate_relation`. Any BROKEN/MISMATCH is a blocker, not a warning. Run `lint_check`.
- **Frontend:** verify against the running instance — read `getComputedStyle` to confirm
  tokens resolve (not empty/cyclic) and the UI matches the mockup; recompile assets and
  re-read, never trust that an edit "took" (see `odoo-design-system-fidelity.md`).
- **Instance / CLI:** before emitting any `odoo-bin` command, resolve the target version's
  real CLI with `cli_help` — do not assume one version's flags apply to another (see
  `INSTANCE-LIFECYCLE.md`, `ODOO-TESTING.md`).

## 4. Standalone fallback is never silent

If OSM is unreachable, do **not** quietly generate from memory. State
`OSM unavailable — ungrounded` in your output, lower your confidence, and make that
caveat survive into the final artifact your orchestrator returns. Grounded-by-default;
ungrounded-but-flagged only as a last resort.
