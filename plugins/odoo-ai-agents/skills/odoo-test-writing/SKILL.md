---
name: odoo-test-writing
argument-hint: "[model/module to test]"
description: >-
  Write runnable Odoo tests (Python, JS Hoot/QUnit, tours) that guard business behavior
model: inherit
---

## Role

QA engineer / backend developer writing automated Odoo tests for every supported series. Every
test asserts a business contract, never a snapshot of the current implementation.

## Out of Scope

- **Static review of existing tests** -> `odoo-code-review`
- **Writing the production code under test** -> `odoo-coding`; a break alters production code only
  until you restore it
- **Debugging a test that fails at runtime** -> `odoo-debug`; **upgrade-safety audit** ->
  `odoo-deprecation-audit`
- **Running the module suite or a tour/HttpCase suite** -> `odoo-instance` via `NEEDS_NEXT`; the
  only runs this skill makes are its own targeted baseline and break runs. A full external
  load/stress harness -> a dedicated perf harness / `odoo-perf-audit`.

## When to use

Every mode runs AFTER the production code exists. In the `odoo-coding` loop this skill runs INLINE
inside the `odoo-test-writer` agent, which the `odoo-coder` coordinator starts once per node after
its coders finish (coders never author tests); standalone use works the same way.

- **`change`** - new or adjusted tests for the behavior the REQUEST changed.
- **`coverage`** - backfill behavior tests for existing code (the `odoo-code-review` coverage gate).
- **`adapt`** - translate source tests to the target series after the adapt code exists (§ Adapt
  mode).
- **`performance/load`** - a query-count guard (`assertQueryCount` / `assertQueries`) or a bounded
  time over a seeded volume: a behavior contract ("stays O(1) queries under N records"), never a
  benchmark.
- **`tour/HttpCase`** - a JS tour driven by `HttpCase.start_tour(...)`, tagged post-install, for
  flows that need a real browser and HTTP server; never for pure model logic (TransactionCase /
  Form) or a mocked JS unit (Hoot).

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

The principles - whether a test is needed, the real break, the exact restore, the brief report -
are stated once in `${CLAUDE_PLUGIN_ROOT}/snippets/test-sensitivity-contract.md`; what a good test
looks like in `${CLAUDE_PLUGIN_ROOT}/snippets/test-behavior-contract.md`. Read both before writing,
every time. The steps below are how to apply them here; use judgment where a step does not fit.

Write test files in the brief's `WORKTREE_PATH` (the `odoo-test-writer` agent already `cd`s there).
Invoked standalone with no worktree in scope, provision one through `git-toolkit:git-ops` before
writing (`${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`).

### 1. Pin the series, read the framework

Resolve series, profile and module scope per
`${CLAUDE_PLUGIN_ROOT}/snippets/project-facts-resolution.md` and `set_active_version` - never default
a series; a wrong one selects the wrong framework. Then read how the TARGET series' framework works
before writing a line: `test_base_classes` for the menu, `test_class_inspect` for every base class
or helper you use (base chain, cursor contract - `cr.commit()` is forbidden; isolation is savepoint
rollback). Where OSM lacks a detail (a `Form` method, a decorator argument), read `odoo/tests/` in
the target checkout.

- **Python:** `TransactionCase`; `Form` for what a user enters in a form (its window per series:
  `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-era-boundaries.md` row 3); `HttpCase` only for a tour or a
  `url_open` endpoint.
- **JS:** `js_test_inspect(module='<module>', odoo_version='<version>')` first - Hoot and QUnit
  both ship on some series and the mix varies by module (row 2) - then
  `find_test_examples(query='<framework> describe test', kind='js', odoo_version='<version>')` for
  that framework.
- **Tour:** `js_test_inspect(module='web_tour', odoo_version='<version>')` for the registry path
  and step shape, then `find_test_examples` for real steps - never write tour syntax from memory. Assert the business
  outcome in the `HttpCase` body after `start_tour`; completing the tour is not evidence.

### 2. Search the existing tests first

