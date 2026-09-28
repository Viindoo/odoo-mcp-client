<!-- SSOT snippet. What a `.po`/`.pot` ENTRY MEANS: the identity rule, the empty-`msgstr` rule,
     the three adjudication buckets, fuzzy, placeholders. Consumers point at
     ${CLAUDE_PLUGIN_ROOT}/snippets/po-entry-semantics.md. What you DO and in what ORDER (build,
     export, keep the export format, diff-review) is
     ${CLAUDE_PLUGIN_ROOT}/skills/odoo-i18n/references/i18n-recipe.md; which WORDS is
     ${CLAUDE_PLUGIN_ROOT}/snippets/translation-term-policy.md. Neither is restated here. -->

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

## Fuzzy and placeholders

- A `fuzzy` flag makes Odoo IGNORE the entry at load time. Clear it only after confirming or
  correcting that `msgstr`.
- The format-placeholder set in `msgstr` must equal the set in `msgid` (`%s`, `%d`, `%(name)s`,
  `{}`, `{name}`); a mismatch raises or renders wrong at runtime.
- A `.pot` is a TEMPLATE: every `msgid` present, every `msgstr` empty. Empty there carries none of
  the meaning above.
