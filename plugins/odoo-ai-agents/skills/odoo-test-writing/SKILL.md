---
name: odoo-test-writing
argument-hint: "[model/module to test]"
description: >
  Write executable Odoo test files that protect business behavior - not just cover code. Produces Python
  `test_*.py` (TransactionCase / Form helper / `@tagged`) and JS Hoot / QUnit suites, selecting the correct
  framework per version. Also translates existing tests across major Odoo versions (adapt mode): strips
  implementation-coupled assertions, maps renamed APIs via OSM, confirms RED on target before production
  code is adapted. Grounds every test via OSM MCP calls. Fire on: test coverage, CI protection, forward-port
  test translation, or tour/HttpCase. Vietnamese: "viết test cho model", "bao phủ ràng buộc bằng test",
  "test hành vi nghiệp vụ Odoo", "dịch test sang version mới", "viết test JS Hoot", "viết tour Odoo", "viết
  HttpCase". Writes RUNNABLE files: a non-executing prose test-PLAN or test-case table -> odoo-qa-suite;
  write scenarios then run live and adjudicate PASS/FAIL -> odoo-acceptance; static code review ->
  odoo-code-review; runtime errors -> odoo-debug
model: inherit
---

## Role

QA Engineer / backend developer writing automated tests for Odoo, all supported versions (v8 onward). Enforces the test-behavior principle: every test asserts a business contract, not a snapshot of current implementation.

## Out of Scope

- **Static review / quality audit of existing tests** - use `odoo-code-review`
- **Writing the production code under test** - use `odoo-coding`
- **Debugging a test that fails at runtime on a live instance** - use `odoo-debug`
- **Upgrade-safety audit** - use `odoo-deprecation-audit`
- **Running the test suite (including tour/HttpCase)** - execution is delegated via NEEDS_NEXT to `odoo-instance`; authoring (Rounds 0-4) is always in scope regardless of instance availability

> **Performance / load tests are IN scope (lightweight mode)** - author a query-count guard (`@tagged('post_install','-at_install')` + `self.assertQueryCount(...)` / `with self.assertQueries([...])`) or a bounded-time assertion over a seeded volume, grounded via OSM (`orm-performance.md` idioms). It guards a BEHAVIOR contract ("stays O(1) queries under N records"), never a benchmark. A full external load/stress harness (locust-style concurrency, sustained throughput) is out of scope -> a dedicated perf harness / `odoo-perf-audit` for diagnosis; state that owner explicitly rather than leaving it unowned.

> Translating existing tests across major versions (adapt mode) IS in scope - see "Adapt mode" below.

## When to use

Five modes, all governed by the red-before-green contract (`${CLAUDE_PLUGIN_ROOT}/snippets/test-first-contract.md`):

- **Test-first (before the code).** Author a module's failing test BEFORE the implementation, independent from the coder, so the test specifies intended behavior and code is written to green. Used standalone, or when a caller hands off red-first authoring. In the `odoo-coding` loop the `odoo-coder` coordinator launches the dedicated `odoo-test-writer` agent, which invokes THIS skill INLINE to author the RED test - so this capability is the coding loop's test author, reached through that context-isolated agent (coders never author tests).
- **Coverage (after the code).** Backfill behavior-protecting tests for existing code; the `odoo-code-review` test-coverage gate routes here when a CRITICAL/HIGH change ships with no protecting test.
- **Adapt (forward-port test translation).** Translate a test file from a source to a target Odoo version (see Adapt mode below). Invoked by the forward-port pipeline (P4a of `odoo-forward-port`) or directly with a source file + version pair.
- **Performance/load (lightweight).** Author a query-count / bounded-time behavior guard for a stated performance contract (boundary in Out of Scope).
- **Tour/HttpCase (full-stack UI acceptance).** Write a JS tour registered in `web_tour.tours` (or the version-appropriate registry) driven by a Python `HttpCase.start_tour(...)`, decorated `@tagged('post_install', '-at_install')`. Use when acceptance flows span multiple real browser steps needing an HTTP server, or `odoo-qa-planner` oracle scenarios need browser-level state verification. Do NOT use for non-browser logic (use `TransactionCase`/`Form`) or a JS unit with mocked models (use Hoot - no server, no real browser). Authoring (Rounds 0-4) needs no live instance; execution requires `--http-port` and MUST be delegated per `${CLAUDE_PLUGIN_ROOT}/snippets/test-execution-handoff.md`.

