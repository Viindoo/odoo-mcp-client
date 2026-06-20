<!-- SSOT reference. The single source for the non-destructive Odoo i18n (.pot/.po) recipe.
     Referenced (not copy-pasted) by the odoo-i18n skill AND by odoo-forward-port's P4 i18n step
     via ${CLAUDE_PLUGIN_ROOT}/skills/odoo-i18n/references/i18n-recipe.md. Edit here only.
     Cross-ref: docs/reference/INSTANCE-LIFECYCLE.md, docs/reference/ODOO-TESTING.md -->

# Odoo i18n recipe - non-destructive .pot/.po (SSOT)

The one load-bearing belief: **re-exporting a `.po` from a fresh database OVERWRITES it with
empty `msgstr`s and silently destroys 40-90% of the existing translation**. A fresh DB has no
human translation, so `--i18n-export` emits a template (`msgid` with empty `msgstr`), and writing
that over the maintained `.po` is data loss with a clean exit code. Every step below exists to
forward the translation MEMORY, never to regenerate it. Export produces a `.pot` TEMPLATE; the
maintained `.po` is updated by MERGE, never by overwrite.

This recipe REQUIRES a running Odoo instance with the target module installed - export and
validate both need a live DB and registry. There is NO no-DB workaround (babel/polib alone cannot
walk the module's translatable terms the way Odoo's registry does). Missing instance is a BLOCK,
not a fallback. Acquire an instance per `docs/reference/INSTANCE-LIFECYCLE.md`.

Ground every odoo-bin flag for the target series before invoking - the CLI surface differs per
version (server flags v8-v18 vs the `i18n` subcommand v19+):

```
cli_help(command='i18n-export', odoo_version='<target>')   # v8-v18 (server flag)
cli_help(command='i18n', odoo_version='19.0')              # v19+ (subcommand)
```

This session pins `vi_VN` as the worked example language. Multi-language is a separate scope:
see issue #97.

---

## L1 - Install + load the language, then export

Two distinct exports exist - know which you need:

- **Template (`.pot`) for the polib merge below:** install the module (no language load needed)
  and export the term inventory with empty `msgstr`s. This is the common path; L2 merges it into
  the maintained `.po`.
- **Translated (`.po`) re-export of the existing translation:** to export a `.po` that CARRIES
  the existing `msgstr`s, the language must be LOADED into the DB FIRST. A fresh DB has no
  translation loaded, so the export emits empty `msgstr`s - a template, not a translation.

**KT1 - `--load-language` activates the translation; `--language`/`-l` only selects the export
file.** These are two different flags and both are needed for a translated export:

- `--load-language=<lang>` (v8-v18) / `odoo-bin i18n loadlang -l <lang>` (v19+) LOADS the
  language INTO the DB so its `msgstr`s become active and exportable. Omit it and the export
  produces empty `msgstr`s - a template only, never the maintained translation.
- `--language=<lang>` (export flag, v8-v18) / `-l <lang>` (`i18n export`, v19+) SELECTS which
  language the export file targets. It does NOT load the translation; without the load step above
  it just emits an empty-`msgstr` file for that language.

(Forward-port lifts `msgstr`s from the source `.po` via polib, so a bare template export is fine
there. The general odoo-i18n use case - re-export the existing translation - REQUIRES the load
step.)

Export the template from a DB where ONLY the target module (and its dependency closure) is
installed, so terms from auto-installed siblings do not leak into the module's `.pot`.

### v8-v16 (no `--skip-auto-install`; server flags; isolate by DATABASE)

One fresh DB per module, installed in dependency order, exported from a DB that does NOT contain
its children, so a parent's `.pot` carries only the parent's terms.

```bash
# install + load the language into an isolated per-module DB (dependency order):
odoo-bin -d <db> -i <module> --load-language=vi_VN \
  --without-demo=all --stop-after-init
# export the language file (.pot template, or .po once vi_VN is loaded above):
odoo-bin -d <db> --modules=<module> --i18n-export=<module>.pot \
  --language=vi_VN --stop-after-init
```

### v17-v18 (has `--skip-auto-install`; server flags)

`--skip-auto-install` blocks auto_install siblings from leaking THEIR terms into the shared
registry - install just the module and its closure:

```bash
# install + load the language, blocking auto_install siblings:
odoo-bin -d <db> -i <module> --skip-auto-install --load-language=vi_VN \
  --stop-after-init
# export the language file:
odoo-bin -d <db> --modules=<module> --i18n-export=<module>.pot \
  --language=vi_VN --stop-after-init
```

`--skip-auto-install` is load-bearing: without it, every `auto_install: True` module whose
dependencies are met installs alongside the target, injecting THEIR translatable terms into the
shared registry and polluting the `.pot`/`.po` with foreign `msgid`s.

### v19+ (the `i18n` subcommand replaces the server flags)

v19 moves i18n onto a dedicated `odoo-bin i18n` subcommand (`loadlang` / `export` / `import`).
The server-flag form (`--i18n-export`, `--load-language`) is gone here - do NOT carry the
`>= 17` server-flag recipe into v19. Ground the exact sub-subcommand flags via
`cli_help(command='i18n', odoo_version='19.0')` before invoking:

