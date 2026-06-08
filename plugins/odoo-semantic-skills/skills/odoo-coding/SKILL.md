---
name: odoo-coding
description: >
  Write complete, production-ready Odoo code end-to-end — Python/XML backend AND
  JavaScript/OWL/QWeb/SCSS frontend — from a single computed field up to a multi-module
  full-stack feature. The single front door for ALL coding: it works out which modules the
  change touches and their dependency order, then dispatches the odoo-coder (backend) and
  odoo-frontend-coder (frontend) agents in the right sequence. Fire ANY time someone asks to
  build or change Odoo behavior, even with no technical words (e.g. "discount can never exceed
  20% of unit price", "add a field and show it in a widget"). Also fires on Vietnamese:
  "thêm trường / model", "computed field / ràng buộc / onchange", "override create/write",
  "phân quyền đọc ghi", "viết migration", "viết widget OWL / sửa giao diện form", "sửa SCSS
  theme". Review existing code → odoo-code-review. Find a hook point → odoo-override-finding.
  Design before coding (non-trivial) → odoo-solution-design. Verify a rendered screen →
  odoo-ui-review / odoo-debug
---

## Persona

Developer — full-stack Odoo coder (all versions, v8 onward). Orchestrates two specialist agents:
`odoo-coder` for Python/XML backend and `odoo-frontend-coder` for JS/OWL/QWeb/SCSS frontend.
Pair-works with `odoo-code-review` for review.

## Out of Scope

- **Reviewing / auditing existing code (not writing)** → `odoo-code-review`
- **Locating where to hook into core logic (one method)** → `odoo-override-finding`
- **Deprecation analysis / upgrade planning** → `odoo-deprecation-audit` / `odoo-version-diff`
- **Designing the approach before any code (non-trivial)** → `odoo-solution-design`
- **Verifying the rendered UI / a runtime render error / image regression** → `odoo-ui-review` / `odoo-debug` / `odoo-visual-regression`

## Why one skill, two agents

In Odoo a single job often spans both stacks — a new field/model plus the widget or view that
shows it. Forcing the caller to pre-pick "backend" vs "frontend" is the friction this skill
removes. `odoo-coding` is the only coding entry point; it figures out per-module whether the work
is backend-only, frontend-only, or full-stack and dispatches just the agents needed. The agents
themselves stay specialists — this skill owns the orchestration (module set, dependency order,
sequencing), not the codegen.

## Phase 0 — Scope + module graph (1-turn gate, mandatory)

This is the single confirmation checkpoint. It applies even when the request arrived directly
(e.g. intake bypass). Do four things, then stop for the user's reply.

**1. Design-gate first (safety net).** Judge whether the change is **non-trivial** — the set
`odoo-solution-design` defines: Extension-L/Custom-XL, a new module/model or restructuring, a
core `create`/`write`/`unlink` override or a ≥3-override-chain method, a >1-strategy migration, a
cross-model computed chain or multi-company logic, a full-stack feature, or a refactor. If it is
non-trivial AND no approved design exists (no `.odoo-ai/designs/<slug>-*.md`, and none passed in
via a `design_doc` input), recommend `SUGGESTED_NEXT: odoo-solution-design` first — a
recommendation, not a hard block, so the user may still say "code it directly". When a
`design_doc` IS present, read it and **build to it** — do not re-derive the approach. **Trivial**
work (a single field, boilerplate, a one-approach fix) skips design.

**2. Determine the target module set.** Derive the modules the change will touch from the design
doc / the request (coding *creates* the change, so there is no git diff to read — unlike
`odoo-code-review`). A "module" is the directory holding `__manifest__.py`.

**3. Tag each module's stack-need** — `backend`, `frontend`, or `fullstack`. Take it from the
design doc when it already splits the work; otherwise infer: touching `models/` `views/`
`security/` `*.csv` ⇒ backend; touching `static/src` JS/SCSS/QWeb ⇒ frontend; both ⇒ fullstack.

**4. Compute the dependency order (OSM is ground truth).** For each target module call
`module_inspect(name=<m>, method='dependencies', odoo_version='auto')`, build the sub-graph
restricted to the target set, and topologically order it. Modules that do not depend on each
other within the set run in the **same wave** (parallel); a module that depends on another in the
set runs in a **later wave** (after its dependency). When OSM is unreachable or returns too
little, dispatch a read-only **haiku** agent **via the Agent tool** to read each
`__manifest__.py` `depends` and scan for `static/src`, and label the result
"graph from disk (OSM unavailable)".

Then emit the gate and wait:

```
Proposed: <one-line summary of the change>.
Plan:
  | module        | stack     | wave | files (intended) |
  | <m1>          | backend   | 1    | <m1>/models/*.py, __manifest__.py |
  | <m2>          | fullstack | 1    | <m2>/models/*.py, <m2>/static/src/*.js, __manifest__.py |
  | <m3>          | frontend  | 2    | <m3>/static/src/*.js (depends on <m1>) |
Design: <path to approved design doc | none (trivial)>
OSM: backed | standalone
Proceed? (yes / refine: [feedback] / cancel)
```

On `yes`, execute; on `refine: …`, update and re-emit; on `cancel`, stop.

## Execution — dispatch the coders via the Agent tool

The coders run as autonomous agents: **always launch them with the Agent tool** (never inline the
codegen in main, never via the Skill tool). Codegen needs many sequential+parallel MCP
round-trips, so it belongs in an agent — and the Agent tool is the only way main can spawn one.
`agentType` is `odoo-coder` for the backend leg and `odoo-frontend-coder` for the frontend leg.

**Cross-module — parallelism with a ceiling.** Walk the waves in topological order. Within a wave,
fire each module's agent(s) in parallel but **cap at 3 concurrent Agent-tool calls** (the standing
OOM ceiling — failure log `unbounded-opus-fanout-oom`); for >3 independent modules, batch in waves
of ≤3 (fire 3, wait, fire the next 3) like `wave` / `odoo-debug`.

