---
name: odoo-run-brl
argument-hint: "[customer-label] [brl-file]"
description: >-
  Slash shortcut: run odoo-brl on a requirement list for a named customer
disable-model-invocation: true
---
# /odoo-run-brl

Thin dispatcher for the `odoo-brl` skill. Takes an optional customer label in `$ARGUMENTS`
(e.g. `/odoo-run-brl Customer-A`). All orchestration logic lives in the skill body.

## When to use

Type `/odoo-run-brl` when you have a list of business requirements (tens to thousands of items)
and need:

- **4-way classification** per item (Available-in-Odoo-CE / -EE / Available-in-Viindoo / Custom)
- **Deterministic cost estimate** (lookup table from `cost-config.json`, auditable for client proposals)
- **RTM export** (rtm.csv for Excel, results.jsonl for machine consumption)
- **Executive report** (report.md with classification mix, budget range, risk flags)

For a **single feature** check: use `/odoo-ai-agents:odoo-feature-check` instead.
For a **short ad-hoc gap matrix** (no cost, no scale): use `/odoo-ai-agents:odoo-gap-analysis` instead.

## Hard rules

1. **Project facts.** At startup, resolve the Odoo series and OSM profile by working the rungs of
   `${CLAUDE_PLUGIN_ROOT}/snippets/project-facts-resolution.md` in order, stopping at the first that
   answers; return `status: NEEDS_CONTEXT` naming what every rung left unresolved. When no `[[instance]]` covers this repo,
   offer `/odoo-ai-agents:odoo-setup` to declare one - an offer, never a precondition. Resolve
   `<SHARE_DIR>`/`<ISOLATE_DIR>` once per `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`
   before any state-root read or write; substitute the captured absolute path - never write the
   placeholder or a bare `.odoo-ai/` into a Read/Write/Edit.
2. **Abstract labels.** Use the customer label from `$ARGUMENTS` or default "Customer-A".
   Never write real company names, VND figures, or internal pricing into any committed file.
3. **Dispatch via the Skill tool.** This command fires the `odoo-brl` skill using the Skill tool. NL description-match is the fallback when the Skill tool is unavailable.
4. **Public repo safety.** All job artifacts go to `<SHARE_DIR>/brl/<job-id>/` which is gitignored.
   No deliverable is committed to the repo.

## Invocation

### Step 0 - Parse arguments + dispatch

1. Extract customer label from `$ARGUMENTS`. If absent, use "Customer-A".
2. **Resolve the BRL content yourself.** If `$ARGUMENTS` contains a file path (ends in
   `.csv`/`.md`/`.txt`/`.xlsx`, or passes a file-exists check), `Read` it and embed the actual
   content into the dispatch. If the BRL is already present in the invocation context, use that.
   When no source is available, return `status: NEEDS_CONTEXT` naming the requirement list.
3. Fire the `odoo-brl` skill via the Skill tool (substitute the real BRL content, never leave a
   placeholder):

> "Process this business requirement list for [CUSTOMER_LABEL]: classify each requirement
> as Available-in-Odoo-CE, Available-in-Odoo-EE, Available-in-Viindoo, or Custom using
> double-profile MCP checks; compute deterministic cost from cost-config.json; produce
> a full RTM (rtm.csv + results.jsonl) and executive report (report.md) in
> <SHARE_DIR>/brl/[CUSTOMER_LABEL]-[DATE]-[HEX]/. Input: [embed the BRL content read above; if a
> file_path was given, use the Read output]."

## Resume

If a previous BRL job was interrupted, include the job-id in the dispatch:

> "Resume BRL job [job-id] for [CUSTOMER_LABEL] from the last checkpoint."

The skill reads `checkpoint.json` and resumes at `last_completed_chunk + 1`.

## Standalone fallback

If OSM is unreachable, the skill classifies by LLM (marked `unverified-llm`) and cost still runs
from config (skill body `## Standalone-first fallback`).
