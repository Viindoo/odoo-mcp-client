"""Guard: the hand-maintained developer personas must not drop a safety-relevant
clause from the generated tool surface.

Neither docs/personas/dev.md nor dev.vi.md is under the SSOT generator (owner
decision: guard, do not generate - a fifth generator function would newly
regenerate a human-facing doc on every server-surface.json edit, and the
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
OSM API-key-pin race - see skills/_shared/concurrency-guard.md) that already has
an English-only guard in tests/test_agent_facing_guidance.py. Do not generalize
these tests into a translation-quality gate.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
SURFACE_FILE = PLUGIN / "generator" / "server-surface.json"
EN = PLUGIN / "docs" / "personas" / "dev.md"
VI = PLUGIN / "docs" / "personas" / "dev.vi.md"

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
    must appear in that tool's row, in BOTH persona files.

    Genre A: the required set is COMPUTED from server-surface.json and the row set
    is derived by scanning the file - no hardcoded list on either axis. A tool that
    gains an enumerated class in the SSOT turns this red until both personas carry
    it; a persona that drops one turns it red immediately. That is exactly the
    reported drift (SavepointCase dropped from the test_base_classes row)."""
    tools = _tools()
    offenders = []
    for path in (EN, VI):
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
    """A tool whose SSOT description carries a safety clause must carry it in dev.md.

    English only, by construction: a Vietnamese cell cannot contain an English
    clause. dev.vi.md's coverage of the same axis is structural - see
    test_persona_tables_are_structurally_identical."""
    tools = _tools()
    offenders = []
    for lineno, name, line in _rows(EN):
        tool = tools.get(name)
        if tool is None:
            continue
        for ssot_marker, row_marker in _SAFETY_CLAUSES:
            if ssot_marker in tool["description"] and row_marker.lower() not in line.lower():
                offenders.append(
                    f"{EN.relative_to(ROOT)}:{lineno}: {name} row omits the safety clause "
                    f"'{row_marker}' (server-surface.json states '{ssot_marker}') - "
                    f"add wording that conveys it to the row"
                )
    assert not offenders, (
        "docs/personas/dev.md dropped a safety clause the tool surface states:\n"
        + "\n".join(offenders)
    )


def test_persona_tables_are_structurally_identical():
    """dev.md and dev.vi.md must name the SAME tools, the same number of times, in
    the same order. This is the Vietnamese file's coverage for every axis a lexical
    English check cannot reach: a row cannot be dropped, added, or reordered in one
    file alone. Fence: green today and expected to stay green."""
    en = [name for _, name, _ in _rows(EN)]
    vi = [name for _, name, _ in _rows(VI)]
    assert en == vi, (
        "persona tool tables diverged (same tools, same count, same order required)\n"
        f"dev.md   : {en}\ndev.vi.md: {vi}"
    )


def test_every_persona_tool_still_exists_in_the_surface():
    """A tool renamed or removed from server-surface.json must not survive as a
    persona row. Fence: catches a removal the personas were not updated for.

    Note the asymmetry: this does NOT catch the reverse (a tool newly ADDED to
    server-surface.json with no row in either persona file at all) - neither file
    documents all 31 current tools as signature rows (11 "base tools" are listed
    bare-name, without a call signature, and are out of this file's `_ROW_RE`
    scan), so "every SSOT tool must have a row" is not this repo's editorial
    policy and asserting it here would be a new, undecided contract, not a guard
    against drift of what is already documented."""
    tools = _tools()
    missing = sorted({
        f"{p.relative_to(ROOT)}:{lineno}: {name}"
        for p in (EN, VI)
        for lineno, name, _ in _rows(p)
        if name not in tools
    })
    assert not missing, (
        "persona rows name tools absent from server-surface.json:\n" + "\n".join(missing)
    )


# --- Vietnamese counterpart of the OSM API-key-pin evasion guard -----------------
# tests/test_agent_facing_guidance.py bans, in English only, prose that licenses
# omitting odoo_version after a set_active_version pin (the pin is API-key-scoped
# and racy under concurrency - see skills/_shared/concurrency-guard.md, "OSM
# API-key-pin race"). That file's own docstring says the Vietnamese mirror "is
# covered structurally" here. It is not, for arbitrary prose (a paraphrase can
# reorder around any fixed set of English regexes) - but the two known evasions
# ("khong co odoo_version=", "khong can lap lai phien ban") are covered: SCOPE IS
# THE WHOLE FILE, not just table rows. An earlier version of this test scanned
# table rows only, via `_rows(VI)`; that scoping was itself a live gap - the exact
# forbidden claim ("khong can lap lai phien ban o cac loi goi tiep theo") survived,
# uncaught, in the free-text "Sample Developer Questions" section (not a `_ROW_RE`
# table row) until it was found and fixed. Restricting a structural assertion to
# one syntactic shape is precisely how the original drift AND this evasion both
# went unnoticed, so this scans every line of the file, in either section.
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
    """No line in dev.vi.md - a table row OR free-running prose - may claim
    odoo_version can be dropped, or that the version need not be repeated, once a
    session is pinned. This is the Vietnamese-language counterpart of
    test_agent_facing_guidance.py's English-only guard: SSOT split by language, not
    duplicated. English coverage lives in test_agent_facing_guidance.py (it already
    whole-file-scans skills/snippets/agents/docs, so it needs only a matching
    pattern, not a second scanner); Vietnamese coverage lives here because nothing
    else in the suite reads Vietnamese."""
    offenders = []
    for i, line in enumerate(VI.read_text(encoding="utf-8").splitlines(), 1):
        if _VI_VERSION_OMISSION_RE.search(line) and not _vi_line_is_a_prohibition(line):
            offenders.append(f"{VI.relative_to(ROOT)}:{i}: {line.strip()}")
    assert not offenders, (
        "dev.vi.md licenses omitting odoo_version, or not repeating it, after a "
        "set_active_version pin - the pin is API-key-scoped and racy under "
        "concurrency, so every call must still carry a concrete odoo_version:\n"
        + "\n".join(offenders)
    )
