<!-- SSOT snippet. How a test that legitimately emits a server/console WARNING or ERROR captures
     or mutes that log so it never leaks into CI/Runbot output. Orthogonal to
     test-behavior-contract.md and test-sensitivity-contract.md. Edit here only; consumers point at
     ${CLAUDE_PLUGIN_ROOT}/snippets/test-expected-log-contract.md. -->

# Expected-Log Contract (capture or mute the log a guard legitimately emits)

A test whose code path legitimately emits a WARNING/ERROR and does NOT capture or mute it leaks
expected noise into CI and Runbot logs, so real failures are harder to spot. Wrap that log; assert
the behavior.

## The rule, stated once

Every test that drives a code path which ACTUALLY emits a WARNING or ERROR does one of:

- **Capture** it with `self.assertLogs(logger, level)` and assert that the logger fired at that
  level - `len(cm.records)`, `cm.records[0].levelname` - never the message wording (it is display
  text: `${CLAUDE_PLUGIN_ROOT}/snippets/test-behavior-contract.md` § Never assert TRANSLATED or
  DISPLAY text (HARD RULE)). Use it when the log IS part of the observable behavior (a guard that
  logs and skips).
- **Mute** it with `@mute_logger('odoo.<logger>')` or `with mute_logger(...)` when the log is
  incidental noise of a sub-call whose behavior is asserted elsewhere.

Either way, the behavioral assertions stay: the exception TYPE and the record's field values /
state unchanged. Use `assertLogs` only when the path really logs - never "by default": a
constraint `ValidationError` raised on save emits no WARNING, so `assertLogs(..., 'WARNING')`
around it fails on correct code. Before wrapping, find the `_logger.warning` / `_logger.error` call
on the path and its level in the target series (OSM or the source), or read it in a run's log.

An unwrapped test that emits expected WARNING/ERROR noise is incomplete; a reviewer flags it HIGH.

## assertLogs vs mute_logger (the decision rule)

**Prefer `self.assertLogs(logger, level)` when** the WARNING is the signal that the guard fired,
so removing the guard must make the test fail:

      with self.assertLogs('odoo.addons.<module>.models.<file>', 'WARNING') as cm:
          order.with_user(self.salesman).action_sync()   # the guard logs, then skips the sync
      self.assertEqual(cm.records[0].levelname, 'WARNING')
      self.assertEqual(order.sync_state, 'skipped')

**Reserve `@mute_logger` / `with mute_logger(...)` when** the log is incidental noise from a
sub-call already asserted by a dedicated test elsewhere - e.g. `odoo.sql_db` noise during a
uniqueness check covered by its own constraint test.

Do NOT use `mute_logger` to silence a warning you do not understand. Investigate first; suppress
only when the guard is confirmed tested elsewhere.

## 3-layer decision matrix

| Layer | Trigger | Wrap with | Assert |
|---|---|---|---|
| Python server log | the path calls `_logger.warning` / `_logger.error` | `with self.assertLogs('<logger>', 'WARNING') as cm:` (log is the behavior) or `@mute_logger('<logger>')` (noise) | the outcome (exception TYPE / state) + `cm.records` at that level from that logger - never the wording |
| SQL constraint | DB-level constraint raises `IntegrityError` at flush time | `with mute_logger('odoo.sql_db'), self.assertRaises(IntegrityError):` then call `rec.flush_recordset([...])` inside the block | the `IntegrityError` is raised; `flush_recordset` forces flush-time constraint fire (do NOT rely on implicit flush at end of test) |
| JS-OWL (per framework) | OWL error path / console ERROR in a JS deny-path test | resolve the framework at runtime - see section below | uncaught error is prevented / expected error is recorded by the framework |

For the SQL constraint row: `flush_recordset` is mandatory because Odoo may batch the SQL
write; without an explicit flush the constraint does not fire inside the `assertRaises` block
and the test gives a false green.

## JS-OWL framework split (resolve at runtime - never hardcode)

Resolve the target Odoo series per `${CLAUDE_PLUGIN_ROOT}/snippets/project-facts-resolution.md`.
Never default to a series, and never take the series off a SHORT manifest `version` - that ladder's
rung 3 already applies the only valid test. An unresolved series is `NEEDS_CONTEXT`, never a guess.
Then call `js_test_inspect(module=..., odoo_version=...)` to confirm the per-module framework before
emitting any JS test code. Which series ship which framework, and that both can coexist in one
series: `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-era-boundaries.md` row 2 - never map a series to a
framework from memory.

**QUnit suites:**

- Silence a console ERROR: `patchWithCleanup(console, { error() {} });`
- Silence a console ERROR on a subtree: `hushConsole(target);`
- For an uncaught promise rejection: handle `PromiseRejectionEvent` / `Event("error")` and
  assert `ev.defaultPrevented`.
- QUnit has NO `expectErrors` API - do not write `expectErrors(...)` in a QUnit test.

**Hoot suites:**

- Record an expected error: `expectErrors('message or pattern');`
- Hoot asserts that the expected error actually occurred; the test fails if it does not fire.
- Do NOT use `patchWithCleanup(console, ...)` as the primary suppress mechanism in Hoot -
  use `expectErrors` so the assertion is explicit.

## mute_logger import

    from odoo.tools import mute_logger

Use it as a decorator when the whole test body is noisy, as a context manager when only one
sub-operation is.
