"""Guard: AI-agent-facing prose must match the required-odoo_version tool surface.

The real consumers of skills/snippets/agents are AI agents - Claude Code reads
SKILL.md; Gemini / OpenAI / Cursor read the snippets as their system prompt. The
server hard-requires ``odoo_version`` on 19 tools: omitting it raises a
ValidationError *before* the handler runs. The pin is scoped per MCP session, so
the sentinel ``'auto'`` resolves against whatever pin the session currently
holds - possibly a subagent's, if one shares this session. This plugin therefore
forbids BOTH forms: guidance that lets an agent omit ``odoo_version``, and
guidance that tells it to pass ``'auto'``. Every example call carries a CONCRETE
version. SSOT for the rule: plugins/odoo-ai-agents/skills/_shared/concurrency-guard.md
section "OSM session-pin race".

``make gen`` only refreshes content between ``<!-- BEGIN/END GENERATED ... -->``
markers (all derived from ``generator/server-surface.json``). Hand-maintained prose
*outside* those markers is never synced to the surface, so it drifts silently and
``make gen-check`` stays green. These tests scan the WHOLE file - generated blocks
*and* hand prose - so that drift can no longer hide.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN = REPO_ROOT / "plugins" / "odoo-ai-agents"


def _md_files(*subdirs: str) -> list[Path]:
    files: list[Path] = []
    for d in subdirs:
        files.extend((PLUGIN / d).rglob("*.md"))
    return sorted(files)


# --- Guidance that tells an agent odoo_version is droppable - always wrong now ---
# Tight enough not to flag the correct replacement wording ("pass odoo_version='auto'
# instead of a concrete version (never omit it ...)") - "omit" must be directly
# followed by odoo_version, and "(optional" must not be separated from odoo_version
# by a comma (which would mean it qualifies a *different*, genuinely-optional param).
_OMIT_RE = re.compile(r"omit\s+(?:the\s+)?[`'\"]?odoo_version", re.I)
_CAN_OMIT_RE = re.compile(r"can\s+omit\b[^\n]*odoo_version", re.I)
_OPTIONAL_VER_RE = re.compile(r"odoo_version[^,\n]{0,30}\(optional", re.I)
_DEFAULT_AUTO_RE = re.compile(r"odoo_version[^,\n]{0,30}default\s+\"auto\"", re.I)
# Evasions the four above miss by word order or verb choice - each was a live
# false-negative on the pre-fix tree (docs/personas/dev.md:26 and :96,
# docs/setup.md:573). Lexical, English-only: the Vietnamese mirror is covered
# structurally by tests/test_persona_docs_consistency.py, not here.
_WITHOUT_VER_RE = re.compile(r"without\s+[`'\"]?odoo_version", re.I)
_DROP_VER_RE = re.compile(r"\bdrop\s+[`'\"]?odoo_version", re.I)
_VER_OMITTED_RE = re.compile(r"odoo_version\s+(?:is\s+)?omitted", re.I)
# A further evasion the seven above miss: framing the pin as removing the need to
# REPEAT the version, rather than saying "omit"/"optional"/"without". Two surface
# forms were live false-negatives on the pre-fix tree: "no need to repeat the
# version on follow-up calls" (docs/personas/dev.md:177) and, scoped to a line that
# already names odoo_version so it cannot false-positive on an unrelated use of
# "repeating it", "...odoo_version='<version>' instead of repeating it"
# (snippets/gemini-gem-instructions.md:17).
_REPEAT_VER_RE = re.compile(r"repeat(?:ing)?\s+(?:the\s+)?version", re.I)
_REPEATING_IT_RE = re.compile(r"odoo_version[^\n]{0,80}\brepeating it\b", re.I)
_PATTERNS = (_OMIT_RE, _CAN_OMIT_RE, _OPTIONAL_VER_RE, _DEFAULT_AUTO_RE,
             _WITHOUT_VER_RE, _DROP_VER_RE, _VER_OMITTED_RE,
             _REPEAT_VER_RE, _REPEATING_IT_RE)


def test_no_omittable_odoo_version_guidance():
    """No agent-facing .md may claim odoo_version can be omitted / is optional."""
    offenders: list[str] = []
    for f in _md_files("skills", "snippets", "agents", "docs"):
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if any(p.search(line) for p in _PATTERNS):
                offenders.append(f"{f.relative_to(REPO_ROOT)}:{i}: {line.strip()}")
    assert not offenders, (
        "Agent-facing prose still claims odoo_version is omittable/optional. "
        "The server hard-requires it and the pin is scoped per MCP session, so "
        "every example and instruction must carry a CONCRETE version. "
        "Offending lines:\n" + "\n".join(offenders)
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
# excluded - its sole argument *is* the version (passed positionally or by name).
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
# to and including that slot - "enough positionals to fill the required COUNT" is
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
    return text[open_paren_idx:]  # unbalanced - return the rest


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


def _required_param_slots(tool: dict) -> dict[str, int | None]:
    """Map each required param to its positional slot in the tool's example_call.

    Mirrors _odoo_version_positional_index but covers ALL required params. This is
    necessary for tools like entity_lookup/profile_inspect/lint_check/cli_help that
    interleave optional positionals between required ones - consuming required_params
    in declaration order would mis-assign coverage.
    """
    ec = tool.get("example_call", "")
    open_i, close_i = ec.find("("), ec.rfind(")")
    if open_i < 0 or close_i < 0:
        return {}
    names = []
    for arg in _top_level_args(ec[open_i + 1 : close_i]):
        nm = _NAMED_ARG_RE.match(arg)
        names.append(nm.group(1) if nm else arg.strip())
    slots = {}
    for r in tool.get("required_params", []):
        slots[r] = names.index(r) if r in names else None
    return slots


_REQUIRED_PARAM_SLOTS = {t["name"]: _required_param_slots(t) for t in _SURFACE["tools"]}
_REQUIRED_PARAMS = {t["name"]: t.get("required_params", []) for t in _SURFACE["tools"]}


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
    of the tool's required params (examples list required params first). Signature sketches -
    spans containing an ellipsis (`...`/`…`) - are illustrative, not verbatim-copyable, so they
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
            # (from the tool's example_call) - NOT merely "enough positionals to fill
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
        "and the server rejects the call; pass a CONCRETE version, e.g. odoo_version='17.0' "
        "or the placeholder odoo_version='<version>', or supply all required params "
        "positionally):\n" + "\n".join(offenders)
    )


def test_example_tool_calls_pass_all_required_params():
    """Every concrete example call must supply ALL required params (per server-surface.json).

    The companion odoo_version test only guards one param; this guards the rest (method, name,
    model, kind, query, intent, ...). An agent copies an example like
    model_inspect(model='x', odoo_version='17.0') verbatim and the server rejects it for the
    missing required method=. A required param counts as supplied when EITHER it is named
    (param=) OR a positional argument fills its slot in the tool's canonical example_call order
    (positional coverage uses example-slot index, NOT required_params order - some tools put an
    optional positional before a required one). Ellipsis sketches (`...`/`...`) are exempt, same
    as the other example-call gates.
    """
    offenders: list[str] = []
    for f in _md_files("skills", "snippets", "agents", "docs"):
        text = f.read_text(encoding="utf-8")
        for m in _ANY_TOOL_CALL_RE.finditer(text):
            tool = m.group(1)
            required = _REQUIRED_PARAMS[tool]
            if not required:
                continue  # list_available_versions / list_available_profiles
            span = _arg_span(text, m.end() - 1)
            if "..." in span or "…" in span:
                continue  # sketch - exempt (same convention as lines 207, 240)
            inner = span[1:-1] if span.startswith("(") and span.endswith(")") else span
            args = _top_level_args(inner)
            named = {nm.group(1) for a in args for nm in [_NAMED_ARG_RE.match(a)] if nm}
            positional_count = sum(1 for a in args if not _NAMED_ARG_RE.match(a))
            slots = _REQUIRED_PARAM_SLOTS[tool]
            missing = []
            for r in required:
                if r in named:
                    continue
                slot = slots.get(r)
                if slot is not None and positional_count > slot:
                    continue  # a positional fills this required param's example slot
                missing.append(r)
            if missing:
                line_no = text.count("\n", 0, m.start()) + 1
                snippet = (tool + span).replace("\n", " ")[:90]
                offenders.append(
                    f"{f.relative_to(REPO_ROOT)}:{line_no}: {tool}() missing required "
                    f"{missing}: {snippet}"
                )
    assert not offenders, (
        "Example tool calls omit required params (agents copy these verbatim and the OSM server "
        "rejects the call with a ValidationError before the handler runs). Supply every required "
        "param by name, pass them positionally up to the param's slot, or use '...' for an "
        "illustrative sketch:\n" + "\n".join(offenders)
    )


# Built at module level alongside _REQUIRED_PARAMS / _REQUIRED_PARAM_SLOTS above.
# Maps tool name -> conditional_required dict from server-surface.json.
# Tools without the key are absent from this dict (no conditional rules to enforce).
_CONDITIONAL_REQUIRED = {
    t["name"]: t["conditional_required"]
    for t in _SURFACE["tools"]
    if "conditional_required" in t
}


def test_example_tool_calls_pass_conditional_required_params():
    """Every concrete example call to a kind-discriminated tool must supply the kind-conditional params.

    Some tools (entity_lookup) have a required `kind` discriminator whose value determines which
    additional params must be present. For example entity_lookup(kind='field', ...) requires both
    `model` and `field`; entity_lookup(kind='method', ...) requires `model` and `method_name`.
    These conditional params are listed in the tool's `conditional_required` map in server-surface.json.

    A call passes when EITHER:
    - the span contains `...`/`...` (sketch - exempt by convention), OR
    - `kind` is absent or not a resolvable literal (pipe-alternation, placeholder `<...>`) - skip, OR
    - `kind` is a literal that matches a `conditional_required` key and all its required params
      are present as named args in the call.

    To fix: add the missing named arg (e.g. `field=<field_name>` for kind='field'), or convert
    to an illustrative sketch using `...` if the call is not a copy-template.
    """
    offenders: list[str] = []
    for f in _md_files("skills", "snippets", "agents", "docs"):
        text = f.read_text(encoding="utf-8")
        for m in _ANY_TOOL_CALL_RE.finditer(text):
            tool = m.group(1)
            if tool not in _CONDITIONAL_REQUIRED:
                continue
            span = _arg_span(text, m.end() - 1)
            if "..." in span or "…" in span:
                continue  # sketch - exempt
            inner = span[1:-1] if span.startswith("(") and span.endswith(")") else span
            args = _top_level_args(inner)
            named = {nm.group(1): a for a in args for nm in [_NAMED_ARG_RE.match(a)] if nm}
            # Determine kind value
            kind_arg = named.get("kind")
            if kind_arg is None:
                continue  # kind not provided as named arg - cannot enforce (no discriminator)
            if "|" in kind_arg:
                continue  # pipe-alternation (kind='field'|'method') - ambiguous, no single rule to apply
            # Extract the literal value from kind='value' or kind="value"
            kind_val_match = re.search(r"""=\s*['"]([^'"]+)['"]""", kind_arg)
            if not kind_val_match:
                continue  # not a simple literal (placeholder or complex expression)
            kind_val = kind_val_match.group(1)
            # Skip if value contains pipe-alternation or is a placeholder
            if "|" in kind_val or (kind_val.startswith("<") and kind_val.endswith(">")):
                continue
            cond_map = _CONDITIONAL_REQUIRED[tool]
            if kind_val not in cond_map:
                continue  # kind value not in the map - no rule to enforce
            required_for_kind = cond_map[kind_val]
            missing = [p for p in required_for_kind if p not in named]
            if missing:
                line_no = text.count("\n", 0, m.start()) + 1
                snippet = (tool + span).replace("\n", " ")[:90]
                offenders.append(
                    f"{f.relative_to(REPO_ROOT)}:{line_no}: {tool}(kind={kind_val!r}) "
                    f"missing {missing}: {snippet}"
                )
    assert not offenders, (
        "Example tool calls omit kind-conditional required params (entity_lookup dispatches on "
        "'kind' and requires different params per kind - e.g. kind='field' needs model= and field=, "
        "kind='method' needs model= and method_name=). Add the missing param or use '...' for an "
        "illustrative sketch that is not a copy-template:\n" + "\n".join(offenders)
    )


# --- Agents must not instruct an OSM tool they were not granted --------------------
# A subagent runs with ONLY the tools in its `tools:` frontmatter allowlist. If its
# body tells the executor to use an OSM tool that is NOT in that allowlist (e.g. the
# old odoo-ui-reviewer / odoo-ui-debugger Step 0 -> `list_available_versions`), the
# executor emits a call it cannot make: the tool is unavailable, the step fails, and
# the agent silently degrades to a default. CI never caught this because the SSOT
# checks *param names* and *odoo_version*, not *grant scope*. This guard closes that
# gap. OSM tool names are specific snake_case identifiers, so matching an inline-code
# `tool` reference or a `tool(` call does not collide with ordinary prose.

AGENT_FILES = sorted((PLUGIN / "agents").glob("*.md"))
_OSM_FM_PREFIX = "mcp__odoo-semantic__"


def _frontmatter_body(text: str) -> tuple[str, str]:
    """Return (frontmatter, body) split on the leading --- ... --- fence."""
    parts = text.split("---", 2)
    return (parts[1], parts[2]) if len(parts) >= 3 else ("", text)


def test_agents_do_not_instruct_ungranted_osm_tools():
    """An agent body must not reference an OSM tool absent from its tools: allowlist.

    The agent can only call what it was granted; naming a tool it lacks makes the
    executor emit a failing call. Flags any OSM tool referenced as an inline-code
    identifier (`tool`) or a call (`tool(`) in the body that is not in the allowlist.
    """
    offenders: list[str] = []
    for f in AGENT_FILES:
        fm, body = _frontmatter_body(f.read_text(encoding="utf-8"))
        # Agents that omit the `tools:` allowlist inherit the FULL surface, so every OSM
        # tool is granted (we never disallow OSM). With an explicit allowlist, fall back to
        # the enumerated grant so a body cannot name a tool the allowlist excludes.
        if "\ntools:" in ("\n" + fm):
            granted = {t for t in _ALL_TOOLS if (_OSM_FM_PREFIX + t) in fm}
        else:
            granted = set(_ALL_TOOLS)
        for tool in _ALL_TOOLS:
            if tool in granted:
                continue
            if re.search(r"`" + re.escape(tool) + r"`", body) or \
               re.search(r"\b" + re.escape(tool) + r"\b\s*\(", body):
                offenders.append(
                    f"{f.relative_to(REPO_ROOT)}: body references OSM tool "
                    f"'{tool}' not in its tools: allowlist"
                )
    assert not offenders, (
        "Agent bodies instruct OSM tools they were not granted (the executor would emit "
        "a failing call). Add the tool to the agent's tools: allowlist, or stop "
        "referencing it in the body:\n" + "\n".join(offenders)
    )


_AUTO_VALUE_RE = re.compile(r"^\s*['\"]auto['\"]\s*$")


def test_example_tool_calls_reject_the_auto_sentinel():
    """No example call may pass odoo_version='auto'.

    The pin is scoped per MCP session, so 'auto' resolves against whatever pin the
    session holds - under fan-out that is another actor SHARING the session's
    version, and the call SUCCEEDS with the WRONG version rather than erroring.
    The companion
    test_example_tool_calls_pass_required_odoo_version is value-BLIND (it accepts
    any span containing `odoo_version`), so this is the assertion that makes the
    ban in concurrency-guard.md enforceable.

    Scoped to argument SPANS, so a line that quotes 'auto' in order to BAN it stays
    green; the four such warning sites are asserted separately below.
    """
    offenders: list[str] = []
    for f in _md_files("skills", "snippets", "agents", "docs"):
        text = f.read_text(encoding="utf-8")
        for m in _ANY_TOOL_CALL_RE.finditer(text):
            span = _arg_span(text, m.end() - 1)
            inner = span[1:-1] if span.startswith("(") and span.endswith(")") else span
            for arg in _top_level_args(inner):
                nm = _NAMED_ARG_RE.match(arg)
                if nm and nm.group(1) == "odoo_version":
                    value = arg[nm.end():]
                    if _AUTO_VALUE_RE.match(value):
                        line_no = text.count("\n", 0, m.start()) + 1
                        offenders.append(
                            f"{f.relative_to(REPO_ROOT)}:{line_no}: "
                            f"{m.group(1)}(... odoo_version={value.strip()} ...)"
                        )
    assert not offenders, (
        "Example calls pass the 'auto' sentinel. Pass a CONCRETE version or the "
        "placeholder odoo_version='<version>'. SSOT: skills/_shared/"
        "concurrency-guard.md. Offending calls:\n" + "\n".join(offenders)
    )


def test_auto_is_still_named_in_the_four_warning_sites():
    """The ban must be TAUGHT, not just enforced: exactly the four sites that quote
    'auto' in order to forbid it must keep doing so, each in a sentence that also
    carries a prohibition token.

    Fence: green today and after. Without it, a naive "delete every auto" fix would
    also delete the four places that teach the ban.
    """
    prohibition = ("HARD RULE", "never", "rejected", "racy", "may resolve to someone else")
    sites = [
        PLUGIN / "agents" / "odoo-backend-coder.md",
        PLUGIN / "agents" / "odoo-frontend-coder.md",
        PLUGIN / "docs" / "setup.md",
        PLUGIN / "generator" / "server-surface.json",
    ]
    for p in sites:
        text = p.read_text(encoding="utf-8")
        assert "auto" in text, f"{p.name} must still name the 'auto' sentinel to ban it"
        for line in text.splitlines():
            if "auto'" in line or 'auto"' in line:
                assert any(tok in line for tok in prohibition), (
                    f"{p.name} mentions the 'auto' sentinel without a prohibition token: "
                    f"{line.strip()[:160]}"
                )


def _section_short_forms(guard_text: str) -> list[str]:
    """Each '## Heading' reduced to its lead phrase, cut at the first ' (' or ' - '.

    Pointer prose in this repo quotes only the lead phrase of a heading (e.g. "§ Browser
    exclusivity" for "## Browser exclusivity (orthogonal)") and then keeps writing the
    surrounding sentence with no fixed terminator - a real citation and a full paragraph
    are lexically indistinguishable past that point. A prefix check against the short form
    (rather than demanding the pointer's trailing prose be a verbatim substring of the whole
    heading) accepts every legitimate citation style on this tree while still failing a
    reference to a heading that was renamed or never existed.
    """
    forms = []
    for ln in guard_text.splitlines():
        if ln.startswith("## "):
            heading = ln[3:].strip()
            forms.append(re.split(r"\s\(|\s-\s", heading, maxsplit=1)[0].strip())
    return forms


def _race_core(name: str) -> str:
    """Strip an optional leading 'OSM ' and lowercase, so 'OSM session-pin race' and a
    bare 'session-pin race' mention compare equal regardless of the OSM prefix."""
    name = name.strip()
    if name[:4].upper() == "OSM ":
        name = name[4:].strip()
    return name.lower()


_WS_RE = re.compile(r"\s+")


def _normalize_ws(text: str) -> str:
    """Collapse all whitespace, including newlines, to single spaces.

    A pointer sentence can wrap across a line break (e.g. a quoted heading name split as
    `"OSM\\nsession-pin race"`); a line-anchored regex silently drops the wrapped half of
    the sentence - the same class of bug as the three line-wrap tautologies already fixed
    elsewhere in this file. Matching against whitespace-normalized text closes it for good.
    """
    return _WS_RE.sub(" ", text)


# A concurrency-guard.md section gets cited in two structurally different ways, and BOTH
# must be recognised or a rename leaves silent dangling pointers - a past heading rename
# once left several references dangling because the guard at the time recognised only ONE
# syntactic shape (filename -> "section"/"§" keyword -> name) and never scanned docs/.
#
# Form 1 - keyword-anchored: works for ANY heading name (e.g. "Odoo instance allocation"),
# filename (".md" optional) followed by "section"/"§" then the name, quoted or bare.
_KEYWORD_POINTER_RE = re.compile(
    r"concurrency-guard(?:\.md)?`?\s+(?:section|§)\s*[\"'“]?([^\n]{1,150})"
)

# Form 2 - a bare "<qualifier>-pin race" phrase (optional "OSM " prefix), with NO
# requirement that a filename appear nearby. This compound is coined specifically for the
# one concurrency-guard.md heading shaped this way and is never used for anything else on
# this tree (every other "race" mention here is "race window/race-free/write race/
# bootstrap-race" - none contain "-pin race"), so the phrase alone is an unambiguous
# reference. Dropping the filename-adjacency requirement is what catches the bare,
# reversed-word-order, and missing-".md" dangling forms that Form 1 structurally cannot:
# a proximity rule would have to pick an arbitrary window size, and the real dangling
# reference in INSTANCE-ALLOCATION.md sits in a different paragraph from its nearest
# "concurrency-guard.md" mention, so no window would catch it while a term-currency check
# does, cleanly.
_RACE_PHRASE_RE = re.compile(r"\b(?:OSM\s+)?([A-Za-z][\w-]*-pin\s+race)\b")


def test_every_concurrency_guard_section_pointer_resolves_to_a_real_heading():
    """Every reference to a concurrency-guard.md section - however phrased - must name a
    heading that actually exists there today.

    No existing test guards heading TEXT (test_concurrency_guard_ssot.py asserts only the
    filename substring), so a rename would otherwise leave every pointer dangling silently.
    This test reads the CURRENT heading dynamically (never a hardcoded name), so it doubles
    as the guard against a future rename: if pointers are not updated in the same change,
    this fails - no separate heading-text assertion is needed.

    Scans the WHOLE plugin tree, not a curated subdir list: a real pointer has been found
    living in skills/, snippets/, agents/, docs/reference/, workflows/, and the plugin
    README, so scoping this to a shorter directory list would repeat the exact "one
    location, one syntactic shape" mistake this test exists to catch.
    """
    guard = (PLUGIN / "skills" / "_shared" / "concurrency-guard.md").read_text(encoding="utf-8")
    short_forms = _section_short_forms(guard)
    valid_race_cores = {_race_core(sf) for sf in short_forms if _race_core(sf).endswith("race")}
    offenders = []
    for f in sorted(PLUGIN.rglob("*.md")):
        text = _normalize_ws(f.read_text(encoding="utf-8"))
        for m in _KEYWORD_POINTER_RE.finditer(text):
            tail = m.group(1).strip().lstrip("`\"'“")
            if not any(tail.startswith(sf) for sf in short_forms):
                offenders.append(f"{f.relative_to(REPO_ROOT)}: points at absent section '{tail[:60]}'")
        for m in _RACE_PHRASE_RE.finditer(text):
            if _race_core(m.group(1)) not in valid_race_cores:
                offenders.append(f"{f.relative_to(REPO_ROOT)}: names stale race-phrase '{m.group(0)}'")
    assert not offenders, "dangling concurrency-guard.md section pointers:\n" + "\n".join(offenders)


# --- SSOT-bound guard: concurrency-guard.md's session-pin race claim must match, not
# contradict, generator/server-surface.json - the in-repo mirror of the live server's own
# set_active_version / set_active_profile descriptions ----------------------------------
# Defect class this guards against: agent-facing prose asserted a fact about the external
# OSM server (the pin is "scoped to the API key, not the calling agent or session") that
# nobody ever checked against the server's own tool descriptions. It was false - the live
# server shares each pin per (api_key_id, mcp_session_id), i.e. per MCP session, not per
# API key alone - and the false claim briefly drove a wrong-direction heading rename before
# being caught and reverted. Every prior review of that rename compared the heading to the
# body and the body to itself; none compared the body to the source of truth. This test does,
# in both directions: it fails if the SSOT mirror itself stops carrying the scope fact (so
# the prose is never left citing a mirror that has gone stale), and it fails if either file
# restates the debunked claim.
_FALSE_SCOPE_PHRASE_RE = re.compile(
    r"scoped\s+to\s+the\s+api\s*key\b|api[- ]key[- ]scoped\b",
    re.IGNORECASE,
)


def test_session_pin_race_scope_claim_matches_ssot():
    """concurrency-guard.md must state the SAME scope generator/server-surface.json's own
    set_active_version / set_active_profile descriptions state, and must never restate the
    debunked 'scoped to the API key (not the calling agent or session)' claim.

    generator/server-surface.json is the in-repo mirror of the live server's tool surface.
    If ITS descriptions ever stop carrying the per-session scope fact, this fails loudly
    instead of letting the prose silently trust a stale mirror - the "consider whether the
    SSOT itself needs it" case this guard exists for.
    """
    surface_by_name = {t["name"]: t for t in _SURFACE["tools"]}
    for tool_name in ("set_active_version", "set_active_profile"):
        desc = surface_by_name[tool_name]["description"]
        assert "mcp_session_id" in desc, (
            f"generator/server-surface.json's {tool_name} description no longer states "
            "the (api_key_id, mcp_session_id) scope - concurrency-guard.md cites this "
            "SSOT for that fact; update the SSOT (re-derived from the live server's own "
            "tool description) before the prose can cite it again"
        )
        assert not _FALSE_SCOPE_PHRASE_RE.search(desc), (
            f"generator/server-surface.json's {tool_name} description restates the "
            "debunked 'scoped to the API key' claim"
        )

    guard = (PLUGIN / "skills" / "_shared" / "concurrency-guard.md").read_text(encoding="utf-8")
    assert "api_key_id" in guard and "mcp_session_id" in guard, (
        "concurrency-guard.md no longer states the SSOT's (api_key_id, mcp_session_id) "
        "scope for the session-pin race - it must be grounded in generator/server-surface"
        ".json's tool descriptions, not restated from memory"
    )
    assert not _FALSE_SCOPE_PHRASE_RE.search(guard), (
        "concurrency-guard.md restates the debunked 'scoped to the API key' claim - the "
        "server scopes each pin per (api_key_id, mcp_session_id), i.e. per MCP session; "
        "two independent sessions never interfere, the hazard is multiple actors sharing "
        "ONE session"
    )


# --- Repo-wide guard: the false "scoped to the API key" claim, in ANY phrasing, ANY file --
# The two tests above bind ONE file (concurrency-guard.md) to the SSOT. This regressed
# TWICE regardless: it was already fixed once (CHANGELOG #253, v2.6.0, "per API key" ->
# "per live MCP session") and came back in >=15 more sites across agents/, skills/,
# snippets/, and docs/ (both languages) - a single-file guard cannot catch a claim that
# spreads by copy-paste into files the guard never reads. This test scans EVERY markdown
# file in the whole repo (not just the plugin) and matches the CLAIM structurally, not one
# hardcoded sentence, so a new phrasing or a new site cannot slip through the same gap
# twice.
#
# Structural approach (two-stage, no allowlist):
#   1. Candidate: an "API key" token (any casing/hyphenation: `api key`, `api-key`,
#      `API-Key`; NOT `api_key_id` - the trailing `_id` breaks the `\b` word boundary after
#      "key" on purpose, so the SSOT's own `(api_key_id, mcp_session_id)` tuple can never
#      match here) sitting within a tight 20-char window of scope vocabulary (`per`,
#      `scope(d)`, `keyed`, `alone`, `state`, `racy`, `pin(ned)`, or Vietnamese `theo`). This
#      is what separates a genuine scope assertion ("the pin is per-API-key state") from an
#      unrelated mention ("sign up for an API key") - measured: the only near-miss on this
#      tree, commands/odoo-setup.md's "session-load state ... API key" (an unrelated
#      credential-masking note), sits outside this window (the connective tissue between
#      "state" and "API key" there runs ~28 chars, this window is 20).
#   2. Once a candidate is found, it is a violation UNLESS a genuine session-scope phrase
#      appears within 300 characters either side: `mcp_session_id`, `MCP session`,
#      `session-scoped`, `scoped to {this,the,one} session`, `keyed to {this,the} session`,
#      or Vietnamese `phien MCP` / `theo (tung) phien`. Deliberately NOT a bare "session" or
#      "per session" - "Call it once per session" (a cadence instruction) and "Session
#      context" (a heading label) both contain "session" yet assert nothing about the PIN's
#      scope; a bare-word check would have let the pre-fix dev.md:26 row survive (it
#      contains both "API-key-scoped" AND "once per session" in the same cell). The 300-char
#      radius (vs. the 20-char candidate window) exists because a correction can be several
#      wrapped lines away from the claim it corrects - CHANGELOG.md's own history of this
#      exact bug narrates the false claim and its fix in the same paragraph, and must be
#      able to keep doing that without tripping this guard.
_API_KEY_TOKEN_RE = re.compile(r"\bapi[\s_-]*key\b", re.IGNORECASE)
_SCOPE_VOCAB_NEAR_RE = re.compile(
    r"\b(?:per|scope|scoped|keyed|alone|state|racy|pin|pinned|theo)\b", re.IGNORECASE
)
_SESSION_SCOPE_PROOF_RE = re.compile(
    r"mcp_session_id"
    r"|\bsession[\s-]scoped\b"
    r"|\bscoped\s+to\s+(?:this|the|one)\s+session\b"
    r"|\bkeyed\s+to\s+(?:this|the)\s+session\b"
    r"|\bMCP\s+session\b"
    r"|phi[eê]n\s+MCP\b"
    r"|theo\s+(?:t[uừ]ng\s+)?phi[eê]n\b",
    re.IGNORECASE,
)
_CANDIDATE_VOCAB_WINDOW = 20
_SESSION_PROOF_WINDOW = 300
# Reuses the exact marker syntax generator/gen_surface.py emits (see also
# tests/test_git_delegation_boundary.py's identical pattern) - generated tool descriptions
# are already bound to the SSOT by test_session_pin_race_scope_claim_matches_ssot above and
# must never be hand-scored by this structural scan.
_GENERATED_BLOCK_RE = re.compile(
    r"<!--\s*BEGIN GENERATED\b.*?-->.*?<!--\s*END GENERATED\b.*?-->",
    re.DOTALL | re.IGNORECASE,
)


def _blank_generated_regions(text: str) -> str:
    """Replace generated-marker spans with whitespace (newlines kept) so line numbers for
    the rest of the file stay accurate and no generated content can ever match."""

    def _blank(m: re.Match) -> str:
        return "".join(c if c == "\n" else " " for c in m.group(0))

    return _GENERATED_BLOCK_RE.sub(_blank, text)


def _normalize_with_linemap(text: str) -> tuple[str, list[int]]:
    """Collapse all whitespace runs (including newlines) to a single space, returning the
    normalized string plus a parallel array mapping each output index back to its 1-based
    source line - needed because a false-claim sentence can wrap across physical lines
    (CHANGELOG.md hard-wraps at ~90 columns; this file's own docstring already documents the
    identical problem for pointer-matching above)."""
    norm_chars: list[str] = []
    linemap: list[int] = []
    line = 1
    prev_was_space = False
    for ch in text:
        if ch == "\n":
            line += 1
        if ch.isspace():
            if not prev_was_space:
                norm_chars.append(" ")
                linemap.append(line)
            prev_was_space = True
        else:
            norm_chars.append(ch)
            linemap.append(line)
            prev_was_space = False
    return "".join(norm_chars), linemap


def _api_key_scope_offenders(text: str) -> list[tuple[int, str]]:
    """Return (line, context) for every place `text` asserts the pin's scope is the API key
    without also naming the MCP session - see the two-stage algorithm documented above."""
    norm, linemap = _normalize_with_linemap(_blank_generated_regions(text))
    offenders: list[tuple[int, str]] = []
    for m in _API_KEY_TOKEN_RE.finditer(norm):
        start, end = m.start(), m.end()
        vocab_window = norm[max(0, start - _CANDIDATE_VOCAB_WINDOW):end + _CANDIDATE_VOCAB_WINDOW]
        if not _SCOPE_VOCAB_NEAR_RE.search(vocab_window):
            continue  # not a scope assertion at all (e.g. "sign up for an API key")
        proof_window = norm[max(0, start - _SESSION_PROOF_WINDOW):end + _SESSION_PROOF_WINDOW]
        if _SESSION_SCOPE_PROOF_RE.search(proof_window):
            continue  # correctly (or historically, in the same breath) names the session
        lineno = linemap[start] if start < len(linemap) else (linemap[-1] if linemap else 1)
        context = norm[max(0, start - 60):end + 60].strip()
        offenders.append((lineno, context))
    return offenders


def test_no_api_key_only_scope_claim_anywhere_in_repo():
    """No markdown file anywhere in the repo may claim the set_active_version /
    set_active_profile pin is scoped to the API key without also naming the MCP session -
    in ANY phrasing, English or Vietnamese. This is the repo-wide counterpart of
    test_session_pin_race_scope_claim_matches_ssot (which binds ONLY concurrency-guard.md):
    the same false claim was fixed once before (CHANGELOG #253, v2.6.0) and regressed into
    more than a dozen other files a single-file guard could never see coming. Scans every
    ``*.md`` in the repo (not just the plugin), generated-marker regions excluded (those are
    covered separately by the SSOT-bound test above)."""
    offenders: list[str] = []
    for f in sorted(REPO_ROOT.rglob("*.md")):
        if ".git" in f.parts:
            continue
        for lineno, context in _api_key_scope_offenders(f.read_text(encoding="utf-8")):
            offenders.append(f"{f.relative_to(REPO_ROOT)}:{lineno}: ...{context}...")
    assert not offenders, (
        "Prose states (or restates) the debunked 'pin is scoped to the API key' claim "
        "somewhere in the repo. The server scopes each pin per (api_key_id, mcp_session_id) "
        "- i.e. per MCP session, last-write-wins; two independent sessions never interfere, "
        "the hazard is multiple actors sharing ONE session. Either state that scope exactly "
        "(matching concurrency-guard.md's 'OSM session-pin race' section) or, better, point "
        "at it instead of restating it. Offending lines:\n" + "\n".join(offenders)
    )
