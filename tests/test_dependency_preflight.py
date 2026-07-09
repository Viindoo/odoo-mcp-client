"""Behavioral guard: dependency-resolvability pre-flight + who owns the classification.

Business rules this protects (solution-v2 § 4.4, survey C root cause):

- The hard-leaf backend coder (`agents/odoo-backend-coder.md`) runs a depends-resolvability PRE-FLIGHT before any
  `odoo-bin -i/-u --test-enable`, resolving every manifest `depends` entry via `check_module_exists`
  (OSM) OR presence on the `--addons-path`, and on a MISS emits a RAW, verbatim
  `BLOCKED: manifest dependency <dep> unresolved on addons-path` and STOPS. This turns the opaque
  Odoo manifest-resolution crash into a clean, graceful status.
- The coder does NOT classify (in-progress vs absent) and is LEDGER-UNAWARE - it holds neither the
  in-set sibling list nor any DONE status.
- The `odoo-coding` dispatch loop (not the coder) owns the decision table on that BLOCKED and is the
  sole ledger writer.

These are CONTRACT checks (the rule + the ownership split are present), not string-count snapshots.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"

# The dependency pre-flight lives on the backend WRITER (odoo-backend-coder), the hard leaf that
# actually runs odoo-bin -i/-u; the odoo-coder LEAD is a coordinator that does not run the pre-flight.
CODER = PLUGIN / "agents" / "odoo-backend-coder.md"
CODING = PLUGIN / "skills" / "odoo-coding" / "SKILL.md"
LEDGER = PLUGIN / "snippets" / "module-coordination-ledger.md"

RAW_BLOCKED = "BLOCKED: manifest dependency <dep> unresolved on addons-path"


def test_coder_has_dependency_preflight_before_odoo_bin():
    """The coder must run a depends-resolvability pre-flight before an install/update run.

    Fails if: the pre-flight (resolve every `depends` via check_module_exists OR addons-path
    presence, before odoo-bin -i/-u --test-enable) is removed - a missing dep would then surface as
    an opaque Odoo manifest crash instead of a graceful BLOCKED.
    """
    text = CODER.read_text(encoding="utf-8")
    low = text.lower()
    assert "dependency pre-flight" in low, (
        "odoo-coder.md must carry a 'Dependency pre-flight' section run before odoo-bin -i/-u "
        "--test-enable."
    )
    assert "check_module_exists" in text, (
        "The pre-flight must resolve each depends via check_module_exists (OSM)."
    )
    assert "addons-path" in low, (
        "The pre-flight must fall back to presence on the effective --addons-path."
    )
    # It gates the actual install/update run.
    assert "--test-enable" in text and "depends" in low, (
        "The pre-flight must resolve every manifest `depends` entry before the --test-enable run."
    )


def test_coder_emits_raw_blocked_verbatim():
    """On a MISS the coder emits the RAW, verbatim BLOCKED status and stops.

    Fails if: the exact status string drifts - the dispatch loop's decision table keys on this
    verbatim phrasing to classify the failure.
    """
    text = CODER.read_text(encoding="utf-8")
    assert RAW_BLOCKED in text, (
        f"odoo-coder.md must emit the verbatim raw status {RAW_BLOCKED!r} on an unresolved dep."
    )


def test_coder_does_not_classify_and_is_ledger_unaware():
    """The coder must NOT classify in-progress vs absent and must be ledger-unaware.

    Fails if: the coder is given the classification job or the ledger - that would break the
    separation of concerns (the coder cannot see the batch or the ledger) and let it guess.
    """
    text = CODER.read_text(encoding="utf-8")
    low = text.lower()
    assert "ledger-unaware" in low or "ledger unaware" in low, (
        "odoo-coder.md must state the coder is LEDGER-UNAWARE (never reads/writes the ledger)."
    )
    assert "do not classify" in low or "does not classify" in low or "not classify" in low, (
        "odoo-coder.md must state the coder does NOT classify in-progress vs absent."
    )


def test_coding_dispatch_loop_owns_the_decision_table_and_the_ledger():
    """The odoo-coding dispatch loop (not the coder) owns the classification + is the ledger writer.

    Fails if: odoo-coding stops pointing at the ledger snippet for the decision table, or stops
    claiming ownership of the ledger writes - the classification would then have no home.
    """
    text = CODING.read_text(encoding="utf-8")
    low = text.lower()
    assert "snippets/module-coordination-ledger.md" in text, (
        "odoo-coding/SKILL.md must reference the module-coordination-ledger snippet (not restate it)."
    )
    assert "decision table" in low, (
        "odoo-coding/SKILL.md must run the decision table on the coder's BLOCKED status."
    )
    assert "manifest dependency" in low and "unresolved" in low, (
        "odoo-coding/SKILL.md must classify the coder's `manifest dependency ... unresolved` BLOCKED."
    )
    # The ledger snippet itself must name odoo-coding as the sole writer and the coder as unaware.
    ledger = LEDGER.read_text(encoding="utf-8").lower()
    assert "only" in ledger and "odoo-coding" in ledger and "write" in ledger, (
        "The ledger snippet must state ONLY odoo-coding writes it."
    )
