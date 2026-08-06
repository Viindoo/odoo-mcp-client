r"""Guard: two S9-adjacent hardening rules in git-toolkit's safety contract stay real, not just
narrated once and then left to drift out of the files that must act on them.

Business rules this protects:

1. **S9 carve-out (RESTORE-PRIMARY-TO-PRINCIPAL-CLEAN).** S9 forbids ANY mutation of the primary
   checkout. Taken literally that also forbids the one action that RESTORES S9 compliance when
   the primary checkout has somehow acquired uncommitted work - an operator reading S9 literally
   has no path back to a clean tree. The carve-out is a narrow, explicit exception: restore
   tracked files to HEAD and remove untracked files, nothing else - never move a branch ref, never
   switch branches, never commit - still gated on human confirmation (it invokes destructive-gate
   items 4/5), and requires a stated pre-flight proof the work exists elsewhere before anything is
   discarded. A carve-out that exists only in ``git-safety-contract.md`` but is invisible to
   ``git-operator.md`` (the agent that actually executes S9) fixes nothing operationally - that
   agent would still read its own "non-negotiable" prose and refuse. This test guards BOTH the
   contract text and the operator's own recognition of it.

2. **S11 positional self-check.** An executing agent must verify, BEFORE its first mutating
   command, that the path it is about to write resolves to the worktree its brief named - a cheap,
   mechanical ``git -C <path> rev-parse --show-toplevel`` comparison - rather than discovering the
   drift after files are already changed in the wrong checkout.

Each test is a STRUCTURAL check anchored to the named section/heading and the RULE it must
express, not a single literal sentence - a rewording that preserves the rule still passes;
deleting or neutering the rule fails. Prose assertions are matched against WHITESPACE-NORMALIZED
text (line wraps must not defeat the guard); code-line assertions are matched against the raw body
so the literal command stays pinned. git-toolkit's independence from any consumer plugin (no
Odoo/Viindoo naming) is already covered by the whole-provider scan in
``test_git_toolkit_independence.py`` and is not duplicated here.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLKIT = REPO_ROOT / "plugins" / "git-toolkit"

SAFETY_CONTRACT = TOOLKIT / "snippets" / "git-safety-contract.md"
GIT_OPERATOR = TOOLKIT / "agents" / "git-operator.md"
NESTING_PROTOCOL = TOOLKIT / "snippets" / "git-nesting-protocol.md"


# ---------------------------------------------------------------------------
# Structural helper - a heading-level-aware markdown section extractor. A
# section's body runs until the next heading whose level is <= its own, so a
# "### " subsection lookup correctly stops at the following "## " heading
# (test_commit_convention_gate.py's single-marker splitter cannot express
# that - S9 has nested "### " subsections other tests here must not swallow).
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^(#{2,6})\s+(.*)$")


def _headings(text: str) -> list[tuple[int, str, int]]:
    out: list[tuple[int, str, int]] = []
    for i, line in enumerate(text.splitlines()):
        m = _HEADING_RE.match(line)
        if m:
            out.append((len(m.group(1)), m.group(2).strip(), i))
    return out


def _section(text: str, prefix: str) -> str:
    lines = text.splitlines()
    headings = _headings(text)
    idx = next((k for k, (_, title, _) in enumerate(headings) if title.startswith(prefix)), None)
    assert idx is not None, (
        f"expected a heading starting with {prefix!r}; found: {[h[1] for h in headings]}"
    )
    level, _, start = headings[idx]
    end = len(lines)
    for lvl2, _, ln2 in headings[idx + 1:]:
        if lvl2 <= level:
            end = ln2
            break
    return "\n".join(lines[start + 1:end])


def _norm(s: str) -> str:
    """Collapse whitespace (incl. line wraps) so a phrase split across markdown line-wrap
    boundaries still matches a plain substring/regex search."""
    return " ".join(s.split())


# ---------------------------------------------------------------------------
# Gap 1 - S9 carve-out
# ---------------------------------------------------------------------------

def test_s9_carve_out_is_narrow_and_gated():
    text = SAFETY_CONTRACT.read_text(encoding="utf-8")
    body = _section(text, "S9 carve-out")
    norm = _norm(body)

    assert "RESTORE-PRIMARY-TO-PRINCIPAL-CLEAN" in norm, (
        "the S9 carve-out must name its op RESTORE-PRIMARY-TO-PRINCIPAL-CLEAN so a brief can "
        "invoke it explicitly rather than the exception being inferred"
    )
    assert re.search(r"git reset --hard HEAD", body), (
        "the carve-out must restore tracked files to the committed state via an explicit command"
    )
    assert re.search(r"git clean -fd", body), (
        "the carve-out must remove untracked files via an explicit command"
    )
    assert re.search(r"never move[s]? a branch ref", norm, re.IGNORECASE), (
        "the carve-out must state it never moves a branch ref"
    )
    assert re.search(r"never switch(es)? branches", norm, re.IGNORECASE), (
        "the carve-out must state it never switches branches"
    )
    assert re.search(r"never commit", norm, re.IGNORECASE), (
        "the carve-out must state it never commits"
    )
    assert re.search(r"human confirmation is still required", norm, re.IGNORECASE), (
        "the carve-out must still require human confirmation - discarding uncommitted work stays "
        "gated, it is not a silent bypass of the destructive gate"
    )
    assert re.search(r"item[s]? 4 and 5", norm), (
        "the carve-out must point at destructive-gate items 4 (reset --hard) and 5 (clean -fd) "
        "rather than inventing a parallel, ungated exception"
    )
    assert re.search(r"pre-flight proof", norm, re.IGNORECASE), (
        "the carve-out must require a stated pre-flight proof the work exists elsewhere before "
        "anything is discarded"
    )
    assert "S1 backup" in norm and re.search(r"does not apply", norm), (
        "the carve-out must explain why the S1 backup branch does not substitute for the "
        "pre-flight proof (it cannot capture uncommitted work)"
    )


def test_s9_main_rule_points_at_the_carve_out():
    """S9's own opening paragraph must not read as an absolute, unqualified 'never' - it must
    point at the carve-out so a literal reading of S9 does not forbid the one action that restores
    S9 compliance in the first place (the exact contradiction this task closes)."""
    text = SAFETY_CONTRACT.read_text(encoding="utf-8")
    body = _section(text, "S9 - Worktree-always")
    norm = _norm(body)

    assert re.search(r"exception is the S9 carve-out", norm, re.IGNORECASE), (
        "S9's main rule must reference the carve-out below it, or an operator reading S9 in "
        "isolation will still conclude the restore-to-clean action is forbidden"
    )


def test_git_operator_recognizes_the_s9_carve_out():
    """The carve-out must be visible to the agent that actually executes S9 - git-operator.md -
    not just narrated in the contract snippet. This is the concrete fix for the observed failure:
    an operator refused a restore-to-clean request by reading S9 literally as unqualified."""
    text = GIT_OPERATOR.read_text(encoding="utf-8")
    norm = _norm(text)

    assert "S9 carve-out" in norm, (
        "git-operator.md must name the S9 carve-out - an agent that only inherits the unqualified "
        "'non-negotiable' S9 prose will still refuse the restore-to-clean op"
    )
    for marker in ("non-negotiable", "ERROR"):
        assert marker in text, f"expected git-operator.md to still contain {marker!r}"
    assert re.search(r"outside the S9 carve-out", norm) or re.search(
        r"exception is a brief whose op is exactly the S9 carve-out", norm
    ), (
        "git-operator.md's absolute S9 statements ('non-negotiable' / 'ERROR') must be qualified "
        "by the carve-out, not left as a blanket refusal"
    )


# ---------------------------------------------------------------------------
# Gap 2 - S11 positional self-check
# ---------------------------------------------------------------------------

def test_s11_positional_self_check_is_mechanical_and_executable():
    text = SAFETY_CONTRACT.read_text(encoding="utf-8")
    body = _section(text, "S11")
    norm = _norm(body)

    assert re.search(
        r"git -C <path-about-to-be-written> rev-parse --show-toplevel", body
    ), (
        "S11 must give the exact, ordinary git command an agent runs to resolve the repo root of "
        "the path it is about to write - not just a caution to 'be careful'"
    )
    assert re.search(r"BEFORE the first", norm, re.IGNORECASE), (
        "S11 must run BEFORE the first mutation, not as an after-the-fact check"
    )
    assert re.search(r"\bBLOCKED\b", norm), (
        "S11 must resolve a mismatch to a BLOCKED stop, not a warning that can be waved through"
    )
    assert re.search(r"worktree path the brief named", norm, re.IGNORECASE) or re.search(
        r"brief's worktree path", norm, re.IGNORECASE
    ), (
        "S11 must compare against the worktree path the BRIEF named - the whole point is catching "
        "drift back to a familiar path despite the brief naming the worktree correctly"
    )


def test_git_operator_runs_s11_before_first_mutation():
    """git-operator.md's own execution process must operationalize S11, not merely inherit it by
    reference - the observed failure was an agent editing files in the wrong checkout and only
    noticing afterwards, which is exactly the ordering S11 forbids."""
    text = GIT_OPERATOR.read_text(encoding="utf-8")
    body = _section(text, "Execution process")

    assert "S11" in body, (
        "git-operator.md's Execution process must name the S11 positional self-check as an "
        "explicit step, not leave it implicit"
    )

    # Split into numbered steps (a step's text may wrap across multiple lines - capture each
    # step's FULL text, not just its first line).
    starts = list(re.finditer(r"^\d+\.\s", body, re.MULTILINE))
    assert starts, "Execution process must be a numbered list"
    steps = []
    for i, m in enumerate(starts):
        end = starts[i + 1].start() if i + 1 < len(starts) else len(body)
        steps.append(body[m.start():end])

    s11_step_idx = next((i for i, s in enumerate(steps) if "S11" in s), None)
    execute_step_idx = next(
        (i for i, s in enumerate(steps) if re.search(r"Execute the op", s)), None
    )
    assert s11_step_idx is not None, "no numbered step names S11"
    assert execute_step_idx is not None, "no numbered step executes the op"
    assert s11_step_idx < execute_step_idx, (
        "the S11 positional self-check step must precede the step that executes the op - a "
        "self-check performed after the first mutation defeats its purpose"
    )
    assert re.search(r"[Bb]efore the first mutating command", _norm(steps[s11_step_idx])), (
        "the step naming S11 must itself state it runs before the first mutating command"
    )


# ---------------------------------------------------------------------------
# Lockstep - git-nesting-protocol.md's own restatement of S9 must not silently
# go stale relative to the carve-out it now qualifies.
# ---------------------------------------------------------------------------

def test_nesting_protocol_n5_stays_in_lockstep_with_the_carve_out():
    text = NESTING_PROTOCOL.read_text(encoding="utf-8")
    body = _section(text, "N5")
    norm = _norm(body)

    assert re.search(r"except the narrow S9 carve-out", norm, re.IGNORECASE), (
        "N5's 'what must NOT be touched' restatement of S9 must be qualified by the carve-out too "
        "- otherwise this file and git-safety-contract.md assert contradictory absolutes"
    )
