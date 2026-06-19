---
name: odoo-run-forward-port
description: >-
  This skill orchestrates a continuous or one-shot Odoo forward-port - porting fixes
  and features from a lower-series source repo or branch up to a higher-series target -
  as an 8-phase agentic pipeline that forwards INTENT, not code text. It runs a plan gate,
  a parallel read-only intent sweep, a 4-outcome classification, an SHA-preserving git
  merge, a symbol-survival check that catches autosilent field breaks, test-first adapt,
  per-batch verify-by-behavior, a human-confirm gate, and a PR. Invoked by the
  /odoo-forward-port command or directly when asked to "forward-port", "port commits to a
  newer Odoo version", "merge a fix forward", "continuous forward-port", "one-shot
  back-of-port", or in Vietnamese "forward-port Odoo", "port fix lên phiên bản mới",
  "đẩy commit lên series cao", "forward-port liên tục". Do NOT use to write one isolated
  change (use odoo-coding), to diff two versions only (use odoo-version-diff), or to
  review a PR (use odoo-code-review)
model: opus
---

## Persona

Forward-port conductor. This skill owns the git topology, the per-commit pipeline, and the
subagent lifecycle for moving source-series commits onto a higher target series. It makes
the orchestration decisions (which commit at which model tier, which outcome bucket, when to
merge, when to stop for a human) and delegates every leaf task - intent extraction, code
adapt, test forwarding - to specialist agents. The load-bearing belief: a forward-port is a
SEMANTIC translation, not a git operation. A green `git merge` + lint + install does NOT
prove the feature still works on the target platform; only an intent test that goes
red-then-green on the target, plus a symbol-survival check, proves it. SHA is sacred -
continuous forward-port advances the merge-base by absorbing the source SHA into the target
DAG, never by squashing or cherry-picking it into a new SHA.

## Out of Scope

- One isolated change with no source commit to port -> use `odoo-coding`
- A version-to-version API/feature delta only (no merge, no adapt) -> use `odoo-version-diff`
- Reviewing or auditing an existing PR or diff -> use `odoo-code-review`
- A pre-upgrade deprecation sweep of one codebase -> use `odoo-deprecation-audit`
- Designing a non-trivial new architecture before any code -> use `odoo-solution-design`
- Single-WI parallelism with cherry-pick + squash semantics -> use `wave` (forward-port
  keeps SHA by merge; `wave` re-bases by cherry-pick - different git contract)

## Hard rules

> These are load-bearing safety contracts. Softening any one of them breaks the
> forward-port correctness guarantee.

1. **Target-branch-lock** - NEVER `git checkout`, `git switch`, `git commit`, `git merge`,
   `git rebase`, `git reset --hard`, or `git push` on the target branch B directly. Another
   session may hold B's working tree. All integration happens in a dedicated integration
   worktree branched FROM B (the JOB tier below). Read-only ops on B are allowed.

2. **Keep the source SHA (continuous)** - continuous forward-port uses
   `git merge --no-ff --no-commit <src-SHA>` so the source commit enters the target DAG
   with its SHA intact and the merge-base advances. NEVER squash or cherry-pick for
   continuous mode - both mint a fresh SHA, leave the merge-base behind, and force
   re-resolving the same conflict every future run. Cherry-pick is the one-shot-only
   fallback. Full protocol: `[[fp-merge-absorption]]`.

3. **Intent before code** - the unit being forwarded is the behavior/purpose, not the diff.
   Phase 1 extracts intent (read-only); Phase 4 re-implements that intent on the target
   idiom. Never paste a source diff hunk forward and call it done. SSOT: `[[fp-intent-4outcome]]`.

4. **Verify by behavior, not by text** - success = the forwarded INTENT test goes RED then
   GREEN on the target, plus confirm-by-toggle (disable the adapt code -> the FP-delta test
   must go red again). A clean merge is necessary, never sufficient.

5. **Symbol-survival before adapt** - after every merge, run the Phase 3.5 symbol-survival
   check on BOTH conflicted files and merge-clean-but-source-touched files. A source line
   referencing a symbol removed/renamed at the target produces NO conflict marker but breaks
   at runtime. Resolve every broken symbol into a bucket before adapt starts. SSOT:
   `[[fp-symbol-survival-check]]`.

6. **Human-confirm merge** - STOP at the Phase 6 gate and at the Phase 0 plan gate. No
   automated commit of the integration into B, no auto-merge of the PR. Present and wait.

