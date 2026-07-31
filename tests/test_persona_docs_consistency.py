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
OSM session-pin race - see skills/_shared/concurrency-guard.md) that already has
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


# --- Vietnamese counterpart of the OSM session-pin evasion guard -----------------
# tests/test_agent_facing_guidance.py bans, in English only, prose that licenses
# omitting odoo_version after a set_active_version pin (the pin is API-key-scoped
# and racy under concurrency - see skills/_shared/concurrency-guard.md, "OSM
# session-pin race"). That file's own docstring says the Vietnamese mirror "is
# covered structurally" here. It is not, for arbitrary prose (a paraphrase can
# reorder around any fixed set of English regexes) - but the reported live defect
# was literal Vietnamese phrasing ("không có `odoo_version=`") in a TABLE ROW, and
# that axis is covered: the fix landed in dev.vi.md's set_active_version row (see
# git history), and this test guards every table row in dev.vi.md against the same
# phrasing being reintroduced, in either language, without needing English regexes
# at all.
_VI_VERSION_OMISSION_RE = re.compile(
    r"không\s+(?:có|cần|phải)\s+[`'\"]?odoo_version"  # "without/no need for/must not odoo_version"
    r"|bỏ\s+[`'\"]?odoo_version"  # "drop odoo_version"
    r"|odoo_version[^\n]{0,40}\bfallback\b",  # "odoo_version ... falls back"
    re.IGNORECASE,
)


def test_vietnamese_rows_do_not_license_omitting_odoo_version():
    """No dev.vi.md tool row may claim odoo_version can be dropped once a version is
    pinned - the Vietnamese-language counterpart of test_agent_facing_guidance.py's
    English-only guard, scoped to the rows this file already parses.

    Residual gap, reported rather than silently left open: this scans table ROWS
    only. The same forbidden claim ("khong can lap lai phien ban o cac loi goi tiep
    theo") also appears in dev.vi.md's free-text "Sample Developer Questions"
    section (and its English counterpart in dev.md, in the same section) - neither
    is a `_ROW_RE` table row, so neither is scanned by this test or by
    test_agent_facing_guidance.py's existing English patterns. That is a live,
    currently-uncaught instance of the same rule the OSM session-pin race
    prohibits, outside this commit's four-cell scope (a different location than
    the reported drift), reported here rather than fixed silently."""
    tools = _tools()
    offenders = []
    for lineno, name, line in _rows(VI):
        if name not in tools:
            continue
        if _VI_VERSION_OMISSION_RE.search(line):
            offenders.append(
                f"{VI.relative_to(ROOT)}:{lineno}: {name} row licenses omitting "
                f"odoo_version after a session pin (Vietnamese evasion of the rule in "
                f"skills/_shared/concurrency-guard.md, 'OSM session-pin race') - "
                f"rewrite to require the concrete odoo_version on every call"
            )
    assert not offenders, (
        "dev.vi.md table row(s) license omitting odoo_version after set_active_version - "
        "the pin is API-key-scoped and racy under concurrency, so every call must still "
        "carry a concrete odoo_version:\n" + "\n".join(offenders)
    )
