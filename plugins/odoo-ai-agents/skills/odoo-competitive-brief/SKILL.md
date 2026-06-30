---
name: odoo-competitive-brief
description: >
  Produce a competitive intelligence brief for a Strategist / CEO - board-ready capability
  matrix vs Odoo, GTM moves (user-provided only), threat assessment, and recommended response.
  Standalone-first - works WITHOUT OSM. Fire when user mentions a competitor alongside
  strategic intent: "competitor brief on", "analyze competitor X",
  "competitive landscape analysis", "competitive update for board",
  "threat assessment for", "competitive intelligence update".
  Also fires on Vietnamese: "phân tích đối thủ X", "brief cạnh tranh cho ban lãnh đạo",
  "đánh giá mối đe doạ cạnh tranh".
  DO NOT trigger for: (a) sales talking-point objections ("they say Odoo can't do X") →
  odoo-objection-handling; (b) feature comparison drill-down between Odoo versions →
  odoo-version-diff; (c) detailed add-on diff → odoo-addon-diff; (d) marketing copy or
  campaign messaging about competitive positioning → odoo-content-draft or
  odoo-campaign-plan; (e) simple feature availability check → odoo-feature-check
---

## Persona

Strategist / CEO needing board-ready competitive intelligence - usable in board decks, investor updates, or strategy sessions. The CEO is the primary intelligence source; this skill structures and prioritizes what the user already knows. It does NOT invent competitive facts.

---

## Out of Scope

| User intent | Route to |
|---|---|
| Sales objection handling ("they say Odoo can't do X") | `odoo-objection-handling` |
| Feature comparison drill-down between Odoo versions | `odoo-version-diff` |
| Detailed module/add-on diff | `odoo-addon-diff` |
| Marketing copy or campaign messaging | `odoo-content-draft` / `odoo-campaign-plan` |
| Single feature availability check | `odoo-feature-check` |
| Customer requirements gap analysis | `odoo-gap-analysis` |

---

## MCP tools

<!-- BEGIN MANUAL TOOLS - odoo-competitive-brief -->

**Optional - call only when grounding "your platform has X" or "Odoo can't do Y" claims:**
- `profile_inspect` - Profile-level introspection (`method='summary'|'repos'|'modules'`): inheritance
  chain + repos + indexed module count/list for your platform profile. Use it to fill the "your
  platform" column of the Round 2 capability matrix with indexed fact instead of training-data
  assertion (the board-facing reason this matters).
- `check_module_exists` - Verify that a module or feature exists in your platform
  (CE/EE/custom distribution), used to substantiate or refute capability claims a
  competitor makes in their messaging. Call when the user says "competitor claims Odoo
  lacks X - is that true?".
- `find_examples` - Semantic code search returning real indexed code snippets from the
  Odoo codebase, used when a competitor's marketing claims "Odoo cannot do Y" and the
  CEO needs concrete proof-of-existence before a board meeting.
<!-- END MANUAL TOOLS - odoo-competitive-brief -->

**Default posture:** skip MCP calls entirely. The brief is grounded in user-provided
intelligence. MCP is additive verification only - never a blocker.

---

## Workflow

### Round 0 - Scope confirmation (at most 1 question)

Identify: (1) subject (named competitor or landscape question), (2) scope (Product / Pricing / GTM / Positioning / All), (3) output use (board deck / investor update / internal / quick scan).

If prompt already names a competitor and ≥1 scope dimension, skip to Round 1.

Otherwise, ask ONE question:
> "Which competitor, which aspect (product / pricing / GTM / positioning / all), and depth (quick scan or board-deck)?"

Make reasonable defaults if user is partially specific.

---

### Round 1 - Competitor snapshot

**Pre-Round (self-serve before marking Unknown):**

1. `Read` vault dossier `Resources/Competitors/<name>.md` if it exists.
2. `WebSearch` `"<competitor> features pricing"` (or `"<competitor> Vietnam ERP"` for local players).
3. `WebFetch` competitor pricing/features page when URL is discoverable.

Pre-fill every field from these tiers. Only mark `Unknown` when all three return no signal. Quote source inline for any external fetch. Never invent.

Required fields:
- **Name** - formal company name
- **Parent company** - if subsidiary (e.g., "acquired by Group X in YYYY")
- **HQ** - city / country
- **Primary geo** - regions where actively selling (Vietnam / SEA / Global)
- **Product line** - named products or modules (brief list)
- **Target segment** - SME / Mid-market / Enterprise; verticals if known
- **Headcount band** - S (<50) / M (50-200) / L (200-1000) / XL (>1000)
- **Funding / ownership** - bootstrapped / PE-backed / listed / subsidiary

---

### Round 2 - Capability matrix vs your platform

Build a comparison table on 5-10 dimensions. Select the most relevant from:

| Dimension | Description |
|---|---|
| ERP module coverage | Which functional modules (Accounting, HR, Inventory, MRP, etc.) |
| Vietnam localization | VAS accounting, e-invoice, labor law, tax compliance |
| Vertical depth | Industry-specific features (F&B, manufacturing, retail, services) |
| AI / automation features | Built-in AI, workflow automation, chatbot, predictive analytics |
| Integration ecosystem | Open API, marketplace connectors, EDI, 3rd-party SaaS |
| Pricing model | Per-user / per-module / flat fee / revenue-based; published or opaque |
| Partner / reseller ecosystem | VAR network size, certification program, geographic coverage |
| Mobile / UX | Native mobile app quality, responsive web, offline capability |
| Deployment model | Cloud SaaS / on-premise / hybrid; data residency options |
| Support & SLA | Tiered support, local support language, SLA commitments |

Mark each cell: **+** (competitor advantage) / **-** (your platform advantage) /
**=** (parity) / **?** (Unknown - data not provided).

