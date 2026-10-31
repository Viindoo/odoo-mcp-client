---
name: odoo-produce-video
argument-hint: "[project-label] [--destination none|pr|youtube|youtube:<purpose>] [--languages vi_VN,en_US]"
description: >-
  Multi-scene demo video assembled into one file
disable-model-invocation: true
---
# /odoo-produce-video

<!-- execution SSOT: workflows/video-produce.workflow.yaml -->

Thin dispatcher. Invoke the `workflow-chaining` skill with
`plugins/odoo-ai-agents/workflows/video-produce.workflow.yaml`; the workflow holds every phase
(storyboard, record-scenes, narrate, assemble, publish), its scripts and its paths.
`$ARGUMENTS` is an optional project label (e.g. `/odoo-produce-video Sales-Demo-Q3`); the runner
collects the remaining inputs before the workflow plan.

The storyboard is the plan, approved once at the gate with its rendering and the AI cost
estimate; the other phases then run in the `odoo-video-producer` agent without stopping, except
for a budget overrun, a key field on screen, a failed verification or a narration line a human
must listen to. Everything lands under `<ISOLATE_DIR>/video/<project_label>/` (resolve
`<ISOLATE_DIR>` once per `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`); the
deliverables per language under `deliverables/<lang>/`.

Prerequisites, each with its setup step: the recorder (`/odoo-ai-agents:odoo-setup browser`
installs the pinned Playwright library and Chromium and runs the recorder's self-test); a spoken
narration (`/odoo-ai-agents:odoo-setup voice`: the speech endpoint, a voice per language, the
speech-to-text check); publishing to YouTube (`/odoo-ai-agents:odoo-setup youtube`: the channel
per purpose). Without the recorder a scene is recorded through `odoo-demo-recording`'s browser
MCP path, without automatic pacing.

`languages` decides the narration: one video per language, its own recording with the UI in that
language, captions, thumbnail, description with chapters, YouTube-spec MP4; no language = a
silent video. A scene that calls an AI feature declares its cost in the storyboard's `ai` block
(key only as the NAME of a dedicated environment variable; a shared key is refused), the plan
shows the estimate, and the run stops when the spend passes it by the margin.

`destination`, asked when not given: `youtube` or `youtube:<purpose>` publishes to the channel of
that purpose (`docs` for user guides, the docs site and the App Store page's video block;
`marketing` for sales and marketing videos) after the `youtube_check` for that purpose passed, the
key scan is clean and the operator approved the "listen" lines; `pr` attaches the preview to a
pull request; `none` keeps the files under the run directory.
