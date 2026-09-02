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

The flag NAME is series-dependent and this test does not restate it - `agents/odoo-instance-ops.md`
already owns that table (`--xmlrpc-port` v8-v10, `--http-port` v11+, legacy aliases REMOVED at
v19), and restating it here is how the two copies drift.

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
    assert "v8 through v19" in text or "v8-v19" in text, (
        "the rule must say the behaviour spans every supported series - a reader who thinks it is "
        "one series' quirk will re-derive the exception"
    )
    assert "http_spawn()" in text, "the rule must cite the mechanism it rests on"


def test_the_run_tests_operation_leases_and_forwards_a_port():
    """Reserving a port and never passing it to odoo-bin leaves the build on the config default,
    which is the same collision with an extra step. `55-instance-ops.sh` carries no port plumbing,
    so `--extra` is the entire path by which a test build learns its port."""
    text = _norm(AGENT)
    mech = text[text.find("**Mechanism:** `fresh` -> run Steps A-D"):][:1400]
    assert mech, "the run-tests Mechanism paragraph moved - re-anchor this test"
    assert "--ports 1" in mech, "a test run must lease a port"
    assert "--ports 0" not in mech, "the test run must not be told to lease no port"
    assert "--extra" in mech, "the leased port must be forwarded to odoo-bin"
    assert "HTTP port" in mech and "cli_help" in mech, (
        "the port flag NAME is series-dependent; the mechanism must point at the version table "
        "and at cli_help rather than hardcoding one spelling"
    )


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
        for m in re.finditer(r"--ports 0", text):
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
    to `--ports 1` would waste a pooled port on every install for no reason."""
    text = _norm(AGENT)
    for context in ("init-modules", "load-language"):
        assert context in text, f"expected the {context} operation to still exist"
    assert "`exclusive` lease and `--ports 0` (no HTTP port needed)" in text, (
        "the load-language path binds no port and must keep --ports 0"
    )
