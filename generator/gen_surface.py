#!/usr/bin/env python3
"""
gen_surface.py — SSOT generator for the Odoo Semantic MCP tool surface.

Reads generator/server-surface.json and emits:
  1. docs/reference/mcp-tool-routing.md      (full replace)
  2. skills/*/SKILL.md                        (only content between markers)
  3. snippets/cursor-rules.md                 (only content between markers)
  4. snippets/openai-gpt-instructions.md      (only content between markers)
  5. snippets/gemini-gem-instructions.md      (only content between markers)

Marker convention:
  <!-- BEGIN GENERATED TOOLS -->
  ... generated content ...
  <!-- END GENERATED TOOLS -->

  If a skill SKILL.md has no markers, they are inserted IMMEDIATELY AFTER the
  H2 heading line "## MCP tools" (or "## MCP tools (odoo-semantic)").
  The original content of the ## MCP tools section (up to the next ## heading)
  is REPLACED by the generated content between the markers.

Idempotent: running twice produces zero diff.

Usage:
  python3 generator/gen_surface.py

Run from the repo root.
"""

import json
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.resolve()
SURFACE_FILE = Path(__file__).parent / "server-surface.json"
SKILL_TOOL_DEPS_FILE = Path(__file__).parent / "skill_tool_deps.json"

BEGIN_MARKER = "<!-- BEGIN GENERATED TOOLS -->"
END_MARKER = "<!-- END GENERATED TOOLS -->"

# Skill dirs to skip for MCP-tools section generation.
# These are pure-text skills with no MCP invocations (router, onboard), skills whose
# marker block is managed manually (new B.2 standalone-first skills), and slim SKILL.md
# files that are part of an agent+skill bundle (tools live in the agent, not the skill).
SKIP_SKILL_DIRS = {
    "odoo-campaign-plan",
    "odoo-code-reviewer",
    "odoo-coder",
    "odoo-competitive-brief",
    "odoo-content-draft",
    "odoo-deal-followup",
    "odoo-deploy-checklist",
    "odoo-discovery-summarize",
    "odoo-frontend-coder",
    "odoo-onboard",
    "odoo-router",
}


# ---------------------------------------------------------------------------
# Description helpers
# ---------------------------------------------------------------------------

def _first_sentence(desc: str) -> str:
    """Return the first sentence of desc, splitting only at '. ' (period+space).

    This avoids clipping on inline periods like '@api.depends', 'v0.9.1+',
    'language=\'xml\'', etc.  If no '. ' boundary is found the full string is
    returned (already a single sentence).
    """
    parts = re.split(r'\.\s+', desc, maxsplit=1)
    sentence = parts[0]
    # Re-add the trailing period if it was stripped by the split boundary
    if not sentence.endswith('.'):
        sentence += '.'
    return sentence


# ---------------------------------------------------------------------------
# Load surface
# ---------------------------------------------------------------------------

