"""Guard the agents.<name>.brief registry manifest against each agent's own hand-authored
Inputs table (M7 in 12-design-final.md).

Per the design: "No generated region in any agent body. The Inputs table stays hand-authored; a
lint asserts it matches the registry." (A11: generating the manifest would emit a required-field
list into a section whose documented response to a missing field is STOP - the Inputs table must
stay a human decision, not codegen.) This is the ENFORCED half of M7's guard pair - the other half
([brief-fields], rule 12 in check_orchestration.py) is warn-first/non-blocking PERMANENTLY because
the wider dispatch-site corpus (39 briefs, 133 ad-hoc key names) is explicitly out of scope for
full normalization. THIS file's half is fully decidable today: 11 agents carry an explicit
"## Inputs" markdown table, and for exactly those, the registry's `brief.required |
brief.optional` key set must equal the table's own Key column, verbatim (normalized only for
markdown mechanics - backticks, trailing colons, "A / B" multi-key cells - never content).

Every agent (all 26, table or not) must additionally carry a structurally valid `brief` manifest
in the registry (`{"required": [...], "optional": [...]}`, both lists) - that is M7 WHAT item 1,
independent of whether the agent happens to have a dedicated Inputs table today.

Run: python -m pytest tests/test_agent_inputs_match_registry.py -v
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN = REPO_ROOT / "plugins" / "odoo-ai-agents"
AGENTS_DIR = PLUGIN / "agents"
DEPS_FILE = PLUGIN / "generator" / "skill_tool_deps.json"

_INPUTS_TABLE_RE = re.compile(
    r"^## Inputs[^\n]*\n\n\| Key \| Meaning \|\n\|[-|]+\|\n((?:\|.*\n)+)", re.M
)


def _registry() -> dict:
    return json.loads(DEPS_FILE.read_text(encoding="utf-8"))


def _normalize_key_cell(cell: str) -> list[str]:
    """Split one table 'Key' cell into canonical field-name tokens: strip backticks/whitespace,
    drop a trailing ':', and split a multi-key cell ('MODULE / MODULE PATH') into separate keys.
    Markdown-mechanics normalization only - never a content judgment call."""
    out = []
    for part in re.split(r"\s*/\s*", cell.strip()):
        part = part.strip().strip("`").strip().rstrip(":").strip("`").strip()
        if part:
            out.append(part)
    return out


def _table_keys(text: str) -> list[str] | None:
    """Return this agent's own declared Inputs-table key set, or None if it has no dedicated
    '## Inputs...' table (many agents document required fields in Brief self-check prose
    instead - out of scope for this ENFORCED equality check, see module docstring)."""
    m = _INPUTS_TABLE_RE.search(text)
    if not m:
        return None
    keys: list[str] = []
    for row in m.group(1).strip().split("\n"):
        cell = row.split("|")[1]
        keys.extend(_normalize_key_cell(cell))
    seen: set[str] = set()
    result = []
    for k in keys:
        if k not in seen:
            seen.add(k)
            result.append(k)
    return result


def _brief_mismatch_findings(name: str, table_keys: set[str], registry_keys: set[str]) -> list[str]:
    """Findings-list comparator (mirrors check_orchestration.py's own convention) - kept as a
    standalone function so the red/green proof below can call it directly on synthetic data
    without touching a real agent file."""
    findings = []
    missing_in_registry = table_keys - registry_keys
    extra_in_registry = registry_keys - table_keys
    if missing_in_registry:
        findings.append(
            f"{name}: Inputs table declares {sorted(missing_in_registry)} that the registry "
            f"brief manifest (required|optional) does not list"
        )
    if extra_in_registry:
        findings.append(
            f"{name}: registry brief manifest lists {sorted(extra_in_registry)} that the agent's "
            f"own Inputs table does not declare"
        )
    return findings


REGISTRY = _registry()
AGENT_NAMES = sorted(REGISTRY.get("agents", {}).keys())
AGENT_BODIES = {name: (AGENTS_DIR / f"{name}.md").read_text(encoding="utf-8") for name in AGENT_NAMES}
AGENTS_WITH_TABLE = sorted(name for name, body in AGENT_BODIES.items() if _table_keys(body) is not None)


# ---------------------------------------------------------------------------
# Discovery floors - a broken registry/table-parser read would silently make
# every parametrized test below vacuous.
# ---------------------------------------------------------------------------


def test_agent_and_table_subject_sets_discovered():
    assert len(AGENT_NAMES) >= 20, f"expected >=20 registered agents, found {len(AGENT_NAMES)}"
    assert len(AGENTS_WITH_TABLE) >= 10, (
        f"expected >=10 agents with an explicit '## Inputs' table, found {len(AGENTS_WITH_TABLE)}: "
        f"{AGENTS_WITH_TABLE}"
    )


# ---------------------------------------------------------------------------
# Structural completeness (all 26 agents) - M7 WHAT item 1: every
# agents.<name> gains a brief manifest, whether or not it has a table today.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", AGENT_NAMES)
def test_every_agent_has_a_structurally_valid_brief_manifest(name):
    entry = REGISTRY["agents"][name]
    assert "brief" in entry, f"agents.{name} has no 'brief' key in the registry"
    brief = entry["brief"]
    assert isinstance(brief.get("required"), list), f"agents.{name}.brief.required must be a list"
    assert isinstance(brief.get("optional"), list), f"agents.{name}.brief.optional must be a list"


@pytest.mark.parametrize("name", AGENT_NAMES)
def test_brief_required_and_optional_are_disjoint(name):
    brief = REGISTRY["agents"][name]["brief"]
    overlap = set(brief["required"]) & set(brief["optional"])
    assert not overlap, f"agents.{name}.brief has key(s) {sorted(overlap)} listed as BOTH required and optional"


# ---------------------------------------------------------------------------
# ENFORCED equality (the 11 agents with a dedicated Inputs table) - the
# fully-decidable half of M7's guard pair.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", AGENTS_WITH_TABLE)
def test_agent_inputs_table_matches_registry_brief_manifest(name):
    table_keys = set(_table_keys(AGENT_BODIES[name]))
    brief = REGISTRY["agents"][name]["brief"]
    registry_keys = set(brief["required"]) | set(brief["optional"])
    findings = _brief_mismatch_findings(name, table_keys, registry_keys)
    assert not findings, "; ".join(findings)


# ---------------------------------------------------------------------------
# Comparator proof (red-before-green) - synthetic data, never a real file.
# ---------------------------------------------------------------------------


def test_brief_mismatch_findings_detects_a_real_mismatch_then_clears():
    """RED: the table declares a key the registry manifest lacks, and the registry manifest
    declares a key the table lacks - both directions must be caught.
    GREEN: once the two sets agree, no finding survives."""
    findings = _brief_mismatch_findings("synthetic", {"A", "B"}, {"A", "C"})
    assert findings, "RED case did not fire for a genuine table/registry mismatch"
    joined = " ".join(findings)
    assert "'B'" in joined, f"missing-in-registry direction did not fire: {findings}"
    assert "'C'" in joined, f"extra-in-registry direction did not fire: {findings}"

    findings2 = _brief_mismatch_findings("synthetic", {"A", "B"}, {"A", "B"})
    assert not findings2, f"GREEN case still produced findings: {findings2}"


def test_normalize_key_cell_handles_markdown_mechanics():
    """Sanity for the normalizer the equality check depends on: backticks, trailing colons, and
    'A / B' multi-key cells must all resolve to the SAME canonical tokens a plain key would."""
    assert _normalize_key_cell("`TARGET:`") == ["TARGET"]
    assert _normalize_key_cell("`MODULE` / `MODULE PATH`") == ["MODULE", "MODULE PATH"]
    assert _normalize_key_cell("`SHARE_DIR:` / `ISOLATE_DIR:`") == ["SHARE_DIR", "ISOLATE_DIR"]
    assert _normalize_key_cell("plain_key") == ["plain_key"]
