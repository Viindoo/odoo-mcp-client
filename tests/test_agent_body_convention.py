"""Guard the agent-body convention: an agent `.md` body is the agent's SYSTEM
PROMPT, not a routing surface.

Per Anthropic's subagent contract (https://code.claude.com/docs/en/sub-agents)
the frontmatter `description` is routing metadata - read by the orchestrator when
it decides whether to delegate - and the Markdown body is the system prompt the
running agent reads at startup. A `## When to invoke` heading in the body
re-states the `description`'s routing text and pollutes the system prompt with
content the running agent cannot act on, so it is banned in every plugin agent
file. See CONTRIBUTING.md "Agent format".

The ban is not limited to that one literal heading (V-36): a `## Out of Scope`
or `## Routing` section whose bullets are DOMINATED by `-> use X` redirects is
the same banned routing content under a different name - it evaded the
heading-only regex while still being unactionable-by-the-running-agent routing
prose. A section is "redirect-dominated" when at least half of its bullet
lines redirect elsewhere (`-> use X`); a genuine boundary note kept as prose
(no majority of bullets redirecting) is not flagged, so a legitimate
non-routing "Out of Scope" note elsewhere would not trip this guard. (Audited
at broadening time via `grep -rniE "^#{2} *(out.of.scope|routing)"
plugins/*/agents/*.md`: only `odoo-ui-debugger.md` carried either heading, and
that section was removed as part of this same fix - re-run the grep before
tightening this guard further.)

Third rule (V-XX, the frontmatter-only prohibition): the split above cuts BOTH ways. Routing must
not leak into the body - and a PROHIBITION must not stay in the `description`, because the
`description` is the launcher's routing listing and is never part of the running agent's system
prompt. An agent whose only "you do not author X" clause lives in frontmatter was never given that
rule at all. Measured incident: `odoo-coder` carried "NOT a code writer and NOT a leaf" at
`odoo-coder.md:4` and nowhere in its 291-line body; when a teammate dispatch was refused it edited a
module's `__manifest__.py` itself. It had not disobeyed a rule - it had never received one.
"""
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENT_FILES = sorted(REPO_ROOT.glob("plugins/*/agents/*.md"))

# A Markdown H2 heading whose title starts with "When to invoke". The `^`
# anchor (with no leading indentation) only matches body headings: inside YAML
# frontmatter the phrase can only appear indented under a block scalar
# (`description: |`), so frontmatter prose mentions are intentionally not caught.
_WHEN_TO_INVOKE_HEADING = re.compile(r"^##\s+When to invoke", re.IGNORECASE)

# Generic routing-section headings (V-36). These are banned ONLY when the
# section is redirect-dominated (see `_is_redirect_dominated`) - unlike the
# unconditional `## When to invoke` ban above.
_REDIRECT_SECTION_HEADING = re.compile(
    r"^##\s+(Out[\s-]of[\s-]Scope|Routing)\b", re.IGNORECASE
)

_ANY_H2_HEADING = re.compile(r"^##\s+")
_BULLET_LINE = re.compile(r"^\s*[-*]\s+")
_REDIRECT_BULLET = re.compile(r"->\s*use\b", re.IGNORECASE)


def _section_body(lines: list[str], heading_idx: int) -> list[str]:
    """Lines strictly after the heading at `heading_idx`, up to (not including)
    the next top-level `## ` heading or end of file."""
    body = []
    for line in lines[heading_idx + 1 :]:
        if _ANY_H2_HEADING.match(line):
            break
        body.append(line)
    return body


def _is_redirect_dominated(section_lines: list[str]) -> bool:
    """True when at least half the bullet lines in the section redirect
    elsewhere (`-> use X`) - i.e. the section is functionally a routing table
    in prose clothing, not a boundary explanation. A section with no bullets
    at all (pure prose) is never dominated."""
    bullets = [line for line in section_lines if _BULLET_LINE.match(line)]
    if not bullets:
        return False
    redirects = [line for line in bullets if _REDIRECT_BULLET.search(line)]
    return len(redirects) / len(bullets) >= 0.5


