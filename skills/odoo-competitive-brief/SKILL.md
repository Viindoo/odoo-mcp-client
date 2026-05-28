---
name: odoo-competitive-brief
description: >
  Produce a structured competitive intelligence brief for a Strategist / CEO persona — covering
  a named competitor or a competitive landscape question. Output is a board-ready snapshot,
  capability matrix vs Viindoo/Odoo, GTM moves (from user-provided signals only), threat
  assessment, and recommended Viindoo response. Fire this skill when the user mentions a
  competitor name alongside any strategic intent: "competitor brief về", "phân tích MISA",
  "phân tích Bravo", "phân tích 1Office", "phân tích Portcities", "phân tích Odoo International",
  "tóm tắt landscape cạnh tranh", "đối thủ X đang làm gì", "competitive update cho board",
  "ai đang đe dọa Viindoo ở vertical X", "competitive brief on", "analyze competitor X",
  "landscape brief for board", "what's competitor Y doing in vertical Z",
  "threat assessment for", "positioning vs competitor", "competitive intelligence update",
  "cập nhật cạnh tranh cho nhà đầu tư", "đánh giá mối đe dọa từ X",
  "so sánh chiến lược với đối thủ", "đối thủ cạnh tranh mới nổi",
  "tình hình cạnh tranh Q[1-4]". Standalone-first — works WITHOUT OSM connectivity;
  OSM optional for capability verification of Viindoo/Odoo claims.
  DO NOT trigger for: (a) sales talking-point objections ("they say Odoo can't do X") →
  odoo-objection-handler; (b) feature comparison drill-down between Odoo versions →
  odoo-version-diff; (c) detailed add-on diff → odoo-addon-diff; (d) marketing copy or
  campaign messaging about competitive positioning → odoo-content-draft or
  odoo-campaign-plan; (e) simple feature availability check → odoo-feature-check.
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
| Sales objection handling ("they say Odoo can't do X") | `odoo-objection-handler` |
| Feature comparison drill-down between Odoo versions | `odoo-version-diff` |
| Detailed module/add-on diff | `odoo-addon-diff` |
| Marketing copy or campaign messaging | `odoo-content-draft` / `odoo-campaign-plan` |
| Single feature availability check | `odoo-feature-check` |
| Customer requirements gap analysis | `odoo-gap-analysis` |

---

## MCP tools

<!-- BEGIN MANUAL TOOLS — odoo-competitive-brief -->
_Tool surface: server v0.8.0. See [`docs/reference/mcp-tool-routing.md`](../../docs/reference/mcp-tool-routing.md) for full routing matrix._

**Optional — call only when grounding "Viindoo has X" or "Odoo can't do Y" claims:**
- `check_module_exists` — Verify that a Viindoo/Odoo module or feature exists in the
  platform (CE/EE/Viindoo edition), used to substantiate or refute capability claims a
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
> "Bạn muốn brief về đối thủ cụ thể nào, và focus vào khía cạnh nào (sản phẩm / giá /
> GTM / positioning, hoặc tất cả)? Mức độ detail: quick scan hay board-deck depth?"

Do NOT ask multiple questions. Make reasonable defaults if user is partially specific.

---

### Round 1 — Competitor snapshot

Gather the following from user's stated knowledge, pasted materials, or context.
Mark any field as `Unknown` if not provided — never invent.

Required fields:
- **Name** — formal company name
- **Parent company** — if subsidiary (e.g., "acquired by Group X in YYYY")
- **HQ** — city / country
- **Primary geo** — regions where actively selling (Vietnam / SEA / Global)
- **Product line** — named products or modules (brief list)
- **Target segment** — SME / Mid-market / Enterprise; verticals if known
- **Headcount band** — S (<50) / M (50-200) / L (200-1000) / XL (>1000)
- **Funding / ownership** — bootstrapped / PE-backed / listed / subsidiary

If the user provides raw paste (press release, LinkedIn post, product page), extract
these fields from the paste. Quote the source inline.

---

### Round 2 — Capability matrix vs Viindoo

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

Mark each cell: **+** (competitor advantage) / **-** (Viindoo advantage) /
**=** (parity) / **?** (Unknown — data not provided).

Viindoo baseline is known to the skill. Competitor column is filled from user-provided
data only. Do NOT infer competitor capabilities not stated by the user.

If OSM is reachable and the user questions a specific Viindoo capability, call
`check_module_exists` to verify before marking + / - / =.

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
- **Low** — competitor weak or absent in this dimension; Viindoo has clear advantage
- **Med** — competitive parity or minor competitor edge; worth watching
- **High** — competitor has material advantage in a dimension that matters to target segment
- **Critical** — competitor advantage is large AND in a dimension central to Viindoo's
  core value proposition (e.g., Vietnam localization for a local ERP incumbent)

Cite specific signals for each High/Critical rating. Do not assign High/Critical without
a stated signal from Round 1/3.

Aggregate overall threat: Low / Med / High / Critical — explain rationale in 2-3 sentences.

---

### Round 5 — Recommended Viindoo response

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

## Capability matrix vs Viindoo

