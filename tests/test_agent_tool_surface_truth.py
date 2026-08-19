"""Whole-tree guard: no file may tell an agent to use a launch lever the Agent tool does not have.

Measured ground truth. The Agent tool delivered to a subagent in this harness carries exactly
{description, isolation, model, prompt, subagent_type} and nothing else. A key the schema does not
declare is stripped silently before the call is evaluated - no `InputValidationError`, no feedback of
any kind. So an instruction to "pass `run_in_background: false`" or to "launch it blocking" is not
merely awkward: it is inert. The reader executes it, sees the launch behave asynchronously anyway,
and falls through to whatever the next live rung says - which is how a coordinator that must not
author source came to write a module's `__manifest__.py` itself.

This guard is about the LEVER, not about whether a subagent may dispatch. It may: every launch is
asynchronous, the launcher ends its turn, and it is woken with the child's result at any depth.

`Bash`'s `run_in_background` is a DIFFERENT tool's real parameter - it is how `odoo-instance-ops`
launches every long Odoo build before its foreground wait-log call - so this guard can never be a
blanket token ban.

Two rules, both over normalized whitespace so a claim split across wrapped lines is scanned as one
string, and both scoped to a SENTENCE rather than to line adjacency:

  R1 - a sentence naming `run_in_background` must also name `Bash` (the tool that has it), or state
       outright that the parameter does not exist. Nothing else admits it. There is deliberately NO
       path allowlist: a NEW Bash-scoped mention passes automatically, and a NEW Agent-scoped one
       fails, which is the behavior an allowlist would invert as soon as a file were added to it.
  R2 - the capability can also be asserted without ever naming the parameter ("launch it blocking",
       "a blocking switch"). Those phrasings are banned outright unless the same sentence denies the
       capability in the same breath.

STATED FALSE NEGATIVES - this is a LEXICAL guard and cannot be anything else:
  1. A phrasing neither list anticipates ("hand it the synchronous flag", "wait on the child in
     place") escapes both rules. That is the honest limit; the enforcing mechanism for the breach
     this protects against is `hooks/block-coordinator-code-write.sh` (the write gate), not this
     file.
  2. R2's denial carve-out is a claim check, not a semantic one: a sentence could in principle carry
     a denial marker AND an instruction. The markers are absolute by construction ("does not exist",
     "exposes no"), so such a sentence would contradict itself on its face.
  3. The corpus is `plugins/**` `.md`, `.sh` and `hooks.json`. Python under `generator/` is
     developer-facing tooling, not text an agent is handed, and is covered by
     `check_orchestration.py`'s own rule set instead.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGINS = ROOT / "plugins"

# Sentence split over already-normalized text: terminal punctuation followed by a space.
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?;])\s")

# R2's banned assertions of a capability that does not exist. Each is a phrasing that has actually
# appeared in this tree, or is the obvious next synonym of one that did.
_BANNED_CAPABILITY_PHRASES = (
    "blocking launch",
    "blocking switch",
    "launch it blocking",
    "launches blocking",
    "launch each teammate blocking",
    "launch it synchronously",
    "launches it synchronously",
    "blocking agent-tool launch",
    "block on that launch",
)

# The only thing that admits either rule: the same sentence says the capability is absent.
_DENIAL_MARKERS = (
    "does not exist",
    "no such parameter",
    "no such",
    "exposes no",
    "carries no",
    "has no ",
    "not a parameter",
    "deliberately absent",
    "do not re-add",
    "do not reintroduce",
    "ignore that instruction",
    "names a lever",
    "must not name a parameter",
    "never names a parameter",
)


def _corpus() -> list[Path]:
    files = list(PLUGINS.rglob("*.md")) + list(PLUGINS.rglob("*.sh"))
    files += list(PLUGINS.rglob("hooks.json"))
    return sorted(set(files))


def _sentences(path: Path) -> list[str]:
    """Whitespace-normalized sentences. Normalizing FIRST is the point: a claim wrapped across two
    source lines is one string here, so a guard cannot be defeated by a line break."""
    flat = re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))
    return [s for s in _SENTENCE_SPLIT.split(flat) if s.strip()]


CORPUS = _corpus()


def test_corpus_is_not_empty():
    """Floor: a glob that resolves to nothing makes every assertion below pass vacuously."""
    assert len(CORPUS) > 50, f"corpus looks wrong - only {len(CORPUS)} files found under {PLUGINS}"


def _denies(sentence_low: str) -> bool:
    return any(marker in sentence_low for marker in _DENIAL_MARKERS)


def test_run_in_background_is_only_ever_attributed_to_the_bash_tool():
    """R1. The parameter is real on `Bash` and absent from the Agent tool. Every mention must make
    that attribution visible in the same sentence, or say the parameter does not exist - because a
    reader who meets it un-attributed will try it on the launch they are holding."""
    offenders = []
    for path in CORPUS:
        for sentence in _sentences(path):
            low = sentence.lower()
            if "run_in_background" not in low:
                continue
            if "bash" in low or _denies(low):
                continue
            offenders.append(f"{path.relative_to(ROOT)}: {sentence.strip()[:180]}")
    assert not offenders, (
        "`run_in_background` is a parameter of the Bash tool ONLY - the Agent tool's schema in this "
        "harness does not declare it, and an undeclared key is stripped before the call is "
        "evaluated. A mention that names neither `Bash` nor the parameter's absence reads as an "
        "instruction to pass it to a launch, which is inert and pushes the reader to the next rung "
        "instead. Attribute it to Bash, or delete it:\n  " + "\n  ".join(offenders)
    )


def test_no_file_asserts_a_blocking_launch_capability():
    """R2. The capability can be claimed without ever naming the parameter, which is exactly how it
    survived the last correction: prose said "launch each teammate blocking" and the token-level
    check saw nothing. Ban the phrasings; admit one only where the same sentence denies it."""
    offenders = []
    for path in CORPUS:
        for sentence in _sentences(path):
            low = sentence.lower()
            hit = next((p for p in _BANNED_CAPABILITY_PHRASES if p in low), None)
            if hit is None or _denies(low):
                continue
            offenders.append(f"{path.relative_to(ROOT)}: [{hit}] {sentence.strip()[:180]}")
    assert not offenders, (
        "a blocking/foreground agent launch does not exist in this harness, so prose asserting one "
        "sends the reader to a dead rung. State the absence, or route to "
        "spawner-completion-contract.md R0 § Which fallback is yours:\n  " + "\n  ".join(offenders)
    )


# --------------------------------------------------------------------------- #
# The detectors must be able to fire - red-before-green on synthetic strings,
# so a future edit that guts them cannot look identical to a clean tree.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "text,should_flag",
    [
        ("Launch the teammate with run_in_background: false and read its result.", True),
        ("Run the build via Bash with run_in_background: true, then wait in the foreground.", False),
        ("The Agent tool has no such parameter, so run_in_background cannot be passed.", False),
        # The wrapped form: normalization must rejoin it before the sentence is scanned.
        ("Launch the teammate with\n   run_in_background:\n   false.", True),
    ],
)
def test_r1_detector_discriminates(tmp_path, text, should_flag):
    """Proves R1 can go BOTH red and green, including on a line-wrapped occurrence - a detector
    that only ever says "clean" is worthless, and one defeated by a newline is worse."""
    f = tmp_path / "probe.md"
    f.write_text(text, encoding="utf-8")
    flagged = any(
        "run_in_background" in s.lower() and "bash" not in s.lower() and not _denies(s.lower())
        for s in _sentences(f)
    )
    assert flagged is should_flag, f"R1 misjudged: {text!r}"


@pytest.mark.parametrize(
    "text,should_flag",
    [
        ("Its launch capability exposes a blocking switch, so it blocks on each teammate.", True),
        ("Use a blocking launch when you need the child's result.", True),
        ("A blocking launch does not exist here, so do not ask for one.", False),
        ("The Agent tool exposes no blocking launch at all.", False),
    ],
)
def test_r2_detector_discriminates(tmp_path, text, should_flag):
    """Proves R2's ban and its denial carve-out both actually discriminate."""
    f = tmp_path / "probe.md"
    f.write_text(text, encoding="utf-8")
    flagged = any(
        any(p in s.lower() for p in _BANNED_CAPABILITY_PHRASES) and not _denies(s.lower())
        for s in _sentences(f)
    )
    assert flagged is should_flag, f"R2 misjudged: {text!r}"


