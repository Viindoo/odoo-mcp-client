# Odoo Semantic - Marketer Guide

> **Get started (Claude Code):** `claude plugin marketplace add Viindoo/claude-plugins` -> `claude plugin install odoo-ai-agents@viindoo-plugins` (auto-pulls `odoo-semantic-mcp`) -> `/odoo-semantic-mcp:connect`. For other AI tools, see [client setup](../setup.md).

Create accurate, data-backed Odoo content: version comparison articles, feature highlight posts, upgrade guides, and capability summaries - all grounded in real codebase facts, not marketing sheets.

---

## What This Tool Does for Marketers

Marketing content about Odoo lives or dies on accuracy. Wrong feature claims, misattributed CE/EE boundaries, or outdated version numbers erode credibility. The Odoo Semantic MCP server lets you query the actual indexed codebase to verify claims before publishing.

Use cases:
- "What's new in Odoo 17 vs 16?" - get real API changes, not just release notes
- "Does Odoo have [feature] in Community?" - verify before writing the comparison table
- "Show me a code example of how Odoo handles [business process]" - for technical content pieces

---

## Most Useful Tools for Marketers

| Tool | What it answers |
|------|----------------|
| `api_version_diff` | What actually changed between two Odoo versions for a specific model/API |
| `find_examples` | Real code snippets showing how a feature works - useful for technical blog posts |
| `check_module_exists` | Is this feature CE or EE? What version added it? |
| `model_inspect` | How many modules and extensions does this core business object have? |

---

## Content Research Workflows

### Version comparison content

```
api_version_diff("sale.order", "16.0", "<version>")
```

Returns actual API changes - new fields, deprecated methods, status changes. Use this to write factual "What's new in Odoo 17" sections instead of relying solely on official release notes.

### CE vs EE feature tables

```
check_module_exists("account_accountant", "<version>")
check_module_exists("sign", "<version>")
check_module_exists("website_livechat", "<version>")
```

Build accurate CE/EE comparison tables. The tool returns the `is_ee` flag and EE confusion warnings for look-alike module names.

### Technical deep-dives

```
find_examples("multi-currency invoice reconciliation workflow", odoo_version='<version>')
```

Semantic code search returns real implementation examples. Great for writing accurate technical content about how Odoo handles complex scenarios.

---

## Sample Marketer Questions

Example invocations (an AI agent can run these directly as NL dispatch; a human reader can copy them into their AI tool):

1. **Version highlights for a blog post:**
   > "Using odoo-semantic, api_version_diff for account.move between Odoo 16.0 and 17.0. Summarize the key changes in non-technical language for a blog audience."

2. **CE vs EE feature table:**
   > "Using odoo-semantic, check if these modules are CE or EE in Odoo 17.0: sign, account_accountant, project_forecast, helpdesk. Give me a table."

3. **Upgrade story research:**
   > "Using odoo-semantic, api_version_diff for sale.order between 15.0 and 17.0. What are the biggest changes? I'm writing an upgrade guide for customers."

4. **Feature explainer research:**
   > "Using odoo-semantic, find_examples for inventory valuation with FIFO costing in Odoo 17. Show me real code so I can describe how it works accurately."

5. **Module ecosystem overview:**
   > "Using odoo-semantic, model_inspect sale.order in Odoo 17.0. How many modules extend it? This is for a piece about Odoo's extensibility."

---

## Plugin Skills (Claude Code)

If you use **Claude Code** with the Odoo AI Agent Team plugin:

| Skill | What it does |
|-------|-------------|
| `/odoo-feature-highlights` | Generates a feature highlight summary for a given Odoo version, grounded in real API data |
| `/odoo-addon-diff` | Compares module availability and features between two Odoo versions |
| `/odoo-doc-illustration` | Capture annotated screenshots of a live Odoo module for blog posts, sales decks, or app-store listings; multi-locale output |

---

## Writing Accurate Content

**Use this pattern for version comparison claims:**

1. Run `api_version_diff` for the relevant model or API
2. Run `check_module_exists` for any module you mention
3. Note the `odoo_version` in your tool call - always specify which version you verified against
4. For CE/EE claims: cite the `is_ee` flag from `check_module_exists`

**Common accuracy mistakes to avoid:**

| Wrong claim | How to verify with MCP |
|-------------|----------------------|
| "Odoo 17 has [feature] for free" | `check_module_exists` -> verify `is_ee: false` |
| "In Odoo 17, name_get was replaced by..." | `lookup_core_api("name_get", "<version>")` -> check `status` |
| "Odoo added [API] in version X" | `api_version_diff` -> `added_in` field |
