---
name: odoo-code-review
description: >
  Review Odoo code (Python, JavaScript, XML, OWL) for bugs, convention violations, security,
  and performance - severity-graded findings, suggested fixes, corrected version. Dispatches
  to the odoo-code-reviewer agent. Fire whenever code is shared with feedback intent, even
  without the word "review". Trigger on: "does this look correct?", "audit this PR",
  "should I worry about N+1?", "before I merge", "review PR #123", "review this pull request".
  Also fires on Vietnamese: "review giúp đoạn này", "kiểm tra code Odoo", "code này có bug
  không", "soát trước khi merge", "đánh giá PR". Trigger on model overrides, write/create
  overrides, computed fields, OWL components, or XML view overrides - Odoo-specific failure
  modes a generic reviewer misses. Static analysis only - live render errors → odoo-debug.
  Write new code → odoo-coding. Pre-upgrade audit → odoo-deprecation-audit
---

## Persona

Developer / Tech Lead reviewing Odoo code with semantic MCP enrichment.

## Out of Scope

- **Writing new code** → route to `odoo-coding`
- **Module-level pre-upgrade audit** → route to `odoo-deprecation-audit`
- **Override safety analysis** → route to `odoo-override-finding`
- **Verifying a render error in a real browser** → route to `odoo-debug`

## When to invoke

Main agent invokes the `odoo-code-reviewer` **agent** (as a subagent launch) when Odoo code needs review. Review **scales with the change size**: one module → one reviewer; many modules → per-module fan-out plus Opus integration pass.

**Two entry paths - choose before dispatching scoper:**

- **Pasted block or single file_path (not a git target):** treat as one review unit, dispatch ONE `odoo-code-reviewer` directly (skip scoper). The code block / file is the review scope; no diff resolution needed.
- **Git target (local working tree, worktree, or PR):** dispatch `odoo-review-scoper` first (Phase 0), then fan-out reviewers from scoper output. Because review needs parallel MCP round-trips, each leg runs as an autonomous agent.

**Deriving `TARGET` from user intent:**

| User intent | TARGET to pass |
|---|---|
| No explicit target - just "review this" on the working tree | `TARGET: local` |
| "review PR #N" or a GitHub PR URL | `TARGET: pr:<N>` or `TARGET: pr:<url>` |
| Orchestrator dispatching from a principal tree where work lives in another worktree | `TARGET: worktree:<abs-path>` - REQUIRED; if omitted, scoper diffs principal cwd (empty diff → BLOCKED) |
| Pasted code block or single file_path with no git context | skip scoper - see pasted-block path above |

For a sibling git worktree (e.g. the wave/forward-port integration tree), the orchestrator passes its WORKTREE_PATH as `TARGET: worktree:<abs-path>` so review runs there, not cwd.

## Phase 0 - Scope the review (git targets only)

**Pre-resolution for `TARGET=pr` (do before dispatching the scoper):**

For `TARGET=pr:<N>`, the skill MUST resolve the PR to an isolated worktree via git-toolkit agents before the scoper is dispatched:
1. Dispatch **github-operator** to fetch PR metadata and the changed file list. Collect `pr_meta = {number, title, head, base, repo}` and `pr_changed_files = [<path>, ...]`.
2. Dispatch **git-operator** to create an isolated worktree (path `/tmp/pr-review-<N>`, S9 contract - never the main checkout) with the PR branch checked out. Receive back `review_root`.

Then pass `review_root`, `pr_meta`, and `pr_changed_files` into the scoper brief. The scoper no longer fetches PR metadata or creates the worktree itself.

Git delegation contract: `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`

---

Dispatch agent `odoo-review-scoper` (sonnet) per the SCOPER I/O CONTRACT (full SSOT: `${CLAUDE_PLUGIN_ROOT}/agents/odoo-review-scoper.md`). Pass it:
- `TARGET:` - `local` | `worktree:<abs-path>` | `pr:<number-or-url>` (for `pr`, also pass `review_root`, `pr_meta`, and `pr_changed_files` from the pre-resolution step above; the scoper no longer resolves these itself)
- `BASE:` - default `master`
- `odoo_version:` - target series
- `USER LANGUAGE:` - language for the scoper's own output

The scoper writes a compact scope file at `.odoo-ai/reviews/<slug>-<date>/_scope.md` and returns the scope result directly. Main receives the compact output only (keeps main context clean - do NOT run git diff inline, map `__manifest__.py`, or call `test_coverage_audit` in main context; the scoper handles all of this).

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

Dispatch one `odoo-code-reviewer` agent per module in `modules[]` from the scoper output, all in one batch. Fan-out is one reviewer per module; concurrency is bounded by the harness automatically - do NOT set a manual wave-cap. For the project-level concurrency policy and any overrides, see the SSOT at `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md`. Each agent is scoped to ONLY its module; it reads files at `review_root` (from scoper). Each agent writes `<module>.md` to `.odoo-ai/reviews/<slug>-<date>/` and returns a short summary + path.

