<!-- SSOT snippet. References inside a module's shipped docs (static/description/index*.html,
     doc/*.rst, manifest `images`), which app stores publish. Edit here only; consumers point at
     ${CLAUDE_PLUGIN_ROOT}/snippets/module-doc-references.md. -->

# Module doc references (images, manifest images, links to other modules)

A module's docs are published to app stores, away from the module tree. Every reference in them
must resolve the same way on disk and on the store.

## Images

- Write every image reference as a plain path relative to the doc file that holds it: no scheme,
  no leading `/`, no `file:`, localhost or instance URL, never a path that escapes the module.
- An `index.html` image must resolve inside `static/description/` (stores rewrite relative `src`
  against that directory).
- An RST image must resolve inside the module's `static/`.
- The referenced file must exist.

## Manifest images

Each manifest `images` entry is relative to the module root and names an existing file.

## Links to another module

- Link a different module with the root-relative store path
  `/apps/modules/<odoo_version>/<module_technical_name>` - no trailing slash, no language prefix.
  `<odoo_version>` is the series you resolved for the module you are documenting; never write a
  literal version.
- RST form: `` `<module> </apps/modules/<odoo_version>/<module>>`__ `` (anonymous `__`: a named
  `_` link repeated in one file is a docutils message the RST render gate rejects).
  HTML form: `<a href="/apps/modules/<odoo_version>/<module>">`.
- Never an absolute URL whose path is `/apps/modules/...` on any host (it sends readers to a
  different store), and never a filesystem path to a sibling module (`../../<module>/...`).
- `mailto:`, author-site and video links are fine.

## Reference gate

After you write or edit any of these files, run the gate, passing every doc file you wrote plus the
module descriptor (`__manifest__.py` / `__openerp__.py`) when you edited its `images`. With no file
arguments it checks every doc file and the descriptor.

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/lib/doc_refs_check.py" --module-root <abs module path> --series <resolved series> [files...]
```

`<resolved series>` is the `X.Y` series form - the same value as `<odoo_version>` above.

- Exit 0: clean.
- Exit 1: each finding prints `file:line: RULE: ref`. Fix every one and re-run until exit 0.
- Exit 2: environment or usage error. Return `NEEDS_CONTEXT` with the remedy it printed.
