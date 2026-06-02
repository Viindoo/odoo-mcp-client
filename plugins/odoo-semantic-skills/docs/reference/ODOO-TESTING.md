# Odoo Testing — how to test, per target version (method, not hardcoded facts)

> **A method reference, not a version fact-sheet.** Test flags, tag syntax and JS frameworks
> changed across Odoo versions. Treat the era boundaries below as *illustrative* and
> **confirm for the target version via OSM** before relying on them: `set_active_version`
> then `cli_help("server", "--test-tags")` (and friends). The running instance is the final
> arbiter — a test command that the version doesn't support will error.
>
> Consumed by: `odoo-qa-suite`, `odoo-deploy-checklist`, `wave` (when running tests), the
> upgrade command chain.

## Core test invocation (verify flags via `cli_help` for the target)

```
odoo-bin -d <DB> -i <module> --test-enable --test-tags /<module> --stop-after-init --log-level=test
```

- `--test-enable` — enable running tests at `-i`/`-u`.
- `--stop-after-init` — exit after load+test (CI-friendly).
- `--test-tags` — **selection syntax (newer versions only — confirm availability):**
  `[-][tag][/module][:Class][.method]`. `-` excludes; an omitted tag in include-mode
  defaults to `standard`. Every test class is implicitly `standard` + `at_install` until
  changed via `@tagged`. `at_install` runs right after the module installs/updates;
  `post_install` runs after **all** modules load (`@tagged('post_install', '-at_install')`).
  Example: `--test-tags :TestClass.test_func,/my_module,external`.
- `--test-file` — run a specific test file (broadly available; confirm).

> Older versions may lack `--test-tags` entirely (then use `--test-enable` alone). **Always
> confirm with `cli_help` for the target version** rather than assuming the syntax exists.

## Test classes (Python)

- `TransactionCase` / `SingleTransactionCase` — ORM-level, rolled back per test/class.
- `Form` — simulates a UI form (onchange/defaults) at recordset level (newer versions).
- `HttpCase` — browser/controller tests, tours.
- `@tagged(...)` — set/clear tags (`at_install`, `post_install`, custom). Confirm the
  decorator + `Form` exist for the target version via OSM (`lookup_core_api` / `find_examples`).

## JS / OWL tests (framework depends on era — verify)

- Older era ships **QUnit** (`web/static/lib/qunit`), run via `HttpCase` tour or the in-browser
  test runner; tagged like `/web.test_js`.
- Newer era introduces **Hoot** (`web/static/lib/hoot`); QUnit may still ship during the
  transition. **Detect which framework a given version/module uses** (check the module's JS
  test assets / `module_inspect`), do not assume.

## Verify-via-OSM checklist before writing a test command

1. `set_active_version(<target>)`.
2. `cli_help("server", "--test-tags")` and `cli_help("server", "--test-enable")` — confirm the
   flags exist and their exact semantics for this version.
3. `find_examples(query="<feature> test")` — reuse the real test pattern from the indexed code.
4. Pick the JS test framework by inspecting the version's web assets, not from memory.
5. State the chosen invocation + why before running.
