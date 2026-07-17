"""Contract tests for run/module-scoped doc-capture staging (issue #157).

Two modules (or two concurrent runs) must never clobber each other's capture
staging, and the doc default capture family must be the ONE eager browser MCP
(chrome-devtools). This file protects:

  - capture-mechanics.md documents chrome-devtools as the DEFAULT capture family;
  - the staging path is run+module scoped: `<run_id>/<module>_staging/...` under
    BOTH `<ISOLATE_DIR>/visual/` (chrome-devtools direct, Tier-2 ISOLATE per
    state-root-resolution.md) and `.playwright-mcp/` (playwright opt-in), and a
    bare `doc-staging/` with no `<run_id>/<module>` prefix is explicitly FORBIDDEN;
  - the odoo-doc-illustration skill threads `RUN_ID` into BOTH writer briefs and
    owns an end-of-run cleanup scoped to `<run_id>` only;
  - the two writer agents' staging examples use the `<run_id>/<module>_staging/`
    template (not a bare `doc-staging/`);
  - `doc-staging/` is gitignored (defense-in-depth).

Stdlib-only; reads the agent-facing Markdown as the contract surface.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
CAPTURE = PLUGIN / "skills" / "odoo-doc-illustration" / "references" / "capture-mechanics.md"
SKILL = PLUGIN / "skills" / "odoo-doc-illustration" / "SKILL.md"
USER_DOC = PLUGIN / "agents" / "odoo-user-doc-writer.md"
MKT_DOC = PLUGIN / "agents" / "odoo-marketing-writer.md"
GITIGNORE = ROOT / ".gitignore"


def _read(p: Path) -> str:
    assert p.is_file(), f"missing: {p}"
    return p.read_text(encoding="utf-8")


def test_chrome_devtools_is_the_documented_default_family():
    text = _read(CAPTURE)
    assert "chrome-devtools (default)" in text, "capture-mechanics must name chrome-devtools the default family"
    assert "playwright (OPT-IN)" in text or "playwright (opt-in)" in text.lower()
    assert "pagecast (OPT-IN)" in text or "pagecast (opt-in)" in text.lower()


def test_staging_path_is_run_and_module_scoped():
    text = _read(CAPTURE)
    # chrome-devtools default stages directly under <ISOLATE_DIR>/visual/<run_id>/<module>_staging/
    # (Tier-2 ISOLATE per state-root-resolution.md - resolved+captured, never a bare .odoo-ai/ literal)
    assert "<ISOLATE_DIR>/visual/<run_id>/<module>_staging/" in text, (
        "chrome-devtools default must stage under <ISOLATE_DIR>/visual/<run_id>/<module>_staging/"
    )
    # playwright opt-in namespaces .playwright-mcp/ by run + module
    assert ".playwright-mcp/<run_id>/<module>_staging/" in text, (
        "playwright opt-in must namespace .playwright-mcp/ by <run_id>/<module>_staging/"
    )


def test_bare_doc_staging_is_forbidden():
    # Whitespace-normalize so a soft line-wrap between words does not hide the phrase.
    text = " ".join(_read(CAPTURE).split())
    lowered = text.lower()
    assert "never stage into a bare `doc-staging/" in lowered, (
        "capture-mechanics must forbid a bare doc-staging/ path"
    )
    assert "with no `<run_id>/<module>` prefix" in lowered, (
        "the forbiddance must tie doc-staging to the missing run/module prefix"
    )


def test_skill_threads_run_id_into_both_writer_briefs():
    text = _read(SKILL)
    assert text.count("RUN_ID: <run-or-slug>") >= 2, (
        "both writer dispatch briefs must carry RUN_ID: <run-or-slug>"
    )
    assert "do NOT mint a new id" in text or "never mint a new id" in text


def test_skill_has_end_of_run_cleanup_scoped_to_run_id():
    text = _read(SKILL)
    assert "rm -rf <ISOLATE_DIR>/visual/<run_id>/ .playwright-mcp/<run_id>/" in text, (
        "skill must own an end-of-run rm -rf scoped to <run_id>"
    )
    # And it must forbid deleting another run's subtree.
    assert "never `rm` another run's subtree" in text or "never rm another run's subtree" in text


def test_writer_agents_use_run_module_staging_template():
    for agent in (USER_DOC, MKT_DOC):
        text = _read(agent)
        assert "<ISOLATE_DIR>/visual/<RUN_ID>/<module>_staging/" in text, (
            f"{agent.name} staging example must use the <RUN_ID>/<module>_staging/ template"
        )
        # doc-staging/ may appear ONLY inside the forbiddance, never as a positive
        # staging instruction.
        assert "NEVER a bare `doc-staging/`" in text, (
            f"{agent.name} must explicitly forbid a bare doc-staging/ staging dir"
        )
        assert "RUN_ID" in text, f"{agent.name} must consume RUN_ID"


def test_doc_staging_is_gitignored():
    assert "doc-staging/" in _read(GITIGNORE), "doc-staging/ must be gitignored (defense-in-depth)"
