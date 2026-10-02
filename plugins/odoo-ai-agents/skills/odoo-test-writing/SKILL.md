---
name: odoo-test-writing
argument-hint: "[model/module to test]"
description: >
  Write executable Odoo test files that protect business behavior - not just cover code - once the code
  exists: new or adjusted tests, each proven by an executed break-check. Produces Python
  `test_*.py` (TransactionCase / Form helper / `@tagged`) and JS Hoot / QUnit suites, selecting the correct
  framework per version. Also translates existing tests across major Odoo versions (adapt mode): strips
  implementation-coupled assertions, maps renamed APIs via OSM. Grounds every test via OSM MCP calls.
  Fire on: test coverage, CI protection, forward-port test translation, or tour/HttpCase. Vietnamese: "viết test cho model", "bao phủ ràng buộc bằng test",
  "test hành vi nghiệp vụ Odoo", "dịch test sang version mới", "viết test JS Hoot", "viết tour Odoo", "viết
  HttpCase". Writes RUNNABLE files: a non-executing prose test-PLAN or test-case table -> odoo-qa-suite;
  write scenarios then run live and adjudicate PASS/FAIL -> odoo-acceptance; static code review ->
  odoo-code-review; runtime errors -> odoo-debug
model: inherit
---

## Role

QA Engineer / backend developer writing automated tests for Odoo, every supported series. Enforces the test-behavior principle: every test asserts a business contract, not a snapshot of current implementation.

## Out of Scope

- **Static review / quality audit of existing tests** - use `odoo-code-review`
- **Writing the production code under test** - use `odoo-coding`; a break-check alters production code only until it restores it (Round 7)
- **Debugging a test that fails at runtime on a live instance** - use `odoo-debug`
- **Upgrade-safety audit** - use `odoo-deprecation-audit`
- **Running the module suite or a tour/HttpCase suite** - execution is delegated via NEEDS_NEXT to `odoo-instance`; the only runs this skill makes are the baseline and break-check runs of Round 7, at test-method granularity, on the database of a forwarded `INSTANCE_HANDLE`. Authoring (Rounds 0-6) is always in scope regardless of instance availability

> **Performance / load tests are IN scope (lightweight mode)** - author a query-count guard (`@tagged('post_install','-at_install')` + `self.assertQueryCount(...)` / `with self.assertQueries([...])`) or a bounded-time assertion over a seeded volume, grounded via OSM (`orm-performance.md` idioms). It guards a BEHAVIOR contract ("stays O(1) queries under N records"), never a benchmark. A full external load/stress harness (locust-style concurrency, sustained throughput) is out of scope -> a dedicated perf harness / `odoo-perf-audit` for diagnosis; state that owner explicitly rather than leaving it unowned.

> Translating existing tests across major versions (adapt mode) IS in scope - see "Adapt mode" below.

## When to use

Five modes, every one run AFTER the production code exists, and every behavior test in each proven by an executed break-check (`${CLAUDE_PLUGIN_ROOT}/snippets/test-sensitivity-contract.md` § The break-check):

- **`change` (after the code).** Write new tests, or adjust existing ones, for the behavior the REQUEST changed. In the `odoo-coding` loop the `odoo-coder` coordinator launches the dedicated `odoo-test-writer` agent ONCE per node after its coders finish, and that agent invokes THIS skill INLINE - so this capability is the coding loop's test author, reached through that context-isolated agent (coders never author tests). Standalone use works the same way once the code is in place.
- **Coverage (after the code).** Backfill behavior-protecting tests for existing code; the `odoo-code-review` test-coverage gate routes here when a CRITICAL/HIGH change ships with no protecting test.
- **Adapt (forward-port test translation).** Translate source tests to the target Odoo version AFTER the adapt code exists (see Adapt mode below). Reached through `odoo-coding` -> `odoo-coder` -> `odoo-test-writer` with `SOURCE TESTS` / `BROKEN TEST-SYMBOLS` / `BUCKET`, or directly with a source file + version pair.
- **Performance/load (lightweight).** Author a query-count / bounded-time behavior guard for a stated performance contract (boundary in Out of Scope).
- **Tour/HttpCase (full-stack UI acceptance).** Write a JS tour registered in the series' tour registry (grounded in Round 1) driven by a Python `HttpCase.start_tour(...)`, decorated `@tagged('post_install', '-at_install')`. Use when acceptance flows span multiple real browser steps needing an HTTP server, or `odoo-qa-planner` oracle scenarios need browser-level state verification. Do NOT use for non-browser logic (use `TransactionCase`/`Form`) or a JS unit with mocked models (use Hoot - no server, no real browser). Authoring needs no live instance; the baseline and break-check run on the forwarded handle's database (Round 7); executing the suite MUST be delegated per `${CLAUDE_PLUGIN_ROOT}/snippets/test-execution-handoff.md`.

