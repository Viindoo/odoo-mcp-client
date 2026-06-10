---
name: odoo-code-review
description: >
  Review Odoo code (Python, JavaScript, XML, OWL) for bugs, convention violations, security,
  and performance — severity-graded findings, suggested fixes, corrected version. Dispatches
  to the odoo-code-reviewer agent. Fire whenever code is shared with feedback intent, even
  without the word "review". Trigger on: "does this look correct?", "audit this PR",
  "should I worry about N+1?", "before I merge". Also fires on Vietnamese requests: "review
  giúp đoạn này", "kiểm tra code Odoo", "code này có bug không", "có bị N+1 không", "soát
  trước khi merge", "đánh giá PR". Trigger especially on model overrides,
  write/create overrides, computed fields, OWL components, or XML view overrides —
  Odoo-specific failure modes a generic reviewer misses. A false positive is cheap; a missed
  CRITICAL bug in production is expensive. Static analysis only — live render errors →
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

Main agent invokes the `odoo-code-reviewer` **agent** (via Agent tool) when Odoo code needs
review. The code may arrive as a pasted block, a `file_path`/diff the agent reads itself, or the
output of a prior tool/step - the agent obtains the code accordingly, it does not require a human
to paste it. The review **scales with the size of the change**: a one-module change gets one
reviewer; a many-module change gets a per-module fan-out plus an Opus integration pass. Run
Phase 0 first to decide which topology applies. Because review needs multiple parallel MCP
round-trips, each leg runs as an autonomous agent rather than inline in main.

## Phase 0 — Scope the review (count the modules touched)

Determine the set of **changed + newly-added** Odoo modules in the target before dispatching any
reviewer. A "module" is the directory that holds `__manifest__.py`.

- **From git** (the usual case): `git diff --name-only` for modified files and
  `git diff --name-only --diff-filter=A` (or untracked) for new files; map each path up to its
  owning `__manifest__.py` directory and dedupe.
- **From a pasted block / single `file_path`**: that is one module (or a standalone snippet).

Count the distinct modules. The count picks the topology: **1 → single-pass**; **>1 →
fan-out + synthesis**. Either way, all output lands in the artifacts dir (below) so later steps
can reference it.

## Single module (the common case)

Exactly one module touched → dispatch ONE `odoo-code-reviewer` agent (sonnet) scoped to that
module's changes, as today. It writes its report to the artifacts dir. A separate synthesis pass
is unnecessary for one module — UNLESS Phase 0's reverse closure shows the module has many
dependents (it is a base/core module others build on); then also run the Opus integration pass
below, because the blast radius is wide even though only one module changed.

## Multi-module — fan-out, then integration synthesis

More than one module touched → two phases. The reason for the split: a per-module reviewer goes
deep without cross-module noise, but it structurally **cannot see** how modules interact — that
is what the Opus pass is for.

### Phase A — Per-module fan-out (parallel, sonnet, ≤3 concurrent)

