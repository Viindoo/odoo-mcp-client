"""Behavioral gate: the build facts an executing agent must get right per series.

Three facts decide what an Odoo build reproduces: which lint modules the backend gate is made of,
which modules load server-wide (`--load`), and whether the database carries demo data. The last
two are applied by the odoo-local tools (instance_build / instance_serve read the server-wide set
from the lease's catalog row and spell the series' demo flag from a `demo` argument - proven in
tests/test_odoo_local_mcp_build_facts.py); what the prose still owns is the JUDGEMENT: which demo
shape each build purpose needs, what to do when a build warns that a module must load server-wide,
and never teaching a second, hand-composed path. The first is still resolved by the agent.

These assertions lock in (1) the lint gate membership per series, (2) the server-wide rule stated
once and no per-series module table left for an agent to copy, (3) demo decided by build purpose,
with a test build never running on demo data where the series' default loads none, and (4) the
series-correct `-i`/`-u` rule for a test run on an existing database. The facts are single-sourced
in snippets/odoo-version-pivots.md; the negative sweeps stop a consumer re-growing a stale copy.

Run: python -m pytest tests/test_viindoo_build_facts.py -v
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN = REPO_ROOT / "plugins" / "odoo-ai-agents"

PIVOTS = PLUGIN / "snippets" / "odoo-version-pivots.md"
LINT_GATE = PLUGIN / "snippets" / "lint-gate-modules.md"
AGENT_MD = PLUGIN / "agents" / "odoo-instance-ops.md"


def _norm(path: Path) -> str:
    """Whitespace-normalized text, so a reflow never silently drops a guarded claim.

    Blockquote markers are stripped first: much of the load-bearing prose here lives in `>`
    callouts, where a line wrap would otherwise leave a stray `>` mid-sentence and make a
    guarded phrase unmatchable for a reason that has nothing to do with the claim.
    """
    raw = path.read_text(encoding="utf-8")
    unquoted = re.sub(r"(?m)^\s*>\s?", "", raw)
    return re.sub(r"\s+", " ", unquoted)


AGENT_FACING_SUFFIXES = {".md", ".yaml", ".yml", ".json", ".sh"}


def _agent_facing_md() -> list[Path]:
    """Every file an executing agent can load at runtime, whatever its extension.

    Rooted at the plugin, not at a hand-listed set of directories: the two sites this change
    had to correct - `README.md` at the plugin root and `generator/skill_tool_deps.json` - sit
    outside any such list, so a directory-scoped sweep would have passed while the stale claim
    was still shipping. Workflows are YAML and evals are JSON, so extension scoping matters too.
    """
    return sorted(
        p
        for p in PLUGIN.rglob("*")
        if p.is_file() and p.suffix in AGENT_FACING_SUFFIXES and ".git" not in p.parts
    )


# --- (1) lint-class gate membership -----------------------------------------------------


def test_pivots_states_the_lint_module_name_per_series():
    """The Viindoo lint module is named differently below and above the rename boundary.

    Tagging the wrong name selects nothing and installs nothing, and the run still passes.
    """
    text = _norm(PIVOTS)
    assert "test_viin_pylint" in text, "pivots must name the current Viindoo lint module"
    assert "test_pylint" in text, "pivots must name the earlier Viindoo lint module"
    # Assert the BOUNDARY holds, not the literal range strings this same commit wrote: a range
    # spelled wrong would satisfy a string match while sending every build to the wrong module.
    # Each name must carry a bound, and the two bounds must not overlap.
    current = re.search(r"`test_viin_pylint`[^|]*\|[^|]*\|\s*v(\d+)\+", text)
    assert current, "the current name's row must give a `vN+` lower bound"
    earlier = re.search(r"`test_pylint`[^|]*\|[^|]*\|\s*v(\d+)(?:-v(\d+))? ONLY", text)
    assert earlier, "the earlier name's row must give an explicit `ONLY` series bound"
    earlier_high = int(earlier.group(2) or earlier.group(1))
    assert earlier_high < int(current.group(1)), (
        f"the two Viindoo lint names must not overlap: earlier covers up to v{earlier_high}, "
        f"current starts at v{current.group(1)}"
    )


def test_pivots_forbids_installing_both_viindoo_lint_names():
    """They are ONE gate under two names - both in one build is a defect, not redundancy."""
    text = _norm(PIVOTS)
    assert "never install or tag both" in text.lower(), (
        "pivots must forbid carrying both Viindoo lint names into one build"
    )


def test_lint_gate_snippet_owns_the_candidate_set_and_the_stale_index_rule():
    """The probe alone cannot prove presence - a stale index answers Yes for a dead name."""
    text = _norm(LINT_GATE)
    for module in ("test_lint", "test_pylint", "test_viin_pylint"):
        assert module in text, f"lint-gate snippet must list {module} as a candidate"
    assert "stale" in text.lower(), "lint-gate snippet must state the index can be stale"
    assert "FALSE GREEN" in text, (
        "lint-gate snippet must name the false-green outcome a stale probe produces"
    )
    assert "tests-inconclusive" in text, (
        "a tagged module whose tests never loaded must be inconclusive, never a pass"
    )


def test_no_file_restates_a_stale_lint_module_version_claim():
    """A consumer that spells the version range grows its own copy, and that copy rots.

    This is the sweep that caught the original defect: the rename landed and eighteen
    restatements kept naming the old module for the new series.
    """
    offenders = []
    for path in _agent_facing_md():
        if path.name in {"odoo-version-pivots.md", "lint-gate-modules.md"}:
            continue
        text = _norm(path)
        # Match EITHER Viindoo lint name near a version token, in either order, and do not let a
        # period end the window: the original defect was written as "... module (v16+). **Full"
        # and a period-terminated window would have skipped it.
        if re.search(r"test_(?:viin_)?pylint.{0,90}?\bv\d\d\b", text) or re.search(
            r"\bv\d\d\b\+?.{0,60}?test_(?:viin_)?pylint", text
        ):
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, (
        "these files restate which series carries which lint module instead of pointing at "
        f"snippets/odoo-version-pivots.md: {offenders}"
    )


# --- (2) server-wide modules on --load --------------------------------------------------


def _pivot_section(start: str, end: str) -> str:
    text = _norm(PIVOTS)
    s = text.find(start)
    assert s != -1, f"pivots section {start!r} not found - re-anchor this test"
    e = text.find(end, s + 1)
    return text[s: e if e != -1 else len(text)]


def test_pivots_states_the_tools_apply_the_build_facts():
    """The rule is stated once: the tools apply --load, the languages and the demo flag."""
    facts = _pivot_section("## Build facts the odoo-local tools apply", "### Demo data by build PURPOSE")
    for fact in ("`--load`", "`--load-language`", "demo flag"):
        assert fact in facts, f"the build-facts SSOT must name {fact} as applied by the tools"
    assert "never compose them by hand" in facts and "`extra_args`" in facts, (
        "the SSOT must forbid composing the build facts in extra_args"
    )
    assert "core default (read from the lease's Odoo checkout)" in facts, (
        "the core server-wide default is a source fact the tool reads, not a table to copy"
    )
    assert "fixed on the lease when it is acquired" in facts, (
        "a catalog change only reaches a lease acquired after it - the remedy depends on that"
    )


def test_server_wide_warning_is_remedied_through_the_catalog_and_a_new_lease():
    """A build that silently ran without a server-wide module still 'succeeds' - only job_wait's
    warning shows it, so the prose must say what to do with it: fix the catalog row, re-acquire,
    and never work around it with an ordinary install."""
    facts = _pivot_section("## Build facts the odoo-local tools apply", "### Demo data by build PURPOSE")
    assert "/odoo-ai-agents:odoo-setup refresh" in facts, "the remedy must name the setup refresh"
    assert re.search(r"release the lease and acquire a new one", facts), (
        "the remedy must re-acquire: the server-wide set is fixed at acquire"
    )
    assert re.search(r"Never answer it by installing the module with `-i`", facts), (
        "an ordinary -i install misses the boot-time patch point; the prose must forbid it"
    )
    rule = _norm(AGENT_MD)
    rule = rule[rule.index("## Demo, languages and server-wide modules (HARD RULE)"):]
    rule = rule[: rule.index("## Lint modules")]
    assert re.search(r"must be loaded server-wide means the catalog row lacks it", rule), (
        "the agent must treat a server-wide warning as an untrusted instance"
    )
    assert "NEEDS_CONTEXT" in rule and "tests-inconclusive" in rule, (
        "the agent must not report a build or a test run green while that warning stands"
    )


def test_no_agent_facing_file_carries_a_server_wide_module_table():
    """The per-series core default and the deployment set used to be a table agents copied into
    --load. The core default is now read from the checkout and the deployment set lives in the
    catalog row, so any copy left in prose is a second, rotting source for a flag the tool
    refuses anyway."""
    stale = re.compile(
        r"base,rpc,web|web,web_kanban|to_erponline_utility,viin_brand|CLI - server-wide modules"
        r"|Viindoo set to union|Some Yes, some No"
    )
    offenders = [
        str(p.relative_to(REPO_ROOT))
        for p in _agent_facing_md()
        if "scripts" not in p.relative_to(PLUGIN).parts and stale.search(_norm(p))
    ]
    assert not offenders, (
        "these files still carry the per-series server-wide module table or its probe rule; the "
        f"tools apply --load from the lease's catalog row: {offenders}"
    )


def test_no_agent_facing_prose_passes_load_modules():
    """instance_serve's `load_modules` input was removed; a call written with it is refused.

    Only a statement that the input is GONE ("no `load_modules`") may still name it."""
    passes = re.compile(r"(?<!no )(?<!no `)\bload_modules\b")
    offenders = [
        str(p.relative_to(REPO_ROOT))
        for p in _agent_facing_md()
        if "scripts" not in p.relative_to(PLUGIN).parts
        and passes.search(_norm(p))
    ]
    assert not offenders, f"these files still pass instance_serve a load_modules argument: {offenders}"


# --- (3) demo data by build purpose -----------------------------------------------------


def test_pivots_states_demo_by_build_purpose():
    """Which purposes carry demo is the decision; the tool only spells the flag."""
    text = _norm(PIVOTS)
    assert "Demo data by build PURPOSE" in text, (
        "pivots must carry the purpose-keyed demo section"
    )
    assert "GATE_ROLE: node-verify" in text and "GATE_ROLE: pre-pr-lint-gate" in text, (
        "the automation-test row must name both gate roles, so neither is read as an exception"
    )
    table = _pivot_section("### Demo data by build PURPOSE", "### Test run on an existing database")
    rows = {cells[0]: cells[1:] for cells in (
        [c.strip() for c in ln.split("|")[1:-1]] for ln in
        PIVOTS.read_text(encoding="utf-8").splitlines() if ln.startswith("| ")
    ) if len(cells) == 3}
    def row(prefix):
        hit = [v for k, v in rows.items() if k.startswith(prefix)]
        assert hit, f"the purpose table must carry a row starting {prefix!r}"
        return hit[0]
    test_default_demo, test_no_demo = row("Automation test run")
    for cell in (test_default_demo, test_no_demo):
        assert cell.startswith("series default (omit `demo`)"), (
            "a test build never passes demo on any series: it runs the series default the tool "
            "reads from the checkout, so neither cell may name a value to pass"
        )
    assert "`TEST_DB_HAS_DEMO`" in test_no_demo and "passes `off`" in test_no_demo, (
        "where the series' default loads no demo, a test build never runs on a demo DB, and the "
        "init its database comes from passes off"
    )
    assert "passes `on`" in test_default_demo, (
        "where the series' default loads demo, the init a test build reuses keeps it - disabling "
        "it would change what that series' own CI reproduces"
    )
    for purpose in ("Translation export", "Acceptance live-UI sweep", "Documentation capture"):
        assert all(v.startswith("`on`") for v in row(purpose)), (
            f"{purpose} builds carry demo on every series"
        )
    assert "`demo` on a series whose default loads none" in table


def test_pivots_forbids_demo_dependent_tests_where_demo_is_off():
    """A test authored on a demo-carrying instance still runs demo-less in the gate later."""
    text = _norm(PIVOTS)
    assert "setUpClass" in text, (
        "pivots must tell a test author to create its own records"
    )
    assert "MUST NOT reference a demo record" in text, (
        "pivots must forbid referencing a demo record from a durable test"
    )


def test_agent_never_passes_demo_on_an_automation_test_build():
    """A test build runs the series default the tool reads from the checkout, so the agent passes
    no demo there and does not apply a brief's DEMO. A forwarded demo database is never planned as a
    reuse target, and when the tool refuses one (it reads demo from the DATABASE, whichever lease
    built it) the agent falls back to a fresh run on its own lease instead of retrying."""
    text = _norm(AGENT_MD)
    assert "Demo, languages and server-wide modules (HARD RULE)" in text, (
        "the agent must own the build-facts HARD RULE section"
    )
    rule = text[text.index("## Demo, languages and server-wide modules (HARD RULE)"):]
    rule = rule[: rule.index("## Lint modules")]
    assert "Never pass `demo` on a test build" in rule and "omit `demo` on op `test`" in rule, (
        "the agent must omit demo on every test build - the series default applies"
    )
    assert re.search(r"A `DEMO:` field on a run-tests dispatch is never applied", rule), (
        "a brief's DEMO on a test dispatch must not reach instance_build"
    )
    assert not re.search(r"Pass `demo` on every `init` and `test` build", rule), (
        "the old rule told the agent to pass demo on test builds"
    )
    run_tests = text[text.index("### 5. run-tests"):text.index("### 6.")]
    call = re.search(r"Then `instance_build` \(op `test`[^)]*\)", run_tests)
    assert call and re.search(r"no `demo`", call.group(0)), (
        "the run-tests instance_build call must say it passes no demo"
    )
    assert re.search(r"whose `demo` is `true` is never a `reuse` target", text), (
        "a forwarded demo handle must stay out of the reuse plan - a refused build costs a round trip"
    )
    assert re.search(r"refuses a test build on any database holding demo[^.]*forwarded one included"
                     r"[^.]*`TEST_DB_HAS_DEMO`\): on that refusal, run `fresh` on your own ephemeral lease",
                     rule), "rule 2 must match the tool: it refuses a forwarded demo database, and the "\
        "agent answers the refusal with a fresh run on its own lease"
    assert "this check is yours" not in rule and "records none" not in rule, (
        "the tool now sees a forwarded database's demo; the rule must not claim the check is the agent's alone"
    )


def test_acceptance_durable_run_never_reuses_the_demo_cluster():
    """Acceptance provisions its cluster WITH demo; its tour/HttpCase run must not execute there."""
    text = _norm(PLUGIN / "skills/odoo-acceptance/SKILL.md")
    phase = text[text.index("## Phase 2a"):text.index("## Phase 2b")]
    assert re.search(r"builds on a FRESH lease", phase), "Phase 2a's test run needs its own lease"
    assert "NEVER on Phase 2's `INSTANCE_HANDLE`" in phase, (
        "Phase 2a must not run the suite on the demo-carrying cluster handle"
    )
    phase2 = text[text.index("## Phase 2 - provision the cluster"):text.index("## Phase 2a")]
    assert "`demo: on`" in phase2, "the acceptance cluster itself keeps demo on"
    assert "except the Phase 2a test run" in phase2, (
        "the handle-forwarding rule must carve out the durable test run it would contradict"
    )


def test_acceptance_never_runs_on_a_test_or_verify_handle():
    """Acceptance instances carry demo; a test/verify build carries the series default, which is no
    demo where demo is opt-in. So no pipeline may forward its verify handle into odoo-acceptance,
    and acceptance itself must refuse a forwarded handle that holds no demo."""
    fp = _norm(PLUGIN / "skills/odoo-forward-port/SKILL.md")
    p11 = fp[fp.index("**P11 - End-to-end acceptance"):fp.index("**P12 - PR + review")]
    assert "`INSTANCE_HANDLE: none provisioned` - NEVER P9's verify handle" in p11, (
        "forward-port P11 must not forward the P9 verify handle into acceptance"
    )
    assert "`INSTANCE_HANDLE` from P9" not in fp, "the old reuse instruction must be gone"
    fpm = _norm(PLUGIN / "snippets/fp-merge-absorption.md")
    assert "which reuses the same `INSTANCE_HANDLE`" not in fpm, (
        "the verify protocol must not say P11 acceptance reuses the per-batch verify handle"
    )
    assert "P11 acceptance never reuses this handle" in fpm
    up = _norm(PLUGIN / "skills/odoo-modules-upgrade/SKILL.md")
    p58 = up[up.index("**P5.8 - Acceptance"):up.index("**P6 - Gate")]
    assert "`INSTANCE_HANDLE: none provisioned` - NEVER the P5 test handle" in p58, (
        "modules-upgrade P5.8 must not forward the P5 test handle into acceptance"
    )
    assert "`INSTANCE_HANDLE` from P5" not in up
    detail = _norm(PLUGIN / "skills/odoo-modules-upgrade/references/upg-phase-detail.md")
    p57 = detail[detail.index("## P5.7 - i18n reconcile"):]
    assert "INSTANCE: SELF_PROVISION" in p57 and "Inherit the P5" not in p57, (
        "the P5.7 export build needs demo AND the target languages from ONE build - never the P5 "
        "test instance"
    )
    acc = _norm(PLUGIN / "skills/odoo-acceptance/SKILL.md")
    inputs = acc[acc.index("## Inputs"):acc.index("## Phase 0")]
    assert re.search(r"`INSTANCE_HANDLE` if a run already provisioned one AND its `demo` is `true`",
                     inputs), "acceptance must refuse a forwarded handle that holds no demo"


# --- (4) test run on an existing database -----------------------------------------------


def test_pivots_states_the_series_correct_reuse_rule():
    """`-u` re-runs an installed module's tests on every series; `-i` stops doing so at a boundary."""
    section = _pivot_section("### Test run on an existing database", "## Framework-validation")
    assert re.search(r"`test_mode` `reuse` \(`-u`\) - right on every series", section)
    assert re.search(r"from v\d+ `-i` skips an installed module and runs none of its tests", section)