Trigger when the user wants: coverage for a model/computed field/constraint/onchange/wizard; a test guarding a named business rule; JS Hoot/QUnit tests for an OWL component; a test droppable into `tests/` and runnable under `--test-enable` (fresh DB `-i <module>`; re-run on installed DB `-u <module>`); the tests that prove a change a coder just wrote; a source test translated for forward-port; or a JS tour + HttpCase file.

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

Run the Rounds in order; each one's output feeds the next.

**`WORKTREE_PATH`.** The test file(s) are git-tracked, so per
`${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md` § Universal skeleton field 5 Round 5 writes into a dedicated worktree -
never the principal checkout. When invoked via the `odoo-test-writer` agent, that agent already `cd`s
into its `WORKTREE_PATH` before invoking this skill inline - the paths below are relative to that
cwd. Invoked standalone (no wrapping agent), require `WORKTREE_PATH`
yourself and resolve `<addon>` under it; with none supplied and no worktree already in scope,
provision one via `git-toolkit:git-ops` before Round 5, per
`${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`.

### Round 0 - resolve project facts + pin the OSM session

Resolve series, profile, and module scope per `${CLAUDE_PLUGIN_ROOT}/snippets/project-facts-resolution.md`, then call `set_active_version('<resolved series>')`. Never default a series - a wrong series selects the wrong test framework, so an unresolved series joins the ladder's single batched ask.

### Round 1 - read the target series' test framework, then select (MANDATORY, OSM-grounded)

Before writing or adjusting any test, read how the TARGET series' test framework works - never write
a test from memory of another series. Call `test_base_classes(odoo_version='<version>')` for the
menu, then `test_class_inspect(name='<class or helper>', odoo_version='<version>')` for every base
class and helper the test will use (base chain, cursor contract, setUp behavior). When OSM lacks a
detail you need - a `Form` method, a decorator's arguments, an assertion helper - Read `odoo/tests/`
in the target series' checkout to fill that gap. Then select per the bullets below.

- **Python:** `TransactionCase` (rolls back after each test); `Form` helper for UI-level
  interactions - ALWAYS call `test_base_classes(odoo_version='<version>', name='Form')` here for a
  Python test, since Round 5 drives every form-entered rule through it (its window:
  `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-era-boundaries.md` row 3 - do not restate it). Tag
  `@tagged('post_install', '-at_install')` or `@tagged('at_install')` where the series ships
  `@tagged` (row 8). The base-class menu carries the PP3 contract: **`cr.commit()` FORBIDDEN -
  isolation is savepoint rollback**. Drill into the chosen class with
  `test_base_classes(odoo_version='<version>', name='TransactionCase')` for setUp behavior
  (savepoint per method) and home module. Do NOT use `lookup_core_api` for test base classes - it
  indexes core ORM/API symbols only and returns not-found (the import is the standard
  `from odoo.tests import TransactionCase`). For **`HttpCase`**: call
  `test_base_classes(odoo_version='<version>', name='HttpCase')` to confirm its target-version
  contract - it extends `TransactionCase` and adds a threaded HTTP server plus
  `start_tour(tour_name, login='admin', ...)`; `cr.commit()` stays FORBIDDEN. Use `HttpCase` ONLY
  when exercising a tour or `url_open` endpoint - never for pure model/field/constraint logic.
