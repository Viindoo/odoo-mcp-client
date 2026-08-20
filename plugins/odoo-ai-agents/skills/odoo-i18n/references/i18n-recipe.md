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
entry as correct (term genuinely gone) or wrong (accidental loss) before commit. No merge library
(no `polib`): the diff is delegated to `git-toolkit:git-ops` and the agent adjudicates the result.

REQUIRES a running Odoo instance with the target module installed - export and validate both need
a live DB + registry. No no-DB workaround (babel/polib cannot walk the module's translatable terms
the way Odoo's registry does). Missing instance is a BLOCK, not a fallback - acquire per
`docs/reference/INSTANCE-LIFECYCLE-BUILD-CONTRACT.md`.

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

## L1 - Install + load the language, then export

Two distinct exports - pick the one you need:

- **Template (`.pot`) for the L2 reconcile / seeding a new language:** install the module (no language load needed), export the
  term inventory with empty `msgstr`s. Common path.
- **Translated (`.po`) re-export of existing translation:** the language must be LOADED into the
  DB FIRST or the export emits empty `msgstr`s (a template, not a translation).

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
# install + load en_US (base language, KT3 - ALWAYS) + the target language into an isolated
# per-module DB (dependency order):
odoo-bin -d <db> -i <module> --load-language=en_US,<lang> \
  --without-demo=all --stop-after-init \
  --limit-memory-hard=${ODOO_AI_LIMIT_MEMORY_HARD:-4294967296}
# export the language file (.pot template, or .po once <lang> is loaded above):
odoo-bin -d <db> --modules=<module> --i18n-export=<module>.pot \
  --language=<lang> --stop-after-init \
  --limit-memory-hard=${ODOO_AI_LIMIT_MEMORY_HARD:-4294967296}
```

### v17-v18 (has `--skip-auto-install`; server flags)

`--skip-auto-install` blocks auto_install siblings from leaking THEIR terms into the shared
registry - install just the module and its closure:

```bash
# Memory-cap policy: ${CLAUDE_PLUGIN_ROOT}/snippets/odoo-bin-resource-limits.md
[ -z "${ODOO_AI_LIMIT_MEMORY_HARD-4294967296}" ] || [ "${ODOO_AI_LIMIT_MEMORY_HARD-4294967296}" = "0" ] || ulimit -Sv "$(( ${ODOO_AI_LIMIT_MEMORY_HARD-4294967296} / 1024 ))" 2>/dev/null || true
# install + load en_US (base language, KT3 - ALWAYS) + the target language, blocking auto_install siblings:
odoo-bin -d <db> -i <module> --skip-auto-install --load-language=en_US,<lang> \
  --stop-after-init --limit-memory-hard=${ODOO_AI_LIMIT_MEMORY_HARD:-4294967296}
# export the language file:
odoo-bin -d <db> --modules=<module> --i18n-export=<module>.pot \
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
odoo-bin -d <db> -i <module> --skip-auto-install --stop-after-init \
  --limit-memory-hard=${ODOO_AI_LIMIT_MEMORY_HARD:-4294967296}
# load en_US (base language, KT3 - ALWAYS) + the target language INTO the DB
# (KT1 - activates msgstr for a translated export). The `i18n` subcommand is a separate CLI
# parser from the server build path above and does not take --limit-memory-hard:
odoo-bin i18n loadlang -d <db> -l en_US
odoo-bin i18n loadlang -d <db> -l <lang>
# export (default -l pot = template .pot; pass <lang> to emit the translated .po):
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

When the resolved scope has more than one target language, run two nested loops:

- Loop 1 (per module, language-agnostic): export the `.pot` template ONCE per module. The `.pot`
  is the untranslated catalog and does NOT depend on language - never re-export it per language.
- Loop 2 (per language, module-inner): for each target `<lang>`, and for each module - build the
  per-language glossary/TM (`glossary-tm-<lang>.json`), `--load-language=<lang>`, reconcile into
  `<lang>.po` by load + re-export + diff-review (non-destructive, no polib), hand-translate the residual, then run the per-language
  validation gates (diff-review adjudication + placeholder-integrity; `-u` reload with
  `<lang>` loaded). Emit `translation-report-<lang>.json` per language. Each language's `-u`
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
4. **Adjudicate every removed/changed `msgstr`** in the reported diff:
   - **CORRECT** - the `msgid` genuinely no longer appears in the module source (term removed /
     renamed in code). Confirm by grepping the module source (or `entity_lookup`). Accept the loss.
   - **WRONG** - the `msgid` still exists in source but its translation vanished/changed. That is an
     accidental loss (language not loaded, wrong export scope, `auto_install` leakage). BLOCK: do NOT
     commit; fix the cause (re-provision fresh, re-load the language, re-export) and re-review.
   Adjudicate only `msgid`/`msgstr` changes; IGNORE header timestamps, `#:` reference-comment churn,
   and entry reordering - those are export-format noise, not translation losses.
5. Only after every removed/changed entry is ruled CORRECT does the re-exported `<lang>.po` become
   the new committed file - and the commit is itself a `git-ops` call (never run by a leaf worker).

**ABSOLUTE PROHIBITION:** never blind-overwrite a committed `.po` with a fresh-DB export that had no
load step, and never commit an un-adjudicated re-export. Load-first + diff-review + adjudication IS
the non-destructive contract; skipping it erases the human translation.

---

## L3 - Hand-translate the residual

After L2, the residual to translate is the ADDED bucket (new-empty `msgstr` for terms new at this
version) plus any entry a WRONG adjudication restored. Translate each residual `msgstr` by hand,
applying the glossary (below). **Placeholder check per entry (no full-file polib scan):** as you
write each `msgstr`, confirm its placeholder set matches the `msgid` - `%s` / `%d` / `%(name)s` /
`{}` / `{name}` must be identical, else the translation raises or renders wrong at runtime. If
Odoo's exporter left a `fuzzy` flag on an entry, clear it only after confirming or correcting the
`msgstr`.

---

## Validation before commit (every gate is a hard BLOCK on failure)

1. **Diff-review adjudication (delegated to git-ops, NOT a raw local diff you run).** Invoke
   `git-toolkit:git-ops` to diff the re-exported `<lang>.po` against its committed version; every
   removed/changed `msgid` in the reported diff MUST be adjudicated CORRECT (term gone from source)
   or WRONG. An un-adjudicated or WRONG-ruled entry is a hard BLOCK - it means the human translation
   was lost by accident (usually the language was not loaded into the DB before the re-export).
   Adjudicate only `msgid`/`msgstr` changes; ignore header/reference-comment/reordering noise. The
   skill/agent never runs git itself - it delegates to git-ops and reads the result.

2. **Placeholder integrity (per entry, no polib).** For every entry translated in L3, the
   placeholder set in `msgstr` must equal the set in `msgid` (`%s`, `%d`, `%(name)s`, `{}` /
   `{name}`); a mismatch makes the translation raise or render wrong at runtime - BLOCK. Check each
   entry as you write it (a `re`-based spot-check on that entry is fine); reproduced entries from the
   diff baseline were already correct and need no full-file re-scan.

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

---

## Glossary - three layers (consult in order, first canonical hit wins)

Consult when building the TM (P1) and hand-translating the residual (L3):

1. **TM from core + deps.** Read the already-translated `<lang>.po` of core Odoo and the module's
   dependency modules; reuse their `msgstr` for any recurring `msgid`. Largest, most authoritative
   term source.
2. **Project glossary file.** `glossary.yml` - YAML map of domain/regulatory terms the
   project has fixed (accounting-circular terminology, product names) + source citation. Project
   terms override a generic TM hit on conflict. Tier-2 SHARE; resolve it via the
   resolve-capture-substitute protocol in `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`
   (captured path shown as `<SHARE_DIR>` below) - `<SHARE_DIR>/glossary.yml`.
3. **OSM canonical field label.** For a term mapping to a model field, reuse the field's canonical
   `string` rather than inventing one:

   ```
   entity_lookup(kind='field', model='<model>', field='<field>', odoo_version='<version>')
   ```

   Translate FROM the returned `field.string` so the translation aligns with the UI label.

**Independent-regime guard:** for legally independent regimes (Vietnam accounting circulars TT200 /
TT133 / TT99), do NOT dedup or cross-copy translations even when `msgid`s look identical. Each
regime's `.po` stays complete and self-standing; an incidental string match is not a reason to
share a translation.