def test_no_file_claims_i_on_an_installed_module_is_a_no_op_everywhere():
    """That claim is true from one series on only; stated flat it teaches the wrong reason for a
    rule whose conclusion (use -u) is right everywhere."""
    pattern = re.compile(r"`?-i`? on an (?:already[- ])?installed module is a no-op", re.I)
    offenders = [
        str(p.relative_to(REPO_ROOT))
        for p in _agent_facing_md()
        if pattern.search(_norm(p))
    ]
    assert not offenders, (
        "these files state flatly that -i on an installed module is a no-op; point at "
        f"odoo-version-pivots.md § Test run on an existing database instead: {offenders}"
    )


def test_demo_load_verification_is_its_own_install_only_build():
    """Dropping demo from the test gate must not drop the only check that demo still loads.

    An installable-flip is the first time a module's `demo/` XML is ever loaded. When the suite
    runs demo-less, nothing else exercises that XML, so broken demo data ships unnoticed - while
    the plugin separately REQUIRES every user-visible feature to ship demo data. The two must be
    separate builds: merging them puts demo rows inside a suite that counts records.
    """
    text = _norm(PIVOTS)
    assert "Demo-load verification" in text, (
        "pivots must carry a purpose row for proving a module's own demo data still loads - "
        "without it the agent BLOCKs on that build as an unresolvable purpose"
    )
    row = next(
        (ln for ln in text.split("|") if "Demo-load verification" in ln), ""
    )
    assert re.search(r"install only", row, re.I) and re.search(
        r"never carries `--test-enable`|no `--test-enable`", row, re.I
    ), (
        "the demo-load row must state it never carries --test-enable, which is the only reason "
        f"it may ask for demo at all; row was: {row!r}"
    )

    parity = _norm(PLUGIN / "skills/odoo-modules-upgrade/references/runbot-parity-checklist.md")
    assert "Gate 7b" in parity, "the upgrade parity checklist must carry the demo-load gate"
    gate = parity[parity.index("Gate 7b"):]
    assert re.search(r"(NO|no|never)\s+`?--test-enable`?", gate), (
        "Gate 7b's command must forbid --test-enable inline, where it is copied from"
    )


