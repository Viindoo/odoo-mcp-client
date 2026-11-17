# Vendor facts (brand, stores)

The vendor's brand palette, its logo and the store pages that list its modules are facts of the
vendor: never invented, never copied from another vendor's module. The context that talks to the
human resolves each one the task needs, first source that answers:

1. the user's words or the brief;
2. what the project or the machine already records: `<SHARE_DIR>/brand-tokens.json` (the
   palette), the author profile (`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/lib/author_profile_config.py show`:
   the vendor name, `font_file`, and `module_page_url` - the pattern of a module's page on the
   vendor's own store);
3. your persistent memory, when your runtime has one;
4. one question to the human, with a candidate when the vendor's other modules show one; the
   confirmed answer, "none" included, is saved to that memory so no later session asks again.

| Fact | Shape | Used by |
|---|---|---|
| Brand palette | one hex per role the vendor states (below) | the App Store page, the store cover, the module icon |
| Logo | a file, or a public image URL pinned to an immutable revision | the App Store page, the store cover |
| Store pages | one URL pattern per store that lists the vendor's modules, with the series and the module name (the Odoo Apps Store, the vendor's own store) | the links in a published video's description |

## The palette is roles

| Role | It colours |
|---|---|
| `primary` | the vendor's identity: the largest coloured field, the headings and marks that carry the brand |
| `secondary` | the accent: small areas beside the primary, never the largest field |
| `success`, `warning`, `danger`, `info` | a state of that meaning and nothing else, never decoration |
| `heading`, `body`, `muted`, `background` | text and surfaces |

Take each role from the source as the source names it: a token map such as `brand-tokens.json`
is CSS custom-property name -> colour, and the role is the meaning of the name (a name ending in
`primary` is `primary`). A role the source does not state stays absent, never derived from
another colour; colours given with no role (two hex values, a logo) do not say which one is
`primary`, so that is asked (source 4). On a coloured field a display line (a cover's product
name, a page's headline: large and heavy) is white; smaller text is white or the `heading`
colour, whichever contrasts more.

In a brief the palette travels as `BRAND: <role>=<hex> ...; logo=<file or URL>`. A consumer uses
the roles its own contract names and takes that contract's default for an absent one.

A subagent never asks: the resolved values travel in its brief. No human to ask: the work takes
the default its own contract names (the Odoo palette, the vendor name as text, no store link) and
reports the gap.
