# App Store Template Reference

**Contents:** 1. Sanitizer Rules - 2. Section Map (the buyer's decision path) - 3. Bootstrap-5 Fragment Skeleton - 4. Images - 5. Manifest keys the page work touches - 6. Files per language

Assembly reference for `static/description/index.html` of an Odoo App Store listing.
`{{PRIMARY_HEX}}` is the `primary` of the brief's `BRAND`
(`${CLAUDE_PLUGIN_ROOT}/snippets/vendor-facts.md` § The palette is roles), else the Odoo palette
`#714B67` with bg-light `#F8F4F8`. It is the only brand colour of the page's fields and headings;
`secondary` marks an accent at most, a state colour only its state. A typeface never comes from
the palette: typography is Bootstrap-5 classes plus
inline `font-weight` / `font-size` only. `<SHARE_DIR>` is the captured absolute path
(`${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`), never the placeholder.

---

## 1. Sanitizer Rules (mandatory - violations are stripped silently)

| Rule | Detail |
|---|---|
| Fragment only | Start at `<section>`. NO `<!DOCTYPE>`, `<html>`, `<head>`, `<body>`. |
| No JavaScript | No `<script>` tags, no inline event handlers (`onclick`, `onmouseover`, etc.). |
| No external CDN links | No `<link>` tags (Bootstrap CDN, Google Fonts, Font Awesome CDN). The store pre-loads Bootstrap 5 - use its classes directly. The store's own rule (apps.odoo.com vendor guidelines): YouTube canonical links and Microsoft Teams links survive, every other external link is invalidated - the store rewrites the anchor to plain text and keeps its words. So an external link's visible text IS its URL (host and path, e.g. `support.acme-erp.com/tickets`), never a label such as "Open a ticket"; the reference gate's `LINK_TEXT_HIDES_URL` enforces it (a YouTube link is exempt: the store keeps it). |
| One carousel, nothing else that hides content | The store keeps Bootstrap 5 carousel markup (`carousel slide`, `carousel-inner`, `carousel-item`, the element's `id`, `data-bs-*` attributes) and loads the script that runs it. The INSIGHTS carousel of § 3 is the only one: no tab, no collapse, no second carousel. |
| No bare `<iframe>` | The store strips every `<iframe>`. A video is the Odoo website video container - `<div class="media_iframe_video" data-oe-expression="//www.youtube.com/embed/<id>?rel=0">` with the `<iframe>` as its child (§ 3 VIDEO): the store's own frontend rebuilds the iframe from `data-oe-expression` after stripping the child, and a marketplace that keeps the child renders it directly. YouTube only. |
| No address anywhere | No `mailto:`, no email address in text, alt or title, obfuscated or not: the page is public and indexed, addresses are harvested (`LINK_MAILTO`, `EMAIL_ADDRESS`). Contact goes through the author profile's pre-sales and support URLs (`${CLAUDE_PLUGIN_ROOT}/snippets/public-docs-contract.md`); an address the author insists on ships only as an image made by `${CLAUDE_PLUGIN_ROOT}/scripts/lib/email_image.py`, with an alt text that is not the address. |
| Bootstrap 5 for flexbox | Use `d-flex align-items-center justify-content-between gap-3`, `row`/`col-*` grid. Do NOT use inline `display:flex`, `align-items`, `justify-content`, `flex-wrap`, `flex-direction`, `gap` - all stripped. |
| Hex colors only | `background-color:#714B67`, `color:#ffffff`. No `rgba()`, no `linear-gradient` (both stripped). |
| HTML entities | `&rarr;` not `->`, `&mdash;` not `--`, `&copy;` not `(c)`, `&#10003;` for a check mark. Raw Unicode glyphs may corrupt on render. |
| Image paths and module links | Per `${CLAUDE_PLUGIN_ROOT}/snippets/module-doc-references.md`. |
| Safe inline styles | `background-color`, `color`, `font-weight`, `font-size`, `line-height`, `padding`, `margin`, `border`, `border-radius`, `width`, `height`, `max-width`, `text-align` survive. Prefer a Bootstrap 5 utility class wherever one exists (`gap-*`, `ratio`, `overflow-hidden`, `mb-3`). |
| Legacy oe_* classes | Still accepted. Keep them when the module already uses them; otherwise Bootstrap 5. Never both in one file. |

---

## 2. Section Map - the buyer's decision path

The buyer is a developer, a business owner or an Odoo consultant: expert, short of time and
allergic to being sold to. The page answers their questions in the order they ask them, then
stops. Reviews, ratings, the price, the version and the install or buy button are the store's
own: the page never imitates them, has no call-to-action section and names no Odoo or product
version anywhere in its visible text (`PAGE_NAMES_SERIES`).

Targets, enforced by the reference gate (`PAGE_TOO_LONG`, `PAGE_TOO_MANY_IMAGES`, `CAROUSEL_*`): at most 900
words of visible text, 8 images outside the INSIGHTS carousel and 5 slides in it; exactly three
WHAT-CHANGES blocks, five FAQ entries, at most 18 FEATURES lines.

Sources: `copy` = the block of that key in the marketing copy, written from the buyer profile;
`catalog` = `feature-catalog.jsonl`; `captures` = screenshots of the module's tasks; `manifest` =
the module descriptor; `brief` = a value the caller supplies; `dependents` = the vendor's own
installable modules whose `depends` names this one, listed by
`${CLAUDE_PLUGIN_ROOT}/scripts/lib/module_dependents.py <module> --addons-path <ADDONS_PATH>
--author "<manifest author>"`; `requirements` =
`${CLAUDE_PLUGIN_ROOT}/scripts/lib/module_requirements.py <module directory> --addons-path
<ADDONS_PATH>`.

| # | Key | ID | The buyer asks | Content | Source | Present |
|---|---|---|---|---|---|---|
| 1 | HERO | `#overview_block` | Is this what I am looking for? | One outcome sentence for the buyer persona (the result, never the module name), a "For <segment>" line, the tagline = manifest `summary`, a capture of the module's main screen; then the compatibility line - every edition the manifest supports, the license, the languages shipped | copy + manifest + captures | Always |
| 2 | WHAT-CHANGES | `#changes_block` | Does it fit my work? | Exactly three blocks "what changes for your team": the work as the team does it today, what it becomes, each tied to ONE verified catalog feature and ONE proof shot | copy + catalog + captures | Always |
| 3 | INSIGHTS | `#insights_block` | What will I see, to decide? | The module's reports and dashboards, for the owner and the managers: per report one capture taken on demo data that gives the chart or table a shape, titled with the management question it answers, and one sentence saying where its figures come from. One report: the image alone. Two to five: the carousel of § 3, the weightiest question first. More: the five weightiest, the others stay FEATURES lines. An index under the carousel lists every question | catalog (`type: report`) + captures | When the catalog holds a report |
| 4 | VIDEO | `#video_block` | Show me | One video narrated in the page's language, in the container of § 1 | brief | When such a video exists |
| 5 | FEATURES | `#features_block` | Does it cover my case? | The catalog as a list to scan: three to five groups named after an area of the user's work (never a menu or a model), one capability per line in the buyer's words, 14 words at most; then, last, one group of what the module guarantees beyond functions (access by role, multi-company, audit trail, behaviour on a weak connection, device) - facts verified like any other claim, the group omitted when there is none. No image | catalog | Always |
| 6 | DAY-ONE | `#day_one_block` | What do I have on day one? | What ships ready to use (data, templates, packs, connections) and what the administrator configures first - from the module's data files and the catalog, never a count or a duration the module does not state | catalog + manifest | When the source has content |
| 7 | EXTENSIONS | `#extensions_block` | What else can I add? | The vendor's optional extensions as cards - the display name linked in the root-relative store form of `${CLAUDE_PLUGIN_ROOT}/snippets/module-doc-references.md` § Links to another module, one or two sentences of the outcome from that module's manifest `summary` or catalog; only modules the `dependents` source lists, up to 6, the ones the buyer needs next first, the rest in the report; no price figure anywhere | dependents | When `dependents` lists a module |
| 8 | FAQ | `#faq_block` | What could go wrong? | Exactly five questions a buyer asks before paying - where the data goes, how cost is controlled, who sees what, what it takes to run or extend it - each answered plainly; a real limit stated as a fact earns more trust than a claim | copy | Always |
| 9 | TRY-AND-SUPPORT | `#support_block` | How do I evaluate it, whom do I ask? | The evaluation path (the Documentation tab, `live_test_url` when the manifest has one, the video) and two contact cards, pre-sales `{{PRESALES_URL}}` and technical support `{{SUPPORT_URL}}`, from the author profile; a card whose URL the profile lacks is omitted and reported as a gap, never filled | brief + author profile | When the source has content |
| 10 | TECH | `#requirement_block` | What must be installed on the server? | Only what the module needs beyond Odoo itself: the Python packages and system programs the `requirements` source prints | requirements | When `requirements` prints `TECH_SECTION=yes` |

Page order is table order; every section is full width, one column, no tab block (a tab hides
content and the buyer does not click to find out). The INSIGHTS carousel stands without a click:
its first slide and its index are on the page, and it never starts by itself. A section whose condition is not met is
omitted, never left as a placeholder.

**Voice.** Calm, specific, evidence-led; outcome before feature; the buyer's words, never a class,
field or model name (unless the buyers are developers and the technical names are the value). No
heading that pushes ("reasons to buy", "buy now", "limited", "best", "most powerful"), no urgency,
no superlative, no invented customer, number, testimonial or certification; a claim with no source
is not written. Present tense, no history.

---

## 3. Bootstrap-5 Fragment Skeleton

Replace `{{PLACEHOLDER}}` values: `{{PRIMARY_HEX}}` per the header, every other placeholder from
the source its Section Map row names (§ 2).

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
  <!-- The module's main screen - the widest image slot: measure its rendered width and frame the
       shot per doc-capture-mechanics.md § Frame for the placement slot. Never the store cover:
       the store shows that one above the page -->
  <div class="row mt-4">
    <div class="col-md-10 offset-md-1 text-center" style="border-radius:20px;padding:3px;background-color:{{PRIMARY_HEX}};">
      <img alt="{{what the screen shows}}" class="img-fluid" loading="lazy" src="./assets/{{SCREEN_FILE}}"
           style="border-radius:15px;display:block;width:100%;height:auto;">
    </div>
  </div>
  <!-- Compatibility line: what a consultant checks first. No version: the store states it -->
  <p class="text-center mt-3 mb-0" style="font-size:14px;color:#666;">
    {{EDITIONS - each edition the manifest supports}} &middot; {{LICENSE}} &middot; {{LANGUAGES - the locales the module ships translations for}}
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

<!-- INSIGHTS - omit the section when the catalog holds no report. One report: its image, title
     and sentence alone, no carousel and no index -->
<section id="insights_block" class="py-4">
  <div style="background-color:#f8f8f8;padding:40px;border-radius:15px;">
    <h2 class="text-center mb-4" style="font-size:30px;font-weight:bold;">What you see as a manager</h2>
    <!-- No data-bs-ride: a reader needs time to read a chart. Exactly one item is active -->
    <div id="insights_carousel" class="carousel carousel-dark slide" data-bs-interval="false">
      <div class="carousel-inner">
        <!-- One item per report, two to five, the weightiest question first -->
        <div class="carousel-item active">
          <img alt="{{QUESTION}}" class="d-block w-100" loading="lazy" src="./assets/{{REPORT_FILE}}"
               style="border-radius:15px;height:auto;">
          <p class="text-center mt-3 mb-1" style="font-size:20px;font-weight:700;">{{QUESTION - the management question this report answers}}</p>
          <p class="text-center mb-0" style="font-size:15px;color:#666;">{{SOURCE - where its figures come from, one sentence}}</p>
        </div>
      </div>
      <a class="carousel-control-prev" href="#insights_carousel" role="button" data-bs-slide="prev">
        <span class="carousel-control-prev-icon"></span>
      </a>
      <a class="carousel-control-next" href="#insights_carousel" role="button" data-bs-slide="next">
        <span class="carousel-control-next-icon"></span>
      </a>
    </div>
    <!-- The index: one entry per slide, in slide order; it names every report where the script
         does not run -->
    <div class="row g-2 mt-3">
      <div class="col-md-4">
        <a href="#insights_carousel" data-bs-target="#insights_carousel" data-bs-slide-to="0"
           class="d-block p-2" style="background-color:#fff;border:1px solid #e8e8e8;border-radius:8px;color:#333;font-size:14px;">{{QUESTION}}</a>
      </div>
    </div>
  </div>
</section>

<!-- VIDEO - omit the section when no video narrated in the page's language exists -->
<section id="video_block" class="py-4">
  <div style="background-color:#f4f8ff;border-radius:20px;padding:40px 24px;">
    <div class="mx-auto text-center" style="max-width:960px;">
      <h2 style="font-size:28px;font-weight:bold;">{{VIDEO_TITLE - what the viewer sees}}</h2>
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

<!-- FEATURES -->
<section id="features_block" class="py-4">
  <div style="background-color:#f8f8f8;padding:40px;border-radius:15px;">
    <h2 class="text-center mb-4" style="font-size:30px;font-weight:bold;">Features</h2>
    <div class="row g-4">
      <!-- One column per group, three to five groups -->
      <div class="col-md-6 col-lg-4">
        <h3 style="font-size:17px;font-weight:700;color:{{PRIMARY_HEX}};">{{GROUP - an area of the user's work}}</h3>
        <ul style="list-style:none;padding-left:0;margin-bottom:0;">
          <li class="py-1" style="font-size:14px;">&#10003; {{ONE CAPABILITY - one line}}</li>
        </ul>
      </div>
    </div>
    <!-- Last, only when the module has such facts: what it guarantees beyond functions -->
    <div class="bg-white rounded p-4 mt-4" style="border:1px solid #e8e8e8;">
      <h3 style="font-size:17px;font-weight:700;color:{{PRIMARY_HEX}};">{{GROUP TITLE - e.g. "Built for daily use"}}</h3>
      <div class="row">
        <div class="col-md-6">
          <ul style="list-style:none;padding-left:0;margin-bottom:0;">
            <li class="py-1" style="font-size:14px;">&#10003; {{ONE VERIFIED FACT - one line}}</li>
          </ul>
        </div>
      </div>
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

<!-- EXTENSIONS - only modules module_dependents.py listed, up to 6 -->
<section id="extensions_block" class="py-4">
  <div style="background-color:#f8f8f8;padding:40px;border-radius:15px;">
    <h2 class="text-center mb-4" style="font-size:30px;font-weight:bold;">Extend it</h2>
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

<!-- TECH - only when module_requirements.py prints TECH_SECTION=yes -->
<section id="requirement_block" class="py-4">
  <div style="background:#f4f4f4;padding:40px;border-radius:15px;">
    <h2 class="text-center mb-4" style="font-size:30px;font-weight:bold;">Technical requirements</h2>
    <div class="p-3 bg-white rounded">
      <ul style="list-style:none;padding-left:0;margin-bottom:0;">
        <li class="py-2"><strong>Python packages to install:</strong> {{PYTHON_EXTRA}}</li>
        <li class="py-2"><strong>System programs:</strong> {{BIN}}</li>
      </ul>
    </div>
  </div>
</section>
```

---

## 4. Images

Where each image lives, its file name, format and how a doc references it:
`${CLAUDE_PLUGIN_ROOT}/snippets/module-doc-references.md` § Images and § Manifest images. Every
screenshot size follows from the measured width of the slot it fills
(`${CLAUDE_PLUGIN_ROOT}/skills/_shared/doc-capture-mechanics.md` § Frame for the placement slot).

| Asset | Made by | Notes |
|---|---|---|
| Module icon (`static/description/icon.png`, PNG only) | `odoo-icon-design` | Implicit path, no manifest key. Missing = ranking penalty. Language-neutral. |
| Store cover (`static/description/main_screenshot.png`) | `odoo-icon-design`, cover mode | The first `images` entry: a designed product cover at 2:1, shown by a store in its lists and above the page (the Odoo Apps Store shows this one image and crops it to 2:1). Not embedded in the page. |
| Main screen, proof shots, report shots | the page's own captures | Inline in `index.html`, under `assets/`. A report is captured as the manager opens it - grouped, filtered and measured to answer its question - on demo data that gives it a shape; an empty report is not captured. |

---

## 5. Manifest keys the page work touches

Never fabricate a commercial value (`price`, `currency`, `live_test_url`): report it missing.

| Key | Rule |
|---|---|
| `summary` | The hero tagline matches it: one or two sentences, outcome-first. |
| `images` | The first entry is the store cover (§ 4): the page work never writes it. The entries after it are the page's English captures of the module's main screens, per `${CLAUDE_PLUGIN_ROOT}/snippets/module-doc-references.md` § Manifest images: the page work writes them, and replaces them when it recaptures those screens. |
| `support` | An email address the store shows to purchasers only - the one place an address may live. From the author profile (`support_email`) when the manifest has none; never copied into the page. |
| `live_test_url` | Named in TRY-AND-SUPPORT when present; never written. |
| The video link | The watch URL of the page's video goes into the manifest key the vendor's other modules use for a video link (a key whose value is a video URL; per-locale variants spelled as those manifests spell them). No module of the vendor has one: leave the manifest as it is and return the question. |
| `license`, `icon.png`, the cover | Missing: listed as a store-readiness gap in the report. |

---

## 6. Files per language

| File | Role |
|---|---|
| `static/description/index.html` | English, canonical - the Description tab. Always present. |
| `static/description/index_<locale>.html` | The Description tab in another language, with that language's captures and video. |
| `doc/index.rst`, `doc/index_<locale>.rst` | The Documentation tab - the user guide, never repeated on this page. |
