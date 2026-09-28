"""A `--test-enable` build binds an HTTP port on EVERY series, so it must lease one.

Root cause this protects: `agents/odoo-instance-ops.md` and three reference docs told callers to
acquire `--ports 0` for a test run, on the premise that `--stop-after-init` (or `--no-http`) means
"binds no port". That premise is false, and has been false since v8. In `odoo/service/server.py`
(`openerp/service/server.py` on v8-v9) the spawn decision reads

    test_mode = config['test_enable'] or config['test_file']
    if test_mode or (config['http_enable'] and not stop):
        self.http_spawn()

so test mode SHORT-CIRCUITS the disjunction: neither `--no-http` nor `--stop-after-init` can stop
it. Verified against all twelve local checkouts v8-v19 (v19 drops `test_file` from the expression
and tests `config['test_enable']` directly - the same short-circuit, one term fewer).

Consequence measured on this host: a `run-tests` acquire following the documented `--ports 0`
advice died with `Address already in use / Port 8069 is in use by another program`, losing the
lease and the whole build; the same run with a reserved, forwarded port passed. This plugin
deliberately runs concurrent ephemeral instances, so the collision is a normal operating condition
rather than an edge case. The lesson was even recorded in this machine's own instance catalog by an
earlier run and never reached the plugin.

The port reaches odoo-bin through the lease: `instance_build` sets it and refuses a port flag in
`extra_args`, so the agent's job is only to lease one (`ports 1`) for every test build.

Run: python -m pytest tests/test_test_run_binds_a_port.py -v
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
AGENT = PLUGIN / "agents" / "odoo-instance-ops.md"
MODES = PLUGIN / "docs" / "reference" / "INSTANCE-ALLOCATION-MODES.md"
TESTING = PLUGIN / "docs" / "reference" / "ODOO-TESTING.md"
REGISTRY = PLUGIN / "docs" / "reference" / "INSTANCE-ALLOCATION-REGISTRY.md"


def _norm(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


def test_the_hard_rule_names_test_enable_as_the_discriminator():
    """`--stop-after-init` was the wrong discriminator, and naming the right one is the whole
    fix - a rule that only changed the flag would be obeyed until the next reader re-derived the
    old one from the same false premise."""
    text = _norm(AGENT)
    assert re.search(r"discriminator is `--test-enable`, NOT `--stop-after-init`", text), (
        "the ports HARD RULE must state which flag actually decides, not just which value to pass"
    )
    assert re.search(r"on every (Odoo )?series Odoo forces `http_spawn\(\)`", text), (
        "the rule must say the behaviour spans every supported series - a reader who thinks it is "
        "one series' quirk will re-derive the exception. It says so without spelling a version "
        "range: agent prose may not carry one (check_orchestration [version-claim])"
    )
    assert "http_spawn()" in text, "the rule must cite the mechanism it rests on"


def _section(text: str, heading: str) -> str:
    start = text.find(heading)
    assert start >= 0, f"the {heading!r} section moved - re-anchor this test"
    nxt = text.find(" ### ", start + len(heading))
    return text[start: nxt if nxt >= 0 else len(text)]


def test_the_run_tests_operation_leases_a_port_the_build_binds():
    """Reserving a port the build never binds leaves it on the config default, which is the same
    collision with an extra step. `instance_build` sets the lease's port itself and REFUSES a port
    flag in `extra_args` (INVALID_ARGUMENTS), so the agent must lease a port in BOTH modes,
    `fresh` and `reuse`, and must never be told to forward it as a flag."""
    text = _norm(AGENT)
    mech = text[text.find("**Mechanism.** A test build binds an HTTP port"):][:2200]
    assert mech.startswith("**Mechanism.**"), "the run-tests Mechanism paragraph moved - re-anchor this test"
    fresh = mech[mech.find("`fresh` ->"): mech.find("`reuse` ->")]
    reuse = mech[mech.find("`reuse` ->"): mech.find("Then `instance_build`")]
    assert fresh and reuse, "the Mechanism must name what `fresh` and `reuse` each lease"
    for name, leg in (("fresh", fresh), ("reuse", reuse)):
        assert "`lease_acquire`" in leg and "ports 1" in leg, f"a `{name}` test run must lease a port"
    assert not re.search(r"`?ports`? 0", mech), "the test run must not be told to lease no port"
    assert "`instance_build` binds that lease's port" in mech, (
        "the mechanism must say the build binds the leased port itself"
    )
    assert "never a port flag" in mech, (
        "instance_build refuses a port flag in extra_args - the mechanism must not forward one"
    )
    assert not re.search(r"--<HTTP-port flag>|HTTP-port flag>=", text), (
        "the retired `--<HTTP-port flag>=<lease port>` extra_args recipe is back"
    )


def test_a_reuse_run_gets_its_own_port_even_on_a_serving_handle():
    """A `reuse` run targets a forwarded handle's database, which may be SERVING: its server holds
    the handle's port. Building on that port collides; refusing the run loses a capability the
    agent had. The run takes its own `exclusive`, `no_create` lease on the handle's database - a
    fresh pooled port, nothing created or dropped - and leaves the handle's lease alone."""
    text = _norm(AGENT)
    mech = text[text.find("**Mechanism.** A test build binds an HTTP port"):][:2200]
    reuse = mech[mech.find("`reuse` ->"): mech.find("Then `instance_build`")]
    assert "mode `exclusive`" in reuse and "`db_name` = the handle's `db_name`" in reuse
    assert "`no_create` true" in reuse, "the reuse lease must never create or drop the handle's database"
    assert "never release or park it" in reuse, "the handle's lease stays the caller's"
    assert "NEEDS_CONTEXT" not in reuse, "a serving handle is no reason to refuse the run"


