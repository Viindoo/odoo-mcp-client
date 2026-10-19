> Source: official Odoo 18.0 coding guidelines - https://raw.githubusercontent.com/odoo/documentation/18.0/content/contributing/development/coding_guidelines.rst

# Odoo 18.0 Coding Guidelines - Index

This page introduces the Odoo Coding Guidelines. Those aim to improve the quality of Odoo Apps
code. Indeed proper code improves readability, eases maintenance, helps debugging, lowers
complexity and promotes reliability. These guidelines should be applied to every new module and to
all new development.

## How to use

Two warnings from the source govern when these guidelines apply to existing code:

- **Stable version:** When modifying existing files in a stable version the original file style
  strictly supersedes any other style guidelines. In other words please never modify existing files
  in order to apply these guidelines. It avoids disrupting the revision history of code lines. Diff
  should be kept minimal. For more details, see the pull request guide
  (https://odoo.com/submit-pr).
- **Master (development) version:** When modifying existing files in master apply those guidelines
  to existing code only for modified code or if most of the file is under revision. In other words
  modify existing files structure only if it is going under major changes. In that case first do a
  **move** commit then apply the changes related to the feature.

Each file below covers one topic area of the official Odoo 18.0 coding guidelines and starts with a
Source header. All rules come directly from the 18.0 RST source.

## Table of contents

1. **module-structure.md** - Directories, file naming, and the complete module tree.
2. **python.md** - PEP8 options, imports, idiomatics of programming, and programming in Odoo
   (context propagation, think extendable, never commit the transaction, translation method).
3. **security.md** - Security pitfalls: secure-coding rules - sudo, SQL injection, XSS/t-raw,
   escaping, safe_eval.
4. **naming.md** - Symbols and conventions: model names, classes, variables, fields, and method
   prefixes.
5. **model-ordering.md** - Order of attributes inside a Model, with a full class example.
6. **xml.md** - Record/field format, XML IDs and naming, inheriting XML, and the `<data>` tag.
7. **javascript.md** - Static files organization and Javascript coding guidelines.
8. **scss.md** - CSS and SCSS: syntax and formatting, properties order, naming conventions,
   variables (SCSS, scoped, mixins/functions, CSS), and the `:root` pseudo-class.
9. **tests.md** - Test classes, Form, HttpCase and tours, the JS test runner, and demo data in tests, for this series only.

## By file type

Before the first line of a file type, read every file its row names. The row is the gate: a
`VERSION RULES APPLIED` block cites the file and the section heading it took each rule from, and
a cited heading that does not exist in the file is a review finding. Snippet path prefix:
`${CLAUDE_PLUGIN_ROOT}/snippets/`.

| File you will write | Read first |
|---|---|
| `.py` model, field, ORM method, compute, constraint, wizard | python.md, naming.md, model-ordering.md; security.md when the code uses `sudo`, raw SQL or access checks; `${CLAUDE_PLUGIN_ROOT}/snippets/field-presence-resolution.md`, `${CLAUDE_PLUGIN_ROOT}/snippets/orm-performance.md`, `${CLAUDE_PLUGIN_ROOT}/snippets/stored-write-survival.md`, `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md §model-API`, `${CLAUDE_PLUGIN_ROOT}/snippets/python-naming-conventions.md` |
| `.xml` view, inherited view, data, report, action, menu | xml.md, `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md §XML views` |
| `.xml` security record (`ir.rule`, groups) and `ir.model.access.csv` | security.md, xml.md, `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md §ACL`, `${CLAUDE_PLUGIN_ROOT}/snippets/access-groups-conventions.md` |
| `__manifest__.py`, a new module tree | module-structure.md, `${CLAUDE_PLUGIN_ROOT}/snippets/new-module-manifest.md` |
| A `_()` call or a `.po` entry | python.md (translation section), `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md §gettext placeholders` |
| `.js`, an OWL template, an asset bundle entry | javascript.md, module-structure.md, `../javascript-coding-guidelines.md` |
| `.scss` | scss.md |
| A test (`tests/*.py`, `static/tests/*`, a tour) | tests.md, plus the row of the language the test is written in |
| Any comment or docstring, in every row above | `${CLAUDE_PLUGIN_ROOT}/snippets/code-comment-contract.md` (governs over the "document your code" line in python.md) |
