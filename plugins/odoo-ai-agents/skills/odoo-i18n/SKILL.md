---
name: odoo-i18n
argument-hint: "[module(s)] [target-lang e.g. vi_VN]"
description: >-
  This skill should be used when the user asks to translate one or more Odoo modules into any
  target language (default vi_VN), export .pot/.po, update translations, sync terminology, or
  audit cross-module term consistency. Fire on "translate this module", "export .pot / .po",
  "update the translation", "sync terminology", "đồng bộ thuật ngữ", "dịch module Odoo",
  "xuất .pot/.po", "cập nhật bản dịch", or any i18n / terminology-consistency ask for Odoo.
  Front door for ALL Odoo translation work and the ONLY dispatcher of the odoo-translator agent;
  also the i18n step other workflows dispatch into (forward-port, new module, bugfix). Non-destructive contract is load-bearing: re-exporting a
  .po from a fresh DB destroys 40-90% of existing msgstr, so translation MEMORY is always
  forwarded by merge, never regenerated. Requires a running Odoo instance; missing instance is a
  BLOCK. Route a one-line UI label fix to odoo-coding; a rendered-UI language check to odoo-ui-review
---

## Role

i18n conductor for Odoo translation. Owns the `.pot`/`.po` lifecycle, the glossary, and the
subagent lifecycle for translating a module or module scope onto a target Odoo series. Makes the
orchestration decisions (phase model tier, when to stop for a human, when to dispatch the leaf
translator) and delegates actual term translation to the `odoo-translator` agent.

The load-bearing belief: a translation is MEMORY to be forwarded, never regenerated. Re-exporting a
`.po` from a database that has NOT loaded the existing translation overwrites it with empty
`msgstr`s and silently destroys 40-90% of the human translation with a clean exit code. The
non-destructive method: build a FRESH instance, LOAD the existing `.po` into it, re-export (which
then reproduces the translation), then RECONCILE by a git-ops diff-review - adjudicate every
removed/changed entry as correct or wrong before commit (no `polib`). A clean export + a green
install is NOT proof the translation survived; only an adjudicated diff-review plus an Odoo `-u`
reload proves it. Full non-destructive recipe (3-layer L1/L2/L3 +
validation + glossary): `references/i18n-recipe.md` - the SSOT this skill and `odoo-forward-port`
both point at.

**Sole dispatcher (single source of truth for i18n fan-out).** This skill is the ONLY component
that launches the `odoo-translator` agent. Any other skill that needs a module translated, a
`.pot`/`.po` exported/merged, or cross-module terminology audited routes that work HERE via the
Skill tool instead of spawning the agent itself, so the non-destructive merge contract and the
per-language leaf scoping (P1-P5) are enforced in one place. A live instance is provisioned by
invoking the `odoo-instance` skill (never the raw `odoo-instance-ops` agent).

**`WORKTREE_PATH` is required whenever this skill runs.** `.po` / `.pot` files are git-tracked, so per
`${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md` field 5 the write happens in a dedicated worktree -
never the principal checkout. A caller (forward-port, modules-upgrade, a run-harness node) passes
`WORKTREE_PATH:`; you forward it verbatim to every `odoo-translator` leaf. Invoked with no
`WORKTREE_PATH` and no worktree of your own -> provision one via `git-toolkit:git-ops` before P2, per
`${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`. The verification instance must load THAT tree, not
the principal checkout: pass `WORKTREE_PATH` through to `odoo-instance`
(`${CLAUDE_PLUGIN_ROOT}/skills/odoo-instance/SKILL.md` § WORKTREE_PATH substitution) so the export
reads the code you are translating.

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
> Look-live-but-static tools (return indexed source, never runtime data): `model_inspect`, `module_inspect`, `entity_lookup`, `validate_domain`, `validate_depends`, `validate_relation`. These tool names look like they query a live instance but return indexed source data only. If you need live records, Odoo Semantic is the wrong server.

**Session bootstrap** (call once at session start):
- `set_active_version(odoo_version='17.0')` - Pin a CONCRETE Odoo version (sentinels like 'auto' are rejected; the call doubles as a cheap reachability probe; 24h idle TTL).

**Primary tools:**
- `cli_help` - Look up odoo-bin subcommand flags, their status, and replacement for deprecated flags.
- `entity_lookup` ★ - Single-entity drill-down by ID: field, method, or view with full inheritance chain and source module.
<!-- END GENERATED TOOLS -->

## Standalone-first fallback

