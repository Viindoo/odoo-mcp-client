# App Store Template Reference

Runtime reference for assembling `static/description/index.html` and related assets for
an Odoo App Store listing. Brand-agnostic - palette and fonts are placeholders resolved from
`.odoo-ai/context.md` brand tokens or user input; default = Odoo palette `#714B67`.

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
| Relative image paths | All `<img src="...">` must be relative to `static/description/` (e.g. `./main_screenshot.gif` for the English canonical, `./main_screenshot.vi_VN.gif` per locale). External image URLs are blocked. |
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

Recommended order. Omit optional sections when content is thin rather than leaving placeholders.

| # | Section | ID | Content | Required |
|---|---|---|---|---|
| 1 | Hero | `#overview_block` | Banner (compatibility badges + title + tagline matching manifest `summary`) + main screenshot/GIF | Yes |
| 2 | Key Features | `#key_features_block` | `row`/`col-md-6 col-lg-4` cards: icon + capability title + user-outcome body (1-2 sentences each). 3-6 features. | Yes |
| 3 | Benefits | `#benefit_block` | 4-6 bullets starting with action verbs (Streamline / Enhance / Ensure / Empower). Each = one buyer outcome, not a toggle. | Optional |
| 4 | Screenshots | `#feature` (tab) | Alternating light/alternate-bg sections. Each: `col-xl-4` task title + `col-xl-8` screenshot. Caption = human task name, not a technical path. | Recommended |
| 5 | Demo | `#demo` (tab) | YouTube embed (16:9) + user-manual link + live-demo link. YouTube only (canonical `youtube.com/embed/` format). | Optional |
| 6 | Support | `#support` (tab) | Two contact cards: pre-sales email + technical support email. | Recommended |
| 7 | Technical Requirements | `#requirement` (tab) | Odoo version range, required modules, editions (Community / Enterprise / Cloud), license. | Recommended |
| 8 | Changelog | `#changelog` (tab) | Chronological list: date + badge (New / Improved / Fixed) + description. | Optional |
| 9 | Target Users | `#target_users_block` | 3 persona cards by ROLE + PAIN (e.g. Executives, Operations Leaders, Implementers). | Optional |

Tab navigation (`<ul class="nav nav-tabs">`) wraps sections 4-8 into one tabbed block.
Sections 1-3 and 9 appear as full-width sections above and below the tab block.

**Tone rule**: hero and features = value-first, buyer-facing. Never open with "This module extends
X to support Y" or expose Python class names / field technical names in headings.

---

## 3. Bootstrap-5 Fragment Skeleton (brand-agnostic)

Replace `{{PLACEHOLDER}}` values from `.odoo-ai/context.md` brand tokens or user input.
Default palette when no brand tokens: primary `#714B67`, accent `#714B67`, bg-light `#F8F4F8`.

