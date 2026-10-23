---
name: odoo-i18n
argument-hint: "[module(s)] [target-lang e.g. vi_VN]"
description: >-
  Translates Odoo modules: exports and updates .pot/.po, keeps existing translations
---

## Role

i18n conductor for Odoo translation. Owns the `.pot`/`.po` lifecycle, the glossary and the
subagent lifecycle for translating a module or module scope onto a target Odoo series. Decides the
phase model tier and when to dispatch the leaf, and delegates term translation to the
`odoo-translator` agent.

A translation is MEMORY to be forwarded, never regenerated. Never export a `.po` from a database
that has not loaded the existing translation. Method: build a FRESH instance, LOAD the existing
`.po` into it, re-export, then RECONCILE by a git-ops diff-review - adjudicate every removed/changed
entry before commit (no `polib`), into the THREE buckets of
`${CLAUDE_PLUGIN_ROOT}/snippets/po-entry-semantics.md` § Adjudicating a removed or changed entry.

A translation equal to its source is stored as an EMPTY `msgstr`. Such an entry is done: never count
it as untranslated, never fill it with its `msgid`, never make "zero empty `msgstr`" a goal. The rules
are in `${CLAUDE_PLUGIN_ROOT}/snippets/po-entry-semantics.md`; term choice is
`${CLAUDE_PLUGIN_ROOT}/snippets/translation-term-policy.md`; the export order and the rule that only
`msgstr` content may change after an export are `references/i18n-recipe.md` § Export order and
§ Keep Odoo's export format.

The export instance is installed WITH DEMO DATA, has `en_US` plus every target language active, and
is the ONE build every artifact of the run - the `.pot` and each `.po` - is exported from
(`references/i18n-recipe.md` KT4/KT5 + Validation gate 6).

A clean export + a green install is NOT proof the translation survived; only an adjudicated
diff-review plus an Odoo `-u` reload is. Full recipe (3-layer L1/L2/L3 + validation + glossary):
`references/i18n-recipe.md`.

**Sole dispatcher.** Only this skill launches the `odoo-translator` agent. A caller that needs a
module translated, a `.pot`/`.po` exported/merged, or cross-module terminology audited invokes this
skill via the Skill tool. A live instance is provisioned by invoking the `odoo-instance` skill
(never the raw `odoo-instance-ops` agent).

**`WORKTREE_PATH` is required whenever this skill runs** (`${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md`
§ Universal skeleton field 5). A caller passes `WORKTREE_PATH:`; forward it verbatim to every
`odoo-translator` leaf. Invoked with no `WORKTREE_PATH` and no worktree of your own -> provision one
via `git-toolkit:git-ops` before P2, per `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`. Pass
`WORKTREE_PATH` through to `odoo-instance` so the export reads that tree.

## Out of Scope

- A single user-facing label or `string=` added while writing code -> use `odoo-coding` (it
  applies the terminology-consistency lookup inline; this skill is for module-scale translation)
- Checking whether a RENDERED screen shows the right language / locale at runtime -> use
  `odoo-ui-review` (live browser), not this static export-and-merge pipeline
- Designing a new model or feature before any code -> use `odoo-solution-design`
- Reviewing translation code or a `.po` diff for bugs -> use `odoo-code-review`
- Writing the production code whose strings will later be translated -> use `odoo-coding`

## MCP tools

<!-- BEGIN GENERATED TOOLS -->
> **Pick the right tool first.** Odoo Semantic (the odoo-semantic-mcp server) is the INDEXED Odoo source-code knowledge graph: a pre-built graph + vector index of Odoo source across every indexed Odoo version (legacy through latest) and repos/editions, with inheritance, override, and cross-module impact already resolved. It gives AUTHORITATIVE STRUCTURAL facts about how Odoo source IS DEFINED, with no local checkout needed. Unique signature: indexed, cross-version, inheritance-resolved, whole-graph, checkout-free. It is a STATIC index with NO runtime/live data.
>
> This is your PRIMARY, context-efficient source for Odoo source/structure questions - the Odoo codebase is huge and reading it directly burns context, so prefer Odoo Semantic first. Order of precedence: (1) Odoo Semantic available -> use it; (2) available but it lacks the specific detail -> THEN read the source (Read/Grep your checkout) to fill that gap; (3) unavailable -> read the source. Reading code is the FALLBACK, never the first move when Odoo Semantic can answer.
>
> Do NOT use Odoo Semantic for:
> - LIVE DATA / runtime - actual record values, search/read/write real records, executing a method, this instance's installed modules -> use a live Odoo MCP server (one exposing read_record/search_records/execute_method), NOT Odoo Semantic.
>
> Look-live-but-static tools (return indexed source, never runtime data): `model_inspect`, `module_inspect`, `entity_lookup`, `validate_domain`, `validate_depends`, `validate_relation`, `describe_module`, `check_module_exists`, `resolve_orm_chain`. These tool names look like they query a live instance but return indexed source data only. If you need live records, Odoo Semantic is the wrong server.

