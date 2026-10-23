---
name: odoo-content-draft
argument-hint: "[content topic / asset type]"
description: >-
  Draft marketing content: blog, LinkedIn post, video script, email, landing copy
---

## Role

Front door for one piece of marketing content about Odoo or a custom distribution: a blog
article, a LinkedIn post, a YouTube script, an email sequence, landing-page copy blocks or a
social caption. Audience: the buying committee of the brief's `BUYER PROFILE`, or the one the
writer builds. It resolves the facts, settles what the request leaves open, and launches ONE
`odoo-marketer` in `MODE: copy`, which verifies every claim and searches earlier drafts before it
writes.

## Out of Scope

- Multi-channel campaign orchestration (strategy, budget, timeline) -> `odoo-campaign-plan`
- Competitive positioning vs. major competitors (SAP, Microsoft, regional vendors) -> `odoo-competitive-brief`
- Feature highlight decks for sales slides -> `odoo-feature-highlights`
- Gap analysis / proposal text for a prospect -> `odoo-gap-analysis`
- Handling objections during a sales conversation -> `odoo-objection-handling`
- A module's App Store page with live screenshots and manifest images -> `odoo-doc-illustration`

## MCP tools

<!-- BEGIN MANUAL TOOLS - odoo-content-draft -->

**Optional - use only when grounding a specific feature claim:**
- `check_module_exists` - Verify that a named Odoo/Viindoo module actually exists before
  citing it in content. Call when user names a specific module (e.g., "mrp", "helpdesk")
  and you want to confirm edition (CE/EE/Viindoo) and version presence.
- `find_examples` - Fetch 1-2 real code or config snippets from the indexed Odoo codebase
  for technical credibility (e.g., a field name, a workflow state). Use sparingly; content
  audiences rarely need raw code.

**NOT required** for most drafts. Skip both if:
- The topic is generic (ERP benefits, SME pain points, productivity tips)
- OSM is unreachable (see Standalone-first fallback section)
- User has already provided feature details verbally
<!-- END MANUAL TOOLS - odoo-content-draft -->

## Steps

1. **Resolve project facts** per `${CLAUDE_PLUGIN_ROOT}/snippets/project-facts-resolution.md`
   before asking for any project fact; capture `SHARE_DIR` and `ISOLATE_DIR` once
   (`${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`). The audience (`BUYER PROFILE` or
   a named audience), messaging pillars, channel restrictions and tone come from the caller's
   brief or the request; whatever they state overrides any default.
2. **Clarify once.** Confirm only what is still missing: channel, topic or product angle,
   audience, output language, tone, and - for landing-page copy whose brief has no
   `TARGET MARKET` - the target market, proposed per `references/buyer-profile.md` § Target
   market. More than one unclear: ONE compound question. Clear enough: launch at once and offer
   to adjust; a target market is never assumed.
3. **Launch `odoo-marketer`** with `MODE: copy` and the brief of `references/marketer-brief.md`,
   `model` per `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § Model-tier selection
   (composing is sonnet; re-cutting an existing draft to another channel is haiku). A revision the
   user asks for goes to the same agent with `SendMessage`, never a new launch.
4. **Return** the draft as the agent wrote it (channel-native format, the `## Buyer profile`
   block first when it built one, every `<TBD: ...>` kept visible), its saved path, and the
   agent's `concerns`. A draft that carries `[Image: ...]` placeholders returns `NEEDS_NEXT` ->
   `odoo-doc-illustration`.

## Standalone-first fallback

OSM unreachable: the marketer drafts from the request, the catalog and abstract SME examples,
marks every unverified module claim `<TBD: verify Odoo has feature X>` and the draft carries a
footer saying the placeholders must be verified before publishing. Never block.

## Agent-managed tools

`odoo-marketer` (`MODE: copy`).

## Continuation Contract

Append a Continuation Contract block per `${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md`
(status / produced / next). A draft with one or more `[Image: ...]` placeholders sets
`status: NEEDS_NEXT` with `next: odoo-doc-illustration` (fill the image slots with live screenshots).
