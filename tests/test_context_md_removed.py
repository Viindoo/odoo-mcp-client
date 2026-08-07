"""Guard: project facts are RESOLVED by the ladder, never READ from a stored artifact.

THE RULE THIS PROTECTS
----------------------
Project facts - the Odoo series, the OSM profile, the module/addons scope, the interpreter, the
brand tokens, the doc languages - are acquired by the terminating precedence ladder in
`plugins/odoo-ai-agents/snippets/project-facts-resolution.md`: the dispatch brief, the declared
instance catalog, the checkout, the caller's own words, then ONE batched ask. Every rung is
observable and every rung terminates.

Nothing a running agent may be handed - skill, agent, command, snippet, doc, workflow, hook, shell
script, manifest, generated block - may instead point that agent at a STORED project-facts artifact:
not at the removed `context.md` / `context-bootstrap` / `odoo-onboarding` mechanism by name, and not
at a fresh one invented under a different name. Such a pointer breaks the ladder: the agent reads a
file that may not exist, gets nothing, and has no rung to fall to - so it either invents a series or
asks the caller for facts already sitting in the instance catalog. The failure is silent, which is
why it needs a guard rather than a review.

WHAT IS ENFORCED - EXACTLY, AND WHAT IS NOT
-------------------------------------------
An earlier version of this file promised the whole rule in prose while its pattern only spelled
`context.md` and `context-bootstrap`. A reviewer ran this module's own `artifact_references()`
against 11 constructed reintroductions and 8 of them walked straight through. So the two layers
below are stated as what they actually do, and `artifact_references()` - the function a reviewer
naturally reaches for - now runs BOTH of them, so probing the guard through its front door can
never again report less than the guard enforces.

**Layer 1 - the removed NAMES, robustly (`name_references`).** ENFORCED: the project-context file
(`context.md`) under any separator (`.` `_` `-` space, or none) and any case; the bootstrap step
(`context-bootstrap`, with or without an extension); the removed skill (`odoo-onboarding`,
`odoo-onboard`, any suffix) which also covers its directory as a path (`skills/odoo-onboarding/`).
Invisible characters (zero-width joiner/non-joiner/space, soft hyphen, word joiner, BOM, variation
selectors - every `Cf`/`Mn` codepoint) are DELETED before matching rather than enumerated, and a
name split across a line break by a wrap hyphen (`con-` newline `text.md`) is rejoined in a second
pass. NOT ENFORCED: a space-separated English "Odoo onboarding" is deliberately not a hit - that is
ordinary prose about a persona, and the removed skill is a slug.

**Layer 2 - the MECHANISM, under any name (`mechanism_references`).** This is the real fix: a
reintroduced facts cache called `project-context.md`, `facts.md`, or `environment-snapshot.json`
carries none of the removed names. ENFORCED are three co-occurrence shapes, each bounded by a
character window measured on the normalized text:

  M1 - a fact-bearing read of a stored artifact: a path rooted at the project state dir ending in a
       data-file basename, a read/persist verb near it, and a project-fact key joined to it by a
       DIRECTIONAL connector (artifact `for`/`->`/`contains` fact, or fact `from`/`in` artifact).
       The connector is what separates "reads X for odoo_version" from a brief that merely passes
       `odoo_version` next to an unrelated output path.
  M2 - an artifact that names itself as the facts store: either a noun phrase
       (`context`/`environment`/`facts` + `file`/`cache`/`snapshot`/`store`) or a state-dir path
       whose basename stem is one of those words, plus a read/persist verb. No fact key needed - the
       artifact has already declared what it holds.
  M3 - a fact-field harvest: two or more DISTINCT unambiguous fact keys clustered together with a
       read/persist verb and a state-dir anchor. This is the shape of the deleted snippet's "Extract
       and use as defaults" list, and it survives having every removed name stripped out.

NOT ENFORCED by Layer 2: a single mention of `series` or `profile` beside a state-dir path with no
directional connector (that is how the ladder and the brief legitimately talk); the declared
instance catalog `instances.toml`, which is rung 2 of the ladder and therefore an allowed source,
not a cache; and any cache whose prose names no fact, no facts-denoting artifact, and no fact-field
list at all. Those are the deliberate blind spots, and they are the price of the CURRENT tree being
clean with no path added to the allowlist for either legitimate file -
`snippets/project-facts-resolution.md` (which instructs agents about these very facts) and
`snippets/state-root-resolution.md` (which describes reading artifacts under the state dir) are
asserted clean DIRECTLY, by `test_the_ladder_and_state_root_snippets_are_not_flagged`.

WHY THE DETECTOR IS SHAPED THE WAY IT IS
----------------------------------------
Each choice answers a way a guard in this repo has actually gone green while the thing it guarded
came back:

1. WHOLE TREE, not a directory list. A guard scoped to where the defect was last seen misses where
   it returns. The scan walks the repo and reads every decodable text file - markdown, YAML, JSON,
   Python, shell - because the artifact was referenced from all of those.

2. LAYOUT NORMALIZED BEFORE MATCHING. Whitespace runs collapse to one space and invisible
   codepoints vanish, so a reference hidden by a re-wrap, an indented continuation, a tab-padded
   table cell, or a zero-width character all reduce to the one form the patterns match. An index map
   sends every normalized offset back to its raw offset, so findings still cite real line numbers.

3. NO SENTENCE SHAPE IN LAYER 1. The signal is the NAME, so it fires equally on a mermaid node
   label, a passing mid-sentence mention, a markdown table cell, a shell `[[ -f ... ]]` test, a
   `case` arm, and a generated tool-example line. Guards here have gone green by matching exactly
   the one sentence they were written against; Layer 1 has no sentence to match.

4. PRECISION INSTEAD OF PATH EXCLUSION. `skills/odoo-solution-design/references/brief-context.md` is
   an unrelated live file that merely ENDS in the same characters. It is not allowlisted - the
   lookbehind requires that the basename IS the artifact, so `brief-context.md`, `some_context.md`,
   and `a.context.md` are not hits and no path needs excluding. Layer 2 is held to the same
   standard: it was tightened until the current tree was clean, never widened by an allowlist.

5. A MINIMAL, REASONED, LAYER-SCOPED ALLOWLIST that is itself tested. Every entry states why the
   reference there is not a runtime instruction AND which layers it exempts, so an entry granted for
   a name cannot silently exempt a mechanism reintroduction in the same file.
   `test_every_allowlist_entry_still_earns_its_place` fails if an entry stops matching the layers it
   claims, so the allowlist can never quietly widen into the fix.

RED EVIDENCE - PERMANENT
------------------------
`test_every_reviewer_defeat_is_detected` replays all 11 reintroductions a reviewer constructed
against the pre-hardening detector (3 it caught, 8 it missed) and requires every one to be flagged.
`test_pre_change_project_context_instructions_are_flagged` replays the eight shapes the reference
actually took before removal. `test_deleted_master_content_is_flagged` and
`test_mechanism_is_detected_with_every_removed_name_stripped` pull the genuinely deleted files off
the `master` ref and require them flagged - the second after PROGRAMMATICALLY deleting every
Layer-1 name, so it proves Layer 2 alone. Those two skip (never fail) where `master` no longer
carries the blobs - a shallow CI clone, or any checkout after this change merges - which is exactly
why the embedded fixtures carry the permanent proof. A guard that has never been red is not
evidence.

Run: python -m pytest tests/test_context_md_removed.py -v
"""
from __future__ import annotations

