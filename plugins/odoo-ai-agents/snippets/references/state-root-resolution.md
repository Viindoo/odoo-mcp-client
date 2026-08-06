<!-- Reference material for snippets/state-root-resolution.md. This file is for humans and authors
     doing repo archaeology - it is never cited from any consumer-facing skill/agent/snippet body
     (see docs/authoring-skills-and-agents.md). Explanation and worked examples only; every
     decidable rule stays in the main file. -->

# State-Root Resolution - rationale

## Why the SHARE table's "EXHAUSTIVE...verified by grep" claim was softened (X-43)

The table used to claim exhaustiveness "verified by
`grep -rhoE '\.odoo-ai/[A-Za-z0-9_.-]+' plugins/ docs/ workflows/`". Running that exact command
shows it only catches literal `.odoo-ai/<name>` occurrences (mostly workflow YAML `output_dir:`
lines and a few Tier-1 files) - it does NOT catch the SHARE/ISOLATE-tier entries, because those are
referenced through the `<SHARE_DIR>`/`<ISOLATE_DIR>` placeholder convention, never a literal
`.odoo-ai/...` string. The claim was therefore unverifiable by its own stated method - an
"exhaustive" claim that cannot be checked without enumerating every writer, which is the missing
thing. The current wording states the table's actual guarantee (every subpath USED IN THIS REPO'S
PROSE today) without claiming a mechanical verification method that does not exist.

## Why the ISOLATE list's 13 workflow-output_dir rows ARE independently exhaustive

Unlike the SHARE list, these 13 names ARE grep-able: every `output_dir:` line in
`workflows/*.workflow.yaml` is a literal string, so "exactly 13, one per output_dir: line" is a
claim a maintainer (or a future lint rule) can mechanically re-verify against the YAML files
directly, without relying on prose placeholder usage.
