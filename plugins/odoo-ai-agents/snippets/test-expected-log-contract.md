<!-- SSOT snippet. Orthogonal to test-behavior-contract.md (governs HOW a test is arranged)
     and test-first-contract.md (governs WHEN - red before green); this one governs how a
     test that legitimately emits a server/console WARNING or ERROR captures or mutes that
     log so it never leaks into CI/Runbot output. Referenced (not copy-pasted) by
     odoo-test-writing, odoo-coder, odoo-frontend-coder, odoo-code-reviewer, odoo-debug, and
     odoo-backend-debugger, plus docs/reference/ODOO-TESTING.md. Edit here only; consumers
     point at ${CLAUDE_PLUGIN_ROOT}/snippets/test-expected-log-contract.md. -->

# Expected-Log Contract (capture or mute the log a guard legitimately emits)

A deny-path test, guard test, or constraint test that does NOT capture or mute the expected
WARNING/ERROR fails the contract in two ways at once: (1) it leaks expected noise into CI and
Runbot logs, inflating signal-to-noise so real failures are harder to spot; (2) it misses
asserting that the guard ACTUALLY fired - the test may pass even if the guard is silently
deleted. Wrap the log; assert the guard.

## The rule, stated once

Every test that drives a code path which legitimately emits a WARNING or ERROR MUST do one of:

- **Capture** it with `self.assertLogs(logger, level)` and assert `cm.output` confirms the
  guard fired (preferred for deny-path / guard / ACL tests - the WARNING IS the observable
  behavior).
- **Mute** it with `@mute_logger('odoo.<logger>')` or `with mute_logger(...)` when the log is
  incidental noise already asserted elsewhere and re-asserting it here would duplicate the
  behavioral check.

An unwrapped negative test that emits expected noise is incomplete. A reviewer MUST flag it
as a HIGH finding.

## assertLogs vs mute_logger (the decision rule)

**Prefer `self.assertLogs(logger, level)` when:**

- The test is a deny-path, guard, or ACL test: the emitted WARNING IS the signal that the
  guard fired. Assert on `cm.output` that the message is present.
- Example - ACL deny emitting a WARNING before raising `AccessError`:

      with self.assertLogs('odoo.addons.base.models.ir_rule', 'WARNING') as cm:
          with self.assertRaises(AccessError):
              record.with_user(self.restricted_user).action_confirm()
      self.assertTrue(any('access_rule_name' in line for line in cm.output))

- The guard behavior must be asserted, not merely suppressed. If the guard is removed or
  changed, `cm.output` assertions fail - that is the desired red-before-green property.

**Reserve `@mute_logger` / `with mute_logger(...)` when:**

- The log is incidental noise from a sub-call whose behavior is already asserted by a
  dedicated test elsewhere; the current test only needs to prove its own behavior is correct.
- Example - suppressing `odoo.sql_db` constraint noise during a uniqueness check already
  covered by a dedicated constraint test.

Do NOT use `mute_logger` as a shortcut to silence a warning you do not understand. Investigate
first; suppress only when the guard is confirmed tested elsewhere.

## 3-layer decision matrix

| Layer | Trigger | Wrap with | Assert |
|---|---|---|---|
| Python server log | guard / ACL deny logs WARNING or ERROR before raising | `with self.assertLogs('<logger>', 'WARNING') as cm:` (preferred) or `@mute_logger('<logger>')` | `assertRaises(AccessError/ValidationError/...)` + `cm.output` contains the guard message |
| SQL constraint | DB-level constraint raises `IntegrityError` at flush time | `with mute_logger('odoo.sql_db'), self.assertRaises(IntegrityError):` then call `rec.flush_recordset([...])` inside the block | the `IntegrityError` is raised; `flush_recordset` forces flush-time constraint fire (do NOT rely on implicit flush at end of test) |
| JS-OWL (era-split) | OWL error path / console ERROR in a JS deny-path test | resolve era at runtime - see section below | uncaught error is prevented / expected error is recorded by the framework |

For the SQL constraint row: `flush_recordset` is mandatory because Odoo may batch the SQL
write; without an explicit flush the constraint does not fire inside the `assertRaises` block
and the test gives a false green.

## JS-OWL era split (resolve at runtime - never hardcode)

Resolve the target Odoo series from `.odoo-ai/context.md` (`odoo_version` field); if that file
is absent or the field is empty, fall back to the first segment of the module `__manifest__.py`
`version` field (e.g. `17.0.x.y.z` -> `17`); if both are absent, default to `v17` and state
the assumption. Then call `js_test_inspect(module=..., odoo_version=...)` to confirm the
per-module framework before emitting any JS test code. The framework mix varies by module and
version; do NOT hardcode "v17 = Hoot" or any equivalent mapping.

**v17 and earlier - QUnit:**

- Silence a console ERROR: `patchWithCleanup(console, { error() {} });`
- Silence a console ERROR on a subtree: `hushConsole(target);`
- For an uncaught promise rejection: handle `PromiseRejectionEvent` / `Event("error")` and
  assert `ev.defaultPrevented`.
- QUnit has NO `expectErrors` API - do not write `expectErrors(...)` in a QUnit test.

**v18 and later - Hoot:**

- Record an expected error: `expectErrors('message or pattern');`
- Hoot asserts that the expected error actually occurred; the test fails if it does not fire,
  preserving the red-before-green property.
- Do NOT use `patchWithCleanup(console, ...)` as the primary suppress mechanism in Hoot -
  use `expectErrors` so the assertion is explicit.

**QUnit does NOT have `expectErrors`. Hoot does NOT use `patchWithCleanup(console, ...)` as
the primary idiom. Do not conflate the two eras.**

## mute_logger import

    from odoo.tools import mute_logger

`mute_logger` is available as a decorator (`@mute_logger('odoo.sql_db')`) or as a context
manager (`with mute_logger('odoo.sql_db'):`) - both forms are valid. The decorator form is
convenient when the entire test body should suppress the logger; the context-manager form is
preferred when suppression is scoped to a specific sub-operation within the test.
