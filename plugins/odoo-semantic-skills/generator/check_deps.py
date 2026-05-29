#!/usr/bin/env python3
"""CI dependency check: assert every tool referenced in skill_tool_deps.json exists in server-surface.json."""
import json
import sys
import pathlib

ROOT = pathlib.Path(__file__).parent
surface = json.loads((ROOT / "server-surface.json").read_text())
deps = json.loads((ROOT / "skill_tool_deps.json").read_text())

live_tools = {t["name"] for t in surface["tools"] if t.get("version_removed") is None}
errors = []

for skill_name, meta in deps["skills"].items():
    for tool in meta.get("mcp_tools", []):
        if tool not in live_tools:
            errors.append(f"Skill '{skill_name}' references removed/missing tool '{tool}'")

for agent_name, meta in deps.get("agents", {}).items():
    for tool in meta.get("mcp_tools", []):
        if tool not in live_tools:
            errors.append(f"Agent '{agent_name}' references removed/missing tool '{tool}'")

if errors:
    print("\n".join(errors), file=sys.stderr)
    sys.exit(1)

num_skills = len(deps["skills"])
num_agents = len(deps.get("agents", {}))
print(f"OK: {num_skills} skills + {num_agents} agents — all tool references resolve.")