def test_agent_files_discovered():
    # Floor: the glob must resolve real files, else the guard passes vacuously.
    assert AGENT_FILES, "no plugins/*/agents/*.md files found - glob is wrong"


# --- unit-level proof each predicate can fail (crafted strings, not just real files) ---
def test_redirect_dominated_predicate_can_fail():
    dominated = [
        "- **Rating a working screen** (aesthetics, a11y) -> use `odoo-ui-reviewer`",
        "- **Comparing two builds for drift** -> use `odoo-visual-regression`",
        "- **Writing the fix** -> use `odoo-coding`",
    ]
    assert _is_redirect_dominated(dominated)
    prose_boundary_note = [
        "- This agent never modifies application code or the running instance;",
        "  it only names the root cause and the file/method to change.",
    ]
    assert not _is_redirect_dominated(prose_boundary_note)
    assert not _is_redirect_dominated([])


def test_section_body_stops_at_next_h2():
    lines = ["## Out of Scope", "- a -> use `x`", "## Next Section", "- b -> use `y`"]
    assert _section_body(lines, 0) == ["- a -> use `x`"]


@pytest.mark.parametrize(
    "agent", AGENT_FILES, ids=lambda p: str(p.relative_to(REPO_ROOT))
)
def test_no_when_to_invoke_routing_heading_in_body(agent):
    rel = agent.relative_to(REPO_ROOT)
    offenders = [
        f"line {n}: {line.strip()}"
        for n, line in enumerate(agent.read_text(encoding="utf-8").splitlines(), 1)
        if _WHEN_TO_INVOKE_HEADING.match(line)
    ]
    assert not offenders, (
        f"{rel} has a `## When to invoke` body heading. Agent routing ('when to "
        "delegate') belongs in the `description` frontmatter, not the body - the "
        "body is the agent's system prompt (Anthropic subagent contract). Move "
        "triggers/examples to `description`; keep only runtime constraints in the "
        "body. See CONTRIBUTING.md 'Agent format'. Offending:\n  "
        + "\n  ".join(offenders)
    )


@pytest.mark.parametrize(
    "agent", AGENT_FILES, ids=lambda p: str(p.relative_to(REPO_ROOT))
)
def test_no_redirect_dominated_routing_section_in_body(agent):
    """Broadens the ban past the literal `## When to invoke` heading (V-36): a
    `## Out of Scope` / `## Routing` section is the same banned routing content
    under a different name once its bullets are dominated by `-> use X`
    redirects - it just evades a heading-only regex. A section kept for a
    genuine non-routing reason (prose boundary note, no bullet majority
    redirecting elsewhere) is NOT flagged."""
    rel = agent.relative_to(REPO_ROOT)
    lines = agent.read_text(encoding="utf-8").splitlines()
    offenders = []
    for n, line in enumerate(lines):
        if not _REDIRECT_SECTION_HEADING.match(line):
            continue
        if _is_redirect_dominated(_section_body(lines, n)):
            offenders.append(f"line {n + 1}: {line.strip()}")
    assert not offenders, (
        f"{rel} has a routing section (`## Out of Scope`/`## Routing`) whose "
        "bullets are dominated by `-> use X` redirects - this is the banned "
        "routing content from a different heading (V-36); routing belongs in "
        "the `description` frontmatter, not the body. Remove the section (moving "
        "any missing redirect into `description`) or rewrite it as prose that is "
        "not a majority of skill/agent redirects. See CONTRIBUTING.md 'Agent "
        "format'. Offending:\n  " + "\n  ".join(offenders)
    )


