# PO entry semantics (SSOT)

## The identity rule - Odoo never exports a translation equal to its source

**A translation identical to its source string is exported as an EMPTY `msgstr`.** In
`odoo/tools/translate.py`, `PoFileWriter.write_rows` takes the translation only when
`trad != src` and writes `''` for every other entry - unchanged in every series this plugin serves.
Odoo displays the source for an empty `msgstr`, so such an entry is correct exactly as exported.

## An empty `msgstr` - translate it; an identity stays EMPTY

For every entry the export left with an empty `msgstr`, translate the `msgid` (word choice:
`translation-term-policy.md`). Decide per entry by actually translating it, never by how technical
the word looks:

- The correct translation is identical to the `msgid` -> leave the `msgstr` EMPTY. It is done, NOT
  residual, never counted as untranslated.
- Otherwise -> write the translation.

Example: `ID` translates to `ID` in almost every language -> leave it empty; `Identification` is
translatable (Vietnamese: `Định danh`) -> write it.

Never write the `msgid` into the `msgstr`, and never set a goal of zero empty `msgstr`.

## Adjudicating a removed or changed entry - THREE buckets, not two

| Bucket | Test | Ruling |
|---|---|---|
| **CORRECT** | the `msgid` no longer appears in the module source (grep / `entity_lookup` to confirm) | accept the loss |
| **ARTEFACT** | the `msgid` still exists AND the committed `msgstr` equals its `msgid` | accept the empty `msgstr` Odoo exported - never write the `msgid` back, never BLOCK |
| **WRONG** | the `msgid` still exists and the committed `msgstr` DIFFERS from it | a real accidental loss (language not loaded, wrong export scope, `auto_install` leakage) - BLOCK |

Apply the ARTEFACT test BEFORE ruling WRONG: an identity entry passes the WRONG test on its face
(the `msgid` is still in source, the translation is gone), so a two-bucket rule blocks a correct run
every time a module contains one. Adjudicate `msgid`/`msgstr` changes only - header, `#:` and
ordering differences are Odoo's export format, never edited.

Two shapes the export build produces by itself; neither is a loss and neither is a translation
choice of the run:

- **A removed entry of a record a module outside the dependency closure supplies** - a field or
  view that module adds to this module's models (a mixin field, for example). The committed file
  got it from a wider build; the isolated build of the recipe has no such record, and Odoo's own
  catalogs carry none. Ruling: CORRECT.
- **A changed `msgstr` on a record a dependency owns and translates** - the `#:` line names a model,
  field or record this module only extends. Loading a catalog never replaces a translation the
  database already holds, so the dependency's value, loaded first, is what the export reads back.
  Ruling: restore the committed `msgstr`; the run changes no translation it did not write.
- **A changed `msgid` that kept its `msgstr`.** Odoo applies a record's translation by xmlid
  without comparing the source text, so a catalog once exported from a wider build pairs this
  module's correct `msgid` with a `msgstr` translated from another module's text. Read every
  such pair: a `msgstr` that translates the previous source, not the new `msgid`, is cleared
  and translated again.

## Fuzzy and placeholders

- A `fuzzy` flag makes Odoo IGNORE the entry at load time. Clear it only after confirming or
  correcting that `msgstr`.
- The format-placeholder set in `msgstr` must equal the set in `msgid` (`%s`, `%d`, `%(name)s`,
  `{}`, `{name}`); a mismatch raises or renders wrong at runtime.
- A `.pot` is a TEMPLATE: every `msgid` present, every `msgstr` empty. Empty there carries none of
  the meaning above.
