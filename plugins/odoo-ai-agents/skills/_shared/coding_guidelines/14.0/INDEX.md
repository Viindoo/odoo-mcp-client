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

## By task

| Task | Files to read |
|---|---|
| New module scaffold | `module-structure.md` |
| Writing a view | `xml.md` |
| Inheriting an existing view | `xml.md` (section: Inheriting XML) |
| Security (groups, rules, access) | `xml.md` + `module-structure.md` + `security.md` |
| Adding a field or model | `naming.md` + `model-ordering.md` + `python.md` |
| ORM method / compute / constraint | `python.md` + `naming.md` + `security.md` |
| Writing / reviewing Python | `python.md` + `naming.md` + `security.md` |
| Translations / i18n | `python.md` (section: Use translation method correctly) |
| Wizard / TransientModel | `naming.md` + `module-structure.md` |
| Report (SQL view or QWeb) | `module-structure.md` + `naming.md` |
| JavaScript / CSS assets | `javascript.md` + `scss.md` (JS tooling/ESLint/Prettier detail: `../javascript-coding-guidelines.md`) |
