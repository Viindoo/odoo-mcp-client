"""Behavioral guard: the JS lint oracle must be the one for the TARGET series.

`verify-frontend.sh` reproduces the Runbot gate by running eslint against an Odoo checkout's
`addons/web/tooling/_eslintrc.json`. That config is SERIES-SPECIFIC: 15.0 pins an es2019 parser
and its own rule set, 17.0 a later one. Picking "whichever checkout `find` happened to return
first" therefore lints 17.0 sources with a 15.0 oracle and reports failures that the real gate
would never raise - a FALSE FAIL on every machine that keeps more than one Odoo checkout, which
is every developer machine.

Tests protect the behaviour, not the implementation:

- the config comes from a checkout whose OWN `odoo/release.py` declares the target series
- when no checkout for that series exists, the gate is CANNOT-VERIFY - it never silently borrows
  a foreign series' config (and, per the script's tri-state contract, never a PASS either)

Run with: python3 -m pytest tests/test_verify_frontend_series.py -v
"""
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
SCRIPT = PLUGIN / "scripts" / "verify-frontend.sh"

# The script's tri-state exit contract: 0 PASS, 1 FAIL, 2 CANNOT-VERIFY.
EXIT_CANNOT_VERIFY = 2


def _make_odoo_checkout(base: Path, name: str, major: int, minor: int, *, tooling: bool = True):
    """A minimal Odoo checkout: odoo-bin (what the script scans for), odoo/release.py (the
    series SSOT the checkout declares about itself), and the web tooling eslint config."""
    d = base / name
    (d / "odoo").mkdir(parents=True)
    (d / "odoo-bin").write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    (d / "odoo-bin").chmod(0o755)
    (d / "odoo" / "release.py").write_text(
        "RELEASE_LEVELS = ['alpha', 'beta', 'candidate', 'final']\n"
        "FINAL = 'final'\n"
        f"version_info = ({major}, {minor}, 0, FINAL, 0, '')\n"
        f"version = '{major}.{minor}'\n",
        encoding="utf-8",
    )
    if tooling:
        t = d / "addons" / "web" / "tooling"
        t.mkdir(parents=True)
        (t / "_eslintrc.json").write_text(
            '{"parserOptions": {"ecmaVersion": %d}}\n' % (2019 if major < 17 else 2022),
            encoding="utf-8",
        )
    return d


def _make_target_repo(base: Path, series: str) -> Path:
    """An addon repo whose manifest declares the target series - the same way every Odoo addon
    declares which core it is written against."""
    repo = base / "addons_repo"
    mod = repo / "my_module"
    (mod / "static" / "src").mkdir(parents=True)
    (mod / "__manifest__.py").write_text(
        "{\n"
        "    'name': 'My Module',\n"
        f"    'version': '{series}.1.0.0',\n"
        "    'depends': ['web'],\n"
        "}\n",
        encoding="utf-8",
    )
    (mod / "__init__.py").write_text("", encoding="utf-8")
    (mod / "static" / "src" / "widget.js").write_text(
        "/** @odoo-module **/\nexport const answer = 42;\n", encoding="utf-8"
    )
    subprocess.run(["git", "init", "-q", "-b", series], cwd=repo, check=True)
    return repo


def _run(repo: Path, git_base: Path, js_file: Path, **env_extra):
    env = dict(os.environ)
    env.update(
        {
            "ODOO_GIT_BASE": str(git_base),
            "CLAUDE_PLUGIN_ROOT": str(PLUGIN),
            # Keep the run hermetic: no live instance, no inherited series override.
            "ODOO_INSTANCE_URL": "",
        }
    )
    env.pop("ODOO_SERIES", None)
    env.update(env_extra)
    return subprocess.run(
        ["bash", str(SCRIPT), str(js_file)],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


@pytest.fixture
def tree(tmp_path):
    git_base = tmp_path / "git"
    git_base.mkdir()
    repo = _make_target_repo(tmp_path, "17.0")
    js = repo / "my_module" / "static" / "src" / "widget.js"
    return git_base, repo, js


def test_eslint_oracle_comes_from_the_checkout_matching_the_target_series(tree):
    """Behaviour: with several Odoo checkouts present, the config MUST come from the one whose
    own release.py declares the target series.

    Fails if the resolver takes the first checkout `find` returns: a 17.0 addon would be linted
    with 15.0's es2019 oracle and report failures the real gate never raises.
    """
    git_base, repo, js = tree
    _make_odoo_checkout(git_base, "odoo_15.0", 15, 0)
    _make_odoo_checkout(git_base, "odoo_17.0", 17, 0)

    res = _run(repo, git_base, js)
    out = res.stdout + res.stderr

    assert "odoo_17.0" in out, (
        "the JS oracle must be resolved from the 17.0 checkout (the target series declared by "
        f"the addon's manifest). Output:\n{out}"
    )
    assert "odoo_15.0" not in out, (
        "a foreign-series checkout must never supply the eslint config - that is the false-FAIL "
        f"this guard exists to catch. Output:\n{out}"
    )


def test_no_checkout_for_the_target_series_is_cannot_verify_not_a_foreign_config(tree):
    """Behaviour: when NO checkout matches the target series, the gate reports CANNOT-VERIFY.

    Fails if the resolver borrows another series' `_eslintrc.json`: the run would produce a
    verdict for an oracle that is not the one Runbot runs, which is worse than no verdict.
    """
    git_base, repo, js = tree
    _make_odoo_checkout(git_base, "odoo_15.0", 15, 0)
    _make_odoo_checkout(git_base, "odoo_16.0", 16, 0)

    res = _run(repo, git_base, js)
    out = res.stdout + res.stderr

    assert "odoo_15.0" not in out and "odoo_16.0" not in out, (
        "with no 17.0 checkout available the gate must not fall back to a 15.0/16.0 eslint "
        f"config. Output:\n{out}"
    )
    assert "CANNOT-VERIFY" in out, (
        f"an unresolvable series oracle must surface as CANNOT-VERIFY. Output:\n{out}"
    )
    assert res.returncode == EXIT_CANNOT_VERIFY, (
        f"CANNOT-VERIFY must exit {EXIT_CANNOT_VERIFY}, got {res.returncode}. Output:\n{out}"
    )


def test_explicit_series_override_wins_over_the_manifest(tree):
    """Behaviour: `ODOO_SERIES` is the explicit escape hatch for a repo whose series cannot be
    read from a manifest (a tooling repo, a bare JS package).

    Fails if the override is ignored - a caller that knows the series would have no way to say so.
    """
    git_base, repo, js = tree
    _make_odoo_checkout(git_base, "odoo_16.0", 16, 0)
    _make_odoo_checkout(git_base, "odoo_17.0", 17, 0)

    res = _run(repo, git_base, js, ODOO_SERIES="16.0")
    out = res.stdout + res.stderr

    assert "odoo_16.0" in out, (
        f"an explicit ODOO_SERIES=16.0 must select the 16.0 checkout. Output:\n{out}"
    )
    assert "odoo_17.0" not in out, (
        f"the manifest must not override an explicit ODOO_SERIES. Output:\n{out}"
    )
