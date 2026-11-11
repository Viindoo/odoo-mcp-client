# Odoo Build Facts - per series (SSOT)

What a build, a test run and a lint gate depend on by series: the facts the odoo-local tools apply
and an instance agent reports. API and view changes by series are in
`${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md`.

## Build facts the odoo-local tools apply

`instance_build` and `instance_serve` apply three build facts themselves, on every series: the
server-wide modules (`--load`), the languages (`--load-language`) and the series' demo flag. Never
put any of them in `extra_args` and never compose them by hand. The judgement left to you is which
`demo` and which `languages` to ask for, and what to do with the warnings `job_wait` reports.

- **Server-wide modules.** The tools load the series' core default (read from the lease's Odoo
  checkout) plus the catalog row's `server_wide_modules`, fixed on the lease when it is acquired:
  the default for every build. Another set for one task: `server_wide` exclude/include on each
  build and serve of that DB. A `job_wait` server-wide warning: `server_wide.include` it for
  the task, or follow its catalog remedy (`/odoo-ai-agents:odoo-setup refresh`), then release the
  lease and acquire a new one before trusting it. Never answer it by installing the module with `-i`.
- **Languages.** Pass the target codes as `languages`; the tool adds `en_US` to every build.
  `job_wait` reports `languages_loaded` and `languages_failed`, proven from the build log; a code in
  `languages_failed` is not loaded, whatever you asked for.
- **Demo.** Pass `demo` (`on` | `off`) on every `init` build by its PURPOSE, per the table below,
  and never on a test build (the tool applies the series default; `job_wait` reports it). Demo data
  never leaves a database; `INSTANCE_HANDLE.demo` is the DATABASE's, from any lease.

| Series default | Series |
|---|---|
| Demo data loaded by default | v8-v18 |
| NO demo data by default | v19+ |

### Demo data by build PURPOSE

Resolve the purpose from the dispatch brief's own signals, never from the operation name alone.

| Build purpose - the signal that decides it | `demo` on a series whose default loads demo | `demo` on a series whose default loads none |
|---|---|---|
| Automation test run that gates code - ANY `--test-enable` build, at BOTH `GATE_ROLE: node-verify` and `GATE_ROLE: pre-pr-lint-gate` | series default (omit `demo`): demo, as its own CI runs; an `init` a test build reuses passes `on` | series default (omit `demo`): none; an `init` a test build reuses passes `off`; `on` and a demo database (`TEST_DB_HAS_DEMO`) are refused |
| Translation export / `.pot` / `.po` work | `on` | `on` |
| Documentation capture (`CONTEXT: doc`), demo recording, UI review | `on` | `on` |
| Acceptance live-UI sweep | `on` | `on` |
| Demo-load verification - proving a module's own `demo/` data still loads. INSTALL ONLY: this build NEVER carries `--test-enable` | `on` | `on` |
| Anything whose OUTPUT does not depend on demo records - a debug reproduction, an ensure-up, a language activation, a bare create, a no-code-change smoke run | `on` - the series default | `off` - the series default |

A demo-carrying build and a code-gating test build are two SEPARATE builds on two leases: loading
demo proves the `demo/` XML installs; the suite proves the code works. Where the default loads no
demo, never test on a database holding demo (a handle whose `demo` is `true`, an acceptance or
documentation instance): test on a fresh lease.

> **A v19+ automation-test build carries NO demo data, and the test suite must not want any.** Demo
> records are absent there, so a test that reads one fails. Every durable test authored for a v19+
> target - Python `TransactionCase` / `HttpCase`, Python tour, JS tour - MUST create its own records
> in `setUpClass` / `setUp` and MUST NOT reference a demo record by xmlid or by name. This holds even
> when the test was authored while driving a demo-carrying acceptance instance: the file it leaves
> behind runs demo-less in the gate.

### Test run on an existing database - `-i` vs `-u`

| Database state | Test build (`instance_build` op `test`) | Series |
|---|---|---|
| Scope modules NOT installed yet (a new database) | `test_mode` `fresh` (`-i`) | every series |
| Scope modules ALREADY installed | `test_mode` `reuse` (`-u`) for a re-run of the scope's own tests. A suite that gates builds a new database (`fresh`): an install-time test of an updated module runs before the modules loaded after it are back in the registry, so a required column one of them added makes its inserts fail spuriously | every series; from v19 `-i` skips an installed module and runs none of its tests |

## Framework-validation test classes (named in `--test-tags` beside module tags)

**Only two classes are listed here, and the list stays that size on purpose.** A class earns a row
ONLY if all three hold: it is a FRAMEWORK class (lives in `base`/`hr`, not in the module under
test), it enforces a convention THIS plugin teaches, and a module-scoped `--test-tags /<module>` run
SKIPS it so nothing else would catch the violation. Odoo ships hundreds of thousands of tests;
this is not a mirror of them, and a class that fails any of the three does not belong.

| Convention it enforces | Class, per series | Tag spec to pass |
|---|---|---|
| Always-invisible view field needs an explanatory XML comment | `TestInvisibleField` (in `base`), v18+ only - absent below; rule: `${CLAUDE_PLUGIN_ROOT}/skills/_shared/coding_guidelines/<series>/xml.md` § Always-invisible field carries a comment | `/base:TestInvisibleField` |
| Custom `hr.employee` field needs `groups="hr.group_hr_user"` | in `hr`: `TestSelfAccessProfile` v13-v18, RENAMED to `TestSelfAccessPreferences` at v19 | `/hr:TestSelfAccessProfile` or `/hr:TestSelfAccessPreferences` per series |

> **The `hr` class was RENAMED, not removed.** Its file and its `test_employee_fields_groups` method
> both still exist at v19 under the new class name, so the enforcement is live there - dropping the
> tag because the old name no longer resolves silently stops the check. (That method itself only
> exists from v18; below that the class is present but enforces the convention through other tests.)

> **The class separator in a tag spec is a COLON.** The grammar is `[-][tag][/module][:class][.method]`
> (`odoo/tests/tag_selector.py`, `filter_spec_re`), so `base.TestInvisibleField` does NOT name a
> class - it parses as tag `base` plus METHOD `TestInvisibleField`, matches no test method that
> exists, and selects NOTHING. Copy the tag-spec column; never re-derive it from a dotted name.

> **A tag that matches nothing is a SILENT no-op, not an error** - whether the spec is misspelled or
> the series ships a different name. The run exits 0 having tested nothing. So CONFIRM the class name
> against the target build's own `addons/<module>/tests/` before tagging it: this table has been
> wrong twice, once on a bound and once by reading "the old name is absent" as "the thing is gone".
> An UNTAGGED run needs none of this - it already includes every framework class - so prefer it
> wherever the cost of running the full closure is acceptable.

## Backend lint-class gate - core module per series

| Module | Source | Present at |
|---|---|---|
| `test_lint` | Odoo core (`odoo/addons/test_lint`) | v10+ ONLY - absent below that, where a `/test_lint` tag silently matches nothing |

Selection of every lint-class module a build tags, and the false-green trap:
`${CLAUDE_PLUGIN_ROOT}/snippets/lint-gate-modules.md`.
