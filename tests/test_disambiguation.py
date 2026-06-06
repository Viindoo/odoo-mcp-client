"""Tests for the static-vs-live disambiguation block (mirror layer).

AI agents routinely confuse `odoo-semantic` (STATIC source-code index) with a
LIVE-instance Odoo MCP server and call the wrong one - a confident-but-wrong
answer with no error to self-correct on. The server carries the guidance over
the wire (FastMCP `instructions=` + per-tool SKIP lines); this mirror layer
carries the SAME guidance into the generated routing docs + IDE snippets +
SKILL.md so clients that read those (not the live server) inherit it too.

These tests guard that:
  1. server-surface.json declares the `disambiguation` SSOT (with the 6 overlap
     tools that match the server-side per-tool SKIP lines).
  2. The rendered block carries the discriminator + the `read_record` marker.
  3. Every generated artifact actually contains the current block - i.e. nobody
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
SKILLS_PLUGIN = REPO_ROOT / "plugins" / "odoo-semantic-skills"
if str(SKILLS_PLUGIN) not in sys.path:
    sys.path.insert(0, str(SKILLS_PLUGIN))

from generator.gen_surface import gen_disambiguation_block  # noqa: E402

SURFACE_FILE = SKILLS_PLUGIN / "generator" / "server-surface.json"

# Must match the tools that received a per-tool live-SKIP line in the server
# repo (odoo-semantic-server/src/mcp/server.py). Keep the two sides aligned.
EXPECTED_OVERLAP_TOOLS = {
    "model_inspect",
    "module_inspect",
    "entity_lookup",
    "validate_domain",
    "validate_depends",
    "validate_relation",
}

# Generated artifacts that must carry the block (paths relative to skills plugin).
SNIPPET_ARTIFACTS = [
    "snippets/cursor-rules.md",
    "snippets/openai-gpt-instructions.md",
    "snippets/gemini-gem-instructions.md",
]
ROUTING_MD = "docs/reference/mcp-tool-routing.md"


def _surface() -> dict:
    return json.loads(SURFACE_FILE.read_text(encoding="utf-8"))


def test_surface_declares_disambiguation_ssot():
    dis = _surface().get("disambiguation")
    assert dis, "server-surface.json must declare a 'disambiguation' block"
    assert dis.get("identity"), "disambiguation.identity required"
    assert dis.get("precedence"), "disambiguation.precedence required (OSM-first contract)"
    assert isinstance(dis.get("not_for"), list) and dis["not_for"], (
        "disambiguation.not_for must be a non-empty list of boundaries"
    )
    assert set(dis.get("overlap_tools", [])) == EXPECTED_OVERLAP_TOOLS, (
        "overlap_tools must match the look-live tool set"
    )


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
    # routing md uses the heading variant; assert its section + a signature marker.
    routing = (SKILLS_PLUGIN / ROUTING_MD).read_text(encoding="utf-8")
    if "## 0. Which server to use (read first)" not in routing or "read_record" not in routing:
        stale.append(ROUTING_MD)
    assert not stale, "run `make gen` - these artifacts are stale: " + ", ".join(stale)
