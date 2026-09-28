<!-- SSOT reference. The single source for the non-destructive Odoo i18n (.pot/.po) recipe.
     Referenced (not copy-pasted) by the odoo-i18n skill AND by odoo-forward-port's P4 i18n step
     via ${CLAUDE_PLUGIN_ROOT}/skills/odoo-i18n/references/i18n-recipe.md. Edit here only.
     Cross-ref: docs/reference/INSTANCE-LIFECYCLE.md, docs/reference/ODOO-TESTING.md -->

# Odoo i18n recipe - non-destructive .pot/.po (SSOT)

Load-bearing belief: **re-exporting a `.po` from a DB that has NOT loaded the existing translation
OVERWRITES it with empty `msgstr`s and silently destroys 40-90% of the human translation** - a clean
exit code on data loss. The non-destructive method: build a FRESH instance, LOAD the existing
`<lang>.po` into it (so its `msgstr`s populate the DB), re-export (the re-export then reproduces the
existing translation, adds new-empty terms, and drops terms gone from code), then RECONCILE by
DIFF-REVIEW - diff the re-export against the committed `.po` and adjudicate every removed/changed
entry into the three buckets of `${CLAUDE_PLUGIN_ROOT}/snippets/po-entry-semantics.md` (CORRECT /
ARTEFACT / WRONG) before commit. No merge library
(no `polib`): the diff is delegated to `git-toolkit:git-ops` and the agent adjudicates the result.

