"""Regression guard: check_deps.py invariant 4 (every OSM tool NAMED in a skill's
hand-written SKILL.md prose must appear in that skill's own declared `mcp_tools`) is
FATAL BY DEFAULT - not warn-first.

Business contract being protected:
- Invariant 4 used to warn-first (exit 0, print WARN:) unless `--strict` / `DEPS_STRICT=1`
  was passed, specifically because 9 pre-existing violations (odoo-discovery-summary,
  odoo-git-rebase, odoo-intake, odoo-visual-regression, odoo-qa-suite, odoo-test-writing,
  odoo-forward-port, odoo-doc-illustration, odoo-acceptance) had to be closed first. All 9
  are now closed (declared genuinely, or ruled a documented negation exception), so a gate
  that still only warns is decorative - the DEFAULT invocation (no flag, no env var) must
  now fail (exit 1) when a skill's prose names an undeclared tool.
- The negation-cue exception (a tool named ONLY inside a "do not call X" / "never call X"
  sentence must NOT be treated as an undeclared-tool gap) must still hold under the new
  fatal-by-default behavior - declaring a forbidden tool would be worse than not declaring
  it, so the default run must stay GREEN for that shape of prose.

Runs the REAL check_deps.py (copied byte-for-byte into an isolated tmp fixture tree so its
ROOT-relative server-surface.json / skill_tool_deps.json / skills/ resolve to fixtures we
control, not the live repo) as a subprocess - this exercises the actual CLI entry point and
its real default-vs-flag behavior, not a reimplementation of its logic.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
REAL_CHECK_DEPS = (
    REPO_ROOT / "plugins" / "odoo-ai-agents" / "generator" / "check_deps.py"
)

_FAKE_SURFACE = {
    "server_version": "1.0.0",
    "tools": [
        {"name": "model_inspect", "version_added": "0.1.0"},
        {"name": "check_module_exists", "version_added": "0.1.0"},
    ],
}


def _build_fixture_tree(tmp_path: Path, *, skill_md_prose: str, declared_mcp_tools: list) -> Path:
    """Build an isolated {generator/, skills/<fake-skill>/SKILL.md} tree mirroring the
    real layout check_deps.py expects relative to its own file location, with the REAL
    check_deps.py copied in verbatim (never re-typed - SSOT stays the shipped file)."""
    generator_dir = tmp_path / "generator"
    generator_dir.mkdir()
    shutil.copy(REAL_CHECK_DEPS, generator_dir / "check_deps.py")
    (generator_dir / "server-surface.json").write_text(
        json.dumps(_FAKE_SURFACE), encoding="utf-8"
    )
    (generator_dir / "skill_tool_deps.json").write_text(
        json.dumps(
            {
                "schema_version": "1",
                "server_version_required": "1.0.0",
                "skills": {
                    "fake-skill": {
                        "mcp_tools": declared_mcp_tools,
                        "min_server_version": "1.0.0",
                        "deprecated_tools_used": [],
                        "notes": "fixture",
                    }
                },
                "agents": {},
            }
        ),
        encoding="utf-8",
    )
    skill_dir = tmp_path / "skills" / "fake-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(skill_md_prose, encoding="utf-8")
    return generator_dir / "check_deps.py"


def _run(check_deps_copy: Path, *extra_args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(check_deps_copy), *extra_args],
        capture_output=True,
        text=True,
    )


class TestInvariant4IsFatalByDefault:
    """A skill whose hand-written prose names a live tool absent from its own
    declared mcp_tools must fail the DEFAULT (no --strict, no DEPS_STRICT) run."""

    def test_undeclared_tool_named_in_prose_fails_default_run(self, tmp_path):
        check_deps_copy = _build_fixture_tree(
            tmp_path,
            skill_md_prose="# fake-skill\n\nCall `model_inspect` to inspect the model.\n",
            declared_mcp_tools=[],
        )
        result = _run(check_deps_copy)
        assert result.returncode != 0, (
            "default run must be FATAL for an undeclared-but-named tool, not warn-and-exit-0:\n"
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )
        assert "model_inspect" in result.stderr
        assert "ERROR" in result.stderr

    def test_undeclared_tool_named_in_prose_fails_with_strict_flag_too(self, tmp_path):
        """--strict is now a documented no-op (back-compat) - it must not become the ONLY
        way to get the fatal behavior."""
        check_deps_copy = _build_fixture_tree(
            tmp_path,
            skill_md_prose="# fake-skill\n\nCall `model_inspect` to inspect the model.\n",
            declared_mcp_tools=[],
        )
        result = _run(check_deps_copy, "--strict")
        assert result.returncode != 0
        assert "model_inspect" in result.stderr

    def test_declared_tool_named_in_prose_passes_default_run(self, tmp_path):
        """Sanity control: once declared, the same prose is clean (proves the failure
        above is about the undeclared gap, not the fixture shape)."""
        check_deps_copy = _build_fixture_tree(
            tmp_path,
            skill_md_prose="# fake-skill\n\nCall `model_inspect` to inspect the model.\n",
            declared_mcp_tools=["model_inspect"],
        )
        result = _run(check_deps_copy)
        assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
        assert "OK" in result.stdout


class TestNegationCueExceptionSurvivesFatalDefault:
    """A tool named ONLY inside a 'do not call' / 'never call' sentence must NOT be
    treated as an undeclared-tool gap, even now that invariant 4 is fatal by default -
    declaring it would falsely assert the skill uses a tool its own prose forbids."""

    def test_do_not_call_sentence_does_not_fail_default_run(self, tmp_path):
        check_deps_copy = _build_fixture_tree(
            tmp_path,
            skill_md_prose=(
                "# fake-skill\n\n"
                "**Do NOT call** `model_inspect` - this skill is business-analysis only.\n"
            ),
            declared_mcp_tools=[],
        )
        result = _run(check_deps_copy)
        assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
        assert "OK" in result.stdout

    def test_never_call_sentence_does_not_fail_default_run(self, tmp_path):
        check_deps_copy = _build_fixture_tree(
            tmp_path,
            skill_md_prose="# fake-skill\n\nNever call `check_module_exists` here.\n",
            declared_mcp_tools=[],
        )
        result = _run(check_deps_copy)
        assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"

    def test_tool_named_positively_elsewhere_still_counts_despite_a_negated_mention(
        self, tmp_path
    ):
        """The negation exception is scoped per-sentence, not per-tool - a genuine call
        mentioned in a DIFFERENT sentence must still be caught as undeclared."""
        check_deps_copy = _build_fixture_tree(
            tmp_path,
            skill_md_prose=(
                "# fake-skill\n\n"
                "**Do NOT call** `model_inspect` speculatively. "
                "Later, call `model_inspect` to confirm the field exists.\n"
            ),
            declared_mcp_tools=[],
        )
        result = _run(check_deps_copy)
        assert result.returncode != 0, (
            "a genuine positive mention in a separate sentence must still fail even "
            "though the SAME tool also appears in a negated sentence"
        )
        assert "model_inspect" in result.stderr


class TestRealRepoPassesInvariant4ByDefault:
    """End-to-end: the actual shipped skill_tool_deps.json + SKILL.md files pass the
    real check_deps.py's DEFAULT (no --strict) invocation - the 9 pre-existing gaps this
    invariant warned about are closed."""

    def test_real_check_deps_default_run_exits_zero(self):
        result = subprocess.run(
            [sys.executable, str(REAL_CHECK_DEPS)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"real repo must pass invariant 4 by default:\n"
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )
        assert "ERROR" not in result.stderr
