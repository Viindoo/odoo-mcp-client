# Python Variable Naming Conventions

**Never use `l`, `O`, or `i` as single-character variable names.** pylint fires
`C0104 ambiguous-variable-name` on them, which is a hard block in Odoo CI
(the `/test_lint` gate enforces it). It applies regardless of distribution, profile, or
Odoo version.

**In review:** any occurrence is a **MED** finding (pylint C0104 blocks CI).