import re
import subprocess
import unicodedata
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# Directories that are not repo content: version control internals, virtualenvs, caches, and
# vendored node modules. Excluding these is a scope statement about what the repository IS, not an
# exemption for any file that ships.
SKIP_DIRS = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
    }
)


# --- Layer 1: the removed names ------------------------------------------------------------------

# The removed artifact and the removed skill, by NAME, in every spelling a reference could take.
#
# `(?<![\w.-])` is the precision half: the basename must BE the artifact, so a longer name that
# merely ends the same way (`brief-context.md`, `some_context.md`, `a.context.md`) is not a hit.
# ` ?[._-]? ?` absorbs every separator spelling - a real dot, an underscore, a hyphen, a space, or
# nothing - which is also what a filename joined back across a line break reduces to.
# `(?![\w-])` keeps an unrelated token that merely STARTS the same way (`context.mdx`, `MD-5` after
# a sentence-final "context.") from counting.
#
# The skill alternative requires a slug separator (`odoo-onboarding`, `odoo_onboarding`,
# `skills/odoo-onboarding/SKILL.md`) and so does NOT fire on the English phrase "Odoo onboarding",
# which is legitimate prose about the intake persona. `[\w-]*` carries any suffix
# (`odoo-onboarding`, `odoo-onboarder`) without needing them enumerated.
_NAME_RE = re.compile(
    r"(?<![\w.-])(?:"
    r"context ?[._-]? ?md"  # the project-context file itself
    r"|context ?[._-]? ?bootstrap(?: ?[._-]? ?md)?"  # the step that made reading it mandatory
    r")(?![\w-])"
    r"|odoo[._-]onboard[\w-]*",  # the removed skill, and its directory as a path
    re.IGNORECASE,
)

# The historical basenames, as an explicit floor. `test_the_name_detector_covers_every_banned_name`
# proves `_NAME_RE` still matches each one, so widening the pattern can never drop a known name.
BANNED_BASENAMES = frozenset({"context.md", "context-bootstrap.md", "odoo-onboarding"})


# --- Layer 2: the mechanism, under any name ------------------------------------------------------

# Where stored project state lives, in every notation the repo uses for it. A bare anchor is only
# ever half a signal - every rule below pairs it with something else.
_ANCHOR = (
    r"<\s*(?:SHARE|ISOLATE)_DIR\s*>"
    r"|(?<![\w-])(?:SHARE|ISOLATE)_DIR(?![\w])"
    r"|\$ODOO_AI_(?:HOME|PROJECT_DIR|WORKTREE_DIR)"
    r"|(?<![\w/-])\.odoo-ai(?![\w])"
    r"|(?<![\w-])(?:SHARE|ISOLATE|project(?:'s)?|state)[ -](?:state[ -])?dir(?:ectory)?(?![\w-])"
    r"|Tier-2 (?:SHARE|ISOLATE)"
)
_ANCHOR_RE = re.compile(_ANCHOR, re.IGNORECASE)

# A concrete stored artifact: a state-dir-rooted path whose last element is a DATA file. Code files
# are not artifacts an agent harvests facts from, so the extension list is data formats only.
_STORED_FILE_RE = re.compile(
    r"(?:" + _ANCHOR + r")[\w<>./-]*?/(?P<base>[\w<>.@-]+)\.(?P<ext>md|json|jsonl|ya?ml|toml|txt)"
    r"(?![\w])",
    re.IGNORECASE,
)

# The declared instance catalog is rung 2 of the ladder - an ALLOWED source of series, profile,
# addons path and interpreter, not a cache of them. Reading it is the fix, not the defect, so it is
# excluded at the pattern level (one basename) rather than by allowlisting every file that cites it.
_LADDER_SOURCES = frozenset({"instances.toml"})

