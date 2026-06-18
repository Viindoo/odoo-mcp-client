---
name: odoo-code-review
description: >
  Review Odoo code (Python, JavaScript, XML, OWL) for bugs, convention violations, security,
  and performance - severity-graded findings, suggested fixes, corrected version. Dispatches
  to the odoo-code-reviewer agent. Fire whenever code is shared with feedback intent, even
  without the word "review". Trigger on: "does this look correct?", "audit this PR",
  "should I worry about N+1?", "before I merge". Also fires on Vietnamese requests: "review
  giúp đoạn này", "kiểm tra code Odoo", "code này có bug không", "có bị N+1 không", "soát
  trước khi merge", "đánh giá PR". Trigger especially on model overrides,
  write/create overrides, computed fields, OWL components, or XML view overrides -
  Odoo-specific failure modes a generic reviewer misses. A false positive is cheap; a missed
  CRITICAL bug in production is expensive. Static analysis only - live render errors →
  odoo-debug. Write new code → odoo-coding. Pre-upgrade audit → odoo-deprecation-audit.
  Override safety → odoo-override-finding
---

## Persona

Developer / Tech Lead reviewing Odoo code with semantic MCP enrichment.

## Out of Scope

- **Writing new code** → route to `odoo-coding`
- **Module-level pre-upgrade audit** → route to `odoo-deprecation-audit`
- **Override safety analysis** → route to `odoo-override-finding`
- **Verifying a render error in a real browser** → route to `odoo-debug`

## When to invoke

Main agent invokes the `odoo-code-reviewer` **agent** (via Agent tool) when Odoo code needs review. The code may arrive as a pasted block, a `file_path`/diff, or the output of a prior step. Review **scales with the change size**: one module → one reviewer; many modules → per-module fan-out plus Opus integration pass. Run Phase 0 first. Because review needs parallel MCP round-trips, each leg runs as an autonomous agent.

## Phase 0 - Scope the review

Read any existing worklog (`.odoo-ai/worklog/<run-or-slug>/*.md`, oldest-first) per `${CLAUDE_PLUGIN_ROOT}/snippets/worklog-contract.md` - the coding phase records what was intentional vs. accidental. If the worklog or run inputs name a design doc (`.odoo-ai/designs/...`, written by `odoo-solution-architect`), pass it to each reviewer as `DESIGN_DOC:` so the review verifies code against the design's intent + acceptance criteria.

Determine **changed + newly-added** modules (dir containing `__manifest__.py`):
- **From git:** `git diff --name-only` + `git diff --name-only --diff-filter=A`; map each path to its owning `__manifest__.py` dir and dedupe.
- **From a pasted block / single `file_path`:** that is one module.

Count distinct modules → **1 = single-pass; >1 = fan-out + synthesis**.

## Single module (the common case)

Dispatch ONE `odoo-code-reviewer` agent (sonnet). It writes its report to `.odoo-ai/reviews/<slug>-<date>/<module>.md`. No synthesis pass needed - UNLESS Phase 0's reverse closure shows many dependents (base/core module); then also run the Opus integration pass below.

## Multi-module - fan-out, then integration synthesis

### Phase A - Per-module fan-out (parallel sonnet, ≤3 concurrent)

One `odoo-code-reviewer` agent per changed/added module, scoped to ONLY that module. Cap at **3 concurrent** (Mode A - see `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md`); for >3 modules batch in **waves of <=3** like `wave` / `workflow-chaining` / `odoo-debug`. Each agent writes `<module>.md` to `.odoo-ai/reviews/<slug>-<date>/` and returns a short summary + path.

### Phase B - Integration synthesis (one agent, OPUS)

After all per-module reviews, dispatch ONE `odoo-code-reviewer` at **opus** for cross-module review. Scope = full **dependency closure** computed from OSM:
- **Forward closure:** walk `module_inspect(name=<m>, method='dependencies', odoo_version='<version>')` transitively.
- **Reverse closure:** `impact_analysis(...)` on changed modules, walked transitively.

The Opus pass reviews only what per-module legs cannot: override-chain conflicts, inheritance/MRO across closure, inter-module field/API contract breaks, manifest `depends` and data load-order, and ripple into dependents. Reads per-module reports on disk; writes `_synthesis.md`.

## Artifacts

All output under `.odoo-ai/reviews/<slug>-<YYYY-MM-DD>/` (gitignored). Slug = branch name, PR title, or changed-module set:
- `<module>.md` - per-module review (or single-module review)
- `_synthesis.md` - Opus integration review
- `index.md` - short map: modules reviewed, dependency closure, per-module severity counts, highest-severity findings linking to detail files

Emit paths in the Continuation Contract `produced[]`; later steps reference these instead of re-reviewing.

## Brief context - Odoo review pitfalls

Ten failure modes the agent checks for. Full details:
`${CLAUDE_PLUGIN_ROOT}/skills/odoo-code-review/references/review-pitfalls.md`