def test_demo_load_gate_does_not_key_its_verdict_on_exit_code():
    """The gate would otherwise pass on exactly the breakage it exists to catch.

    Odoo catches every exception from a module's demo load, logs a WARNING, records an
    `ir.demo_failure` row, and finishes installing the module WITHOUT its demo data - exit 0,
    completion marker printed. A verdict read from the exit code is therefore green on broken
    demo XML, so this gate has to key on the warning instead.
    """
    parity = _norm(PLUGIN / "skills/odoo-modules-upgrade/references/runbot-parity-checklist.md")
    gate = parity[parity.index("Gate 7b"):]
    # The requirement is behavioural, not a phrasing: the gate must (a) warn that the exit code
    # alone is not the verdict here, and (b) name a signal to read instead. How it words either is
    # free - pinning the sentence is what makes a correct rewrite turn CI red.
    assert "exit code" in gate.lower(), (
        "Gate 7b must address the exit code, which is green on a failed demo load"
    )
    assert re.search(
        r"demo[- ]failure warning|demo data failed to install|_INSTALL_FAIL_RE|STATUS=error", gate
    ), (
        "Gate 7b must name at least one concrete failure signal to read instead of the exit code"
    )


def test_flip_gates_are_reachable_from_the_phase_that_triggers_them():
    """A gate nothing routes to is a gate that never runs.

    The installable-flip gates live in the parity checklist, but the pipeline phase that detects
    the flip is what an agent actually walks. Without an explicit pointer naming BOTH gates, an
    agent following the phase steps literally never reaches them.
    """
    phase = _norm(PLUGIN / "skills/odoo-modules-upgrade/references/upg-phase-detail.md")
    assert "Gate 7" in phase and "Gate 7b" in phase, (
        "the upgrade phase detail must name BOTH installable-flip gates, not just the demo one"
    )
    assert "they ADD to Step 3, they never replace it" in phase, (
        "the phase must say whether the flip gates replace or supplement the per-level run - "
        "leaving that open makes the agent invent an answer"
    )


