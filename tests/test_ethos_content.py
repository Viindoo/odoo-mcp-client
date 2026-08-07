"""Content-guard tests for ODOO-AI-ETHOS.md, plus the repo-wide ASCII-hyphen guard.

These tests protect the (separately authored) plugin principles file against:
  - accidental deletion or empty-out;
  - Vietnamese language leaking in (must be English-only, depersonalized);
  - de-personalization tokens that would reveal internal Viindoo/vault context;
  - silent removal of any of the 11 principle headings.

They also guard ETHOS#0 (ASCII hyphen only, U+002D) - not just in ODOO-AI-ETHOS.md, but across
every decodable text file in the repository. A guard scoped to the one file that stated the rule
misses every other file the rule applies to just as strongly; see `test_no_banned_unicode_dashes`
below for the whole-tree scan and its allowlist.

This test suite is intentionally RED until the other agent writes ODOO-AI-ETHOS.md.
Only the missing-file assertion will fail; all other ETHOS-specific tests are guarded by
pytest.importorskip / skip marks so they produce clear SKIP not ERROR when the
file is absent. The whole-tree dash guard below does not depend on ETHOS.md and always runs.
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
# No banned Unicode dashes anywhere in the repository (ETHOS#0)
# ---------------------------------------------------------------------------
#
# ETHOS#0 requires the ASCII hyphen (U+002D) in every text artifact this repo ships. A guard that
# reads only ODOO-AI-ETHOS.md proves the rule is stated but nothing about whether it is followed
# anywhere else - so this scans every decodable text file in the repository, the same shape of
# fix as `tests/test_context_md_removed.py` (whole tree, not a hand-picked directory list).

# Figure dash U+2012, en dash U+2013, em dash U+2014, horizontal bar U+2015 - never ASCII hyphen
# (U+002D), which this pattern deliberately excludes.
_BANNED_DASH_RE = re.compile(r"[‒–—―]")

# Directories that are not repo content: version control internals, virtualenvs, caches, and
# vendored node modules. Mirrors tests/test_context_md_removed.py's SKIP_DIRS.
_DASH_SKIP_DIRS = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
    }
)

# repo-relative POSIX path -> why the banned glyph legitimately appears there. Each entry here
# DECLARES one of the four glyphs AS THE PATTERN used to detect it - the glyph is the detector's
# payload, not prose that violates the rule. Nothing else goes in this dict: every other hit in
# the tree is a genuine violation and must be fixed, not allowlisted.
_DASH_ALLOWLIST: dict[str, str] = {
    "tests/test_dispatch_brief.py": (
        "declares `_BANNED_UNICODE_DASH = re.compile(r\"[...]\")` to detect banned dashes inside "
        "a dispatch brief under test - the four glyphs are the detector's own pattern, not prose"
    ),
    "tests/test_ethos_content.py": (
        "this guard - the detector pattern above and the RED-proof sample below have to spell "
        "the four banned glyphs in order to test for them"
    ),
}


def _dash_scan_files() -> list[Path]:
    """Every decodable text file in the repository, minus the non-content directories."""
    found: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        if _DASH_SKIP_DIRS & set(path.relative_to(ROOT).parts):
            continue
        found.append(path)
    return sorted(found)


def _dash_findings() -> list[str]:
    """Every non-allowlisted banned-dash occurrence in the repository, as `path:line: glyph`."""
    findings: list[str] = []
    for path in _dash_scan_files():
        rel = path.relative_to(ROOT).as_posix()
        if rel in _DASH_ALLOWLIST:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            for match in _BANNED_DASH_RE.finditer(line):
                findings.append(f"{rel}:{lineno}: {match.group()!r}")
    return findings


def test_no_banned_unicode_dashes():
    """ETHOS#0, enforced tree-wide: only the ASCII hyphen (U+002D) is allowed anywhere.

    Scans every decodable text file in the repository - not just ODOO-AI-ETHOS.md - for figure
    dash, en dash, em dash, and horizontal bar. A file that legitimately declares one of these
    glyphs AS THE PATTERN used to detect it is allowlisted in `_DASH_ALLOWLIST` with a stated
    reason; every other hit is a real violation of the rule and must be fixed at the source.
    """
    findings = _dash_findings()
    assert not findings, (
        "banned Unicode dash found (use ASCII hyphen '-' per ETHOS#0); if this file legitimately "
        "declares the glyph as a detection pattern, add a reasoned entry to _DASH_ALLOWLIST "
        "instead of fixing it:\n  " + "\n  ".join(findings)
    )


def test_dash_allowlist_entries_still_earn_their_place():
    """A stale allowlist entry is an un-guarded file: the exemption survives after the reason (the
    glyph it declares) is gone. Every entry must still exist and still contain a banned glyph,
    mirroring `test_context_md_removed.py::test_every_allowlist_entry_still_earns_its_place`."""
    for rel, reason in _DASH_ALLOWLIST.items():
        path = ROOT / rel
        assert path.is_file(), (
            f"allowlisted path {rel} does not exist - delete the entry instead of leaving an "
            f"exemption behind (reason on record: {reason})"
        )
        text = path.read_text(encoding="utf-8")
        assert _BANNED_DASH_RE.search(text), (
            f"allowlisted path {rel} no longer contains a banned dash - delete the entry so the "
            f"file is guarded again (reason on record: {reason})"
        )
        assert reason.strip(), f"allowlist entry {rel} must state why the glyph is legitimate there"


def test_banned_dash_detector_can_fail():
    """RED proof: the detector must actually flag a banned glyph, not merely always pass.

    A guard that has never been red is not evidence it guards anything. This feeds the exact
    regex the whole-tree scan uses a sample containing each of the four banned glyphs in turn and
    requires every one to be flagged."""
    samples = {
        "figure dash": "a value in the 8‒12 range",  # U+2012
        "en dash": "pages 8–12",  # U+2013
        "em dash": "Two clauses joined by an em dash — like this — must be flagged.",  # U+2014
        "horizontal bar": "a rule drawn with a horizontal bar ― here",  # U+2015
    }
    undetected = [name for name, text in samples.items() if not _BANNED_DASH_RE.search(text)]
    assert not undetected, (
        f"the detector failed to flag: {undetected} - it would not catch a real violation using "
        "that glyph"
    )
    # And the negative control: a clean ASCII-hyphen sample must NOT be flagged.
    assert not _BANNED_DASH_RE.search("a value in the 8-12 range - ASCII hyphen only"), (
        "the detector flagged an ASCII hyphen - it would force every legitimate hyphen use into "
        "the allowlist"
    )


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