# A basename stem that declares the file holds project facts. Matched on the stem only, so
# `run-<id>.json`, `plan.md`, `findings.md`, `brand-tokens.json`, `glossary.yml` and the rest of the
# real Tier-2 inventory are unaffected.
_FACTS_STEM_RE = re.compile(
    r"(?:^|[-_.])(?:context|facts?|environment|env|onboarding|onboard|snapshot|probe)(?:$|[-_.])",
    re.IGNORECASE,
)

# A noun phrase that declares a stored facts artifact without naming a file at all - the shape of
# "read the project context snapshot under <SHARE_DIR>/". Zero occurrences in the current tree.
_FACTS_NOUN_RE = re.compile(
    r"(?<![\w-])(?:context|environment|facts?)[ -](?:file|files|cache|snapshot|store)(?![\w-])",
    re.IGNORECASE,
)

# Verbs that move bytes between an agent and a file. `resolve`, `derive`, `use` and `execute` are
# deliberately absent: they are the LADDER's own verbs, and counting them would flag the fix.
_ACT_RE = re.compile(
    r"(?<![\w-])(?:re-?reads?|re-?reading|reads?|reading|loads?|loaded|loading"
    r"|persist(?:s|ed|ing|ence)?|cach(?:e|es|ed|ing)|stores?|stored|storing"
    r"|writes?|written|writing|wrote|saves?|saved|extracts?|extracted|extracting)(?![\w-])",
    re.IGNORECASE,
)

# The facts that must now be resolved rather than cached. The first group are unambiguous keys; the
# second (`series`, `profile`) are also ordinary English words, so they count only inside M1's
# directional relation and never toward M3's distinct-key count.
_STRONG_FACT_RE = re.compile(
    r"(?<![\w-])(?:odoo_version|viindoo_profile|addons_path|verify_python"
    r"|brand_tokens_source|doc_languages)(?![\w-])",
    re.IGNORECASE,
)
_ANY_FACT_RE = re.compile(
    r"(?<![\w-])(?:odoo_version|viindoo_profile|addons_path|verify_python"
    r"|brand_tokens_source|doc_languages|series|profile)(?![\w-])",
    re.IGNORECASE,
)

# Directional connectors. FORWARD reads "artifact ... fact" (`reads X for odoo_version`); BACKWARD
# reads "fact ... artifact" (`odoo_version from X`). Requiring one is what keeps a dispatch brief
# that merely lists `ODOO_VERSION:` above an unrelated `CATALOG_PATH:` from counting - `with` is
# excluded for exactly that reason.
_FORWARD_RE = re.compile(
    r"(?<![\w-])(?:for|contains?|carr(?:y|ies)|holds?|provides?|records?|yields?|gives?"
    r"|key|keys|field|fields|value|values|defaults?)(?![\w-])|->|=>",
    re.IGNORECASE,
)
_BACKWARD_RE = re.compile(
    r"(?<![\w-])(?:from|in|inside|out of|via|under|recorded|stored|cached|persisted)(?![\w-])",
    re.IGNORECASE,
)

_GAP = 160  # max normalized chars between an artifact and the fact it is related to
_NEAR = 200  # max normalized chars between an artifact and the read/persist verb acting on it
_WIDE = 400  # max normalized span of an M3 fact-field harvest

# Codepoint categories that render as nothing: format controls (zero-width joiner/non-joiner/space,
# soft hyphen, word joiner, BOM) and non-spacing marks (variation selectors). Deleted before
# matching, so a name cannot be split by one. Normalizing the CLASS beats enumerating members.
_INVISIBLE_CATEGORIES = frozenset({"Cf", "Mn"})


# Each entry: repo-relative POSIX path -> (layers exempted, why a reference there is NOT a runtime
# instruction). Layers are scoped so an exemption earned by spelling a name cannot also hide a
# mechanism reintroduction in the same file. Nothing goes in here to make a scan pass.
_NAMES = "names"
_MECHANISM = "mechanism"

ALLOWLIST: dict[str, tuple[frozenset[str], str]] = {
    "CHANGELOG.md": (
        frozenset({_NAMES, _MECHANISM}),
        "release history - each entry describes an already-shipped release and is never handed to a "
        "running agent, so this is the one place the change is recorded rather than re-taught. It "
        "needs BOTH layers because the entries that introduced the mechanism describe it in full "
        "(a verify-environment cache of `verify_python` / `addons_path` written into the state dir)",
    ),
    "tests/test_state_migration.py": (
        frozenset({_NAMES}),
        "deliberate fixture - it plants an unrecognized top-level entry under a legacy state dir to "
        "prove the migration leaves it exactly where it is (never copied into SHARE, never into "
        "ISOLATE, never deleted). That is the case a user upgrading actually hits, and the coverage "
        "is only real while the fixture keeps using that name. NAMES only: the file instructs no "
        "agent to harvest facts, so a mechanism reintroduction there stays guarded",
    ),
    "tests/test_context_md_removed.py": (
        frozenset({_NAMES, _MECHANISM}),
        "this guard - the detector patterns and the permanent RED fixtures below have to spell the "
        "names AND reproduce the mechanism verbatim in order to test for them",
    ),
}


# --- normalization ------------------------------------------------------------------------------


