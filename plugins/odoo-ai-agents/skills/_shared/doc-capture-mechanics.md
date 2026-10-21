# Doc Capture Mechanics Reference

Browser-capture mechanics for the documentation writers (`odoo-doc-writer`, `odoo-doc-site-writer`).

A writer captures only the shots its shot list names and launches nothing but the read-only
`Explore` agent for code tracing. Section 13 applies to module docs; § 15 states what differs
for `odoo-doc-site-writer`.

---

## 1. Browser exclusivity + server family

Browser-exclusive PER FAMILY, serial within a dispatch (never concurrent with another
browser-driving agent on the SAME MCP family); full rule + close-before-done:
`${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T2. When the skill fans out multiple
capture workers (multi-module / multi-locale), each worker is on a DISTINCT browser MCP server
family and a DISTINCT instance - the skill computes the cap; you do not self-parallelize and you
never share a family/instance with another worker. Distinct families MAY run concurrently.

- **Pick one server family per run and stay on it - a FAMILY choice, not a page-lifetime one.**
  Staying on one family across the run does not mean keeping a page open across the run; you still
  close per T2. **The DEFAULT is `chrome-devtools`**; the others are OPT-IN and require the odoo-setup wiring step
  (`/odoo-ai-agents:odoo-setup browser`) before their tools exist:
  - **chrome-devtools (default)** - `mcp__plugin_odoo-ai-agents_chrome-devtools__*`: `navigate_page`,
    `emulate` (viewport + device pixel ratio, section 7), `take_screenshot` (`filePath`, section 3),
    `click` / `fill` / `fill_form` / `hover`, `evaluate_script`. Use for ALL standard capture steps,
    plus any Lighthouse / console-log illustration.
  - **playwright (OPT-IN)** - `mcp__plugin_odoo-ai-agents_playwright__*` (`browser_navigate`,
    `browser_take_screenshot`, `browser_resize`, `browser_evaluate`, `browser_fill_form`, ...). Use
    only when the brief explicitly selects it AND it has been wired.
  - **pagecast (OPT-IN)** - use ONLY when the brief asks for a banner GIF / short video
    (`record_and_gif`); also requires the wiring step.
  The generic verbs below (navigate / emulate / screenshot / fill) map to the chosen family's
  tool names above.

## 2. Browser mode - headless by default

Each backend ships a headless default (`...chrome-devtools__*`) and a headed variant
(`...chrome-devtools-headed__*`, itself opt-in). DEFAULT to headless. Use `-headed` ONLY when the brief states `BROWSER MODE: headed`; never opt in on
your own. Pick one variant for the whole run.

## 3. Run/module-scoped staging (mandatory for every capture)

Stage every capture, on every family, at the absolute path

```
<ISOLATE_DIR>/visual/<run_id>/<module>_staging/<shot>[.<locale>].<ext>
```

`<shot>` is the shot's slug from your shot list: `<scenario_id>-step<NN>` for a `scenarios` step,
else the `[Image: <slug>]` marker slug or the screen's kebab-case name. English carries no locale
suffix. This is the staging name only: the final name is decided at placement (section 13), and you
rename the file to it in the same `mv`.

Pass that path with the per-family parameter and handle a refusal as
`${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md` § Where a captured artifact goes states.
`<run_id>` is the brief's `RUN_ID` (the
worklog run-or-slug - reuse it, never mint a new id); `<module>` is the module being documented.
**NEVER stage into a bare `doc-staging/<...>` with no `<run_id>/<module>` prefix.** `mkdir -p` the
dir first. On chrome-devtools pass the path as `take_screenshot filePath` (never `path`).

**`<ISOLATE_DIR>` resolution.** Your dispatch brief carries
`ISOLATE_DIR:` (the `odoo-doc-illustration` skill resolves it ONCE against `doc_root` and passes it
to every writer + reuses it at its own end-of-run cleanup - see
`${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md` §Cross-worktree dispatch) - use that
literal directly; do NOT re-resolve. Only when it is absent (standalone dispatch outside the
skill's pipeline) resolve it yourself via the resolve-capture-substitute protocol in
`${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`.

The skill owns end-of-run cleanup of `<ISOLATE_DIR>/visual/<run_id>/`; never delete another run's
subtree.

## 4. INSTANCE_HANDLE - the instance is already provisioned

When the brief carries `INSTANCE_HANDLE: <db>:<port>`:
- **The handle OUTRANKS every other way of resolving the target instance, including section 5's
  fallback.** Set `instance_base_url = http://localhost:<port from INSTANCE_HANDLE>` and use the
  handle's DB name for all browser navigation and any live Odoo MCP call. NEVER recompute the URL from the declared catalog while a handle is present. Skip any self-provisioning step and skip the standalone install gate.
- Still run the documentation-clean precondition check (demo data present, each resolved locale
  active, no out-of-scope menus) and emit a WARNING if unmet - but do NOT re-provision; the skill
  owns provisioning. Never drop or release the lease. CLOSE every browser page you drove, opened or
  reused (resource-teardown-contract.md T2).
- Report every file path. Never install the next module yourself.

When `INSTANCE_HANDLE` is absent (standalone dispatch), confirm on the instance you capture from
before anything else: `instance_status` says it is up and where, and the Apps screen of that
instance, opened through the browser MCP and filtered to `<module>`, shows it installed. Not
installed -> stop `BLOCKED` and route to `odoo-instance` (`operation: install-module`).

## 5. Instance

**Resolve the instance URL before anything else, and let `INSTANCE_HANDLE` win.** Brief carries
`INSTANCE_HANDLE` -> `instance_base_url = http://localhost:<port from INSTANCE_HANDLE>` (section 4).
ONLY when the brief carries NO handle (standalone dispatch) resolve `instance_base_url` per
`${CLAUDE_PLUGIN_ROOT}/snippets/instance-resolution.md`.

## 6. On-theme check (before every capture)

Read 1-2 primary design tokens via the family's script-eval tool:
- **chrome-devtools (default):** `evaluate_script`.
- **playwright (OPT-IN):** `browser_evaluate`.
e.g. `getComputedStyle(document.documentElement).getPropertyValue('--primary')` and
`'--body-bg'`. If either resolves EMPTY, the render is off-theme - skip this screen, log `WARN: off-theme render detected (token EMPTY)`,
and move on; emit `NEEDS_CONTEXT` only if every screen fails. Reference:
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-frontend-fidelity.md`.

## 7. Frame for the placement slot

Decide where each image goes BEFORE you capture it - the slot decides the frame.

1. **Placement first.** For each shot, name the target doc and the slot the image fills: the
   `<img>` and its enclosing grid column in `index.html`, or the `.. image::` directive in the RST.
2. **Measure the slot width** in CSS pixels; never take it from a fixed table or compute it from
   class names.
   - Choose ONE reading viewport width per module, state it in your capture-coverage report
     (section 11), and measure every slot of that module at it.
   - Render the doc in the browser at that width: `index.html` inside a local wrapper page that
     loads Bootstrap 5 CSS from a CDN (the store renders the fragment with it); RST as docutils
     HTML output. An image in an RST published on the internet has the content column as its slot; its form
     is `${CLAUDE_PLUGIN_ROOT}/snippets/module-doc-references.md` § Images. Save the page
     under `<ISOLATE_DIR>/visual/<run_id>/<module>_staging/` and open it as a `file://` URL.
   - Read the slot element's width with the script-eval tool (chrome-devtools `evaluate_script`,
     playwright `browser_evaluate`): `el.getBoundingClientRect().width`.
   - When the doc cannot be rendered (no docutils, Bootstrap unreachable), apply the full-width
     rule: the slot is the reading viewport width.
3. **Legibility.** The captured CSS width must be at most 1.25 x the slot width. Narrow the viewport toward the slot width, but never so far that the
   web client switches to its mobile layout - when it does, widen back. For a slot narrower than
   that, capture element-scoped: chrome-devtools `take_screenshot` `uid` (from the page snapshot),
   playwright `browser_take_screenshot` `target`.
4. **Device pixel ratio 2.** Set the viewport with chrome-devtools `emulate` `viewport`
   `<W>x<H>x2`. Prefer chrome-devtools for doc shots: playwright cannot change the device pixel
   ratio at runtime.
5. **Required context.**
   - **User guide** (an enterprise end user who must recognize where they are and what to click):
     the subject (the button, field group or list being described), the breadcrumb and control
     panel (its first crumb names the app), and the active notebook tab when the subject lives in
     one. Capture the action area below the top menu bar that holds them - never `.o_content` alone
     (it drops the breadcrumb). Include the top menu bar only when the whole client still fits the
     1.25 x cap.
   - **When the required context exceeds 1.25 x the slot:** place the image in a full-width slot
     instead, or split it into an orientation shot (full width, the whole screen) plus a detail shot
     (element-scoped, the narrow slot).
   - **Marketing** (a prospect judging value): the visible outcome - a result, a dashboard, a
     completed document, never an empty form - plus the app name, legible at the slot width. A
     full-width slot (hero/banner) may capture the whole viewport at a deliberately chosen width.
6. **Final format at capture time.** chrome-devtools `take_screenshot` `format` `jpeg` + `quality`,
   or `png`; playwright `type`. A GIF's width = the slot width: record at a viewport within the step-3 cap and pass the slot width as
   `record_and_gif` `gifWidth` / `convert_to_gif` `width`.
7. **Verify.** Read the image's pixel width from its file header with the plugin interpreter:

   ```
   python3 - <image file> <<'EOF'
   import struct, sys
   b = open(sys.argv[1], "rb").read()
   if b[:4] == b"\x89PNG":
       w = struct.unpack(">I", b[16:20])[0]
   elif b[:3] == b"GIF":
       w = struct.unpack("<H", b[6:8])[0]
   else:  # JPEG: walk the segments to the first SOF marker
       i = 2
       while b[i + 1] < 0xC0 or b[i + 1] > 0xCF or b[i + 1] in (0xC4, 0xC8, 0xCC):
           i += 2 + struct.unpack(">H", b[i + 2:i + 4])[0]
       w = struct.unpack(">H", b[i + 7:i + 9])[0]
   print(w)
   EOF
   ```

   Divide by the device pixel ratio (1 for a GIF) to get the captured CSS width; that value is the
   `:width:` the doc writer records for the image in an RST. When it fails the step-3 cap,
   re-capture at most once; then keep the better shot and mark it `downgraded` (with the measured
   ratio) in the capture-coverage report.
8. **No annotation.** Neither family's default path has a highlight/annotate overlay. Do NOT use
   `browser_highlight` unless the brief explicitly requests it (`ANNOTATION: highlight`) AND the
   playwright family has been wired (chrome-devtools has no highlight equivalent - requesting one
   on the default family is a routing signal to the OPT-IN playwright family, never a bare-verb
   call). NEVER use `browser_annotate` on any family.

## 8. Capture step (per screen)

1. Navigate to the screen URL - **chrome-devtools (default):** `navigate_page`; **playwright
   (OPT-IN):** `browser_navigate`. Resolve backend URLs per version using
   `docs/odoo-ui-knowledge.md` (e.g. the `/odoo/<model>` vs `/web#action=...` split); resolve a
   menu entry via the live `ir.ui.menu` action when needed.
2. Frame the shot for its slot (section 7).
3. On-theme check (section 6).
4. Capture straight to the section-3 staging path in the final format, then verify its width
   (section 7).

## 9. CAPTURE MODE - screens vs scenarios

- **`screens` (default):** navigate + snapshot per screen. Read-only; honour the per-locale loop
  (section 10).
- **`scenarios`:** the walkthrough (`walkthrough.jsonl`, the brief's or the one you wrote this round);
  each scenario carries `steps[]` of `{action: navigate|fill|click|select|wait, target, value, note}`.
  For each step, in order:
  1. Resolve `target` (menu path / field label / button label / state badge) to a selector or URL via
     OSM labels + the live `ir.ui.menu` / `ir.ui.view` data.
  2. Perform the action:
     - **chrome-devtools (default):** `navigate_page` / `fill_form` / `click` / `wait_for`.
       chrome-devtools has no dedicated "select" tool - a `select` step action maps onto
       `fill_form` (or single-element `fill`), which sets a `<select>` element's value directly.
     - **playwright (OPT-IN):** `browser_navigate` / `browser_fill_form` / `browser_click` /
       `browser_select_option` / `browser_wait_for`.
  3. Frame for the step's slot (section 7), on-theme check, then `take_screenshot` (chrome-devtools
     default) to the section-3 staging path.
  4. Optional state-assert: confirm the step produced the expected record/state on the leased
     instance itself - the record's form or list view in the browser MCP - before driving the next
     step.
  Each step's still is staged under its section-3 name.

## 10. Per-locale capture loop

Applies whenever the resolved language set is larger than English-only. English (no suffix) is
captured FIRST and in full.
- **Read-only `screens`:** if the screenshot text does not change with locale, shoot once and share.
  When on-screen text IS locale-dependent, switch locale and re-shoot for each affected screen.
- **Driven `scenarios`:** re-drive each scenario from its precondition per locale. Loop order: **outer = locale** (set the
  screenshot user's `res.users.lang`, or append `?lang=<locale>` on the backend URL, then
  re-establish the precondition), **middle = scenario**, **inner = step**.

## 11. No silent cap + capture-coverage report

Never trim silently. Emit one capture-coverage line per
`(scenario, locale, step)` marking it `captured / downgraded / downgraded-to-screen / skipped` + the
reason and the bound that triggered it. Open the report
with the reading viewport width you measured slots at (section 7).

## 12. Degraded paths

- **Per-locale failure (never block the whole run for one locale):** if a locale fails to load or
  switch, reuse the English screenshots for that locale, mark each affected image with an
  `[Image: <slug>]` note, and report `status: DONE` with `concerns: [locale <x>: English
  screenshots used]`. Other locales proceed normally.
- **No instance / no browser at all:** do not hard-BLOCK. The writer still assembles its artifact
  STRUCTURE + supplied text with `[Image: <slug>]` placeholders at every illustration point, then
  emits `NEEDS_NEXT -> odoo-instance`. `BLOCKED` only when even the
  structure cannot be written.
- **OSM unreachable:** disk-grep the module XML for view names + menu ids; prefix
  `WARN: OSM unreachable - screens/labels from disk source`.

## 13. Place finals where the target doc resolves them (module docs)

A final is every image the module ships: each image a doc embeds and each manifest `images` entry.
The cover goes to the root of the module's `static/description/` (§ Manifest images of
`${CLAUDE_PLUGIN_ROOT}/snippets/module-doc-references.md`); every other final goes directly into
`static/description/assets/`, named per that snippet's § Images. A screen that already has an
image there under a convention name keeps that name: your capture replaces it, and every doc
showing that screen references the one file. An existing off-convention name or location (e.g.
`shot_form.png`, `ws1-step03.png`, a screenshot at the root of `static/description/`) is moved
into `assets/` under the convention name.

`mv` (never `cp`) each final from staging into its directory under its final name, renaming it in
the same `mv` (`mkdir -p` the directory first).

In every doc file you write, bring each off-convention image reference into the convention, per
`${CLAUDE_PLUGIN_ROOT}/snippets/module-doc-references.md` § Images.

Reference every final per `${CLAUDE_PLUGIN_ROOT}/snippets/module-doc-references.md`. Every other
capture stays where it was written, cited by that path.

## 14. Hard constraints (capture)

- You run no git, `gh` or GitHub MCP call: a repo fact comes from `repo_facts`; the dispatching
  skill commits via git-toolkit `git-ops`.

## 15. Docs-site writer

For `odoo-doc-site-writer` (a docs-site page, never a module doc):

- **Staging.** Sections 3 and 13 do not apply. Stage every shot under the staging root `S` =
  `<ISOLATE_DIR>/visual/<RUN_ID>/site_staging/`, already at its final repo-relative path and name,
  which the writer body states.
- **Slot.** The slot is the CONTENT WIDTH of the brief. Section 7's slot measurement, `:width:` and
  module-slot rules do not apply; the viewport is at most 1.25 x CONTENT WIDTH at device pixel
  ratio 2.
- **Locale.** A locale that fails to load or switch is `BLOCKED` for that page; never reuse another
  language's shots (section 12's locale fallback does not apply).
- **Company.** Before the first shot of a language, the main company of the capture database
  carries `POLICY` `demo_company[<lang>]`: open the company in Settings in that language's UI, set
  its name when it differs, save, reload. No entry for the language: leave the company alone. The
  name comes from `POLICY`, never from you. All shots of a language are taken before the next
  language's change.
- **Capture-text log.** After each shot, read the visible text of the captured region with
  `evaluate_script` (`innerText` of the captured element, else of the action area) and append one
  line to `<ISOLATE_DIR>/docs-site/<RUN_ID>/capture-text.jsonl`:
  `{"image": "<repo-relative final path>", "lang": "<lang>", "text": "<visible text>"}`.
