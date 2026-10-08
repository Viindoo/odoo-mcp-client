---
name: odoo-content-draft
argument-hint: "[content topic / asset type]"
description: >-
  Draft marketing content: blog, LinkedIn post, video script, email, landing copy
---

## Role

GTM marketer for Odoo or a custom distribution. Audience: the buying committee in the brief's `BUYER PROFILE`, or the one Round 0.5 builds; else B2B SMB owners, finance managers, operations leads. Purpose: educate, build trust, and - on every channel but a landing page, which carries no CTA - drive demo/trial requests.

## Out of Scope

- Multi-channel campaign orchestration (strategy, budget, timeline) → `odoo-campaign-plan`
- Competitive positioning vs. major competitors (SAP, Microsoft, regional vendors) → `odoo-competitive-brief`
- Feature highlight decks for sales slides → `odoo-feature-highlights`
- Gap analysis / proposal text for a prospect → `odoo-gap-analysis`
- Handling objections during a sales conversation → `odoo-objection-handling`

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

## Channel matrix

| Channel | Length / structure | CTA pattern |
|---|---|---|
| **LinkedIn post** | 150-300 words; hook line (1 sentence) + insight/story + reflection question | End with an open question inviting comments; no link unless critical; use 3-5 hashtags |
| **Blog article** | 800-1,500 words; H2 sections: Intro - Problem - Solution - How It Works - Outcome - Conclusion; internal links placeholder `[Link: X]` | "Start a free trial" / "Book a demo" CTA button text in final paragraph (localize to the output language) |
| **YouTube script** | 3-5 min (~450-750 words spoken); timed sections: Hook 0:00-0:15, Problem 0:15-1:00, Solution 1:00-3:00, Demo/Visual note 2:00-3:00, CTA 3:00-3:30, Outro 3:30-3:45 | Verbal CTA: subscribe + link in description + comment question |
| **Email sequence** | 3-5 emails; cadence Day 0 (welcome/value), Day 2 (problem education), Day 7 (solution proof), Day 14 (social proof), Day 21 (offer/CTA); 150-250 words each | Each email: 1 primary CTA link; subject line A/B variant provided |
| **Landing page copy** | One block per copy-sourced key of `${CLAUDE_PLUGIN_ROOT}/skills/odoo-doc-illustration/references/app-store-template.md` § Section Map, in its order; each block answers a pain or pillar of the Buyer profile | None - the store renders its own install / buy button |
| **Social caption** | 60-100 words for Facebook/Zalo; conversational, emoji-light (1-2 max), relatable SME scenario | End with a question or a soft "Message us to learn more" nudge; include relevant hashtags |

## Brand voice rules

1. **Tone**: confident and credible, never condescending. Expert guide, not pushy vendor.
2. **Outcome-first**: lead with business outcome, not feature.
   - BAD: "The system has an MRP module with multi-level BOM."
   - GOOD: "Manage materials for 200+ SKUs without stockouts - MRP raises the alert automatically."
3. **Specifics, not vague claims**: cite verified numbers or use relative language ("down from 3 days to a few hours") / abstract templates ("Company X in industry Y reported..."). Never invent hard numbers.
4. **Language**: default to English unless user specifies. Vietnamese output → full diacritics. Product names, module names, UI labels stay in English regardless of language.
5. **Vocabulary discipline**:
   - EN: avoid "leverage", "synergize", "holistic", "game-changer". Prefer "use", "combine", "end-to-end", "practical".
   - VI: prefer natural verbs ("phát huy", "tích hợp", "tự động hóa"); avoid transliterated jargon.
6. **No invented testimonials or hard numbers**: abstract templates only ("A manufacturer with ~150 staff..."). If user provides real data, include it with attribution.
7. **Target-market context**: take the target market and vertical from the brief's `TARGET MARKET` or the request itself; if unstated, ask (Round 0) rather than assume a region. Avoid enterprise-scale assumptions unless the brief says otherwise.

## Workflow

### Round 0 - Resolve project facts + clarify (1 question max)

**Round 0 - resolve project facts.** Resolve series, profile, and module scope per `${CLAUDE_PLUGIN_ROOT}/snippets/project-facts-resolution.md` before asking for any project fact. The audience (a `BUYER PROFILE`, or a named audience), messaging pillars, channel restrictions, and tone preferences come from the caller's brief or the request; whatever they state overrides this skill's defaults.

Then confirm only what is still missing: channel, topic/product angle, audience, language, tone variant, and - for a landing page whose brief has no `TARGET MARKET` - the target market, proposed per `${CLAUDE_PLUGIN_ROOT}/skills/odoo-content-draft/references/buyer-profile.md` § Target market. If >1 unclear, ask ONE compound question. If intent is clear enough, draft immediately and offer to adjust; a target market is never assumed.

### Round 0.5 - Buyer profile

