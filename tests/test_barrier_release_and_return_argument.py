"""A coordinator's batch barrier must have a release, and a leaf must be given the REASON.

Root cause this protects, observed across two real runs: five leaf workers finished their work,
could not deliver it, and each fell back to a final message asking a human to relay - while the
`odoo-coder` coordinator that launched them sat on its batch barrier. Nothing in the plugin ever
told a leaf to message its launcher (the tool names appear zero times in the whole plugin), and the
runtime makes upward messaging impossible: the address book has no launcher entry, and the
discovery tool is stripped from every background subagent before frontmatter is consulted. So the
prose was already right, and the failures came from two other places:

1. The barrier had no release. `agents/odoo-coder.md` said to hold until every WI worker returned
   one of the four terminal statuses. A worker whose final message is a plea to relay carries NO
   status, so under that sentence it is neither terminal nor running and the barrier never clears.
   R1's STALL clause and `odoo-coding`'s dead-dispatch clause both exist, one level up each, and
   neither was restated where the WI barrier is defined.

2. The leaf was given the rule without its reason. `generator/check_orchestration.py` forbids a
   `role: leaf` body from citing any spawner-tier file, so all 24 leaves see only the short form in
   `snippets/worker-brief.md` - the rule, without the passage that names, one by one, the three
   things a worker tries when a send fails. A rule handed over without its reason is the one a
   capable model talks itself out of, and the transcripts show exactly that: each worker tried the
   `from` address, the skill name, the agent type, and a node label read out of a worklog.

Run: python -m pytest tests/test_barrier_release_and_return_argument.py -v
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
CODER = PLUGIN / "agents" / "odoo-coder.md"
TEST_WRITER = PLUGIN / "agents" / "odoo-test-writer.md"
WORKER_BRIEF = PLUGIN / "snippets" / "worker-brief.md"
R3 = PLUGIN / "snippets" / "spawner-completion-contract.md"


def _norm(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


def test_the_wi_barrier_states_its_own_release():
    """The barrier and its release must sit together. A release that lives only one level up is a
    release the coordinator does not apply - that is how the observed deadlock happened."""
    text = _norm(CODER)
    assert re.search(r"carries NO terminal `status` is STALLED", text), (
        "odoo-coder.md must classify a status-less return as STALLED, not as still-running"
    )
    for shape, why in (
        (r"re-dispatch the same WI yourself", "the coordinator must have a concrete first move"),
        (r"roll it up as your own `BLOCKED`", "and a concrete second move when it cannot"),
        (r"[Nn]ever leave it pending as if it were running",
         "the failure mode must be named, not merely the remedy"),
    ):
        assert re.search(shape, text), why


def test_a_relayed_summary_is_not_a_return():
    """The workaround the runs actually used - a human relaying the worker's text - must not be
    blessed. If a worker could not deliver, the WORK needs re-dispatching; accepting a pasted
    summary turns an unverified claim into a recorded result."""
    text = _norm(CODER)
    assert re.search(r"never accept a relayed or pasted summary in place of the return", text), (
        "the coordinator must refuse a relayed summary as a substitute for a worker's return"
    )


def test_the_leaf_is_given_the_argument_not_just_the_rule():
    """worker-brief.md is the ONLY return-path text a leaf ever reads, because the orchestration
    linter forbids a leaf body from citing the spawner-tier contract. It therefore has to carry the
    reasoning, not a pointer to it."""
    text = _norm(WORKER_BRIEF)
    assert "Three things will look like a way back up" in text, (
        "the leaf's own brief must enumerate the three look-alikes, not defer to a file it is "
        "forbidden to cite"
    )
    for shape, why in (
        (r"BRIEF, not an envelope", "(a) a launch delivers a brief, so there is no `from` to answer"),
        (r"no listing[^.]{0,60}lookup", "(b) discovery is unavailable at any depth"),
        (r"not an address book",
         "(b) and that a messaging tool in the toolset is not evidence of a reachable target"),
        (r"`main` does NOT fail|`main` is the dangerous one",
         "(c) the send that SUCCEEDS into the wrong context is the trap that costs most"),
        (r"never answered by a different name|the answer is not a different name",
         "guessing another name must be ruled out explicitly - four were tried in the real runs"),
    ):
        assert re.search(shape, text), f"worker-brief.md must state {why}"


def test_r3_does_not_rest_on_a_false_mechanism():
    """The rule was right and its stated reason was wrong: `from` carries an id that would resolve;
    the type label is a separate field. A correct rule resting on a checkable falsehood is
    overturned by the first reader who checks, so the reason had to be replaced - with the absence
    of any envelope at all, which is both true and stronger."""
    text = _norm(R3)
    assert "TYPE label, not an address" not in text, (
        "the falsified reason must be removed, not left beside its replacement"
    )
    assert re.search(r"nothing inbound to answer|no inbound message to answer", text), (
        "the corrected reason must be stated: there is no envelope, so there is no `from`"
    )
    assert re.search(r"BRIEF, not an envelope", text), (
        "and it must say WHY - a launch delivers a brief, which is the checkable fact"
    )


def test_the_commit_owner_is_stated_once_and_consistently():
    """A leftover from an earlier ownership change: odoo-test-writer.md still told workers that
    odoo-coding commits, while odoo-coder.md had already taken that over. Two agents describing the
    same handoff differently is how a worker's files end up committed twice or not at all."""
    writer = _norm(TEST_WRITER)
    assert "returns them to `odoo-coding`, which commits" not in writer, (
        "the stale commit owner must be removed from odoo-test-writer.md"
    )
    assert "COMMITS the node" in writer and "does\nnot re-commit".replace("\n", " ") in writer, (
        "odoo-test-writer.md must name the coordinator as the committer and say odoo-coding does not"
    )
    coder = _norm(CODER)
    assert "COMMIT the node" in coder, "odoo-coder.md remains the owner of the commit step"
