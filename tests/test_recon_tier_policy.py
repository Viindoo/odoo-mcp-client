"""Guard: recon/scouting phases must default away from opus (R1a), and a Write-constrained
scout's findings must be persisted VERBATIM per agent, never as a parent-authored digest (R1b).

Business rules protected (behavior-first, ETHOS #11):

1. An Agent-tool launch with NO explicit `model` parameter does not fall back to some neutral
   tier - it INHERITS THE CALLING CONTEXT'S OWN MODEL. In an opus-tier session this silently
   turns every unstated recon dispatch into an opus dispatch. `concurrency-guard.md` (the
   Model-tier SSOT) must name this mechanism explicitly, not just assert "use a cheap tier" as
   an unexplained rule - a runtime agent that understands WHY applies the rule at a site nobody
   has written yet.

2. Every recon/scouting dispatch site in the tree (skills/ + agents/, not docs/reference mirrors)
   must state its tier explicitly (or point at the SSOT) - never leave it silent. This is
   deliberately a WHOLE-TREE, no-allowlist scan (test_recon_dispatch_sites_state_a_tier) rather
   than a check pinned to the one known offender (`odoo-intake` Phase R) - a guard scoped to a
   single known site would go green forever while the next unstated site walks straight past it,
   which is the exact trap this PR has hit repeatedly on other guards.

3. `scouting-persistence-contract.md` Clause 2 already lets the PARENT write on behalf of a
   Write-constrained scout (`Explore`, an anonymous read-only agent) because the tool, not the
   content, is constrained. A parent that reworks the scout's return into its own words recreates
   the exact defect this whole contract exists to close: a lossy digest standing in for the
   actual finding is the caller's memory wearing a file. Clause 3 (new) requires the parent's
   write to be that scout's OWN returned text, VERBATIM - no merging, no summarizing, no
   re-ordering - with one file per additional scout when more than one is dispatched.

Genre A (structural/computed) throughout - every assertion fails for a concrete textual reason,
never a value judgement.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"

GUARD = PLUGIN / "skills" / "_shared" / "concurrency-guard.md"
CONTRACT = PLUGIN / "snippets" / "scouting-persistence-contract.md"


def _tree_md_files():
    """Every skill/agent prose file - NOT docs/reference (those are human/agent-facing mirrors
    of a skill's own text, not an independently-executed dispatch site; scoping here avoids
    double-counting the same site under two paths)."""
    for sub in ("skills", "agents"):
        base = PLUGIN / sub
        if not base.is_dir():
            continue
        yield from base.rglob("*.md")


# --------------------------------------------------------------------------- #
# 1 - the SSOT names the inheritance mechanism, not just the rule.
# --------------------------------------------------------------------------- #


def test_concurrency_guard_declares_recon_default_and_names_inheritance_mechanism():
    """Genre A (structural). concurrency-guard.md must state that a recon/scouting phase
    defaults to haiku/sonnet, must explicitly forbid an unstated (silent) tier, and must name
    WHY: an unstated `model` inherits the calling context's own model rather than any neutral
    default - the actual mechanism behind the owner-observed "recon lands on opus" runtime
    behavior in an opus-tier session.

    Fails if: the clause is absent, or present but missing the inheritance-mechanism sentence
    (a bare "use haiku/sonnet" rule without the WHY does not self-enforce at a new site).
    """
    assert GUARD.is_file(), "skills/_shared/concurrency-guard.md is missing"
    text = GUARD.read_text(encoding="utf-8")

    heading = re.search(r"\*\*Recon/scouting phase default[^*]*\*\*", text)
    assert heading, (
        "concurrency-guard.md must declare a 'Recon/scouting phase default' clause under "
        "§ Model-tier selection."
    )

    # The mechanism sentence: an unstated `model` INHERITS the caller's own model.
    assert re.search(r"INHERITS?\s+THE\s+CALLING\s+CONTEXT'?S?\s+OWN\s+MODEL", text), (
        "concurrency-guard.md must name the mechanism: an unstated `model` parameter INHERITS "
        "the calling context's own model - not a neutral/safe default."
    )

    # The decidable default + escalation rule.
    clause_start = text.find("**Recon/scouting phase default")
    clause = text[clause_start:clause_start + 1200] if clause_start != -1 else ""
    assert re.search(r"\bhaiku\b.{0,40}\bsonnet\b|\bsonnet\b.{0,40}\bhaiku\b", clause), (
        "the recon-default clause must name haiku/sonnet as the default tier."
    )
    assert re.search(r"never\s+opus\s+or\s+fable|never\s+.{0,20}opus.{0,20}fable", clause, re.IGNORECASE), (
        "the recon-default clause must explicitly forbid opus/fable as a default."
    )
    assert "justification" in clause.lower(), (
        "the recon-default clause must require a stated justification to escalate to opus/fable."
    )


# --------------------------------------------------------------------------- #
# 2 - GENERAL CLASS: every recon-dispatch site anywhere in skills/+agents/ states its tier.
# --------------------------------------------------------------------------- #

# A recon/scout dispatch site, in EITHER of the two idioms actually used in this tree - ONE
# detector, reused verbatim by every test below (the single source of truth for "what counts as
# a recon dispatch site"; no second, parallel detector object anywhere in this file):
#   (a) a dispatch clause whose grammatical object is a recon/scouting-typed agent
#       ("Launch/Dispatch ... recon subagent(s)/scout(s)") - odoo-intake's idiom, or
#   (b) a phase-ID heading that DECLARES ITS WORKER - a `P<digits><optional letter>` heading
#       carrying a parenthesised worker-type/tier token in the heading line itself, e.g.
#       "### P1a - DAG build (Explore, sonnet)" - odoo-modules-upgrade's idiom.
# (b) was added after measuring a widened-but-unanchored heading pattern (bare "P\S* - ... (...)")
# against the whole tree: it produced ONE false positive, "## Per-module reviewer (sonnet)" in
# `skills/odoo-code-review/references/agent-prompts.md` - a regex artifact, not a real phase
# heading (the greedy `\S*` treated the hyphen INSIDE "Per-module" as the "P<x> - <name>"
# separator). Anchoring to an actual phase-ID token (`P\d+[a-zA-Z]?`, e.g. P1a/P1d/P3/P10) closed
# that false positive while still matching both genuine sites - measured 2 matches, both real,
# zero false positives, confirmed by direct tree-wide scan before landing this pattern.
DISPATCH_RECON_RE = re.compile(
    r"\b(?:Launch|Dispatch)(?:es|ing)?\b[^.\n]{0,60}?"
    r"\b(?:recon(?:naissance)?\s+(?:subagents?|agents?)|scouts?)\b"
    r"|"
    r"^#{1,6}\s*P\d+[a-zA-Z]?\s*-\s*[^\n(]*\([^)\n]*"
    r"\b(?:haiku|sonnet|opus|fable|Explore)\b[^)\n]*\)",
    re.IGNORECASE | re.MULTILINE,
)
TIER_TOKEN_RE = re.compile(r"\b(haiku|sonnet|opus|fable)\b", re.IGNORECASE)
TIER_POINTER_RE = re.compile(r"concurrency-guard\.md", re.IGNORECASE)
WINDOW_AFTER_MATCH = 500


def test_recon_dispatch_sites_state_a_tier():
    """Genre A (whole-tree, no allowlist). For every textual site in skills/+agents/ that matches
    `DISPATCH_RECON_RE` (either idiom - a "launch/dispatch a recon subagent/scout" clause, or a
    phase-ID heading declaring its worker), a model tier token (haiku/sonnet/opus/fable) or an
    explicit pointer to the concurrency-guard.md SSOT must appear within the following ~500
    characters (trivially true for idiom (b), since the tier token is inside the match itself).

    Measured (current tree): 4 matches total - 2 inside `odoo-intake/SKILL.md` (Hard rule 2(b)
    and the Phase R body bullet - the same site restated twice) and 2 inside
    `upg-phase-detail.md` (`### P1a - DAG build (Explore, sonnet)`, `### P1d - Transitive Symbol
    Survey (Explore, sonnet, read-only)`) - 0 offenders in all 4 cases; a whitespace-normalized,
    no-allowlist scan of the WHOLE skills/+agents/ tree surfaced no other unstated recon-dispatch
    site.

    Fails if: any recon-dispatch clause anywhere in the tree states no tier and no SSOT pointer
    within range - including a brand-new site nobody has written yet, which is the entire point
    of scoping this whole-tree rather than to the one historically-known offender.
    """
    offenders = []
    for path in _tree_md_files():
        text = path.read_text(encoding="utf-8")
        norm = re.sub(r"[ \t]+", " ", text)
        for m in DISPATCH_RECON_RE.finditer(norm):
            start = m.start()
            window = norm[start:start + WINDOW_AFTER_MATCH]
            if TIER_TOKEN_RE.search(window) or TIER_POINTER_RE.search(window):
                continue
            offenders.append(
                f"{path.relative_to(PLUGIN)}:~char{start}: "
                f"{norm[start:start + 140]!r}"
            )
    assert not offenders, (
        "Recon/scouting dispatch site(s) with no stated tier and no SSOT pointer within "
        f"{WINDOW_AFTER_MATCH} chars:\n" + "\n".join(offenders)
    )


# --------------------------------------------------------------------------- #
# 3 - the contract requires verbatim per-agent capture (not a parent-authored digest).
# --------------------------------------------------------------------------- #


def test_scouting_persistence_contract_requires_verbatim_per_agent_capture():
    """Genre A (structural). `scouting-persistence-contract.md` must declare a Clause 3
    (verbatim per-agent capture) that: (a) forbids merging/summarizing/re-ordering a scout's
    returned findings, (b) states the single-scout case is transcribed verbatim, and (c) states
    that a second (and further) scout dispatched in the same phase gets its OWN sibling file -
    never merged into the first scout's file.

    Fails if: Clause 3 is absent, or present but missing the no-merge/no-summarize prohibition,
    or missing the one-sibling-file-per-additional-scout rule.
    """
    assert CONTRACT.is_file(), "snippets/scouting-persistence-contract.md is missing"
    text = CONTRACT.read_text(encoding="utf-8")

    clause_match = re.search(r"## Clause 3.*?(?=\n## |\Z)", text, re.DOTALL)
    assert clause_match, (
        "scouting-persistence-contract.md must declare a '## Clause 3' section for verbatim "
        "per-agent capture."
    )
    clause = clause_match.group(0)

    assert re.search(r"VERBATIM", clause), (
        "Clause 3 must require the parent's write to be the scout's own text captured VERBATIM."
    )
    assert re.search(r"no merging,\s*no summarizing,\s*no re-ordering", clause, re.IGNORECASE), (
        "Clause 3 must explicitly ban merging, summarizing, AND re-ordering a scout's return - "
        "a parent-authored digest is the defect this clause exists to close."
    )
    assert re.search(r"findings-<N>\.md|findings-2\.md", clause), (
        "Clause 3 must define a per-additional-scout sibling file (e.g. `findings-<N>.md`) - "
        "one file per dispatched agent beyond the first, not one shared/merged file."
    )


# --------------------------------------------------------------------------- #
# 4 - Clause 3's OWN consumer registry: every registered site cites the clause, AND every
#     site the SHARED (guard-2) recon-dispatch detector finds is itself registered. A named
#     list checked only against itself goes green forever while an unregistered new site walks
#     straight past it; feeding guard 2's own match set into the same check turns "add a new
#     recon/scout dispatch site and forget to register it" into a red result instead of a blind
#     spot - the registry lives in the contract (SSOT), this test only reads it.
# --------------------------------------------------------------------------- #

_REGISTRY_ROW_RE = re.compile(
    r"^\|\s*`([^`]+)`\s*\|\s*`([^`]+)`\s*\|\s*$", re.MULTILINE
)


def _parse_clause3_registry(contract_text: str) -> list[tuple[str, str]]:
    """Parse Clause 3's 'Consumer registry' table into (file, section_anchor) pairs.

    The registry is authored as prose in scouting-persistence-contract.md (Clause 3's own
    ownership - the contract is the SSOT for who must cite it); this only reads it back, it
    never hardcodes the list in Python.
    """
    clause_match = re.search(r"## Clause 3.*?(?=\n## |\Z)", contract_text, re.DOTALL)
    assert clause_match, "Clause 3 section not found - cannot locate its consumer registry."
    registry_match = re.search(
        r"\*\*Consumer registry.*?\n\n(\|.*?\n(?:\|.*?\n)+)",
        clause_match.group(0),
        re.DOTALL,
    )
    assert registry_match, (
        "Clause 3 must declare a 'Consumer registry' table (file | section anchor rows)."
    )
    table = registry_match.group(1)
    rows = [
        (m.group(1), m.group(2))
        for m in _REGISTRY_ROW_RE.finditer(table)
        if m.group(1) != "file"  # skip the header row
    ]
    assert rows, "Clause 3's consumer registry table has no data rows."
    return rows


def test_clause3_registry_rows_each_cite_the_clause_in_their_own_section():
    """Genre A (registry-driven, not a hardcoded Python list). Every row in Clause 3's OWN
    consumer registry (parsed from scouting-persistence-contract.md, not restated here) must
    cite 'clause 3' within its named section - proving the registry is wired in, not just
    declared and never read.

    Pre-fix (measured against `git show HEAD`): 3 offenders (the registry table and Clause 3
    itself did not exist yet, so none of the three sections mentioned 'clause 3').

    Fails if: a registered site's clause-3 pointer is removed, or its section is dropped/renamed
    without updating the registry row.
    """
    contract_text = CONTRACT.read_text(encoding="utf-8")
    registry = _parse_clause3_registry(contract_text)

    failures = []
    for relpath, section_marker in registry:
        path = PLUGIN / relpath
        assert path.exists(), f"{relpath}: registered file not found on disk"
        text = path.read_text(encoding="utf-8")
        idx = text.find(section_marker)
        assert idx != -1, f"{relpath}: section anchor {section_marker!r} not found"
        section = text[idx:idx + 3000]
        if not re.search(r"clause 3", section, re.IGNORECASE):
            failures.append(f"{relpath} ({section_marker!r}): no 'clause 3' pointer in its section")
    assert not failures, "Missing verbatim-capture clause pointers:\n" + "\n".join(failures)


def test_every_shared_detector_recon_site_is_registered():
    """Genre A (GENERAL CLASS, whole-tree, reuses the ONE shared detector - `DISPATCH_RECON_RE` -
    verbatim; no second detector object exists in this file). Every FILE that pattern matches
    anywhere in skills/+agents/ must have at least one row in Clause 3's consumer registry - a
    NEW site written in EITHER idiom the detector covers (a "Launch/Dispatch ... recon
    subagent/scout" clause, or a phase-ID heading declaring its worker) that is never registered
    turns this test red, instead of silently walking past a named list.

    Measured (current tree): `DISPATCH_RECON_RE` matches inside two files -
    `odoo-intake/SKILL.md` (2 matches) and `upg-phase-detail.md` (2 matches, P1a + P1d) - both
    already registered, 0 offenders.

    History (why both idioms are covered, not left as a documented gap): the first version of
    this test only reused the dispatch-verb half of the detector, which cannot see
    `odoo-modules-upgrade`'s P1a/P1d sites (phrased as a `### P1a - DAG build (Explore, sonnet)`
    heading + task block, never a "Launch/Dispatch a recon subagent/scout" sentence) - a real
    blind spot, at the time reported via a separate pinning assertion. That pinning assertion was
    itself a defect: asserting the detector CANNOT see a known site makes the gap load-bearing -
    the moment someone correctly widens the detector, that assertion goes red and reads like
    breakage, inviting a revert instead of a fix. It was removed. The detector was widened
    instead, adding the phase-ID-heading idiom directly to `DISPATCH_RECON_RE` above (see that
    definition's comment for the false-positive-then-fixed measurement) - both idioms are now one
    detector, and both known sites are now auto-discovered by it, not just registry-listed.
    """
    registry = _parse_clause3_registry(CONTRACT.read_text(encoding="utf-8"))
    registered_files = {relpath for relpath, _ in registry}

    offenders = []
    for path in _tree_md_files():
        relpath = str(path.relative_to(PLUGIN))
        text = path.read_text(encoding="utf-8")
        norm = re.sub(r"[ \t]+", " ", text)
        if DISPATCH_RECON_RE.search(norm) and relpath not in registered_files:
            offenders.append(relpath)
    assert not offenders, (
        "Recon/scout dispatch site(s) found by the shared detector but not registered in "
        f"Clause 3's consumer registry: {offenders}"
    )


# --------------------------------------------------------------------------- #
# Pre-fix measurement harness (not a test - documents how the offender counts above were
# measured against the committed baseline, without disturbing any concurrently-edited file).
# --------------------------------------------------------------------------- #


def _measure_against_head(relpath: str) -> str:
    """Read a file's content as committed at HEAD - the 'saved copy of the original text' this
    suite's RED-before-GREEN measurement used, without `git stash` (safe under concurrent edits
    to other files elsewhere in the tree)."""
    result = subprocess.run(
        ["git", "show", f"HEAD:{relpath}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout
