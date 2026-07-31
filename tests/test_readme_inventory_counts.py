"""README inventory-count guard - every headline number is COMPUTED, never hardcoded.

This closes the count-drift CLASS, not just one instance of it. In this PR alone, count
drift has now been hand-fixed four separate times (a topology value twice, the
forward-port phase set once, and the skill count once) and each time a fresh drift
surfaced somewhere else - because nothing compared the README's stated numbers against
the filesystem they claim to describe. `### Skills (53)` vs the plugin's actual 52
skill directories (`skills/_shared/` has no `SKILL.md` - it is a shared resource
library, not a skill) is the fifth instance: the top-of-file blurb and the `Skills`
table itself both agreed on 52, but the section header said 53.

Every expected value below is derived at test time from `plugins/odoo-ai-agents/`
(directory globs) or, where no independent on-disk registry exists, from the README's
own enumerating table (see the persona-count docstring) - never from a number typed
into this file. A hardcoded expectation would just move the drift source here.

Scope of this guard - deliberately stated, per the lesson of `test_readme_phase_parity.py`
(a topology guard later found scoped to only two of three pipelines): this file covers
every TOP-LEVEL PLUGIN INVENTORY count the README states as a number - skills, agents,
commands, declarative workflows, and persona buckets. That is the full set of inventory
counts found by an explicit audit of README.md (grep for "<number> <inventory-noun>"
across skills/agents/commands/workflows/snippets/hooks/scripts/docs/personas/tools) -
snippets, hooks, scripts, docs, and tools carry NO numeric count claim in README.md today,
so there is nothing to guard for them; the moment one is added, extend this file.

Explicitly OUT of scope, by design, not by oversight:
- Per-pipeline PHASE counts ("13-phase", "8-phase" for forward-port / git-rebase /
  modules-upgrade) are a structurally different SSOT (the phase anchors each pipeline's
  own SKILL.md declares) already guarded by `test_readme_phase_parity.py`. That guard's
  known gap (git-rebase is not in its PIPELINE_CASES) is a separate, already-recorded
  finding - fixing it is a different change than this one.
- The "11 principles" count in `ODOO-AI-ETHOS.md` / its README mention is about that
  file's own content structure, not this plugin's skill/agent/command/workflow/persona
  inventory - out of this guard's stated scope.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN = REPO_ROOT / "plugins" / "odoo-ai-agents"
README = PLUGIN / "README.md"


def _readme_text() -> str:
    return README.read_text(encoding="utf-8")


def _real_skill_count() -> int:
    """A skill is a directory with its own SKILL.md. `skills/_shared/` deliberately has
    none (it holds shared coding-guideline / module-graph resources, not a skill)."""
    return len(list(PLUGIN.glob("skills/*/SKILL.md")))


def _real_agent_count() -> int:
    return len(list(PLUGIN.glob("agents/*.md")))


def _real_command_count() -> int:
    return len(list(PLUGIN.glob("commands/*.md")))


def _real_workflow_count() -> int:
    return len(list(PLUGIN.glob("workflows/*.workflow.yaml")))


def _flattened_prose(text: str) -> str:
    """Collapse markdown line-wrapping and '> ' blockquote continuation into a single
    logical line per sentence, so a "**52 skills**" claim that wraps across a
    blockquote line boundary (as the top-of-file blurb does) is not missed by a
    single-line-anchored regex."""
    delined = "\n".join(re.sub(r"^>\s?", "", line) for line in text.split("\n"))
    return re.sub(r"\s+", " ", delined)


def _section(text: str, heading_regex: str) -> str:
    """Return the README slice from a heading matching `heading_regex` up to the next
    heading of the same or shallower level (##/###)."""
    m = re.search(rf"^(#{{2,3}})\s+{heading_regex}\s*$", text, re.MULTILINE)
    assert m, f"README.md has no heading matching /{heading_regex}/"
    level = len(m.group(1))
    tail = text[m.end():]
    next_heading = re.search(rf"^#{{1,{level}}}\s", tail, re.MULTILINE)
    end = m.end() + (next_heading.start() if next_heading else len(tail))
    return text[m.start():end]


def _first_table_row_count(section_text: str) -> int:
    """Count the data rows (excluding header + separator) of the first contiguous
    markdown table in `section_text`."""
    table_lines = []
    started = False
    for line in section_text.split("\n"):
        stripped = line.strip()
        is_row = stripped.startswith("|") and stripped.endswith("|") and len(stripped) > 1
        if is_row:
            table_lines.append(line)
            started = True
        elif started:
            break
    assert len(table_lines) >= 2, (
        f"expected a markdown table (header + separator + rows) in section:\n{section_text[:200]}"
    )
    return len(table_lines) - 2


def _prose_claims(flat_text: str, noun_pattern: str) -> list[int]:
    """Every '<number> <noun>' claim in the flattened prose, as ints, in document order."""
    return [int(n) for n in re.findall(rf"\b(\d+)\s+{noun_pattern}\b", flat_text)]


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------

def test_skill_count_prose_matches_filesystem():
    real = _real_skill_count()
    flat = _flattened_prose(_readme_text())
    claims = _prose_claims(flat, "skills")
    bad = [c for c in claims if c != real]
    assert not bad, (
        f"README.md prose claims {sorted(set(bad))} skill(s) but "
        f"plugins/odoo-ai-agents/skills/*/SKILL.md counts {real}. "
        f"Fix the README prose to say '{real} skills' (or investigate why a skill "
        f"directory is missing/extra a SKILL.md if {real} looks wrong)."
    )


def test_skill_section_header_matches_filesystem():
    real = _real_skill_count()
    m = re.search(r"^### Skills \((\d+)\)\s*$", _readme_text(), re.MULTILINE)
    assert m, "README.md has no '### Skills (N)' section header"
    claimed = int(m.group(1))
    assert claimed == real, (
        f"README.md '### Skills ({claimed})' header claims {claimed} skills but "
        f"plugins/odoo-ai-agents/skills/*/SKILL.md counts {real}. "
        f"Fix the header to read '### Skills ({real})'."
    )


def test_skill_table_row_count_matches_filesystem():
    real = _real_skill_count()
    section = _section(_readme_text(), r"Skills \(\d+\)")
    rows = _first_table_row_count(section)
    assert rows == real, (
        f"README.md '### Skills' table has {rows} data row(s) but "
        f"plugins/odoo-ai-agents/skills/*/SKILL.md counts {real}. "
        f"A skill is either missing from the table or listed without a matching "
        f"skills/<name>/SKILL.md directory."
    )


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------

def test_agent_count_prose_matches_filesystem():
    real = _real_agent_count()
    flat = _flattened_prose(_readme_text())
    claims = _prose_claims(flat, "agents")
    bad = [c for c in claims if c != real]
    assert not bad, (
        f"README.md prose claims {sorted(set(bad))} agent(s) but "
        f"plugins/odoo-ai-agents/agents/*.md counts {real}. "
        f"Fix the README prose to say '{real} agents'."
    )


def test_agent_section_header_matches_filesystem():
    real = _real_agent_count()
    m = re.search(r"^### Agents \((\d+)\)\s*$", _readme_text(), re.MULTILINE)
    assert m, "README.md has no '### Agents (N)' section header"
    claimed = int(m.group(1))
    assert claimed == real, (
        f"README.md '### Agents ({claimed})' header claims {claimed} agents but "
        f"plugins/odoo-ai-agents/agents/*.md counts {real}. "
        f"Fix the header to read '### Agents ({real})'."
    )


def test_agent_table_row_count_matches_filesystem():
    real = _real_agent_count()
    section = _section(_readme_text(), r"Agents \(\d+\)")
    rows = _first_table_row_count(section)
    assert rows == real, (
        f"README.md '### Agents' table has {rows} data row(s) but "
        f"plugins/odoo-ai-agents/agents/*.md counts {real}. "
        f"An agent is either missing from the table or listed without a matching "
        f"agents/<name>.md file."
    )


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def test_command_count_prose_matches_filesystem():
    real = _real_command_count()
    flat = _flattened_prose(_readme_text())
    claims = _prose_claims(flat, "commands")
    bad = [c for c in claims if c != real]
    assert not bad, (
        f"README.md prose claims {sorted(set(bad))} command(s) but "
        f"plugins/odoo-ai-agents/commands/*.md counts {real}. "
        f"Fix the README prose to say '{real} commands'. (Note: "
        f"/odoo-semantic-mcp:connect belongs to the sibling odoo-semantic-mcp plugin "
        f"and is correctly excluded from this count.)"
    )


def test_command_table_row_count_matches_filesystem():
    real = _real_command_count()
    section = _section(_readme_text(), r"Available commands")
    rows = _first_table_row_count(section)
    assert rows == real, (
        f"README.md '### Available commands' table has {rows} data row(s) but "
        f"plugins/odoo-ai-agents/commands/*.md counts {real}. "
        f"A command is either missing from the table or listed without a matching "
        f"commands/<name>.md file."
    )


# ---------------------------------------------------------------------------
# Workflows
# ---------------------------------------------------------------------------

def test_workflow_count_prose_matches_filesystem():
    real = _real_workflow_count()
    flat = _flattened_prose(_readme_text())
    claims = _prose_claims(flat, "declarative workflows")
    bad = [c for c in claims if c != real]
    assert not bad, (
        f"README.md prose claims {sorted(set(bad))} declarative workflow(s) but "
        f"plugins/odoo-ai-agents/workflows/*.workflow.yaml counts {real}. "
        f"Fix the README prose to say '{real} declarative workflows'."
    )


# ---------------------------------------------------------------------------
# Persona buckets
# ---------------------------------------------------------------------------

def test_persona_count_prose_matches_who_is_it_for_table():
    """There is no independent on-disk persona registry: the 'Who is it for' table
    IS the enumeration of persona buckets (the Domain column cross-references the
    workflows/_schema.md domain enum, but several personas intentionally share one
    domain value - e.g. Engineer/Coder/Code-Reviewer all map to `engineering` - so
    the enum's size is not the persona count). The mechanical check available here
    is self-consistency: every '<N> persona bucket(s)' prose claim must match the
    row count of the table that defines the buckets, computed fresh each run."""
    text = _readme_text()
    section = _section(text, r"Who is it for")
    real = _first_table_row_count(section)

    flat = _flattened_prose(text)
    claims = _prose_claims(flat, "persona bucket(?:s)?")
    bad = [c for c in claims if c != real]
    assert not bad, (
        f"README.md prose claims {sorted(set(bad))} persona bucket(s) but the "
        f"'## Who is it for' table has {real} data row(s). "
        f"Fix the README prose to say '{real} persona buckets', or fix the table "
        f"if a persona row is missing/extra."
    )
