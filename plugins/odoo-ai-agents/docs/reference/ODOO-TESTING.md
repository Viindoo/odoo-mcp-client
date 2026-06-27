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
