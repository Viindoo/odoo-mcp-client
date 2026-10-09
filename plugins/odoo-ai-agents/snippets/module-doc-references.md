<!-- SSOT snippet. References in a module's shipped docs, which app stores publish. Edit here
     only; consumers cross-ref, never restate. -->

# Module doc references (images, manifest images, links to other modules)

A module's docs are published to app stores, away from the module tree. Each form below is the
one the stores resolve; the gate (§ Reference gate) checks it.

## Images

- The root of `static/description/` holds only `icon.png` (`icon.svg`), `index*.html` and the
  cover (§ Manifest images). Every other image the module ships lives directly in
  `static/description/assets/` - no deeper folder, none under `doc/`.
- Reference it as `.. image:: assets/<file>` in `doc/*.rst`, `src="./assets/<file>"` in
  `index*.html`, `static/description/assets/<file>` in `README.rst`; the cover the same way
  without `assets/`. The file must exist.
- Name it `<slug>[.<locale>].<ext>` (the cover: § Manifest images): `<slug>` is kebab-case,
  describes the screen and is unique in the module; English has no locale suffix; `<ext>` is png,
  gif or jpeg/jpg; only `A-Za-z0-9._-`. A screen the guide and the landing both show is one file.
  Never a staging or scenario name (`<scenario>-step<NN>`). A localized doc shows
  `<slug>.<locale>.<ext>` when that file exists, else the English `<slug>.<ext>`.
- An image that is not a module file (e.g. a vendor logo) may be a public `https://` URL; pin it
  to an immutable revision (a commit, a versioned path); the gate does not check pinning. Never
  `http://`, `data:`, `file:`, a leading `/` or `//`, a local or reserved host, or an instance URL.
- Whoever writes a doc file owns every image reference in it and brings each off-convention one
  (a screenshot at the root of `static/description/`, `../static/description/x.png`,
  `img/x.png`, `doc/images/x.png`) into this convention: the file moved into `assets/` under its
  convention name, the reference rewritten. While a file you do not write still references the
  old path, copy the file instead of moving it.

## Manifest images

`images[0]` is the cover `static/description/main_screenshot.<ext>`; a further entry is
`static/description/assets/<file>` or a locale cover; each an existing png, gif or jpeg. The
English `index.html` shows the cover (in its HERO); a localized page, its cover per § Images.

## Links to another module

- Link a different module with the root-relative store path
  `/apps/modules/<odoo_version>/<module_technical_name>`, a vendor's module listing with
  `/apps/modules/browse?author=<vendor>` - no trailing slash, no language prefix.
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