Summary: (1) ORM/N+1, (2) missing `super()` in create/write/unlink, (3) `@api.depends` errors, (4) deprecated API, (5) OWL reactivity + `position="replace"`, (6) design-system SCSS/token fidelity (flag per `${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-frontend-fidelity.md`), (7) coding-guideline conventions (grounded against `coding_guidelines/<version>/`), (8) runtime presence probing (`hasattr`/`getattr` smell), (9) platform design principles (company/branch isolation, generic-before-localization, app-menu shape), (10) behavior change with no protecting test → HIGH finding → route to `odoo-test-writing`, (11) forward-ported test coupled to source-version API/snapshot → assert observable outcome on target, RED-then-GREEN, route to `odoo-test-writing` mode `adapt`.

## Agent invocation

Full prompt templates: `${CLAUDE_PLUGIN_ROOT}/skills/odoo-code-review/references/agent-prompts.md`

Key constraints for each dispatched agent:
- Per-module (sonnet): write `<module>.md`, light bidirectional-impact pass, platform-design check, flag unprotected behavior. Return 5-line summary + path.
- Synthesis (opus): cross-module closure only; read per-module reports on disk; write `_synthesis.md`. Return summary + path.
- Each agent: restricted tools, writes only its own artifact, does NOT spawn subagents, does NOT invoke Skill tool.

After legs finish, main writes `index.md` summarizing the set.

## Standalone-first fallback

When OSM (the odoo-semantic-mcp server) is unreachable, each reviewer falls back to static analysis against internalized Odoo conventions. MCP-enriched findings are skipped; output notes "MCP unavailable - static analysis only". For synthesis, derive dependency closure from disk: read each changed module's `__manifest__.py` `depends` (forward) and `grep -rl "_inherit\|depends.*<module>"` across addons path for approximate reverse; label "closure approximate from disk (OSM unavailable)". Fan-out/synthesis topology still applies; only grounding degrades. When OSM is reachable but a customer-local addon is not in the index (Tier-1 MISS), keep OSM for indexed entities and Read/Grep the local addon for the missed ones (grounded: osm + local-source hybrid, per `snippets/disk-fallback-protocol.md`).

## Agent-managed tools

See `agents/odoo-code-reviewer.md` for the full restricted tool list and execution detail.

## Autonomous fix loop - drive it yourself (mandatory)

You run at **depth-0 in the main context** (the Skill tool loads you here), so the **Skill tool is available to you and you MUST use it to drive the fix loop** - do not write a report and stop. A passive `next: odoo-coding` is NOT enough: when no run-driver is active (a direct invocation, or an intake fast-path - the common case), nothing advances that `next` and the loop dies. So:

1. **On a CRITICAL or HIGH finding that needs a code change, IMMEDIATELY invoke `odoo-coding` via the Skill tool yourself.** Pass it the review report path, the exact findings to fix, and the literal line **"AUTONOMOUS FIX (review-driven): skip your Phase 0 human gate, fix to these findings, then invoke odoo-code-review to verify"**. This is autonomous - do NOT pause for a human (running the review IS the opt-in).
2. `odoo-coding` fixes, then invokes you again to verify. That round-trip - **review → code → review** - repeats until the review is clean (no CRITICAL/HIGH and the behavior is covered).
3. **Bound it to 3 iterations.** If still not clean after 3, STOP and escalate to the human with what remains - bad work is worse than no work, never loop forever. Record each iteration in the worklog.

The ONLY case where you emit a Continuation Contract `next` and let a driver advance instead of invoking directly: your brief shows you were dispatched **by an active run-driver** (a `run-<id>` is named) - then do not double-dispatch.

## Continuation Contract

Before finishing, APPEND your significant findings/decisions to the run worklog (`.odoo-ai/worklog/<run-or-slug>/`) per `${CLAUDE_PLUGIN_ROOT}/snippets/worklog-contract.md`.

When you finish, append a Continuation Contract block per `${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next). Set `produced` to the artifact paths actually written. Decide the `next` arm by what the review found (test-discipline SSOT: `${CLAUDE_PLUGIN_ROOT}/snippets/test-first-contract.md`).
**The `next:` entries below are the audit record AND the run-driver path - they are NOT a substitute for the direct Skill-tool invoke in § Autonomous fix loop.** When NO run-driver is active (the common direct / intake-fast-path case) you have ALREADY invoked the target yourself per § Autonomous fix loop; emitting `next:` advances nothing on its own, so **never stop at it**.
- CRITICAL/HIGH findings that need a code fix → you invoked `odoo-coding` directly (§ Autonomous fix loop); under an active run-driver instead, emit `next: odoo-coding` carrying the report path (the driver bounds the loop to 3 iterations, then escalates).
- A behavior change with no protecting test (pitfall #10) → drive it through `odoo-coding` (which is test-first) the same way; under a run-driver, emit `next: odoo-test-writing` carrying the module + behavior so the gap is closed before merge.
- Clean review, behavior covered → no fix needed, no `next` (the loop terminates).
A review that finds a CRITICAL bug in a behavior that also lacks a test drives BOTH the protecting test and the fix (under a run-driver: `next: odoo-coding` and `next: odoo-test-writing`).
Additive output for the depth-0 run-driver - it does not change anything produced above.
