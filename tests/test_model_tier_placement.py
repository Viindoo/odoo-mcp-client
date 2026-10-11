"""Guard: model-tier rules live where the CALLER reads them, and never rest on context size.

Business rules protected (behavior-first, ODOO-AI-ETHOS #8):

1. An agent reads its own body only AFTER it was launched - by then its model is already chosen.
   A sentence in a LEAF agent's body telling it which model it runs at ("Model floor", "haiku for
   boilerplate", "MODE=synthesis (opus)") can therefore never steer anything: the caller that
   actually picks the model never reads it, and the agent that reads it cannot act on it. Such a
   rule belongs in the agent's frontmatter `model:` default, the shared tier SSOT, or the
   skill/agent that launches it. A SPAWNER agent may name tiers - for the children IT launches.

2. Context size is never a reason to raise a tier or to split work: every model family now holds
   a large window, so a cap justified by "fits one context window" / "overflow one opus context"
   silently forces fan-out or opus on work a single cheaper worker does well.

3. The documented model-resolution order is the one Claude Code applies: the launch `model`
   parameter beats the agent frontmatter, which beats `CLAUDE_CODE_SUBAGENT_MODEL`. A caller
   that believes the env var wins stops passing `model` and silently inherits instead.

4. The session's MAIN agent learns the rule at SessionStart: the injected orchestration digest
   tells it to pass `model` explicitly on every launch and where the tier map lives. Without it,
   the main agent's own Explore / general-purpose launches inherit its (often top-tier) model.

Genre A (structural) throughout - each assertion fails for a concrete textual reason.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ODOO = ROOT / "plugins" / "odoo-ai-agents"
GIT = ROOT / "plugins" / "git-toolkit"

TIER_RE = re.compile(r"\b(?:haiku|sonnet|opus|fable)\b", re.IGNORECASE)
SELF_MODEL_RE = re.compile(r"model floor|own model identity", re.IGNORECASE)


def _split(path: Path) -> tuple[str, str]:
    """(frontmatter, body) of a Markdown file with a leading --- block."""
    text = path.read_text(encoding="utf-8")
    parts = text.split("\n---\n", 1)
    assert text.startswith("---") and len(parts) == 2, f"{path}: no frontmatter block"
    return parts[0], parts[1]


def _odoo_leaf_agents() -> list[Path]:
    """Agents the odoo-ai-agents registry declares role=leaf (they launch nobody)."""
    registry = json.loads((ODOO / "generator" / "skill_tool_deps.json").read_text(encoding="utf-8"))
    leaves = [name for name, e in registry["agents"].items() if e.get("role") == "leaf"]
    assert leaves, "premise: the registry must declare leaf agents"
    return [ODOO / "agents" / f"{name}.md" for name in sorted(leaves)]


def _git_leaf_agents() -> list[Path]:
    """git-toolkit agents whose explicit `tools:` allowlist grants no agent-launch tool."""
    leaves = []
    for path in sorted((GIT / "agents").glob("*.md")):
        front, _ = _split(path)
        tools = re.search(r"^tools:\s*(.+)$", front, re.MULTILINE)
        if tools and not re.search(r"\b(?:Agent|Task)\b", tools.group(1)):
            leaves.append(path)
    assert leaves, "premise: git-toolkit must have leaf agents with an explicit tools allowlist"
    return leaves


def _agent_files() -> list[Path]:
    return sorted((ODOO / "agents").glob("*.md")) + sorted((GIT / "agents").glob("*.md"))


def test_leaf_agent_body_never_names_a_model_tier():
    """A leaf launches nobody, so any tier name in its body can only be about ITSELF - which it
    reads too late to matter. Fails naming the agent and the offending line."""
    offenders = []
    for path in _odoo_leaf_agents() + _git_leaf_agents():
        assert path.is_file(), f"premise: {path} must exist"
        _, body = _split(path)
        for n, line in enumerate(body.splitlines(), 1):
            if TIER_RE.search(line):
                offenders.append(f"{path.relative_to(ROOT)} body:{n}: {line.strip()[:120]}")
    assert not offenders, (
        "a leaf agent's body names a model tier; the caller picks the model before the agent "
        "reads its body - move the rule to the frontmatter `model:`, the tier SSOT, or the "
        "launching skill:\n" + "\n".join(offenders)
    )


def test_no_agent_body_instructs_its_own_model():
    """Spawners may choose their CHILDREN's tiers, but no agent - leaf or spawner - may carry a
    rule about the model it itself runs at ('Model floor', 'confirm your own model identity')."""
    offenders = []
    for path in _agent_files():
        _, body = _split(path)
        for n, line in enumerate(body.splitlines(), 1):
            if SELF_MODEL_RE.search(line):
                offenders.append(f"{path.relative_to(ROOT)} body:{n}: {line.strip()[:120]}")
    assert not offenders, "agent body instructs its own model:\n" + "\n".join(offenders)


CONTEXT_SIZE_RE = re.compile(
    r"fits?\b[^.\n]{0,40}\bone context"
    r"|overflow\w*\b[^.\n]{0,25}\bcontext\b"
    r"|into one \w+ context"
    r"|exceeded the worker budget",
    re.IGNORECASE,
)


def _prose_corpus() -> list[Path]:
    files = []
    for plugin in (ODOO, GIT):
        for sub in ("skills", "agents", "snippets", "workflows", "commands"):
            base = plugin / sub
            if base.is_dir():
                files += [p for p in base.rglob("*") if p.suffix in (".md", ".yaml", ".json")]
    return sorted(files)


def test_no_tier_or_split_rests_on_context_size():
    """Fails on any prose that justifies a cap, a split or a tier by what fits in one context."""
    offenders = []
    for path in _prose_corpus():
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if CONTEXT_SIZE_RE.search(line):
                offenders.append(f"{path.relative_to(ROOT)}:{n}: {line.strip()[:120]}")
    assert not offenders, (
        "context size is never a reason to raise a tier or to split work:\n" + "\n".join(offenders)
    )


STALE_ORDER_RE = re.compile(
    r"env\b[^>\n]{0,40}>\s*`?(?:the\s+)?(?:agent-launch|agent-param|launch)", re.IGNORECASE
)


def test_model_resolution_order_puts_the_launch_param_first():
    """No prose may claim the env var outranks the launch `model` parameter, and the git-toolkit
    tier SSOT must still state the order (so the convention it builds on stays explained)."""
    offenders = []
    for path in _prose_corpus():
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if STALE_ORDER_RE.search(line):
                offenders.append(f"{path.relative_to(ROOT)}:{n}: {line.strip()[:120]}")
    assert not offenders, "stale model-resolution order (env first):\n" + "\n".join(offenders)
    tiers = (GIT / "snippets" / "git-model-tiers.md").read_text(encoding="utf-8")
    assert "CLAUDE_CODE_SUBAGENT_MODEL" in tiers, (
        "git-model-tiers.md must keep stating where the env var sits in the resolution order"
    )


def test_session_start_digest_tells_main_agent_to_pass_model():
    """The digest SessionStart injects must tell the main agent to pass `model` on every launch
    and point at the tier SSOT - the only path by which the main session learns the map."""
    digest = (ODOO / "docs" / "reference" / "orchestration-digest.txt").read_text(encoding="utf-8")
    assert re.search(r"`?model`?[^\n]{0,80}explicit|explicit[^\n]{0,80}`?model`?", digest, re.I), (
        "orchestration-digest.txt must tell the main agent to pass `model` explicitly"
    )
    assert "concurrency-guard.md" in digest, (
        "orchestration-digest.txt must point at the model-tier SSOT (concurrency-guard.md)"
    )