def load_surface() -> dict:
    with open(SURFACE_FILE, encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Per-tool section helpers (shared content)
# ---------------------------------------------------------------------------

def persona_tags_display(tags: list[str]) -> str:
    return ", ".join(tags)


def params_display(params: list[str]) -> str:
    if not params:
        return "_(none)_"
    return ", ".join(f"`{p}`" for p in params)


def version_badge(tool: dict) -> str:
    added = tool.get("version_added", "")
    removed = tool.get("version_removed")
    badge = f"v{added}+" if added else ""
    if removed:
        badge += f" — removed in v{removed}"
    return badge


def tool_group_label(tool: dict) -> str:
    """Return the typographic label prefix used in the routing matrix."""
    name = tool["name"]
    added = tool.get("version_added", "")
    if added == "0.5.0" and name in ("model_inspect", "module_inspect", "entity_lookup"):
        return "★"
    if added == "0.6.0":
        return "☆"
    if added == "0.7.0":
        return "✦"
    if added == "0.8.0" and name not in ("model_inspect", "module_inspect", "entity_lookup"):
        return "⊕"
    return ""


# ---------------------------------------------------------------------------
# 1. Generate docs/reference/mcp-tool-routing.md
# ---------------------------------------------------------------------------

# Map persona tag codes → matrix column labels used in the routing-md table
PERSONA_COLUMNS = ["CEO", "dev", "consultant", "marketer", "sales"]
# Canonical display widths for persona tags in the surface JSON vs matrix column names
TAG_TO_COL = {
    "CEO": "CEO",
    "dev": "dev",
    "consultant": "consultant",
    "marketer": "marketer",
    "sales": "sales",
}


def gen_routing_md(surface: dict) -> str:
    server_ver = surface["server_version"]
    pr_ref = surface.get("server_pr_ref", "")
    # Use the surface's own generated_at timestamp (not wall-clock) to keep output idempotent.
    now_iso = surface.get("generated_at", "")
    tools = surface["tools"]
    resources = surface["resources"]

    # Build persona matrix rows
    def persona_cell(tags, col):
        if col in tags:
            return "●"
        # secondary: some personas are secondary (○) — we track this via 03-osm-surface.
        # Encoding rule: persona_tags = primary only. We add ○ for "adjacent" personas
        # by checking the routing-md appendix hints. For generator simplicity, we use ● for
        # primary tags and leave others empty. Persona_tags in JSON = primary only.
        return ""

    lines = []

    # Header
    lines.append("# MCP Tool × Persona × Adapter Routing Matrix")
    lines.append("")
    lines.append(
        f"> **Generated:** {now_iso}  "
    )
    lines.append(
        f"> **Server version:** {server_ver} (PR {pr_ref})  "
    )
    lines.append(
        "> **Source:** `generator/server-surface.json` — edit that file and run `make gen` to update."
    )
    lines.append(
        "> **v0.6 change:** 10 legacy tools (`resolve_model`, `resolve_field`, `resolve_method`, "
        "`resolve_view`, `list_fields`, `list_methods`, `list_views`, `list_owl_components`, "
        "`list_qweb_templates`, `list_js_patches`) were removed. "
        "Use the superset tools (`model_inspect`, `module_inspect`, `entity_lookup`) instead."
    )
    lines.append("")

    # Purpose
    lines.append("## Purpose")
    lines.append("")
    lines.append("Single-source documentation answering:")
    lines.append("- Which MCP tool maps to which persona?")
    lines.append("- Which trigger phrases route a user prompt to which tool?")
    lines.append("- Where does each adapter (Cursor, Gemini Gem, Custom GPT, Claude plugin) duplicate this routing logic?")
    lines.append("- How are skill keyword conflicts resolved?")
    lines.append("")
    lines.append(
        "When adding a new MCP tool or persona, update **`generator/server-surface.json`** "
        "first, then run `make gen` to propagate."
    )
    lines.append("")
    lines.append("---")
    lines.append("")

    # 1. Tool × Persona Matrix
    lines.append("## 1. Tool × Persona Matrix")
    lines.append("")
    header = "| MCP Tool | CEO | dev | consultant | marketer | sales |"
    sep = "|----------|:---:|:---:|:----------:|:--------:|:-----:|"
    lines.append(header)
    lines.append(sep)

    for tool in tools:
        name = tool["name"]
        label = tool_group_label(tool)
        tags = tool.get("persona_tags", [])
        display_name = f"**{name}**" if label else name
        if label:
            display_name = f"**{name}** {label}"
        cells = []
        for col in PERSONA_COLUMNS:
            cells.append("●" if col in tags else "")
        row = f"| {display_name} | " + " | ".join(cells) + " |"
        lines.append(row)

    lines.append("")
    lines.append(
        "**Legend:** ● = primary persona for this tool.  \n"
        "★ = M11 Wave D superset (supersedes removed v0.6 tools).  \n"
        "☆ = M11 Wave E session-context tool (sticky 24h TTL per API key).  \n"
        "✦ = M10A stylesheet tools (CSS/SCSS/LESS indexing).  \n"
        "⊕ = M10.5 Phase 2 ORM-validation tools (static domain / @api.depends / relation / dotted-path checks — v0.8+)."
    )
    lines.append("")

    # MCP Resources sub-table
    lines.append("### MCP Resources (M11 Wave F)")
    lines.append("")
    lines.append("Read-only bookmark-stable handles addressable via the `odoo://` URI scheme:")
    lines.append("")
    lines.append("| URI template | Returns |")
    lines.append("|---|---|")
    for res in resources:
        lines.append(f"| `{res['uri_template']}` | {res['description']} |")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 2. Tool Trigger Phrases
    lines.append("## 2. Tool Trigger Phrases")
    lines.append("")

    for tool in tools:
        name = tool["name"]
        label = tool_group_label(tool)
        label_str = f" {label}" if label else ""
        ver_badge = version_badge(tool)
        added_note = f"(added {ver_badge})" if ver_badge else ""
        lines.append(f"### {name}{label_str} {added_note}".rstrip())
        lines.append("")
        lines.append("| Attribute | Value |")
        lines.append("|-----------|-------|")
        lines.append(f"| **Description** | {tool['description']} |")
        lines.append(f"| **Personas** | {persona_tags_display(tool.get('persona_tags', []))} |")
        lines.append(
            f"| **Required params** | {params_display(tool.get('required_params', []))} |"
        )
        lines.append(
            f"| **Optional params** | {params_display(tool.get('optional_params', []))} |"
        )
        lines.append(f"| **Example call** | `{tool.get('example_call', '')}` |")
        kw = tool.get("routing_keywords", [])
        if kw:
            lines.append(f"| **Routing keywords** | {', '.join(kw)} |")
        lines.append("")

    lines.append("---")
    lines.append("")

    # 3. Adapter Sync Map
    lines.append("## 3. Adapter Sync Map")
    lines.append("")
    lines.append("When updating the tool surface, run `make gen` to propagate to all adapters.")
    lines.append("")
    lines.append("| Adapter | File path | Format |")
    lines.append("|---------|-----------|--------|")
    lines.append("| Cursor IDE rules | `snippets/cursor-rules.md` | Markdown list + code snippets |")
    lines.append("| Gemini Gem | `snippets/gemini-gem-instructions.md` | Instruction prose + tables |")
    lines.append("| Custom GPT | `snippets/openai-gpt-instructions.md` | System instruction prose |")
    lines.append("| Plugin skills | `skills/*/SKILL.md` | Between `<!-- BEGIN GENERATED TOOLS -->` markers |")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 4. Skill Conflict Resolution (preserved, static)
    lines.append("## 4. Skill Conflict Resolution")
    lines.append("")
    lines.append(
        "Plugin skills can claim overlapping trigger keywords. Standard resolution policy:"
    )
    lines.append("")
    lines.append("### 4.1 `odoo-risk-overview` vs `odoo-deprecation-audit`")
    lines.append("")
    lines.append(
        "- **Overlap:** \"upgrade risk\", \"is our code ready for v17\", \"what breaks in our system\""
    )
    lines.append(
        "- **Resolution:** `odoo-risk-overview` → CEO/Manager persona (executive summary, "
        "LOW/MEDIUM/HIGH labels). `odoo-deprecation-audit` → Developer persona "
        "(file:line evidence, code-level fixes)."
    )
    lines.append(
        "- **Heuristic:** User mentions \"team\", \"budget\", \"timeline\", \"business risk\" "
        "→ `odoo-risk-overview`. User shows code or mentions specific module/file "
        "→ `odoo-deprecation-audit`."
    )
    lines.append("")
    lines.append("### 4.2 `odoo-version-diff` vs `odoo-feature-highlights`")
    lines.append("")
    lines.append(
        "- **Overlap:** \"what's new in Odoo 17\", \"what's new in v17\", \"feature comparison\""
    )
    lines.append(
        "- **Resolution:** `odoo-version-diff` → Developer persona (API changes, migration guide, "
        "breaking changes). `odoo-feature-highlights` → Marketer persona "
        "(sales-deck tone, business value, announcement copy)."
    )
    lines.append(
        "- **Heuristic:** \"migration\", \"breaking\", \"API\", \"deprecation\" → `odoo-version-diff`. "
        "\"highlight\", \"sales deck\", \"blog post\", \"announcement\" → `odoo-feature-highlights`."
    )
    lines.append("")
    lines.append("### 4.3 `odoo-feature-check` vs `odoo-addon-diff`")
    lines.append("")
    lines.append(
        "- **Overlap:** \"is module X in CE or EE\", \"do we need Enterprise for feature Y\""
    )
    lines.append(
        "- **Resolution:** `odoo-feature-check` → Consultant (requirement scoping, gap analysis). "
        "`odoo-addon-diff` → Marketer/Sales (edition comparison table for proposals)."
    )
    lines.append(
        "- **Heuristic:** Embedded in scoping/gap context → `odoo-feature-check`. "
        "Standalone edition comparison → `odoo-addon-diff`."
    )
    lines.append("")
    lines.append("### 4.4 `odoo-owl-coder` vs `odoo-js-coder` at Odoo v14")
    lines.append("")
    lines.append(
        "- **Overlap:** Odoo v14 JavaScript code (grey zone — pre-OWL but post-legacy peak)"
    )
    lines.append(
        "- **Resolution:** Prefer `odoo-js-coder` for v14 (legacy widget system still dominant)."
    )
    lines.append(
        "- **Heuristic:** `odoo.define()`, `web.Widget`, `field_registry` → `odoo-js-coder`. "
        "`useService`, `t-component`, `patch()`, `useState` → `odoo-owl-coder`."
    )
    lines.append("")
    lines.append("---")
    lines.append("")

    # 5. Appendix: Tool × Adapter Quick Reference
    lines.append("## 5. Appendix: Tool × Adapter Quick Reference")
    lines.append("")
    lines.append("| Tool | Cursor | Gemini | OpenAI |")
    lines.append("|------|:------:|:------:|:------:|")
    for tool in tools:
        name = tool["name"]
        label = tool_group_label(tool)
        label_str = f" {label}" if label else ""
        lines.append(f"| **{name}**{label_str} | ✓ | ✓ | ✓ |")
    lines.append("")
    lines.append(
        f"> **v{server_ver} tool surface ({len(tools)} tools + {len(resources)} resources):** "
        "All tools are reached via HTTP MCP protocol to the Odoo Semantic MCP server. "
        "No logic is duplicated — only routing heuristics."
    )
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 2. Generate skill ## MCP tools section content
# ---------------------------------------------------------------------------

# SKILL_TO_TOOLS and SKILL_OLLAMA_TOOLS are populated at runtime from
# generator/skill_tool_deps.json (SSOT written by A2).  The dicts below are
# assigned inside _load_skill_tool_deps() and referenced by gen_skill_tools_block().

SKILL_TO_TOOLS: dict[str, list[str]] = {}
SKILL_OLLAMA_TOOLS: dict[str, list[str]] = {}


def _load_skill_tool_deps() -> None:
    """Populate SKILL_TO_TOOLS and SKILL_OLLAMA_TOOLS from skill_tool_deps.json.

    The JSON is the SSOT for which MCP/Ollama tools each skill uses.
    Session bootstrap tools (set_active_version, set_active_profile) are included
    in each skill's mcp_tools list and separated at render time in
    gen_skill_tools_block() — same logic as before, just data-driven now.
    """
    with open(SKILL_TOOL_DEPS_FILE, encoding="utf-8") as fh:
        data = json.load(fh)

    for skill_name, entry in data["skills"].items():
        SKILL_TO_TOOLS[skill_name] = list(entry["mcp_tools"])
        SKILL_OLLAMA_TOOLS[skill_name] = list(entry["ollama_tools"])


def gen_skill_tools_block(skill_name: str, surface: dict) -> str:
    """Generate the ## MCP tools section body for one skill."""
    tool_names = SKILL_TO_TOOLS.get(skill_name, [])
    ollama_tools = SKILL_OLLAMA_TOOLS.get(skill_name, [])
    tools_by_name = {t["name"]: t for t in surface["tools"]}

    server_ver = surface["server_version"]

    lines = []
    lines.append(
        f"_Tool surface: server v{server_ver}. "
        "See [`docs/reference/mcp-tool-routing.md`](../../docs/reference/mcp-tool-routing.md) "
        "for full routing matrix._"
    )
    lines.append("")

    # Session bootstrap
    session_tools = [n for n in tool_names if n in ("set_active_version", "set_active_profile")]
    work_tools = [n for n in tool_names if n not in ("set_active_version", "set_active_profile")]

    if session_tools:
        lines.append("**Session bootstrap** (call once at session start):")
        for st in session_tools:
            t = tools_by_name.get(st)
            if t:
                lines.append(f"- `{t['example_call']}` — {_first_sentence(t['description'])}")
        lines.append("")

    if work_tools:
        lines.append("**Primary tools:**")
        for tn in work_tools:
            t = tools_by_name.get(tn)
            if t:
                label = tool_group_label(t)
                label_str = f" {label}" if label else ""
                lines.append(f"- `{tn}`{label_str} — {_first_sentence(t['description'])}")
        lines.append("")

    if ollama_tools:
        lines.append("**Ollama-delegate tools** (local model, cost-free):")
        for ot in ollama_tools:
            lines.append(f"- `mcp__ollama-delegate__{ot}`")
        lines.append("")

    return "\n".join(lines).rstrip()


# ---------------------------------------------------------------------------
# 3. Generate snippet tool list blocks
# ---------------------------------------------------------------------------

def gen_cursor_tools_block(surface: dict) -> str:
    """Generate the tool list section for cursor-rules.md."""
    tools = surface["tools"]
    server_ver = surface["server_version"]
    lines = []
    lines.append(
        f"_Tool surface: server v{server_ver}. "
        "Generated from `generator/server-surface.json`. Run `make gen` to update._"
    )
    lines.append("")
    lines.append("## Key mappings (generated)")
    for tool in tools:
        name = tool["name"]
        label = tool_group_label(tool)
        label_str = f" {label}" if label else ""
        kw = tool.get("routing_keywords", [])
        trigger = kw[0] if kw else name
        lines.append(f'- "{trigger}" → `{name}{label_str}` — {_first_sentence(tool["description"])}')
    return "\n".join(lines)


def gen_openai_tools_block(surface: dict) -> str:
    """Generate the tool routing section for openai-gpt-instructions.md."""
    tools = surface["tools"]
    resources = surface["resources"]
    server_ver = surface["server_version"]
    lines = []
    lines.append(
        f"_Tool surface: server v{server_ver}. "
        "Generated from `generator/server-surface.json`. Run `make gen` to update._"
    )
    lines.append("")
    lines.append("**TOOLS (generated — v{ver}):**".format(ver=server_ver))
    lines.append("")
    for tool in tools:
        name = tool["name"]
        label = tool_group_label(tool)
        label_str = f" {label}" if label else ""
        req = tool.get("required_params", [])
        opt = tool.get("optional_params", [])
        desc = _first_sentence(tool["description"])
        lines.append(f"**{name}**{label_str} — {desc}")
        if req:
            lines.append(f"  REQUIRED: {', '.join(req)}")
        if opt:
            lines.append(f"  OPTIONAL: {', '.join(opt)}")
        kw = tool.get("routing_keywords", [])
        if kw:
            lines.append(f"  WHEN: {kw[0]}")
        lines.append("")
    lines.append("**MCP RESOURCES (generated):**")
    lines.append("")
    for res in resources:
        lines.append(f"- `{res['uri_template']}` — {res['description']}")
    return "\n".join(lines)


def gen_gemini_tools_block(surface: dict) -> str:
    """Generate the tool routing section for gemini-gem-instructions.md."""
    tools = surface["tools"]
    resources = surface["resources"]
    server_ver = surface["server_version"]
    lines = []
    lines.append(
        f"_Tool surface: server v{server_ver}. "
        "Generated from `generator/server-surface.json`. Run `make gen` to update._"
    )
    lines.append("")
    lines.append(f"Use these tools based on what the user is asking (v{server_ver} surface):")
    lines.append("")
    for tool in tools:
        name = tool["name"]
        label = tool_group_label(tool)
        label_str = f" {label}" if label else ""
        req = tool.get("required_params", [])
        opt = tool.get("optional_params", [])
        desc = _first_sentence(tool["description"])
        kw = tool.get("routing_keywords", [])
        trigger = kw[0] if kw else f"user asks about {name}"
        lines.append(f"### {name}{label_str}")
        lines.append(f"TRIGGER: {trigger}")
        lines.append(f"PREFER: {desc}")
        if req:
            lines.append(f"ARGS (required): {', '.join(req)}")
        if opt:
            lines.append(f"ARGS (optional): {', '.join(opt)}")
        lines.append("")
    lines.append("### MCP Resources (read-only, URI-addressable)")
    lines.append("")
    for res in resources:
        lines.append(f"- `{res['uri_template']}` — {res['description']}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Marker injection helpers
# ---------------------------------------------------------------------------

def inject_markers_into_file(path: Path, new_block: str) -> bool:
    """
    Insert or replace content between BEGIN/END markers in a file.
    - If markers already exist: replace content between them.
    - If no markers but a '## MCP tools' H2 heading exists: insert markers
      immediately after the heading line, replacing the original section body
      up to (but not including) the next H2 heading.
    Returns True if the file was changed, False if already up-to-date.
    """
    original = path.read_text(encoding="utf-8")
    lines = original.splitlines(keepends=True)

    begin_re = re.compile(r"^\s*" + re.escape(BEGIN_MARKER) + r"\s*$")
    end_re = re.compile(r"^\s*" + re.escape(END_MARKER) + r"\s*$")
    mcp_heading_re = re.compile(r"^## MCP tools", re.IGNORECASE)
    next_h2_re = re.compile(r"^## ", re.IGNORECASE)

    # Case 1: markers already present
    begin_idx = None
    end_idx = None
    for i, line in enumerate(lines):
        if begin_re.match(line):
            begin_idx = i
        elif end_re.match(line) and begin_idx is not None:
            end_idx = i
            break

    # Orphan guard: BEGIN without END corrupts on next gen (Case 2 would insert a
    # second BEGIN/END pair, then subsequent runs would replace the wrong window).
    if begin_idx is not None and end_idx is None:
        raise RuntimeError(
            f"orphan BEGIN marker in {path}: "
            f"<!-- BEGIN GENERATED TOOLS --> at line {begin_idx + 1} has no matching END"
        )

    if begin_idx is not None and end_idx is not None:
        # Replace content between markers (keep markers)
        new_content = (
            lines[: begin_idx + 1]
            + [new_block + "\n"]
            + lines[end_idx:]
        )
        new_text = "".join(new_content)
        if new_text == original:
            return False
        path.write_text(new_text, encoding="utf-8")
        return True

    # Case 2: no markers — find ## MCP tools heading and insert
    heading_idx = None
    for i, line in enumerate(lines):
        if mcp_heading_re.match(line):
            heading_idx = i
            break

    if heading_idx is None:
        # No MCP tools section at all — nothing to do for this file
        return False

    # Find end of the MCP tools section (next H2 or EOF)
    section_end_idx = len(lines)
    for i in range(heading_idx + 1, len(lines)):
        if next_h2_re.match(lines[i]):
            section_end_idx = i
            break

    # Build new content: heading line + blank line + marker block
    new_content = (
        lines[: heading_idx + 1]
        + ["\n"]
        + [BEGIN_MARKER + "\n"]
        + [new_block + "\n"]
        + [END_MARKER + "\n"]
        + ["\n"]
        + lines[section_end_idx:]
    )
    new_text = "".join(new_content)
    if new_text == original:
        return False
    path.write_text(new_text, encoding="utf-8")
    return True


def inject_markers_into_snippet(path: Path, new_block: str) -> bool:
    """
    Like inject_markers_into_file but for snippet files.
    If markers don't exist, append a new section at end of file.
    """
    if not path.exists():
        return False

    original = path.read_text(encoding="utf-8")
    lines = original.splitlines(keepends=True)

    begin_re = re.compile(r"^\s*" + re.escape(BEGIN_MARKER) + r"\s*$")
    end_re = re.compile(r"^\s*" + re.escape(END_MARKER) + r"\s*$")

    begin_idx = None
    end_idx = None
    for i, line in enumerate(lines):
        if begin_re.match(line):
            begin_idx = i
        elif end_re.match(line) and begin_idx is not None:
            end_idx = i
            break

    # Orphan guard: BEGIN without END would silently get a second pair appended below,
    # corrupting subsequent gens. Hard-fail with the offending line for a clean fix.
    if begin_idx is not None and end_idx is None:
        raise RuntimeError(
            f"orphan BEGIN marker in {path}: "
            f"<!-- BEGIN GENERATED TOOLS --> at line {begin_idx + 1} has no matching END"
        )

    if begin_idx is not None and end_idx is not None:
        new_content = (
            lines[: begin_idx + 1]
            + [new_block + "\n"]
            + lines[end_idx:]
        )
        new_text = "".join(new_content)
        if new_text == original:
            return False
        path.write_text(new_text, encoding="utf-8")
        return True

    # No markers — append at end
    separator = "\n\n---\n\n"
    new_section = (
        separator
        + "## Generated Tool Surface\n\n"
        + BEGIN_MARKER + "\n"
        + new_block + "\n"
        + END_MARKER + "\n"
    )
    new_text = original.rstrip() + new_section
    if new_text == original:
        return False
    path.write_text(new_text, encoding="utf-8")
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    # Load skill→tools mapping from JSON SSOT (populates SKILL_TO_TOOLS / SKILL_OLLAMA_TOOLS)
    _load_skill_tool_deps()

    surface = load_surface()
    changed_files: list[str] = []

    # Preflight: every skills/<name>/SKILL.md must be either in SKIP_SKILL_DIRS
    # or registered in skill_tool_deps.json.  Catches Phase B regressions where
    # a new skill dir is added but its entry is omitted from the JSON.
    skills_dir = REPO_ROOT / "skills"
    if skills_dir.exists():
        for skill_dir in sorted(skills_dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_name = skill_dir.name
            if skill_name in SKIP_SKILL_DIRS:
                continue
            if skill_name not in SKILL_TO_TOOLS:
                print(
                    f"ERROR: skill '{skill_name}' is neither in SKIP_SKILL_DIRS nor in "
                    f"skill_tool_deps.json. Add an entry to one of them.",
                    file=sys.stderr,
                )
                return 1

    # Preflight: every commands/*.md must be registered in .claude-plugin/plugin.json
    # commands array. Catches Phase C regressions where a new command is added but
    # not declared in the plugin manifest.
    plugin_json = json.loads((REPO_ROOT / ".claude-plugin" / "plugin.json").read_text())
    declared_commands = {Path(p).stem for p in plugin_json.get("commands", [])}
    commands_dir = REPO_ROOT / "commands"
    if commands_dir.is_dir():
        for cmd_file in sorted(commands_dir.glob("*.md")):
            if cmd_file.stem not in declared_commands:
                print(
                    f"ERROR: command '{cmd_file.stem}' not declared in .claude-plugin/plugin.json commands: array. Add it or remove the file.",
                    file=sys.stderr,
                )
                return 1

    # 1. Generate docs/reference/mcp-tool-routing.md (full replace)
    routing_md_path = REPO_ROOT / "docs" / "reference" / "mcp-tool-routing.md"
    routing_md_content = gen_routing_md(surface)
    routing_md_path.parent.mkdir(parents=True, exist_ok=True)
    original = routing_md_path.read_text(encoding="utf-8") if routing_md_path.exists() else None
    if original != routing_md_content:
        routing_md_path.write_text(routing_md_content, encoding="utf-8")
        changed_files.append(str(routing_md_path.relative_to(REPO_ROOT)))

    # 2. Update each skill's ## MCP tools section
    for skill_dir in sorted(skills_dir.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_name = skill_dir.name
        if skill_name in SKIP_SKILL_DIRS:
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue
        block = gen_skill_tools_block(skill_name, surface)
        changed = inject_markers_into_file(skill_md, block)
        if changed:
            changed_files.append(str(skill_md.relative_to(REPO_ROOT)))

    # 3. Update snippets
    snippets_dir = REPO_ROOT / "snippets"

    cursor_path = snippets_dir / "cursor-rules.md"
    cursor_block = gen_cursor_tools_block(surface)
    if inject_markers_into_snippet(cursor_path, cursor_block):
        changed_files.append(str(cursor_path.relative_to(REPO_ROOT)))

    openai_path = snippets_dir / "openai-gpt-instructions.md"
    openai_block = gen_openai_tools_block(surface)
    if inject_markers_into_snippet(openai_path, openai_block):
        changed_files.append(str(openai_path.relative_to(REPO_ROOT)))

    gemini_path = snippets_dir / "gemini-gem-instructions.md"
    gemini_block = gen_gemini_tools_block(surface)
    if inject_markers_into_snippet(gemini_path, gemini_block):
        changed_files.append(str(gemini_path.relative_to(REPO_ROOT)))

    if changed_files:
        print(f"gen_surface.py: updated {len(changed_files)} file(s):")
        for f in changed_files:
            print(f"  {f}")
    else:
        print("gen_surface.py: all files already up-to-date (idempotent).")

    return 0


if __name__ == "__main__":
    sys.exit(main())
