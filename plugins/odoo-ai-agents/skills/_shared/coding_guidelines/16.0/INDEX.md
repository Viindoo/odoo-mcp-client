> Source: official Odoo 16.0 coding guidelines - https://raw.githubusercontent.com/odoo/documentation/16.0/content/contributing/development/coding_guidelines.rst

# Odoo 16.0 Coding Guidelines - Index

These guidelines aim to improve the quality of Odoo Apps code. Proper code improves readability, eases maintenance, helps debugging, lowers complexity and promotes reliability. They should be applied to every new module and to all new development.

## How to use

1. These files cover Odoo **16.0**. Read the relevant file(s) BEFORE writing any code, XML, or SCSS.
2. When in doubt about a rule, the source RST is the canonical reference (URL above).

> Warning (stable version): When modifying existing files in **stable version** the original file style strictly supersedes any other style guidelines. In other words please never modify existing files in order to apply these guidelines. It avoids disrupting the revision history of code lines. Diff should be kept minimal. For more details, see the pull request guide at https://odoo.com/submit-pr.

> Warning (master/development version): When modifying existing files in **master (development) version** apply those guidelines to existing code only for modified code or if most of the file is under revision. In other words modify existing files structure only if it is going under major changes. In that case first do a **move** commit then apply the changes related to the feature.

---

## Files in this directory

| File | Covers |
|------|--------|
| `module-structure.md` | Directories, file naming conventions, the complete module tree, module naming prefix recommendation |
| `python.md` | Import order (including `Command`), PEP8 options, Python idioms, programming in Odoo (batch ORM methods, never commit the transaction, context propagation, `_()` translations) |
| `naming.md` | Model name notation, Python class naming, variable naming, field suffix rules (`_id`/`_ids`), method prefix conventions |
| `model-ordering.md` | Required attribute order inside a Model class, with annotated example |
| `xml.md` | Record/field format rules, XML-ID naming patterns, view inheritance `.inherit.` suffix, `<data>`/`noupdate` usage |
| `javascript.md` | Static files organization, JS coding guidelines, pointer to the upstream wiki |
| `scss.md` | Full CSS/SCSS section: syntax and formatting, Stylelint settings, properties order, naming conventions, SCSS variables, scoped SCSS variables, mixins and functions, CSS variables (BEM), use of CSS variables, CSS vs SCSS variables, the `:root` pseudo-class |

---

## By task

| Task | Read these files |
|------|-----------------|
| Creating a new module | `module-structure.md`, `naming.md` |
| Writing Python models | `python.md`, `naming.md`, `model-ordering.md` |
| Writing XML views / data | `xml.md`, `naming.md` |
| Writing JavaScript | `javascript.md` |
| Writing SCSS / CSS | `scss.md` |
| Code review checklist | all files relevant to the changed file types |
