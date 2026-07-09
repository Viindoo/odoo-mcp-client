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

- **Browser-exclusive, serial within a dispatch.** You drive exactly ONE browser, one action at a
  time, for the whole run. NEVER run concurrently with another browser-driving agent
  (`odoo-ui-reviewer`, `odoo-visual-regression`, `odoo-demo-recording`, or the sibling writer).
  When the skill fans out multiple capture workers (multi-module / multi-locale), each worker is on
  a DISTINCT browser MCP server family and a DISTINCT instance - the skill computes the cap; you do
  not self-parallelize and you never share a family/instance with another worker.
- **Pick one server family per run and stay on it. The DEFAULT is `chrome-devtools`** - the one
  EAGER browser MCP (always present via the bundled `.mcp.json`); the others are OPT-IN and require
  the odoo-setup wiring step (`/odoo-ai-agents:odoo-setup browser`) before their tools exist:
  - **chrome-devtools (default)** - `mcp__plugin_odoo-ai-agents_chrome-devtools__*`: `navigate_page`,
    `resize_page`, `take_screenshot` (accepts a configurable `path` - stage DIRECTLY, see section 3),
    `click` / `fill` / `fill_form` / `hover`, `evaluate_script`. Use for ALL standard capture steps,
    plus any Lighthouse / console-log illustration.
  - **playwright (OPT-IN)** - `mcp__plugin_odoo-ai-agents_playwright__*` (`browser_navigate`,
    `browser_take_screenshot`, `browser_resize`, `browser_evaluate`, `browser_fill_form`, ...). No
    longer eager; use only when the brief explicitly selects it AND it has been wired.
  - **pagecast (OPT-IN)** - use ONLY when the brief asks for a banner GIF / short clip
    (`record_and_gif`); also requires the wiring step.
  The staging constraint (section 3) applies to every family. The generic verbs below
  (navigate / resize / screenshot / fill) map to the chosen family's tool names above.

## 2. Browser mode - headless by default

Each backend ships a headless default (`...chrome-devtools__*`) and a headed variant
(`...chrome-devtools-headed__*`, itself opt-in). DEFAULT to headless - the only safe choice on a
no-display/CI host. Use `-headed` ONLY when the brief states `BROWSER MODE: headed`; never opt in on
your own. Pick one variant for the whole run.

## 3. Run/module-scoped staging (mandatory for every capture)

Every capture stages under a **run- and module-scoped** path so two modules (or two concurrent runs)
never clobber each other's images. `<run_id>` is the brief's `RUN_ID` (the worklog run-or-slug -
reuse it, never mint a new id); `<module>` is the module being documented. **NEVER stage into a bare
`doc-staging/<...>` with no `<run_id>/<module>` prefix.** Both roots below are gitignored.

- **Default family `chrome-devtools`** accepts a configurable `take_screenshot` `path`, so stage
  DIRECTLY - no two-tier dance:
  ```
  .odoo-ai/visual/<run_id>/<module>_staging/<scenario_id>-step<NN>.png
  ```
  Pass that relative path as `take_screenshot path`; `mkdir -p` its dir first. Read the returned
  actual path, then Bash `cp`/`mv` (not MCP file tools) to place the image at its final destination
  inside the module dir.
- **OPT-IN family `playwright`** writes only inside its allowed roots (the MCP process cwd plus
  `.playwright-mcp/`), so it keeps the two-tier write, now NAMESPACED by run + module:
  1. Capture with a RELATIVE filename `<run_id>/<module>_staging/<scenario_id>-step<NN>.png`. The tool
     writes to `<cwd>/.playwright-mcp/<run_id>/<module>_staging/...` and RETURNS the actual path.
  2. READ the returned path, then Bash `cp`/`mv` to the final destination inside the module dir.
  Never pass an absolute filename to a browser tool; never pass `--allow-unrestricted-file-access`
  (an absolute path outside the allowed roots is REJECTED: `File access denied: ... outside allowed
  roots`).
