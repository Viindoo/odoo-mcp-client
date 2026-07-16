---
name: odoo-code-review
argument-hint: "[PR#|local|worktree:<path>]"
description: >
  Review Odoo code (Python, JavaScript, XML, OWL) for bugs, convention violations, security, and performance -
  severity-graded findings, suggested fixes, corrected version. Dispatches to the odoo-code-reviewer agent.
  Fire whenever code is shared with feedback intent, even without the word "review". Trigger on: "does this
  look correct?", "audit this PR", "should I worry about N+1?", "before I merge", "review PR #123". Also fires
  on Vietnamese: "review giúp đoạn này", "kiểm tra code Odoo", "code này có bug không", "soát trước khi
  merge", "đánh giá PR". Trigger on model overrides, write/create overrides, computed fields, OWL components,
  or XML view overrides - Odoo-specific failure modes a generic reviewer misses. Static analysis only - a live
  render/console error -> odoo-debug, rating a rendered screen's look/UX -> odoo-ui-review. Write new code ->
  odoo-coding. Pre-upgrade audit -> odoo-deprecation-audit. A dedicated performance-only deep scan ->
  odoo-perf-audit; a security-only scan -> odoo-security-audit
---

## Role

Developer / Tech Lead reviewing Odoo code with semantic MCP enrichment.

## Out of Scope

- **Writing new code** → route to `odoo-coding`
- **Module-level pre-upgrade audit** → route to `odoo-deprecation-audit`
- **Override safety analysis** → route to `odoo-override-finding`
- **Verifying a render error in a real browser** → route to `odoo-debug`
- **Rating a rendered screen's look / UX / accessibility** → route to `odoo-ui-review` (static source review here never judges rendered appearance)

## When to invoke

Invoke the `odoo-code-reviewer` agent when Odoo code needs review. Review scales with change size: one module -> one reviewer; many modules -> per-module fan-out + Opus integration pass.

**Two entry paths - choose before dispatching the scoper:**

- **Pasted block or single file_path (not a git target):** dispatch ONE `odoo-code-reviewer` directly (skip scoper); the block/file is the scope.
- **Git target (local tree, worktree, or PR):** dispatch `odoo-review-scoper` first (Phase 0), then fan-out reviewers from its output. Each leg runs as an autonomous agent.

**Derive `TARGET` from user intent:**

| User intent | TARGET to pass |
|---|---|
| "review this" on the working tree | `TARGET: local` |
| "review PR #N" or a GitHub PR URL | `TARGET: pr:<N>` or `TARGET: pr:<url>` |
| Work lives in another worktree | `TARGET: worktree:<abs-path>` - REQUIRED; if omitted, scoper diffs principal cwd (empty diff -> BLOCKED) |
| Pasted block / single file_path, no git context | skip scoper (see above) |

For a sibling git worktree (wave/forward-port integration tree), the orchestrator passes its WORKTREE_PATH as `TARGET: worktree:<abs-path>` so review runs there, not cwd.

## Phase 0 - Scope the review (git targets only)

**Pre-resolution for `TARGET=pr:<N>` (before dispatching the scoper)** - resolve the PR to an isolated worktree via the `git-toolkit:git-ops` skill (delegation contract: `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`):
1. Invoke `git-toolkit:git-ops` to fetch PR metadata + changed-file list: `pr_meta = {number, title, head, base, repo}`, `pr_changed_files = [<path>, ...]`.
2. Invoke `git-toolkit:git-ops` to create an isolated worktree (`/tmp/pr-review-<N>`, S9 - never the main checkout) with the PR branch checked out; receive `review_root`.

Pass `review_root`, `pr_meta`, `pr_changed_files` into the scoper brief (the scoper no longer resolves these).

Dispatch agent `odoo-review-scoper` (sonnet) per the SCOPER I/O CONTRACT (SSOT: `${CLAUDE_PLUGIN_ROOT}/agents/odoo-review-scoper.md`). Pass:
- `TARGET:` - `local` | `worktree:<abs-path>` | `pr:<number-or-url>` (for `pr`, also `review_root`, `pr_meta`, `pr_changed_files`)
- `BASE:` - default `master`
- `odoo_version:` - target series
- `USER LANGUAGE:` - language for the scoper's output

