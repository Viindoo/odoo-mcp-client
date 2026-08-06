#!/usr/bin/env python3
"""CI dependency check: assert every tool referenced in skill_tool_deps.json exists in
server-surface.json, AND that the declared version-gate fields are consistent (issue #40
Finding 2 - previously declared-but-dead).

Version-gate invariants enforced:
  1. server_version_required <= surface.server_version (the mirror cannot require a server
     newer than the surface it mirrors).
  2. every skill/agent min_server_version <= surface.server_version (each floor is satisfiable
     by the mirrored/deployed server).
  3. every skill/agent min_server_version >= max(version_added) of the tools it references
     (the declared floor actually covers the newest tool the skill uses - this is what makes
     the field meaningful: a skill using profile_inspect (0.13.1) must declare min >= 0.13.1).

Invariants 1-4 are ALWAYS fatal (invariant 4 was warn-first while the 9 pre-existing violations it
surfaced were being closed - see below; all 9 are now declared or ruled a documented negation
exception, so it is fatal by default. --strict / DEPS_STRICT=1 are now no-ops kept only for
back-compat with the same flag/env-var convention check_workflows.py's WORKFLOWS_STRICT and
check_orchestration.py's ORCH_STRICT still use):
  4. every mcp__odoo-semantic__* tool NAMED in a skill's HAND-WRITTEN SKILL.md prose (the text
     outside the <!-- BEGIN/END GENERATED TOOLS --> markers) must appear in that skill's OWN
     declared mcp_tools list. Without this, a skill's prose can silently call a tool its own
     SSOT entry doesn't know about (measured: odoo-perf-audit / odoo-security-audit /
     odoo-data-migration all called set_active_version/set_active_profile in Round-0 prose while
     their declared mcp_tools omitted both - now fixed and declared) - undetectable by
     invariants 1-3, which only ever look at the declared list, never the prose that
     references it.

     EXCEPTION, openly documented (not a silent suppression list): a tool named ONLY inside a
     sentence that explicitly instructs the agent NOT to call it (cue phrase "do not call" /
     "never call", case-insensitive - e.g. "**Do NOT call** `set_active_profile`, `model_inspect`,
     `lint_check`" in odoo-discovery-summary, or "do NOT call cross-version `api_version_diff`" in
     odoo-git-rebase) is excluded from "named" for that sentence - declaring it would falsely
     assert the skill uses a tool its prose forbids. A tool named in a DIFFERENT, non-negated
     sentence elsewhere in the same file still counts normally. See tools_named_in_prose().
"""
import json
import os
import re
import sys
import pathlib

ROOT = pathlib.Path(__file__).parent
SKILLS_DIR = ROOT.parent / "skills"
surface = json.loads((ROOT / "server-surface.json").read_text())
deps = json.loads((ROOT / "skill_tool_deps.json").read_text())

BEGIN_MARKER = "<!-- BEGIN GENERATED TOOLS -->"
END_MARKER = "<!-- END GENERATED TOOLS -->"
_MARKER_BLOCK_RE = re.compile(
    re.escape(BEGIN_MARKER) + r".*?" + re.escape(END_MARKER), re.DOTALL
)


def hand_written_prose(skill_md_text: str) -> str:
    """Return skill_md_text with every <!-- BEGIN/END GENERATED TOOLS --> block removed.

    Handles zero, one, or many marker pairs (re.sub replaces every non-overlapping
    match) - this check does not itself enforce marker-pair well-formedness (that is
    gen_surface.py's job); it just needs the generated regions excluded so a tool name
    that only appears there (rendered FROM the skill's own declared list, or from the
    universal disambiguation boilerplate) is never mistaken for a hand-written call.
    """
    return _MARKER_BLOCK_RE.sub("", skill_md_text)


# Cue phrase for the invariant-4 negation exception (see module docstring): a sentence telling
# the agent NOT to call a tool is the opposite of an undeclared-but-used registry gap. Matches
# "do not call" / "do NOT call" / "never call" case-insensitively; deliberately narrow (does not
# match a bare "not", which would swallow unrelated sentences like "call X, not Y").
_NEGATION_CUE_RE = re.compile(r"\b(?:do\s+not|never)\s+call\b", re.IGNORECASE)


