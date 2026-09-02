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

Ground every odoo-bin flag for the target series before invoking - the EXPORT/IMPORT surface
is the half that moved off the server flags onto an `i18n` subcommand; the language-ACTIVATION
flag did not move. Resolve each one, never assume from the series:

```
cli_help(command='i18n-export', odoo_version='<target>')            # export: server flag, where it still exists
cli_help(command='i18n', odoo_version='<target>')                   # export/import/loadlang subcommand, where it exists
cli_help(command='server', flag='--load-language', odoo_version='<target>')  # activation
```

Examples below use `<lang>` as the target-language placeholder. There is no default target
language: `odoo-i18n` P0 resolves it from explicit input, the machine-global registry, on-disk
`.po` filenames, or the live instance's active languages (`skills/odoo-i18n/SKILL.md` P0
tiers 1-4) - a run that resolves none returns `NEEDS_CONTEXT`/escape E3 rather than guessing.

---

## L1 - Build ONE instance, then export every artifact from it

**One build per module per run serves the WHOLE run.** Install the module WITH DEMO DATA (KT4),
activate `en_US` plus every target language in that same build (KT1 + KT3), then export BOTH
artifacts from that one database: the `.pot` template AND each `<lang>.po`. Do not provision a
second, differently-shaped instance for the `.pot` - see KT5 for why that quietly breaks the L2
reconcile.

The two exports differ only in the flag that selects the output, never in the build behind them:

- **Template (`.pot`)** - the term INVENTORY with empty `msgstr`s. The export reads the source
  language, so having target languages loaded in the DB does not leak into it (the reader falls back
  to `en_US` when no language is selected); the `.pot` is the same file whether or not they are
  loaded. Export it ONCE per module per run.
- **Translated (`.po`)** - the existing translation re-exported. The language must be LOADED into
  the DB or the export emits empty `msgstr`s (a template, not a translation). Export one per target
  language from the SAME database.

**KT1 - `--load-language` ACTIVATES the translation in the DB; `--language`/`-l` only SELECTS the
export file.** Two different flags, both needed for a translated export:

- `--load-language=<lang>` - or the `odoo-bin i18n loadlang -l <lang>` subcommand form where
  `cli_help` reports it - LOADS the language
  INTO the DB so its `msgstr`s become active and exportable. Omit it -> empty `msgstr`s.
- `--language=<lang>` (export flag, v8-v18) / `-l <lang>` (`i18n export`, v19+) SELECTS which
  language the export file targets. Does NOT load the translation; without the load step it emits
  an empty-`msgstr` file.

**KT3 - `en_US` MUST ALWAYS be loaded/active alongside every target language.** `en_US` is Odoo's
base/source language; the export baseline and the `-u` reload resolve correctly ONLY when it is
active. Loading ONLY the target language (e.g. `--load-language=vi_VN`) is the #1 operational
failure mode - ALWAYS include `en_US` in the activation set: `--load-language=en_US,<lang>`, or a
preceding `odoo-bin i18n loadlang -d <db> -l en_US` call in the subcommand form. `en_US` is an ACTIVATION
requirement only - it is NEVER a translation deliverable (Odoo ships no `en_US.po`; do not export
one).

**KT4 - the export build MUST carry DEMO DATA. Never disable demo for a translation run.**
A module's translatable terms are not only its code strings. Every record the module OWNS is
exported too - view arch, action and menu names, group names, mail-template subject/body, selection
and field labels - and that includes every record loaded from the manifest's `demo` files. The
exporter reaches those records through `ir_model_data` filtered by MODULE ALONE; there is no demo
predicate and no `noupdate` predicate anywhere on the EXPORT leg (read in every series v8 through
v19, 2026-09-02: the `... FROM ir_model_data WHERE module ...` query behind
`_export_translatable_records`, and its `trans_generate` ancestor in the pre-reader series). A
record's terms are in the catalog **if and only if that record is in the database**, so a demo-less
build silently ships a truncated catalog.