**When `module.needs_ui_review` is `true` or `candidate`**, add `UI_REVIEW=delegated` to that module's reviewer brief. Under that flag the reviewer still reviews everything NON-rendered - Python/ORM/security/perf/data AND the SOURCE correctness of the view layer (XPath targets resolve, view `arch` well-formed, no dead JS module import, SCSS compiles + reuses real tokens) - but does NOT grade rendered appearance, UX, accessibility, or runtime; that rendered-UI verdict is delegated to Phase A.5's `odoo-ui-reviewer`, so the two passes never overlap. The reviewer still writes `<module>.md` (and, for a `candidate`, resolves view-binding via OSM and records `ui_review_required` there).

**Before dispatching the batch**, for each affected model in `modules[]`, call OSM `tests_covering(model='<affected_model>', odoo_version='<version>')`. Collect results. Include the result as `COVERAGE_CHECK:` in each reviewer brief so the agent has the evidence without re-querying. `COVERAGE_CHECK` is model-edge level data from main (distinct from `COVERAGE_BASELINE` which is the module-level `test_coverage_audit` result from the scoper).

**Before flagging pitfall #10 (behavior change with no protecting test) as a HIGH finding**, verify with evidence rather than heuristic: if the model-level `COVERAGE_CHECK` shows zero covering tests, the HIGH finding stands and should note "zero test edges confirmed via `tests_covering` (model-level)". If tests exist but do not cover the changed path, the finding stays HIGH with the note "tests exist for model but do not cover this behavior". A finding without this check is heuristic and should be downgraded to MED. **Caveat on method-narrow queries:** `tests_covering` with `method=` returns zero edges for many well-tested methods because COVERS_METHOD edges are sparse; a zero from a method-narrow call is supporting evidence, not proof - corroborate with the model-level count or `find_test_examples` before escalating to HIGH.

### Phase A.5 - Rendered-UI review (conditional, per module)

For each module with `needs_ui_review` (`true` or `candidate`):
- **For a `candidate` module**, first read its `<module>.md` and check `ui_review_required`; skip the ui-reviewer dispatch when it is `false` or absent (the reviewer already resolved the Python change is not view-bound).
- **Resolve an instance.** Read `instance_base_url` from `.odoo-ai/context.md`, else `~/.odoo-ai/instances.toml` (project `./.odoo-ai/instances.toml` is a transitional fallback; SSOT `${CLAUDE_PLUGIN_ROOT}/snippets/instance-resolution.md`), and confirm a browser MCP is reachable.
- **Instance reachable** → dispatch one `odoo-ui-reviewer` (sonnet) scoped to that module's `affected_screens`, briefing `ARTIFACT_DIR: .odoo-ai/reviews/<slug>-<date>/` and `ARTIFACT_FILE: ui-review-<module>.md` (brief template in `references/agent-prompts.md`). These run in parallel; each `ui-review-<module>.md` feeds Phase B synthesis.
- **No instance / browser unreachable** → do NOT block. Write `ui-review-<module>.md` holding `UI review REQUIRED - no running instance (affected_screens: [...])`, and mark the run `DONE_WITH_CONCERNS` for the UI dimension - surface to the user that an instance is needed to finish the rendered-UI review.

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

Report is presented as an artifact in chat by default. Post to PR ONLY when user explicitly requests it (keyword `post`): delegate to **github-operator** (via Agent tool) with the PR number from `pr.number` in the scope result and the review body; github-operator posts via the PR comment API (flat) or PR review API (per-finding inline) - prefer inline for actionable findings.

Emit paths in the Continuation Contract `produced[]`; later steps reference these instead of re-reviewing.

## Brief context - Odoo review pitfalls

Eleven failure modes the agent checks for. Full details:
`${CLAUDE_PLUGIN_ROOT}/skills/odoo-code-review/references/review-pitfalls.md`

Summary: (1) ORM/N+1, (2) missing `super()` in create/write/unlink, (3) `@api.depends` errors, (4) deprecated API, (5) OWL reactivity + `position="replace"`, (6) design-system SCSS/token fidelity (flag per `${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-frontend-fidelity.md`), (7) coding-guideline conventions (grounded against `coding_guidelines/<version>/`), (8) runtime presence probing (`hasattr`/`getattr` smell), (9) platform design principles (company/branch isolation, generic-before-localization, app-menu shape), (10) behavior change with no protecting test → HIGH finding → route to `odoo-test-writing`, (11) forward-ported test coupled to source-version API/snapshot → assert observable outcome on target, RED-then-GREEN, route to `odoo-test-writing` mode `adapt`.

## Agent invocation

Full prompt templates: `${CLAUDE_PLUGIN_ROOT}/skills/odoo-code-review/references/agent-prompts.md`

Key constraints for each dispatched agent:
- Per-module (sonnet): write `<module>.md`, light bidirectional-impact pass, platform-design check, flag unprotected behavior. Return 5-line summary + path.
- Synthesis (opus): cross-module closure only; read per-module reports on disk; write `_synthesis.md`. Return summary + path.
- Each agent: restricted tools, writes only its own artifact, does NOT spawn subagents, does NOT invoke Skill tool.
- Guidelines: reviewer reads `<version>/INDEX.md` index-first, consults the "By task" table, reads ONLY the files mapping to the changed file types (not all 6 topic files; full contract: `${CLAUDE_PLUGIN_ROOT}/snippets/read-before-write-contract.md`).

