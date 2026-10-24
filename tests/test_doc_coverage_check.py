"""`scripts/lib/doc_coverage_check.py` - a full guide accounts for every catalog row."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "lib" / "doc_coverage_check.py"


def _catalog(tmp_path, rows):
    p = tmp_path / "feature-catalog.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return p


def _run(path, *args):
    return subprocess.run([sys.executable, str(TOOL), str(path), *args], capture_output=True, text=True)


def test_an_unstamped_or_unexplained_row_is_a_gap_that_fails_a_full_guide(tmp_path):
    rows = [{"feature_id": "m-01", "name": "Agents", "coverage": "guide"},
            {"feature_id": "m-02", "name": "Setup", "coverage": "setup"},
            {"feature_id": "m-03", "name": "Internal view", "coverage": "excluded: a technical view no user opens"},
            {"feature_id": "m-04", "name": "Knowledge Sources"},
            {"feature_id": "m-05", "name": "Skills", "coverage": "excluded:"},
            {"feature_id": "m-06", "name": "Memory", "coverage": "in_guide"}]
    proc = _run(_catalog(tmp_path, rows))
    assert proc.returncode == 1
    assert "GAP=m-04 Knowledge Sources" in proc.stdout and "GAP=m-05" in proc.stdout and "GAP=m-06" in proc.stdout
    assert "GAP=m-01" not in proc.stdout and "COVERED=2 EXCLUDED=1 GAPS=3" in proc.stdout


def test_a_fully_stamped_catalog_passes_and_a_screenshot_doc_only_reports(tmp_path):
    rows = [{"feature_id": "m-01", "name": "Agents", "coverage": "guide"},
            {"feature_id": "m-02", "name": "Memory", "coverage": "excluded: documented by the base module's guide"}]
    assert _run(_catalog(tmp_path, rows)).returncode == 0
    gaps = [{"feature_id": "m-01", "name": "Agents"}]
    proc = _run(_catalog(tmp_path, gaps), "--scope", "screenshot-doc")
    assert proc.returncode == 0 and "GAP=m-01" in proc.stdout
