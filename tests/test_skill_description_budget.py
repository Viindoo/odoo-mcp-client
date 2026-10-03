"""Guard: each plugin's share of Claude Code's skill listing stays inside its budget.

Every turn Claude Code shows the model ONE listing of every model-invocable skill and command:
its own bundled skills, every installed plugin's and the user's. The listing is capped at a
fraction of the context window; past the cap Claude Code keeps every NAME but drops the
descriptions of the least-used entries (bundled skills are never cut), so routing degrades for
everything installed alongside. The counting formula, Claude Code's defaults and the observed
cost of the bundled skills live in `scripts/lib/skill_listing.py` - the module setup step 35
uses to measure a real session - and this test counts with it, so the two cannot drift.

What the default budget can hold (observed, see BUNDLED_OBSERVED_CHARS/_CLI in that module): on
a 200k-token window the bundled skills plus the NAMES of this repo's entries already exceed the
default budget, so at the default Claude Code shows most plugin skills by name only.
`/odoo-ai-agents:odoo-setup` (step 35) measures the session and offers to raise
`skillListingBudgetFraction`; on large-context models the default budget holds everything.

The shares below are therefore sized for a raised budget: at RAISED_FRACTION on a 200k window,
the bundled skills plus every share must leave USER_SKILLS_ROOM_CHARS for the user's own and
third-party skills. RAISED_FRACTION and that room are design choices, not measurements.

Agents are not part of this listing (they are offered through the agent-launch tool).

An entry with ``disable-model-invocation: true`` is not listed at all, so it costs nothing - and
the model can no longer invoke it, which is why such an entry must never be something an
orchestrator skill or workflow calls (`test_hidden_entries_are_not_called_by_orchestrators`).

Descriptions are English only: users may write in any language, the model maps intent across
languages, and per-language trigger lists cost listing budget for every user.
"""
import json
import re
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
PLUGINS_DIR = ROOT / "plugins"
AGENTS_PLUGIN = PLUGINS_DIR / "odoo-ai-agents"
sys.path.insert(0, str(AGENTS_PLUGIN / "scripts" / "lib"))
import skill_listing as sl  # noqa: E402

DEFAULT_BUDGET_CHARS = sl.budget_chars(sl.DEFAULT_WINDOW_TOKENS, sl.DEFAULT_FRACTION)
# Anthropic's documented maximum length of a skill `description` field.
DESCRIPTION_FIELD_MAX = 1024

# Each plugin's share of the listing, in chars. Installing odoo-ai-agents also installs
# odoo-semantic-mcp and git-toolkit (its plugin.json dependencies), so every plugin in this repo
# has a share.
# - odoo-ai-agents: ~58 skills + commands; its names alone cost about a third of the share,
#   leaving room per entry for what the skill does plus a route-out where a neighbour is
#   confusable.
# - git-toolkit: one front-door skill covering casual git/GitHub phrasing, pasted PR/issue URLs and
#   deferral to a domain skill.
# - odoo-semantic-mcp: one setup command.
PLUGIN_LISTING_BUDGETS = {
    "odoo-ai-agents": 6_100,
    "git-toolkit": 400,
    "odoo-semantic-mcp": 200,
}
# Design choices (see the docstring): the raised fraction the shares are sized for, and the room
# it must still leave for the user's own and third-party skills (~30 skills of ~100 chars).
RAISED_FRACTION = 0.02
USER_SKILLS_ROOM_CHARS = 3_000
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
    return sl.listing_text({k: v for k, v in fm.items() if v is not None})


def _hidden(fm):
    return fm.get("disable-model-invocation") is True


def listing_entries(plugin):
    """(listed name, chars) per model-visible entry, counted with the runtime module."""
    prefix = _plugin_name(plugin)
    entries = []
    for path in _entry_files(plugin):
        fm = sl.parse_frontmatter(path.read_text(encoding="utf-8"))
        listed = f"{prefix}:{fm.get('name') or _entry_name(path)}"
        chars = sl.entry_chars(listed, fm)
        if chars is not None:
            entries.append((listed, chars))
    return entries


