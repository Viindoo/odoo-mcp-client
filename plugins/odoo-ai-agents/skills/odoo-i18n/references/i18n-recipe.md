<!-- SSOT reference. The single source for the non-destructive Odoo i18n (.pot/.po) recipe.
     Referenced (not copy-pasted) by the odoo-i18n skill AND by odoo-forward-port's P4 i18n step
     via ${CLAUDE_PLUGIN_ROOT}/skills/odoo-i18n/references/i18n-recipe.md. Edit here only.
     Cross-ref: docs/reference/INSTANCE-LIFECYCLE.md, docs/reference/ODOO-TESTING.md -->

# Odoo i18n recipe - non-destructive .pot/.po (SSOT)

Load-bearing belief: **re-exporting a `.po` from a fresh DB OVERWRITES it with empty `msgstr`s and
silently destroys 40-90% of the existing translation** - a clean exit code on data loss. A fresh
DB has no human translation, so `--i18n-export` emits a template (`msgid` + empty `msgstr`). Every
step forwards the translation MEMORY, never regenerates it: export a `.pot` TEMPLATE, update the
maintained `.po` by MERGE, never overwrite.

REQUIRES a running Odoo instance with the target module installed - export and validate both need
a live DB + registry. No no-DB workaround (babel/polib cannot walk the module's translatable terms
the way Odoo's registry does). Missing instance is a BLOCK, not a fallback - acquire per
`docs/reference/INSTANCE-LIFECYCLE.md`.

Ground every odoo-bin flag for the target series before invoking - server flags v8-v18 vs the
`i18n` subcommand v19+:

```
cli_help(command='i18n-export', odoo_version='<target>')   # v8-v18 (server flag)
cli_help(command='i18n', odoo_version='19.0')              # v19+ (subcommand)
```

Examples below use `<lang>` as the target-language placeholder; the default language when none is resolved is `vi_VN`.

---

## L1 - Install + load the language, then export

Two distinct exports - pick the one you need:

- **Template (`.pot`) for the L2 merge:** install the module (no language load needed), export the
  term inventory with empty `msgstr`s. Common path.
- **Translated (`.po`) re-export of existing translation:** the language must be LOADED into the
  DB FIRST or the export emits empty `msgstr`s (a template, not a translation).

**KT1 - `--load-language` ACTIVATES the translation in the DB; `--language`/`-l` only SELECTS the
export file.** Two different flags, both needed for a translated export:

- `--load-language=<lang>` (v8-v18) / `odoo-bin i18n loadlang -l <lang>` (v19+) LOADS the language
  INTO the DB so its `msgstr`s become active and exportable. Omit it -> empty `msgstr`s.
- `--language=<lang>` (export flag, v8-v18) / `-l <lang>` (`i18n export`, v19+) SELECTS which
  language the export file targets. Does NOT load the translation; without the load step it emits
  an empty-`msgstr` file.

Forward-port lifts `msgstr`s from the source `.po` via polib, so a bare template export is fine
there; the general re-export-existing-translation case REQUIRES the load step.

Export from a DB where ONLY the target module + its dependency closure is installed, so terms from
auto-installed siblings do not leak into the `.pot`.

### v8-v16 (no `--skip-auto-install`; server flags; isolate by DATABASE)

One fresh DB per module, installed in dependency order, exported from a DB that does NOT contain
its children, so a parent's `.pot` carries only the parent's terms.

```bash
# install + load the language into an isolated per-module DB (dependency order):
odoo-bin -d <db> -i <module> --load-language=<lang> \
  --without-demo=all --stop-after-init
# export the language file (.pot template, or .po once <lang> is loaded above):
odoo-bin -d <db> --modules=<module> --i18n-export=<module>.pot \
  --language=<lang> --stop-after-init
```

### v17-v18 (has `--skip-auto-install`; server flags)

`--skip-auto-install` blocks auto_install siblings from leaking THEIR terms into the shared
registry - install just the module and its closure:

```bash
# install + load the language, blocking auto_install siblings:
odoo-bin -d <db> -i <module> --skip-auto-install --load-language=<lang> \
  --stop-after-init
# export the language file:
odoo-bin -d <db> --modules=<module> --i18n-export=<module>.pot \
  --language=<lang> --stop-after-init
```

`--skip-auto-install` is load-bearing: omit it and every `auto_install: True` module whose deps
are met installs alongside the target, injecting THEIR terms into the registry and polluting the
`.pot`/`.po` with foreign `msgid`s.

### v19+ (the `i18n` subcommand replaces the server flags)

v19 moves i18n onto a dedicated `odoo-bin i18n` subcommand (`loadlang` / `export` / `import`). The
server-flag form (`--i18n-export`, `--load-language`) is GONE - do NOT carry the `>= 17` recipe
into v19. Ground exact sub-subcommand flags via `cli_help(command='i18n', odoo_version='19.0')`
before invoking:

```bash
# install the module (still a server-flag concern):
odoo-bin -d <db> -i <module> --skip-auto-install --stop-after-init
# load the language INTO the DB (KT1 - activates msgstr for a translated export):
odoo-bin i18n loadlang -d <db> -l <lang>
# export (default -l pot = template .pot; pass <lang> to emit the translated .po):
odoo-bin i18n export -d <db> -l <lang> -o <lang>.po <module>
# import (e.g. after the polib merge, to reload the merged .po):
odoo-bin i18n import -d <db> -l <lang> -w <lang>.po
```

The `.pot` is a TEMPLATE: every `msgid` present, every `msgstr` empty - the inventory of current
translatable terms, NOT a translation. Never commit a `.pot` over a `.po`.

---

## Multi-language loop order

When the resolved scope has more than one target language, run two nested loops:

- Loop 1 (per module, language-agnostic): export the `.pot` template ONCE per module. The `.pot`
  is the untranslated catalog and does NOT depend on language - never re-export it per language.
- Loop 2 (per language, module-inner): for each target `<lang>`, and for each module - build the
  per-language glossary/TM (`glossary-tm-<lang>.json`), `--load-language=<lang>`, merge into
  `<lang>.po` via polib (non-destructive), hand-translate the residual, then run the per-language
  validation gates (msgstr-regression + placeholder-integrity on `<lang>.po`; `-u` reload with
  `<lang>` loaded). Emit `translation-report-<lang>.json` per language. Each language's `-u`
  reload follows the reserve-only allocator guard (see gate-3 above): reuse the L1 install lease
  or use `--mode exclusive` on a declared DB - never a fresh ephemeral lease for reload-only.

Artifacts are per-language EXCEPT the shared `.pot`: `<module>.pot` (shared) vs
`<lang>.po` / `glossary-tm-<lang>.json` / `translation-report-<lang>.json` / `consistency-audit-<lang>.md`.

---

## L2 - polib TM-merge (the non-destructive core)

Merge the fresh `.pot` template INTO the maintained `.po` with `polib`: keep every existing
`msgstr` whose `msgid` survives, mark dropped entries obsolete, add new empty entries. Only the
term inventory is refreshed; the translation memory survives.

```python
import polib

po = polib.pofile('<lang>.po')           # the maintained translation (has human msgstrs)
pot = polib.pofile('<module>.pot')        # the fresh template (msgstrs empty)

before = len([e for e in po if e.msgstr])  # non-empty count BEFORE (regression baseline)

po.merge(pot)                              # keep live msgstr, obsolete the dropped, add new-empty

# drop obsolete entries (msgid gone from the module) so they stop shipping:
po[:] = [e for e in po if not e.obsolete]

po.save('<lang>.po')

after = len([e for e in po if e.msgstr])
```

`po.merge(pot)` semantics (the forward-translation-memory contract): `msgid` in both -> keep the
`.po`'s `msgstr`; in `.po` not `.pot` -> flag obsolete; in `.pot` not `.po` -> add with empty
`msgstr`.

**ABSOLUTE PROHIBITION:** never `odoo-bin --i18n-export=<lang>.po` from a fresh DB, and never
overwrite a maintained `.po` with a freshly exported one - the fresh-DB export's empty `msgstr`s
erase the human translation. Export ONLY to a `.pot` template, then merge.

---

## L3 - Hand-translate the residual

After L2, the only empty/fuzzy entries are genuinely new or changed terms. Translate each residual
`msgstr` by hand, applying the glossary (below). Clear each entry's `fuzzy` flag only after
confirming or correcting its `msgstr` - a left-over `fuzzy` flag makes Odoo ignore the translation
at load time.

---

## Validation before commit (every gate is a hard BLOCK on failure)

1. **Non-empty-msgstr regression (polib, NOT grep).** Compare the non-empty count before and
   after the merge:

   ```python
   before = len([e for e in polib.pofile('<lang>.po.orig') if e.msgstr])
   after  = len([e for e in polib.pofile('<lang>.po')      if e.msgstr])
   assert after >= before, f"REGRESSION: {before} -> {after} non-empty msgstr - L2 merge skipped"
   ```

   A large drop means an overwrite slipped past L2 - BLOCK and re-run the merge. Do NOT measure
   this with `grep -c '^msgstr ""'`: a `.po` `msgstr` can span multiple lines (`msgstr ""` header
   line + continuation strings), so the grep miscounts multi-line entries and the file header -
   false pass.

2. **Placeholder integrity.** For each entry, the placeholder set in `msgstr` must equal the set
   in `msgid`. Extract `%s`, `%d`, `%(name)s`, `{}` / `{name}` from both; differ -> the translation
   raises or renders wrong at runtime - BLOCK:

   ```python
   import re
   PH = re.compile(r'%\([^)]+\)[sd]|%[sd]|\{[^}]*\}')
   for e in polib.pofile('<lang>.po'):
       if e.msgstr and set(PH.findall(e.msgid)) != set(PH.findall(e.msgstr)):
           raise SystemExit(f"PLACEHOLDER MISMATCH: {e.msgid!r} vs {e.msgstr!r}")
   ```

3. **Load validation via Odoo, NOT msgfmt.** Reload the module: `odoo-bin -d <db> -u <module>
   --stop-after-init` (see `docs/reference/INSTANCE-LIFECYCLE.md`). `-u` re-imports the translation
   and surfaces a broken `.po` (duplicate `msgid`, bad header, format error) that `msgfmt` misses -
   `msgfmt` validates gettext syntax only, not Odoo's import path. Pass signal: clean `-u` reload,
   no translation error in the log.

   **Pre-condition - target language must be active in the DB (KT1).** Before `-u`, confirm the
   target language is LOADED (Settings > Translations > Activate a language, or `--load-language=<lang>`
   on the install run for v8-v18 / `odoo-bin i18n loadlang -d <db> -l <lang>` for v19+ - see L1).
   Absent language -> reload succeeds silently but translations do not load at runtime - false pass.

   **Reserve-only allocator guard.** Reuse the SAME instance and lease the L1 `-i` install used -
   the `-u` reload requires the DB to ALREADY EXIST with the module installed. Under the
   reserve-only allocator, `--mode ephemeral` only reserves a unique DB name and ports; the DB is
   created by the L1 `-i` run via Odoo create-on-init, not by the allocator. Do NOT acquire a
   fresh ephemeral lease for the reload - its DB is uncreated and `-u` will fail. Keep the L1
   lease, or use `--mode exclusive` on a declared DB that already has the module installed.

4. **Export against the adapted code (PR-head / merged tree).** When odoo-i18n is dispatched from a
   forward-port run, the Odoo instance must run the POST-ADAPT code (PR branch or merged worktree),
   NOT the source/original branch. Exporting from pre-adapt code yields a `.pot` with the old term
   inventory, missing new/renamed strings introduced in the port.

---

## Glossary - three layers (consult in order, first canonical hit wins)

Consult when building the TM (P1) and hand-translating the residual (L3):

1. **TM from core + deps.** Read the already-translated `<lang>.po` of core Odoo and the module's
   dependency modules; reuse their `msgstr` for any recurring `msgid`. Largest, most authoritative
   term source.
2. **Project glossary file.** `.odoo-ai/glossary.yml` - YAML map of domain/regulatory terms the
   project has fixed (accounting-circular terminology, product names) + source citation. Project
   terms override a generic TM hit on conflict.
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