That demo terms BELONG in the catalog is checkable rather than argued: Odoo's own committed
`<module>.pot` files carry the terms of records defined only in those modules' `demo` files, in
every series v8 through v19 (2026-09-02) - dozens of modules and hundreds of entries per series.
A catalog exported from a demo-less build does not disagree with a preference; it disagrees with
the file Odoo itself ships.

**The missing terms are the smaller half of the damage.** Re-exporting a maintained `<lang>.po`
from a demo-less build DROPS every demo-owned entry the committed file already holds. Those entries
then reach the L2 diff-review as REMOVED while their `msgid`s are plainly still in the module
source - which is precisely the WRONG bucket's test - so a correct run BLOCKS, or, adjudicated
carelessly, real human translation is deleted with a clean exit code. Demo-on is what makes the
re-export and the committed file comparable at all.

Demo loads at `-i` and NEVER at `-u`, so a build that came up without demo cannot be repaired -
provision a new one. Resolve the era's flag instead of carrying one forward; the arity and the
default both moved (SSOT: `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md` § CLI - demo
flag): in the earlier era demo is ON by default, so pass NO demo flag at all; in the later one it is
OFF by default, so `--with-demo` must be passed explicitly - the SSOT row above names the boundary,
and `cli_help(command='server', flag='--with-demo', odoo_version='<target>')` confirms it for the
series in hand. Never pass `--without-demo` in any form on a translation run, and never
`--without-demo=False`, a truthy string that disables the demo data you need.

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

Export from a DB where ONLY the target module + its dependency closure is installed, so terms from
auto-installed siblings do not leak into the `.pot`.

### v8-v16 (no `--skip-auto-install`; server flags; isolate by DATABASE)

One fresh DB per module, installed in dependency order, exported from a DB that does NOT contain
its children, so a parent's `.pot` carries only the parent's terms.

```bash
# Memory-cap policy: ${CLAUDE_PLUGIN_ROOT}/snippets/odoo-bin-resource-limits.md
[ -z "${ODOO_AI_LIMIT_MEMORY_HARD-4294967296}" ] || [ "${ODOO_AI_LIMIT_MEMORY_HARD-4294967296}" = "0" ] || ulimit -Sv "$(( ${ODOO_AI_LIMIT_MEMORY_HARD-4294967296} / 1024 ))" 2>/dev/null || true
# ONE build (KT5): install + demo + activate en_US (KT3 - ALWAYS) and EVERY target language,
# into an isolated per-module DB, in dependency order.
# NO demo flag here: demo is ON by default on these series (KT4) - passing --without-demo in any
# form truncates the catalog, and --without-demo=False truncates it too (the string is truthy).
odoo-bin -d <db> -i <module> --load-language=en_US,<lang1>[,<lang2>...] \
  --stop-after-init \
  --limit-memory-hard=${ODOO_AI_LIMIT_MEMORY_HARD:-4294967296}
# export the .pot TEMPLATE from that same DB (no --language: the inventory, empty msgstrs):
odoo-bin -d <db> --modules=<module> --i18n-export=<module>.pot \
  --stop-after-init --limit-memory-hard=${ODOO_AI_LIMIT_MEMORY_HARD:-4294967296}
# export one translated .po per target language from the SAME DB (repeat per <lang>):
odoo-bin -d <db> --modules=<module> --i18n-export=<lang>.po \
  --language=<lang> --stop-after-init \
  --limit-memory-hard=${ODOO_AI_LIMIT_MEMORY_HARD:-4294967296}
```

### v17-v18 (has `--skip-auto-install`; server flags)

`--skip-auto-install` blocks auto_install siblings from leaking THEIR terms into the shared
registry - install just the module and its closure:

```bash
# Memory-cap policy: ${CLAUDE_PLUGIN_ROOT}/snippets/odoo-bin-resource-limits.md
[ -z "${ODOO_AI_LIMIT_MEMORY_HARD-4294967296}" ] || [ "${ODOO_AI_LIMIT_MEMORY_HARD-4294967296}" = "0" ] || ulimit -Sv "$(( ${ODOO_AI_LIMIT_MEMORY_HARD-4294967296} / 1024 ))" 2>/dev/null || true
# ONE build (KT5): install + demo + activate en_US (KT3 - ALWAYS) and EVERY target language,
# blocking auto_install siblings. Still NO demo flag - demo is ON by default here too (KT4).
odoo-bin -d <db> -i <module> --skip-auto-install \
  --load-language=en_US,<lang1>[,<lang2>...] \
  --stop-after-init --limit-memory-hard=${ODOO_AI_LIMIT_MEMORY_HARD:-4294967296}
# export the .pot TEMPLATE from that same DB (no --language):
odoo-bin -d <db> --modules=<module> --i18n-export=<module>.pot \
  --stop-after-init --limit-memory-hard=${ODOO_AI_LIMIT_MEMORY_HARD:-4294967296}
# export one translated .po per target language from the SAME DB (repeat per <lang>):
odoo-bin -d <db> --modules=<module> --i18n-export=<lang>.po \
  --language=<lang> --stop-after-init \
  --limit-memory-hard=${ODOO_AI_LIMIT_MEMORY_HARD:-4294967296}
```

`--skip-auto-install` is load-bearing: omit it and every `auto_install: True` module whose deps
are met installs alongside the target, injecting THEIR terms into the registry and polluting the
`.pot`/`.po` with foreign `msgid`s.

### The `odoo-bin i18n` subcommand era (EXPORT/IMPORT only - NOT language activation)

v19 moves i18n export/import onto a dedicated `odoo-bin i18n` subcommand (`loadlang` / `export` /
`import`), and `--i18n-export` is no longer a server flag there -
`cli_help(command='server', flag='--i18n-export', odoo_version='19.0')` -> not found on command
'server'. `--load-language` is NOT part of that move: it is still a stable server flag there -
`cli_help(command='server', flag='--load-language', odoo_version='19.0')` -> `Status: stable` -
so never drop it when carrying an earlier recipe forward, and never assume the subcommand replaced
it. Ground exact sub-subcommand flags via `cli_help(command='i18n', odoo_version='19.0')` before
invoking:

```bash
# install the module (still a server-flag concern) - memory-cap policy:
# ${CLAUDE_PLUGIN_ROOT}/snippets/odoo-bin-resource-limits.md
[ -z "${ODOO_AI_LIMIT_MEMORY_HARD-4294967296}" ] || [ "${ODOO_AI_LIMIT_MEMORY_HARD-4294967296}" = "0" ] || ulimit -Sv "$(( ${ODOO_AI_LIMIT_MEMORY_HARD-4294967296} / 1024 ))" 2>/dev/null || true
# ONE build (KT5). Demo is OFF by default on this series, so --with-demo MUST be passed explicitly
# (KT4) - the one era where a demo flag belongs on a translation build; confirm with
# cli_help(command='server', flag='--with-demo', odoo_version='<target>'). Do NOT reach for
# --without-demo here: its arity moved too - snippets/odoo-version-pivots.md owns that row.
odoo-bin -d <db> -i <module> --skip-auto-install --with-demo \
  --stop-after-init --limit-memory-hard=${ODOO_AI_LIMIT_MEMORY_HARD:-4294967296}
# activate en_US (base language, KT3 - ALWAYS) + EVERY target language INTO the DB
# (KT1 - activates msgstr for a translated export). Two forms exist here and BOTH work: the csv
# server flag was NOT removed when export/import moved onto the subcommand - confirm with
# cli_help(command='server', flag='--load-language', odoo_version='<target>'). The i18n subcommand
# is a separate CLI parser from the server build path above and does not take --limit-memory-hard:
odoo-bin i18n loadlang -d <db> -l en_US
odoo-bin i18n loadlang -d <db> -l <lang1> [<lang2> ...]
# export the .pot TEMPLATE and then one .po per target language, all from that SAME DB
# (default -l pot = template .pot; pass <lang> to emit the translated .po):
odoo-bin i18n export -d <db> -o <module>.pot <module>
odoo-bin i18n export -d <db> -l <lang> -o <lang>.po <module>
# import (optional: test-import the finalized post-adjudication .po; the -u reload gate covers this):
odoo-bin i18n import -d <db> -l <lang> -w <lang>.po
```

