"""Behavioural guard: a gate that did NOT run must be legible as such.

`verify-frontend.sh` runs several independent tiers. The expensive failure mode here is not a
tier going red - that is loud, and someone acts on it. It is a tier that skips ITSELF while its
siblings print their clean lines, so the run as a whole reads as "nothing to report".

That is not hypothetical. A module declaring the short manifest version `0.3.1` made the resolver
derive the series `0.3`, no checkout could declare it, and the JS eslint oracle never executed -
while Tier 2 printed `no issues` directly underneath and the verdict blamed an unresolved
"toolchain" that was in fact installed and fine. Every visible line was true; the run still read
as clean.

So the observable contract these tests protect:

- every run prints a per-tier ledger, and a tier that did not run says so in it;
- the CANNOT-VERIFY verdict NAMES the gates that did not run, rather than asserting one generic
  cause that may not be the real one;
- a tier's own clean line never phrases itself as the run's verdict;
- a tier claims a scan only when it actually scanned something.

Tests assert on the printed contract and the exit code - never on which internal branch ran - so
a correct refactor cannot break them, and each fails for the right reason.

Run with: python3 -m pytest tests/test_verify_frontend_gate_ledger.py -v
"""
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
SCRIPT = PLUGIN / "scripts" / "verify-frontend.sh"

EXIT_PASS = 0
EXIT_CANNOT_VERIFY = 2


def _make_repo(base: Path, branch: str = "18.0") -> Path:
    """An addon repo on a series-named branch, committed so `git rev-parse HEAD` resolves."""
    repo = base / "addons_repo"
    mod = repo / "my_module"
    (mod / "static" / "src").mkdir(parents=True)
    (mod / "__manifest__.py").write_text(
        "{'name': 'My Module', 'version': '1.0', 'depends': ['web']}\n", encoding="utf-8"
    )
    (mod / "__init__.py").write_text("", encoding="utf-8")
    (mod / "static" / "src" / "widget.js").write_text(
        "/** @odoo-module **/\nexport const answer = 42;\n", encoding="utf-8"
    )
    (mod / "models.py").write_text("ANSWER = 42\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", "-b", branch], cwd=repo, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
         "commit", "-q", "-m", "fixture"],
        cwd=repo, check=True,
    )
    return repo


def _run(repo: Path, git_base: Path, *targets: Path):
    env = dict(os.environ)
    env.update({
        "ODOO_GIT_BASE": str(git_base),
        "CLAUDE_PLUGIN_ROOT": str(PLUGIN),
        "ODOO_INSTANCE_URL": "",
    })
    env.pop("ODOO_SERIES", None)
    return subprocess.run(
        ["bash", str(SCRIPT), *[str(t) for t in targets]],
        cwd=repo, env=env, capture_output=True, text=True, timeout=120,
    )


@pytest.fixture
def tree(tmp_path):
    git_base = tmp_path / "git"
    git_base.mkdir()          # deliberately holds NO checkout for the target series
    repo = _make_repo(tmp_path)
    return git_base, repo


def test_an_unrun_js_gate_is_named_in_the_ledger(tree):
    """Behaviour: when the eslint oracle does not execute, the summary says so in the tier it
    belongs to.

    Fails if the ledger is missing or reports the JS gate as anything other than not-run - which
    is the state in which a reader would have to infer non-participation from silence.
    """
    git_base, repo = tree
    res = _run(repo, git_base, repo / "my_module" / "static" / "src" / "widget.js")
    out = res.stdout + res.stderr

    assert res.returncode == EXIT_CANNOT_VERIFY, f"expected CANNOT-VERIFY. Output:\n{out}"
    assert "Gate ledger" in out, f"every run must print the per-tier ledger. Output:\n{out}"
    ledger = [ln for ln in out.splitlines() if "Tier 1 JS" in ln]
    assert ledger and "DID NOT RUN" in ledger[0], (
        f"the unrun JS oracle must be reported as DID NOT RUN. Output:\n{out}"
    )