7. **Outcome a/d still merge** - buckets (a) already-satisfied and (d) no-longer-relevant
   produce no adapt diff but STILL create the merge commit (keeps SHA, advances merge-base).
   Skipping the merge for them re-encounters the commit tomorrow. SSOT: `[[fp-merge-absorption]]`.

8. **Verify subagent claims** - never trust a leaf's self-report of GREEN. Run the verify
   command yourself per batch (Phase 5) before the Phase 6 gate.

## Git topology - two tiers of worktree

Forward-port never touches B directly and parallelizes through worktree isolation.

**JOB tier (always):** create `fp/<slug>` integration branch + `git worktree add` from B's
HEAD. All absorption, adapt, and verify happen inside this integration worktree. The target
branch B is read-only for the whole run; the only thing that ever lands on B is the final PR
merge (Phase 7), human-confirmed.

**WORK tier (when a phase fans out):** from the integration worktree, each parallel unit
(one module or work-item in Phase 4 adapt) gets its OWN `git worktree add` child worktree +
branch off integration. Each adapt subagent works in its child worktree (a private git index
-> safe parallelism, no `index.lock` race). When a child finishes, the orchestrator brings
it back into integration by merge (keeping SHA), then removes the child worktree. The next
phase recreates child worktrees from the updated integration. LOOP until phases are done.

The only serialized point is converging children into integration + writing the
source-merge commit. `spawn_class = spawner-agent`: the depth-0 orchestrator dispatches
named agents at depth 0->1 and creates WORK-tier worktrees for filesystem isolation
(no depth-2 agent dispatch). There is no depth-2 dispatch - the worktrees are filesystem
isolation, not a second agent-dispatch level.

## The 8-phase pipeline

