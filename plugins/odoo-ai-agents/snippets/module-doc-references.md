# Module doc references (images, manifest images, links to other modules)

## Images

- The root of `static/description/` holds only `icon.png` (`icon.svg`), `index*.html` and the
  cover (§ Manifest images). Every other image the module ships lives directly in
  `static/description/assets/` - no deeper folder, none under `doc/`.
- Reference it as `.. image:: assets/<file>` in `doc/*.rst`, `src="./assets/<file>"` in
  `index*.html`, `static/description/assets/<file>` in `README.rst`. The file must exist.
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

The first entry of `images` is the store cover `static/description/main_screenshot.<ext>` (an
existing png, gif or jpeg): a product cover at 2:1 designed by `odoo-icon-design`, the same for
every language - the one image a single-image store shows, and every store's listing card. A doc
embeds its own captures, never the cover.

The entries after it are the module's main screens, for a store that shows the whole list as a
gallery: English captures already under `static/description/assets/` (never a locale variant or
a second cover), main screens first and reports after, landscape (about 16:10) and legible at
630 px wide. A module with no screen of its own and no change to another module's screen lists
the cover alone.

## Links to another module

- Link a different module with the root-relative store path
  `/apps/modules/<odoo_version>/<module_technical_name>`, a vendor's module listing with
  `/apps/modules/browse?author=<vendor>` - no trailing slash, no language prefix.
  `<odoo_version>` is the series you resolved for the module you are documenting; never write a
  literal version.
- RST: `` `<module> </apps/modules/<odoo_version>/<module>>`__ `` (anonymous `__`: a repeated named
  `_` link fails the RST render gate). HTML: `<a href="/apps/modules/<odoo_version>/<module>">`.
- Never an absolute URL whose path is `/apps/modules/...` on any host (it sends readers to a
  different store), and never a filesystem path to a sibling module (`../../<module>/...`). With
  `--addons-path`, a link to a module in none of those directories is a finding.
- Never a `mailto:` link or an email address, plain or obfuscated, in a doc file, an alt or a
  title. Contact is a web page from the author profile; an address the author insists on ships
  only as an image (`${CLAUDE_PLUGIN_ROOT}/scripts/lib/email_image.py`).
- On the store page every external link's visible text shows its host and path (the store
  renders external anchors as plain text); author-site and video links are fine written that way.

## Reference gate

After you write or edit any of these files, run the gate, passing every doc file you wrote plus the
module descriptor (`__manifest__.py` / `__openerp__.py`) when you edited its `images`. With no file
arguments it checks every doc file and the descriptor, and reports `IMG_ORPHAN` for each image
under `static/description/` or `doc/` that no other module file names (`icon.png` / `icon.svg`
exempt); delete an orphan.

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/lib/doc_refs_check.py" --module-root <abs module path> --series <resolved series> [--addons-path <dirs>] [files...]
```

It also enforces the image fit above and the manifest list.

Exit 1 prints one `file:line: RULE: ref` per finding: fix each and re-run until it exits 0. Exit 2
is an environment or usage error: return `NEEDS_CONTEXT` with the remedy it printed.