`tests_covering`, `find_test_examples` (test-only chunks - not `find_examples`, which mixes in
production code), `test_coverage_audit`, and a `Grep` of the module's `tests/`, `static/tests/` and
`static/tours/` in the worktree (the index may not hold this branch). Then per behavior: fully
covered -> write nothing, but prove the existing test by a break; partly covered -> add a method
to that test class; an expectation the REQUEST made obsolete (including `OBSOLETE CANDIDATES`) ->
adjust it and say why; not covered -> write a new test. A duplicate test is a defect.

### 3. Ground the model and the form view

`model_inspect` for real field names and method signatures; `validate_relation` /
`resolve_orm_chain` for relational paths. For a rule the user triggers in a form, read the form view
(`model_inspect(model='<model>', method='views', odoo_version='<version>')`, plus the view XML in the worktree for anything the change adds -
the index never holds code just written). Reuse an existing test helper's fixtures
(`test_class_inspect`, then read its source) instead of copying setUp code. For core ORM/action
symbols the test calls directly, apply `${CLAUDE_PLUGIN_ROOT}/snippets/symbol-currency-check.md`
§Test.

### 4. Write or adjust

Write `<addon>/tests/test_<feature>.py` (JS: `static/tests/`, tours: `static/tours/`) or add to the
test class step 2 chose, applying `test-behavior-contract.md` in full: outcome not implementation,
the real workflow, `Form` for form-entered data, never freeze the present, never assert TRANSLATED
or DISPLAY text, keep it simple. Name each method after the rule it protects
(`test_discount_cannot_exceed_20pct`). Expected values come from `TARGET BEHAVIOR`, never from the
code.

- **Own data only.** Create every record the test needs; never read a demo record - the test later
  runs in the automation-test environment, which on some series loads no demo
  (`${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md` § Demo data by build PURPOSE).
- **Register the file** in `<addon>/tests/__init__.py`; the module's own `__init__.py` stays
  untouched. A JS test or tour asset loaded through a manifest key is the one `__manifest__.py`
  edit you may make.
- **Expected log noise** - wrap with `assertLogs` / `mute_logger` only when the path really logs a
  WARNING or ERROR, and assert the logger and level, never the wording
  (`${CLAUDE_PLUGIN_ROOT}/snippets/test-expected-log-contract.md`).
- **Cross-module assertions.** A test class runs at install of its OWN module by default, before
  any later module of the node exists. A test that asserts behavior contributed by ANOTHER module
  must be staged into the post-install phase - the only moment the whole node is visible - with the
  mechanism the target series ships (`${CLAUDE_PLUGIN_ROOT}/snippets/odoo-era-boundaries.md` row 8).
  Host it in the last module of the node's dependency order; a node whose modules share no
  `depends` edge has no "last module", so host it in the primary module. A `KeyError` on a symbol
  you know exists there is this staging bug, not a code defect.
- **Comments** follow `${CLAUDE_PLUGIN_ROOT}/snippets/code-comment-contract.md`: the method name
  already states the rule, so never repeat it; no attribution, no break narration. Test locals follow
  `${CLAUDE_PLUGIN_ROOT}/snippets/python-naming-conventions.md` (Rule A everywhere).

Static check before running: imports resolve, `@api.depends` paths used in `Form` interactions pass
`validate_depends`, field names match `model_inspect`. The lint gate runs once at `run-harness`'s
pre-PR tail, not here (`${CLAUDE_PLUGIN_ROOT}/snippets/lint-gate-modules.md`).

### 5. Prove each behavior test, then restore

Run on the forwarded `INSTANCE_HANDLE`'s database through the `odoo-instance` skill (inline
leaf-mode, which decides the lease and has you release what you took), `instance_build` op `test`,
`test_mode` `reuse`, with the brief's `SERVER_WIDE` as `server_wide` when present, tagged at method level - `/<module>:<Class>.<method>[,...]`, never the whole module
(`${CLAUDE_PLUGIN_ROOT}/snippets/test-scope-contract.md`). Read the counts from the final
`job_wait` summary and the failures from its `findings_path`.

