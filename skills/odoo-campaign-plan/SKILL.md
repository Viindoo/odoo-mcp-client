---
name: odoo-campaign-plan
description: >
  Plan a multi-week, multi-channel marketing campaign for a Viindoo / Odoo vertical or
  geography push. Given target vertical or geo, campaign objective, timeline, budget
  category (S/M/L), and available channels, produce a complete campaign blueprint:
  week-by-week timeline, channel mix matrix, content asset inventory, KPI definitions,
  and an owner map that distinguishes AI-doable tasks from human-required tasks.
  This skill ORCHESTRATES campaigns; it does NOT draft individual content pieces.
  Trigger on: "lập kế hoạch campaign", "plan campaign Q3 cho manufacturing",
  "campaign brief cho vertical X", "lập chiến dịch marketing 4 tuần",
  "thiết kế campaign multi-channel", "plan a campaign for", "campaign brief",
  "multi-channel plan for vertical X", "Q3 marketing push plan",
  "build a campaign blueprint", "marketing push plan for", "lên kế hoạch chiến dịch",
  "campaign roadmap cho", "kế hoạch go-to-market cho", "4-week campaign plan",
  "8-week campaign for", "go-to-market blueprint".
  DO NOT trigger for: drafting an individual piece of content (→ odoo-content-draft),
  competitive positioning analysis (→ odoo-competitive-brief),
  feature-highlight slides for a sales deck (→ odoo-feature-highlights),
  capability proof for a prospect (→ odoo-capability-proof).
  This skill is STANDALONE-FIRST: works without MCP. OSM tools optional for
  feature-claim verification only
---

## Persona

Marketer — Viindoo Vietnam SME ERP go-to-market team. Planning B2B campaigns targeting
Vietnamese small-to-medium business owners, department heads (finance, operations,
manufacturing), and IT decision-makers. Campaign purpose: generate awareness, drive demo
requests, and support regional or vertical expansion.

## Out of Scope

- Drafting individual content pieces (blog posts, LinkedIn posts, email sequences)
  → `odoo-content-draft`
- Competitive positioning vs. SAP / Microsoft Dynamics / MISA
  → `odoo-competitive-brief`
- Feature-highlight decks for sales slides or proposal presentations
  → `odoo-feature-highlights`
- Capability proofs or RFP responses for a specific prospect
  → `odoo-capability-proof`
- Gap analysis or proposal text for a named opportunity
  → `odoo-gap-analysis`

## MCP tools

<!-- BEGIN MANUAL TOOLS — odoo-campaign-plan -->
_Tool surface: server v0.8.0. See [`docs/reference/mcp-tool-routing.md`](../../docs/reference/mcp-tool-routing.md) for full routing matrix._

**Optional — use only when verifying a specific feature claim in the campaign angle:**
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

### Round 0 - Confirm campaign inputs

Before building the plan, confirm all six inputs. If more than one is missing, ask ONE
compound question. If the user's request contains enough context, infer reasonable defaults
and proceed — offer to adjust afterward.

**Required inputs:**
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
6. **Odoo version / edition** (default: read from `.odoo-ai/context.md` if present; fallback
   to "Odoo 17 CE" if file absent)

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

### Round 6 - Owner map (one-man-company aware)

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

## Owner map (one-man-company)
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
```

After the plan, add a short `---` section: **Campaign health checks** (2-3 bullets) — the
most common reasons this type of campaign underperforms and what to watch in week 1-2.

## Standalone-first fallback

When OSM is unreachable or the skill is used without MCP configuration:

1. Do NOT block. Produce the full campaign plan using:
   - User's verbal description of the product angle and target market
   - General Odoo/Viindoo product knowledge from training data
   - Abstract SME examples and relative performance benchmarks (no fabricated hard numbers)

2. Insert `<TBD: verify Odoo has feature X in version Y>` placeholders for any specific
   feature claim that anchors the campaign angle but cannot be confirmed without OSM.
   Example:
   > "Campaign angle: Vietnam VAT e-invoice compliance via `<TBD: verify l10n_vn_edi module
   > in target version>` — confirm before finalizing messaging."

3. Add a note at the end of the plan:
   > _Note: Cac placeholder `<TBD: ...>` can xac nhan bang `check_module_exists` khi OSM kha
   > dung. Nhung placeholder nay khong can thiet neu goc do campaign la chung (vi du: chuyen
   > doi so, tang nang suat SME)._

## Examples

### Example 1 - Vietnamese (Manufacturing SME / Miền Bắc)

**Input:**
- Vertical: sản xuất (ngành nội thất / gỗ)
- Geo: Mien Bac (Ha Noi, Binh Duong khu cong nghiep)
- Objective: lead generation — demo requests
- Timeline: 6 weeks
- Budget: M
- Channels: Blog, LinkedIn company, email list (~500 contacts), light Google Ads remarketing

**Summary of plan output:**

- **Title**: "Campaign Plan: MRP cho Nhà Máy Nội Thất Miền Bắc — Q3 2026"
- **Angle**: Vertical pain → product fit ("Quản lý nguyên liệu bằng Excel → MRP tự động hóa
  kế hoạch sản xuất")
- **Timeline**: Tuần 1-2 nhận thức (bài blog "5 dấu hiệu Excel không đủ"); Tuần 3-4 sản phẩm
  (demo video MRP, email sequence 3 email); Tuần 5-6 conversion (landing page CTA, Google Ads
  remarketing đến người đã đọc blog)
- **Channel mix**: Blog 20% / LinkedIn 25% / Email 25% / Google Ads 20% / Landing page 10%
- **KPI leading**: blog unique visitors/week (target: +30% vs. baseline), email open rate >30%
- **KPI lagging**: demo requests submitted (target: 15 trong 6 tuan), cost per demo <$25
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

- **Project context file**: if the working repository contains `.odoo-ai/context.md`, read it
  at session start for Odoo version default, target audience personas, approved messaging
  pillars, and any channel restrictions. Settings in that file take precedence over this
  skill's generic defaults.
- **Brand assets**: for color palette, logo usage, and typography guidelines, refer to the
  internal document named `Viindoo Brand Assets`. This skill produces a planning document, not
  visual assets — but reference `Viindoo Brand Assets` when the plan includes a landing page
  brief or visual design spec that will be handed to a designer.
- **No fabricated data**: NEVER invent customer names, real revenue figures, or hard ROI
  percentages in the plan. Use abstract templates: "Một doanh nghiệp sản xuất tại miền Nam
  với ~150 nhân sự" or "A trading company in the FMCG sector reported...". If the user
  provides real data verbally, incorporate it with attribution.
- **Depth rule**: this skill operates at depth 1 (called from main agent). It does NOT invoke
  other skills or spawn subagents. The campaign plan is a text deliverable — the marketer
  executes it, the main agent does not chain it into another automated tool.
- **Localization note**: output defaults to Vietnamese with full diacritics. Switch to English
  only when the user explicitly requests it. Product names, module names, and channel names
  remain in English regardless of output language (e.g., "module MRP", "LinkedIn Ads",
  "Google Search Console").
