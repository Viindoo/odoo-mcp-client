<!-- SSOT snippet. References in a module's shipped docs, which app stores publish. Edit here
     only; consumers cross-ref, never restate. -->

# Module doc references (images, manifest images, links to other modules)

## Images

- The root of `static/description/` holds only `icon.png` (`icon.svg`), `index*.html` and the
  cover (§ Manifest images). Every other image the module ships lives directly in
  `static/description/assets/` - no deeper folder, none under `doc/`.
- Reference it as `.. image:: assets/<file>` in `doc/*.rst`, `src="./assets/<file>"` in
  `index*.html`, `static/description/assets/<file>` in `README.rst`; the cover the same way
  without `assets/`. The file must exist.
- Name it `<slug>[.<locale>].<ext>` (the cover: § Manifest images): `<slug>` is kebab-case,
  describes the screen, unique in the module; English has no locale suffix; `<ext>` png, gif or
  jpeg/jpg; only `A-Za-z0-9._-`. A screen the guide and the landing both show is one file. Never a
  staging or scenario name. A localized doc shows `<slug>.<locale>.<ext>` when it exists, else the
  English file.
- A non-module image (e.g. a vendor logo) may be a public `https://` URL pinned to an immutable
  revision (unchecked). Never `http://`, `data:`, `file:`, a leading `/` or `//`, a local or
  reserved host, or an instance URL.
- **Fit on the stores.** Doc screenshots are captured at device pixel ratio 2 (pixel width = 2x the
  intended CSS width). For every image in a module's `.rst` the stores publish (the gate checks `doc/*.rst` and
  `README.rst`; a docs site has its own rules):
  1. A block image (`.. image::`, `.. figure::`) carries `:class: img-fluid d-block mx-auto`.
  2. An inline substitution image (`.. |x| image::`) carries `:class: img-fluid` only (`d-block`
     breaks the line).
  3. A module image file carries `:width: <N>px`: N = the intended CSS width (pixel width / 2 for a
     DPR-2 capture), never above the file's pixel width.
  4. Never `:width:` in %, class `w-100`, `:scale:`, `:height:` or `:align:`.
  5. An external `https://` image needs only the class part.

  `:alt:` describes the image; it never replaces the class and the width.
- Whoever writes a doc file owns every image reference in it and brings each off-convention one
  (root of `static/description/`, `../static/description/x.png`, `img/x.png`, `doc/images/x.png`)
  into this convention: file moved into `assets/` under its convention name, reference rewritten.
  While a file you do not write still references the old path, copy instead of moving.

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
- RST: `` `<module> </apps/modules/<odoo_version>/<module>>`__ `` (anonymous `__`: a repeated named
  `_` link fails the RST render gate). HTML: `<a href="/apps/modules/<odoo_version>/<module>">`.
- Never an absolute URL whose path is `/apps/modules/...` on any host (it sends readers to a
  different store), and never a filesystem path to a sibling module (`../../<module>/...`).
- `mailto:`, author-site and video links are fine.

## Reference gate

After you write or edit any of these files, run the gate, passing every doc file you wrote plus the
module descriptor (`__manifest__.py` / `__openerp__.py`) when you edited its `images`. With no file
arguments it checks every doc file and the descriptor, and reports `IMG_ORPHAN` for each image
under `static/description/` or `doc/` that no other module file names (`icon.png` / `icon.svg`
exempt); delete an orphan.

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/lib/doc_refs_check.py" --module-root <abs module path> --series <resolved series> [files...]
```

It also enforces the image fit above: `IMG_NOT_FLUID`, `IMG_STRETCHED`, `IMG_NO_WIDTH`,
`IMG_UPSCALED` (pixel width read from the file header).

- Exit 0: clean.
- Exit 1: each finding prints `file:line: RULE: ref`. Fix every one and re-run until exit 0.
- Exit 2: environment or usage error. Return `NEEDS_CONTEXT` with the remedy it printed.