def _normalize(raw: str, join_wraps: bool = False) -> tuple[str, list[int]]:
    """Flatten layout; return the text plus an index map back into `raw`.

    Three things happen: every invisible codepoint is deleted, every whitespace RUN collapses to a
    single space, and - when `join_wraps` - a hyphen that ends a line is dropped together with the
    break, rejoining a word a re-wrap split. The map sends each normalized character index back to
    its index in `raw`, which is what lets a finding cite a real line number after layout has been
    flattened.

    `join_wraps` is a SECOND pass rather than the only pass: rejoining also destroys a legitimately
    hyphenated word that happens to wrap, so both forms are scanned and their findings unioned.
    """
    out: list[str] = []
    index: list[int] = []
    i, n = 0, len(raw)

    def _absorbable(ch: str) -> bool:
        return ch.isspace() or unicodedata.category(ch) in _INVISIBLE_CATEGORIES

    while i < n:
        ch = raw[i]
        if unicodedata.category(ch) in _INVISIBLE_CATEGORIES:
            i += 1
            continue
        if ch.isspace():
            j = i
            while j < n and _absorbable(raw[j]):
                j += 1
            out.append(" ")
            index.append(i)
            i = j
            continue
        if join_wraps and ch == "-":
            j = i + 1
            saw_break = False
            while j < n and _absorbable(raw[j]):
                saw_break = saw_break or raw[j] == "\n"
                j += 1
            if saw_break:
                i = j
                continue
        out.append(ch)
        index.append(i)
        i += 1
    return "".join(out), index


def _stored_files(text: str) -> list[re.Match[str]]:
    """Every state-dir-rooted data-file reference, minus the ladder's own declared sources."""
    return [
        m
        for m in _STORED_FILE_RE.finditer(text)
        if f"{m.group('base')}.{m.group('ext')}".lower() not in _LADDER_SOURCES
    ]


# --- Layer 2 rules ------------------------------------------------------------------------------


def _m1_fact_bearing_read(text: str) -> list[tuple[int, str]]:
    """M1: a stored artifact, a read/persist verb, and a fact joined by a directional connector."""
    acts = [m.start() for m in _ACT_RE.finditer(text)]
    facts = list(_ANY_FACT_RE.finditer(text))
    hits: list[tuple[int, str]] = []
    for art in _stored_files(text):
        if not any(abs(a - art.start()) <= _NEAR for a in acts):
            continue
        for fact in facts:
            if art.end() <= fact.start() <= art.end() + _GAP:
                joined = _FORWARD_RE.search(text, art.end(), fact.start())
            elif fact.end() <= art.start() <= fact.end() + _GAP:
                joined = _BACKWARD_RE.search(text, fact.end(), art.start())
            else:
                continue
            if joined:
                start = min(art.start(), fact.start())
                end = max(art.end(), fact.end())
                what = f"M1 stored artifact read for a project fact: {text[start:end]}"
                hits.append((start, what))
                break
    return hits


def _m2_self_declaring_artifact(text: str) -> list[tuple[int, str]]:
    """M2: an artifact whose own name says it holds project facts, plus a read/persist verb."""
    acts = [m.start() for m in _ACT_RE.finditer(text)]
    artifacts = [(m.start(), m.group()) for m in _FACTS_NOUN_RE.finditer(text)]
    artifacts += [
        (m.start(), m.group())
        for m in _stored_files(text)
        if _FACTS_STEM_RE.search(m.group("base"))
    ]
    return [
        (start, f"M2 read/persist of a self-declared project-facts artifact: {found}")
        for start, found in artifacts
        if any(abs(a - start) <= _NEAR for a in acts)
    ]


def _m3_fact_field_harvest(text: str) -> list[tuple[int, str]]:
    """M3: two or more DISTINCT unambiguous fact keys, a read/persist verb, and a state anchor."""
    keys = sorted((m.start(), m.group().lower()) for m in _STRONG_FACT_RE.finditer(text))
    acts = [m.start() for m in _ACT_RE.finditer(text)]
    anchors = [m.start() for m in _ANCHOR_RE.finditer(text)]
    hits: list[tuple[int, str]] = []
    for i, (pos, _tok) in enumerate(keys):
        distinct: set[str] = set()
        for pos2, tok2 in keys[i:]:
            if pos2 - pos > _WIDE:
                break
            distinct.add(tok2)
        if len(distinct) < 2:
            continue
        if not any(abs(a - pos) <= _WIDE for a in acts):
            continue
        if not any(abs(x - pos) <= _WIDE for x in anchors):
            continue
        hits.append(
            (pos, "M3 fact-field harvest from the state dir: " + ", ".join(sorted(distinct)))
        )
    return hits


# --- detector front doors ------------------------------------------------------------------------


def _findings(raw: str, rules) -> list[tuple[int, str]]:
    """Run `rules` over both normalized forms of `raw`; return (line number, description) pairs."""
    seen: set[tuple[int, str]] = set()
    ordered: list[tuple[int, str]] = []
    for join_wraps in (False, True):
        normalized, index = _normalize(raw, join_wraps=join_wraps)
        for rule in rules:
            for pos, description in rule(normalized):
                line = raw.count("\n", 0, index[pos]) + 1
                key = (line, description)
                if key in seen:
                    continue
                seen.add(key)
                ordered.append(key)
    return sorted(ordered)


def _name_rule(text: str) -> list[tuple[int, str]]:
    return [(m.start(), m.group()) for m in _NAME_RE.finditer(text)]


def name_references(raw: str) -> list[tuple[int, str]]:
    """Layer 1 only: every removed NAME in `raw`, as (line number, matched text)."""
    return _findings(raw, (_name_rule,))


def mechanism_references(raw: str) -> list[tuple[int, str]]:
    """Layer 2 only: every stored-project-facts MECHANISM in `raw`, as (line number, why)."""
    return _findings(raw, (_m1_fact_bearing_read, _m2_self_declaring_artifact,
                           _m3_fact_field_harvest))


def artifact_references(raw: str) -> list[tuple[int, str]]:
    """The whole detector - BOTH layers. This is the front door; probing it can never under-report.

    Kept under its original name on purpose: a reviewer reached for this function to test whether
    the guard held, and at the time it answered for the name pattern alone. It now answers for
    everything the guard enforces."""
    return sorted(set(name_references(raw)) | set(mechanism_references(raw)))


