<!-- SSOT snippet. HOW a single test is written so it guards the business behavior. Whether a node
     owes a test, and the break-check that proves it can fail:
     ${CLAUDE_PLUGIN_ROOT}/snippets/test-sensitivity-contract.md. Edit here only; consumers cite
     ${CLAUDE_PLUGIN_ROOT}/snippets/test-behavior-contract.md § <heading>. -->

# Test-Behavior Contract (protect the business outcome, drive the real workflow)

## Protect the outcome, never the implementation

Assert observable business results: the return value, the resulting state, the records produced,
the exception TYPE. Many algorithms give the same result, so never assert the HOW: private calls,
call counts, intermediate variables, SQL, the ORM cache. If a test would still pass with the rule
deleted, or would fail on a correct rewrite, it guards nothing - rewrite it.

## Drive the real workflow

1. **Call the real action method.** Reach a state through its transition - `action_confirm()`,
   `action_post()`, `button_validate()` - never by seeding the terminal `state`/flag in `create()`
   or a raw INSERT. The test must traverse the same ORM hooks, constraints and recomputes a user
   would.
2. **`with_user()`, not `sudo()`, on the action under test.** Run it as the real user and assert it
   is allowed or raises `AccessError`. `sudo()` is for ARRANGE setup only (fixtures the test user
   cannot create); on the action under test it silently passes a broken rule.
3. **No seeded end state.** A shortcut record skips the transition, constraint, onchange and access
   code the workflow runs, so the test stays green while that code is broken.

## Simulate the user with Form

Test any behavior a user reaches through a form view with Odoo's `Form` helper: set only the fields
the user can set on THAT view, in the order the user sets them, let onchange fire, `save()`. `Form`
enforces the view's readonly/invisible/required, so never force a field the user cannot set through
`create`/`write`/`Form` workarounds to make the test pass. Pass `view=` when the behavior lives in a
specific view. A button = call that button's method on the saved record as the acting user
(`with_user()`). Confirm the target series ships `Form`
(`test_base_classes(name='Form', odoo_version='<series>')`); where it does not, drive the flow with a
tour / HttpCase.

## Never freeze the present

A test must keep passing when someone ADDS a field, view, method, module or record. Never assert:

- a count of files, records, fields, methods, views or menus - unless the count IS the business
  result;
- that a field / view / method / xml-id / menu EXISTS, or what it is NAMED;
- an arch string;
- `__manifest__.py` contents (version, depends, data list, assets keys) - Odoo core validates
  manifests; they are never test subjects.

## Never assert TRANSLATED or DISPLAY text (HARD RULE)

Labels, `string=`, `help=`, `placeholder`, selection labels, exception message prose, menu / action /
report names and every `.po` `msgstr` are improved continuously by people who never see the test
suite - so an assertion pinned to that wording fails on an IMPROVEMENT, not on a defect, and its
only cheap remedy is editing the expectation, which is itself banned.

**Never author, and REJECT on review:** a field's `string` / `help` / `placeholder` or a selection
LABEL; a menu / action / report / group NAME; the WORDING of an exception (`str(e) == "..."`,
`assertRaisesRegex` over prose); a rendered UI string, a `.po`/`.pot` `msgstr`, or "this term is
translated thus"; an untranslated-entry COUNT or "translation coverage"; any test whose failure
would be fixed by editing a `.po`.

**Assert the stable thing underneath - there always is one:**

| Instead of the text | Assert |
|---|---|
| the exception's wording | the exception TYPE (`ValidationError` / `UserError` / `AccessError`) and the state that did NOT change |
| a selection's label | its technical VALUE (`state == 'sale'`) |
| a field's `string` / `help` | the behavior the field drives - or nothing |
| a menu / action name | what triggering the action produces - or nothing |
| "the term is translated" | nothing. This is not a test |

What IS assertable near i18n is the MECHANISM, never the wording: that a message is wrapped in
`_()`/`_lt()` at all, that a `msgstr`'s placeholder set matches its `msgid`, that a record resolves
under a given `lang` context.

**A text LOCATOR is not a text ASSERTION.** A tour may click an element by its visible label when no
stable handle exists - that is addressing and stays allowed. Prefer `data-*` / an `xml_id`-derived
selector / a technical value, and never make the locator the thing under test.

**Deleting an EXISTING assertion of this kind is cleanup, not loosening** - say in the report which
assertion went and why. RELAXING it to keep it green (widening a regex, comparing
case-insensitively, asserting a substring) stays banned. Remove it or leave it; never sand it down.

A `.po`/`.pot` `msgstr` edit owes no test (`${CLAUDE_PLUGIN_ROOT}/snippets/test-sensitivity-contract.md`
§ No test leg); a catalog is validated by
`${CLAUDE_PLUGIN_ROOT}/skills/odoo-i18n/references/i18n-recipe.md` § Validation, never by the test
suite.

## Keep the test simple

Arrange-Act-Assert; one business rule per test. Expected values are literals taken from the business
rule (a number, a state value) - never computed in the test. No loops, comprehensions or helpers
that build expectations, no re-implementing the rule, no clever fixtures. A junior reads it top-down
and sees the rule; if a test needs its own test, rewrite it.

## Odoo BAD vs GOOD (approval workflow)

BAD - seeds the end state, so a broken `action_approve` (missing guard, wrong access rule, skipped
onchange) is never caught:

    leave = self.env['hr.leave'].create({
        'employee_id': self.emp.id, 'holiday_status_id': self.type.id,
        'state': 'validate',  # SHORTCUT: jumps straight to approved
    })
    self.assertEqual(leave.state, 'validate')  # tests the assignment, not the workflow

GOOD - the employee fills the form as the user would, the manager clicks the button:

    with Form(self.env['hr.leave'].with_user(self.employee_user)) as f:
        f.holiday_status_id = self.type          # onchange fires
        f.request_date_from = date(2026, 6, 1)
        f.request_date_to = date(2026, 6, 3)
    leave = f.save()
    leave.with_user(self.manager_user).action_approve()   # the button, as the approver
    self.assertEqual(leave.state, 'validate')
    with self.assertRaises(AccessError):                  # a non-manager is refused
        leave.with_user(self.employee_user).action_approve()