REQUIRES a running Odoo instance with the target module installed - export and validate both need
a live DB + registry. No no-DB workaround (babel/polib cannot walk the module's translatable terms
the way Odoo's registry does). Missing instance is a BLOCK, not a fallback - acquire per
`docs/reference/INSTANCE-LIFECYCLE-BUILD-CONTRACT.md`.

**And not just any instance - the BUILD SHAPE is part of the recipe, not an operator preference.**
The catalog a run can produce is bounded by what that build contains: demo data must be loaded or
every demo-owned term is missing from it (KT4), `en_US` plus every target language must be active or
the exports come back blank (KT1 + KT3), and the `.pot` and every `.po` of the run must come from
that ONE build or the reconcile is comparing different inventories (KT5). A wrongly-shaped build
fails silently with a clean exit code, exactly like the unloaded-language failure above - so it is
checked (Validation gate 6), never assumed.

Export through `instance_i18n_export` on every series - never compose an `odoo-bin` export or
import command: the tool reads which export command line the lease's Odoo checkout declares, and
writes exactly what Odoo's exporter produced. The build it exports from goes through
`instance_build` (L1), which also owns language activation.

`<lang>` below is the target-language placeholder, and `<lang>.po` the file exported for it: the
module's existing `.po` for that language, else the name Odoo's export gives it - so take every path
from the export's `exports` list, never from the code. There is no default target
language: `odoo-i18n` P0 resolves it from explicit input, the machine-global registry, on-disk
`.po` filenames, or the live instance's active languages (the same four tiers) - a run that
resolves none returns `NEEDS_CONTEXT`/escape E3 rather than guessing.

---

## L1 - Build ONE instance, then export every artifact from it

**One build per module per run serves the WHOLE run.** Install the module WITH DEMO DATA (KT4),
activate `en_US` plus every target language in that same build (KT1 + KT3), then export BOTH
artifacts from that one database: the `.pot` template AND each `<lang>.po`. Do not provision a
second, differently-shaped instance for the `.pot` - see KT5 for why that quietly breaks the L2
reconcile.

The build itself goes through the `odoo-instance` skill (the `odoo-i18n` P2 dispatch) as ONE
`instance_build` op `init` on every series: `modules` = the module, `demo` `on` (KT4), `languages` =
every target language (KT1; the tool adds `en_US`, KT3), and skip-auto-install in `extra_args` where
the series' `cli_help` lists it (§ Isolate the term inventory). The tool emits the
language-activation flag and the series' demo flag itself - never compose either, and never activate
a language by any other path. Before exporting, confirm the `INSTANCE_HANDLE` that build's final
`job_wait` returned: its `languages_loaded` lists `en_US` and every target language (a code in
`languages_failed` is not loaded) and its `demo` is `true`. Both are facts of the DATABASE, from
every build on it.

**Export order: the `.pot` FIRST, then each `<lang>.po`**, every one of them from that same build.
Export with ONE `instance_i18n_export` call on that handle's `lease_token`: `modules` = the target
module(s) of that build, never their dependencies; `languages` = every target language (never
`en_US`). The tool enforces the
order and the single database - per module it writes the `.pot`, then one `.po` per language, into
the module's own `i18n/` directory, where Odoo reads them. `job_wait` the job until its `result` is
not `timeout`; its `exports` list names every file written, `.pot` first - use those paths. When
the tool refuses the call or fails the job, follow its remedy. An exported module without its own
demo data, or a requested language not loaded, means the build is wrong: fix the BUILD - never
export from another database to get past it. A module found in more than one addons directory, or
a language with two `.po` files in the module, is the operator's choice: report it, never delete
a copy or a file yourself.

The two artifacts differ only in what they select, never in the build behind them:

- **Template (`.pot`)** - the term INVENTORY with empty `msgstr`s. The export reads the source
  language, so having target languages loaded in the DB does not leak into it; the `.pot` is the same
  file whether or not they are loaded. It comes out ONCE per module per run, with the first export.
- **Translated (`.po`)** - the existing translation re-exported. The language must be LOADED into
  the DB or the export emits empty `msgstr`s (a template, not a translation). One per target
  language, from the SAME database.

**KT1 - a language must be LOADED into the DB by the build; naming it to the export only SELECTS
the file.** Two different steps, both needed for a translated export:

- `--load-language` - the flag `instance_build` emits for its `languages` input - LOADS the
  language INTO the DB so its `msgstr`s become active and exportable. Leave the language out of
  `languages` -> empty `msgstr`s.
- `instance_i18n_export`'s `languages` SELECTS which `.po` files it writes. It loads nothing, which
  is why it refuses a language the database's builds have not proven loaded.

**KT3 - `en_US` MUST ALWAYS be loaded/active alongside every target language.** `en_US` is Odoo's
base/source language; the export baseline and the `-u` reload resolve correctly ONLY when it is
active. Loading ONLY the target language is the #1 operational failure mode. `instance_build`
closes it: it adds `en_US` to every build's `languages` (it emits `--load-language=en_US,<lang>`), so
pass only the target codes and never load a language outside that build. `en_US` is an ACTIVATION
requirement only - it is NEVER a translation deliverable (Odoo ships no `en_US.po`; never ask the
export for one).

**KT4 - the export build MUST carry DEMO DATA. Never disable demo for a translation run.**
A module's translatable terms are not only its code strings. Every record the module OWNS is
exported too - view arch, action and menu names, group names, mail-template subject/body, selection
and field labels - and that includes every record loaded from the manifest's `demo` files. The
exporter reaches those records through `ir_model_data` filtered by MODULE ALONE; there is no demo
predicate and no `noupdate` predicate anywhere on the EXPORT leg (read in every indexed series,
2026-09-02: the `... FROM ir_model_data WHERE module ...` query behind
`_export_translatable_records`, and its `trans_generate` ancestor in the pre-reader series). A
record's terms are in the catalog **if and only if that record is in the database**, so a demo-less
build silently ships a truncated catalog.

That demo terms BELONG in the catalog is checkable rather than argued: Odoo's own committed
`<module>.pot` files carry the terms of records defined only in those modules' `demo` files, in
every indexed series (2026-09-02) - dozens of modules and hundreds of entries per series.
A catalog exported from a demo-less build does not disagree with a preference; it disagrees with
the file Odoo itself ships.

**The missing terms are the smaller half of the damage.** Re-exporting a maintained `<lang>.po`
from a demo-less build DROPS every demo-owned entry the committed file already holds. Those entries
then reach the L2 diff-review as REMOVED while their `msgid`s are plainly still in the module
source - which is precisely the WRONG bucket's test - so a correct run BLOCKS, or, adjudicated
carelessly, real human translation is deleted with a clean exit code. Demo-on is what makes the
re-export and the committed file comparable at all.

Demo loads at `-i` and NEVER at `-u`, so a build that came up without demo cannot be repaired -
provision a new one. Ask for the export build with `demo` `on` (the `odoo-instance` dispatch field,
`instance_build`'s argument): the tool spells the series' own demo flag, whose default and arity
moved across the span (`${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md` § Build facts the
odoo-local tools apply). Never compose a demo flag by hand for the export build.

**KT5 - the `.pot` and every `.po` of one run come from ONE build.** The L2 reconcile compares a
re-export against a committed file and rules each difference; that comparison is only meaningful if
both sides describe the same term inventory. Two builds that differ in ANY inventory-shaping input -
demo on/off, `--skip-auto-install` on/off, a different addons path, a different code state -
manufacture differences that belong to neither the code nor the translation, and the adjudication
has no way to tell them from a real loss. So: install once, activate `en_US` + every target language
once, and export the `.pot` and every `<lang>.po` from that same database before releasing it. If
the build must be replaced mid-run, re-export EVERY artifact from the replacement - never mix
artifacts across builds.

When dispatched from `odoo-forward-port`, copy each source-series `<lang>.po` into the target
module's `i18n/<lang>.po` BEFORE L1 - that makes the source translation the "existing `.po`" L1
loads, so the same fresh-instance -> load -> re-export -> diff-review path forwards it (no polib
lift). L2's diff-review then adjudicates every difference the version gap introduced (a renamed
label, a removed feature). The general re-export-existing-translation case likewise REQUIRES the
load step.

### Isolate the term inventory

Export from a DB where ONLY the target module + its dependency closure is installed, so terms from
auto-installed siblings do not leak into the `.pot`:

- **Where the series' `cli_help` lists `--skip-auto-install`**, pass it in the export build's
  `extra_args`. It is load-bearing: omit it and every `auto_install: True` module whose deps are met
  installs alongside the target, injecting THEIR terms into the registry and polluting the
  `.pot`/`.po` with foreign `msgid`s.
- **Where it does not exist, isolate by DATABASE:** one build per module, installed in dependency
  order, exported from a DB that does NOT contain its children, so a parent's `.pot` carries only
  the parent's terms.

The `.pot` is a TEMPLATE: every `msgid` present, every `msgstr` empty - the inventory of current
translatable terms, NOT a translation. Never commit a `.pot` over a `.po`.

**Always re-export the `.pot` FRESH.** Regenerate `<module>.pot` from the currently-installed code
on EVERY invocation - the L1 export does it - and never reuse a committed or prior-run `.pot` already
on disk. A stale template is missing the run's new/renamed `msgid`s, so the L2 reconcile silently
under-populates and the new terms never reach the translators. This is once-per-module-per-run (a
fresh export each run), NOT per-language - see the multi-language loop below.

## Keep Odoo's export format

After an export, only the content of a `msgstr` may change. Everything else in the file stays
exactly as Odoo wrote it:

- Never rewrap a line, reorder entries, or rewrite the header.
- Never add, remove or edit a comment line (`#.`, `#:`, `#,`).
- Never hand-add a `#. module:` comment or a whole entry. Odoo writes `#. module:` on every entry
  it exports, so an entry without one did not come from the export: fix the source so Odoo extracts
  the term, then re-export.
- When writing a `msgstr` by hand, give it the layout Odoo gives that entry's `msgid`: one line when
  it fits; otherwise `msgstr ""` followed by one quoted segment per line, broken after each `\n`
  and wrapped at the width Odoo used for the `msgid`.

Before hand-translating, copy the file Odoo exported (its `exports` path) to the run's ISOLATE dir;
Validation gate 7 compares against that copy.

---

## Multi-language loop order

When the resolved scope has more than one target language, the BUILD is still singular (KT5) - it is
the exports and the translation work that loop:

- Loop 0 (per module, ONCE): the L1 build - install with demo, activate `en_US` plus EVERY target
  language in that one call. Not per language: activating three languages is one build with three
  codes in the activation set, never three builds.
- Loop 1 (ONCE, from that build): the L1 export - one `instance_i18n_export` call with every target
  language, which writes each module's `.pot` and then every `<lang>.po`. The `.pot` is the
  untranslated catalog and does NOT depend on language - never export it per language, and never
  from a different build than the `.po`s (KT5).
- Loop 2 (per language, module-inner): for each target `<lang>`, and for each module - build the
  per-language glossary/TM (`glossary-tm-<lang>.json`), take the `<lang>.po` Loop 1 exported (its
  language is already active from Loop 0 - do not re-provision to add one), reconcile by
  load + re-export + diff-review (non-destructive, no polib), hand-translate the residual, then run
  the per-language validation gates (diff-review adjudication + placeholder-integrity; `-u` reload
  with `<lang>` loaded). Emit `translation-report-<lang>.json` per language. Each language's `-u`
  reload follows the reserve-only lease guard (see gate-3 above): reuse the L1 install lease
  or use mode `exclusive` on a declared DB - never a fresh ephemeral lease for reload-only. Languages
  looped in parallel share that database:
  `${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md` § One build or export per database.

Artifacts are per-language EXCEPT the shared `.pot`: `<module>.pot` (shared) vs
`<lang>.po` / `glossary-tm-<lang>.json` / `translation-report-<lang>.json` / `consistency-audit-<lang>.md`.

---

## L2 - Diff-review reconcile (the non-destructive core - no polib)

The fresh instance already has the existing `<lang>.po` loaded (L1: the committed file sits in the
module's `i18n/` dir, so the build's language load staged its `msgstr`s into the DB). So the
re-export REPRODUCES the human translation - it is NOT a blind fresh-DB export. Reconcile the
re-exported file against the committed one by DIFF-REVIEW:

1. The committed `<lang>.po` is the diff baseline - it is still at git HEAD; the re-export lands in
   the working tree, so no manual `.orig` copy is needed.
2. The L1 export wrote the re-export over the working-tree `i18n/<lang>.po` (its `exports` path) -
   that file is what this review reads. To start again from Odoo's export, call
   `instance_i18n_export` again on the SAME lease for that module and language; it rewrites the
   module's `.pot` from the same database, so KT5 holds.
3. **Diff-review (delegated - never run git yourself).** Invoke the `git-toolkit:git-ops` skill
   (via the Skill tool) to diff the re-exported `i18n/<lang>.po` against its committed (HEAD) version
   and report the changes back. Per `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`, the git op is
   delegated to git-ops and its result is read back - the skill/agent does not run git itself.
4. **Adjudicate every removed/changed `msgstr`** in the reported diff into one of the THREE
   buckets - CORRECT / ARTEFACT / WRONG - defined once in
   `${CLAUDE_PLUGIN_ROOT}/snippets/po-entry-semantics.md` § Adjudicating a removed or changed entry.
   Read it rather than working from memory: the ARTEFACT test must be applied BEFORE ruling WRONG,
   or every module holding an identity entry blocks a correct run. Only a WRONG ruling
   is a BLOCK - do NOT commit; fix the cause (re-provision fresh, re-load the language, re-export)
   and re-review.
5. Only after every removed/changed entry is ruled CORRECT or ARTEFACT does the re-exported
   `<lang>.po` become the new committed file - and the commit is itself a `git-ops` call (never run
   by a leaf worker).

**ABSOLUTE PROHIBITION:** never blind-overwrite a committed `.po` with a fresh-DB export that had no
load step, and never commit an un-adjudicated re-export. Load-first + diff-review + adjudication IS
the non-destructive contract; skipping it erases the human translation.

---

## L3 - Hand-translate the residual

After L2, translate every entry left with an empty `msgstr` by the rule in
`${CLAUDE_PLUGIN_ROOT}/snippets/po-entry-semantics.md` § An empty `msgstr`: an entry whose correct
translation is identical to its `msgid` stays EMPTY and is NOT residual; every other one gets its
translation written. Never write the `msgid` into a `msgstr`.

Choose the words by the term policy (`${CLAUDE_PLUGIN_ROOT}/snippets/translation-term-policy.md`)
and write each `msgstr` in Odoo's layout (§ Keep Odoo's export format). Check the placeholder set
and the `fuzzy` flag per entry as you write it (no full-file polib scan) - both rules live in
`po-entry-semantics.md` § Fuzzy and placeholders.