The `.pot` is a TEMPLATE: every `msgid` present, every `msgstr` empty - the inventory of current
translatable terms, NOT a translation. Never commit a `.pot` over a `.po`.

**Always re-export the `.pot` FRESH.** Regenerate `<module>.pot` from the currently-installed code
on EVERY invocation - never reuse a committed or prior-run `.pot` already on disk. A stale template
is missing the run's new/renamed `msgid`s, so the L2 reconcile silently under-populates and the new
terms never reach the translators. This is once-per-module-per-run (a fresh export each run), NOT
per-language - see the multi-language loop below.

---

## Multi-language loop order

When the resolved scope has more than one target language, the BUILD is still singular (KT5) - it is
the exports and the translation work that loop:

- Loop 0 (per module, ONCE): the L1 build - install with demo, activate `en_US` plus EVERY target
  language in that one call. Not per language: activating three languages is one build with three
  codes in the activation set, never three builds.
- Loop 1 (per module, language-agnostic): export the `.pot` template ONCE per module from that
  build. The `.pot` is the untranslated catalog and does NOT depend on language - never re-export it
  per language, and never from a different build than the `.po`s (KT5).
- Loop 2 (per language, module-inner): for each target `<lang>`, and for each module - build the
  per-language glossary/TM (`glossary-tm-<lang>.json`), re-export `<lang>.po` from the SAME build
  (its language is already active from Loop 0 - do not re-provision to add one), reconcile by
  load + re-export + diff-review (non-destructive, no polib), hand-translate the residual, then run
  the per-language validation gates (diff-review adjudication + placeholder-integrity; `-u` reload
  with `<lang>` loaded). Emit `translation-report-<lang>.json` per language. Each language's `-u`
  reload follows the reserve-only allocator guard (see gate-3 above): reuse the L1 install lease
  or use `--mode exclusive` on a declared DB - never a fresh ephemeral lease for reload-only.

Artifacts are per-language EXCEPT the shared `.pot`: `<module>.pot` (shared) vs
`<lang>.po` / `glossary-tm-<lang>.json` / `translation-report-<lang>.json` / `consistency-audit-<lang>.md`.

---

## L2 - Diff-review reconcile (the non-destructive core - no polib)

