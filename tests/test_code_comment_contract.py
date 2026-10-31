"""The docstring rule - reStructuredText fields, no Google or NumPy sections - present in the
contract and in every agent that applies or checks it."""
from __future__ import annotations

from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent / "plugins" / "odoo-ai-agents"

CONTRACT = "snippets/code-comment-contract.md"


def _read(rel):
    return (PLUGIN / rel).read_text(encoding="utf-8")


def _between(text, start, end):
    head = text.index(start)
    return text[head:text.index(end, head + len(start))]


def _docstrings_section():
    return _between(_read(CONTRACT), "## 5. Docstrings", "\n## ")


def test_the_docstring_section_requires_the_rst_field_syntax():
    section = _docstrings_section()
    for marker in (":param", ":return:", ":rtype:", ":raises", "reStructuredText"):
        assert marker in section


def test_the_docstring_section_says_google_style_sections_are_not_written():
    assert "Args:" in _docstrings_section()


def test_the_review_table_flags_google_and_numpy_docstrings():
    review = _read(CONTRACT)[_read(CONTRACT).index("## In review"):]
    assert [line for line in review.splitlines() if line.startswith("|") and "Google or NumPy" in line]


def test_the_reviewer_mechanical_pass_greps_for_google_style_sections():
    mode_r1 = _between(_read("agents/odoo-code-reviewer.md"), "## MODE R1", "## MODE R2")
    assert "Args:" in mode_r1
    assert "Raises:" in mode_r1


def test_the_coder_validates_docstrings_against_the_rst_field_form():
    step6 = next(p for p in _read("agents/odoo-coder.md").split("\n") if p.startswith("**6. Validate before running.**"))
    assert "rst field form" in step6


def test_the_test_writing_skill_requires_the_rst_field_form():
    assert "rst field form" in _read("skills/odoo-test-writing/SKILL.md")