```html
<!-- static/description/index.html - FRAGMENT ONLY, no html/head/body -->
<!-- Bootstrap 5 already loaded by the store; do NOT add <link> CDN tags -->

<!-- ================================================================
  HERO
================================================================ -->
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
    <!-- Title + tagline -->
    <div class="row mt-4 text-center">
      <div class="col-md-12">
        <h1 style="color:#fff;font-weight:700;font-size:34px;margin-bottom:10px;">
          {{MODULE_DISPLAY_NAME}}
        </h1>
        <p class="mx-auto"
           style="color:#fff;font-size:18px;line-height:26px;max-width:78%;margin-bottom:16px;">
          {{TAGLINE - matches manifest summary, outcome-first, 15 words max}}
        </p>
      </div>
    </div>
  </div>
  <!-- Hero screenshot -->
  <div class="row mt-4">
    <div class="col-md-10 offset-md-1 text-center"
         style="border-radius:20px;padding:3px;background-color:{{PRIMARY_HEX}};">
      <img alt="{{MODULE_DISPLAY_NAME}}" class="img-fluid" loading="lazy"
           src="./main_screenshot.gif"
           style="border-radius:15px;display:block;width:100%;height:auto;">
    </div>
  </div>
</section>

<!-- ================================================================
  KEY FEATURES GRID
================================================================ -->
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

<!-- ================================================================
  BENEFITS (optional)
================================================================ -->
<section id="benefit_block" class="py-4">
  <div style="background-color:#f8f8f8;padding:40px;border-radius:15px;">
    <h2 class="text-center mb-4" style="font-size:32px;font-weight:bold;">
      Benefits
    </h2>
    <div class="bg-white rounded" style="padding:24px;border:1px solid #e8e8e8;">
      <!-- Repeat per benefit (4-6 items) -->
      <div class="d-flex align-items-start p-2 gap-2">
        <span style="font-size:20px;color:{{PRIMARY_HEX}};margin-top:2px;">&#8227;</span>
        <p class="mb-0" style="font-size:15px;">
          {{BENEFIT - action verb first, buyer outcome, no feature toggle language}}
        </p>
      </div>
    </div>
  </div>
</section>

<!-- ================================================================
  TABS: Screenshots / Demo / Support / Requirements / Changelog
  NOTE: nav-tabs rely on Bootstrap 5 JS. `data-bs-toggle="tab"` is a JS-driven behavior, NOT pure
  CSS - it does NOT work without Bootstrap JS. It works here only because the store PRELOADS
  Bootstrap JS (verified on live listings); you still ship NO <script> of your own (CSP strips it).
================================================================ -->
<div id="tabs" class="container px-0">
  <ul class="nav nav-tabs justify-content-center bg-white py-2"
      id="moduleTab" role="tablist"
      style="border-radius:6px 6px 0 0;">
    <li class="nav-item">
      <a class="nav-link active" data-bs-toggle="tab" href="#feature" role="tab">
        Features
      </a>
    </li>
    <li class="nav-item">
      <a class="nav-link" data-bs-toggle="tab" href="#demo" role="tab">Demo</a>
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

  <!-- FEATURE DEEP-DIVE -->
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
            <!-- NN = 2-digit sequence, slug = kebab-case task name; English canonical = NO suffix (NN-slug.jpg), per-locale = NN-slug.<locale>.jpg (e.g. 01-submit-request.vi_VN.jpg) -->
            <img alt="{{FEATURE_TASK_TITLE}}" class="img-fluid" loading="lazy"
                 src="./NN-slug.jpg"
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

  <!-- TECHNICAL REQUIREMENT -->
  <div class="tab-pane fade" id="requirement" role="tabpanel">
    <section class="py-4">
      <div style="background:#f8f8f8;padding:40px;border-radius:15px;">
        <h2 class="text-center mb-4"
            style="font-size:30px;font-weight:bold;">Technical Requirement</h2>
        <div class="p-3 bg-white rounded">
          <ul style="list-style:none;padding-left:0;margin-bottom:0;">
            <li class="py-2">
              <strong>Odoo version:</strong> {{SERIES}} (e.g. 17.0, 18.0)
            </li>
            <li class="py-2">
              <strong>Editions:</strong> Community / Enterprise / Cloud (list applicable)
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

<!-- ================================================================
  TARGET USERS (optional)
================================================================ -->
<section id="target_users_block" class="py-4">
  <div style="background-color:#f4f4f4;padding:40px;border-radius:15px;">
    <h2 class="text-center mb-4"
        style="font-size:30px;font-weight:bold;">Who Should Use This Module?</h2>
    <div class="row g-4">
      <!-- 3 persona cards: describe by ROLE + PAIN, not by feature -->
      <div class="col-md-4">
        <div class="bg-white rounded p-4 h-100"
             style="border-top:4px solid {{PRIMARY_HEX}};">
          <h4 style="font-size:16px;font-weight:700;">{{PERSONA_ROLE}}</h4>
          <p style="font-size:14px;">{{PERSONA_PAIN_AND_GAIN}}</p>
        </div>
      </div>
    </div>
  </div>
</section>
```

