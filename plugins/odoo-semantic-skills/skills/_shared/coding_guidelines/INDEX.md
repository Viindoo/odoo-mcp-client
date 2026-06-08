# Odoo Coding Guidelines - Version Index

Per-version, self-contained extraction of the official Odoo coding guidelines
(`contributing/development/coding_guidelines.rst`). Every Odoo engineering agent
(coding, review, debugging - backend and frontend) MUST consult these BEFORE writing code.

## How agents use this directory (read-before-write)

1. **Resolve the Odoo version first.** Determine the target Odoo series from `.odoo-ai/context.md`
   (`odoo_version`), the discovered `__manifest__.py`, or what the user stated. This is a
   precondition, not optional - if the version cannot be resolved, stop and resolve it first.
2. **Open the matching version index:** `<version>/INDEX.md` (e.g. `17.0/INDEX.md`).
3. **Read the topic files relevant to the task BEFORE writing any code.** The version index has a
   "By task" map that points to the right files. Write code that conforms to those rules on the
   first pass - do not write first and fix against a checklist afterwards.

There is no cross-version inheritance here: each `<version>/` directory contains the COMPLETE rule
set for that series. Always read the directory for the version you are working on - never assume one
version's conventions carry to another.

## Available versions

| Version | Directory | Notes |
|---|---|---|
| Odoo 14.0 | `14.0/` | Baseline for v14+ guidelines |
| Odoo 15.0 | `15.0/` | OWL 2 becomes the default frontend framework |
| Odoo 16.0 | `16.0/` | Asset bundles in `__manifest__.py`; SCSS/CSS section greatly expanded; `Command` import |
| Odoo 17.0 | `17.0/` | `tree` view type; CSS custom properties are DOM-contextual only |
| Odoo 18.0 | `18.0/` | `_ = self.env._` translation; `<tree>` renamed to `<list>` |
| Odoo 19.0 | `19.0/` | `<list>` view type; current series |

For Odoo versions earlier than 14.0 (v8-v13), the official coding-guidelines document does not exist;
use `14.0/` as the closest baseline and combine it with the era-specific API differences documented in
the backend coder agent (`_columns`/`cr, uid` for v8-v9, `@api.multi` for v10-v12).

## Each version directory contains

- `INDEX.md` - the version's table of contents + "By task" lookup
- `module-structure.md` - directory layout, file naming, manifest
- `python.md` - imports, idioms, ORM programming, translations
- `naming.md` - model/class/variable/field/method naming
- `model-ordering.md` - attribute order inside a Model class
- `xml.md` - record/field format, XML-ID naming, view inheritance
- `javascript.md` - JS/OWL conventions
- `scss.md` - SCSS/CSS conventions

## Mechanical gate (safety net, not a substitute)

A subset of these rules that can be checked mechanically (deprecated decorators, `_()` misuse,
`cr.commit()`, `<tree>` on v18+) is enforced by `scripts/verify-guidelines.sh` against changed
`.py`/`.xml` files. The gate catches only the mechanical subset; the semantic rules (attribute
ordering, naming intent, structure) are the responsibility of the agent reading these files
up front.