i18n REQUIRES a running Odoo instance with the target module installed. Export (`--i18n-export`)
walks the live registry to enumerate translatable terms, and validation reloads the module against a
real DB - both need an instance. There is NO no-DB workaround: babel or a raw PO parser alone cannot discover a
module's translatable terms the way Odoo's registry does, so every "translate without an instance"
path produces an INCOMPLETE or WRONG result and must be refused.

When no instance is available, BLOCK with status `NEEDS_CONTEXT` (Continuation Contract
`blocked_reason`); do not improvise a partial export. Acquire an instance by invoking the `odoo-instance` skill
(never the raw `odoo-instance-ops` agent) per
`docs/reference/INSTANCE-LIFECYCLE.md` (allocator/lifecycle decision tree) and resume at P2.
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
under the Tier-2 ISOLATE dir; resolve it via the resolve-capture-substitute protocol in
`${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md` (captured path shown as `<ISOLATE_DIR>`
below) - `<ISOLATE_DIR>/i18n/<slug>-<date>/`. The full non-destructive recipe (every command, the
diff-review reconcile, the validation gates, the glossary) lives in `references/i18n-recipe.md`.

**Orphan sweep (do this every run, BEFORE P0 below).** `i18n/<slug>-<date>/` is never deleted by
anything today, so it leaks one directory per run forever - on top of the recipe's own mandate
that a prior run's artifacts are never reused, making anything past the very next run already
dead weight:

`find <ISOLATE_DIR>/i18n/ -mindepth 1 -maxdepth 1 -type d -mmin +43200 -exec rm -rf {} +`

(any sibling `<slug>-<date>/` dir untouched for over 30 days is presumed consumed). Full
rule + bound rationale: `${CLAUDE_PLUGIN_ROOT}/snippets/visual-evidence-lifecycle-contract.md`
Clause 3. Enforcer: whoever executes `odoo-i18n` next, unconditionally, every run.

**P0 - Scope gate [sonnet, STOP].** Resolve the target language list by precedence (highest first),
then echo which source was used:

1. Explicit languages in the request/args.
2. Machine-global registry: read `${ODOO_AI_HOME:-$HOME/.odoo-ai}/i18n.json` and use its
   `default_languages` array if present and non-empty.
3. Infer from existing `<lang>.po` filenames in each module's `i18n/` directory
   (`<module>/i18n/<lang>.po`); skip this tier when no `i18n/` dir exists.
4. Query the confirmed instance: `res.lang` records with `active = True` (codes).
5. Default `["vi_VN"]` - **standalone invocations ONLY.**

**Inside a MANDATED invocation, tier 5 is unreachable.** When a caller dispatches this skill as a
required step of its own pipeline (`${CLAUDE_PLUGIN_ROOT}/snippets/i18n-mandate-contract.md`), it
SHOULD pass explicit `TARGET LANGUAGES` whenever it already has one - but when it has none to give,
tiers 2-4 above still run, against whatever IS available, before giving up (the caller's silence on
this field is never a licence for THIS P0 to skip straight past them). Reaching tier 5 is NOT a
licence to default either: once ALL FOUR tiers are empty, record
`i18n: not-applicable (no target language resolvable from tiers 1-4)`, return that verbatim to the
caller, and translate nothing. A public, global plugin must never generate Vietnamese catalogs for a
user who did not ask for them.

