"""Size guard: an instruction file must stay inside what Claude Code actually delivers of it.

Claude Code keeps only part of a long instruction file, silently, so a rule written past the
cut is a rule the model never sees. The limits below are the measured behaviours (Claude Code
2.1.316, docs and the installed binary):

- a SKILL.md or command body keeps only its first ~5,000 tokens after a context compaction
  (about 16,000 bytes of this repo's prose);
- the Read tool refuses a file over 25,000 tokens (about 50,000 bytes), so a reference, snippet
  or doc file that large cannot be read at all;
- an agent body (the text after the frontmatter) is its system prompt: it stays within
  AGENT_BODY_MAX_LINES lines and AGENT_BODY_MAX_BYTES bytes (generator/check_orchestration.py);
  a dimension over its limit is recorded in tests/fixtures/agent_body_budget.json and that figure
  only goes down;
- a skill description is cut at 1,536 characters in the listing, `when_to_use` included.

`PENDING` lists the skill, command, reference and snippet files that may exceed a limit for now; a file leaves the set the
moment it fits, and a file in the set that already fits fails the guard, so the set only shrinks.

Run with: python3 -m pytest tests/test_instruction_size_limits.py -v
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGINS = ROOT / "plugins"
sys.path.insert(0, str(PLUGINS / "odoo-ai-agents" / "scripts" / "lib"))
import skill_listing as sl  # noqa: E402

sys.path.insert(0, str(PLUGINS / "odoo-ai-agents"))
from generator import check_orchestration as co  # noqa: E402

ENTRY_LIMIT = 16_000
SUPPORT_LIMIT = 50_000
DESCRIPTION_LIMIT = 1_536

ENTRY_WHY = "Claude Code keeps only the first ~5,000 tokens of a skill or command body after a compaction"
SUPPORT_WHY = "the Read tool refuses a file over 25,000 tokens"
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


def test_agent_bodies_fit_their_limits_or_are_recorded_and_shrinking():
    figures = co.agent_body_figures(_agent_files(), ROOT)
    record = co._load_agent_body_record(co.AGENT_BODY_RECORD_FILE)
    assert co.agent_body_findings(figures, record) == []


REL = "plugins/p/agents/a.md"
MAX_L, MAX_B = co.AGENT_BODY_MAX_LINES, co.AGENT_BODY_MAX_BYTES


def _findings(lines: int, size: int, record: dict | None = None) -> list[str]:
    return co.agent_body_findings({REL: (lines, size)}, {REL: record} if record else {})


def test_an_unrecorded_agent_over_the_line_limit_is_flagged():
    assert _findings(MAX_L + 1, 1000)


def test_an_unrecorded_agent_with_few_long_lines_is_flagged_by_the_byte_ceiling():
    assert _findings(100, MAX_B + 1)


def test_an_unrecorded_agent_within_both_limits_is_clean():
    assert _findings(MAX_L, MAX_B) == []


def test_a_recorded_figure_that_grew_is_flagged():
    assert _findings(MAX_L + 51, 5000, {"lines": MAX_L + 50})
    assert _findings(100, MAX_B + 51, {"bytes": MAX_B + 50})


def test_a_recorded_figure_above_the_real_size_is_flagged_as_slack():
    assert _findings(MAX_L + 49, 5000, {"lines": MAX_L + 50})


def test_a_recorded_agent_equal_to_its_record_is_clean():
    assert _findings(MAX_L + 50, MAX_B + 50, {"lines": MAX_L + 50, "bytes": MAX_B + 50}) == []


def test_a_recorded_agent_that_now_fits_must_leave_the_record():
    assert _findings(100, 5000, {"bytes": MAX_B + 50})


def test_a_dimension_within_its_limit_moves_freely_while_the_other_is_ratcheted():
    record = {"bytes": MAX_B + 2000}
    assert _findings(113, MAX_B + 1500, {**record, "bytes": MAX_B + 1500}) == []
    assert _findings(MAX_L - 1, MAX_B + 1500, {"bytes": MAX_B + 1500}) == []
    assert _findings(MAX_L + 1, MAX_B + 1500, {"bytes": MAX_B + 1500})


def test_a_recorded_dimension_that_now_fits_is_flagged_while_the_other_stays_recorded():
    assert _findings(100, MAX_B + 10, {"lines": MAX_L + 5, "bytes": MAX_B + 10})


def _write_agent(tmp_path, body_lines: int, line: str = "word\n") -> Path:
    path = tmp_path / "plugins" / "p" / "agents" / "a.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("---\nname: a\ndescription: d\n---\n" + line * body_lines, encoding="utf-8")
    return path


def test_the_body_is_measured_after_the_frontmatter(tmp_path):
    path = _write_agent(tmp_path, 7)
    assert co.agent_body_figures([path], tmp_path) == {REL: (7, 7 * 5)}


def test_sync_lowers_the_record_drops_a_fitting_agent_and_never_raises(tmp_path):
    over = MAX_L + 30
    path = _write_agent(tmp_path, over)
    record = tmp_path / "record.json"
    size = over * 5
    args = (tmp_path / "card.json", tmp_path, record, [path], tmp_path)

    record.write_text(json.dumps({"agents": {REL: {"lines": over + 10}}}))
    changes, refusals = co.sync_budgets(*args)
    assert json.loads(record.read_text())["agents"][REL] == {"lines": over}
    assert changes and not refusals

    record.write_text(json.dumps({"agents": {REL: {"lines": over - 5}}}))
    changes, refusals = co.sync_budgets(*args)
    assert json.loads(record.read_text())["agents"][REL] == {"lines": over - 5}
    assert refusals

    record.write_text(json.dumps({"agents": {}}))
    changes, refusals = co.sync_budgets(*args)
    assert json.loads(record.read_text())["agents"] == {} and refusals

    path = _write_agent(tmp_path, 10)
    record.write_text(json.dumps({"agents": {REL: {"lines": over, "bytes": size}}}))
    changes, refusals = co.sync_budgets(*args)
    assert json.loads(record.read_text())["agents"] == {} and changes and not refusals


def test_sync_drops_only_the_dimension_that_now_fits(tmp_path):
    long_line = "x" * 300 + "\n"
    lines = 50
    path = _write_agent(tmp_path, lines, long_line)
    size = lines * len(long_line)
    assert size > MAX_B
    record = tmp_path / "record.json"
    record.write_text(json.dumps({"agents": {REL: {"lines": MAX_L + 5, "bytes": size + 10}}}))
    changes, refusals = co.sync_budgets(tmp_path / "card.json", tmp_path, record, [path], tmp_path)
    assert json.loads(record.read_text())["agents"][REL] == {"bytes": size}
    assert changes and not refusals
