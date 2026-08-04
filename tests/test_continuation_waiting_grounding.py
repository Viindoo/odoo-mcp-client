"""Behavior gate for D8 (V1b Q2): the Continuation Contract's "waiting" ban was textually
decidable but mechanically unenforceable, and V1b constructed a vacuous-but-compliant
`blocked_reason` that satisfied every literal clause of the ban while telling the receiving
coordinator nothing actionable:

    Made some progress but hit a snag.

    produced: []
    ```continuation
    status: BLOCKED
    produced: []
    next: []
    blocked_reason: I am waiting on missing information to proceed; the coordinator can unblock
    this by providing more context; the caller should re-brief me with additional detail.
    ```

`status` was not the literal string `waiting`, a `continuation` block was present, and
`blocked_reason` grammatically supplied (a) "missing information", (b) "the coordinator", and (c)
"re-brief me with additional detail" - satisfying the pre-fix rule's (a)/(b)/(c) presence check
while being pure category paraphrase: it could be copy-pasted into ANY other agent's report on ANY
other module without becoming false.

The fix adds a decidable GROUNDING requirement to `continuation-contract.md`'s "waiting" ban: each
of (a)/(b)/(c) must cite a concrete, checkable referent (a real file path, symbol, error, or
tool-call result), and names an explicit copy-paste decidability test: if the sentence would read
equally true after swapping in a different module/task, it names nothing and fails.

Run: python -m pytest tests/test_continuation_waiting_grounding.py -v
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN = REPO_ROOT / "plugins" / "odoo-ai-agents"
CONTINUATION_CONTRACT_MD = PLUGIN / "snippets" / "continuation-contract.md"

# The verbatim constructed message from phase4-verify/11-v1b-ambiguous-returns.md Q2.
V1B_CONSTRUCTED_BLOCKED_REASON = (
    "I am waiting on missing information to proceed; the coordinator can unblock this by "
    "providing more context; the caller should re-brief me with additional detail."
)

# Generic category words the constructed message relies on, and their swapped-in equivalents -
# used to mechanically demonstrate the copy-paste decidability test the fix introduces.
_GENERIC_TOKENS = ("missing information", "the coordinator", "more context", "additional detail")


def _norm(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_waiting_ban_requires_a_concrete_checkable_referent():
    """The ban must require each of (a)/(b)/(c) to cite a concrete referent (file/symbol/error/
    tool-call result) - not merely be present as a clause."""
    low = _norm(CONTINUATION_CONTRACT_MD).lower()
    assert "concrete, checkable referent" in low, (
        "continuation-contract.md must require each of (a)/(b)/(c) to cite a concrete, checkable "
        "referent, not just be present as a grammatical clause"
    )
    assert "generic paraphrase" in low, (
        "the ban must explicitly name and forbid the generic-paraphrase failure mode the V1b "
        "message exploited"
    )


def test_waiting_ban_states_the_copy_paste_decidability_check():
    """The fix's decidability check - would the sentence read equally true after swapping in a
    different module/task - must be stated explicitly, since it is the check that actually
    distinguishes a grounded blocked_reason from a vacuous one."""
    low = _norm(CONTINUATION_CONTRACT_MD).lower()
    assert "copy-paste" in low, (
        "the ban must name the copy-paste decidability check explicitly"
    )
    assert "swap" in low or "swapping" in low, (
        "the check must describe swapping in a different module/task/caller as the test"
    )
    assert "names nothing" in low, (
        "the check must state plainly that a sentence surviving the swap unchanged names nothing"
    )


def test_v1b_constructed_message_no_longer_satisfies_the_ban():
    """Defeat the verbatim V1b message: apply the copy-paste decidability check by hand against
    the constructed blocked_reason and confirm it fails - every generic token in the message can
    be verified to survive a swap (module/task-agnostic), which is exactly the condition the fixed
    rule calls a protocol violation."""
    rule_text = _norm(CONTINUATION_CONTRACT_MD).lower()
    # The rule's own check must be present (guards against the rule regressing away).
    assert "concrete, checkable referent" in rule_text and "copy-paste" in rule_text

    reason = V1B_CONSTRUCTED_BLOCKED_REASON
    # Reproduce the copy-paste test mechanically: does the reason contain even ONE concrete
    # referent (a file path, a dotted/underscored symbol, a quoted error) as opposed to only the
    # generic category tokens the message actually uses? A grounded reason would contain a `/` or
    # `.py`/`.js`/`.xml` path fragment, a `snake_case`/`CamelCase` symbol, or a quoted literal; this
    # message contains NONE of those - only the generic tokens below.
    has_path_like_fragment = any(tok in reason for tok in ("/", ".py", ".js", ".xml", "`"))
    generic_hits = [tok for tok in _GENERIC_TOKENS if tok in reason]

    assert not has_path_like_fragment, (
        "sanity check on the fixture itself: the V1b message must contain no path/symbol-like "
        f"referent for this test to be meaningful; reason={reason!r}"
    )
    assert generic_hits == list(_GENERIC_TOKENS), (
        "sanity check on the fixture itself: the V1b message's clauses must be pure generic "
        f"category paraphrase; found={generic_hits!r}"
    )
    # Therefore: under the fixed rule, this message fails the concrete-referent requirement - it
    # has (a)/(b)/(c) as grammatical clauses but zero grounded referents, and would read equally
    # true against any other module/task (the swap test). This is the fix's verdict, demonstrated
    # against the exact verbatim string from the lane report - not a paraphrase of it.
    verdict_grounded = has_path_like_fragment
    assert verdict_grounded is False, (
        "V1B constructed message must be judged UNGROUNDED (fails the fixed ban) - "
        f"reason={reason!r}"
    )
