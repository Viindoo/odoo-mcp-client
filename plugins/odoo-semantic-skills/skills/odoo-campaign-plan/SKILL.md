---
name: odoo-campaign-plan
description: >
  Plan a multi-week, multi-channel marketing campaign for an Odoo vertical or geography push
  — blueprint with timeline, channel mix matrix, asset inventory, KPIs, and owner map
  (AI-doable vs human-required). ORCHESTRATES campaigns; does NOT draft individual content.
  Trigger on: "plan a campaign for", "campaign brief", "multi-channel plan for vertical X",
  "build a campaign blueprint", "marketing push plan for", "campaign roadmap for",
  "go-to-market blueprint".
  Also fires on Vietnamese: "lập kế hoạch chiến dịch", "kế hoạch marketing đa kênh",
  "chiến dịch go-to-market cho ngành X", "lộ trình truyền thông".
  DO NOT trigger for: individual content draft (→ odoo-content-draft),
  competitive positioning analysis (→ odoo-competitive-brief),
  feature-highlight slides for a sales deck (→ odoo-feature-highlights),
  capability proof for a prospect (→ odoo-capability-proof).
  STANDALONE-FIRST: works without MCP; OSM optional for feature-claim verification only
---

## Persona

Marketer — Odoo / your Odoo distribution go-to-market team. Planning B2B campaigns targeting
small-to-medium business owners, department heads (finance, operations,
manufacturing), and IT decision-makers. Campaign purpose: generate awareness, drive demo
requests, and support regional or vertical expansion.

## Out of Scope

- Drafting individual content pieces (blog posts, LinkedIn posts, email sequences)
  → `odoo-content-draft`
- Competitive positioning vs. major competitors (SAP, Microsoft Dynamics, regional vendors)
  → `odoo-competitive-brief`
- Feature-highlight decks for sales slides or proposal presentations
  → `odoo-feature-highlights`
- Capability proofs or RFP responses for a specific prospect
  → `odoo-capability-proof`
- Gap analysis or proposal text for a named opportunity
  → `odoo-gap-analysis`

## MCP tools

<!-- BEGIN MANUAL TOOLS — odoo-campaign-plan -->
_Tool surface: server v0.13.1. See [`docs/reference/mcp-tool-routing.md`](../../docs/reference/mcp-tool-routing.md) for full routing matrix._

**Optional — use only when verifying a specific feature claim in the campaign angle:**
- `profile_inspect` — When the campaign angle is "competitive displacement" or "platform breadth"
  (a claim about what the platform actually covers), call `profile_inspect(method='modules', name=<profile>,
  odoo_version='<version>')` to ground the breadth claim in the real module inventory rather than asserting it.
