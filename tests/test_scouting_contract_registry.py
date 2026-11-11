"""Every row of the consumer registry of snippets/scouting-persistence-contract.md Clause 3 names a
site file that exists and an anchor that is really in it."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parent.parent / "plugins" / "odoo-ai-agents"
CONTRACT = PLUGIN / "snippets" / "scouting-persistence-contract.md"


def _registry():
    text = CONTRACT.read_text(encoding="utf-8")
    block = text[text.index("**Consumer registry"):]
    rows = re.findall(r"^\|\s*`([^`]+)`\s*\|\s*`([^`]+)`\s*\|\s*$", block, re.MULTILINE)
    assert rows, "the Clause 3 consumer registry lost its rows"
    return rows


def _site_file(site):
    return PLUGIN / (site if "/" in site else "skills/%s/SKILL.md" % site)


@pytest.mark.parametrize("site,anchor", _registry())
def test_a_registry_row_names_a_site_and_anchor_that_exist(site, anchor):
    path = _site_file(site)
    assert path.is_file(), "registry row %r: no such site file %s" % (site, path)
    assert anchor in path.read_text(encoding="utf-8"), (
        "registry row %r: anchor %r is not in the file - the section was renamed or removed, "
        "so the row points at nothing" % (site, anchor))