Trigger when the user wants: coverage for a model/computed field/constraint/onchange/wizard; a test guarding a named business rule; JS Hoot/QUnit tests for an OWL component; a test droppable into `tests/` and runnable under `--test-enable` (fresh DB `-i <module>`; re-run on installed DB `-u <module>`); the failing test a coder implements to green; a source test translated for forward-port; or a JS tour + HttpCase file.

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
- `model_inspect` ★ - Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, extenders, or a summary in one call.
- `find_examples` - Semantic code search returning real indexed code snippets from the Odoo codebase.
- `lookup_core_api` - Verify Odoo core API symbol signature, status (stable/deprecated/removed), and replacement.
- `test_base_classes` - Menu of official Odoo test framework base classes (TransactionCase, HttpCase, SavepointCase, Form, etc.) for the given version, with test_type and cursor contract.
- `find_test_examples` - Semantic search for Odoo test code examples (test_method, test_class, js_test chunks only - never returns production code).
- `js_test_inspect` - List JsTestSuite nodes in a module: framework mix (hoot/qunit/tour), file paths, suite sizes, describe/test sample, mounts, tags.
- `tests_covering` - List test methods that have COVERS_MODEL/COVERS_FIELD/COVERS_METHOD edges to the target model or field (static reference coverage, not runtime executed coverage).
- `test_coverage_audit` - Audit an entire module for test coverage gaps: lists fields/methods with zero COVERS_* edges (never referenced by any test).
- `test_class_inspect` - Inspect a TestClass or TestHelper by name: base chain (INHERITS_TEST), setUpClass cursor contract (test_type, commit_allowed), test methods with assert counts, and subclassed-by list.
- `api_version_diff` - Structured diff of an API symbol or scope across two Odoo versions: new, changed, removed, deprecated items.
- `resolve_orm_chain` ⊕ - Walk a dotted ORM field path hop by hop to the terminal field type or the exact hop where it breaks.
- `validate_relation` ⊕ - Assert a relational field points at the expected comodel (many2one/one2many/many2many).
- `validate_depends` ⊕ - Validate compute method's `@api.depends('a.b', ...)` paths; flag `id` and suggest typos.
- `cli_help` - Look up odoo-bin subcommand flags, their status, and replacement for deprecated flags.
<!-- END GENERATED TOOLS -->

## Method

**`WORKTREE_PATH`.** The test file(s) are git-tracked, so per
`${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md` field 5 Round 4 writes into a dedicated worktree -
never the principal checkout. When invoked via the `odoo-test-writer` agent, that agent already `cd`s
into its `WORKTREE_PATH` before invoking this skill inline (`agents/odoo-test-writer.md`) - the paths
below are relative to that cwd. Invoked standalone (no wrapping agent), require `WORKTREE_PATH`
yourself and resolve `<addon>` under it; with none supplied and no worktree already in scope,
provision one via `git-toolkit:git-ops` before Round 4, per
`${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`.

### Round 0 - version pin + context

Call `set_active_version('<version>')`. Resolve from `<SHARE_DIR>/context.md` (resolve `<SHARE_DIR>` once per `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`; substitute the captured absolute path - never write the placeholder or a bare `.odoo-ai/` into a Read/Write/Edit) first; fall back to manifest `version` field; default to v17 only when both absent.

### Round 1 - framework selection (OSM-grounded)

