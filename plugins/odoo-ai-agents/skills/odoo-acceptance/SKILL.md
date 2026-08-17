---
name: odoo-acceptance
argument-hint: "[module/cluster to accept]"
description: >
  Run end-to-end Odoo acceptance on a change AND its blast-radius: map the affected cluster, plan an
  INDEPENDENT oracle, then EXECUTE it on a real running instance/UI and adjudicate PASS/FAIL with
  evidence. Fire on: acceptance test, QA the affected cluster, verify on the real UI, "write scenarios
  then run them", verify blast-radius, "works end-to-end before release". Also Vietnamese: "nghiệm thu
  cụm module", "chạy thật trên UI", "kịch bản test rồi chạy", "kiểm thử chấp nhận". Sole dispatcher of
  odoo-qa-planner (oracle) + odoo-qa-tester (live run); chains tours/HttpCase via odoo-instance.
  Routing: a STATIC release test-plan doc / deploy checklist -> route to odoo-qa-suite; rating ONE
  rendered screen -> route to odoo-ui-review; static code or PR review with no run -> route to
  odoo-code-review; writing the fix -> route to odoo-coding. EXECUTION needs a live instance + browser
  MCP (Odoo Semantic is static, no live data); with none up it still scopes + plans the oracle, then
  emits NEEDS_NEXT to provision one
---

## Role

Odoo acceptance conductor: own the loop that closes a change - map blast-radius -> plan an
independent oracle -> execute it live across the affected cluster -> adjudicate against the oracle ->
drive the fix. Keep your context clean; delegate each heavy phase to a specialist. Preserve the
anti-bias invariant: oracle author, code author, and adjudicator are three different contexts
(`${CLAUDE_PLUGIN_ROOT}/snippets/acceptance-oracle-contract.md`). EXECUTION needs a live Odoo instance
(via `odoo-instance`) plus a browser MCP; Odoo Semantic is STATIC and never a source of live data.

**Sole dispatcher of acceptance fan-out.** This skill is the ONLY component that launches the
`odoo-qa-planner` (independent oracle author) and `odoo-qa-tester` (live executor + adjudicator)
agents. Any other skill needing an oracle authored and/or executed-and-adjudicated routes that work
HERE via the Skill tool - centralizing the three-context invariant and the per-family browser
exclusivity rule. Provision live execution by invoking the `odoo-instance` skill.

**Dispatch-brief skeleton.** When composing the dispatch prompt for `odoo-qa-planner`,
`odoo-qa-tester`, or any other specialist agent dispatched below, fill the caller-side skeleton in
`${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md` (read it by path) plus the target agent's family
delta; never inline that file verbatim into a hard-leaf brief.

## Out of Scope

- **A static release test-plan doc, deploy checklist, or user-level bug triage** (no execution) -> `odoo-qa-suite`
- **Rating ONE rendered screen** (aesthetics/a11y/perf/theme verdict, read-only) -> `odoo-ui-review`
- **Static review of a diff / PR / pasted block** (no run) -> `odoo-code-review`
- **Writing or fixing the code** -> `odoo-coding`; **finding root cause of one symptom** -> `odoo-debug`
- **Writing a standalone durable test** (a tour/HttpCase with no live acceptance loop) -> `odoo-test-writing`
- **Authoring the oracle alone** (no execution wanted) -> still THIS skill (run Phase 1 only) - it is the sole dispatcher of `odoo-qa-planner`; do NOT spawn the raw agent
- **Writing walkthrough TEXT or usage scenarios for documentation** (no execution required) -> `odoo-doc-walkthrough`. This skill drives live UI and yields a PASS/FAIL verdict; it does NOT produce text-only scenario docs

## MCP tools

<!-- BEGIN GENERATED TOOLS -->
> **Pick the right tool first.** Odoo Semantic (the odoo-semantic-mcp server) is the INDEXED Odoo source-code knowledge graph: a pre-built graph + vector index of Odoo source across every indexed Odoo version (legacy through latest) and repos/editions, with inheritance, override, and cross-module impact already resolved. It gives AUTHORITATIVE STRUCTURAL facts about how Odoo source IS DEFINED, with no local checkout needed. Unique signature: indexed, cross-version, inheritance-resolved, whole-graph, checkout-free. It is a STATIC index with NO runtime/live data.
>
> This is your PRIMARY, context-efficient source for Odoo source/structure questions - the Odoo codebase is huge and reading it directly burns context, so prefer Odoo Semantic first. Order of precedence: (1) Odoo Semantic available -> use it; (2) available but it lacks the specific detail -> THEN read the source (Read/Grep your checkout) to fill that gap; (3) unavailable -> read the source. Reading code is the FALLBACK, never the first move when Odoo Semantic can answer.
>
> Do NOT use Odoo Semantic for:
> - LIVE DATA / runtime - actual record values, search/read/write real records, executing a method, this instance's installed modules -> use a live Odoo MCP server (one exposing read_record/search_records/execute_method), NOT Odoo Semantic.
>
> Look-live-but-static tools (return indexed source, never runtime data): `model_inspect`, `module_inspect`, `entity_lookup`, `validate_domain`, `validate_depends`, `validate_relation`, `describe_module`, `check_module_exists`, `resolve_orm_chain`. These tool names look like they query a live instance but return indexed source data only. If you need live records, Odoo Semantic is the wrong server.

