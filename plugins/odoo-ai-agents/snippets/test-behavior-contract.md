<!-- SSOT snippet. HOW a single test is written so it guards the business behavior. Whether a node
     owes a test, and the break-check that proves it can fail:
     ${CLAUDE_PLUGIN_ROOT}/snippets/test-sensitivity-contract.md. Edit here only; consumers cite
     ${CLAUDE_PLUGIN_ROOT}/snippets/test-behavior-contract.md § <heading>. -->

# Test-Behavior Contract (protect the business outcome, drive the real workflow)

Short rules, each with an example. Where a case falls outside them, keep their intent: the test
must fail when the business rule breaks and keep passing through every correct change.

## Search existing tests first

Before writing, look for tests that already exercise the behavior (OSM `tests_covering` /
`find_test_examples`, or the module's `tests/`). Fully covered -> write nothing new and report the
covering tests. Partly covered -> add a test method to that class. Example: a new cap on
`discount` whose save path `TestSaleOrderLine` already drives gets one new method there.

## Read the framework first

Ground the base class, helpers and test framework of the target series before you write (OSM
`test_base_classes`, `js_test_inspect`, `find_test_examples`), never from memory. Example: confirm
the series ships `Form` before you rely on it; where it does not, drive the flow with a tour or
HttpCase.

## Protect the outcome, never the implementation

Assert observable business results: the return value, the resulting state, the records produced,
the exception TYPE. Never assert the HOW - private calls, call counts, intermediate variables, SQL,
the ORM cache. Example: assert `order.state == 'sale'` after confirming, not that `_check_cap` was
called once.

## Drive the real workflow

Reach a state through its real transition - `action_confirm()`, `action_post()`,
`button_validate()` - never by seeding the end `state` in `create()`. Run the action under test as
the real user with `with_user()`; `sudo()` is for arrange data only, because on the action under test
it silently passes a broken access rule. Example: BAD vs GOOD below.

## Simulate the user with Form

When the rule is triggered by data a user enters in a form view (a constraint on save, an onchange,
a default, readonly/required), arrange AND act through `Form`:

1. Read the form view first (OSM `model_inspect` views, or the view XML in the worktree) for the
   fields the acting user can set.
2. Set only those fields, in the user's order, so onchanges fire as they would; pass `view=` when the
   behavior lives in a specific view. Never force a field the user cannot set.
3. Refused value: `save()` inside `assertRaises(<BusinessError>)`, then assert the stored values are
   unchanged. Accepted value: plain `save()`, then assert the stored outcome.
4. A button = call that button's method on the saved record as the acting user.

ORM `create` / `write` is only for arrange data the user does not enter in that flow; setting a
user-entered field through the ORM bypasses the rule under test.

## Never freeze the present

A test must keep passing when someone ADDS a field, view, method, module or record. Never assert a
count of files / records / fields / views / menus (unless the count IS the business result), that
something EXISTS or what it is NAMED, an arch string, or `__manifest__.py` contents. Example: not
`assertIn('discount_cap', Model._fields)` - assert what the cap does.

## Never assert TRANSLATED or DISPLAY text (HARD RULE)

Labels, `string=`, `help=`, `placeholder`, selection labels, exception message prose, menu / action /
report names and every `.po` `msgstr` are improved by people who never see the test suite, so a test
pinned to that wording fails on an improvement. Never author it, and reject it on review: a field's
`string` / `help` / `placeholder` or a selection LABEL; a menu / action / report / group NAME; the
WORDING of an exception (`str(e) == "..."`, `assertRaisesRegex` over prose); a rendered UI string or
a `.po`/`.pot` `msgstr`; a translation count or coverage.

Assert the stable thing underneath:

| Instead of the text | Assert |
|---|---|
| the exception's wording | the exception TYPE and the record's values / state unchanged |
| a selection's label | its technical VALUE (`state == 'sale'`) |
| a field's `string` / `help` | the behavior the field drives - or nothing |
| a menu / action name | what triggering the action produces - or nothing |
| "the term is translated" | nothing - this is not a test |

The i18n MECHANISM stays assertable: a message wrapped in `_()`, a `msgstr` keeping its `msgid`'s
placeholders, a record resolving under a given `lang` context.

**A text LOCATOR is not a text ASSERTION.** A tour may click an element by its visible label when no
stable handle exists; prefer a `data-*` or technical selector, and never make the locator the thing
under test.

Deleting an existing assertion of this kind is cleanup, not loosening - say which one went and why.
RELAXING it to keep it green (widening a regex, a case-insensitive compare, a substring) stays
banned. A `.po` catalog is validated by
`${CLAUDE_PLUGIN_ROOT}/skills/odoo-i18n/references/i18n-recipe.md` § Validation, never by the suite.

## Keep the test simple

Arrange-Act-Assert, one business rule per test, readable top-down by a junior. Expected values are
literals from the business rule - never computed in the test, no loops or helpers that build
expectations, no re-implemented rule. Register each test file in `tests/__init__.py`; never import
`tests` from the module's own `__init__.py` (Odoo's loader imports it). Example: the GOOD tests below.

## Odoo BAD vs GOOD (confirm workflow)

BAD - seeds the end state, so a broken `action_confirm` is never caught:

    order = self.env['sale.order'].create({'partner_id': self.partner.id, 'state': 'sale'})
    self.assertEqual(order.state, 'sale')  # tests the assignment, not the workflow

GOOD - the salesperson fills the form, then clicks the button; one rule per test (rule: a line
discount above 20% is refused):

    def test_order_within_discount_cap_confirms(self):
        f = Form(self.env['sale.order'].with_user(self.salesman))
        f.partner_id = self.partner
        with f.order_line.new() as line:
            line.product_id = self.product
            line.discount = 15
        order = f.save()
        order.action_confirm()
        self.assertEqual(order.state, 'sale')

    def test_discount_above_cap_is_refused_on_save(self):
        f = Form(self.draft_order.with_user(self.salesman))   # setUp: discount 10
        with f.order_line.edit(0) as line:
            line.discount = 25
        with self.assertRaises(ValidationError):
            f.save()
        self.assertEqual(self.draft_order.order_line.discount, 10)
