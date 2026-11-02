# App Store Template Reference

**Contents:** 1. Sanitizer Rules (mandatory - violations are stripped silently) - 2. Section Map (the buyer's decision path) - 3. Bootstrap-5 Fragment Skeleton - 4. Image Specifications - 5. Manifest Store Keys - 6. i18n Conventions

Assembly reference for `static/description/index.html` and related assets of an Odoo App Store
listing. `{{PRIMARY_HEX}}` resolves from `<SHARE_DIR>/brand-tokens.json` when that file exists - a
map of CSS custom-property NAME -> COLOUR (e.g. `{ "--primary": "#1E88E5" }`; schema SSOT:
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-frontend-fidelity.md` § Brand-token fidelity), read by
VALUE: an unfamiliar token NAME is never a miss, take the colour it maps to - else from user input,
else the Odoo palette `#714B67`. A typeface never comes from that map: typography is Bootstrap-5
classes plus inline `font-weight` / `font-size` only. `<SHARE_DIR>` is the captured absolute path
(`${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`), never the placeholder.

---

## 1. Sanitizer Rules (mandatory - violations are stripped silently)

| Rule | Detail |
|---|---|
| Fragment only | Start at `<section>`. NO `<!DOCTYPE>`, `<html>`, `<head>`, `<body>`. |
| No JavaScript | No `<script>` tags, no inline event handlers (`onclick`, `onmouseover`, etc.). |
| No external CDN links | No `<link>` tags (Bootstrap CDN, Google Fonts, Font Awesome CDN). The store pre-loads Bootstrap 5 - use its classes directly. The store's own rule (apps.odoo.com vendor guidelines): YouTube canonical links and Microsoft Teams links survive, every other external link is invalidated - the store rewrites the anchor to plain text and keeps its words. So an external link's visible text IS its URL (host and path, e.g. `support.acme-erp.com/tickets`), never a label such as "Open a ticket"; the reference gate's `LINK_TEXT_HIDES_URL` enforces it (a YouTube link is exempt: the store keeps it). |
| No bare `<iframe>` | The store strips every `<iframe>`. A video is the Odoo website video container - `<div class="media_iframe_video" data-oe-expression="//www.youtube.com/embed/<id>?rel=0">` with the `<iframe>` as its child (§ 3 VIDEO): the store's own frontend rebuilds the iframe from `data-oe-expression` after stripping the child, and a marketplace that keeps the child renders it directly. YouTube only. |
| No address anywhere | No `mailto:`, no email address in text, alt or title, obfuscated or not: the page is public and indexed, addresses are harvested (`LINK_MAILTO`, `EMAIL_ADDRESS`). Contact goes through the author profile's pre-sales and support URLs (`${CLAUDE_PLUGIN_ROOT}/snippets/public-docs-contract.md`); an address the author insists on ships only as an image made by `${CLAUDE_PLUGIN_ROOT}/scripts/lib/email_image.py`, with an alt text that is not the address. |
| Bootstrap 5 for flexbox | Use `d-flex align-items-center justify-content-between gap-3`, `row`/`col-*` grid. Do NOT use inline `display:flex`, `align-items`, `justify-content`, `flex-wrap`, `flex-direction`, `gap` - all stripped. |
| Hex colors only | `background-color:#714B67`, `color:#ffffff`. No `rgba()`, no `linear-gradient` (both stripped). |
| HTML entities | `&rarr;` not `->`, `&mdash;` not `--`, `&copy;` not `(c)`. Raw Unicode glyphs may corrupt on render. |
| Image paths and module links | Per `${CLAUDE_PLUGIN_ROOT}/snippets/module-doc-references.md`. |
| Safe inline styles | `background-color`, `color`, `font-weight`, `font-size`, `line-height`, `padding`, `margin`, `border`, `border-radius`, `width`, `height`, `max-width`, `text-align` survive. Prefer a Bootstrap 5 utility class wherever one exists (`gap-*`, `ratio`, `overflow-hidden`, `mb-3`). |
| Legacy oe_* classes | Still accepted. Keep them when the module already uses them; otherwise Bootstrap 5. Never both in one file. |

---

## 2. Section Map - the buyer's decision path

The buyer is a developer, a business owner or an Odoo consultant: expert, short of time and
allergic to being sold to. The page answers their questions in the order they ask them, in about
thirty seconds of reading, then stops. Reviews, ratings and the install or buy button are the
store's own; the page never imitates them and has no call-to-action section.

Targets, enforced by the reference gate (`PAGE_TOO_LONG`, `PAGE_TOO_MANY_IMAGES`): at most 700
words of visible text and 8 images (the cover, three proof shots, up to four more); exactly three
WHAT-CHANGES blocks and five FAQ entries.

Sources: `copy` = the block of that key in the marketing copy, written from the buyer profile;
`catalog` = `feature-catalog.jsonl`; `captures` = screenshots of the module's tasks; `manifest` =
the module descriptor; `brief` = a value the caller supplies; `dependents` = the vendor's own
installable modules whose `depends` names this one, listed by
`${CLAUDE_PLUGIN_ROOT}/scripts/lib/module_dependents.py <module> --addons-path <ADDONS_PATH>
--author "<manifest author>"`.

| # | Key | ID | The buyer asks | Content | Source | Required |
|---|---|---|---|---|---|---|
| 1 | HERO | `#overview_block` | Is this what I am looking for? | One outcome sentence for the buyer persona (the result, never the module name), a "For <segment>" line, the tagline = manifest `summary`, the cover; then the compatibility line - series, every edition the manifest supports, license - what a consultant checks first | copy + manifest | Yes |
| 2 | WHAT-CHANGES | `#changes_block` | Does it fit my work? | Exactly three blocks "what changes for your team": the work as the team does it today, what it becomes, each tied to ONE verified catalog feature and ONE proof shot | copy + catalog + captures | Yes |
| 3 | VIDEO | `#video_block` | Show me | One video with ENGLISH narration (the store page is English) in the container of § 1; no English video = no section | brief | Optional |
| 4 | DAY-ONE | `#day_one_block` | What do I have on day one? | What ships ready to use (data, templates, packs, connections) and what the administrator configures first - from the module's data files and the catalog, never a count or a duration the module does not state | catalog + manifest | Recommended |
| 5 | INCLUDED | `#included_block` | What else will I need? | What this module covers on its own, then the vendor's optional extensions as cards - the display name linked in the root-relative store form of `${CLAUDE_PLUGIN_ROOT}/snippets/module-doc-references.md` § Links to another module (the same path works on the vendor's marketplace and on the Odoo Apps Store), one or two sentences of the outcome from that module's manifest `summary` or catalog; only modules the `dependents` source lists, up to 6, the ones the buyer needs next first, the rest in the report; no price figure anywhere (the store shows prices; prices change) | manifest + dependents | Yes |
| 6 | FAQ | `#faq_block` | What could go wrong? | Exactly five questions a buyer asks before paying - where the data goes, how cost is controlled, who sees what, which languages, what it takes to run or extend it - each answered plainly; a real limit stated as a fact earns more trust than a claim | copy | Yes |
| 7 | TRY-AND-SUPPORT | `#support_block` | How do I evaluate it, whom do I ask? | The evaluation path (the Documentation tab, `live_test_url` when the manifest has one, the video) and two contact cards, pre-sales `{{PRESALES_URL}}` and technical support `{{SUPPORT_URL}}`, from the author profile; a card whose URL the profile lacks is omitted and reported as a gap, never filled | brief + author profile | Recommended |
| 8 | TECH | `#requirement_block` | (the developer) | Series, editions, required modules (each module of the same vendor linked in the store form, text = its display name; a core or third-party module by name, no link), license, languages shipped | manifest | Yes |

Page order is table order; every section is full width, one column, no tab block (a tab hides
content and the buyer does not click to find out). Omit an `Optional` or `Recommended` section
whose source is empty rather than leaving placeholders.

**Voice.** Calm, specific, evidence-led; outcome before feature; the buyer's words, never a class,
field or model name (unless the buyers are developers and the technical names are the value). No
heading that pushes ("reasons to buy", "buy now", "limited", "best", "most powerful"), no urgency,
no superlative, no invented customer, number, testimonial or certification; a claim with no source
is not written. Present tense, no history.

---

## 3. Bootstrap-5 Fragment Skeleton

Replace `{{PLACEHOLDER}}` values: `{{PRIMARY_HEX}}` per the header, `{{EXT}}` from the cover's
captured format, every other placeholder from the source its Section Map row names (§ 2).
Default palette when `brand-tokens.json` is absent: primary `#714B67`, bg-light `#F8F4F8`.

```html
<!-- static/description/index.html - FRAGMENT ONLY, no html/head/body -->
<!-- Bootstrap 5 already loaded by the store; do NOT add <link> CDN tags -->
<!-- Each section opens with its Section Map key (§2) -->

<!-- HERO -->
<section id="overview_block" style="margin-top:1.5rem;margin-bottom:1.5rem;">
  <div class="rounded p-4" style="background-color:{{PRIMARY_HEX}};border-radius:15px;">
    <div class="row mx-0 p-3 align-items-center" style="border-radius:15px;background-color:#f8f8f8;">
      <div class="col-lg-4 text-center text-lg-start p-2">
        <!-- Vendor logo: a public https image pinned to an immutable URL or a local png / jpeg
             (both per module-doc-references.md § Images), else the vendor name as text -->
        <strong style="font-size:20px;color:{{PRIMARY_HEX}};">{{VENDOR_NAME}}</strong>
      </div>
      <div class="col-lg-8 p-3 d-flex flex-wrap justify-content-end gap-2">
        <!-- One badge per edition the manifest supports -->
        <div class="btn" style="border-radius:10px;color:#fff;background-color:{{PRIMARY_HEX}};padding:10px 20px;">
          Odoo Community
        </div>
      </div>
    </div>
    <div class="row mt-4 text-center">
      <div class="col-md-12">
        <h1 style="color:#fff;font-weight:700;font-size:34px;margin-bottom:10px;">
          {{OUTCOME_HEADLINE - the result the buyer gets, not the module name}}
        </h1>
        <p style="color:#fff;font-size:16px;font-weight:600;margin-bottom:8px;">
          For {{SEGMENT - from the buyer profile}}
        </p>
        <p class="mx-auto" style="color:#fff;font-size:18px;line-height:26px;max-width:78%;margin-bottom:16px;">
          {{TAGLINE - matches manifest summary, outcome-first, 15 words max}}
        </p>
      </div>
    </div>
  </div>
  <!-- Cover - the widest image slot: measure its rendered width and frame the shot per
       doc-capture-mechanics.md § Frame for the placement slot -->
  <div class="row mt-4">
    <div class="col-md-10 offset-md-1 text-center" style="border-radius:20px;padding:3px;background-color:{{PRIMARY_HEX}};">
      <img alt="{{MODULE_DISPLAY_NAME}}" class="img-fluid" loading="lazy" src="./main_screenshot.{{EXT}}"
           style="border-radius:15px;display:block;width:100%;height:auto;">
    </div>
  </div>
  <!-- Compatibility line: what a consultant checks first -->
  <p class="text-center mt-3 mb-0" style="font-size:14px;color:#666;">
    Odoo {{SERIES}} &middot; {{EDITIONS - each edition the manifest supports}} &middot; {{LICENSE}}
  </p>
</section>

<!-- WHAT-CHANGES -->
<section id="changes_block" class="py-4">
  <div style="background-color:#f8f8f8;padding:40px;border-radius:15px;">
    <h2 class="text-center mb-4" style="font-size:32px;font-weight:bold;">What changes for your team</h2>
    <!-- Exactly three blocks; alternate the image side (offset the text column on the second) -->
    <div class="row align-items-center mb-4">
      <div class="col-md-12 col-xl-4">
        <h3 style="font-weight:700;font-size:22px;line-height:30px;">{{CHANGE_TITLE - the outcome, in the buyer's words}}</h3>
        <p style="font-size:15px;color:#666;">{{TODAY - how the team does this work now}}</p>
        <p class="mb-0" style="font-size:16px;font-weight:600;">&rarr; {{AFTER - what it becomes, tied to one verified feature}}</p>
      </div>
      <div class="col-md-12 col-xl-8 mt-3 mt-xl-0 d-flex justify-content-center">
        <!-- Proof shot: measure the slot width and frame per doc-capture-mechanics.md § Frame for
             the placement slot; {{SCREEN_FILE}} named per module-doc-references.md § Images -->
        <img alt="{{CHANGE_TITLE}}" class="img-fluid" loading="lazy" src="./assets/{{SCREEN_FILE}}"
             style="border-radius:15px;width:100%;height:auto;">
      </div>
    </div>
  </div>
</section>

<!-- VIDEO - omit the section when no ENGLISH narration exists -->
<section id="video_block" class="py-4">
  <div style="background-color:#f4f8ff;border-radius:20px;padding:40px 24px;">
    <div class="mx-auto text-center" style="max-width:960px;">
      <h2 style="font-size:28px;font-weight:bold;">{{VIDEO_TITLE - what the viewer sees, e.g. "Ninety seconds, start to finish"}}</h2>
      <!-- The Odoo website video container (§ 1): the store rebuilds the iframe from
           data-oe-expression; a marketplace that keeps the child iframe renders it as is -->
      <div class="media_iframe_video" data-oe-expression="//www.youtube.com/embed/{{VIDEO_ID}}?rel=0">
        <div class="css_editable_mode_display">&nbsp;</div>
        <div class="media_iframe_video_size">&nbsp;</div>
        <iframe src="//www.youtube.com/embed/{{VIDEO_ID}}?rel=0" frameborder="0" allowfullscreen="allowfullscreen" aria-label="Video"></iframe>
      </div>
      <p class="mt-3 mb-0" style="font-size:14px;">
        <a href="https://www.youtube.com/watch?v={{VIDEO_ID}}">youtube.com/watch?v={{VIDEO_ID}}</a>
      </p>
    </div>
  </div>
</section>

<!-- DAY-ONE -->
<section id="day_one_block" class="py-4">
  <div style="background-color:#f4f4f4;padding:40px;border-radius:15px;">
    <h2 class="text-center mb-4" style="font-size:30px;font-weight:bold;">Ready on day one</h2>
    <div class="row g-4">
      <!-- One card per thing that ships ready (data, templates, packs, connections), then one
           for what the administrator configures first; 2-4 cards -->
      <div class="col-md-6 col-lg-3">
        <div class="bg-white rounded p-4 h-100" style="border-top:4px solid {{PRIMARY_HEX}};">
          <h4 style="font-size:16px;font-weight:700;">{{SHIPPED_ITEM}}</h4>
          <p class="mb-0" style="font-size:14px;">{{what it lets the team do without setting anything up}}</p>
        </div>
      </div>
    </div>
  </div>
</section>

<!-- INCLUDED -->
<section id="included_block" class="py-4">
  <div style="background-color:#f8f8f8;padding:40px;border-radius:15px;">
    <h2 class="text-center mb-2" style="font-size:30px;font-weight:bold;">What is included</h2>
    <p class="text-center mb-4" style="font-size:15px;">
      {{ONE OR TWO SENTENCES - what this module covers on its own; no price figure}}
    </p>
    <!-- Optional extensions: only modules module_dependents.py listed, up to 6; omit the grid
         when it lists nothing -->
    <h3 class="text-center mb-3" style="font-size:20px;font-weight:700;">Optional extensions</h3>
    <div class="row g-4">
      <div class="col-md-6 col-lg-4 d-flex">
        <div class="flex-fill" style="padding:24px;border-radius:12px;background:#fff;border:1px solid #e8e8e8;">
          <h4 style="font-size:16px;font-weight:600;">
            <a href="{{EXT_STORE_LINK - the root-relative store path of module-doc-references.md § Links to another module}}"
               style="color:{{PRIMARY_HEX}};text-decoration:none;">{{EXT_DISPLAY_NAME}}</a>
          </h4>
          <p class="mb-0" style="font-size:14px;">{{EXT_BODY - the outcome of adding it, 1-2 sentences, no code names}}</p>
        </div>
      </div>
    </div>
  </div>
</section>

<!-- FAQ -->
<section id="faq_block" class="py-4">
  <div style="background:#f4f4f4;padding:40px;border-radius:15px;">
    <h2 class="text-center mb-4" style="font-size:30px;font-weight:bold;">Before you decide</h2>
    <!-- Exactly five: the question as the buyer asks it, then the plain answer -->
    <div class="bg-white rounded mb-3" style="padding:18px 24px;border:1px solid #e8e8e8;">
      <h4 style="font-size:16px;font-weight:700;">{{QUESTION}}</h4>
      <p class="mb-0" style="font-size:14px;">{{ANSWER}}</p>
    </div>
  </div>
</section>

<!-- TRY-AND-SUPPORT -->
<section id="support_block" class="py-4">
  <div style="padding:40px;border-radius:15px;background-color:#f8f8f8;">
    <h2 class="text-center" style="font-size:30px;font-weight:bold;">Try it, then ask us</h2>
    <p class="text-center mt-3" style="font-size:15px;">
      {{EVALUATION PATH - the Documentation tab above; the live demo when the manifest has
      live_test_url; the video}}
    </p>
    <div class="row mt-4">
      <div class="col-lg-6 col-md-12 mb-4">
        <div style="background:#f4f4f4;padding:32px;border-radius:15px;">
          <h3>Pre-sales &amp; partnership</h3>
          <!-- The store turns this anchor into plain text: the visible text is the URL -->
          <a href="{{PRESALES_URL}}">{{PRESALES_URL_TEXT}}</a>
        </div>
      </div>
      <div class="col-lg-6 col-md-12 mb-4">
        <div style="background:#fff;padding:32px;border-radius:15px;border:1px solid #e8e8e8;">
          <h3>Technical support</h3>
          <a href="{{SUPPORT_URL}}">{{SUPPORT_URL_TEXT}}</a>
        </div>
      </div>
    </div>
  </div>
</section>

<!-- TECH -->
<section id="requirement_block" class="py-4">
  <div style="background:#f4f4f4;padding:40px;border-radius:15px;">
    <h2 class="text-center mb-4" style="font-size:30px;font-weight:bold;">Technical requirements</h2>
    <div class="p-3 bg-white rounded">
      <ul style="list-style:none;padding-left:0;margin-bottom:0;">
        <li class="py-2"><strong>Odoo version:</strong> {{SERIES}}</li>
        <li class="py-2"><strong>Editions:</strong> {{each edition the manifest supports}}</li>
        <li class="py-2"><strong>Required modules:</strong> {{depends list from the manifest - each module of the
            same vendor as a link in the store form of module-doc-references.md § Links to another module,
            text = its display name; a core or third-party module as its display name, no link}}</li>
        <li class="py-2"><strong>License:</strong> {{manifest license key}}</li>
        <li class="py-2"><strong>Languages:</strong> {{the locales the module ships translations for}}</li>
      </ul>
    </div>
  </div>
</section>
```

---

## 4. Image Specifications

Where each image lives, its file name, format and how a doc references it:
`${CLAUDE_PLUGIN_ROOT}/snippets/module-doc-references.md` § Images and § Manifest images. Every
screenshot size follows from the measured width of the slot it fills
(`${CLAUDE_PLUGIN_ROOT}/skills/_shared/doc-capture-mechanics.md` § Frame for the placement slot);
the module icon is the only fixed size.

| Asset | Size | Notes |
|---|---|---|
| Module icon (`static/description/icon.png`, PNG only) | the size and style of the series' core icons (`icon_gate.py facts`); the store resizes it | No manifest key needed - implicit path. Missing = ranking penalty. Language-neutral. |
| Cover | from the hero slot | Shown in the HERO and, as the first `images` entry, in the store's browse and grid views. A GIF carries an animated walkthrough. |
| Proof shots | from the WHAT-CHANGES slot | Inline in `index.html`; further `manifest['images']` entries feed the store carousel. |

---

## 5. Manifest Store Keys

Keys that drive store display or ranking. Never fabricate commercial values (`price`, `currency`,
`support`, `live_test_url`) - audit what the user provides and suggest; leave absent if unknown.

| Key | Type | Where displayed on store | Audit guidance |
|---|---|---|---|
| `name` | str | h1 on listing page + page title + store search | Max 25 chars (vendor guideline). No adjectives or company name prefix. |
| `summary` | str | Grid/browse teaser text (NOT on the detail page itself). Tagline source for `index.html` hero. | 1-2 sentences, outcome-first. Match to hero tagline in `index.html`. |
| `description` | str (RST) | Description tab fallback ONLY when `index.html` is absent | Store prefers `index.html`; RST-only incurs a ranking penalty. |
| `images` | list[str] | First entry = cover in browse/grid. Subsequent entries = store carousel. | At least one entry (ranking penalty if absent). Each entry per `${CLAUDE_PLUGIN_ROOT}/snippets/module-doc-references.md` § Manifest images (the English cover first). |
| `license` | str | License row in sidebar metadata table | Required (ranking penalty if missing). Common values: `LGPL-3`, `OPL-1`, `AGPL-3`. |
| `price` | float | Price display; determines Add-to-Cart vs Download button | Minimum 9 EUR if set. Absent or `<= 0` = free. DO NOT fabricate; ask user. |
| `currency` | str | Price display | `EUR` (default) or `USD` only. Audit: only set when `price` is set. |
| `support` | str | Shown to purchasers only (after purchase confirmation) | Email address the store shows only after purchase - the one place an address may live. Take it from the author profile (`support_email`); never fabricate, never copy it into the page. |
| `live_test_url` | str | "Live Preview" button on listing | Must point to a live, accessible demo instance. Verify before writing. |
| `application` | bool | Browsing category filter (standalone apps vs extensions) | `True` for top-level apps; `False` (default) for extension modules. |
| `category` | str | Browse navigation tree | Use `/` hierarchy (e.g. `Accounting / Localizations`). Check existing category tree on apps.odoo.com for valid values. |
| `maintainer` | str | Author/maintainer link in listing header (if different from `author`) | Separate from `author`; use when maintainer differs from original author. |
| `website` | str | Website row in sidebar metadata | Author/vendor URL. |
| `version` | str | Version badge (`v SERIES`) in sidebar | Format `SERIES.major.minor.patch` (e.g. `17.0.1.0.0`). SERIES stripped for display. |

---

## 6. i18n Conventions

**English is the mandatory canonical**: the final language set for any module documentation is
`{en_US}` union with all registry-resolved locales (`odoo-doc-illustration` § Language resolution).

| File | Role | Notes |
|---|---|---|
| `static/description/index.html` | English canonical - Description tab | No locale suffix. Always present. |
| `static/description/index_<locale>.html` | Localized Description tab | One file per non-English locale (e.g. `index_vi_VN.html`). Its images per `module-doc-references.md` § Images. |
| `doc/index.rst` | English canonical - Documentation tab | No locale suffix. Tab appears on listing only when this file exists. |
| `doc/index_<locale>.rst` | Localized Documentation tab | One file per non-English locale. |

Per-locale screenshots are captured separately; their location, their names and which one a
localized page shows follow `${CLAUDE_PLUGIN_ROOT}/snippets/module-doc-references.md` § Images.
The icon is language-neutral (one `icon.png`, no locale suffix).

**Tab split discipline**: marketing copy lives in `index.html`; the user guide for the business
roles (Overview, Setup, one chapter per role, Troubleshooting / FAQ) lives in `doc/index.rst`.
Nothing is duplicated between the two tabs.
