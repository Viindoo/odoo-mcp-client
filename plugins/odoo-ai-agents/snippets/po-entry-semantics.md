<!-- SSOT snippet. The single home for what a `.po`/`.pot` ENTRY MEANS - the format-and-Odoo FACTS
     every translation consumer must agree on: the identity rule, the two origins of an empty
     `msgstr`, the three adjudication buckets, the residual rule, fuzzy, placeholders.
     Edit here only; consumers point at ${CLAUDE_PLUGIN_ROOT}/snippets/po-entry-semantics.md.
     BOUNDARY - this file says what an entry MEANS. What you DO and in what ORDER (install, load,
     export, diff-review, the commit gates) is owned by
     ${CLAUDE_PLUGIN_ROOT}/skills/odoo-i18n/references/i18n-recipe.md; how you CHOOSE the wording is
     owned by ${CLAUDE_PLUGIN_ROOT}/snippets/translation-term-policy.md. Neither is restated here. -->

# PO entry semantics (SSOT)

## The identity rule - Odoo never exports a translation equal to its source

**A translation identical to its source string is written as an EMPTY `msgstr`.** That is Odoo's
convention, not a defect and not a lost string. Grounded at source rather than inferred: in
`odoo/tools/translate.py`, `PoFileWriter.write_rows` takes the translation only when `trad != src`,
then writes `''` for every entry left unassigned. Verified identical in v15, v16, v17, v18 and v19
(read 2026-08-24). It is the EXPORT leg that drops the entry, so no import fix can preserve it.

A term deliberately NOT localised - a proper noun, protocol name, acronym, product or vendor name
(`ID`, `URL`, `AI`, `Model`, `Chat`, `Access Token`, `Streamable HTTP`) - therefore returns from
EVERY re-export as `msgstr ""`, no matter how carefully it was translated before.

## An empty `msgstr` has TWO origins - never merge them

| Origin | What it is | What to do |
|---|---|---|
| **NEW** | the `msgid` is new or changed in source; nobody has translated it | translate it |
| **ARTEFACT** | the entry already existed and its translation EQUALS the source, so the export blanked it | restore the committed entry; do NOT translate it again |

The committed `.po` is what tells them apart: empty in the re-export but PRESENT in the committed
file = ARTEFACT; absent from both = NEW. One measured module (Odoo 17) came back with 31 blanked
entries, all 31 identity, none a real loss. Reacting to the aggregate would have re-translated all
31 - and hidden a genuine loss among them.

## Adjudicating a removed or changed entry - THREE buckets, not two

| Bucket | Test | Ruling |
|---|---|---|
| **CORRECT** | the `msgid` no longer appears in the module source (grep / `entity_lookup` to confirm) | accept the loss |
| **ARTEFACT** | the `msgid` still exists AND the committed `msgstr` equals its `msgid` | expected round-trip loss - restore the committed entry silently, never BLOCK |
| **WRONG** | the `msgid` still exists and the committed `msgstr` DIFFERS from it | a real accidental loss (language not loaded, wrong export scope, `auto_install` leakage) - BLOCK |

Apply the ARTEFACT test BEFORE ruling WRONG: an identity entry passes the WRONG test on its face
(the `msgid` is still in source, the translation is gone), so a two-bucket rule blocks a correct run
every time the module contains one. Adjudicate `msgid`/`msgstr` changes only - header timestamps,
`#:` reference-comment churn and entry reordering are export-format noise.

## The residual rule

The residual to translate is the NEW bucket only, plus any entry a WRONG ruling restored. An
ARTEFACT blank is NOT residual. An `msgstr` equal to its `msgid` is a REVIEWED DECISION - a term
that must not be localised - never missing work: do not empty it, do not re-translate it, and never
let an "untranslated count" report it as debt.

## Fuzzy and placeholders

- A `fuzzy` flag makes Odoo IGNORE the entry at load time. Clear it only after confirming or
  correcting that `msgstr`.
- The format-placeholder set in `msgstr` must equal the set in `msgid` (`%s`, `%d`, `%(name)s`,
  `{}`, `{name}`); a mismatch raises or renders wrong at runtime.
- A `.pot` is a TEMPLATE: every `msgid` present, every `msgstr` empty. Empty there carries none of
  the meaning above.