| Dimension | Viindoo | <Competitor> | Notes |
|---|---|---|---|
| ERP module coverage | <rating> | <rating> | <notes> |
| Vietnam localization | <rating> | <rating> | <notes> |
| Vertical depth | <rating> | <rating> | <notes> |
| AI / automation | <rating> | <rating> | <notes> |
| Integration ecosystem | <rating> | <rating> | <notes> |
| Pricing model | <rating> | <rating> | <notes> |
| Partner ecosystem | <rating> | <rating> | <notes> |
| Mobile / UX | <rating> | <rating> | <notes> |
| Deployment model | <rating> | <rating> | <notes> |
| Support & SLA | <rating> | <rating> | <notes> |

_Legend: + = competitor advantage · - = Viindoo advantage · = = parity · ? = Unknown_

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

## Recommended Viindoo response

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
- Where a Viindoo capability claim cannot be verified, insert placeholder:
  `<TBD: verify via odoo-feature-check — module_name>`
- Proceed with the full brief using user-provided data and training knowledge for
  Viindoo/Odoo baseline.
- Add a footer note to the output:
  > _OSM not connected. Viindoo capability claims marked `<TBD>` should be verified
  > before using in board or investor materials._

The brief remains useful for internal strategy sessions even without OSM verification.

---

## Examples

### Example 1 — Vietnam ERP incumbent (local-market player)

**User prompt:** "cần competitive brief về Đối thủ A — họ vừa ra gói SME mới, focus vào
kế toán và HRM, giá khoảng X triệu/năm. Mình cần deck cho board tuần sau."

**Skill action:**
- Round 0: scope is clear (Product + Pricing, board deck) — skip clarification.
- Round 1: Extract from user statement — local HQ, Vietnam-primary geo, SME segment,
  Accounting + HRM modules, published pricing band. Mark unknown fields (headcount, parent).
- Round 2: Build matrix. Competitor strengths likely in Vietnam localization (local player),
  pricing (published + aggressive). Viindoo strengths in module breadth, EE features.
  Mark unknown dimensions as `?` — do not infer.
- Round 3: GTM move = new SME bundle launch. Source = user statement. Date = user-stated.
- Round 4: Threat High on Pricing (published aggressive), Med on Vietnam localization
  (both are local), Low on AI/automation (not mentioned). Overall threat: Med.
- Round 5: Recommend (1) Viindoo counter-bundle packaging review — Owner: CEO/Product,
  Immediate; (2) Publish pricing page with value comparison — Owner: Marketing, Short-term;
  (3) Accelerate HRM Vietnam compliance feature — Owner: Product, Medium-term.

**Note:** This template applies to any Vietnam-domiciled ERP incumbent with local compliance
depth and aggressive SME pricing. Do not hardcode specific competitor names or pricing
figures in this skill.

---

### Example 2 — International SaaS player entering Vietnam

**User prompt:** "Đối thủ B là SaaS quốc tế, vừa mở văn phòng Việt Nam, có partner lớn
ở HCM. Họ push mạnh vào manufacturing vertical. Cần threat assessment nhanh."

**Skill action:**
- Round 0: scope is Product + GTM + threat assessment, quick scan. Proceed.
- Round 1: International HQ, Vietnam entry-stage (new office), partner announcement,
  Manufacturing vertical focus. Headcount and pricing unknown — mark `?`.
- Round 2: Competitor strengths likely in global integration ecosystem and AI features
  (international SaaS). Viindoo strengths in Vietnam localization and local support.
  Manufacturing vertical: mark `?` for competitor depth until user provides data.
- Round 3: GTM moves = office opening + partner announcement. Source = user statement.
- Round 4: Threat High on Integration ecosystem (international SaaS breadth),
  Med on Manufacturing vertical (needs data), Low on Vietnam localization (new entrant),
  High on Partner ecosystem (named large partner). Overall threat: Med-High.
- Round 5: Recommend (1) Accelerate Manufacturing vertical case studies — Owner: Marketing,
  Short-term; (2) Engage Manufacturing sector associations before competitor does — Owner:
  CEO/Sales, Immediate; (3) Monitor partner's customer wins via LinkedIn — Owner: CEO,
  Ongoing.

**Note:** This template applies to any international SaaS entering a specific Vietnam vertical
via local partnerships. Adjust threat ratings based on actual user-provided signals.

---

## Notes

### `.odoo-ai/context.md` integration

If the project has an `.odoo-ai/context.md` file, the skill will read it for:
- Viindoo's current product roadmap signals (to inform capability matrix and response recommendations)
- Known active competitors already tracked by the team

The skill does NOT auto-read vault competitor profiles. If you maintain competitor dossiers
in Obsidian or another knowledge base, paste the relevant section into the chat —
the skill will incorporate it into the appropriate round.

### Confidentiality notice

Competitive intelligence is sensitive. This skill structures information YOU provide —
it does not access external competitive databases, does not invent pricing or GTM facts,
and does not retain information between sessions. Treat the output as internal-only
unless you have independently verified all claims before sharing externally.

When sharing the brief output outside the organization (e.g., with investors or partners),
remove or redact signals sourced from customer conversations, partner disclosures, or
non-public channels.
