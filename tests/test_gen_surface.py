"""Tests for the SSOT generator (generator/gen_surface.py).

Covers safety-critical behavior of the marker-based file injection helpers:
- Orphan BEGIN marker (no matching END) must hard-fail, not silently corrupt
  by inserting a second BEGIN/END pair (which would shift subsequent gens to
  replace the wrong window).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make the generator package importable when tests are run from the repo root.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from generator.gen_surface import (  # noqa: E402
    inject_markers_into_file,
    inject_markers_into_snippet,
)


def test_orphan_begin_marker_raises_in_inject_markers_into_file(tmp_path):
    """A BEGIN without END must raise RuntimeError naming the offending file/line.

    This guards against the corruption mode where Case 2 (no-marker insert path)
    would silently add a second BEGIN+END pair, so the next gen run finds two
    BEGINs and replaces a window the author never intended.
    """
    target = tmp_path / "broken_skill.md"
    target.write_text(
        "# Foo\n"
        "\n"
        "## MCP tools\n"
        "\n"
        "<!-- BEGIN GENERATED TOOLS -->\n"
        "stale content with no matching END marker\n"
        "\n"
        "More body below.\n",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="orphan BEGIN"):
        inject_markers_into_file(target, "new block content")


def test_orphan_begin_marker_raises_in_inject_markers_into_snippet(tmp_path):
    """Same orphan-BEGIN safety in the snippet variant."""
    target = tmp_path / "broken_snippet.md"
    target.write_text(
        "# Snippet\n"
        "\n"
        "<!-- BEGIN GENERATED TOOLS -->\n"
        "stale snippet body with no END marker\n"
        "\n"
        "Trailing content.\n",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="orphan BEGIN"):
        inject_markers_into_snippet(target, "new block content")


def test_paired_markers_replace_cleanly_in_inject_markers_into_file(tmp_path):
    """Sanity: when both markers are present, content between them is replaced."""
    target = tmp_path / "skill.md"
    target.write_text(
        "# Foo\n"
        "\n"
        "## MCP tools\n"
        "\n"
        "<!-- BEGIN GENERATED TOOLS -->\n"
        "OLD\n"
        "<!-- END GENERATED TOOLS -->\n"
        "\n"
        "Body.\n",
        encoding="utf-8",
    )

    changed = inject_markers_into_file(target, "NEW")
    assert changed is True
    out = target.read_text(encoding="utf-8")
    assert "NEW" in out
    assert "OLD" not in out
    assert out.count("<!-- BEGIN GENERATED TOOLS -->") == 1
    assert out.count("<!-- END GENERATED TOOLS -->") == 1


def test_no_markers_inserts_new_block_under_mcp_heading(tmp_path):
    """Sanity: when no markers exist, the block is inserted under ## MCP tools."""
    target = tmp_path / "skill.md"
    target.write_text(
        "# Foo\n"
        "\n"
        "## MCP tools\n"
        "\n"
        "## Other section\n",
        encoding="utf-8",
    )

    changed = inject_markers_into_file(target, "INSERTED")
    assert changed is True
    out = target.read_text(encoding="utf-8")
    assert "INSERTED" in out
    assert out.count("<!-- BEGIN GENERATED TOOLS -->") == 1
    assert out.count("<!-- END GENERATED TOOLS -->") == 1
