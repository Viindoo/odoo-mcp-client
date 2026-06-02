"""Tests for the SSOT generator (generator/gen_surface.py).

Covers safety-critical behavior of the marker-based file injection helpers:
- Orphan BEGIN marker (no matching END) must hard-fail, not silently corrupt
  by inserting a second BEGIN/END pair (which would shift subsequent gens to
  replace the wrong window).

Also covers server-surface.json invariants:
- 19 tools must declare odoo_version as REQUIRED (mirror of server ADR-0029 amend)
- 4 session/version-diff tools must NOT have odoo_version in required_params
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Make the generator package importable when tests are run from the repo root.
# After the v2 split, the generator lives under the skills plugin, so its parent
# (the skills-plugin root) is what must be on sys.path for `import generator`.
REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_PLUGIN = REPO_ROOT / "plugins" / "odoo-semantic-skills"
if str(SKILLS_PLUGIN) not in sys.path:
    sys.path.insert(0, str(SKILLS_PLUGIN))

from generator.gen_surface import (  # noqa: E402
    inject_markers_into_file,
    inject_markers_into_snippet,
)


# ---------------------------------------------------------------------------
# server-surface.json odoo_version invariants (mirrors server ADR-0029 amend)
# ---------------------------------------------------------------------------

SURFACE_FILE = SKILLS_PLUGIN / "generator" / "server-surface.json"

# Tools that MUST have odoo_version in required_params
TOOLS_REQUIRE_VERSION = {
    "find_examples",
    "impact_analysis",
    "lookup_core_api",
    "find_deprecated_usage",
    "lint_check",
    "cli_help",
    "suggest_pattern",
    "check_module_exists",
    "find_override_point",
    "describe_module",
    "model_inspect",
    "module_inspect",
    "entity_lookup",
    "resolve_stylesheet",
    "find_style_override",
    "resolve_orm_chain",
    "validate_domain",
    "validate_depends",
    "validate_relation",
}

# Tools that must NOT have odoo_version in required_params
# (set_active_version already requires it as its payload — intentional; not in this set)
TOOLS_KEEP_VERSION_OPTIONAL = {
    "list_available_versions",
    "list_available_profiles",
    "set_active_profile",
    "api_version_diff",
}


@pytest.fixture(scope="module")
def surface_tools() -> dict[str, dict]:
    """Load server-surface.json and return a name→tool dict."""
    with open(SURFACE_FILE, encoding="utf-8") as fh:
        data = json.load(fh)
    return {t["name"]: t for t in data["tools"]}


def test_required_version_tools_have_odoo_version_in_required(surface_tools):
    """19 tools must list odoo_version in required_params (not optional)."""
    failures = []
    for name in sorted(TOOLS_REQUIRE_VERSION):
        tool = surface_tools.get(name)
        assert tool is not None, f"Tool '{name}' not found in server-surface.json"
        req = tool.get("required_params", [])
        opt = tool.get("optional_params", [])
        if "odoo_version" not in req:
            failures.append(f"{name}: odoo_version missing from required_params (required={req})")
        if "odoo_version" in opt:
            failures.append(f"{name}: odoo_version still in optional_params")
    assert not failures, "odoo_version invariant failures:\n" + "\n".join(failures)


def test_exempt_tools_do_not_have_odoo_version_in_required(surface_tools):
    """4 exempt tools must NOT have odoo_version in required_params."""
    failures = []
    for name in sorted(TOOLS_KEEP_VERSION_OPTIONAL):
        tool = surface_tools.get(name)
        assert tool is not None, f"Tool '{name}' not found in server-surface.json"
        req = tool.get("required_params", [])
        if "odoo_version" in req:
            failures.append(f"{name}: odoo_version must NOT be in required_params")
    assert not failures, "exempt-tool invariant failures:\n" + "\n".join(failures)


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