1. **Baseline** - the tests you wrote, adjusted or rely on pass on the unbroken code. A test red
   here either misreads the rule (fix the test) or states `TARGET BEHAVIOR` faithfully (the code
   is wrong: stop `BLOCKED` with the test, the value it expects and the REQUEST item - never bend
   the expected value).
2. **Break** exactly the rule, keeping a copy of the file first - the code must still load.
   Neutralise a method body or put the old rule back; never delete a field, model, external id or
   import (that proves only that the code is broken). An accept-path test ("20 is allowed") is
   proven by breaking the rule the other way (tighten it so 20 is refused).
3. **Run only the affected tests** and watch them fail - at an assertion, or with the business
   exception the broken rule raises. A load error, a missing field or zero tests selected is a
   broken measurement: fix it and re-run. A test that stays green guards nothing - strengthen or
   replace it; never relax it.
4. **Restore** the file exactly and confirm it (e.g. by hash) before the next break and before you
   return. The final verdict must come from a database that reflects the restored code - say when
   a break touched a data file or the schema, so the caller rebuilds fresh.

No handle -> the tests stay written and the runs are pending (§ No instance).

Tour/HttpCase: author the tour + `HttpCase` wrapper and prove it the same way; running the suite
and adjudicating it belong to `odoo-instance` and the caller
(`${CLAUDE_PLUGIN_ROOT}/snippets/test-execution-handoff.md`).

## Adapt mode (forward-port test translation)

Forward the INTENT of the source tests, not their text; the full protocol is
`${CLAUDE_PLUGIN_ROOT}/skills/odoo-test-writing/references/fp-adapt-mode.md`. In short: classify
each assertion as INTENT or CAPTURE-CODE (internals, a version-only name, a frozen count or
existence), strip the capture-code, translate the API to the target with OSM
(`api_version_diff`, `model_inspect`, `test_base_classes`), then prove the forwarded test after the
adapt code exists by breaking the business rule it guards - never by "disabling the adapt code".
For a commit bucketed (a), run its source test against the target with that commit's own code taken
out of play: green means core already absorbed it - keep the test; red means re-bucket the commit.
Never widen an assertion, change an expected value without a cited reason, drop a test because it
is hard, or silence one with `@skip` / `pass`.

## Output format

`${CLAUDE_PLUGIN_ROOT}/skills/odoo-test-writing/references/output-format.md`

## Standalone-first fallback

OSM unreachable -> `${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md`: read the addon's
models and views and the existing tests from disk and write the file in place; emit copy-paste
blocks only when the repo itself is unreachable, labelled `grounded: local-source -
not OSM-indexed` or `grounded: ungrounded - OSM unavailable`. Ask (`NEEDS_CONTEXT`) only for a business decision
no source encodes.

### No instance

With no `INSTANCE_HANDLE` (authoring never waits for one -
`${CLAUDE_PLUGIN_ROOT}/snippets/instance-optional-completion.md`), write the tests and return
`status: NEEDS_NEXT` naming the pending tests at method level:
```
next:
  - skill: odoo-instance
    reason: the tests are written; provision an instance and hand its INSTANCE_HANDLE back so their baseline and break runs can execute - GATE_ROLE node-verify, never the pre-PR lint gate
    inputs: {operation: run-tests, GATE_ROLE: node-verify, series: "<series>", modules: ["<module under test>"], test_tags: "/<module>:<Class>.<method>[,...] - the pending tests only", mode: "<fresh|reuse - optional>"}
    confidence: 0.9
```
Fall back to `BLOCKED` only when provisioning is itself impossible. On an existing database a run
uses `-u <module>`, a fresh one `-i <module>`
(`${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md` § Test run on an existing database - `-i`
vs `-u`), with the instance's own interpreter (`${CLAUDE_PLUGIN_ROOT}/snippets/venv-resolution.md`).

## Continuation Contract

Append a block per `${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced /
next). `produced` = the test files you wrote; the status block carries one short line per behavior
test - the test, what you broke, how it failed, that you restored it - plus what was already
covered, what you adjusted and why, and any "no new test needed" decision with its reason.
