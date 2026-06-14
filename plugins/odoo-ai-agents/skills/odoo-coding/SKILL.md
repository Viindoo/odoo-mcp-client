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

An Odoo job often spans both stacks (a field/model plus its widget/view). This is the only coding
entry point: it figures out per-module whether work is backend / frontend / fullstack and dispatches
just the agents needed. The agents stay specialists; this skill owns orchestration (module set,
dependency order, sequencing), not codegen.

## Phase 0 — Scope + module graph (1-turn gate, mandatory)

This is the single confirmation checkpoint. It applies even when the request arrived directly
(e.g. intake bypass) — **unless your brief carries the AUTONOMOUS FIX sentinel (see the exception
immediately below), in which case you skip this gate entirely.**

**Autonomous-fix exception — SKIP this gate entirely** when your brief contains
**"AUTONOMOUS FIX (review-driven)"** or **"AUTONOMOUS FIX (debug-driven)"**: the human already
opted into the autonomous review/debug fix loop, so do NOT stop for a confirmation. Read the worklog
+ the review report / proven root cause passed in, fix directly to those findings, and the moment
you finish writing **IMMEDIATELY invoke `odoo-code-review` via the Skill tool yourself** to verify
(§ The code -> review+test -> code loop). Bound to 3 iterations, then STOP and escalate.

Otherwise (normal invocation), First READ any existing worklog for this run
(`.odoo-ai/worklog/<run-or-slug>/*.md`, oldest-first) per
`${CLAUDE_PLUGIN_ROOT}/snippets/worklog-contract.md` so you build on the decisions an upstream
phase (e.g. `odoo-solution-design`) already recorded instead of re-deriving them. Then do six
things, then stop for the user's reply.

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

