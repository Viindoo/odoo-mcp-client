---
name: odoo-feature-highlights
argument-hint: "[version/distribution]"
description: >-
  Marketing highlights of what is new in an Odoo version
---

## Role
Marketer / Product Manager

## Out of Scope

- Source-level API diff for developers → use `odoo-version-diff`
- Proof of a specific capability requirement → use `odoo-capability-proof`
- Single feature availability lookup → use `odoo-feature-check`

## MCP tools

<!-- BEGIN GENERATED TOOLS -->
- `api_version_diff` - Structured diff of an API symbol or scope across two Odoo versions: new, changed, removed, deprecated items.
- `check_module_exists` - Verify module availability, edition (CE/EE/Viindoo), and cross-version presence.
- `find_examples` - Semantic code search returning real indexed code snippets from the Odoo codebase.
- `model_inspect` ★ - Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, extenders, or a summary in one call.
- `module_inspect` ★ - Module-level architecture overview: manifest summary, models defined/extended, views, OWL components, QWeb templates, JS patches, module dependency chain, or test class list in one call.
- `set_active_version` ☆ - Pin a CONCRETE Odoo version (sentinels like 'auto' are rejected; the call doubles as a cheap reachability probe; 24h idle TTL).
<!-- END GENERATED TOOLS -->

## Context

Odoo ships annual major releases - each brings API changes (developer-facing) and user-facing improvements. This skill serves both audiences.

**Key version leaps:**

| Version | Highlight |
|---|---|
| v9 | First CE/EE split |
| v11/v12 | Community stabilization; major accounting improvements |
| v15 | ES6 module system canonical (`/** @odoo-module **/`); spreadsheet; sign matured |
| v17 | Performance; Python 3.10+; UX refinements |
| v18+ | ORM enhancements; module restructuring |

Frontend milestones (OWL library first release and major, module system, shell, legacy `web.Widget` lifetime) and the `openerp`-to-`odoo` package rename: `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-era-boundaries.md` rows 1, 1b and 5.

Custom distributions track Odoo versions - distinguish CE base from distribution-specific add-ons. **Data priority:** `api_version_diff` is ground truth - never assert "added in vX" without MCP confirmation.

## Instructions

**Round 1:** `api_version_diff` first - drives which features to highlight.

**Round 2 - Parallel (after Round 1):** Batch all of the following simultaneously:
- `find_examples` for top models (`sale.order`, `account.move`, `mrp.production`, `hr.leave`)
- `model_inspect(model=…, method='fields')` for headline feature models
- `check_module_exists` for all modules being highlighted
- `module_inspect(name=<module>, method='summary', odoo_version='<version>')` for those same modules

`module_inspect` summary gives concrete numbers ("adds 3 models and 12 views") instead of bare "module exists".

**Writing rules:**
- Lead with business outcomes, not technical mechanisms
- Use concrete numbers where available; avoid acronyms/jargon in main section
- Keep a separate "Technical notes" section for developers
- Vietnamese market: mention VAS accounting and Vietnamese tax features prominently

## Standalone-first fallback

When OSM is unreachable, follow `${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md`:

1. **Tier 2:** `WebFetch` `https://www.odoo.com/odoo-<version>/release-notes`; if that fails, `WebFetch` GitHub CHANGELOG (`https://github.com/odoo/odoo/blob/<version>/CHANGELOG.rst`) or releases page. Label artifact `grounded: local-source - not OSM-indexed`.
2. **Tier 3 (both fail):** Generate from training knowledge; prepend `grounded: ungrounded - OSM unavailable`; add caveat. Never ask caller to paste release notes.

## Output format

```
## Feature Highlights: Odoo <version>
*<Optional: custom distribution <version> highlights if applicable>*

### Headline features (top 3-5)
1. **<Feature name>** - <1-2 sentence business value description>
2. **<Feature name>** - <1-2 sentence business value description>
3. **<Feature name>** - <1-2 sentence business value description>

### Feature comparison: <prev version> vs <version>
| Capability | <prev> | <version> | Business impact |
|------------|--------|-----------|-----------------|
| ...        | ...    | ...       | ...             |

### Vietnamese market highlights (if applicable)
- <localization or regulatory feature relevant to Vietnam>

### Technical notes (for developers)
- <API change 1>
- <API change 2>

### Use in sales deck
**Slide title:** <suggested title>
**Talking points:**
- <point 1>
- <point 2>
- <point 3>
```

## Examples

**Example 1:** "feature highlights for Odoo 17 sales deck" → 3-5 headlines with business-value descriptions, comparison table vs Odoo 16, deck talking points.

**Example 2:** "highlights for custom distribution v17 marketing blog" → headlines in business language, emphasis on distribution-specific add-ons, comparison table vs prior version.

## Continuation Contract

Append a Continuation Contract block per `${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md`
(status / produced / next) - additive plan-runner output, changes nothing above.

In the `next` field, include optional suggestions:
- skill: odoo-doc-illustration
  confidence: 0.5
  reason: illustrate new features with screenshots for sales deck or blog post (use when static images are needed, not a recorded video)
