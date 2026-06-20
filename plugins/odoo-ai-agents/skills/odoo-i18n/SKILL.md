---
name: odoo-i18n
description: >-
  Translate Odoo modules and keep terminology consistent - the dedicated i18n cluster that exports
  .pot templates, non-destructively merges them into maintained .po translations, dispatches
  hand-translation, and audits cross-module term consistency. Front door for ALL Odoo translation
  and the i18n step other workflows dispatch into (forward-port, a new module/feature, a bugfix). Fire on "translate this module", "export .pot / .po", "update the
  Vietnamese translation", "sync terminology", "đồng bộ thuật ngữ", "dịch module Odoo",
  "xuất .pot/.po", "cập nhật bản dịch", or any i18n / terminology-consistency ask for Odoo. The non-destructive contract is load-bearing: re-exporting a .po from a fresh DB destroys
  40-90% of existing msgstr, so translation MEMORY is always forwarded by merge, never regenerated.
  Requires a running Odoo instance (export + validate need a live DB); missing instance is a BLOCK.
  Route a one-line UI label fix to odoo-coding; a rendered-UI language check to odoo-ui-review
---

## Persona

i18n conductor for Odoo translation work. This skill owns the `.pot`/`.po` lifecycle, the
glossary, and the subagent lifecycle for translating a module or a scope of modules onto a target
Odoo series. It makes the orchestration decisions (which phase at which model tier, when to stop
for a human, when to dispatch the leaf translator) and delegates the actual term translation to the
`odoo-translator` agent.

The load-bearing belief: a translation is MEMORY to be forwarded, never regenerated. Re-exporting a
`.po` from a fresh database overwrites it with empty `msgstr`s and silently destroys 40-90% of the
existing human translation with a clean exit code. Every phase below preserves the maintained
`msgstr`s by polib MERGE and only refreshes the term inventory from a fresh `.pot` template. A clean
export + a green install is NOT proof the translation survived; only a polib non-empty-msgstr
regression check plus an Odoo `-u` reload proves it. Full non-destructive recipe (3-layer L1/L2/L3 +
validation + glossary): `references/i18n-recipe.md` - the SSOT this skill and `odoo-forward-port`
both point at.

## Out of Scope

- A single user-facing label or `string=` added while writing code -> use `odoo-coding` (it
  applies the terminology-consistency lookup inline; this skill is for module-scale translation)
- Checking whether a RENDERED screen shows the right language / locale at runtime -> use
  `odoo-ui-review` (live browser), not this static export-and-merge pipeline
- Designing a new model or feature before any code -> use `odoo-solution-design`
- Reviewing translation code or a `.po` diff for bugs -> use `odoo-code-review`
- Writing the production code whose strings will later be translated -> use `odoo-coding`

## Standalone-first fallback

i18n REQUIRES a running Odoo instance with the target module installed. Export (`--i18n-export`)
walks the live registry to enumerate translatable terms, and validation reloads the module against a
real DB - both need an instance. There is NO no-DB workaround: babel/polib alone cannot discover a
module's translatable terms the way Odoo's registry does, so every "translate without an instance"
path produces an INCOMPLETE or WRONG result and must be refused.

When no instance is available, BLOCK with status `NEEDS_CONTEXT` (Continuation Contract
`blocked_reason`). Do not improvise a partial export. Acquire an instance per
`docs/reference/INSTANCE-LIFECYCLE.md` (the allocator/lifecycle decision tree) and resume at P2.
Ground the exact odoo-bin export/reload flags for the target series before invoking - the CLI
surface differs per version (server flags v8-v18 vs the `i18n` subcommand v19+):

```
cli_help(command='i18n-export', odoo_version='<target>')   # v8-v18 (server flag)
cli_help(command='i18n', odoo_version='19.0')              # v19+ (subcommand)
```

When OSM itself is unreachable, flag-grounding falls back to the instance's own `odoo-bin --help`;
the instance requirement is absolute and never degrades to a no-DB path.

## The 6-phase pipeline

Run phases in order. Each phase names its model tier; dispatch follows
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` (Mode B) for any fan-out. Artifacts land
under `.odoo-ai/i18n/<slug>-<date>/`. The full non-destructive recipe (every command, the polib
merge, the validation gates, the glossary) lives in `references/i18n-recipe.md` - this skill points
at it rather than duplicating it.

**P0 - Scope gate [sonnet, STOP].** Parse the request into target modules, target language(s), and
target Odoo series. Confirm an instance is available (else BLOCK per `## Standalone-first fallback`).
Resolve each module name to its directory and dependency closure. Emit a one-line scope summary
(modules x languages x series + dependency order) and STOP for approval in a single turn before any
export or DB op.

