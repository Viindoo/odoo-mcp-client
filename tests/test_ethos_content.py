"""Content-guard tests for ODOO-AI-ETHOS.md.

These tests protect the (separately authored) plugin principles file against:
  - accidental deletion or empty-out;
  - Unicode dashes (en/em/figure/horizontal-bar) banned by ETHOS#0;
  - Vietnamese language leaking in (must be English-only, depersonalized);
  - de-personalization tokens that would reveal internal Viindoo/vault context;
  - silent removal of any of the 11 principle headings.

This test suite is intentionally RED until the other agent writes ODOO-AI-ETHOS.md.
Only the missing-file assertion will fail; all other tests are guarded by
pytest.importorskip / skip marks so they produce clear SKIP not ERROR when the
file is absent.
"""
import re
import unicodedata
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ETHOS = ROOT / "plugins" / "odoo-ai-agents" / "ODOO-AI-ETHOS.md"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _text() -> str:
    """Read ETHOS content; skip all dependent tests if file absent."""
    if not ETHOS.exists():
        pytest.skip(f"ODOO-AI-ETHOS.md not yet authored (expected red until other agent writes it): {ETHOS}")
    return ETHOS.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Existence
# ---------------------------------------------------------------------------


def test_ethos_file_exists_and_non_empty():
    """This test is the designated RED one until the file lands."""
    assert ETHOS.exists(), f"ODOO-AI-ETHOS.md not found at {ETHOS}"
    assert ETHOS.stat().st_size > 0, "ODOO-AI-ETHOS.md is empty"


# ---------------------------------------------------------------------------
# No banned Unicode dashes (ETHOS#0)
# ---------------------------------------------------------------------------


def test_no_banned_unicode_dashes():
    text = _text()
    # figure dash U+2012, en dash U+2013, em dash U+2014, horizontal bar U+2015
    assert not re.search(r"[‒–—―]", text), \
        "banned Unicode dash found (use ASCII hyphen '-' per ETHOS#0)"


# ---------------------------------------------------------------------------
# No Vietnamese language content
# ---------------------------------------------------------------------------


def test_no_vietnamese_combining_tones():
    text = _text()
    # NFD-normalize so combining diacritics are separate code points.
    nfd = unicodedata.normalize("NFD", text)
    # Vietnamese combining tone marks: grave ̀, acute ́, hook above ̉,
    # tilde ̃, dot below ̣; and the Vietnamese D with stroke.
    assert not re.search(r"[̣̀́̉̃]", nfd), \
        "Vietnamese combining tone marks found - file must be English-only"


def test_no_vietnamese_d_stroke():
    text = _text()
    assert "đ" not in text and "Đ" not in text, \
        "Vietnamese d-with-stroke (đ/Đ) found - file must be English-only"


# ---------------------------------------------------------------------------
# No de-personalization tokens
# ---------------------------------------------------------------------------


_BANNED_TOKENS = [
    "Viindoo",
    "vault",
    "AI-Memory",
    "Meta/Home",
    "wikilink",
    "[[",
    "/home/",
    "Codex",
    "Gemini",
    "frontmatter v3",
    "Dao huu",
    "Ban dao",
]


@pytest.mark.parametrize("token", _BANNED_TOKENS)
def test_no_banned_token(token):
    text = _text()
    assert token.lower() not in text.lower(), \
        f"de-personalization token {token!r} found - must be stripped from the public plugin file"


# ---------------------------------------------------------------------------
# Positive presence: all 11 principle headings must survive trimming
# ---------------------------------------------------------------------------


_REQUIRED_MARKERS = [
    "Boil the Ocean",
    "Think Before Acting",
    "Search Before Building",
    "Outcomes over Procedures",
    "Root Cause",
    "See Something",
    "Completion Status",
    "Build for the Audience",
    "Artifact Production",
    "Test the Behavior",
]


@pytest.mark.parametrize("marker", _REQUIRED_MARKERS)
def test_principle_heading_present(marker):
    text = _text()
    assert marker in text, \
        f"principle marker {marker!r} missing - a trim must not silently drop a principle"


def test_ascii_principle_is_a_heading():
    """A9: the P0 ASCII-hyphens principle must appear as a markdown HEADING line.

    A bare word match would pass even if the heading were deleted and the word
    appeared elsewhere in the body. This pins the heading specifically.
    The author keeps: '## 0. Output Convention - ASCII Hyphens' (or similar).
    """
    text = _text()
    assert re.search(r"(?m)^#+ .*ASCII", text), \
        "no heading line containing 'ASCII' found - P0 ASCII-hyphens principle heading was dropped"