def _text_files() -> list[Path]:
    """Every file in the repository, minus the non-content directories."""
    found: list[Path] = []
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        if SKIP_DIRS & set(path.relative_to(REPO_ROOT).parts):
            continue
        found.append(path)
    return sorted(found)


def _read_text(path: Path) -> str | None:
    """The file's text, or None when it is binary (nothing to instruct an agent with)."""
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def scan_tree() -> list[str]:
    """Every non-exempt finding in the repository, as `path:line: description`."""
    findings: list[str] = []
    for path in _text_files():
        rel = path.relative_to(REPO_ROOT).as_posix()
        exempt = ALLOWLIST.get(rel, (frozenset(), ""))[0]
        text = _read_text(path)
        if text is None:
            continue
        if _NAMES not in exempt:
            findings.extend(f"{rel}:{line}: {what!r}" for line, what in name_references(text))
        if _MECHANISM not in exempt:
            findings.extend(f"{rel}:{line}: {what!r}" for line, what in mechanism_references(text))
    return findings


# --- RED evidence: the 11 reintroductions a reviewer built against the pre-hardening guard --------
# Three were caught then; eight were not. All eleven are permanent fixtures so no hole can silently
# reopen. Invisible characters and the wrap hyphen are built from escapes, keeping this file ASCII.

_ZWJ = "\u200d"

REVIEWER_ATTEMPTS: dict[str, str] = {
    # --- the three the pre-hardening detector already caught ---
    "1. the filename inside a mermaid node label": (
        "```mermaid\ngraph TD\n  A[Round 0: read context.md] --> B[pin the series]\n```"
    ),
    "2. the filename upper-cased": "Round 0 - read CONTEXT.MD before you ask the caller anything.",
    "3. spaces around the dot": "Round 0 - read `<SHARE_DIR>/context . md` before asking.",
    # --- the eight it missed ---
    "4. a renamed artifact read for facts (no removed name anywhere)": (
        "## Round 0\n\nRound 0 reads `<SHARE_DIR>/project-context.md` for `odoo_version` and "
        "`profile`; fall back to the user-stated series."
    ),
    "5. a renamed artifact described as persisted by the removed skill": (
        "Resolve the module scope by the same mechanism as `<SHARE_DIR>/facts.md`, which "
        "odoo-onboarding persisted on first run."
    ),
    "6. the removed skill's prose, artifact unnamed": (
        "This skill persists the project's captured environment cache; every skill reads it "
        "silently at Round 0 and skips setup."
    ),
    # 7 is assembled from real master content in `test_deleted_master_content_is_flagged`; the
    # embedded copy below keeps the shape covered when the `master` blobs are unreachable.
    "7. the deleted snippet's harvest list with the filename gone": (
        "Resolve the SHARE dir, capture the printed absolute path, then `Read <captured>/` if\n"
        "present (e.g. `/home/user/.odoo-ai/projects/ab12cd34ef56`). Extract and use as defaults:\n"
        "  - `odoo_version` -> feeds `set_active_version`.\n"
        "  - `viindoo_profile` -> feeds `set_active_profile`.\n"
        "  - `verify_python` -> the interpreter for any odoo-bin run.\n"
        "  - `addons_path` -> the default addons path.\n"
    ),
    "8. a facts noun phrase over a bare state dir, no basename at all": (
        "Read the project context snapshot under `<SHARE_DIR>/` for odoo_version before you ask."
    ),
    "9. an underscore where the dot was": "Round 0 - read `<SHARE_DIR>/context_md` if present.",
    "10. a zero-width joiner inside the filename": (
        f"Round 0 - read `<SHARE_DIR>/context{_ZWJ}.md` if present."
    ),
    "11. the filename split by a wrap hyphen across a line break": (
        "Round 0 - read the project file `<SHARE_DIR>/con-\ntext.md` if present."
    ),
}

# The three above that the pre-hardening pattern already covered. Named so
# `test_every_reviewer_defeat_is_detected` can report separately on the eight that defeated it.
_ALREADY_CAUGHT = frozenset(
    k for k in REVIEWER_ATTEMPTS if k.split(".", 1)[0] in {"1", "2", "3"}
)


# --- RED evidence: verbatim pre-change content must be flagged -----------------------------------
# Each sample is the real text this change removed, copied unaltered from the pre-change tree. They
# are embedded rather than fetched from git so the proof stays portable (no machine, no remote, no
# branch that still holds the old content) and keeps working after the change is merged.

