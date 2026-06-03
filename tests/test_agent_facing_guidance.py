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
    """Snippet/agent prose must not document parameter names no tool accepts."""
    offenders: list[str] = []
    for f in _md_files("snippets", "agents"):
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            for tok in _WRONG_PARAM_TOKENS:
                if tok in line:
                    offenders.append(f"{f.relative_to(REPO_ROOT)}:{i}: '{tok}' in: {line.strip()}")
    assert not offenders, (
        "Snippet/agent prose uses parameter names no current tool accepts "
        "(drifted from server-surface.json required/optional params):\n"
        + "\n".join(offenders)
    )
