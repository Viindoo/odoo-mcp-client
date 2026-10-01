# Capture Mechanics Reference

Shared browser-capture mechanics for the two documentation writer agents -
`odoo-user-doc-writer` (end-user guide) and `odoo-marketing-writer` (App-Store landing).
Both agents drive a live Odoo instance to shoot screenshots, then hand the images to their
own assembly step. This file is the SSOT for HOW to capture; each writer body stays short and
owns only its AUDIENCE and its assembly. It is also the SSOT that `docs/odoo-ui-knowledge.md`
points at for the browser write mechanism.

Each writer is a leaf executor: it captures ONLY the shots it needs and NEVER spawns a subagent,
invokes the Skill tool, or runs an orchestration loop. The dispatching skill owns provisioning,
copy pre-fetch, the per-instance loop, verify, and commit.

---

## 1. Browser exclusivity + server family

Browser-exclusive PER FAMILY, serial within a dispatch (never concurrent with another
browser-driving agent on the SAME MCP family); full rule + close-before-done:
`${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T2. When the skill fans out multiple
capture workers (multi-module / multi-locale), each worker is on a DISTINCT browser MCP server
family and a DISTINCT instance - the skill computes the cap; you do not self-parallelize and you
never share a family/instance with another worker. Distinct families MAY run concurrently (each is
an isolated process with its own Chromium profile - no shared-DOM risk).

- **Pick one server family per run and stay on it - a FAMILY choice, not a page-lifetime one.**
  Staying on one family across the run does not mean keeping a page open across the run; you still
  close per T2. **The DEFAULT is `chrome-devtools`** - the one EAGER browser MCP (always present via
  the bundled `.mcp.json`); the others are OPT-IN and require the odoo-setup wiring step
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
  The staging constraint (section 3) applies to every family. The generic verbs below
  (navigate / emulate / screenshot / fill) map to the chosen family's tool names above.

## 2. Browser mode - headless by default

Each backend ships a headless default (`...chrome-devtools__*`) and a headed variant
(`...chrome-devtools-headed__*`, itself opt-in). DEFAULT to headless - the only safe choice on a
no-display/CI host. Use `-headed` ONLY when the brief states `BROWSER MODE: headed`; never opt in on
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

per `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md` § Where a captured artifact goes (the
per-family parameter and the refused-path stop live there). `<run_id>` is the brief's `RUN_ID` (the
worklog run-or-slug - reuse it, never mint a new id); `<module>` is the module being documented.
**NEVER stage into a bare `doc-staging/<...>` with no `<run_id>/<module>` prefix.** `mkdir -p` the
dir first. On chrome-devtools pass the path as `take_screenshot filePath` (never `path` - the schema
accepts unknown keys silently, so the wrong key writes nothing).

**`<ISOLATE_DIR>` resolution.** This staging tree is Tier-2 ISOLATE. Your dispatch brief carries
`ISOLATE_DIR:` (the `odoo-doc-illustration` skill resolves it ONCE against `doc_root` and passes it
to every writer + reuses it at its own end-of-run cleanup - see
`${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md` §Cross-worktree dispatch) - use that
literal directly; do NOT re-resolve. Only when it is absent (standalone dispatch outside the
skill's pipeline) resolve it yourself via the resolve-capture-substitute protocol in
`${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`.

The skill owns end-of-run cleanup of `<ISOLATE_DIR>/visual/<run_id>/` (scoped to `<run_id>` only),
reusing the SAME `ISOLATE_DIR` literal it passed to every writer this run; do not delete another
run's subtree. This staging cleanup is a FILES step only - it is not resource teardown (the browser
page you drove and the instance lease the skill holds are separate obligations); see
`${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T2/T3.

## 4. INSTANCE_HANDLE - the instance is already provisioned

When the brief carries `INSTANCE_HANDLE: <db>:<port>`, the dispatching skill already provisioned,
started, and installed the module (as a cumulative delta) on that instance and owns the lease:
- **The handle OUTRANKS every other way of resolving the target instance, including section 5's
  fallback.** Set `instance_base_url = http://localhost:<port from INSTANCE_HANDLE>` and use the
  handle's DB name for all browser navigation, the `/web/login` step (section 5), and any live Odoo
  MCP call. NEVER recompute the URL from the declared catalog while a handle is present: this
  instance is held under an EXCLUSIVE lease, and a leased port is allocated from a pool that starts
  ABOVE the catalog-declared `http_port` and reserves every declared port in the catalog, so a
  catalog-derived URL reaches a DIFFERENT server than the one seeded with the target module - wrong
  screenshots, no error. Skip any self-provisioning step and skip the standalone install gate.
- Still run the documentation-clean precondition check (demo data present, each resolved locale
  active, no out-of-scope menus) and emit a WARNING if unmet - but do NOT re-provision; the skill
  owns provisioning. Never drop or release the lease. (This ban is about the INSTANCE lease only -
  it is orthogonal to browser pages. You MUST still CLOSE every browser page you drove, opened or
  reused; closing a page never touches the lease. See resource-teardown-contract.md T2 vs T3.)
- After all writes, emit the path-incremental completion block so the skill can verify + commit and
  install the next module delta. Never install the next module yourself.

When `INSTANCE_HANDLE` is absent (standalone dispatch), confirm the module is installed first:
`search_records` on `ir.module.module` with `[['name','=','<module>'],['state','=','installed']]`;
if empty, stop `BLOCKED` and route to `odoo-instance` (`operation: install-module`).

## 5. Auth

**Resolve the login URL before anything else, and let `INSTANCE_HANDLE` win.** Brief carries
`INSTANCE_HANDLE` -> `instance_base_url = http://localhost:<port from INSTANCE_HANDLE>` (section 4),
full stop; do NOT consult the declared catalog, whose port is guaranteed to differ. ONLY when the
brief carries NO handle (standalone dispatch) resolve `instance_base_url` per
`${CLAUDE_PLUGIN_ROOT}/snippets/instance-resolution.md`.

Load `<SHARE_DIR>/visual/baselines/storageState-admin.json` if it exists (cached auth session -
the file format is family-specific; reuse it only within the family that wrote it). Otherwise
navigate to `<instance_base_url>/web/login` and fill credentials: the login IDENTIFIER is the
brief's, else `admin`. The PASSWORD is stored neither in this repo nor in project state - use the
value the brief supplies, and when the brief supplies none, ask for it ONCE. Never guess a password,
and never reuse a database credential for the web login.
- **chrome-devtools (default):** `fill_form` (one call for the username + password elements
  from the page snapshot).
- **playwright (OPT-IN):** `browser_fill_form`.
If no storageState AND no brief-supplied password, stop `NEEDS_CONTEXT` and request the password
once. Always authenticate via `/web/login` before
navigating any backend URL (see `docs/odoo-ui-knowledge.md`).

## 6. On-theme check (before every capture)

Read 1-2 primary design tokens via the family's script-eval tool:
- **chrome-devtools (default):** `evaluate_script`.
- **playwright (OPT-IN):** `browser_evaluate`.
e.g. `getComputedStyle(document.documentElement).getPropertyValue('--primary')` and
`'--body-bg'`. If either resolves EMPTY (self-referential cycles resolve to empty per CSS spec),
the render is off-theme - skip this screen, log `WARN: off-theme render detected (token EMPTY)`,
and move on; emit `NEEDS_CONTEXT` only if every screen fails. Reference:
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-frontend-fidelity.md`.

## 7. Frame for the placement slot

Decide where each image goes BEFORE you capture it - the slot decides the frame.

1. **Placement first.** For each shot, name the target doc and the slot the image fills: the
   `<img>` and its enclosing grid column in `index.html`, or the `.. image::` directive in the RST.
2. **Measure the slot width** in CSS pixels; never take it from a fixed table or compute it from
   class names (the store's container width is not in the module).
   - Choose ONE reading viewport width per module, state it in your capture-coverage report
     (section 11), and measure every slot of that module at it.
   - Render the doc in the browser at that width: `index.html` inside a local wrapper page that
     loads Bootstrap 5 CSS from a CDN (the store renders the fragment with it); RST as docutils
     HTML output, where a directive with no `:width:` fills the full content column. Save the page
     under `<ISOLATE_DIR>/visual/<run_id>/<module>_staging/` and open it as a `file://` URL.
   - Read the slot element's width with the script-eval tool (chrome-devtools `evaluate_script`,
     playwright `browser_evaluate`): `el.getBoundingClientRect().width`.
   - When the doc cannot be rendered (no docutils, Bootstrap unreachable), apply the full-width
     rule: the slot is the reading viewport width.
3. **Legibility.** The captured CSS width must be at most 1.25 x the slot width, or the store scales
   UI text below readability. Narrow the viewport toward the slot width, but never so far that the
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
   or `png`; playwright `type`. A GIF's width = the slot width: pagecast records at device pixel
   ratio 1, so record at a viewport within the step-3 cap and pass the slot width as
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

   Divide by the device pixel ratio (1 for a GIF) to get the captured CSS width. When it fails the step-3 cap,
   re-capture at most once; then keep the better shot and mark it `downgraded` (with the measured
   ratio) in the capture-coverage report.
8. **No annotation.** Neither family's default path has a highlight/annotate overlay. Do NOT use
   `browser_highlight` unless the brief explicitly requests it (`ANNOTATION: highlight`) AND the
   playwright family has been wired (chrome-devtools has no highlight equivalent - requesting one
   on the default family is a routing signal to the OPT-IN playwright family, never a bare-verb
   call). NEVER use `browser_annotate` on any family - it opens an interactive dashboard that
   blocks on headless hosts.

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

- **`screens` (default):** navigate + snapshot per screen. Read-only, so a screen is language-neutral
  UI-chrome-wise - but text on screen IS locale-dependent, so honour the per-locale loop (section 10).
- **`scenarios`:** the brief supplies a `WALKTHROUGH:` walkthrough.jsonl (from `odoo-doc-scenarist`);
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
  4. Optional state-assert: confirm the step produced the expected record/state via the live Odoo MCP
     (`mcp__odoo__read_record` / `search_records` / `execute_method`) before driving the next step.
  Each step's still is staged under its section-3 name. This is the gap vs `odoo-demo-recording` (one continuous
  video) and `odoo-qa-tester` (drives to a PASS/FAIL verdict) - here you shoot a still per step.

## 10. Per-locale capture loop

Applies whenever the resolved language set is larger than English-only. English (no suffix) is
captured FIRST and in full.
- **Read-only `screens`:** if the screenshot text does not change with locale, shoot once and share.
  When on-screen text IS locale-dependent, switch locale and re-shoot for each affected screen.
- **Driven `scenarios`:** a driven capture MUTATES state, so it CANNOT be re-rendered with `?lang=` -
  re-drive each scenario from its precondition per locale. Loop order: **outer = locale** (set the
  screenshot user's `res.users.lang`, or append `?lang=<locale>` on the backend URL, then
  re-establish the precondition), **middle = scenario**, **inner = step**.

## 11. No silent cap + capture-coverage report

Never trim silently (See-Something-Say-Something). Emit one capture-coverage line per
`(scenario, locale, step)` marking it `captured / downgraded / downgraded-to-screen / skipped` + the
reason and the bound that triggered it, so the caller sees exactly what was produced. Open the report
with the reading viewport width you measured slots at (section 7).

## 12. Degraded paths

- **Per-locale failure (never block the whole run for one locale):** if a locale fails to load or
  switch, reuse the English screenshots for that locale, mark each affected image with an
  `[Image: <slug>]` note, and report `status: DONE` with `concerns: [locale <x>: English
  screenshots used]`. Other locales proceed normally.
- **No instance / no browser at all:** do not hard-BLOCK. The writer still assembles its artifact
  STRUCTURE + supplied text with `[Image: <slug>]` placeholders at every illustration point, then
  emits `NEEDS_NEXT -> odoo-instance` so a later pass fills the captures. `BLOCKED` only when even the
  structure cannot be written.
- **OSM unreachable:** disk-grep the module XML for view names + menu ids; prefix
  `WARN: OSM unreachable - screens/labels from disk source`.

## 13. Place finals where the target doc resolves them

Find the destination directory for each final, in this order - the first candidate that satisfies
`${CLAUDE_PLUGIN_ROOT}/snippets/module-doc-references.md` § Images wins; skip one that does not
(an existing `doc/` image directory fails it for RST):
1. The directory the target doc's existing image references resolve to.
2. Sibling locale docs of the same doc, then the manifest `images` entries.
3. The directory the store serves for that doc type: `static/description/` for `index.html`; for
   RST, the module `static/` subtree, following the convention already on disk.

Name each final by the convention already on disk in that directory, else by
`${CLAUDE_PLUGIN_ROOT}/skills/odoo-doc-illustration/references/app-store-template.md` § Image
Specifications (store page) or the shot slug (user guide). The English canonical carries no locale
suffix; every other locale appends `.<locale>` before the extension.

`mv` (never `cp`) each final from staging into that directory under its final name, renaming it in
the same `mv` (`mkdir -p` the directory first). Reference it per
`${CLAUDE_PLUGIN_ROOT}/snippets/module-doc-references.md`, then run that snippet's reference gate
(§ Reference gate) until it exits 0. A capture the doc does not embed stays in staging.

## 14. Hard constraints (capture)

- Every capture names its absolute section-3 staging path; every image reference and cross-module
  link in the assembled artifact follows `${CLAUDE_PLUGIN_ROOT}/snippets/module-doc-references.md`.
- Never use `browser_annotate` (playwright-only; chrome-devtools has no equivalent) in the
  capture loop, on any family; never run concurrently with another browser-driving agent on the
  SAME MCP family (T2) - a distinct family/instance may run in parallel.
- Git/GitHub mutations are NOT yours - the dispatching skill commits via git-toolkit `git-ops`.
  Bounded reads (`git status`, `git diff --stat`) may stay inline; never run git mutations, `gh`, or
  the github MCP directly.