- **JS:** ALWAYS call `js_test_inspect(module='<module>', odoo_version='<version>')` FIRST to
  confirm the exact framework mix, suite paths, describe blocks, and mock_models convention, THEN
  call `find_test_examples(query='<framework> describe test expect', kind='js', odoo_version='<version>')`
  for concrete test-only examples matching the confirmed framework. QUnit and Hoot both ship and
  both run on some series, and the mix varies by module
  (`${CLAUDE_PLUGIN_ROOT}/snippets/odoo-era-boundaries.md` row 2) - never pick a framework or an
  import path from the series number. Do NOT use `lookup_core_api` for JS frameworks; it indexes
  Python core API only.
- **JS tour:** Tours live in `static/tours/<name>.js` and register in the series' tour registry.
  ALWAYS call `js_test_inspect(module='web_tour', odoo_version='<version>')` FIRST to confirm the
  registry path, step object shape, and whether `run` accepts a string action or a function on the
  target series, then `find_test_examples(query='web_tour start_tour tour steps trigger run', kind='js', odoo_version='<version>')`
  for grounded step examples - never write tour steps, the `run` syntax, or the module-loader call
  form from memory. Step anatomy: `{ trigger: '<CSS selector>', run: '<string action or function>' }`.
  Tour steps are implicit oracles: each `trigger` asserts the UI reached that state before
  proceeding. Additionally, assert the observable business outcome (state change, produced record,
  computed value) in the `HttpCase` body AFTER `start_tour` completes - tour completion alone is not
  evidence of correctness.

### Round 2 - model, field and form-view grounding

For each model call `model_inspect(model='<model>', method='fields', odoo_version='<version>')` to get real field names and types (do not guess from description), relational paths for `@api.depends`/`Form` interactions, existing method signatures. Call `validate_relation` or `resolve_orm_chain` for relational chains (`partner_id.country_id.code`) to confirm each hop.

**Ground the form view the user acts in.** For every rule a user triggers by entering or changing
data in a form view, read that form view: `model_inspect(model='<model>', method='views', odoo_version='<version>')`,
and the view XML in the WORKTREE for any view the change adds or alters (the index never holds the
code just written). Record which fields the acting user can set, in which order, and under which
`groups` / readonly / invisible / required modifiers - Round 5 sets exactly those on the `Form`.

