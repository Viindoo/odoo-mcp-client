"""Structural guard (constraint C2, same class as `test_no_self_referential_tracker_citation.py`):
a shipped plugin file must not carry an internal-process label that points at nothing a future
reader can resolve.

Confirmed pre-fix defect (the G4 instance-allocator fix round, 2026-08): the fix-group session
label "G4" - invented purely to partition THIS round's own work ("fix group G4 - a live instance
must never be reaped") - was written into 21 sites across `scripts/lib/allocator.py`,
`docs/reference/INSTANCE-ALLOCATION.md`, `docs/reference/INSTANCE-LIFECYCLE.md`,
`agents/odoo-qa-tester.md`, `agents/odoo-instance-ops.md`, `snippets/resource-teardown-contract.md`,
`hooks/session-end-gc.sh`, and `hooks/enforce-teardown.sh`. There is no "G4" section, heading, or
definition anywhere in the repository - an agent (or a human contributor) reading any of those
files next month has nothing to resolve the token against. This is the same defect class as the
tracker-citation guard above it (an unresolvable outside-the-file pointer riding along with the
real rule) - not "no G-labels", but "no label that points at nothing the reader can actually
resolve".

## The structural property, not a filename allowlist

A `G<digits>` token in a scanned file is EXEMPT (resolvable) via exactly one of THREE structural
shapes - never by naming a specific file:

1. **Same-file definition.** The token has at least one DEFINITION-SHAPED occurrence anywhere in
   the SAME file:
   - a markdown ATX heading that OPENS with the token (`## G4 - Token absent`) - the file is
     defining its own section scheme. Real example:
     `plugins/git-toolkit/snippets/github-mcp-first.md` (`## G1` .. `## G4`).
   - a markdown table row whose FIRST pipe-delimited cell IS the token
     (`| G4 | menu / action mis-point | ... |`) - the file is defining a taxonomy entry. Real
     example: `plugins/odoo-ai-agents/docs/odoo-ui-knowledge.md` (`| G1 | ... |` .. `| G8 | ... |`,
     each also referenced bare elsewhere in the same file, e.g. "the G8 Legacy class below" - a
     bare reference is fine once the label is defined AT LEAST ONCE anywhere in the file).
   - a diagram-node declaration: the token immediately followed by `[`, `(`, or `{` with NO space,
     inside a ` ```mermaid ` fenced block (`F1["Specialist fires"]`) - the token names a flowchart
     node, not a process label. (No `G<digits>`-named mermaid node exists in this repo today; this
     rule is included so the guard's own reasoning generalizes to the shape the coordinator's
     report named, not just the literal instances found - see
     `plugins/odoo-ai-agents/README.md`'s `F1`/`F2` nodes for the real occurrence of this SHAPE,
     tested here with a synthetic `G`-labeled fixture since no real file needs it yet.)
2. **Verified cross-file pointer.** The token shares a LINE with a backtick-quoted relative file
   path (resolved against the referencing file's OWN plugin root, e.g. `docs/foo.md` from a file
   under `plugins/odoo-ai-agents/` resolves to `plugins/odoo-ai-agents/docs/foo.md`; a leading
   `${CLAUDE_PLUGIN_ROOT}/` is the same thing spelled out), AND that referenced file itself
   contains a same-file definition (shape 1) of the EXACT SAME token. Real example:
   `plugins/odoo-ai-agents/agents/odoo-ui-reviewer.md` bare-references "G1-G8" while naming
   `` `docs/odoo-ui-knowledge.md` `` on the same line/paragraph - and that file's own table DOES
   define G1-G8, so the pointer is real, not decorative. This is DELIBERATELY VERIFIED (the
   pointed-to file must actually define the token), not "any nearby backtick path counts" - an
   unsound version of this rule would let a violation dodge the guard by naming an unrelated
   file next to it.
3. A token defined via shape 1 or resolved via shape 2 ANYWHERE in a file exempts every OTHER
   bare reference to that same token elsewhere in the SAME file (an already-resolved label may be
   freely repeated in prose without re-justifying itself on every line).

A token with NONE of the above anywhere in its own file is a violation, regardless of how many
times it is referenced.

## Scope: why `.md` / `.py` / `.sh` under `plugins/*/`, and NOT `.yaml`/`.json`

Every actual G4 violation this round landed in agent/skill/doc prose (`.md`), a code
docstring/comment (`.py`), or a hook/script comment (`.sh`) - the three content types a reader
(agent or human) consumes as narrative instruction or maintainer documentation. Scanning is
tree-wide across every plugin directory (`plugins/*/`), not a per-file allowlist.

`.yaml`/`.json` were deliberately evaluated and REJECTED for this guard, not silently omitted:
`plugins/odoo-ai-agents/workflows/qa-suite.workflow.yaml` carries a comment
`# Cross-workflow transition (G2): ...` with no in-file definition and no same-line file pointer
either - on the same raw regex this would be a second offender. But that file's own vocabulary
already uses `gate:` as a per-step YAML key (see `workflows/_schema.md`), so "G2" reads at least
as plausibly as shorthand for "gate 2 (of this workflow)" as it does a fix-group label - a
coincidental surface collision this guard cannot soundly resolve without semantic understanding of
the workflow schema, unlike the three concrete structural shapes above. Rather than build a rule
that either false-positives on legitimate workflow-step shorthand or silently allowlists that one
file by name, this guard does not scan `.yaml`/`.json` at all. This is a stated, known scope
limit, not a silent gap: a future `.yaml`/`.json` instance of this defect class needs a human
read, or a guard that actually understands workflow-YAML's own vocabulary well enough to tell the
two apart.

## Method

Direct-detector unit tests exercise the exemption logic against synthetic fixtures mirroring each
real legitimate shape (so the guard's own correctness is pinned independent of the live tree,
which can change). A separate whole-tree test runs the same detector against every
`.md`/`.py`/`.sh` file under every `plugins/*/` directory and asserts zero unresolved labels
anywhere.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGINS_DIR = ROOT / "plugins"
SCAN_EXTS = (".md", ".py", ".sh")

LABEL_RE = re.compile(r"\bG\d+\b")
_HEADING_DEF_RE = re.compile(r"^\s*#{1,6}\s+(G\d+)\b")
_TABLE_DEF_RE = re.compile(r"^\s*\|\s*(G\d+)\s*\|")
_MERMAID_FENCE_OPEN_RE = re.compile(r"^\s*```mermaid\s*$")
_FENCE_CLOSE_RE = re.compile(r"^\s*```")
_NODE_DEF_RE = re.compile(r"(G\d+)[\[({]")
_BACKTICK_PATH_RE = re.compile(r"`(\$\{CLAUDE_PLUGIN_ROOT\}/|\$CLAUDE_PLUGIN_ROOT/)?([\w./-]+\.(?:md|py|sh))`")


def _mermaid_spans(lines: list[str]) -> list[tuple[int, int]]:
    """[start, end) 0-indexed line ranges that are INSIDE a ```mermaid fence."""
    spans = []
    i, n = 0, len(lines)
    while i < n:
        if _MERMAID_FENCE_OPEN_RE.match(lines[i]):
            start = i + 1
            j = start
            while j < n and not _FENCE_CLOSE_RE.match(lines[j]):
                j += 1
            spans.append((start, j))
            i = j + 1
        else:
            i += 1
    return spans


def _collect_definitions(text: str, is_markdown: bool = True) -> set[str]:
    """Same-file definition set only (shape 1) - used both for the file under scan and,
    recursively, for a cross-file-pointer TARGET (shape 2), so a pointer only counts when the
    target genuinely defines the label itself.

    All three definition shapes (ATX heading, table row, mermaid-fenced node) are MARKDOWN
    syntax - `is_markdown=False` (a `.py`/`.sh` file) skips them entirely. This matters: a `#`
    is BOTH a markdown ATX-heading marker AND a Python/shell comment marker, so
    `# G4: some comment` in a `.py`/`.sh` file would otherwise satisfy `_HEADING_DEF_RE` and
    wrongly "define" the label for the whole file - exactly how the pre-fix reconstruction of
    `scripts/lib/allocator.py`'s own `# G4: TTL now governs...` comment line self-exempted
    that file's OTHER, genuinely bare `G4` occurrence during this guard's own RED proof. A
    `.py`/`.sh` file has no established same-file definition shape in this repo today; it can
    only resolve a label via shape 2 (a verified cross-file pointer)."""
    if not is_markdown:
        return set()
    lines = text.splitlines()
    mermaid_spans = _mermaid_spans(lines)
    defined: set[str] = set()
    for idx, line in enumerate(lines):
        hm = _HEADING_DEF_RE.match(line)
        if hm:
            defined.add(hm.group(1))
        tm = _TABLE_DEF_RE.match(line)
        if tm:
            defined.add(tm.group(1))
        if any(start <= idx < end for start, end in mermaid_spans):
            for nm in _NODE_DEF_RE.finditer(line):
                defined.add(nm.group(1))
    return defined


def _plugin_root_of(path: Path) -> Path | None:
    """The `plugins/<name>/` directory `path` lives under, however deep on disk that `plugins/`
    segment sits - NOT tied to this test module's own `PLUGINS_DIR` constant, so the same
    resolution logic works identically for the real tree and for a synthetic tmp_path fixture."""
    parts = path.parts
    for i, part in enumerate(parts):
        if part == "plugins" and i + 1 < len(parts):
            return Path(*parts[: i + 2])
    return None


def find_unresolvable_labels(text: str, path: Path | None = None) -> dict[str, list[int]]:
    """{label: [1-indexed line numbers of every occurrence]} for every `G<digits>` token in
    `text` resolvable by NEITHER shape 1 (same-file definition) NOR shape 2 (a verified same-line
    cross-file pointer - only checked when `path` is given, since resolution needs to know the
    file's own plugin root). `path` is optional so the synthetic unit tests below can exercise
    shape 1 without touching disk."""
    is_markdown = path is None or path.suffix == ".md"
    lines = text.splitlines()
    defined = _collect_definitions(text, is_markdown)
    all_refs: dict[str, list[int]] = {}

    plugin_root = _plugin_root_of(path) if path is not None else None

    cross_ref_candidates: dict[str, list[Path]] = {}
    for idx, line in enumerate(lines):
        lineno = idx + 1
        line_labels = [m.group(0) for m in LABEL_RE.finditer(line)]
        for lbl in line_labels:
            all_refs.setdefault(lbl, []).append(lineno)

        if line_labels and plugin_root is not None:
            for pm in _BACKTICK_PATH_RE.finditer(line):
                target = (plugin_root / pm.group(2)).resolve()
                if target.is_file():
                    for lbl in line_labels:
                        cross_ref_candidates.setdefault(lbl, []).append(target)

    for label, targets in cross_ref_candidates.items():
        if label in defined:
            continue
        for target in targets:
            try:
                target_text = target.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if label in _collect_definitions(target_text, target.suffix == ".md"):
                defined.add(label)
                break

    return {label: linenos for label, linenos in all_refs.items() if label not in defined}


# --------------------------------------------------------------------------- #
# Detector unit tests - pin the structural rule itself against synthetic
# fixtures mirroring each real shape, independent of the live tree's content.
# --------------------------------------------------------------------------- #
def test_detector_flags_a_bare_parenthetical_label_with_no_in_file_definition():
    """The exact shape this guard exists to catch - reproduces the reported defect."""
    text = (
        "A same-host owner pid that is verified alive is never TTL-reaped (G4) - by design, "
        "an un-reaped orphan only costs RAM.\n"
    )
    hits = find_unresolvable_labels(text)
    assert "G4" in hits, "a bare, undefined parenthetical label must be flagged"


def test_detector_exempts_a_markdown_heading_definition():
    """Mirrors plugins/git-toolkit/snippets/github-mcp-first.md's `## G1` .. `## G4` sections."""
    text = "## G4 - Token absent\n\nSome body text with no other G4 mention.\n"
    hits = find_unresolvable_labels(text)
    assert "G4" not in hits, "a file that defines its own G-numbered heading scheme is not a violation"


def test_detector_exempts_a_markdown_table_row_definition_and_its_bare_cross_references():
    """Mirrors docs/odoo-ui-knowledge.md's taxonomy table + later bare references to it."""
    text = (
        "| G1 | xpath-inherit broken | the view fails to load |\n"
        "| G4 | menu / action mis-point | opens an empty / wrong list |\n"
        "\n"
        "Rate a screen against the G4 class above; G1 also applies to menus.\n"
    )
    hits = find_unresolvable_labels(text)
    assert "G4" not in hits and "G1" not in hits, (
        "a table-defined taxonomy label may be freely referenced elsewhere in the SAME file"
    )


def test_detector_does_not_treat_a_python_or_shell_comment_as_a_heading_definition(tmp_path):
    """Regression pin for a bug this guard's own RED proof caught: `#` is BOTH a markdown
    ATX-heading marker and a Python/shell comment marker, so `# G4: ...` at the start of a `.py`
    or `.sh` file's comment line must NOT satisfy the heading-definition shape - that shape is
    markdown-only. Without this, a `.py`/`.sh` file could dodge every OTHER bare `G4` reference
    in itself just by writing one `# G4: ...` comment anywhere."""
    text = (
        "# G4: TTL now governs ONLY the residual case.\n"
        "DEFAULT_TTL_S = 7200\n"
        '"""G4 fix: liveness is AUTHORITATIVE, not merely a condemn signal."""\n'
    )
    py_path = tmp_path / "plugins" / "fake-plugin" / "scripts" / "lib" / "allocator.py"
    py_path.parent.mkdir(parents=True)
    py_path.write_text(text, encoding="utf-8")
    hits = find_unresolvable_labels(text, path=py_path)
    assert "G4" in hits, (
        "a '# G4: ...' comment in a .py/.sh file is not a heading definition - it must not "
        "self-exempt the file's other bare G4 references"
    )

    sh_path = tmp_path / "plugins" / "fake-plugin" / "hooks" / "foo.sh"
    sh_path.parent.mkdir(parents=True)
    sh_text = "# G4 note: some comment\nsome_command --flag\n"
    sh_path.write_text(sh_text, encoding="utf-8")
    hits_sh = find_unresolvable_labels(sh_text, path=sh_path)
    assert "G4" in hits_sh, "same bug, .sh flavor"


def test_detector_exempts_a_mermaid_node_declaration():
    """Mirrors the diagram-node shape (real occurrence uses F1/F2, not G-labels; this fixture
    uses a G-label so the exemption is actually exercised by this guard's own regex)."""
    text = (
        "```mermaid\n"
        'flowchart TD\n'
        '    A --> G4["Specialist fires"]\n'
        "    G4 --> B\n"
        "```\n"
    )
    hits = find_unresolvable_labels(text)
    assert "G4" not in hits, "a mermaid flowchart node id is not a process label"


def test_detector_does_not_exempt_a_g_shaped_token_outside_a_mermaid_fence():
    """The node-declaration exemption is fence-scoped: the SAME bracket-adjacency shape OUTSIDE
    a ```mermaid block must not be treated as a definition (it is not a diagram, and this guard
    must not be foolable by writing `G4[foo]` in plain prose)."""
    text = 'Some unrelated text where G4["looks like a node"] appears outside any fence.\n'
    hits = find_unresolvable_labels(text)
    assert "G4" in hits, "bracket-adjacency outside a mermaid fence is not a real definition"


def test_detector_treats_each_label_independently():
    """Defining G1 does not exempt G4 in the same file - each token is checked on its own."""
    text = "## G1 - defined here\n\nBut G4 is only ever mentioned bare, never defined.\n"
    hits = find_unresolvable_labels(text)
    assert "G1" not in hits
    assert "G4" in hits


def test_detector_exempts_a_verified_same_line_cross_file_pointer(tmp_path):
    """Mirrors agents/odoo-ui-reviewer.md bare-referencing G1-G8 while naming
    `docs/odoo-ui-knowledge.md` (which DOES define them) on the same line."""
    plugin = tmp_path / "plugins" / "fake-plugin"
    (plugin / "agents").mkdir(parents=True)
    (plugin / "docs").mkdir(parents=True)
    target = plugin / "docs" / "taxonomy.md"
    target.write_text("| G9 | some defect class | description |\n", encoding="utf-8")
    referencer = plugin / "agents" / "reviewer.md"
    referencer.write_text(
        "Classify the defect with the taxonomy (G9) in `docs/taxonomy.md`.\n", encoding="utf-8"
    )
    hits = find_unresolvable_labels(referencer.read_text(encoding="utf-8"), path=referencer)
    assert "G9" not in hits, "a same-line pointer to a file that ACTUALLY defines the label must resolve it"


def test_detector_does_not_exempt_an_unverified_cross_file_pointer(tmp_path):
    """The cross-file exemption is VERIFIED, not trusted blindly: a same-line backtick path to a
    file that does NOT itself define the label must not launder the violation."""
    plugin = tmp_path / "plugins" / "fake-plugin"
    (plugin / "agents").mkdir(parents=True)
    (plugin / "docs").mkdir(parents=True)
    target = plugin / "docs" / "unrelated.md"
    target.write_text("This file never defines G9 anywhere.\n", encoding="utf-8")
    referencer = plugin / "agents" / "reviewer.md"
    referencer.write_text(
        "Classify the defect with the taxonomy (G9) in `docs/unrelated.md`.\n", encoding="utf-8"
    )
    hits = find_unresolvable_labels(referencer.read_text(encoding="utf-8"), path=referencer)
    assert "G9" in hits, "a pointer to a file that does not define the label must still be flagged"


# --------------------------------------------------------------------------- #
# Whole-tree guard
# --------------------------------------------------------------------------- #
def _iter_scanned_files():
    for plugin_dir in sorted(p for p in PLUGINS_DIR.iterdir() if p.is_dir()):
        for ext in SCAN_EXTS:
            for path in sorted(plugin_dir.rglob(f"*{ext}")):
                if path.is_file():
                    yield path


def test_no_unresolvable_internal_process_label_in_shipped_plugin_files():
    offenders = []
    for path in _iter_scanned_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        hits = find_unresolvable_labels(text, path=path)
        if hits:
            rel = path.relative_to(ROOT)
            for label, linenos in sorted(hits.items()):
                offenders.append(f"{rel}:{linenos}: unresolvable label {label!r}")
    assert not offenders, (
        "shipped plugin file(s) reference an internal-process label ('G<digits>') with no "
        "in-file definition and no verified cross-file pointer resolving it - a session-scoped "
        "fix-group name that points at nothing a future reader can resolve:\n"
        + "\n".join(offenders)
    )
