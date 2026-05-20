# Odoo Semantic — Consultant Guide

> **Get started (Claude Code):** `claude plugin marketplace add Viindoo/claude-plugins` → `claude plugin install odoo-semantic@viindoo-plugins` → `/odoo-semantic:connect`. Chi tiết + AI tools khác: [client setup](../setup.md).

For functional consultants and solution architects: quickly verify feature availability, close gap analyses, and scope customizations before committing estimates.

---

## What This Tool Solves for Consultants

The most common consultant pain points:

- **"Does Odoo do X natively?"** — check before promising it to the client
- **"Is this CE or EE?"** — avoid the embarrassing discovery mid-project
- **"How hard is this customization?"** — understand the inheritance chain before estimating
- **"Show me an existing example"** — demonstrate capability without building a demo from scratch

---

## Most Useful Tools for Consultants

| Tool | What it answers |
|------|----------------|
| `check_module_exists` | Is this feature native? CE or EE? What version added it? |
| `find_examples` | Show me real Odoo code that does something similar |
| `lookup_core_api` | Does this API exist and is it stable? |
| `resolve_model` | How complex is this model? How many modules already extend it? |
| `impact_analysis` | How risky is the customization the client wants? |
| `api_version_diff` | What changed between the client's current version and the target upgrade? |

---

## Feature Gap Analysis Workflow

### 1. Check native availability first

```
check_module_exists("account_budget", "17.0")
```

This tells you: module exists (yes/no), CE vs EE, and whether there's an EE confusion risk (a free addon with a similar name that might mislead).

### 2. Find comparable examples

```
find_examples("budget control with approval workflow and department-level limits")
```

Semantic search across indexed repos — returns real code snippets from the codebase that match what you're describing.

### 3. Understand the model complexity

```
resolve_model("account.budget", "17.0")
```

Field count, module extensions, method list. If the model has 15+ modules extending it, customization risk is higher — factor that into your estimate.

### 4. Check upgrade path if relevant

```
api_version_diff("account.move", "16.0", "17.0")
```

Quickly surface breaking changes before telling the client how smooth the upgrade will be.

---

## Sample Consultant Questions

Copy these prompts into your AI tool:

1. **Feature availability check:**
   > "Using odoo-semantic, does Odoo 17.0 have a native field service management module? Is it Community or Enterprise?"

2. **Gap analysis for a prospect:**
   > "Using odoo-semantic, check if Odoo 17.0 Community has a subscription / recurring invoice module. If EE-only, what are the key features missing from CE?"

3. **Customization scope:**
   > "Using odoo-semantic, resolve model account.move in Odoo 17.0. How many modules extend it? Does extending it for invoice approval carry HIGH risk?"

4. **Example-based demo prep:**
   > "Using odoo-semantic, find_examples for approval workflow on sale.order with multi-level validation. Show me real code from indexed repos."

5. **Upgrade risk briefing:**
   > "Using odoo-semantic, find_deprecated_usage for Odoo 17.0. My client is on 16.0. What are the top 3 risks they should budget for?"

---

## Plugin Skills (Claude Code)

If you use **Claude Code** with the Odoo Semantic plugin:

| Skill | What it does |
|-------|-------------|
| `/odoo-feature-check` | Full feature availability report: native vs EE vs addon; includes CE/EE flag |
| `/odoo-gap-analysis` | Gap analysis between client requirements and Odoo native features; flags missing CE capabilities |

---

## Reading Results

- **`is_ee_confusion: true`** — There is a known CE module with a similar name; clients often confuse CE and EE. Flag this in your proposal.
- **`Fields: N`** — The model has N fields across all extending modules. More fields = higher complexity.
- **`Extends: N modules`** — N modules touch this model. Custom extension risk increases with N.
- **`status: deprecated`** from `lookup_core_api` — The API your customization relies on is being removed. This is a project risk.

---

## Estimating From Results

| Signal | Implication |
|--------|-------------|
| Model extended by >10 modules | Customization is medium-to-high risk — plan extra testing |
| impact_analysis: Risk HIGH | Budget 2-3x the dev estimate; this will break things |
| check_module_exists: EE only | Add license cost to proposal |
| find_deprecated_usage: 3+ items | Upgrade project needs a remediation phase |