The scoper writes `.odoo-ai/reviews/<slug>-<date>/_scope.md` and returns the compact scope. Do NOT run git diff inline, map `__manifest__.py`, or call `test_coverage_audit` in main context - the scoper handles all of it.

Scope output fields used by main: full field schema per Step 6 of the scoper I/O contract (`${CLAUDE_PLUGIN_ROOT}/agents/odoo-review-scoper.md`). Key dispatch behaviors:

**Mode detection:** master-child mode iff `master_design_doc != none` in the scope block; else single mode.

- `design_doc` (per-module column in master-child; `### Design doc` field in single): when non-null, pass as `DESIGN_DOC:` to each per-module reviewer - MANDATORY TDD verify (§1 Intent + §9 ACs + `### TDD Conformance`; skipping is a review defect).
- `master_design_doc`: when != none, pass as `MASTER_DESIGN_DOC:` to all reviewers AND synthesis - MANDATORY §10 cross-module constraint check; violation = CRITICAL.
- `coverage_baseline`: pass as `COVERAGE_BASELINE:` - label BASELINE throughout to distinguish from per-model `COVERAGE_CHECK`.
- `needs_ui_review` (per module): drives `UI_REVIEW=delegated` arm (Phase A) and Phase A.5 dispatch.

Decide review topology from `fanout`: `single` → one reviewer pass; `multi` → fan-out + synthesis.

## Single module (the common case)

Dispatch ONE `odoo-code-reviewer` agent (sonnet). It writes its report to `.odoo-ai/reviews/<slug>-<date>/<module>.md`. No synthesis pass needed for a single module. When `module.needs_ui_review` is `true` or `candidate`, add `UI_REVIEW=delegated` to the reviewer brief and run Phase A.5 (same instance-check + dispatch) after the reviewer completes.

## Multi-module - fan-out, then integration synthesis

### Phase A - Per-module fan-out (parallel sonnet)

Dispatch one `odoo-code-reviewer` agent per module in `modules[]`, all in one batch. Concurrency is bounded by the harness automatically - do NOT set a manual wave-cap (policy SSOT: `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md`). Each agent is scoped to ONLY its module, reads files at `review_root`, writes `<module>.md` to `.odoo-ai/reviews/<slug>-<date>/`, and returns a short summary + path.

When the CHP capability probe is positive (Agent Team mode on), TaskCreate one task per work-item, inject TASK_ID + REPLY_TO: <this skill's current orchestrating context> (this skill runs INLINE in whatever invoked it - that context IS `main` when the main-context driver invoked it, per CHP capability-probe condition 4; do NOT hardcode a literal `main` if you are running inside a non-lead agent) + NOTIFY: <dependent names> into each teammate brief, poll TaskList/TaskGet, and read each result from the teammate's SendMessage push (NEVER from the .output transcript) - per `${CLAUDE_PLUGIN_ROOT}/snippets/agent-team-protocol.md` (defense-in-depth; see also `${CLAUDE_PLUGIN_ROOT}/snippets/spawner-completion-contract.md` R3). When off, dispatch + collect inline.

**When `module.needs_ui_review` is `true` or `candidate`**, add `UI_REVIEW=delegated` to that module's reviewer brief. Under that flag the reviewer reviews everything NON-rendered - Python/ORM/security/perf/data AND the SOURCE correctness of the view layer (XPath targets resolve, view `arch` well-formed, no dead JS import, SCSS compiles + reuses real tokens) - but does NOT grade rendered appearance, UX, accessibility, or runtime (delegated to Phase A.5's `odoo-ui-reviewer`). It still writes `<module>.md` (for a `candidate`, resolve view-binding via OSM and record `ui_review_required` there).

