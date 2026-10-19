<!-- SSOT snippet. Python variable naming rules for Odoo.
     Edit here only; consumers cross-ref, never restate.
     Consumers are DERIVED, never listed here - re-derive with `grep -rl "python-naming-conventions.md" plugins/odoo-ai-agents/`. -->

# Python Variable Naming Conventions

**Never use `l`, `O`, or `i` as single-character variable names.** pylint fires
`C0104 ambiguous-variable-name` on them, which is a hard block in Odoo CI
(the `/test_lint` gate enforces it). It applies regardless of distribution, profile, or
Odoo version.

**In review:** any occurrence is a **MED** finding (pylint C0104 blocks CI).
