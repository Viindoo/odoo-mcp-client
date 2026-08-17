"""ANTI-REGROWTH guards for the wave-layer removal.

The refactor these protect did five things. Each is a BEHAVIOUR, and each guard below is phrased
against the behaviour so that a future edit which deletes the mechanism fails, not merely one which
renames it:

1. The `wave` GROUPING layer is DELETED, not renamed. A plan is a flat DAG of work NODES joined by
   `depends_on`, and NOTHING groups nodes - no batch, no layer, no phase, no wave. (G1)
2. `odoo-coding` dispatches ONE `odoo-coder` COORDINATOR per work NODE, never per module. The
   module is a PROPERTY of a node (Odoo's install / test-selection / dependency unit), never the
   dispatch cardinality and never a tier of decomposition. (G4, G7)
3. Integration and cumulative regression are ORDINARY PLAN NODES. The driver keeps no between-X
   logic and no cadence; it consumes the plan and never re-derives a decision the plan made. (G2)
4. `nodes[].gate_tier` is DELETED. The tier is a TOTAL FUNCTION resolved at dispatch, with an
   EPHEMERAL CEILING for the one case where the driver itself composed a fresh-database brief. (G2, G8)
5. Dependency ORDER behaviour is PRESERVED everywhere it was real - only the word changed. (G6)

Guard-writing discipline this file follows, because this repo has a documented history of guards
that go green while missing every other phrasing:
  * scan the WHOLE tree, never one adjacent file;
  * NORMALISE WHITESPACE to single spaces before matching (markdown line-wrapping has produced
    false negatives here repeatedly);
  * strip markdown emphasis before matching (`**DONE** or SKIPPED` defeated a `DONE\\s+or` pattern);
  * SKIP FENCED CODE BLOCKS in any scan that would otherwise read a decoy example;
  * every guard carries an explicit INVERSION-REJECTION clause, not just a positive assertion;
  * allowlists are DATA files with a stated reason per entry, never inline literals, and a STALE
    entry (one whose file no longer matches) fails just as loudly as a missing one.

Coverage note - these guards deliberately do NOT restate what already exists elsewhere:
  * "ONE odoo-coder per (work) node" in `odoo-coding/SKILL.md` and in the orchestration SSOT
    -> `test_coder_coordinator_topology.py`;
  * "ONE node per iteration / never two dispatches in flight"
    -> `test_run_harness_hardrules.py::test_driver_dispatches_one_node_per_iteration_never_two_in_flight`;
  * "never open a PR on red" + "a verification node per repo"
    -> `test_run_harness_gate.py`;
  * the plan carries no concrete ref state -> `test_worktree_graph.py`;
  * the `approach_kind` enum's declaration sites agree -> `test_worktree_graph.py`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA = Path(__file__).resolve().parent / "data"
PLUGINS = REPO_ROOT / "plugins"
PLUGIN = PLUGINS / "odoo-ai-agents"

SKILLS = PLUGIN / "skills"
AGENTS = PLUGIN / "agents"
RUN_HARNESS = SKILLS / "run-harness" / "SKILL.md"
PLAN_SCHEMA = SKILLS / "odoo-intake" / "references" / "plan-mode-schema.md"
PLANNER = AGENTS / "odoo-planner.md"
CODER = AGENTS / "odoo-coder.md"
CODING = SKILLS / "odoo-coding" / "SKILL.md"
TEST_WRITING = SKILLS / "odoo-test-writing" / "SKILL.md"
HARNESS_DOC = PLUGIN / "docs" / "reference" / "workflow-harness.md"
PLANNING = SKILLS / "odoo-planning" / "SKILL.md"
MODULE_GRAPH = SKILLS / "_shared" / "odoo-module-graph.md"
UPGRADE_SKILL = SKILLS / "odoo-modules-upgrade" / "SKILL.md"
UPGRADE_DETAIL = SKILLS / "odoo-modules-upgrade" / "references" / "upg-phase-detail.md"
SURVEY_SKILL = SKILLS / "odoo-deep-survey" / "SKILL.md"
SURVEY_LENSES = SKILLS / "odoo-deep-survey" / "references" / "survey-lenses.md"
DEPS_JSON = PLUGIN / "generator" / "skill_tool_deps.json"
WORKFLOW_SCHEMA = PLUGIN / "workflows" / "_schema.md"
CHECK_WORKFLOWS = PLUGIN / "generator" / "check_workflows.py"


# ---------------------------------------------------------------------------
# Shared text helpers
# ---------------------------------------------------------------------------

def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _ws(text: str) -> str:
    """Collapse every whitespace run to ONE space - markdown wraps sentences mid-clause."""
    return re.sub(r"\s+", " ", text)


def _flat(text: str) -> str:
    """Whitespace-normalised, markdown emphasis and inline-code ticks removed.

    `**DONE** or SKIPPED` and `` `depends_on` `` must match the same pattern as the plain words.
    """
    return _ws(text).replace("*", "").replace("`", "").replace("_", "_")


_FENCE_RE = re.compile(r"^[ \t]*```.*?^[ \t]*```", re.S | re.M)


def _strip_fences(text: str) -> str:
    """Blank out fenced code blocks (a decoy heading/example inside a fence is not prose)."""
    return _FENCE_RE.sub("\n", text)


def _section(text: str, heading_re: str) -> str:
    """Return one markdown section: from its heading to the next heading of the same-or-higher level."""
    m = re.search(heading_re, text, re.M)
    assert m, f"section {heading_re!r} not found - the guard's anchor moved, fix the guard"
    level = len(re.match(r"#+", m.group(0)).group(0))
    rest = text[m.end():]
    nxt = re.search(r"^#{1,%d} " % level, rest, re.M)
    return rest[: nxt.start()] if nxt else rest


_SENTENCE_SPLIT = re.compile(r"(?<=[.;])\s+")


def _sentence_around(text: str, pos: int) -> str:
    """The single sentence/clause containing `pos`.

    Negation must be scoped to the CLAUSE that names the token: a `not` 300 characters away in an
    unrelated sentence must not launder a live re-introduction.
    """
    start = 0
    for m in _SENTENCE_SPLIT.finditer(text):
        if m.end() > pos:
            break
        start = m.end()
    end = len(text)
    m = _SENTENCE_SPLIT.search(text, pos)
    if m:
        end = m.start()
    return text[start:end]


def _json_array_span(text: str, key: str, before: int | None = None) -> str | None:
    """Return the raw `"<key>": [ ... ]` slice, bracket-matched (JSON-with-comments safe).

    `before` selects the LAST such array starting before that offset - a file may hold several
    `"nodes": [...]` examples and only the one the field declaration follows is the contract.
    """
    starts = [m.end() - 1 for m in re.finditer(r'"%s"\s*:\s*\[' % re.escape(key), text)
              if before is None or m.start() < before]
    if not starts:
        return None
    start = starts[-1]
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def _allowlist(name: str) -> list[tuple[str, str]]:
    """Parse a `path: reason` DATA file; returns [(path, reason)] with comments/blanks dropped."""
    path = DATA / name
    assert path.exists(), f"missing allowlist DATA file {path} - allowlists are data, never literals"
    out: list[tuple[str, str]] = []
    for lineno, raw in enumerate(_read(path).splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        assert ":" in line, f"{name}:{lineno}: entry must be `<path>: <reason>` - got {line!r}"
        head, reason = line.split(":", 1)
        out.append((head.strip(), reason.strip()))
    return out


# ===========================================================================
# G1 - the word ban
# ===========================================================================
#
# `wave` / `waves` in any case, word-bounded, INCLUDING hyphen compounds (`wave-13`, `spawner-wave`,
# `/odoo-run-wave`), underscore compounds (`wave_number`) and camelCase compounds (`waveId`). The
# hyphen alternative is spelled out separately because the design names it explicitly - it is
# subsumed by the first alternative, and keeping it documents the requirement.
_WAVE_RE = re.compile(
    r"(?<![A-Za-z0-9])[Ww][Aa][Vv][Ee][Ss]?(?![A-Za-z0-9])"
    r"|(?<![A-Za-z0-9])[Ww][Aa][Vv][Ee](?=[A-Z])"
    r"|(?<![A-Za-z0-9])[Ww][Aa][Vv][Ee]-"
)

_WAVE_SCAN_EXTS = {".md", ".yaml", ".yml", ".json", ".py", ".sh"}
# Release history is a record of what happened; it is not runtime prose and it never regrows.
_WAVE_SCAN_EXCLUDED_NAMES = {"CHANGELOG.md", "ROADMAP.md"}
_WAVE_SCAN_EXCLUDED_PARTS = {"__pycache__", ".venv", "node_modules", ".git", ".claude"}

# SSOT for the five senses a `wave_allowlist.txt` reason may name. The data file's header restates
# them for the reader; THIS dict is what the test enforces.
ALLOWED_SENSES = {
    "a": "development-milestone narration (a delivery round, never a plan-node grouping)",
    "b": "the WMS domain term 'wave picking' (a real Odoo warehouse feature)",
    "c": "the English idiom ('waved through', 'hand-waved', 'wave it through')",
    "d": "a legacy on-disk key or path that must still be READ for backward compatibility",
    "e": "guard subject - the token IS what an assertion bans, or that assertion's rationale/pattern",
}
_SENSE_RE = re.compile(r"^(?P<marks>(?:\([a-e]\))+)\s+(?P<text>\S.*)$")


def _wave_scan_files() -> list[Path]:
    files: list[Path] = []
    for root in (PLUGINS, REPO_ROOT / "tests", REPO_ROOT / "docs"):
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if not p.is_file() or p.suffix not in _WAVE_SCAN_EXTS:
                continue
            # Compare the REPO-RELATIVE parts: the checkout itself may live under a `.claude/`
            # worktree directory, and matching absolute parts would silently empty the scan.
            if _WAVE_SCAN_EXCLUDED_PARTS & set(p.relative_to(REPO_ROOT).parts):
                continue
            files.append(p)
    files += [p for p in REPO_ROOT.glob("*.md") if p.is_file()]
    return sorted({p for p in files if p.name not in _WAVE_SCAN_EXCLUDED_NAMES})


def _wave_hits() -> dict[str, list[str]]:
    hits: dict[str, list[str]] = {}
    for p in _wave_scan_files():
        rel = p.relative_to(REPO_ROOT).as_posix()
        for n, line in enumerate(_read(p).splitlines(), 1):
            if _WAVE_RE.search(line):
                hits.setdefault(rel, []).append(f"{rel}:{n}: {line.strip()[:120]}")
    return hits


def test_the_word_wave_never_regrows_outside_the_allowlist():
    """The `wave` GROUPING layer is DELETED, not renamed - so the WORD must not reappear.

    Behaviour protected: a plan is a flat DAG of work NODES joined by `depends_on` and nothing
    groups nodes. Every re-introduction of the vocabulary has, historically, arrived with the
    concept attached (`Wave N` headers, `approach_kind: wave`, `spawner-wave`, per-wave gates),
    so the token is banned outright and every legitimate survivor is DATA in
    `tests/data/wave_allowlist.txt` with a named sense.

    Fails if: any `*.md`/`*.yaml`/`*.json`/`*.py`/`*.sh` under `plugins/`, `tests/`, `docs/` or the
    repo-root markdown (CHANGELOG/ROADMAP excepted) grows the token in a file that is not
    allowlisted.
    """
    allowed = {path for path, _ in _allowlist("wave_allowlist.txt")}
    hits = _wave_hits()
    offenders = [line for rel, lines in sorted(hits.items()) if rel not in allowed for line in lines]
    assert not offenders, (
        "The retired `wave` grouping vocabulary reappeared. A plan is a flat DAG of work NODES "
        "joined by `depends_on`; nothing groups nodes - no batch, no layer, no phase, no wave. "
        "Say `node`, `dependency level` or `delivery round`, whichever you actually mean. If the "
        "occurrence is one of the five allowed senses, add it to tests/data/wave_allowlist.txt "
        "with that sense named.\n" + "\n".join(offenders)
    )


def test_the_wave_allowlist_is_data_with_a_named_sense_and_no_stale_entry():
    """The allowlist is DATA, every entry names an ALLOWED SENSE, and no entry outlives its text.

    An allowlist that accepts an unexplained path is a mute exemption; an allowlist that keeps a
    line for a file which no longer holds the token quietly re-opens that file to regrowth. Both
    are failures here.
    """
    entries = _allowlist("wave_allowlist.txt")
    assert entries, "wave_allowlist.txt must carry the live exemptions, not be emptied"
    hits = _wave_hits()

    bad_sense, missing_file, stale, dupes = [], [], [], []
    seen: set[str] = set()
    for path, reason in entries:
        if path in seen:
            dupes.append(path)
        seen.add(path)
        m = _SENSE_RE.match(reason)
        if not m or len(m.group("text")) < 20:
            bad_sense.append(f"{path}: {reason[:80]!r}")
            continue
        for letter in re.findall(r"\(([a-e])\)", m.group("marks")):
            if letter not in ALLOWED_SENSES:
                bad_sense.append(f"{path}: unknown sense ({letter})")
        if not (REPO_ROOT / path).exists():
            missing_file.append(path)
        elif path not in hits:
            stale.append(path)

    assert not dupes, f"duplicate allowlist entries (one line per path): {dupes}"
    assert not bad_sense, (
        "Every allowlist reason must OPEN with one or more parenthesised sense letters "
        f"{sorted(ALLOWED_SENSES)} followed by a real explanation:\n" + "\n".join(bad_sense)
    )
    assert not missing_file, f"allowlisted path does not exist: {missing_file}"
    assert not stale, (
        "STALE allowlist entries - these files no longer contain the token, so the exemption is "
        f"silently re-opening them to regrowth. Delete the line: {stale}"
    )


@pytest.mark.parametrize("sample", [
    "Wave 1 - the billing modules",
    "wave-13 files earn a budget entry",
    '"approach_kind": "wave"',
    "spawn_class: spawner-wave",
    "the odoo-wave git executor",
    "run `/odoo-run-wave` to advance",
    "NO per-WAVE stop",
    "between-wave integration",
    "wave_number is read from the ledger",
    "waveId groups the nodes",
    "the driver advances nodes in waves",
    "## Wave 3 (terminal lifecycle)",
])
def test_the_wave_word_ban_catches_every_regrowth_shape(sample):
    """Detector proof (MUST-CATCH): the pattern fires on every shape the vocabulary has taken.

    A word ban whose regex misses hyphen, underscore, camelCase or plural compounds is a guard that
    goes green while the concept walks back in under a slightly different spelling.
    """
    assert _WAVE_RE.search(sample), f"the wave word ban must catch {sample!r}"


@pytest.mark.parametrize("sample", [
    "the microwave test fixture",
    "a wavefront of requests",
    "shockwaves in the dependency graph",
])
def test_the_wave_word_ban_leaves_unrelated_words_alone(sample):
    """Detector proof (MUST-NOT-CATCH): the ban is word-bounded, not a substring sweep."""
    assert not _WAVE_RE.search(sample), f"the wave word ban must NOT catch {sample!r}"


# ---------------------------------------------------------------------------
# G1 - the STRUCTURAL half: nothing may group nodes, on either side of the schema
# ---------------------------------------------------------------------------

_NO_GROUPING_SENTENCE = re.compile(
    # `and` / `+` and `:` / `-` are both live spellings of the SAME sentence - match the CLAUSE,
    # not one file's punctuation, or the guard passes on the file it was written against only.
    r"nodes (?:and|\+) edges are the ONLY ordering statement a plan makes\s*[:-]?\s*no field, "
    r"header, annotation, or grouping construct may batch nodes together",
    re.I,
)
_EXHAUSTIVE_CLAUSE = re.compile(
    r"That list is EXHAUSTIVE and there is no field that groups, batches, layers, or orders nodes "
    r"other than depends_on",
    re.I,
)
_FIELD_SET_RE = re.compile(r"A node's serialized field set is exactly:(?P<fields>[^.]+)\.")
# Names a resurrected grouping layer would arrive under. `depends_on` is the ONLY ordering field.
_GROUPING_FIELD_NAMES = {
    "wave", "waves", "bundle", "level", "levels", "cohort", "tranche", "batch", "batch_of",
    "batch_id", "group", "grouping", "layer", "phase", "band", "stage",
}


def test_the_schema_states_that_nothing_may_group_nodes():
    """`nodes` + `edges` are the ONLY ordering statement a plan makes.

    Behaviour protected: the wave was a GROUPING construct. Deleting the word without stating the
    prohibition leaves the next author free to reinvent it under any other name, so the schema, the
    harness reference and the human-facing plan-approval gate must all carry the sentence - the gate
    especially, because it is the only reader of a RENDERED plan's shape.

    Fails if: the canonical no-grouping sentence is dropped or weakened at any of the three sites.
    """
    for label, path in (
        ("plan-mode-schema.md (the schema itself)", PLAN_SCHEMA),
        ("workflow-harness.md (the harness reference)", HARNESS_DOC),
        ("odoo-planning/SKILL.md (the human plan-approval gate)", PLANNING),
    ):
        assert _NO_GROUPING_SENTENCE.search(_flat(_read(path))), (
            f"{label} must carry the canonical no-grouping sentence: \"`nodes` and `edges` are the "
            "ONLY ordering statement a plan makes: no field, header, annotation, or grouping "
            "construct may batch nodes together.\" Without it, deleting the WORD `wave` leaves the "
            "GROUPING CONCEPT free to return under any other name."
        )


def test_the_node_field_list_is_exhaustive_and_identical_on_both_sides():
    """The node's serialized field set is EXHAUSTIVE and the two declaring files AGREE.

    Behaviour protected: the most dangerous regrowth is not a word, it is a serialized grouping
    FIELD (`bundle`, `level`, `cohort`, `tranche`, `batch_of`) added to ONE side of the schema. Set
    equality across `plan-mode-schema.md` and `workflow-harness.md` § 8.3 makes that impossible to
    land quietly, and the EXHAUSTIVE clause makes an unlisted field illegal rather than merely
    undocumented.

    Fails if: either file drops the EXHAUSTIVE clause, the two declared field sets diverge, a
    grouping-shaped name enters either set, or either file's serialized node EXAMPLE grows a key
    the declaration does not list.
    """
    declared: dict[str, set[str]] = {}
    for label, path in (("plan-mode-schema.md", PLAN_SCHEMA), ("workflow-harness.md", HARNESS_DOC)):
        flat = _flat(_read(path))
        assert _EXHAUSTIVE_CLAUSE.search(flat), (
            f"{label} must declare the node field list EXHAUSTIVE and state that no field groups, "
            "batches, layers or orders nodes other than `depends_on` - an open-ended field list is "
            "an invitation to re-add the grouping layer as a field."
        )
        m = _FIELD_SET_RE.search(flat)
        assert m, f"{label} must state 'A node's serialized field set is exactly: ...'"
        fields = {f.strip() for f in m.group("fields").split(",") if f.strip()}
        assert fields, f"{label} declares an empty node field set"
        declared[label] = fields

    a, b = declared["plan-mode-schema.md"], declared["workflow-harness.md"]
    assert a == b, (
        "The two declaring files disagree about the node's serialized field set. A field added to "
        "one side only is exactly how a grouping field lands without review.\n"
        f"  only in plan-mode-schema.md: {sorted(a - b)}\n"
        f"  only in workflow-harness.md: {sorted(b - a)}"
    )
    assert "depends_on" in a, "`depends_on` must remain a declared node field - it IS the ordering"
    intruders = sorted(a & _GROUPING_FIELD_NAMES)
    assert not intruders, (
        f"A grouping-shaped node field re-entered the schema: {intruders}. `depends_on` is the ONLY "
        "field that may order nodes; nothing may batch them together."
    )

    # The serialized EXAMPLES must not carry a key the declaration does not list. Both files hold
    # several `"nodes": [...]` blocks; the contract is the one the field declaration follows.
    for label, path in (("plan-mode-schema.md", PLAN_SCHEMA), ("workflow-harness.md", HARNESS_DOC)):
        raw = _read(path)
        anchor = raw.find("A node's serialized field set is exactly")
        span = _json_array_span(raw, "nodes", before=anchor if anchor >= 0 else None)
        assert span, f"{label} must keep a serialized `\"nodes\": [...]` example"
        keys = set(re.findall(r'"([\w-]+)"\s*:', span))
        extra = sorted(keys - a)
        assert not extra, (
            f"{label}'s serialized node example carries key(s) {extra} that the EXHAUSTIVE field "
            "declaration does not list - the example and the declaration must be the same contract."
        )


# ===========================================================================
# G2 - the harness does not re-derive a plan-owned decision
# ===========================================================================

# `gate_tier` as a NODE field, in every serialization shape it could take.
_NODE_GATE_TIER_PATTERNS = (
    ("node.gate_tier", re.compile(r"(?<!default_)\bnodes?\[?\]?\.gate_tier\b")),
    ('"gate_tier":', re.compile(r'"(?<!default_)gate_tier"\s*:')),
    ("gate_tier: as a serialized key", re.compile(r"(?m)^\s*-?\s*(?<!default_)gate_tier\s*:")),
)
# The THREE structurally distinct homes the token legitimately keeps.
_GATE_TIER_LEGAL_PATHS = {
    "plugins/odoo-ai-agents/workflows",              # WORKFLOW-PHASE gate_tier (a different field)
    "plugins/odoo-ai-agents/generator/check_workflows.py",
}
# A retirement mention ("a retired `nodes[].gate_tier` field", "a node carries NO `gate_tier`") is
# the guard prose, not the field.
_RETIREMENT_MARKER = re.compile(
    r"(?i)retired|deleted|removed|no longer|never author|must not|carries NO|schema violation|"
    r"not a field|there is no stored tier|nobody authors|is a total function|"
    r"total function resolved at dispatch"
)
_GATE_TIER_SCAN_EXTS = {".md", ".yaml", ".yml", ".json", ".py", ".sh"}


def _scan(text: str, patterns, exemption_re) -> list[str]:
    """Whole-file scan over ONE whitespace-normalised blob, with a sentence-scoped exemption.

    Markdown wraps a sentence across lines, so matching line by line produces false NEGATIVES
    (the clause is split) and false duplicates (a sliding window re-reports the same match). The
    file is therefore normalised into a single blob with an offset -> line map; the exemption (a
    negation / retirement clause) is scoped to the SENTENCE that names the token, so a `not` in an
    unrelated sentence cannot launder a live re-introduction.
    """
    lines = text.splitlines()
    starts: list[tuple[int, int]] = []
    parts: list[str] = []
    pos = 0
    for n, line in enumerate(lines, 1):
        s = _ws(line).strip()
        starts.append((pos, n))
        parts.append(s)
        pos += len(s) + 1
    blob = " ".join(parts)

    def _lineno(off: int) -> int:
        last = 1
        for st, n in starts:
            if st > off:
                break
            last = n
        return last

    out: list[str] = []
    for label, pat in patterns:
        for m in pat.finditer(blob):
            if exemption_re and exemption_re.search(_sentence_around(blob, m.start())):
                continue
            out.append(f"{_lineno(m.start())} [{label}]: "
                       f"{blob[max(0, m.start() - 60):m.end() + 60].strip()}")
    return sorted(set(out))


def _gate_tier_offenders() -> list[str]:
    offenders = []
    for p in sorted(PLUGIN.rglob("*")):
        if not p.is_file() or p.suffix not in _GATE_TIER_SCAN_EXTS:
            continue
        if "__pycache__" in p.parts:
            continue
        rel = p.relative_to(REPO_ROOT).as_posix()
        if any(rel == allow or rel.startswith(allow + "/") for allow in _GATE_TIER_LEGAL_PATHS):
            continue
        offenders += [f"{rel}:{hit}"
                      for hit in _scan(_read(p), _NODE_GATE_TIER_PATTERNS, _RETIREMENT_MARKER)]
    return offenders


def test_gate_tier_is_never_a_node_field():
    """`nodes[].gate_tier` is DELETED: the tier is a total function, not a stored value.

    Behaviour protected: with three claimed authors (planner, Phase P, driver) the stored tier was
    a three-way disagreement waiting to happen, and the driver's "NOT raw node.gate_tier" override
    kept the inversion alive in weaker form. Deleting the FIELD is what closes it - so no file may
    reintroduce it as a node field, in any serialization shape.

    Fails if: `node.gate_tier`, `nodes[].gate_tier`, `"gate_tier":` or a bare `gate_tier:` key
    appears anywhere under `plugins/odoo-ai-agents/` in a NON-retirement context and outside the
    workflow-phase field's own files.
    """
    offenders = _gate_tier_offenders()
    assert not offenders, (
        "`gate_tier` reappeared as a NODE field. The per-node tier is a TOTAL FUNCTION resolved at "
        "dispatch (`run-harness/SKILL.md` § Gate-tier resolution) from the registry default plus "
        "two runtime facts; there is no stored tier to author, override or hand-edit. Only three "
        "homes are legal: the registry key `default_gate_tier`, the `gate_log[].tier` RECORD, and "
        "the WORKFLOW-PHASE `gate_tier` in `workflows/`.\n" + "\n".join(offenders)
    )


def test_the_three_legal_gate_tier_homes_survive_the_deletion():
    """Inversion pair to the ban: an over-zealous purge must not take the three legal homes with it.

    Each is structurally distinct from the deleted node field, and each has a live reader:
    `default_gate_tier` is the registry input to the total function; `gate_log[].tier` is the
    RECORD of the resolved tier; the workflow-phase `gate_tier` is a pre-existing per-PHASE field
    validated by `check_workflows.py`.
    """
    deps = _read(DEPS_JSON)
    assert '"default_gate_tier"' in deps, (
        "the registry key `default_gate_tier` is the INPUT to the tier function - deleting it would "
        "leave the function with nothing to read"
    )
    harness_83 = _flat(_section(_read(HARNESS_DOC), r"^### 8\.3 "))
    assert re.search(r"gate_log.{0,120}tier", harness_83), (
        "`gate_log[].tier` (the RECORD of the resolved tier) must survive - it is the audit trail, "
        "never an input"
    )
    # The DECLARATION ROW, not merely a mention: a YAML example elsewhere in the file would keep a
    # bare-token assertion green while the field table itself had been renamed away.
    assert re.search(r"\|\s*`gate_tier`\s*\|\s*enum\s*\|", _read(WORKFLOW_SCHEMA)), (
        "workflows/_schema.md must keep the WORKFLOW-PHASE `gate_tier` field-table row - a "
        "structurally distinct, pre-existing field that the node-field ban must not break"
    )
    assert 'get("gate_tier")' in _read(CHECK_WORKFLOWS), (
        "check_workflows.py must keep VALIDATING the workflow-phase `gate_tier` - a declared field "
        "nothing checks is the 'mechanism described, never reached' defect"
    )


@pytest.mark.parametrize("sample", [
    'A node may carry "gate_tier": "L2" to force a human gate.',
    "The driver reads node.gate_tier and gates accordingly.",
    "Serialize nodes[].gate_tier alongside depends_on.",
    "  gate_tier: L2   # per-node override",
])
def test_the_gate_tier_node_field_detector_fires_on_a_live_reintroduction(sample):
    """Detector proof (MUST-CATCH): the scan is not laundered by any serialization shape."""
    assert _scan(sample, _NODE_GATE_TIER_PATTERNS, _RETIREMENT_MARKER), (
        f"the node-field `gate_tier` ban must catch {sample!r}"
    )


@pytest.mark.parametrize("sample", [
    "A node carries NO `gate_tier`: the tier is a total function resolved at dispatch.",
    "corroborate on the node objects (a retired `nodes[].gate_tier` field).",
    "writing a `gate_tier` field is a schema violation.",
    'the registry key "default_gate_tier": "L1" is the function\'s INPUT.',
])
def test_the_gate_tier_node_field_detector_leaves_the_retirement_prose_alone(sample):
    """Detector proof (MUST-NOT-CATCH): naming the deleted field to FORBID it is the contract."""
    assert not _scan(sample, _NODE_GATE_TIER_PATTERNS, _RETIREMENT_MARKER), (
        f"the node-field `gate_tier` ban must NOT catch {sample!r}"
    )


def test_every_plan_agreement_check_routes_back_to_odoo_planning():
    """Each `verify_plan_agreement` check either AGREES or STOPS BLOCKED and routes back.

    Behaviour protected: the harness owns only pure functions of plan fields plus runtime-only
    facts. A check that quietly substitutes its own answer for a disagreeing plan field re-creates
    the re-derivation the ownership contract exists to kill - so EVERY check (there are five today;
    the count is not the contract) must terminate its disagreement path at `odoo-planning`.

    Fails if: a check is added or rewritten without the route-back clause, or the section's
    never-substitute rule is dropped.
    """
    section = _section(_read(RUN_HARNESS), r"^## Plan agreement")
    flat_section = _flat(section)
    assert re.search(r"(?i)Each either AGREES.{0,120}STOPS the run BLOCKED", flat_section), (
        "§ Plan agreement must state each check either AGREES or STOPS the run BLOCKED"
    )
    assert re.search(r"(?i)Never substitute, re-?partition, re-?order or re-?plan", flat_section), (
        "§ Plan agreement must forbid substituting / re-partitioning / re-ordering / re-planning - "
        "the whole point of the ownership contract"
    )

    items = re.split(r"(?m)^\d+\.\s+\*\*", section)[1:]
    assert len(items) >= 4, (
        f"§ Plan agreement must enumerate its checks as a numbered list (found {len(items)}) - an "
        "unenumerated blob cannot be checked clause by clause"
    )
    missing = []
    for item in items:
        flat_item = _flat(item)
        name = flat_item.split(".")[0][:60]
        if not re.search(r"(?i)routes? back to odoo-planning", flat_item):
            missing.append(name)
    assert not missing, (
        "These `verify_plan_agreement` checks do not route their disagreement back to "
        f"`odoo-planning`: {missing}. A check that stops without naming the owner who must fix the "
        "plan leaves the driver as the only actor who can proceed - which it does by substituting."
    )


_SUBSTITUTION_PHRASINGS = (
    ("re-derive-instead-of-trust", re.compile(r"(?i)re-?deriv\w+ .{0,80}(instead of|rather than) (trust|believ)")),
    ("never-trust-X-alone", re.compile(r"(?i)never trust \w+ alone")),
    ("NOT-raw-node.gate_tier", re.compile(r"(?i)NOT raw node\.gate_tier")),
)


def test_the_harness_never_substitutes_its_own_value_for_a_plan_field():
    """Inversion-rejection for the ownership contract: no substitution phrasing may return.

    These three phrasings are how the four re-derivation carve-outs were worded before the change.
    Each licensed the driver to override a plan field it disagreed with instead of stopping.
    """
    offenders = []
    for path in sorted((SKILLS / "run-harness").rglob("*.md")):
        flat = _flat(_read(path))
        for label, pat in _SUBSTITUTION_PHRASINGS:
            m = pat.search(flat)
            if m:
                offenders.append(f"{path.relative_to(REPO_ROOT)} [{label}]: {m.group(0)!r}")
    assert not offenders, (
        "run-harness re-grew a substitution carve-out. Where a pure function disagrees with a plan "
        "field the driver STOPS BLOCKED and routes back to `odoo-planning`; it never silently "
        "substitutes its own value.\n" + "\n".join(offenders)
    )


# ===========================================================================
# G3 - the plan carries no executor-shaped artifact
# ===========================================================================

_EXECUTOR_SHAPED_TOKENS = (
    ("Block 2W", re.compile(r"Block\s*2W")),
    ("worktree( projection", re.compile(r"worktree\s*\(")),
    ("topology", re.compile(r"(?i)\btopolog(?:y|ies)\b")),
    ("cumulative_modules", re.compile(r"(?i)\bcumulative_modules\b")),
    ("gate_tier", re.compile(r"(?i)\bgate_tier\b")),
)
# A token named only to FORBID it is the contract, not a violation of it.
_NEGATION_MARKER = re.compile(
    r"(?i)\b(?:no|not|never|without|retired|deleted|removed|no longer)\b"
    r"|is a schema violation|is a total function|total function resolved at dispatch"
)


def test_the_plan_and_the_planner_carry_no_executor_shaped_artifact():
    """The plan is a DECISION RECORD, not a projection of the executor's runtime shape.

    Behaviour protected: `Block 2W`, the `worktree(...)` graph projection, `topology`,
    `cumulative_modules` and `gate_tier` were all plan-side restatements of something the driver
    already owns or computes. Every one of them gave a decision two authors. They are deleted, and
    the plan's authority is stated positively instead: it is the only place a run decision is made.

    Fails if: any of the five tokens returns to `plan-mode-schema.md` or `agents/odoo-planner.md`
    as a live construct (a NEGATED mention - "carries NO `gate_tier`" - stays legal and is the
    contract), or the positive authority/no-tier sentences are dropped.
    """
    offenders = []
    for path in (PLAN_SCHEMA, PLANNER):
        rel = path.relative_to(REPO_ROOT).as_posix()
        offenders += [f"{rel}:{hit}"
                      for hit in _scan(_read(path), _EXECUTOR_SHAPED_TOKENS, _NEGATION_MARKER)]
    assert not offenders, (
        "An executor-shaped artifact returned to the plan layer. The plan declares NODES with "
        "`depends_on` and nothing else about HOW the driver will run them - no Block 2W, no "
        "worktree projection, no topology, no cumulative_modules, no gate_tier.\n"
        + "\n".join(offenders)
    )

    schema = _flat(_read(PLAN_SCHEMA))
    assert re.search(r"(?i)The plan is the only place a run decision is made", schema), (
        "plan-mode-schema.md must state positively that the plan is the ONLY place a run decision "
        "is made - the sentence that makes every driver re-derivation a bug rather than a style"
    )
    planner = _flat(_read(PLANNER))
    assert re.search(r"(?i)node carries NO gate_tier.{0,40}never author one", planner), (
        "odoo-planner must be told the node carries NO `gate_tier` and to never author one - the "
        "producer half of the deletion; banning the field only in the schema leaves the planner "
        "writing one that nothing reads"
    )


@pytest.mark.parametrize("sample", [
    "Block 2W - the worktree lineage graph, one row per node.",
    "Render worktree(m)@run-integration ==> run-integration for each coding node.",
    "Set `topology: single` when the batch holds one module.",
    "`cumulative_modules` lists every module the regression run has covered so far.",
    "Each node carries a `gate_tier` the planner chooses at authoring time.",
])
def test_the_executor_shaped_detector_fires_on_a_live_reintroduction(sample):
    """Detector proof (MUST-CATCH): a live re-introduction of each deleted construct is flagged."""
    assert _scan(sample, _EXECUTOR_SHAPED_TOKENS, _NEGATION_MARKER), (
        f"the executor-shaped artifact ban must catch {sample!r}"
    )


@pytest.mark.parametrize("sample", [
    "It carries NO worktree topology and NO concrete ref STATE - no SHAs, no branch tips.",
    "**A node carries NO `gate_tier` - never author one, anywhere in the plan.**",
    "writing a `gate_tier` field is a schema violation.",
    "a retired `approach_kind` value, or a `topology`/`cumulative_modules` field.",
])
def test_the_executor_shaped_detector_leaves_the_prohibition_prose_alone(sample):
    """Detector proof (MUST-NOT-CATCH): the prohibition must be allowed to name what it forbids."""
    assert not _scan(sample, _EXECUTOR_SHAPED_TOKENS, _NEGATION_MARKER), (
        f"the executor-shaped artifact ban must NOT catch {sample!r}"
    )


# ===========================================================================
# G4 - the dispatch unit is the NODE, whole-tree
# ===========================================================================

_PER_MODULE_DISPATCH = (
    ("one odoo-coder per module", re.compile(r"(?i)one .{0,30}odoo-coder.{0,30}per module")),
    ("more than one odoo-coder per node", re.compile(r"(?i)more than one .{0,30}odoo-coder.{0,30}per node")),
    ("per-module coordinator/dispatch/brief",
     re.compile(r"(?i)per-module (COORDINATOR|coordinator|dispatch|brief)")),
)
# "Never split a node into per-module dispatches" states the rule; it is not a claim of one.
_PER_MODULE_NEGATION = re.compile(
    r"(?i)\b(never|not|no|nor|neither|without|stop|forbid\w*|must not|rather than|instead of|"
    r"retired|deleted|no longer)\b"
)


def test_the_dispatch_unit_is_the_node_across_the_whole_plugin():
    """ONE `odoo-coder` COORDINATOR per work NODE - never one per module, anywhere in the plugin.

    Behaviour protected: the node is the unit the plan approved, the unit the coordinator commits
    and the unit `run-harness` cherry-picks. A per-module dispatch desynchronises all three, and it
    survives most easily as a stale DESCRIPTION of `odoo-coder` in a file nobody re-reads (an agent
    frontmatter, a setup-script comment, the orchestration registry's `notes`) rather than in the
    dispatching skill itself. This scan is therefore whole-tree.

    Fails if: any runtime file under `plugins/odoo-ai-agents/` claims a per-module `odoo-coder`
    cardinality or a per-module coordinator/dispatch/brief, outside a negation and outside the
    DATA allowlist for the pipelines deliberately left per-module.
    """
    allow_entries = _allowlist("per_module_dispatch_allowlist.txt")
    allowed = {path for path, _ in allow_entries}
    for path, reason in allow_entries:
        assert len(reason) >= 30, (
            f"per_module_dispatch_allowlist.txt entry {path!r} must state WHY that pipeline's "
            "per-module unit is an Odoo fact rather than a plugin convention"
        )

    offenders, matched_allowed = [], set()
    for p in sorted(PLUGIN.rglob("*")):
        if not p.is_file() or p.suffix not in {".md", ".yaml", ".yml", ".json", ".py", ".sh"}:
            continue
        if "__pycache__" in p.parts:
            continue
        rel = p.relative_to(REPO_ROOT).as_posix()
        hits = _scan(_read(p), _PER_MODULE_DISPATCH, _PER_MODULE_NEGATION)
        if not hits:
            continue
        if rel in allowed:
            matched_allowed.add(rel)
            continue
        offenders += [f"{rel}:{hit}" for hit in hits]
    assert not offenders, (
        "A per-module `odoo-coder` dispatch claim survived. `odoo-coding` launches ONE `odoo-coder` "
        "COORDINATOR per work NODE - whatever the node's stack tag, whether it touches one module, "
        "part of one, or several. The module is a PROPERTY of the node, never the dispatch unit.\n"
        + "\n".join(sorted(set(offenders)))
    )
    stale = sorted(allowed - matched_allowed)
    assert not stale, (
        "STALE per-module allowlist entries - these files no longer match, so the exemption is "
        f"silently covering whatever lands there next. Delete the line: {stale}"
    )

    # Positive half (new coverage - the coder FAMILY, not the dispatching skill): every agent the
    # coordinator launches must describe its launcher as the per-NODE coordinator.
    for agent in ("odoo-backend-coder.md", "odoo-frontend-coder.md", "odoo-test-writer.md"):
        flat = _flat(_read(AGENTS / agent))
        assert re.search(r"(?i)odoo-coder per-node coordinator", flat), (
            f"agents/{agent} must name its launcher the `odoo-coder` PER-NODE coordinator. A "
            "teammate that still believes it was dispatched per module will scope its own work to "
            "one module of a node that spans several."
        )


@pytest.mark.parametrize("sample", [
    "Launch one odoo-coder coordinator per module in the plan's set.",
    "odoo-coding dispatches one `odoo-coder` COORDINATOR per module.",
    "A big node may need more than one odoo-coder per node.",
    "Fill the per-module COORDINATOR brief before dispatch.",
    "Compose a per-module brief for each coder.",
    "The per-module dispatch happens in Phase 0.",
])
def test_the_per_module_dispatch_detector_fires_on_a_live_reintroduction(sample):
    """Detector proof (MUST-CATCH): every phrasing of the retired cardinality is flagged."""
    assert _scan(sample, _PER_MODULE_DISPATCH, _PER_MODULE_NEGATION), (
        f"the per-module dispatch ban must catch {sample!r}"
    )


@pytest.mark.parametrize("sample", [
    "Never split a node into per-module dispatches, and never merge two nodes into one dispatch.",
    "There is no per-module coordinator: the coordinator is per node.",
    "The retired per-module brief was replaced by the per-node brief.",
])
def test_the_per_module_dispatch_detector_leaves_the_prohibition_prose_alone(sample):
    """Detector proof (MUST-NOT-CATCH): the rule must be allowed to name the thing it forbids."""
    assert not _scan(sample, _PER_MODULE_DISPATCH, _PER_MODULE_NEGATION), (
        f"the per-module dispatch ban must NOT catch {sample!r}"
    )


# ===========================================================================
# G6 - dependency-ORDER behaviour survives the vocabulary purge
# ===========================================================================

def test_dependency_order_behaviour_survives_the_vocabulary_purge():
    """Deleting the WORD must not delete the ORDER. Phrased against the behaviour, not the noun.

    Behaviour protected (an Odoo fact, not a plugin convention): a module cannot load before its
    dependencies, so `odoo-modules-upgrade` P5 installs bottom-up ONE DEPENDENCY LEVEL AT A TIME,
    leaves first, checkpointing each level so a resume skips the proven ones; and `odoo-deep-survey`
    walks its dependency closure one LAYER at a time with ordinal labels. A purge that replaced
    those mechanisms with "in dependency order" prose would pass a word ban and lose the behaviour.

    Fails if: any of the four files stops stating the mechanism, or the module-graph SSOT stops
    stating that a module must run after its in-set dependency.
    """
    upg_skill = _flat(_read(UPGRADE_SKILL))
    upg_detail = _flat(_read(UPGRADE_DETAIL))
    for label, text in (("odoo-modules-upgrade/SKILL.md", upg_skill),
                        ("references/upg-phase-detail.md", upg_detail)):
        assert re.search(r"(?i)one dependency level at a time", text), (
            f"{label} must still state the install runs ONE DEPENDENCY LEVEL AT A TIME - Odoo "
            "cannot load a module before its dependencies (grounded v8-v19)"
        )
        assert re.search(r"(?i)bottom-up", text), (
            f"{label} must still state the install is BOTTOM-UP"
        )
        assert re.search(r"(?i)leaves first", text), (
            f"{label} must still state leaves-first ordering"
        )
    assert re.search(r"(?i)per-level green is recorded in checkpoint\.json", upg_detail), (
        "upg-phase-detail.md must keep PER-LEVEL checkpointing - it is what makes a failure "
        "localize to the level that introduced it"
    )
    assert re.search(r"(?i)resume skips proven levels", upg_detail), (
        "upg-phase-detail.md must keep the RESUME rule (skip already-proven levels) - without it "
        "the checkpoint is written and never read"
    )
    assert re.search(r"(?i)skip already-green levels", upg_skill), (
        "odoo-modules-upgrade/SKILL.md must keep the resume rule that skips already-green levels"
    )

    survey = _flat(_read(SURVEY_SKILL))
    assert re.search(r"(?i)PHASED one dependency layer at a time", survey), (
        "odoo-deep-survey/SKILL.md must keep the PHASED closure walk - one dependency layer at a "
        "time - not a flattened 'read the whole closure' instruction"
    )
    lenses = _flat(_read(SURVEY_LENSES))
    assert re.search(r"(?i)Walk the closure one layer at a time", lenses), (
        "survey-lenses.md must keep the one-layer-at-a-time closure walk"
    )
    assert re.search(r"(?i)Layer 0 - nearest", lenses) and re.search(r"(?i)Layer 1\.\.n", lenses), (
        "survey-lenses.md must keep its ORDINAL layer labels (Layer 0 = nearest, Layer 1..n toward "
        "`base`) - the labels are what make the closure map readable to the next agent"
    )

    graph = _flat(_read(MODULE_GRAPH))
    assert re.search(r"(?i)must run after its in-set dependency", graph), (
        "odoo-module-graph.md must keep the ordering invariant: a module that depends on another "
        "in the set MUST RUN AFTER its in-set dependency"
    )
    # Inversion-rejection: independence is legal, ignoring the edge is not.
    for label, text in (("odoo-module-graph.md", graph), ("upg-phase-detail.md", upg_detail),
                        ("odoo-modules-upgrade/SKILL.md", upg_skill)):
        assert not re.search(
            r"(?i)(may run before its in-set|ignore the dependency (order|edge|level)|"
            r"install all levels at once|in any order regardless of depend)", text), (
            f"{label} states that dependency order may be ignored - it is an Odoo fact, not a "
            "scheduling preference: a module cannot load before its dependencies."
        )


# ===========================================================================
# G7 - one instance, one run, one commit, one SHA per node
# ===========================================================================

_PER_MODULE_EXECUTION = (
    ("one instance per module", re.compile(r"(?i)(one|a|its own) (isolated |ephemeral |live )*instance per module")),
    ("per-module instance/verification/commit",
     re.compile(r"(?i)per-module (instance|verification|verify|commit|test run|integrated test)")),
    ("one commit per module", re.compile(r"(?i)(one|a) commit per module")),
    ("commit each module", re.compile(r"(?i)commits? (each|every) module")),
    ("one SHA per module", re.compile(r"(?i)(one|a) SHA per module")),
)


def test_one_instance_one_run_one_commit_one_sha_per_node():
    """`odoo-coder` verifies and commits the WHOLE NODE once - not once per module inside it.

    Behaviour protected: the node is the unit of readiness (`depends_on`), of cherry-pick and of
    rollback. A node that landed as two commits has no single SHA the integration saga can
    checkpoint or revert, and a per-module instance cannot see a cross-module assertion at all.
    Grounded: `-i`/`-u` accept a comma-separated module list in every series v8-v19, so ONE
    instance and ONE run genuinely cover a multi-module node.

    Fails if: the single-instance / dependency-order / single-commit / single-SHA statements are
    dropped, or a per-module instance or commit claim returns.
    """
    flat = _flat(_read(CODER))
    assert re.search(r"(?i)verify the WHOLE NODE together.{0,120}on a SINGLE live instance", flat), (
        "odoo-coder must verify the WHOLE NODE together on a SINGLE live instance"
    )
    assert re.search(r"(?i)MODULES:? .{0,80}(node's full module list )?IN DEPENDENCY ORDER", flat), (
        "odoo-coder must install the node's full module list IN DEPENDENCY ORDER - Odoo cannot "
        "load a module before its dependencies"
    )
    assert re.search(r"(?i)one instance and one run covers the whole node", flat), (
        "odoo-coder must state ONE instance and ONE integrated run cover the whole node - the "
        "grounded fact (-i/-u take a LIST in every series v8-v19) that makes the node the unit"
    )
    assert re.search(r"(?i)capture the ONE returned SHA", flat), (
        "odoo-coder must commit the node ONCE and capture the ONE returned SHA"
    )
    assert re.search(
        r"(?i)a node that landed as two commits has no single SHA the saga can checkpoint or revert",
        flat), (
        "odoo-coder must state WHY one commit per node is load-bearing (the saga's checkpoint and "
        "revert unit) - a rule with no reason is the first thing an agent optimises away"
    )

    offenders = []
    for label, pat in _PER_MODULE_EXECUTION:
        for path in (CODER, CODING):
            m = pat.search(_flat(_read(path)))
            if m:
                offenders.append(f"{path.relative_to(REPO_ROOT)} [{label}]: {m.group(0)!r}")
    assert not offenders, (
        "A per-module instance / commit claim survived inside the node executor. One node -> one "
        "worktree -> one instance -> one integrated run -> one commit -> one SHA.\n"
        + "\n".join(offenders)
    )


def test_cross_module_test_staging_names_both_era_remedies():
    """A node may span modules, so the cross-module staging rule must be stated in BOTH authors.

    Behaviour protected (grounded v8-v19): Odoo runs tests in two phases, and a test class is
    `at_install` by DEFAULT - so an unstaged assertion in the first module of a node fires before
    the second module is loaded and fails with a KeyError on a symbol that genuinely exists. The
    12.0+ remedy and the 8.0-11.0 remedy are DIFFERENT APIs; naming only the modern one silently
    breaks four series.

    Fails if: either `agents/odoo-coder.md` or `skills/odoo-test-writing/SKILL.md` loses the rule,
    the 12.0+ `@tagged('post_install', '-at_install')` form, or the 8.0-11.0 decorator remedy.
    """
    for label, path in (("agents/odoo-coder.md", CODER),
                        ("skills/odoo-test-writing/SKILL.md", TEST_WRITING)):
        flat = _flat(_read(path))
        assert re.search(r"(?i)must be staged into the post-install phase", flat), (
            f"{label} must state that a cross-module assertion is STAGED into the post-install "
            "phase - the only moment the whole node is visible"
        )
        assert re.search(r"(?i)Series 12\.0 and later:.{0,80}@tagged\('post_install', '-at_install'\)", flat), (
            f"{label} must name the 12.0-and-later remedy verbatim: "
            "@tagged('post_install', '-at_install')"
        )
        assert re.search(r"(?i)Series 8\.0 to 11\.0", flat), (
            f"{label} must carry a SEPARATE 8.0-11.0 branch - `@tagged` does not exist before 12.0"
        )
        assert re.search(r"(?i)@common\.post_install\(True\)", flat) and \
               re.search(r"(?i)@common\.at_install\(False\)", flat), (
            f"{label} must name the 8.0-11.0 remedy - the phase decorators "
            "@common.post_install(True) / @common.at_install(False) - not just say 'use the old API'"
        )
        assert re.search(r"(?i)has no \"?last module\"?", flat), (
            f"{label} must state that last-module placement only works when the node's modules are "
            "TOTALLY ORDERED by `depends` - a node spanning unrelated modules has no last module"
        )


# ===========================================================================
# G8 - the tier function is TOTAL and the ephemeral ceiling is justified
# ===========================================================================

_APPROACH_KINDS = ("skill", "agent", "workflow", "inline", "integrate")


def test_the_gate_tier_function_is_total_and_carries_the_ephemeral_ceiling():
    """The tier is a TOTAL function over all five `approach_kind` values, with ONE lowering term.

    Behaviour protected: with the wave-only L1 carve-out deleted and `odoo-instance` sitting at
    registry L2, every verification node would become a mandatory human stop and `--auto` would
    halt a 6-node plan three times - breaking the skill's own promise. The EPHEMERAL CEILING
    replaces the carve-out with a general rule keyed on a fact the driver owns: it knows the touch
    is not shared BECAUSE IT WROTE THE BRIEF (`MODE: fresh` + `PERSIST: ephemeral` +
    `SELF_PROVISION: worktree-addons`).

    Fails if: the function stops being total (an `approach_kind` with no term), the ceiling or its
    justification is dropped, or a duplicate prose tier exception for `integrate` reappears
    OUTSIDE the function - which would give the tier two sources again.
    """
    body = _read(RUN_HARNESS)
    section = _section(body, r"^## Gate-tier resolution")
    flat_section = _flat(section)

    assert re.search(r"(?i)TOTAL FUNCTION - nobody authors it", flat_section), (
        "§ Gate-tier resolution must open by stating the tier is a TOTAL FUNCTION nobody authors"
    )
    assert re.search(r"(?i)A node carries NO gate_tier field", flat_section), (
        "§ Gate-tier resolution must state the node carries NO `gate_tier` field"
    )
    assert re.search(r'(?i)approach_kind == "inline":\s*return L0', flat_section), (
        "the tier function must carry an explicit `inline` term (L0 - chat-only, writes nothing)"
    )
    assert re.search(r'(?i)approach_kind == "integrate":\s*return L1', flat_section), (
        "the tier function must carry an explicit `integrate` term (L1 - the land tail opens a PR "
        "and rewrites nothing); without it the land tail falls through to a registry lookup for a "
        "skill name it does not have"
    )
    assert re.search(r"(?i)registry default_gate_tier\(node\.approach\)", flat_section), (
        "the remaining kinds (skill | agent | workflow) must resolve from the registry default - "
        "that is what makes the function TOTAL over all five values"
    )
    for kind in _APPROACH_KINDS:
        assert kind in flat_section, (
            f"the tier function must account for `approach_kind` = {kind!r}: all five values, or it "
            "is not a total function and some node kind resolves to nothing"
        )
    assert re.search(r"(?i)the EPHEMERAL CEILING", flat_section), (
        "the tier function must carry the EPHEMERAL CEILING term by name"
    )
    assert re.search(r"(?i)t = min\(t, L1\)", flat_section), (
        "the ceiling must be a min() CEILING, never a raise - it can only lower, and only to L1"
    )
    assert re.search(r"(?i)because you wrote the brief", flat_section), (
        "the ceiling must state its justification - the driver knows the touch is NOT shared "
        "BECAUSE IT WROTE THE BRIEF. An unjustified tier lowering is a carve-out, which is exactly "
        "what the wave-only L1 was."
    )
    assert re.search(
        r"(?i)MODE: fresh.{0,40}PERSIST: ephemeral.{0,60}SELF_PROVISION: worktree-addons",
        flat_section), (
        "the ceiling's precondition must name all three brief fields (MODE: fresh + PERSIST: "
        "ephemeral + SELF_PROVISION: worktree-addons) - the observable facts that make the touch "
        "ephemeral"
    )
    assert re.search(r"(?i)keeps its registry L2", flat_section), (
        "the ceiling must state its OWN limit: a node dispatched to a skill owning its instance "
        "policy (odoo-i18n, odoo-acceptance) keeps its registry L2, because the driver did not "
        "write that brief"
    )
    assert re.search(r"(?i)L2 NEVER lowers", flat_section), (
        "the function must keep the L2 floor - the ceiling lowers to L1, never past it"
    )

    # Inversion-rejection: no SECOND home for the integrate tier, outside the function.
    outside = _flat(_strip_fences(body.replace(section, "\n")))
    dup = re.search(
        r"(?i)(opening [^.]{0,50}\bPR\b|the land tail|integrate)[^.]{0,90}"
        r"\b(is NOT L2|is L1|is not a human gate|auto-pass\w*)\b",
        outside)
    assert not dup, (
        "A duplicate prose tier exception for `integrate` reappeared OUTSIDE § Gate-tier "
        f"resolution: {dup.group(0)!r}. EVERY node's tier, `integrate` included, comes from the "
        "ONE total function; keeping a prose restatement gives the tier two sources and the two "
        "will drift."
    )


def test_the_coder_cites_the_live_ceiling_not_the_deleted_harness_section():
    """`odoo-coder`'s instance-release rule must cite the CEILING, not a deleted section number.

    Behaviour protected: the release is not housekeeping - the ceiling's whole premise is that the
    instance is ephemeral, so a lease left dangling is the shared-instance risk the ceiling assumes
    away. The paragraph must therefore point at the live owner of that assumption. A pointer at
    `workflow-harness.md` § 8.4 (the wave-era home) resolves to text that no longer makes the
    claim, which is the 'mechanism described, never reached' defect in pointer form.

    Fails if: the release paragraph loses the ceiling citation, loses the reason, or re-points at
    the retired § 8.4.
    """
    flat = _flat(_read(CODER))
    m = re.search(r"(?i)After the integrated test, RELEASE the instance you self-provisioned\..{0,1400}", flat)
    assert m, "odoo-coder must keep the 'RELEASE the instance you self-provisioned' paragraph"
    para = m.group(0)
    assert re.search(r"(?i)run-harness/SKILL\.md . Gate-tier resolution", para), (
        "the instance-release paragraph must cite `run-harness/SKILL.md` § Gate-tier resolution - "
        "the LIVE owner of the ephemeral ceiling this release upholds"
    )
    assert re.search(r"(?i)ephemeral ceiling", para), (
        "the release paragraph must name the ephemeral ceiling by name"
    )
    assert re.search(r"(?i)a lease you leave dangling is a shared-instance risk that ceiling assumes away",
                     para), (
        "the release paragraph must state the CONSEQUENCE - a dangling lease is the shared-instance "
        "risk the ceiling assumes away - so an agent cannot read the release as optional tidying"
    )
    assert not re.search(r"(?i)workflow-harness\.md . ?8\.4", para), (
        "the release paragraph must NOT cite the retired `workflow-harness.md` § 8.4 wave-era tier "
        "carve-out - that pointer resolves to text which no longer states the rule"
    )