**4. Compute the dependency order (OSM is ground truth).** Follow
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-module-graph.md` - the SSOT for the module DAG, shared
with `wave` so both order work the same way. In short: call
`module_inspect(name=<m>, method='dependencies', odoo_version='[resolved version]')` per target
module (concrete version - the pin is per-API-key and racy, see
`skills/_shared/concurrency-guard.md` "OSM version-pin race"), build the sub-graph restricted to the
target set, and topologically order it - independent modules share a **wave** (parallel), a
dependent module runs in a **later wave**. The disk fallback (haiku reader of each
`__manifest__.py` `depends` + `static/src` scan, labelled "graph from disk (OSM unavailable)")
lives in that SSOT.

**5. Assign a model tier per module (deterministic - no judgment call mid-flow).**
Every dispatch in this skill passes an explicit `model`. Resolve the tier for each
module's work-item by walking this table TOP-DOWN and stopping at the FIRST match.
When a design doc is present, its effort tier takes precedence over the heuristics.

| # | Condition (first match wins) | Tier |
|---|---|---|
| 1 | Design doc grades it Custom-XL; OR the work-item spans >=3 modules of the set AND is full-stack AND estimated >800 LOC; OR it changes an inheritance axis across modules | **fable** |
| 2 | Design doc grades it Extension-L; OR it overrides core `create`/`write`/`unlink`; OR the override chain has >=3 entries (`find_override_point`); OR cross-model computed chain / multi-company logic; OR a migration with >1 viable strategy; OR full-stack module with >5 intended files | **opus** |
| 3 | Design doc grades it Standard or Config; OR (single-stack AND <=2 intended files AND ~<=50 LOC AND no method override): one field/attr, boilerplate XML view shell, label/string change, security CSV row | **haiku** |
| 4 | Everything else - Extension-M, normal computed/onchange/constraint, single-method override, standard OWL widget, mid-size single-stack module - and ANY case you cannot classify confidently | **sonnet** (default) |

Constraints on the table:
- **sonnet is the ambiguous-case default.** If two rows seem to apply, the higher
  row (smaller #) wins; if NO row clearly applies, use sonnet.
- **fable is never a default and ALWAYS needs explicit human confirmation.** It is
  the rare top band (~2x opus price). When any row resolves to fable, the gate
  message must call it out on its own line - tier, cost, and a one-line why
  (e.g. `Fable row: <m2> - Custom-XL cross-module inheritance change (~2x opus
  cost). Confirm fable?`) - and the human's yes covers it. If the human declines
  fable, downgrade that row to **opus** before dispatch and record the downgrade
  in plan.md (`<m2>: opus (fable declined)`). If the work is fable-grade but NO
  approved design doc exists, recommend `SUGGESTED_NEXT: odoo-solution-design`
  first (Custom-XL work is design-first).
- A fullstack module gets ONE tier applied to both legs by default; you MAY set a
  lower `frontendModel` when the design doc splits effort (e.g. opus backend +
  sonnet frontend). Never set the frontend leg HIGHER than the module tier.
- Record the chosen tier in the gate table and later in plan.md - the tier is part
  of the approved plan, not a runtime improvisation.

**6. Decide test-first authorship per module (red before green).** The test protects the business
behavior and is written BEFORE the code (`${CLAUDE_PLUGIN_ROOT}/snippets/test-first-contract.md`).
Choose per module, hybrid by complexity:
- **non-trivial** module (anything the design gate flags non-trivial - core override, cross-model
  chain, multi-company logic, new model, full-stack) → `test: test-author`: a SEPARATE author
  writes the failing test first, so the test author is not the code author (independence keeps the
  test honest). Execution runs that test-author before the coder, per stack.
- **trivial** module (single field, boilerplate, one-approach fix) → `test: self`: the coder writes
  its own red test first, then the code - a separate author is not worth the round-trip at that
  size.

Then emit the gate and wait. Write the gate message in the USER'S language (translate
labels and prose; keep module names, paths, and the reply keywords verbatim - SSOT:
`${CLAUDE_PLUGIN_ROOT}/snippets/language-mirroring.md`), and when the user is not
working in English pass `userLanguage` in the Workflow `args` so the coder agents
return their summaries pre-mirrored:

```
Proposed: <one-line summary of the change>.
Plan:
  | module | stack     | wave | model  | test        | files (intended) |
  | <m1>   | backend   | 1    | haiku  | self        | <m1>/models/*.py, __manifest__.py |
  | <m2>   | fullstack | 1    | opus   | test-author | <m2>/models/*.py, <m2>/static/src/*.js, __manifest__.py |
  | <m3>   | frontend  | 2    | sonnet | test-author | <m3>/static/src/*.js (depends on <m1>) |
Design: <path to approved design doc | none (trivial)>
OSM: backed | standalone
Dispatch: Workflow rolling-window (fallback: Agent-tool weighted batches)
Proceed? (yes / refine: [feedback] / cancel)
```

The `wave` column stays for the reader's benefit (it shows depends-on), but the
executor does not barrier on waves - dependency order is enforced per-module
during execution.

On `yes`, execute; on `refine: …`, update and re-emit; on `cancel`, stop.

## Execution - dispatch the coders (Workflow rolling-window, canonical path)

The coders run as autonomous agents - never inline codegen in main, never via the Skill tool. The
canonical path is the **Workflow tool**: this skill instructing the main agent to call it after the
Phase 0 gate is approved is what satisfies the tool's opt-in. When the Workflow tool is unavailable
or its permission is denied, use the **Agent-tool fallback** below - never silently skip execution.

Concurrency/OOM rule (SSOT: `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md`):
model-weighted budget - WEIGHT haiku=1, sonnet=2, opus=4, fable=8; at most 8 weight-units run at
once (keeps opus <=2 and fable exclusive while haiku/sonnet flow freely - the OOM risk comes from
opus-class fan-out, so heavier tiers weigh more).

### Canonical path - one Workflow call

Call the Workflow tool ONCE with the script below as `script` and the approved
Phase 0 plan as `args`. Derive `args` from the approved plan: `name`/`stack`/
`model` (and `frontendModel` when split) come straight from the gate table;
`path` is the module's directory on disk; `depends` comes from the dependency
edges computed in Phase 0 step 4 (shown as "(depends on ...)" in the plan);
`request`/`frontendRequest` come from the per-module change description behind
the one-line Proposed summary:

```json
{
  "odooVersion": "<resolved version - ONE version for the whole run>",
  "designDoc": "<path | none>",
  "runSlug": "<the <slug> used for .odoo-ai artifacts - scopes the shared worklog dir>",
  "userLanguage": "<the user's chat language - omit when the user works in English>",
  "modules": [
    {
      "name": "<m1>", "path": "<abs path>", "stack": "backend|frontend|fullstack",
      "model": "haiku|sonnet|opus|fable", "frontendModel": "<optional, <= model>",
      "depends": ["<other module names within the set - the dependency edges from Phase 0 step 4, shown as (depends on ...) in the plan>"],
      "newModule": false,
      "test": "test-author|self",
      "request": "<the change for this module, with target model + constraints>",
      "frontendRequest": "<the UI/UX for this module - omit for backend-only>"
    }
  ]
}
```

```js
export const meta = {
  name: 'odoo-coding-dispatch',
  description: 'Rolling-window per-module backend->frontend Odoo codegen with model-weighted concurrency',
  phases: [{ title: 'codegen' }],
};

const WEIGHT = { haiku: 1, sonnet: 2, opus: 4, fable: 8 };
const BUDGET = 8; // SSOT: skills/_shared/concurrency-guard.md

const RESULT_SCHEMA = {
  type: 'object',
  properties: {
    status: { type: 'string', enum: ['DONE', 'DONE_WITH_CONCERNS', 'BLOCKED', 'NEEDS_CONTEXT'] },
    files_written: { type: 'array', items: { type: 'string' } },
    manifest_changes: { type: 'string' },
    grounding: { type: 'string' },
    summary: { type: 'string' },
    suggested_next: { type: 'string' },
  },
  required: ['status', 'files_written', 'summary'],
};

const { modules, odooVersion, designDoc, userLanguage } = args;
const runSlug = args.runSlug || 'coding';
const worklogLine = `WORKLOG: read then append your significant decisions (approach, impact + mitigation, demo-data, tier) to .odoo-ai/worklog/${runSlug}/ per snippets/worklog-contract.md.`;
// test-first line for the coder prompt: implement-to-green against the separately
// authored failing test, or (trivial) write your own red test first - never weaken
// a test to make it pass. snippets/test-first-contract.md.
const testLine = (m, testFiles) =>
  m.test === 'test-author' && testFiles && testFiles.length
    ? `FAILING TEST (written by a separate test-author, currently RED): ${testFiles.join(', ')} - implement until these pass; do NOT edit the tests to make them pass. See snippets/test-first-contract.md.`
    : `TEST-FIRST: write the failing test for the business rule FIRST and confirm it goes RED, then implement to green; never weaken the test to pass. The test MUST drive the real workflow (action_confirm/action_validate/button_validate, Form() for onchange, with_user() not sudo()) - never seed the terminal state with create({state:...}). See snippets/test-first-contract.md and snippets/test-behavior-contract.md.`;

// --- validate args up front: a typo'd/missing tier must fail the whole run at
// t=0 (before any agent or resolver exists), not silently book the wrong weight
for (const m of modules) {
  if (!WEIGHT[m.model]) throw new Error(`module ${m.name}: unknown model tier '${m.model}'`);
  if (m.frontendModel && !WEIGHT[m.frontendModel]) throw new Error(`module ${m.name}: unknown frontendModel '${m.frontendModel}'`);
}

// --- weighted semaphore (plain JS - the runtime has no per-model knob).
// release() admits strictly FIFO so a heavy (fable) waiter is never starved by
// lighter waiters arriving behind it.
let used = 0;
const waiters = [];
const acquire = (w) => new Promise((resolve) => {
  const attempt = () => (used + w <= BUDGET ? ((used += w), resolve(), true) : false);
  if (!attempt()) waiters.push(attempt);
});
const release = (w) => {
  used -= w;
  while (waiters.length && waiters[0]()) waiters.shift();
};

// --- per-module completion promises: dependency rolling-window, no wave barrier.
// Each resolves with a boolean: true = module fully done (both legs), false =
// blocked/failed - dependents must NOT build on it.
const resolvers = {};
const completed = {};
for (const m of modules) completed[m.name] = new Promise((r) => { resolvers[m.name] = r; });

const OK_STATUSES = ['DONE', 'DONE_WITH_CONCERNS'];

const backendPrompt = (m, testFiles) => [
  'You are the odoo-coder agent. Produce production-ready Python/XML Odoo code for:',
  `REQUEST: ${m.request}`,
  `MODULE SCOPE: ${m.name} @ ${m.path} - write ONLY within this module (+ its __manifest__.py).`,
  `NEW MODULE: ${m.newModule ? 'yes - scaffold the skeleton first with odoo-bin scaffold, then fill it in (do NOT hand-roll the skeleton)' : 'no'}.`,
  `ODOO VERSION: ${odooVersion}`,
  `DESIGN_DOC: ${designDoc} - if present, build to it; do not re-derive.`,
  testLine(m, testFiles),
  `GUIDELINES: before writing, read skills/_shared/coding_guidelines/${odooVersion}/INDEX.md and the by-task files for this change (python/naming/model-ordering for models, xml for views) - conform on the first pass. snippets/read-before-write-contract.md.`,
  worklogLine,
  `Step 0 (only if mcp__odoo-semantic__* is available): set_active_version('${odooVersion}'), then follow Rounds 1-4 from your system prompt.`,
  'If OSM is down, use the disk-grounded fallback and still write files. If OSM answers but a specific module/model is not in the index (customer-local addon), Read/Grep the local addon for just that entity and ground hybrid (osm + local-source) - an index miss is not proof of absence. Do not spawn subagents or invoke skills.',
  ...(userLanguage ? [`USER LANGUAGE: ${userLanguage} - write the summary field of your structured result in this language; keep identifiers verbatim.`] : []),
].join('\n');

const frontendPrompt = (m, testFiles) => [
  'You are the odoo-frontend-coder agent. Produce production-ready Odoo frontend code (JS / OWL / QWeb / SCSS) for:',
  `REQUEST: ${m.frontendRequest || m.request}`,
  `MODULE SCOPE: ${m.name} @ ${m.path} - write ONLY within this module (+ its __manifest__.py assets).`,
  `ODOO VERSION: ${odooVersion}`,
  `DESIGN_DOC: ${designDoc} - if present, build to it; do not re-derive.`,
  testLine(m, testFiles),
  `GUIDELINES: before writing, read skills/_shared/coding_guidelines/${odooVersion}/INDEX.md and the by-task files (javascript + scss; python/xml if you also touch controllers/views) - conform on the first pass. snippets/read-before-write-contract.md.`,
  worklogLine,
  `Step 0 (only if mcp__odoo-semantic__* is available): read .odoo-ai/context.md, then set_active_version('${odooVersion}');`,
  'ground styling tokens against skills/_shared/odoo-frontend-fidelity.md (no hardcoded hex for themeable colors, no self-referential --bs-* shim).',
  'If OSM is down, use the disk-grounded fallback and still write files. If OSM answers but a specific module/model is not in the index (customer-local addon), Read/Grep the local addon for just that entity and ground hybrid (osm + local-source) - an index miss is not proof of absence.',
  'If the Skill tool is unavailable in this context, Read skills/odoo-frontend-design/SKILL.md directly instead of invoking it.',
  'Follow the version gate + rounds from your system prompt. Do not spawn subagents or invoke any other skill.',
  ...(userLanguage ? [`USER LANGUAGE: ${userLanguage} - write the summary field of your structured result in this language; keep identifiers verbatim.`] : []),
].join('\n');

// Test-first (red before green): for a module marked test:'test-author' a SEPARATE
// author writes the FAILING test before the coder, so the test author is not the
// code author - independence keeps the test honest (snippets/test-first-contract.md).
// It runs per stack (backend test before backend coder; frontend test before
// frontend coder), shares the same weighted budget, and returns the test paths to
// hand the coder. Trivial modules (test:'self') skip this; their coder self-tests.
const testAuthorPrompt = (m, leg) => [
  `You are the ${leg === 'frontend' ? 'odoo-frontend-coder' : 'odoo-coder'} agent in TEST-AUTHOR mode.`,
  'Write ONLY the failing test(s) that protect the business behavior below - do NOT write the implementation.',
  `REQUEST: ${leg === 'frontend' ? (m.frontendRequest || m.request) : m.request}`,
  `MODULE SCOPE: ${m.name} @ ${m.path} - write only test files (tests/ or static/tests/).`,
  `ODOO VERSION: ${odooVersion}`,
  'Follow snippets/test-first-contract.md (red-before-green) AND snippets/test-behavior-contract.md (drive the real workflow: action_confirm/action_validate/button_validate, Form() for onchange, with_user() not sudo(); never seed the terminal state with create({state:...})): assert observable behavior, not internals; ONE intent per test; confirm each test goes RED before the code exists (state the RED confirmation).',
  worklogLine,
  'Return the test file paths in files_written and a one-line RED confirmation in summary. Do not spawn subagents or invoke skills.',
].join('\n');

const authorRedTest = async (m, leg) => {
  if (m.test !== 'test-author') return null;
  const model = leg === 'frontend' ? (m.frontendModel || m.model) : m.model;
  const w = WEIGHT[model];
  await acquire(w);
  try {
    log(`[${m.name}:${leg}] test-author @ ${model}`);
    const r = await agent(testAuthorPrompt(m, leg), {
      label: `${m.name}:${leg}-test`,
      phase: 'codegen',
      agentType: leg === 'frontend' ? 'odoo-frontend-coder' : 'odoo-coder',
      model,
      schema: RESULT_SCHEMA,
    });
    return r && Array.isArray(r.files_written) && r.files_written.length ? r.files_written : null;
  } catch (e) {
    log(`[${m.name}:${leg}] test-author failed (${String(e)}) - coder will self-test`);
    return null;
  } finally {
    release(w);
  }
};

// agentType resolves from the same registry as the Agent tool; if a short name
// ever fails to resolve, retry once with the plugin-qualified form
// 'odoo-ai-agents:odoo-coder' / 'odoo-ai-agents:odoo-frontend-coder'.
const dispatchOnce = async (m, leg, model, testFiles) => {
  const w = WEIGHT[model];
  await acquire(w);
  try {
    log(`[${m.name}:${leg}] dispatch @ ${model} (weight ${w}, in-flight ${used}/${BUDGET})`);
    return await agent(leg === 'frontend' ? frontendPrompt(m, testFiles) : backendPrompt(m, testFiles), {
      label: `${m.name}:${leg}`,
      phase: 'codegen',
      agentType: leg === 'frontend' ? 'odoo-frontend-coder' : 'odoo-coder',
      model,
      schema: RESULT_SCHEMA,
    });
  } finally {
    release(w);
  }
};

// fable runtime fallback: if a fable dispatch dies (insufficient usage credit,
// model unavailable, harness error -> throw or null), retry ONCE at opus and
// mark the downgrade so plan.md records it.
const runLeg = async (m, leg, testFiles) => {
  const model = leg === 'frontend' ? (m.frontendModel || m.model) : m.model;
  let result = null;
  let err = null;
  try {
    result = await dispatchOnce(m, leg, model, testFiles);
  } catch (e) {
    err = e;
  }
  if (model === 'fable' && (result === null || result === undefined)) {
    log(`[${m.name}:${leg}] fable unavailable (${err ? String(err) : 'null result'}) - retrying once @ opus`);
    result = await dispatchOnce(m, leg, 'opus', testFiles);
    if (result) result.downgraded = 'opus (fable unavailable)';
    return result;
  }
  if (err) throw err;
  return result;
};

// Stage 1 - backend leg. Waits for in-set dependencies first (this IS the wave
// ordering, enforced per-module so an independent module never waits on a wave).
// If any dependency resolved false (blocked upstream), do NOT dispatch - mark
// blocked so resumeFromRunId re-runs this module for real (no cached agent call).
// Errors are caught into a marker instead of thrown, so stage 2 always runs and
// the module's resolver always fires (a thrown stage would skip stage 2 and hang
// every dependent forever).
const backendStage = async (m) => {
  const depsOk = (await Promise.all((m.depends || []).map((d) => completed[d] ?? Promise.resolve(true)))).every(Boolean);
  if (!depsOk) return { leg: 'backend', upstreamBlocked: true };
  if (m.stack === 'frontend') return { leg: 'backend', skipped: true };
  try {
    const testFiles = await authorRedTest(m, 'backend'); // red before green
    return { leg: 'backend', testFiles, result: await runLeg(m, 'backend', testFiles) };
  } catch (e) {
    return { leg: 'backend', error: String(e) };
  }
};

// Stage 2 - frontend leg, strictly after the module's own backend leg
// (pipeline guarantees per-item stage order; NO barrier across modules).
// Gates on the backend outcome: a BLOCKED/failed/null backend must not get a
// frontend built on top of it. try/finally guarantees the resolver fires.
const frontendStage = async (prev, m) => {
  const out = { module: m.name, model: m.model, backend: prev };
  try {
    if (prev?.upstreamBlocked) {
      out.status = 'BLOCKED';
      out.reason = 'upstream dependency blocked or failed - not dispatched';
      return out;
    }
    const backendOk = prev?.skipped || (prev?.result && OK_STATUSES.includes(prev.result.status));
    if (!backendOk) {
      out.status = 'BLOCKED';
      out.reason = prev?.error ? `backend error: ${prev.error}` : `backend status: ${prev?.result?.status ?? 'null (skipped by user or agent failure)'}`;
      return out;
    }
    if (m.stack !== 'backend') {
      try {
        const testFiles = await authorRedTest(m, 'frontend'); // red before green
        out.frontend = await runLeg(m, 'frontend', testFiles);
      } catch (e) {
        out.status = 'BLOCKED';
        out.reason = `frontend error: ${String(e)}`;
        return out;
      }
      const frontendOk = out.frontend && OK_STATUSES.includes(out.frontend.status);
      if (!frontendOk) {
        out.status = 'BLOCKED';
        out.reason = `frontend status: ${out.frontend?.status ?? 'null'}`;
        return out;
      }
    }
    out.status = 'DONE';
    return out;
  } finally {
    resolvers[m.name](out.status === 'DONE'); // unblock dependents with the outcome
  }
};

const results = await pipeline(modules, backendStage, frontendStage);
const blocked = results.filter(Boolean).filter((r) => r.status !== 'DONE');
log(`codegen complete: ${results.length} module(s), ${blocked.length} blocked`);
return { odooVersion, designDoc, results };
```

The Workflow tool returns immediately with a task ID (and a `runId` + the path
of the persisted script in the tool result); the run executes in the background
and a `<task-notification>` arrives when it completes. Do NOT write plan.md or
the Continuation Contract before that notification arrives. On a partial
failure (modules reported `BLOCKED` in the result), fix the input and resume
with `Workflow({scriptPath: <persisted script path from the tool result>,
resumeFromRunId: <runId>})` - completed agent calls return cached results, and
blocked modules made no agent call, so exactly they re-run.

Why this satisfies the rolling-window requirement:
- `pipeline()` has no barrier between items - module A can run its frontend leg while B is still in
  backend; freed weight is re-acquired immediately.
- Per-module backend->frontend is the two pipeline stages; single-stack modules skip the unused leg.
- Cross-module order is enforced by awaiting `completed[dep]` (weaker than a wave barrier: a
  dependent starts the moment ITS deps finish, not when a whole wave finishes).
- Every `agent()` call passes `model` explicitly; the frontmatter `model: sonnet` is only a default
  the dispatch `model` overrides either way (same convention as `odoo-debug`).

### Fallback path - Agent tool, weighted batches (no Workflow tool)

Use when the Workflow tool is not present in the tool list, errors out, or the
user denies it. The coders still run as autonomous agents - launch them with the
Agent tool (`agentType: odoo-coder` backend / `agentType: odoo-frontend-coder`
frontend; if a short name fails to resolve, retry with the plugin-qualified form
`odoo-ai-agents:odoo-coder` / `odoo-ai-agents:odoo-frontend-coder`).
Same plan, same explicit models; only the scheduling degrades:

1. Order modules so every module appears after its in-set dependencies
   (the wave column already encodes this).
2. Greedily pack the next batch: take modules in order whose dependencies are all
   done (done = BOTH legs of the dependency finished successfully) and whose
   summed WEIGHT stays <= 8. A fable item always forms a batch of ONE.
3. Fire the whole batch as parallel Agent-tool calls in a SINGLE message; per
   module fire only the backend leg first, then after it returns fire that
   module's frontend leg in the next batch round.
4. Wait for the batch, then pack the next. (This re-introduces a batch barrier -
   accepted degradation; the canonical path does not have it.)
5. Each Agent-tool call sets BOTH the `model` parameter AND the first prompt line
   `DISPATCH MODEL: <haiku|sonnet|opus|fable>` (belt and braces, mirroring
   `odoo-debug`), using the same prompt templates as the Workflow script above.
6. If a fable dispatch fails (insufficient usage credit, model unavailable,
   Agent-tool error), retry that work-item ONCE at `model: opus` and record the
   downgrade in plan.md (`opus (fable unavailable)`).
7. Each brief carries the same grounding branches as the Workflow prompts: OSM
   down -> disk-grounded fallback; OSM reachable but a specific module/model not
   in the index (customer-local addon) -> Read/Grep just that entity, ground
   hybrid (osm + local-source) - an index miss is not proof of absence.

Each agent locates files via Read/Grep, writes the code, and reports the files it
wrote plus `__manifest__.py` changes.

## Artifacts — persist the coding plan

Write the orchestration plan to `.odoo-ai/coding/<slug>-<YYYY-MM-DD>/plan.md` (`.odoo-ai/` is
gitignored): the module/stack/wave/**model** table, the computed dependency order, and the design
doc referenced. The agents write source directly; `plan.md` records what was built so a later
review / fix / resume step can pick up without recomputing the graph. `<slug>` derives from the
change (branch, feature name, or the module set).

plan.md MUST record, per work-item: module, stack, wave, the model tier chosen
(and frontendModel when split), the dispatch path actually used
(workflow:<runId> | agent-tool-fallback), and the per-module result status. A
later review / fix / resume step re-dispatches at the SAME recorded tier unless
the human changes it.

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

## The code -> review+test -> code loop (bounded)

Coding is not one-shot. After this skill writes code (each non-trivial module implemented to a
separately-authored failing test), the **code -> review+test -> code** round-trip runs:
`odoo-code-review` reviews AND checks the tests cover the behavior, looping back on a CRITICAL/HIGH
issue or a red/missing test.

**Drive it yourself when there is no run-driver (mandatory).** You run at depth-0, so the Skill tool
is available. After writing, **IMMEDIATELY invoke `odoo-code-review` via the Skill tool yourself** - a
passive `next: odoo-code-review` is not advanced without an active run-driver (the common case: direct
invocation, intake fast-path, autonomous fix), so verification would silently never happen. ONLY
exception: dispatched by an active run-driver (a `run-<id>` is named) - then emit
`next: odoo-code-review` and let it advance, do not double-dispatch. Emit the Continuation Contract either way.

Bound the loop to **3 iterations** per `${CLAUDE_PLUGIN_ROOT}/snippets/test-first-contract.md`; still
not green-and-clean after 3 -> STOP and escalate (bad work is worse than no work). Each iteration's
outcome goes in the worklog.

## Continuation Contract

When the bundle finishes, append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next). Set
`produced` to the source + test files written, plus `.odoo-ai/coding/<slug>-<date>/plan.md` and the
`.odoo-ai/worklog/<slug>/` entries, and emit `next: odoo-code-review` so the just-written code is
reviewed (that skill now scales to the same multi-module set). Additive output for the depth-0
run-driver - it does not change anything produced above.
