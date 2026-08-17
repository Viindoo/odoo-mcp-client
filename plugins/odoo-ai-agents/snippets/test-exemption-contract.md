<!-- SSOT snippet. The single declaring file for `TEST_EXEMPTION` - the ONE sanctioned escape from
     red-before-green, which `test-first-contract.md` owns and which stays the default. Referenced
     (not copy-pasted) by odoo-coding (declares it per node), odoo-coder (declares it per
     work-item), odoo-backend-coder / odoo-frontend-coder (receive and verify it). Edit here only;
     consumers point at ${CLAUDE_PLUGIN_ROOT}/snippets/test-exemption-contract.md. -->

# Test-Exemption Contract (the only escape from red before green)

Test-first is the default and stays the default: a change to BEHAVIOR with no RED test is refused.
But some real work cannot go red at all, because it alters nothing a test can observe. For exactly
that work the CALLER declares an exemption. A receiver NEVER infers one from a missing, empty, or
unresolvable field - an absent declaration is a refusal, not a licence.

## The declaration

`TEST_EXEMPTION: <category> - <what specifically cannot go red>`

- Declared by the CALLER that fills the brief (`odoo-coding` per node, `odoo-coder` per
  work-item), on the same brief that carries `RED_TEST_PATH`.
- `TEST_EXEMPTION: none` and an absent key mean the SAME thing: no exemption. That is the safe
  value, and it is what every brief that says nothing about testability means.
- Closed category set - a value outside it is not an exemption:
  - `comment-only` - only comments and docstrings change.
  - `prose-rename` - a name changes only inside comment or doc prose; every declared symbol, XML
    id, external id, selector, CSS class, and msgid keeps its spelling.
  - `formatting` - whitespace, indentation, or ordering only; the parsed tree is unchanged.
  - `docs` - files no Odoo runtime loads (`README`, `doc/*.rst`, `static/description` prose).
  - `translation-text` - a `.po`/`.pot` msgstr edit; msgid, code path, and record data unchanged.
- MALFORMED IS ABSENT. A bare `TEST_EXEMPTION:`, a category outside the set, or a category with no
  specifics clause carries no exemption and the gate fires. Never repair a malformed value by
  guessing which category the caller meant - ask for the declaration instead.
- A `RED_TEST_PATH` that resolves WINS: implement to that test. An exemption never cancels a test
  that exists and never authorises editing one.

## The receiver verifies the claim against what it actually writes

A declaration is a claim about the change, not a licence to write anything. Before writing, name
the category and the exact file set it covers, and write nothing outside that set. The exemption is
VOID the moment the work needs one edit a runtime can observe - a selector, rule value, default,
domain, method signature, msgid, external id, security rule, manifest key, or an asset the loader
reads. On a void exemption, write no behavioural line and refuse: that change needs a RED test
after all, so the caller must launch `odoo-test-writer` first.

## Refusing is loud

Every refusal here - an absent or malformed declaration with no test, an unresolvable
`RED_TEST_PATH`, or an exemption voided mid-work - is a FULL report, never a near-empty message:
prose summary, a `produced` list naming what you genuinely wrote (your worklog entry at minimum -
`[]` only when you truly wrote nothing), and the terminal `continuation` block carrying `status: BLOCKED` and
a `blocked_reason` that names the field plus the concrete referent that failed (the path you read
and could not open, the category string you were handed, the specific edit that voided the
exemption). Shape and rules: `${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md`. A
near-empty return is indistinguishable from silence and strands the caller with no way to tell a
refusal from a success.
