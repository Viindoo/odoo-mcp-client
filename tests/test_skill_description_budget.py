"""Guard: the plugin's share of Claude Code's skill listing stays inside the listing budget.

Every turn Claude Code shows the model one line per model-invocable skill or command:
``- <plugin>:<name>: <description>[ - <when_to_use>]``. The whole listing is capped at a fraction
of the context window; past the cap the harness keeps every NAME but drops the descriptions of
the least-used entries - this plugin's, other plugins', and the user's own - so routing degrades
for everything installed alongside. A per-skill cap cannot prevent that: 59 entries that are each
"short enough" still overflowed the listing several times over.

The counting below mirrors Claude Code's listing builder (read from the shipped CLI, v2.1.x):

  budget      = floor(context_window_tokens * 4 chars/token * skillListingBudgetFraction)
              = 200_000 * 4 * 0.01 = 8_000 chars for the default fraction on a 200k window
  entry chars = len("<plugin>:<name>") + 4 + min(len(text), 1536)
                where text = description, or "description - when_to_use" when both exist
  listing     = sum(entry chars) + one newline between consecutive entries

An entry with ``disable-model-invocation: true`` is not listed at all, so it costs nothing - and
the model can no longer invoke it, which is why such an entry must never be something an
orchestrator skill or workflow calls (`test_hidden_entries_are_not_called_by_orchestrators`).

Descriptions are English only: users may write in any language, the model maps intent across
languages, and per-language trigger lists cost listing budget for every user.
"""
import json
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
SKILL_FILES = sorted((PLUGIN / "skills").glob("*/SKILL.md"))
COMMAND_FILES = sorted((PLUGIN / "commands").glob("*.md"))
ENTRY_FILES = SKILL_FILES + COMMAND_FILES
PLUGIN_NAME = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())["name"]

# Claude Code defaults (see module docstring): 1% of a 200k-token window at 4 chars/token.
CONTEXT_WINDOW_TOKENS = 200_000
CHARS_PER_TOKEN = 4
LISTING_BUDGET_FRACTION = 0.01
LISTING_BUDGET_CHARS = int(CONTEXT_WINDOW_TOKENS * CHARS_PER_TOKEN * LISTING_BUDGET_FRACTION)
# Claude Code's per-entry cap on description + when_to_use (`skillListingMaxDescChars` default).
PER_ENTRY_TEXT_CAP = 1536
# Anthropic's documented maximum length of a skill `description` field.
DESCRIPTION_FIELD_MAX = 1024

# The skills and workflows that invoke other entries through the Skill tool. Anything they name
# must stay model-invocable.
ORCHESTRATOR_SOURCES = (
    sorted((PLUGIN / "skills" / "odoo-intake").rglob("*.md"))
    + sorted((PLUGIN / "skills" / "run-harness").rglob("*.md"))
    + sorted((PLUGIN / "skills" / "workflow-chaining").rglob("*.md"))
    + sorted((PLUGIN / "workflows").glob("*.yaml"))
)


def _frontmatter(path):
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert m, f"{path}: no YAML frontmatter"
    return yaml.safe_load(m.group(1))


def _entry_name(path):
    return path.parent.name if path.name == "SKILL.md" else path.stem


def _listing_text(fm):
    desc = str(fm.get("description") or "").strip()
    when = str(fm.get("when_to_use") or "").strip()
    return f"{desc} - {when}" if when else desc


def _hidden(fm):
    return fm.get("disable-model-invocation") is True


def _listing_entries():
    """(listed name, chars this entry adds to the listing) for every model-visible entry."""
    entries = []
    for path in ENTRY_FILES:
        fm = _frontmatter(path)
        if _hidden(fm):
            continue
        listed = f"{PLUGIN_NAME}:{fm.get('name') or _entry_name(path)}"
        text = _listing_text(fm)
        entries.append((listed, len(listed) + 4 + min(len(text), PER_ENTRY_TEXT_CAP)))
    return entries


def test_entries_discovered():
    # Floor below the real counts so a dropped directory or a broken glob trips CI, while adding
    # entries never does.
    assert len(SKILL_FILES) >= 41, f"expected >=41 skills, found {len(SKILL_FILES)}"
    assert len(COMMAND_FILES) >= 5, f"expected >=5 commands, found {len(COMMAND_FILES)}"


def test_listing_fits_the_default_budget():
    entries = _listing_entries()
    total = sum(chars for _, chars in entries) + max(0, len(entries) - 1)
    biggest = ", ".join(f"{n}={c}" for n, c in sorted(entries, key=lambda e: -e[1])[:8])
    assert total <= LISTING_BUDGET_CHARS, (
        f"{PLUGIN_NAME} adds {total} chars to the skill listing; Claude Code's default budget for a "
        f"200k window is {LISTING_BUDGET_CHARS}. Over it, descriptions of other skills (this "
        f"plugin's, other plugins', the user's) are dropped to name-only. Shorten descriptions by "
        f"meaning (docs/authoring-skills-and-agents.md) - do not raise this budget. "
        f"Largest entries: {biggest}"
    )


@pytest.mark.parametrize("path", ENTRY_FILES, ids=_entry_name)
def test_description_is_english_ascii(path):
    text = _listing_text(_frontmatter(path))
    assert text, f"{_entry_name(path)}: empty description"
    foreign = sorted({ch for ch in text if ord(ch) > 127})
    assert not foreign, (
        f"{_entry_name(path)}: description must be English-only ASCII; found {foreign}. "
        f"Trigger phrases in other languages are not needed - the model maps intent across "
        f"languages - and every one of them costs listing budget for every user."
    )


@pytest.mark.parametrize("path", SKILL_FILES, ids=_entry_name)
def test_description_under_field_max(path):
    n = len(str(_frontmatter(path).get("description") or "").strip())
    assert n <= DESCRIPTION_FIELD_MAX, (
        f"{_entry_name(path)}: description is {n} chars, over the {DESCRIPTION_FIELD_MAX}-char "
        f"field maximum"
    )


def test_hidden_entries_are_not_called_by_orchestrators():
    hidden = [_entry_name(p) for p in ENTRY_FILES if _hidden(_frontmatter(p))]
    callers = {}
    for name in hidden:
        token = re.compile(rf"(?<![\w-]){re.escape(name)}(?![\w-])")
        hits = [
            str(src.relative_to(ROOT))
            for src in ORCHESTRATOR_SOURCES
            if token.search(src.read_text(encoding="utf-8"))
        ]
        if hits:
            callers[name] = hits
    assert not callers, (
        "these entries set disable-model-invocation: true, so the model cannot invoke them, yet an "
        f"orchestrator skill or workflow routes to them: {callers}. Make them model-invocable "
        f"again, or route the orchestrator to the entry that stays visible."
    )
