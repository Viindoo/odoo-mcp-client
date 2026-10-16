> Source: official Odoo 14.0 coding guidelines - https://raw.githubusercontent.com/odoo/documentation/14.0/content/contributing/development/coding_guidelines.rst

# Odoo 14.0 Coding Guidelines - Index

These guidelines aim to improve the quality of Odoo Apps code. Proper code improves readability, eases maintenance, helps debugging, lowers complexity and promotes reliability. They should be applied to every new module and to all new development.

## How to use

Read the files relevant to your task before writing code. The two warnings below come from the top of the source guidelines and govern when these rules apply to existing files.

> **Warning - stable version:** When modifying existing files in a stable version, the original file style strictly supersedes any other style guidelines. In other words, never modify existing files in order to apply these guidelines. It avoids disrupting the revision history of code lines. Diff should be kept minimal. For more details, see the Odoo pull request guide (https://odoo.com/submit-pr).

> **Warning - master (development) version:** When modifying existing files in the master (development) version, apply these guidelines to existing code only for modified code or if most of the file is under revision. In other words, modify existing file structure only if it is going under major changes. In that case, first do a **move** commit, then apply the changes related to the feature.

## Files in this directory

| File | Contents |
|---|---|
| `module-structure.md` | Module directories, file naming conventions, and the complete module tree |
| `xml.md` | XML record/field format, xml-id naming patterns, view inheritance naming |
| `python.md` | PEP8 options, import order, Python idioms, programming in Odoo (batch methods, never commit the transaction, context propagation, translations) |
| `security.md` | Security pitfalls: secure-coding rules - sudo, SQL injection, XSS/t-raw, escaping, safe_eval |
| `naming.md` | Symbols and conventions: model names, class style, variable naming, field suffixes, method prefixes |
| `model-ordering.md` | Attribute order inside a model class, with example |
| `javascript.md` | Static files organization and JavaScript coding guidelines |
| `scss.md` | CSS coding guidelines |
| `tests.md` | Test classes, Form, HttpCase and tours, the JS test runner, and demo data in tests, for this series only |

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
