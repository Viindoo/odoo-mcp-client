r"""Agent-facing-prose inventory-count guard - extends the count-drift guard in
`test_readme_inventory_counts.py` (README.md only) to the rest of agent-facing
prose: snippets, skills, agents, commands, and workflows, across every plugin.

Why this file exists (closing PR #189's last defect): the README guard closed
one surface, but the SAME bug (a bare count of a growable file/tool collection,
typed once and never revisited) had already escaped into a snippet's own SSOT
comment. `plugins/odoo-ai-agents/snippets/continuation-contract.md` stated
"pasting the block into 31 SKILL.md + 4 agent files" - the real numbers were 50
and 21 (roughly 2x and 5x off) at the time this was found. Separately,
`snippets/gemini-gem-instructions.md`, `snippets/openai-gpt-instructions.md`,
and `snippets/jetbrains-mcp-config.md` each hardcoded "31 tools + 9 MCP
Resources" OUTSIDE the `<!-- BEGIN/END GENERATED TOOLS -->` markers the first
two files also contain - a number `make gen` never touches, even though the
SAME FILE'S generated section, a few hundred lines below, regenerates the
real, current tool/resource list on every `make gen` run. All three happened
to be numerically correct at the moment of writing (31 tools, 9 resources per
`generator/server-surface.json`) - which is precisely what makes this bug
dangerous: it reads as "already verified" while nothing re-verifies it the
moment a tool or resource is added or removed.

Fix applied in all four files: remove the dependence on the hardcoded number
rather than update it to the current value - updating it just resets the same
clock. This repo already forbids hardcoded inventory counts in agent-facing
prose (CLAUDE.md, "This repo is public - confidentiality"). continuation-
contract.md now describes its applicability by what makes a file a member (any
SKILL.md/agent file that references this snippet's path - `grep` the plugin
tree for the literal path to enumerate the current set) instead of a count
that needs re-typing every time a skill or agent is added. The three IDE-
instruction snippets now point at their own "Generated Tool Surface" section /
`generator/server-surface.json` (mirroring the wording their own MCP-Resources
paragraph already used, for the identical reason) instead of restating a
surface size nothing regenerates.

--- What this guard checks -------------------------------------------------
Three narrow, high-precision patterns - deliberately NOT a blanket "any digit
next to an inventory noun" scan. A first draft tried exactly that (mirroring
test_readme_inventory_counts.py's noun list: skills/agents/commands/workflows)
and it fires on prose that is NOT this bug: `odoo-intake/SKILL.md`'s "these 4
skills" and `.../output-format-templates.md`'s "2 skills" (curated worked
examples, not plugin-total claims), `odoo-solution-design/SKILL.md`'s "four
tools" (a named subset), and three sites that restate the ALREADY-enumerated
"13 workflow `output_dir` trees" (`visual-evidence-lifecycle-contract.md`
names all 13 once; `state-root-resolution.md` and `workflow-chaining/SKILL.md`
cite that same enumeration rather than re-deriving it). None of those are the
escaping bug this guard exists to catch, and telling them apart from a genuine
drift-prone total by regex alone needs either an allowlist (rejected - see
"Definitional enum sizes" below) or a much heavier per-sentence enumeration-
adjacency parser that is out of proportion to the defect actually found. The
three patterns below are the subset of that wider scan that is BOTH
unambiguous (this exact phrasing has no other use anywhere in the scanned
corpus today - verified by sweep) and a complete fix for the defect actually
identified:

1. `\d+ SKILL\.md`               - a count of SKILL.md files.
2. `\d+ agent files?`            - a count of agent .md files.
3. `\d+ tools? *\+ *\d+ (MCP )?Resources?` - a combined tool+resource surface
   count (the exact shape the three IDE-instruction snippets used).

The bare "13 workflow `output_dir` trees" restatements in
`state-root-resolution.md` and `workflow-chaining/SKILL.md` are the same class
of finding, at lower risk (the full 13-name enumeration lives one file away,
in `visual-evidence-lifecycle-contract.md`) - recorded, not fixed here; this
guard's three patterns do not match that phrasing and a future commit should
decide whether to extend it.

--- Definitional enum sizes deliberately NOT matched (and why no allowlist) --
Nothing above matches "three-tier", "L0 | L1 | L2", "four discriminator-routed
supersets", or a curated example's "N skills"/"N tools". Those numbers count
members of a FIXED design (a tier scheme, a status enum, a named subset called
out in the same sentence) that does not grow when the plugin's skill/agent/
tool roster grows - there is no external SSOT (a directory, a JSON array) for
them to drift from, so restating them is not the bug. The three patterns above
instead key on phrasing that is unambiguous ONLY in inventory-counting contexts
in this corpus: the literal filename "SKILL.md", the literal phrase "agent
file(s)", and the literal "tools + ... Resources" surface-size shape. This is
a property of the SENTENCE's subject (a growable SSOT collection vs. a fixed
category scheme), not a per-file exemption list - so there is nothing to
allowlist; the distinction is baked into what each regex matches, not into a
set of files it skips.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGINS_DIR = REPO_ROOT / "plugins"

# Directories that hold agent-facing prose read by a skill/agent/hook AT
# RUNTIME - as opposed to docs/, CHANGELOG.md, README.md (human-facing; the
# README's own inventory counts are guarded separately by
# test_readme_inventory_counts.py, and docs/ is explicitly out of scope here -
# see the sibling test_persona_docs_consistency.py for why docs/personas/ gets
# its own, different guard instead of this one).
SCOPED_SUBDIRS = ("snippets", "skills", "agents", "commands", "workflows")

GENERATED_BLOCK_RE = re.compile(
    r"<!--\s*BEGIN GENERATED[^>]*-->.*?<!--\s*END GENERATED[^>]*-->",
    re.DOTALL,
)

PATTERNS = {
    "hardcoded SKILL.md file count": re.compile(r"\b\d+\s+SKILL\.md\b"),
    "hardcoded agent file count": re.compile(r"\b\d+\s+agent\s+files?\b", re.IGNORECASE),
    "hardcoded tool+resource surface count": re.compile(
        r"\b\d+\s+tools?\s*\+\s*\d+\s+(?:MCP\s+)?Resources?\b", re.IGNORECASE
    ),
}


def _scoped_files():
    """Every file under `plugins/<any>/{snippets,skills,agents,commands,workflows}/`
    - recursive, so `skills/<name>/references/*.md` and `agents/*.md` alike are
    covered, across odoo-ai-agents, git-toolkit, and odoo-semantic-mcp."""
    for plugin_dir in sorted(p for p in PLUGINS_DIR.iterdir() if p.is_dir()):
        for sub in SCOPED_SUBDIRS:
            base = plugin_dir / sub
            if not base.is_dir():
                continue
            for path in sorted(base.rglob("*")):
                if path.is_file() and path.suffix in (".md", ".yaml", ".yml"):
                    yield path


def _prose_outside_generated_markers(path: Path) -> str:
    """Strip `<!-- BEGIN GENERATED ... --> ... <!-- END GENERATED ... -->`
    regions before scanning - those are `make gen`-owned and derived fresh from
    `generator/server-surface.json` on every run; a count inside them cannot
    rot the way a hand-typed one can, and CLAUDE.md forbids hand-editing them
    regardless of what this guard finds."""
    text = path.read_text(encoding="utf-8")
    return GENERATED_BLOCK_RE.sub("", text)


def test_no_hardcoded_inventory_counts_in_agent_facing_prose():
    violations = []
    for path in _scoped_files():
        text = _prose_outside_generated_markers(path)
        for label, pattern in PATTERNS.items():
            for m in pattern.finditer(text):
                rel = path.relative_to(REPO_ROOT)
                line_no = text.count("\n", 0, m.start()) + 1
                violations.append(f"{rel}:{line_no}: {label} - '{m.group(0)}'")
    assert not violations, (
        "Hardcoded inventory count(s) found in agent-facing prose (outside any "
        "generated-content markers). These rot silently as the plugin's "
        "skill/agent/tool/resource roster grows, because nothing recomputes a "
        "hand-typed sentence. Remove the dependence on the literal number - "
        "state scope by what makes a file/entry a member (so a reader/agent "
        "can `grep` to enumerate it), or point at the file's own generated "
        "section / the SSOT JSON - instead of restating a count:\n"
        + "\n".join(violations)
    )