def tools_named_in_prose(prose: str, live_tool_names: set) -> set:
    """Return the subset of live_tool_names that appear as a whole word in prose.

    Scoped per sentence (split on '.', the cheapest boundary that matches how these skills'
    Markdown prose is actually written): a tool named ONLY inside a sentence carrying the
    negation cue is excluded from the result. A tool also named in a DIFFERENT, non-negated
    sentence anywhere else in the same prose still counts - only the negated mention is
    dropped, never the tool globally. This can only shrink the result (never invent a false
    "named" hit), so it cannot mask a genuine undeclared-tool gap elsewhere.
    """
    found = set()
    for sentence in prose.split("."):
        if _NEGATION_CUE_RE.search(sentence):
            continue
        for name in live_tool_names:
            if re.search(r"(?<![\w-])" + re.escape(name) + r"(?![\w-])", sentence):
                found.add(name)
    return found


def semver(v):
    """Parse 'X.Y.Z' -> (X, Y, Z) int tuple; tolerate short/empty -> zero-padded."""
    parts = [int(p) for p in str(v or "0").split(".") if p.isdigit()]
    return tuple((parts + [0, 0, 0])[:3])


live_tools = {t["name"] for t in surface["tools"] if t.get("version_removed") is None}
tool_added = {t["name"]: semver(t.get("version_added")) for t in surface["tools"]}
surface_ver = semver(surface["server_version"])
errors = []
warn_first_findings = []  # always empty now - kept so the OK-message plumbing below is a no-op

# --strict / DEPS_STRICT=1: historically promoted invariant 4 from warn-first to fatal, same
# convention as check_workflows.py's WORKFLOWS_STRICT and check_orchestration.py's ORCH_STRICT.
# Invariant 4 is fatal BY DEFAULT now (the 9 pre-existing violations it warned about are closed -
# see module docstring), so this flag/env-var is a no-op kept only for CLI back-compat.
strict = "--strict" in sys.argv[1:] or os.environ.get("DEPS_STRICT") == "1"

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
                f"the version_added of '{newest}' ({'.'.join(map(str, needed))}) - bump the floor"
            )

# Invariant 4: every OSM tool NAMED in a skill's hand-written SKILL.md prose must be in
# that same skill's declared mcp_tools list. Scoped to "skills" only (not "agents") - a
# skill's own SKILL.md is the file this checks; several agents deliberately carry no
# mcp_tools entry at all ("inherit the FULL tool surface, no fixed list" by design), so
# there is nothing meaningful to cross-check there. A skill with no SKILL.md on disk (or
# no skill_tool_deps.json entry, hence never iterated below) is not this invariant's job.
# FATAL by default (not warn-first) - see module docstring for the negation-cue exception.
for name, meta in deps.get("skills", {}).items():
    skill_md = SKILLS_DIR / name / "SKILL.md"
    if not skill_md.exists():
        continue
    declared = set(meta.get("mcp_tools", []))
    prose = hand_written_prose(skill_md.read_text(encoding="utf-8"))
    named = tools_named_in_prose(prose, live_tools)
    undeclared = sorted(named - declared)
    if undeclared:
        errors.append(
            f"Skill '{name}' hand-written prose (outside <!-- BEGIN/END GENERATED TOOLS -->) "
            f"names tool(s) {undeclared} that are missing from its own declared mcp_tools "
            f"{sorted(declared)} in skill_tool_deps.json - declare them there (or remove the "
            f"prose reference if the call was never intentional)"
        )

if errors:
    print("\n".join(f"ERROR: {e}" for e in errors), file=sys.stderr)
    sys.exit(1)

assert not warn_first_findings  # invariant 4 is fatal by default now - nothing should land here

num_skills = len(deps["skills"])
num_agents = len(deps.get("agents", {}))
print(
    f"OK: {num_skills} skills + {num_agents} agents - all tool references resolve; "
    f"version-gate consistent against surface {surface['server_version']}."
)