def listing_chars(plugin):
    return sl.listing_total(chars for _, chars in listing_entries(plugin))


@pytest.mark.parametrize("path", ALL_ENTRY_FILES, ids=lambda p: _entry_id(p))
def test_runtime_parser_reads_frontmatter_like_yaml(path):
    """The stdlib parser setup uses at runtime must read what a YAML parser reads, or the
    measurement it offers the user is wrong."""
    mine = sl.parse_frontmatter(path.read_text(encoding="utf-8"))
    ref = _frontmatter(path)
    assert sl.listing_text(mine) == _listing_text(ref)
    assert sl.is_hidden(mine) == _hidden(ref)
    assert (mine.get("name") or None) == (ref.get("name") or None)


def test_budgeted_plugins_are_every_plugin_in_the_repo():
    shipped = sorted(p.name for p in PLUGINS_DIR.iterdir() if (p / ".claude-plugin" / "plugin.json").is_file())
    assert shipped == sorted(PLUGIN_LISTING_BUDGETS), (
        f"every plugin in plugins/ needs a share of the skill listing: shipped {shipped}, "
        f"budgeted {sorted(PLUGIN_LISTING_BUDGETS)}"
    )


def test_shares_fit_a_raised_budget_with_room_for_user_skills():
    shares = sum(PLUGIN_LISTING_BUDGETS.values()) + len(PLUGIN_LISTING_BUDGETS) - 1
    raised = sl.budget_chars(sl.DEFAULT_WINDOW_TOKENS, RAISED_FRACTION)
    room = raised - sl.BUNDLED_OBSERVED_CHARS - shares - 1
    assert room >= USER_SKILLS_ROOM_CHARS, (
        f"at skillListingBudgetFraction={RAISED_FRACTION} on a {sl.DEFAULT_WINDOW_TOKENS}-token "
        f"window the listing holds {raised} chars; Claude Code's bundled skills take "
        f"{sl.BUNDLED_OBSERVED_CHARS} (observed on CLI {sl.BUNDLED_OBSERVED_CLI}) and this repo's "
        f"shares {shares}, leaving {room} for the user's own skills - less than "
        f"{USER_SKILLS_ROOM_CHARS}. Shrink a share by tightening descriptions."
    )


def test_entries_discovered():
    # Floors below the real counts so a dropped directory or a broken glob trips CI, while adding
    # entries never does.
    assert len(_skill_files(AGENTS_PLUGIN)) >= 41
    assert len(_entry_files(AGENTS_PLUGIN)) - len(_skill_files(AGENTS_PLUGIN)) >= 5
    assert len(_skill_files(PLUGINS_DIR / "git-toolkit")) >= 1
    assert len(_entry_files(PLUGINS_DIR / "odoo-semantic-mcp")) >= 1


@pytest.mark.parametrize("plugin", BUDGETED_PLUGINS, ids=lambda p: p.name)
def test_listing_fits_the_plugin_budget(plugin):
    budget = PLUGIN_LISTING_BUDGETS[plugin.name]
    total = listing_chars(plugin)
    biggest = ", ".join(
        f"{n}={c}" for n, c in sorted(listing_entries(plugin), key=lambda e: -e[1])[:8]
    )
    assert total <= budget, (
        f"{plugin.name} adds {total} chars to the skill listing, over its {budget}-char share. "
        f"Every turn the model sees one listing for all installed skills, capped at "
        f"{DEFAULT_BUDGET_CHARS} chars by default on a 200k window; over the cap Claude Code drops the "
        f"descriptions of the least-used skills, this plugin's and everyone else's. Shorten "
        f"descriptions by meaning: what the skill does, its core trigger, and a route-out only "
        f"where a neighbour is confusable; English only, no paraphrase lists or examples. Do "
        f"not raise the share. Largest entries: {biggest}"
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
