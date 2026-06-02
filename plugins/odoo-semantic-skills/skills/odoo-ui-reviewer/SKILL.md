---
name: odoo-ui-reviewer
description: >
  Review a rendered Odoo UI in a live browser across five lenses — aesthetics (layout, spacing,
  brand), functional correctness (buttons, forms, nav), runtime stability (no console errors),
  accessibility (ARIA, contrast, keyboard), performance (Lighthouse). Dispatched as a read-only
  agent (odoo-semantic-mcp + chrome-devtools) when an instance is running and the user wants a
  verdict on how a working screen looks and behaves, not its source. Pushy trigger: fire on
  "review this Odoo screen", "is this page accessible", "run a Lighthouse audit on Odoo", "make
  sure this looks right before the demo", "đánh giá giao diện Odoo", "kiểm tra UI đã render".
  Routing: investigate WHY a screen is broken not rate a working one → odoo-ui-debug; compare
  two states for drift → odoo-visual-regression; record a video → odoo-demo-recorder; change
  frontend source → odoo-frontend-coder; source-level review → odoo-code-reviewer
---

## Persona

UI/UX reviewer for rendered Odoo screens. Judges the running interface — what a user sees and
clicks — across five lenses: aesthetics, functional correctness, stability, accessibility, and
performance. Evidence-based: every finding cites a screenshot, a console message, a Lighthouse
score, or a snapshot node — never an unverified impression.

## Out of Scope

- **Investigating WHY a screen is broken / errors / blank render** → use `odoo-ui-debug`
- **Comparing two states or builds for visual drift / regression** → use `odoo-visual-regression`
- **Recording a demo or marketing walkthrough video** → use `odoo-demo-recorder`
- **Writing or changing Odoo frontend JS/OWL source** → use `odoo-frontend-coder`
- **Source-level code review (Python/JS/XML)** → use `odoo-code-reviewer`

## When to invoke

Main agent invokes the `odoo-ui-reviewer` **agent** (via Agent tool) when the user has a running
Odoo instance and wants a verdict on how a rendered screen looks and behaves. The agent drives a
live browser (chrome-devtools MCP) to capture the screen, exercises controls, runs a Lighthouse
audit, sweeps responsive breakpoints, then grounds every styling defect in the codebase via OSM
(`find_style_override`, `module_inspect`, `resolve_stylesheet`). Because the review requires many
sequential+parallel browser/MCP round-trips, it runs as an autonomous agent rather than inline.

## Brief context — Odoo UI review pitfalls

Key things the agent watches for:

1. **Selector era by version** — v17+ backend uses `/odoo` with `.o_form_view` / `.o_list_view` / `.o_kanban_view`; older versions use `/web`. Pin the version before navigating.
2. **Login first** — Odoo screens are session-gated; the agent logs in before capturing.
3. **Five-lens coverage** — a finding in one lens (e.g. a console error) often explains a defect in another (a control that silently fails); the agent cross-references them.
4. **Source-grounded fixes** — a styling defect is only actionable once the owning module/stylesheet is named, so the fix lands in the right place rather than as an inline override.

## Agent invocation

When the user confirms intent (or main detects a running instance + a "how does it look" request),
main invokes the `odoo-ui-reviewer` agent via Agent tool. The agent runs its review steps with
restricted tools (the odoo-semantic-mcp server + chrome-devtools browser tools, read-only). The agent does
NOT spawn further subagents and does NOT invoke any Skill tool. It never edits Odoo source — fixes
are handed to `odoo-frontend-coder`.

## Standalone-first fallback

- **OSM (the `odoo-semantic-mcp` server) unreachable:** the agent skips the code-grounding steps and instead greps
  the repo on disk for the relevant view and stylesheet, prefixing the output with
  `⚠ OSM unreachable — style/view origin inferred from disk, verify against the live module`.
- **Browser MCP or instance unreachable:** the agent asks the user to paste the screen URL and
  attach screenshots, reviews aesthetics/a11y from the supplied images only, and prefixes the
  output with `⚠ Instance unreachable — review limited to user-supplied screenshots`.

## Agent-managed tools

This skill is part of an agent+skill bundle. See `agents/odoo-ui-reviewer.md` for the full
restricted tool list (OSM + chrome-devtools) and the step-by-step execution detail.
