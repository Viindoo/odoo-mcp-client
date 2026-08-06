"""Guard against `odoo-ai-agents` composing its own commit-message format
instead of requesting the commit (files touched + business outcome) and
letting `git-toolkit:git-ops` detect the repo's actual convention and
compose the message itself - see `12-design-final.md` § M3b and
`03-commit-convention.md` § C8-C10 for the evidence this fix closes.

Scoped to exactly two shapes. A v1 draft of this guard used an unscoped
"any `KEY: value` line that mentions commit" pattern and matched 587
in-fence lines across 53 files, because every dispatch brief in this repo is
written in that `KEY: value` shape - almost none of them are about commit
messages at all. This version is deliberately narrow:

  1. a line that is the VALUE of a `commit[-_]messa?ge?` / `commit-msg` KEY,
     where the value is a LITERAL string - it starts with a backtick or a
     double quote. An angle-bracket `<...>` placeholder (this repo's
     universal "fill this in, never copy verbatim" notation - see
     dispatch-brief.md) is NOT a literal and is explicitly allowed: the
     fix landed by this file keeps the `commit-msg` KEY name in
     `wave-integration.md` (git-toolkit's own `git-squash-push.md` recipe
     requires that literal key), but its VALUE is now a placeholder
     describing "let git-ops compose it", never a pre-written subject.
  2. the invented `upg: ` commit-subject prefix, anywhere in this plugin's
     prose - it has no other legitimate use.

Proves: no `odoo-ai-agents` file hands a pre-composed commit subject to
`git-toolkit:git-ops`.
Does NOT prove: that the message git-ops finally writes conforms to the
repo's detected convention - that is M3's job on the git-toolkit provider
side, and neither side has a CI observer for the literal `git log` in this
repo.
"""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ODOO_AI_AGENTS = REPO_ROOT / "plugins" / "odoo-ai-agents"

MD_FILES = sorted(ODOO_AI_AGENTS.rglob("*.md"))

# Shape 1: a `commit_message` / `commit-message` / `commit-msg` / `commit_msg`
# key - optionally suffixed with a parenthetical variant tag, e.g.
# "commit_message (absorbed):" - whose value is a LITERAL string (starts
# with a backtick or a double quote), never a `<...>` placeholder.
_COMMIT_KEY_LINE = re.compile(
    r"^\s*[-*]?\s*`?commit[-_](?:messa?ge?|msg)`?\s*(?:\([^)]*\))?\s*:\s*(?P<value>.+?)\s*$",
    re.IGNORECASE,
)
_LITERAL_VALUE_START = re.compile(r'^["`]')

# Shape 2: the invented `upg: ` commit-subject prefix (word-boundary guarded
# so it never matches inside a longer identifier).
_UPG_PREFIX = re.compile(r"(?<![\w-])upg:\s")


def _scan_lines(lines):
    """Return [(shape, line)] for every shape-1/shape-2 hit in `lines`."""
    hits = []
    for line in lines:
        m = _COMMIT_KEY_LINE.match(line)
        if m and _LITERAL_VALUE_START.match(m.group("value")):
            hits.append(("commit-key-literal-value", line))
        if _UPG_PREFIX.search(line):
            hits.append(("upg-prefix", line))
    return hits


def _scan_files(files):
    hits = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            for shape, matched_line in _scan_lines([line]):
                hits.append((path, lineno, shape, matched_line))
    return hits


# ---------------------------------------------------------------------------
# Discovery floor - the same failure mode as a vacuous parametrize/glob.
# ---------------------------------------------------------------------------


def test_md_files_discovered():
    assert len(MD_FILES) >= 40, (
        f"expected at least 40 plugins/odoo-ai-agents/**/*.md files, found "
        f"{len(MD_FILES)} - glob is wrong or files went missing"
    )


# ---------------------------------------------------------------------------
# The real guard.
# ---------------------------------------------------------------------------


def test_no_precomposed_commit_request_shapes():
    hits = _scan_files(MD_FILES)
    assert not hits, (
        "odoo-ai-agents hands git-toolkit:git-ops a pre-composed commit "
        "subject instead of requesting the commit by files touched + "
        "business outcome (M3b - see 03-commit-convention.md § C8-C10): "
        + "; ".join(
            f"{p.relative_to(REPO_ROOT)}:{ln} [{shape}] {txt.strip()!r}"
            for p, ln, shape, txt in hits
        )
    )


# ---------------------------------------------------------------------------
# Self-check (ETHOS #8 - the detector must be CAPABLE of catching what it
# claims to guard, and must NOT flag the resolved-value replacement pattern
# this fix lands). Run standalone to prove RED-before-GREEN:
#
#   .venv/bin/python -m pytest tests/test_commit_request_shape.py -q -k self_check
#
# against synthetic fixtures that never touch the real tree, so these two
# tests stay green regardless of the current file contents - they protect
# the DETECTOR's behavior, not the fix.
# ---------------------------------------------------------------------------

_KNOWN_BAD_LINES = [
    # the old odoo-modules-upgrade hardcoded format (SKILL.md)
    "- Commit messages (adapt): `upg: <module> <src>-><tgt> - <KEEP|REWRITE|MERGE|SPLIT> <summary>`.",
    # the old git-ops request template (upg-phase-detail.md)
    "    - commit_message (absorbed): `upg: delete <module> - absorbed by core <absorbing_core_feature> in <target_version> (no custom delta remains)`",
    '  Commit message: "upg: <module> <source_version>-><target_version> - <ACTION> <one-line summary>"',
    "- commit_message: `upg: <module> <src>-><tgt> - <ACTION> <summary>` (signed)",
    # the old run-harness pre-labeled literal (wave-integration.md)
    'commit-msg         : "feat(scope): a literal, already-composed subject"',
]

_KNOWN_GOOD_LINES = [
    # the M3b replacement: business outcome, never a literal subject
    "Request the commit via `git-toolkit:git-ops`: the files touched, the business outcome.",
    "  commit        : <resolved by git-toolkit:git-ops at commit time - do not pre-declare a standard>",
    "commit-msg         : <none - let git-toolkit:git-ops compose it from the business outcome>",
    "- [ ] Adapted modules: commit requested via `git-toolkit:git-ops` with business outcome `<module> <src>-><tgt> - <ACTION> <summary>`; git-ops composed the message",
    "SCOPE: module '<module>' adapt diff only (the module's adapt commit); attribute findings to",
    "- business outcome: <module> <src>-><tgt> - <ACTION> <summary> (signed via git-ops)",
    # generic prose mentioning "commit message" (space, not hyphen/underscore)
    # mid-sentence must never trip the key-anchored regex.
    "git-ops OWNS the commit-message CONVENTION, the DCO sign-off, and all git mechanics.",
]


def test_self_check_detector_catches_known_bad_commit_message_shapes():
    for line in _KNOWN_BAD_LINES:
        hits = _scan_lines([line])
        assert hits, f"detector failed to flag a known-bad (pre-fix) line: {line!r}"


def test_self_check_detector_does_not_flag_resolved_value_replacement_shapes():
    for line in _KNOWN_GOOD_LINES:
        hits = _scan_lines([line])
        assert not hits, f"detector false-positived on a known-good (post-fix) line: {line!r} -> {hits}"
