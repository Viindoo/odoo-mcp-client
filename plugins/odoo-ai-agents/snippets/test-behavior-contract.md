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

When the rule is triggered by data a user enters or changes in a form view - a constraint on save,
an onchange, a default, readonly/required - arrange AND act through `Form`:

1. **Ground the view first.** Read the model's form view (OSM `model_inspect` views, or the view XML
   in the worktree) for the fields the acting user can set, their order and their groups. Confirm
   the target series ships `Form` (`test_base_classes(name='Form', odoo_version='<series>')`);
   where it does not, drive the flow with a tour / HttpCase.
2. **Set only those fields on the `Form`, in the user's order**, so onchange fires as it would. Pass
   `view=` when the behavior lives in a specific view. `Form` enforces the view's
   readonly/invisible/required: never force a field the user cannot set through
   `create`/`write`/`Form` workarounds.
3. **Refused value:** `save()` inside `assertRaises(<BusinessError>)`, then assert the record's
   field values / state unchanged. **Accepted value:** plain `save()`, then assert the stored
   outcome.
4. **A button** = call that button's method on the saved record as the acting user (`with_user()`).

ORM `create`/`write` is only for ARRANGE data the user does not enter in that flow. A reviewer flags
any test that sets through the ORM a field the user enters in a form.

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
| the exception's wording | the exception TYPE (`ValidationError` / `UserError` / `AccessError`) and the record's field values / state unchanged |
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

Odoo's test loader imports `<module>.tests` itself: register each test file in `tests/__init__.py`,
and never add `from . import tests` to the module's own `__init__.py`.

## Odoo BAD vs GOOD (confirm workflow)

BAD - seeds the end state, so a broken `action_confirm` (missing guard, wrong access rule, skipped
onchange) is never caught:

    order = self.env['sale.order'].create({
        'partner_id': self.partner.id,
        'state': 'sale',  # SHORTCUT: jumps straight to confirmed
    })
    self.assertEqual(order.state, 'sale')  # tests the assignment, not the workflow

GOOD - the salesperson fills the form as the user would, then clicks the button; each rule gets its
own test (rule: a line discount above 20% is refused; the view shows `discount` only to the discount
group, which `setUp` grants the salesperson):

    def test_order_within_discount_cap_confirms(self):
        f = Form(self.env['sale.order'].with_user(self.salesman))
        f.partner_id = self.partner                     # onchange fires
        with f.order_line.new() as line:
            line.product_id = self.product
            line.discount = 15
        order = f.save()
        order.action_confirm()                          # the button, as the salesperson
        self.assertEqual(order.state, 'sale')

    def test_discount_above_cap_is_refused_on_save(self):
        f = Form(self.draft_order.with_user(self.salesman))   # arranged in setUp, discount 10
        with f.order_line.edit(0) as line:
            line.discount = 25
        with self.assertRaises(ValidationError):
            f.save()
        self.assertEqual(self.draft_order.order_line.discount, 10)   # stored value unchanged
