"""Guard: a next step must ride the one channel the driver reads - the fenced continuation block.

`snippets/continuation-contract.md` makes the fenced `continuation` block the only handoff
`run-harness` reads: a status or a next step written anywhere else reaches no driver. A
recommendation an emitter writes outside that block - a bare `SUGGESTED_NEXT:` line, or a `next:`
hop placed below the block - is lost without a trace, while the skill name it carries makes any
grep for the skill look satisfied.

The design-first recommendation is the hop this matters most for: `odoo-coding` and
`odoo-data-migration` both recommend `odoo-solution-design` from a body that also emits its own
`next:` entry and a status. So every check below is keyed on the CHANNEL - is the hop an in-block
`next:` entry - not on the presence of the skill name.

A sibling guard, `test_design_precedes_planning.py`, owns the ORDER (design never after planning).
This file owns the CHANNEL (the design hop is readable at all). The two interact: a reachable
design hop is correct only on a standalone invocation, so
`test_the_design_hop_is_suppressed_under_a_plan` asserts the suppression that keeps this guard from
undoing that one.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"

#: The two design-routing emitters. Each recommends `odoo-solution-design` from a
#: body that also appends a Continuation Contract (hence always sets a status).
DESIGN_ROUTERS = {
    "odoo-coding": PLUGIN / "skills" / "odoo-coding" / "SKILL.md",
    "odoo-data-migration": PLUGIN / "skills" / "odoo-data-migration" / "SKILL.md",
}

DESIGN_SKILL = "odoo-solution-design"

_GENERATED = re.compile(
    r"<!-- BEGIN GENERATED TOOLS -->.*?<!-- END GENERATED TOOLS -->", re.DOTALL
)
_TEXT_EXTS = {".md", ".yaml", ".yml", ".json", ".sh", ".py", ".toml"}


def _read(path: Path) -> str:
    assert path.is_file(), f"{path} is missing"
    return _GENERATED.sub("", path.read_text(encoding="utf-8"))


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _tree_texts():
    for plugin_dir in sorted((ROOT / "plugins").iterdir()):
        if not plugin_dir.is_dir():
            continue
        for path in sorted(plugin_dir.rglob("*")):
            if path.is_file() and path.suffix in _TEXT_EXTS:
                yield path, path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# The off-channel detector. Pure function of text, so the probes below run the
# SAME code as the real-tree sweep.
# ---------------------------------------------------------------------------

#: Each entry is (shape, regex). No nearby wording excuses a match: the driver reads the fenced
#: block only, so prose has no reason to name a line outside it at all.
OFF_CHANNEL_SHAPES: tuple[tuple[str, re.Pattern[str]], ...] = (
    # A bare `SUGGESTED_NEXT:` line - a recommendation outside the block, in any wording.
    ("bare-suggested-next-line", re.compile(r"SUGGESTED_NEXT")),
    # A hop placed OUTSIDE the fenced block - the same loss, spelled without that token.
    ("hop-outside-the-fenced-block",
     re.compile(r"(?i)(?:outside|below|alongside|separate from) the fenced(?: `?continuation`?)?"
                r" block[^.]{0,160}?\bnext\b"
                r"|\bnext:[^.\n]{0,80}?\b(?:outside|not inside) the fenced")),
)


def find_off_channel(text: str) -> list[tuple[str, str]]:
    """Every (shape, match) that puts a next step where the driver never reads it."""
    return [(name, m.group(0)) for name, rx in OFF_CHANNEL_SHAPES for m in rx.finditer(text)]


# ---------------------------------------------------------------------------
# The two design routers: reachable channel, suppressed under a plan.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(DESIGN_ROUTERS))
def test_the_design_hop_rides_the_channel_the_driver_reads(name):
    """The design recommendation must be an IN-BLOCK `next:` entry, not the dropped bare line.

    Behaviour protected: a design-first recommendation actually reaches its reader. Fails if the
    site moves the hop outside the fenced block, or names the design skill with no in-block entry
    to carry it.
    """
    text = _read(DESIGN_ROUTERS[name])
    flat = _flat(text)

    assert "snippets/continuation-contract.md" in flat, (
        f"{name} must append a Continuation Contract - the block is the channel this test checks."
    )

    offenders = find_off_channel(text)
    assert not offenders, (
        f"{name} puts a next step outside the fenced continuation block: {offenders}. The driver "
        f"reads only the block, so that recommendation reaches nobody."
    )

    # And the design hop exists in the reachable form: a `skill: odoo-solution-design` entry.
    assert re.search(rf"`?skill:\s*\n?\s*`?{DESIGN_SKILL}", flat) or re.search(
        rf"`skill:\s*{DESIGN_SKILL}`", flat
    ), (
        f"{name} must carry the design hop as an in-block `next:` array entry "
        f"(`skill: {DESIGN_SKILL}`, with reason/inputs/confidence). Naming the skill in prose is "
        f"not a channel - the driver reads the array, not the sentence."
    )
    assert re.search(r"(?i)`?next:`?\s+is a LIST|second entry to the SAME fenced block", flat), (
        f"{name} must say HOW the design entry coexists with its other hop - `next:` is a LIST, so "
        f"both ride one block. Without that an author drops one of the two."
    )
    assert re.search(r"confidence:\s*0?\.\d", flat), (
        f"{name} must give the design entry an explicit `confidence` - the contract makes "
        f"confidence the advisory-vs-auto-run lever, and an omitted value is not a default."
    )


@pytest.mark.parametrize("name", sorted(DESIGN_ROUTERS))
def test_the_design_hop_is_suppressed_under_a_plan(name):
    """Making the channel reachable must NOT reopen the ordering hole the sibling guard closed.

    Behaviour protected: a reachable design hop is correct ONLY standalone. Under an approved plan
    a missing design is plan drift routed back to `odoo-planning`, never a design node scheduled
    after the plan. Fails if the suppression condition or its owner is dropped.
    """
    flat = _flat(_read(DESIGN_ROUTERS[name]))
    assert re.search(r"(?i)STANDALONE", flat), (
        f"{name}'s design entry must be scoped to STANDALONE invocations."
    )
    assert re.search(r"(?i)omit this entry entirely when a plan signal is in scope", flat), (
        f"{name} must state the suppression condition for the design entry - without it the entry "
        f"fires under a run and schedules a design AFTER the plan it should have preceded."
    )
    assert "Approved-plan-artifact detection" in flat, (
        f"{name} must resolve 'is a plan in scope?' from the three-signal SSOT "
        f"(planning-gate-contract.md § Approved-plan-artifact detection), never a local guess."
    )
    assert re.search(r"(?i)PLAN DRIFT", flat) and re.search(
        r"(?i)route back to `?odoo-planning", flat
    ), (
        f"{name} must name the alternative under a plan: a missing design is PLAN DRIFT, routed "
        f"back to `odoo-planning` to amend the plan. A suppression with no alternative just drops "
        f"the finding again - the defect this change exists to remove."
    )


# ---------------------------------------------------------------------------
# Tree-wide sweep, scoped to design routing (the coordinator's scope).
# ---------------------------------------------------------------------------


def test_no_next_step_anywhere_rides_outside_the_block():
    """Whole-tree sweep: no file may route a next step outside the fenced block.

    Scope is every plugin tree and EVERY prose/config/script artifact in them, generated regions
    included - no pre-filter, so the same loss aimed at any other target (or reached through an
    alias or a variable) is caught too.
    """
    offenders = []
    for path, text in _tree_texts():
        for shape, hit in find_off_channel(text):
            line = text[: text.index(hit)].count("\n") + 1 if hit in text else 0
            offenders.append(f"{path.relative_to(ROOT)}:{line} [{shape}] {hit[:110]!r}")
    assert not offenders, (
        "These sites put a next step where the driver never reads it:\n  "
        + "\n  ".join(offenders)
    )


def test_the_sweep_has_a_corpus():
    """Discovery floor - an empty corpus would make the sweep green for the wrong reason.

    Two floors: the whole corpus the sweep walks, and the design-routing subset within it.
    """
    corpus = [p for p, _ in _tree_texts()]
    assert len(corpus) >= 200, (
        f"the unfiltered sweep walks only {len(corpus)} files - expected a substantial prose corpus "
        f"across both plugin trees, so the sweep would pass vacuously"
    )
    routers = [p for p, t in _tree_texts() if DESIGN_SKILL in t]
    assert len(routers) >= 10, (
        f"only {len(routers)} files mention {DESIGN_SKILL!r} - the sweep has nothing to judge"
    )


# ---------------------------------------------------------------------------
# Detector proofs.
# ---------------------------------------------------------------------------

MUST_CATCH = [
    pytest.param(
        "If the work is fable-grade but NO approved design doc exists, recommend "
        "`SUGGESTED_NEXT: odoo-solution-design` first (Custom-XL work is design-first).",
        id="bare-line-naming-the-design-skill",
    ),
    pytest.param(
        "Set `status: DONE`, then add a SUGGESTED_NEXT: odoo-solution-architect line below.",
        id="bare-line-beside-a-status",
    ),
    pytest.param(
        "Set status: NEEDS_NEXT in the block, and put the next: odoo-solution-design hop "
        "outside the fenced continuation block so a human sees it.",
        id="hop-outside-the-fenced-block",
    ),
]


@pytest.mark.parametrize("sample", MUST_CATCH)
def test_detector_catches_every_off_channel_shape(sample):
    assert find_off_channel(sample), (
        f"the off-channel detector must catch {sample!r} - a guard keyed on the skill NAME rather "
        f"than the CHANNEL passes on every one of these"
    )


MUST_NOT_CATCH = [
    pytest.param(
        "add a SECOND entry to the SAME fenced block's `next:` array: `skill: "
        "odoo-solution-design`, `reason: Custom-XL work is design-first`, `confidence: 0.4`.",
        id="the-in-block-entry",
    ),
    pytest.param(
        "add a `next:` entry naming `odoo-ui-review` to your Continuation Contract block "
        "(see `## Continuation Contract` below).",
        id="an-agent-follow-up-in-the-block",
    ),
    pytest.param(
        "emit `next: odoo-solution-design` with `inputs: {design_doc: <path>}` inside the fenced "
        "continuation block; the driver reads the array.",
        id="plain-reachable-in-block-hop",
    ),
]


@pytest.mark.parametrize("sample", MUST_NOT_CATCH)
def test_detector_leaves_in_block_hops_alone(sample):
    hits = find_off_channel(sample)
    assert not hits, (
        f"the off-channel detector must NOT catch {sample!r} (matched {hits!r}) - an in-block hop "
        f"is the channel the driver reads"
    )


# ---------------------------------------------------------------------------
# A status shown in a template sits in the continuation block, the one place the driver reads it.
# ---------------------------------------------------------------------------

_FENCE_LINE = re.compile(r"^\s*(`{3,}|~{3,})\s*(\S*)")
_STATUS_LINE = re.compile(r"^\s*(?:[-*]\s+)?`?status`?\s*:\s*`?(?:DONE|NEEDS_NEXT|BLOCKED|NEEDS_CONTEXT)\b")


def find_status_outside_block(text: str) -> list[str]:
    """Each fenced `status:` line carrying a continuation status that no `continuation` fence
    encloses - a template that teaches an agent to report its status where no driver reads it."""
    out, stack = [], []
    for n, line in enumerate(text.splitlines(), 1):
        m = _FENCE_LINE.match(line)
        if m:
            mark, info = m.group(1), m.group(2)
            if stack and not info and mark[0] == stack[-1][0][0] and len(mark) >= len(stack[-1][0]):
                stack.pop()
            else:
                stack.append((mark, info))
            continue
        if stack and _STATUS_LINE.match(line) and not any(i == "continuation" for _, i in stack):
            out.append(f"{n}: {line.strip()[:100]}")
    return out


def test_no_template_reports_a_status_outside_the_continuation_block():
    offenders = []
    for path in sorted(PLUGIN.rglob("*")):
        if path.is_file() and path.suffix in {".md", ".yaml", ".yml"}:
            offenders += [f"{path.relative_to(ROOT)}:{hit}"
                          for hit in find_status_outside_block(path.read_text(encoding="utf-8"))]
    assert not offenders, (
        "These templates put a continuation status outside a ```continuation block:\n  "
        + "\n  ".join(offenders)
    )


@pytest.mark.parametrize("sample, caught", [
    pytest.param("```\nodoo-x result\nstatus: BLOCKED - input missing\n```", True, id="plain-fence"),
    pytest.param("```yaml\nstatus: NEEDS_NEXT\nnext: odoo-planning\n```", True, id="yaml-fence"),
    pytest.param("```continuation\nstatus: BLOCKED\nblocked_reason: x\n```", False, id="in-block"),
    pytest.param("````\nodoo-x result\n\n```continuation\nstatus: NEEDS_CONTEXT(SLUG)\n```\n````",
                 False, id="nested-in-a-display-fence"),
    pytest.param("Emit `status: BLOCKED` with a `blocked_reason`.", False, id="prose"),
])
def test_the_status_detector_reads_fences(sample, caught):
    assert bool(find_status_outside_block(sample)) is caught, sample
