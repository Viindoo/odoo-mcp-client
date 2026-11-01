"""`--help` of every video script prints the whole header docstring, not only its first line."""
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

LIB = Path(__file__).resolve().parent.parent / "plugins" / "odoo-ai-agents" / "scripts" / "lib"

# one phrase that only the body of each docstring carries (never its first line)
BODY_PHRASE = {
    "video_publish.py": "one ABSOLUTE path per line",
    "video_record.py": "The library lives under",
    "storyboard_check.py": "Action objects carry",
    "video_budget.py": "names the JSONL ledger file",
    "video_keyscan.py": "is optional and repeatable",
    "narration_check.py": "Word error rate over NFC-normalised",
    "pronunciation.py": "Two layers, one rule",
}


@pytest.mark.parametrize("name", sorted(BODY_PHRASE))
def test_help_prints_the_whole_header_docstring(name):
    doc = ast.get_docstring(ast.parse((LIB / name).read_text(encoding="utf-8")))
    phrase = BODY_PHRASE[name]
    assert phrase in doc and phrase not in doc.splitlines()[0]
    proc = subprocess.run([sys.executable, str(LIB / name), "--help"], capture_output=True, text=True,
                          timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert phrase in proc.stdout
