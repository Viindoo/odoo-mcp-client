---
name: odoo-feature-positioning
description: |
  Generate positioning copy for a specific Odoo feature/capability. Chains feature-check (does it exist?) → addon-diff (which edition?) → competitive-brief (vs competitor) → positioning copy block. Use for marketing assets, sales decks, or RFP positioning
---
# /odoo-feature-positioning

Interactive command to generate positioning copy for a specific Odoo feature or capability.

Chains four operations in sequence: verify the feature exists, determine which edition(s) support it,
optionally compare against a competitor, and produce final positioning copy adapted to your audience
and output channel.

## When to use

- Marketing needs talking points for a specific Odoo feature (e.g., "advanced approval workflows").
- Sales needs to position Odoo's capability X against competitor Y.
- Preparing a slide deck with feature-specific messaging for a vertical-specific pitch.
- RFP response requires positioning a capability in the context of customer requirements.

## Hard rules

- Read `.odoo-ai/context.md` for the default Odoo version (ask user only if missing).
- Ask user for: **feature/capability name** (required), **target audience** (exec / sales / developer / marketer),
  **competitor name** (optional; skip Phase 3 if not provided), **output channel** (slide / blog / email / proposal).
- Do not produce a full marketing piece (e.g., 2000-word blog post) — that is out of scope for this command.
  Use `/odoo-content-draft` for longer-form marketing assets.
- Do not call the `/odoo-objection-handler` command — this command is for proactive positioning,
  not reactive objection response.
- Confidentiality: use generic competitor names (e.g., "leading competitor X") in examples; do not hardcode real names.

## Phases

### Phase 0: Parse arguments and read context

1. Check `$ARGUMENTS` for feature name. If provided, use it; otherwise ask user.
2. Read `.odoo-ai/context.md` for default Odoo version.
3. Ask user for missing inputs:
   - Target audience: exec / sales / developer / marketer
   - Competitor name (optional; answer "none" to skip Phase 3)
   - Output channel: slide / blog / email / proposal
4. Summarize inputs back to user. Gate: "Ready to check feature?"

### Phase 1: Feature existence check

1. Invoke skill `odoo-feature-check` with the feature name and Odoo version from context.
2. Output summary:
   - **Feature exists**: Y/N
   - **Supported editions**: CE / EE / your Odoo distribution (list which ones)
   - **Key modules**: names of core modules that provide this feature
   - **Key fields/capabilities**: example field names or API landmarks
3. Gate: "Feature verdict clear?" If NO, stop and ask user to refine the feature name.
4. If feature does not exist in any edition, stop and inform user.

### Phase 2: Edition comparison (if applicable)

1. If feature exists in 2+ editions (e.g., CE vs EE, or EE vs your Odoo distribution):
   - Invoke skill `odoo-addon-diff` for the feature across editions.
   - Output a 3-column table: **Capability**, **CE**, **EE**, **Dist.** (check as Y/✓, NA, N).
   - Highlight any edition-specific enhancements or distribution-exclusive capabilities.
2. If feature exists in only 1 edition, note it and proceed.
3. Gate: "Edition comparison clear?"

### Phase 3: Competitive context (if competitor named)

1. If user provided a competitor name:
   - Invoke skill `odoo-competitive-brief` with the feature as the focal point.
   - Narrow the focus: "Compare Odoo's [feature] vs [competitor]'s [equivalent feature]."
   - Output a 2-column capability matrix showing Odoo vs competitor for this feature only.
   - Highlight Odoo's unique strengths or gaps.
2. If user answered "none" or skipped: note this and proceed to Phase 4.
3. Gate: "Competitive picture done?"

### Phase 4: Positioning copy production

Produce a positioning block adapted to target audience and channel:

- **Slide (3–5 talking points):**
  - 1 opening value statement (headline)
  - 2–3 capability bullets (concrete, benefit-focused)
  - 1 differentiator (Odoo vs typical alternatives)
  - Optional competitive callout if competitor data available

- **Blog/article (1 intro paragraph + 3 bullets + close):**
  - 1-paragraph introduction (what is the feature, why it matters)
  - 3 key benefits or use cases (short bullet format)
  - 1 closing paragraph with next steps or evidence pointer

