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
  3. Read-only work (analysis/review/brainstorm, and any output that lands outside the git work
     tree) is named as exempt - the rule must not overreach into work that never touches git.
     The exemption is asserted as a CRITERION, never as a list of destination literals; see
     `test_intake_worktree_default_exempts_read_only_work` for the re-derivation.
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
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parent
PLUGIN = REPO_ROOT / "plugins" / "odoo-ai-agents"
INTAKE = PLUGIN / "skills" / "odoo-intake" / "SKILL.md"
GIT_DELEGATION_SNIPPET = PLUGIN / "snippets" / "git-delegation.md"

if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

# The `/tmp`-is-dead fact is OWNED by tests/test_no_tmp_scratch.py (GT3b Rule 1). Imported, not
# re-derived, so the prose criterion below and the source fact it rests on can never disagree.
from test_no_tmp_scratch import tmpdir_hits_in_tree  # noqa: E402


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


# ---------------------------------------------------------------------------
# The exemption clause: a CRITERION, not a destination list.
#
# Re-derivation (second time this assertion has been re-grounded, so the history matters):
#
#   Round 1 keyed on a project-relative `.odoo-ai/` literal. That convention was retired by the
#   two-axis state root (`state-root-resolution.md`), so the assertion was re-keyed onto
#   `$ODOO_AI_HOME` - the SSOT env var - PLUS a `/tmp` literal.
#
#   Round 2 (here) removes the `/tmp` half. The BEHAVIOUR being protected never changed:
#   worktree isolation exists to guard GIT-TRACKED files, so a deliverable that lands nowhere
#   git-tracked needs no dedicated worktree. `/tmp` was only ever ONE INSTANCE of "not
#   git-tracked", used as a stand-in for the category - and the plugin now writes no artifact
#   there at all, so naming it would re-legitimise a destination nothing uses (which is exactly
#   how the fragment-write pattern got sanctioned in the first place).
#
# The replacement is strictly STRONGER than the token pair it replaces, on three axes:
#   (a) it demands the CATEGORY (a git-tracking criterion, satisfied by any of a documented
#       synonym set) rather than two literals, so it covers destinations no enumeration lists
#       and survives a re-wording;
#   (b) it FORBIDS `/tmp` and `$TMPDIR`, turning a preference into an assertion; and
#   (c) that prohibition is underwritten by a SOURCE-DERIVED fact
#       (`test_exemption_may_omit_tmp_because_no_plugin_code_writes_there`), so the prose is
#       silent about `/tmp` because nothing writes there - not merely because prose was edited.
# ---------------------------------------------------------------------------

# Any ONE of these satisfies "expresses the git-tracking criterion". A synonym set, because the
# guard being replaced was itself a one-phrasing guard, and this one must not repeat that.
_GIT_TRACKING_CRITERION_SYNONYMS = (
    "git-tracked",
    "git tracked",
    "work tree",
    "working tree",
    "under git",
    "version-controlled",
    "version controlled",
)

# Destinations the clause must NOT name: proven dead by GT3b, and naming a dead scratch
# destination is what sanctioned the write pattern this whole change removes.
_FORBIDDEN_DESTINATIONS = ("/tmp", "/var/tmp", "$TMPDIR", "TMPDIR")

_EXEMPTION_RE = re.compile(r"\*\*Exempt:\*\*.*$", re.MULTILINE)


def _exemption_clause(text: str) -> str:
    """The `**Exempt:**` clause, located by content (never by line number)."""
    m = _EXEMPTION_RE.search(text)
    assert m, (
        "Hard rule 6 must carry an explicit `**Exempt:**` clause - the rule must not overreach "
        "into work that never touches git, and the carve-out has to be findable to be trusted."
    )
    return m.group(0)


def exemption_findings(clause: str) -> list[str]:
    """Every way `clause` fails the exemption contract. Empty list == compliant.

    A pure function of the clause text so the probe corpus below can prove it goes red for
    each distinct defect SHAPE without touching the real file.
    """
    findings = []
    if "$ODOO_AI_HOME" not in clause:
        findings.append(
            "does not name the $ODOO_AI_HOME state root - the canonical non-git-tracked "
            "destination, and the one every dispatched skill resolves"
        )
    if not any(syn in clause.lower() for syn in _GIT_TRACKING_CRITERION_SYNONYMS):
        findings.append(
            "states no git-tracking CRITERION (none of "
            f"{list(_GIT_TRACKING_CRITERION_SYNONYMS)}) - an enumeration of destinations is not "
            "a criterion: it silently excludes every destination it forgot to list"
        )
    for dead in _FORBIDDEN_DESTINATIONS:
        if dead in clause:
            findings.append(
                f"names the dead scratch destination {dead!r} - GT3b proves no plugin code "
                f"writes there, and naming one is how the fragment-write pattern was sanctioned"
            )
    return findings


def test_intake_worktree_default_exempts_read_only_work():
    """Hard rule 6 must carve out work that never touches git - by criterion, not by literal."""
    text = _text()
    low = text.lower()
    assert "read-only work" in low or "exempt" in low, (
        "The worktree-isolation rule must explicitly exempt read-only work (analysis, review, "
        "brainstorming) - it must not overreach into work that never touches git."
    )
    clause = _exemption_clause(text)
    findings = exemption_findings(clause)
    assert findings == [], (
        "odoo-intake's Hard-rule-6 `**Exempt:**` clause must state the git-tracking CRITERION "
        "and name $ODOO_AI_HOME, without naming any temp-dir destination. Findings:\n  - "
        + "\n  - ".join(findings)
        + f"\n\nClause read:\n{clause}"
    )