**Before dispatching the batch**, for each affected model in `modules[]` call OSM `tests_covering(model='<affected_model>', odoo_version='<version>')` and include the result as `COVERAGE_CHECK:` in each reviewer brief (model-edge level; distinct from the scoper's module-level `COVERAGE_BASELINE`).

**Before flagging pitfall #10 (behavior change with no protecting test) as HIGH**, verify with evidence: if `COVERAGE_CHECK` shows zero covering tests, the HIGH finding stands, noting "zero test edges confirmed via `tests_covering` (model-level)"; if tests exist but do not cover the changed path, it stays HIGH noting "tests exist for model but do not cover this behavior"; without this check, downgrade to MED. **Method-narrow caveat:** `tests_covering` with `method=` returns zero for many well-tested methods (COVERS_METHOD edges are sparse) - a method-narrow zero is supporting evidence, not proof; corroborate with the model-level count or `find_test_examples` before escalating to HIGH.

### Phase A.5 - Rendered-UI review (conditional, per module)

**Widen the render-check scope to dependents (blast-radius)** - a changed field/method/view/component ripples into DEPENDENT modules that `super()`/`xpath`/`inherit` it. Derive the widened set per `${CLAUDE_PLUGIN_ROOT}/snippets/acceptance-scope.md` (reverse-closure -> risk rank -> affected screens): `render_check_set` = every screen binding a changed symbol across the changed modules AND their dependents, each tagged a risk tier (High = deep, Low = smoke). This stays a STATIC code-review pass (it only widens which screens the conditional ui-reviewer covers; it runs no CRUD/role flows). OSM is PRIMARY for the closure; fall back to disk and label it approximate when OSM is unreachable.

For each module with `needs_ui_review` (`true` or `candidate`), plus each dependent module the `render_check_set` flags:
- **For a `candidate` module**, first read its `<module>.md` and check `ui_review_required`; skip the ui-reviewer dispatch when it is `false` or absent (the reviewer already resolved the Python change is not view-bound).
- **Resolve an instance.** Read `instance_base_url` from `.odoo-ai/context.md`, else `~/.odoo-ai/instances.toml` (project `./.odoo-ai/instances.toml` is a transitional fallback; SSOT `${CLAUDE_PLUGIN_ROOT}/snippets/instance-resolution.md`), and confirm a browser MCP is reachable.
- **Instance reachable** → dispatch one `odoo-ui-reviewer` (sonnet) scoped to that module's screens from the `render_check_set` (changed-module `affected_screens` plus the dependent screens that bind a changed symbol), briefing `ARTIFACT_DIR: .odoo-ai/reviews/<slug>-<date>/` and `ARTIFACT_FILE: ui-review-<module>.md` (brief template in `references/agent-prompts.md`). These run in parallel; each `ui-review-<module>.md` feeds Phase B synthesis.
- **No instance / browser unreachable** → do NOT block, and do NOT let the UI dimension drift silently. Write `ui-review-<module>.md` holding `UI review REQUIRED - no running instance (render_check_set: [...])`, mark the run `DONE_WITH_CONCERNS` for the UI dimension, AND emit `next: odoo-acceptance` (see below) so the dependent cluster is verified opt-in rather than skipped.

**Emit the acceptance hand-off (L2, opt-in).** Whenever the `render_check_set` reaches beyond the changed modules (dependents bind a changed symbol) OR the rendered-UI dimension is left `DONE_WITH_CONCERNS` (no instance), add a `next` entry to this skill's Continuation Contract (the same contract carrying `produced[]`):

```
next:
  - skill: odoo-acceptance
    reason: change touches a UI/behavior surface with dependents (render_check_set beyond the changed modules); run blast-radius acceptance over the affected cluster
    inputs: {changed_set: [<modules|model.field|model.method>], scope_hint: ".odoo-ai/qa/<slug>-scope.md", odoo_version: "<version>"}
    confidence: 0.7
    gate_tier: L2
```

Opt-in: it surfaces the verdict + recommended acceptance pass for an L2 (human) gate - never auto-blocks the review, never auto-runs acceptance. `scope_hint` is advisory (odoo-acceptance Phase 0 regenerates the verify-scope manifest from the changed set).

### Phase B - Integration synthesis (OPUS)

Pick the synthesis topology by scale - default threshold **~8 modules** (adjustable: lower it when per-module reports are unusually large and the combined set would overflow one opus context).

**Small set (`len(modules)` ≤ ~8 and reports fit one context) - single pass:**
Dispatch ONE `odoo-code-reviewer` at **opus**. Scope = full **dependency closure** from OSM:
- **Forward closure:** walk `module_inspect(name=<m>, method='dependencies', odoo_version='<version>')` transitively.
- **Reverse closure:** `impact_analysis(...)` on changed modules, walked transitively.

It reviews only what per-module legs cannot: override-chain conflicts, inheritance/MRO across closure, inter-module field/API contract breaks, manifest `depends` and data load-order, ripple into dependents. It `Read`s every `<module>.md` AND every `ui-review-<module>.md` on disk; writes `_synthesis.md`.

**Large set (`len(modules)` > ~8 or reports overflow one context) - domain-partition:**
1. **Group by business domain** - classify each module with OSM `describe_module` (fall back to the manifest `category` on disk) into business-domain buckets (e.g. Accounting/Finance, Sales/CRM, Purchase, Inventory/Logistics, MRP, HR/Payroll, Project/Helpdesk, eCommerce/Website, Core/Base).
2. **Per-domain synthesis** - for each bucket, dispatch one `odoo-code-reviewer` at **opus** (`MODE=synthesis`, scoped to that bucket): it reads only that bucket's `<module>.md` + `ui-review-<module>.md`, computes the closure WITHIN the bucket, and writes `domain-<d>.md`.
3. **Final cross-domain synthesis** - dispatch ONE final `odoo-code-reviewer` at **opus** that `Read`s every `domain-<d>.md`, computes cross-domain closure (inter-domain field/API contracts, load-order, ripple), and writes `_synthesis.md` with the overall verdict + score.

(The per-domain and final cross-domain passes use the two domain-synthesis brief templates in `references/agent-prompts.md`.)

**`DESIGN_DOC` for synthesis:** In master-child mode, pass `DESIGN_DOC: null` to ALL synthesis passes (per-module §9 ACs verified in Phase A; synthesis checks §10 only via `MASTER_DESIGN_DOC`). In single mode, pass the flat TDD path as `DESIGN_DOC`.

## Artifacts

All output under `.odoo-ai/reviews/<slug>-<YYYY-MM-DD>/` (gitignored). Slug comes from scoper `slug` field; every phase agent (scoper, per-module reviewer, ui-reviewer, domain + final synthesis) writes ONLY into this directory:
- `_scope.md` - scoper output (written by scoper agent)
- `<module>.md` - per-module review (or single-module review); each contains VERDICT + SCORE per the `odoo-code-reviewer` agent output contract (SSOT: `${CLAUDE_PLUGIN_ROOT}/agents/odoo-code-reviewer.md`)
- `ui-review-<module>.md` - rendered-UI six-lens review for a `needs_ui_review` module (Phase A.5); when no instance was available it holds the `UI review REQUIRED - no running instance` placeholder (run is `DONE_WITH_CONCERNS` for UI)
- `_synthesis.md` - Opus integration review; also contains overall VERDICT (APPROVE/REQUEST_CHANGES) + SCORE 0-100
- `domain-<d>.md` - per-domain synthesis (large sets only, Phase B domain-partition); the final `_synthesis.md` is built from these
- `index.md` - short map: modules reviewed, dependency closure, per-module severity counts, overall verdict + score, highest-severity findings linking to detail files

Report is presented as an artifact in chat by default. Post to PR ONLY on explicit request (keyword
`post`). Do NOT hand over a single review body. `git-toolkit:git-ops` is domain-agnostic: its
inline-findings fan-out recipe (its GitHub specialist owns the create-pending -> per-finding ->
submit fan-out internally) consumes a plain findings array and knows nothing about an Odoo "Issues
table" or a "Suggested replacement" block. THIS skill - the owner of that Odoo-specific shape -
CONVERTS it BEFORE invoking `git-toolkit:git-ops`:

1. **Build `findings[]`** - one object per Issues-table row, across every report in scope. Post
   EVERY severity CRITICAL through LOW so no finding is dropped. Per finding, emit exactly:
   `{path, startLine, line, severity, body, suggestion}` where:
   - `path` (diff-relative) - the row's `File` value, already repo-relative per the agent contract
     - never the `review_root` worktree-absolute path.
   - `startLine` - parsed from the row's `Line/Range`: a bare line `N` gives `startLine=N`; a range
     `A-B` gives `startLine=A`.
   - `line` - the LAST line of the range: `=startLine` for a single line, `=B` for range `A-B`.
   - `severity` - the row's `Severity` value verbatim.
   - `body` - the row's `Issue` cell (+ `Suggested fix` prose when no replacement block exists).
   - `suggestion` (optional) - when the row has a matching `#### <File>:<Line/Range>` Suggested
     replacement block, that block's fenced lines VERBATIM, with NO ```suggestion wrapper (the
     poster adds the fence); omit the key entirely when the row has no replacement block.
