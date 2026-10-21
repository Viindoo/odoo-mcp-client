"""The consumer registry of snippets/scouting-persistence-contract.md Clause 3 stays true.

The contract says a row with no citation, or a citation with no row, is a guard-test failure. These
tests are that guard, and they protect the rule rather than one phrasing:

  - every registry row names a site that exists and an anchor that is really in it;
  - the section that anchor opens cites the contract's clause 3 (a site that registers itself but
    no longer relies on the clause is a dead row, which is how the debug row survived its skill
    dropping the scout it once dispatched);
  - every site in the plugin that cites clause 3 has a registry row (a citation with no row).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parent.parent / "plugins" / "odoo-ai-agents"
CONTRACT = PLUGIN / "snippets" / "scouting-persistence-contract.md"
CONTRACT_NAME = "scouting-persistence-contract.md"
# `clause 3`, `Clause 3`, `clauses 2 and 3`, `clause 3` after a section sign - whitespace-normalised.
CITES_CLAUSE_3 = re.compile(re.escape(CONTRACT_NAME) + r"`?\s*(?:§\s*)?clauses?\s+[0-9, and]*\b3\b",
                            re.IGNORECASE)
HEADING = re.compile(r"^#{1,6}\s", re.MULTILINE)


def _registry():
    text = CONTRACT.read_text(encoding="utf-8")
    block = text[text.index("**Consumer registry"):]
    rows = re.findall(r"^\|\s*`([^`]+)`\s*\|\s*`([^`]+)`\s*\|\s*$", block, re.MULTILINE)
    assert rows, "the Clause 3 consumer registry lost its rows"
    return rows


def _site_file(site):
    return PLUGIN / (site if "/" in site else "skills/%s/SKILL.md" % site)


def _section(text, anchor):
    """The anchor's own section: from the anchor to the next markdown heading (or the end)."""
    start = text.index(anchor)
    nxt = HEADING.search(text, start + len(anchor))
    return text[start:nxt.start() if nxt else len(text)]


def _squash(text):
    return re.sub(r"\s+", " ", text)


@pytest.mark.parametrize("site,anchor", _registry())
def test_a_registry_row_names_a_site_and_anchor_that_exist(site, anchor):
    path = _site_file(site)
    assert path.is_file(), "registry row %r: no such site file %s" % (site, path)
    assert anchor in path.read_text(encoding="utf-8"), (
        "registry row %r: anchor %r is not in the file - the section was renamed or removed, "
        "so the row points at nothing" % (site, anchor))


@pytest.mark.parametrize("site,anchor", _registry())
def test_a_registered_site_still_cites_clause_3_in_the_section_its_anchor_opens(site, anchor):
    text = _site_file(site).read_text(encoding="utf-8")
    assert CITES_CLAUSE_3.search(_squash(_section(text, anchor))), (
        "registry row %r: the section at %r no longer cites clause 3 of the contract - drop the "
        "row if the site stopped dispatching a Write-constrained scout, else restore the citation"
        % (site, anchor))


def test_every_site_citing_clause_3_has_a_registry_row():
    registered = {_site_file(site).resolve() for site, _anchor in _registry()}
    cited = set()
    for path in PLUGIN.rglob("*.md"):
        if path == CONTRACT or "docs" in path.relative_to(PLUGIN).parts[:1]:
            continue
        if CITES_CLAUSE_3.search(_squash(path.read_text(encoding="utf-8", errors="replace"))):
            cited.add(path.resolve())
    assert cited - registered == set(), (
        "sites citing clause 3 with no registry row: %s" % sorted(str(p.relative_to(PLUGIN))
                                                                  for p in cited - registered))