def test_the_verdict_names_which_gate_did_not_run(tree):
    """Behaviour: the CANNOT-VERIFY line names the gate that did not run.

    The verdict used to assert a single fixed cause ("JS lint toolchain unresolved") for every
    CANNOT-VERIFY. Here the toolchain is irrelevant - no checkout declares the series - so a
    fixed cause sends the reader to fix something that was never broken.

    Fails if the verdict cannot say which gate is missing.
    """
    git_base, repo = tree
    res = _run(repo, git_base, repo / "my_module" / "static" / "src" / "widget.js")
    out = res.stdout + res.stderr

    verdict = [ln for ln in out.splitlines() if "RESULT: CANNOT-VERIFY" in ln]
    assert verdict, f"expected a CANNOT-VERIFY verdict. Output:\n{out}"
    assert "did NOT run" in verdict[0] and "Tier 1 JS" in verdict[0], (
        f"the verdict must name the gate that did not run. Verdict: {verdict[0]!r}"
    )
    assert "DO NOT treat as pass" in verdict[0], (
        f"the verdict must keep its not-a-pass warning. Verdict: {verdict[0]!r}"
    )


def test_a_clean_tier_line_does_not_speak_for_the_whole_run(tree):
    """Behaviour: Tier 2's clean line is scoped to Tier 2.

    A bare `no issues` sitting under a gate that never ran is what made a skipped run read as a
    clean one. The line must carry its own scope so it cannot be quoted as the verdict.

    Fails if Tier 2 announces itself clean without saying what it covers.
    """
    git_base, repo = tree
    res = _run(repo, git_base, repo / "my_module" / "static" / "src" / "widget.js")
    out = res.stdout + res.stderr

    clean = [ln for ln in out.splitlines() if "Tier 2 static scan" in ln]
    assert clean, f"Tier 2 must report its own outcome. Output:\n{out}"
    assert "Tier 2 only" in clean[0], (
        f"Tier 2's clean line must scope itself to Tier 2. Line: {clean[0]!r}"
    )


def test_a_python_only_change_never_claims_a_static_scan(tree):
    """Behaviour: with no .js/.xml/.scss file in scope, Tier 2 reports not-applicable - it does
    not claim to have scanned.

    The file list was spliced as `("${OWL_FILES[@]:-}" "${SCSS_FILES[@]:-}")`, which contributes
    one EMPTY STRING per empty source array. The list was therefore never length 0, so a
    Python-only change took the scan branch, scanned nothing, and reported itself clean.

    Fails if Tier 2 claims a run over an empty file set.
    """
    git_base, repo = tree
    res = _run(repo, git_base, repo / "my_module" / "models.py")
    out = res.stdout + res.stderr

    ledger = [ln for ln in out.splitlines() if "Tier 2 static" in ln]
    assert ledger, f"the ledger must carry a Tier 2 row. Output:\n{out}"
    assert "RAN" not in ledger[0], (
        f"Tier 2 must not claim a scan with no scannable file in scope. Row: {ledger[0]!r}"
    )
    assert "Tier 2 static scan: no issues" not in out, (
        f"an empty scan must not be reported as a clean scan. Output:\n{out}"
    )


def test_the_ledger_is_printed_even_when_the_run_passes(tree):
    """Behaviour: the ledger is unconditional, not a failure-only diagnostic.

    A PASS whose ledger is hidden is the same false-green in a quieter costume: `ruff` absent is
    a WARN by contract, so a run can exit 0 with a gate that never executed.

    Fails if the ledger only appears on non-zero exits.
    """
    git_base, repo = tree
    # No JS/SCSS in scope and no eslint needed -> the run can reach a PASS.
    res = _run(repo, git_base, repo / "my_module" / "models.py")
    out = res.stdout + res.stderr

    assert "Gate ledger" in out, f"the ledger must print on every run. Output:\n{out}"
    if res.returncode == EXIT_PASS:
        assert "Tier 1 JS (eslint oracle) : n/a" in out, (
            f"a tier with nothing in scope must say so rather than stay silent. Output:\n{out}"
        )