- **Python (all versions):** `TransactionCase` (rolls back after each test); `Form` helper (v12+, see `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-era-boundaries.md` row 3 - do not restate the window here) for UI-level interactions. Tag `@tagged('post_install', '-at_install')` or `@tagged('at_install')`. Call `test_base_classes(odoo_version='<version>')` FIRST - it surfaces the full base-class menu (TransactionCase, SavepointCase, HttpCase, Form, SingleTransactionCase) with their PP3 contract: **`cr.commit()` FORBIDDEN - isolation is savepoint rollback**. Drill into the chosen class with `test_base_classes(odoo_version='<version>', name='TransactionCase')` for setUp behavior (savepoint per method) and home module. Do NOT use `lookup_core_api` for test base classes - it indexes core ORM/API symbols only and returns not-found (the import is the standard `from odoo.tests import TransactionCase`). For **`HttpCase`**: call `test_base_classes(odoo_version='<version>', name='HttpCase')` to confirm its target-version contract - it extends `TransactionCase` and adds a threaded HTTP server plus `start_tour(tour_name, login='admin', ...)`; `cr.commit()` stays FORBIDDEN. Use `HttpCase` ONLY when exercising a tour or `url_open` endpoint - never for pure model/field/constraint logic. It requires `--http-port`; delegate execution per `${CLAUDE_PLUGIN_ROOT}/snippets/test-execution-handoff.md`.
- **JS (all versions) - procedure (state once):** ALWAYS call `js_test_inspect(module='<module>', odoo_version='<version>')` FIRST to confirm the exact framework mix, suite paths, describe blocks, and mock_models convention (framework varies per module/version), THEN call `find_test_examples(...)` for concrete test-only examples matching the confirmed framework. Per-version framework + example query:
  - **JS v16 and earlier:** QUnit / `odoo.define`; `find_test_examples(query='QUnit test odoo.define', odoo_version='<version>')`.
  - **JS v17:** QUnit dominant (some modules hybrid); same QUnit query.
  - **JS v18+:** Hoot dominant (`import { describe, test, expect } from "@odoo/hoot"`), QUnit legacy in some modules; `find_test_examples(query='Hoot describe test expect', kind='js', odoo_version='<version>')`. Do NOT use `lookup_core_api` for JS frameworks like Hoot; it indexes Python core API only and returns not-found.

Never assume same JS import paths between major versions - always call OSM. Never assume JS framework without calling `js_test_inspect` first: the framework mix varies by module and version (QUnit dominant v16-v17; Hoot dominant v18+, QUnit legacy still present). Do NOT hardcode "v17=Hoot" - `js_test_inspect` is the authoritative source per module.

- **JS tour (all versions):** Tours live in `static/tours/<name>.js` and register via `registry.category('web_tour.tours').add(...)` (v16+; earlier series used different registry paths - always ground). ALWAYS call `js_test_inspect(module='web_tour', odoo_version='<version>')` FIRST to confirm the exact registry path, step object shape, and whether `run` accepts a string action or a function for the target version. Then call `find_test_examples(query='web_tour start_tour tour steps trigger run', kind='js', odoo_version='<version>')` for grounded step examples - do NOT write tour steps from memory, especially the `run` field syntax and the `odoo.loader.modules.get` vs `require` call form (v17 uses `odoo.loader.modules.get('@web_tour/...')` not `require`). Step anatomy: `{ trigger: '<CSS selector>', run: '<string action or function>' }`. Tour steps are implicit oracles: each `trigger` asserts the UI reached that state before proceeding. Additionally, add explicit Python assertions in the `HttpCase` body AFTER `start_tour` completes to assert observable business outcomes (state change, record count, computed value) - do not rely solely on tour completion as evidence of correctness.

### Round 2 - model / field grounding

For each model call `model_inspect(model='<model>', method='fields', odoo_version='<version>')` to get real field names and types (do not guess from description), relational paths for `@api.depends`/`Form` interactions, existing method signatures. Call `validate_relation` or `resolve_orm_chain` for relational chains (`partner_id.country_id.code`) to confirm each hop.