When the test needs to extend an existing test helper (e.g. `AccountTestInvoicingCommon`, `MailCommon`, a module's own `Common` class), call `test_class_inspect(name='<HelperClass>', odoo_version='<version>')` to get the full base chain, the cursor contract (commit_allowed flag), and which other test files subclass it. This tool does NOT return setUpClass fixture contents - to see what fixtures a helper actually seeds, Read the source file at the path shown in "Defined in:". Use the inherited fixtures directly - do not copy-paste setUp code that the helper already provides.

For any CORE ORM / action-method symbol the setUp, factory dict keys, or assertions call directly (e.g. `create`, `write`, `action_confirm`), apply the Tier-0 currency check (`${CLAUDE_PLUGIN_ROOT}/snippets/symbol-currency-check.md` §Test): `lookup_core_api(name='<symbol>', odoo_version='<version>')` for core ORM/action symbols ONLY. Base-class currency stays with `test_base_classes` and JS-framework currency stays with `js_test_inspect` (Round 1). Adapt mode keeps its own `api_version_diff` step (see below).

### Round 3 - search the existing tests and their patterns (MANDATORY, anti-duplication)

Before writing any test, find every existing test that already touches each target behavior, and
the patterns the target series uses. Run ALL of these - the index may not hold this branch, and it
never holds the code just written:

- `tests_covering(model='<model>', odoo_version='<version>')` - test methods with a static coverage
  edge to the model or field;
- `find_test_examples(query='<behavior> <model>', odoo_version='<version>')` (JS:
  `kind='js'`) - tests exercising the same flow, and the real test-only pattern to follow. Use
  `find_test_examples`, not `find_examples` - the latter mixes in production code that contaminates
  the pattern;
- `test_coverage_audit(module='<module>', odoo_version='<version>')` - fields/methods with zero
  coverage;
- `Grep` the module's `tests/` and `static/tests/` (and `static/tours/`) in the WORKTREE for the
  model, the fields and the action methods the change touches.

Decide per target behavior:

- **Fully protected** by an existing test -> write nothing; it is `COVERED` only once its own
  break-check in Round 7 turns it red.
- **Partly protected** -> ADD a new test method to that existing test class for the missing part.
- **Expectation made obsolete by the REQUEST** (this also governs every `OBSOLETE CANDIDATES`
  entry) -> adjust it per `${CLAUDE_PLUGIN_ROOT}/snippets/test-sensitivity-contract.md`
  § Adjusting an existing test. Adjust for no other reason.
- **Not protected** -> write a new test in Round 5.

A new test duplicating one that already protects the behavior is a defect.

### Round 4 - read the behavior contract now (MANDATORY)

Read ${CLAUDE_PLUGIN_ROOT}/snippets/test-behavior-contract.md now, in full, before writing a line of
a test - every time, never from memory of it. Round 5 applies every section of it.

### Round 5 - write or adjust tests

Write `<addon>/tests/test_<feature>.py` (or `<addon>/static/tests/test_<feature>.js` for JS), `<addon>` resolved under `WORKTREE_PATH` per the Method preamble above, or add to the existing test class Round 3 chose. Apply these rules without exception:

**Business-rule naming.** Every test method name states the rule being protected: `test_discount_cannot_exceed_20pct`, `test_confirmed_order_locks_price`, `test_access_denied_for_portal_user`. Not: `test_sale_order_field`, `test_write_method`.

**Apply the contract you read in Round 4, section by section:** § Protect the outcome, never the implementation; § Drive the real workflow; § Simulate the user with Form; § Never freeze the present; § Keep the test simple; and § Never assert TRANSLATED or DISPLAY text (finding an element by its visible label is a LOCATOR and stays allowed; translation correctness is gated by the `odoo-i18n` pipeline, never by this suite). Expected values come from `TARGET BEHAVIOR`, never from reading the code under test.

**Form is MANDATORY for a form-entered rule.** When the rule is triggered by data a user enters or
changes in a form view - a constraint on save, an onchange, a default, a readonly/required
modifier - arrange AND act through `Form`, on the fields Round 2 grounded, in the user's order:

- a refused value: set the fields on the `Form`, then call `save()` inside
  `assertRaises(<BusinessError>)`;
- an accepted value: plain `save()`, then assert the stored outcome on the saved record.

ORM `create` / `write` is allowed only for ARRANGE data the user does not enter in that flow.
Where the target series ships no `Form` (Round 1), drive the flow with a tour / HttpCase.

**Expected log noise (SSOT: `${CLAUDE_PLUGIN_ROOT}/snippets/test-expected-log-contract.md`).** Wrap
with `assertLogs` / `mute_logger` only when the exercised path actually logs a WARNING or ERROR - a
constraint's `ValidationError` on save logs none, so it gets no wrapper. When you capture, assert the
logger and level fired, never the message wording; assert the exception TYPE and the unchanged
state. For JS, confirm the per-module framework with `js_test_inspect` before emitting any
suppress/assert idiom.

**Register the test, never import it from the module.** Odoo's test loader imports
`<module>.tests` itself: add each new file to `<addon>/tests/__init__.py` (create it when absent),
and never add `from . import tests` to the module's own `__init__.py`. A JS test or tour asset the
series loads through a manifest bundle key is the one `__manifest__.py` edit you may make - report it
as a `MANIFEST TEST ASSETS:` record (`test-sensitivity-contract.md` § Break-check record).

**Cross-module test staging (when this module is part of a multi-module node).** Every Odoo test
class is `at_install` by default and runs RIGHT AFTER its OWN module installs - before any module
later in the node's dependency order exists. A default test in module A therefore CANNOT see
module B, even when both install in the same `-i` run. **A test that asserts on behaviour
contributed by ANOTHER module in this node - one that installs after the test's own module, or one
with no dependency edge to it at all - must be staged into the post-install phase, or it will run
before that module exists.** Odoo runs tests in TWO phases on every indexed series: the at-install
phase, right after each module installs, and the post-install phase, at the end of module loading
with every module in the `-i` list present. A test class is in the at-install phase by default, so
an unstaged class in the first module fires before the second is loaded. The post-install phase is
the only moment the whole node is visible.
- Stage that class post-install with the mechanism the TARGET series ships - `@tagged` or the
  phase decorators - read from `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-era-boundaries.md` row 8 and
  confirmed with `find_test_examples` for the target series. Leave every single-module assertion at
  the default.
- Placing the test in the LAST module to install also works, but ONLY when the node's modules are
  totally ordered by `depends` - a node spanning modules with NO dependency edge between them has no
  "last module", so stage it post-install there.

**Placement: which module's `tests/` directory hosts the file.** The cross-module assertion's file
lives in the LAST module, in the node's dependency order, among the modules it touches. When those
modules carry no dependency edge between them, it lives in the node's own PRIMARY module instead -
the tag/decorator above (not the file's location) is what makes the whole node visible, so hosting
it in the primary module loses nothing.

A cross-module assertion that fails with `KeyError`/`AttributeError` on a symbol you know exists is
this bug, not a code defect: fix the staging, do not chase the symbol. When the brief's
`CROSS-MODULE ASSERTIONS` names which target behaviours cross a module boundary, apply the
decorator above at authoring time rather than waiting for the integrated test to fail (mirrored in
`odoo-coder`'s own Cross-module test staging step).

**Minimal arrange.** `setUp` creates only records required by the test. No fields/models/fixtures for "possible future tests".

**Independence (FIRST rule).** Each test passes in isolation and in any order. No mutable shared state via class-level attributes set inside a test body.

**The test must build its own data - never reach for a demo record.** A test file outlives the
instance it was written on: it later runs in the automation-test environment, whose demo shape is
the automation-test row of `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md` § Demo data by
build PURPOSE. On any series where that row says the test build carries NO demo, a test that reads a
demo record by xmlid or by name fails there even though it passed where it was authored. So create
every record the test needs in `setUpClass` / `setUp`, and treat a demo xmlid in an assertion or a
fixture lookup as a defect to fix, not a shortcut - including when you are authoring against a live
demo-carrying instance (an acceptance sweep, a doc capture), where the record IS present and the
test will pass in front of you. The one place a demo reference is legitimate is a test that exists
to assert something about the demo data itself.

**Comments and docstrings in the authored files.** Follow `${CLAUDE_PLUGIN_ROOT}/snippets/code-comment-contract.md`. The test method NAME states the business rule it protects, so a docstring that merely restates the name is banned; comment only a non-obvious arrange step, stating what it SERVES rather than what it does. No attribution or self-defense line, no narration of the break-check, no ticket, date or author - a test file is where those collect fastest.

### Round 6 - static validation

- Import paths resolve (the base-class import Round 1 grounded for the target series)
- `@api.depends` paths used in `Form` interactions pass `validate_depends`
- Field names in `env['<model>'].create({...})` and on every `Form` match `model_inspect` output
- Every new test file is listed in `tests/__init__.py`; the module's own `__init__.py` is untouched

Backend code-quality gate: the lint-class CI-parity gate (module set:
${CLAUDE_PLUGIN_ROOT}/snippets/lint-gate-modules.md) runs ONCE, over the run-integration branch's aggregate diff, at `run-harness`'s
pre-PR tail - not appended per test-run here
(`${CLAUDE_PLUGIN_ROOT}/skills/run-harness/references/run-integration.md` § Pre-PR tail). Test method local variables must follow `${CLAUDE_PLUGIN_ROOT}/snippets/python-naming-conventions.md`: Rule A (no `l`/`O`/`i`) applies universally (pylint C0104 blocks the gate); Rules B/C (meaningful names, `for r in self`) apply on Viindoo Standard/Internal profiles. On later execution under `--test-enable` (FRESH DB `-i <module>`; already-installed DB `-u <module>` - `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md` § Test run on an existing database - `-i` vs `-u`; full rule `${CLAUDE_PLUGIN_ROOT}/docs/reference/ODOO-TESTING.md`), resolve the interpreter (the instance's `python` field) per `snippets/venv-resolution.md`, not system `python3`.

### Round 7 - baseline, then break-check every behavior test (MANDATORY)

A test proves nothing until it has passed on the correct code and failed against a broken rule.
Run the sequence `${CLAUDE_PLUGIN_ROOT}/snippets/test-sensitivity-contract.md` § The break-check
states, choosing each break from `CHANGE KIND` per § How to break each change kind. How to run it
here:

- **Where it runs.** Every run is one `instance_build` op `test` with `test_mode` `reuse` on the
  database of the forwarded `INSTANCE_HANDLE`, made by invoking the `odoo-instance` skill (inline
  leaf-mode inside the `odoo-test-writer` agent) on a one-port lease of your own on that database,
  released before you return - never on the handle's own lease, never a new database, never
  `odoo-instance-ops`. No handle: the tests stay written and
  every baseline and break-check is pending - emit the `NEEDS_NEXT` under § Standalone-first
  fallback.
- **Method granularity.** Tag each run with exactly the test methods it targets:
  `test_tags` = `/<module>:<Class>.<method>[,/<module>:<Class>.<method>...]` - never `/<module>`,
  never untagged (`${CLAUDE_PLUGIN_ROOT}/snippets/test-scope-contract.md`). Read `TESTS_RUN` and
  the failed/errored counts from the final `job_wait` summary, and the failing names and traceback
  heads from its `findings_path`. `TESTS_RUN` must EQUAL the number of methods you targeted; any
  other count is a broken measurement - fix the tags and re-run. A JS test is targeted through the
  Python test method that runs its suite on the series (ground it with `find_test_examples`), read
  from the `JS_*` figures. Where `cli_help` shows the series has no test-tag filter, the run carries
  the module's suite: record as `selected` the targeted methods found in `findings_path` / the log.
- **Baseline first.** Run the tests you authored or adjusted, and every test you claim as
  `COVERED`, on the UNBROKEN code: every one must pass. A red baseline is not a break-check: compare
  the failing assertion with `TARGET BEHAVIOR` - a test that misreads the rule, or a broken
  measurement, is yours to fix before any break; a test that states `TARGET BEHAVIOR` faithfully
  means the code contradicts it - never bend the expected value; stop with `status: BLOCKED`,
  `blocked_reason: baseline red - <test> expects <value> per <REQUEST item>` (the caller applies
  § The loop, bounded).
- **Copy, break, run, restore.** Before the break, copy each production file you will alter to
  `<ISOLATE_DIR>/break-check/<path relative to WORKTREE_PATH>` and record its `sha256sum`; restore by
  copying it back and re-hashing - no git. Break exactly the rule, in the file as it stands (a
  `bug fix` break neutralises the fix at the brief's `fix hunk file:lines`), so the code still loads. Deleting a field,
  model, xml-id or imported symbol is banned (it manufactures a broken measurement); neutralising a
  method body, or removing a method nothing else references, is allowed. One run per broken rule,
  carrying every test that guards it.
- **What counts as red.** A targeted test FAILS at its assertion, or its act step raises the
  business exception the broken rule produces (an accept-path test whose `save()` now raises the
  rule's `ValidationError`). Everything § Broken measurement is not a red lists never counts - fix
  it and re-run. Only the tests you authored, adjusted or claim as `COVERED` must go red; an
  existing test for adjacent behavior may stay green. A targeted test that stays green guards
  nothing: strengthen its assertion and re-run; never relax a test, and never fix code here.
- **A data-file break leaves the database dirty.** A break in an XML/CSV data file loads broken
  records into the database: run those breaks after every other run on that database, and mark the
  record `data-file yes` - the caller's next verdict on that database then comes from a fresh build.
- **Restore before anything else.** Restore every altered production file and prove its sha256
  matches before the next break and before you return; a mismatch you cannot repair ->
  `status: BLOCKED` naming the file.
- **Record** one line per behavior in the exact shapes § Break-check record fixes (`BREAK_CHECK`,
  `COVERED`, `ADJUSTED`, `NO NEW TEST`, `MANIFEST TEST ASSETS`; adapt adds `ABSORBED`). A
  re-dispatch whose `PRIOR ATTEMPT` names tests you already wrote runs only their pending baseline
  and break-checks.

**Tour/HttpCase execution boundary:** `HttpCase` + `start_tour` tests require a live HTTP server.
Do NOT run tour suites inline - the targeted Round 7 runs are the only runs this skill makes. Three
distinct roles: Author (this skill) writes the tour file + `HttpCase` wrapper and break-checks it;
Execute (`odoo-instance` -> `odoo-instance-ops`) provisions the server and runs the suite;
Adjudicate (caller or `odoo-qa-tester`) compares actual vs oracle. Full contract:
`${CLAUDE_PLUGIN_ROOT}/snippets/test-execution-handoff.md`.

## Adapt mode (forward-port test translation)

Adapt mode forwards the INTENT of tests from `src_version` to `tgt_version` - it does NOT
copy the text. Full protocol: `${CLAUDE_PLUGIN_ROOT}/skills/odoo-test-writing/references/fp-adapt-mode.md`.

**Summary of steps:**

1. **Classify** each assertion as INTENT (guards an observable business outcome) or
   CAPTURE-CODE (asserts an internal - private method, call count, version-specific field
   name with no semantic equivalent on target - or freezes the present: a count, an existence or a
   name of a field/view/method/record, an arch string, `__manifest__.py` contents). Use
   `api_version_diff` + `model_inspect` against `tgt_version` to ground the classification.

2. **Strip** CAPTURE-CODE assertions. Keep every assertion that guards observable behavior.
   Drop a `def test_*` only when nothing in it is INTENT. Record dropped methods in the
   Continuation Contract.

3. **Translate API** to `tgt_version` - framework imports, Form helper path, the test-phase
   convention, renamed fields (from `api_version_diff`), changed method signatures (from
   `model_inspect`). OSM grounding is mandatory - same as Rounds 1-2 above but targeting
   `tgt_version`. Specifically: call `test_base_classes(odoo_version='<tgt_version>')` to confirm the correct base class for the target, applying the ADAPT RULE in `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-era-boundaries.md` row 3 (test base-class windows + `SavepointCase` adapt boundary) - do not restate the windows here. Also reaffirm the `cr.commit()` FORBIDDEN contract from the same call. Run Round 3 against the target - an equivalent test already there is `COVERED` (with its own break-check) and that method is not forwarded.

4. **Prove it after the code** - translate AFTER the adapt code exists, then run Round 7 on every
   forwarded behavior test. The break is the business rule the forwarded test guards (§ How to
   break each change kind; `CHANGE KIND` `adapt (rule file:lines)` names where it lives) - never
   "disable the adapt code": an idiom or API adapt cannot be disabled without a broken measurement.
   A commit with `BUCKET` (a) - already absorbed by target core - has no ported code to break: run
   its forwarded test in this same launch, after the node's other code is adapted, as
   `${CLAUDE_PLUGIN_ROOT}/snippets/test-sensitivity-contract.md` § Absorption probe (forward-port classification, not a test gate)
   states. Green -> an `ABSORBED:` record. Red on the assertion -> report the commit for
   re-bucketing to (b)/(c) and stop for its tests; the coordinator re-dispatches the coder, then
   you. A `KeyError` / `AttributeError` / `Invalid field` on the target means the TRANSLATION is
   incomplete (a `BROKEN TEST-SYMBOLS` entry step 3 missed), never a classification and never a
   break-check result (§ Broken measurement is not a red) - fix the translation and re-run.

**BANNED in adapt mode** (in addition to the standard bans in `test-behavior-contract.md`):
- Widening or relaxing an assertion to make it pass on target
- Changing `expected` values without a cited reason from `api_version_diff` / intent doc
- Dropping a test because translation is hard (escalate BLOCKED instead)
- `@skip`, `pass`, or empty assertion bodies to silence a failing test

## Output format

Files written directly to the addon's `tests/` (or `static/`) directory:
- `<addon>/tests/__init__.py` - ensure new test module is imported (append if exists)
- `<addon>/tests/test_<feature>.py` - the test file (TransactionCase / HttpCase)
- `<addon>/static/tests/test_<feature>.js` - JS test file (Hoot/QUnit; only when JS unit tests requested)
- `<addon>/static/tours/<feature>_tour.js` - JS tour file (only when tour/HttpCase requested; tours live under `static/tours/`, not `static/tests/`)

Report format: `${CLAUDE_PLUGIN_ROOT}/skills/odoo-test-writing/references/output-format.md`

## Standalone-first fallback

When OSM is unreachable, follow `${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md`:

- **Tier 2 - Disk:** `Grep`/`Read` the addon's `models/*.py` for field names/types and its `views/*.xml` for the form view; locate existing tests in `tests/` to infer the framework in use. Write the test file to the correct location - do NOT fall back to copy-pasteable blocks unless the repo is genuinely inaccessible.
- **Tier 2 - Project facts:** series, profile, and module scope per `${CLAUDE_PLUGIN_ROOT}/snippets/project-facts-resolution.md`.
- **Copy-pasteable-only mode** (last resort): emit standalone blocks only when the repo itself is unreachable. Label `grounded: local-source (not OSM-indexed)` when built from disk; `OSM unavailable - ungrounded` only when neither OSM nor local source is available.
- Escalate (`NEEDS_CONTEXT`) only for business decisions no source encodes - never ask a human to paste field lists, model definitions, or manifests.

When no `INSTANCE_HANDLE` was forwarded for the Round 7 runs, or no live Odoo instance is reachable to run the suite under `--test-enable` (FRESH DB: `-i <module>`; already-installed DB: `-u <module>`): emit `status: NEEDS_NEXT` with a `PENDING BREAK_CHECK: <module>:<Class>.<method>[, ...]` line naming every test whose baseline and break-check are owed, and (execution is instance-REQUIRED - authoring is NOT gated, only the run is; see `${CLAUDE_PLUGIN_ROOT}/snippets/instance-optional-completion.md` for the instance-optional/instance-required split):
```
next:
  - skill: odoo-instance
    reason: run the baseline and break-checks - the tests are written and their break-checks pending; provision the live instance they need and hand its INSTANCE_HANDLE back so the break-checks run on it; pass mode (fresh|reuse) and log_mode through when known; GATE_ROLE node-verify - a break-check run is never the pre-PR lint gate
    inputs: {operation: run-tests, GATE_ROLE: node-verify, series: "<series from context>", modules: ["<module under test>"], test_tags: "<`/<m>` per module in modules - scopes the run to them; omitted, the executor derives the same thing>", mode: "<fresh|reuse - fresh installs with -i, reuse re-runs with -u; omit to let the executor decide>", log_mode: "<info|debug|sql verbosity - optional>"}
    confidence: 0.9
```
so the run-harness provisions one; fall back to `BLOCKED` only if provisioning is itself impossible. Test file authoring (Rounds 0-6) proceeds regardless; only Round 7 waits. This is the canonical NEEDS_NEXT pattern referenced by `${CLAUDE_PLUGIN_ROOT}/snippets/test-execution-handoff.md`.

## Continuation Contract

When you finish, append a Continuation Contract block per `${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next). Set `produced` to the test file paths you wrote, and carry the Round 7 record lines in the status block, in the exact shapes `${CLAUDE_PLUGIN_ROOT}/snippets/test-sensitivity-contract.md` § Break-check record fixes - never a bare sentence claiming a test can fail. With break-checks pending, carry the `PENDING BREAK_CHECK:` line under the `NEEDS_NEXT`. Additive output for the run-harness - it does not change anything produced above.
