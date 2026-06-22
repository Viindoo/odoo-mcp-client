---
name: odoo-ui-review
description: >
  Review a rendered Odoo UI in a live browser across six lenses - aesthetics (layout, spacing,
  brand), functional correctness (buttons, forms, nav), runtime stability (no console errors),
  accessibility (ARIA, contrast, keyboard), performance (Lighthouse), design-system/theme
  fidelity (off-theme detection). Dispatched as a read-only
  agent (odoo-semantic-mcp + chrome-devtools) when an instance is running and the user wants a
  verdict on how a working screen looks and behaves, not its source. Pushy trigger: fire on
  "review this Odoo screen", "is this page accessible", "run a Lighthouse audit on Odoo", "make
  sure this looks right before the demo", "is it off-theme / sai theme Odoo", "đánh giá giao
  diện Odoo", "kiểm tra UI đã render".
  Routing: investigate WHY a screen is broken not rate a working one → odoo-debug; compare
  two states for drift → odoo-visual-regression; record a video → odoo-demo-recording; change
  frontend source → odoo-coding; source-level review → odoo-code-review
---

## Persona

UI/UX reviewer for rendered Odoo screens. Judges the running interface - what a user sees and
clicks - across six lenses: aesthetics, functional correctness, stability, accessibility,
performance, and **design-system fidelity** (does the screen match the Odoo design system and
the project mockup, or is it off-theme?). Evidence-based: every finding cites a screenshot, a
console message, a Lighthouse score, a computed-style readout, or a snapshot node - never an
unverified impression.

## Out of Scope

- **Investigating WHY a screen is broken / errors / blank render** → `odoo-debug`
- **Comparing two states or builds for visual drift / regression** → `odoo-visual-regression`
- **Recording a demo or marketing walkthrough video** → `odoo-demo-recording`
- **Writing or changing Odoo frontend JS/OWL source** → `odoo-coding`
- **Source-level code review (Python/JS/XML)** → `odoo-code-review`

## When to invoke

Main agent launches the `odoo-ui-reviewer` **agent** as a subagent when the user has a running
Odoo instance and wants a verdict on how a rendered screen looks and behaves. The agent drives a
live browser (chrome-devtools MCP) to capture the screen, exercises controls, runs a Lighthouse
audit, sweeps responsive breakpoints, then grounds every styling defect in the codebase via OSM.
Because the review requires many sequential+parallel browser/MCP round-trips, it runs as an
autonomous agent rather than inline.

## Brief context - Odoo UI review pitfalls

Key things the agent watches for:

1. **Selector era by version** - v17+ backend uses `/odoo` with `.o_form_view` / `.o_list_view` / `.o_kanban_view`; older versions use `/web`. Pin the version before navigating.
2. **Login first** - Odoo screens are session-gated; the agent logs in before capturing.
3. **Six-lens coverage** - a finding in one lens (e.g. a console error) often explains a defect in another (a control that silently fails); cross-reference them.
4. **Source-grounded fixes** - a styling defect is only actionable once the owning module/stylesheet is named, so the fix lands in the right place rather than as an inline override.
5. **Design-system / theme lens** - run a token-reality check per `${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-frontend-fidelity.md`: read `getComputedStyle` on `:root` + representative elements and flag empty/transparent surfaces, self-referential CSS custom properties, `--bs-*` references (Odoo sets `$variable-prefix:''`, so Bootstrap `--bs-*` runtime vars are absent across v16+ confirmed through v19 - reference `--primary` / `--o-color-*` instead), hardcoded palette, and divergence from the mockup. Emit remediation as a token+file pointer, not an inline patch.

## Agent invocation

**Before dispatching:** check for a design document from an upstream `odoo-solution-design` /
`odoo-solution-architect` run. List `.odoo-ai/designs/` under the project root; if one or more
files are present, take the most recently modified one and add the following line to the dispatch
brief:

```
DESIGN_DOC: .odoo-ai/designs/<filename>
```

The reviewer uses this to verify UI-observable acceptance criteria (controls visible, workflow
paths reachable, labels correct, access-rule state reflected in the UI) from §1 (Expected outcomes /
User impact) and §9 (Acceptance Criteria) of the design document. When no `designs/` directory
exists or it is empty, omit the line entirely.

When the user confirms intent (or main detects a running instance + a "how does it look" request),
main launches the `odoo-ui-reviewer` agent as a subagent with restricted tools (odoo-semantic-mcp +
chrome-devtools, read-only). The agent does NOT spawn further subagents, does NOT invoke any Skill
tool, and never edits Odoo source - fixes are handed to `odoo-coding`.

**Browser mode (headless default / headed on request).** The agent defaults to headless - the only
safe choice on a no-display/CI host. Only when the human explicitly asks to see/watch the browser
does main add a `BROWSER MODE: headed` line to the dispatch brief; the agent then uses its
`*-headed` tool variant. This is an AI/NL decision passed in the brief - no env var or on-disk flag.
Before dispatching headed, sanity-check that a display is plausibly available; on a headless/CI host
warn the human rather than dispatching a doomed run.

## Standalone-first fallback

- **OSM unreachable:** agent skips code-grounding steps and greps the repo on disk for the relevant view and stylesheet. Prefix output with `⚠ OSM unreachable - style/view origin inferred from disk, verify against the live module`.
- **OSM reachable but view/stylesheet/module not in index (customer-local addon):** Tier-1 MISS, not proof of absence - keep OSM for what it covers; grep disk for just the missed entity, label `grounded: osm + local-source (hybrid)` (see `snippets/disk-fallback-protocol.md`).
- **Browser MCP or instance unreachable:** if the orchestrator has provided pre-captured screenshot paths in context, use those for aesthetics/a11y review. If no pre-captured screenshots are available, emit `status: NEEDS_NEXT` with:
  ```
  next:
    - skill: odoo-instance
      reason: provision the Odoo instance needed for live screenshot capture
      inputs: {operation: ensure-up, series: "<series from context>", modules: ["<modules to install>"]}
      confidence: 0.9
      risk_level: L2
  ```
  so the run-driver provisions one; fall back to `BLOCKED(Browser MCP unavailable - cannot capture screenshots for review)` only if provisioning is itself impossible. Do NOT ask the caller to paste a URL or attach screenshots. Prefix (if pre-captured evidence used) with `⚠ Instance unreachable - review limited to pre-captured screenshots`.

## Agent-managed tools

This skill is part of an agent+skill bundle. See `agents/odoo-ui-reviewer.md` for the full
restricted tool list (OSM + chrome-devtools) and step-by-step execution detail.

## Continuation Contract

When you finish, append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next). Additive
output for the run-driver - it does not change anything produced above.