When the test needs to extend an existing test helper (e.g. `AccountTestInvoicingCommon`, `MailCommon`, a module's own `Common` class), call `test_class_inspect(name='<HelperClass>', odoo_version='<version>')` to get the full base chain, the cursor contract (commit_allowed flag), and which other test files subclass it. Note: this tool does NOT return setUpClass fixture contents - to see what fixtures a helper actually seeds, Read the source file at the path shown in "Defined in:". Use the inherited fixtures directly - do not copy-paste setUp code that the helper already provides.

For any CORE ORM / action-method symbol the setUp, factory dict keys, or assertions call directly (e.g. `create`, `write`, `action_confirm`), apply the Tier-0 currency check (`${CLAUDE_PLUGIN_ROOT}/snippets/symbol-currency-check.md` §Test): `lookup_core_api(name='<symbol>', odoo_version='<version>')` for core ORM/action symbols ONLY. Base-class currency stays with `test_base_classes` and JS-framework currency stays with `js_test_inspect` (both already wired in Round 1 above) - do NOT route base classes or JS frameworks through `lookup_core_api`, it returns not-found for them. Adapt mode keeps its own `api_version_diff` step (see below).

### Round 2.5 - coverage baseline (anti-reinvention)

Before writing any test, establish what is already covered. Call `tests_covering(model='<model>', odoo_version='<version>')` to list every existing test method exercising this model, and scope new tests to fields/methods/constraints NOT in that list - the gap is the deliverable; duplicating existing coverage is a defect.

For a broader whole-module audit, call `test_coverage_audit(module='<module>', odoo_version='<version>')` to identify models with zero or partial coverage.

### Round 3 - find existing test patterns

Call `find_test_examples(query='test <model or feature> TransactionCase', odoo_version='<version>')` (or for JS: `find_test_examples(query='Hoot describe test expect', kind='js', odoo_version='<version>')`) for real test-only patterns. Use `find_test_examples`, not `find_examples` - the latter mixes in production code that contaminates the pattern. Cross-reference with `tests_covering(model='<model>', odoo_version='<version>')` to confirm which patterns map to real coverage edges. Prefer grounded patterns over hand-written boilerplate.

### Round 4 - write tests

Write `<addon>/tests/test_<feature>.py` (or `<addon>/static/tests/test_<feature>.js` for JS), `<addon>` resolved under `WORKTREE_PATH` per the Method preamble above. Apply these rules without exception:

**Business-rule naming.** Every test method name states the rule being protected: `test_discount_cannot_exceed_20pct`, `test_confirmed_order_locks_price`, `test_access_denied_for_portal_user`. Not: `test_sale_order_field`, `test_write_method`.

**Assert observable outcomes.** Assert computed field values, state after ORM call, exception from constraint, domain filter result - not private method call counts or ORM cache internals.

**Drive the real workflow - never the shortcut (SSOT: `${CLAUDE_PLUGIN_ROOT}/snippets/test-behavior-contract.md`).** Reach a state by CALLING the action (`action_confirm` / `action_validate` / `button_validate` / `action_approve`) - never seed with `create({'state': ...})` or a raw insert. Use `Form(self.env['<model>'])` when an `onchange` produces the value under test. Test access with `record.with_user(self.<user>).action_*()` and assert allowed-or-`AccessError`; `sudo()` is for ARRANGE setup only, NEVER on the action whose permission you assert.

**Expected-log contract for deny-path / guard tests (SSOT: `${CLAUDE_PLUGIN_ROOT}/snippets/test-expected-log-contract.md`).** When a test exercises a deny-path, guard, or constraint that legitimately emits a WARNING or ERROR, wrap per the contract BY DEFAULT - use `assertLogs` for deny-path tests (the WARNING is the observable behavior; assert it fired), `mute_logger` only for incidental noise already asserted elsewhere. For JS tests call `js_test_inspect(module=..., odoo_version=...)` to confirm the per-module framework before emitting any suppress/assert idiom - do not use a version-to-framework shorthand; modules can be hybrid (SSOT: `${CLAUDE_PLUGIN_ROOT}/snippets/test-expected-log-contract.md`).

**One business rule per test.** Each `def test_*` covers exactly one invariant.

**Each test must be able to fail - confirm RED (binding).** Core of `${CLAUDE_PLUGIN_ROOT}/snippets/test-first-contract.md`: in test-first mode the production code doesn't exist - state it's RED. In coverage mode confirm by reasoning (or intentionally removing the rule) that it would go red. Never weaken a test to make it pass; fix the code instead.

**Minimal arrange.** `setUp` creates only records required by the test. No fields/models/fixtures for "possible future tests".

**No implementation coupling.** Do not assert on private method call counts, internal variable names, or ORM cache internals.

**Independence (FIRST rule).** Each test passes in isolation and in any order. No mutable shared state via class-level attributes set inside a test body.

### Round 5 - static validation

- Import paths resolve (`from odoo.tests.common import TransactionCase` for detected version)
- `@api.depends` paths used in `Form` interactions pass `validate_depends`
- Field names in `env['<model>'].create({...})` match `model_inspect` output

Backend code-quality gate - moved: the `/test_lint` (+ `/test_pylint` on v16+ Viindoo profiles)
CI-parity gate is no longer appended per test-run here - it runs ONCE, over the run-integration
branch's aggregate diff, at `run-harness`'s pre-PR tail
(`${CLAUDE_PLUGIN_ROOT}/skills/run-harness/references/wave-integration.md` § Pre-PR tail). Test method local variables must follow `${CLAUDE_PLUGIN_ROOT}/snippets/python-naming-conventions.md`: Rule A (no `l`/`O`/`i`) applies universally (pylint C0104 blocks the gate); Rules B/C (meaningful names, `for r in self`) apply on Viindoo Standard/Internal profiles. On later execution under `--test-enable` (FRESH DB `-i <module>`; already-installed DB `-u <module>`, since `-i` is then a no-op; confirm flags via `cli_help`, full rule `${CLAUDE_PLUGIN_ROOT}/docs/reference/ODOO-TESTING.md`), resolve the interpreter (the instance's `python` field) per `snippets/venv-resolution.md`, not system `python3`.

On newer series (17.0+ illustrative - confirm via `cli_help`) you MUST add `--skip-auto-install` to the install/init run (`-i <module> --test-enable`, or `-u <module>` on an installed DB) to avoid auto-installed-module noise.

**Tour/HttpCase execution boundary:** `HttpCase` + `start_tour` tests require a live HTTP server (`--http-port`). Do NOT run tour suites inline - the executor's job and log volume are both large. Three distinct roles: Author (this skill, Rounds 0-4) writes the tour file + `HttpCase` wrapper; Execute (`odoo-instance` -> `odoo-instance-ops`) provisions the server and runs the suite; Adjudicate (caller or `odoo-qa-tester`) compares actual vs oracle. Full contract: `${CLAUDE_PLUGIN_ROOT}/snippets/test-execution-handoff.md`. When emitting NEEDS_NEXT (below), add `http_port: true` to `inputs` if the module has tour/HttpCase tests.

## Adapt mode (forward-port test translation)

Adapt mode forwards the INTENT of tests from `src_version` to `tgt_version` - it does NOT
copy the text. Full protocol: `${CLAUDE_PLUGIN_ROOT}/skills/odoo-test-writing/references/fp-adapt-mode.md`.

**Summary of steps:**

1. **Classify** each assertion as INTENT (guards an observable business outcome) or
   CAPTURE-CODE (asserts an internal - private method, call count, version-specific field
   name with no semantic equivalent on target). Use `api_version_diff` + `model_inspect`
   against `tgt_version` to ground the classification.

2. **Strip** CAPTURE-CODE assertions. Keep every assertion that guards observable behavior.
   Drop a `def test_*` only when nothing in it is INTENT. Record dropped methods in the
   Continuation Contract.

3. **Translate API** to `tgt_version` - framework imports, Form helper path, `@tagged`
   convention, renamed fields (from `api_version_diff`), changed method signatures
   (from `model_inspect`). OSM grounding is mandatory - same as Rounds 1-2 above but
   targeting `tgt_version`. Specifically: call `test_base_classes(odoo_version='<tgt_version>')` to confirm the correct base class for the target, applying the ADAPT RULE in `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-era-boundaries.md` row 3 (test base-class windows + `SavepointCase` adapt boundary) - do not restate the windows here. Also reaffirm the `cr.commit()` FORBIDDEN contract from the same call. Call `tests_covering(model='<model>', odoo_version='<tgt_version>')` to check whether an equivalent test already exists on the target - if it does, record as outcome (a) "already covered on target" and skip forward-port of that method (see [[fp-merge-absorption]]).

4. **Confirm RED on target** - the translated test must fail on the target before the
   production code is adapted. State the failing assertion as evidence. If the test passes
   immediately (behavior already in target), record as outcome (a) and skip code-adapt
   (see [[fp-merge-absorption]]).

**BANNED in adapt mode** (in addition to the standard bans in `test-behavior-contract.md`):
- Widening or relaxing an assertion to make it pass on target
- Changing `expected` values without a cited reason from `api_version_diff` / intent doc
- Dropping a test because translation is hard (escalate BLOCKED instead)
- `@skip`, `pass`, or empty assertion bodies to silence a red test

## Output format

Files written directly to the addon's `tests/` (or `static/`) directory:
- `<addon>/tests/__init__.py` - ensure new test module is imported (append if exists)
- `<addon>/tests/test_<feature>.py` - the test file (TransactionCase / HttpCase)
- `<addon>/static/tests/test_<feature>.js` - JS test file (Hoot/QUnit; only when JS unit tests requested)
- `<addon>/static/tours/<feature>_tour.js` - JS tour file (only when tour/HttpCase requested; tours live under `static/tours/`, not `static/tests/`)

Report format: `${CLAUDE_PLUGIN_ROOT}/skills/odoo-test-writing/references/output-format.md`

## Standalone-first fallback

When OSM is unreachable, follow `${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md`:

- **Tier 2 - Disk:** `Grep`/`Read` the addon's `models/*.py` for field names/types; locate existing tests in `tests/` to infer the framework in use. Write the test file to the correct location - do NOT fall back to copy-pasteable blocks unless the repo is genuinely inaccessible.
- **Tier 2 - Version fallback:** Derive Odoo version from manifest `version` field if `<SHARE_DIR>/context.md` is absent.
- **Copy-pasteable-only mode** (last resort): emit standalone blocks only when the repo itself is unreachable. Label `grounded: local-source (not OSM-indexed)` when built from disk; `OSM unavailable - ungrounded` only when neither OSM nor local source is available.
- Escalate (`NEEDS_CONTEXT`) only for business decisions no source encodes - never ask a human to paste field lists, model definitions, or manifests.

When no live Odoo instance is reachable to run the suite under `--test-enable` (FRESH DB: `-i <module>`; already-installed DB: `-u <module>`) in Round 5: emit `status: NEEDS_NEXT` with (execution is instance-REQUIRED - authoring is NOT gated, only the run is; see `${CLAUDE_PLUGIN_ROOT}/snippets/instance-optional-completion.md` for the instance-optional/instance-required split):
```
next:
  - skill: odoo-instance
    reason: provision the live instance needed to run the suite and confirm RED; pass mode (fresh|reuse) and log_mode through when known; add http_port: true if the module has tour/HttpCase tests requiring --http-port
    inputs: {operation: run-tests, series: "<series from context>", modules: ["<module under test>"], mode: "<fresh|reuse - fresh installs with -i, reuse re-runs with -u; omit to let the executor decide>", log_mode: "<warn|info|debug|sql verbosity - optional>", http_port: "<true if tour/HttpCase present, else omit>"}
    confidence: 0.9
    risk_level: L2
```
so the run-harness provisions one; fall back to `BLOCKED` only if provisioning is itself impossible. Test file authoring (Rounds 0-4) proceeds regardless. This is the canonical NEEDS_NEXT pattern referenced by `${CLAUDE_PLUGIN_ROOT}/snippets/test-execution-handoff.md`.

## Continuation Contract

When you finish, append a Continuation Contract block per `${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next). Set `produced` to the test file paths you wrote, and state the **RED confirmation** (test-first mode: "RED - production code not yet written"; coverage mode: "RED-on-rule-removal verified"). A coder consuming these tests implements to green and must not edit them. Additive output for the run-harness - it does not change anything produced above.
