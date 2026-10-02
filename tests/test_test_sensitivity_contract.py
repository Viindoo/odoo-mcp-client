"""Guard the code-then-test contract: code is written first, then ONE odoo-test-writer per node
writes or adjusts the tests and proves each can fail with an executed break-check
(plugins/odoo-ai-agents/snippets/test-sensitivity-contract.md).

Three things would bring the retired doctrine back, and each has one check here:
  (a) a retired token in runtime prose - an agent reading it would wait for a test before coding;
  (b) a registry brief that makes a coder require a test, or lets the test-writer run without the
      instance its break-check needs;
  (c) the SSOT losing the break-check record, the broken-measurement classes, or the restore proof.

Run: python -m pytest tests/test_test_sensitivity_contract.py -v
"""

import json
import re
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent / "plugins" / "odoo-ai-agents"
REGISTRY = PLUGIN / "generator" / "skill_tool_deps.json"
CONTRACT = PLUGIN / "snippets" / "test-sensitivity-contract.md"
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


def test_test_writer_requires_the_instance_its_break_check_runs_on():
    assert "INSTANCE_HANDLE" in _brief("odoo-test-writer")["required"]


def test_coordinator_accepts_commit_ownership_from_its_caller():
    assert "COMMIT" in _brief("odoo-coder")["optional"]


# (c) the SSOT ----------------------------------------------------------------------------------


def test_contract_defines_the_break_check_record_line():
    assert CONTRACT.is_file()
    assert re.search(r"^`BREAK_CHECK: <test node id> \|.*\| restored <sha256 match>`$",
                     CONTRACT.read_text(encoding="utf-8"), re.MULTILINE)


def test_contract_names_broken_measurements_that_are_not_a_red():
    text = _flat(CONTRACT)
    assert "## Broken measurement is not a red" in text
    assert "KeyError" in text
    assert "0 tests selected" in text


def test_contract_requires_a_sha256_restore_proof():
    text = _flat(CONTRACT)
    assert "sha256sum" in text
    assert "every hash must match" in text
