"""Contract tests for the RST-validity contract snippet and its wiring into
`agents/odoo-user-doc-writer.md` (GitHub issue #158 - invalid RST shipped in
`doc/*.rst` because the writer had no RST-validity contract and no mechanical
verification that its output actually renders).

These protect the BEHAVIOR the fix promises, not a text snapshot:
  1. The SSOT contract snippet exists and states the load-bearing rules a
     plain-docutils renderer (no Sphinx) actually enforces: no Sphinx-only
     roles, underline-only titles sized to the exact character count, the
     `#.` auto-enumerator to resume an interrupted list, and double-backtick
     inline literals.
  2. `odoo-user-doc-writer.md` references the contract AND carries a MANDATORY
     self-verify gate that actually renders each `doc/*.rst` through docutils
     `publish_programmatically` and requires zero `system_message` nodes,
     with a defined BLOCKED failure path.
  3. The gate is NOT copied onto `odoo-marketing-writer.md`, which emits HTML
     (App-Store landing page), not RST - carrying it there would be dead
     weight referencing a file type that agent never writes.

Red-before-green: deleting the contract file, the reference to it, or the
docutils gate from the writer agent makes the matching assertion fail.
stdlib only.
"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
SNIPPETS = PLUGIN / "snippets"
AGENTS = PLUGIN / "agents"

CONTRACT = SNIPPETS / "rst-validity-contract.md"
DOC_WRITER = AGENTS / "odoo-user-doc-writer.md"
MARKETING_WRITER = AGENTS / "odoo-marketing-writer.md"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. The contract snippet exists and states the load-bearing rules
# ---------------------------------------------------------------------------


def test_contract_snippet_exists():
    """The rst-validity-contract.md SSOT snippet must exist."""
    assert CONTRACT.is_file(), f"missing SSOT snippet {CONTRACT}"


@pytest.mark.parametrize("role", [":ref:", ":menuselection:", ":guilabel:"])
def test_contract_bans_sphinx_only_roles(role):
    """Each Sphinx-only role plain docutils cannot resolve must be named as banned.

    Plain docutils (no Sphinx build step in this pipeline) raises an "Unknown
    interpreted text role" system_message for any of these - the contract must
    call each one out explicitly so the writer never emits it.
    """
    text = _read(CONTRACT)
    assert role in text, (
        f"{CONTRACT.relative_to(ROOT)} must name {role!r} as a banned Sphinx-only role"
    )


def test_contract_mandates_underline_only_titles_exact_length():
    """Contract must require underline-only titles sized to the exact char count.

    A docutils title underline that is too short/long raises "Title underline
    too short" - the single most common invalid-RST failure mode named in the
    issue. The rule must be stated, not merely the word "underline" in passing.
    """
    text = _read(CONTRACT).lower()
    assert "underline" in text, (
        f"{CONTRACT.relative_to(ROOT)} must document the underline-only title rule"
    )
    assert "exact" in text and "character count" in text, (
        f"{CONTRACT.relative_to(ROOT)} must require the underline length to match "
        "the EXACT (Unicode) character count of the title text"
    )


def test_contract_mandates_auto_enumerator_for_interrupted_lists():
    """Contract must mandate `#.` to resume a list interrupted by a block."""
    text = _read(CONTRACT)
    assert "#." in text, (
        f"{CONTRACT.relative_to(ROOT)} must mandate the '#.' auto-enumerator "
        "to resume a list interrupted by a non-list block"
    )


def test_contract_mandates_double_backtick_inline_literals():
    """Contract must mandate double backticks, not Sphinx's single-backtick default role."""
    text = _read(CONTRACT)
    assert "``" in text, (
        f"{CONTRACT.relative_to(ROOT)} must show the double-backtick inline-literal form"
    )
    assert "double backtick" in text.lower() or "double-backtick" in text.lower(), (
        f"{CONTRACT.relative_to(ROOT)} must call out DOUBLE backticks explicitly "
        "(a single backtick is Sphinx's undefined-in-docutils default role)"
    )


