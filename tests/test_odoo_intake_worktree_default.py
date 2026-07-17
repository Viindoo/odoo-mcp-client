"""Guard: odoo-intake enforces worktree isolation as a UNIVERSAL git-safety default.

Business rule this protects: `odoo-intake` is the universal front door, and the NAMED
specialist workflows it routes to (`odoo-forward-port`, `odoo-git-rebase`,
`odoo-modules-upgrade`, PR-mode `odoo-code-review`) already provision their own dedicated
worktree/branch before touching a git-tracked file - so they never switch the principal
checkout off its branch. The gap this test guards: every OTHER path out of intake
(the Tier-4 ambiguous/unclassified brainstorm branch, the trivial inline-micro-plan
fast-path, and the Plan-Mode-exempt `odoo-code-review`/`odoo-debug` fast-path) must ALSO
be covered - a direct git-tracked write on the principal checkout from any of those paths
corrupts the working tree of any OTHER session sharing that branch.

Four things must hold in `skills/odoo-intake/SKILL.md`:
  1. A universal rule exists requiring worktree/branch provisioning via `git-toolkit:git-ops`
     before ANY dispatched skill/workflow writes to a git-tracked file, with the principal
     checkout named as never the target.
  2. The rule explicitly states it covers the ambiguous/unclassified/fast-path/inline path,
     not only the named multi-WI specialists.
  3. Read-only work (analysis/review/brainstorm, `$ODOO_AI_HOME`/`/tmp`-only output) is named as
     exempt - the rule must not overreach into work that never touches git.
  4. The concrete Plan Mode Procedure actually provisions the worktree BEFORE the
     Skill-tool dispatch step (ordering, not just a floating mention), and the mechanics are
     referenced from the existing SSOT (`snippets/git-delegation.md`) rather than restated -
     keeping this DRY with the idiom every other git-touching skill already uses.

This module intentionally uses robust substring/behavioral checks (not verbatim sentence
matching) so prose can be re-worded later without breaking the guard, as long as the
underlying contract survives.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN = REPO_ROOT / "plugins" / "odoo-ai-agents"
INTAKE = PLUGIN / "skills" / "odoo-intake" / "SKILL.md"
GIT_DELEGATION_SNIPPET = PLUGIN / "snippets" / "git-delegation.md"


def _text() -> str:
    return INTAKE.read_text(encoding="utf-8")


def _frontmatter_description(text: str) -> str:
    """Extract the YAML frontmatter `description:` block verbatim (guard boundary)."""
    m = re.search(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert m, "odoo-intake/SKILL.md must have a YAML frontmatter block"
    fm = m.group(1)
    m2 = re.search(r"^description:.*?(?=^\S|\Z)", fm, re.DOTALL | re.MULTILINE)
    assert m2, "odoo-intake/SKILL.md frontmatter must have a description field"
    return m2.group(0)


# ---------------------------------------------------------------------------
# 1 + 2 + 3: the universal default is declared, scoped to every path, and
# read-only work is carved out.
# ---------------------------------------------------------------------------


def test_intake_declares_universal_worktree_isolation_default():
    text = _text()
    low = text.lower()

    assert "worktree" in low and "git-toolkit:git-ops" in text, (
        "odoo-intake/SKILL.md must declare a rule requiring worktree provisioning via "
        "git-toolkit:git-ops before a git-tracked write - none found."
    )
    assert "principal checkout" in low, (
        "The worktree-isolation rule must explicitly name the principal checkout as the "
        "thing that must never be the target of a git-mutating dispatch."
    )
    # The rule must be framed as a DEFAULT/catch-all, not an opt-in or per-tier carve-out.
    assert re.search(r"catch-all\s+default", text, re.IGNORECASE), (
        "odoo-intake must frame worktree isolation as a catch-all DEFAULT that engages even "
        "when the work cannot yet be fully classified, not merely a rule for named specialists."
    )


def test_intake_worktree_default_covers_ambiguous_and_fastpath_routes():
    text = _text()
    low = text.lower()

    # The rule must name coverage of the fast-path / brainstorm / inline-micro-plan / and the
    # Plan-Mode-exempt review+debug fast-path - not just the named multi-WI specialists.
    assert "tier-4" in low or "brainstorm" in low, (
        "Worktree isolation must explicitly cover the ambiguous/Tier-4 brainstorm route."
    )
    assert "inline-micro-plan" in low, (
        "Worktree isolation must explicitly cover the trivial inline-micro-plan fast-path."
    )
    assert "odoo-code-review" in text and "odoo-debug" in text and (
        "hard rule 6" in low
    ), (
        "Worktree isolation must explicitly state it still applies to the Plan-Mode-exempt "
        "odoo-code-review/odoo-debug fast-path (which otherwise looks like it skips every gate)."
    )
    # It must not be scoped ONLY to the named forward-port/rebase/upgrade specialists -
    # those are called out as ALREADY covered (self-provisioning), which is a distinct claim
    # from "this rule only applies to them".
    assert "self-provision" in low or "already satisf" in low, (
        "The rule must distinguish specialists that already self-provision a worktree from "
        "the paths that still need intake to provision one itself."
    )


def test_intake_worktree_default_exempts_read_only_work():
    """Premise re-derived for the ~/.odoo-ai/ two-axis convention (state-root-resolution.md):
    Tier-2 ISOLATE is now the private per-worktree store and Tier-2 SHARE is deliberately
    cross-worktree, so the exemption can no longer key on a project-relative `.odoo-ai/`
    literal (that convention no longer exists). What the rule actually protects is unchanged -
    worktree isolation exists to guard GIT-TRACKED files, so any deliverable confined to the
    machine-global `$ODOO_AI_HOME` state root (either tier) or `/tmp` never needs a dedicated
    worktree, because nothing there is git-tracked to begin with. The re-derived assertion keys
    on `$ODOO_AI_HOME` (the SSOT env var for the state root) instead of the retired literal.
    """
    text = _text()
    low = text.lower()
    assert "read-only work" in low or "exempt" in low, (
        "The worktree-isolation rule must explicitly exempt read-only work (analysis, review, "
        "brainstorming) - it must not overreach into work that never touches git."
    )
    assert "$ODOO_AI_HOME" in text and "/tmp" in text, (
        "The exemption must name the $ODOO_AI_HOME state root and /tmp scratch output as out of "
        "scope for worktree isolation (nothing git-tracked to isolate) - under the new "
        "SHARE/ISOLATE convention this is expressed via $ODOO_AI_HOME, not a bare .odoo-ai/ literal."
    )


# ---------------------------------------------------------------------------
# 4: the concrete Plan Mode Procedure actually provisions BEFORE dispatch, and
# points at the existing SSOT rather than re-deriving the mechanics (DRY).
# ---------------------------------------------------------------------------


def test_plan_mode_procedure_provisions_worktree_before_dispatch():
    text = _text()
    proc_match = re.search(
        r"\*\*Procedure\*\* \(execute-skill that touches files\):\n(.*?)\n\n\*\*Red flags for Plan Mode\*\*:",
        text,
        re.DOTALL,
    )
    assert proc_match, "Could not locate the Plan Mode '**Procedure**' numbered list."
    procedure = proc_match.group(1)

    worktree_pos = procedure.lower().find("worktree isolation")
    dispatch_pos = procedure.lower().find("invokes the execute-skill via the")
    assert worktree_pos != -1, (
        "The Plan Mode Procedure must contain a numbered step that provisions worktree "
        "isolation, not just a mention elsewhere in the file."
    )
    assert dispatch_pos != -1, "Could not find the final Skill-tool dispatch step in the Procedure."
    assert worktree_pos < dispatch_pos, (
        "Worktree provisioning must be ordered BEFORE the Skill-tool dispatch step in the "
        "Plan Mode Procedure - provisioning after dispatch defeats the purpose."
    )
    assert "git-toolkit:git-ops" in procedure, (
        "The Procedure step must instruct invoking git-toolkit:git-ops to create the worktree."
    )


def test_worktree_mechanics_reference_ssot_snippet_not_restated():
    assert GIT_DELEGATION_SNIPPET.exists(), (
        "snippets/git-delegation.md (the repo's existing worktree-first / S9 SSOT) is missing - "
        "expected it to already exist as the canonical home for git delegation mechanics."
    )
    text = _text()
    assert "git-delegation.md" in text, (
        "odoo-intake must reference snippets/git-delegation.md as the SSOT for the worktree "
        "provisioning mechanics (DRY), rather than re-deriving the git-ops invocation contract."
    )
    # DRY guard: odoo-intake should not restate the S9 invariant name/definition inline -
    # it should point at the snippet. (git-delegation.md itself, which legitimately defines
    # S9, is a different file and is not scanned here.)


def test_intake_description_frontmatter_unchanged_by_worktree_default():
    """The worktree-isolation addition must be a BODY-only change - odoo-intake's
    description frontmatter is near the 1024-char routing budget and is guarded
    separately by test_skill_description_budget; this test asserts the specific
    phrases this change introduces do not leak into the frontmatter description."""
    text = _text()
    description = _frontmatter_description(text)
    for marker in ("worktree isolation", "git-toolkit:git-ops", "principal checkout", "Hard rule 6"):
        assert marker.lower() not in description.lower(), (
            f"Worktree-isolation addition leaked into the description frontmatter ({marker!r}); "
            "this must be a body-only edit."
        )
