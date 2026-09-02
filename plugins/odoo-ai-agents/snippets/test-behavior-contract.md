<!-- SSOT snippet. Orthogonal to test-first-contract.md: that one governs WHEN (red before green);
     this one governs HOW a test is ARRANGED so it actually exercises the behavior. Referenced (not
     copy-pasted) by odoo-test-writing + odoo-test-writer (the authoring skill + its context-isolated
     agent), odoo-backend-coder / odoo-frontend-coder (reading the handed-in test), odoo-code-reviewer
     (rejects shortcut tests), odoo-qa-suite, odoo-solution-architect, odoo-backend-debugger, and the
     odoo-coding dispatch brief. Edit here only; consumers point at
     ${CLAUDE_PLUGIN_ROOT}/snippets/test-behavior-contract.md. -->

# Test-Behavior Contract (drive the real workflow, never the shortcut)

A test that injects the final state directly - `create({'state': 'approved'})`, a raw INSERT of an
already-validated record, a field set straight to its end value - tests nothing. It skips the
state-transition, constraint, onchange, and access-control code that the real workflow runs, so it
stays green even when that code is broken. A shortcut test is an unguarded behavior: a
change-detector that snapshots the schema, not a guard on the rule (a test must fail when the behavior breaks - never snapshot current code).

## Core rules

1. **Drive the real action method.** To reach a state, CALL the transition that reaches it -
   `action_confirm()`, `action_validate()`, `button_validate()`, `action_approve()`,
   `action_post()` - never seed the terminal `state`/flag directly. The test must traverse the same
   ORM hooks, constraints, and `@api.depends` recomputes a user would.
2. **Use `Form()` for onchange-dependent setup.** When the value under test is produced by an
   `onchange` (price from a product, taxes from a fiscal position, a default from a partner), build
   the record through `odoo.tests.common.Form(self.env['<model>'])` so onchange fires - a bare
   `create({...})` bypasses onchange and the values are wrong/missing.
3. **`with_user()`, not `sudo()`, on the action under test.** To test access control, run the action
   as the real user (`record.with_user(self.portal_user).action_confirm()`) and assert it is allowed
   or raises `AccessError`. `sudo()` ESCALATES privileges - it is legitimate only for ARRANGE setup a
   privileged actor would do (seeding fixtures the test user cannot create), NEVER on the call whose
   permission you are asserting. A `sudo()` on the action under test silently passes a broken rule.
4. **Assert observable outcomes.** Assert the resulting `state`, the computed field value, the raised
   exception, the records created as a side effect - not that a private method was called or how many
   times `write` ran.

## Never assert TRANSLATED or DISPLAY text (HARD RULE)

Rule 4 says assert observable OUTCOMES; user-facing wording is not one. Labels, `string=`, `help=`,
`placeholder`, selection labels, exception message prose, menu / action / report names and every
`.po` `msgstr` are improved continuously by people who never see the test suite - so an assertion
pinned to that wording fails on an IMPROVEMENT, not on a defect, and its only cheap remedy is
editing the expectation, which is itself banned. A guard that fires on intended change is an
obstacle.

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
| a field's `string` / `help` | the field's existence, type, store/compute BEHAVIOR - or nothing |
| a menu / action name | the action's `res_model`, `xml_id`, or domain |
| "the term is translated" | nothing. This is not a test |

What IS assertable near i18n is the MECHANISM, never the wording: that a message is wrapped in
`_()`/`_lt()` at all, that a `msgstr`'s placeholder set matches its `msgid`, that a record resolves
under a given `lang` context. Those break; which words they render is a catalogue decision.

**A text LOCATOR is not a text ASSERTION.** A tour may have to click an element by its visible label
when no stable handle exists - that is addressing and stays allowed. Prefer `data-*` / an
`xml_id`-derived selector / a technical value, and never make the locator the thing under test.

**Deleting an EXISTING assertion of this kind is cleanup, not loosening** - the ban on weakening a
test protects guards, and this is not one; say in the report which assertion went and why. The
opposite move stays banned: RELAXING it to keep it green (widening a regex, comparing
case-insensitively, asserting a substring) keeps the obstacle and hides it. Remove it or leave it;
never sand it down.

A `.po`/`.pot` `msgstr` edit needs no RED test at all
(`${CLAUDE_PLUGIN_ROOT}/snippets/test-exemption-contract.md`, category `translation-text`); what
validates a catalog instead - adjudicated diff-review, placeholder integrity, an Odoo `-u` reload -
is `${CLAUDE_PLUGIN_ROOT}/skills/odoo-i18n/references/i18n-recipe.md` § Validation. Translation
correctness is gated there, never by the test suite.

## Odoo BAD vs GOOD (approval workflow)

BAD - seeds the end state, so a broken `action_approve` (missing guard, wrong access rule, skipped
onchange) is never caught:

    leave = self.env['hr.leave'].create({
        'employee_id': self.emp.id, 'holiday_status_id': self.type.id,
        'state': 'validate',  # SHORTCUT: jumps straight to approved
    })
    self.assertEqual(leave.state, 'validate')  # tests the assignment, not the workflow

GOOD - builds via Form() so onchange computes dates/allocation, then drives the real action as the
real approver and asserts the observable outcome:

    with Form(self.env['hr.leave'].with_user(self.employee_user)) as f:
        f.holiday_status_id = self.type      # onchange fires: number_of_days, etc.
        f.request_date_from = date(2026, 6, 1)
        f.request_date_to = date(2026, 6, 3)
    leave = f.save()
    leave.with_user(self.manager_user).action_approve()   # real transition, real approver
    self.assertEqual(leave.state, 'validate')             # the workflow actually ran
    # negative: a non-manager must be refused
    with self.assertRaises(AccessError):
        leave.with_user(self.employee_user).action_approve()

(For `sale.order`: build the order + lines via `Form()`, call `action_confirm()`, then assert
`state == 'sale'` and that downstream records - e.g. delivery/invoice - were produced; never
`create({'state': 'sale'})`.)

## The rule, stated once

Shortcut data == unguarded behavior == change-detector. If a test would still pass with the
transition/constraint/onchange/access logic deleted, it is not protecting the behavior - rewrite it
to drive the workflow.