**Session bootstrap** (call once at session start):
- `set_active_version(odoo_version='17.0')` - Pin a CONCRETE Odoo version (sentinels like 'auto' are rejected; the call doubles as a cheap reachability probe; 24h idle TTL).

**Primary tools:**
- `impact_analysis` - Risk assessment of changing or removing a field, method, or model: blast radius, dependent modules, and downstream fields.
- `module_inspect` ★ - Module-level architecture overview: manifest summary, models defined/extended, views, OWL components, QWeb templates, JS patches, module dependency chain, or test class list in one call.
- `model_inspect` ★ - Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, extenders, or a summary in one call.
- `cli_help` - Look up odoo-bin subcommand flags, their status, and replacement for deprecated flags.
<!-- END GENERATED TOOLS -->

Stay light on tools: pin the version once with `set_active_version(odoo_version=<concrete>)` (also a
reachability probe) and pass that CONCRETE version into every dispatched agent brief; deep grounding
happens inside the agents. Fan-out and model-tier policy:
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md`.

## Inputs

A change reference (changed modules / diff / design doc), the `odoo_version`, and a way to reach a
live instance (`INSTANCE_HANDLE` if a run already provisioned one, else resolve per
`${CLAUDE_PLUGIN_ROOT}/snippets/instance-resolution.md`, which also yields the `BROWSER_MODE` -
headed/headless - for the live channel). This run's `slug` is minted at Phase 0 below (after its
orphan sweep) and reused in every artifact path from there on - including each dispatched
`odoo-qa-tester`'s `visual/qa/<slug>/<module>/` evidence dir.

## Phase 0 - SCOPE (verify-scope manifest)

Resolve the Tier-2 ISOLATE dir per `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`'s
resolve-capture-substitute protocol (captured path shown as `<ISOLATE_DIR>` below).

**Orphan sweep (do this every run, BEFORE minting this run's slug below).** `visual/qa/<slug>/`
evidence is RETAINED past its own run (it is the cited evidence behind each PASS/FAIL/UNVERIFIED
verdict) - nothing else ever deletes it, so it leaks one directory per run forever unless a later
run reaps it:

`find <ISOLATE_DIR>/visual/qa/ -mindepth 1 -maxdepth 1 -type d -mmin +43200 -exec rm -rf {} +`

(any sibling `<slug>/` dir untouched for over 30 days is presumed consumed - its verdict has long
since been read). Full rule + bound rationale:
`${CLAUDE_PLUGIN_ROOT}/snippets/visual-evidence-lifecycle-contract.md` Clause 2. Enforcer: whoever
executes `odoo-acceptance` next, unconditionally, every run - not a separate cleanup agent or cron.

Generate one `slug` for the run per
`${CLAUDE_PLUGIN_ROOT}/snippets/visual-evidence-lifecycle-contract.md` Clause 1 (collision-proof
derivation: `<intent-slug>-<YYYYMMDD>-<4 random chars>`, the SAME mechanism `odoo-visual-regression`
uses) and reuse it in every artifact path below.

Now build the verify-scope manifest per `${CLAUDE_PLUGIN_ROOT}/snippets/acceptance-scope.md`:
reverse `impact_analysis` closure on the changed set -> rank each dependent module/screen by risk
(likelihood x impact) -> enumerate the affected screens (views binding a changed symbol) -> emit
`install_set` / `test_set` / `render_check_set`. Write it to `<ISOLATE_DIR>/qa/<slug>-scope.md`.
This is the scope every later phase obeys - depth on High tier, smoke on Low.

## Phase 1 - PLAN (independent oracle)

Dispatch `odoo-qa-planner` (tier per the model-tier SSOT - sonnet default; escalate ONLY when the requirement spans multiple hard business domains with heavy cross-module coupling, never for cluster width or scenario count alone) with
`REQUIREMENT` (+ DESIGN_DOC §1/§9 when present), `odoo_version`, `CHANGED_SET`, the `SCOPE_MANIFEST`
path, and
`SCENARIOS_PATH: <ISOLATE_DIR>/qa/<slug>-scenarios.md`. It returns the immutable oracle (GWT +
EP/BVA/negative + role/CRUD/state/search matrices, risk-tagged). The planner derives `expected` from
the requirement only - it never reads the implementation to decide it.

## Phase 2 - provision the cluster (once)

Provision the live instance via `odoo-instance` with the FULL `install_set` co-installed as ONE
cluster (demo=on, `--http-port`, `persist: exclusive-running` - the cluster stays listening across
Phase 2a/2b and the Phase 3 fix-loop, not a `--stop-after-init` build) - co-installing surfaces MRO /
load-order breaks a single-module install hides. Capture `INSTANCE_HANDLE` once and forward it to
every dispatch below (precedence: `${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md`).
Provisioning and the test-run lifecycle are NOT owned here - `odoo-instance` (the
`odoo-instance-ops` agent) owns create/init/run-tests/drop
and grounds per-series odoo-bin flags via `cli_help`; this skill stays conductor/adjudicator.
Lifecycle + test-invocation conventions: `${CLAUDE_PLUGIN_ROOT}/docs/reference/INSTANCE-LIFECYCLE.md`
and `${CLAUDE_PLUGIN_ROOT}/docs/reference/ODOO-TESTING.md`. This skill does NOT independently
re-derive a worktree root: when the dispatching caller's brief carries a `worktree_path` /
`WORKTREE_PATH` (e.g. `run-harness`'s pre-PR tail, `${CLAUDE_PLUGIN_ROOT}/skills/run-harness/references/run-integration.md`
§ Pre-PR tail stage 2), thread it into this Phase 2 `odoo-instance` dispatch as `WORKTREE_PATH`
verbatim - never default to the catalog/principal checkout when one was supplied.

## Phase 2a - DURABLE channel (parallelizable, no browser)

For High- AND Med-tier modules in `test_set`, launch the `odoo-test-writer` agent (mode tour/HttpCase;
it authors by invoking the `odoo-test-writing` skill inline, in its own context) to realize the
oracle's user-flow scenarios as durable regression, then have `odoo-instance` run them (headless
`--test-enable`). This channel uses no browser, parallelizes across ephemeral DBs, feeds CI, and MAY
run concurrently with Phase 2b. Delegation boundary (writer != executor, INSTANCE_HANDLE precedence,
output-volume): `${CLAUDE_PLUGIN_ROOT}/snippets/test-execution-handoff.md`. (Med-tier also gets a
SEPARATE smoke pass on the live channel below - see the Med-tier depth note in Phase 2b; the two
clauses target different channels, not a contradiction.)

## Phase 2b - LIVE channel (browser-exclusive, per MCP family)

Browser work is exclusive-serial PER MCP FAMILY (chrome-devtools, playwright, pagecast; headed and
headless each count as their own family) - never two browser-driving agents on the SAME family at
once. Distinct families MAY run in parallel, up to the pool cap `W` (RAM-permitting) - SSOT:
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § Browser exclusivity; full rule +
rationale: `${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T2 (this channel may
overlap Phase 2a, which uses no browser).

- **High-tier screens (deep):** for each High-tier module dispatch ONE `odoo-qa-tester` with
  `ORACLE_PATH`, the `INSTANCE_HANDLE`, that module's `SCOPE` (screens from the manifest; roles from
  the oracle scenarios' `role:` field), `BROWSER_MODE`, the SAME `ISOLATE_DIR:` captured in Phase 0
  (the tester composes `<ISOLATE_DIR>/visual/qa/<slug>/<module>/` for its own captured evidence - do
  NOT re-resolve), the SAME `SLUG: <slug>` minted at Phase 0 (passed explicitly - the tester's own
  contract only falls back to stripping it off `REPORT_PATH`'s filename when this field is absent),
  and `REPORT_PATH: <ISOLATE_DIR>/qa/<slug>-acceptance-report.md`. It drives real
  CRUD + at least two roles + state transitions + search on each in-scope screen and adjudicates
  PASS/FAIL/UNVERIFIED with evidence. Optionally, in the same serial slot, dispatch `odoo-ui-reviewer`
  for that module's screens for the read-only one-screen quality verdict (distinct from the tester's
  behavior verdict; do not duplicate).
- **Med/Low-tier screens (smoke):** cover the rest of `render_check_set` with a smoke pass - open each
  screen and assert it renders with NO console error and NO 4xx/5xx (a lightweight `odoo-qa-tester`
  smoke dispatch, ALSO passing the same `ISOLATE_DIR:` and `SLUG:`) - so P0's "smoke on Low" is actually executed,
  not just computed. Med-tier here is
  the smoke half of its depth (it already got the deep durable regression in Phase 2a above); Med
  getting BOTH is by design, not double-work - full definition + rationale (SSOT, do not restate):
  `${CLAUDE_PLUGIN_ROOT}/snippets/acceptance-scope.md` (tier-assignment section) and
  `${CLAUDE_PLUGIN_ROOT}/agents/odoo-qa-planner.md`.

Between Phase 2a/2b and Phase 3, call `allocator.py heartbeat <token>` on the cluster's
`INSTANCE_HANDLE` while the fix-loop below is still iterating. A same-host lease whose owner pid is
verified alive is protected from reaping regardless of heartbeat freshness; heartbeat still matters
here because it is what protects THIS run on the residual case the allocator cannot verify liveness
for at all (a different host, or no pid recorded), and it is cheap enough to call unconditionally
rather than branch on which case applies. Full rule: `${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T3.

## Phase 3 - ADJUDGE + fix-loop (bounded)

Read the tester report and durable results, reconcile them against the oracle, and produce the
acceptance verdict + consolidated bug list (severity / repro / expected-vs-actual / suspected module).
On any FAIL, drive the fix yourself: `odoo-debug` for root cause -> `odoo-coding` for the fix -> re-run
the failed scenarios on whichever channel failed (Phase 2a durable and/or Phase 2b live). Bound the
loop to **3 iterations**; if still not clean, STOP and
escalate with what remains - never loop forever.

**UNVERIFIED is a separate bounded path, not the FAIL loop.** A FAIL means the system disagreed with
the oracle; UNVERIFIED means no capturable evidence was obtained (step blocked, role/instance
unavailable, browser error) - re-running the fix-loop does not address it. On UNVERIFIED, retry
evidence capture (re-dispatch `odoo-qa-tester` for that scenario only) on a fresh instance/session
**at most 2 times**; if still unobtainable, stop retrying and emit `status: BLOCKED (evidence
unobtainable)` for that scenario - never loop indefinitely chasing evidence. A UNVERIFIED on a
High-tier scenario blocks ACCEPTED until evidence is obtained or the scenario is explicitly
escalated as BLOCKED.

**Release on the final verdict (conditions DONE).** Once the verdict is final (ACCEPTED, or the
3-iteration escalation STOP), RELEASE the Phase 2 cluster instance you provisioned - via
`odoo-instance` or `allocator.py release <token> --run-id <id>` - before emitting your terminal
status. Do NOT release between iterations of the fix-loop above (the re-runs need the same live
cluster); release exactly once, after the verdict is final. `DONE` is not valid while that instance
is still leased. Full rule: `${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T0/T1/T3.

## Output

- `<ISOLATE_DIR>/qa/<slug>-scope.md` - the verify-scope manifest
- `<ISOLATE_DIR>/qa/<slug>-scenarios.md` - the immutable oracle (planner)
- `<ISOLATE_DIR>/qa/<slug>-acceptance-report.md` - per-scenario verdict + evidence + bug list (tester),
  with the final ACCEPTED/REJECTED roll-up

## Standalone-first fallback

When Odoo Semantic is unreachable, structural grounding falls back to the local checkout
(`${CLAUDE_PLUGIN_ROOT}/snippets/osm-first-contract.md` §4): derive the closure from disk
(each module's descriptor `depends` - `__manifest__.py`, or `__openerp__.py` on v8-v9 - plus grep
for `_inherit`) and label the manifest "closure approximate from disk". When NO live instance + browser MCP is reachable, EXECUTION cannot run: still produce Phase 0
scope and the Phase 1 oracle, then emit `NEEDS_NEXT -> odoo-instance` to provision one
(`${CLAUDE_PLUGIN_ROOT}/snippets/test-execution-handoff.md`); fall back to `BLOCKED` only when
provisioning is impossible. Never report ACCEPTED without live evidence. This skill is
instance-REQUIRED - live execution + adjudication IS the deliverable, unlike a static-review
skill's instance-optional split (`${CLAUDE_PLUGIN_ROOT}/snippets/instance-optional-completion.md`).

## Continuation Contract

When you finish, append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next). Set `produced`
to the artifact paths written. Emit `NEEDS_NEXT -> odoo-debug` / `odoo-coding` while FAILs remain (or
`-> odoo-instance` when execution is blocked on provisioning); `DONE` only on ACCEPTED with evidence.
