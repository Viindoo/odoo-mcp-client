"""Cross-check: the manual smoke checklist must not drift from the SSOT deps.

`tests/smoke/runtime_parity.md` is a hand-authored checklist used during the
multi-runtime smoke pass; `generator/skill_tool_deps.json` is the generator
SSOT of skill -> MCP-tool dependencies. When the two disagree, runtime tests
either look for tools the skill never calls (false-positive failures) or
miss tools the skill actually depends on (false-positive passes).

This test asserts: for every skill listed in the parity table, the MCP tools
named in the table must be a subset of the deps SSOT (after stripping
session-bootstrap tools `set_active_*` / `list_available_*`, which the parity
table treats as orthogonal context-setup work).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PARITY_FILE = REPO_ROOT / "tests" / "smoke" / "runtime_parity.md"
# After the v2 split, the generator SSOT moved under the skills plugin.
DEPS_FILE = (
    REPO_ROOT / "plugins" / "odoo-ai-agents" / "generator" / "skill_tool_deps.json"
)

SESSION_BOOTSTRAP_TOOLS = {
    "set_active_version",
    "set_active_profile",
    "list_available_versions",
    "list_available_profiles",
}

# Tokens in the "MCP dependency" column that are intentionally not tool names.
NON_TOOL_TOKENS = {
    "None",
    "Read-only",
    "Optional",
    "All",
    "standalone-first capable",
    "deal context is user-provided",
    "pure text routing",
}


def _load_deps():
    return json.loads(DEPS_FILE.read_text(encoding="utf-8"))


def _parse_parity_table():
    """Return {skill_name: set(tool_names_from_md_table)} for the 10 parity rows."""
    text = PARITY_FILE.read_text(encoding="utf-8")
    rows: dict[str, set[str]] = {}
    # Each row begins with "| <n> | `skill-name` | <phase> | <persona> | <deps cell> |"
    pattern = re.compile(
        r"^\|\s*\d+\s*\|\s*`(?P<skill>[a-z0-9-]+)`\s*\|[^|]+\|[^|]+\|(?P<deps>[^|]+)\|\s*$",
        re.MULTILINE,
    )
    for m in pattern.finditer(text):
        skill = m.group("skill")
        deps_cell = m.group("deps").strip()
        # Extract anything that looks like a tool name: backticked identifier.
        tools = set(re.findall(r"`([a-z_][a-z0-9_]+)`", deps_cell))
        # Filter out non-tool tokens that may accidentally be backticked.
        tools = {t for t in tools if t not in NON_TOOL_TOKENS}
        rows[skill] = tools
    return rows


def test_parity_table_subset_of_deps_ssot():
    """Every tool the parity table claims a skill uses must also live in deps SSOT."""
    deps_data = _load_deps()
    deps_by_skill = {
        name: set(entry.get("mcp_tools", []))
        for name, entry in deps_data.get("skills", {}).items()
    }

    parity_rows = _parse_parity_table()
    assert parity_rows, "expected at least one parity row to be parsed"

    drifts = []
    for skill, parity_tools in parity_rows.items():
        if skill not in deps_by_skill:
            # Skill might be unmapped intentionally (e.g., router) — skip
            # only if parity also declares no tools.
            if parity_tools - SESSION_BOOTSTRAP_TOOLS:
                drifts.append(
                    f"{skill}: declared in parity ({sorted(parity_tools)}) "
                    f"but missing from skill_tool_deps.json"
                )
            continue

        ssot_tools = deps_by_skill[skill]
        # Strip session-bootstrap from BOTH sides before comparing.
        parity_effective = parity_tools - SESSION_BOOTSTRAP_TOOLS
        ssot_effective = ssot_tools - SESSION_BOOTSTRAP_TOOLS
        missing = parity_effective - ssot_effective
        if missing:
            drifts.append(
                f"{skill}: parity claims {sorted(missing)} but deps SSOT only "
                f"declares {sorted(ssot_effective)}"
            )

    assert not drifts, "Smoke parity drift detected:\n  " + "\n  ".join(drifts)
