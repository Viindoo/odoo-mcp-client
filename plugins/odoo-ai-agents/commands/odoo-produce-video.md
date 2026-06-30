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

Output lands in `.odoo-ai/video/<project_label>-<YYYY-MM-DD>/`.

For full phase specifications, gate behavior, standalone fallback rules, hard rules,
and examples - read `workflows/video-produce.workflow.yaml` directly.
