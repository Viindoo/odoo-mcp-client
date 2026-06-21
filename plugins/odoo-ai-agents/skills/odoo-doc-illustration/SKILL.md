---
name: odoo-doc-illustration
description: >
  Produce illustrated documentation for an Odoo module or cluster: drives a live browser to
  capture screenshots of rendered screens then embeds them into static/description/ (UC1) or
  a doc-repo/marketing output dir (UC2). Dispatched as agent odoo-doc-illustrator.
  Pushy trigger - fire on: "document an Odoo module with screenshots", "tạo tài liệu có ảnh
  cho module", "screenshot doc Odoo", "làm static/description với hình", "viết tài liệu cụm
  module kèm ảnh", "illustrate module README with captured screens", "add screenshots to addon
  docs", "thêm ảnh chụp màn hình vào tài liệu module".
  Routing: record a video walkthrough -> odoo-demo-recording; rate/audit a rendered screen ->
  odoo-ui-review; pure text draft (no screenshots) -> odoo-content-draft; compare two builds
  -> odoo-visual-regression; write frontend code -> odoo-coding
---

## Persona

Visual documentation producer for Odoo: drives a live browser to capture fully-rendered
screenshots then embeds them into durable module documentation. Captured images are copied
into the module's `static/description/` (or the cluster doc dir), so they survive across
working sessions and git commits instead of being lost to an ephemeral temp dir.

## Out of Scope

- **Record a video/GIF walkthrough** -> `odoo-demo-recording`
- **Rate or audit a rendered screen** (aesthetics, a11y, Lighthouse) -> `odoo-ui-review`
- **Pure text draft** (blog post, marketing copy, no screenshot capture needed) -> `odoo-content-draft`
- **Compare two builds for visual drift** -> `odoo-visual-regression`
- **Write or fix frontend source code** -> `odoo-coding`

## When to invoke / Agent invocation

Main launches `odoo-doc-illustrator` as a subagent with a DISPATCH BRIEF:

```
MODE: module | cluster
TARGET: <absolute path to module dir (UC1) | doc_output_dir (UC2)>
SCREENS: <ordered list of menus / views / flows to capture, e.g. "Sales > Orders list, form view of draft order, Confirm button result">
BROWSER MODE: headless | headed
USER LANGUAGE: vi | en
```

**Browser exclusivity.** The doc-illustrator drives the browser (playwright by default) sequentially - do NOT
dispatch it in parallel with odoo-ui-reviewer, odoo-visual-regression, or odoo-demo-recording
on the same instance, as concurrent browser sessions collide.

**Image write - 2-tier mechanism.** The agent captures screenshots into the browser MCP output-dir then Bash-copies images to the final destination; see `agents/odoo-doc-illustrator.md` for the SSOT on the write mechanism.

**UC2 text.** For cluster/marketing docs the agent delegates prose to `odoo-content-draft`
(skill invocation or subagent as appropriate), then slots the captured screenshots into the
returned document at the agreed anchor points. When `doc_output_dir` is not specified in the
brief or `.odoo-ai/context.md`, the agent falls back to `.odoo-ai/visual/doc/`.

Image quality: `${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-frontend-fidelity.md` (agent verifies
on-theme render before capturing).

**Headless/headed decision.** The agent defaults to headless - the only safe choice on a
no-display or CI host. Main adds `BROWSER MODE: headed` to the brief only when the user
explicitly asks to watch the browser; before doing so, confirm a display is plausibly available
and warn rather than dispatch on a headless host.

## Standalone fallback

- **OSM unreachable:** agent skips source-grounding steps and greps the repo on disk for
  module views and menu ids to confirm which screens exist. Prefix output with
  `WARNING: OSM unreachable - screen list inferred from disk grep, verify against live instance`.
- **Browser MCP or instance unreachable:** emit `status: NEEDS_NEXT` with:
  ```
  next:
    - skill: odoo-instance
      reason: provision the Odoo instance needed for live screenshot capture
      inputs: {operation: ensure-up, series: "<series from context>", modules: ["<modules to install>"]}
      confidence: 0.9
      risk_level: L2
  ```
  so the run-driver provisions one; fall back to `BLOCKED(Browser MCP unavailable - cannot capture screenshots)` only if provisioning is itself impossible.

## Continuation Contract

When you finish, append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next). Additive
output for the run-driver - it does not change anything produced above.
