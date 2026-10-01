---
name: odoo-demo-recording
argument-hint: "[flow/feature to record] [--label before|after]"
description: >
  Record a screen-capture video (MP4/GIF) of one Odoo workflow for a demo, sales walkthrough,
  marketing clip, or narrated before/after bug-evidence pair - driving the live instance through
  a scripted click path and saving the result. Capture runs via pagecast/Playwright-video MCP
  (the recorder drives the path; chrome-devtools screenshot frames when no recorder is wired).
  Use when the deliverable is a video of a live flow, not a static review. Pushy trigger: fire on
  "record a demo of this Odoo workflow", "capture a GIF of creating an invoice in Odoo", "capture
  a short MP4 for the website", "record narrated before/after evidence", "quay video demo Odoo",
  "tạo video hướng dẫn quy trình". Routing: stitch many scenes / multi-scene walkthrough into one
  video → /odoo-produce-video (command); RATE how a screen looks → odoo-ui-review; diagnose a
  broken screen's root cause → odoo-debug; compare two builds → odoo-visual-regression; write
  frontend code → odoo-coding; code audit → odoo-code-review
---

## Role

Demo/marketing recorder for Odoo. Turn a described workflow into a clean, scripted click path
through the live instance and produce a polished video or GIF artifact. Plan the path before
recording (which menus, which records, what to type) so the take is smooth and re-runnable.

## Out of Scope

- **Rating how a screen looks** (aesthetic/a11y/performance verdict) → `odoo-ui-review`
- **Diagnosing a broken screen** → `odoo-debug`
- **Comparing two builds for visual drift** → `odoo-visual-regression`
- **Writing Odoo frontend code** → `odoo-coding`
- **Static source-level code audit** → `odoo-code-review`

## MCP tools

<!-- BEGIN GENERATED TOOLS -->
> **Pick the right tool first.** Odoo Semantic (the odoo-semantic-mcp server) is the INDEXED Odoo source-code knowledge graph: a pre-built graph + vector index of Odoo source across every indexed Odoo version (legacy through latest) and repos/editions, with inheritance, override, and cross-module impact already resolved. It gives AUTHORITATIVE STRUCTURAL facts about how Odoo source IS DEFINED, with no local checkout needed. Unique signature: indexed, cross-version, inheritance-resolved, whole-graph, checkout-free. It is a STATIC index with NO runtime/live data.
>
> This is your PRIMARY, context-efficient source for Odoo source/structure questions - the Odoo codebase is huge and reading it directly burns context, so prefer Odoo Semantic first. Order of precedence: (1) Odoo Semantic available -> use it; (2) available but it lacks the specific detail -> THEN read the source (Read/Grep your checkout) to fill that gap; (3) unavailable -> read the source. Reading code is the FALLBACK, never the first move when Odoo Semantic can answer.
>
> Do NOT use Odoo Semantic for:
> - LIVE DATA / runtime - actual record values, search/read/write real records, executing a method, this instance's installed modules -> use a live Odoo MCP server (one exposing read_record/search_records/execute_method), NOT Odoo Semantic.
>
> Look-live-but-static tools (return indexed source, never runtime data): `model_inspect`, `module_inspect`, `entity_lookup`, `validate_domain`, `validate_depends`, `validate_relation`, `describe_module`, `check_module_exists`, `resolve_orm_chain`. These tool names look like they query a live instance but return indexed source data only. If you need live records, Odoo Semantic is the wrong server.

**Session bootstrap** (call once at session start):
- `set_active_version(odoo_version='17.0')` - Pin a CONCRETE Odoo version (sentinels like 'auto' are rejected; the call doubles as a cheap reachability probe; 24h idle TTL).

