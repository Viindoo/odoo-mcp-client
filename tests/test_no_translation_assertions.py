"""Behavioral gate: a test may never assert TRANSLATED or DISPLAY text.

Terminology, help text and `.po` msgstrs are improved continuously by people who never see the
test suite, so an assertion pinned to that wording fails on an IMPROVEMENT rather than on a defect.
Its only cheap remedy is editing the expected value, which is itself banned - so such a test is a
permanent obstacle that gates nothing.

These tests protect the orchestrator hint that stops a translation-test instruction being issued in
the first place: it fires on translation intent (in either language) and stays silent otherwise.

Run: python -m pytest tests/test_no_translation_assertions.py -v
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN = REPO_ROOT / "plugins" / "odoo-ai-agents"

INTENT_HOOK = PLUGIN / "hooks" / "detect-intent.sh"


# ---------------------------------------------------------------------------
# The orchestrator hint - issue #3's mechanism. The main agent never reads a
# snippet it has not been pointed at, so the doctrine has to reach it at prompt
# time or it does not reach it at all.
# ---------------------------------------------------------------------------

def _run_hook(prompt: str) -> str:
    """Return the hook's additionalContext for a prompt ('' when it emits nothing)."""
    out = subprocess.run(
        ["bash", str(INTENT_HOOK)],
        input=json.dumps({"prompt": prompt}),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert out.returncode == 0, f"hook must always exit 0; got {out.returncode}: {out.stderr}"
    if not out.stdout.strip():
        return ""
    return json.loads(out.stdout)["hookSpecificOutput"]["additionalContext"]


def test_hook_fires_on_vietnamese_translation_intent():
    """The user base prompts in Vietnamese; an English-only trigger reaches half the sessions."""
    ctx = _run_hook("dịch module Odoo sang tiếng Việt")
    assert "[i18n]" in ctx, "Vietnamese translation intent must fire the same hint"


def test_hook_stays_silent_on_non_translation_odoo_work():
    """A hint on every Odoo prompt is noise, and noise gets skimmed past.

    'document' and 'write' share the hook's content bucket with 'translate', so this is the
    false-positive most likely to creep back in."""
    for prompt in (
        "write documentation for this Odoo module",
        "add a computed field to sale.order in Odoo",
    ):
        assert "[i18n]" not in _run_hook(prompt), f"hint must not fire on: {prompt!r}"


def test_hook_stays_silent_on_non_odoo_translation():
    """This plugin has no business steering a plain translation request."""
    assert "[i18n]" not in _run_hook("translate this English contract into Spanish")