- **OPT-IN family `pagecast`** (GIF/clip only) stages its output dir under the same
  `.odoo-ai/visual/<run_id>/<module>_staging/` prefix.

**Branch selection (decide once, before the capture loop):**
- **Branch A (dest inside cwd):** if the final destination is a subpath of cwd
  (`realpath --relative-base=<cwd> <dest>` returns no leading `../`), capture with the relative
  staged path pointing straight into the dest subfolder - no `cp` needed.
- **Branch B (dest outside cwd, default safe branch):** capture into the run/module-scoped staging
  dir, read the returned path, Bash `cp` to the dest absolute path. `mkdir -p` the dest dir first.

The skill owns end-of-run cleanup of `.odoo-ai/visual/<run_id>/` and `.playwright-mcp/<run_id>/`
(scoped to `<run_id>` only); do not delete another run's subtree.

## 4. INSTANCE_HANDLE - the instance is already provisioned

When the brief carries `INSTANCE_HANDLE: <db>:<port>`, the dispatching skill already provisioned,
started, and installed the module (as a cumulative delta) on that instance and owns the lease:
- Use the DB name and port from `INSTANCE_HANDLE` directly for all browser navigation and any live
  Odoo MCP calls. Skip any self-provisioning step and skip the standalone install gate.
- Still run the documentation-clean precondition check (demo data present, each resolved locale
  active, no out-of-scope menus) and emit a WARNING if unmet - but do NOT re-provision; the skill
  owns provisioning. Never drop or release the lease.
- After all writes, emit the path-incremental completion block so the skill can verify + commit and
  install the next module delta. Never install the next module yourself.

When `INSTANCE_HANDLE` is absent (standalone dispatch), confirm the module is installed first:
`search_records` on `ir.module.module` with `[['name','=','<module>'],['state','=','installed']]`;
if empty, stop `BLOCKED` and route to `odoo-instance` (`operation: install-module`).

## 5. Auth

Load `${screenshot_baseline_dir}/storageState-admin.json` if it exists (cached auth session -
the file format is family-specific; reuse it only within the family that wrote it). Otherwise
navigate to `<instance_base_url>/web/login` and fill credentials from `instance_login`:
- **chrome-devtools (default):** `fill_form` (one call for the username + password elements
  from the page snapshot).
- **playwright (OPT-IN):** `browser_fill_form`.
If no storageState AND `instance_login` has no password, stop `NEEDS_CONTEXT` and request
credentials - never guess a default password. Always authenticate via `/web/login` before
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

## 7. Capture step (per screen)

1. Navigate to the screen URL - **chrome-devtools (default):** `navigate_page`; **playwright
   (OPT-IN):** `browser_navigate`. Resolve backend URLs per version using
   `docs/odoo-ui-knowledge.md` (e.g. the `/odoo/<model>` vs `/web#action=...` split); resolve a
   menu entry via the live `ir.ui.menu` action when needed.
2. Resize to the OUTPUT SIZE the caller needs (banner vs feature vs hero) - **chrome-devtools
   (default):** `resize_page`; **playwright (OPT-IN):** `browser_resize`. If the module already
   ships screenshots of the same type, MATCH their dimensions (`identify <file>`).
3. On-theme check (section 6).
4. **Crop/region default:** capture the smallest region that shows the feature.
   - **chrome-devtools (default):** `take_screenshot` scoped with a `uid` (the smallest
     containing element from the page snapshot) instead of a full-viewport shot; chrome-devtools
     has no free-form `clip` rect, so element-scoping IS the region-crop equivalent.
   - **playwright (OPT-IN):** `browser_take_screenshot` with a `clip` rect.
   Neither family's default path has a highlight/annotate overlay. Do NOT use `browser_highlight`
   unless the brief explicitly requests it (`ANNOTATION: highlight`) AND the playwright family has
   been wired (chrome-devtools has no highlight equivalent - requesting one on the default family
   is a routing signal to the OPT-IN playwright family, never a bare-verb call). NEVER use
   `browser_annotate` on any family, default or opt-in - it opens an interactive dashboard that
   blocks on headless hosts.