- **Email (1-paragraph value pitch):**
  - Single focused paragraph (~80 words)
  - Lead with the business outcome (not feature name)
  - Close with a CTA (schedule demo, download guide, etc.)

- **Proposal (1 paragraph + evidence pointer):**
  - 1 paragraph confirming Odoo's capability and how it maps to RFP requirement
  - Pointer to module docs, demo, or proof (e.g., "See section 5.3 of RFP response matrix")

Adapt tone to audience:
- **Exec**: business outcome, ROI/time-to-value, competitive advantage
- **Sales**: proof points, customer success stories, removal of objections
- **Developer**: technical depth, integration patterns, API/module names
- **Marketer**: messaging hooks, social proof, differentiator framing

### Phase 5: Output and explicit gate

1. Display the positioning copy block in the terminal (syntax highlighting if applicable).
2. Ask explicitly: "Save positioning copy? Reply `yes` to save to `.odoo-ai/positioning/<slug>-<channel>-<date>.md`, `terminal` to keep output here only, or `cancel` to discard."
3. On `yes` → write file; confirm path. On `terminal` → end command without writing. On `cancel` → end command without writing.

## Example

**Input:**
- Feature: "Multi-level approval workflows"
- Audience: sales
- Competitor: "leading mid-market ERP"
- Channel: slide

**Phase 1 output:**
```
✓ Feature exists in: CE, EE, and your Odoo distribution
  Modules: purchase_approval (EE+), workflow (CE), approval_engine (distribution)
  Key fields: approval_status, approver_id, approval_chain
```

**Phase 2 output:**
```
| Capability                | CE  | EE  | Dist.   |
|---------------------------|-----|-----|---------|
| Basic approval rules      | ✓   | ✓   | ✓       |
| Multi-level chains        | -   | ✓   | ✓       |
| Dynamic approver routing  | -   | -   | ✓       |
| Mobile approval           | -   | ✓   | ✓       |
```

**Phase 3 output:**
```
Odoo vs Leading Competitor — Multi-level Approval
✓ Odoo: no-code workflow builder; competitor: XML config
✓ Odoo: unlimited approval levels; competitor: 3-level cap
— Competitor: native mobile app; Odoo: browser-based
```

**Phase 4 output (slide talking points):**
```
Headline: Approval workflows that scale with your business

Bullets:
• Configure multi-level approval chains without code — drag-and-drop builder
• Route approvals dynamically based on order amount, department, or custom rules
• Track audit trail and escalation in real-time

Differentiator:
Odoo's approval engine works across all modules (purchase, sale, expenses, HR)
— one workflow rule set, applied everywhere. Competitors require module-by-module setup.
```

## Standalone fallback

If `odoo-feature-check`, `odoo-addon-diff`, or `odoo-competitive-brief` skills are unavailable, the command prompts the user to manually state: (a) feature available in which edition, (b) key differentiator vs competitor, (c) target audience. Command produces positioning copy from manual inputs only, marked with `<TBD: verify via skill when OSM back>` for any unverified claim.

## What this command does NOT do

- Does **not** produce a full marketing piece (blog post, whitepaper, case study). Use `/odoo-content-draft` for that.
- Does **not** handle objection responses (use `/odoo-objection-handler` for "Why Odoo vs SAP?").
- Does **not** customize copy to a specific customer or vertical beyond the stated audience segment.
- Does **not** include pricing, licensing, or implementation timelines (use `/odoo-bid-respond` for RFPs).

## See also

- `/odoo-feature-check` — verify a feature exists and which edition(s) support it (also available as skill `odoo-semantic-skills:odoo-feature-check`)
- `/odoo-addon-diff` — compare feature parity across Odoo editions (also available as skill `odoo-semantic-skills:odoo-addon-diff`)
- `/odoo-competitive-brief` — deep competitive analysis for sales (also available as skill `odoo-semantic-skills:odoo-competitive-brief`)
- `/odoo-content-draft` — produce full marketing pieces (blog, guide, landing page copy)
- `/odoo-bid-respond` — position Odoo in the context of an RFP or customer proposal
