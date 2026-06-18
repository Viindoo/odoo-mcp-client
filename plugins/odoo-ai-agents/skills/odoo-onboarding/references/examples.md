# odoo-onboarding - Worked Examples

## Example 1 - Fresh custom distribution repo

User prompt: "I just cloned this Odoo repo - set up context for me"

Skill flow:
1. Pre-flight: no `.odoo-ai/context.md` → continue.
2. Detect root: 12 manifests found under `./` → root inferred as `.`.
3. Version probe: server returns [8.0..19.0]; user picks 17.0.
4. Profile probe: server returns [odoo_17, viindoo_17, ...]; default = viindoo_17 (because `viin_*` prefix detected in Step 4 will run after - for now, ask user).
5. Module discovery: 12 modules; 10 have `viin_` prefix, 2 are `custom_*`.
6. Conventions: prefix=`viin_`, field=`snake_case`, branch=`feature/<slug>`.
7. Pins set: version=17.0, profile=standard_viindoo_17.
8. Write `.odoo-ai/context.md` + add `.gitignore` line.
9. Verify + ask notes.

Output:
```
✓ Onboarding complete

**Project context** saved to `.odoo-ai/context.md`:
- Odoo version: 17.0
- Profile: viindoo_17
- Modules detected: 12 (top: viin_sale_advance, viin_account_vat, viin_purchase_advance)
- Module prefix: viin_
- Lint: ruff line-length=120, JS=web/tooling

`.gitignore` updated to exclude `.odoo-ai/`.

Suggest next: Run `odoo-customization-inventory` to list all 12 modules and assess their business purpose.
```

## Example 2 - Pure Odoo CE repo (no Viindoo)

User prompt: "first time using Odoo for this project - it's a pure Odoo 16 CE deployment"

Skill flow:
1. Pre-flight: no context → continue.
2. Detect root: 3 manifests under `./addons/` → root = `.`.
3. Version probe: user picks 16.0.
4. Profile probe: user picks `odoo_16` (default for pure-Odoo).
5. Module discovery: 3 modules, all prefixed `custom_*`.
6. Conventions: prefix=`custom_`, field=`snake_case`.
7. Pins set: version=16.0, profile=odoo_16.
8. Write context + gitignore.
9. Output suggest-next: default (no special signal in prompt).

## Example 3 - Refresh existing context

User prompt: "initialize Odoo context" (but `.odoo-ai/context.md` already exists, last_updated yesterday)

Skill flow:
1. Pre-flight: context exists, last_updated 2026-05-27 (1 day ago, fresh) → output: "Context already exists (updated 2026-05-27). Refresh? (yes/no)". User says "no" → end.

If user said "yes": continue with full flow, but preserve `## Notes` from existing file.

## Example 4 - Not an Odoo project

User prompt: "set up Odoo for this project" (working dir is a React app, no `__manifest__.py`)

Skill flow:
1. Pre-flight: no context.
2. Detect root: 0 manifests found.
3. Output:

```
No `__manifest__.py` found in working dir or 3 levels down. Is this an Odoo repo?

If yes: provide the project root path (e.g. `/home/user/projects/erp-customer-a`).
If no: this skill is not applicable - try `/odoo-semantic-mcp:connect` to set up the MCP server connection instead (a different scope from project root).
```

Wait for user.
