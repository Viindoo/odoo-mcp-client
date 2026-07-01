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
- **Pick one server family per run and stay on it:**
  - **playwright (default)** - `mcp__plugin_odoo-ai-agents_playwright__*`: navigate, resize,
    screenshot, evaluate. Use for all standard capture steps.
  - **chrome-devtools** - use ONLY when the brief asks for a Lighthouse or console-log illustration.
  - **pagecast** - use ONLY when the brief asks for a banner GIF / short clip (`record_and_gif`).
  Same allowed-roots constraint (section 3) applies to every family.

## 2. Browser mode - headless by default

Two variants exist per family: headless default (`...playwright__*`) and headed
(`...playwright-headed__*`). DEFAULT to headless - the only safe choice on a no-display/CI host.
Use `-headed` ONLY when the brief states `BROWSER MODE: headed`; never opt in on your own. Pick one
variant for the whole run.

## 3. Allowed-roots 2-tier write (mandatory for every capture)

Browser MCP tools only write inside **allowed roots** = the MCP process cwd plus `.playwright-mcp/`.
A RELATIVE filename lands in `<cwd>/.playwright-mcp/<file>` (persistent, not os.tmpdir()). An
ABSOLUTE path outside the allowed roots is REJECTED (`File access denied: ... outside allowed roots`).
Never pass an absolute filename to a browser tool; never pass `--allow-unrestricted-file-access`.

**P9 - preferred staging dir.** Where a tool accepts a configurable output path (e.g.
`chrome-devtools-headed take_screenshot path`, `pagecast-headed` output dir), stage into
`.odoo-ai/visual/doc-staging/` (gitignored). If a family writes only to `.playwright-mcp/` with no
override (the current playwright constraint), that directory IS the staging path - do not invent an
alternative; note `WARN: playwright staging constrained to .playwright-mcp/ (browser allowed-roots)`.

**Two-tier mechanism:**
1. Capture with a RELATIVE filename (e.g. `doc-staging/<slug>.png`). The tool writes to
   `<cwd>/.playwright-mcp/doc-staging/<slug>.png` and RETURNS the actual path written.
2. READ the actual path from the tool result, then use Bash `cp`/`mv` (not MCP file tools - not
   subject to allowed-roots) to place the image at its final destination inside the module dir.

**Branch selection (decide once, before the capture loop):**
- **Branch A (dest inside cwd):** if the final destination is a subpath of cwd
  (`realpath --relative-base=<cwd> <dest>` returns no leading `../`), capture with a relative
  filename pointing straight into the dest subfolder - no `cp` needed.
- **Branch B (dest outside cwd, default safe branch):** capture into `.playwright-mcp/doc-staging/`,
  read the returned path, Bash `cp` to the dest absolute path. `mkdir -p` the dest dir first.

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

Load `${screenshot_baseline_dir}/storageState-admin.json` if it exists (cached auth cookies).
Otherwise navigate to `<instance_base_url>/web/login` and fill credentials from `instance_login`
via `browser_fill_form`. If no storageState AND `instance_login` has no password, stop
`NEEDS_CONTEXT` and request credentials - never guess a default password. Always authenticate via
`/web/login` before navigating any backend URL (see `docs/odoo-ui-knowledge.md`).

## 6. On-theme check (before every capture)

Use `browser_evaluate` to read 1-2 primary design tokens, e.g.
`getComputedStyle(document.documentElement).getPropertyValue('--primary')` and `'--body-bg'`.
If either resolves EMPTY (self-referential cycles resolve to empty per CSS spec), the render is
off-theme - skip this screen, log `WARN: off-theme render detected (token EMPTY)`, and move on;
emit `NEEDS_CONTEXT` only if every screen fails. Reference:
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-frontend-fidelity.md`.

## 7. Capture step (per screen)

1. `browser_navigate` to the screen URL. Resolve backend URLs per version using
   `docs/odoo-ui-knowledge.md` (e.g. the `/odoo/<model>` vs `/web#action=...` split); resolve a menu
   entry via the live `ir.ui.menu` action when needed.
2. `browser_resize` to the OUTPUT SIZE the caller needs (banner vs feature vs hero). If the module
   already ships screenshots of the same type, MATCH their dimensions (`identify <file>`).
3. On-theme check (section 6).
4. **Crop/region default:** capture the smallest region that shows the feature. Use
   `browser_take_screenshot` with a `clip` rect or a focused view. Do NOT use `browser_highlight`
   unless the brief requests it (`ANNOTATION: highlight`); NEVER use `browser_annotate` - it opens an
   interactive dashboard that blocks on headless hosts.
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
  2. Perform the action (`browser_navigate` / `browser_fill_form` / `browser_click` /
     `browser_select_option` / `browser_wait_for`).
  3. On-theme check, then `take_screenshot` for this step.
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
- Never use `browser_annotate` in the capture loop; never run concurrently with another
  browser-driving agent.
- Git/GitHub mutations are NOT yours - the dispatching skill commits via git-toolkit `git-ops`.
  Bounded reads (`git status`, `git diff --stat`) may stay inline; never run git mutations, `gh`, or
  the github MCP directly.
