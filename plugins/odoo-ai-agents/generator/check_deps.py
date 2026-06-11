#!/usr/bin/env python3
"""CI dependency check: assert every tool referenced in skill_tool_deps.json exists in
server-surface.json, AND that the declared version-gate fields are consistent (issue #40
Finding 2 — previously declared-but-dead).

Version-gate invariants enforced:
  1. server_version_required <= surface.server_version (the mirror cannot require a server
     newer than the surface it mirrors).
  2. every skill/agent min_server_version <= surface.server_version (each floor is satisfiable
     by the mirrored/deployed server).
  3. every skill/agent min_server_version >= max(version_added) of the tools it references
     (the declared floor actually covers the newest tool the skill uses — this is what makes
     the field meaningful: a skill using profile_inspect (0.13.1) must declare min >= 0.13.1).
"""
import json
import sys
import pathlib

ROOT = pathlib.Path(__file__).parent
surface = json.loads((ROOT / "server-surface.json").read_text())
deps = json.loads((ROOT / "skill_tool_deps.json").read_text())


def semver(v):
    """Parse 'X.Y.Z' -> (X, Y, Z) int tuple; tolerate short/empty -> zero-padded."""
    parts = [int(p) for p in str(v or "0").split(".") if p.isdigit()]
    return tuple((parts + [0, 0, 0])[:3])


live_tools = {t["name"] for t in surface["tools"] if t.get("version_removed") is None}
tool_added = {t["name"]: semver(t.get("version_added")) for t in surface["tools"]}
surface_ver = semver(surface["server_version"])
errors = []

# Invariant 1: overall required floor satisfiable by the mirrored surface.
if semver(deps.get("server_version_required")) > surface_ver:
    errors.append(
        f"server_version_required '{deps.get('server_version_required')}' exceeds mirrored "
        f"server_version '{surface['server_version']}'"
    )

for section in ("skills", "agents"):
    for name, meta in deps.get(section, {}).items():
        kind = section[:-1].capitalize()
        tools = meta.get("mcp_tools", [])
        # Invariant: every referenced tool exists (live, not removed).
        for tool in tools:
            if tool not in live_tools:
                errors.append(f"{kind} '{name}' references removed/missing tool '{tool}'")
        floor = semver(meta.get("min_server_version"))
        # Invariant 2: floor satisfiable by the mirrored surface.
        if floor > surface_ver:
            errors.append(
                f"{kind} '{name}' min_server_version '{meta.get('min_server_version')}' exceeds "
                f"mirrored server_version '{surface['server_version']}'"
            )
        # Invariant 3: floor must cover the newest tool the skill/agent uses.
        needed = max((tool_added.get(t, (0, 0, 0)) for t in tools), default=(0, 0, 0))
        if needed > floor:
            newest = max(tools, key=lambda t: tool_added.get(t, (0, 0, 0)))
            errors.append(
                f"{kind} '{name}' min_server_version '{meta.get('min_server_version')}' is below "
                f"the version_added of '{newest}' ({'.'.join(map(str, needed))}) — bump the floor"
            )

if errors:
    print("\n".join(errors), file=sys.stderr)
    sys.exit(1)

num_skills = len(deps["skills"])
num_agents = len(deps.get("agents", {}))
print(
    f"OK: {num_skills} skills + {num_agents} agents — all tool references resolve; "
    f"version-gate consistent against surface {surface['server_version']}."
)
