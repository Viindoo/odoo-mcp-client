---
name: odoo-competitive-brief
description: >
  Produce a competitive intelligence brief for a Strategist / CEO — board-ready capability
  matrix vs Odoo, GTM moves (user-provided only), threat assessment, and recommended response.
  Standalone-first — works WITHOUT OSM. Fire when user mentions a competitor alongside
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

Strategist / CEO — one-person or small leadership team needing competitive intelligence
in synthesized, board-ready form. The output must be usable directly in board decks,
investor updates, or strategic planning sessions without further reformatting.

The skill respects that the CEO is the primary intelligence source. It structures and
prioritizes what the user already knows — it does NOT invent competitive facts.

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

<!-- BEGIN MANUAL TOOLS — odoo-competitive-brief -->
_Tool surface: server v0.13.1._

**Optional — call only when grounding "your platform has X" or "Odoo can't do Y" claims:**
- `profile_inspect` — Profile-level introspection (`method='summary'|'repos'|'modules'`): inheritance
  chain + repos + indexed module count/list for your platform profile. Use it to fill the "your
  platform" column of the Round 2 capability matrix with indexed fact instead of training-data
  assertion (the board-facing reason this matters).
- `check_module_exists` — Verify that a module or feature exists in your platform
  (CE/EE/custom distribution), used to substantiate or refute capability claims a
  competitor makes in their messaging. Call when the user says "competitor claims Odoo
  lacks X — is that true?".
- `find_examples` — Semantic code search returning real indexed code snippets from the
  Odoo codebase, used when a competitor's marketing claims "Odoo cannot do Y" and the
  CEO needs concrete proof-of-existence before a board meeting.
<!-- END MANUAL TOOLS — odoo-competitive-brief -->

**Default posture:** skip MCP calls entirely. The brief is grounded in user-provided
intelligence. MCP is additive verification only — never a blocker.

---

## Workflow

### Round 0 — Scope confirmation (ask at most 1 question if scope is vague)

Before proceeding, identify:
1. **Subject** — a named competitor OR a landscape question (e.g., "ERP for F&B vertical").
2. **Scope dimensions** — one or more of: Product / Pricing / GTM / Positioning / All.
3. **Output use** — board deck, investor update, internal strategy session, quick scan.

If the user's prompt already specifies a competitor name and at least one scope dimension,
skip Round 0 and proceed directly to Round 1.

If subject or scope is missing, ask ONE clarifying question:
> "Which competitor would you like a brief on, and which aspect should we focus on (product / pricing /
> GTM / positioning, or all)? Level of detail: quick scan or board-deck depth?"

Do NOT ask multiple questions. Make reasonable defaults if user is partially specific.

---

### Round 1 — Competitor snapshot

**Pre-Round (agent self-serve before marking anything Unknown):**

Before marking any field Unknown, attempt to fill it from available sources:
1. `Read` the vault dossier at `Resources/Competitors/<name>.md` if it exists.
2. `WebSearch` `"<competitor> features pricing"` (or `"<competitor> Vietnam ERP"` for
   local players) to surface public product/pricing pages, LinkedIn About, or press
   releases.
3. `WebFetch` the competitor's pricing or features page when a URL is discoverable.

Pre-fill every field from the above tiers. Only then mark fields as `Unknown` when all
three tiers return no signal - never invent. Quote the source inline for any field
populated from an external fetch.

Required fields:
- **Name** — formal company name
- **Parent company** — if subsidiary (e.g., "acquired by Group X in YYYY")
- **HQ** — city / country
- **Primary geo** — regions where actively selling (Vietnam / SEA / Global)
- **Product line** — named products or modules (brief list)
- **Target segment** — SME / Mid-market / Enterprise; verticals if known
- **Headcount band** — S (<50) / M (50-200) / L (200-1000) / XL (>1000)
- **Funding / ownership** — bootstrapped / PE-backed / listed / subsidiary

---

### Round 2 — Capability matrix vs your platform

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
**=** (parity) / **?** (Unknown — data not provided).

Your platform baseline must be grounded in the index, not asserted from training data. When OSM is
reachable, fill the "your platform" column from `profile_inspect(method='summary', name=<your_profile>,
odoo_version='<version>')` (real inheritance chain + repos + module count) and `profile_inspect(method='modules', …)`
for the module-coverage row — this turns the platform side of the matrix into verifiable fact. The competitor
column is filled from user-provided data only; do NOT infer competitor capabilities not stated by the user.

If the user questions a specific platform capability, also call `check_module_exists` to verify before
marking + / - / =.

---

### Round 3 — GTM moves (observed)

List only signals the user has explicitly provided or pasted. Do NOT invent or infer.

For each move, capture:
- What the move is (product launch, pricing change, partnership, hire, campaign)
- Approximate date or quarter if known
- Source / evidence type (press release / LinkedIn / customer report / conference)

If no GTM signals are available, output:
> _No GTM signals provided. Recommend monitoring: [competitor's blog / LinkedIn /
> industry press] for announcements._

---

### Round 4 — Threat assessment

Score each dimension from Round 2 by threat level: **Low / Med / High / Critical**.

Threat level criteria:
- **Low** — competitor weak or absent in this dimension; your platform has clear advantage
- **Med** — competitive parity or minor competitor edge; worth watching
- **High** — competitor has material advantage in a dimension that matters to target segment
- **Critical** — competitor advantage is large AND in a dimension central to your platform's
  core value proposition

Cite specific signals for each High/Critical rating. Do not assign High/Critical without
a stated signal from Round 1/3.