---

## 4. Image Specifications

| Asset | Path | Format | Size | Notes |
|---|---|---|---|---|
| Module icon | `static/description/icon.png` | PNG only | 256x256 px | No manifest key needed - implicit path. Missing = ranking penalty. |
| Main screenshot / hero | Declared first in `manifest['images']` | PNG, GIF, or JPEG | No official spec; 960-1100px wide recommended | Used as cover in store browse/grid views. |
| Feature screenshots | Additional entries in `manifest['images']` or inline in `index.html` | PNG, GIF, or JPEG | No official spec; ~1100px wide | Inline-only images (not in `images`) do not appear in grid views. |
| Banner/enlarged display | Any image whose filename ends with `_screenshot` | PNG, GIF, or JPEG | Full demo page width | First `*_screenshot` file is selected as the main banner display. |
| Feature screenshot (English canonical) | `static/description/NN-slug.jpg` | JPEG or PNG | ~1100px wide | No locale suffix. `index.html` references these. |
| Per-locale screenshot | `static/description/NN-slug.<locale>.jpg` | JPEG or PNG | ~1100px wide | Each locale's `index_<locale>.html` references its own locale-suffixed images. |
| Animated walkthrough (English canonical) | `static/description/main_screenshot.gif` | GIF | ~960px wide, 16:9 | No locale suffix. Declared in `manifest['images']` for the cover position. |
| Animated walkthrough (per locale) | `static/description/main_screenshot.<locale>.gif` | GIF | ~960px wide, 16:9 | One per non-English locale. |

**Filename convention** (enforced for new modules): the English canonical has NO locale suffix -
`NN-slug.<ext>` and `main_screenshot.<ext>`; every non-English locale appends `.<locale>` -
`NN-slug.<locale>.<ext>` and `main_screenshot.<locale>.<ext>`. `NN` is a 2-digit sequence
(`01`, `02`, ...), `slug` is a kebab-case task description, and `<locale>` is a full locale code
(`vi_VN`, `fr_FR`, etc.). This matches the step-capture naming in `agents/odoo-doc-illustrator.md`
(English step files carry no suffix).

All paths in `index.html` must be relative to `static/description/` (i.e. start with `./`).
External image URLs are blocked by the store.

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
| `images` | list[str] | First entry = cover in browse/grid. Subsequent entries = store carousel. | Must have at least one entry (ranking penalty if absent). Paths relative to module root (e.g. `static/description/main_screenshot.gif` for the English cover). |
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

**Language resolver order** (doc-illustration tiers - reuse, do not clone):

1. Brief field `LANGUAGES:` (explicit override, optional)
2. `.odoo-ai/context.md` -> `doc_languages`
3. `${ODOO_AI_HOME:-$HOME/.odoo-ai}/i18n.json` -> `default_languages`
4. Disk: `<module>/i18n/*.po` locale codes
5. Live `res.lang` (active languages on instance, late fallback)
6. Hard fallback (tier-6 default stays `["vi_VN"]` for the shared resolver)

After resolving, **union with existing on-disk `index_*.html` / `index_*.rst`** so prior
translations are never dropped.

**Screenshot localization**: per-locale screenshots are captured separately. Filename pattern:
English canonical has NO suffix (`NN-slug.jpg`, `main_screenshot.gif`); every non-English locale
appends `.<locale>` (`NN-slug.<locale>.jpg`, `main_screenshot.<locale>.gif`). Each locale's HTML
references only its own images. Icon is language-neutral (one `icon.png`, no locale suffix).

**Tab split discipline**: keep marketing copy in `index.html` and deep technical steps
(Install / Config / Usage / Troubleshooting / Changelog / Credits) in `doc/index.rst`. Do not
duplicate content between the two tabs.