2. **Invoke `git-toolkit:git-ops`** (Skill tool) with `owner`/`repo` (from the scope's
   `### PR metadata` `repo: <fullName>`, split on `/`), `pullNumber` (`number`), the `findings[]`
   array just built, and the instruction: "open ONE pending review, post one inline comment per
   `findings[]` entry, then submit the pending review with event REQUEST_CHANGES if any
   CRITICAL/HIGH remains, else COMMENT." Pass the array - never a bare report path + prose;
   `git-toolkit:git-ops` stays generic and never sees the words "Issues table" or "Suggested
   replacement".

Post the synthesis-level verdict/score as ONE separate top-level PR comment (flat) - the summary
only, never a substitute for the per-finding inline comments. "Prefer inline" = this fan-out,
always.

Emit paths in the Continuation Contract `produced[]`; later steps reference these instead of re-reviewing.

## Brief context - Odoo review pitfalls

Eleven failure modes the agent checks for. Full details:
`${CLAUDE_PLUGIN_ROOT}/skills/odoo-code-review/references/review-pitfalls.md`

Summary: (1) ORM/N+1, (2) missing `super()` in create/write/unlink, (3) `@api.depends` errors, (4) deprecated API, (5) OWL reactivity + `position="replace"`, (6) design-system SCSS/token fidelity (flag per `${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-frontend-fidelity.md`), (7) coding-guideline conventions (grounded against `coding_guidelines/<version>/`), (8) runtime presence probing (`hasattr`/`getattr` smell), (9) platform design principles (company/branch isolation, generic-before-localization, app-menu shape), (10) behavior change with no protecting test → HIGH finding → launch the `odoo-test-writer` agent (context-isolated; it authors by invoking the `odoo-test-writing` skill inline), (11) forward-ported test coupled to source-version API/snapshot → assert observable outcome on target, RED-then-GREEN, launch the `odoo-test-writer` agent (adapt mode).

