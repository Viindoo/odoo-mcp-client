"""Structural guard for constraint C2 (Phase 3 runtime review, item P11): plugin files carry
decidable runtime instructions only - no self-referential citation to THIS repo's own issue/PR
tracker. An agent that opens `scripts/setup-steps/55-instance-ops.sh` (or any other shipped
plugin file) has no access to this repo's tracker, so "see issue #171" / "(PR #42)" carries zero
decidable information for it - it is project-management residue riding along with the real rule,
not part of the rule itself.

Confirmed pre-fix defect (round 4.20.0 phase-3 runtime review, RT6 lane, P11): 3x "issue #171" in
`scripts/setup-steps/55-instance-ops.sh` (lines 296, 314, 443) plus 1x "PR #42" in
`docs/reference/INSTANCE-ALLOCATION.md` (owned by a different fix group). This test sweeps the
GENERAL class - any `issue #<N>` / `PR #<N>` / `pull request #<N>` citation - across BOTH
installed plugin trees (`odoo-ai-agents`, `git-toolkit`), not just the four reported sites.

Design notes (why each exemption is STRUCTURAL, never a per-file allowlist):

- `evals/` is a repo-wide directory convention (every skill's `evals/evals.json` holds quoted
  user-prompt fixtures for the trigger-accuracy harness) - never loaded by an execute-agent
  during real task work. Exempting the DIRECTORY exempts every present and future eval fixture,
  not one named file.
- `generator/` is documented at the repo root (`CLAUDE.md` "What this repo is": "the Python
  under `generator/` and `tests/` exists to *validate and generate* that Markdown, not to run at
  user time") as build/validation tooling, never agent-facing prose. A `#<N>` citation in a
  generator docstring or an SSOT JSON `notes` field (e.g. `generator/skill_tool_deps.json`'s
  "(PR #323, v0.15.0)" maintainer note) is dev bookkeeping, structurally never read by a running
  agent - same rationale as the `evals/` exemption, applied to the other whole-directory
  convention CLAUDE.md itself names.
- A citation inside an agent frontmatter `<example>...</example>` block is the standard Claude
  Code agent-description convention (illustrative worked scenarios), not an operating instruction
  the running agent's body carries.
- A citation that falls INSIDE a double-quoted span (tracked via whole-FILE quote parity, not
  per-line, since a wrapped YAML `description: |` paragraph can open its quote on an earlier
  physical line) is a generic trigger-phrase example - the same convention used throughout this
  plugin's routing/trigger lists (`"review PR #123"`, `"rebase PR #482"`), illustrating an intent
  pattern rather than citing a real tracked item.
- A citation immediately adjacent to an Odoo-version marker (`at v18`, `v0.15.0`, "Odoo core",
  "upstream") is a domain fact about ODOO'S OWN (or the OSM server's own) PR/issue history, not a
  self-reference to this repo's tracker - verified case: `snippets/fp-symbol-survival-check.md`'s
  "`account.account.company_id` -> `company_ids` at v18 (PR #14070)" cites Odoo core's own PR.

None of the above is a per-file or per-path allowlist: each is a structural marker (a directory
convention CLAUDE.md itself documents, a Claude Code frontmatter convention, or a textual/quoting
pattern) that would exempt ANY future site using the same convention, and still catches a future
site that does not.
"""
from __future__ import annotations

import bisect
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGINS_DIR = ROOT / "plugins"
PLUGIN_NAMES = ("odoo-ai-agents", "git-toolkit")

_GENERATED_BLOCK = re.compile(
    r"<!-- BEGIN GENERATED TOOLS -->.*?<!-- END GENERATED TOOLS -->", re.S
)
_TRACKER_RE = re.compile(r"\b(issue|pr|pull request)\s*#(\d+)", re.IGNORECASE)
_EXAMPLE_TAG_RE = re.compile(r"<example>.*?</example>", re.S)
# A citation adjacent to an explicit Odoo/OSM-server version marker is a domain fact about THAT
# project's own history, not a self-reference to this repo's tracker.
_VERSION_ADJACENT_RE = re.compile(
    r"(at\s+v\d|v\d+(\.\d+)+|odoo core|upstream|core odoo)", re.IGNORECASE
)
# Directory-wide conventions (apply to every present/future file under them, not one filename).
_EXEMPT_DIR_SEGMENTS = ("/evals/", "/generator/")

_SCAN_GLOBS = ("*.md", "*.sh", "*.py", "*.json", "*.yaml")


def _plugin_roots():
    for name in PLUGIN_NAMES:
        p = PLUGINS_DIR / name
        if p.is_dir():
            yield name, p


def _iter_scanned_files():
    for _name, plugin_dir in _plugin_roots():
        for pattern in _SCAN_GLOBS:
            for path in sorted(plugin_dir.rglob(pattern)):
                yield path


def _rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def _tracker_citation_hits() -> list[str]:
    hits = []
    for path in _iter_scanned_files():
        rel = _rel(path)
        rel_slashed = f"/{rel}/"
        if any(seg in rel_slashed for seg in _EXEMPT_DIR_SEGMENTS):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        # Generated MCP-tools blocks are SSOT-regenerated (make gen); blank them (preserving
        # newline count so line numbers stay correct) rather than scan hand-authored text there.
        text = _GENERATED_BLOCK.sub(lambda m: "\n" * m.group(0).count("\n"), text)

        example_spans = [(m.start(), m.end()) for m in _EXAMPLE_TAG_RE.finditer(text)]
        quote_positions = [m.start() for m in re.finditer(r'"', text)]

        def _inside_quotes(pos: int) -> bool:
            # Whole-FILE quote parity (not per-line): a wrapped `description: |` paragraph can
            # open its quote on an earlier physical line, so a per-line reset misses it.
            n = bisect.bisect_left(quote_positions, pos)
            return n % 2 == 1

        lines = text.splitlines(keepends=True)
        pos = 0
        for lineno, line in enumerate(lines, start=1):
            line_start = pos
            pos += len(line)
            for m in _TRACKER_RE.finditer(line):
                abs_pos = line_start + m.start()
                if any(s <= abs_pos < e for s, e in example_spans):
                    continue
                if _inside_quotes(abs_pos):
                    continue
                window = line[max(0, m.start() - 20) : m.end() + 10]
                if _VERSION_ADJACENT_RE.search(window):
                    continue
                hits.append(f"{rel}:{lineno}: {line.strip()}")
    return hits


def test_no_self_referential_tracker_citation():
    hits = _tracker_citation_hits()
    assert not hits, (
        "A self-referential citation to THIS repo's own issue/PR tracker was found inside a "
        "shipped plugin file (constraint C2: plugin files carry decidable runtime instructions "
        "only). An agent loading this file has no access to the tracker, so the citation carries "
        "no decidable information - state the substantive rule inline instead:\n"
        + "\n".join(hits)
    )
