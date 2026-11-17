# odoo-marketer - MODE landing

## MODE landing

Reader: the buying committee of the profile - developers, business owners and Odoo consultants,
expert, short of time and allergic to being sold to. The page is the decision path of
`${CLAUDE_PLUGIN_ROOT}/skills/odoo-doc-illustration/references/app-store-template.md` § 2: its
sections in its order, within its targets. Value first; never open with "This module extends X"
and never a class, field or model name in a heading or a sentence - unless the module is a
developer tool whose buyers are developers, when the technical names are the value.

The store shows a module in two parts, and this page is the first: it sells - the outcome, the
proof, the decision. The second is the guide (`doc/`, the Documentation tab), the writer's file,
which teaches. Nothing on this page reads like the guide: no click path, no numbered procedure, no
field-by-field or menu-by-menu description, no configuration walkthrough; a step the buyer must
know is one sentence of outcome with a link to the guide.

1. **Inputs.** `FEATURE CATALOG` and `ROLE MAP` are required; absent, return
   `NEEDS_NEXT` with `next: odoo-doc-feature-map`. Copy: `MARKETING COPY` when supplied, else
   write the landing-page copy blocks yourself per § Channels from the catalog, the role map, the
   descriptor and the profile. A section the Section Map marks `Always` with no block is
   `NEEDS_CONTEXT(marketing copy: <KEY>)`. Editions, license, shipped languages and what must be
   installed come from the manifest, the module tree and the scripts the Section Map names, never
   from memory. With `CHANGE` as a feature list, only the sections of the changed capabilities
   are rewritten and only their shots recaptured; every other section stays byte-identical.
2. **Capture** the module's main screen for the HERO, the proof shot of each WHAT-CHANGES block,
   the reports of INSIGHTS (each opened as its manager opens it, on data that gives it a shape;
   an empty report is left out and reported) and the few the DAY-ONE cards need, within the
   image targets, per
   `${CLAUDE_PLUGIN_ROOT}/skills/_shared/doc-capture-mechanics.md` with the marketing framing of
   its § 7.5; a screen already in `STAGED CAPTURES` (this run's captures on this build) is reused,
   never reshot; an image on the page from an EARLIER build (another theme, another demo user,
   another version) is recaptured on this build, never kept - every image of a page you return
   shows the build you worked on. One browser family at a time.
3. **Assemble `static/description/index.html`** (and `index_<locale>.html` per other locale)
   strictly per app-store-template: sections in Section Map order from the source each row names,
   the hero tagline from the manifest `summary`, the sanitizer rules of its § 1, the palette from
   `BRAND` (else the template's own fallbacks), legacy `oe_*` classes kept when the module
   already uses them. The video of a page is the entry of `VIDEO` for that page's language; none,
   no VIDEO section. FEATURES lists the catalog, grouped, within its line target: a capability
   the catalog does not hold is not listed, and a claim of its closing group is verified like any
   other. After the hero, one line per `extends_in_scope` base, linked per
   `${CLAUDE_PLUGIN_ROOT}/snippets/module-doc-references.md` § Links to another module. The cards
   of EXTENSIONS are the installable modules `module_dependents.py` lists (up to 6, the ones the
   buyer profile needs next; the rest in the report), each body from that module's manifest
   `summary` or its own catalog in the buyer's words - never a module the script did not list.
   A marker left in the shipped file means a capture degraded: say so in `concerns`.
4. **Contact and manifest.** The TRY-AND-SUPPORT section takes its two cards from
   `AUTHOR PROFILE`: `presales_url` and `support_url`, each written as an anchor whose visible
   text is the URL itself; a URL the profile lacks drops its card, and `AUTHOR PROFILE: none`
   drops the cards - reported as a store-readiness gap, never filled from memory. No address
   appears anywhere on the page; under `address_policy: image` an address the vendor insists on
   is a PNG from `${CLAUDE_PLUGIN_ROOT}/scripts/lib/email_image.py` with the alt text it prints.
   The manifest takes two edits at most, each a targeted Edit, per app-store-template § 5:
   `support` and the video link. You never write `images`, `price`, `currency` or
   `live_test_url`; the gaps of § 5 go in the report.
5. **Finals and gates.** `mv` each final into `static/description/assets/` under its convention
   name and optimise it (doc-capture-mechanics § 13), bring every off-convention reference into the convention,
   then run the gate of `module-doc-references.md` § Reference gate (`--series` = the resolved
   `ODOO VERSION`, `--addons-path` = `ADDONS_PATH`, so a store link to a module that does not exist
   is caught) on every `index*.html` you wrote plus the descriptor until it exits 0; exit 2
   is `NEEDS_CONTEXT` with the printed remedy. Its page findings measure the targets: under
   `CHANGE: whole` cut until the page passes - a page over the targets is not DONE; under a
   feature-list `CHANGE`, where the other sections stay as they are, report them in `concerns`
   with the recommendation `CHANGE: whole`. A finding about the manifest `images` list or the
   cover is the cover designer's, reported and not fixed here. Close every page you
   drove (`${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T2).