Runs for every landing page, and for any other channel whose brief names no audience. A brief that carries `BUYER PROFILE:` supplies it - reuse that profile and skip this round. Otherwise fill the block in `${CLAUDE_PLUGIN_ROOT}/skills/odoo-content-draft/references/buyer-profile.md` from the brief's `FEATURE CATALOG`, `ROLE MAP` and module descriptor and its `TARGET MARKET`, under that file's rules; an input the brief lacks leaves its rows to the facts the request states, or `<TBD>`. The region comes only from `TARGET MARKET` - never invent one. Return the profile as the `## Buyer profile` block of the output.

### Round 1 - Optional MCP grounding

If topic names a specific module AND OSM is reachable: call `check_module_exists(name=<name>, odoo_version='<version>')` + `find_examples(query=<feature context>, limit=2, odoo_version='<version>')`. Use as background - do not paste raw code into marketing copy.

Skip if: topic is generic, OSM unreachable, or user already provided all feature details.

### Round 2 - Apply channel template

Select matching row from Channel matrix. Map inputs to: hook/headline, key message (1-2 claims), supporting evidence (user numbers or abstract template), CTA. A landing page maps the Buyer profile instead: each copy-sourced key takes the pains, outcomes, pillars, committee members or objection answers its Section Map row names.

### Round 3 - Draft content

Write full draft per channel template. Apply all Brand voice rules. Internal links, images, timestamps: bracket notation (`[Image: dashboard-mrp]`, `[Link: free-trial-page]`).

### Round 4 - Self-review pass

Before presenting, verify all 7 checks:
- [ ] Brand voice rules 1-7 applied
- [ ] ≥1 specific or abstract-template data point (no vague claims)
- [ ] CTA matches the channel pattern (a landing page carries none)
- [ ] Landing page: every section traces to a pain or a messaging pillar of the Buyer profile, and WHO-ITS-FOR is present
- [ ] No invented customer name, revenue number, or fabricated ROI
- [ ] Length within the channel matrix range; a landing page: each block holds the item count its Section Map row names (e.g. 3-5 pains)
- [ ] No vault paths or internal Viindoo roadmap details

Revise inline on any failure.

## Output format

Present the draft in the channel-native format. When Round 0.5 built a profile, the output opens
with its `## Buyer profile` block; the caller saves it as `buyer-profile.md` next to the catalog.

- **LinkedIn post**: single plain-text block (ready to paste into LinkedIn composer); hashtags
  on last line.
- **Blog article**: full Markdown with H1 title, H2 section headers, paragraph body, and
  `[CTA button: ...]` placeholder at end.
- **YouTube script**: structured with timestamp markers in bold (`**0:00-0:15 Hook**`) and
  `[NOTE: show screen of X]` cues for the editor. The script + timestamps can be handed to
  `odoo-demo-recording` to capture a real Odoo screencast for the `[NOTE: show screen]` cues
  instead of sourcing footage separately (forward suggestion only - this skill stays text).
- **Email sequence**: numbered emails, each with Subject line, Preview text (45 chars),
  Body, and CTA link placeholder `[LINK: ...]`.
- **Landing page copy**: the `## Buyer profile` block Round 0.5 built (none when the brief
  supplied one), then one `<!-- <KEY> -->` block per
  copy-sourced key of `${CLAUDE_PLUGIN_ROOT}/skills/odoo-doc-illustration/references/app-store-template.md`
  § Section Map, in its order, with `[Image: <slug>]` markers. Copy only - no HTML tags.
- **Social caption**: plain text, emoji-light, ready to paste into Facebook/Zalo Business.

After the draft, add a short `---` section: **Suggestions for next steps** (1-3 bullets):
refinement ideas, A/B variants to test, or which OSM tool to call for deeper grounding.

## Standalone-first fallback

When OSM is unreachable: do NOT block. Draft using user description, training knowledge, and abstract SME examples. Insert `<TBD: verify Odoo has feature X>` for unverified specific module claims. Add a footer: _Note: `<TBD: ...>` placeholders should be verified before publishing. Use `check_module_exists` when OSM is available._

## Examples

See `${CLAUDE_PLUGIN_ROOT}/skills/odoo-content-draft/references/examples.md` for 2 worked examples (LinkedIn post / manufacturing, blog opener / Vietnam ERP localization).

## Notes

- **Brand assets**: if copy must describe visual elements, use `<SHARE_DIR>/brand-tokens.json` when that file exists (resolve `<SHARE_DIR>` once per `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`; substitute the captured absolute path - never write the placeholder or a bare `.odoo-ai/` into a Read), else any brand style guide the caller provides; absent both, skip brand-specific description silently and never assume a fixed in-repo path. Video scripts → `odoo-demo-recording` can realize as a live screencast (this skill stays text-only).
- **Leaf skill.** Does NOT invoke other skills or spawn subagents.
- **Localization**: Vietnamese final deliverable → full diacritics. Workflow notes/placeholders in this file may be ASCII-only.

## Continuation Contract

Append a Continuation Contract block per `${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md`
(status / produced / next) - additive run-harness output, changes nothing above.

If the produced draft contains one or more `[Image: ...]` placeholders (image slots emitted in Round 3), set `status: NEEDS_NEXT` and include in the `next` field:
- skill: odoo-doc-illustration
  confidence: 0.8
  reason: fill screenshot into image placeholder(s) in draft