```bash
# install the module (still a server-flag concern):
odoo-bin -d <db> -i <module> --skip-auto-install --stop-after-init
# load the language INTO the DB (KT1 - activates msgstr for a translated export):
odoo-bin i18n loadlang -d <db> -l vi_VN
# export (default -l pot = template .pot; pass vi_VN to emit the translated .po):
odoo-bin i18n export -d <db> -l vi_VN -o <module>.po <module>
# import (e.g. after the polib merge, to reload the merged .po):
odoo-bin i18n import -d <db> -l vi_VN -w <module>.po
```

The `.pot` is a TEMPLATE: every `msgid` present, every `msgstr` empty. It is the inventory of
current translatable terms, NOT a translation. Never commit a `.pot` over a `.po`.

---

## L2 - polib TM-merge (the non-destructive core)

Merge the fresh `.pot` template INTO the maintained `.po` with `polib`. This keeps every existing
`msgstr` whose `msgid` still exists, marks removed entries obsolete, and adds new empty entries -
the translation memory survives; only the term inventory is refreshed.

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

`po.merge(pot)` semantics: an entry whose `msgid` is in both keeps the `.po`'s `msgstr`; an entry
in `.po` but not in `.pot` is flagged obsolete; an entry in `.pot` but not in `.po` is added with
an empty `msgstr`. This is exactly the forward-translation-memory contract.

**ABSOLUTE PROHIBITION:** never `odoo-bin --i18n-export=<lang>.po` from a fresh DB, and never
overwrite a maintained `.po` with a freshly exported one. A fresh-DB export has empty `msgstr`s; writing
it over the maintained `.po` erases the human translation. Export ONLY to a `.pot` template, then merge.

---

## L3 - Hand-translate the residual

After L2, the only empty/fuzzy entries left are genuinely new or changed terms. Translate each
residual `msgstr` by hand, applying the glossary (below) so terminology stays consistent with
core, deps, and prior project translations. Clear the `fuzzy` flag on each entry only after
confirming or correcting its `msgstr`; a left-over `fuzzy` flag makes Odoo ignore the translation
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
   line followed by continuation strings), so the grep miscounts both multi-line entries and the
   file header, giving a false pass.

2. **Placeholder integrity.** For each entry, the set of format placeholders in `msgstr` must
   equal the set in `msgid`. Extract `%s`, `%d`, `%(name)s`, and `{}` / `{name}` from both; if the
   sets differ, the translation will raise or render wrong at runtime - BLOCK:

   ```python
   import re
   PH = re.compile(r'%\([^)]+\)[sd]|%[sd]|\{[^}]*\}')
   for e in polib.pofile('<lang>.po'):
       if e.msgstr and set(PH.findall(e.msgid)) != set(PH.findall(e.msgstr)):
           raise SystemExit(f"PLACEHOLDER MISMATCH: {e.msgid!r} vs {e.msgstr!r}")
   ```

3. **Load validation via Odoo, NOT msgfmt.** Validate the merged `.po` by reloading the module
   with Odoo - `odoo-bin -d <db> -u <module> --stop-after-init` (see
   `docs/reference/INSTANCE-LIFECYCLE.md`). `-u` re-imports the translation and surfaces a broken
   `.po` (duplicate `msgid`, bad header, format error) that `msgfmt` does not catch because
   `msgfmt` validates gettext syntax only, not Odoo's import path. A clean `-u` reload with no
   translation error in the log is the pass signal.

   **Pre-condition - target language must be active in the DB (KT1).** Before running `-u`
   validation, confirm that the target language is LOADED in the DB (Settings > Translations >
   Activate a language, or pass `--load-language=vi_VN` on the install run for v8-v18 /
   `odoo-bin i18n loadlang -d <db> -l vi_VN` for v19+ - see L1 above). If the language is absent
   the reload will succeed silently but translations will not load at runtime - a false pass.

4. **Export against the adapted code (PR-head / merged tree).** When odoo-i18n is dispatched from
   a forward-port run, ensure the Odoo instance is running the POST-ADAPT code (the PR branch or
   merged worktree), NOT the source/original branch. Exporting from the pre-adapt codebase
   produces a `.pot` that reflects the old term inventory and misses new or renamed translatable
   strings introduced in the port.

---

## Glossary - three layers (consult in order, first canonical hit wins)

Consult the glossary when building the TM (P1) and when hand-translating the residual (L3) to keep terminology consistent across modules and across independent regimes:

1. **Translation memory from core + deps.** Read the already-translated `<lang>.po` of core Odoo
   and the module's dependency modules; reuse their `msgstr` for any `msgid` that recurs. This is
   the largest and most authoritative term source.
2. **Project glossary file.** `.odoo-ai/glossary.yml` - a YAML map of domain/regulatory terms the
   project has fixed (e.g. accounting-circular terminology, product-specific names) plus their
   source citation. Project terms override a generic TM hit when they conflict.
3. **OSM canonical field label.** For a term that maps to a model field, look up the field's
   canonical `string` to reuse Odoo's own label rather than inventing one:

   ```
   entity_lookup(kind='field', model='<model>', field='<field>', odoo_version='<version>')
   ```

   Use the returned `field.string` as the canonical English term to translate FROM, so the
   translation aligns with how the field is labelled in the UI.

**Independent-regime guard:** when modules implement legally independent regimes (e.g. the
Vietnam accounting circulars TT200 / TT133 / TT99), do NOT dedup or cross-copy their translations
even when `msgid`s look identical. Each regime's `.po` stays complete and self-standing; an
incidental string match is not a reason to share a translation across regimes.
