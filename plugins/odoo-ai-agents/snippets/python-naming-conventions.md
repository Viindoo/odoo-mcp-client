<!-- SSOT snippet. Python variable naming rules for Odoo.
     Consumers: odoo-coder.md, odoo-frontend-coder.md, odoo-code-reviewer.md,
       odoo-backend-debugger.md, odoo-ui-debugger.md,
       skills/odoo-qa-suite/SKILL.md, skills/odoo-test-writing/SKILL.md,
       coding_guidelines/<v>/INDEX.md (By-task "Naming" row, all versions).
     Edit here only; consumers cross-ref, never restate. -->

# Python Variable Naming Conventions

## Universal (all distributions; pylint C0104-enforced)

**Never use `l`, `O`, or `i` as single-character variable names.** pylint fires
`C0104 ambiguous-variable-name` on them, which is a hard block in Odoo CI
(`verify-backend.sh` reproduces it). This is a universal Python/pylint rule - applies
regardless of distribution, profile, or Odoo version.

**In review:** any occurrence is a **MED** finding (pylint C0104 blocks CI).

## Viindoo Standard/Internal (profile-gated)

> **PROFILE GATE:** Apply the rules below ONLY when BOTH conditions hold:
>
> 1. OSM (`odoo-semantic`) is reachable.
> 2. The active profile resolves to a Viindoo Standard or Viindoo Internal distribution -
>    profiles of the form `standard_viindoo_<series>` or `viindoo_internal_<series>`.
>    Check `.odoo-ai/context.md` (`viindoo_profile`), or via OSM `profile_inspect` /
>    `list_available_profiles`.
>
> Do NOT apply these rules for Odoo CE/EE upstream or any other non-Viindoo
> distribution.

**Rule B - Use meaningful names, avoid arbitrary single-letter abbreviations.**
`for k, v in ...`, `x`, `y` (outside mathematical contexts) are careless shortcuts.
Choose names that reveal intent: `for field_name, field_val in ...`.

**Rule C - Record iteration over `self` MUST use `r`.**
When iterating over a model's own recordset, write `for r in self:` - not `rec`, not
`record`, not any other name.

```python
# Correct (Rule C)
for r in self:
    r.total = r.qty * r.price_unit

# Wrong - do NOT write
for rec in self:   # banned Viindoo-internal
    rec.total = ...
```

**In review (Viindoo profile only):** Rule B and Rule C violations are **MED** findings.
