<!-- SSOT snippet. Orthogonal to test-first-contract.md: that one governs WHEN (red before green);
     this one governs HOW a test is ARRANGED so it actually exercises the behavior. Referenced (not
     copy-pasted) by odoo-test-writing, odoo-coder, odoo-frontend-coder, odoo-code-reviewer (rejects
     shortcut tests), odoo-qa-suite, odoo-solution-architect, odoo-backend-debugger, and the
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
