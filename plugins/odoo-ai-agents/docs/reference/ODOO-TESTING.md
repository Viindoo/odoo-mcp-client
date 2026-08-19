# Odoo Testing - how to test, per target version (method, not hardcoded facts)

> **A method reference, not a version fact-sheet.** Test flags, tag syntax and JS frameworks
> changed across Odoo versions. Treat the era boundaries below as *illustrative* and
> **confirm for the target version via OSM** before relying on them: `set_active_version`
> then `cli_help("server", "--test-tags", odoo_version='<version>')` (and friends). The running instance is the final
> arbiter - a test command that the version doesn't support will error.
>
> Consumed by: `odoo-qa-suite`, `odoo-deploy-checklist`, `run-harness`
> (when running tests), the upgrade command chain.
>
> **Programmatic front door:** the `odoo-instance` skill and the `odoo-instance-ops` agent are the
> high-level interface for build/drop/init/update/test operations on a local instance. Persistent
> logs live under `${ODOO_AI_HOME:-$HOME/.odoo-ai}/logs/<db>-<UTC-ts>.log`.

## Core test invocation (verify flags via `cli_help` for the target)

```
[ -z "${ODOO_AI_LIMIT_MEMORY_HARD-4294967296}" ] || [ "${ODOO_AI_LIMIT_MEMORY_HARD-4294967296}" = "0" ] || ulimit -Sv "$(( ${ODOO_AI_LIMIT_MEMORY_HARD-4294967296} / 1024 ))" 2>/dev/null || true
odoo-bin -d <DB> -i <module> --test-enable --test-tags /<module> --stop-after-init --log-level=info \
  --limit-memory-hard=${ODOO_AI_LIMIT_MEMORY_HARD:-4294967296}
```

Memory-cap policy (default, override, uncap escape hatch): `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-bin-resource-limits.md`.

**Fresh DB vs re-run - `-i` vs `-u`.** The example above is the **fresh-DB** case: `-i` installs
the not-yet-installed module and runs its `at_install` tests in one pass. To RE-RUN the suite on a
DB where the module is **already installed**, use `-u <module> --test-enable` instead - `-i` on an
already-installed module is a no-op, so the install-time tests silently do **not** re-run. So: a
fresh DB / not-yet-installed module uses `-i ... --test-enable` (init + test in one pass); an
already-installed DB uses `-u ... --test-enable`. Confirm the exact flag semantics via `cli_help`
for the target version. (This is the runner's `mode` = `fresh` vs `reuse`; see
`${CLAUDE_PLUGIN_ROOT}/snippets/test-execution-handoff.md`.)

> **Under concurrency, `<DB>` must be an ISOLATED database, never the shared declared one** - a
> parallel agent or another Claude Code session may be testing against it. Acquire a throwaway:
> `python3 scripts/lib/allocator.py acquire --mode ephemeral --ports 0 --run-id <id>` (reserves a
> unique DB name under that run's ownership; the `-i <module>` run below performs Odoo
> create-on-init to build the DB; a `--stop-after-init` run binds no port), use `$ALLOC_DB_NAME` /
> `$ALLOC_PYTHON` (and `$ALLOC_DB_PORT` when non-empty), then
> `allocator.py release $ALLOC_TOKEN --run-id <id>` (drops through Odoo via `scripts/lib/odoo_db.py`).
> See `snippets/instance-resolution.md` § Allocate and `docs/reference/INSTANCE-ALLOCATION.md`.

- `--test-enable` - enable running tests at `-i`/`-u`.
- `--stop-after-init` - exit after load+test (CI-friendly).
- `--test-tags` - **selection syntax (newer versions only - confirm availability):**
  `[-][tag][/module][:Class][.method]`. `-` excludes; an omitted tag in include-mode
  defaults to `standard`. Every test class is implicitly `standard` + `at_install` until
  changed via `@tagged`. `at_install` runs right after the module installs/updates;
  `post_install` runs after **all** modules load (`@tagged('post_install', '-at_install')`).
  Example: `--test-tags :TestClass.test_func,/my_module,external`.
- `--test-file` - run a specific test file (broadly available; confirm).

> Older versions may lack `--test-tags` entirely (then use `--test-enable` alone). **Always
> confirm with `cli_help` for the target version** rather than assuming the syntax exists.

