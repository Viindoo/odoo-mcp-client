> Source: official Odoo 17.0 coding guidelines - https://raw.githubusercontent.com/odoo/documentation/17.0/content/contributing/development/coding_guidelines.rst

# Odoo 17.0 Coding Guidelines - Index

## Version warnings (from RST source)

**When modifying existing files in a stable version:** the original file style strictly supersedes
any other style guidelines. Never modify existing files in order to apply these guidelines - it
avoids disrupting the revision history of code lines. Keep diffs minimal. See the
[pull request guide](https://odoo.com/submit-pr).

**When modifying existing files in master (development version):** apply these guidelines to
existing code only for modified code or if most of the file is under revision. Modify existing
files structure only if it is going under major changes - in that case, first do a **move** commit
then apply the changes related to the feature.

## How to use

Each file in this directory is self-contained and covers one topic area of the official Odoo 17.0
coding guidelines. Read every file the "By file type" table names for the file type you are about to write. Cross-references between files
are noted where relevant. All rules come directly from the 17.0 RST source - nothing is invented
or borrowed from other versions.

## Files

- **module-structure.md** - Directory layout, file naming conventions, module naming/prefix rules,
  complete module tree example.
- **python.md** - Import ordering, Python idioms, ORM best practices (never commit, context
  propagation, think extendable). Includes the `_()` translation method with full examples.
- **security.md** - Security pitfalls: secure-coding rules - sudo, SQL injection, XSS/t-raw,
  escaping, safe_eval.
- **naming.md** - Model `_name` conventions, Python class naming, variable naming, field suffix
  rules (`_id`/`_ids`), method prefix conventions.
- **model-ordering.md** - Required attribute order within a Model class, with annotated example.
- **xml.md** - Record/field format rules, XML-ID naming patterns (view type is `tree` not `list`),
  view inherit `.inherit.` suffix, `<data noupdate>` usage.
- **javascript.md** - Static file organization, JS coding rules as specified in the 17.0 RST source.
- **scss.md** - Full SCSS/CSS section: syntax and formatting, properties order, naming conventions,
  SCSS variable convention (`$o-[root]-[element]-[property]-[modifier]`), scoped variables
  (`$-name`), mixins/functions, CSS custom properties with BEM convention, `:root` usage rules.
- **tests.md** - Test classes, Form, HttpCase and tours, the JS test runner, and demo data in tests, for this series only.

## By file type

Before the first line of a file type, read every file its row names. The row is the gate: a
`VERSION RULES APPLIED` block cites the file and the section heading it took each rule from, and
a cited heading that does not exist in the file is a review finding. Snippet path prefix:
`${CLAUDE_PLUGIN_ROOT}/snippets/`.

| File you will write | Read first |
|---|---|
| `.py` model, field, ORM method, compute, constraint, wizard | python.md, naming.md, model-ordering.md; security.md when the code uses `sudo`, raw SQL or access checks; `${CLAUDE_PLUGIN_ROOT}/snippets/field-presence-resolution.md`, `${CLAUDE_PLUGIN_ROOT}/snippets/orm-performance.md`, `${CLAUDE_PLUGIN_ROOT}/snippets/stored-write-survival.md`, `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md §model-API`, `${CLAUDE_PLUGIN_ROOT}/snippets/python-naming-conventions.md` (Viindoo profile) |
| `.xml` view, inherited view, data, report, action, menu | xml.md, `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md §XML views` |
| `.xml` security record (`ir.rule`, groups) and `ir.model.access.csv` | security.md, xml.md, `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md §ACL`, `${CLAUDE_PLUGIN_ROOT}/snippets/access-groups-conventions.md` |
| `__manifest__.py`, a new module tree | module-structure.md, `${CLAUDE_PLUGIN_ROOT}/snippets/new-module-manifest.md` |
| A `_()` call or a `.po` entry | python.md (translation section), `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md §gettext placeholders` |
| `.js`, an OWL template, an asset bundle entry | javascript.md, module-structure.md, `../javascript-coding-guidelines.md` |
| `.scss` | scss.md |
| A test (`tests/*.py`, `static/tests/*`, a tour) | tests.md, plus the row of the language the test is written in |
| Any comment or docstring, in every row above | `${CLAUDE_PLUGIN_ROOT}/snippets/code-comment-contract.md` (governs over the "document your code" line in python.md) |
