---
name: odoo-summarize-discovery
description: |
  Quick slash-command wrapper for the odoo-discovery-summary skill. Type `/odoo-summarize-discovery` when you want to explicitly synthesize raw meeting or discovery notes into a structured customer profile, bypassing the router to directly invoke the skill
---

# /odoo-summarize-discovery

Interactive command to synthesize raw discovery notes into a structured customer profile.

Use this command when you already know you want to run discovery synthesis and want to skip natural-language description matching. Useful in long conversations where the router may not reliably fire the skill, or when you want a direct, explicit path.

## Steps for the AI agent

1. **Phase 0: Parse input**
   - Check if `$ARGUMENTS` contains a customer label (e.g., `/odoo-summarize-discovery Customer-A`).
   - If a label is provided, store it. Otherwise, ask the user for one.
   - Resolve the raw notes yourself before asking: if they are already in the invocation
     context (e.g. passed by an orchestrator or earlier in the conversation), use them; if
     `$ARGUMENTS` or the context names a file path, `Read` it directly. Only ask the user to
     supply notes when none are available from context or a readable path.

2. **Phase 1: Trigger skill**
   - Construct a natural-language prompt that includes:
     - Customer label (name / org / context)
     - Raw notes (full text)
     - Request: "Synthesize these discovery notes into a structured customer profile. Include business context, pain points, goals, and recommended product fit."
   - The natural-language prompt auto-fires the `odoo-discovery-summary` skill.
   - The skill outputs a structured markdown profile with sections: summary, business context, pain points, goals, product fit, recommended next step.

3. **Phase 2: Show output**
   - Display the skill's output to the user.
   - Ask: "Save this profile? (yes / no / change-name)"
   - If the user provides a custom filename, use it. Otherwise, default to `.odoo-ai/discovery/<label>-<date>.md` where `<date>` is YYYY-MM-DD.

4. **Phase 3: Write file (optional)**
   - If the user answers `yes`, write the profile to the file using the `Write` tool.
   - Confirm: "`✓ Profile saved to .odoo-ai/discovery/<filename>.md`"
   - If the user answers `no`, stop. Do not write.

## Hard rules

- Do **not** call the MCP `Skill` tool directly. Instead, construct a natural-language prompt that describes what the user wants, and the router will auto-fire the skill.
- Do **not** spawn a subagent. This command runs at depth 0.
- Do **not** proceed to gap analysis, proposal drafting, or other chained skills. If the user wants the full discovery → proposal chain, redirect to `/odoo-respond-bid`.
- Check for `.odoo-ai/context.md` in the project root. If it exists and contains an `odoo_version` key, use that as the default Odoo version for the skill context. If the file is absent, do not assume a version — the skill will use its internal default.
- The file path `<cwd>/.odoo-ai/discovery/` is the canonical location. Create the directory if it does not exist.
- Do **not** commit or push the file. File ownership: read-only for this command.

## Examples

**Example 1: Inline notes**

```
User: /odoo-summarize-discovery Customer-A

Agent: What are the raw discovery notes? (paste or file path)

User:
  Met with finance team at Customer-A.
  They track invoices in Excel.
  20 invoices/month, growing to 50.
  Pain: no audit trail, manual data entry errors.
  Goal: automate invoice workflow, reduce errors significantly.
  Budget: small SMB tier, ROI required within first quarter.

Agent: [Triggers skill with customer label + notes]

Skill output:
  ## Customer-A — Discovery Profile
  
  **Business context:** Manufacturing, 120 employees...
  **Pain points:** Manual invoice tracking...
  **Goals:** Automate workflow, audit trail...
  **Recommended product fit:** Odoo Accounting + Invoice Automation...
  **Next step:** Demo accounts module, pricing discussion...

Agent: Save to .odoo-ai/discovery/Customer-A-Corp-2026-05-28.md? (yes / no / change-name)

User: yes

Agent: ✓ Profile saved to .odoo-ai/discovery/Customer-A-Corp-2026-05-28.md
```

## Standalone fallback

If `odoo-discovery-summary` skill is unavailable (OSM offline, network error), synthesize the customer profile yourself from the raw notes - filling the schema (industry, pain points, success criteria, decision process) is straightforward inference, not work to hand back to the user. Mark each synthesized field `[source: LLM-unverified]` (rather than blank `<TBD>`); the profile is still useful and can be cross-checked when OSM returns. Continue per the `yes/iterate/cancel` gate. Ask the user only for facts the notes genuinely do not contain.

## What this command does NOT do

- Does **not** perform gap analysis (use `/odoo-gap-analysis` for that).
- Does **not** draft a proposal or response (use `/odoo-respond-bid` for the full chain).
- Does **not** call MCP write tools directly — only `Write` via the agent after user confirmation.
- Does **not** commit or push files to Git.

## See also

- `/odoo-respond-bid` — Full discovery → gap analysis → proposal chain.
- `/odoo-semantic-mcp:connect` — Setup the Odoo Semantic MCP server (prerequisite).
- `odoo-discovery-summary` skill — The underlying skill triggered by this command.