## Agent invocation

When composing the dispatch prompt for `odoo-code-reviewer`, fill the universal skeleton in `${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md` (read by path) plus the Reviewer/auditor family delta.

Full prompt templates: `${CLAUDE_PLUGIN_ROOT}/skills/odoo-code-review/references/agent-prompts.md`

Key constraints for each dispatched agent:
- Per-module (sonnet): write `<module>.md`, light bidirectional-impact pass, platform-design check, flag unprotected behavior. Return 5-line summary + path.
- Synthesis (opus): cross-module closure only; read per-module reports on disk; write `_synthesis.md`. Return summary + path.
- Each agent: restricted tools, writes only its own artifact, does NOT spawn subagents. `odoo-code-reviewer` MAY invoke the Skill tool inline, but only for its own dedicated-audit escalation (see `agents/odoo-code-reviewer.md`); every other dispatched agent (scoper, ui-reviewer) still does NOT invoke Skill tool.
- Guidelines: reviewer reads `<version>/INDEX.md` index-first, consults the "By task" table, reads ONLY the files mapping to the changed file types (not all 6 topic files; full contract: `${CLAUDE_PLUGIN_ROOT}/snippets/read-before-write-contract.md`).

After legs finish, main writes `index.md` summarizing the set.

## Standalone-first fallback

When OSM (the odoo-semantic-mcp server) is unreachable, each reviewer falls back to static analysis against internalized Odoo conventions. MCP-enriched findings are skipped; output notes "MCP unavailable - static analysis only". For synthesis, derive dependency closure from disk: read each changed module's `__manifest__.py` `depends` (forward) and `grep -rl "_inherit\|depends.*<module>"` across addons path for approximate reverse; label "closure approximate from disk (OSM unavailable)". Fan-out/synthesis topology still applies; only grounding degrades. When OSM is reachable but a customer-local addon is not in the index (Tier-1 MISS), keep OSM for indexed entities and Read/Grep the local addon for the missed ones (grounded: osm + local-source hybrid, per `snippets/disk-fallback-protocol.md`).