PRE_CHANGE_SAMPLES: dict[str, str] = {
    # 1. The deleted snippet - the SSOT that made reading the artifact a mandatory first step.
    "the deleted context-bootstrap snippet": """\
<!-- SSOT snippet. The single home for the "Round 0 - read project context before asking
     anything" step. Referenced (not copy-pasted) by every skill that needs odoo_version / profile /
     module list / instance URL. Edit here only; consumers point at
     ${CLAUDE_PLUGIN_ROOT}/snippets/context-bootstrap.md. Written by the odoo-onboarding skill. -->

# Round 0 - Context Bootstrap (read before you ask)

Before asking the caller for any project fact, **read what onboarding already captured.** A
human running `odoo-onboarding` persists `context.md` under the project's Tier-2 SHARE dir; treat
it as authoritative ground truth for this project. Do this first, silently, every run:
""",
    # 2. A G1-style "Round 0: read the context file" restatement in an agent body.
    "a Round 0 restatement in an agent body": """\
## Round 0 - Read context file + pin version

1. Read `<SHARE_DIR>/context.md` if present for `odoo_version` and `profile`; fall back to \
user-stated version, then manifest discovery (`${CLAUDE_PLUGIN_ROOT}/snippets/context-bootstrap.md`).
2. `set_active_version(odoo_version=<version>)` once (reachability probe).
""",
    # 3. Sample 2 re-wrapped so the filename itself straddles a line break - the exact evasion
    #    whitespace normalization exists to defeat. Layout is synthetic; the words are not.
    "the same restatement re-wrapped across the filename": """\
1. Read `<SHARE_DIR>/context.
   md` if present for `odoo_version` and `profile`; fall back to user-stated version.
""",
    # 4. A one-line passing mention inside a resolution chain - no heading, no imperative.
    "a one-line passing mention": """\
Resolve `odoo_version` and the module absolute path as in the icon/user-doc flow: brief `VERSION:` ->
`context.md` `odoo_version` -> `__manifest__.py` `version` (major >= 8) -> parent-dir regex
`(?:addons|tvtmaaddons)(\\d+)`; else `NEEDS_CONTEXT`.
""",
    # 5. A shell conditional - proof the scan is not markdown-only.
    "a shell conditional in an executable script": """\
_BRAND_SRC=""
if [[ -f "$_SHARE_DIR/context.md" ]]; then
    _BRAND_SRC="$(grep -iE '^[-*][[:space:]]*\\**brand_tokens_source' "$_SHARE_DIR/context.md")"
fi
""",
    # 6. A `case` arm - a bare basename with no path prefix and no surrounding prose at all.
    "a bare basename in a shell case arm": """\
        context.md | coordination | designs | plans | gap-analysis | \\
        documentation | survey | brl | brand-tokens.json | mockups | \\
        glossary.yml | cost-config.json)
            printf 'share\\n' ;;
""",
    # 7. A markdown table row - a cell, not a sentence.
    "a markdown table row": """\
| Component | Sub-path | Tier | Written by |
|-----------|----------|------|------------|
| Context snapshot | `.odoo-ai/context.md` | SHARE | `odoo-onboarding` skill |
""",
    # 8. A generated tool-example line - inside a BEGIN/END GENERATED TOOLS region, which is where
    #    the reference survived longest because it is emitted from the JSON surface SSOT.
    "a generated tool-example line": """\
<!-- BEGIN GENERATED TOOLS -->
- `set_active_profile(profile_name='<viindoo_profile from <SHARE_DIR>/context.md>')` - Pin tenant \
profile for the session so subsequent calls scope to one customer profile.
<!-- END GENERATED TOOLS -->
""",
}

# Names that merely share a suffix or prefix with the artifact, plus prose the ladder itself must be
# free to write. None is a stored project-facts artifact, so none may be flagged - otherwise the
# guard's own false positives would drive someone to allowlist a path, which is how a guard stops
# guarding.
NEAR_MISS_SAMPLES: dict[str, str] = {
    "a different reference file that ends in the same characters": (
        "`${CLAUDE_PLUGIN_ROOT}/skills/odoo-solution-design/references/brief-context.md`"
    ),
    "an underscore-prefixed basename": "Read `docs/module_context.md` for the module notes.",
    "a dotted-prefix basename": "See `state.context.md` in the vendor bundle.",
    "a longer extension": "The template lives at `context.mdx` in the site generator.",
    "sentence-final 'context.' followed by an unrelated token": (
        "Resolve the series before you lose the context. MD-5 digests are compared afterwards."
    ),
    "the plain English word in prose": (
        "Carry the caller's context forward; the brief is the first rung of the ladder."
    ),
    "'onboarding' as an English word, not the removed slug": (
        "Onboarding / Concierge - `odoo-intake` brainstorms when the ask is vague. Step 32 solves "
        "the permissions-onboarding problem, and a CS lead may onboard a new internal champion."
    ),
    "rung 2 reading the declared instance catalog": (
        "Reads an instance profile written by 40-instance-profile.sh from "
        "$ODOO_AI_HOME/instances.toml, generates a temporary odoo.conf with the correct "
        "addons_path, and starts odoo-bin."
    ),
    "a dispatch brief that passes a fact next to an unrelated output path": (
        "MODULE: <module technical name>\nODOO_VERSION: <concrete series, e.g. 17.0>\n"
        "SLUG: <short identifier for output paths>\n"
        "CATALOG_PATH: <SHARE_DIR>/documentation/<slug>/<module>/feature-catalog.jsonl "
        "(written by the cataloger)"
    ),
    "a continuation contract emitting a resolved fact alongside a run artifact": (
        "Report the files written, plus `<ISOLATE_DIR>/coding/<slug>-<date>/plan.md` and the "
        "`<ISOLATE_DIR>/worklog/<slug>/` entries, and emit `next: odoo-code-review` with "
        "`inputs: {odoo_version: <the run's resolved series>}`."
    ),
}

# Invisible codepoints an evader can drop inside the filename. Normalization deletes the CLASS
# (`Cf`/`Mn`), so this list is coverage for the class, not the enumeration the detector relies on.
INVISIBLE_CODEPOINTS = (
    "\u200b",  # zero width space
    "\u200c",  # zero width non-joiner
    "\u200d",  # zero width joiner
    "\u00ad",  # soft hyphen
    "\u2060",  # word joiner
    "\ufeff",  # zero width no-break space / BOM
    "\ufe0f",  # variation selector-16
)

# The two files that legitimately talk about these very facts and about reading artifacts under the
# state dir. Neither is allowlisted; the detector is required to be precise enough to leave them
# alone, and this is where that requirement is enforced.
LEGITIMATE_SNIPPETS = (
    "plugins/odoo-ai-agents/snippets/project-facts-resolution.md",
    "plugins/odoo-ai-agents/snippets/state-root-resolution.md",
)

# The files this change deleted, read off the `master` ref for realistic RED material.
DELETED_ON_MASTER = (
    "plugins/odoo-ai-agents/snippets/context-bootstrap.md",
    "plugins/odoo-ai-agents/skills/odoo-onboarding/SKILL.md",
)


