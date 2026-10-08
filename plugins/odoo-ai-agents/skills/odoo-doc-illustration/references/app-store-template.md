# App Store Template Reference

Runtime reference for assembling `static/description/index.html` and related assets for
an Odoo App Store listing. Brand-agnostic - the PALETTE placeholder resolves from
`<SHARE_DIR>/brand-tokens.json` when that file exists, else from user input; absent both, the
default is the Odoo palette `#714B67`. That file is a map of CSS custom-property NAME -> COLOUR
(e.g. `{ "--primary": "#1E88E5" }`; schema SSOT:
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-frontend-fidelity.md` § Brand-token fidelity), so read it
by VALUE: an unfamiliar token NAME is NEVER a miss - take the colour that entry maps to instead of
declaring the tier unresolved and shipping off-brand output.

**A TYPEFACE never comes from that map, and this template has no font placeholder.** The sanitizer
strips `<link>` / CDN / web-font loading, and `font-family` is absent from its safe inline-style set,
so typography is Bootstrap-5 classes plus safe inline `font-weight` / `font-size` only.

`brand-tokens.json` is Tier-2 SHARE; resolve `<SHARE_DIR>`
via the resolve-capture-substitute protocol in
`${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md` and substitute the captured absolute path
into every Read - never the placeholder or a bare `.odoo-ai/`.

---

## 1. Sanitizer Rules (mandatory - violations are stripped silently)

| Rule | Detail |
|---|---|
| Fragment only | Start at `<section>`. NO `<!DOCTYPE>`, `<html>`, `<head>`, `<body>`. The store injects the file into its own Jinja template. |
| No JavaScript | No `<script>` tags, no inline event handlers (`onclick`, `onmouseover`, etc.). CSP strips all JS. |
| No external CDN links | No `<link>` tags (Bootstrap CDN, Google Fonts, Font Awesome CDN). The store pre-loads Bootstrap 5 - use its classes directly. Permitted embeds: YouTube `youtube.com/embed/`, `mailto:`, `skype:` |
| Bootstrap 5 for flexbox | Use `d-flex align-items-center justify-content-between gap-3`, `row`/`col-*` grid. Do NOT use inline `display:flex`, `align-items`, `justify-content`, `flex-wrap`, `flex-direction`, `gap` - all stripped. |
| Hex colors only | `background-color:#714B67`, `color:#ffffff`. No `rgba()`, no `linear-gradient` (both stripped). |
| HTML entities | `&rarr;` not `->`, `&mdash;` not `--`, `&copy;` not `(c)`. Raw Unicode glyphs may corrupt on render. |
| Image paths and module links | Per `${CLAUDE_PLUGIN_ROOT}/snippets/module-doc-references.md`. |
| Safe inline styles | `background-color`, `color`, `font-weight`, `font-size`, `line-height`, `padding`, `margin`, `border`, `border-radius`, `width`, `height`, `max-width`, `text-align` survive. |
| Legacy oe_* classes | Still accepted. Use for OCA-style modules. New modules: prefer Bootstrap 5. Do not mix both in the same file. |

> **Caveat - the "Safe inline styles" set is store-accepted but a known-incomplete list.** It is
> empirically derived from accepted listings, not from a published store allowlist; treat it as a
> minimum-safe set. Prefer Bootstrap 5 utility classes over inline styles wherever a class exists
> (e.g. `gap-*`, `ratio`, `overflow-hidden`, `mb-3`) - the skeleton below uses inline `max-width`
> only where no Bootstrap utility maps cleanly. Do NOT add inline flexbox/`gap`/`position`/`display:flex`
> (all stripped); those are the rows above.

---

## 2. Section Map (marketing, `index.html` = Description tab)

The SSOT for the landing's sections, their order, and the `<!-- <KEY> -->` marker that labels each
one - in the copy `odoo-content-draft` returns and in the skeleton below. Source: `copy` = the
block of that key in the supplied marketing copy, written from the buyer profile; `catalog` =
`feature-catalog.jsonl`; `captures` = screenshots of the module's tasks; `manifest` = the module
descriptor; `brief` = a value the caller supplies or the module already states (e.g. the manifest
`support` key). A `Yes` section is always present; omit a `Recommended` or `Optional` section whose
source is empty rather than leaving placeholders.

| # | Key | ID | Content | Source | Required |
|---|---|---|---|---|---|
| 1 | HERO | `#overview_block` | Outcome headline + a "For <segment>" line + tagline matching manifest `summary` + the cover `main_screenshot` | copy | Yes |
| 2 | PAINS | `#pains_block` | "Is this you?" - 3-5 pains of the buying committee, in its own words | copy | Yes |
| 3 | OUTCOMES | `#benefit_block` | Each pain -> the outcome the module delivers | copy | Yes |
| 4 | HOW-IT-WORKS | `#process_block` | The process stages and the role acting at each, from the role map `process` | copy | Recommended |
| 5 | KEY-FEATURES | `#key_features_block` | `row`/`col-md-6 col-lg-4` cards: icon + capability title + user-outcome body (1-2 sentences). 3-6 features. | catalog | Yes |
| 6 | WHO-ITS-FOR | `#target_users_block` | One card per buying-committee member (who + pain + gain), then the Best for line | copy | Yes |
| 7 | SCREENS | `#feature` (tab) | Alternating sections: `col-xl-4` task title + `col-xl-8` task screenshot. Caption = human task name, not a technical path. | captures | Recommended |
| 8 | DEMO | `#demo` (tab) | YouTube embed (16:9, canonical `youtube.com/embed/` format) + user-manual and live-demo links | brief | Optional |
| 9 | FAQ | `#faq` (tab) | Answers to the buying committee's top objections | copy | Recommended |
| 10 | SUPPORT | `#support` (tab) | Two contact cards: pre-sales + technical support | brief | Recommended |
| 11 | TECH-REQUIREMENTS | `#requirement` (tab) | Series, supported editions, required modules, license | manifest | Recommended |
| 12 | CHANGELOG | `#changelog` (tab) | Chronological list: date + badge (New / Improved / Fixed) + description | brief | Optional |

HERO through WHO-ITS-FOR run as full-width sections in that order; SCREENS through CHANGELOG share
one tab block (`<ul class="nav nav-tabs">`) after them. There is no call-to-action section - the
store renders its own install / buy button.

**Tone rule**: every section is buyer-facing and value-first. Never open with "This module extends
X to support Y" or expose Python class names / field technical names in headings.

---

## 3. Bootstrap-5 Fragment Skeleton (brand-agnostic)

Replace `{{PLACEHOLDER}}` values: `{{PRIMARY_HEX}}` from `<SHARE_DIR>/brand-tokens.json` (by VALUE -
see the header), every other placeholder from the source its Section Map row names (§2).
Default palette when that file is absent: primary `#714B67`, accent `#714B67`, bg-light `#F8F4F8`.

```html
<!-- static/description/index.html - FRAGMENT ONLY, no html/head/body -->
<!-- Bootstrap 5 already loaded by the store; do NOT add <link> CDN tags -->
<!-- Each section opens with its Section Map key (§2) -->

<!-- HERO -->
<section id="overview_block" style="margin-top:1.5rem;margin-bottom:1.5rem;">
  <!-- Banner card -->
  <div class="rounded p-4" style="background-color:{{PRIMARY_HEX}};border-radius:15px;">
    <!-- Compatibility badges row -->
    <div class="row mx-0 p-3 align-items-center"
         style="border-radius:15px;background-color:#f8f8f8;">
      <div class="col-lg-4 text-center text-lg-start p-2">
        <!-- Replace with vendor logo img or text -->
        <strong style="font-size:20px;color:{{PRIMARY_HEX}};">{{VENDOR_NAME}}</strong>
      </div>
      <div class="col-lg-8 p-3 d-flex flex-wrap justify-content-end gap-2">
        <!-- Add one button per supported edition -->
        <div class="btn" style="border-radius:10px;color:#fff;
             background-color:{{PRIMARY_HEX}};padding:10px 20px;">
          Odoo Community
        </div>
      </div>
    </div>
    <!-- Outcome headline + segment + tagline -->
    <div class="row mt-4 text-center">
      <div class="col-md-12">
        <h1 style="color:#fff;font-weight:700;font-size:34px;margin-bottom:10px;">
          {{OUTCOME_HEADLINE - the result the buyer gets, not the module name}}
        </h1>
        <p style="color:#fff;font-size:16px;font-weight:600;margin-bottom:8px;">
          For {{SEGMENT - from the buyer profile}}
        </p>
        <p class="mx-auto"
           style="color:#fff;font-size:18px;line-height:26px;max-width:78%;margin-bottom:16px;">
          {{TAGLINE - matches manifest summary, outcome-first, 15 words max}}
        </p>
      </div>
    </div>
  </div>
  <!-- Hero screenshot - the widest image slot: measure its rendered width and frame the shot per
       capture-mechanics.md § Frame for the placement slot -->
  <div class="row mt-4">
    <div class="col-md-10 offset-md-1 text-center"
         style="border-radius:20px;padding:3px;background-color:{{PRIMARY_HEX}};">
      <img alt="{{MODULE_DISPLAY_NAME}}" class="img-fluid" loading="lazy"
           src="./main_screenshot.gif"
           style="border-radius:15px;display:block;width:100%;height:auto;">
    </div>
  </div>
</section>

<!-- PAINS -->
<section id="pains_block" class="py-4">
  <div style="background-color:#f8f8f8;padding:40px;border-radius:15px;">
    <h2 class="text-center mb-4" style="font-size:32px;font-weight:bold;">Is this you?</h2>
    <div class="bg-white rounded" style="padding:24px;border:1px solid #e8e8e8;">
      <!-- Repeat per pain (3-5 items), in the buying committee's own words -->
      <div class="d-flex align-items-start p-2 gap-2">
        <span style="font-size:20px;color:{{PRIMARY_HEX}};margin-top:2px;">&#8227;</span>
        <p class="mb-0" style="font-size:15px;">{{PAIN}}</p>
      </div>
    </div>
  </div>
</section>

<!-- OUTCOMES -->
<section id="benefit_block" class="py-4">
  <div style="background-color:#f4f4f4;padding:40px;border-radius:15px;">
    <h2 class="text-center mb-4" style="font-size:32px;font-weight:bold;">What changes</h2>
    <div class="row g-4">
      <!-- Repeat per pain: the pain, then the outcome the module delivers -->
      <div class="col-md-6">
        <div class="bg-white rounded p-4 h-100" style="border:1px solid #e8e8e8;">
          <p class="mb-2" style="font-size:14px;color:#666;">{{PAIN}}</p>
          <p class="mb-0" style="font-size:16px;font-weight:600;">
            &rarr; {{OUTCOME - the buyer's result, action verb first}}
          </p>
        </div>
      </div>
    </div>
  </div>
</section>

<!-- HOW-IT-WORKS -->
<section id="process_block" class="py-4">
  <div style="background-color:#f8f8f8;padding:40px;border-radius:15px;">
    <h2 class="text-center mb-4" style="font-size:32px;font-weight:bold;">How it works</h2>
    <div class="row g-4">
      <!-- Repeat per process stage, in stage order -->
      <div class="col-md-6 col-lg-3">
        <div class="bg-white rounded p-4 h-100" style="border-top:4px solid {{PRIMARY_HEX}};">
          <div style="font-size:24px;font-weight:700;color:{{PRIMARY_HEX}};">{{STAGE_NUMBER}}</div>
          <h4 style="font-size:16px;font-weight:700;">{{STAGE_NAME}}</h4>
          <p class="mb-0" style="font-size:14px;">
            {{BUSINESS_ROLE}} {{what they do at this stage, and who the record goes to next}}
          </p>
        </div>
      </div>
    </div>
  </div>
</section>

<!-- KEY-FEATURES -->
<section id="key_features_block" class="py-4">
  <div style="background-color:#f4f4f4;padding:40px;border-radius:15px;">
    <h2 class="text-center mb-4"
        style="font-size:32px;font-weight:bold;">Key Features</h2>
    <div class="row g-4">
      <!-- Repeat per feature (3-6 total) -->
      <div class="col-md-6 col-lg-4 d-flex">
        <div class="d-flex align-items-start flex-fill"
             style="padding:24px;border-radius:12px;background:#fff;
                    border:1px solid #e8e8e8;">
          <!-- Icon: use a Unicode entity or inline SVG, not an external icon font CDN -->
          <div class="me-3">
            <span style="font-size:28px;color:{{PRIMARY_HEX}};">&#9881;</span>
          </div>
          <div>
            <h4 style="font-size:16px;font-weight:600;">{{FEATURE_TITLE}}</h4>
            <p class="mb-0" style="font-size:14px;">
              {{FEATURE_BODY - what the user sees/gets, 1-2 sentences, no code names}}
            </p>
          </div>
        </div>
      </div>
      <!-- /feature card -->
    </div>
  </div>
</section>

<!-- WHO-ITS-FOR -->
<section id="target_users_block" class="py-4">
  <div style="background-color:#f8f8f8;padding:40px;border-radius:15px;">
    <h2 class="text-center mb-4"
        style="font-size:30px;font-weight:bold;">Who it is for</h2>
    <div class="row g-4">
      <!-- Repeat per buying-committee member: who they are + their pain + what they gain -->
      <div class="col-md-6 col-lg-3">
        <div class="bg-white rounded p-4 h-100"
             style="border-top:4px solid {{PRIMARY_HEX}};">
          <h4 style="font-size:16px;font-weight:700;">{{MEMBER_WHO}}</h4>
          <p class="mb-0" style="font-size:14px;">{{MEMBER_PAIN_AND_GAIN}}</p>
        </div>
      </div>
    </div>
    <p class="text-center mt-4 mb-0" style="font-size:16px;">
      <strong>Best for:</strong> {{BEST_FOR}}
    </p>
  </div>
</section>

<!-- Tab block: SCREENS / DEMO / FAQ / SUPPORT / TECH-REQUIREMENTS / CHANGELOG.
  nav-tabs rely on Bootstrap 5 JS. `data-bs-toggle="tab"` is a JS-driven behavior, NOT pure
  CSS - it does NOT work without Bootstrap JS. It works here only because the store PRELOADS
  Bootstrap JS (verified on live listings); you still ship NO <script> of your own (CSP strips it).
  Drop the nav item of every tab section you omit. -->
<div id="tabs" class="container px-0">
  <ul class="nav nav-tabs justify-content-center bg-white py-2"
      id="moduleTab" role="tablist"
      style="border-radius:6px 6px 0 0;">
    <li class="nav-item">
      <a class="nav-link active" data-bs-toggle="tab" href="#feature" role="tab">
        Screenshots
      </a>
    </li>
    <li class="nav-item">
      <a class="nav-link" data-bs-toggle="tab" href="#demo" role="tab">Demo</a>
    </li>
    <li class="nav-item">
      <a class="nav-link" data-bs-toggle="tab" href="#faq" role="tab">FAQ</a>
    </li>
    <li class="nav-item">
      <a class="nav-link" data-bs-toggle="tab" href="#support" role="tab">Support</a>
    </li>
    <li class="nav-item">
      <a class="nav-link" data-bs-toggle="tab" href="#requirement" role="tab">
        Technical Requirement
      </a>
    </li>
    <li class="nav-item">
      <a class="nav-link" data-bs-toggle="tab" href="#changelog" role="tab">
        Changelog
      </a>
    </li>
  </ul>
</div>
<div class="tab-content" id="moduleTabContent">

  <!-- SCREENS -->
  <div class="tab-pane fade show active" id="feature" role="tabpanel">
    <!-- Repeat per screenshot; alternate background colors for visual rhythm -->
    <section class="py-4">
      <div style="background-color:#f4f4f4;padding:32px;border-radius:15px;">
        <div class="row align-items-center">
          <div class="col-md-12 col-xl-4">
            <h3 style="font-weight:700;font-size:22px;line-height:30px;">
              {{FEATURE_TASK_TITLE - human task name, e.g. "Submit an Approval Request"}}
            </h3>
          </div>
          <div class="col-md-12 col-xl-8 mt-3 mt-xl-0 d-flex justify-content-center">
            <!-- Feature slot: measure its rendered width and frame the shot per
                 capture-mechanics.md § Frame for the placement slot -->
            <!-- {{SCREEN_FILE}} = this screen's file, named per module-doc-references.md § Images -->
            <img alt="{{FEATURE_TASK_TITLE}}" class="img-fluid" loading="lazy"
                 src="./{{SCREEN_FILE}}"
                 style="border-radius:15px;width:100%;height:auto;">
          </div>
        </div>
      </div>
    </section>
  </div>

  <!-- DEMO -->
  <div class="tab-pane fade" id="demo" role="tabpanel">
    <section class="py-4">
      <div style="background-color:#f4f8ff;border-radius:20px;padding:40px 24px;">
        <div style="max-width:960px;margin:0 auto;background:#fff;
                    border-radius:18px;padding:32px;text-align:center;">
          <h3 style="font-size:22px;font-weight:700;">
            See {{MODULE_DISPLAY_NAME}} in Action
          </h3>
          <!-- YouTube embed only (permitted CDN). Replace VIDEO_ID. -->
          <!-- Bootstrap 5 `.ratio` supplies the 16:9 box; position/padding-top/overflow/inset
               are handled by Bootstrap classes (`.ratio > *` is sized automatically), NOT by
               stripped inline flex/position styles. -->
          <div class="ratio ratio-16x9 overflow-hidden mb-3" style="border-radius:14px;">
            <iframe src="https://www.youtube.com/embed/{{VIDEO_ID}}"
                    title="Demo video" frameborder="0"
                    allow="accelerometer;autoplay;clipboard-write;
                           encrypted-media;gyroscope;picture-in-picture"
                    allowfullscreen>
            </iframe>
          </div>
          <!-- Optional: user-manual + live-demo links -->
        </div>
      </div>
    </section>
  </div>

  <!-- FAQ -->
  <div class="tab-pane fade" id="faq" role="tabpanel">
    <section class="py-4">
      <div style="background:#f8f8f8;padding:40px;border-radius:15px;">
        <h2 class="text-center mb-4"
            style="font-size:30px;font-weight:bold;">Frequently Asked Questions</h2>
        <!-- Repeat per objection: the question as the buyer asks it, then the answer -->
        <div class="bg-white rounded mb-3" style="padding:18px 24px;border:1px solid #e8e8e8;">
          <h4 style="font-size:16px;font-weight:700;">{{QUESTION}}</h4>
          <p class="mb-0" style="font-size:14px;">{{ANSWER}}</p>
        </div>
      </div>
    </section>
  </div>

  <!-- SUPPORT -->
  <div class="tab-pane fade" id="support" role="tabpanel">
    <section class="py-4">
      <div style="padding:40px;border-radius:15px;background-color:#f8f8f8;">
        <h2 class="text-center"
            style="font-size:30px;font-weight:bold;">
          Need help with {{MODULE_DISPLAY_NAME}}?
        </h2>
        <div class="row mt-4">
          <div class="col-lg-6 col-md-12 mb-4">
            <div style="background:#f4f4f4;padding:32px;border-radius:15px;">
              <h3>Pre-Sales &amp; Partnership</h3>
              <!-- Replace with actual pre-sales contact -->
              <a href="mailto:{{PRESALES_EMAIL}}">{{PRESALES_EMAIL}}</a>
            </div>
          </div>
          <div class="col-lg-6 col-md-12 mb-4">
            <div style="background:#fff;padding:32px;border-radius:15px;
                        border:1px solid #e8e8e8;">
              <h3>Technical Support</h3>
              <!-- Replace with actual support contact -->
              <a href="mailto:{{SUPPORT_EMAIL}}">{{SUPPORT_EMAIL}}</a>
            </div>
          </div>
        </div>
      </div>
    </section>
  </div>

  <!-- TECH-REQUIREMENTS -->
  <div class="tab-pane fade" id="requirement" role="tabpanel">
    <section class="py-4">
      <div style="background:#f8f8f8;padding:40px;border-radius:15px;">
        <h2 class="text-center mb-4"
            style="font-size:30px;font-weight:bold;">Technical Requirement</h2>
        <div class="p-3 bg-white rounded">
          <ul style="list-style:none;padding-left:0;margin-bottom:0;">
            <li class="py-2">
              <strong>Odoo version:</strong> {{SERIES - the module's series}}
            </li>
            <li class="py-2">
              <strong>Editions:</strong> {{each edition the module supports}}
            </li>
            <li class="py-2">
              <strong>Required modules:</strong> {{depends list from manifest}}
            </li>
            <li class="py-2">
              <strong>License:</strong> {{manifest license key}}
            </li>
          </ul>
        </div>
      </div>
    </section>
  </div>

  <!-- CHANGELOG -->
  <div class="tab-pane fade" id="changelog" role="tabpanel">
    <section class="py-4">
      <div style="background:#f8f8f8;padding:40px;border-radius:15px;">
        <h2 class="text-center mb-3"
            style="font-size:30px;font-weight:bold;">Changelog</h2>
        <div class="bg-white rounded" style="padding:18px 24px;">
          <ul style="list-style:none;padding-left:0;margin-bottom:0;">
            <!-- Per entry: date + badge type + description -->
            <!-- Badge types: New (#e6f9ef), Improved (#e8f4fb), Fixed (#fff4e5) -->
            <li class="py-2 d-flex align-items-start gap-2">
              <span style="font-size:13px;color:#666;white-space:nowrap;">
                {{YYYY-MM-DD}}
              </span>
              <span style="border-radius:6px;padding:2px 8px;font-size:12px;
                           font-weight:600;background:#e6f9ef;color:#00864a;">
                New
              </span>
              <span style="font-size:14px;">{{CHANGE_DESCRIPTION}}</span>
            </li>
          </ul>
        </div>
      </div>
    </section>
  </div>

</div><!-- /tab-content -->
```

---

## 4. Image Specifications

Where each image lives, its file name and how a doc references it:
`${CLAUDE_PLUGIN_ROOT}/snippets/module-doc-references.md` § Images and § Manifest images. Every
screenshot size follows from the measured width of the slot it fills
(`${CLAUDE_PLUGIN_ROOT}/skills/odoo-doc-illustration/references/capture-mechanics.md` § Frame for the
placement slot); the module icon is the only fixed size.

| Asset | File | Format | Size | Notes |
|---|---|---|---|---|
| Module icon | `static/description/icon.png` | PNG only | 256x256 px | No manifest key needed - implicit path. Missing = ranking penalty. Language-neutral. |
| Cover / hero | `static/description/main_screenshot.<ext>` | PNG, GIF, or JPEG | from the hero slot | `manifest['images'][0]` and the first image of `index.html`: the cover in store browse/grid views, shown enlarged because its name ends with `_screenshot`. A GIF carries an animated walkthrough. |
| Screens | `static/description/<slug>.<ext>` | PNG, GIF, or JPEG | from the feature slot | Inline in `index.html`. Extra `manifest['images']` entries feed the store carousel; inline-only images do not appear in grid views. |

---

## 5. Manifest Store Keys

Keys that drive store display or ranking. Never fabricate commercial values (`price`, `currency`,
`support`, `live_test_url`) - audit what the user provides and suggest; leave as `None`/absent if
unknown.

| Key | Type | Where displayed on store | Audit guidance |
|---|---|---|---|
| `name` | str | h1 on listing page + page title + store search | Max 25 chars (vendor guideline). No adjectives or company name prefix. |
| `summary` | str | Grid/browse teaser text (NOT on the detail page itself). Tagline source for `index.html` hero. | 1-2 sentences, outcome-first. Match to hero tagline in `index.html`. |
| `description` | str (RST) | Description tab fallback ONLY when `index.html` is absent | Store prefers `index.html`; RST fallback incurs ranking penalty. Keep for text-only fallback. |
| `images` | list[str] | First entry = cover in browse/grid. Subsequent entries = store carousel. | Must have at least one entry (ranking penalty if absent). Each entry per `${CLAUDE_PLUGIN_ROOT}/snippets/module-doc-references.md` § Manifest images (e.g. `static/description/main_screenshot.gif` for the English cover). |
| `license` | str | License row in sidebar metadata table | Required (ranking penalty if missing). Common values: `LGPL-3`, `OPL-1`, `AGPL-3`. |
| `price` | float | Price display; determines Add-to-Cart vs Download button | Minimum 9 EUR if set. Absent or `<= 0` = free. DO NOT fabricate; ask user. |
| `currency` | str | Price display | `EUR` (default) or `USD` only. Audit: only set when `price` is set. |
| `support` | str | Shown to purchasers only (after purchase confirmation) | Email address. DO NOT fabricate; ask user. |
| `live_test_url` | str | "Live Preview" button on listing | Must point to a live, accessible demo instance. Verify before writing. |
| `application` | bool | Browsing category filter (standalone apps vs extensions) | `True` for top-level apps; `False` (default) for extension modules. |
| `category` | str | Browse navigation tree | Use `/` hierarchy (e.g. `Accounting / Localizations`). Check existing category tree on apps.odoo.com for valid values. |
| `maintainer` | str | Author/maintainer link in listing header (if different from `author`) | Separate from `author`; use when maintainer differs from original author. |
| `website` | str | Website row in sidebar metadata | Author/vendor URL. |
| `version` | str | Version badge (`v SERIES`) in sidebar | Format `SERIES.major.minor.patch` (e.g. `17.0.1.0.0`). SERIES stripped for display. |

**Ranking score** (5-point system; each missing item = penalty):

1. Missing `static/description/icon.png`
2. Missing cover image (`images` key empty or absent)
3. `license` not set
4. Star rating below 3.0 (ongoing)
5. No HTML description (RST-only = penalized; `index.html` = preferred)

---

## 6. i18n Conventions

**English is the mandatory canonical** (project rule): the final language set for any module
documentation is `{en_US}` union with all registry-resolved locales. English is always included
even if the registry omits it.

| File | Role | Notes |
|---|---|---|
| `static/description/index.html` | English canonical - Description tab | No locale suffix. Always present. |
| `static/description/index_<locale>.html` | Localized Description tab | One file per non-English locale (e.g. `index_vi_VN.html`). Each references its own locale-suffixed images. |
| `doc/index.rst` | English canonical - Documentation tab | No locale suffix. Tab appears on listing only when this file exists. |
| `doc/index_<locale>.rst` | Localized Documentation tab | One file per non-English locale. |

**Language resolver order.** SSOT: this skill's own Language resolution section (4-tier +
disk-UNION, no default) - do not restate the tier order or the disk-UNION rule here; that section
is authoritative and this file cross-references it.

**Screenshot localization**: per-locale screenshots are captured separately. English canonical
has NO suffix (`<slug>.<ext>`, `main_screenshot.<ext>`); every non-English locale appends
`.<locale>` (`<slug>.<locale>.<ext>`, `main_screenshot.<locale>.<ext>`). Each locale's HTML
references only its own images. Icon is language-neutral (one `icon.png`, no locale suffix).

**Tab split discipline**: keep marketing copy in `index.html` and the user guide for the business
roles (Overview, Setup, one chapter per role, Troubleshooting / FAQ) in `doc/index.rst`. Do not
duplicate content between the two tabs.
