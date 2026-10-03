"""Guard: each plugin's share of Claude Code's skill listing stays inside its budget.

Every turn Claude Code shows the model one line per model-invocable skill or command:
``- <plugin>:<name>: <description>[ - <when_to_use>]``. The whole listing - shared by every
installed plugin and the user's own skills - is capped at a fraction of the context window; past
the cap the harness keeps every NAME but drops the descriptions of the least-used entries, so
routing degrades for everything installed alongside. A per-skill cap cannot prevent that: 59
entries that were each "short enough" still overflowed the listing several times over.

The counting below mirrors Claude Code's listing builder (read from the shipped CLI, v2.1.x):

  budget      = floor(context_window_tokens * 4 chars/token * skillListingBudgetFraction)
              = 200_000 * 4 * 0.01 = 8_000 chars for the default fraction on a 200k window
  entry chars = len("<plugin>:<name>") + 4 + min(len(text), 1536)
                where text = description, or "description - when_to_use" when both exist
  listing     = sum(entry chars) + one newline between consecutive entries

Agents are not part of this listing (they are offered through the agent-launch tool), so agent
descriptions are not counted here.

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
PLUGINS_DIR = ROOT / "plugins"
AGENTS_PLUGIN = PLUGINS_DIR / "odoo-ai-agents"

# Claude Code defaults (see module docstring): 1% of a 200k-token window at 4 chars/token.
CONTEXT_WINDOW_TOKENS = 200_000
CHARS_PER_TOKEN = 4
LISTING_BUDGET_FRACTION = 0.01
LISTING_BUDGET_CHARS = int(CONTEXT_WINDOW_TOKENS * CHARS_PER_TOKEN * LISTING_BUDGET_FRACTION)
# Claude Code's per-entry cap on description + when_to_use (`skillListingMaxDescChars` default).
PER_ENTRY_TEXT_CAP = 1536
# Anthropic's documented maximum length of a skill `description` field.
DESCRIPTION_FIELD_MAX = 1024

# Each plugin's share of the listing, in chars. odoo-ai-agents ships ~58 entries and may use the
# whole default budget on its own; git-toolkit ships one front-door skill whose description must
# cover casual git/GitHub phrasing, pasted PR/issue URLs and deferral to a domain front door - 400
# chars is that one entry plus headroom, and keeps the toolkit cheap for users who install it
# beside other plugins.
PLUGIN_LISTING_BUDGETS = {
    "odoo-ai-agents": LISTING_BUDGET_CHARS,
    "git-toolkit": 400,
}
BUDGETED_PLUGINS = [PLUGINS_DIR / name for name in PLUGIN_LISTING_BUDGETS]

# The skills and workflows that invoke other entries through the Skill tool. Anything they name
# must stay model-invocable.
ORCHESTRATOR_SOURCES = (
    sorted((AGENTS_PLUGIN / "skills" / "odoo-intake").rglob("*.md"))
    + sorted((AGENTS_PLUGIN / "skills" / "run-harness").rglob("*.md"))
    + sorted((AGENTS_PLUGIN / "skills" / "workflow-chaining").rglob("*.md"))
    + sorted((AGENTS_PLUGIN / "workflows").glob("*.yaml"))
)


def _skill_files(plugin):
    return sorted((plugin / "skills").glob("*/SKILL.md"))


def _entry_files(plugin):
    return _skill_files(plugin) + sorted((plugin / "commands").glob("*.md"))


def _plugin_name(plugin):
    return json.loads((plugin / ".claude-plugin" / "plugin.json").read_text())["name"]


ALL_ENTRY_FILES = [path for plugin in BUDGETED_PLUGINS for path in _entry_files(plugin)]
ALL_SKILL_FILES = [path for plugin in BUDGETED_PLUGINS for path in _skill_files(plugin)]


def _frontmatter(path):
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert m, f"{path}: no YAML frontmatter"
    return yaml.safe_load(m.group(1))


def _entry_name(path):
    return path.parent.name if path.name == "SKILL.md" else path.stem


def _entry_id(path):
    return f"{path.relative_to(PLUGINS_DIR).parts[0]}:{_entry_name(path)}"


def _listing_text(fm):
    desc = str(fm.get("description") or "").strip()
    when = str(fm.get("when_to_use") or "").strip()
    return f"{desc} - {when}" if when else desc


def _hidden(fm):
    return fm.get("disable-model-invocation") is True


def listing_entries(plugin):
    """(listed name, chars this entry adds to the listing) for every model-visible entry."""
    prefix = _plugin_name(plugin)
    entries = []
    for path in _entry_files(plugin):
        fm = _frontmatter(path)
        if _hidden(fm):
            continue
        listed = f"{prefix}:{fm.get('name') or _entry_name(path)}"
        text = _listing_text(fm)
        entries.append((listed, len(listed) + 4 + min(len(text), PER_ENTRY_TEXT_CAP)))
    return entries


def listing_chars(plugin):
    entries = listing_entries(plugin)
    return sum(chars for _, chars in entries) + max(0, len(entries) - 1)


def test_entries_discovered():
    # Floors below the real counts so a dropped directory or a broken glob trips CI, while adding
    # entries never does.
    assert len(_skill_files(AGENTS_PLUGIN)) >= 41
    assert len(_entry_files(AGENTS_PLUGIN)) - len(_skill_files(AGENTS_PLUGIN)) >= 5
    assert len(_skill_files(PLUGINS_DIR / "git-toolkit")) >= 1


@pytest.mark.parametrize("plugin", BUDGETED_PLUGINS, ids=lambda p: p.name)
def test_listing_fits_the_plugin_budget(plugin):
    budget = PLUGIN_LISTING_BUDGETS[plugin.name]
    total = listing_chars(plugin)
    biggest = ", ".join(
        f"{n}={c}" for n, c in sorted(listing_entries(plugin), key=lambda e: -e[1])[:8]
    )
    assert total <= budget, (
        f"{plugin.name} adds {total} chars to the skill listing; its budget is {budget} (Claude "
        f"Code's default for the WHOLE listing on a 200k window is {LISTING_BUDGET_CHARS}). Over "
        f"the shared cap, descriptions of other skills (this plugin's, other plugins', the "
        f"user's) are dropped to name-only. Shorten descriptions by meaning "
        f"(docs/authoring-skills-and-agents.md) - do not raise the budget. "
        f"Largest entries: {biggest}"
    )


@pytest.mark.parametrize("path", ALL_ENTRY_FILES, ids=_entry_id)
def test_description_is_english_ascii(path):
    text = _listing_text(_frontmatter(path))
    assert text, f"{_entry_id(path)}: empty description"
    foreign = sorted({ch for ch in text if ord(ch) > 127})
    assert not foreign, (
        f"{_entry_id(path)}: description must be English-only ASCII; found {foreign}. "
        f"Trigger phrases in other languages are not needed - the model maps intent across "
        f"languages - and every one of them costs listing budget for every user."
    )


@pytest.mark.parametrize("path", ALL_SKILL_FILES, ids=_entry_id)
def test_description_under_field_max(path):
    n = len(str(_frontmatter(path).get("description") or "").strip())
    assert n <= DESCRIPTION_FIELD_MAX, (
        f"{_entry_id(path)}: description is {n} chars, over the {DESCRIPTION_FIELD_MAX}-char "
        f"field maximum"
    )


def test_hidden_entries_are_not_called_by_orchestrators():
    hidden = [_entry_name(p) for p in ALL_ENTRY_FILES if _hidden(_frontmatter(p))]
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
