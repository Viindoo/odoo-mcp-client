---
name: odoo-produce-video
argument-hint: "[project-label]"
description: >-
  Multi-scene demo video assembled into one file
disable-model-invocation: true
---
# /odoo-produce-video

<!-- execution SSOT: workflows/video-produce.workflow.yaml -->

Thin dispatcher. Invoke the `workflow-chaining` skill with
`plugins/odoo-ai-agents/workflows/video-produce.workflow.yaml`; the workflow YAML holds all phase
logic, skill invocations, output paths and fallback rules (storyboard, record-scenes, assemble).
`$ARGUMENTS` is an optional project label (e.g. `/odoo-produce-video Sales-Demo-Q3`); the runner
collects the remaining inputs before the workflow plan.

The storyboard is the workflow plan, approved once; the other phases then run without stopping.
Scene clips land in `<ISOLATE_DIR>/visual/videos/`; the assembled video lands at
`<ISOLATE_DIR>/video/<project_label>-<YYYY-MM-DD>.<mp4|gif>` (resolve `<SHARE_DIR>`/`<ISOLATE_DIR>`
once per `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`; substitute the captured
absolute path - never write the placeholder or a bare `.odoo-ai/` into a Read/Write/Edit).

Recording (pagecast / Playwright video) needs its browser family wired first via
`/odoo-ai-agents:odoo-setup browser`; without it the record-scenes phase falls back to a
`chrome-devtools` screenshot frame sequence assembled into a GIF.

A scene described with "narrated", "before/after evidence", or a `--label before|after` argument
gets `odoo-demo-recording`'s Narrated evidence mode (its SKILL.md § Narrated evidence mode); this
command adds no narrated-mode logic of its own.