---

## Validation before commit (every gate is a hard BLOCK on failure)

1. **Diff-review adjudication (delegated to git-ops, NOT a raw local diff you run).** Invoke
   `git-toolkit:git-ops` to diff the re-exported `<lang>.po` against its committed version; every
   removed/changed `msgid` in the reported diff MUST carry one of the three rulings from
   `${CLAUDE_PLUGIN_ROOT}/snippets/po-entry-semantics.md` § Adjudicating a removed or changed entry.
   An un-adjudicated entry, or one ruled WRONG, is a hard BLOCK - the human translation was lost by
   accident (usually the language was not loaded into the DB before the re-export). An ARTEFACT
   ruling is NOT a block and NOT residual: the entry keeps the empty `msgstr` Odoo exported. The
   skill/agent never runs git itself - it delegates to git-ops and reads the result.

2. **Placeholder integrity (per entry, no polib).** Every entry translated in L3 must satisfy the
   placeholder rule in `${CLAUDE_PLUGIN_ROOT}/snippets/po-entry-semantics.md` § Fuzzy and
   placeholders; a mismatch makes the translation raise or render wrong at runtime - BLOCK. Check
   each entry as you write it (a `re`-based spot-check on that entry is fine); reproduced entries
   from the diff baseline were already correct and need no full-file re-scan.