Dispatch one `odoo-code-reviewer` agent **per changed/added module**, each scoped to ONLY that
module's changes. Run them in parallel but cap at **3 concurrent** (Mode A - see
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md`); for >3 modules, batch in
**waves of <=3** (fire 3, wait, fire the next 3) like `wave` / `workflow-chaining` / `odoo-debug`. Each agent writes its own
per-module report to `.odoo-ai/reviews/<slug>-<date>/<module>.md` and returns a short summary +
the path (so main does not carry every full report in context).

### Phase B — Integration synthesis (one agent, OPUS)

After every per-module review completes, dispatch ONE `odoo-code-reviewer` agent at **opus** for
the cross-module review. Its scope is the full **dependency closure** of the change, which it
computes from OSM (not from memory):

- **The changed + newly-added modules** (the Phase 0 set).
- **Forward closure — what they depend on (direct AND indirect):** walk
  `module_inspect(name=<m>, method='dependencies', odoo_version='<version>')` transitively from each
  changed module until it stops adding modules.
- **Reverse closure — what depends on them (direct AND indirect):** `impact_analysis(...)` on the
  changed modules/models returns dependent modules / blast radius; walk it transitively too.

The Opus pass reviews only what the per-module legs cannot: override-chain conflicts spanning
modules, inheritance / MRO order across the closure, inter-module field/API contract breaks,
manifest `depends` and data load-order, and how the change ripples into its dependents. It reads
the per-module reports (on disk) as input and writes the synthesis to
`.odoo-ai/reviews/<slug>-<date>/_synthesis.md`.

## Artifacts — persist every result for later steps

All review output is persisted under `.odoo-ai/reviews/<slug>-<YYYY-MM-DD>/` (`.odoo-ai/` is
gitignored). `<slug>` is derived from the change (branch name, PR title, or the changed-module
set). The directory holds:

- `<module>.md` — one per per-module review (or the single-module review).
- `_synthesis.md` — the Opus integration review (multi-module, or single-module-with-many-dependents).
- `index.md` — a short map: modules reviewed, the computed dependency closure, per-module
  severity counts, and the highest-severity findings, each linking to its detail file.

A later coding / fix / deploy step references these instead of re-reviewing — so emit the paths
in the Continuation Contract `produced[]`.

## Brief context — Odoo review pitfalls

Key failure modes the agent is aware of:

1. **ORM / N+1** — field reads or `search()` inside `for rec in self` loops; use `mapped()` or prefetch outside loop.
2. **Inheritance breaks** — missing `super()` in `create`/`write`/`unlink` breaks tracking, compute triggers, and downstream module overrides (always CRITICAL).
3. **`@api.depends` errors** — stale or wrong dotted paths; `id` in depends list; constraint on relational field (silently skipped).
4. **Deprecated API** — `@api.multi`, `@api.one` removed in v13/v14; raise at call time, not import.
5. **OWL reactivity** — direct `this.state.items.push()` bypasses OWL reactivity; `position="replace"` in XML views breaks other override chains. These render-level defects should be confirmed visually on a live instance with `odoo-debug` once the static review flags them.
6. **Design-system fidelity (SCSS/OWL styling)** — hardcoded `hex`/`rgba` for themeable colors, or surface tokens chained into Bootstrap `--bs-*` custom properties the target version does not emit at runtime (often via a self-referential shim — a CSS var whose value references itself, a cycle that resolves to empty and flattens the theme). Flag per `${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-frontend-fidelity.md`; confirm at runtime with `odoo-debug`/`odoo-ui-review`, and route the fix to `odoo-coding` (this reviewer does not write frontend source).
7. **Coding-guideline conventions** — after pinning the version, the reviewer grounds convention findings against `${CLAUDE_PLUGIN_ROOT}/skills/_shared/coding_guidelines/<version>/` (naming prefixes, model attribute order, import order, `_()` form) and cites the violated file + section — see `agents/odoo-code-reviewer.md`.

## Agent invocation — prompt template

Dispatch `odoo-code-reviewer` via the Agent tool, passing the **MODE** and scope explicitly so the
agent knows which job it is doing and where to write its artifact:

- **Per-module (sonnet):**
  ```
  MODE=per-module. Review ONLY the changes in module `<module>` at `<path>`.
  Artifacts dir: .odoo-ai/reviews/<slug>-<date>/ — write your report to <module>.md there.
  Return a 5-line summary (counts by severity + top finding) and the artifact path.
  ```
- **Synthesis (dispatch with model `opus`):**
  ```
  MODE=synthesis. Changed/added modules: [<m1>, <m2>, …]. Compute the dependency closure —
  forward via module_inspect(method='dependencies', odoo_version='<version>') transitively, reverse via impact_analysis —
  and review CROSS-MODULE integration risk only (override conflicts, MRO, inter-module contracts,
  depends/load-order, ripple to dependents). Read the per-module reports already in
  .odoo-ai/reviews/<slug>-<date>/. Write _synthesis.md there. Return a summary + path.
  ```

Each agent runs its review rounds with restricted tools, **writes only its own report artifact**
under `.odoo-ai/reviews/`, does NOT spawn further subagents, and does NOT invoke any Skill tool.
After the legs finish, main writes `index.md` summarizing the set.

## Standalone-first fallback

When OSM (the odoo-semantic-mcp server) is unreachable, each reviewer falls back to its own static
analysis - reading the code and pattern-matching against internalized Odoo conventions. MCP-enriched
findings (existence verification, `validate_depends`, etc.) are skipped and the output notes
"MCP unavailable — static analysis only". For the synthesis pass, the dependency closure cannot be
computed via OSM either - derive it from disk instead: read each changed module's `__manifest__.py`
`depends` (forward closure) and `grep -rl "_inherit\|depends.*<module>"` across the addons path for
an approximate reverse closure, and label the synthesis "closure approximate from disk (OSM
unavailable)". The fan-out / synthesis topology itself still applies; only the grounding degrades.
When OSM is reachable but a specific module/model in the diff is not in the index (a
customer-local addon), that is a Tier-1 MISS, not proof of absence - the reviewers keep OSM for
what it covers and Read/Grep the local addon for just the missed entities (grounded: osm +
local-source (hybrid), per `snippets/disk-fallback-protocol.md`).

## Agent-managed tools

This skill is part of an agent+skill bundle. See `agents/odoo-code-reviewer.md` for the full restricted tool list and execution detail.

## Continuation Contract

When you finish, append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next). Set
`produced` to the artifact paths actually written — `.odoo-ai/reviews/<slug>-<date>/index.md`
plus the per-module reports and `_synthesis.md` — so a later coding / fix / deploy step
references the review instead of re-running it. If CRITICAL/HIGH findings need a code fix, emit
`next: odoo-coding` carrying the relevant report path as an
input. Additive output for the depth-0 run-driver - it does not change anything produced above.