def test_every_test_enable_example_actually_enables_tests():
    """`--test-tags` only filters; without `--test-enable` the run tests nothing and exits 0.

    That is a silent false green of the same family as a tagged-but-uninstalled lint module, so no
    example in the parity checklist may carry tags without enabling the suite.
    """
    raw = (PLUGIN / "skills/odoo-modules-upgrade/references/runbot-parity-checklist.md").read_text(
        encoding="utf-8"
    )
    # Rejoin shell continuations first: an odoo-bin example spans several lines, and judging each
    # line alone would flag the half that carries the tags while its --test-enable sits one line up.
    commands, current = [], ""
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.startswith(("#", ">", "|")):
            current = ""
            continue
        current += " " + stripped
        if stripped.endswith("\\"):
            continue
        commands.append(current)
        current = ""
    offenders = [
        c.strip()
        for c in commands
        # Only an actual invocation counts; prose that merely MENTIONS the flag is not a command.
        if "odoo-bin" in c and "--test-tags" in c and "--test-enable" not in c
    ]
    assert not offenders, (
        "these command lines filter a test run that was never enabled, so they run zero tests and "
        f"still exit 0: {offenders}"
    )


def test_framework_validation_classes_carry_both_boundaries():
    """Neither class spans the indexed range, and they move in OPPOSITE directions.

    One appears partway through the range; the other is removed before the end. A `--test-tags`
    entry naming a class the series does not ship matches nothing and the run still exits 0, so a
    gate that names the pair unconditionally is green on both sides of the range while testing
    nothing.
    """
    text = _norm(PIVOTS)
    assert "Framework-validation test classes" in text, (
        "pivots must own the framework-validation class boundaries"
    )
    assert "RENAMED to `TestSelfAccessPreferences` at v19" in text, (
        "the hr self-access class was RENAMED at v19, not removed - reading 'the old name is "
        "absent' as 'the check is gone' silently drops an enforcement that still runs"
    )
    assert "TestSelfAccessPreferences" in text, "pivots must name the current hr class"
    # Bounds pinned because they were wrong twice: read from each checkout's own addons/ tree.
    assert "v18+ only" in text.lower(), "the base view-arch class appears at v18, not earlier"
    assert "v13-v18" in text, (
        "the hr class spans v13-v18 under its old name - a bound starting later drops a gate "
        "that exists"
    )
    assert "/base:TestInvisibleField" in text and "/hr:TestSelfAccessProfile" in text, (
        "pivots must give the COPYABLE tag spec for each class, colon-separated"
    )
    assert "SILENT no-op, not an error" in text, (
        "pivots must state that tagging an absent class fails silently rather than erroring"
    )