def test_exemption_may_omit_tmp_because_no_plugin_code_writes_there():
    """The source-derived half: the clause's SILENCE about `/tmp` is a fact, not a preference.

    Without this, dropping `/tmp` from the prose would be an unproven style change - and the
    next author could argue it back in. `TMPDIR` occurring zero times under `plugins/` is what
    makes the omission correct: there is no ambient temp destination left to exempt. The scan
    itself is owned by tests/test_no_tmp_scratch.py (GT3b Rule 1) and imported here, so the two
    halves of this contract cannot drift apart.
    """
    hits = tmpdir_hits_in_tree()
    assert hits == [], (
        "the exemption clause is allowed to stay silent about temp dirs ONLY while no plugin "
        "code names one. TMPDIR is back under plugins/, so either remove it again or re-derive "
        "this exemption honestly:\n" + "\n".join(hits)
    )


# ---------------------------------------------------------------------------
# Probe corpus for the exemption contract - the committed red-before-green proof.
# MUST-CATCH shapes first, then the anti-brittleness controls that must stay green.
# ---------------------------------------------------------------------------

_EXEMPTION_MUST_CATCH = [
    (
        "re-adds `or /tmp`",
        "**Exempt:** read-only work, and any deliverable whose write is not git-tracked - the "
        "`$ODOO_AI_HOME` state root or `/tmp`.",
    ),
    (
        "drops $ODOO_AI_HOME",
        "**Exempt:** read-only work, and any deliverable that is not git-tracked.",
    ),
    (
        "bare enumeration, no criterion",
        "**Exempt:** read-only work, and deliverables confined to the `$ODOO_AI_HOME` state root.",
    ),
    (
        "names $TMPDIR instead of /tmp",
        "**Exempt:** read-only work, and any deliverable outside the working tree - the "
        "`$ODOO_AI_HOME` state root or `$TMPDIR`.",
    ),
    (
        "names /var/tmp as the workaround",
        "**Exempt:** read-only work, and any deliverable outside the working tree - the "
        "`$ODOO_AI_HOME` state root or `/var/tmp`.",
    ),
    (
        "criterion and state root both dropped",
        "**Exempt:** read-only work (recon, review, brainstorming).",
    ),
]

_EXEMPTION_MUST_NOT_CATCH = [
    (
        "criterion phrased as version-controlled",
        "**Exempt:** read-only work, and anything that is not version-controlled - the "
        "`$ODOO_AI_HOME` state root is the canonical such location.",
    ),
    (
        "criterion phrased as outside the working tree",
        "**Exempt:** read-only work, and any path outside the working tree - the "
        "`$ODOO_AI_HOME` state root is the canonical such location.",
    ),
    (
        "criterion phrased as under git",
        "**Exempt:** read-only work, and any deliverable with nothing under git to isolate; "
        "`$ODOO_AI_HOME` is the canonical such destination.",
    ),
]


@pytest.mark.parametrize(
    "shape,clause", _EXEMPTION_MUST_CATCH, ids=[s for s, _ in _EXEMPTION_MUST_CATCH]
)
def test_exemption_guard_catches_every_defect_shape(shape, clause):
    assert exemption_findings(clause), (
        f"the exemption guard accepted a {shape} clause: {clause!r}. The assertion it replaced "
        f"was a two-token check; the replacement must be stronger on every axis, not just one."
    )


@pytest.mark.parametrize(
    "shape,clause", _EXEMPTION_MUST_NOT_CATCH, ids=[s for s, _ in _EXEMPTION_MUST_NOT_CATCH]
)
def test_exemption_guard_accepts_every_compliant_rewording(shape, clause):
    assert exemption_findings(clause) == [], (
        f"the exemption guard rejected a compliant rewording ({shape}): {clause!r} -> "
        f"{exemption_findings(clause)}. A criterion guard that only accepts today's sentence is "
        f"just the old token guard with more steps."
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


# ---------------------------------------------------------------------------
# CS-C4: the new Phase-R recon persistence write is a STATE-ROOT write, so it rides the
# SAME Hard-rule-6 exemption as every other $ODOO_AI_HOME-confined deliverable - it must
# never become an argument for provisioning a worktree just to persist a findings file.
# ---------------------------------------------------------------------------


def test_recon_persistence_is_a_state_root_write_not_a_git_tracked_write():
    """Two facts must both hold: (1) intake's Phase-R persist instruction names the resolved
    `<ISOLATE_DIR>` literal - never a repo-relative path and never a bare `.odoo-ai/` literal -
    and (2) Hard rule 6's exemption clause still names `$ODOO_AI_HOME` (test_worktree_default_
    exempts_read_only_work already proves this half independently; re-asserted here as the
    OTHER half of the same contract so a future edit cannot break the pairing silently)."""
    text = _text()

    persist_match = re.search(
        r"write\s+their findings to `([^`]+)`", text,
    )
    assert persist_match, (
        "Could not locate the Phase-R persist-before-propose write instruction naming its "
        "target path."
    )
    target_path = persist_match.group(1)
    assert target_path.startswith("<ISOLATE_DIR>/"), (
        f"The Phase-R recon findings write must target the resolved <ISOLATE_DIR> literal, "
        f"never a repo-relative or bare .odoo-ai/ path; got: {target_path!r}"
    )
    assert not target_path.startswith(".odoo-ai/") and not target_path.startswith("./"), (
        "The Phase-R recon findings write must not use a bare project-relative literal."
    )

    assert "$ODOO_AI_HOME" in text, (
        "Hard rule 6's exemption clause must still name $ODOO_AI_HOME - the recon findings "
        "write rides this existing exemption rather than requiring its own."
    )
