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


def test_concurrency_guard_binds_the_directly_invoked_leaf_skill_path():
    """Genre A (structural). Hard rule 2(b) (`odoo-intake/SKILL.md` § Phase R) sanctions an
    alternative to subagent dispatch: a read-only recon/scouting task done by invoking a leaf
    skill (e.g. `odoo-feature-check`, `odoo-override-finding`) directly via the Skill tool. A
    Skill-tool call carries NO per-call `model` parameter - it always executes in the invoking
    context's own model, with no lever to lower it. In an opus/fable-tier orchestrating session
    this reproduces the exact inheritance defect the recon-default clause above closes, through a
    second door the subagent-dispatch fix cannot reach. concurrency-guard.md - the model-tier SSOT
    - must state this fact and give a decidable rule: wrap the leaf-skill call in a haiku/sonnet
    subagent when the invoking context is opus/fable-tier; invoke it directly only when the
    invoking context is already haiku/sonnet-tier.

    Pre-fix (measured against `git show HEAD`): the clause did not exist - 0 of the 3 assertions
    below would have matched.

    Fails if: the leaf-skill path is not addressed at all, or is addressed without both (a) the
    'no model parameter' fact and (b) the wrap-in-a-subagent decision rule for an opus/fable
    caller - a bare acknowledgement with no decidable rule leaves the agent taking this path
    guessing, which is the same failure the inheritance-mechanism sentence above exists to avoid.
    """
    text = GUARD.read_text(encoding="utf-8")
    idx = text.find("**Recon/scouting phase default")
    assert idx != -1, "concurrency-guard.md must still declare the recon-default clause."
    window = text[idx:idx + 3500]

    assert re.search(r"\bleaf skill\b", window, re.IGNORECASE), (
        "concurrency-guard.md must address the directly-invoked leaf-skill path (Hard rule 2(b)'s "
        "sanctioned alternative to subagent dispatch) within the Model-tier selection section."
    )
    assert re.search(r"no\b.{0,30}\bmodel\b.{0,30}\bparameter", window, re.IGNORECASE | re.DOTALL), (
        "concurrency-guard.md must state the Skill tool carries no per-call `model` parameter - "
        "the fact that makes the leaf-skill path undecidable without an explicit rule."
    )
    assert re.search(
        r"\bwrap\b.{0,80}\b(?:haiku|sonnet)\b.{0,60}\bsubagent\b", window, re.IGNORECASE | re.DOTALL
    ), (
        "concurrency-guard.md must give the decidable rule: wrap the leaf-skill call in a "
        "haiku/sonnet subagent when the invoking context is opus/fable-tier."
    )


# The inheritance-mechanism sentence's own load-bearing wording (this repo's inheritance
# mechanism is stated once, here, and every OTHER site must REFERENCE it, never restate it -
# mirrors `test_readback_rule_has_exactly_one_definer` in test_scouting_persistence.py). Checked
# against WHITESPACE-NORMALIZED text (all runs of whitespace, including newlines, collapsed to one
# space) because concurrency-guard.md's own prose is soft-wrapped - the phrase spans a line break
# there ("...it INHERITS THE CALLING\nCONTEXT'S OWN MODEL." at the time this test was written) - a
# naive un-normalized substring search would miss the SSOT's own occurrence and misreport it as
# having zero definers instead of exactly one.
INHERITANCE_DEFINER_PHRASE = "INHERITS THE CALLING CONTEXT'S OWN MODEL"


def _tree_texts_whole_plugin():
    """Every text artifact under the plugin (md/yaml/json/txt/sh/py) - mirrors
    test_scouting_persistence.py's `_tree_texts()` exactly, so a restatement anywhere in the
    plugin (not just skills/+agents/) is caught."""
    exts = {".md", ".yaml", ".yml", ".json", ".txt", ".sh", ".py"}
    for p in PLUGIN.rglob("*"):
        if p.is_file() and p.suffix in exts:
            yield p, p.read_text(encoding="utf-8")


def test_inheritance_mechanism_sentence_has_exactly_one_definer():
    """Genre A (count == 1). A verbatim (or line-wrap-only-different) restatement of the
    inheritance-mechanism sentence anywhere else in the plugin tree goes red - closing the exact
    gap a reviewer found: `odoo-intake/SKILL.md` restated this sentence character-for-character in
    TWO places (Hard rule 2(b) and the Phase R body bullet) while no test protected the SSOT's
    "reference, never restate" rule for it, unlike the sibling read-back rule which already had
    `test_readback_rule_has_exactly_one_definer`.

    Pre-fix (measured against `git show HEAD`, whitespace-normalized whole-plugin scan): 2
    definers - `skills/_shared/concurrency-guard.md` (the SSOT) and `skills/odoo-intake/SKILL.md`
    (Hard rule 2(b)'s restatement; the Phase R body bullet's paraphrase used lower-case "INHERITS
    the calling context's own model" and would not have matched this case-sensitive phrase, but
    was fixed in the same edit since it restates the identical mechanism).

    Fails if: this sentence is ever restated (verbatim, case-sensitive) anywhere outside
    concurrency-guard.md again.
    """
    definers = []
    for p, text in _tree_texts_whole_plugin():
        norm = re.sub(r"\s+", " ", text)
        if INHERITANCE_DEFINER_PHRASE in norm:
            definers.append(str(p.relative_to(PLUGIN)))
    assert definers == ["skills/_shared/concurrency-guard.md"], (
        "The inheritance-mechanism sentence must be defined in exactly ONE place; found in: "
        f"{definers}"
    )


# --------------------------------------------------------------------------- #
# 2 - GENERAL CLASS: every recon-dispatch site anywhere in skills/+agents/ states its tier.
# --------------------------------------------------------------------------- #

# A recon/scout dispatch site, in ANY of the idioms actually used in this tree (widened from the
# original 2-idiom detector after a class sweep found ~14/18 real recon-dispatch sites in the tree
# used phrasing neither idiom recognized, and a constructed evasive phrasing - "Spin up one worker
# agent... fold the replies together into one summary" - matched NEITHER, walking past this guard
# and the Clause-3 registry guard below while violating both):
#   (a) a dispatch clause whose grammatical object is a recon/scouting-typed agent
#       ("Launch/Dispatch ... recon subagent(s)/scout(s)", or the hyphen-qualified
#       "recon-class subagent" phrasing `odoo-debug` uses) - odoo-intake's idiom, widened;
#   (b) a phase-ID heading that DECLARES ITS WORKER - a `P<digits><optional letter>` heading OR
#       the equivalent spelled-out `Phase <digits>` heading, carrying a parenthesised
#       worker-type/tier token in the heading line itself, e.g. "### P1a - DAG build (Explore,
#       sonnet)" (odoo-modules-upgrade) or "## Phase 1 - broad / shallow sweep (haiku)"
#       (odoo-deep-survey);
#   (c) an anonymous-worker dispatch clause for enumeration/mapping work - a dispatch verb
#       ("Launch/Dispatch/Spin up/Fan out/Fire off") whose object is an UNNAMED "worker agent"
#       (no `backtick-quoted agent name` right after the verb - a specific, Write-capable,
#       registered agent name is a DIFFERENT, already-compliant idiom, not this one) doing a
#       scouting-flavored verb (map/survey/enumerate/discover) - this is what the constructed
#       evasive phrasing above matches (see test_widened_detector_catches_evasive_worker_phrasing).
# (b) was added after measuring a widened-but-unanchored heading pattern (bare "P\S* - ... (...)")
# against the whole tree: it produced ONE false positive, "## Per-module reviewer (sonnet)" in
# `skills/odoo-code-review/references/agent-prompts.md` - a regex artifact, not a real phase
# heading (the greedy `\S*` treated the hyphen INSIDE "Per-module" as the "P<x> - <name>"
# separator). Anchoring to an actual phase-ID token (`P\d+[a-zA-Z]?`) closed that false positive
# while still matching both genuine sites.
#
# Structural exclusion (NOT a filename allowlist): idiom (c) also matches one sentence in
# `odoo-deep-survey/SKILL.md`'s own `## Role` section ("fans out anonymous worker agents to
# map...") - a one-line ABSTRACT overview of the skill's mechanism, not a per-phase dispatch
# instruction (the skill's REAL per-phase tiers are stated later, in its Phase 1/2/3 headings,
# which idiom (b) already matches and finds compliant). `## Role` is a MANDATORY, test-enforced
# heading in every skill (`test_skill_format.py`) whose own contract is "operating role/audience/
# scope", never per-phase dispatch mechanics - so excluding matches that fall inside a file's own
# `## Role` section is a STRUCTURAL exclusion (any file, present or future, that shares this
# heading gets the same treatment), never a per-file/filename carve-out.
#
# DISPATCH_VERB_RE is the ONE verb alternation shared by every idiom below AND by
# `WRITE_CONSTRAINED_SCOUT_RE`'s idiom (a) further down - a single constant, not two lists that
# can drift. This closes a real defect a reviewer found in an earlier version of this file: the
# registration detector once used a NARROWER verb list ("Launch|Dispatch" only) than the
# tier-check detector ("Launch|Dispatch|Spin up|Fan out|Fire off"), so "Spin up a recon-class
# subagent (Explore)..." was recognized as a recon dispatch for TIER purposes but silently exempt
# from the Clause-3 registry - the guard-scoped-to-one-syntactic-shape failure this whole round
# exists to close, reintroduced inside the fix for it. The VERB describes the ACT of dispatching
# and has NOTHING to do with whether the dispatched agent is Write-constrained - narrowing on verb
# was never a valid way to narrow the registration guard; both detectors below use this identical
# alternation, and the two detectors diverge ONLY on the axis documented next to
# `WRITE_CONSTRAINED_SCOUT_RE`.
DISPATCH_VERB_RE = r"(?:Launch|Dispatch|Spin up|Fan(?:s)?\s+out|Fire off)(?:es|ing)?"

DISPATCH_RECON_RE = re.compile(
    r"\b" + DISPATCH_VERB_RE + r"\b"
    r"(?:"
    r"(?![^.\n]{0,20}`)[^.\n]{0,60}?\bworkers?\b[^.\n]{0,10}?\bagents?\b"
    r"[^.\n]{0,100}?\b(?:map|maps|mapping|survey|surveys|enumerate|enumerates|discover|discovers)\b"
    r"|"
    r"[^.\n]{0,60}?\b(?:recon(?:naissance)?(?:[- ](?:class|type))?\s+(?:subagents?|agents?)|scouts?)\b"
    r")"
    r"|"
    r"^#{1,6}\s*(?:P\d+[a-zA-Z]?|Phase\s*\d+[a-zA-Z]?)\s*-\s*[^\n(]*\([^)\n]*"
    r"\b(?:haiku|sonnet|opus|fable|Explore)\b[^)\n]*\)",
    re.IGNORECASE | re.MULTILINE,
)

# The narrower Write-constrained/anonymous-scout SUBSET of the detector above - reused ONLY by the
# Clause-3 registration-completeness check (test_every_shared_detector_recon_site_is_registered).
# Clause 3 (scouting-persistence-contract.md) exists specifically for a Write-CONSTRAINED scout
# (`Explore`, or another anonymous read-only type that cannot save its own file) - a NAMED,
# Write-capable, registered agent (e.g. `odoo-review-scoper`, dispatched as
# "Dispatch agent `odoo-review-scoper` (sonnet)") writes its OWN file directly and needs no
# parent-transcription registration at all.
#
# THE DISCRIMINATOR (stated explicitly, per review): Write-constrained-ness is a property of WHAT
# is dispatched, never of the VERB used to dispatch it (see the note above `DISPATCH_VERB_RE` -
# that was the bug). The two textual signals that actually indicate a Write-constrained scout,
# grounded directly in Clause 2's own definition ("a Write-constrained agent type (`Explore`, or
# another ANONYMOUS read-only type)"), are:
#   1. a GENERIC noun for the dispatched worker - "recon subagent(s)", "recon-class/-type
#      subagent(s)", or bare "scout(s)" - used INSTEAD OF a specific backtick-quoted registered
#      agent name. A generic noun is how you refer to something that has no name of its own,
#      which is exactly what "anonymous" means; a NAMED agent (`odoo-review-scoper`,
#      `odoo-diff-comparator`, ...) is Write-capable by construction (it is a full registered
#      agent file, not an anonymous type) and writes its own artifact directly - this is idiom (a)
#      below, verb-shared with the tier detector, narrowed only by this noun choice.
#   2. the literal `Explore` token - this repo's own name for the built-in Write-constrained agent
#      type - appearing in a phase-ID heading's parenthesised worker declaration (idiom (b)
#      below). A heading whose parens carry any OTHER tier word (haiku/sonnet/opus/fable) with no
#      `Explore` token is NOT evidence of Write-constraint by itself (measured:
#      `odoo-deep-survey/SKILL.md`'s Phase 1/2 headings carry `(haiku)`/`(sonnet)` with no
#      `Explore` token, and that skill's workers persist their OWN file directly per its own
#      `<SHARE_DIR>/survey/` cache contract - never routing through
#      scouting-persistence-contract.md at all) - so idiom (b) here requires the literal token,
#      unlike the tier detector's idiom (b) which accepts any of the five.
# Idiom (c) (the anonymous "worker agent...map/survey/enumerate/discover" clause) is deliberately
# NOT included here at all: "worker agent" is even more generic than "recon subagent"/"scout", and
# reusing it for registration would require every such site provably route through
# scouting-persistence-contract.md, which is not true tree-wide (same `odoo-deep-survey` case).
# Measured: 3 files (`odoo-intake/SKILL.md`, `upg-phase-detail.md`, `odoo-debug/SKILL.md`) -
# 0 unregistered.
WRITE_CONSTRAINED_SCOUT_RE = re.compile(
    r"\b" + DISPATCH_VERB_RE + r"\b[^.\n]{0,60}?"
    r"\b(?:recon(?:naissance)?(?:[- ](?:class|type))?\s+(?:subagents?|agents?)|scouts?)\b"
    r"|"
    r"^#{1,6}\s*P\d+[a-zA-Z]?\s*-\s*[^\n(]*\([^)\n]*\bExplore\b[^)\n]*\)",
    re.IGNORECASE | re.MULTILINE,
)

TIER_TOKEN_RE = re.compile(r"\b(haiku|sonnet|opus|fable)\b", re.IGNORECASE)
TIER_POINTER_RE = re.compile(r"concurrency-guard\.md", re.IGNORECASE)
WINDOW_AFTER_MATCH = 500
ROLE_HEADING_RE = re.compile(r"^##\s+Role\s*$", re.MULTILINE)
NEXT_HEADING_RE = re.compile(r"^##\s+", re.MULTILINE)


def _role_section_spans(norm_text: str) -> list[tuple[int, int]]:
    """(start, end) char spans of every file's own `## Role` section (up to the next `## `
    heading, or EOF). Used ONLY to apply the structural exclusion documented above - never to
    exclude by filename."""
    spans = []
    for m in ROLE_HEADING_RE.finditer(norm_text):
        nxt = NEXT_HEADING_RE.search(norm_text, m.end())
        end = nxt.start() if nxt else len(norm_text)
        spans.append((m.start(), end))
    return spans


def _in_any_span(pos: int, spans: list[tuple[int, int]]) -> bool:
    return any(start <= pos < end for start, end in spans)


def _recon_dispatch_offenders(text_by_path: dict[Path, str]) -> list[str]:
    """The ONE reusable offender-finder - every test in this module that needs to know 'which
    DISPATCH_RECON_RE site has no stated tier and no SSOT pointer nearby' calls this, rather than
    reimplementing the window-check logic a second time (including the synthetic-construct test
    below, which proves the SAME production logic - not a parallel copy - now flags the evasive
    phrasing)."""
    offenders = []
    for path, norm in text_by_path.items():
        role_spans = _role_section_spans(norm)
        for m in DISPATCH_RECON_RE.finditer(norm):
            start = m.start()
            if _in_any_span(start, role_spans):
                continue
            window = norm[start:start + WINDOW_AFTER_MATCH]
            if TIER_TOKEN_RE.search(window) or TIER_POINTER_RE.search(window):
                continue
            offenders.append(f"{path}:~char{start}: {norm[start:start + 140]!r}")
    return offenders


def test_recon_dispatch_sites_state_a_tier():
    """Genre A (whole-tree, no allowlist). For every textual site in skills/+agents/ that matches
    `DISPATCH_RECON_RE` (any idiom above), a model tier token (haiku/sonnet/opus/fable) or an
    explicit pointer to the concurrency-guard.md SSOT must appear within the following ~500
    characters (trivially true for idioms (b)/most of (c), since the tier token is inside the
    match itself) - excluding a match that falls inside the file's own `## Role` section (see the
    structural-exclusion note above `DISPATCH_RECON_RE`).

    Measured (current tree, post-widening): 7 matches across 4 files - 2 inside
    `odoo-intake/SKILL.md`, 2 inside `upg-phase-detail.md` (P1a/P1d), 2 inside
    `odoo-deep-survey/SKILL.md` (Phase 1/Phase 2 headings), 1 inside `odoo-debug/SKILL.md`
    ("Dispatch ONE anonymous Explore/recon-class subagent") - 0 offenders in all 7 (one further
    match, `odoo-deep-survey/SKILL.md`'s `## Role`-section overview sentence, is excluded by the
    structural filter, not miscounted as compliant or silently dropped).

    Fails if: any recon-dispatch clause anywhere in the tree states no tier and no SSOT pointer
    within range - including a brand-new site nobody has written yet, which is the entire point
    of scoping this whole-tree rather than to the one historically-known offender.
    """
    text_by_path = {}
    for path in _tree_md_files():
        text = path.read_text(encoding="utf-8")
        norm = re.sub(r"[ \t]+", " ", text)
        text_by_path[path.relative_to(PLUGIN)] = norm
    offenders = _recon_dispatch_offenders(text_by_path)
    assert not offenders, (
        "Recon/scouting dispatch site(s) with no stated tier and no SSOT pointer within "
        f"{WINDOW_AFTER_MATCH} chars:\n" + "\n".join(offenders)
    )


def test_widened_detector_catches_evasive_worker_phrasing():
    """Genre A (regression/construct test - proves the WIDENED production detector, not a copy of
    it, now recognizes a real evasive phrasing this guard previously missed entirely).

    Verified evasive construct (would have matched NEITHER the original 2-idiom
    `DISPATCH_RECON_RE` NOR the original Clause-3 registration check): a "Discovery sweep" phase
    that dispatches an anonymous worker agent to do recon-shaped work ("map current usage") with
    no stated tier, AND explicitly folds distinct scouts' returns into one summary (violating
    Clause 3 of scouting-persistence-contract.md - covered separately by
    test_scouting_persistence.py's structural-cue test).

    Pre-widening (measured against `git show HEAD` of this test file): the original
    `DISPATCH_RECON_RE` does not match this construct at all (no "Launch/Dispatch", no
    "recon"/"scout" noun, no `P<n>`-style heading) - it would have walked past this guard AND the
    guard's own site-detection undetected, exactly the failure mode the widening above closes.

    Fails if: the widened detector stops matching this construct, or the reused
    `_recon_dispatch_offenders` helper stops flagging it as tier-less.
    """
    construct = (
        "### Discovery sweep\n"
        "Spin up one worker agent per candidate area to map current usage. Each worker keeps its\n"
        "findings in its reply; fold the replies together into one summary before continuing.\n"
    )
    assert DISPATCH_RECON_RE.search(construct), (
        "the widened DISPATCH_RECON_RE must recognize the 'Spin up one worker agent... to map...' "
        "dispatch shape - it did not, meaning the widening regressed."
    )
    offenders = _recon_dispatch_offenders({Path("synthetic-construct.md"): construct})
    assert offenders, (
        "the evasive construct states no tier and no SSOT pointer - it must be flagged as an "
        "offender by the SAME production offender-finder the whole-tree test uses, proving this "
        "guard would now catch it if a new site were ever phrased this way."
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
    """Genre A (GENERAL CLASS, whole-tree). Every FILE matched by `WRITE_CONSTRAINED_SCOUT_RE`
    anywhere in skills/+agents/ must have at least one row in Clause 3's consumer registry - a NEW
    Write-constrained/anonymous-scout site that is never registered turns this test red, instead
    of silently walking past a named list.

    Detector choice (why this test uses `WRITE_CONSTRAINED_SCOUT_RE`, the narrower SUBSET of
    `DISPATCH_RECON_RE`, not the full widened detector `test_recon_dispatch_sites_state_a_tier`
    uses): Clause 3 exists specifically for a Write-CONSTRAINED scout (`Explore`, or another
    anonymous read-only type that cannot save its own file) - see the comment above
    `WRITE_CONSTRAINED_SCOUT_RE`'s definition for the measured reason the full detector cannot be
    reused here without wrongly demanding a Clause-3 row from `odoo-deep-survey/SKILL.md` (a real
    recon-tier site with its OWN, separate, direct-write persistence contract - not Write-
    constrained, not a Clause-3 consumer). This is a documented, principled narrowing of the
    original "one shared detector" note below, not a second detector invented to dodge a failure:
    the registration guard's true business rule (Write-constrained dispatch) is a strict subset of
    the tier-statement guard's (any recon dispatch).

    Measured (current tree): `WRITE_CONSTRAINED_SCOUT_RE` matches inside three files -
    `odoo-intake/SKILL.md` (2 matches), `upg-phase-detail.md` (2 matches, P1a + P1d), and
    `odoo-debug/SKILL.md` (1 match, "Dispatch ONE anonymous Explore/recon-class subagent") - all
    three registered, 0 offenders.

    History (why the recon-class-subagent phrasing and the Explore-anchored P-heading idiom are
    both covered, not left as a documented gap): the first version of this test only reused the
    dispatch-verb half of the detector, which could not see `odoo-modules-upgrade`'s P1a/P1d sites
    (phrased as a `### P1a - DAG build (Explore, sonnet)` heading + task block, never a
    "Launch/Dispatch a recon subagent/scout" sentence) - a real blind spot, at the time reported
    via a separate pinning assertion. That pinning assertion was itself a defect: asserting the
    detector CANNOT see a known site makes the gap load-bearing - the moment someone correctly
    widens the detector, that assertion goes red and reads like breakage, inviting a revert
    instead of a fix. It was removed. The detector was widened instead. A second class sweep later
    found `odoo-debug/SKILL.md`'s "Explore/recon-class subagent" phrasing was ALSO invisible (the
    hyphenated qualifier broke the original "recon" + whitespace + "subagent" match) - widened again, in lockstep
    with registering that site (see `test_clause3_registry_rows_each_cite_the_clause_in_their_own_section`).
    """
    registry = _parse_clause3_registry(CONTRACT.read_text(encoding="utf-8"))
    registered_files = {relpath for relpath, _ in registry}

    offenders = []
    for path in _tree_md_files():
        relpath = str(path.relative_to(PLUGIN))
        text = path.read_text(encoding="utf-8")
        norm = re.sub(r"[ \t]+", " ", text)
        if WRITE_CONSTRAINED_SCOUT_RE.search(norm) and relpath not in registered_files:
            offenders.append(relpath)
    assert not offenders, (
        "Write-constrained recon/scout dispatch site(s) found by the shared detector but not "
        f"registered in Clause 3's consumer registry: {offenders}"
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
