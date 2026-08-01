"""Guard: the hand-maintained persona docs must not drop a safety-relevant
clause from the generated tool surface, and must not silently drift from the
router's persona/domain list.

None of docs/personas/*.md|*.vi.md is under the SSOT generator (owner
decision: guard, do not generate - a fifth generator function would newly
regenerate a human-facing doc on every server-surface.json edit, and each
Vietnamese mirror would need a guard regardless). These assertions are the
substitute.

WORDING FIDELITY OF THE VIETNAMESE TRANSLATION IS OUT OF SCOPE, and deliberately
so: there is no LLM judge in tests/, and a lexical check over translated prose
would either pass everything or block legitimate rewording (measured: only 1 of
20 dev.md rows and 0 of 20 dev.vi.md rows contain the SSOT description's first
sentence verbatim - "assert containment of the canonical sentence" is therefore
not implementable). What IS checkable in both files is (1) code identifiers,
which are never translated, (2) the structural parity of the two tables, and
(3) a small, explicit list of known evasion phrasings for one specific rule (the
OSM session-pin race - see skills/_shared/concurrency-guard.md) that already has
an English-only guard in tests/test_agent_facing_guidance.py. Do not generalize
these tests into a translation-quality gate.

--- Runtime-loaded vs human-facing reference (decides the widening below) -----
docs/personas/ is NEVER Read by any skill/agent/snippet/command/workflow/hook
at runtime - grep-verified across the whole plugin (only README.md, docs/
setup.md, CONTRIBUTING.md, and CHANGELOG.md reference the path, all four
human-facing). It is therefore legitimate for it to be a CURATED SUBSET of the
9 persona buckets `odoo-intake` routes to (docs/setup.md already says so: "The
five role guides in personas/ ... group these buckets. This table is a
curated subset") - authoring a guide for every remaining domain merely to make
a count match would be manufactured work, not a fix for a runtime gap. What
DOES need a fence is the two going silently out of sync: a doc pair for a
domain the router no longer recognizes (orphaned guide), a doc pair added or
removed without updating the SSOT mapping below, or one language of a pair
shipping without its counterpart. See the "router persona/domain list" section
near the bottom of this file for that guard.

--- Row-format scope note (decides the widening of the four SSOT-derived tests
below) -------------------------------------------------------------------
Only dev.md/dev.vi.md use the tool-call-signature row format
(a table cell opening with a backtick-quoted "tool_name(...)") `_ROW_RE`
matches - by design, per the file's own comment ("intentionally enumerates the
full 31-tool arsenal instead of the 'Most Useful Tools' template variant").
ceo/consultant/marketer/sales use a bare-name "tool_name" table cell with NO
call signature. Widening the
four SSOT-derived tests below from dev-only to EVERY persona pair is still the
right move (a persona doc adopting the signature format later is covered for
free, and nothing regresses since `_rows()` returns an empty list for the
other four today) - measured: 0 additional offenders across all four tests on
the current tree, because there is nothing for `_ROW_RE` to match yet in
ceo/consultant/marketer/sales.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
SURFACE_FILE = PLUGIN / "generator" / "server-surface.json"
PERSONAS_DIR = PLUGIN / "docs" / "personas"

# --- SSOT: which persona docs exist, and which router domain each documents ----
# Nothing else in the repo structurally declares "which domain does dev.md
# correspond to" - this dict IS that declaration. Adding/removing a
# docs/personas/<x>.md + <x>.vi.md pair must update this map in the SAME
# commit; test_persona_doc_set_matches_domain_mapping fails otherwise.
PERSONA_DOC_DOMAIN = {
    "ceo": "strategy",
    "consultant": "consultant",
    "dev": "engineering",
    "marketer": "marketing",
    "sales": "sales",
}

# The router's full persona/domain list - mirrors workflows/_schema.md's
# `domain` enum (9 persona buckets), which drives `odoo-intake` tier-3 routing.
# Same set tests/test_workflow_format.py's ALLOWED_DOMAINS mirrors, from the
# same SSOT (workflows/_schema.md section 3) - kept as a second, independent
# copy here (not imported) because a workflow-schema change should force a
# conscious update of BOTH the workflow contract test and this persona-doc
# guard, not silently pass one because it imported the other's already-stale
# copy.
ROUTER_DOMAINS = {
    "engineering",
    "sales",
    "presales",
    "marketing",
    "strategy",
    "qa",
    "support",
    "content",
    "consultant",
}


def _persona_pairs() -> list[tuple[Path, Path]]:
    """(English, Vietnamese) path pairs for every mapped persona, in a stable
    (sorted) order. Does NOT glob the disk - iterates PERSONA_DOC_DOMAIN, the
    SSOT, so a file present on disk but absent from the map is caught by
    test_persona_doc_set_matches_domain_mapping instead of silently joining
    the pair list here."""
    return [
        (PERSONAS_DIR / f"{name}.md", PERSONAS_DIR / f"{name}.vi.md")
        for name in sorted(PERSONA_DOC_DOMAIN)
    ]


# A table row whose first cell opens with a tool call signature, e.g.
# "| `test_base_classes(odoo_version="<version>")` | ...".
_ROW_RE = re.compile(r"^\|\s*`([a-z_]+)\(")
# CamelCase graph/class identifiers - never translated, never paraphrased.
_CAMEL_RE = re.compile(r"\b[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+\b")
# A parenthesized COMMA LIST in a description is an explicit enumeration the
# persona row mirrors item-for-item (e.g. "(TransactionCase, HttpCase,
# SavepointCase, Form, etc.)"). A CamelCase name in running prose
# (module_inspect's "TestClass nodes", js_test_inspect's "JsTestSuite nodes") is
# an internal node type a persona row legitimately omits, so it is NOT required.
_PAREN_RE = re.compile(r"\(([^()]*)\)")


def _tools() -> dict:
    return {t["name"]: t for t in json.loads(SURFACE_FILE.read_text(encoding="utf-8"))["tools"]}


def _rows(path: Path) -> list[tuple[int, str, str]]:
    out = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        m = _ROW_RE.match(line)
        if m:
            out.append((i, m.group(1), line))
    return out


def _enumerated_identifiers(desc: str) -> set[str]:
    ids: set[str] = set()
    for grp in _PAREN_RE.findall(desc):
        if "," in grp:
            ids |= set(_CAMEL_RE.findall(grp))
    return ids


def test_enumerated_identifiers_survive_in_both_personas():
    """Every CamelCase identifier the SSOT lists inside a parenthesized enumeration
    must appear in that tool's row, in BOTH language files of EVERY persona pair
    (not dev-only - see module docstring "Row-format scope note").

    Genre A: the required set is COMPUTED from server-surface.json and the row set
    is derived by scanning the file - no hardcoded list on either axis. A tool that
    gains an enumerated class in the SSOT turns this red until every persona
    documenting it carries it; a persona that drops one turns it red immediately.
    That is exactly the reported drift (SavepointCase dropped from the
    test_base_classes row in dev.md)."""
    tools = _tools()
    offenders = []
    for en, vi in _persona_pairs():
        for path in (en, vi):
            for lineno, name, line in _rows(path):
                tool = tools.get(name)
                if tool is None:
                    continue
                for ident in sorted(_enumerated_identifiers(tool["description"])):
                    if ident not in line:
                        offenders.append(
                            f"{path.relative_to(ROOT)}:{lineno}: {name} row omits '{ident}' "
                            f"(enumerated in server-surface.json) - add it to the row"
                        )
    assert not offenders, (
        "Persona tool rows dropped an identifier the tool surface enumerates. Add it to "
        "the row (both language files) or remove it from server-surface.json:\n"
        + "\n".join(offenders)
    )


# Each pair is (SSOT marker, row marker): the SSOT marker decides WHICH tools this
# clause applies to (computed - a tool whose description contains it becomes a
# subject automatically); the row marker is what the persona row must carry to
# count as still conveying that clause. They are not always the same literal
# string: tests_covering's SSOT description also says "not runtime executed
# coverage", but its (untouched, correctly-worded) row already conveys that via
# the word "static" - measured, requiring the identical SSOT phrase verbatim in
# the row produced a false positive on tests_covering that is not part of the
# reported drift. Matching on "static" instead keeps the check computed from the
# SSOT on the subject axis while no longer flagging a row that already states the
# distinction in fewer words. Case-insensitive: a row may open a sentence with the
# capitalized form.
_SAFETY_CLAUSES = (
    ("for the given version", "for the given version"),
    ("not runtime executed", "static"),
)


def test_safety_clauses_survive_in_the_english_persona():
    """A tool whose SSOT description carries a safety clause must carry it in
    EVERY English persona file that documents it (not dev.md-only).

    English only, by construction: a Vietnamese cell cannot contain an English
    clause. Vietnamese coverage of the same axis is structural - see
    test_persona_tables_are_structurally_identical."""
    tools = _tools()
    offenders = []
    for en, _vi in _persona_pairs():
        for lineno, name, line in _rows(en):
            tool = tools.get(name)
            if tool is None:
                continue
            for ssot_marker, row_marker in _SAFETY_CLAUSES:
                if ssot_marker in tool["description"] and row_marker.lower() not in line.lower():
                    offenders.append(
                        f"{en.relative_to(ROOT)}:{lineno}: {name} row omits the safety clause "
                        f"'{row_marker}' (server-surface.json states '{ssot_marker}') - "
                        f"add wording that conveys it to the row"
                    )
    assert not offenders, (
        "A docs/personas/*.md dropped a safety clause the tool surface states:\n"
        + "\n".join(offenders)
    )


def test_persona_tables_are_structurally_identical():
    """For EVERY persona pair, the English and Vietnamese file must name the SAME
    tools, the same number of times, in the same order. This is the Vietnamese
    file's coverage for every axis a lexical English check cannot reach: a row
    cannot be dropped, added, or reordered in one file alone. Fence: green today
    and expected to stay green."""
    offenders = []
    for en, vi in _persona_pairs():
        en_names = [name for _, name, _ in _rows(en)]
        vi_names = [name for _, name, _ in _rows(vi)]
        if en_names != vi_names:
            offenders.append(
                f"{en.name}/{vi.name} diverged (same tools, same count, same order required)\n"
                f"  {en.name}: {en_names}\n  {vi.name}: {vi_names}"
            )
    assert not offenders, "persona tool tables diverged:\n" + "\n".join(offenders)


def test_every_persona_tool_still_exists_in_the_surface():
    """A tool renamed or removed from server-surface.json must not survive as a
    persona row, in ANY persona pair. Fence: catches a removal the personas were
    not updated for.

    Note the asymmetry: this does NOT catch the reverse (a tool newly ADDED to
    server-surface.json with no row in any persona file at all) - no persona
    file documents all current tools as signature rows (11 "base tools" are
    listed bare-name, without a call signature, and are out of this file's
    `_ROW_RE` scan), so "every SSOT tool must have a row" is not this repo's
    editorial policy and asserting it here would be a new, undecided contract,
    not a guard against drift of what is already documented."""
    tools = _tools()
    missing = sorted({
        f"{p.relative_to(ROOT)}:{lineno}: {name}"
        for en, vi in _persona_pairs()
        for p in (en, vi)
        for lineno, name, _ in _rows(p)
        if name not in tools
    })
    assert not missing, (
        "persona rows name tools absent from server-surface.json:\n" + "\n".join(missing)
    )


# --- Vietnamese counterpart of the OSM session-pin evasion guard -----------------
# tests/test_agent_facing_guidance.py bans, in English only, prose that licenses
# omitting odoo_version after a set_active_version pin (the pin is scoped per MCP
# session and racy when actors share one - see skills/_shared/concurrency-guard.md,
# "OSM session-pin race"). That file's own docstring says the Vietnamese mirror "is
# covered structurally" here. It is not, for arbitrary prose (a paraphrase can
# reorder around any fixed set of English regexes) - but the two known evasions
# ("khong co odoo_version=", "khong can lap lai phien ban") are covered: SCOPE IS
# THE WHOLE FILE, not just table rows, and now EVERY persona's .vi.md, not just
# dev.vi.md - an earlier version of this test scanned dev.vi.md table rows only,
# via `_rows(VI)`; that double-narrowing (rows-only, dev-only) was itself a live
# gap - the exact forbidden claim ("khong can lap lai phien ban o cac loi goi
# tiep theo") survived, uncaught, in dev.vi.md's free-text "Sample Developer
# Questions" section (not a `_ROW_RE` table row) until it was found and fixed.
# Restricting a structural assertion to one syntactic shape, or one file, is
# precisely how the original drift AND this evasion both went unnoticed, so this
# scans every line of every persona .vi.md, in either section.
_VI_VERSION_OMISSION_RE = re.compile(
    r"không\s+(?:có|cần|phải)\s+[`'\"]?odoo_version"  # "without/no need for/must not odoo_version"
    r"|bỏ\s+[`'\"]?odoo_version"  # "drop odoo_version"
    r"|odoo_version[^\n]{0,40}\bfallback\b"  # "odoo_version ... falls back"
    r"|(?:không\s+cần|không\s+phải)\s+lặp\s+lại\s+phiên\s+bản",  # "no need to repeat the version"
    re.IGNORECASE,
)
# A line that PROHIBITS the omission necessarily names the same words the pattern
# above matches on ("... KHONG CHO PHEP bo `odoo_version=` ..." - dev.vi.md:96's
# correct, already-shipped wording) - measured as a live false positive when this
# guard was widened to whole-file scope. Excluding a line that carries one of these
# negation markers is a tighter rule than the bare keyword match above, not a
# broader allowlist: it does not name a specific line or tool, only a closed set of
# Vietnamese negation verbs that make "drop/bo odoo_version" the STATED rule rather
# than a licensed evasion of it.
_VI_NEGATION_MARKERS = ("không cho phép", "không được", "cấm")


def _vi_line_is_a_prohibition(line: str) -> bool:
    lowered = line.lower()
    return any(marker in lowered for marker in _VI_NEGATION_MARKERS)


def test_vietnamese_prose_does_not_license_omitting_odoo_version():
    """No line in ANY persona .vi.md - a table row OR free-running prose - may
    claim odoo_version can be dropped, or that the version need not be repeated,
    once a session is pinned. This is the Vietnamese-language counterpart of
    test_agent_facing_guidance.py's English-only guard: SSOT split by language,
    not duplicated. English coverage lives in test_agent_facing_guidance.py (it
    already whole-file-scans skills/snippets/agents/docs, so it needs only a
    matching pattern, not a second scanner); Vietnamese coverage lives here
    because nothing else in the suite reads Vietnamese."""
    offenders = []
    for _en, vi in _persona_pairs():
        for i, line in enumerate(vi.read_text(encoding="utf-8").splitlines(), 1):
            if _VI_VERSION_OMISSION_RE.search(line) and not _vi_line_is_a_prohibition(line):
                offenders.append(f"{vi.relative_to(ROOT)}:{i}: {line.strip()}")
    assert not offenders, (
        "A docs/personas/*.vi.md licenses omitting odoo_version, or not repeating "
        "it, after a set_active_version pin - the pin is scoped per MCP session and "
        "racy when actors share one, so every call must still carry a concrete "
        "odoo_version:\n" + "\n".join(offenders)
    )


# --- Persona-doc coverage vs the router's persona/domain list ------------------
# docs/personas/ documents 5 of the router's 9 persona/domain buckets - a
# CURATED SUBSET, not a runtime gap (see module docstring). That asymmetry
# itself is fine and is NOT what these tests assert against. What they DO
# assert: the three facts (what is on disk, what PERSONA_DOC_DOMAIN maps, and
# what the router still recognizes) must never silently diverge from each
# other, in either direction.
def test_persona_doc_set_matches_domain_mapping():
    """Every docs/personas/<x>.md on disk must be a key in PERSONA_DOC_DOMAIN,
    and every key in PERSONA_DOC_DOMAIN must exist on disk - catches a persona
    doc added or removed without updating the SSOT mapping in the SAME commit."""
    on_disk = {
        p.stem for p in PERSONAS_DIR.glob("*.md")
        if not p.stem.endswith(".vi")
    }
    mapped = set(PERSONA_DOC_DOMAIN)
    only_on_disk = sorted(on_disk - mapped)
    only_in_map = sorted(mapped - on_disk)
    assert not only_on_disk and not only_in_map, (
        "docs/personas/ file set and PERSONA_DOC_DOMAIN (this file's SSOT "
        "mapping) diverged - "
        f"on disk but unmapped: {only_on_disk}; mapped but missing the English "
        f"file on disk: {only_in_map}. Update PERSONA_DOC_DOMAIN in the same "
        "commit as adding/removing a docs/personas/<x>.md."
    )


def test_persona_doc_pair_languages_both_exist():
    """Every mapped persona must have BOTH an English and a Vietnamese file on
    disk - catches a half-authored pair (one language added/removed without the
    other)."""
    missing = []
    for name in PERSONA_DOC_DOMAIN:
        en = PERSONAS_DIR / f"{name}.md"
        vi = PERSONAS_DIR / f"{name}.vi.md"
        if not en.is_file():
            missing.append(str(en.relative_to(ROOT)))
        if not vi.is_file():
            missing.append(str(vi.relative_to(ROOT)))
    assert not missing, (
        "persona doc pair incomplete (both languages are required for every "
        f"mapped persona): {missing}"
    )


def test_persona_doc_domains_are_still_valid_router_domains():
    """Every domain a persona doc documents (per PERSONA_DOC_DOMAIN) must still
    be one the router recognizes (the `domain` enum in workflows/_schema.md,
    mirrored here as ROUTER_DOMAINS). Catches the router renaming or removing a
    domain out from under a hand-authored guide - the guide would otherwise
    silently document a persona/domain `odoo-intake` no longer routes to."""
    stale = sorted(
        f"{name} -> {domain!r} (not in the router's domain enum)"
        for name, domain in PERSONA_DOC_DOMAIN.items()
        if domain not in ROUTER_DOMAINS
    )
    assert not stale, (
        "docs/personas/ documents a domain the router no longer recognizes "
        f"(workflows/_schema.md domain enum): {stale}"
    )
