"""Guard: every gate-reply string in the tree is one of the two declared sets, verbatim.

Business contract being protected: a gate reply is a word the USER TYPES. If the plugin advertises
`edit` and the runner only understands `refine:`, the user did exactly what they were told and
nothing happens. `snippets/planning-gate-contract.md` therefore declares exactly two reply sets and
says "Never invent a third set"; `snippets/vocabulary.md` is the cross-cutting index that renders
them. Both sets are READ FROM `snippets/vocabulary.md` below rather than hardcoded here, so this
test cannot drift away from the SSOT it enforces - change the snippet and this guard changes with
it. (Whether the snippet itself still agrees with `generator/skill_tool_deps.json` -> `vocabulary`
is a DIFFERENT contract, already owned by `tests/test_status_vocabulary.py`; not re-checked here.)

Why the whole tree, and not just `workflows/`. The 4.22.0 sweep normalized all 49 `gate:` values in
`workflows/*.yaml` and nothing else, because nothing measured anything else. Twelve non-conforming
reply strings survived in `commands/`, in a skill body, in the harness reference's worked example,
and in the front door's own plan gate. This guard measures every agent-facing file plus the
plugin's own top-level markdown.

Scope - what counts as a gate-reply STRING, and why the scoping matters more than the breadth.
A version of this test that flagged any slash-separated list would flag `yes / no` rubric answers,
`APPROVE / REQUEST_CHANGES` review verdicts, and every prose sentence that mentions a gate - and the
next maintainer would delete it, after which it protects nothing. So a candidate is extracted only
from a GATE SLOT, of which there are exactly five:

  1. a `gate:` key (the workflow schema's own field) - in a `.yaml` workflow, or quoted inside a
     YAML example fenced in a `.md`;
  2. a `Gate:` label opening a line - the rendered gate line of a plan template;
  3. a markdown table cell under a `Gate` column header - the per-phase tables in `commands/`;
  4. a parenthetical reply list inside a question put to the user - `... ? (a / b / c)`;
  5. an `Options:` label followed on the SAME line by the replies - the BRL engine's two gates as
     the harness reference states them. Same-line is the whole scoping: a bare `Options:` that
     introduces a lettered (a)/(b) choice on the lines BELOW it is not a reply set, and neither is
     the block form that renders one reply per line (`odoo-brl`'s own GATE 0 / GATE E screens).
     Those block forms are unmeasured by construction, not by accident - a multi-line extractor
     would have to guess where the block ends, and guessing is what makes a guard get deleted.

Prose that merely DESCRIBES a set (a backticked shorthand mid-sentence, `run-harness`'s driver-loop
comment "resume after approve/skip/cancel") is out of scope by construction: it is not in a slot.
So are yes/no answer rubrics and verdict enums. The scoping tests below prove all of that against
the real tree, in both directions, rather than asserting it.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
if str(PLUGIN) not in sys.path:
    sys.path.insert(0, str(PLUGIN))

from generator.check_orchestration import agent_facing_files  # noqa: E402

VOCABULARY = PLUGIN / "snippets" / "vocabulary.md"

# `- PLAN gate: `approve / refine: [feedback] / cancel`` - the SSOT rendering this test reads.
VOCAB_SET_RE = re.compile(r"^-\s+(?P<kind>PLAN|STEP)\s+gate:\s*`(?P<set>[^`]+)`\s*$", re.M)

# ---------------------------------------------------------------------------
# Slot extractors
# ---------------------------------------------------------------------------

# 1. A `gate:` key. In a .md the value must be QUOTED - that is what a YAML example looks like, and
#    it keeps an English sentence that happens to open "gate: the .pot tooling changes ..." out.
GATE_KEY_RE = re.compile(r"^\s*gate\s*:\s*(?P<v>\S.*?)\s*$")
# 2. A `Gate:` label opening a line (optionally behind a blockquote/list marker or a backtick).
GATE_LABEL_RE = re.compile(r"^\s*(?:[>\-*+]\s*)*`?Gate\s*:\s*(?P<v>[^`\n]+)")
# 3. Markdown table rows.
TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
# 4. A parenthetical reply list inside a question: a `?` earlier on the line, then `( ... / ... )`.
QUESTION_PAREN_RE = re.compile(r"\?[^()\n]*\((?P<v>[^()\n]*?/[^()\n]*?)\)")
# 5. An `Options:` label with the replies on the SAME line. Scoped to what FOLLOWS the label, never
#    the whole line: `... (~<LOC> LOC / <reason>). Options:` carries a slash BEFORE the label, and a
#    whole-line reading of it would manufacture a finding out of prose.
OPTIONS_LABEL_RE = re.compile(r"\bOptions\s*:\s*(?P<v>.*)$")
# ... and prefer the first backticked run inside that remainder, so `Options: `a / b / c` - a does X`
# is read as the reply set rather than as the set plus the sentence explaining it.
BACKTICKED_RE = re.compile(r"`([^`\n]+)`")

TRAILING_YAML_COMMENT_RE = re.compile(r"\s+#.*$")


def _declared_sets() -> dict[str, str]:
    """The two reply sets, read from the SSOT snippet instead of hardcoded here."""
    text = VOCABULARY.read_text(encoding="utf-8")
    sets = {m.group("kind"): m.group("set").strip() for m in VOCAB_SET_RE.finditer(text)}
    assert set(sets) == {"PLAN", "STEP"}, (
        "snippets/vocabulary.md must declare exactly a PLAN and a STEP gate reply set as "
        f"'- <KIND> gate: `<set>`' bullets - parsed {sorted(sets)}"
    )
    return sets


def _clean(value: str) -> str:
    value = TRAILING_YAML_COMMENT_RE.sub("", value.strip())
    return value.strip().strip('"').strip("'").strip("`").strip()


def _options(value: str) -> list[str]:
    return [part.strip() for part in value.split("/") if part.strip()]


def _is_reply_list(options: list[str]) -> bool:
    """A parenthetical is a GATE reply list, not an answer rubric, when it offers `cancel` - or
    opens with `yes`, the retired keyword, without being a plain yes/no question."""
    low = [o.lower() for o in options]
    if "cancel" in low:
        return True
    return low[0] == "yes" and "no" not in low


def gate_reply_candidates(text: str, *, is_yaml: bool):
    """Yield (slot, normalized_reply_set, line_no) for every GATE SLOT occupied in `text`."""
    gate_col = None
    for line_no, line in enumerate(text.splitlines(), 1):
        m = GATE_KEY_RE.match(line)
        if m and (is_yaml or m.group("v")[:1] in "\"'"):
            options = _options(_clean(m.group("v")))
            if len(options) >= 2:
                yield "gate-key", " / ".join(options), line_no
                continue

        m = GATE_LABEL_RE.match(line)
        if m:
            options = _options(_clean(m.group("v")))
            if len(options) >= 2:
                yield "Gate-label", " / ".join(options), line_no
                continue

        m = OPTIONS_LABEL_RE.search(line)
        if m:
            tick = BACKTICKED_RE.search(m.group("v"))
            options = _options(_clean(tick.group(1) if tick else m.group("v")))
            if len(options) >= 2:
                yield "Options-label", " / ".join(options), line_no
                continue

        m = QUESTION_PAREN_RE.search(line)
        if m:
            options = _options(_clean(m.group("v")))
            if len(options) >= 2 and _is_reply_list(options):
                yield "question-paren", " / ".join(options), line_no

        if TABLE_ROW_RE.match(line):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            lowered = [c.lower() for c in cells]
            if "gate" in lowered:
                gate_col = lowered.index("gate")
            elif gate_col is not None and gate_col < len(cells):
                options = _options(_clean(cells[gate_col]))
                if len(options) >= 2:
                    yield "table", " / ".join(options), line_no
        else:
            gate_col = None


def scanned_files() -> list[Path]:
    """Every agent-facing file, PLUS the plugin's own top-level markdown (README and friends) -
    a gate advertised on the front page misroutes a user exactly like one in a skill body."""
    files = set(agent_facing_files())
    files.update(p for p in PLUGIN.glob("*.md") if p.is_file())
    return sorted(files)


def _findings(files) -> list[str]:
    declared = set(_declared_sets().values())
    out: list[str] = []
    for f in files:
        text = f.read_text(encoding="utf-8")
        is_yaml = f.suffix in (".yaml", ".yml")
        for slot, reply_set, line_no in gate_reply_candidates(text, is_yaml=is_yaml):
            if reply_set not in declared:
                out.append(f"{f.relative_to(PLUGIN)}:{line_no}: [{slot}] {reply_set!r}")
    return sorted(set(out))


# ---------------------------------------------------------------------------
# The rule
# ---------------------------------------------------------------------------


def test_the_two_sets_are_read_from_the_ssot_snippet():
    """Premise: the SSOT parses, and yields two distinct non-empty sets. Without this, every
    conformance check below could pass against an empty allowlist."""
    declared = _declared_sets()
    assert len(set(declared.values())) == 2, f"the two sets must differ: {declared}"
    for kind, reply_set in declared.items():
        assert len(_options(reply_set)) >= 2, f"{kind} gate set is not a reply list: {reply_set!r}"
        assert reply_set.strip() == reply_set, f"{kind} gate set has stray whitespace"


def test_every_gate_slot_in_the_tree_carries_a_declared_reply_set():
    """A user who types exactly what a gate advertises must hit a branch that exists."""
    declared = _declared_sets()
    findings = _findings(scanned_files())
    assert not findings, (
        "a gate advertises reply keywords the runner does not implement - every gate slot must "
        f"carry one of the two declared sets VERBATIM ({declared['PLAN']!r} when the artifact can "
        f"be iterated on, {declared['STEP']!r} when the only choice is do-it or skip-it; SSOT: "
        "snippets/planning-gate-contract.md). An option with no equivalent is asked as a SEPARATE "
        "question - never as a third set:\n  " + "\n  ".join(findings)
    )


def test_the_scan_actually_sees_the_tree_s_gates():
    """Anti-vacuity: a detector that matched nothing would satisfy the rule above trivially.

    Floors are set well under today's real counts so adding gates never breaks CI, while a
    refactor that silently blinds an extractor does.
    """
    per_slot: dict[str, int] = {}
    for f in scanned_files():
        for slot, _set, _line in gate_reply_candidates(
            f.read_text(encoding="utf-8"), is_yaml=f.suffix in (".yaml", ".yml")
        ):
            per_slot[slot] = per_slot.get(slot, 0) + 1
    for slot, floor in (
        ("gate-key", 40),
        ("Gate-label", 3),
        ("table", 5),
        ("question-paren", 8),
        # The whole tree holds exactly TWO same-line `Options:` gates (the BRL engine's Gate 0 and
        # Gate E in the harness reference), so this floor IS the count rather than sitting under it.
        # Deliberate: it is the only value at which blinding the newest extractor still fails.
        ("Options-label", 2),
    ):
        assert per_slot.get(slot, 0) >= floor, (
            f"the {slot!r} extractor found {per_slot.get(slot, 0)} gates, under the floor of "
            f"{floor} - an extractor that stops matching makes this guard vacuous"
        )


# ---------------------------------------------------------------------------
# Mutation proofs - each slot must be able to fail, and to stop failing
# ---------------------------------------------------------------------------


def test_detector_flags_a_retired_reply_set_in_every_slot():
    """Red proof: one synthetic offender per slot, using the real retired strings 4.22.0 missed."""
    synthetic = (
        "## Phases\n"
        "\n"
        "| Phase | Skill | Gate |\n"
        "|---|---|---|\n"
        "| 1 - Synthesis | `odoo-discovery-summary` | yes / edit / cancel |\n"
        "\n"
        "```yaml\n"
        '    gate: "save / discard / cancel"\n'
        "```\n"
        "\n"
        "Gate: approve / refine: [your feedback] / deep-survey / cancel\n"
        "\n"
        "Save this profile? (yes / list to exclude)\n"
        "\n"
        "Shows the chunk plan. Options: approve / refine(chunk_size, version) / cancel\n"
    )
    found = {
        (slot, reply_set)
        for slot, reply_set, _line in gate_reply_candidates(synthetic, is_yaml=False)
    }
    assert found == {
        ("table", "yes / edit / cancel"),
        ("gate-key", "save / discard / cancel"),
        ("Gate-label", "approve / refine: [your feedback] / deep-survey / cancel"),
        ("question-paren", "yes / list to exclude"),
        ("Options-label", "approve / refine(chunk_size, version) / cancel"),
    }, f"one of the five slot extractors is blind: {sorted(found)}"

    declared = set(_declared_sets().values())
    assert all(reply_set not in declared for _slot, reply_set in found), (
        "premise: every synthetic string above must be non-conforming, or this proves nothing"
    )


def test_detector_is_silent_when_every_slot_carries_a_declared_set():
    """Green proof: the SAME four slots, filled with the declared sets, produce no finding - so the
    rule fails for the reply set, not merely because a gate slot exists."""
    declared = _declared_sets()
    clean = (
        "| Phase | Skill | Gate |\n"
        "|---|---|---|\n"
        f"| 1 - Synthesis | `odoo-discovery-summary` | {declared['PLAN']} |\n"
        "\n"
        "```yaml\n"
        f'    gate: "{declared["STEP"]}"   # approve = save the artifact; skip = do not save\n'
        "```\n"
        "\n"
        f"Gate: {declared['PLAN']}\n"
        "\n"
        f"Save this profile? ({declared['STEP']})\n"
        "\n"
        f"Shows the chunk plan. Options: {declared['PLAN']}\n"
    )
    candidates = list(gate_reply_candidates(clean, is_yaml=False))
    assert len(candidates) == 5, f"premise: all five slots must still be seen, got {candidates}"
    assert all(reply_set in set(declared.values()) for _s, reply_set, _l in candidates), (
        f"a tree of declared sets must produce no finding, got {candidates}"
    )


def test_a_trailing_yaml_comment_does_not_disguise_a_bad_set():
    """The workflows annotate their gates ("# approve = save the artifact"). A comment must never
    be able to hide a non-conforming value - nor make a conforming one look non-conforming."""
    good = list(gate_reply_candidates(
        '  gate: "approve / skip / cancel"   # approve = save; skip = do not save\n', is_yaml=True
    ))
    assert good == [("gate-key", "approve / skip / cancel", 1)], good
    bad = list(gate_reply_candidates(
        '  gate: "save / discard / cancel"   # approve = save the artifact\n', is_yaml=True
    ))
    assert bad == [("gate-key", "save / discard / cancel", 1)], bad


# ---------------------------------------------------------------------------
# Scoping proofs against the REAL tree - the legitimate non-gate uses stay unflagged
# ---------------------------------------------------------------------------


def test_prose_that_describes_a_gate_is_out_of_scope():
    """`run-harness`'s driver loop says "resume after approve/skip/cancel" - a description of the
    mechanism, not a prompt anyone answers. Premise first, then: it yields no candidate."""
    harness = PLUGIN / "skills" / "run-harness" / "SKILL.md"
    text = harness.read_text(encoding="utf-8")
    assert "approve/skip/cancel" in text, (
        "premise: run-harness's driver loop must still carry the unspaced prose form, otherwise "
        "this test proves nothing about scoping"
    )
    prose_lines = {
        line_no for line_no, line in enumerate(text.splitlines(), 1)
        if "approve/skip/cancel" in line
    }
    hit_lines = {line for _s, _set, line in gate_reply_candidates(text, is_yaml=False)}
    assert not (prose_lines & hit_lines), (
        "the driver loop's own comment is internal machinery - flagging it would get this guard "
        "deleted, after which it protects nothing"
    )


def test_yes_no_answer_rubrics_and_verdict_enums_are_out_of_scope():
    """`yes/no` scoring rubrics and `APPROVE/REQUEST_CHANGES` review verdicts are answer
    vocabularies, not gate replies. Premise first (they exist), then: zero candidates from them.

    `odoo-code-reviewer.md` is the sharp case: its rubric rows sit in a markdown TABLE and its
    verdict enum reads like a reply set, so an unscoped detector would flag both.
    """
    rubric = PLUGIN / "agents" / "odoo-code-reviewer.md"
    text = rubric.read_text(encoding="utf-8")
    assert re.search(r"\byes\s*/\s*no\b", text), (
        "premise: the reviewer rubric must still carry a yes/no answer enum, otherwise this test "
        "proves nothing about scoping"
    )
    assert list(gate_reply_candidates(text, is_yaml=False)) == [], (
        "a review verdict enum / yes-no rubric is not a gate reply set"
    )

    verdicts = PLUGIN / "skills" / "odoo-code-review" / "references" / "agent-prompts.md"
    verdict_text = verdicts.read_text(encoding="utf-8")
    assert re.search(r"\bAPPROVE\s*/\s*REQUEST_CHANGES\b", verdict_text), (
        "premise: the reviewer prompts must still carry the APPROVE/REQUEST_CHANGES verdict enum"
    )
    assert list(gate_reply_candidates(verdict_text, is_yaml=False)) == [], (
        "a review VERDICT the agent emits is not a gate REPLY the user types"
    )


def test_an_options_label_with_no_same_line_replies_is_out_of_scope():
    """`Options:` is the sharpest false-positive risk of the five slots, and the real tree holds
    the exact trap: `odoo-git-rebase`'s re-implement escape hatch ends a PROSE line with `Options:`
    and lists a lettered (a)/(b) choice below it - and that same line carries a `/` BEFORE the
    label. Read whole-line, it manufactures a two-option "reply set" out of `~<LOC> LOC` and a
    reason. Premise first (the line is still shaped that way), then: it yields no candidate.
    """
    triage = PLUGIN / "skills" / "odoo-git-rebase" / "references" / "rb-triage-table.md"
    text = triage.read_text(encoding="utf-8")
    trap = [
        line for line in text.splitlines()
        if re.search(r"Options\s*:\s*$", line) and "/" in line
    ]
    assert trap, (
        "premise: rb-triage-table.md must still end a slash-carrying prose line with a bare "
        "'Options:', otherwise this test proves nothing about scoping"
    )
    hits = [c for c in gate_reply_candidates(text, is_yaml=False) if c[0] == "Options-label"]
    assert not hits, (
        "a bare 'Options:' introducing a lettered choice on the lines below is not a reply set - "
        f"flagging it would be an unfixable accusation: {hits}"
    )


def test_the_options_extractor_is_not_evaded_by_backticks():
    """A reply set wrapped in backticks after the label must still be read - otherwise the way to
    silence this slot is to type one character. Red and green, one line each."""
    bad = list(gate_reply_candidates(
        "Options: `save / discard / cancel` - `save` writes the file\n", is_yaml=False
    ))
    assert bad == [("Options-label", "save / discard / cancel", 1)], bad
    declared = _declared_sets()
    good = list(gate_reply_candidates(
        f"Options: `{declared['PLAN']}` - `approve` writes the deliverables\n", is_yaml=False
    ))
    assert good == [("Options-label", declared["PLAN"], 1)], good


def test_a_gate_column_that_names_ci_gates_is_out_of_scope():
    """`Gate` is an overloaded word: the runbot parity matrix heads a column with it and lists CI
    gate NAMES (`flake8`, `/test_lint (Odoo CE)`) under it. Those are not reply sets."""
    checklist = (
        PLUGIN / "skills" / "odoo-modules-upgrade" / "references" / "runbot-parity-checklist.md"
    )
    text = checklist.read_text(encoding="utf-8")
    assert re.search(r"^\|\s*Gate\s*\|", text, re.M), (
        "premise: the parity checklist must still head a column with 'Gate', otherwise this test "
        "proves nothing about scoping"
    )
    assert list(gate_reply_candidates(text, is_yaml=False)) == [], (
        "a CI-gate applicability matrix carries gate NAMES, not gate REPLIES"
    )