Your platform baseline must be grounded in the index, not asserted from training data. When OSM is
reachable, fill the "your platform" column from `profile_inspect(method='summary', name=<your_profile>,
odoo_version='<version>')` (real inheritance chain + repos + module count) and `profile_inspect(method='modules', …)`
for the module-coverage row - this turns the platform side of the matrix into verifiable fact. The competitor
column is filled from user-provided data only; do NOT infer competitor capabilities not stated by the user.

If the user questions a specific platform capability, also call `check_module_exists` to verify before
marking + / - / =.

---

### Round 3 - GTM moves (observed)

List only user-provided signals. Do NOT invent or infer. For each: move type, date/quarter, source type.

If none available: _No GTM signals provided. Recommend monitoring: [competitor's blog / LinkedIn / industry press]._

---

### Round 4 - Threat assessment

Score each Round 2 dimension: Low / Med / High / Critical.

| Level | Meaning |
|---|---|
| Low | Competitor weak/absent; your platform has clear advantage |
| Med | Parity or minor competitor edge; watch |
| High | Competitor has material advantage in a segment-relevant dimension |
| Critical | Large advantage AND central to your platform's core value prop |

Cite signals for each High/Critical. Do not assign High/Critical without a Round 1/3 signal. Aggregate overall threat in 2-3 sentences.

---

### Round 5 - Recommended response

3-5 actionable moves, prioritized by urgency. For each: action (what) + owner (CEO/Product/Marketing/Sales/Partner) + timeline (Immediate/Short-term/Medium-term) + dependency/blocker if any. Must link to a specific Round 4 threat signal - no generic strategic moves.

---

## Output format

```markdown
# Competitive Brief: <Competitor Name>

> **Date:** <YYYY-MM-DD>
> **Scope:** <Product / Pricing / GTM / Positioning / All>
> **Prepared for:** <Board / Investor update / Internal strategy / Quick scan>
> **Sources:** <User-provided: [list source types]>

---

## Snapshot

| Field | Value |
|---|---|
| Name | <competitor> |
| Parent company | <parent or "Independent"> |
| HQ | <city, country> |
| Primary geo | <regions> |
| Product line | <list> |
| Target segment | <SME/Mid/Enterprise + vertical> |
| Headcount band | <S/M/L/XL> |
| Funding / ownership | <bootstrapped/PE/listed/subsidiary> |

---

## Capability matrix vs your platform

| Dimension | Your platform | <Competitor> | Notes |
|---|---|---|---|
| ERP module coverage | <rating> | <rating> | <notes> |
| Localization & compliance | <rating> | <rating> | <notes> |
| Vertical depth | <rating> | <rating> | <notes> |
| AI / automation | <rating> | <rating> | <notes> |
| Integration ecosystem | <rating> | <rating> | <notes> |
| Pricing model | <rating> | <rating> | <notes> |
| Partner ecosystem | <rating> | <rating> | <notes> |
| Mobile / UX | <rating> | <rating> | <notes> |
| Deployment model | <rating> | <rating> | <notes> |
| Support & SLA | <rating> | <rating> | <notes> |

_Legend: + = competitor advantage · - = your platform advantage · = = parity · ? = Unknown_

---

## GTM moves (observed)

- <Move 1> - <source type> / <date or quarter>
- <Move 2> - <source type> / <date or quarter>

_No moves listed = no signals provided by user._

---

## Threat assessment

| Dimension | Threat level | Signals |
|---|---|---|
| ERP module coverage | <Low/Med/High/Critical> | <signal> |
| Vietnam localization | <Low/Med/High/Critical> | <signal> |
| Vertical depth | <Low/Med/High/Critical> | <signal> |
| AI / automation | <Low/Med/High/Critical> | <signal> |
| Integration ecosystem | <Low/Med/High/Critical> | <signal> |
| Pricing model | <Low/Med/High/Critical> | <signal> |
| Partner ecosystem | <Low/Med/High/Critical> | <signal> |
| Mobile / UX | <Low/Med/High/Critical> | <signal> |

**Overall threat: <Low / Med / High / Critical>**
<2-3 sentence rationale>

---

## Recommended response

1. **<Action 1>** - Owner: <CEO/Product/Marketing/Sales/Partner> · Timeline: <Immediate/Short/Medium>
   - Rationale: <link to threat signal>
   - Dependency: <blocker if any>

2. **<Action 2>** - Owner: <…> · Timeline: <…>
   - Rationale: <…>

3. **<Action 3>** - Owner: <…> · Timeline: <…>
   - Rationale: <…>

---

## Open data needs

_What additional intelligence would sharpen this brief:_
- <data point 1> - suggested source
- <data point 2> - suggested source
```

---

## Standalone-first fallback

When OSM is unreachable: skip MCP calls entirely. Insert `<TBD: verify via odoo-feature-check - module_name>` for unverifiable capability claims. Proceed with full brief on user-provided data + training knowledge. Add footer: _OSM not connected. `<TBD>` claims should be verified before board/investor use._

---

## Examples

See `${CLAUDE_PLUGIN_ROOT}/skills/odoo-competitive-brief/references/examples.md` for 2 worked examples (Vietnam ERP incumbent, international SaaS entering Vietnam).

## Notes

- **Context integration**: read `.odoo-ai/context.md` for platform roadmap signals and active competitor list. Load vault dossier `Resources/Competitors/<name>.md` automatically in Round 1 Pre-Round if it exists.
- **Confidentiality**: this skill structures information YOU provide. No external competitive databases; no invented pricing or GTM facts; no session retention. Treat output as internal-only. Remove/redact signals from customer conversations or partner disclosures before sharing externally.

## Continuation Contract

Append a Continuation Contract block per `${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md`
(status / produced / next) - additive run-harness output, changes nothing above.