# Both nested-spawn denial hooks are retired: `block-nested-background-spawn.sh` (which asserted
# BACKGROUNDING was the discriminator) and its successor `block-nested-agent-spawn.sh` (which
# asserted a subagent may not dispatch at all). Nested dispatch works and is the sanctioned shape,
# so neither file exists and neither name may be cited anywhere.
_RETIRED_HOOK_NAMES = ("block-nested-background-spawn", "block-nested-agent-spawn")


def test_no_retired_nested_spawn_hook_is_cited_anywhere():
    """A surviving citation of either retired hook is both a dead file reference and a restatement
    of a refuted premise - this repo's recurring defect is exactly the stale copy that outlives its
    definition."""
    offenders = [
        f"{p.relative_to(ROOT)}: {name}"
        for p in CORPUS
        for name in _RETIRED_HOOK_NAMES
        if name in p.read_text(encoding="utf-8")
    ]
    assert not offenders, (
        "a retired nested-spawn denial hook is still cited. Neither hook exists: a subagent may "
        f"dispatch, and the launcher is woken with the result once it ends its turn. Found: "
        f"{offenders}"
    )


def test_no_retired_nested_spawn_hook_file_survives():
    """Deletion is the fix, not disabling: a hook file left on disk is one `hooks.json` edit away
    from firing again."""
    survivors = [
        str(p.relative_to(ROOT))
        for p in (PLUGINS / "odoo-ai-agents" / "hooks").glob("*.sh")
        if any(name in p.name for name in _RETIRED_HOOK_NAMES)
    ]
    assert not survivors, f"a retired nested-spawn denial hook still exists on disk: {survivors}"