def test_framework_class_list_states_its_admission_criteria():
    """Without a stated boundary the list grows, and every entry is a new rot point.

    Odoo and Viindoo ship hundreds of thousands of tests. This table names two, and the reason it
    names exactly those two has to be written down - otherwise the next person adds a third.
    """
    text = _norm(PIVOTS)
    section = text[text.index("Framework-validation test classes"):]
    section = section[: section.index("## JavaScript / OWL / tests")]
    assert "all three hold" in section, (
        "the framework-class table must state the admission criteria for a row"
    )
    low = section.lower()
    for condition in ("framework class", "this plugin teaches", "skips it"):
        assert condition in low, (
            f"the admission criteria must include {condition!r} - all three are what keep the "
            "list from growing into a mirror of Odoo's test suite"
        )


def test_untagged_gate_does_not_name_framework_classes():
    """Naming them inside an already-untagged run adds no coverage and all of the rot.

    The parity gate runs untagged precisely so every framework class runs without being named.
    A `--test-tags` list there is redundant, and it is the line that rotted twice.
    """
    parity = _norm(PLUGIN / "skills/odoo-modules-upgrade/references/runbot-parity-checklist.md")
    for name in ("TestInvisibleField", "TestSelfAccessProfile", "TestSelfAccessPreferences"):
        assert name not in parity, (
            f"the untagged parity gate must not name {name} - it already runs every framework "
            "class, so the name buys nothing and has to be re-verified every series"
        )