The fresh instance already has the existing `<lang>.po` loaded (L1: the committed file sits in the
module's `i18n/` dir, so `--load-language` / `loadlang` staged its `msgstr`s into the DB). So the
re-export REPRODUCES the human translation - it is NOT a blind fresh-DB export. Reconcile the
re-exported file against the committed one by DIFF-REVIEW:

1. The committed `<lang>.po` is the diff baseline - it is still at git HEAD; the re-export lands in
   the working tree, so no manual `.orig` copy is needed.
2. Re-export `<module>` for `<lang>` (the L1 translated-re-export path) - this overwrites the
   working-tree `i18n/<lang>.po`.
3. **Diff-review (delegated - never run git yourself).** Invoke the `git-toolkit:git-ops` skill
   (via the Skill tool) to diff the re-exported `i18n/<lang>.po` against its committed (HEAD) version
   and report the changes back. Per `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`, the git op is
   delegated to git-ops and its result is read back - the skill/agent does not run git itself.
4. **Adjudicate every removed/changed `msgstr`** in the reported diff into one of the THREE
   buckets - CORRECT / ARTEFACT / WRONG - defined once in
   `${CLAUDE_PLUGIN_ROOT}/snippets/po-entry-semantics.md` § Adjudicating a removed or changed entry.
   Read it rather than working from memory: the ARTEFACT test must be applied BEFORE ruling WRONG,
   or every module holding a deliberately-unlocalised term blocks a correct run. Only a WRONG ruling
   is a BLOCK - do NOT commit; fix the cause (re-provision fresh, re-load the language, re-export)
   and re-review.
5. Only after every removed/changed entry is ruled CORRECT does the re-exported `<lang>.po` become
   the new committed file - and the commit is itself a `git-ops` call (never run by a leaf worker).

**ABSOLUTE PROHIBITION:** never blind-overwrite a committed `.po` with a fresh-DB export that had no
load step, and never commit an un-adjudicated re-export. Load-first + diff-review + adjudication IS
the non-destructive contract; skipping it erases the human translation.

---

## L3 - Hand-translate the residual

After L2 the residual is the NEW bucket plus any entry a WRONG adjudication restored. **An
ARTEFACT blank is NOT residual** - it is an entry whose translation equals its source, which Odoo
never re-exports; restore the committed entry and move on. The two origins of an empty `msgstr`, and
the test that separates them, are in `${CLAUDE_PLUGIN_ROOT}/snippets/po-entry-semantics.md`
§ An empty `msgstr` has TWO origins. Re-translating an ARTEFACT is the most common way this phase
does damage: it overwrites a reviewed do-not-localise decision with an invented translation.

Translate each genuine residual `msgstr` by hand, applying the term policy
(`${CLAUDE_PLUGIN_ROOT}/snippets/translation-term-policy.md`). Check the placeholder set and the
`fuzzy` flag per entry as you write it (no full-file polib scan) - both rules live in
`po-entry-semantics.md` § Fuzzy and placeholders.

---

## Validation before commit (every gate is a hard BLOCK on failure)

1. **Diff-review adjudication (delegated to git-ops, NOT a raw local diff you run).** Invoke
   `git-toolkit:git-ops` to diff the re-exported `<lang>.po` against its committed version; every
   removed/changed `msgid` in the reported diff MUST carry one of the three rulings from
   `${CLAUDE_PLUGIN_ROOT}/snippets/po-entry-semantics.md` § Adjudicating a removed or changed entry.
   An un-adjudicated entry, or one ruled WRONG, is a hard BLOCK - the human translation was lost by
   accident (usually the language was not loaded into the DB before the re-export). An ARTEFACT
   ruling is NOT a block and NOT residual: restore the committed entry. The skill/agent never runs
   git itself - it delegates to git-ops and reads the result.

2. **Placeholder integrity (per entry, no polib).** Every entry translated in L3 must satisfy the
   placeholder rule in `${CLAUDE_PLUGIN_ROOT}/snippets/po-entry-semantics.md` § Fuzzy and
   placeholders; a mismatch makes the translation raise or render wrong at runtime - BLOCK. Check
   each entry as you write it (a `re`-based spot-check on that entry is fine); reproduced entries
   from the diff baseline were already correct and need no full-file re-scan.

3. **Load validation via Odoo, NOT msgfmt.** Reload the module (HARD RULE, never omit the
   `ulimit -Sv` guard; memory-cap policy: `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-bin-resource-limits.md`;
   see `docs/reference/INSTANCE-LIFECYCLE.md` § `-i` vs `-u` semantics):

   ```bash
   [ -z "${ODOO_AI_LIMIT_MEMORY_HARD-4294967296}" ] || [ "${ODOO_AI_LIMIT_MEMORY_HARD-4294967296}" = "0" ] || ulimit -Sv "$(( ${ODOO_AI_LIMIT_MEMORY_HARD-4294967296} / 1024 ))" 2>/dev/null || true
   odoo-bin -d <db> -u <module> --stop-after-init --limit-memory-hard=${ODOO_AI_LIMIT_MEMORY_HARD:-4294967296}
   ```

   `-u` re-imports the translation
   and surfaces a broken `.po` (duplicate `msgid`, bad header, format error) that `msgfmt` misses -
   `msgfmt` validates gettext syntax only, not Odoo's import path. Pass signal: clean `-u` reload,
   no translation error in the log.

   **Pre-condition - target language must be active in the DB (KT1).** Before `-u`, confirm the
   target language is LOADED (Settings > Translations > Activate a language, or `--load-language=<lang>`
   on the install run, or `odoo-bin i18n loadlang -d <db> -l <lang>` in the subcommand form - see L1).
   Absent language -> reload succeeds silently but translations do not load at runtime - false pass.
   **`en_US` must ALSO be active (KT3).** Confirm BOTH `en_US` (the base/source language) and each
   `<lang>` are loaded before the reload - not the target language alone.

   **Reserve-only allocator guard.** Reuse the SAME instance and lease the L1 `-i` install used -
   the `-u` reload requires the DB to ALREADY EXIST with the module installed. Under the
   reserve-only allocator, `--mode ephemeral` only reserves a unique DB name and ports; the DB is
   created by the L1 `-i` run via Odoo create-on-init, not by the allocator. Do NOT acquire a
   fresh ephemeral lease for the reload - its DB is uncreated and `-u` will fail. Keep the L1
   lease, or use `--mode exclusive` on a declared DB that already has the module installed.

4. **Export against the adapted code (PR-head / merged tree).** When odoo-i18n is dispatched from a
   forward-port or upgrade run, the Odoo instance must run the POST-ADAPT code - the worktree the adapt
   wrote - NOT the source/original branch and NOT the principal checkout. Exporting from pre-adapt code
   yields a `.pot` with the old term inventory, missing new/renamed strings introduced in the port.
   **Mechanism (this is not advice - without it L2 silently under-merges):** pass `WORKTREE_PATH` to
   `odoo-instance`, which re-roots the instance's addons list onto that worktree
   (`${CLAUDE_PLUGIN_ROOT}/skills/odoo-instance/SKILL.md` § WORKTREE_PATH substitution ->
   `allocator.py acquire --addons-path-override`). An instance whose addons path points at the
   principal checkout makes a worktree-only `msgid` surface as NEITHER a removed nor a changed entry,
   so the L2 adjudication loop has nothing to rule on and the loss is committed unseen. Before the L1
   export, apply `${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md` § Addons coverage
   assertion; on a miss, BLOCK - do not export.

5. **`.pot` freshness (always re-export) + `en_US` active.** The `.pot` merged in L2 MUST be the one
   this run exported from the currently-installed code - a committed or prior-run `<module>.pot` on
   disk is never sufficient by itself; re-export unconditionally every invocation (once per module,
   not per language). AND `en_US` must be in the activation set of every `--load-language` / `loadlang`
   call (KT3), never the target language alone. Skipping either is a silent under-merge / false pass -
   BLOCK.

6. **Build shape - demo loaded, and ONE build behind every artifact (KT4 + KT5).** Confirm, before
   trusting any exported file, that the build these artifacts came from was installed WITH demo data
   and that the `.pot` and every `<lang>.po` of this run came from THAT SAME database. Both are
   decidable from what you already have, so neither is a judgement call:

   - **Demo:** the `-i` command line carries no `--without-demo` in any form, and carries
     `--with-demo` on the series where demo defaults OFF
     (`${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md` § CLI - demo flag). Corroborate against
     the instance rather than the command alone - a module in
     scope whose manifest declares `demo` files must have its demo records present
     (`ir.model.data` rows for that module pointing at records those files define). Absent -> the
     catalog is truncated: BLOCK and re-provision. Demo loads only at `-i`, so there is no repair
     short of a new build.
   - **One build:** the `.pot` and every `.po` name the same `INSTANCE_HANDLE` / lease. A mismatch
     means the reconcile compared two different term inventories and its rulings are void -
     re-export every artifact from one build and re-adjudicate.

   A demo-less or mixed-build run is exactly the shape that produces a mass of REMOVED entries whose
   `msgid`s are still in source, so it is ALSO the shape most likely to be mis-ruled WRONG and
   "fixed" by deleting real translation. Check the build before you trust the diff.

---

## Glossary and term choice

Which WORDS to use - the three glossary layers and their precedence (TM from core + deps, the
project `glossary.yml`, the OSM canonical `field.string`), plus the independent-regime guard - is
owned by `${CLAUDE_PLUGIN_ROOT}/snippets/translation-term-policy.md`. Consult it when building the
TM (P1) and when hand-translating the residual (L3). It is not restated here.
