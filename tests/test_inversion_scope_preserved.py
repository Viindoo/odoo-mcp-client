"""Guard for the M9 contract-inversion checklist (12-design-final.md § M9, PR7/wave 7).

Background: wave 7 shrinks 13 shared snippets to their measured-minimum size, moving explanation
to `snippets/references/<name>.md`. The audit MEASURED that 14 specific path:line sentences change
BEHAVIOR (not merely cost) if their adjacent explanation is removed - two of them produce a HANG
(an infinite re-queue / a deadlock) rather than a cost regression, several silently destroy a
guarantee (mutual exclusion, the OOM bound, lease-leak visibility, status-enum authority, a
grounded `blocked_reason`, the teardown obligation, base-branch correctness, evidence placement,
lead-strand prevention, active-run data safety, red-before-green semantics).

`tests/fixtures/inversion_scope_checklist.json` is the checked-in SSOT for those 14 items. This
file asserts every one of their `sentences` entries survives, WHITESPACE-NORMALIZED (collapse all
runs of whitespace to one space before comparing), in its file - "verbatim" here means the exact
words and punctuation survive, not that the source markdown never rewraps a line, since a line
rewrap changes zero behavior while deleting the words does.

Red-before-green proof (run manually when touching this file):
    1. Temporarily delete one `sentences` entry's text from its target file.
    2. `pytest tests/test_inversion_scope_preserved.py -v` -> the corresponding parametrized case
       goes RED, naming the missing item.
    3. Restore the text -> GREEN again.

Run: python -m pytest tests/test_inversion_scope_preserved.py -v
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN = REPO_ROOT / "plugins" / "odoo-ai-agents"
CHECKLIST_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "inversion_scope_checklist.json"


def _load_checklist() -> list[dict]:
    data = json.loads(CHECKLIST_FIXTURE.read_text(encoding="utf-8"))
    return data["items"]


def _normalize(s: str) -> str:
    return " ".join(s.split())


CHECKLIST = _load_checklist()

# Flatten to (item_id, file, sentence_index, sentence) so each sentence is its own parametrized
# case - a file with 3 sub-ranges (resource-teardown-contract.md) gets 3 independent RED/GREEN
# signals instead of one case masking the other two.
CASES = [
    (item["id"], item["file"], idx, sentence)
    for item in CHECKLIST
    for idx, sentence in enumerate(item["sentences"])
]


def test_checklist_fixture_loads_and_has_14_items():
    """Discovery floor - a broken/truncated fixture would silently make every case below
    vacuous (0 params = 0 assertions = green for the wrong reason)."""
    assert len(CHECKLIST) == 14, f"expected 14 checklist items, found {len(CHECKLIST)}"
    assert len(CASES) >= 14, f"expected >=14 flattened sentence cases, found {len(CASES)}"


@pytest.mark.parametrize(
    "item_id,relpath,idx,sentence",
    CASES,
    ids=[f"item{c[0]}-{Path(c[1]).name}-{c[2]}" for c in CASES],
)
def test_checklist_sentence_survives(item_id, relpath, idx, sentence):
    p = PLUGIN / relpath
    assert p.is_file(), f"checklist item {item_id} names a missing file: {relpath}"
    text = p.read_text(encoding="utf-8")
    assert _normalize(sentence) in _normalize(text), (
        f"checklist item {item_id} ({relpath}): the behavior-critical sentence did not survive "
        f"verbatim (whitespace-normalized) - {sentence!r} is missing. This sentence is the "
        f"documented reason a trim of this file does not regress to a hang/deadlock/silent "
        f"guarantee loss (see tests/fixtures/inversion_scope_checklist.json's 'hazard' field for "
        f"this item)."
    )
