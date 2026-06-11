---
name: odoo-run-brl
description: |
  Process a business requirement list (BRL) of any size into a classified, costed, dependency-ordered implementation plan with full RTM export. Chains INGEST + GATE 0 + chunked 4-way classify + deterministic cost + dependency DAG + GATE E + deliverables (rtm.csv, cost.json, dag.mermaid, report.md). Invoke when you have a multi-item requirement list and want end-to-end scoping
---
# /odoo-run-brl

Thin dispatcher for the `odoo-brl` skill. Accepts an optional `$ARGUMENTS` token for
the customer label (e.g. `/odoo-run-brl Customer-A`). All orchestration logic lives in the
skill body - this command is a recipe shim only, following the 1-orchestration-SSOT rule.

> Named `odoo-run-brl` (not `odoo-brl`) because a command name must stay disjoint from the
> skill name `odoo-brl`. The skill also auto-registers `/odoo-ai-agents:odoo-brl`; this
> command is the convenience entry point that takes a customer-label argument and dispatches to
> the same skill body — one orchestration mechanism, two entry points.

## When to use

Type `/odoo-run-brl` when you have a list of business requirements (tens to thousands of items)
and need:

- **4-way classification** per item (Available-in-Odoo-CE / -EE / Available-in-Viindoo / Custom)
- **Deterministic cost estimate** (lookup table from `cost-config.json`, auditable for client proposals)
- **RTM export** (rtm.csv for Excel, results.jsonl for machine consumption)
- **Executive report** (report.md with classification mix, budget range, risk flags)

For a **single feature** check: use `/odoo-feature-check` instead.
For a **short ad-hoc gap matrix** (no cost, no scale): use `/odoo-gap-analysis` instead.

## Hard rules

1. **Phase gate mandatory.** GATE 0 blocks all classification work; GATE E blocks all deliverable
   writes. The command does NOT advance past either gate without explicit user confirmation.
2. **Context check.** At startup, load `.odoo-ai/context.md` if present. If missing, suggest
   `/odoo-onboarding` but allow manual continuation.
3. **Abstract labels.** Use the customer label from `$ARGUMENTS` or default "Customer-A".
   Never write real company names, VND figures, or internal pricing into any committed file.
4. **NL-dispatch only.** This command fires the `odoo-brl` skill via a natural-language prompt
   matching the skill's description. The Skill tool is never used.
5. **Public repo safety.** All job artifacts go to `.odoo-ai/brl/<job-id>/` which is gitignored.
   No deliverable is committed to the repo.

## Invocation

### Step 0 - Parse arguments + dispatch

1. Extract customer label from `$ARGUMENTS`. If absent, use "Customer-A" as default or
   ask the user in a single brief message.
2. **Resolve the BRL content yourself.** If `$ARGUMENTS` contains a file path (ends in
   `.csv`/`.md`/`.txt`/`.xlsx`, or passes a file-exists check), `Read` it and embed the actual
   content into the dispatch. If the BRL is already present in the invocation context, use that.
   Only ask for a path or paste when no source is available.
3. Fire the `odoo-brl` skill via NL dispatch (substitute the real BRL content, never leave a
   placeholder):

> "Process this business requirement list for [CUSTOMER_LABEL]: classify each requirement
> as Available-in-Odoo-CE, Available-in-Odoo-EE, Available-in-Viindoo, or Custom using
> double-profile MCP checks; compute deterministic cost from cost-config.json; produce
> a full RTM (rtm.csv + results.jsonl) and executive report (report.md) in
> .odoo-ai/brl/[CUSTOMER_LABEL]-[DATE]-[HEX]/. Input: [embed the BRL content read above; if a
> file_path was given, use the Read output]."

The skill handles all phases (INGEST, GATE 0, Phase A-B-C-E, GATE E) with checkpoint/resume.

## Resume

If a previous BRL job was interrupted, include the job-id in the dispatch:

> "Resume BRL job [job-id] for [CUSTOMER_LABEL] from the last checkpoint."

The skill reads `checkpoint.json` and resumes at `last_completed_chunk + 1`.

## Standalone fallback

If OSM is unreachable, the skill degrades gracefully: LLM-based classification
(marked `unverified-llm`), cost computation still runs from config. See skill body
`## Standalone-first fallback` section.

## Examples

```
/odoo-run-brl Customer-A
```
Starts BRL pipeline for Customer-A. The command reads the BRL from a file path in `$ARGUMENTS`
or from the invocation context (paste is the last resort). GATE 0 presents plan. After
approval: classify -> cost -> evidence -> DAG -> GATE E -> deliverables.

```
/odoo-run-brl
```
Defaults to Customer-A label. Same flow.

## What this command does NOT do

- Does NOT send emails or upload files
- Does NOT commit anything to the repo (all artifacts in `.odoo-ai/brl/`)
- Does NOT guarantee OSM availability - degrades gracefully when unreachable
- Does NOT externalize cost estimates without passing GATE E (the approval gate is the
  safeguard before any deliverable is shared, whether the caller is a human or an orchestrator)
