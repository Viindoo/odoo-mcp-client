<!-- SSOT snippet. RST-validity contract for every third-party `doc/*.rst` an agent writes
     (currently `agents/odoo-user-doc-writer.md`). Referenced (not copy-pasted) by any writer
     of Odoo module end-user documentation. Edit here only; consumers point at
     ${CLAUDE_PLUGIN_ROOT}/snippets/rst-validity-contract.md. -->

# RST-Validity Contract

Every `doc/*.rst` file you write is rendered by a PLAIN docutils reader - there is no Sphinx
build step anywhere in this pipeline. A file that only renders under Sphinx-specific roles or
directives is BROKEN here, even if it looks correct in an editor that assumes a Sphinx project.
Follow every rule below when you author or edit a `doc/*.rst` file. This contract is enforced
mechanically - see `agents/odoo-user-doc-writer.md` Step 4.5 (the mandatory docutils
self-verify gate): a doc that violates any rule below fails that gate and blocks the agent's
return until it is fixed.

## 1. No Sphinx-only roles

NEVER emit `:ref:`, `:menuselection:`, or `:guilabel:`. Plain docutils has no interpreted-text
role of that name - each one renders as an "Unknown interpreted text role" `system_message`
error under the standalone reader. Use the plain-text equivalents in rules 2 and 3 instead.

## 2. Menu paths - bold text plus the TRIANGULAR BULLET separator

Write a menu path as a single bold-text span with each step separated by the Unicode
character at code point **U+2023 (TRIANGULAR BULLET)** - not `:menuselection:` (banned by
rule 1), not a plain `>`, and not `->`. Example shape (the separator character itself is
named here by code point per this repo's ASCII-output convention; you literally TYPE the
U+2023 glyph into the `doc/*.rst` file you are writing - the file is a third-party
deliverable, not this contract's own prose):

```
**Sales [U+2023] Orders [U+2023] New**
```

Read `[U+2023]` above as an instruction to insert the actual TRIANGULAR BULLET character at
that position - it is not literal bracket-and-text to copy.

## 3. Cross-references - plain text or an external hyperlink, never an internal reference

Plain docutils resolves `` `Title`_ `` only when a matching internal target (a `.. _Title:`
line) exists in the SAME document. A `doc/*.rst` file that points `` `Title`_ `` at a section
in ANOTHER file renders an "Unknown target name" `system_message`. Use one of:

- Plain prose naming the target ("see the Configuration section above" or "see the
  <module> documentation"), or
- An external hyperlink with a real URL: `` `link text <https://example.com/...>`_ ``.

NEVER use `:ref:` (banned by rule 1) and never use an internal `` `Title`_ `` reference that
crosses a file boundary - internal references stay inside their own document.

## 4. Titles - underline-only, exact length

Every title (top-level or subsection) is underline-only - no overline. Use a consistent
hierarchy of underline characters, e.g. `=` for the top level, `-` for the next, `~` below
that. The underline length MUST equal the EXACT Unicode character count of the title text
above it - count characters, not bytes, and count every accented letter or non-ASCII glyph
(including a TRIANGULAR BULLET if one appears in a title) as exactly one character. A short
or long underline is a docutils "Title underline too short" `system_message`.

## 5. Blank lines around structure

- A blank line follows every title underline before the next line of body text.
- A blank line precedes AND follows every block (an image directive, a note directive, a
  code block, a literal block) and every list (bullet, enumerated, or definition). Docutils
  treats a list or directive glued directly to the preceding paragraph as a syntax error or
  a silently-wrong nested structure - always isolate each one with a blank line on both
  sides.

## 6. List continuation across an interrupting block

When a list is interrupted by a non-list block (an image, a note, a paragraph) and then the
list resumes, the resumed item MUST use the `#.` auto-enumerator - never a literal digit -
so docutils treats it as a CONTINUATION of the same list rather than a new list restarting
at 1. A literal digit after an interruption breaks the numbering and can split one list into
two.

## 7. Inline literals - double backtick only

Any inline literal (a field value shown as code-like text, a button caption, a file name)
uses DOUBLE backticks: `` ``like this`` ``. A single backtick invokes Sphinx's default-role
behavior, which is undefined in plain docutils and renders inconsistently. NEVER use a
single backtick for an inline literal.

## 8. vi_VN second person - "ban", no honorifics

Every Vietnamese-locale doc (`doc/index_vi_VN.rst` and any other vi_VN Odoo doc) addresses
the reader with the neutral second-person pronoun "ban" - NEVER an age/rank/gender honorific
such as "anh", "chi", "quy khach", or "ong/ba". This keeps guide tone consistent regardless
of the reader's age, gender, or seniority. This rule governs the vi_VN locale specifically;
other locales follow their own natural second-person form. As with rule 2's TRIANGULAR
BULLET, every Vietnamese word above ("ban", "anh", "chi", "quy khach", "ong/ba") is spelled
here in de-accented ASCII only because this contract's OWN prose follows the repo's
ASCII-output convention - it is not the literal spelling to copy. When you write the actual
`doc/*.rst` deliverable, TYPE the real Vietnamese Unicode diacritics for every one of these
words exactly as real vi_VN orthography requires; the ASCII convention governs this contract
file, never the third-party deliverable you write.

## 9. Why this is a hard gate, not a lint nitpick

A `doc/*.rst` that violates any rule above is not a style preference - it is a file a real
RST renderer refuses to render cleanly, shipping a visibly broken page to an end user.
`agents/odoo-user-doc-writer.md` Step 4.5 enforces this contract mechanically: it renders
every `doc/*.rst` it writes through docutils `publish_programmatically` (standalone reader,
`restructuredtext` parser, `pseudoxml` writer, `report_level=1`, `halt_level=5`) and requires
`document.findall(nodes.system_message)` to be empty before the agent may return. Any
non-empty result means the file broke one of rules 1-7 above (rule 8 is a tone rule docutils
cannot check; verify it by inspection).