def _master_blob(repo_path: str) -> str | None:
    """The pre-change content of `repo_path` from the `master` ref, or None when unreachable.

    Read with `git show` against the checkout the test is running in, so there is no machine-
    specific path to hardcode and nothing is ever written into the working tree. A shallow CI clone
    that carries only the PR branch, or any checkout made after this change merges, has no such
    blob - that returns None and the caller SKIPS instead of failing."""
    for ref in ("master", "origin/master"):
        try:
            done = subprocess.run(
                ["git", "-C", str(REPO_ROOT), "show", f"{ref}:{repo_path}"],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if done.returncode == 0 and done.stdout.strip():
            return done.stdout
    return None


# --- tests ---------------------------------------------------------------------------------------


def test_every_reviewer_defeat_is_detected():
    """RED proof: all 11 reintroductions built against the pre-hardening guard must be flagged.

    Eight of them walked straight through the name-only pattern: a renamed artifact read for facts,
    a renamed artifact the removed skill persisted, the skill's prose with no artifact named, the
    deleted harvest list with the filename gone, a facts noun phrase over a bare state dir, an
    underscore separator, a zero-width joiner, and a wrap-hyphen split. Any of them going
    undetected means that shape can come back."""
    undetected = [
        name for name, body in REVIEWER_ATTEMPTS.items() if not artifact_references(body)
    ]
    assert not undetected, (
        "the detector missed a reintroduction a reviewer already demonstrated - it would not stop "
        f"these shapes from returning: {undetected}"
    )
    previously_missed = sorted(set(REVIEWER_ATTEMPTS) - _ALREADY_CAUGHT)
    assert len(previously_missed) == 8, (
        "the eight reintroductions that defeated the name-only pattern must all stay fixtures; "
        f"found {len(previously_missed)}: {previously_missed}"
    )
    caught_by_mechanism = [
        name for name in previously_missed if mechanism_references(REVIEWER_ATTEMPTS[name])
    ]
    assert len(caught_by_mechanism) >= 5, (
        "Layer 2 is the real fix - the five mechanism-shaped reintroductions (a renamed artifact "
        "read for facts, one the removed skill persisted, the skill's prose, the deleted harvest "
        "list, and a facts noun phrase over a bare state dir) must be caught by mechanism "
        f"detection, not only by a name. Mechanism-detected: {caught_by_mechanism}"
    )


def test_pre_change_project_context_instructions_are_flagged():
    """RED proof: every pre-change form of the instruction must be detected.

    The samples span an SSOT snippet, an agent Round 0 step, a re-wrapped restatement, a passing
    mention, a shell conditional, a `case` arm, a table row, and a generated block - eight
    different shapes, one detector. A sample that goes undetected means the guard would have let
    that shape back in."""
    undetected = [
        name for name, body in PRE_CHANGE_SAMPLES.items() if not artifact_references(body)
    ]
    assert not undetected, (
        "the detector missed pre-change content it must flag - it would not stop these shapes "
        f"from returning: {undetected}"
    )
    assert len(PRE_CHANGE_SAMPLES) >= 8, (
        "the RED proof must keep covering every shape the reference took: an SSOT snippet, an "
        "agent Round 0 step, a re-wrapped restatement, a passing mention, a shell conditional, a "
        "case arm, a table row, and a generated block"
    )


@pytest.mark.parametrize("deleted", DELETED_ON_MASTER)
def test_deleted_master_content_is_flagged(deleted):
    """RED proof against the genuinely deleted files, not a hand-written approximation.

    The bodies are read from the `master` ref in memory - never checked out, never copied into the
    tree - and the artifact filename is then stripped PROGRAMMATICALLY, so the fixture is the real
    thing minus one token rather than something written to match the pattern."""
    body = _master_blob(deleted)
    if body is None:
        pytest.skip(f"pre-change blob master:{deleted} is unreachable from this checkout")
    assert artifact_references(body), f"the verbatim pre-change body of {deleted} must be flagged"
    filename_stripped = re.sub(r"context\.md", "", body, flags=re.IGNORECASE)
    assert artifact_references(filename_stripped), (
        f"{deleted} with the artifact filename stripped out must still be flagged - renaming the "
        "file is the cheapest way to bring the mechanism back"
    )


@pytest.mark.parametrize("deleted", DELETED_ON_MASTER)
def test_mechanism_is_detected_with_every_removed_name_stripped(deleted):
    """The load-bearing proof: Layer 2 alone must flag the deleted mechanism.

    Every Layer-1 name is deleted from the real master body first, and the result is asserted to
    carry NO name hit - so the flag that follows can only have come from mechanism detection. This
    is what makes the guard hold against a facts cache reintroduced under a brand-new name."""
    body = _master_blob(deleted)
    if body is None:
        pytest.skip(f"pre-change blob master:{deleted} is unreachable from this checkout")
    stripped = _NAME_RE.sub("", body)
    assert not name_references(stripped), (
        f"the name-stripped fixture for {deleted} still contains a removed name, so it cannot "
        "prove anything about Layer 2"
    )
    assert mechanism_references(stripped), (
        f"with every removed name deleted, {deleted} is still an instruction to harvest project "
        "facts from a stored artifact - Layer 2 must flag it, or renaming the artifact defeats the "
        "whole guard"
    )


def test_names_that_merely_resemble_the_artifact_are_not_flagged():
    """Precision, not path exclusion: a longer basename is a different file.

    `brief-context.md` is a live reference file in `odoo-solution-design`. If the detector counted
    it, the repair would be an allowlist entry - and an allowlisted path stops being guarded for
    every other reason too. The same standard applies to Layer 2: a dispatch brief passing
    `ODOO_VERSION` beside an unrelated output path, a continuation contract emitting a resolved
    fact, and rung 2 reading the declared instance catalog are all the FIX, not the defect."""
    misfired = {
        name: artifact_references(body)
        for name, body in NEAR_MISS_SAMPLES.items()
        if artifact_references(body)
    }
    assert not misfired, (
        "the detector flagged something that is not a stored project-facts artifact; a false "
        f"positive here pushes the next author toward allowlisting a path: {misfired}"
    )


@pytest.mark.parametrize("invisible", INVISIBLE_CODEPOINTS)
def test_invisible_characters_cannot_hide_the_artifact(invisible):
    """A codepoint that renders as nothing must not make the reference invisible to the guard.

    Normalization deletes the whole `Cf`/`Mn` class rather than a hand-kept list, so a codepoint
    nobody thought of is covered too."""
    hidden = f"Round 0 - read `<SHARE_DIR>/context{invisible}.md` if present."
    assert name_references(hidden), (
        f"an invisible codepoint (U+{ord(invisible):04X}) inside the filename hid it from the "
        "name detector"
    )


@pytest.mark.parametrize("snippet", LEGITIMATE_SNIPPETS)
def test_the_ladder_and_state_root_snippets_are_not_flagged(snippet):
    """The precision bar, enforced on the real files instead of bought with an allowlist entry.

    `project-facts-resolution.md` is the ladder that REPLACED the artifact - it names every fact
    the mechanism used to cache. `state-root-resolution.md` legitimately describes reading and
    writing artifacts under the project state dir. Both are the fix. If Layer 2 ever flags either,
    the answer is to tighten the detector, never to exempt the path - an exempted path stops being
    guarded for every other reason too."""
    path = REPO_ROOT / snippet
    assert path.is_file(), (
        f"{snippet} is missing - it is the SSOT this guard points every failure at, and its "
        "absence means project facts have no documented resolution ladder"
    )
    assert snippet not in ALLOWLIST, f"{snippet} must earn its clean scan, not be allowlisted"
    text = _read_text(path)
    assert text is not None, f"{snippet} is not decodable text"
    assert not artifact_references(text), (
        f"the detector flagged {snippet}, which is the mechanism's REPLACEMENT. Tighten the "
        f"detector; do NOT allowlist this path: {artifact_references(text)}"
    )


def test_no_file_in_the_repository_instructs_an_agent_to_read_a_project_context_file():
    """The rule itself, over the whole tree: project facts come from the ladder, not from a file.

    Scoping this to the directories where the reference last lived would miss wherever it comes
    back, so it reads every decodable text file in the repository."""
    findings = scan_tree()
    assert not findings, (
        "a stored project-facts artifact is back in the tree. Project facts are resolved by "
        "plugins/odoo-ai-agents/snippets/project-facts-resolution.md - the dispatch brief, the "
        "declared instance catalog, the checkout, the caller's words, then ONE batched ask. "
        "Replace the reference with the rung that answers the fact; do NOT add an allowlist "
        "entry.\n  " + "\n  ".join(findings)
    )


def test_no_file_or_directory_is_named_after_a_removed_artifact():
    """The artifact and the removed skill must not come back as real paths either.

    Checked on every file AND directory name, so the skill's directory (`skills/odoo-onboarding/`)
    counts even while it is still empty. A basename check, so `brief-context.md` and
    `module_context.md` stay unaffected."""
    named = sorted(
        path.relative_to(REPO_ROOT).as_posix()
        for path in REPO_ROOT.rglob("*")
        if not SKIP_DIRS & set(path.relative_to(REPO_ROOT).parts)
        and not path.is_symlink()
        and _NAME_RE.search(path.name)
        and path.relative_to(REPO_ROOT).as_posix() not in ALLOWLIST
    )
    assert not named, (
        "a removed project-context artifact or skill exists as a path again; the ladder in "
        f"snippets/project-facts-resolution.md replaces it: {named}"
    )


def test_the_name_detector_covers_every_banned_name():
    """The historical names are a floor the pattern may widen past but never below.

    Without this, a future rewrite of `_NAME_RE` could stop matching `context-bootstrap.md` and
    every test would still pass."""
    uncovered = sorted(name for name in BANNED_BASENAMES if not _NAME_RE.search(name))
    assert not uncovered, (
        f"the name detector no longer matches a name this change removed: {uncovered}"
    )


def test_every_allowlist_entry_still_earns_its_place():
    """An allowlist entry that no longer matches must be deleted, not left standing.

    A stale entry is an un-guarded path: the file keeps its exemption long after the reason for it
    is gone. Each entry must still exist AND still produce a finding in EVERY layer it exempts - so
    an exemption granted for spelling a name cannot quietly go on hiding a mechanism nobody checked
    for."""
    layer_probe = {_NAMES: name_references, _MECHANISM: mechanism_references}
    for rel, (layers, reason) in ALLOWLIST.items():
        path = REPO_ROOT / rel
        assert path.is_file(), (
            f"allowlisted path {rel} does not exist - delete the entry instead of leaving an "
            f"exemption behind (reason on record: {reason})"
        )
        text = _read_text(path)
        assert text is not None, f"allowlisted path {rel} is not decodable text"
        assert reason.strip(), f"allowlist entry {rel} must state why the reference is legitimate"
        assert layers, f"allowlist entry {rel} exempts no layer - delete it"
        assert layers <= set(layer_probe), f"allowlist entry {rel} names an unknown layer: {layers}"
        for layer in sorted(layers):
            assert layer_probe[layer](text), (
                f"allowlisted path {rel} no longer produces a {layer} finding - drop {layer} from "
                f"its entry so that layer guards the file again (reason on record: {reason})"
            )