def test_no_test_tags_example_spells_a_class_with_a_dot():
    """`module.Class` in a tag spec selects NOTHING, and nothing errors.

    Odoo's selector grammar is `[-][tag][/module][:class][.method]` - the class separator is a
    COLON. `base.TestInvisibleField` therefore parses as tag `base` plus METHOD
    `TestInvisibleField`, matches no method that exists, and the run exits 0 having tested nothing.
    Every example an agent might copy has to use the colon form.
    """
    offenders = []
    for path in _agent_facing_md():
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            if "test-tags" not in raw_line and "test_tags" not in raw_line:
                continue
            # A dotted CapitalisedName inside a tag spec is the defect; `/mod:Class.method` is fine.
            if re.search(r"[,'\"\s/]\w+\.[A-Z]\w+", raw_line) and ":" not in raw_line:
                offenders.append(f"{path.relative_to(REPO_ROOT)}: {raw_line.strip()[:90]}")
    assert not offenders, (
        "these --test-tags examples name a class with a dot, which selects nothing and still "
        f"exits 0; use /module:ClassName instead: {offenders}"
    )


def test_no_consumer_tags_both_framework_classes_unconditionally():
    """A consumer that hardcodes the pair is wrong on one side of the range or the other."""
    offenders = []
    for path in _agent_facing_md():
        if path.name == "odoo-version-pivots.md":
            continue
        text = _norm(path)
        if "TestInvisibleField" in text and "TestSelfAccessProfile" in text:
            if "Framework-validation test classes" not in text:
                offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, (
        "these files name both framework-validation classes without pointing at the per-series "
        f"boundary that says which one the target actually ships: {offenders}"
    )