**`en_US` is mandatory, independent of the tiers above.** After resolving the target languages, set
`activation_languages = {"en_US"} union target_languages`. `en_US` (Odoo's base/source language) is
ALWAYS loaded into the DB alongside every target language (recipe KT3) - none of the tiers above can
produce it (Odoo ships no `en_US.po`), so it MUST be added here. This governs the DB-activation set
passed to every `--load-language`/`loadlang` call ONLY; it does NOT add `en_US` as a translation
deliverable (no `en_US.po` is exported or merged).

Echo the resolved language list (target languages + the `activation_languages` set) AND the source tier
that produced it in the scope summary.

Also in P0: confirm an instance is available (else BLOCK per `## Standalone-first fallback`). Resolve
each module name to its directory and dependency closure. Emit a one-line scope summary (modules x
target_languages x series + dependency order + language-source tier).

**Then gate - and WHERE the gate lives depends on how you were invoked:**

- **Standalone** (a human asked for a translation directly, not as a dispatched pipeline step) ->
  STOP for approval in a single turn before any export or DB op, as before.
- **Mandated** (a caller dispatched you as a required step) -> do NOT stop, period - a human stop per
  invocation, per BATCH in forward-port's P5->P10 loop, turns a mandatory step into a deadlock. What
  makes a dispatch Mandated is `WORKTREE_PATH` AND (an `INSTANCE_HANDLE` or
  `SELF_PROVISION: worktree-addons`) - the two inputs the caller can never omit
  (`${CLAUDE_PLUGIN_ROOT}/snippets/i18n-mandate-contract.md` obligations 1-2). Missing either one is a
  caller-contract violation, not a language problem: RETURN `status: BLOCKED`
  (`i18n: blocked (missing <field>)`, the same E5/E6 shape) to the caller's OWN gate - never open a
  fresh interactive STOP for it either. `TARGET LANGUAGES` is best-effort, never gating: when the
  caller supplies it, tier 1 resolves immediately; when the caller has none to give, this P0 still
  runs tiers 2-4 itself (registry / `.po`-filename inference / live instance query) against whatever
  IS available - an empty `TARGET LANGUAGES` field is never a shortcut past those tiers. Only once
  tiers 1-4 are ALL empty does tier 5 become reachable in principle, and inside a mandate that
  reachability is capped at escape E3, never the standalone-only fallback two paragraphs above: RECORD
  `i18n: not-applicable (no target language resolvable from tiers 1-4)`, RETURN it, and PROCEED -
  translate nothing, but never stop for it. RETURN the scope summary (or the E3/BLOCKED record) to the
  caller, which presents it at its OWN existing gate alongside its other verdicts (precedent:
  `${CLAUDE_PLUGIN_ROOT}/skills/odoo-modules-upgrade/SKILL.md` § P5.8/P6, where the acceptance verdict
  is presented "ALONGSIDE the P6 sign-off ... so the human sees ONE combined decision").

**P1 - Glossary build [haiku or sonnet].** Assemble the translation memory the later phases reuse:
read the already-translated `<lang>.po` of core Odoo and the module's dependency modules, load the
project `glossary.yml` (domain/regulatory terms + their source citation) - Tier-2 SHARE, resolved
via the same `state-root-resolution.md` protocol (captured path shown as `<SHARE_DIR>` below):
`<SHARE_DIR>/glossary.yml` - and for any
field-mapped term confirm the canonical label via OSM (see the glossary layer in the recipe). Build
the TM **per language** (one independent memory per language, covering all in-scope modules). Write
each assembled TM to `<ISOLATE_DIR>/i18n/<slug>-<date>/glossary-tm-<lang>.json` (one file per target
language). Do NOT share or merge TM across languages. Sonnet when the scope spans domain/regulatory
terminology; haiku for a plain module.

**P2 - Export `.pot` template [sonnet].** Per L1 of the recipe: install the module, then export a
`.pot` TEMPLATE on a clean per-module install in an isolated DB, in dependency order (a `.pot`
template needs NO language load - the L1 load step applies only to a translated `.po` re-export).
Never export over a maintained `.po`. ALWAYS re-export the `.pot` FRESH from the
currently-installed code on every invocation - never reuse a committed or prior-run `.pot` already
on disk (a stale template misses the run's new/renamed terms and silently under-merges; recipe
gate 5). The `.pot` is language-agnostic (shared
across all target languages - one FRESH export per module per run, not per language). The per-version flags and
their rationale - `--load-language` (activate in DB) vs `--language`/`-l` (select export file),
`--skip-auto-install` v17-v18, one fresh DB per module v8-v16, the `odoo-bin i18n` subcommand
v19+ - live in the recipe; ground the exact form via `cli_help` above (`command='i18n-export'`
v8-v18, `command='i18n'` v19+).

**P3 - Translate [dispatch `odoo-translator`].** Dispatch the `odoo-translator` agent as a
subagent launch for EACH (module-cluster × language) pair - the Cartesian product of module
clusters and target languages. Each leaf carries exactly ONE language; never bundle multiple
languages in a single leaf. Each leaf runs the L2 re-export + diff-review reconcile and L3 hand-translation of the
residual for its specific language. Loop order: see `## Multi-language loop order` in
`references/i18n-recipe.md` (`.pot` exported once per module, `.po`/glossary/validate per-lang).
See the dispatch contract below for the model and brief.

**P4 - Validate [haiku].** Run all validation gates (recipe § Validation) for EACH target language independently. P4 is the
orchestrator-level gate run after all P3 leaves finish - a second, independent pass over each
leaf's own Round 4 self-check, not a replacement for it. Per language:
run the git-ops diff-review adjudication on `<lang>.po` (BLOCK on any un-adjudicated or WRONG-ruled
loss - that means an overwrite slipped through without the load step), the per-entry placeholder-integrity check,
and the Odoo `-u <module>` reload (NOT `msgfmt`). Pre-condition for each language's reload: the
target language must be LOADED in the DB first (`--load-language=<lang>` v8-v18 / `i18n loadlang
-l <lang>` v19+); an absent language makes the reload pass silently while translations stay inactive
- a false pass. `en_US` (the base language) MUST be active too (KT3) - confirm BOTH `en_US` and each
`<lang>`, never the target language alone. Also verify the `.pot` consumed was re-exported THIS run
(recipe gate 5), not a stale on-disk template. A clean reload with no translation error in the log is the pass signal per language.
See `docs/reference/INSTANCE-LIFECYCLE.md` for the reload semantics. Each per-language `-u
<module>` reload must run against the SAME lease as the P2/L1 `-i` install that created the DB
via Odoo create-on-init, or `--mode exclusive` on a declared DB with the module pre-installed -
never a fresh `ephemeral` lease (reserve-only = uncreated DB, `-u` will fail).

**P5 - Consistency audit + report [sonnet default; opus ONLY when the in-scope terminology is domain/legal/regulatory (e.g. accounting circulars) - never for module or language count alone; ADVISORY].** Audit terminology consistency across the
translated modules for EACH target language separately. This phase is **ADVISORY and NEVER
blocking**: it surfaces inconsistencies for a human to decide on, but it does NOT auto-edit or
auto-dedup. Critically, legally independent regimes (e.g. the Vietnam accounting circulars TT200 /
TT133 / TT99) MUST NOT be deduped even when their `msgid`s match - each regime's translation stays
complete and self-standing, and an incidental string match is never a reason to share or rewrite a
translation across regimes. Write findings per language to
`<ISOLATE_DIR>/i18n/<slug>-<date>/consistency-audit-<lang>.md` (one file per target language).

## Dispatch contract -> odoo-translator

When composing the dispatch prompt for any specialist agent you dispatch, fill the caller-side
skeleton in `${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md` (read it by path) plus the target
agent's family delta; never inline that file verbatim into a hard-leaf brief.

P3 dispatches the `odoo-translator` agent as a subagent launch - one leaf per (module-cluster ×
language) pair. Each leaf is scoped to exactly ONE language. Carry a brief with: `WORKTREE_PATH` (the
absolute worktree the `.po`/`.pot` writes land in - MANDATORY, per
`${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md` field 5, because the leaf is a separate agent
context that does NOT inherit your cwd); the target module(s), the single target language, series; the
glossary TM path for that language (`glossary-tm-<lang>.json`) from P1; the maintained `<lang>.po` and
fresh `<module>.pot` paths; and the validation gates the leaf must self-check. Pass the model both as a
`DISPATCH MODEL:` line in the brief and as the Agent `model` parameter:

- **sonnet** (default) for a plain module translation.
- **opus** when the scope carries domain / legal / regulatory terminology (e.g. accounting
  circulars, statutory report labels) where a wrong term has compliance cost.

The leaf carries the worker brief (`${CLAUDE_PLUGIN_ROOT}/snippets/worker-brief.md`) and appends its
decisions to the worklog (`${CLAUDE_PLUGIN_ROOT}/snippets/worklog-contract.md`). It does the
re-export + translation directly - there is no OSM i18n tool, so it uses shell `odoo-bin` (the
git-ops diff-review + commit stay with the skill, never the leaf), and uses OSM only to confirm
canonical field labels, e.g.:

```
entity_lookup(kind='field', model='account.move', field='amount_total', odoo_version='<target>')
```

**`.po`/`.pot` file format constraint (authoring and hand-editing):** Every message entry in a
`.po` or `.pot` file MUST carry a `#. module: <technical_name>` extractor comment on the line
immediately before the `#: <file>:<line>` location reference. A hand-written or hand-patched entry
missing this comment causes `translate.py` to crash at module load and Runbot misattributes the
failure to a later module. Odoo's `--i18n-export` generates this comment automatically; the
re-export preserves it, and it must be added manually when entries are written by hand.

## Artifacts

All under `<ISOLATE_DIR>/i18n/<slug>-<date>/`:

- `glossary-tm-<lang>.json` - assembled translation memory per target language (P1; one file per
  language; TM of one language is never shared with another)
- `<module>.pot` - exported template(s) (P2; language-agnostic, shared across all target languages)
- `translation-report-<lang>.json` - per-module diff-review adjudication log (removed/changed/added
  msgids + correct/wrong rulings) for each language (an un-adjudicated or WRONG-ruled loss is a BLOCK)
- `consistency-audit-<lang>.md` - the advisory P5 findings per language

## Continuation Contract

When the run finishes (or pauses at the P0 gate or an instance BLOCK), append a Continuation
Contract block per `${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced /
next). `produced` lists the artifacts above; a missing instance is `status: NEEDS_CONTEXT` with the
instance requirement as `blocked_reason`. Additive output for the run-harness - it does not change
anything produced above.
