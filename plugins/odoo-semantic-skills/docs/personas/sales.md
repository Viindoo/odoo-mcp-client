# Odoo Semantic — Sales Guide

> **Get started (Claude Code):** `claude plugin marketplace add Viindoo/claude-plugins` -> `claude plugin install odoo-semantic-skills@viindoo-plugins` (auto-pulls `odoo-semantic-mcp`) -> `/odoo-semantic-mcp:connect`. For other AI tools, see [client setup](../setup.md).

Turn objections into answered questions in seconds. Verify Odoo capabilities on the spot, pull real code examples as proof, and never get caught off-guard by a "does Odoo do X?" during a demo.

---

## What This Tool Does for Sales

When a prospect asks "can Odoo do X?", you have two options: guess, or know. The Odoo Semantic MCP server lets you query the actual indexed Odoo codebase to give factual, confident answers.

Key scenarios:
- **Feature verification:** "Does Odoo Community have [feature], or is it Enterprise?"
- **Capability demonstration:** "Show me that Odoo actually handles [business scenario]"
- **Objection handling:** "The prospect says Odoo can't do X — prove them wrong (or right)"
- **Competitive positioning:** "What does Odoo have that competitors don't?"

---

## Most Useful Tools for Sales

| Tool | What it answers |
|------|----------------|
| `check_module_exists` | Is this feature native? CE or EE? What versions support it? |
| `find_examples` | Real code from the codebase showing the feature in action |
| `model_inspect` | How complete is Odoo's implementation of this business object? |
| `impact_analysis` | (For technical objections) How mature/stable is this feature? |

---

## Quick Capability Proof Workflow

### Handle "Does Odoo have X?" instantly

```
check_module_exists("sign", "17.0")
```

Returns: module exists yes/no, CE vs EE, EE confusion warnings if relevant. Answer the prospect's question with certainty.

### Demonstrate real functionality

```
find_examples("digital signature on purchase order approval workflow", odoo_version='auto')
```

Returns actual code from indexed Odoo repos — not a demo script, but real implementation evidence. Use this when prospects want proof that Odoo's feature is production-ready, not just a checkbox.

### Scope a prospect's existing Odoo instance

```
model_inspect(model="sale.order", method="summary", odoo_version="16.0")
```

See how many modules extend their core models. If the prospect is on an older version with heavy customization, this tells you the migration complexity before your competitor does.

---

## Sample Sales Questions

Copy these prompts into your AI tool:

1. **Quick capability check:**
   > "Using odoo-semantic, does Odoo 17.0 Community have an eSignature module? Or is it Enterprise-only? The prospect is on a CE budget."

2. **Feature proof for a skeptical prospect:**
   > "Using odoo-semantic, find_examples for multi-company intercompany purchase-to-sale flow in Odoo 17. I need to show the prospect this is a real native feature."

3. **Handling 'Odoo can't do X' objection:**
   > "Using odoo-semantic, check_module_exists for 'project_forecast' in Odoo 17.0. The prospect says Odoo doesn't have resource planning. Is that true?"

4. **Assessing a prospect's upgrade appetite:**
   > "Using odoo-semantic, api_version_diff for sale.order between Odoo 14.0 and 17.0. The prospect is on v14. Give me 3 high-value improvements to mention."

5. **Competitive win story:**
   > "Using odoo-semantic, model_inspect account.move in Odoo 17.0 and show me its full field count and extending modules. I want to demonstrate Odoo's accounting depth vs a competing platform."

---

## Plugin Skills (Claude Code)

If you use **Claude Code** with the Odoo Semantic plugin:

| Skill | What it does |
|-------|-------------|
| `/odoo-capability-proof` | Given a business requirement, returns CE/EE availability + real code examples from indexed repos |
| `/odoo-objection-handler` | Given an objection ("Odoo can't do X"), checks the codebase and returns a factual response |

---

## Reading the Results

- **`is_ee: false`** — Feature is in Community Edition. Free for the prospect.
- **`is_ee: true`** — Requires Enterprise license. Factor into pricing discussion.
- **`is_ee_confusion: true`** — There is a CE module AND an EE module with similar names. Be careful — clarify which tier the prospect expects.
- **`Fields: 148`** — The model has 148 fields across all versions. This is evidence of a mature, feature-rich implementation.
- **Real code from `find_examples`** — This is not a demo — it is actual production code from Odoo's codebase. That is your credibility advantage.

---

## Preparing for a Demo

Before a major demo, run these checks:

1. `check_module_exists` for every feature you plan to show — verify CE vs EE
2. `find_examples` for 2-3 key scenarios — have proof-points ready
3. `api_version_diff` if the prospect is upgrading — know the upgrade story
4. `model_inspect` for the core model you're demoing — know the field count and module depth
