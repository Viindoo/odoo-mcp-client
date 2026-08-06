"""Tests for the static-vs-live disambiguation block (mirror layer).

AI agents routinely confuse `odoo-semantic` (STATIC source-code index) with a
LIVE-instance Odoo MCP server and call the wrong one - a confident-but-wrong
answer with no error to self-correct on. The server carries the guidance over
the wire (FastMCP `instructions=` + per-tool SKIP lines); this mirror layer
carries the SAME guidance into the generated routing docs + IDE snippets +
SKILL.md so clients that read those (not the live server) inherit it too.

These tests guard that:
  1. server-surface.json declares the `disambiguation` SSOT (identity/precedence/
     not_for/overlap_tools all present and non-empty).
  2. overlap_tools is DATA-DRIVEN off server-surface.json itself, not a second
     hand-maintained copy of the tool-name list: every declared entry must
     resolve to a real, still-live tool (catches a typo/rename/removed-tool
     regression) and the list must be duplicate-free - AND it must still cover
     the known "look-live-but-static" set the live MCP server's own INSTRUCTIONS
     text names (model_inspect, module_inspect, entity_lookup, validate_domain,
     validate_depends, validate_relation, describe_module, check_module_exists,
     resolve_orm_chain) as a floor, not an exact-equality ceiling - so the SSOT
     is free to grow this list without a matching test edit, while a regression
     that silently drops a known member still fails for the right reason.
     (Before this fix, this file's own EXPECTED_OVERLAP_TOOLS constant was a
     SECOND hardcoded copy of server-surface.json's overlap_tools - the
     redundant-hardcoding anti-pattern this test now replaces.)
  3. The rendered block carries the discriminator + the `read_record` marker.
  4. Every generated artifact actually contains the current block - i.e. nobody
     edited the SSOT and forgot to run `make gen` (silent drift).

The block is carried as a dedicated field, NOT appended to a tool description,
because the generators emit only the FIRST sentence of `description`
(`_first_sentence`) - a trailing disambiguation sentence would be dropped.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_PLUGIN = REPO_ROOT / "plugins" / "odoo-ai-agents"
if str(SKILLS_PLUGIN) not in sys.path:
    sys.path.insert(0, str(SKILLS_PLUGIN))

from generator.gen_surface import gen_disambiguation_block  # noqa: E402

SURFACE_FILE = SKILLS_PLUGIN / "generator" / "server-surface.json"

# Floor, not a ceiling: verified (2026-08-06) against the live MCP server's own
# INSTRUCTIONS text ("Tools whose names look live but are STATIC here") - every one of
# these MUST remain in server-surface.json's overlap_tools, but the SSOT may grow the
# list further without needing a matching edit here (see test_overlap_tools_are_data_
# driven_against_the_live_surface, which derives its assertions from the JSON itself).
MUST_INCLUDE_LOOK_LIVE_STATIC_TOOLS = {
    "model_inspect",
    "module_inspect",
    "entity_lookup",
    "validate_domain",
    "validate_depends",
    "validate_relation",
    "describe_module",
    "check_module_exists",
    "resolve_orm_chain",
}

# Generated artifacts that must carry the block (paths relative to skills plugin).
SNIPPET_ARTIFACTS = [
    "snippets/cursor-rules.md",
    "snippets/openai-gpt-instructions.md",
    "snippets/gemini-gem-instructions.md",
]


def _surface() -> dict:
    return json.loads(SURFACE_FILE.read_text(encoding="utf-8"))


def _live_tool_names(surface: dict) -> set[str]:
    """Tool names still live (not version_removed) in server-surface.json."""
    return {t["name"] for t in surface["tools"] if t.get("version_removed") is None}


def test_surface_declares_disambiguation_ssot():
    dis = _surface().get("disambiguation")
    assert dis, "server-surface.json must declare a 'disambiguation' block"
    assert dis.get("identity"), "disambiguation.identity required"
    assert dis.get("precedence"), "disambiguation.precedence required (OSM-first contract)"
    assert isinstance(dis.get("not_for"), list) and dis["not_for"], (
        "disambiguation.not_for must be a non-empty list of boundaries"
    )
    assert dis.get("overlap_tools"), "disambiguation.overlap_tools must be a non-empty list"


def test_overlap_tools_are_data_driven_against_the_live_surface():
    """overlap_tools entries must be real, live, duplicate-free tool names.

    Derived entirely from server-surface.json's own `tools` array (data-driven) -
    no second hardcoded tool-name list to drift out of sync with the JSON.
    """
    surface = _surface()
    overlap = surface["disambiguation"]["overlap_tools"]
    live = _live_tool_names(surface)
    unknown = [t for t in overlap if t not in live]
    assert not unknown, f"overlap_tools names non-live/unknown tool(s): {unknown}"
    assert len(overlap) == len(set(overlap)), "overlap_tools has duplicate entries"


def test_overlap_tools_includes_the_known_look_live_static_floor():
    """Regression guard: the 9 tools verified against the live server's own
    INSTRUCTIONS text must never silently disappear from overlap_tools."""
    overlap = set(_surface()["disambiguation"]["overlap_tools"])
    missing = MUST_INCLUDE_LOOK_LIVE_STATIC_TOOLS - overlap
    assert not missing, f"overlap_tools missing known look-live-but-static tool(s): {missing}"


def test_rendered_block_carries_signature_precedence_and_live_boundary():
    block = gen_disambiguation_block(_surface())
    # Unique positive signature (so a generic/future Odoo-code tool can't claim it).
    assert "INDEXED" in block
    assert "cross-version" in block
    assert "STATIC" in block
    # OSM-first precedence: OSM is PRIMARY, reading code is the FALLBACK.
    assert "PRIMARY" in block
    assert "FALLBACK" in block
    # Live-instance boundary (the one true "wrong server" case).
    assert "live Odoo MCP server" in block
    assert "read_record" in block  # single token, never wraps


def test_generated_artifacts_in_sync_with_block():
    """Every generated artifact must contain the CURRENT block verbatim.

    Fails if the SSOT changed but `make gen` was not re-run (silent drift).
    """
    surface = _surface()
    block = gen_disambiguation_block(surface)
    stale = []
    for rel in SNIPPET_ARTIFACTS:
        text = (SKILLS_PLUGIN / rel).read_text(encoding="utf-8")
        if block not in text:
            stale.append(rel)
    assert not stale, "run `make gen` - these artifacts are stale: " + ", ".join(stale)
