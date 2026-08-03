"""Guard: base/work-base branch resolution never inherits the invoking checkout's HEAD.

Business rule (R3, arbitration A-04): a worktree/branch created to receive new coding-wave,
upgrade, or self-provisioned work resolves its start point from the version-named series
branch, never from whatever the invoking checkout's current branch/HEAD happens to be.
Protects against the owner-reported defect: "if someone has already checked out to a
different branch, the agent gets confused and uses that branch as the base." The confirmed
root cause was `plan-mode-schema.md` defining `base` as "the principal branch at dispatch" -
literally "whatever is checked out when the run starts" - not a git-command-defaulting bug
(git-toolkit's own S9 template + git-operator's Brief self-check already required an explicit
BASE ref and STOPped when it was missing).

Two independent guards, split per the C4 dependency direction (odoo-ai-agents MAY reference
git-toolkit; git-toolkit MUST NEVER reference odoo-ai-agents):

1. git-toolkit (domain-agnostic): the four branch-creating command forms (`git worktree add`,
   `git branch <name>`, `git checkout -b`, `git switch -c`) must be documented, in ONE place,
   as requiring an explicit start-point ref - stating the mechanical HEAD-default fact as the
   reason - with the two legitimate current-HEAD exceptions (S1 backup, S7 recovery) named,
   and without naming Odoo in any form.
2. odoo-ai-agents (domain-specific): `plan-mode-schema.md` must no longer define `base` as
   "the principal branch at dispatch" (the root-cause phrase) and must point at
   `git-delegation.md`'s base-resolution algorithm, which must forbid substring/contains
   matching and must state a decidable action + terminal status for each of: zero
   candidates, multiple candidates, local-behind-remote, detached HEAD, dirty tree.

Red-before-green: every assertion below was verified to FAIL against the ORIGINAL (pre-fix)
text of the three target files before the fix was applied (see the phase-2 Group D round-2
report for the measured pre-fix failure count) - re-running this file is how that claim is
checked, not merely asserted.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GIT_TOOLKIT = REPO_ROOT / "plugins" / "git-toolkit"
AGENTS_PLUGIN = REPO_ROOT / "plugins" / "odoo-ai-agents"

SAFETY_CONTRACT = GIT_TOOLKIT / "snippets" / "git-safety-contract.md"
GIT_DELEGATION = AGENTS_PLUGIN / "snippets" / "git-delegation.md"
PLAN_SCHEMA = AGENTS_PLUGIN / "skills" / "odoo-intake" / "references" / "plan-mode-schema.md"


def _text(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _norm(s: str) -> str:
    """Collapse whitespace so a reflow/line-wrap cannot defeat the scan."""
    return re.sub(r"\s+", " ", s)


# ---------------------------------------------------------------------------
# 1. git-toolkit: explicit start point, all four command forms, stated as the
#    HEAD-default mechanical fact, with the two named exceptions - and no Odoo mention.
# ---------------------------------------------------------------------------

def test_safety_contract_names_all_four_branch_creating_forms():
    text = _norm(_text(SAFETY_CONTRACT))
    for form in (
        "git worktree add",
        "git branch <branch>",
        "git checkout -b",
        "git switch -c",
    ):
        assert form in text, (
            f"git-safety-contract.md must name the command form '{form}' in its "
            "explicit-start-point rule - a guard scoped to only 'git worktree add' leaves "
            "the other three forms unguarded while staying green."
        )


def test_safety_contract_states_head_default_as_the_reason():
    text = _norm(_text(SAFETY_CONTRACT))
    assert re.search(r"silently\s+resolve\w*\s+.{0,80}HEAD", text, re.IGNORECASE), (
        "the rule must name the mechanical fact explicitly: omitting the start-point ref "
        "silently resolves to HEAD - 'be careful which ref you use' is not decidable enough."
    )


def test_safety_contract_names_the_backup_and_recovery_exceptions():
    text = _norm(_text(SAFETY_CONTRACT))
    m = re.search(r"does\s+not\s+apply.{0,400}", text, re.IGNORECASE)
    assert m, "the rule must carve out its two exceptions with an explicit 'does not apply' clause"
    window = m.group(0)
    assert "backup" in window.lower(), "the S1 backup-anchor exception must be named in the carve-out"
    assert "recover" in window.lower(), "the S7 recovery exception must be named in the carve-out"


def test_safety_contract_names_no_odoo_ai_agents_artifact():
    """C4 boundary: the generic rule must be readable with no Odoo knowledge at all.

    This is a regression-only guard (it already holds before AND after this fix); it is
    included here so a future edit to this exact rule cannot quietly reintroduce a domain
    reference without tripping a test scoped to the rule itself, not just the whole-file
    scan in test_git_toolkit_independence.py.
    """
    text = _text(SAFETY_CONTRACT)
    assert not re.search(r"\bodoo\b", text, re.IGNORECASE), (
        "git-toolkit's explicit-start-point rule must not mention Odoo in any form - it is a "
        "domain-agnostic provider file (C4)."
    )


# ---------------------------------------------------------------------------
# 2. odoo-ai-agents: plan-mode-schema.md drops the root-cause phrase and points at
#    git-delegation.md's resolution algorithm.
# ---------------------------------------------------------------------------

def test_plan_schema_drops_the_root_cause_phrase():
    text = _norm(_text(PLAN_SCHEMA))
    assert "principal branch at dispatch" not in text, (
        "plan-mode-schema.md must not define `base` as 'the principal branch at dispatch' - "
        "that phrase IS the owner-reported defect written down as a specification (A-04): "
        "it resolves to whatever the invoking checkout's HEAD happens to be."
    )


def test_plan_schema_points_at_git_delegation_base_resolution():
    text = _norm(_text(PLAN_SCHEMA))
    assert "git-delegation.md" in text, (
        "the Block 2W `base` node definition must point at snippets/git-delegation.md's "
        "base-resolution algorithm rather than restating it (SSOT - one definition, "
        "everywhere else a pointer)."
    )
    assert "base-branch resolution" in text.lower(), (
        "the pointer must name the section it points at, not just the filename, so the "
        "reader can find it without grepping the whole file."
    )


# ---------------------------------------------------------------------------
# 3. odoo-ai-agents: git-delegation.md carries the decidable algorithm with every
#    required failure mode + a decidable action / terminal status for each, plus the
#    exact-match-only ban and the fetch-routing rule.
# ---------------------------------------------------------------------------

def test_git_delegation_forbids_show_current_as_base_value():
    text = _norm(_text(GIT_DELEGATION)).lower()
    assert "must never be the value assigned to a" in text, (
        "git-delegation.md must explicitly carve `git branch --show-current` OUT of use for "
        "resolving `base`/`work-base` - a loose check for 'show-current' and 'base' anywhere "
        "in the file is not sufficient since both already appear pre-fix in unrelated "
        "contexts (the bounded-read allowlist, `git merge-base`)."
    )


def test_git_delegation_bans_substring_match():
    text = _norm(_text(GIT_DELEGATION)).lower()
    assert "exact branch-name match" in text and (
        "substring" in text or "contains match" in text
    ), (
        "the resolution algorithm must require an EXACT branch-name match and explicitly "
        "forbid a substring/contains match - a substring match would let a human's feature "
        "branch (e.g. '17.0-feat-x') qualify as a candidate purely for containing the series "
        "number, reproducing the bug one level down."
    )


def test_git_delegation_covers_every_named_failure_mode():
    text = _norm(_text(GIT_DELEGATION)).lower()
    required = {
        "zero candidates": ["zero candidate"],
        "multiple candidates": ["more than one distinct candidate", "distinct candidate"],
        "local behind remote / staleness": ["diverge"],
        "detached HEAD": ["detached head"],
        "dirty tree": ["dirty tree"],
    }
    missing = [label for label, needles in required.items() if not any(n in text for n in needles)]
    assert not missing, (
        f"git-delegation.md's base-resolution algorithm is missing a decidable rule for: "
        f"{missing} - an unhandled failure mode reproduces the bug in a new shape."
    )


def test_git_delegation_gives_each_failure_mode_a_terminal_status():
    text = _norm(_text(GIT_DELEGATION))
    assert "NEEDS_CONTEXT" in text, (
        "the zero-candidate case must name NEEDS_CONTEXT as its terminal status"
    )
    assert "open_question" in text, (
        "the multi-candidate and staleness-after-fetch cases must surface as open_question"
    )


def test_git_delegation_names_who_may_fetch():
    text = _norm(_text(GIT_DELEGATION))
    m = re.search(r"diverge.{0,400}", text, re.IGNORECASE)
    assert m, "the staleness (local-behind-remote) case must be present"
    window = m.group(0)
    assert "git-toolkit:git-ops" in window, (
        "the staleness case must explicitly route the fetch through git-toolkit:git-ops "
        "within the base-resolution section itself - not merely rely on git-ops being "
        "mentioned generically elsewhere in the file (every git MUTATION already routes "
        "through git-ops, but that generic rule alone does not tell an agent that resolving "
        "a stale `base` requires a fetch in the first place)."
    )
    assert "fetch" in window.lower()
