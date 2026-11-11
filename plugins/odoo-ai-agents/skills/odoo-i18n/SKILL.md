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
diff-review plus an Odoo `-u` reload is. Full recipe: `references/i18n-recipe.md`.

**Sole dispatcher.** Only this skill launches the `odoo-translator` agent. A caller needing a module translated, a `.pot`/`.po` exported/merged, or terminology audited
invokes this skill via the Skill tool. A live instance is provisioned by invoking the `odoo-instance` skill
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
- Reviewing translation code or a `.po` diff -> use `odoo-code-review`
- Writing the production code whose strings are translated later -> use `odoo-coding`

## MCP tools

<!-- BEGIN GENERATED TOOLS -->
- `set_active_version` ☆ - Pin a CONCRETE Odoo version (sentinels like 'auto' are rejected; the call doubles as a cheap reachability probe; 24h idle TTL).
- `cli_help` - Look up odoo-bin subcommand flags, their status, and replacement for deprecated flags.
- `entity_lookup` ★ - Single-entity drill-down by kind discriminator: model, field, method, view, module, pattern, or report - with full inheritance chain and source module.
<!-- END GENERATED TOOLS -->

## Standalone-first fallback

i18n REQUIRES a running Odoo instance with the target module installed. Never translate without one (no babel, no raw PO parser). When no instance is available, BLOCK with status `NEEDS_CONTEXT`
(Continuation Contract `blocked_reason`) and do not export partially. Acquire an instance by invoking
the `odoo-instance` skill per `docs/reference/INSTANCE-LIFECYCLE.md` § Decision tree, and resume at P2.

## The 6-phase pipeline

Run phases in order. Each phase names its model tier; fan-out follows
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` (Mode B). Artifacts land under the
Tier-2 ISOLATE dir, resolved per `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md` (shown as
`<ISOLATE_DIR>`): `<ISOLATE_DIR>/i18n/<slug>-<date>/`. Full recipe: `references/i18n-recipe.md`.

**Orphan sweep (every run, BEFORE P0).** Run:

`find <ISOLATE_DIR>/i18n/ -mindepth 1 -maxdepth 1 -type d -mmin +43200 -exec rm -rf {} +`

Rule: `${CLAUDE_PLUGIN_ROOT}/snippets/visual-evidence-lifecycle-contract.md` Clause 3.

**P0 - Scope [haiku].** Resolve the target language list by the 4-tier precedence and echo the source tier used (tiers and rules: `references/i18n-phase-detail.md` § P0 language resolution). There is NO tier 5: `en_US` is never a target or a stand-in. All tiers empty -> `NEEDS_CONTEXT` (`target language`) standalone, or when mandated record `i18n: not-applicable (no target language resolvable from tiers 1-4)` (escape E3), return it verbatim and translate nothing. `en_US` is always added: `activation_languages = {"en_US"} union target_languages` (DB activation only, no `en_US.po`). Echo the resolved list, the `activation_languages` set and the tier in the scope summary.

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
never bundle languages in a leaf. Each leaf adjudicates the L2 diff and hand-translates the L3
residual for its language. The diff is yours to obtain: a leaf runs no git and invokes no git-ops,
so before each launch invoke `git-toolkit:git-ops` for the changes of the re-exported `<lang>.po`
against its committed version and put the reported changes (or the path of the file holding them)
in the brief; after a leaf re-exports, obtain the diff again and resume the leaf with it. The leaves, and your own P4 reloads, share ONE
database: they follow `${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md` § One build or
export per database. Loop order: `## Multi-language loop order` in `references/i18n-recipe.md`.
Model and brief: dispatch contract below.

**P4 - Validate [haiku].** After all P3 leaves finish, run all validation gates (recipe § Validation) for EACH target language independently, as a second pass over each leaf's Round 4 self-check: the git-ops diff-review adjudication on `<lang>.po` (BLOCK on any un-adjudicated or WRONG-ruled loss), per-entry placeholder integrity, gate 6 (build shape: demo on, `.pot` plus every `.po` from that ONE build - on a mismatch re-export and re-adjudicate), gate 7 (export format: only `msgstr` content differs), gate 5 (the `.pot` was re-exported THIS run), and the Odoo `-u <module>` reload (NOT `msgfmt`). Pre-condition: `en_US` (KT3) and each `<lang>` are in the export build's `languages_loaded`. A clean reload with no translation error in the log is the pass signal. Reload semantics: `docs/reference/INSTANCE-LIFECYCLE.md` § `-i` vs `-u` semantics. Each reload runs against the SAME lease as the P2 `-i` install (Odoo create-on-init, or mode `exclusive` on a declared DB with the module pre-installed) - never a fresh `ephemeral` lease.

**[MANDATORY after the last P4 reload]** release or park the lease you provisioned; `HAND_ON: <skill>` and a forwarded handle are exceptions - `references/i18n-phase-detail.md` § Release the export instance.

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

Also carry the P2 build (`INSTANCE_HANDLE`, `BUILD_SHAPE`), the launch `model` and `effort`, and any specialist `business_function`: `references/i18n-phase-detail.md` § Dispatch brief extras.

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
