"""Guard the code-then-test contract: code is written first, then ONE odoo-test-writer per node
writes or adjusts the tests and proves each can fail with an executed break-check
(plugins/odoo-ai-agents/snippets/test-sensitivity-contract.md).

Three things would bring the retired doctrine back, and each has one check here:
  (a) a retired token in runtime prose - an agent reading it would wait for a test before coding;
  (b) a registry brief that makes a coder require a test, or a coordinator fence that launches the
      test-writer without the instance its break-check needs;
  (c) the SSOT losing the break-check principle (break the rule, watch the test fail, restore the
      code) or the broken-measurement classes.

Run: python -m pytest tests/test_test_sensitivity_contract.py -v
"""

import json
import re
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent / "plugins" / "odoo-ai-agents"
REGISTRY = PLUGIN / "generator" / "skill_tool_deps.json"
CONTRACT = PLUGIN / "snippets" / "test-sensitivity-contract.md"
CODER = PLUGIN / "agents" / "odoo-coder.md"
RUNTIME_DIRS = ("agents", "skills", "snippets", "workflows", "commands", "hooks")

RETIRED = re.compile(
    r"RED_TEST_PATH|RED_MODE|TEST_EXEMPTION"
    r"|red-evidence-contract|test-exemption-contract|test-first-contract"
    r"|\btest-first\b|\bred[- ]before[- ]green\b",
    re.IGNORECASE,
)


def _runtime_files():
    files = [REGISTRY]
    for name in RUNTIME_DIRS:
        files += [p for p in (PLUGIN / name).rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    return files


def _flat(path):
    return " ".join(path.read_text(encoding="utf-8").split())


def _brief(agent):
    return json.loads(REGISTRY.read_text(encoding="utf-8"))["agents"][agent]["brief"]


# (a) retired vocabulary ------------------------------------------------------------------------


def test_retired_pattern_catches_each_retired_spelling():
    for sample in ("RED_TEST_PATH", "red_mode", "TEST_EXEMPTION", "test-first-contract.md",
                   "a test-first teammate", "Red before\n  green", "red-evidence-contract.md",
                   "test-exemption-contract.md"):
        assert RETIRED.search(" ".join(sample.split())), sample
    assert not RETIRED.search("sort latest-first"), "must not match inside another word"


def test_no_runtime_file_carries_retired_vocabulary():
    hits = []
    for path in _runtime_files():
        try:
            text = _flat(path)
        except UnicodeDecodeError:
            continue
        hits += [f"{path.relative_to(PLUGIN)}: {m.group(0)}" for m in RETIRED.finditer(text)]
    assert not hits, f"retired test-first vocabulary in runtime files: {hits}"


# (b) registry briefs ---------------------------------------------------------------------------


def test_no_coder_brief_requires_a_test():
    for coder in ("odoo-backend-coder", "odoo-frontend-coder"):
        required = _brief(coder)["required"]
        assert not [k for k in required if "TEST" in k or k.startswith("RED")], (coder, required)


def test_test_writer_accepts_a_handle_but_does_not_require_one():
    """A caller with no instance (acceptance, code review) still gets tests written; the
    break-checks come back as PENDING BREAK_CHECK with NEEDS_NEXT: odoo-instance."""
    brief = _brief("odoo-test-writer")
    assert "INSTANCE_HANDLE" in brief["optional"]
    assert "INSTANCE_HANDLE" not in brief["required"]


def _test_writer_fence():
    text = CODER.read_text(encoding="utf-8")
    m = re.search(r"```\n# odoo-test-writer \(ONE per node.*?```", text, re.S)
    assert m, "odoo-coder.md has no odoo-test-writer fence"
    return m.group(0)


def test_coordinator_always_forwards_a_handle_to_the_test_writer():
    """odoo-coder is the caller whose test-writer must break-check before the node commits, so
    its fence always carries the handle - never 'omit when none'."""
    line = next(ln for ln in _test_writer_fence().splitlines() if ln.startswith("INSTANCE_HANDLE:"))
    assert "ALWAYS" in line and "omit" not in line.lower(), line


def test_coordinator_accepts_commit_ownership_from_its_caller():
    assert "COMMIT" in _brief("odoo-coder")["optional"]


# (c) the SSOT ----------------------------------------------------------------------------------


def test_contract_says_a_test_must_fail_when_its_rule_is_broken_and_the_code_be_restored():
    """The one principle the test leg exists for: a test guards a rule only if breaking that rule
    turns it red, and the writer never leaves the production code broken."""
    text = _flat(CONTRACT).lower()
    assert "fails when the business rule it guards is deliberately broken" in text
    assert "restore every file exactly as it was" in text
    assert "never leave production code broken" in text


def test_contract_names_broken_measurements_that_are_not_a_red():
    text = _flat(CONTRACT)
    assert "## Broken measurement is not a red" in text
    assert "KeyError" in text
    assert "0 tests selected" in text
