# Odoo Testing - how to test, per target version (method, not hardcoded facts)

> **A method reference, not a version fact-sheet.** Test flags, tag syntax and JS frameworks
> changed across Odoo versions. Treat the era boundaries below as *illustrative* and
> **confirm for the target version via OSM** before relying on them: `set_active_version`
> then `cli_help("server", "--test-tags", odoo_version='<version>')` (and friends). The running instance is the final
> arbiter - a test command that the version doesn't support will error.
>
> Consumed by: `odoo-qa-suite`, `odoo-deploy-checklist`, `wave` (when running tests), the
> upgrade command chain.
>
> **Programmatic front door:** the `odoo-instance` skill and the `odoo-instance-ops` agent are the
> high-level interface for build/drop/init/update/test operations on a local instance. Persistent
> logs live under `${ODOO_AI_HOME:-$HOME/.odoo-ai}/logs/<db>-<UTC-ts>.log`.

## Core test invocation (verify flags via `cli_help` for the target)

```
odoo-bin -d <DB> -i <module> --test-enable --test-tags /<module> --stop-after-init --log-level=test
```

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
> `python3 scripts/lib/allocator.py acquire --mode ephemeral --ports 0` (reserves a unique DB name;
> the `-i <module>` run below performs Odoo create-on-init to build the DB; a `--stop-after-init`
> run binds no port), use `$ALLOC_DB_NAME` / `$ALLOC_PYTHON`, then `allocator.py release $ALLOC_TOKEN`
> (drops through Odoo via `scripts/lib/odoo_db.py`).
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
| (omitted) | `--log-level=test` | default - test-progress + the `N failed, N error` summary |
| `warn` | `--log-level=warn` | WARNING+ only (quietest; still shows FAIL/ERROR) |
| `info` | `--log-level=info` | per-test progress + module-load lines |
| `debug` | `--log-level=debug` | full framework debug trace |
| `sql` | `--log-handler=odoo.sql_db:DEBUG` | dump executed SQL (query-count / N+1 probing) |

When `log_mode` is omitted the runner keeps `--log-level=test` (it does NOT default to `warn`); pass
a row above only to override. `sql` raises only the SQL logger, not the whole framework. **Confirm the exact log-level values and
the sql-debug handler for the target version via `cli_help`** (`--log-level` / `--log-handler`) -
the handler name above is illustrative. A run's WARNINGs are findings to fix (not noise) - the
warnings-are-findings contract lives in `${CLAUDE_PLUGIN_ROOT}/snippets/test-execution-handoff.md`.

## Quality gate / lint tests - always include (the part that slips to CI)

A normal `--test-tags /<module>` run does **not** include lint tests - which is why lint failures
pass locally then fail CI. **Always append the lint module tag(s)** when running the suite.
Requires a running instance + DB.

Odoo ships its own lint test module that runs Odoo's custom AST checkers (`sql_injection`,
`gettext`, `unlink_override`) plus manifest, eslint, pofile, and `__init__` consistency checks.
This is **not** the third-party `pylint-odoo` package - it is Odoo's own module and is what Runbot runs.

| Series | Tag(s) to append to `--test-tags` | Source |
|---|---|---|
| v10-v13 | `/test_pylint` | Odoo CE (module renamed to `test_lint` at v13/saas-15 boundary) |
| v14-v15 | `/test_lint` | Odoo CE only |
| v16+ | `/test_lint,/test_pylint` | CE `test_lint` + Viindoo `tvtmaaddons` custom `test_pylint` |

```bash
# v14-v15: test_lint only
odoo-bin -d <DB> -u <module> --test-enable \
  --test-tags '/<module>,/test_lint' --stop-after-init --log-level=test

# v16+ Viindoo: also add /test_pylint (tvtmaaddons)
odoo-bin -d <DB> -u <module> --test-enable \
  --test-tags '/<module>,/test_lint,/test_pylint' --stop-after-init --log-level=test
```

**Confirm the exact tag and module name for the target version via OSM before running:**
`set_active_version(<version>)` then `check_module_exists("test_lint", odoo_version='<version>')` and
`cli_help("server", "--test-tags", odoo_version='<version>')`. The table above is illustrative -
never assume without checking.

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

## Expected-log handling per layer (deny-path / guard tests)

Tests that exercise a deny-path, guard, or constraint that legitimately emits WARNING/ERROR must capture or silence that log - an unwrapped test leaks expected noise into CI output and misses asserting the guard fired. The rule applies across all three layers (Python server log, SQL constraint, and JS-OWL with the era-correct idiom). Full rule per layer: `${CLAUDE_PLUGIN_ROOT}/snippets/test-expected-log-contract.md`.

## Verify-via-OSM checklist before writing a test command

1. `set_active_version(<target>)`.
2. `cli_help("server", "--test-tags", odoo_version='<version>')` and `cli_help("server", "--test-enable", odoo_version='<version>')` - confirm the
   flags exist and their exact semantics for this version.
3. `find_examples(query="<feature> test", odoo_version='<version>')` - reuse the real test pattern from the indexed code.
4. Pick the JS test framework by inspecting the version's web assets, not from memory.
5. State the chosen invocation + why before running.
