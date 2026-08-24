<!-- SSOT snippet. The single home for how a translator CHOOSES the wording: the three glossary
     layers and their precedence, and the independent-regime guard.
     Edit here only; consumers point at ${CLAUDE_PLUGIN_ROOT}/snippets/translation-term-policy.md.
     BOUNDARY - this file decides WHICH WORDS. What a `.po` entry MEANS (identity rule, empty-msgstr
     origins, adjudication buckets, fuzzy, placeholders) is owned by
     ${CLAUDE_PLUGIN_ROOT}/snippets/po-entry-semantics.md; what you DO and in what ORDER is owned by
     ${CLAUDE_PLUGIN_ROOT}/skills/odoo-i18n/references/i18n-recipe.md. Neither is restated here. -->

# Translation term policy (SSOT)

Consult when assembling the translation memory and when hand-translating the residual.

## Three glossary layers - in order, first canonical hit wins

1. **TM from core + deps.** The already-translated `<lang>.po` of core Odoo and of the module's
   dependency modules; reuse their `msgstr` for any recurring `msgid`. Largest and most
   authoritative term source, and it keeps a module reading like the product around it.
2. **Project glossary** - `<SHARE_DIR>/glossary.yml`: a YAML map of the domain and regulatory terms
   the project has fixed (accounting-circular terminology, product names) plus a source citation.
   A project term OVERRIDES a generic TM hit on conflict.
3. **OSM canonical field label.** For a term that maps to a model field, translate FROM Odoo's own
   UI label instead of inventing an English source:

   ```
   entity_lookup(kind='field', model='<model>', field='<field>', odoo_version='<version>')
   ```

   Use the returned `field.string` as the canonical term, so the translation matches what the user
   actually sees on screen.

`<SHARE_DIR>` is a Tier-2 path: resolve it once per
`${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md` and substitute the captured absolute path
- never write the placeholder or a bare `.odoo-ai/` into a Read/Write/Edit. A dispatched worker
whose brief already carries `SHARE_DIR:`/`ISOLATE_DIR:` uses those literals directly and does NOT
re-run the resolver.

## Independent-regime guard

Where modules implement legally INDEPENDENT regimes - the Vietnam accounting circulars TT200 /
TT133 / TT99 are the standing example - do NOT dedup or cross-copy their translations even when the
`msgid`s look identical. Each regime's `.po` stays complete and self-standing. An incidental string
match is never a reason to share a translation across regimes, because the regimes can diverge later
and a shared entry would then be wrong in one of them with nothing to flag it.

## A term that must NOT be localised

Keeping the source wording IS a translation decision - a proper noun, protocol name, acronym,
product or vendor name. Record it in the project glossary so the next translator inherits the
decision instead of re-litigating it. How Odoo then stores such an entry, and why it comes back
blank from a re-export, is `${CLAUDE_PLUGIN_ROOT}/snippets/po-entry-semantics.md`
§ The identity rule - do not act on a blank one without reading that rule first.