# --- V-XX: a prohibition stated in `description` must also be stated in the BODY ---------------
#
# Claim-shaped, whitespace-normalized, whole-file: a negation, an authoring verb within a few
# words, and the object being denied. It protects the CLAIM, not one sentence, so rewording either
# half still passes and deleting the body half fails.
_AUTHORING_PROHIBITION = re.compile(
    # Both word orders, because both occur in this tree: verb-then-object ("never author
    # production source") and object-then-agent-noun ("NOT a code writer" - the exact clause that
    # was frontmatter-only in the measured incident).
    r"(?:never|not|no|must not|does not|do not|don'?t)[^.\n]{0,45}?"
    r"(?:"
    r"\b(?:author|authors|authoring|write|writes|writing)\b[^.\n]{0,60}?"
    r"\b(?:source|code|production|tests?|fix)\b"
    r"|"
    r"\b(?:source|code|production|test|doc|docs)\b[^.\n]{0,20}?\b(?:writer|author)\b"
    r")",
    re.IGNORECASE,
)
_FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n", re.S)


def _split_frontmatter(text: str) -> tuple[str, str]:
    """(frontmatter, body), each whitespace-normalized so a wrapped clause is one string."""
    m = _FRONTMATTER.match(text)
    fm, body = (m.group(1), text[m.end():]) if m else ("", text)
    return re.sub(r"\s+", " ", fm), re.sub(r"\s+", " ", body)


@pytest.mark.parametrize(
    "agent", AGENT_FILES, ids=lambda p: str(p.relative_to(REPO_ROOT))
)
def test_an_authoring_prohibition_in_description_is_repeated_in_the_body(agent):
    """THE guard for the observed breach. The frontmatter `description` is routing metadata the
    ORCHESTRATOR reads when deciding whether to delegate; the body is the system prompt the RUNNING
    agent reads. They have different readers. So a prohibition kept only in `description` is a
    prohibition the agent itself never sees - and the agent that took the refused-dispatch fallback
    and wrote a module's `__manifest__.py` was in exactly that position.

    Remaining false negatives, stated rather than hidden:
      1. Lexical. A prohibition phrased in a way this claim regex cannot see reads as absent in the
         body (a false POSITIVE, which is safe - it asks an author to state it plainly) and as
         absent in the description too (a false NEGATIVE, which is the real gap).
      2. Presence, not obedience. This proves the sentence is in the text the agent is handed. That
         it is followed is enforced by `hooks/block-coordinator-code-write.sh` - not a prose
         check.
      3. Scoped to AUTHORING prohibitions. A frontmatter-only prohibition of a different kind
         ("never runs git", "never spawns a subagent") is not covered here; the agent-role lint in
         `check_orchestration.py` covers the never-spawn/never-git pair for `role: leaf`.
    """
    fm, body = _split_frontmatter(agent.read_text(encoding="utf-8"))
    in_fm = [m.group(0) for m in _AUTHORING_PROHIBITION.finditer(fm)]
    if not in_fm:
        return
    assert _AUTHORING_PROHIBITION.search(body), (
        f"{agent.relative_to(REPO_ROOT)} states an authoring prohibition in its frontmatter "
        f"`description` ({in_fm[0][:120]!r}) but nowhere in its BODY. `description` is the "
        "launcher's routing listing and is never part of the running agent's system prompt, so "
        "the agent is never given this rule. Restate it in the body, in the second person, as a "
        "runtime constraint - keep the description clause too, it is what the router reads."
    )


def test_the_authoring_prohibition_detector_can_fail():
    """Red-before-green on crafted strings: a detector that can only ever say "clean" is worthless,
    and one defeated by a line wrap is worse."""
    assert _AUTHORING_PROHIBITION.search(
        "It is a spawner, NOT a code writer and NOT a leaf"
    ), "must catch the exact clause that was frontmatter-only in the measured incident"
    assert _AUTHORING_PROHIBITION.search("You never author production source.")
    assert _AUTHORING_PROHIBITION.search("This agent does\n   not write\n   application code.".replace("\n", " "))
    assert not _AUTHORING_PROHIBITION.search("You write the production code to green.")
    assert not _AUTHORING_PROHIBITION.search("Never run a git mutation yourself.")
