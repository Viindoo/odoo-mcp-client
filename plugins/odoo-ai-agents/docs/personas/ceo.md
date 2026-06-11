# Odoo Semantic — Manager / Decision-Maker Guide

> **Get started (Claude Code):** `claude plugin marketplace add Viindoo/claude-plugins` -> `claude plugin install odoo-semantic-skills@viindoo-plugins` (auto-pulls `odoo-semantic-mcp`) -> `/odoo-semantic-mcp:connect`. For other AI tools, see [client setup](../setup.md).

You do not need to understand Odoo's code to get value from this tool. Ask plain-language questions about risk, upgrade cost, and customization scope — and get structured answers your team can act on.

---

## What This Tool Does for You

The Odoo Semantic MCP server has indexed your entire Odoo codebase. Your AI assistant (Claude Code, ChatGPT, Gemini) can query it to answer questions like:

- "How many custom modules will be affected if we upgrade from Odoo 16 to 17?"
- "Is the subscription feature part of Community or Enterprise?"
- "What is the risk level of removing the custom `amount_total` override?"

These answers come from live codebase analysis — not guesswork.

---

## Most Useful Tools for Managers

| Tool | What it answers |
|------|----------------|
| `impact_analysis` | Risk level (HIGH/MEDIUM/LOW) + what breaks if a field or method is changed |
| `find_deprecated_usage` | Which parts of your codebase use APIs that Odoo is removing in the next version |
| `check_module_exists` | Whether a feature is available in Community Edition or requires Enterprise |
| `model_inspect` | How many modules touch a given business object (e.g., `sale.order`) |

---

## Questions You Can Ask Your AI Assistant

Example invocations (an AI agent can run these directly as NL dispatch; a human reader can copy them):

1. **Upgrade risk scan:**
   > "Using odoo-semantic, run find_deprecated_usage for Odoo 17.0 on our codebase. Summarize the HIGH-risk items in plain language."

2. **Customization inventory:**
   > "Using odoo-semantic, model_inspect sale.order in Odoo 17.0 and tell me how many modules extend it. Which are custom vs standard?"

3. **Feature availability check:**
   > "Using odoo-semantic, does Odoo 17.0 Community have a subscription billing module? Or is it Enterprise-only?"

4. **Change impact assessment:**
   > "Using odoo-semantic, run impact_analysis on the field sale.order.amount_total in Odoo 17.0. What is the risk level and what would break?"

5. **Cross-version comparison:**
   > "Using odoo-semantic, what changed in the account.move model between Odoo 16.0 and 17.0? Focus on breaking changes."

---

## Plugin Skills (Claude Code)

If you use **Claude Code** with the Odoo Semantic plugin installed, these slash commands are available:

| Skill | What it does |
|-------|-------------|
| `/odoo-risk-overview` | Runs upgrade risk scan — deprecated APIs + impact summary for your version |
| `/odoo-customization-inventory` | Lists all custom modules and the standard Odoo models they extend |

---

## How to Read Results

When your AI returns results from these tools, look for:

- **Risk: HIGH** — This will require developer time to fix before upgrade. Budget accordingly.
- **Risk: MEDIUM** — Should be reviewed; may work fine but has potential for breakage.
- **Risk: LOW** — Safe to proceed with minor review.
- **EE Warning** — Feature requires Odoo Enterprise license, not available in Community.
- **Defined in: [repo] module** — This is where the original business logic lives.

---

## Getting Started

1. Ask your admin for the API key and MCP server URL
2. Add the MCP server to your AI tool of choice (see the install page at your server URL)
3. Start with: *"Using odoo-semantic, check_module_exists for 'account_accountant' in Odoo 17.0"*
