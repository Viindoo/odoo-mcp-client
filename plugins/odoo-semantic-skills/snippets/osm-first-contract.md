<!-- SSOT snippet. Referenced (not copy-pasted) by every skill/agent that writes Odoo
     code or makes an Odoo capability claim, and injected verbatim into every spawned
     worker brief (wave WI workers, workflow-chaining fan-out workers, conflict resolver).
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
OSM call OR a direct source read — never asserted from memory:

- `set_active_version` first (pin the target version), then
- `model_inspect`, `entity_lookup`, `check_module_exists`, `lookup_core_api`,
  `module_inspect` — as appropriate to the claim.
- When OSM is reachable but the SPECIFIC entity is not in the index (a customer-local
  custom module/model), `Read`/`Grep` the local source for that entity instead - a
  Tier-1 MISS per `disk-fallback-protocol.md` - and keep OSM for everything it does
  cover (`grounded: osm + local-source (hybrid)`). An index miss is not proof of
  absence when a local repo is available to check.

An unverifiable claim is flagged as an assumption, not stated as fact.

Having verified existence (above), do not re-probe field/method PRESENCE at runtime with `hasattr`/`getattr`-default/`try...except AttributeError` - resolve it via dep closure; full rule: `${CLAUDE_PLUGIN_ROOT}/snippets/field-presence-resolution.md`.

## 2. Reuse before you write

Before generating any non-trivial Odoo artifact, find what already exists and prefer it:

- **Backend (Python/XML/ORM):** call `suggest_pattern(intent=…)` **and**
  `find_examples(query=…)` *before* writing. Prefer the indexed pattern/snippet over
  hand-written code. `find_override_point` when hooking into existing behavior.
- **Frontend (JS/OWL/SCSS/QWeb):** call `find_examples(query=…)` for real widget/
  component patterns, and `resolve_stylesheet` / `find_style_override` to discover the
  **real design tokens and style origins for the target version** (see
  `skills/_shared/odoo-frontend-fidelity.md`). Never invent token or selector names.

If the index genuinely has nothing relevant, say so explicitly — then write.

## 3. Validate before you declare done

- **Backend:** any generated `@api.depends`, `domain=`, `related=` chain, or relational
  assumption MUST pass `validate_depends` / `validate_domain` / `resolve_orm_chain` /
  `validate_relation`. Any BROKEN/MISMATCH is a blocker, not a warning. Then run the static
  code-quality gate `${CLAUDE_PLUGIN_ROOT}/scripts/verify-backend.sh <changed .py>` (reproduces
  the CI `pylint-odoo` checks) and include `/test_lint` in the test run (see `ODOO-TESTING.md`).
  Note: OSM `lint_check` is a fuzzy V0 screen (it can miss e.g. SQL injection) — it is a hint,
  **not** the gate; do not treat a clean `lint_check` as a passing quality gate.
- **Frontend:** verify against the running instance — read `getComputedStyle` to confirm
  tokens resolve (not empty/cyclic) and the UI matches the mockup; recompile assets and
  re-read, never trust that an edit "took" (see `skills/_shared/odoo-frontend-fidelity.md`).
- **Instance / CLI:** before emitting any `odoo-bin` command, resolve the target version's
  real CLI with `cli_help` — do not assume one version's flags apply to another (see
  `INSTANCE-LIFECYCLE.md`, `ODOO-TESTING.md`).

## 4. Standalone fallback: read the source, don't ask the human

If OSM is unreachable, you are **not** reduced to generating from memory, and you do **not**
ask a human to paste data you can fetch yourself. Reading the real source is a legitimate
grounding path. **"Unreachable" includes a tool call that times out, hangs, or returns a
transport error - not only a clean connection-refused.** A timed-out OSM call counts as a
Tier-1 failure: drop to Tier 2 (read the source) immediately; never sit and re-wait on a
stalled server, and never treat a hang as a reason to ask the human. After repeated OSM
timeouts in a session, trip the circuit-breaker (see `disk-fallback-protocol.md`) and stop
calling OSM for the rest of the session. Follow the three-tier order in
`${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md`:

1. **Tier 2 - disk first.** `Read`/`Grep`/`Bash` the local addons, or `WebFetch` the official
   Odoo source for the target version (and, only if this environment happens to expose a live
   ERP MCP, enrich from it as a bonus - never assume one exists). Output built this way is
   **grounded against real source** (label `grounded: local-source (not OSM-indexed)`), one
   notch below OSM - it is NOT `ungrounded`.
2. **Tier 3 - training-memory only as a last resort**, when no index, no readable repo, no live
   instance, and no network are available. Then do not generate silently: state
   `OSM unavailable - ungrounded` in your output, lower confidence, and make that caveat survive
   into the final artifact your orchestrator returns.

Grounded-by-default (Tier 1 or Tier 2); ungrounded-but-flagged (Tier 3) only as a true last
resort. Escalate to a human (`NEEDS_CONTEXT`) solely for secrets or business decisions no
source encodes - never to re-supply code, fields, manifests, changelogs, or CRM data.

## 5. This contract is enforced (not just advisory)

For **spawned workers** (wave WI workers, workflow-chaining fan-out, code/UI agents), a
`SubagentStop` hook (`hooks/enforce-grounding.sh`) reads the worker's own transcript and makes
§1/§4 a checkable invariant: if your artifact claims `grounded: osm` but you made **zero**
`mcp__odoo-semantic__*` calls, the stop is **blocked** and you are asked to either actually
verify or relabel honestly (`grounded: local-source` / `OSM unavailable - ungrounded`). The
label must be *earned* from real calls, not asserted. Two softer gaps raise a **non-blocking
note** (not a block): backend code written with OSM reachable but the ORM validators skipped;
and backend `.py` written with zero OSM calls and no grounding label at all (the silent case) —
the note asks you to ground it, or to state plainly it is pure-Python/standalone so the gate is
satisfied. Only the provable lie (`grounded: osm` with zero calls) is blocked. Honest grounding
is cheaper than a blocked stop — make the calls.
