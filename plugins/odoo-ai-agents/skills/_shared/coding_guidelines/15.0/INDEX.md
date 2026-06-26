> Source: official Odoo 15.0 coding guidelines - https://raw.githubusercontent.com/odoo/documentation/15.0/content/contributing/development/coding_guidelines.rst

# Odoo 15.0 Coding Guidelines - Index

These guidelines aim to improve the quality of Odoo Apps code. Proper code improves readability, eases maintenance, helps debugging, lowers complexity and promotes reliability. They should be applied to every new module and to all new development.

## How to use

1. These files cover Odoo **15.0**. Read the relevant file(s) BEFORE writing any code, XML, or SCSS.
2. When in doubt about a rule, the source RST is the canonical reference (URL above).

> **Warning - stable version:** When modifying existing files in a **stable version** the original file style strictly supersedes any other style guidelines. Never modify existing files in order to apply these guidelines. It avoids disrupting the revision history of code lines. Diffs should be kept minimal.
>
> **Warning - master (development) version:** When modifying existing files in **master (development) version** apply these guidelines to existing code only for modified code or if most of the file is under revision. Modify existing file structure only if it is going under major changes. In that case first do a **move** commit then apply the changes related to the feature.

## Files in this directory

| File | Covers |
|------|--------|
| `module-structure.md` | Directories, file naming conventions, the complete module tree |
| `python.md` | PEP8 options, import order, Python idioms, programming in Odoo (extendable design, never commit the transaction, context propagation, `_()` translations) |
| `security.md` | Security pitfalls: secure-coding rules - sudo, SQL injection, XSS/t-raw, escaping, safe_eval |
| `naming.md` | Model name notation, Python class naming, variable naming, field suffix rules (`_id`/`_ids`), method prefix conventions |
| `model-ordering.md` | Required attribute order inside a Model class, with annotated example |
| `xml.md` | Record/field format rules, XML-ID naming patterns, view inheritance `.inherit.` suffix, `<data>`/`noupdate` usage |
| `javascript.md` | JavaScript coding guidelines, pointer to the canonical local copy `../javascript-coding-guidelines.md` |
| `scss.md` | CSS coding guidelines from the 15.0 source |

## By task

> Read ONLY the files mapped to your current task. Snippet path prefix: `${CLAUDE_PLUGIN_ROOT}/snippets/`.

| Task | Read these files |
|------|-----------------|
| Creating a new module | `module-structure.md`, `naming.md`, `${CLAUDE_PLUGIN_ROOT}/snippets/new-module-manifest.md` |
| Writing Python models | `python.md`, `naming.md`, `model-ordering.md`, `security.md`, `${CLAUDE_PLUGIN_ROOT}/snippets/field-presence-resolution.md`, `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md §model-API` |
| Writing XML views / data | `xml.md`, `naming.md`, `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md §XML views` |
| Translation / `_()` usage | `python.md` |
| CRUD override or onchange | `model-ordering.md`, `python.md`, `security.md`, `${CLAUDE_PLUGIN_ROOT}/snippets/orm-performance.md`, `${CLAUDE_PLUGIN_ROOT}/snippets/stored-write-survival.md`, `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md §model-API` |
| Security (groups, rules, access) | `xml.md`, `module-structure.md`, `security.md`, `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md §ACL` |
| Writing JavaScript | `javascript.md` (JS tooling/ESLint/Prettier detail: `../javascript-coding-guidelines.md`) |
| Writing CSS / SCSS | `scss.md` |
| Naming fields, methods, classes, variables | `naming.md`, `${CLAUDE_PLUGIN_ROOT}/snippets/python-naming-conventions.md` |