**Session bootstrap** (call once at session start):
- `set_active_version(odoo_version='17.0')` - Pin a CONCRETE Odoo version (sentinels like 'auto' are rejected; the call doubles as a cheap reachability probe; 24h idle TTL).

**Primary tools:**
- `cli_help` - Look up odoo-bin subcommand flags, their status, and replacement for deprecated flags.
- `entity_lookup` ★ - Single-entity drill-down by kind discriminator: model, field, method, view, module, pattern, or report - with full inheritance chain and source module.
<!-- END GENERATED TOOLS -->

## Standalone-first fallback

i18n REQUIRES a running Odoo instance with the target module installed. Never translate without one
(no babel, no raw PO parser). When no instance is available, BLOCK with status `NEEDS_CONTEXT`
(Continuation Contract `blocked_reason`) and do not export partially. Acquire an instance by invoking
the `odoo-instance` skill (never the raw `odoo-instance-ops` agent) per
`docs/reference/INSTANCE-LIFECYCLE.md` § Decision tree, and resume at P2.

## The 6-phase pipeline

Run phases in order. Each phase names its model tier; dispatch follows
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` (Mode B) for any fan-out. Artifacts land
under the Tier-2 ISOLATE dir; resolve it via the resolve-capture-substitute protocol in
`${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md` (captured path shown as `<ISOLATE_DIR>`
below) - `<ISOLATE_DIR>/i18n/<slug>-<date>/`. The full recipe (every command, the diff-review
reconcile, the validation gates, the glossary) is `references/i18n-recipe.md`.

**Orphan sweep (every run, BEFORE P0).** Run:

`find <ISOLATE_DIR>/i18n/ -mindepth 1 -maxdepth 1 -type d -mmin +43200 -exec rm -rf {} +`

Rule: `${CLAUDE_PLUGIN_ROOT}/snippets/visual-evidence-lifecycle-contract.md` Clause 3.

**P0 - Scope [haiku].** Resolve the target language list by precedence (highest first),
then echo which source was used:

1. Explicit languages in the request/args.
2. Machine-global registry: read `${ODOO_AI_HOME:-$HOME/.odoo-ai}/i18n.json` and use its
   `default_languages` array if present and non-empty.
3. Infer from existing `<lang>.po` filenames in each module's `i18n/` directory
   (`<module>/i18n/<lang>.po`); skip this tier when no `i18n/` dir exists. A stem is either the
   full language code or Odoo's export name, the language's ISO code: resolve an ISO-code stem to
   its language code before passing it to a build.
4. Query the confirmed instance: `res.lang` records with `active = True` (codes).

**No tier 5 - the target language is a REQUIRED input with NO built-in default.**
Never treat `en_US` as a *target* language or as a stand-in for an unresolved target. When tiers
1-4 ALL resolve empty:

- **Standalone** (a human asked directly, not as a dispatched pipeline step): return
  `status: NEEDS_CONTEXT` naming the missing field (`target language`).
- **Mandated** (a caller dispatched you as a required step, `${CLAUDE_PLUGIN_ROOT}/snippets/i18n-mandate-contract.md`):
  record `i18n: not-applicable (no target language resolvable from tiers 1-4)` (escape E3), return
  that verbatim to the caller, and translate nothing.

A caller SHOULD pass explicit `TARGET LANGUAGES` when it has them; when it has none, tiers 2-4 still
run against whatever IS available.

**`en_US` is mandatory, independent of the tiers above.** After resolving the target languages, set
`activation_languages = {"en_US"} union target_languages`. `en_US` is ALWAYS loaded into the DB
alongside every target language (recipe KT3) - none of the tiers above can produce it (Odoo ships no
`en_US.po`), so add it here. It governs the DB-activation set - the export build's `languages` and
the `languages_loaded` its `INSTANCE_HANDLE` must show - ONLY; no `en_US.po` is exported or merged.

Echo the resolved language list (target languages + the `activation_languages` set) AND the source tier
that produced it in the scope summary.

Also in P0: confirm an instance is available (else BLOCK per `## Standalone-first fallback`). Resolve
each module name to its directory and dependency closure. Emit a one-line scope summary (modules x
target_languages x series + dependency order + language-source tier), then run P1.

A dispatch is Mandated when it carries `WORKTREE_PATH` AND (an `INSTANCE_HANDLE` or
`SELF_PROVISION: worktree-addons`) (`i18n-mandate-contract.md` obligations 1-2). When either is
missing from a mandated dispatch, RETURN `status: BLOCKED` (`i18n: blocked (missing <field>)`, the
E5/E6 shape). Return the scope summary (or the E3/BLOCKED record) to the caller with the final result.

**P1 - Glossary build [haiku or sonnet].** Assemble the translation memory the later phases reuse:
read the already-translated `<lang>.po` of core Odoo and the module's dependency modules, load the
project `glossary.yml` (domain/regulatory terms + their source citation) from
`<SHARE_DIR>/glossary.yml` (Tier-2 SHARE, resolved via the same `state-root-resolution.md` protocol),
and for any field-mapped term confirm the canonical label via OSM (glossary layer in the recipe).
Build the TM **per language** (one independent memory per language, covering all in-scope modules).
Write each to `<ISOLATE_DIR>/i18n/<slug>-<date>/glossary-tm-<lang>.json`. Do NOT share or merge TM
across languages. Sonnet when the scope spans domain/regulatory terminology; haiku for a plain
module.

**P2 - Build the export instance, then export `.pot` + every `.po` from it [haiku].** Per L1 of
the recipe: ONE build per module serves the whole run, and both artifact kinds come out of it.

Dispatch `odoo-instance` with this build shape, stated explicitly:

| Field | Value |
|---|---|
| `demo` | `on` (recipe KT4) |
| `languages` | the full `activation_languages` set from P0 (recipe KT1 + KT3); `instance_build` adds `en_US` to every build |
| `skip_auto_install` | `true` where the series has it |
| `WORKTREE_PATH` | the run's worktree |

Then export from THAT database with `mcp__plugin_odoo-ai-agents_odoo-local__instance_i18n_export`
on the build's `lease_token` - one call, every target language - and `job_wait` it until its `result`
is not `timeout`. Its `exports` list is the run's artifact paths. Never compose an `odoo-bin`
export. When the tool refuses the call or fails the job, follow its remedy (recipe L1): a demo or
language refusal means the build is wrong (KT1 / KT4) - fix the build, never the route to the export.
The committed `.po` at HEAD stays the P3 diff-review baseline. ALWAYS re-export the `.pot` FRESH
from the currently-installed code on every invocation - never reuse a committed or prior-run `.pot`
on disk (recipe gate 5). One FRESH `.pot` export per module per run, not per language.

**Every artifact of one run comes from ONE build (recipe KT5).** Do not provision a second instance
for the `.pot`, or a fresh one per language. Record the `INSTANCE_HANDLE` every artifact came from
and pass the SAME one to every P3 leaf. Language loading, `--skip-auto-install` scope and database
isolation: recipe KT1 and § Isolate the term inventory.

**P3 - Translate [dispatch `odoo-translator`].** Dispatch the `odoo-translator` agent as a
subagent launch for EACH (module-cluster × language) pair. Each leaf carries exactly ONE language;
never bundle languages in a leaf. Each leaf runs the L2 re-export + diff-review reconcile and L3
hand-translation of the residual for its language. The leaves, and your own P4 reloads, share ONE
database: they follow `${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md` § One build or
export per database. Loop order: `## Multi-language loop order` in `references/i18n-recipe.md`.
Model and brief: dispatch contract below.

**P4 - Validate [haiku].** Run all validation gates (recipe § Validation) for EACH target language
independently, after all P3 leaves finish - a second, independent pass over each leaf's own Round 4
self-check. Per language:
run the git-ops diff-review adjudication on `<lang>.po` (BLOCK on any un-adjudicated or WRONG-ruled
loss), the per-entry placeholder-integrity check, the build-shape gate (recipe gate 6: the export
build carried demo data, and the `.pot` plus every `.po` came from that ONE build - on a mismatch
re-export and re-adjudicate rather than commit), the export-format gate (recipe gate 7: only
`msgstr` content differs from Odoo's export), and the Odoo `-u <module>` reload (NOT `msgfmt`).
Pre-condition for each language's reload: the target language is LOADED in the DB (listed in the
export build's `languages_loaded`); confirm BOTH `en_US` (KT3) and each `<lang>`. Verify the `.pot`
consumed was re-exported THIS run (recipe gate 5). A clean reload with no translation error in the
log is the pass signal per language. Reload semantics:
`docs/reference/INSTANCE-LIFECYCLE.md` § `-i` vs `-u` semantics. Each per-language `-u <module>`
reload runs against the SAME lease as the P2/L1 `-i` install that created the DB via Odoo
create-on-init, or mode `exclusive` on a declared DB with the module pre-installed - never a fresh
`ephemeral` lease.

**Release the export instance [MANDATORY, after the last P4 reload].** When THIS skill provisioned
the P2 build (standalone, or `SELF_PROVISION`), you are the run-level owner of the lease
(`${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T1): once every P3 leaf has returned
and the last per-language reload is done, call
`mcp__plugin_odoo-ai-agents_odoo-local__lease_release` with its `lease_token` and `run_id` - or
`lease_park` when the user or a named next step still wants that database. An `INSTANCE_HANDLE`
your caller forwarded DOWN to you is never yours to release or park.

**P5 - Consistency audit + report [sonnet; ADVISORY].** Audit terminology consistency across the
translated modules for EACH target language separately. NEVER blocking; do NOT auto-edit or
auto-dedup. The independent-regime guard binds it (`${CLAUDE_PLUGIN_ROOT}/snippets/translation-term-policy.md`
§ Independent-regime guard): never dedup legally independent regimes even when their `msgid`s match.
An entry left with an empty `msgstr` because its translation equals its source is never an
inconsistency or a gap to report (`po-entry-semantics.md` § An empty `msgstr`). Write findings per
language to `<ISOLATE_DIR>/i18n/<slug>-<date>/consistency-audit-<lang>.md`.

## Dispatch contract -> odoo-translator

Fill the caller-side skeleton in `${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md` § Universal
skeleton (read it by path) plus the target agent's family delta; never inline that file verbatim
into a hard-leaf brief.

P3 launches one `odoo-translator` leaf per (module-cluster × language) pair, scoped to exactly ONE
language. Carry a brief with: `WORKTREE_PATH` (the absolute worktree the `.po`/`.pot` writes land in
- MANDATORY, `dispatch-brief.md` § Universal skeleton field 5); `SHARE_DIR` + `ISOLATE_DIR` as the
absolute literals you captured at P0 (field 5 again); the target module(s), the single target
language, series; the glossary TM path for that language (`glossary-tm-<lang>.json`) from P1; the
`<lang>.po` and fresh `<module>.pot` paths from the P2 `exports`; and the validation gates the leaf
must self-check.

Also carry, verbatim, the P2 build the artifacts came from: `INSTANCE_HANDLE` (the SAME handle for
every leaf of the run) plus `BUILD_SHAPE: demo=on, languages=<activation set>,
skip_auto_install=<bool>`. A leaf that receives a `BUILD_SHAPE` with `demo` anything but `on`, or
that cannot corroborate demo records for a module whose manifest declares `demo` files, returns
BLOCKED rather than reconciling.

Pick the leaf's model per `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § Model-tier
selection and pass it both as a `DISPATCH MODEL:` line in the brief and as the Agent `model`
parameter. When a module in the leaf's scope has a `business_function` on the specialist list of
`${CLAUDE_PLUGIN_ROOT}/snippets/business-taxonomy.md` (read from its manifest `category`), state the
function in the brief.

The leaf carries the worker brief (`${CLAUDE_PLUGIN_ROOT}/snippets/worker-brief.md`) and appends its
decisions to the worklog (`${CLAUDE_PLUGIN_ROOT}/snippets/worklog-contract.md`).

## Artifacts

All under `<ISOLATE_DIR>/i18n/<slug>-<date>/`:

- `glossary-tm-<lang>.json` - translation memory per target language (P1)
- `<module>.pot` - exported template(s) (P2; shared across all target languages)
- `translation-report-<lang>.json` - per-module diff-review adjudication log (removed/changed/added
  msgids + CORRECT/ARTEFACT/WRONG rulings) for each language. An un-adjudicated entry or a WRONG
  ruling is a BLOCK; an ARTEFACT ruling is neither a block nor residual - it records an identity
  entry that keeps the empty `msgstr` Odoo exported
- `consistency-audit-<lang>.md` - the advisory P5 findings per language

## Continuation Contract

When the run finishes (or returns on an instance BLOCK), append a Continuation
Contract block per `${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced /
next). `produced` lists the artifacts above; a missing instance is `status: NEEDS_CONTEXT` with the
instance requirement as `blocked_reason`, and a standalone invocation where tiers 1-4 leave the
target language unresolved is likewise `status: NEEDS_CONTEXT` with `target language` as
`blocked_reason` (P0 above).