Run phases in order. Concurrency for any fan-out follows
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` (Mode B, model-weighted budget 8) -
do not restate the weight numbers here. Full per-phase dispatch briefs, git commands, and
worklog templates: `references/fp-phase-detail.md`.

**P0 - Plan gate [STOP].** Read any existing worklog
(`${CLAUDE_PLUGIN_ROOT}/snippets/worklog-contract.md`) and `checkpoint.json` (resume - skip
commits with `status=done`). Enumerate commits with
`git log <merge-base>..<source-ref>` (read-only ops on B - no worktree, no branch yet);
apply `--scope` / `--since` filters. Map each `--scope` module name to its directory path
before passing to `git log -- <paths>` (module `l10n_vn` -> `l10n_vn/`; resolve via manifest
location, may be at repo root or under an addons subdir). TRIAGE each commit to an EXTRACT
model tier INLINE (`git show --stat` + one `find_override_point` probe - never dispatch an
agent to decide a dispatch). Emit `plan.md` listing each commit + tier + bucket-guess + scope,
then STOP for approval. Triage tier table: `references/fp-triage-table.md`.

After user approves the plan, create the JOB-tier integration worktree from B (Hard rule 1):
`git worktree add -b fp/<slug> <path>/fp-integration <target-branch>`. No branch is created
before this point - the plan gate is read-only.

**P1 - Intent extract [PARALLEL, READ-ONLY].** This is the only true parallel speed-up - and
it is honored fully. Dispatch one `odoo-intent-extractor` agent per commit via the Agent tool,
each with its triaged `model` override, up to the Mode B budget (rolling window beyond it).
Each writes `.odoo-ai/forward-port/<slug>/intents/<sha>.md` (the why + behavioral contract +
OSM-grounded symbols, never the diff). No worktree children needed - extraction is read-only.
Aggregate the returned summaries into the Phase 2 classify queue.

**P2 - 4-outcome classify [per-commit, OSM].** For each commit, ground its symbols against the
TARGET version (`set_active_version` once, then `api_version_diff` + `model_inspect`) and
assign exactly one bucket a/b/c/d. SSOT: `[[fp-intent-4outcome]]`. Append one row per commit to
`merge-log.md`. `odoo-version-diff` in forward-port mode can supply the per-symbol bucket
suggestion. Every Odoo Semantic call carries `odoo_version=` - never omit it.

**P3 - Git merge --no-commit [critical section, in integration].** Continuous:
`git merge --no-ff --no-commit <src-SHA>`. One-shot: `git cherry-pick -n <src-SHA>`. Only one
merge in flight at a time (shared git index). Do NOT commit yet - the working tree is now the
absorption zone (Phase 3.5 -> 4 -> 5 all happen before the commit). SSOT: `[[fp-merge-absorption]]`.

**P3.5 - Symbol-survival check [MUST].** Before any adapt, OSM-ground every source-side symbol
in conflicted AND merge-clean-but-source-touched files against the target surface. Any symbol
absent/changed at target FORCES the commit into bucket b/c/d and BANS leaving the auto-merged
line unchanged. This catches the autosilent field-break (no conflict marker, runtime crash).
SSOT: `[[fp-symbol-survival-check]]`.

**P3.5 TEST-survival sub-check [MUST - runs in parallel with production symbol check].**
After production symbol check, also run test-coverage grounding to detect test code that
references a field or model symbol removed at the target version (git auto-merge produces no
conflict marker, so this break is autosilent at test time, not just at runtime). For each model
or field touched by the commit, call `tests_covering(model='<model>', odoo_version='<target_version>')`
(also accepts optional `field='<field>'` to narrow). If the tool returns test methods that
reference a symbol NOT present in the target `model_inspect` output, those test methods
reference a deleted symbol and MUST be triaged as part of the same bucket assignment - they
cannot be forwarded verbatim. When a broader audit is needed (e.g. the commit touches an
entire module), supplement with `test_coverage_audit(module='<module>', odoo_version='<target_version>')`
to surface fields with zero COVERS edges at target (field-level only; method gaps are NOT
reported by this tool - for per-method coverage use `tests_covering(model='<model>', method='<method>',
odoo_version='<version>')`, which is sparse and may return 0 edges even for tested methods).
After `tests_covering` returns a list of test methods referencing field X at source, CONFIRM X
is absent at target before concluding those tests are broken candidates: call
`model_inspect(model='<model>', method='fields', odoo_version='<target_version>')` - only if X
is absent in that output are the test methods broken; `tests_covering` does not itself compare
cross-version. Record all broken test-symbol references in the per-commit row of
`merge-log.md` alongside the production symbols. The P4a adapt brief MUST include this list.

**P4 - Adapt [test-first; SERIAL per-module within a commit (v1 default); SERIAL across commits].** For each touched module/WI,
spawn an adapt unit in its own child worktree off integration (worktree per module for filesystem isolation):
- **4a forward the test FIRST** via `odoo-test-writing` mode `adapt`: translate to target API,
  strip implementation-coupled assertions, confirm RED on target (the test is the oracle).
  Before dispatching `odoo-test-writing`, build an FP-ENRICHED brief that carries:
  (i) **base class grounding** - call `test_base_classes(odoo_version='<target_version>')` to
  confirm the correct base class at the target (e.g. `SavepointCase` is a deprecated alias
  from v8-v15, still present and runnable in v16+ but should be adapted to `TransactionCase`
  idiom - not a BREAKING removal; `cr.commit()` is FORBIDDEN in all test cases - isolation
  is savepoint rollback); include the `test_base_classes` output
  in the brief so the `odoo-test-writing` agent adapts to target-native idiom without relying
  on memory;
  (ii) **test examples at target** - call `find_test_examples(query='<feature_or_model>', odoo_version='<target_version>')`
  (also accepts optional `model='<model>'`; for kind use `'transaction'`|`'http'`|`'form'`
  matching the case type, or omit kind to get all Python test types; use `kind='js'` only for
  JS tests - `kind='python'` is NOT a valid value) to fetch real test chunks from the target
  Odoo version; attach the top examples to the brief so the agent
  has a concrete template to adapt to, not a source-side pattern that may no longer be idiomatic;
  (iii) **broken test-symbol list** from the P3.5 test-survival sub-check - the adapt agent
  must rewrite or drop every test assertion that references a symbol removed at target.
- **4b adapt the code** per bucket via `odoo-coder` (backend) / `odoo-frontend-coder` (frontend),
  dispatched with an FP-ENRICHED brief = intent record + bucket + the failing test + the
  installable:False checklist. Bucket (a)/(d): no adapt code. Bucket (b): 3-way merge + adapt.
  Bucket (c): re-implement on the target idiom.
- **4c new module** (exists at source, not yet at target): `installable: False` + comment
  `auto_install`/`application`, lint-fix only. SSOT: `[[fp-installable-false]]`.
- **4d migration script**: rename `<src-series>` -> `<tgt-series>` dir ONLY when the gate
  `installed < parse(dir) <= current` holds - never rename blind (an inert dir is silent).
  (`installed` = `ir.module.module.installed_version` for the module; `current` = manifest `version`.)
Converge each child worktree back to integration (serialized), then remove it.

**P5 - Verify by behavior [PER-BATCH, in integration].** Resolve odoo-bin flags for the
TARGET series via `cli_help` before invoking (the allocator returns version-agnostic ports;
flags differ per series, e.g. v19 namespace bootstrap). Acquire ONE ephemeral instance per
batch via the allocator, install the N affected modules ONCE, run the target suite:
RED-then-GREEN for the whole module + confirm-by-toggle for FP-delta tests only. Triage each
red test as FP-delta vs pre-existing (run it on clean target tip). Never relax an assertion to
hide a pre-existing failure. Full per-batch + allocator + CREATEDB-role protocol:
`[[fp-merge-absorption]]`. Instance lifecycle and test invocation conventions:
`docs/reference/INSTANCE-LIFECYCLE.md` and `docs/reference/ODOO-TESTING.md`.

**P6 - Gate merge [STOP, per batch].** Emit `merge-log.md`, present it, wait for human-confirm.
On confirm: `git commit` the merge (buckets a/d still commit - Hard rule 7), update
`checkpoint.json` `{<sha>: done}`. More commits/batches remain -> LOOP back to recreate WORK-tier
worktrees from integration for the next batch.

**P7 - PR + review [depth-0].** Open PR `fp/<slug>` -> B. Run `/code-review` inline (depth-0
only) + optionally dispatch `odoo-code-review` for the FP pitfall (test coupled to source API).
NEVER squash (keeps SHA). B stays LOCKED - the PR only adds the merge commits. Wait for human
merge.

## Model triage - two tier tables

Triage is INLINE and deterministic, run twice with different tables:

- **EXTRACT tier (P0 -> P1 intent extraction):** haiku for docstring/comment/string-only
  commits, sonnet for logic commits, opus for migration/cross-module commits. **fable is NOT
  in the EXTRACT band** - intent extraction is read-only analysis, never worth fable cost.
- **ADAPT tier (P4 code adapt):** follow the `odoo-coding` deterministic tier table
  (haiku/sonnet/opus/fable, sonnet default, fable always needs explicit human confirmation).

Resolve a tier by walking each table top-down, first match wins. Full both-table detail with
per-row conditions: `references/fp-triage-table.md`. Record every chosen tier in `plan.md` - a
tier is part of the approved plan, not a runtime improvisation.

## Two modes

- **Continuous (default).** Recurring; source keeps evolving. Merge keeps SHA; merge-base
  advances; `checkpoint.json` makes the next daily run skip done commits and never re-resolve a
  past conflict. This is the primary mode and the reason SHA preservation is non-negotiable.
- **One-shot (`--one-shot`).** Port one frozen batch once; source will not advance, so the
  repeated-resolution footgun does not apply. `git cherry-pick -n` is the accepted git op. The
  architecture reserves this path; everything else (intent -> classify -> symbol-survival ->
  adapt -> verify -> gate) is identical.

## Checkpoint / resume

`.odoo-ai/forward-port/<slug>/checkpoint.json` maps `{<sha>: extracted | adapted | verified | done}`.
P0 reads it and skips `status=done` commits; a crash mid-batch is recovered by re-reading the
checkpoint + the on-disk `intents/` and `merge-log.md` (file existence is the source of truth,
the JSON is the fast index). Child worktrees left dangling by a crash are removed and recreated
from integration. Cache any held allocator lease token in the batch worklog so a crash can
release the DB instead of orphaning it.

## Frontend / i18n / data-XML caveats

Forward-port adds platform-drift classes a pure-Python port misses - flag and route each:

- **Frontend (JS/OWL/SCSS).** Asset-bundle keys drift across series (e.g. `web.assets_backend`
  manifest entry shape) and OWL moved from the legacy `web.Widget` / `odoo.define()` era to
  OWL 2.x `patch()` / `useState` / `useService`. Route a frontend adapt commit to
  `odoo-frontend-coder` (it owns both eras) - never hand-translate OWL from memory.
- **i18n (.pot / .po).** Do NOT carry a source `.po`/`.pot` forward verbatim - re-export per
  module on an isolated target DB after the code adapt; a stale translation references dropped
  message ids. Treat the re-export as part of the module's adapt, verified by an Odoo `-u`
  reload (not `msgfmt`).
- **Data XML (`noupdate` records).** A source data record may reference an external-id that does
  not resolve at the target. After merge, verify every external-id in touched data XML resolves
  on the target (Phase 3.5 covers `ref()` / `xml_id`); a `noupdate="1"` record will not be
  re-written, so a broken ref is permanent until fixed here.

## MCP tools

<!-- BEGIN GENERATED TOOLS -->
> **Pick the right tool first.** Odoo Semantic (the odoo-semantic-mcp server) is the INDEXED Odoo source-code knowledge graph: a pre-built graph + vector index of Odoo source across every indexed Odoo version (legacy through latest) and repos/editions, with inheritance, override, and cross-module impact already resolved. It gives AUTHORITATIVE STRUCTURAL facts about how Odoo source IS DEFINED, with no local checkout needed. Unique signature: indexed, cross-version, inheritance-resolved, whole-graph, checkout-free. It is a STATIC index with NO runtime/live data.
>
> This is your PRIMARY, context-efficient source for Odoo source/structure questions - the Odoo codebase is huge and reading it directly burns context, so prefer Odoo Semantic first. Order of precedence: (1) Odoo Semantic available -> use it; (2) available but it lacks the specific detail -> THEN read the source (Read/Grep your checkout) to fill that gap; (3) unavailable -> read the source. Reading code is the FALLBACK, never the first move when Odoo Semantic can answer.
>
> Do NOT use Odoo Semantic for:
> - LIVE DATA / runtime - actual record values, search/read/write real records, executing a method, this instance's installed modules -> use a live Odoo MCP server (one exposing read_record/search_records/execute_method), NOT Odoo Semantic.
>
> Look-live-but-static tools (return indexed source, never runtime data): `model_inspect`, `module_inspect`, `entity_lookup`, `validate_domain`, `validate_depends`, `validate_relation`. These tool names look like they query a live instance but return indexed source data only. If you need live records, Odoo Semantic is the wrong server.

**Session bootstrap** (call once at session start):
- `set_active_version(odoo_version='17.0')` - Pin a CONCRETE Odoo version (sentinels like 'auto' are rejected; the call doubles as a cheap reachability probe; 24h idle TTL).

**Primary tools:**
- `api_version_diff` - Structured diff of an API symbol or scope across two Odoo versions: new, changed, removed, deprecated items.
- `model_inspect` ★ - Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, extenders, or a summary in one call.
- `module_inspect` ★ - Module-level architecture overview: manifest summary, models defined/extended, views, OWL components, QWeb templates, JS patches, module dependency chain, or test class list in one call.
- `entity_lookup` ★ - Single-entity drill-down by ID: field, method, or view with full inheritance chain and source module.
- `find_override_point` - Show override chain, super() safety guidance, and anti-patterns for a method to find the safest place to inject custom behavior.
- `find_test_examples` - Semantic search for Odoo test code examples (test_method, test_class, js_test chunks only - never returns production code).
- `test_base_classes` - Menu of official Odoo test framework base classes (TransactionCase, HttpCase, SavepointCase, Form, etc.) for the given version, with test_type and cursor contract.
- `test_coverage_audit` - Audit an entire module for test coverage gaps: lists fields/methods with zero COVERS_* edges (never referenced by any test).
- `tests_covering` - List test methods that have COVERS_MODEL/COVERS_FIELD/COVERS_METHOD edges to the target model or field (static reference coverage, not runtime executed coverage).
<!-- END GENERATED TOOLS -->

## Standalone-first fallback

When Odoo Semantic (the odoo-semantic-mcp server) is unreachable, the pipeline degrades but
does not stop. Phase 1 intent extractors fall back to local-source reads
(`${CLAUDE_PLUGIN_ROOT}/snippets/osm-first-contract.md`), labelling each record
`grounded: local-source (not OSM-indexed)`. Phase 2 classify and Phase 3.5 symbol-survival
fall back to disk reads of the target checkout per
`${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md` (read each `__manifest__.py`
`depends` and the model/field source) - the symbol-survival guarantee still holds via grep on
the target source, only the grounding citation changes. `odoo-version-diff` standalone mode
supplies the version delta from GitHub release notes when the index is down. Never ask a human
to paste code, field lists, or manifests; the merge SHA-preservation and verify-by-behavior
contracts are unchanged - only the grounding source degrades.

## Continuation Contract

When the run finishes (or pauses at a gate), append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next).
`produced` lists `plan.md`, `intents/<sha>.md`, `merge-log.md`, `checkpoint.json`, and the PR
URL; `next` is the human-confirm gate (Phase 6 or Phase 7 merge). Additive output for the
depth-0 run-driver - it does not change anything produced above.
