# Expected-Log Contract (a test run logs no WARNING and no ERROR)

A CI that grades a build by its log, Odoo's runbot among them, reports a build whose tests all
pass but whose log holds a WARNING as passed with warnings, and one whose log holds an ERROR as
failed. A test run is clean only when its log holds neither.

## The rule

A test that drives a code path which logs a WARNING or an ERROR wraps that log, in the way the
intent of the test decides:

- **Capture** when the log is the behaviour under test (a guard that logs and skips), so that
  removing the guard makes the test fail. Assert that the logger fired at that level, never the
  wording of the message (`${CLAUDE_PLUGIN_ROOT}/snippets/test-behavior-contract.md` § Never
  assert TRANSLATED or DISPLAY text (HARD RULE)):

      with self.assertLogs('odoo.addons.<module>.models.<file>', 'WARNING') as cm:
          order.with_user(self.salesman).action_sync()   # the guard logs, then skips the sync
      self.assertEqual(cm.records[0].levelname, 'WARNING')
      self.assertEqual(order.sync_state, 'skipped')

- **Mute** when the log is a side effect of the path and the test asserts something else (the
  exception type, the record left unchanged): `from odoo.tools import mute_logger`, then
  `@mute_logger('<logger>')` over a test whose whole body logs, `with mute_logger('<logger>'):`
  around the one operation that does. Name the exact logger, never a parent that hides other logs.

Either way the behavioural assertions stay. Wrap only a log the path really emits: find the
`_logger.warning` / `_logger.error` call on the path and its level at the target series (OSM or
the source), or read the line in a run's log. A constraint's `ValidationError` logs nothing, so
`assertLogs` around it fails on correct code.

A log the test did not mean to cause is never muted: the code or the test's data is wrong, and
that is what gets fixed.

## The proof

The run of the tests you wrote or changed ends `tests-passed` with no warning counted. Each
WARNING or ERROR line of the run's findings file is settled before you report: wrapped as above
when a test of yours causes it on purpose, fixed at its cause otherwise (a module that warns while
it loads - a model without an access rule, a view or a field definition core complains about - is
a defect of the module), then the run is repeated. A line that comes from code the change does
not touch goes to your caller with the line quoted.

A test that leaves an expected WARNING or ERROR unwrapped is a HIGH review finding.

## Per layer

| Layer | Trigger | Wrap with | Assert |
|---|---|---|---|
| Python server log | the path calls `_logger.warning` / `_logger.error` | `assertLogs` (the log is the behaviour) or `mute_logger` (a side effect) | the outcome (exception TYPE, state) and, when captured, `cm.records` at that level |
| SQL constraint | a database constraint raises `IntegrityError` at flush time | `with mute_logger('odoo.sql_db'), self.assertRaises(IntegrityError):` with `rec.flush_recordset([...])` inside the block | the `IntegrityError`; without the explicit flush Odoo may write after the block and the test passes whatever the constraint does |
| JS (per framework) | an error path or a console error in a JS test | the idiom of the suite's framework, below | the expected error is recorded, an uncaught one is prevented |

## JS framework split (resolve at runtime - never hardcode)

Resolve the target Odoo series per `${CLAUDE_PLUGIN_ROOT}/snippets/project-facts-resolution.md`;
an unresolved series is `NEEDS_CONTEXT`, never a guess. Then call
`js_test_inspect(module=..., odoo_version=...)` to confirm the module's framework before writing
any JS test code. Which series ship which framework, and that both can coexist in one series:
`${CLAUDE_PLUGIN_ROOT}/snippets/odoo-era-boundaries.md` row 2 - never map a series to a framework
from memory.

**QUnit suites:**

- Silence a console error: `patchWithCleanup(console, { error() {} });`, or `hushConsole(target);`
  on a subtree.
- For an uncaught promise rejection: handle `PromiseRejectionEvent` / `Event("error")` and
  assert `ev.defaultPrevented`.
- QUnit has no `expectErrors` API.

**Hoot suites:**

- Record an expected error: `expectErrors('message or pattern');` - Hoot fails the test when the
  error does not occur.
- `patchWithCleanup(console, ...)` is not the way to silence an expected error in Hoot.
