# odoo-icon-designer - MODE cover

The store cover is the image a store shows for the module before anyone opens its page, most
often as a card about 300 px wide in a grid of other modules: a product cover, never a
screenshot. It is `<MODULE_PATH>/static/description/main_screenshot.png`, the first entry of the
manifest `images` list, and it is the same for every language.

Brief fields of this mode: `MODULE_PATH`, `WORKTREE_PATH` and `ISOLATE_DIR` (absent:
`NEEDS_CONTEXT(<field>)`); optional `BRAND` (the vendor's palette and logo) and `FONT_FILE`.
Work files go under `<ISOLATE_DIR>/icon-gate/<module>/`.

1. **Facts.** From the descriptor: `name`, the product name as the store shows it; the module's
   own icon. A cover states nothing else: no tagline, no version, no price, no edition.
2. **Family.** Read the covers of the vendor's other modules in the repository (the modules
   sharing this one's name prefix and the in-repo modules it depends on) and keep what the
   designed ones share - where the name stands, how the two fields are split, the type. Covers
   that are screenshots are not a family to follow.
3. **Palette.** `BRAND` by role (`${CLAUDE_PLUGIN_ROOT}/snippets/vendor-facts.md`): `primary` is
   the largest field, `secondary` an accent, no state colour; absent, the palette of step 3 of
   your icon steps.
4. **Compose `cover.svg`** in the work directory, `viewBox="0 0 1280 640"` (the Odoo Apps Store
   crops a cover to 2:1; a marketplace built on Odoo shows it whole; both show it about 630 px
   wide, so more pixels only weigh on the page), from two things only:
   - the product name, the largest element: two or three lines of heavy type, at a font size of
     at least a tenth of the cover's height;
   - one flat illustration drawn as vector shapes from the module's icon - its glyph, enlarged
     and simplified - on a field of its own (an icon with no vector source is embedded as an
     image on less than a quarter of the cover).
   Two fields split by a diagonal or a curve, generous empty space, every element inside a margin
   of 5% of each side. No capture of the software, no photograph, no text besides the name.
   `FONT_FILE` is embedded in the SVG as a base64 data URI: a rasterizer loads the SVG as one
   image and fetches nothing. Without it, name a generic sans-serif family.
5. **Render and gate.** `icon_gate render <cover.svg>
   <MODULE_PATH>/static/description/main_screenshot.png --size 1280x640`, then `icon_gate cover
   <that png> --svg <cover.svg> --out-dir <work directory>` -> `COVER_GATE=PASS|FAIL`,
   `FAIL_REASON=` lines and `PREVIEW=`, the cover at the width of a store card. `FAIL`: fix the
   SVG, render and gate again. No rasterizer: `NEEDS_CONTEXT(no SVG rasterizer; cover.svg
   written)`.
6. **Read the preview** the way a buyer scans a grid of apps, at least twice: the name reads at
   a glance, the illustration says what kind of product this is, nothing is cut or crowded, and
   beside the family's covers it belongs. Redraw until it does.
7. **Manifest.** With a targeted Edit make `'static/description/main_screenshot.png'` the first
   entry of `images`, in place of a previous cover; the entries after it (the screen captures)
   stay as they are. A previous cover file that no doc references is deleted.

Report: the cover path, the gate line, one line per preview read, the source of the colours and
the family followed, and the manifest edit.
