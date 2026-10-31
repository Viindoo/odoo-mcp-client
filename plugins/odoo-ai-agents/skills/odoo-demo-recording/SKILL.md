---
name: odoo-demo-recording
argument-hint: "[flow/feature to record] [--label before|after]"
description: >-
  Records a video of one Odoo workflow on a live instance
---

## Role

Recorder of one Odoo workflow on a live instance: a short clip or GIF of a scripted click path
through a browser MCP family, or the narrated before/after evidence clip of a bug. A multi-scene,
narrated, multi-language video is `odoo-produce-video` (workflow `video-produce`), which records
through the plugin's recorder script in the `odoo-video-producer` agent; when that workflow asks
this skill to record a scene (the recorder is unavailable for it), record it as below and write
the events log by hand.

## Events log

Beside every clip, `<clip>.events.json`: `[{"kind": "typing" | "wait" | "travel" | "load",
"start": <s>, "end": <s>}]` from the recording's start - each typed input, each wait for an
indicator or a page load, each cursor travel or scroll. The assembler (`video_publish.py
speedup`) plays typing at 3x, keeps the first second of a wait and squeezes the rest, plays
travel and loads at 2x; a clip without the log plays as recorded. A click is a cut point: the
next shot opens when its result is on screen.

## Out of Scope