**Primary tools:**
- `check_module_exists` - Verify module availability, edition (CE/EE/Viindoo), and cross-version presence.
- `find_examples` - Semantic code search returning real indexed code snippets from the Odoo codebase.
- `model_inspect` ★ - Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, extenders, or a summary in one call.
- `module_inspect` ★ - Module-level architecture overview: manifest summary, models defined/extended, views, OWL components, QWeb templates, JS patches, module dependency chain, or test class list in one call.
<!-- END GENERATED TOOLS -->

OSM use is light here - only to plan the click path: `module_inspect(name=<module>, method='views', odoo_version='<version>')` tells you which views/menus exist; `model_inspect(model=<model>, method='summary', odoo_version='<version>')` confirms fields/records the demo will touch; `check_module_exists` confirms the demo module is installed; `find_examples` surfaces the canonical flow for the feature.

## Browser tools

Each family is its own browser: the family that records a take is the family that drives it. Pick
ONE path per take. Each family has a **headless default** and a **headed** (`-headed`) variant -
default to headless (recording works headless; only safe choice on no-display hosts); use headed
only when the human asks to watch. This skill runs INLINE (call tools yourself, no dispatch brief)
- call the `-headed` tool directly when needed.

- **pagecast (OPT-IN) - records its own private browser.** `record_page` (`url`, `width`,
  `height`) opens it and starts the video; `interact_page` drives it with the actions `wait`,
  `scroll`, `click`, `hover`, `type`, `press`, `select`, `navigate`; `stop_recording` saves the
  `.webm`. `record_and_gif` records a fixed duration of one URL with no interaction. pagecast has
  no script evaluation, no screenshot and no form fill.
- **playwright (OPT-IN) - records the page you drive.** `browser_start_video` (`filename`,
  `size`) / `browser_stop_video` around `browser_navigate`, `browser_click`, `browser_type`,
  `browser_fill_form`, `browser_select_option`, `browser_evaluate`, `browser_take_screenshot`.
- **chrome-devtools (eager) - drives, never records video.** `navigate_page` (its `initScript`
  runs on every new document before any other script - narrated mode's overlay injection point;
  re-pass the SAME `initScript` on every navigation, a fresh document wipes injected globals),
  `click` / `fill` / `fill_form` / `hover`, `evaluate_script`, `take_screenshot`. Use it for the
  screenshot-frame path.

> **pagecast and playwright are OPT-IN** - only `chrome-devtools` is eager (bundled `.mcp.json`);
> the recorder families must be wired first via `/odoo-ai-agents:odoo-setup browser` (step 12 for
> Claude, step 10 for Codex/Gemini). If no recorder is wired (its tools are absent), capture a
> chrome-devtools `take_screenshot` frame sequence and assemble it in Round 4.

## Workflow

Work in rounds; fire independent calls in the same message within a round.

### Round 0 - Resolve the run's inputs

Resolve each input from its own SSOT - never from a stored snapshot, and never by guessing:

- **Odoo series** - per `${CLAUDE_PLUGIN_ROOT}/snippets/project-facts-resolution.md`.
- **`instance_base_url`** - per `${CLAUDE_PLUGIN_ROOT}/snippets/instance-resolution.md` (the live
  shared server `mcp__plugin_odoo-ai-agents_odoo-local__lease_find` returns first, then the matching row `mcp__plugin_odoo-ai-agents_odoo-local__catalog_read` returns).
- **Login identifier** - the brief's, else `admin`. The PASSWORD is stored neither in this repo nor
  in project state: use the value the brief supplies, and when the brief supplies none, ask for it
  ONCE. Never guess a password and never reuse a database credential for the web login.
- **Video output dir** - always `<ISOLATE_DIR>/visual/videos/` (resolved below); there is no
  per-project override.

Ask the user only for what no SSOT above supplies (plus the workflow to record, format MP4/GIF, and
length) in a single message. Do not guess.

