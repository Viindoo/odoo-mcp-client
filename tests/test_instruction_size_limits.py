"""Size guard: an instruction file must stay inside what Claude Code actually delivers of it.

Claude Code keeps only part of a long instruction file, silently, so a rule written past the
cut is a rule the model never sees. The limits below are the measured behaviours (Claude Code
2.1.316, docs and the installed binary):

- a SKILL.md or command body keeps only its first ~5,000 tokens after a context compaction
  (about 16,000 bytes of this repo's prose);
- the Read tool refuses a file over 25,000 tokens (about 50,000 bytes), so a reference, snippet
  or doc file that large cannot be read at all, and an agent file that large is not usable as a
  system prompt (30,000 bytes);
- a skill description is cut at 1,536 characters in the listing, `when_to_use` included.

`PENDING` lists the files that are allowed to exceed a limit for now; a file leaves the set the
moment it fits, and a file in the set that already fits fails the guard, so the set only shrinks.

Run with: python3 -m pytest tests/test_instruction_size_limits.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGINS = ROOT / "plugins"
sys.path.insert(0, str(PLUGINS / "odoo-ai-agents" / "scripts" / "lib"))
import skill_listing as sl  # noqa: E402

ENTRY_LIMIT = 16_000
SUPPORT_LIMIT = 50_000
AGENT_LIMIT = 30_000
DESCRIPTION_LIMIT = 1_536

ENTRY_WHY = "Claude Code keeps only the first ~5,000 tokens of a skill or command body after a compaction"
SUPPORT_WHY = "the Read tool refuses a file over 25,000 tokens"
AGENT_WHY = "an agent file over this size cannot be read whole by the Read tool and bloats its system prompt"
DESCRIPTION_WHY = "Claude Code cuts a skill description plus when_to_use at 1,536 characters in the listing"

# Files allowed to exceed their limit for now (paths relative to plugins/odoo-ai-agents/). Each is
# being compacted; the caller empties this set as they shrink.
PENDING: set[str] = set()


def _rel(path: Path) -> str:
    """The path relative to the odoo-ai-agents plugin (the PENDING key), else to plugins/."""
    base = PLUGINS / "odoo-ai-agents"
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.relative_to(PLUGINS).as_posix()


def _entry_files() -> list[Path]:
    return sorted(PLUGINS.glob("*/skills/*/SKILL.md")) + sorted(PLUGINS.glob("*/commands/*.md"))


def _support_files() -> list[Path]:
    found: set[Path] = set()
    for pattern in ("*/skills/**/references/**/*.md", "*/skills/**/reference/**/*.md",
                    "*/snippets/**/*.md", "*/docs/**/*.md"):
        found.update(PLUGINS.glob(pattern))
    return sorted(found)


def _agent_files() -> list[Path]:
    return sorted(PLUGINS.glob("*/agents/*.md"))


def _bytes(path: Path) -> int:
    return len(path.read_bytes())


def _over(files: list[Path], limit: int) -> list[Path]:
    return [p for p in files if _bytes(p) > limit]


def _check(files: list[Path], limit: int, why: str) -> None:
    offenders = [p for p in _over(files, limit) if _rel(p) not in PENDING]
    assert not offenders, "\n".join(
        f"{_rel(p)} is {_bytes(p)} bytes, over the {limit}-byte limit: {why}." for p in offenders)


def test_skill_and_command_bodies_fit_what_survives_a_compaction():
    _check(_entry_files(), ENTRY_LIMIT, ENTRY_WHY)


def test_reference_snippet_and_doc_files_fit_one_read():
    _check(_support_files(), SUPPORT_LIMIT, SUPPORT_WHY)


def test_agent_files_fit_the_agent_limit():
    _check(_agent_files(), AGENT_LIMIT, AGENT_WHY)


def _listing_chars(path: Path) -> int:
    fm = sl.parse_frontmatter(path.read_text(encoding="utf-8"))
    desc = str(fm.get("description", ""))
    when = str(fm.get("when_to_use", ""))
    return len(desc) + (3 + len(when) if when else 0)


def test_skill_and_command_descriptions_fit_the_listing_cut():
    offenders = [p for p in _entry_files() if _listing_chars(p) > DESCRIPTION_LIMIT]
    assert not offenders, "\n".join(
        f"{_rel(p)} has description + when_to_use of {_listing_chars(p)} characters, over the "
        f"{DESCRIPTION_LIMIT}-character limit: {DESCRIPTION_WHY}." for p in offenders)


def test_a_pending_file_that_already_fits_leaves_the_set():
    limits = {}
    for p in _entry_files():
        limits[_rel(p)] = ENTRY_LIMIT
    for p in _support_files():
        limits[_rel(p)] = SUPPORT_LIMIT
    for p in _agent_files():
        limits[_rel(p)] = AGENT_LIMIT
    stale = []
    for rel in sorted(PENDING):
        path = PLUGINS / "odoo-ai-agents" / rel
        if not path.is_file():
            stale.append(f"{rel} does not exist; remove it from PENDING.")
        elif rel not in limits:
            stale.append(f"{rel} is not covered by any size limit; remove it from PENDING.")
        elif _bytes(path) <= limits[rel]:
            stale.append(f"{rel} is {_bytes(path)} bytes, within its {limits[rel]}-byte limit; "
                         "remove it from PENDING.")
    assert not stale, "\n".join(stale)
