"""Guard for the resource-teardown-before-DONE contract wiring (L2.7).

Six checks lock in the BEHAVIOR the contract promises (ETHOS #10: a DONE claim needs
observable evidence; a leaked browser page/instance is the absence of that evidence):

1. Wiring + executable-step presence - a file that drives a browser page (opens or
   reuses it) or self-provisions an Odoo instance must carry BOTH a pointer to the SSOT contract
   AND a concrete, tool-named teardown step for its class. A pointer alone (prose
   with no named verb) does not prove the agent will actually call the tool.
2. Hub presence - the two hubs every skill/agent already reads
   (continuation-contract.md, spawner-completion-contract.md) surface the gate.
3. Dedup freeze - the normative browser-exclusivity sentence and the T1 ownership
   matrix rows live ONLY in the snippet; consumers may point, never restate.
4. Verb discipline - "release"/"drop" (instance verbs) never take a browser noun
   (page/tab/context/recording) as their object; the three pre-existing lease-ban
   lines keep their verbatim ban plus the new orthogonality suffix.
5. Version robustness - no version-specific flag or an unconditional DB drop leaks
   into agent-facing prose uncaveated; the mechanism sites name their grounding tool.
6. Lockstep - the snippet may claim "release stops the process group" only while
   the mechanism (`allocator.py::_stop_group`) actually exists, so the prose can
   never outrun the code if L1.2 is reverted.

Every matcher below is unit-tested against a crafted positive AND a crafted negative
string (not just the real tree) so each check is provably capable of failing, per
the "test the behavior" mandate - a check that cannot fail protects nothing.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"

SNIPPET = PLUGIN / "snippets" / "resource-teardown-contract.md"
ALLOCATOR = PLUGIN / "scripts" / "lib" / "allocator.py"
CONTINUATION = PLUGIN / "snippets" / "continuation-contract.md"
SPAWNER = PLUGIN / "snippets" / "spawner-completion-contract.md"
INSTANCE_OPS = PLUGIN / "agents" / "odoo-instance-ops.md"

POINTER = "resource-teardown-contract.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _rel(path: Path) -> str:
    return str(path.relative_to(PLUGIN)).replace("\\", "/")


def _md_files(*subdirs: str, exclude_evals: bool = True) -> list[Path]:
    """All .md files under the given plugin subdirs, recursively.

    `evals/` fixtures are excluded by default: they are test PROMPTS + expected-
    routing data consumed by the eval harness, not agent-facing prose an executor
    reads and acts on - the object of this guard.
    """
    files: list[Path] = []
    for d in subdirs:
        base = PLUGIN / d
        if not base.exists():
            continue
        for p in base.rglob("*.md"):
            if exclude_evals and "/evals/" in ("/" + _rel(p)):
                continue
            files.append(p)
    return sorted(files)


def _yaml_files(*subdirs: str, suffix: str = ".workflow.yaml") -> list[Path]:
    files: list[Path] = []
    for d in subdirs:
        base = PLUGIN / d
        if not base.exists():
            continue
        files.extend(sorted(base.glob(f"*{suffix}")))
    return files


def _section(text: str, heading: str, next_prefix: str = "\n## ") -> str:
    """Return the text from `heading` (inclusive) to the next `next_prefix` line."""
    idx = text.index(heading)
    rest = text[idx:]
    nxt = rest.find(next_prefix, len(heading))
    return rest if nxt == -1 else rest[:nxt]


# --------------------------------------------------------------------------- #
# Scan universe for check 1
# --------------------------------------------------------------------------- #
ALL_SCANNED_FILES = (
    _md_files("agents")
    + _md_files("skills")
    + _md_files("commands")
    + _yaml_files("workflows")
)

# A file DRIVES a browser page when it opens one OR reuses one: T1 counts a page reused by
# navigating it as acquired, so chrome-devtools `navigate_page` is an open token too (the
# same DRIVE set enforce-teardown.sh counts).
BROWSER_OPEN_RE = re.compile(
    r"new_page|navigate_page|browser_navigate|record_page|record_and_gif|start_video|start_trac"
)

# The executable close step, by family (T2 "End of dispatch, by family"): close_page,
# browser_close, stop_recording - or, for the chrome-devtools page that cannot be closed
# because it is the last one, navigate_page to about:blank. A bare `about:blank` or a bare
# navigate_page is not a close step; the two must name the same call.
BROWSER_STEP_RE = re.compile(
    r"close_page|browser_close|stop_recording|navigate_page\W{0,4}(?:\w+\W{1,4}){0,6}?about:blank"
)

INSTANCE_ACQUIRE_RE = re.compile(
    r"Skill\(odoo-instance\)|lease_acquire|allocator\.py acquire|persist:\s*ephemeral"
    r"|persist:\s*exclusive-running"
)

_RELEASE_STEM_RE = re.compile(r"releas\w*", re.I)
# \b before "lease" matters: "release" ITSELF contains the substring "lease"
# (r-e-LEASE), so an unanchored search would trivially "find" a lease reference
# inside the very word being matched, making the proximity check vacuous. The
# leading \b requires a real word boundary (e.g. "the lease", "still-leased",
# "lease_token") that "release" does not have at that position.
_LEASE_TOKEN_HINT_RE = re.compile(r"\blease\w*|\btoken\w*|run[-_]id", re.I)
_OPERATION_DROP_RE = re.compile(r"operation:\s*drop", re.I)


def _instance_step_present(text: str) -> bool:
    """An executable instance-teardown step: `operation: drop`, or `release`
    (any inflection) within reach of a lease/token/run-id reference - not a bare
    'release' floating with no concrete handle nearby."""
    if _OPERATION_DROP_RE.search(text):
        return True
    for m in _RELEASE_STEM_RE.finditer(text):
        window = text[max(0, m.start() - 150) : m.end() + 150]
        if _LEASE_TOKEN_HINT_RE.search(window):
            return True
    return False


def _browser_step_present(text: str) -> bool:
    return bool(BROWSER_STEP_RE.search(text))


def _has_pointer(text: str) -> bool:
    return POINTER in text


# Documented forwarded-handle / non-self-provisioning consumers (L2.3's "Unchanged
# exclusions" list). Each entry is checked to still exist on disk (a stale entry
# for a renamed/removed file would silently rot the allowlist).
ALLOWLIST: dict[str, str] = {
    "skills/odoo-doc-illustration/references/capture-mechanics.md": (
        "shared HOW-to-capture mechanics reference for odoo-user-doc-writer / "
        "odoo-marketing-writer - not itself a dispatched agent body. The executable "
        "close_page/browser_close step is owned once by each consuming agent's own "
        "Step 4.5/4.6 (dedup D2), not duplicated in this shared reference."
    ),
    "skills/odoo-i18n/references/i18n-recipe.md": (
        "reference doc for the non-destructive i18n recipe (read by odoo-i18n/SKILL.md and "
        "odoo-forward-port's P4 step) - not itself a dispatched agent/skill body. Its "
        "`lease_acquire` mentions CITE the WORKTREE_PATH re-root odoo-instance performs and the "
        "reserve-only lease guard; they do not instruct this recipe's reader to acquire an "
        "instance directly. Acquisition/release ownership stays with odoo-i18n/SKILL.md "
        "(Standalone-first fallback -> the odoo-instance skill) and its callers."
    ),
    "skills/odoo-git-rebase/references/rb-phase-detail.md": (
        "never self-provisions - consumes the orchestrator-forwarded INSTANCE_HANDLE "
        "and releases via its lease_token at run end; L2.3 unchanged exclusion."
    ),
    "skills/odoo-qa-suite/SKILL.md": (
        "NEEDS_NEXT ensure-up is a named handoff to odoo-instance, never a "
        "self-provision; L2.3 unchanged exclusion."
    ),
    "skills/odoo-test-writing/SKILL.md": (
        "never self-provisions - execution (and any instance) is delegated via "
        "NEEDS_NEXT to odoo-instance per test-execution-handoff.md; L2.3 unchanged exclusion."
    ),
    "skills/odoo-modules-upgrade/SKILL.md": (
        "consumes a forwarded instance handle; does not self-provision; L2.3 unchanged exclusion."
    ),
    "commands/odoo-produce-video.md": (
        "thin dispatcher onto the video-produce workflow; carries no browser/instance "
        "tokens of its own; L2.3 unchanged exclusion (thin dispatcher)."
    ),
}


def test_allowlist_entries_point_at_real_files():
    """A stale allowlist entry (renamed/removed file) must not silently rot - fail loud."""
    missing = [p for p in ALLOWLIST if not (PLUGIN / p).exists()]
    assert not missing, f"allowlist entries with no file on disk: {missing}"


# --- unit-level proof each predicate can fail (crafted strings, not real files) ---
def test_instance_step_predicate_can_fail():
    assert _instance_step_present("release the lease_token before your terminal status")
    assert _instance_step_present("allocator.py release $ALLOC_TOKEN --run-id $RUN_ID")
    assert _instance_step_present("emit next: {operation: drop}")
    assert _instance_step_present("call `lease_release` with the handle's token and run_id")
    # negative: bare "release" with no lease/token/run-id anywhere nearby
    assert not _instance_step_present(
        "you must release the pressure before continuing the workflow procedure text padding " * 3
    )
    assert not _instance_step_present("point at the resource-teardown-contract.md for the rule")


def test_browser_step_predicate_can_fail():
    assert _browser_step_present("call `close_page` for each page you created")
    assert _browser_step_present("playwright: `browser_close`")
    assert _browser_step_present("pagecast: `stop_recording`")
    assert _browser_step_present("then `navigate_page` that page to `about:blank`")
    assert not _browser_step_present("CLOSE every page you opened before terminal status")
    # navigating somewhere else is driving the page, not closing it
    assert not _browser_step_present("`navigate_page` to the next form view")
    assert not _browser_step_present("the page ends on about:blank")


def test_browser_open_predicate_counts_a_reused_page():
    """Navigating a reused chrome-devtools page acquires it (T1), so a file that only
    navigates must still be held to the close-step check."""
    assert BROWSER_OPEN_RE.search("`navigate_page` to the record URL")
    assert BROWSER_OPEN_RE.search("`new_page` per role")
    assert not BROWSER_OPEN_RE.search("`take_snapshot` of the current form")


def test_pointer_predicate_can_fail():
    assert _has_pointer("see ${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md T2")
    assert not _has_pointer("see the teardown rules elsewhere")


# --------------------------------------------------------------------------- #
# Check 1 - wiring + executable-step presence
# --------------------------------------------------------------------------- #
BROWSER_CANDIDATES = [f for f in ALL_SCANNED_FILES if BROWSER_OPEN_RE.search(_read(f))]
INSTANCE_CANDIDATES = [f for f in ALL_SCANNED_FILES if INSTANCE_ACQUIRE_RE.search(_read(f))]


def test_scan_actually_found_candidates():
    """Sanity: the token scan must not be vacuous (an empty candidate list would
    make the parametrized checks below pass by having nothing to check)."""
    assert BROWSER_CANDIDATES, "no file matched a browser-open token - scan or repo state changed"
    assert INSTANCE_CANDIDATES, "no file matched an instance-acquire token - scan or repo state changed"


@pytest.mark.parametrize("path", BROWSER_CANDIDATES, ids=_rel)
def test_browser_open_site_has_pointer_and_close_step(path: Path):
    rel = _rel(path)
    if rel in ALLOWLIST:
        pytest.skip(f"allowlisted: {ALLOWLIST[rel]}")
    text = _read(path)
    assert _has_pointer(text), (
        f"{rel}: opens a browser resource but carries no pointer to "
        f"{POINTER} - add one or add a justified ALLOWLIST entry"
    )
    assert _browser_step_present(text), (
        f"{rel}: opens a browser resource and points at the contract, but names no "
        f"executable close verb (close_page/browser_close/stop_recording, or navigate_page "
        f"to about:blank) - a pointer "
        f"alone does not prove the agent will actually close the page"
    )


@pytest.mark.parametrize("path", INSTANCE_CANDIDATES, ids=_rel)
def test_instance_acquire_site_has_pointer_and_release_step(path: Path):
    rel = _rel(path)
    if rel in ALLOWLIST:
        pytest.skip(f"allowlisted: {ALLOWLIST[rel]}")
    text = _read(path)
    assert _has_pointer(text), (
        f"{rel}: self-provisions an instance but carries no pointer to "
        f"{POINTER} - add one or add a justified ALLOWLIST entry"
    )
    assert _instance_step_present(text), (
        f"{rel}: self-provisions an instance and points at the contract, but names no "
        f"executable release step (release <token>/lease/run-id, or operation: drop) - "
        f"a pointer alone does not prove the agent will actually release the lease"
    )


# --------------------------------------------------------------------------- #
# Check 2 - hub presence
# --------------------------------------------------------------------------- #
def test_continuation_contract_has_teardown_bullet_under_done():
    text = _read(CONTINUATION)
    assert "status: DONE" in text
    done_idx = text.index("`status: DONE` when the run's goal is met")
    bullet_idx = text.index("Teardown gate on every terminal status")
    assert bullet_idx > done_idx, (
        "the teardown bullet must sit under the status:DONE rule, not before it"
    )
    assert POINTER in text[bullet_idx : bullet_idx + 400]


def test_spawner_completion_contract_has_r2_rollup_pointer():
    text = _read(SPAWNER)
    r2 = _section(text, "## R2 - No early DONE")
    assert POINTER in r2, (
        "spawner-completion-contract.md's R2 section must point at the teardown "
        "contract (the barrier also covers resources forwarded to a child)"
    )


# --------------------------------------------------------------------------- #
# Check 3 - dedup freeze (normative sentence + ownership-matrix rows: snippet-only)
# --------------------------------------------------------------------------- #
UNIQUE_TO_SNIPPET_FINGERPRINTS = [
    # T1 ownership-matrix rows (verbatim substrings unlikely to be paraphrased by accident).
    "the skill that drives the path",
    "NO single consumer, ever",
    "Teardown belongs to whoever ACQUIRED the resource",
    # The ONE orchestrator-vs-leaf release rule. Stated once; a second copy is how the
    # "never release directly" contradiction in the forward-port references arose.
    "Release directly only what you own.",
    # The normative PER-FAMILY browser-exclusivity sentences (E-3b: same-family
    # hard exclusivity + the cross-family parallelism permission that
    # distinguishes per-family from the old global single-flight rule).
    "Two drivers on the SAME family share one Chromium process",
    "and corrupt each other's evidence - that is the hard exclusivity",
    "Across DISTINCT families, parallel drivers ARE allowed",
]


@pytest.mark.parametrize("fingerprint", UNIQUE_TO_SNIPPET_FINGERPRINTS)
def test_normative_sentence_or_matrix_row_lives_only_in_snippet(fingerprint: str):
    hits = [f for f in ALL_SCANNED_FILES if fingerprint in _read(f)]
    assert hits == [SNIPPET] or (not hits and SNIPPET not in ALL_SCANNED_FILES), (
        f"'{fingerprint}' must live ONLY in {POINTER}, found restated in: "
        f"{[_rel(h) for h in hits if h != SNIPPET]}"
    )
    # The snippet itself is not scanned by ALL_SCANNED_FILES (snippets/ excluded from
    # check 1's universe on purpose - it is the SSOT, not a consumer) - assert directly.
    assert fingerprint in _read(SNIPPET), f"'{fingerprint}' missing from the SSOT snippet itself"


def test_snippet_not_in_consumer_scan_universe():
    """Sanity for the fingerprint test above: snippets/ must not be part of
    ALL_SCANNED_FILES, or a fingerprint would trivially 'match' its own home file
    and the restatement guard above would be vacuous."""
    assert SNIPPET not in ALL_SCANNED_FILES


# --------------------------------------------------------------------------- #
# Check 4 - verb discipline
# --------------------------------------------------------------------------- #
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_VERB_NOUN_COLLISION_RE = re.compile(
    r"\b(releas\w*|drop\w*)\b.{0,30}\b(page|tab|context|recording)\b"
    r"|\b(page|tab|context|recording)\b.{0,30}\b(releas\w*|drop\w*)\b",
    re.I | re.S,
)


def _verb_noun_collisions(text: str) -> list[str]:
    """Sentence-scoped: 'release'/'drop' must never take a browser noun as its
    object. Scoped per-sentence so a ban clause ('drop or release the lease') and
    an unrelated later clause about browser pages in the SAME PARAGRAPH ('...is
    orthogonal to browser pages') do not falsely collide - they are different
    sentences with the verb only near 'lease' in its own sentence."""
    offenders = []
    for sentence in _SENTENCE_SPLIT_RE.split(text):
        if _VERB_NOUN_COLLISION_RE.search(sentence):
            offenders.append(sentence.strip())
    return offenders


def test_verb_noun_collision_predicate_can_fail():
    assert _verb_noun_collisions("Please release the page before you continue.")
    assert _verb_noun_collisions("Drop the recording when you are finished.")
    # negative: verb and noun in DIFFERENT sentences must not collide
    assert not _verb_noun_collisions(
        "Never drop or release the lease. It is orthogonal to browser pages."
    )
    assert not _verb_noun_collisions("Close every page you opened.")


def test_t2_never_collocates_release_or_drop_with_a_browser_noun():
    t2 = _section(_read(SNIPPET), "## T2 - Browser: close what you drove")
    offenders = _verb_noun_collisions(t2)
    assert not offenders, f"T2 must never pair release/drop with a browser noun: {offenders}"


BROWSER_EDITED_LEAK_SITES = [
    PLUGIN / "agents" / "odoo-ui-reviewer.md",
    PLUGIN / "agents" / "odoo-ui-debugger.md",
    PLUGIN / "agents" / "odoo-qa-tester.md",
    PLUGIN / "agents" / "odoo-user-doc-writer.md",
    PLUGIN / "agents" / "odoo-marketing-writer.md",
    PLUGIN / "skills" / "odoo-ui-review" / "SKILL.md",
    PLUGIN / "skills" / "odoo-doc-illustration" / "SKILL.md",
    PLUGIN / "skills" / "odoo-doc-illustration" / "references" / "capture-mechanics.md",
    PLUGIN / "skills" / "odoo-demo-recording" / "SKILL.md",
    PLUGIN / "skills" / "odoo-demo-recording" / "references" / "examples.md",
    PLUGIN / "skills" / "odoo-debug" / "SKILL.md",
    PLUGIN / "skills" / "odoo-visual-regression" / "SKILL.md",
    PLUGIN / "workflows" / "video-produce.workflow.yaml",
    PLUGIN / "skills" / "_shared" / "concurrency-guard.md",
]


@pytest.mark.parametrize("path", BROWSER_EDITED_LEAK_SITES, ids=lambda p: _rel(p))
def test_browser_leak_site_never_collocates_release_or_drop_with_browser_noun(path: Path):
    assert path.exists(), f"expected leak site missing: {_rel(path)}"
    offenders = _verb_noun_collisions(_read(path))
    assert not offenders, f"{_rel(path)}: release/drop paired with a browser noun: {offenders}"


LEASE_BAN_RE = re.compile(r"\b(?:never|do\s+not)\s+drop\s+or\s+release\s+the\s+lease", re.I)
LEASE_BAN_SITES = [
    PLUGIN / "agents" / "odoo-user-doc-writer.md",
    PLUGIN / "agents" / "odoo-marketing-writer.md",
    PLUGIN / "skills" / "odoo-doc-illustration" / "references" / "capture-mechanics.md",
]


@pytest.mark.parametrize("path", LEASE_BAN_SITES, ids=lambda p: _rel(p))
def test_lease_ban_line_keeps_verbatim_ban_and_orthogonality_suffix(path: Path):
    text = _read(path)
    m = LEASE_BAN_RE.search(text)
    assert m, f"{_rel(path)}: must keep the verbatim 'never/do not drop or release the lease' ban"
    tail = text[m.end() : m.end() + 300]
    assert "orthogonal" in tail.lower() and "page" in tail.lower(), (
        f"{_rel(path)}: the ban must carry the orthogonality suffix (ban is INSTANCE-only, "
        f"does not excuse skipping the browser CLOSE rule) within reach of the ban line"
    )


# --------------------------------------------------------------------------- #
# Check 5 - version robustness
# --------------------------------------------------------------------------- #
_VERSION_FLAG_RE = re.compile(r"--longpolling-port|--xmlrpc-port")
_VERSION_CAVEAT_HINT_RE = re.compile(r"removed|v19|v8-v10|v11-v15|v16\+|cli_help|deprecated|ONLY for|ONLY where", re.I)


def _uncaveated_version_flags(text: str) -> list[str]:
    offenders = []
    for m in _VERSION_FLAG_RE.finditer(text):
        window = text[max(0, m.start() - 120) : m.end() + 120]
        if not _VERSION_CAVEAT_HINT_RE.search(window):
            offenders.append(text[max(0, m.start() - 30) : m.end() + 30])
    return offenders


def test_uncaveated_version_flag_predicate_can_fail():
    assert _uncaveated_version_flags("run odoo-bin --longpolling-port 8072 always")
    assert not _uncaveated_version_flags(
        "--longpolling-port and --xmlrpc-port are removed at v19; resolve via cli_help"
    )


@pytest.mark.parametrize(
    "path",
    [f for f in ALL_SCANNED_FILES if _VERSION_FLAG_RE.search(_read(f))]
    + [INSTANCE_OPS, SNIPPET, PLUGIN / "docs" / "reference" / "INSTANCE-ALLOCATION-MODES.md",
       PLUGIN / "skills" / "odoo-instance" / "SKILL.md"],
    ids=lambda p: _rel(p),
)
def test_no_uncaveated_version_specific_port_flags(path: Path):
    text = _read(path)
    offenders = _uncaveated_version_flags(text)
    assert not offenders, (
        f"{_rel(path)}: --longpolling-port/--xmlrpc-port must always be caveated "
        f"(removed-at-version / cli_help-resolved), never presented as an "
        f"unconditional flag: {offenders}"
    )


def test_t3_names_cli_help():
    t3 = _section(_read(SNIPPET), "## T3 - Instance: release what you provisioned")
    assert "cli_help" in t3, "T3 must name cli_help as the per-version CLI grounding tool"


def test_instance_ops_op2_describes_stop_group_then_drop():
    text = _read(INSTANCE_OPS)
    # op 2 ("Drop an existing Odoo database...") through the next '##' heading.
    op2 = _section(text, "Drop an existing Odoo database", next_prefix="\n## ")
    assert re.search(r"process\s+group", op2, re.I), (
        "odoo-instance-ops.md op 2 must describe stop-group-then-drop, not a bare drop"
    )
    assert re.search(r"THEN drops|then drops", op2), (
        "op 2 must state the ORDER: stop the group FIRST, THEN drop"
    )


_DROPDB_QUALIFIER_RE = re.compile(
    r"fallback|never|NEVER|raw|logged|block|belt|internally|through Odoo|pg_terminate|mechanism",
    re.I,
)


def test_dropdb_qualifier_predicate_can_fail():
    assert not _DROPDB_QUALIFIER_RE.search("just run dropdb on the database directly")
    assert _DROPDB_QUALIFIER_RE.search("raw dropdb as a logged fallback")


def test_no_unconditional_dropdb_in_agent_facing_prose():
    """`dropdb`/`DROP DATABASE` may appear only as a documented, labeled FALLBACK, an
    explicit ban ('never run dropdb yourself'), or descriptive mechanism prose
    (explaining what a second belt/internal call does) - never as a bare instruction
    telling the agent to go run it."""
    offenders = []
    for f in _md_files("agents", "skills", "snippets", "docs"):
        text = _read(f)
        for m in re.finditer(r"\bdropdb\b|DROP DATABASE", text):
            window = text[max(0, m.start() - 80) : m.end() + 80]
            if not _DROPDB_QUALIFIER_RE.search(window):
                offenders.append(f"{_rel(f)}: {window.strip()}")
    assert not offenders, "unconditional dropdb/DROP DATABASE outside a fallback/ban context:\n" + "\n".join(offenders)


# --------------------------------------------------------------------------- #
# Check 6 - lockstep (prose may not outrun the mechanism)
# --------------------------------------------------------------------------- #
def test_release_stops_process_group_claim_requires_stop_group_in_code():
    t3 = _section(_read(SNIPPET), "## T3 - Instance: release what you provisioned")
    claims_stop_group = bool(re.search(r"stops? the server'?s process group", t3, re.I))
    assert claims_stop_group, (
        "T3 is expected to claim release stops the server's process group (L1.2 shipped) - "
        "if this fails, T3's wording changed; update this test's expectation deliberately"
    )
    if claims_stop_group:
        assert "_stop_group" in _read(ALLOCATOR), (
            "T3 claims release stops the process group, but scripts/lib/allocator.py no "
            "longer defines _stop_group - the prose has outrun the code (L1.2 reverted?); "
            "either restore _stop_group or walk back T3's claim"
        )


# --------------------------------------------------------------------------- #
# Check 7 - the lease-tool contract: one ownership rule, no contradicting copy
# --------------------------------------------------------------------------- #
def _three_exits_section() -> str:
    text = _read(SNIPPET)
    start = text.index("### The three exits")
    end = text.find("\n## ", start)
    return text[start:] if end == -1 else text[start:end]


def test_three_exits_name_the_lease_tools_that_perform_them():
    """An exit the agent cannot map to a call is an exit it will not take. release and park
    must each name the odoo-local tool that performs it."""
    section = _three_exits_section()
    assert "`lease_release`" in section, "the release exit must name the lease_release tool"
    assert "`lease_park`" in section, "the park exit must name the lease_park tool"


_KEEPALIVE_RE = re.compile(r"\bheartbeat\b|\bTTL\b|keep-?alive", re.I)


def test_keepalive_predicate_can_fail():
    assert _KEEPALIVE_RE.search("call allocator.py heartbeat <token> between phases")
    assert _KEEPALIVE_RE.search("once the allocator's TTL (default 3600s) lapses")
    assert not _KEEPALIVE_RE.search("a lease stays protected while its session is alive")


def test_contract_teaches_no_lease_keepalive():
    """A lease is protected for as long as the session that acquired it lives. An instruction
    to heartbeat or to race a TTL makes an agent spend turns babysitting a lease nothing will
    reclaim - and, worse, implies the lease is unsafe without it."""
    offenders = [line for line in _read(SNIPPET).splitlines() if _KEEPALIVE_RE.search(line)]
    assert not offenders, f"the teardown contract still teaches lease keep-alive: {offenders}"


def test_forwarded_handle_is_never_the_consumers_to_release():
    """The consumer side of the ownership rule, stated where the rule lives: holding a handle's
    token and run_id makes a release call POSSIBLE, never permitted."""
    text = " ".join(_read(SNIPPET).split())
    assert "is never yours to release or park" in text, (
        "T1 must state that a lease received DOWN as a forwarded INSTANCE_HANDLE is never "
        "the consumer's to release or park"
    )
    assert "handed back UP to you as the run-level owner" in text, (
        "T1 must state the owner side: a lease provisioned for your run and handed back to you "
        "is yours to release directly"
    )


_RELEASE_TOKEN = r"`?(?:allocator\.py`?\s+release|lease_release)`?"
_DIRECT_RELEASE_BAN_RE = re.compile(
    r"\b(?:never|not|n't)\b[^.]{0,60}?(?:\bbare\s+" + _RELEASE_TOKEN + r"|" + _RELEASE_TOKEN
    + r"[^.]{0,20}?\bdirectly\b)",
    re.I,
)


def _direct_release_bans(text: str) -> list[str]:
    """Whitespace-normalized first: a ban wrapped across a line break is still a ban."""
    return [m.group(0) for m in _DIRECT_RELEASE_BAN_RE.finditer(" ".join(text.split()))]


def test_direct_release_ban_predicate_can_fail():
    assert _direct_release_bans("Do NOT `pkill` an `odoo-bin` process or call\n`allocator.py release` directly.")
    assert _direct_release_bans("through Odoo - never a raw `dropdb` or a bare `allocator.py release`.")
    assert _direct_release_bans("never call lease_release directly on the batch lease")
    assert not _direct_release_bans("call `lease_release` with the batch's cached lease_token/run_id")
    assert not _direct_release_bans("Do NOT `pkill` an `odoo-bin` process. Call `lease_release` yourself.")


def test_no_agent_facing_file_forbids_releasing_an_owned_lease_directly():
    """The contract says: release directly what you own. A file that bans a direct release
    outright contradicts it and sends an orchestrator that OWNS the lease down a dispatch path
    instead - the contradiction the forward-port references carried."""
    offenders = []
    for f in _md_files("agents", "skills", "snippets"):
        for ban in _direct_release_bans(_read(f)):
            offenders.append(f"{_rel(f)}: {ban!r}")
    assert not offenders, (
        "these files forbid a direct release, contradicting resource-teardown-contract.md T1 "
        "('Release directly only what you own'):\n" + "\n".join(offenders)
    )
