"""Guard: AI-agent-facing prose must match the required-odoo_version tool surface.

The real consumers of skills/snippets/agents are AI agents — Claude Code reads
SKILL.md; Gemini / OpenAI / Cursor read the snippets as their system prompt. The
server hard-requires ``odoo_version`` on 19 tools: omitting it raises a
ValidationError *before* the handler runs, and a pinned session can only be reused
by passing ``odoo_version='auto'`` explicitly (never by omitting it). So any
guidance telling an agent it may *omit* ``odoo_version``, or that ``odoo_version``
is *optional / defaults to "auto"*, makes the agent emit a failing tool call —
the exact opposite of what these artifacts are for.

``make gen`` only refreshes content between ``<!-- BEGIN/END GENERATED ... -->``
markers (all derived from ``generator/server-surface.json``). Hand-maintained prose
*outside* those markers is never synced to the surface, so it drifts silently and
``make gen-check`` stays green. These tests scan the WHOLE file — generated blocks
*and* hand prose — so that drift can no longer hide.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN = REPO_ROOT / "plugins" / "odoo-semantic-skills"


def _md_files(*subdirs: str) -> list[Path]:
    files: list[Path] = []
    for d in subdirs:
        files.extend((PLUGIN / d).rglob("*.md"))
    return sorted(files)


# --- Guidance that tells an agent odoo_version is droppable — always wrong now ---
# Tight enough not to flag the correct replacement wording ("pass odoo_version='auto'
# instead of a concrete version (never omit it ...)") — "omit" must be directly
# followed by odoo_version, and "(optional" must not be separated from odoo_version
# by a comma (which would mean it qualifies a *different*, genuinely-optional param).
_OMIT_RE = re.compile(r"omit\s+(?:the\s+)?[`'\"]?odoo_version", re.I)
_CAN_OMIT_RE = re.compile(r"can\s+omit\b[^\n]*odoo_version", re.I)
_OPTIONAL_VER_RE = re.compile(r"odoo_version[^,\n]{0,30}\(optional", re.I)
_DEFAULT_AUTO_RE = re.compile(r"odoo_version[^,\n]{0,30}default\s+\"auto\"", re.I)
_PATTERNS = (_OMIT_RE, _CAN_OMIT_RE, _OPTIONAL_VER_RE, _DEFAULT_AUTO_RE)


def test_no_omittable_odoo_version_guidance():
    """No agent-facing .md may claim odoo_version can be omitted / is optional."""
    offenders: list[str] = []
    for f in _md_files("skills", "snippets", "agents", "docs"):
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if any(p.search(line) for p in _PATTERNS):
                offenders.append(f"{f.relative_to(REPO_ROOT)}:{i}: {line.strip()}")
    assert not offenders, (
        "Agent-facing prose still claims odoo_version is omittable/optional. "
        "The server hard-requires it; agents must pass odoo_version='auto' to reuse "
        "a pinned session. Offending lines:\n" + "\n".join(offenders)
    )


# --- Parameter names that no current tool accepts (drifted SSOT duplications) ---
# impact_analysis uses entity_type/entity_name; lookup_core_api uses name;
# api_version_diff uses symbol. These tokens in operating-instruction prose mean
# an agent would emit a tool call the server rejects.
_WRONG_PARAM_TOKENS = ("target_type", "target_name", "symbol_name")


def test_no_drifted_param_names_in_agent_snippets():
    """Skill/snippet/agent prose must not document parameter names no tool accepts."""
    offenders: list[str] = []
    for f in _md_files("skills", "snippets", "agents"):
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            for tok in _WRONG_PARAM_TOKENS:
                if tok in line:
                    offenders.append(f"{f.relative_to(REPO_ROOT)}:{i}: '{tok}' in: {line.strip()}")
    assert not offenders, (
        "Prose uses parameter names no current tool accepts "
        "(drifted from server-surface.json required/optional params):\n"
        + "\n".join(offenders)
    )


# --- Concrete example tool calls must include the required odoo_version ----------
# Agents copy example calls verbatim. An example like `find_examples(query="...")`
# for a tool that requires odoo_version makes the agent emit a call the server
# rejects. We scan inline-code and fenced example calls for the 19 required tools
# and assert each call's argument span carries odoo_version. set_active_version is
# excluded — its sole argument *is* the version (passed positionally or by name).
import json  # noqa: E402

_SURFACE = json.loads((PLUGIN / "generator" / "server-surface.json").read_text(encoding="utf-8"))
_REQ_VERSION_TOOLS = sorted(
    t["name"]
    for t in _SURFACE["tools"]
    if "odoo_version" in t.get("required_params", []) and t["name"] != "set_active_version"
)
# Agents/snippets emit BOTH the bare name (`suggest_pattern(...)`) and the
# fully-qualified MCP form (`mcp__odoo-semantic__suggest_pattern(...)`). Match an
# optional server prefix so the qualified form is scanned too (real failing calls
# were slipping through on the bare-name-only regex).
_MCP_PREFIX = r"(?:mcp__[\w-]+__)?"
_TOOL_CALL_RE = re.compile(r"\b" + _MCP_PREFIX + r"(" + "|".join(_REQ_VERSION_TOOLS) + r")\(")

# Positional index of odoo_version in each tool's canonical signature ORDER.
# A bare positional only covers odoo_version when the call supplies positionals up
# to and including that slot — "enough positionals to fill the required COUNT" is
# not enough, because some tools (lint_check, cli_help) take optional positionals
# (code/command) BEFORE odoo_version, so a single positional fills the optional
# slot, not odoo_version. The SSOT for that signature order is each tool's own
# `example_call` (odoo_version is the last positional in every example). We parse
# the example to find odoo_version's slot rather than trusting required_params order.
def _odoo_version_positional_index(tool: dict) -> int | None:
    ec = tool.get("example_call", "")
    open_i, close_i = ec.find("("), ec.rfind(")")
    if open_i < 0 or close_i < 0:
        return None
    args = _top_level_args(ec[open_i + 1 : close_i])
    for idx, arg in enumerate(args):
        nm = _NAMED_ARG_RE.match(arg)
        name = nm.group(1) if nm else arg.strip()
        if name == "odoo_version":
            return idx
    return None


_REQUIRED_PARAM_COUNT = {
    t["name"]: len(t.get("required_params", []))
    for t in _SURFACE["tools"]
}


def _arg_span(text: str, open_paren_idx: int) -> str:
    """Return the substring from the opening '(' to its matching ')' (across newlines)."""
    depth = 0
    for j in range(open_paren_idx, len(text)):
        c = text[j]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return text[open_paren_idx : j + 1]
    return text[open_paren_idx:]  # unbalanced — return the rest


def _top_level_args(inner: str) -> list[str]:
    """Split call args on top-level commas (ignoring quotes and nested brackets)."""
    args: list[str] = []
    depth = 0
    quote: str | None = None
    cur = ""
    for c in inner:
        if quote:
            cur += c
            if c == quote:
                quote = None
            continue
        if c in "\"'":
            quote = c
            cur += c
        elif c in "([{":
            depth += 1
            cur += c
        elif c in ")]}":
            depth -= 1
            cur += c
        elif c == "," and depth == 0:
            args.append(cur)
            cur = ""
        else:
            cur += c
    if cur.strip():
        args.append(cur)
    return [a for a in args if a.strip()]


_ALLOWED_PARAMS = {
    t["name"]: set(t.get("required_params", [])) | set(t.get("optional_params", []))
    for t in _SURFACE["tools"]
}
_ALL_TOOLS = sorted(_ALLOWED_PARAMS)
_ANY_TOOL_CALL_RE = re.compile(r"\b" + _MCP_PREFIX + r"(" + "|".join(_ALL_TOOLS) + r")\(")
_NAMED_ARG_RE = re.compile(r"^\s*([A-Za-z_]\w*)\s*=(?!=)")

# Built after _top_level_args / _NAMED_ARG_RE exist (the helper uses both).
_ODOO_VERSION_POS_INDEX = {
    t["name"]: _odoo_version_positional_index(t)
    for t in _SURFACE["tools"]
    if "odoo_version" in t.get("required_params", [])
}


def test_example_tool_calls_use_valid_param_names():
    """Named arguments in example calls must be real params of the tool (per server-surface.json).

    Catches drifted/renamed params (e.g. check_module_exists(module=…) → must be `name`,
    find_deprecated_usage(scope=…) → no such param, lint_check(code_snippet=…) → `code`).
    Sketches with an ellipsis are skipped; positional args carry no name to validate.
    """
    offenders: list[str] = []
    for f in _md_files("skills", "snippets", "agents", "docs"):
        text = f.read_text(encoding="utf-8")
        for m in _ANY_TOOL_CALL_RE.finditer(text):
            tool = m.group(1)
            span = _arg_span(text, m.end() - 1)
            if "..." in span or "…" in span:
                continue
            inner = span[1:-1] if span.startswith("(") and span.endswith(")") else span
            allowed = _ALLOWED_PARAMS[tool]
            for arg in _top_level_args(inner):
                nm = _NAMED_ARG_RE.match(arg)
                if nm and nm.group(1) not in allowed:
                    line_no = text.count("\n", 0, m.start()) + 1
                    offenders.append(
                        f"{f.relative_to(REPO_ROOT)}:{line_no}: {tool}(...) has param "
                        f"'{nm.group(1)}' not in {sorted(allowed)}"
                    )
    assert not offenders, (
        "Example tool calls use parameter names the tool does not accept "
        "(drifted from server-surface.json):\n" + "\n".join(offenders)
    )


def test_example_tool_calls_pass_required_odoo_version():
    """Every concrete, copyable example call to a version-required tool must supply odoo_version.

    An agent copies example calls verbatim, so a call to a tool that requires odoo_version
    but doesn't supply it makes the server reject the call. A call is considered to supply it
    when EITHER it names `odoo_version=` OR it passes enough positional arguments to cover all
    of the tool's required params (examples list required params first). Signature sketches —
    spans containing an ellipsis (`...`/`…`) — are illustrative, not verbatim-copyable, so they
    are skipped (they should still read sensibly, but they don't produce a literal failing call).
    """
    offenders: list[str] = []
    for f in _md_files("skills", "snippets", "agents", "docs"):
        text = f.read_text(encoding="utf-8")
        for m in _TOOL_CALL_RE.finditer(text):
            tool = m.group(1)
            span = _arg_span(text, m.end() - 1)
            if "odoo_version" in span or "..." in span or "…" in span:
                continue
            inner = span[1:-1] if span.startswith("(") and span.endswith(")") else span
            # Only POSITIONAL args (no `name=`) count toward covering odoo_version; a
            # named-but-wrong arg (e.g. scope=...) does not satisfy the required param.
            positional = [a for a in _top_level_args(inner)
                          if not re.match(r"\s*[A-Za-z_]\w*\s*=(?!=)", a)]
            # A positional covers odoo_version only when the call supplies positionals
            # up to and including odoo_version's slot in the canonical signature ORDER
            # (from the tool's example_call) — NOT merely "enough positionals to fill
            # the required count". lint_check(code, language, odoo_version) puts
            # odoo_version at slot 2, so lint_check(code_chunk) (1 positional) fills the
            # `code` slot, not odoo_version → still flagged. find_deprecated_usage puts
            # odoo_version at slot 0, so a single positional there DOES cover it.
            ver_idx = _ODOO_VERSION_POS_INDEX.get(tool)
            if ver_idx is not None and len(positional) > ver_idx:
                continue  # odoo_version slot covered positionally
            line_no = text.count("\n", 0, m.start()) + 1
            snippet = (tool + span).replace("\n", " ")[:90]
            offenders.append(f"{f.relative_to(REPO_ROOT)}:{line_no}: {snippet}")
    assert not offenders, (
        "Example tool calls omit the now-required odoo_version (agents copy these verbatim "
        "and the server rejects the call; pass odoo_version='auto' to reuse the pinned "
        "session, or supply all required params positionally):\n" + "\n".join(offenders)
    )