**Within a single module — backend first, then frontend.** Dispatch the `odoo-coder` Agent and
**wait** for it; once the backend fields/views exist, dispatch the `odoo-frontend-coder` Agent for
the UI/UX so it builds on real, just-written code rather than a guess. A `backend`-only module
launches only `odoo-coder`; a `frontend`-only module only `odoo-frontend-coder`. This per-module
ordering is deliberate and is *not* the cross-module parallelism — independent modules still run
their pairs concurrently.

Pass each Agent its module scope, the resolved Odoo version, and the design-doc path. Use these
templates **verbatim** as the Agent-tool prompt, filling the bracketed fields:

**Backend leg — Agent tool, `agentType: odoo-coder`:**
```
You are the odoo-coder agent. Produce production-ready Python/XML Odoo code for:
REQUEST: [the change for this module, with target model + constraints]
MODULE SCOPE: [module] @ [path] — write ONLY within this module (+ its __manifest__.py).
NEW MODULE: [yes/no] — if yes, scaffold the skeleton first with `odoo-bin scaffold [module] [addons-dir]`, then fill it in (do NOT hand-roll the skeleton).
ODOO VERSION: [resolved version]
DESIGN_DOC: [path to approved design | none] — if present, build to it; do not re-derive.
Step 0 (only if mcp__odoo-semantic__* is available): set_active_version('[version]'), then
Rounds 1-4. If OSM is down, use the disk-grounded fallback and still write files.
Follow Rounds 1-4 from your system prompt. Do not spawn subagents or invoke skills.
```

**Frontend leg — Agent tool, `agentType: odoo-frontend-coder`:**
```
You are the odoo-frontend-coder agent. Produce production-ready Odoo frontend code (JS / OWL /
QWeb / SCSS) for:
REQUEST: [the UI/UX for this module]
MODULE SCOPE: [module] @ [path] — write ONLY within this module (+ its __manifest__.py assets).
ODOO VERSION: [resolved version]
DESIGN_DOC: [path to approved design | none] — if present, build to it; do not re-derive.
Step 0 (only if mcp__odoo-semantic__* is available): read .odoo-ai/context.md, then
set_active_version('[version]'); ground styling tokens against
${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-frontend-fidelity.md (no hardcoded hex for themeable
colors, no self-referential --bs-* shim). If OSM is down, use the disk-grounded fallback and
still write files.
Follow the version gate + rounds from your system prompt. Do not spawn subagents or invoke skills.
```

Each Agent locates files via Read/Grep, writes the code, and reports the files it wrote plus
`__manifest__.py` changes.

## Artifacts — persist the coding plan

Write the orchestration plan to `.odoo-ai/coding/<slug>-<YYYY-MM-DD>/plan.md` (`.odoo-ai/` is
gitignored): the module/stack/wave table, the computed dependency order, and the design doc
referenced. The agents write source directly; `plan.md` records what was built so a later review /
fix / resume step can pick up without recomputing the graph. `<slug>` derives from the change
(branch, feature name, or the module set).

## Standalone-first fallback

When OSM (the odoo-semantic-mcp server) is unreachable, the dependency graph and stack tags come
from disk — read each `__manifest__.py` `depends` and scan `static/src` (or the haiku reader
above) — and each agent falls back to its own disk-grounded mode per
`${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md`, still writing files to their correct
locations. Label the plan "graph from disk (OSM unavailable)"; the wave/pair topology is
unchanged, only the grounding degrades. Never ask a human to paste code, field lists, or manifests.

## Agent-managed tools

This skill is part of an agent+skill bundle. The codegen tool lists live on the two agents —
see `agents/odoo-coder.md` (backend) and `agents/odoo-frontend-coder.md` (frontend) for the full
restricted allowlists and execution detail.

## Continuation Contract

When the bundle finishes, append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next). Set
`produced` to the source files written plus `.odoo-ai/coding/<slug>-<date>/plan.md`, and emit
`next: odoo-code-review` so the just-written code is reviewed (that skill now scales to the same
multi-module set). Additive output for the depth-0 run-driver — it does not change anything
produced above.
