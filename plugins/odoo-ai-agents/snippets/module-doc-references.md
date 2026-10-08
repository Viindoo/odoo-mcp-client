<!-- SSOT snippet. References inside a module's shipped docs (static/description/index*.html,
     doc/*.rst, manifest `images`), which app stores publish. Edit here only; consumers point at
     ${CLAUDE_PLUGIN_ROOT}/snippets/module-doc-references.md. -->

# Module doc references (images, manifest images, links to other modules)

A module's docs are published to app stores, away from the module tree. Every reference in them
must resolve the same way on disk and on the store.

## Images

- Every image the module ships lives flat in `static/description/` - no subdirectory, none under
  `doc/`.
- Reference it as `.. image:: <file>` in `doc/*.rst` (the bare file name: stores resolve only
  that, looked up in `static/description/`), `src="./<file>"` in `index*.html`, and
  `static/description/<file>` in `README.rst`. Never a scheme, a leading `/`, `file:`, localhost or
  an instance URL. The file must exist.
- Name a screen `<slug>[.<locale>].<ext>` (the cover: § Manifest images): `<slug>` is kebab-case,
  describes the screen and is unique in the module; English has no locale suffix; `<ext>` is png,
  gif or jpeg/jpg. A screen the guide and the landing both show is one file. Never a staging or
  scenario name (`<scenario>-step<NN>`).
- Whoever writes a doc file owns every image reference in it and brings each off-convention one
  (`assets/x.png`, `../static/description/x.png`, `/assets/x.png`, `img/x.png`,
  `doc/images/x.png`) into this convention: the file into `static/description/` under its
  convention name, the reference rewritten.

## Manifest images

Each `images` entry is `static/description/<file>`, an existing png, gif or jpeg. The cover is
`images[0]` = `main_screenshot.<ext>` and is the first local image of the English `index.html`;
each `index_<locale>.html` opens with its own `main_screenshot.<locale>.<ext>`.

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
arguments it checks every doc file and the descriptor, and reports `IMG_ORPHAN` for each image
under `static/description/` or `doc/` that no other module file names (`icon.png` / `icon.svg`
exempt); an orphan is fixed by deleting the file.

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/lib/doc_refs_check.py" --module-root <abs module path> --series <resolved series> [files...]
```

`<resolved series>` is the `X.Y` series form - the same value as `<odoo_version>` above.

- Exit 0: clean.
- Exit 1: each finding prints `file:line: RULE: ref`. Fix every one and re-run until exit 0.
- Exit 2: environment or usage error. Return `NEEDS_CONTEXT` with the remedy it printed.
