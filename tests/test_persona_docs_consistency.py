"""Reference integrity: every tool a persona doc (docs/personas/*.md, *.vi.md) shows as a call
signature row is a tool the generated surface (generator/server-surface.json) still declares."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
SURFACE_FILE = PLUGIN / "generator" / "server-surface.json"
PERSONAS_DIR = PLUGIN / "docs" / "personas"

# A table row whose first cell opens with a tool call signature, e.g.
# "| `test_base_classes(odoo_version="<version>")` | ...".
_ROW_RE = re.compile(r"^\|\s*`([a-z_]+)\(")


def test_every_persona_tool_still_exists_in_the_surface():
    tools = {t["name"] for t in json.loads(SURFACE_FILE.read_text(encoding="utf-8"))["tools"]}
    persona_docs = sorted(PERSONAS_DIR.glob("*.md"))
    assert persona_docs, "no persona docs found"
    missing = sorted({
        f"{path.relative_to(ROOT)}:{lineno}: {m.group(1)}"
        for path in persona_docs
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        for m in [_ROW_RE.match(line)] if m and m.group(1) not in tools
    })
    assert not missing, "persona rows name tools absent from server-surface.json:\n" + "\n".join(missing)
