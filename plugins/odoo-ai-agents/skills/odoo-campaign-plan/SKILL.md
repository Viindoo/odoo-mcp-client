---
name: odoo-campaign-plan
description: >
  Plan a multi-week, multi-channel marketing campaign for an Odoo vertical or geography push
  - blueprint with timeline, channel mix matrix, asset inventory, KPIs, and owner map
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

Marketer on the Odoo / your-distribution go-to-market team. Plans B2B campaigns targeting SMB
owners, department heads (finance, operations, manufacturing), and IT decision-makers. Purpose:
generate awareness, drive demo requests, support regional or vertical expansion.

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

<!-- BEGIN MANUAL TOOLS - odoo-campaign-plan -->

**Optional - use only when verifying a specific feature claim in the campaign angle:**
- `profile_inspect` - When the campaign angle is "competitive displacement" or "platform breadth"
  (a claim about what the platform actually covers), call `profile_inspect(method='modules', name=<profile>,
  odoo_version='<version>')` to ground the breadth claim in the real module inventory rather than asserting it.
- `check_module_exists` - Confirm that a named Odoo/Viindoo module is present in the
  target version before including a feature claim in the campaign (e.g., "Vietnam VAT
  compliance via l10n_vn", "MRP multi-level BOM"). Call when user names a specific module
  and the claim is central to the campaign angle.
- `find_examples` - Retrieve 1-2 real code or config examples from the indexed codebase
  for technical grounding. Use sparingly - campaign plans reference features at a business
  level, not implementation level.

**NOT required** for most campaigns. Skip both if:
- The campaign angle is generic (digital transformation, SME productivity, regional expansion)
- OSM is unreachable (see Standalone-first fallback section)
- User has already confirmed the feature exists or provided a product brief
<!-- END MANUAL TOOLS - odoo-campaign-plan -->

## Workflow

### Round 0 - Context bootstrap + confirm campaign inputs

Before asking anything, read what onboarding captured
(see `${CLAUDE_PLUGIN_ROOT}/snippets/context-bootstrap.md`):

1. **Read `.odoo-ai/context.md`** if present; apply as authoritative overrides:
   - `odoo_version` - default for all feature-claim verification and version references.
   - Audience personas / messaging pillars there override this skill's generic defaults.
   - Channel restrictions (e.g. "no paid ads", "LinkedIn only") are applied without asking.
2. If the file is absent, use this skill's generic defaults.

After bootstrap, confirm only what is still missing. If >1 input is unclear, ask ONE compound
question. If the request has enough context, infer reasonable defaults and proceed - offer to
adjust afterward.

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

Declare the chosen angle explicitly in the plan output. If the objective suggests a different
angle than inferred, flag it and ask for a one-word confirmation first.

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
Effort % = share of total production + distribution time for the campaign period. Use the default
allocations per budget category (S / M / L) in
`${CLAUDE_PLUGIN_ROOT}/skills/odoo-campaign-plan/references/channel-mix.md`, then adjust to the
user's actual available channels - channels not available drop to 0%, redistribute proportionally.

### Round 4 - Asset inventory

List every content piece required by the timeline. For each asset:
- **Type**: blog post, LinkedIn post, email (numbered), YouTube script, landing page copy,
  social caption, ad copy (headline + description), infographic brief
- **Target length / format**: approximate word count or duration
- **Audience**: which persona this piece targets
- **Draft via**: reference `odoo-content-draft` for all text drafting tasks

Group assets by week so the marketer can sequence production before distribution.

### Round 5 - KPI definition

Define 2-3 leading + 2-3 lagging metrics, specific to the campaign objective. Use the
objective-specific KPI sets (lead-gen / brand awareness / release announcement / retention) in
`${CLAUDE_PLUGIN_ROOT}/skills/odoo-campaign-plan/references/kpi-tables.md`. For each metric, give a
concrete measurement method (Google Analytics event, LinkedIn Analytics export, email platform
dashboard) so ownership is clear.

### Round 6 - Owner map (small-team founder aware)

For each task in the campaign, classify as:

- **AI-doable** - can be fully delegated to an AI skill; the human reviews and approves
  the output but does not write it:
  - All text drafts → `odoo-content-draft`
  - Competitive angle research → `odoo-competitive-brief`
  - Feature claims verification → OSM `check_module_exists`
  - Campaign plan iteration → this skill (`odoo-campaign-plan`)

- **Human-required** - requires human judgment, relationships, or access:
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
- **Target audience**: <persona - title, company type, challenge>
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
- **Week 1** - [Asset name] - <type, ~N words> - Audience: <persona> - Draft via `odoo-content-draft`
- **Week 2** - ...
...

## KPI definition
- **Leading**: <metric 1> (measure via: <tool/dashboard>), <metric 2>, <metric 3>
- **Lagging**: <metric 1> (measure via: <tool/dashboard>), <metric 2>, <metric 3>

## Owner map (small-team founder)
### AI-doable (delegate)
- <task> → `odoo-content-draft` / `odoo-competitive-brief` / OSM / this skill
...

### Human-required (your time)
- <task> - estimated <N min/hr per week>
...

## Suggested next skills
- `odoo-content-draft` - draft each asset listed in Asset inventory above
- `odoo-competitive-brief` - if angle is competitive displacement
- `odoo-feature-highlights` - if angle is release announcement and slide deck is needed
- `odoo-capability-proof` - if a specific prospect demo is part of the campaign
- `odoo-demo-recording` - if the asset inventory includes demo videos / screencasts (capture them for real from a live instance instead of briefing a designer)
```

After the plan, add a short `---` section: **Campaign health checks** (2-3 bullets) - the
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
   > in target version>` - confirm before finalizing messaging."

3. Add a note at the end of the plan:
   > _Note: `<TBD: ...>` placeholders can be confirmed with `check_module_exists` once OSM is
   > available. These placeholders are not needed if the campaign angle is generic (e.g.,
   > digital transformation, SME productivity improvement)._

## Examples

Two worked examples (Manufacturing SME / Northern Vietnam lead-gen; English Q4 release
announcement) are in `${CLAUDE_PLUGIN_ROOT}/skills/odoo-campaign-plan/references/examples.md` -
read them when you need a concrete plan shape to anchor against.

## Notes

- **Project context file**: read automatically in Round 0 (see Round 0 / context-bootstrap snippet);
  values there are authoritative overrides applied before any question.
- **Brand assets**: reference repo brand guidelines (e.g. `branding/STYLE.md`) only when the plan
  includes a landing-page or visual-design brief for a designer - this skill stays a planning
  document, not visual assets. Demo videos/screencasts in the inventory → `odoo-demo-recording`.
- **No fabricated data**: NEVER invent customer names, revenue figures, or hard ROI %. Use abstract
  templates ("A manufacturing company in the southern region with ~150 employees"). Incorporate
  real data only with attribution when the user provides it.
- **Leaf skill.** Does NOT invoke other skills or spawn subagents. The plan is a text deliverable
  the marketer executes.
- **Localization**: output language follows the user's request; product/module/channel names stay
  English regardless (e.g. "MRP module", "LinkedIn Ads").

## Continuation Contract

Append a Continuation Contract block per `${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md`
(status / produced / next) - additive run-harness output, changes nothing above.
