"""Guard: the Terminal stage order constant is DECLARED once and CITED everywhere else.

`skills/run-harness/references/run-integration.md` § Pre-PR tail > "Terminal stage order"
is the constant's ONE owner and says so in its own words: "Cite this constant by name. Do NOT
restate the order in another file, and do NOT reorder it locally." (The owner file was renamed
from `wave-integration.md` when the wave grouping layer was removed - the owner-discovery logic
below never hardcoded that path, so the rename alone did not break it.)

Nothing enforced that. The order has now drifted twice, and each time the failure was the same
shape: the rule was right in one file and wrong in another, and the executing agent read the wrong
copy. The worst restatements did not REORDER the stages - they silently DROPPED i18n and
acceptance, so a plan built from them shipped untranslated, unaccepted code.

WHAT THIS FILE CHECKS

  1. `test_stage_order_declared_in_exactly_one_file` - exactly one file declares the constant
     (the owner), and the owner's own block parses into a non-empty ordered stage list. Without
     this the two checks below could pass vacuously against an empty canon.

  2. `test_no_competing_stage_ordering_outside_the_owner` - no file except the owner asserts its
     OWN lifecycle ordering. An ordering is an arrow chain: >= MIN_CHAIN_TOKENS canonical stage
     tokens joined by `->`, reaching the land tail (PR / monitor / merge). That shape is what a
     planner or an executing agent copies; a chain that stops short of the land tail (the
     `code -> review+test -> code` fix loop, `design -> plan -> code -> review`) is a different,
     legitimate concept and is deliberately NOT a finding.

  3. `test_naming_the_constant_carries_a_pointer_to_its_owner` - a file that invokes the constant
     BY NAME must point at where it lives (the owner file, or the owner skill) within
     CITATION_WINDOW chars, so a reader who meets the name can always reach the definition.

  4. `test_every_references_pointer_resolves_to_a_real_file` - EVERY textual pointer anywhere in
     the plugin (plus `scripts/audit-run.py`) of the shape `skills/<skill>/references/<file>.md`
     (with or without the `${CLAUDE_PLUGIN_ROOT}/` prefix) must resolve to a file that actually
     exists on disk. The `wave-integration.md` -> `run-integration.md` rename touched dozens of
     citing sites across the plugin (27 plugin files + `scripts/audit-run.py`, per the design's
     own count) - a single missed site is a dangling pointer, and that is exactly the defect class
     this check exists to catch generically (not only for this one rename).

WHAT THIS FILE DOES **NOT** CATCH - stated, not implied:

  * A comma-, slash-, or prose-separated enumeration ("i18n, acceptance, doc, then the land
    tail"). In this corpus those forms are SET enumerations far more often than sequences - e.g.
    "A terminal lifecycle stage (doc / i18n / acceptance / PR / monitor / merge) is its own node"
    lists WHICH stages are terminal, not their order. Flagging them would manufacture violations
    that are correct as written and therefore unfixable, and an unfixable rule is how an
    exemption list gets re-opened. `->` is the only separator here that unambiguously asserts
    sequence.
  * An ordering split across sentences ("i18n runs first. Acceptance follows.").
  * An ordering drawn with a different arrow glyph, or rendered as an image.
  * A restatement of a stage's POSITION relative to one neighbour ("doc after acceptance") -
    that is one edge, not the order.

The canonical stage list is PARSED from the owner's own block, never hardcoded here: adding or
removing a stage in the constant must not require editing this test.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = REPO_ROOT / "plugins" / "odoo-ai-agents"

# The heading that DECLARES the constant. Its presence is what makes a file the owner.
OWNER_HEADING = "### Terminal stage order"
# The name a citing file invokes the constant by.
CONSTANT_NAME = "Terminal stage order"

# A chain must carry at least this many canonical stage tokens before it reads as an ordering.
# Two tokens is one edge ("doc -> PR"), which the constant permits a file to state locally.
MIN_CHAIN_TOKENS = 3
# How far from a `Terminal stage order` mention a pointer to the owner may sit.
CITATION_WINDOW = 400

# Non-canonical stage words that appear in the same chains. Kept ONLY so a finding's message shows
# the whole chain a reader would copy; a chain still needs MIN_CHAIN_TOKENS *canonical* tokens and
# a land-tail token to be a finding, so nothing here can create one on its own.
CHAIN_CONTEXT_TOKENS = {"code", "review", "test", "qa", "design", "plan", "scope"}

# Historical record, not instruction: a changelog states what the tree said at the time, and
# rewriting it would destroy the only account of the drift this guard exists to stop.
EXCLUDED_NAMES = {"CHANGELOG.md"}
EXCLUDED_DIR_PARTS = {".git", "node_modules", "__pycache__", ".venv", "tests", "evals"}

CHAIN_RE = re.compile(r"[A-Za-z0-9_+/`*-]+(?:\s*->\s*[A-Za-z0-9_+/`*-]+)+")
SEGMENT_STRIP = "`*_ \t\n"


def _scanned_files() -> list[Path]:
    """Every prose/definition file a reader or an agent could take the order from."""
    out: list[Path] = []
    for pattern in ("*.md", "*.yaml", "*.yml"):
        for path in REPO_ROOT.rglob(pattern):
            if path.name in EXCLUDED_NAMES:
                continue
            if EXCLUDED_DIR_PARTS & set(path.relative_to(REPO_ROOT).parts):
                continue
            out.append(path)
    return sorted(out)


def _owner_files() -> list[Path]:
    return [p for p in _scanned_files() if OWNER_HEADING in p.read_text(encoding="utf-8")]


def parse_canonical_stages(owner_text: str) -> list[str]:
    """The ordered stage tokens, read out of the owner's own ASCII block.

    Each stage is a `+--> (n) <stage>` / `+-------> <stage>` row. Returns lower-cased tokens in
    declaration order."""
    start = owner_text.index(OWNER_HEADING)
    fence = re.search(r"```text\n(.*?)```", owner_text[start:], re.S)
    assert fence, f"{OWNER_HEADING!r} declares no ```text block - the constant is unreadable"
    stages: list[str] = []
    for line in fence.group(1).splitlines():
        m = re.match(r"\s*\+-+>\s*(?:\(\w+\)\s*)?([A-Za-z0-9_-]+)", line)
        if m:
            stages.append(m.group(1).lower())
    return stages


def parse_land_tail(owner_text: str) -> set[str]:
    """The stages at or after the PR - the tokens whose presence makes a chain a LIFECYCLE
    ordering rather than an inner loop. Read from the block: the `PR` row plus every row the
    owner marks `[post-PR]`."""
    start = owner_text.index(OWNER_HEADING)
    fence = re.search(r"```text\n(.*?)```", owner_text[start:], re.S)
    assert fence
    tail = {"pr"}
    for line in fence.group(1).splitlines():
        m = re.match(r"\s*\+-+>\s*(?:\(\w+\)\s*)?([A-Za-z0-9_-]+)", line)
        if m and "[post-PR]" in line:
            tail.add(m.group(1).lower())
    return tail


def find_competing_orderings(text: str, canon: list[str], land_tail: set[str]) -> list[str]:
    """Every arrow chain in `text` that asserts a lifecycle ordering.

    A chain qualifies when its longest run of CONSECUTIVE stage tokens holds at least
    MIN_CHAIN_TOKENS canonical stages AND at least one land-tail stage. Returns the offending
    chains, verbatim, so a failure names what to delete."""
    canon_set = set(canon)
    vocabulary = canon_set | CHAIN_CONTEXT_TOKENS
    findings: list[str] = []
    for m in CHAIN_RE.finditer(text):
        segments = [s.strip(SEGMENT_STRIP).lower() for s in m.group(0).split("->")]
        run: list[str] = []
        best: list[str] = []
        for seg in segments:
            if seg in vocabulary:
                run.append(seg)
                if len(run) > len(best):
                    best = list(run)
            else:
                run = []
        canonical_in_run = [t for t in best if t in canon_set]
        if len(canonical_in_run) < MIN_CHAIN_TOKENS:
            continue
        if not (set(canonical_in_run) & land_tail):
            continue
        findings.append(" ".join(m.group(0).split()))
    return findings


@pytest.fixture(scope="module")
def owner() -> Path:
    files = _owner_files()
    assert files, f"no file declares {OWNER_HEADING!r} - the constant has no owner"
    return files[0]


@pytest.fixture(scope="module")
def canon(owner: Path) -> list[str]:
    return parse_canonical_stages(owner.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def land_tail(owner: Path) -> set[str]:
    return parse_land_tail(owner.read_text(encoding="utf-8"))


def test_stage_order_declared_in_exactly_one_file() -> None:
    """Two owners is the drift condition itself - whichever copy an agent reads first wins."""
    owners = [str(p.relative_to(REPO_ROOT)) for p in _owner_files()]
    assert len(owners) == 1, (
        f"Terminal stage order must be declared in exactly ONE file; found {len(owners)}: {owners}"
    )


def test_owner_block_parses_into_an_ordered_stage_list(canon: list[str], land_tail: set[str]) -> None:
    """Anchors the two checks below: an empty canon would let them pass measuring nothing."""
    assert len(canon) >= 4, f"parsed too few stages from the constant: {canon}"
    assert len(canon) == len(set(canon)), f"the constant lists a stage twice: {canon}"
    assert land_tail, "no land-tail stage parsed - every chain would then be ignored"
    assert land_tail <= set(canon), f"land tail {land_tail} is not a subset of the canon {canon}"


def test_no_competing_stage_ordering_outside_the_owner(
    owner: Path, canon: list[str], land_tail: set[str]
) -> None:
    """No file but the owner may state its own lifecycle stage ordering.

    This fires on the SHAPE of a competing ordering (an arrow chain reaching the land tail), not
    on stage names appearing in prose - a file is free to name, describe, or route to any stage."""
    offences: list[str] = []
    for path in _scanned_files():
        if path == owner:
            continue
        text = path.read_text(encoding="utf-8")
        for chain in find_competing_orderings(text, canon, land_tail):
            line_no = text.count("\n", 0, text.index(chain.split(" ->")[0])) + 1
            offences.append(f"{path.relative_to(REPO_ROOT)}: {chain}")
    assert not offences, (
        "these files restate the Terminal stage order instead of citing it "
        f"(its ONE owner is {owner.relative_to(REPO_ROOT)} § {OWNER_HEADING.strip('# ')}):\n  "
        + "\n  ".join(sorted(set(offences)))
    )


def test_naming_the_constant_carries_a_pointer_to_its_owner(owner: Path) -> None:
    """Invoking the constant by name without saying where it lives leaves a reader stuck - and a
    stuck reader re-derives the order locally, which is how the drift starts."""
    owner_file_token = owner.name
    owner_skill_token = owner.parent.parent.name  # the owning skill dir, e.g. `run-harness`
    offences: list[str] = []
    for path in _scanned_files():
        if path == owner:
            continue
        text = path.read_text(encoding="utf-8")
        for m in re.finditer(re.escape(CONSTANT_NAME), text):
            window = text[max(0, m.start() - CITATION_WINDOW): m.end() + CITATION_WINDOW]
            if owner_file_token in window or owner_skill_token in window:
                continue
            line_no = text.count("\n", 0, m.start()) + 1
            offences.append(f"{path.relative_to(REPO_ROOT)}:{line_no}")
    assert not offences, (
        f"these sites name {CONSTANT_NAME!r} with no pointer to its owner "
        f"({owner_file_token} / the {owner_skill_token} skill) within {CITATION_WINDOW} chars:\n  "
        + "\n  ".join(offences)
    )


# --- References-pointer resolution (generalized dangling-pointer guard) -----------------------
#
# The wave-layer removal renamed `wave-integration.md` -> `run-integration.md` and touched dozens
# of citing sites across the plugin (27 plugin files + `scripts/audit-run.py`, per the design's
# own count - not the handful an earlier draft estimated). A guard scoped to ONE constant's name
# cannot catch a stray, un-renamed pointer to the OLD filename sitting in unrelated prose, so this
# check is deliberately generic: ANY `skills/<skill>/references/<file>.md` pointer, anywhere in
# the plugin (plus scripts/audit-run.py, the one such citing site outside the plugin directory),
# must resolve to a file that actually exists. This is not specific to the Terminal stage order
# constant or to this one rename - a dangling `references/` pointer is exactly what this guard
# exists to catch, whichever rename left it behind.

AUDIT_RUN_PY = REPO_ROOT / "scripts" / "audit-run.py"

REFERENCES_POINTER_RE = re.compile(
    r"(?:\$\{CLAUDE_PLUGIN_ROOT\}/)?skills/([a-zA-Z0-9_-]+)/references/([a-zA-Z0-9_.-]+\.md)"
)


def _pointer_scanned_files() -> list[Path]:
    """Every file whose text could hold a `skills/<skill>/references/<file>` pointer: the whole
    plugin tree (every extension a pointer could live in) plus `scripts/audit-run.py`, the one
    such citing site outside the plugin directory. No exclusions beyond dedup - a pointer is
    either resolvable or it is a bug, in any file that names one."""
    out: list[Path] = [AUDIT_RUN_PY]
    for pattern in ("*.md", "*.py", "*.sh", "*.yaml", "*.yml", "*.json"):
        out.extend(PLUGIN_ROOT.rglob(pattern))
    return sorted(set(out))


def test_every_references_pointer_resolves_to_a_real_file() -> None:
    """Behavior protected: every `skills/<skill>/references/<file>.md` pointer (with or without
    the `${CLAUDE_PLUGIN_ROOT}/` prefix) names a file that actually exists on disk. A rename this
    size (dozens of citing sites) is exactly the shape of change that leaves ONE stray pointer at
    the old name - and a dangling pointer sends the reading agent to a file that is not there.

    Fails on every unresolvable pointer found (file, line, and the missing target), scanning the
    whole plugin tree plus scripts/audit-run.py - not scoped to the Terminal stage order constant
    or to any one rename.
    """
    offences: list[str] = []
    for path in _pointer_scanned_files():
        text = path.read_text(encoding="utf-8")
        for m in REFERENCES_POINTER_RE.finditer(text):
            skill, fname = m.group(1), m.group(2)
            target = PLUGIN_ROOT / "skills" / skill / "references" / fname
            if not target.exists():
                line_no = text.count("\n", 0, m.start()) + 1
                offences.append(
                    f"{path.relative_to(REPO_ROOT)}:{line_no} -> "
                    f"skills/{skill}/references/{fname} (does not exist)"
                )
    assert not offences, (
        "these sites point at a skills/<skill>/references/<file> path that does not exist on "
        "disk:\n  " + "\n  ".join(sorted(set(offences)))
    )


# --- Synthetic mutation proof -----------------------------------------------------------------
#
# The two checks above are only worth their runtime if they can FAIL. These run the SAME detector
# used above over constructed text, so a refactor that neuters the detector reddens here even
# while the real tree happens to be clean.

_SYNTHETIC_CANON = ["i18n", "acceptance", "doc", "lint", "pr", "monitor", "merge"]
_SYNTHETIC_TAIL = {"pr", "monitor", "merge"}


@pytest.mark.parametrize(
    "mutation",
    [
        # the exact drift that shipped: a reordering that drops i18n and acceptance
        "the full lifecycle (code -> review -> doc -> PR -> monitor -> merge)",
        # a reordering that keeps every stage but moves doc ahead of acceptance
        "code -> i18n -> doc -> acceptance -> lint -> PR -> monitor -> merge",
        # a subset that drops the lint gate
        "Lifecycle: i18n -> acceptance -> doc -> PR -> merge",
        # wrapped across a line, as a README would render it
        "spans the full lifecycle (code -> review ->\n  doc -> PR -> monitor -> merge).",
    ],
)
def test_detector_flags_a_competing_ordering(mutation: str) -> None:
    assert find_competing_orderings(mutation, _SYNTHETIC_CANON, _SYNTHETIC_TAIL), (
        f"detector missed a competing ordering: {mutation!r}"
    )


@pytest.mark.parametrize(
    "compliant",
    [
        # the citation form every file is supposed to use
        "in the Terminal stage order constant run-harness owns - never restated here",
        # the per-module fix loop: a real, different concept that must stay legal
        "the code -> review+test -> code round-trip runs until the review is clean",
        # an upstream chain that never reaches the land tail
        "scope -> design -> code -> review",
        # a set enumeration, not a sequence
        "a terminal lifecycle stage (doc / i18n / acceptance / PR / monitor / merge) is its own node",
        # one edge, which the owner allows a file to state locally
        "doc -> PR",
        # a routing table row that happens to contain an arrow
        "enumerate ALL capabilities for docs -> doc-feature-map",
    ],
)
def test_detector_leaves_compliant_prose_alone(compliant: str) -> None:
    assert not find_competing_orderings(compliant, _SYNTHETIC_CANON, _SYNTHETIC_TAIL), (
        f"detector false-positived on compliant prose: {compliant!r}"
    )