def test_contract_ascii_only():
    """The contract's own prose stays ASCII (ETHOS rule 0).

    The one deliberate non-ASCII character in this feature - the TRIANGULAR
    BULLET (U+2023) menu separator - is emitted by the AGENT into third-party
    `doc/*.rst` files, never into this contract's own prose, which names it
    only by code point.
    """
    text = _read(CONTRACT)
    assert text.isascii(), (
        f"{CONTRACT.relative_to(ROOT)} must be ASCII-only prose - name the "
        "TRIANGULAR BULLET separator by code point (U+2023), never print the glyph here"
    )


# ---------------------------------------------------------------------------
# 2. odoo-user-doc-writer.md references the contract and carries the gate
# ---------------------------------------------------------------------------


def test_doc_writer_references_contract():
    """odoo-user-doc-writer.md must point at the RST-validity contract SSOT."""
    text = _read(DOC_WRITER)
    assert "rst-validity-contract.md" in text, (
        f"{DOC_WRITER.relative_to(ROOT)} must reference "
        "${CLAUDE_PLUGIN_ROOT}/snippets/rst-validity-contract.md where it authors doc/*.rst"
    )


def test_doc_writer_has_step_4_5_heading():
    """The mandatory gate must be its own Step 4.5, ahead of the agent's return."""
    text = _read(DOC_WRITER)
    assert "4.5" in text, (
        f"{DOC_WRITER.relative_to(ROOT)} must add a 'Step 4.5' self-verify gate "
        "before Step 5 / before the agent returns"
    )


@pytest.mark.parametrize(
    "token",
    [
        "publish_programmatically",
        "standalone",
        "restructuredtext",
        "pseudoxml",
        "report_level",
        "halt_level",
    ],
)
def test_doc_writer_docutils_render_call_wired(token):
    """The gate must actually call docutils the way the spec requires.

    standalone reader + restructuredtext parser + pseudoxml writer +
    report_level=1 + halt_level=5 is the exact configuration that collects
    every system_message in one pass instead of halting on the first one.
    """
    text = _read(DOC_WRITER)
    assert token in text, (
        f"{DOC_WRITER.relative_to(ROOT)} Step 4.5 must reference {token!r} "
        "as part of the docutils publish_programmatically render call"
    )


def test_doc_writer_requires_empty_system_message_list():
    """The gate must require document.findall(nodes.system_message) to be empty."""
    text = _read(DOC_WRITER)
    assert "findall(nodes.system_message)" in text, (
        f"{DOC_WRITER.relative_to(ROOT)} Step 4.5 must check "
        "document.findall(nodes.system_message) and require it empty"
    )


def test_doc_writer_blocks_on_persistent_failure():
    """A doc that still fails after the bounded fix loop must return BLOCKED, not ship broken."""
    text = _read(DOC_WRITER)
    assert "BLOCKED" in text, (
        f"{DOC_WRITER.relative_to(ROOT)} Step 4.5 must define a BLOCKED outcome "
        "when the render-check still fails after the bounded retry loop"
    )


def test_doc_writer_gate_is_stated_as_mandatory():
    """The gate must be framed as a hard MUST, not an optional nice-to-have."""
    text = _read(DOC_WRITER)
    assert "MUST NOT return" in text or "MANDATORY" in text, (
        f"{DOC_WRITER.relative_to(ROOT)} Step 4.5 must be stated as a hard gate - "
        "the agent must not be able to return a doc that fails it"
    )


# ---------------------------------------------------------------------------
# 3. odoo-marketing-writer.md (HTML, not RST) must NOT carry this gate
# ---------------------------------------------------------------------------


def test_marketing_writer_has_no_docutils_gate():
    """odoo-marketing-writer emits HTML (App-Store landing page), not RST.

    Carrying the docutils render-check there would be dead weight pointing at
    a file type that agent never writes. This is the non-tautology guard: it
    proves the parametrized checks above are actually selective, not just
    matching on any agent file.
    """
    if not MARKETING_WRITER.is_file():
        pytest.skip(f"{MARKETING_WRITER} not found - nothing to guard")
    text = _read(MARKETING_WRITER)
    assert "publish_programmatically" not in text, (
        f"{MARKETING_WRITER.relative_to(ROOT)} must NOT carry the docutils RST "
        "self-verify gate - it emits HTML, not RST (see rst-validity-contract.md)"
    )
