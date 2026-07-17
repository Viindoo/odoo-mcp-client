---
name: odoo-produce-video
argument-hint: "[project-label]"
description: |
  Produce a multi-scene Odoo demo video: author a storyboard (scene list with click paths), record each scene via odoo-demo-recording, then assemble all clips into a single MP4 or GIF deliverable. Invoke when you need a structured multi-scene walkthrough - e.g. "make a 3-scene product demo", "record storyboard and assemble into one video", "multi-scene Odoo marketing video", "quay nhiều scene ghép thành một video demo"
---
# /odoo-produce-video

<!-- execution SSOT: workflows/video-produce.workflow.yaml -->

This command is a thin dispatcher. All phase logic, gates, skill invocations, output
paths, and fallback rules are defined in the declarative workflow SSOT:

```
plugins/odoo-ai-agents/workflows/video-produce.workflow.yaml
```

## How to run

The `workflow-chaining` skill auto-discovers `video-produce.workflow.yaml` and executes it
when this command fires. Dispatch happens via natural-language routing - the runner reads
the workflow YAML and drives each phase in sequence.

To invoke: type `/odoo-produce-video` (optionally followed by a project label, e.g.
`/odoo-produce-video Sales-Demo-Q3`). The runner collects remaining inputs interactively
at Phase 0.

## What the workflow produces

Three gated phases (Pipeline pattern):

| Phase | Handler | Gate |
|-------|---------|------|
| 0 - Storyboard | inline | approve / edit / cancel |
| 1 - Record scenes | `odoo-demo-recording` (per scene) | approve-all / retake: [N] / cancel |
| 2 - Assemble | inline | save / discard / cancel |

Output lands in `<ISOLATE_DIR>/video/<project_label>-<YYYY-MM-DD>/` (resolve `<SHARE_DIR>`/`<ISOLATE_DIR>`
once per `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`; substitute the captured
absolute path - never write the placeholder or a bare `.odoo-ai/` into a Read/Write/Edit).

> **pagecast is opt-in.** Recording (pagecast / Playwright video) is no longer an eager browser
> MCP - only the headless `chrome-devtools` is eager. Wire the recorder family first via
> `/odoo-ai-agents:odoo-setup browser` (step 12 for Claude, step 10 for Codex/Gemini). If it is
> not wired, Phase 1 falls back to a `chrome-devtools` screenshot frame sequence assembled into a GIF.

For full phase specifications, gate behavior, standalone fallback rules, hard rules,
and examples - read `workflows/video-produce.workflow.yaml` directly.
