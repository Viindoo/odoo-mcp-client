"""Reference integrity: every `${CLAUDE_PLUGIN_ROOT}/...` path an instruction file names resolves to
at least one real file or directory under the plugin that owns the file (a `<placeholder>` path
segment is wildcarded). Generated `<!-- BEGIN/END GENERATED TOOLS -->` regions are blanked first.
"""
from __future__ import annotations

import glob
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGINS_DIR = ROOT / "plugins"
PLUGIN_NAMES = ("odoo-ai-agents", "odoo-semantic-mcp", "git-toolkit")

_GENERATED_BLOCK = re.compile(
    r"<!-- BEGIN GENERATED TOOLS -->.*?<!-- END GENERATED TOOLS -->", re.S
)
_CLAUDE_PLUGIN_PATH_RE = re.compile(r"`\$\{CLAUDE_PLUGIN_ROOT\}/([^`]+)`")
_PLACEHOLDER_SEGMENT_RE = re.compile(r"<[^/>]+>")


def _general_path_hits() -> list[str]:
    hits = []
    for name in PLUGIN_NAMES:
        plugin_dir = PLUGINS_DIR / name
        if not plugin_dir.is_dir():
            continue
        for path in sorted(plugin_dir.rglob("*.md")):
            text = _GENERATED_BLOCK.sub("", path.read_text(encoding="utf-8", errors="replace"))
            for lineno, line in enumerate(text.splitlines(), start=1):
                for m in _CLAUDE_PLUGIN_PATH_RE.finditer(line):
                    raw = m.group(1)
                    # Strip a trailing prose continuation: a `§ Section` pointer or a `:<line>`
                    # locator, both valid after the real path ends.
                    cut = re.split(r"[\s§]", raw, maxsplit=1)[0]
                    cut = cut.rstrip(").,:;").split(":")[0] if cut.count(":") else cut.rstrip(").,:;")
                    globpath = _PLACEHOLDER_SEGMENT_RE.sub("*", cut)
                    if not glob.glob(str(plugin_dir / globpath)):
                        hits.append(f"{path.relative_to(ROOT)}:{lineno}: ${{CLAUDE_PLUGIN_ROOT}}/{cut}")
    return hits


def test_claude_plugin_root_paths_resolve():
    hits = _general_path_hits()
    assert not hits, (
        "A `${CLAUDE_PLUGIN_ROOT}/...` path reference does not resolve to any real file/dir "
        "under its owning plugin - a runtime agent following it gets nothing:\n" + "\n".join(hits)
    )
