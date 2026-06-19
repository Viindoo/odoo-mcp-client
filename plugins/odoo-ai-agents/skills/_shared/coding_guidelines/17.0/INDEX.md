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
coding guidelines. Read the file for the topic you are working in. Cross-references between files
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

## By task

| Task | File(s) to read |
|---|---|
| Creating a new module | module-structure.md |
| Adding Python model code | python.md, naming.md, model-ordering.md, security.md |
| Writing XML views or data | xml.md |
| ORM method / compute / constraint | python.md, naming.md, security.md |
| Security (groups, rules, access) | xml.md, module-structure.md, security.md |
| Adding translations / `_()` calls | python.md (translation section) |
| Adding JS components | javascript.md, module-structure.md |
| Writing SCSS / CSS styles | scss.md |
| Naming fields, methods, classes | naming.md |
| Ordering model attributes | model-ordering.md |