After legs finish, main writes `index.md` summarizing the set.

## Standalone-first fallback

When OSM (the odoo-semantic-mcp server) is unreachable, each reviewer falls back to static analysis against internalized Odoo conventions. MCP-enriched findings are skipped; output notes "MCP unavailable - static analysis only". For synthesis, derive dependency closure from disk: read each changed module's `__manifest__.py` `depends` (forward) and `grep -rl "_inherit\|depends.*<module>"` across addons path for approximate reverse; label "closure approximate from disk (OSM unavailable)". Fan-out/synthesis topology still applies; only grounding degrades. When OSM is reachable but a customer-local addon is not in the index (Tier-1 MISS), keep OSM for indexed entities and Read/Grep the local addon for the missed ones (grounded: osm + local-source hybrid, per `snippets/disk-fallback-protocol.md`).

## Agent-managed tools

See `agents/odoo-code-reviewer.md` for the full restricted tool list and execution detail.

## Autonomous fix loop - drive it yourself (mandatory)

The Skill tool is available in the main context where you run, and you MUST use it to drive the fix loop - do not write a report and stop. A passive `next: odoo-coding` is NOT enough: when no run-driver is active (a direct invocation, or an intake fast-path - the common case), nothing advances that `next` and the loop dies. So:

1. **On a CRITICAL or HIGH finding that needs a code change, drive the fix yourself - attempt CHP Tier A first, fall back to Tier C.** Per `${CLAUDE_PLUGIN_ROOT}/snippets/context-handoff-protocol.md`: if the capability probe passes (env + `SendMessage` tool present + you are the lead) AND the original `coder-<module>` agentId is recorded in plan.md, take the **Tier-A path** - `SendMessage` the review findings + fix instructions (framed as shared team context / prior-phase findings, never as "secret") directly to that recorded agentId, then **PARK: end your turn here (emit nothing after the SendMessage call), do NOT await a synchronous return (`SendMessage` is fire-and-forget) - you are resumed automatically when the coder replies.** If any probe condition fails or the agentId is not addressable, take the **Tier-C fallback** (always correct): **IMMEDIATELY invoke `odoo-coding` via the Skill tool yourself**, passing it the review report path, the exact findings to fix, and the literal line **"AUTONOMOUS FIX (review-driven): skip your Phase 0 human gate, fix to these findings, then invoke odoo-code-review to verify"** (keep this sentinel text unchanged for the Tier-C path). Either way this is autonomous - do NOT pause for a human (running the review IS the opt-in).
2. The coder fixes, then comes back to you to verify - the resumed Tier-A worker replies to you, or the Tier-C `odoo-coding` invokes you again. That round-trip - **review → code → review** - repeats until the review is clean (no CRITICAL/HIGH and the behavior is covered).
3. **Bound it to 3 iterations.** If still not clean after 3, STOP and escalate to the human with what remains - bad work is worse than no work, never loop forever. Record each iteration in the worklog.

The ONLY case where you emit a Continuation Contract `next` and let a driver advance instead of invoking directly: your brief shows you were dispatched **by an active run-driver** (a `run-<id>` is named) - then do not double-dispatch.

## Continuation Contract

Before finishing, APPEND your significant findings/decisions to the run worklog (`.odoo-ai/worklog/<run-or-slug>/`) per `${CLAUDE_PLUGIN_ROOT}/snippets/worklog-contract.md`.

When you finish, append a Continuation Contract block per `${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next). Set `produced` to the artifact paths actually written. Decide the `next` arm by what the review found (test-discipline SSOT: `${CLAUDE_PLUGIN_ROOT}/snippets/test-first-contract.md`).
**The `next:` entries below are the audit record AND the run-driver path - NOT a substitute for the direct Skill-tool invoke in § Autonomous fix loop.** With NO run-driver active (the common direct / intake-fast-path case) you have ALREADY invoked the target per § Autonomous fix loop; `next:` advances nothing on its own, so **never stop at it**.
- CRITICAL/HIGH findings that need a code fix → you invoked `odoo-coding` directly (§ Autonomous fix loop); under an active run-driver instead, emit `next: odoo-coding` carrying the report path (the driver bounds the loop to 3 iterations, then escalates).
- A behavior change with no protecting test (pitfall #10) → drive it through `odoo-coding` (which is test-first) the same way; under a run-driver, emit `next: odoo-test-writing` carrying the module + behavior so the gap is closed before merge.
- Clean review, behavior covered → no fix needed, no `next` (the loop terminates).
A review that finds a CRITICAL bug in a behavior that also lacks a test drives BOTH the protecting test and the fix (under a run-driver: `next: odoo-coding` and `next: odoo-test-writing`).
Additive output for the run-driver - it does not change anything produced above.