Once the series is resolved, **pin it** with `set_active_version(odoo_version=<concrete>)` and
pass that concrete version on every Round 1 OSM call - the pin is session-scoped and racy when
actors share a session (SSOT: `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § OSM
session-pin race); without explicit passing the click path may target the wrong version's view
names and URL scheme (`/odoo` vs `/web`, which differ by version).

### Round 1 - Plan the click path (parallel, OSM)

For the feature to demo, fire in parallel:
- `check_module_exists(name=<module>, odoo_version='<version>')` - confirm demo module is installed.
- `module_inspect(name=<module>, method='views', odoo_version='<version>')` - enumerate menus/views the path will visit.
- `model_inspect(model=<model>, method='summary', odoo_version='<version>')` - confirm fields/records the demo touches.
- `find_examples(query='<feature> typical flow Odoo', odoo_version='<version>')` - sanity-check the canonical happy path.

Produce an ordered step list (menu → record → field input → action) before recording.

### Round 2 - Set up deterministic state (in the recording browser)

Log in and reach a clean, repeatable demo state (known record, expanded menu, top of page) in the
browser that will record - a login in another family's browser does not carry over:

- **pagecast:** inside the pagecast session - `record_page` at `<instance_base_url>/web/login`, then
  `interact_page`: `type` the login and the password into their inputs, `press` `Enter`, `navigate`
  to the start screen. The login is part of the take; trim it off in Round 4.
- **playwright:** `browser_navigate` to `/web/login` and `browser_fill_form` the credentials before
  `browser_start_video`; set state with `browser_evaluate`.
- **chrome-devtools (frame path):** `navigate_page` + `fill_form`; set state with
  `evaluate_script` / `fill`.

### Round 3 - Record the take (browser)

The recorder and the browser that drives the path must be the SAME browser, or the take records
nothing of the drive:

- **pagecast:** drive the path with `interact_page` in the session Round 2 opened; never drive
  with chrome-devtools while a pagecast recording runs. `record_and_gif` fits only a page that
  needs no login. Immediately after `stop_recording`, `mv` the `.webm` it returns into
  `<ISOLATE_DIR>/visual/videos/`.
- **playwright:** `browser_start_video` with `filename` = the absolute path
  `<ISOLATE_DIR>/visual/videos/<stem>.webm`, drive with the playwright tools in that same browser,
  then `browser_stop_video`.

Pause briefly on key screens. Capture key frames (poster, frame path) with the driving family's
screenshot tool (chrome-devtools `take_screenshot` `filePath`, playwright `browser_take_screenshot`
`filename`) to the absolute path `<ISOLATE_DIR>/visual/videos/<stem>-frameNN.png` (NN zero-padded
in step order), `<stem>` being the slug Round 4 mints - mint it before the first capture. pagecast
takes no screenshot: extract a poster from its video with `ffmpeg` in Round 4. Delete the frames
once the video/GIF is assembled (a frame sequence that IS the deliverable stays). Stop the recorder, then CLOSE every page you DROVE this round
before moving to Round 4. Both steps are mandatory for EVERY recording round, including a retake.
Full rule: `${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T0 and T2 - Browser: close
what you drove.

### Round 4 - Produce the artifact

`visual/videos/` is Tier-2 ISOLATE; resolve it via the same resolve-capture-substitute protocol
(captured path shown as `<ISOLATE_DIR>` below).

**Mint the filename slug ONCE, before the first Round 3 capture and the orphan sweep below.** `<feature>-<YYYYMMDD>-<4 random
chars>` - the IDENTICAL collision-proof suffix mechanism the four sibling `visual/*/<slug>/`
evidence directories use, applied here to a filename instead of a directory (`<feature>` plays the
role of `<intent-slug>`); SSOT: `${CLAUDE_PLUGIN_ROOT}/snippets/visual-evidence-lifecycle-contract.md`
Clause 1. Reuse the SAME minted value for every artifact path this run touches - see
`## Narrated evidence mode` § Matched-pair filenames below for the before/after case.

**Orphan sweep (do this every run, BEFORE saving THIS run's artifact below).** Nothing deletes an
old recording today, so `visual/videos/` leaks one file per run forever:

`find <ISOLATE_DIR>/visual/videos/ -maxdepth 1 -type f -mmin +43200 -exec rm -rf {} +`

(any sibling
`<feature>-<YYYYMMDD>-<4 random chars>.{mp4,gif}` untouched for over 30 days is presumed consumed -
this run's own file cannot match since it does not exist yet). Full rule + bound rationale:
`${CLAUDE_PLUGIN_ROOT}/snippets/visual-evidence-lifecycle-contract.md` Clause 3. Enforcer: whoever
executes `odoo-demo-recording` next, unconditionally, every run.

**Produce the file.** pagecast `convert_to_mp4` / `convert_to_gif` each convert ONE `.webm`
(`webmPath` = its absolute path under `<ISOLATE_DIR>`); a GIF's `width` is the size it is shown
at. Trim a pagecast login off the start with `convert_to_gif` `startTime`, or with `ffmpeg` for
an MP4. Assemble a frame sequence, or join clips, with `ffmpeg`; check `command -v ffmpeg` first -
when it is missing, deliver the frames or per-clip files and name the missing `ffmpeg` in
`concerns:`.

Save the MP4 (or GIF) to
`<ISOLATE_DIR>/visual/videos/<feature>-<YYYYMMDD>-<4 random chars>.{mp4,gif}` and report the
path, duration, and step list so the take is re-runnable.

## Narrated evidence mode

Optional sub-mode of Rounds 0-4 above: turns a bug-evidence take into a self-explanatory clip -
a per-step caption bar, a before/after corner badge, and a verdict end-card - using ONLY the
script-execution tools this skill already declares (chrome-devtools `evaluate_script` /
`navigate_page(initScript=...)`, or playwright `browser_evaluate` when that family is wired
instead). Bundle template + a fully worked example:
`${CLAUDE_PLUGIN_ROOT}/skills/odoo-demo-recording/references/narrated-mode.md`.

### Trigger (decidable)

Enter this mode when the request states ANY of: the word "narrated"; "before/after (bug)
evidence"; a `--label before|after` argument; or a dispatch brief carrying both `LABEL` and a
verdict (`VERDICT_STATUS` plus expected/observed text). Absent all four, run Rounds 0-4 unchanged
- this mode never fires on a bare "record a demo" ask.

### Required additional inputs

- `LABEL` (`before` | `after`) - selects badge color/text and the output filename suffix. Missing
  → ask once, in the single Round-0 question batch; never guess which side of a fix this take is.
- `COMMIT_SHA` - the build's commit. If not supplied, resolve inline in the repo under
  demonstration with `git rev-parse --short HEAD` - a bounded, non-mutating read, the same class
  `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md` keeps inline-legal - never a git-ops dispatch
  for this one read.
- `VERDICT_STATUS` (`bug` | `fixed`), `VERDICT_EXPECTED`, `VERDICT_OBSERVED` - the end-card
  content. Take these from the caller (an `odoo-debug` root-cause, an `odoo-qa-tester` verdict,
  or the human reporting the bug); never invent them.
- A caption line per Round 1 step-list entry - one short present-tense sentence per menu/record/
  field/action, in the operator's language.

### Overlay mechanism (verified capability - do not exceed it)

- Caption bar, corner badge, and end-card are ONE self-contained DOM-overlay bundle (inline HTML/
  CSS/JS, no CDN, no external fetch - CSP-safe by construction) injected via a script-execution
  tool this skill already declares - never a new capability. Exact bundle text + calling
  convention: `references/narrated-mode.md`.
- **chrome-devtools:** pass the bundle as `initScript` on every `navigate_page` call this run
  (re-pass the SAME string on every navigation - a fresh document wipes injected globals); call
  `evaluate_script` between steps to invoke the bundle's `__setCaption` / `__setBadge` /
  `__endCard` functions, updating caption/badge/end-card text without a fresh navigation. Do not
  pass caption text via `evaluate_script`'s `args` - that parameter is documented for element-uid
  substitution, not arbitrary strings; inline the text into a fresh `function` string per call
  instead.
- **playwright (if wired):** `browser_navigate` has no `initScript`-equivalent parameter - call
  `browser_evaluate` with the bundle immediately after every `browser_navigate`, then again to
  call `__setCaption` / `__setBadge` / `__endCard` between steps. Its native `browser_start_video` /
  `browser_stop_video` records the SAME page the bundle draws on in real time (a continuous take,
  no frame assembly needed). Its native `browser_video_chapter` MAY supplement as a scene marker
  but does not substitute for the end-card - that tool has no color parameter, so it cannot carry
  the required red/green verdict color; the DOM overlay's own end-card owns that.
- **pagecast is NOT a narrated-mode driver.** Verified against its declared schema: `record_page`
  accepts only `url`/`width`/`height`, and `interact_page`'s action set (`wait/scroll/click/hover/
  type/press/select/navigate`) has no script-injection or evaluate action - pagecast cannot render
  the overlay into its own recording. If pagecast is the only recorder family wired, drive this
  mode via chrome-devtools instead (next section) - never present a silent, unnarrated pagecast
  clip as narrated.

### Capture, by path

- **playwright wired:** `browser_start_video` before the first step; drive with playwright's own
  `browser_click` / `browser_fill_form` / `browser_type`, updating the caption via
  `browser_evaluate` immediately before each action; hold the end-card on screen >= 2s before
  `browser_stop_video` (the start call names an absolute `filename` under
  `<ISOLATE_DIR>/visual/videos/` per Round 3). Convert the result with pagecast's `convert_to_mp4` / `convert_to_gif` -
  a pure file-format conversion (both take a file path, not a live session), so this cross-family
  reuse needs no new capability.
- **chrome-devtools only:** `take_screenshot` one frame per step AFTER the caption update and the
  action complete (the frame must show the rendered result, not the pending state - see Grounding
  rule below), plus one final frame of the held end-card; each frame goes to
  `<ISOLATE_DIR>/visual/videos/<stem>-frameNN.png` per Round 3. This is the SAME screenshot-frame path
  the base flow already uses when the recorder is unreachable (`## Standalone-first fallback`
  below) - reused deliberately here, not a second assembly path. If `ffmpeg` is not on PATH (Round 4),
  the ordered PNG sequence itself IS the deliverable - report it as
  such (Output format) rather than claiming an MP4 the tool surface did not produce.

### Grounding rule

A caption asserting rendered STATE (a value shown on screen, e.g. "vendor: Acme Freight") must be
checked against the frame actually captured for that step - re-read the field via
`evaluate_script` / `browser_evaluate` (or the screenshot itself) - never written from the
expected/predicted value ahead of time. A predicted caption that turns out wrong (the bug means
the field stays empty) is the exact defect this mode exists to make visible.

### Matched-pair filenames

Both takes of a before/after pair share the SAME `<feature>-<YYYYMMDD>-<4 random chars>` slug
(mint it ONCE, per Round 4's slug-mint step above, and reuse it for both invocations) plus the
`LABEL` suffix, landing in the SAME `visual/videos/` path Round 4 already uses - no new directory,
no new retention row; the existing orphan sweep and 30-day bound (Round 4, above) already cover
any file here regardless of suffix:

```
<ISOLATE_DIR>/visual/videos/<feature>-<YYYYMMDD>-<4 random chars>-before.{mp4,gif}
<ISOLATE_DIR>/visual/videos/<feature>-<YYYYMMDD>-<4 random chars>-after.{mp4,gif}
```

### When the capability is not available

- **Neither chrome-devtools nor playwright is reachable** (only pagecast is): no script-injection-
  capable family exists. Emit `BLOCKED(narrated mode needs chrome-devtools or playwright for
  overlay injection; only pagecast is reachable)`. Do not silently produce an unnarrated pagecast
  clip and call it narrated.
- **chrome-devtools is reachable (it always is - eager, bundled) but `ffmpeg` is not on PATH and
  playwright is not wired:** produce the PNG frame sequence (each frame
  overlay-correct) and return `status: DONE` with a `concerns:` entry naming the missing
  `ffmpeg` and the sequence path, rather than promising an MP4/GIF the toolchain cannot produce.
- Recorder single-flight (never two drivers on the same MCP family) and close-before-DONE still
  apply unchanged - `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § Browser
  exclusivity + `${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T2; this mode adds
  no new exception.

## Standalone-first fallback

- **OSM unreachable:** skip Round 1 verification; grep the repo for menu/view ids (`grep -rn "<menu_id>" --include=*.xml`) to reconstruct the click path from source; only ask the caller to confirm the menu path and records if the grep result is insufficient. Prefix with `⚠ OSM unreachable - click path planned from disk grep, verify menus on the live instance`.
- **Browser MCP / video recorder unreachable:** if video capture is unavailable, fall back to a screenshot frame sequence assembled into a GIF. If the instance itself is unreachable, re-run the instance resolution per `${CLAUDE_PLUGIN_ROOT}/snippets/instance-resolution.md` (`lease_find`, then `catalog_read` - never a stored file); if still unreachable after trying the resolved URL, emit `status: NEEDS_NEXT` with:
  ```
  next:
    - skill: odoo-instance
      reason: provision the Odoo instance needed to record the demo
      inputs: {operation: ensure-up, series: "<the resolved series>", modules: ["<modules required for workflow>"]}
      confidence: 0.9
  ```
  so the run-harness provisions one; fall back to `BLOCKED(instance unreachable - tried <url>)` only if provisioning is itself impossible. Do NOT ask the user for a screen-capture of the flow. Prefix with `⚠ Recorder unreachable - produced frame sequence / GIF only`.

## Output format

```
## Demo Recording: <feature workflow> (Odoo v<N>)

### Click path (re-runnable)
1. Navigate <url> → 2. Click <menu> → 3. Fill <field>=<value> → 4. Click <action> …

### Artifact
- File: <ISOLATE_DIR>/visual/videos/<feature>-<YYYYMMDD>-<4 random chars>.mp4 (or .gif)
- Duration: <s> · Resolution: <WxH> · Poster: <screenshot path>

### Notes
<any state setup assumptions, e.g. demo data record used>
```

Narrated evidence mode adds, to the same report:

```
### Narrated evidence (label: before|after)
- Badge: <BEFORE (unfixed)|AFTER (fixed)> <COMMIT_SHA>
- Captions: <N> steps, 1 line each (see Click path above for the matching step text)
- End-card verdict: <bug|fixed> - Expected: <VERDICT_EXPECTED> · Observed: <VERDICT_OBSERVED>
- Paired file: <ISOLATE_DIR>/visual/videos/<feature>-<YYYYMMDD>-<4 random chars>-<before|after>.{mp4,gif}
```

Examples (sales order MP4 + portal GIF with recorder unavailable, plus a narrated before/after
bug-evidence pair): `${CLAUDE_PLUGIN_ROOT}/skills/odoo-demo-recording/references/examples.md`.
Narrated-mode overlay bundle + calling convention:
`${CLAUDE_PLUGIN_ROOT}/skills/odoo-demo-recording/references/narrated-mode.md`.

## Notes / Integration

- Videos/GIFs are written under `<ISOLATE_DIR>/visual/videos/`.
- Use a consistent viewport and login for repeatable takes.
- This skill records flows only; it never edits Odoo source. Hand any needed fix to `odoo-coding`.
- Narrated mode never fires unless explicitly requested (see `## Narrated evidence mode` §
  Trigger) - the default flow above is unchanged.

## Continuation Contract

Append a Continuation Contract block per `${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md`
(status / produced / next) - additive run-harness output, changes nothing above.