- `check_module_exists` — Confirm that a named Odoo/Viindoo module is present in the
  target version before including a feature claim in the campaign (e.g., "Vietnam VAT
  compliance via l10n_vn", "MRP multi-level BOM"). Call when user names a specific module
  and the claim is central to the campaign angle.
- `find_examples` — Retrieve 1-2 real code or config examples from the indexed codebase
  for technical grounding. Use sparingly — campaign plans reference features at a business
  level, not implementation level.

**NOT required** for most campaigns. Skip both if:
- The campaign angle is generic (digital transformation, SME productivity, regional expansion)
- OSM is unreachable (see Standalone-first fallback section)
- User has already confirmed the feature exists or provided a product brief
<!-- END MANUAL TOOLS — odoo-campaign-plan -->

## Workflow

### Round 0 - Context bootstrap + confirm campaign inputs

Before asking the user for anything, read what onboarding already captured
(see `${CLAUDE_PLUGIN_ROOT}/snippets/context-bootstrap.md`):

1. **Read `.odoo-ai/context.md`** if present. Extract and apply as authoritative overrides:
   - `odoo_version` - used as the default for all feature-claim verification and version
     references in the plan.
   - Audience personas / messaging pillars defined there override this skill's generic
     defaults.
   - Channel restrictions (e.g., "no paid ads", "LinkedIn only") recorded there are applied
     without asking.
2. If the file is absent, proceed with this skill's generic defaults.

After the bootstrap, confirm only what is still missing. If more than one input is unclear,
ask ONE compound question. If the user's request contains enough context, infer reasonable
defaults and proceed - offer to adjust afterward.

**Required inputs (resolved by bootstrap or user):**
1. **Target vertical or geo**: which industry (manufacturing, trading, services, F&B, retail)
   or geography (Hanoi, HCMC, Mekong Delta, export market) is this campaign for?
2. **Campaign objective**: lead generation, brand awareness, product launch / release
   announcement, or retention / upsell?
3. **Timeline**: how many weeks? (4-8 weeks recommended; fewer = tactical burst,
   more = phased drip)
4. **Budget category**:
   - **S (Small)**: content-only, no paid ads; LinkedIn organic + blog + email
   - **M (Medium)**: light paid amplification; LinkedIn + Google Ads remarketing + blog + email
   - **L (Large)**: full paid mix; LinkedIn Ads + Google Search + YouTube + landing page + email
5. **Available channels**: which channels can the team actually publish to? (LinkedIn company
   page, personal LinkedIn, blog/website, YouTube, email list, Facebook/Zalo page, paid ads)
6. **Odoo version / edition** (resolved from `.odoo-ai/context.md` in bootstrap step above;
   fallback to "Odoo 17 CE" if file absent and user does not specify)

### Round 1 - Frame the campaign angle

Choose ONE primary angle. One campaign = one angle. Mixing angles dilutes message and budget.

| Angle | When to use | Core message structure |
|---|---|---|
| **Vertical pain → product fit** | Entering a new industry segment | "Industry X suffers pain Y → Odoo module Z solves it exactly" |
| **Geo localization** | Expanding to a new region | "Odoo now speaks your market: localization + local partner + local references" |
| **Release announcement** | New version or major feature shipped | "What's new in Odoo X.Y that matters for SMEs" |
| **Competitive displacement** | Active competitor in territory | "Why companies switching from [category] are choosing Odoo" |

Declare the chosen angle explicitly in the plan output. If the user's objective suggests a
different angle than the default inference, flag it and ask for a one-word confirmation before
proceeding.

Optional MCP step (if angle depends on a specific feature claim):
1. Call `check_module_exists` to confirm the module is present in the target version.
2. If absent or uncertain, insert `<TBD: verify feature X in version Y>` placeholder.

### Round 2 - Build week-by-week timeline

Construct a week-by-week table for the confirmed duration (4-8 weeks). Each week has:
- **Theme**: one-sentence content focus for that week
- **Touchpoints**: 2-3 channel actions (specific, e.g., "Publish blog post on topic X",
  "Send email #2 to list segment Y", "Post LinkedIn carousel")
- **Asset needed**: what content piece must be created (these feed the Asset inventory
  in Round 4)

Structure: Awareness weeks first (broad problem framing) → Consideration weeks (product fit,
demos) → Conversion/CTA weeks (offer, urgency, follow-up). Adjust ratio based on objective:
- Lead generation: 40% awareness / 40% consideration / 20% conversion
- Brand awareness: 60% awareness / 30% consideration / 10% CTA
- Release announcement: 20% teaser / 50% launch week / 30% follow-up

### Round 3 - Channel mix matrix

For the confirmed channel list and budget category, allocate effort percentage across channels.
Effort % = share of total production + distribution time for the campaign period.

Default allocations by budget category:

**Budget S (content-only):**
| Channel | Effort % | Notes |
|---|---|---|
| Blog / SEO | 30% | 2-3 long-form posts; evergreen |
| LinkedIn organic | 30% | 2x/week posts; company + personal |
| Email | 30% | 3-4 email sequence to existing list |
| Other social (FB/Zalo) | 10% | Repurposed from LinkedIn |

**Budget M (light paid):**
| Channel | Effort % | Notes |
|---|---|---|
| LinkedIn organic | 25% | As above |
| Blog / SEO | 20% | |
| Email | 20% | |
| LinkedIn / Google Ads | 20% | Remarketing only; requires landing page |
| Landing page | 10% | Dedicated campaign page |
| Other social | 5% | |

**Budget L (full paid):**
| Channel | Effort % | Notes |
|---|---|---|
| LinkedIn Ads | 25% | Sponsored content + lead gen form |
| Google Search Ads | 20% | Keyword-targeted; needs ad copy |
| Blog / SEO | 15% | |
| Email | 15% | |
| YouTube | 10% | 1-2 short videos (60-90 sec) |
| Landing page | 10% | A/B tested headline |
| Other social | 5% | |

Adjust percentages to match the user's actual available channels. Channels not available
drop to 0%; redistribute proportionally.

### Round 4 - Asset inventory

List every content piece required by the timeline. For each asset:
- **Type**: blog post, LinkedIn post, email (numbered), YouTube script, landing page copy,
  social caption, ad copy (headline + description), infographic brief
- **Target length / format**: approximate word count or duration
- **Audience**: which persona this piece targets
- **Draft via**: reference `odoo-content-draft` for all text drafting tasks

Group assets by week so the marketer can sequence production before distribution.

### Round 5 - KPI definition

Define 2-3 leading metrics and 2-3 lagging metrics, specific to the campaign objective.

**Lead generation objective:**
- Leading: weekly new email list subscribers, LinkedIn post engagement rate,
  landing page unique visitors
- Lagging: demo requests submitted, qualified leads (MQL), cost per lead (if paid budget)

**Brand awareness objective:**
- Leading: content reach (impressions), share / save rate, blog session duration
- Lagging: branded search volume trend (Google Search Console), inbound contact form
  (unprompted), community mentions

**Release announcement objective:**
- Leading: announcement post reach, click-through to release notes / changelog,
  email open rate on launch day
- Lagging: trial sign-ups attributable to campaign period, upgrade rate (existing customers),
  press / partner mentions

**Retention / upsell objective:**
- Leading: email open rate (existing customer segment), webinar / demo registrations,
  feature adoption (if tracked)
- Lagging: NPS movement, upsell pipeline created, churn delta vs. baseline period

For each metric, provide a concrete measurement method (Google Analytics event, LinkedIn
Analytics export, email platform dashboard) so ownership is clear.

### Round 6 - Owner map (small-team founder aware)

For each task in the campaign, classify as:

- **AI-doable** — can be fully delegated to an AI skill; the human reviews and approves
  the output but does not write it:
  - All text drafts → `odoo-content-draft`
  - Competitive angle research → `odoo-competitive-brief`
  - Feature claims verification → OSM `check_module_exists`
  - Campaign plan iteration → this skill (`odoo-campaign-plan`)

- **Human-required** — requires human judgment, relationships, or access:
  - Strategic go/no-go on campaign angle (Round 1 decision)
  - Budget authorization and paid ad account setup
  - Publishing / scheduling content on owned channels (LinkedIn company page admin, email
    platform send)
  - Sales follow-up on leads generated
  - Partnerships, co-marketing agreements, or event commitments
  - Final review and approval of all published content

Present this as a two-column list so a one-person team can immediately see their personal
time commitment vs. what they can offload.

## Output format

Present the campaign plan in the following Markdown structure:

```
# Campaign Plan: <Campaign Title>

## Objective
<One sentence: what success looks like at campaign end>

## Angle + audience
- **Primary angle**: <vertical pain / geo localization / release announcement / competitive displacement>
- **Target audience**: <persona — title, company type, challenge>
- **Pain hook**: <one-line problem statement that opens all campaign messaging>

## Timeline (<N> weeks)
| Week | Theme | Touchpoints | Asset needed |
|---|---|---|---|
| 1 | <theme> | <2-3 actions> | <content piece> |
| 2 | ... | ... | ... |
...

## Channel mix
| Channel | Effort % | Budget category | Owner |
|---|---|---|---|
| Blog / SEO | <X>% | S/M/L | AI-doable (draft) / Human-required (publish) |
...

## Asset inventory
- **Week 1** — [Asset name] — <type, ~N words> — Audience: <persona> — Draft via `odoo-content-draft`
- **Week 2** — ...
...

## KPI definition
- **Leading**: <metric 1> (measure via: <tool/dashboard>), <metric 2>, <metric 3>
- **Lagging**: <metric 1> (measure via: <tool/dashboard>), <metric 2>, <metric 3>

## Owner map (small-team founder)
### AI-doable (delegate)
- <task> → `odoo-content-draft` / `odoo-competitive-brief` / OSM / this skill
...

### Human-required (your time)
- <task> — estimated <N min/hr per week>
...

## Suggested next skills
- `odoo-content-draft` — draft each asset listed in Asset inventory above
- `odoo-competitive-brief` — if angle is competitive displacement
- `odoo-feature-highlights` — if angle is release announcement and slide deck is needed
- `odoo-capability-proof` — if a specific prospect demo is part of the campaign
- `odoo-demo-recording` — if the asset inventory includes demo videos / screencasts (capture them for real from a live instance instead of briefing a designer)
```

After the plan, add a short `---` section: **Campaign health checks** (2-3 bullets) — the
most common reasons this type of campaign underperforms and what to watch in week 1-2.

## Standalone-first fallback

When OSM is unreachable or the skill is used without MCP configuration:

1. Do NOT block. Produce the full campaign plan using:
   - User's verbal description of the product angle and target market
   - General Odoo / your Odoo distribution product knowledge from training data
   - Abstract SME examples and relative performance benchmarks (no fabricated hard numbers)

2. Insert `<TBD: verify Odoo has feature X in version Y>` placeholders for any specific
   feature claim that anchors the campaign angle but cannot be confirmed without OSM.
   Example:
   > "Campaign angle: Vietnam VAT e-invoice compliance via `<TBD: verify l10n_vn_edi module
   > in target version>` — confirm before finalizing messaging."

3. Add a note at the end of the plan:
   > _Note: `<TBD: ...>` placeholders can be confirmed with `check_module_exists` once OSM is
   > available. These placeholders are not needed if the campaign angle is generic (e.g.,
   > digital transformation, SME productivity improvement)._

## Examples

### Example 1 - Manufacturing SME / Northern Vietnam

**Input:**
- Vertical: manufacturing (furniture / wood industry)
- Geo: Northern Vietnam (Hanoi, Binh Duong industrial zones)
- Objective: lead generation - demo requests
- Timeline: 6 weeks
- Budget: M
- Channels: Blog, LinkedIn company, email list (~500 contacts), light Google Ads remarketing

**Summary of plan output:**

- **Title**: "Campaign Plan: MRP for Furniture Factories in Northern Vietnam - Q3 2026"
- **Angle**: Vertical pain → product fit ("Managing materials in Excel → MRP automates the
  production plan")
- **Timeline**: Weeks 1-2 awareness (blog post "5 signs Excel is not enough"); Weeks 3-4
  product (MRP demo video, 3-email sequence); Weeks 5-6 conversion (landing page CTA, Google
  Ads remarketing to people who read the blog)
- **Channel mix**: Blog 20% / LinkedIn 25% / Email 25% / Google Ads 20% / Landing page 10%
- **KPI leading**: blog unique visitors/week (target: +30% vs. baseline), email open rate >30%
- **KPI lagging**: demo requests submitted (target: 15 in 6 weeks), cost per demo <$25
- **Owner map**: draft all 7 assets → `odoo-content-draft`; ad setup + publish + sales
  follow-up → Human

### Example 2 - English (Q4 Release Announcement)

**Input:**
- Angle: Release announcement — new Odoo 18 features for SME
- Objective: Awareness + trial sign-ups from existing community (Odoo partners + prospects)
- Timeline: 4 weeks
- Budget: S (content-only)
- Channels: Blog, LinkedIn personal + company, email list

**Summary of plan output:**

- **Title**: "Campaign Plan: Odoo 18 SME Features — Q4 Announcement"
- **Angle**: Release announcement ("What's new in Odoo 18 that your SME will actually use")
- **Week 1**: Teaser — "What's coming" LinkedIn post + email preview to list
- **Week 2**: Launch — long-form blog post (1,200 words, top 5 features), LinkedIn article
  repurpose, email #1 (announcement)
- **Week 3**: Deep-dive — two LinkedIn posts (one per feature), email #2 (use case story)
- **Week 4**: CTA push — email #3 (trial offer), LinkedIn final recap post
- **Assets**: 1 blog post, 4 LinkedIn posts, 3 emails — all drafted via `odoo-content-draft`
- **KPI leading**: LinkedIn post reach, email open rate (target >35% on launch week email)
- **KPI lagging**: trial sign-ups attributable to campaign period, blog-to-trial conversion %
- **Owner map**: all 8 assets AI-doable; scheduling + publish + partner outreach = Human (est.
  ~3 hr/week)

## Notes

- **Project context file**: `.odoo-ai/context.md` is read automatically in Round 0
  (see `${CLAUDE_PLUGIN_ROOT}/snippets/context-bootstrap.md`) - not at the end as an
  optional note. `odoo_version`, audience personas, approved messaging pillars, and channel
  restrictions found there are applied as authoritative overrides before any clarification
  question is asked.
- **Brand assets**: for color palette, logo usage, and typography guidelines, refer to your
  project's brand guidelines document if one is checked into the working repository (e.g.,
  `branding/STYLE.md` or equivalent). This skill produces a planning document, not visual
  assets — but reference the brand guidelines when the plan includes a landing page brief
  or visual design spec that will be handed to a designer. When the asset inventory lists demo
  videos or screencasts, `odoo-demo-recording` can capture them from a live instance (forward
  suggestion only — this skill stays a planning document).
- **No fabricated data**: NEVER invent customer names, real revenue figures, or hard ROI
  percentages in the plan. Use abstract templates: "A manufacturing company in the southern
  region with ~150 employees" or "A trading company in the FMCG sector reported...". If the
  user provides real data verbally, incorporate it with attribution.
- **Depth rule**: this skill operates at depth 1 (called from main agent). It does NOT invoke
  other skills or spawn subagents. The campaign plan is a text deliverable — the marketer
  executes it, the main agent does not chain it into another automated tool.
- **Localization note**: output language follows the user's request language. Product names,
  module names, and channel names remain in English regardless of output language
  (e.g., "MRP module", "LinkedIn Ads", "Google Search Console").

## Continuation Contract

When you finish, append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next). Additive
output for the depth-0 run-driver - it does not change anything produced above.
