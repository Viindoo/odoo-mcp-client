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

## By task

| Task | File(s) to read |
|---|---|
| Creating a new module's folders and files | module-structure.md |
| Writing Python models, methods, idioms | python.md, security.md |
| Writing translatable strings (`self.env._`) | python.md |
| ORM method / compute / constraint | python.md, naming.md, security.md |
| Security (groups, rules, access) | xml.md, module-structure.md, security.md |
| Naming a model, class, variable, field, or method | naming.md |
| Ordering attributes and methods in a model class | model-ordering.md |
| Declaring records, views, actions, menus, inherits | xml.md |
| Organizing and writing web assets in Javascript | javascript.md (JS tooling/ESLint/Prettier detail: `../javascript-coding-guidelines.md`) |
| Writing CSS/SCSS styles, variables, and mixins | scss.md |