> **`--test-tags` only FILTERS - it never ADDS framework tests.** Narrowing tags to just
> `/<cluster>` SKIPS framework `post_install` validation classes (e.g. Odoo `base` view-arch
> tests, hr self-access tests) that are not tagged with your module - so a tag-restricted run can
> stay green while a framework check the change actually broke never runs. To catch them, let the
> suite run the full `post_install` set (do not narrow the tag to the cluster) or name the
> framework class explicitly in `--test-tags`. The class names here are illustrative - confirm via
> OSM / `cli_help`.

## Log verbosity modes (the runner's `log_mode` param)

The `odoo-instance` run-tests runner exposes a `log_mode` param that maps to Odoo log flags. Pick
the lowest verbosity that still surfaces the findings you need - higher levels flood the caller's
context.

| `log_mode` | Odoo flag(s) | Use when |
|---|---|---|
| (omitted) | `--log-level=info` | default - per-test progress plus the summary line that says a PASSING run actually ran |
| `warn` | (none) | REFUSED, exit 2 - a PASSING run emits NO summary on any series v8-v19, so every green run would parse as `TEST_RESULT=inconclusive` |
| `debug` | `--log-level=debug` | full framework debug trace |
| `sql` | `--log-handler=odoo.sql_db:DEBUG` | dump executed SQL (query-count / N+1 probing) |

When `log_mode` is omitted the runner keeps the build default (`--log-level=info`); pass a row
above only to override. `sql` raises only the SQL logger, not the whole framework. **Confirm the
exact log-level values and the sql-debug handler for the target version via `cli_help`** (`--log-level` / `--log-handler`) - the handler name above is illustrative. A run's WARNINGs are findings to fix (not noise) - the warnings-are-findings contract lives in `${CLAUDE_PLUGIN_ROOT}/snippets/test-execution-handoff.md`.

## Quality gate / lint tests - always include (the part that slips to CI)

A normal `--test-tags /<module>` run does **not** include lint tests - which is why lint failures
pass locally then fail CI. **Always append the lint module tag(s)** when running the suite.
Requires a running instance + DB.

Odoo ships its own lint test module that runs Odoo's custom AST checkers (`sql_injection`,
`gettext`, `unlink_override`) plus manifest, eslint, pofile, and `__init__` consistency checks.
This is **not** the third-party `pylint-odoo` package - it is Odoo's own module and is what Runbot
runs. (The `gettext` checker's actual rule - named placeholders required for multi-arg `_()`,
lint-enforced from v18 - is `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md §gettext
placeholders`; this section only catalogs the checker.)

