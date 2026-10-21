"""Behavior guards for odoo-doc-site: one gate, no approval record, the demo company applied.

Business rules protected:

1. The page plan (page-plan.md, the Plan-Mode gate) is the ONE place the skill asks the user to
   approve something. Under the approved plan nothing asks again: the check shot is judged by the
   run itself and a step that cannot finish returns BLOCKED. Only an outward action (closing the bot
   pull request of a port) may still be a question.
2. The check shot leaves no "approval" record, and the gate that needed a login (the old UI-term
   check) is gone from the whole plugin.
3. `policy.demo_company` is applied by the run: the writer's capture contract sets the main
   company's name for each language from the POLICY file before it captures that language.

Run with: python3 -m pytest tests/test_docs_site_single_gate.py -q
"""

from __future__ import annotations

import re
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent / "plugins" / "odoo-ai-agents"
SKILL_DIR = PLUGIN / "skills" / "odoo-doc-site"
WRITER = PLUGIN / "agents" / "odoo-doc-site-writer.md"
MECHANICS = PLUGIN / "skills" / "_shared" / "doc-capture-mechanics.md"
PLAN_GATE_FILE = SKILL_DIR / "references" / "page-plan.md"

TEXT_SUFFIXES = (".md", ".yaml", ".yml", ".json", ".sh", ".py", ".txt")

# A question put to the user: a gate keyword set, a text question, "ask/stop and ask the user".
ASKS = re.compile(
    r"approve\s*/\s*(?:refine|skip)|text\s+question|(?:stop\s+and\s+)?ask\s+the\s+user|human\s+decision",
    re.IGNORECASE,
)
# The one allowed question outside the plan gate: an outward action (closing the bot's pull request).
OUTWARD = re.compile(r"close\s+the\s+bot\s+pull\s+request", re.IGNORECASE)


def flat(path):
    return re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))


def doc_site_prose():
    files = [p for p in sorted(SKILL_DIR.rglob("*")) if p.is_file() and p.suffix == ".md"]
    return files + [WRITER]


def test_only_the_page_plan_asks_the_user_to_approve():
    offenders = []
    for path in doc_site_prose():
        if path == PLAN_GATE_FILE:
            continue
        text = flat(path)
        for m in ASKS.finditer(text):
            window = text[max(0, m.start() - 120): m.end() + 120]
            if not OUTWARD.search(window):
                offenders.append("%s: ...%s..." % (path.relative_to(PLUGIN), window))
    assert not offenders, "a question under the approved plan (return BLOCKED with evidence instead):\n" + "\n".join(offenders)


def test_the_page_plan_is_still_the_one_plan_mode_gate():
    text = flat(PLAN_GATE_FILE)
    assert "ExitPlanMode" in text and "planning-gate-contract.md" in text


def test_no_approval_record_and_no_login_gate_remain():
    stale = []
    for path in sorted(PLUGIN.rglob("*")):
        if not path.is_file() or path.suffix not in TEXT_SUFFIXES or "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for token in ("approval.json", "ui_terms"):
            if token in text:
                stale.append("%s mentions %s" % (path.relative_to(PLUGIN), token))
    assert not stale, "\n".join(stale)
    assert not (PLUGIN / "scripts" / "lib" / "docs_site" / "ui_terms.py").exists()


def test_the_run_sets_the_demo_company_of_each_language_from_policy():
    text = flat(MECHANICS)
    section = text[text.index("## 15. Docs-site writer"):]
    company = re.search(r"\*\*Company\.\*\*(.*?)(?:- \*\*|$)", section)
    assert company, "section 15 has no Company rule"
    rule = company.group(1)
    assert "demo_company" in rule and "POLICY" in rule, rule
    assert "before the first shot of a language" in rule.lower(), rule
    # The site row points at that rule instead of describing the behaviour a second time.
    assert "doc-capture-mechanics.md" in flat(SKILL_DIR / "references" / "site-row.md")
