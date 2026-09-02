"""The run's ownership identity must reach every descendant that can acquire a lease.

Root cause this protects: `run_id` IS the ownership identity across the lease registry - it is
what a release is authorised against, what the SubagentStop teardown gate correlates a live lease
to, and what a leak audit matches on. Nothing generated it wrongly; the chain that carries it down
simply had no link at the bottom:

- the universal dispatch skeleton had no `RUN_ID` field at all. The value travelled only INSIDE
  `INSTANCE_HANDLE`, itself a conditional rider - so a brief saying `none provisioned` carried no
  run id whatsoever;
- the leaf carve-out permitting self-provisioning fired precisely `when handed NO INSTANCE_HANDLE`,
  i.e. exactly the state in which no run id had been forwarded, while the skill it then invokes
  demands a mandatory `RUN_ID` field. The only escapes were invent or block, and nothing said
  block.

A grandchild in that position minted `upgrade-18-two-modules-a-red-oracle-b14-20260830` while the
run's real id was `upgrade-18-two-modules-20260830-k3n8`. The audit caught it only because the two
strings happened to share a prefix - a coincidence, not a mechanism.

Run: python -m pytest tests/test_run_id_ownership_chain.py -v
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
DISPATCH = PLUGIN / "snippets" / "dispatch-brief.md"
WORKER = PLUGIN / "snippets" / "worker-brief.md"
SPINUP = PLUGIN / "scripts" / "setup-steps" / "50-instance-spinup.sh"
ALLOCATOR = PLUGIN / "scripts" / "lib" / "allocator.py"


def _norm(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


def test_the_brief_skeleton_carries_the_run_id_itself():
    """Not as a passenger inside a conditional field. The whole defect is that `INSTANCE_HANDLE:
    none provisioned` is a legal brief which nonetheless carries no owner, and the agents allowed
    to self-provision are the ones that get exactly that brief."""
    text = _norm(DISPATCH)
    assert re.search(r"\| 11 \| `RUN_ID` \|", text), (
        "dispatch-brief.md must carry RUN_ID as a skeleton field of its own"
    )
    row = text[text.index("| 11 | `RUN_ID` |"):][:1200]
    assert "NEVER invents" in row or "never invents" in row, (
        "the row must forbid inventing the value - that is the observed failure, not a hypothetical"
    )
    assert "NEEDS_CONTEXT(RUN_ID)" in row, "and must name the exit when it is absent"


def test_the_self_provision_carve_out_requires_an_owner():
    """`no handle` must stop meaning `no owner`. The carve-out fires exactly where the run id is
    most likely missing, so it is the one place the precondition has to be stated."""
    text = _norm(WORKER)
    assert "no handle does not mean no owner" in text, (
        "worker-brief.md must break the inference that produced the invented id"
    )
    assert "NEEDS_CONTEXT(RUN_ID)" in text, "and name the exit a leaf takes instead of inventing"
    assert re.search(r"invented id is worse than none", text), (
        "the reason has to be stated: an invented id LOOKS owned to the registry while being "
        "invisible to the only run that could release it, so it survives every audit"
    )


def test_the_allocator_refuses_rather_than_recording_an_ownerless_lease():
    src = ALLOCATOR.read_text(encoding="utf-8")
    assert '"--allow-unowned": "allow_unowned"' in src, "the deliberate opt-out must exist"
    assert re.search(r"if not run_id and not opts\.get\(\"allow_unowned\"\)", src), (
        "acquire must refuse an ownerless lease unless the caller declares it wants one"
    )
    assert "10 REFUSED: no --run-id and no --allow-unowned" in src, (
        "the exit code must be documented in the same table as its siblings"
    )
    assert "today's behavior" not in src, (
        "the comment calling the unowned default 'today's behavior' must go with the behaviour it "
        "described - a provisional note left beside its own replacement is how prose rots"
    )


def test_the_one_production_caller_that_wants_an_ownerless_lease_says_so():
    """A shared lease legitimately outlives its acquirer - many readers across sessions, and
    `drop_on_release` false. That caller must DECLARE it rather than inherit it by omission, or
    the refusal would simply have broken a working path."""
    src = SPINUP.read_text(encoding="utf-8")
    assert "args+=(--allow-unowned)" in src, (
        "50-instance-spinup.sh must declare the ownerless shared lease it deliberately takes"
    )
    assert re.search(r"INST_RUN_ID.*\n.*args\+=\(--run-id", src) or "--run-id \"${INST_RUN_ID}\"" in src, (
        "and must still prefer a real owner whenever the caller supplied one"
    )