**Illustrative only - the runtime probe is authoritative (see D4).** The table below is a rough
era guide, kept for orientation; it is superseded by the `check_module_exists` probe below whenever
they disagree. OSM shows `test_lint` present as early as v10 (not "renamed from `test_pylint` at
v13" as the table implies) - never assume the table over a live probe.

| Series | Tag(s) to append to `--test-tags` | Source |
|---|---|---|
| v10-v13 | `/test_pylint` | Odoo CE (module renamed to `test_lint` at v13/saas-15 boundary) |
| v14-v15 | `/test_lint` | Odoo CE only |
| v16+ | `/test_lint,/test_pylint` | CE `test_lint` + Viindoo `tvtmaaddons` custom `test_pylint` |

```bash
[ -z "${ODOO_AI_LIMIT_MEMORY_HARD-4294967296}" ] || [ "${ODOO_AI_LIMIT_MEMORY_HARD-4294967296}" = "0" ] || ulimit -Sv "$(( ${ODOO_AI_LIMIT_MEMORY_HARD-4294967296} / 1024 ))" 2>/dev/null || true

# v14-v15: test_lint only
odoo-bin -d <DB> -u <module> --test-enable \
  --test-tags '/<module>,/test_lint' --stop-after-init --log-level=info \
  --limit-memory-hard=${ODOO_AI_LIMIT_MEMORY_HARD:-4294967296}

# v16+ Viindoo: also add /test_pylint (tvtmaaddons)
odoo-bin -d <DB> -u <module> --test-enable \
  --test-tags '/<module>,/test_lint,/test_pylint' --stop-after-init --log-level=info \
  --limit-memory-hard=${ODOO_AI_LIMIT_MEMORY_HARD:-4294967296}
```

Memory-cap policy: `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-bin-resource-limits.md`.

**Confirm the exact tag and module name for the target version via OSM before running:**
`set_active_version(<version>)` then `check_module_exists("test_lint", odoo_version='<version>')` and
`cli_help("server", "--test-tags", odoo_version='<version>')`. The table above is illustrative -
never assume without checking.

### Install the lint modules (not just tag them)

Appending `/test_lint`/`/test_pylint` to `--test-tags` only SELECTS those tests IF the module is
already installed in the target DB - it does not install it. For a **test-run build** (any build
whose purpose is running `--test-enable`: `run-tests`, or a coder/reviewer inline lint-gate run),
each lint module must be INSTALLED, not merely tagged:

1. For each of `test_lint` and `test_pylint`, call `check_module_exists(name='<module>',
   odoo_version='<version>', profile_name='<active profile>')`.
2. For every module that is Indexed = Yes, UNION it into the `-i`/`-u` INSTALL list for that build
   (exactly as `en_US` is unioned into the language activation set - see `agents/odoo-instance-ops.md`
   "en_US - always loaded on every build (HARD RULE)"), AND append its tag to `--test-tags`.
3. The install set and the tag set MUST come from the SAME probe. Never tag a module that was not
   also installed - its tests will not load, and the run will report a false-clean pass.

The operational HARD RULE unioning these into the install set lives in `agents/odoo-instance-ops.md`
"Lint modules - installed for test-run builds (HARD RULE)" - this section is the test-invocation
method; that section is the build-time enforcement point.

> `test_lint` (Odoo CE) is distinct from the third-party `pylint-odoo` package
> (`pip install pylint-odoo` / `pylint --load-plugins=pylint_odoo`). They are separate tools with
> separate checker sets. The authoritative gate is Odoo's own module, not the third-party package.
>
> OSM's `lint_check` is a fast V0.5 hybrid matcher - useful for sql-injection hints as an early
> signal, but it is **not** a substitute for running the lint test module (it does not reproduce
> the full Odoo AST checker set). See `docs/reference/odoo-code-quality.md` for the JS lint gate.

## Test classes (Python)

- `TransactionCase` / `SingleTransactionCase` - ORM-level, rolled back per test/class.
- `Form` - simulates a UI form (onchange/defaults) at recordset level (newer versions).
- `HttpCase` - browser/controller tests, tours.
- `@tagged(...)` - set/clear tags (`at_install`, `post_install`, custom). Confirm the
  decorator + `Form` exist for the target version via OSM (`lookup_core_api` / `find_examples`).

## JS / OWL tests (framework depends on era - verify)

- Older era ships **QUnit** (`web/static/lib/qunit`), run via `HttpCase` tour or the in-browser
  test runner; tagged like `/web.test_js`.
- Newer era introduces **Hoot** (`web/static/lib/hoot`); QUnit may still ship during the
  transition. **Detect which framework a given version/module uses** (check the module's JS
  test assets / `module_inspect`), do not assume.
- **Reading a JS suite's RESULT is a separate problem from choosing its framework.** The two
  frameworks publish different markers and count different units (QUnit reports failed
  assertions, Hoot reports failed tests), and one build drives several browser suites, each
  under its own logger scope. The counting mechanism is implemented once, in the `_JS_*` marker
  SSOT and `_js_fail_counts` of `${CLAUDE_PLUGIN_ROOT}/scripts/setup-steps/55-instance-ops.sh`,
  and surfaced as the `JS_RUNS`/`JS_SCOPE`/`JS_FAILED_REPORTED`/`JS_FAILED_TESTS` fields the
  `run-tests` operation emits. Read those fields; do not hand-roll a grep over a run log.

## Expected-log handling per layer (deny-path / guard tests)

Tests that exercise a deny-path, guard, or constraint that legitimately emits WARNING/ERROR must capture or silence that log - an unwrapped test leaks expected noise into CI output and misses asserting the guard fired. The rule applies across all three layers (Python server log, SQL constraint, and JS-OWL with the era-correct idiom). Full rule per layer: `${CLAUDE_PLUGIN_ROOT}/snippets/test-expected-log-contract.md`.

## Verify-via-OSM checklist before writing a test command

1. `set_active_version(<target>)`.
2. `cli_help("server", "--test-tags", odoo_version='<version>')` and `cli_help("server", "--test-enable", odoo_version='<version>')` - confirm the
   flags exist and their exact semantics for this version.
3. `find_examples(query="<feature> test", odoo_version='<version>')` - reuse the real test pattern from the indexed code.
4. Pick the JS test framework by inspecting the version's web assets, not from memory.
5. State the chosen invocation + why before running.
