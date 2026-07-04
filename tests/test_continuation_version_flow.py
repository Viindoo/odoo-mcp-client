"""Guard: odoo_version must survive a Continuation Contract hop into a coding-chain skill.

Business rule (SCHEMA-2 / F4): a plan/design resolves ONE concrete Odoo version for a run: if a
`next:` hand-off from one skill's Continuation Contract into a code/test/review skill
(`odoo-coding`, `odoo-code-review`, `odoo-test-writing`, `odoo-wave`) drops `odoo_version` from its
`inputs`, the next skill has to re-derive the version instead of trusting the one already resolved
- silent re-derivation is exactly the drift SCHEMA-2 exists to prevent. `odoo_version` is therefore
a RESERVED `inputs` key (`snippets/continuation-contract.md`), not a suggestion.

Two independent assertions:

(a) SSOT-presence (robust). `continuation-contract.md` still documents `odoo_version` as a
    RESERVED `inputs` key for a hop into one of the four coding-chain skills. This guards F4 itself
    against silent removal, independent of any single skill file's wording.

(b) Behavioral (scoped to real payload-bearing hops). Scanning is paragraph-based, not
    fenced-block-only: an earlier design assumed every coding-chain hop is emitted as a fenced
    ```continuation block with `next: <skill>`, but a live read of the four skill files
    (2026-07) found the opposite - the fenced `next:` blocks in `odoo-code-review/SKILL.md` and
    `odoo-wave/SKILL.md` target `odoo-acceptance` (not a coding-chain skill), and the ONE hop that
    actually carries a payload into the coding chain (`odoo-coding/SKILL.md`'s
    "emit `next: odoo-code-review` with `inputs: {odoo_version: ...}`") is plain PROSE, not a
    fenced block. A fenced-only scan would therefore match zero hops and pass vacuously - it would
    never go red no matter what got deleted. Instead: split each coding-chain SKILL.md into
    blank-line-separated paragraphs; a paragraph counts as a real hop-with-payload only when it
    mentions BOTH `next:` and `inputs:` together with one of the four coding-chain skill names (a
    bare mention of `next: odoo-code-review` with no `inputs:` payload nearby - e.g. the "drive it
    yourself" prose in odoo-coding/SKILL.md that only says whether to emit or double-dispatch - is
    not a data hand-off and must not be flagged). Every such paragraph must also contain
    `odoo_version`. An explicit anti-vacuity assertion (`hits > 0`) makes the test fail loudly, not
    silently pass, if every payload-bearing hop is ever rewritten away or reworded past detection.

Prose-only mentions of a coding-chain skill with no `inputs:` payload (e.g. odoo-code-review's
"Autonomous fix loop" section, which says "carrying the report path" without a structured
`inputs:` block) fall back to assertion (a) plus review discipline - they are a real, pre-existing
gap (flagged in the delivering session's report) but out of scope for this test, which guards the
structured-`inputs:` contract SCHEMA-2 actually defines.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN = REPO_ROOT / "plugins" / "odoo-ai-agents"
CONTINUATION_CONTRACT = PLUGIN / "snippets" / "continuation-contract.md"

# The coding-chain skills named by continuation-contract.md's own "Reserved `inputs` keys" rule.
CODING_CHAIN_SKILLS = ("odoo-coding", "odoo-code-review", "odoo-test-writing", "odoo-wave")
CODING_CHAIN_FILES = [PLUGIN / "skills" / s / "SKILL.md" for s in CODING_CHAIN_SKILLS]


def _paragraphs(text: str) -> list[str]:
    """Split markdown text on blank lines - the natural unit a hop + its payload live in."""
    return re.split(r"\n\s*\n", text)


def test_odoo_version_documented_as_reserved_inputs_key():
    """SCHEMA-2/F4 must stay documented: odoo_version is a RESERVED `inputs` key, not free-form.

    Guards continuation-contract.md itself against silent removal of the F4 rule - independent of
    whether any individual skill file's wording drifts (that is assertion (b), below).
    """
    text = CONTINUATION_CONTRACT.read_text(encoding="utf-8")
    # Anchor on the heading phrase itself, not a loose "reserved"+"inputs" co-occurrence - the
    # fenced schema example above the Rules list also says "# odoo_version, viindoo_profile are
    # RESERVED - see Rules" (a forward-pointer comment, not the rule), which would otherwise be
    # picked up as a false paras[0] and hide the real enumeration that lives in the Rules bullet.
    paras = [p for p in _paragraphs(text) if "reserved" in p.lower() and "`inputs` keys" in p.lower()]
    assert paras, (
        f"{CONTINUATION_CONTRACT.relative_to(REPO_ROOT)} no longer has a 'Reserved `inputs` keys' "
        "paragraph - SCHEMA-2/F4 was removed."
    )
    reservation = paras[0]
    assert "odoo_version" in reservation, (
        "The reserved-inputs-keys rule no longer names odoo_version as reserved."
    )
    assert "RESERVED" in reservation, (
        "odoo_version is mentioned but the rule no longer marks it RESERVED (may have been "
        "downgraded to a suggestion)."
    )
    missing_skills = [s for s in CODING_CHAIN_SKILLS if s not in reservation]
    assert not missing_skills, (
        "The reserved-inputs-keys rule dropped one or more coding-chain skills from its "
        f"enumeration: {missing_skills}. A hop into a skill absent from this list is no longer "
        "covered by the F4 requirement."
    )


def test_continuation_hop_into_coding_chain_carries_odoo_version():
    """A `next:` hop that hands a payload (`inputs:`) into a coding-chain skill must carry odoo_version.

    Scoped to paragraphs that are an actual hand-off (mention `next:` AND `inputs:` together with a
    coding-chain skill name), not every prose mention of a coding-chain skill name - see module
    docstring for why a fenced-block-only scan would be vacuous here.
    """
    offenders: list[str] = []
    hits = 0
    for f in CODING_CHAIN_FILES:
        text = f.read_text(encoding="utf-8")
        for para in _paragraphs(text):
            if "next:" not in para or "inputs:" not in para:
                continue
            targeted = [s for s in CODING_CHAIN_SKILLS if s in para]
            if not targeted:
                continue
            hits += 1
            if "odoo_version" not in para:
                first_line = para.strip().splitlines()[0][:100]
                offenders.append(
                    f"{f.relative_to(REPO_ROOT)}: hop into {targeted} carries `inputs:` but no "
                    f"odoo_version - paragraph starts: {first_line!r}"
                )
    assert hits > 0, (
        "No paragraph in any coding-chain SKILL.md (odoo-coding/odoo-code-review/"
        "odoo-test-writing/odoo-wave) matched a `next:` hop with an `inputs:` payload into a "
        "coding-chain skill - this assertion has become vacuous (it would pass even if every such "
        "hop were deleted). The known site as of 2026-07 is odoo-coding/SKILL.md's "
        "'emit `next: odoo-code-review` with `inputs: {odoo_version: ...}`' paragraph; if it was "
        "intentionally reworded, update this test's matching rule rather than letting it go quiet."
    )
    assert not offenders, (
        "Continuation Contract hop(s) into a coding-chain skill drop odoo_version from their "
        "inputs payload, so the next skill must re-derive the version instead of trusting the "
        "one already resolved for the run (SCHEMA-2/F4):\n" + "\n".join(offenders)
    )