5. Capture via the Branch A or Branch B write (section 3).

**Screenshot filenames** follow the DETECTED on-disk convention when one exists (tiebreaker: disk
`ls` of `static/description/` wins, then `context.md doc_image_naming`, then the caller's default).
General rule: the English canonical carries NO locale suffix; every non-English locale appends
`.<locale>` (see section 8). Marketing filename specs live in
`${CLAUDE_PLUGIN_ROOT}/skills/odoo-doc-illustration/references/app-store-template.md` Image
Specifications.

## 8. CAPTURE MODE - screens vs scenarios

- **`screens` (default):** navigate + snapshot per screen. Read-only, so a screen is language-neutral
  UI-chrome-wise - but text on screen IS locale-dependent, so honour the per-locale loop (section 9).
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
  3. On-theme check, then `take_screenshot` (chrome-devtools default) for this step.
  4. Optional state-assert: confirm the step produced the expected record/state via the live Odoo MCP
     (`mcp__odoo__read_record` / `search_records` / `execute_method`) before driving the next step.
  Per-step filename: `<scenario-slug>-step<NN>.<locale>.png`; English canonical =
  `<scenario-slug>-step<NN>.png` (no suffix). This is the gap vs `odoo-demo-recording` (one continuous
  clip) and `odoo-qa-tester` (drives to a PASS/FAIL verdict) - here you shoot a still per step.

## 9. Per-locale capture loop

Applies whenever the resolved language set is larger than English-only. English (no suffix) is
captured FIRST and in full.
- **Read-only `screens`:** if the screenshot text does not change with locale, shoot once and share.
  When on-screen text IS locale-dependent, switch locale and re-shoot for each affected screen.
- **Driven `scenarios`:** a driven capture MUTATES state, so it CANNOT be re-rendered with `?lang=` -
  re-drive each scenario from its precondition per locale. Loop order: **outer = locale** (set the
  screenshot user's `res.users.lang`, or append `?lang=<locale>` on the backend URL, then
  re-establish the precondition), **middle = scenario**, **inner = step**.

## 10. No silent cap + capture-coverage report

Never trim silently (See-Something-Say-Something). Emit one capture-coverage line per
`(scenario, locale, step)` marking it `captured / downgraded-to-screen / skipped` + the reason and
the bound that triggered it, so the caller sees exactly what was produced.

## 11. Degraded paths

- **Per-locale failure (never block the whole run for one locale):** if a locale fails to load or
  switch, reuse the English screenshots for that locale, mark each affected image with an
  `[Image: <slug>]` note, and report `status: DONE_WITH_CONCERNS(locale <x>: English screenshots
  used)`. Other locales proceed normally.
- **No instance / no browser at all:** do not hard-BLOCK. The writer still assembles its artifact
  STRUCTURE + supplied text with `[Image: <slug>]` placeholders at every illustration point, then
  emits `NEEDS_NEXT -> odoo-instance` so a later pass fills the captures. `BLOCKED` only when even the
  structure cannot be written.
- **OSM unreachable:** disk-grep the module XML for view names + menu ids; prefix
  `WARN: OSM unreachable - screens/labels from disk source`.

## 12. Hard constraints (capture)

- Image `src` refs inside the assembled artifact MUST be relative (`./file.png`, `../static/...`);
  absolute paths appear ONLY at the Bash write/cp step.
- Never pass an absolute path as a screenshot filename to any browser tool (rejected by allowed-roots).
- Never use `browser_annotate` (playwright-only; chrome-devtools has no equivalent) in the
  capture loop, on any family; never run concurrently with another browser-driving agent.
- Git/GitHub mutations are NOT yours - the dispatching skill commits via git-toolkit `git-ops`.
  Bounded reads (`git status`, `git diff --stat`) may stay inline; never run git mutations, `gh`, or
  the github MCP directly.