def test_upgrade_test_gate_never_asks_for_demo():
    """The defect this change fixes: a v19 upgrade suite run with demo, failing correct tests.

    A record-counting test is inflated by demo rows, so the suite looks broken and the tempting
    repair is to weaken the test. Neither upgrade file may reinstate an unconditional demo=on.
    """
    for rel in (
        "skills/odoo-modules-upgrade/SKILL.md",
        "skills/odoo-modules-upgrade/references/upg-phase-detail.md",
        # Gate 7's demo shape lives here, so leaving it out let a demo=on reappear un-caught.
        "skills/odoo-modules-upgrade/references/runbot-parity-checklist.md",
    ):
        text = _norm(PLUGIN / rel)
        assert "demo=on" not in text, (
            f"{rel} still prescribes an unconditional demo=on for the install + test gate; "
            "the demo shape must come from the automation-test purpose row instead"
        )


def test_no_file_spells_the_demo_enable_flag_with_a_value():
    """`--with-demo` takes no value - a `=<value>` form dies at option parsing (issue #252).

    The prose stated this correctly while the copy-paste template a few hundred lines below
    contradicted it, so the sweep covers every agent-facing file rather than that one section.
    """
    offenders = []
    for path in _agent_facing_md():
        if "--with-demo=" in path.read_text(encoding="utf-8"):
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, (
        "`--with-demo` takes no value; these files spell it with one and would fail at "
        f"option parsing: {offenders}"
    )


def test_handle_demo_and_languages_are_facts_of_the_database():
    """A handle forwarded on another lease of the same database must state what that database
    holds: the tools refuse a test build or an i18n export by the DATABASE's demo and languages, so
    prose that ties the facts to one lease teaches an agent to trust a handle the tools reject."""
    handle = _norm(PLUGIN / "snippets/instance-handle-contract.md")
    assert "`demo` - whether the DATABASE holds demo data" in handle
    assert "`languages_loaded` - the languages active in the DATABASE" in handle
    assert re.search(r"`facts_source` - who answered `demo` / `languages_loaded`: `database` [^-]*"
                     r"or `leases`", handle), (
        "the handle must carry facts_source: the tools answer from the database itself and fall "
        "back to the leases' build records only when it cannot be read"
    )
    assert "facts of the database, whichever lease built it" in handle
    offenders = [str(p.relative_to(REPO_ROOT)) for p in _agent_facing_md()
                 if "scripts" not in p.relative_to(PLUGIN).parts
                 and re.search(r"the lease records it|lease you take on a forwarded database records",
                               _norm(p))]
    assert not offenders, f"these files still tie demo to the lease that built it: {offenders}"
