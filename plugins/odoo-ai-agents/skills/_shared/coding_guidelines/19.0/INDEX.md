> Source: official Odoo 19.0 coding guidelines - https://raw.githubusercontent.com/odoo/documentation/19.0/content/contributing/development/coding_guidelines.rst

# Odoo 19.0 Coding Guidelines

This page introduces the Odoo Coding Guidelines. Those aim to improve the quality of Odoo Apps code. Indeed proper code improves readability, eases maintenance, helps debugging, lowers complexity and promotes reliability. These guidelines should be applied to every new module and to all new development.

## How to use these guidelines

These guidelines apply to every new module and to all new development. Two warnings from the source govern how they apply to existing files:

- **Stable version.** When modifying existing files in a **stable version** the original file style strictly supersedes any other style guidelines. In other words please never modify existing files in order to apply these guidelines. It avoids disrupting the revision history of code lines. Diff should be kept minimal. For more details, see the Odoo pull request guide (https://odoo.com/submit-pr).
- **Master (development) version.** When modifying existing files in the **master (development) version** apply those guidelines to existing code only for modified code or if most of the file is under revision. In other words modify existing files structure only if it is going under major changes. In that case first do a **move** commit then apply the changes related to the feature.

## Table of contents

1. [module-structure.md](module-structure.md) - Module structure: directories, file naming, and the complete module tree.
2. [python.md](python.md) - Python: PEP8 options, imports, idiomatics of programming, and programming in Odoo (context, extendable code, never commit, exceptions, translations).
3. [security.md](security.md) - Security pitfalls: secure-coding rules - sudo, SQL injection, XSS/t-raw, escaping, safe_eval.
4. [naming.md](naming.md) - Symbols and Conventions: model name, Python class, variable name, field suffixes, and method prefixes.
5. [model-ordering.md](model-ordering.md) - Order of attributes in a Model, with a full example class.
6. [xml.md](xml.md) - XML files: record format, XML IDs and naming, inheriting XML.
7. [javascript.md](javascript.md) - Javascript: static files organization and coding guidelines.
8. [scss.md](scss.md) - CSS and SCSS: syntax and formatting, properties order, naming conventions, variables.

## By task

> Read ONLY the files mapped to your current task. Snippet path prefix: `${CLAUDE_PLUGIN_ROOT}/snippets/`.

| Task | File(s) to read |
|---|---|
| Setting up a new module's directory layout | module-structure.md, `${CLAUDE_PLUGIN_ROOT}/snippets/new-module-manifest.md` |
| Writing or reviewing Python models | python.md, naming.md, model-ordering.md, security.md, `${CLAUDE_PLUGIN_ROOT}/snippets/field-presence-resolution.md`, `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md §model-API` |
| ORM method / compute / constraint | python.md, naming.md, security.md, `${CLAUDE_PLUGIN_ROOT}/snippets/orm-performance.md`, `${CLAUDE_PLUGIN_ROOT}/snippets/stored-write-survival.md`, `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md §model-API` |
| Security (groups, rules, access) | xml.md, module-structure.md, security.md, `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md §ACL`, `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md §Core test-enforced authoring rules (hr.employee field groups, v16+)` |
| Propagating context, managing transactions, handling exceptions | python.md |
| Translating static strings in code | python.md |
| Declaring records, views, actions, menus, security | xml.md, `${CLAUDE_PLUGIN_ROOT}/snippets/xml-view-conventions.md`, `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md §XML views` |
| Naming XML IDs and inheriting views | xml.md, `${CLAUDE_PLUGIN_ROOT}/snippets/xml-view-conventions.md`, `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md §XML views` |
| Organizing or writing web assets (JS) | javascript.md (JS tooling/ESLint/Prettier detail: `../javascript-coding-guidelines.md`) |
| Writing CSS/SCSS, variables, mixins, and naming classes | scss.md |
| Naming fields, methods, classes, variables | naming.md, `${CLAUDE_PLUGIN_ROOT}/snippets/python-naming-conventions.md` |