def test_no_document_pairs_ports_zero_with_a_test_run():
    """Whole-corpus guard. The advice lived in four files and one of them was the SSOT the rest
    inherited from, so fixing any subset leaves the wrong rule reachable."""
    # Scanned as a WINDOW around each occurrence, on whitespace-normalized text. Neither of the
    # two obvious granularities works on this corpus: a markdown table row holds several
    # independent claims, so sentence-splitting invents adjacencies that are not in the text, and
    # a prose line can wrap mid-clause, so line-splitting tears an exclusion away from the rule it
    # qualifies. Both produced false positives on the very sentences that state the fix.
    exempt = re.compile(
        r"NOT such a pass"
        r"|only for a run that binds NO HTTP port"
        r"|binds nothing"
        r"|needs `--ports 1`"
        r"|one pooled port for ANY"
        r"|a plain `-i`/`-u`"
    )
    offenders = []
    for path in (AGENT, MODES, TESTING, REGISTRY):
        text = _norm(path)
        for m in re.finditer(r"(?:--)?`?\bports`?:? ?0\b", text):
            window = text[max(0, m.start() - 200): m.end() + 200]
            if not re.search(r"--test-enable|\btests?\b|run-tests", window, re.I):
                continue
            if exempt.search(window):
                continue
            offenders.append(f"{path.name}: ...{window[:200]}...")
    assert not offenders, (
        "these sentences still recommend --ports 0 for a run that binds a port:\n  "
        + "\n  ".join(offenders)
    )


def test_the_false_invariant_is_gone_from_its_ssot():
    """`Port leasing applies only when a server actually listens` reads as a definition and was
    the premise every other site inherited. Leaving it while changing the flags would let the next
    reader re-derive the removed advice from first principles."""
    text = _norm(MODES)
    assert "Port leasing applies only when a server actually listens" not in text, (
        "the false invariant must be removed, not merely contradicted elsewhere"
    )
    assert "A `--test-enable` build is NOT such a pass" in text, (
        "its replacement must name the exception explicitly, in the same place"
    )


def test_the_non_test_paths_keep_ports_zero():
    """Scope discipline, and the inverted defect this could easily become: an `-i`/`-u`/
    `--load-language` pass with `--stop-after-init` genuinely binds nothing, and rewriting those
    to lease a port would waste a pooled port on every install for no reason."""
    text = _norm(AGENT)
    for heading in ("### 3. init-modules", "### 7. load-language"):
        section = _section(text, heading)
        assert re.search(r"`lease_acquire`\s*\(`series`, mode `exclusive`, `db_name`, `no_create` true, ports 0\)",
                         section), f"{heading}: an existing-database build binds no port and leases ports 0"
        assert "ports 1" not in section, f"{heading}: must not lease a port it never binds"
