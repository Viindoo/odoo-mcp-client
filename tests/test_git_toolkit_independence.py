r"""Guard: git-toolkit is domain-agnostic and MUST NOT name odoo-ai-agents.

Business rule (dependency direction): git-toolkit is a domain-agnostic PROVIDER
library (Apache-2.0). As a provider it must not know, name, or point into its
CONSUMER plugin odoo-ai-agents. References in the OTHER direction
(odoo-ai-agents -> git-toolkit) are legal and are guarded by
``test_git_delegation_boundary.py``. This test is the exact inverse: it scans
ONLY ``plugins/git-toolkit/**`` so it structurally cannot touch odoo-ai-agents,
and together the two form a non-overlapping bidirectional guard.

A reference is forbidden when git-toolkit text names any odoo-ai-agents artifact
(the sibling plugin id, or any of its skills / agents / commands) or points into
the consumer-side delegation snippet (``git-delegation.md``). The denylist is
DATA-DRIVEN - derived from the actual basenames under
``plugins/odoo-ai-agents/{skills,agents,commands}`` (mirroring how
``test_naming_consistency.py`` discovers names) - so a newly added consumer skill
is covered automatically with no edit here.

FP-avoidance choices (do NOT loosen these without an accompanying test update):

1. NEVER the bare product noun ``odoo``. The Odoo product (``commit-convention-odoo.md``,
   ``__manifest__.py`` detection, "Odoo-the-product" prose) is legitimate domain
   knowledge for a git tool. Only FULL compound artifact names are forbidden
   (``odoo-git-rebase``, ``odoo-coding``, ...), matched with word boundaries.

2. WORD BOUNDARIES. Each token is matched as ``\bTOKEN\b`` (case-sensitive - artifact
   names are always written lowercase). The hyphen is a non-word char, so
   ``\bodoo-code-review\b`` does NOT match inside ``odoo-code-reviewer`` (which is
   itself a separate denylist token), and the dot-anchored ``git-delegation.md``
   token does NOT match the provider's own ``git-delegation-decision.md``.

3. GENERIC GIT TERMS stay legal. ``forward-port`` / ``backport`` are generic git ops
   git-toolkit performs; only the ``odoo-``-prefixed compound ``odoo-forward-port``
   is forbidden.

4. UNPREFIXED CONSUMER NAMES (``run-harness``, ``workflow-chaining``) are
   included from the skills glob (dirs starting with neither ``odoo-`` nor ``_``).

5. SELF + BINARY skipped. This test file lives outside the scan root by
   construction; non-UTF-8 (binary) files are skipped defensively.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENTS_PLUGIN = REPO_ROOT / "plugins" / "odoo-ai-agents"
TOOLKIT = REPO_ROOT / "plugins" / "git-toolkit"

# git-toolkit's OWN, provider-agnostic team-mode reporting snippet. It is the inverse-direction
# counterpart of odoo-ai-agents' agent-team-protocol.md: it tells a git-toolkit agent spawned as a
# named teammate how to end its turn (push a report), naming NO consumer. Guarded for existence +
# anchors here; the independence scan below additionally proves it names no odoo-ai-agents artifact.
AGENT_TEAM_REPORTING = TOOLKIT / "snippets" / "agent-team-reporting.md"

# The consumer-side delegation snippet filename. Distinct from the provider's own
# ``git-delegation-decision.md`` - forbidding this token must NOT flag that file
# (see FP-guard #2: the token is dot-anchored).
DELEGATION_SNIPPET = "git-delegation.md"
SIBLING_PLUGIN = "odoo-ai-agents"


# ---------------------------------------------------------------------------
# Data-driven denylist
# Mirrors test_naming_consistency.py: names are directory/file basenames under
# plugins/odoo-ai-agents/{skills,agents,commands}. Globbing keeps the denylist
# in sync with the consumer automatically (ETHOS #11 data-driven).
# ---------------------------------------------------------------------------

def _consumer_names() -> set[str]:
    names: set[str] = set()
    for skill in AGENTS_PLUGIN.glob("skills/*/SKILL.md"):
        names.add(skill.parent.name)
    for md in AGENTS_PLUGIN.glob("agents/*.md"):
        names.add(md.stem)
    for md in AGENTS_PLUGIN.glob("commands/*.md"):
        names.add(md.stem)
    # Drop shared/private dirs (e.g. _shared) - not addressable artifacts.
    names = {n for n in names if not n.startswith("_")}
    # Plus the literals: the sibling plugin id and the consumer delegation snippet.
    names.add(SIBLING_PLUGIN)
    names.add(DELEGATION_SNIPPET)
    return names


def _forbidden_re(names: set[str]) -> re.Pattern[str]:
    """Compile an alternation of word-bounded, literal-escaped denylist tokens.

    Sorted longest-first so the regex engine reports the most specific token at a
    position. ``\\b`` on both ends + ``re.escape`` make each token a literal that
    only matches the full compound name (never the bare ``odoo`` product noun and
    never a longer superstring like ``odoo-code-reviewer`` for ``odoo-code-review``).
    """
    alt = "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))
    return re.compile(r"\b(?:" + alt + r")\b")


# ---------------------------------------------------------------------------
# File discovery + scan (provider side only)
# ---------------------------------------------------------------------------

_SELF = Path(__file__).resolve()


def _text_files() -> list[Path]:
    files: list[Path] = []
    for p in sorted(TOOLKIT.rglob("*")):
        if not p.is_file():
            continue
        if p.resolve() == _SELF:  # never scan this test (defensive; it is outside TOOLKIT)
            continue
        files.append(p)
    return files


def _scan(path: Path, pattern: re.Pattern[str]) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []  # skip binary / unreadable
    rel = path.relative_to(REPO_ROOT)
    hits: list[str] = []
    for n, line in enumerate(text.splitlines(), 1):
        for m in pattern.finditer(line):
            hits.append(f"{rel}:{n}: {m.group()}  [{line.strip()[:90]!r}]")
    return hits


# ---------------------------------------------------------------------------
# In-test self-checks: the matcher must flag a real consumer name and spare
# the bare product noun / generic git terms / the provider's own snippet.
# These fail for the RIGHT reason if a future edit weakens the matcher.
# ---------------------------------------------------------------------------

def test_matcher_flags_consumer_name_and_spares_generics():
    pattern = _forbidden_re(_consumer_names())

    # FLAGS a real, full consumer artifact name embedded in prose.
    assert pattern.search("see the odoo-coding skill for details"), (
        "matcher must flag a full odoo-ai-agents artifact name"
    )
    assert pattern.search("delegated via odoo-ai-agents/snippets/git-delegation.md"), (
        "matcher must flag the consumer plugin id and the delegation snippet"
    )

    # Does NOT flag the bare product noun ``odoo`` (legitimate domain knowledge).
    assert not pattern.search("detect an Odoo repo via __manifest__.py"), (
        "matcher must NOT flag the bare Odoo product noun"
    )
    assert not pattern.search("odoo commit-convention support"), (
        "matcher must NOT flag the bare lowercase odoo product noun"
    )

    # Does NOT flag generic git ops that merely share a suffix with a consumer name.
    assert not pattern.search("a forward-port of 60 commits"), (
        "matcher must NOT flag the generic git op forward-port"
    )
    assert not pattern.search("backport the fix to v16"), (
        "matcher must NOT flag the generic git op backport"
    )

    # Does NOT flag the provider's OWN snippet (dot-anchored token boundary).
    assert not pattern.search("${ROOT}/snippets/git-delegation-decision.md"), (
        "matcher must NOT flag the provider's own git-delegation-decision.md"
    )


def test_denylist_is_populated():
    names = _consumer_names()
    # Sanity: the glob actually discovered the consumer's artifacts.
    assert "odoo-coding" in names, "expected odoo-coding skill in the data-driven denylist"
    assert SIBLING_PLUGIN in names and DELEGATION_SNIPPET in names
    assert "_shared" not in names, "private/shared dirs must be excluded"


def test_agent_team_reporting_snippet_exists():
    """git-toolkit's team-mode reporting SSOT snippet must exist and carry its anchor tokens.

    The snippet's contract: a git-toolkit agent spawned as a NAMED TEAMMATE must end its turn with
    a report PUSH to the lead (`SendMessage`), as opposed to a cold-spawned agent that returns its
    result as the final message. The anchors guard that report-contract language. This complements
    the independence scan: that test proves the snippet names no consumer, this one proves the
    snippet still says what it must (the two together stop it from being silently emptied OR
    quietly re-coupled to a consumer).
    """
    assert AGENT_TEAM_REPORTING.is_file(), f"missing SSOT snippet {AGENT_TEAM_REPORTING}"
    body = AGENT_TEAM_REPORTING.read_text(encoding="utf-8")
    for token in ("SendMessage", "completion report", "report push", 'to: "main"'):
        assert token in body, (
            f"agent-team-reporting.md: missing anchor token '{token}'"
        )


# ---------------------------------------------------------------------------
# The guard
# ---------------------------------------------------------------------------

def test_git_toolkit_names_no_odoo_ai_agents_artifact():
    """git-toolkit (domain-agnostic provider) must not name any odoo-ai-agents artifact.

    Business rule: a provider library must not know its consumers by name. Any
    git-toolkit text that names an odoo-ai-agents skill / agent / command, the
    sibling plugin id, or points into the consumer's git-delegation.md violates
    the dependency direction (odoo-ai-agents -> git-toolkit is fine; never the
    reverse). The denylist is derived from the consumer's actual artifact
    basenames, so adding a consumer skill extends the guard automatically.
    """
    pattern = _forbidden_re(_consumer_names())
    violations: list[str] = []
    for f in _text_files():
        violations.extend(_scan(f, pattern))

    n = len(violations)
    head = violations[:120]
    tail = f"\n... and {n - 120} more" if n > 120 else ""
    assert not violations, (
        f"git-toolkit: {n} reference(s) to an odoo-ai-agents artifact. git-toolkit is a "
        f"domain-agnostic provider and MUST NOT name its consumers (skills/agents/commands), "
        f"the {SIBLING_PLUGIN!r} plugin, or point into the consumer's {DELEGATION_SNIPPET!r}. "
        f"Genericize the reference (name no consumer) and point only at git-toolkit's own "
        f"snippets.\n" + "\n".join(head) + tail
    )