Aggregate overall threat: Low / Med / High / Critical — explain rationale in 2-3 sentences.

---

### Round 5 — Recommended response

Produce 3-5 actionable moves, prioritized by urgency and effort.

For each recommendation:
- State the action (what)
- Identify likely owner: CEO / Product / Marketing / Sales / Partner
- Suggest timeline: Immediate (<30 days) / Short-term (30-90 days) / Medium-term (90+ days)
- Note the dependency or blocker if any

Recommendations must be grounded in threat signals from Round 4 — do not recommend
generic strategic moves without linking them to a specific threat.

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

- <Move 1> — <source type> / <date or quarter>
- <Move 2> — <source type> / <date or quarter>

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

1. **<Action 1>** — Owner: <CEO/Product/Marketing/Sales/Partner> · Timeline: <Immediate/Short/Medium>
   - Rationale: <link to threat signal>
   - Dependency: <blocker if any>

2. **<Action 2>** — Owner: <…> · Timeline: <…>
   - Rationale: <…>

3. **<Action 3>** — Owner: <…> · Timeline: <…>
   - Rationale: <…>

---

## Open data needs

_What additional intelligence would sharpen this brief:_
- <data point 1> — suggested source
- <data point 2> — suggested source
```

---

## Standalone-first fallback

When OSM is unreachable or not configured:
- Skip `check_module_exists` and `find_examples` calls entirely.
- Where a platform capability claim cannot be verified, insert placeholder:
  `<TBD: verify via odoo-feature-check — module_name>`
- Proceed with the full brief using user-provided data and training knowledge for
  your platform baseline.
- Add a footer note to the output:
  > _OSM not connected. Platform capability claims marked `<TBD>` should be verified
  > before using in board or investor materials._

The brief remains useful for internal strategy sessions even without OSM verification.

---

## Examples

### Example 1 — Vietnam ERP incumbent (local-market player)

**User prompt:** "need competitive brief on Competitor A — they just launched a new SME package,
focus on accounting and HR, pricing around X per year. I need a deck for board next week."

**Skill action:**
- Round 0: scope is clear (Product + Pricing, board deck) — skip clarification.
- Round 1: Extract from user statement — target segment SME, Accounting + HR modules, published pricing.
  Mark unknown fields (HQ, headcount, parent).
- Round 2: Build matrix. Competitor strengths likely in pricing (published + competitive),
  your platform strengths in module breadth, EE features. Mark unknown dimensions as `?` — do not infer.
- Round 3: GTM move = new SME bundle launch. Source = user statement. Date = user-stated.
- Round 4: Threat High on Pricing (competitive), Med on feature depth (both have core HR/Accounting),
  Low on AI/automation (not mentioned). Overall threat: Med.
- Round 5: Recommend (1) Counter-bundle packaging review — Owner: CEO/Product, Immediate;
  (2) Publish pricing comparison — Owner: Marketing, Short-term; (3) Accelerate HR compliance
  feature — Owner: Product, Medium-term.

**Note:** This template applies to any competitor with local market presence, published pricing,
and focus on SME segment. Do not hardcode specific competitor names.

---

### Example 2 — International SaaS player entering Vietnam

**User prompt:** "Competitor B is international SaaS, just opened Vietnam office with a major partner
in HCM. They're pushing hard into manufacturing. Need quick threat assessment."

**Skill action:**
- Round 0: scope is Product + GTM + threat assessment, quick scan. Proceed.
- Round 1: International HQ, Vietnam entry-stage (new office), partner announcement,
  Manufacturing focus. Headcount and pricing unknown — mark `?`.
- Round 2: Competitor strengths likely in global integration ecosystem and AI
  (international SaaS). Your platform strengths in localization and local support.
  Manufacturing depth: mark `?` for competitor until user provides data.
- Round 3: GTM moves = office opening + partner announcement. Source = user statement.
- Round 4: Threat High on Integration ecosystem (international SaaS breadth),
  Med on Manufacturing vertical (needs data), Low on localization (new entrant),
  High on Partner ecosystem (named major partner). Overall threat: Med-High.
- Round 5: Recommend (1) Accelerate Manufacturing case studies — Owner: Marketing,
  Short-term; (2) Engage Manufacturing sector before competitor — Owner: CEO/Sales,
  Immediate; (3) Monitor partner's customer wins — Owner: CEO, Ongoing.

**Note:** This template applies to any international SaaS entering a specific vertical
via local partnerships. Adjust threat ratings based on user-provided signals.

---

## Notes

### `.odoo-ai/context.md` integration

If the project has an `.odoo-ai/context.md` file, the skill will read it for:
- Your platform's current product roadmap signals (to inform capability matrix and response recommendations)
- Known active competitors already tracked by the team

The skill reads vault competitor dossiers directly at `Resources/Competitors/<name>.md`
rather than asking the caller to paste them. If the dossier is present on disk, its
content is loaded as part of Round 1 Pre-Round automatically.

### Confidentiality notice

Competitive intelligence is sensitive. This skill structures information YOU provide —
it does not access external competitive databases, does not invent pricing or GTM facts,
and does not retain information between sessions. Treat the output as internal-only
unless you have independently verified all claims before sharing externally.

When sharing the brief output outside the organization (e.g., with investors or partners),
remove or redact signals sourced from customer conversations, partner disclosures, or
non-public channels.

## Continuation Contract

When you finish, append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next). Additive
output for the depth-0 run-driver - it does not change anything produced above.
