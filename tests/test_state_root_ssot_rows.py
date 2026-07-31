"""Guard: the two new Tier-2 ISOLATE rows this PR adds (`recon/<slug>-<date>/`,
`visual/current/<slug>/`) are declared in the ISOLATE table (not merely somewhere in the
file), the bucket section no longer sanctions the visual-regression comparison set as SHARE,
and the visual/ split note's "FOUR sibling" claim matches an actually-enumerated count of four.

Genre A on all three axes: each assertion slices a NAMED heading-bounded region and asserts
membership, absence, or a computed count inside THAT region, so a row added to the wrong
table, a defence sentence reinstated, or a count claim that drifts from the real list all go
red. Whitespace is normalized before every literal search because the file is hard-wrapped at
~100 columns and any phrase longer than a few words straddles a newline.

Each test below is labeled PROSE-PRESENCE (checks a literal substring inside a named region -
the weaker, spec-proposed form) or STRUCTURAL/COMPUTED (slices a narrower sub-region or counts
regex matches, so it also catches a phrase landing in the wrong bucket/row - something a
whole-section substring check cannot see).
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE_ROOT = ROOT / "plugins" / "odoo-ai-agents" / "snippets" / "state-root-resolution.md"
_WS = re.compile(r"\s+")


def _text() -> str:
    return STATE_ROOT.read_text(encoding="utf-8")


def _norm(s: str) -> str:
    return _WS.sub(" ", s)


def _region(text: str, start_heading: str, end_heading: str) -> str:
    a = text.index(start_heading)
    b = text.index(end_heading, a + len(start_heading))
    return text[a:b]


def test_new_isolate_rows_are_declared_in_the_isolate_table():
    """STRUCTURAL: both new subpaths must live in the ISOLATE table region, not the SHARE one.

    This is the assertion that catches a row added to the wrong table - the single
    most consequential mistake available in this file."""
    text = _text()
    isolate = _region(text, "## Tier-2 ISOLATE list", "## Codemod guards")
    share = _region(text, "## Tier-2 SHARE list", "## Tier-2 ISOLATE list")
    for row in ("recon/<slug>-<date>/", "visual/current/<slug>/"):
        assert row in isolate, f"{row} must be a row in the Tier-2 ISOLATE table"
        assert row not in share, f"{row} must NOT appear in the Tier-2 SHARE table"


def test_bucket_one_no_longer_sanctions_the_comparison_set_as_share():
    """PROSE-PRESENCE (spec-proposed): bucket 1 must not name the comparison set, and the
    defence sentence that kept it sanctioned must be gone - while bucket 3's
    committed-deliverable sentence survives (it shared a source line with the defence, so a
    line-level delete would clip it)."""
    buckets = _norm(_region(
        _text(),
        "## Where a captured artifact goes",
        "## The resolve-capture-substitute protocol",
    ))
    assert "Bucket 1 explicitly names" not in buckets, (
        "the bucket-1 defence of current/-as-SHARE must be deleted"
    )
    assert "comparison set) ->" not in buckets and "their `current/` comparison set" not in buckets, (
        "bucket 1 must no longer name the visual-regression comparison set"
    )
    assert "state-B comparison set" in buckets, (
        "bucket 2 must name the run-scoped comparison set"
    )
    assert "Bucket 3 keeps the committed-deliverable pipeline intact" in buckets, (
        "bucket 3's sentence must survive the bucket-1 deletion (shared source line)"
    )


def test_bucket_one_and_two_sub_regions_are_precise_not_just_section_wide():
    """STRUCTURAL/COMPUTED: slice EACH numbered bucket's own sub-region (bucket 1 stops at the
    start of bucket 2; bucket 2 stops at the start of bucket 3) rather than the whole
    three-bucket section, so a phrase merely present SOMEWHERE in the section (e.g. accidentally
    left in the wrong bucket) cannot satisfy this test. Also asserts the section still contains
    exactly 3 numbered buckets - a computed count, not a literal-string check."""
    section = _region(
        _text(), "## Where a captured artifact goes", "## The resolve-capture-substitute protocol",
    )
    bucket_1 = _norm(_region(section, "1. **Reusable across runs**", "2. **Run-scoped**"))
    bucket_2 = _norm(_region(section, "2. **Run-scoped**", "3. **A committed"))

    assert "current/" not in bucket_1, (
        "bucket 1's OWN sub-region must not name the current/ comparison set "
        f"(bucket 1 text: {bucket_1!r})"
    )
    assert "BASELINES" in bucket_1, "bucket 1 must still name the reusable baselines"
    assert "state-B comparison set" in bucket_2, (
        "the state-B comparison set must live in bucket 2's OWN sub-region, not merely "
        "somewhere in the three-bucket section"
    )

    # Computed: the section must enumerate exactly 3 buckets (no bucket silently dropped or
    # duplicated by the edit).
    bucket_markers = re.findall(r"^\d+\. \*\*", section, flags=re.MULTILINE)
    assert len(bucket_markers) == 3, (
        f"expected exactly 3 numbered buckets, found {len(bucket_markers)}"
    )


def test_visual_split_note_enumerates_four_owned_evidence_subpaths():
    """PROSE-PRESENCE (spec-proposed) + STRUCTURAL/COMPUTED. The split note is the file's only
    statement of how many sibling evidence subpaths exist and who owns each. First assert the
    literal COUNT claim and the four owner/path pairs (spec's own form). Then, independently,
    regex-extract every `` `visual/<path>` (`<owner>`) `` pair actually written in the note and
    assert the COMPUTED count equals 4 - so a stale "FOUR" that no longer matches the real
    enumerated list (e.g. a 5th pair added without updating the word) goes red on the count
    itself, not just on the literal word."""
    note = _norm(_region(_text(), "**Note the split inside", "## Codemod guards"))
    for path, owner in (
        ("visual/screenshots/<slug>/", "odoo-ui-reviewer"),
        ("visual/current/<slug>/", "odoo-visual-regression"),
        ("visual/qa/<slug>/<module>/", "odoo-qa-tester"),
        ("visual/debug/<slug>/", "odoo-ui-debugger"),
    ):
        assert path in note and owner in note, f"split note must pair {path} with {owner}"
    assert "FOUR sibling" in note, "the split note must state the count as FOUR"

    # STRUCTURAL/COMPUTED: count the actual (path, owner) pairs in the note text, independent
    # of the word "FOUR" itself.
    pairs = re.findall(r"`(visual/[^`]+)`\s*\(`([^`]+)`\)", note)
    assert len(pairs) == 4, (
        f"the split note's word 'FOUR' must match an ACTUAL count of 4 (path, owner) pairs; "
        f"found {len(pairs)}: {pairs}"
    )