**P1 - Glossary build [haiku or sonnet].** Assemble the translation memory the later phases reuse:
read the already-translated `<lang>.po` of core Odoo and the module's dependency modules, load the
project `.odoo-ai/glossary.yml` (domain/regulatory terms + their source citation), and for any
field-mapped term confirm the canonical label via OSM (see the glossary layer in the recipe). Write
the assembled TM to `.odoo-ai/i18n/<slug>-<date>/glossary-tm.json`. Sonnet when the scope spans
domain/regulatory terminology; haiku for a plain module.

**P2 - Export `.pot` template [sonnet].** Per L1 of the recipe: install the module, LOAD the target
language, then export a `.pot` TEMPLATE on a clean per-module install in an isolated DB, in
dependency order. Never export over a maintained `.po`. The per-version flags and their rationale -
`--load-language` (activate in DB) vs `--language`/`-l` (select export file), `--skip-auto-install`
v17-v18, one fresh DB per module v8-v16, the `odoo-bin i18n` subcommand v19+ - live in the recipe;
ground the exact form via `cli_help` above (`command='i18n-export'` v8-v18, `command='i18n'` v19+).
Multi-language is a separate scope (issue #97).

**P3 - Translate [dispatch `odoo-translator`].** Dispatch the `odoo-translator` agent (one per
language, or per module-cluster for a large scope) as a subagent launch to run the L2 polib TM-merge
and L3 hand-translation of the residual. See the dispatch contract below for the model and brief.

**P4 - Validate [haiku].** Per the recipe's validation gates: run the polib non-empty-msgstr
regression (BLOCK on a large drop - that means the merge was skipped and an overwrite slipped
through), the placeholder-integrity check, and the Odoo `-u <module>` reload (NOT `msgfmt`). The
`-u` reload's pre-condition is that the target language is LOADED in the DB (`--load-language` v8-v18
/ `i18n loadlang` v19+); an absent language makes the reload pass silently while translations stay
inactive - a false pass. A clean reload with no translation error in the log is the pass signal. See
`docs/reference/INSTANCE-LIFECYCLE.md` for the reload semantics.

**P5 - Consistency audit + report [opus, ADVISORY].** Audit terminology consistency across the
translated modules against the glossary TM and report divergences. This phase is **ADVISORY and
NEVER blocking**: it surfaces inconsistencies for a human to decide on, but it does NOT auto-edit or
auto-dedup. Critically, legally independent regimes (e.g. the Vietnam accounting circulars TT200 /
TT133 / TT99) MUST NOT be deduped even when their `msgid`s match - each regime's translation stays
complete and self-standing, and an incidental string match is never a reason to share or rewrite a
translation across regimes. Write the findings to
`.odoo-ai/i18n/<slug>-<date>/consistency-audit.md`.

## Dispatch contract -> odoo-translator

P3 dispatches the `odoo-translator` agent as a subagent launch. Carry a brief with: the target
module(s), language(s), series; the glossary TM path from P1; the maintained `.po` and fresh `.pot`
paths; and the validation gates the leaf must self-check. Pass the model both as a `DISPATCH MODEL:`
line in the brief and as the Agent `model` parameter:

- **sonnet** (default) for a plain module translation.
- **opus** when the scope carries domain / legal / regulatory terminology (e.g. accounting
  circulars, statutory report labels) where a wrong term has compliance cost.

The leaf carries the worker brief (`${CLAUDE_PLUGIN_ROOT}/snippets/worker-brief.md`) and appends its
decisions to the worklog (`${CLAUDE_PLUGIN_ROOT}/snippets/worklog-contract.md`). It does the polib
merge and translation directly - there is no OSM i18n tool, so it uses shell `odoo-bin` + `polib`,
and uses OSM only to confirm canonical field labels, e.g.:

```
entity_lookup(kind='field', model='account.move', field='amount_total', odoo_version='<target>')
```

## Artifacts

All under `.odoo-ai/i18n/<slug>-<date>/`:

- `glossary-tm.json` - assembled translation memory (P1)
- `<module>.pot` - exported template(s) (P2)
- `translation-report.json` - per-module non-empty `msgstr` count before/after the merge (the
  regression evidence; a drop is a BLOCK)
- `consistency-audit.md` - the advisory P5 findings

## Continuation Contract

When the run finishes (or pauses at the P0 gate or an instance BLOCK), append a Continuation
Contract block per `${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced /
next). `produced` lists the artifacts above; a missing instance is `status: NEEDS_CONTEXT` with the
instance requirement as `blocked_reason`. Additive output for the run-driver - it does not change
anything produced above.