- **Narrated, multi-language, publish-ready video** -> `odoo-produce-video`
- **Rating how a screen looks** -> `odoo-ui-review`
- **Diagnosing a broken screen** -> `odoo-debug`
- **Comparing two builds for visual drift** -> `odoo-visual-regression`
- **Writing Odoo frontend code** -> `odoo-coding`
- **Static screenshot docs** (a module's guide or App Store page) -> `odoo-doc-illustration`

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

## Browser tools

The family that records a take is the family that drives it; one path per take; headless by
default, `-headed` only when the human asks to watch. This skill runs INLINE.

- **pagecast (opt-in) - records its own browser.** `record_page` (`url`, `width`, `height`)
  opens it and starts the video; `interact_page` drives it (`wait`, `scroll`, `click`, `hover`,
  `type`, `press`, `select`, `navigate`); `stop_recording` saves the `.webm`. No script
  evaluation, no screenshot, no form fill.
- **playwright (opt-in) - records the page you drive.** `browser_start_video` (`filename`,
  `size`) / `browser_stop_video` around `browser_navigate`, `browser_click`, `browser_type`,
  `browser_fill_form`, `browser_select_option`, `browser_evaluate`, `browser_take_screenshot`.
- **chrome-devtools (eager) - drives, never records video.** `navigate_page` (`initScript` runs
  before any page script and must be re-passed on every navigation), `click` / `fill` /
  `fill_form` / `hover`, `evaluate_script`, `take_screenshot`: the screenshot-frame path.

pagecast and playwright are wired by `/odoo-ai-agents:odoo-setup browser`; with neither, capture
a chrome-devtools `take_screenshot` frame sequence and assemble it in Round 4.

## Workflow

### Round 0 - Resolve the run's inputs

- **Odoo series** - `${CLAUDE_PLUGIN_ROOT}/snippets/project-facts-resolution.md`.
- **`instance_base_url`** - `${CLAUDE_PLUGIN_ROOT}/snippets/instance-resolution.md`
  (`mcp__plugin_odoo-ai-agents_odoo-local__lease_find` first, then `catalog_read`).
- **Video output dir** - `<ISOLATE_DIR>/visual/videos/`, no per-project override.

Ask the user only for what no SSOT supplies (the workflow to record, MP4 or GIF, length), in one
message. Pin the series with `set_active_version(odoo_version=<concrete>)` and pass it on every
OSM call (`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § OSM session-pin race).

### Round 1 - Plan the click path (parallel, OSM)

`check_module_exists`, `module_inspect(method='views')`, `model_inspect(method='summary')`,
`find_examples('<feature> typical flow Odoo')` with the concrete version; produce the ordered step
list (menu -> record -> field input -> action) before recording.

### Round 2 - Set up deterministic state (in the recording browser)

A known record, the menu open, the top of the page, in the browser that will record - state set
in another family's browser does not carry over. pagecast: `record_page` at
`<instance_base_url>`, then `interact_page` to the start screen (the lead-in is trimmed in
Round 4). playwright: `browser_navigate` to the start screen before `browser_start_video`.
chrome-devtools: `navigate_page`, then `evaluate_script` / `fill`.

### Round 3 - Record the take

Drive in the SAME browser that records. pagecast: `interact_page` in the session Round 2 opened;
`record_and_gif` fits only a page that needs no setup; after `stop_recording`, `mv` the `.webm`
into `<ISOLATE_DIR>/visual/videos/`. playwright: `browser_start_video` with `filename` = the
absolute path `<ISOLATE_DIR>/visual/videos/<stem>.webm`, drive, `browser_stop_video`.

Pause briefly on key screens. Key frames go to `<ISOLATE_DIR>/visual/videos/<stem>-frameNN.png`
(`<stem>` = the slug Round 4 mints, minted before the first capture); pagecast takes no
screenshot - extract a poster with `ffmpeg` in Round 4. Delete the frames once the video is
assembled (a frame sequence that IS the deliverable stays). Stop the recorder, then CLOSE every
page you drove, on every take including a retake
(`${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T0 and T2).

### Round 4 - Produce the artifact

Mint the slug ONCE: `<feature>-<YYYYMMDD>-<4 random chars>`
(`${CLAUDE_PLUGIN_ROOT}/snippets/visual-evidence-lifecycle-contract.md` Clause 1), reused by
every artifact of the run. Orphan sweep before saving:
`find <ISOLATE_DIR>/visual/videos/ -maxdepth 1 -type f -mmin +43200 -exec rm -rf {} +` (Clause 3).
pagecast `convert_to_mp4` / `convert_to_gif` convert ONE `.webm` each (`webmPath` absolute; a
GIF's `width` is the size it is shown at); trim the setup lead-in with `convert_to_gif`
`startTime` or `ffmpeg`; join clips or a frame sequence with `ffmpeg` (`command -v ffmpeg` first;
missing -> deliver the frames or per-clip files and name it in `concerns:`). Save to
`<ISOLATE_DIR>/visual/videos/<feature>-<YYYYMMDD>-<4 random chars>.{mp4,gif}` and report the path,
duration and step list.

## Narrated evidence mode

A bug-evidence take with a per-step caption bar, a before/after corner badge and a verdict
end-card, drawn by the overlay bundle of
`${CLAUDE_PLUGIN_ROOT}/skills/odoo-demo-recording/references/narrated-mode.md` through a
script-execution tool this skill already has.

**Trigger:** the request says "narrated", "before/after evidence", carries `--label
before|after`, or the brief carries `LABEL` plus a verdict. Absent all four, Rounds 0-4 run
unchanged.

**Inputs:** `LABEL` (`before` | `after`; missing -> ask once in the Round-0 batch), `COMMIT_SHA`
(else `head_sha` of a `repo_facts` call), `VERDICT_STATUS` (`bug` | `fixed`), `VERDICT_EXPECTED`,
`VERDICT_OBSERVED` (from the caller, never invented), one caption line per step.

**Overlay:** chrome-devtools: the bundle as `initScript` on every `navigate_page`, then
`evaluate_script` calling `__setCaption` / `__setBadge` / `__endCard` with the text inlined
(never through `args`). playwright: `browser_evaluate` with the bundle after every
`browser_navigate`, then the same calls. pagecast cannot inject: when it is the only recorder,
drive with chrome-devtools; never present an unnarrated clip as narrated.

**Capture:** playwright wired: `browser_start_video`, drive with playwright's tools, update the
caption before each action, hold the end-card >= 2 s, `browser_stop_video`, convert with
pagecast. chrome-devtools only: `take_screenshot` one frame per step AFTER the caption update and
the action's result rendered, plus one of the held end-card; without `ffmpeg` the ordered PNG
sequence IS the deliverable.

A caption asserting a rendered value is read back from the page (`evaluate_script` /
`browser_evaluate` or the frame), never predicted.

**Matched pair:** both takes share one slug plus the suffix:
`<ISOLATE_DIR>/visual/videos/<feature>-<YYYYMMDD>-<4 random chars>-{before,after}.{mp4,gif}`.

**Unavailable:** only pagecast reachable -> `BLOCKED(narrated mode needs chrome-devtools or
playwright for overlay injection; only pagecast is reachable)`; no `ffmpeg` and no playwright ->
the PNG sequence with `status: DONE` and a `concerns:` entry.

## Standalone-first fallback

OSM unreachable: skip Round 1, reconstruct the click path from a grep of the repo's XML
(`grep -rn "<menu_id>" --include=*.xml`), prefix the report `⚠ OSM unreachable - click path
planned from disk grep, verify menus on the live instance`. Recorder unreachable: the
screenshot-frame GIF, prefixed `⚠ Recorder unreachable - produced frame sequence / GIF only`.
Instance unreachable after the resolution above: `status: NEEDS_NEXT` with `skill: odoo-instance`
(`operation: ensure-up`, the series, the modules), `BLOCKED(instance unreachable - tried <url>)`
only when provisioning is impossible; never ask the user for a screen capture.

## Output format

```
## Demo Recording: <feature workflow> (Odoo v<N>)

### Click path (re-runnable)
1. Navigate <url> -> 2. Click <menu> -> 3. Fill <field>=<value> -> 4. Click <action> ...

### Artifact
- File: <ISOLATE_DIR>/visual/videos/<feature>-<YYYYMMDD>-<4 random chars>.mp4 (or .gif)
- Duration: <s> · Resolution: <WxH> · Poster: <screenshot path>

### Notes
<state setup assumptions, e.g. the demo record used>
```

Narrated evidence mode adds:

```
### Narrated evidence (label: before|after)
- Badge: <BEFORE (unfixed)|AFTER (fixed)> <COMMIT_SHA>
- Captions: <N> steps, 1 line each
- End-card verdict: <bug|fixed> - Expected: <VERDICT_EXPECTED> · Observed: <VERDICT_OBSERVED>
- Paired file: <ISOLATE_DIR>/visual/videos/<slug>-<before|after>.{mp4,gif}
```

## Continuation Contract

Append the block of `${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md`
(status / produced / next). This skill records flows only; a needed fix goes to `odoo-coding`.
