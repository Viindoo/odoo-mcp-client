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
- `security.md` - secure-coding pitfalls (sudo, SQL injection, XSS/t-raw, safe_eval, domain injection)
- `naming.md` - model/class/variable/field/method naming
- `model-ordering.md` - attribute order inside a Model class
- `xml.md` - record/field format, XML-ID naming, view inheritance
- `javascript.md` - version-specific JS/OWL stub (static file layout, class-case rule); points to the canonical detail file below
- `scss.md` - SCSS/CSS conventions

One file lives at the root of `coding_guidelines/` and is shared across all versions:

- `javascript-coding-guidelines.md` - canonical, version-agnostic JS/OWL reference incl. ESLint/Prettier tooling config and full linting rules. Each `<v>/javascript.md` stub points here for detail beyond the version-specific excerpt.

## Mechanical gate (safety net, not a substitute)

A subset of these rules that can be checked mechanically is enforced by two pre-push scripts
against changed files. `scripts/verify-backend.sh` runs `pylint --load-plugins=pylint_odoo`
over changed `.py` files using a version-matched, isolated toolchain (deprecated decorators,
`cr.commit()`, ORM misuse, and other pylint-odoo codes). `scripts/verify-frontend.sh` runs a
three-tier check over changed `.js`/`.xml`/`.scss` files: JS lint/format via repo-pinned
`eslint -c _eslintrc.json` (Tier 1 - the same oracle Runbot uses), static OWL/SCSS pattern scan
via `scripts/rules/owl-pitfalls.txt` (Tier 2), and an optional runtime smoke check (Tier 3).
The JS Tier-1 gate is tri-state: `RESULT: PASS` (exit 0) means eslint ran clean; `RESULT: FAIL`
(exit 1) means eslint found errors; `RESULT: CANNOT-VERIFY` (exit 2) means the repo-pinned
toolchain could not be resolved - exit 2 is NOT a pass, and the agent MUST NOT declare done on
it. Both gates catch only the mechanical subset; the semantic rules (attribute ordering, naming
intent, structure, secure-coding patterns) are the responsibility of the agent reading these
files up front.

## Viindoo additions beyond upstream RST

The per-version `<version>/python.md` files are verbatim extractions of the official Odoo RST
source - they are not edited to carry Viindoo-specific rules. Rules that go beyond upstream RST
live here (in this root index) or in the shared snippets directory, and are kept in a single
SSOT to avoid 6-way duplication.

**Field / method presence resolution (don't probe - resolve):** Do NOT probe whether an Odoo
field or method exists on a recordset at runtime (`hasattr(record, 'field')`,
`getattr(record, 'field', default)`, `try: record.field except AttributeError`). The ORM schema
is statically knowable from the module dependency graph; a runtime probe masks one of three real
defects (lookup-gap, wrong ORM path, or missing `depends`) instead of surfacing it. Resolve
presence via OSM before writing or accepting the access.
Full rule, 3-way classification, worked examples, and JS/OWL analogue:
`${CLAUDE_PLUGIN_ROOT}/snippets/field-presence-resolution.md`

**Module rename conventions (profile-gated - Viindoo Standard/Internal only):** When a module is
renamed (technical name / directory changes) under a Viindoo Standard or Internal profile
(OSM-detected; profiles of the form `standard_viindoo_<series>` or `viindoo_internal_<series>`),
the renamed module's `__manifest__.py` must carry `'old_technical_name': '<previous name>'` so
Viindoo internal tooling can map the old technical name to the new one. This key is ignored by the
Odoo core loader and is NOT an OCA convention - do not apply it outside Viindoo distributions.
Full rule: `${CLAUDE_PLUGIN_ROOT}/snippets/module-rename.md`
