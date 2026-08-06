r"""Guard: the git-toolkit commit-convention gate (C6 inbound validation) is real, not advisory.

Business rule (the hole this closes): a caller may hand ``git-toolkit:git-ops`` an
already-composed ``commit-msg``. Before this gate, nothing checked that string against the repo's
DETECTED convention (C3, ``snippets/commit-convention.md``) and nothing stopped
``git-squash-push.md`` step 4 from running ``git commit -m "<commit-msg>"`` on an unvalidated,
possibly non-conforming, possibly unsigned string - the only "check" was a non-executable code
comment. C6 makes conformance BINDING on the literal string that reaches ``git commit``: detect,
match-or-rewrite, or STOP with ``NEEDS_CONTEXT(business-outcome)`` when neither a conforming
message nor a business outcome to rewrite from is available. C4 turns DCO sign-off from an
intention ("add -s when required", a comment) into a POST-condition an agent must verify after
committing. N6 (``git-nesting-protocol.md``) gains the missing enumerated STOP condition for a
non-conforming supplied message - previously only advisory prose in N5 ("a hint, never a
license"), never an actual gate. ``skills/git-ops/SKILL.md`` Step 6 states the same physics for the
front-door skill: a supplied message is input to validate, never output to pass through.

Each test below is a STRUCTURAL check anchored to the named section (C6 / C4 / N6 / Step 6) and
the RULE it must express, not a single literal sentence - a rewording that preserves the rule
still passes; deleting or neutering the rule fails. Every test here was proven capable of failing
for the right reason: the guarded content was temporarily removed, the test was re-run and
observed RED with the expected assertion message, then the content was restored and the test was
re-run and observed GREEN (see the implementer's report for the transcript).

git-toolkit independence (no Odoo/Viindoo naming) for the files these tests touch is already
covered by the whole-provider scan in ``test_git_toolkit_independence.py`` - not duplicated here.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLKIT = REPO_ROOT / "plugins" / "git-toolkit"

COMMIT_CONVENTION = TOOLKIT / "snippets" / "commit-convention.md"
SQUASH_PUSH = TOOLKIT / "snippets" / "git-squash-push.md"
NESTING_PROTOCOL = TOOLKIT / "snippets" / "git-nesting-protocol.md"
GIT_OPS_SKILL = TOOLKIT / "skills" / "git-ops" / "SKILL.md"


# ---------------------------------------------------------------------------
# Structural helpers - split markdown into {heading text: body until next
# same-level heading}, keyed by the FULL heading line (minus the marker), so
# callers match by prefix (``h.startswith("C6")``) rather than a brittle
# full-string equality that breaks on any wording tweak to the heading tail.
# ---------------------------------------------------------------------------

def _sections(text: str, marker: str = "## ") -> dict[str, str]:
    lines = text.splitlines()
    sections: dict[str, str] = {}
    current: str | None = None
    buf: list[str] = []
    for line in lines:
        if line.startswith(marker):
            if current is not None:
                sections[current] = "\n".join(buf)
            current = line[len(marker):].strip()
            buf = []
        else:
            buf.append(line)
    if current is not None:
        sections[current] = "\n".join(buf)
    return sections


def _find_section(sections: dict[str, str], prefix: str) -> str:
    heading = next((h for h in sections if h.startswith(prefix)), None)
    assert heading is not None, (
        f"expected a section whose heading starts with {prefix!r}; found headings: "
        f"{sorted(sections)}"
    )
    return sections[heading]


# ---------------------------------------------------------------------------
# C6 - inbound validation must be a real 3-outcome gate, grounded in C3
# detection, never a hardcoded/reinvented convention.
# ---------------------------------------------------------------------------

def test_c6_exists_and_names_stop_and_rewrite():
    text = COMMIT_CONVENTION.read_text(encoding="utf-8")
    sections = _sections(text, marker="## ")
    body = _find_section(sections, "C6")

    assert "C3" in body, (
        "C6 must ground detection in C3 (the existing detection protocol) - never reinvent or "
        "hardcode a separate convention check"
    )
    assert re.search(r"\bREWRITE\b", body), (
        "C6 must name the REWRITE outcome for a supplied message that mismatches the detected "
        "convention but has a recoverable business outcome"
    )
    assert "NEEDS_CONTEXT" in body, (
        "C6 must name the STOP outcome (NEEDS_CONTEXT) for when neither a conforming message nor "
        "a business outcome to rewrite from exists"
    )
    assert "business-outcome" in body, (
        "C6's STOP outcome must be parameterized as NEEDS_CONTEXT(business-outcome), matching "
        "the N6 self-check entry it feeds"
    )
    assert re.search(r"never commit a string[^.\n]*not validate", body, re.IGNORECASE), (
        "C6 must explicitly forbid committing an unvalidated string (the anti-passthrough clause)"
    )
    assert "hint" in body.lower(), (
        "C6 must state a caller-stated format preference is only a hint, never an override of "
        "the detected convention"
    )


# ---------------------------------------------------------------------------
# git-squash-push.md step 4: validation must run BEFORE `git commit`, in the
# SAME step, and the commit itself must sign off (DCO is now a hard -s, not a
# comment a worker can ignore).
# ---------------------------------------------------------------------------

def test_squash_push_validates_before_commit():
    text = SQUASH_PUSH.read_text(encoding="utf-8")
    steps = _sections(text, marker="### ")

    commit_steps = {h: b for h, b in steps.items() if "git commit" in b}
    assert commit_steps, "git-squash-push.md must contain a step that runs `git commit`"

    for heading, body in commit_steps.items():
        commit_line_match = re.search(r"^\s*git commit\b.*$", body, re.MULTILINE)
        assert commit_line_match, f"step {heading!r}: no literal `git commit` invocation line found"
        commit_idx = commit_line_match.start()

        ref_idx = None
        for marker in ("commit-convention.md", "C6"):
            idx = body.find(marker)
            if idx != -1 and (ref_idx is None or idx < ref_idx):
                ref_idx = idx
        assert ref_idx is not None, (
            f"step {heading!r} runs `git commit` but never references the C6 gate "
            "(commit-convention.md) anywhere in the same step"
        )
        assert ref_idx < commit_idx, (
            f"step {heading!r}: the C6/commit-convention.md reference must appear BEFORE the "
            f"`git commit` line in the same step (validation must run first) - found the "
            f"reference at offset {ref_idx} but `git commit` at offset {commit_idx}"
        )
        assert "-s" in commit_line_match.group(), (
            f"step {heading!r}: `git commit` must sign off (-s) so DCO is a binding action, not "
            "an optional trailing comment a worker can skip"
        )


# ---------------------------------------------------------------------------
# N6 - the brief self-check's enumerated STOP list must include the missing
# condition: a supplied commit message that fails the detected convention.
# ---------------------------------------------------------------------------

def test_n6_stops_on_nonconforming_message():
    text = NESTING_PROTOCOL.read_text(encoding="utf-8")
    sections = _sections(text, marker="## ")
    body = _find_section(sections, "N6")

    bullets = [b for b in re.split(r"\n(?=- )", body) if b.strip().startswith("- ")]
    stop_bullets = [
        b for b in bullets
        if re.search(r"supplied (commit )?message", b, re.IGNORECASE)
        and "NEEDS_CONTEXT" in b
    ]
    assert stop_bullets, (
        "N6's enumerated brief self-check list must include a STOP condition for a supplied "
        "commit message that fails the detected convention, returning NEEDS_CONTEXT - it must be "
        "an actual enumerated gate here, not just advisory prose elsewhere (e.g. N5)"
    )
    assert any("business-outcome" in b for b in stop_bullets), (
        "the N6 STOP condition must resolve to NEEDS_CONTEXT(business-outcome), matching C6"
    )


# ---------------------------------------------------------------------------
# C4 - sign-off must be stated as a POST-condition (verified after the
# commit), not merely an intention to add `-s` when required.
# ---------------------------------------------------------------------------

def test_dco_is_a_postcondition():
    text = COMMIT_CONVENTION.read_text(encoding="utf-8")
    sections = _sections(text, marker="## ")
    body = _find_section(sections, "C4")

    assert re.search(r"post-condition", body, re.IGNORECASE), (
        "C4 must state sign-off is a POST-condition, not just an intention to pass `-s`"
    )
    assert re.search(r"not an intention", body, re.IGNORECASE), (
        "C4 must explicitly contrast 'post-condition' against 'intention'"
    )
    assert "Signed-off-by" in body and "git log" in body, (
        "C4 must give the executable post-commit check for the Signed-off-by trailer "
        "(a `git log` query), not just describe the requirement in prose"
    )
    assert re.search(r"not DONE", body, re.IGNORECASE), (
        "C4 must state a commit created without the trailer is not DONE - i.e. it must be "
        "amended, not silently accepted"
    )


# ---------------------------------------------------------------------------
# skills/git-ops/SKILL.md Step 6 - the front-door skill states the same
# physics: a supplied message is input, never output.
# ---------------------------------------------------------------------------

def test_skill_step6_states_supplied_message_is_input_not_output():
    text = GIT_OPS_SKILL.read_text(encoding="utf-8")
    sections = _sections(text, marker="## ")
    body = _find_section(sections, "Step 6")

    low = body.lower()
    assert "input" in low and "output" in low, (
        "Step 6 must state a caller-supplied commit message is input to validate, never output "
        "to pass through unchanged"
    )
    assert "commit-convention.md" in body or re.search(r"\bC6\b", body), (
        "Step 6 must point at the C6 gate (commit-convention.md) for how the input is validated"
    )