3. **Load validation via Odoo, NOT msgfmt.** Reload the module on the export build's database:
   `instance_build` (op `update`, the `INSTANCE_HANDLE`'s `lease_token`, `modules` [<module>]) ->
   `job_wait` until `result` is not `timeout` (the tool applies the memory cap and the build facts;
   see `docs/reference/INSTANCE-LIFECYCLE.md` § `-i` vs `-u` semantics). `-u` re-imports the translation
   and surfaces a broken `.po` (duplicate `msgid`, bad header, format error) that `msgfmt` misses -
   `msgfmt` validates gettext syntax only, not Odoo's import path. Pass signal: clean `-u` reload,
   no translation error in the log.

   **Pre-condition - target language must be active in the DB (KT1).** Before `-u`, confirm the
   export build's `INSTANCE_HANDLE` lists the target language in `languages_loaded` (it was in that
   build's `languages` - see L1). Absent language -> reload succeeds silently but translations do not
   load at runtime - false pass. **`en_US` must ALSO be active (KT3).** Confirm BOTH `en_US` (the
   base/source language) and each `<lang>` are in `languages_loaded` before the reload - not the
   target language alone. A language missing there means the export build is wrong: rebuild it with
   that language (KT5 - then re-export every artifact), never load it separately.

   **Reserve-only lease guard.** Reuse the SAME instance and lease the L1 `-i` install used -
   the `-u` reload requires the DB to ALREADY EXIST with the module installed. A `lease_acquire`
   in mode `ephemeral` only reserves a unique DB name and ports; the DB is created by the L1 `-i`
   run via Odoo create-on-init, not by the lease. Do NOT acquire a fresh ephemeral lease for the
   reload - its DB is uncreated and `-u` will fail. Keep the L1 lease, or use mode `exclusive` on a
   declared DB that already has the module installed.

4. **Export against the adapted code (PR-head / merged tree).** When odoo-i18n is dispatched from a
   forward-port or upgrade run, the Odoo instance must run the POST-ADAPT code - the worktree the adapt
   wrote - NOT the source/original branch and NOT the principal checkout. Exporting from pre-adapt code
   yields a `.pot` with the old term inventory, missing new/renamed strings introduced in the port.
   **Mechanism (this is not advice - without it L2 silently under-merges):** pass `WORKTREE_PATH` to
   `odoo-instance`, which re-roots the instance's addons list onto that worktree
   (its own WORKTREE_PATH substitution -> `lease_acquire` with `addons_path` naming that tree). An
   instance whose addons path points at the
   principal checkout makes a worktree-only `msgid` surface as NEITHER a removed nor a changed entry,
   so the L2 adjudication loop has nothing to rule on and the loss is committed unseen. Before the L1
   export, apply `${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md` § Addons coverage
   assertion; on a miss, BLOCK - do not export.

5. **`.pot` freshness (always re-export) + `en_US` active.** The `.pot` merged in L2 MUST be the one
   this run exported from the currently-installed code - a committed or prior-run `<module>.pot` on
   disk is never sufficient by itself; re-export unconditionally every invocation (once per module,
   not per language). AND `en_US` must be in the export build's `languages_loaded` beside every target
   language (KT3), never the target language alone. Skipping either is a silent under-merge / false pass -
   BLOCK.

6. **Build shape - demo loaded, and ONE build behind every artifact (KT4 + KT5).** Confirm, before
   trusting any exported file, that the build these artifacts came from was installed WITH demo data
   and that the `.pot` and every `<lang>.po` of this run came from THAT SAME database. Both are
   decidable from what you already have, so neither is a judgement call:

   - **Demo:** the build's `INSTANCE_HANDLE` reads `demo: true` - a fact of the database, which
     `instance_i18n_export` also checks before it writes anything
     (`${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md` § Build facts the odoo-local tools
     apply). Corroborate against the instance rather than the handle alone - a module in
     scope whose manifest declares `demo` files must have its demo records present
     (`ir.model.data` rows for that module pointing at records those files define). Absent -> the
     catalog is truncated: BLOCK and re-provision. Demo loads only at `-i`, so there is no repair
     short of a new build.
   - **One build:** the `.pot` and every `.po` came from `instance_i18n_export` jobs on the same
     `INSTANCE_HANDLE`'s lease (the L1 export, or a restart on that lease). A mismatch
     means the reconcile compared two different term inventories and its rulings are void -
     re-export every artifact from one build and re-adjudicate.

   A demo-less or mixed-build run is exactly the shape that produces a mass of REMOVED entries whose
   `msgid`s are still in source, so it is ALSO the shape most likely to be mis-ruled WRONG and
   "fixed" by deleting real translation. Check the build before you trust the diff.

7. **Export format intact (§ Keep Odoo's export format).** Compare each finished `.po` with the copy
   of the file Odoo exported (a plain file diff, not git): every differing line must lie inside a
   `msgstr`. A changed header, comment, wrap or entry order - or an added entry - is a BLOCK: restart
   from Odoo's export and re-apply only the `msgstr` content.

---

## Glossary and term choice

Which WORDS to use - the three glossary layers and their precedence (TM from core + deps, the
project `glossary.yml`, the OSM canonical `field.string`), plus the independent-regime guard - is
owned by `${CLAUDE_PLUGIN_ROOT}/snippets/translation-term-policy.md`. Consult it when building the
TM (P1) and when hand-translating the residual (L3). It is not restated here.