## Agent-managed tools

See `agents/odoo-code-reviewer.md` for the full restricted tool list and execution detail.

## Autonomous fix loop - drive it yourself (mandatory)

You MUST use the Skill tool to drive the fix loop - do not write a report and stop. A passive `next: odoo-coding` advances nothing when no run-harness is active (a direct invocation or intake fast-path - the common case), so the loop would die. Therefore:

1. **On a CRITICAL or HIGH finding that needs a code change, drive the fix yourself - attempt CHP Tier A first, fall back to Tier C.** Per `${CLAUDE_PLUGIN_ROOT}/snippets/context-handoff-protocol.md`: if the capability probe passes (env + `SendMessage` tool present + you are the lead) AND the original `coder-<module>` agentId is recorded in plan.md, take the **Tier-A path** - `SendMessage` the review findings + fix instructions (framed as shared team context / prior-phase findings, never as "secret") directly to that recorded agentId, then **PARK: end your turn here (emit nothing after the SendMessage call), do NOT await a synchronous return (`SendMessage` is fire-and-forget) - you are resumed automatically when the coder replies.** If any probe condition fails or the agentId is not addressable, take the **Tier-C fallback** (always correct): **IMMEDIATELY invoke `odoo-coding` via the Skill tool yourself**, passing it the review report path, the exact findings to fix, and the literal line **"AUTONOMOUS FIX (review-driven): skip your Phase 0 human gate, fix to these findings, then invoke odoo-code-review to verify"** (keep this sentinel text unchanged for the Tier-C path). Either way this is autonomous - do NOT pause for a human (running the review IS the opt-in).
2. The coder fixes, then comes back to you to verify - the resumed Tier-A worker replies to you, or the Tier-C `odoo-coding` invokes you again. That round-trip - **review → code → review** - repeats until the review is clean (no CRITICAL/HIGH and the behavior is covered).
3. **Bound it to 3 iterations.** If still not clean after 3, STOP and escalate to the human with what remains - bad work is worse than no work, never loop forever. Record each iteration in the worklog.

The ONLY case where you emit a Continuation Contract `next` and let a driver advance instead of invoking directly: your brief shows you were dispatched **by an active run-harness** (a `run-<id>` is named) - then do not double-dispatch.

## Continuation Contract

Before finishing, APPEND your significant findings/decisions to the run worklog (`.odoo-ai/worklog/<run-or-slug>/`) per `${CLAUDE_PLUGIN_ROOT}/snippets/worklog-contract.md`.

When you finish, append a Continuation Contract block per `${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next). Set `produced` to the paths actually written; decide the `next` arm by what the review found (test-discipline SSOT: `${CLAUDE_PLUGIN_ROOT}/snippets/test-first-contract.md`).
**The `next:` entries below are the audit record AND the run-harness path - NOT a substitute for the direct Skill-tool invoke in § Autonomous fix loop.** With NO run-harness active you have ALREADY invoked the target; `next:` advances nothing on its own, so **never stop at it**.
- CRITICAL/HIGH findings needing a code fix → you invoked `odoo-coding` directly (§ Autonomous fix loop); under an active run-harness instead, emit `next: odoo-coding` with `inputs: {odoo_version: <run's resolved version>, report_path: <this report>, ...}` (the driver bounds the loop to 3 iterations, then escalates).
- Behavior change with no protecting test (pitfall #10) → when the code is fine and only the test is missing, LAUNCH the `odoo-test-writer` agent directly (context isolation; it authors by invoking the `odoo-test-writing` skill inline) for the protecting RED test; when a code fix is also needed, drive it through `odoo-coding` (test-first - its `odoo-coder` coordinator launches `odoo-test-writer` per WI). Under an active run-harness, emit `next: odoo-coding` with `inputs: {odoo_version: <run's resolved version>, module: <module>, behavior: <behavior>, ...}`.
- Clean review, behavior covered → no fix, no `next` (loop terminates).
A CRITICAL bug in a behavior that also lacks a test drives BOTH the RED test and the fix through `odoo-coding` (test-first) - under a run-harness: `next: odoo-coding` with `inputs: {odoo_version: <run's resolved version>, ...}`. Additive output for the run-harness; it changes nothing produced above.
