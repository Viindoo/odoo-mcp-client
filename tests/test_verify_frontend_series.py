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


def _make_target_repo(
    base: Path, series: str, *, branch: str | None = None, version: str | None = None
) -> Path:
    """An addon repo checked out on a series-named branch - which is how an addons-only repo
    declares which core it is written against.

    The manifest `version` deliberately does NOT carry that meaning. It is the ADDON's own
    version: this ecosystem ships short forms like `0.3.1` that name no series at all, and even
    a series-prefixed value survives a code-level upgrade unbumped, so it can name an earlier
    series than the checkout holding it. Callers override `version` to pin the exact shape a
    case is about, and `branch` to take the series-named branch away.

    The repo is COMMITTED, not just `git init`-ed: on an unborn HEAD `git rev-parse
    --abbrev-ref HEAD` fails outright, so an uncommitted fixture would test the no-branch path
    while looking like it tests the branch one.
    """
    repo = base / "addons_repo"
    mod = repo / "my_module"
    (mod / "static" / "src").mkdir(parents=True)
    (mod / "__manifest__.py").write_text(
        "{\n"
        "    'name': 'My Module',\n"
        f"    'version': '{version if version is not None else series + '.1.0.0'}',\n"
        "    'depends': ['web'],\n"
        "}\n",
        encoding="utf-8",
    )
    (mod / "__init__.py").write_text("", encoding="utf-8")
    (mod / "static" / "src" / "widget.js").write_text(
        "/** @odoo-module **/\nexport const answer = 42;\n", encoding="utf-8"
    )
    subprocess.run(
        ["git", "init", "-q", "-b", branch if branch is not None else series],
        cwd=repo,
        check=True,
    )
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(
        [
            "git",
            "-c", "user.name=verify-frontend test",
            "-c", "user.email=test@example.invalid",
            "commit", "-q", "-m", "fixture",
        ],
        cwd=repo,
        check=True,
    )
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


def test_explicit_series_override_wins_over_every_derived_answer(tree):
    """Behaviour: `ODOO_SERIES` is the explicit escape hatch, and it outranks every series the
    gate could derive on its own (here, a repo sitting on the `17.0` branch).

    Fails if the override is ignored - a caller that knows the series would have no way to say
    so, which is precisely the remedy the gate prints when it cannot derive one.
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
        f"nothing derived may override an explicit ODOO_SERIES. Output:\n{out}"
    )


def test_a_short_manifest_version_is_never_read_as_a_series(tmp_path):
    """Behaviour: a module declaring the SHORT version `0.3.1` is still linted against the series
    its checkout really is - and the string `0.3` never becomes a series.

    This is the regression that made the gate skip itself in silence. The old resolver took the
    first two dotted components of any three-part manifest `version`, so `0.3.1` produced the
    series `0.3` - a series no Odoo checkout can ever declare. No config resolved, the eslint
    oracle never ran once, and the run exited CANNOT-VERIFY while Tier 2 printed a clean scan
    underneath it, which reads as "nothing to report" to anyone skimming.

    Fails if any series is derived from the addon's own version number.
    """
    git_base = tmp_path / "git"
    git_base.mkdir()
    _make_odoo_checkout(git_base, "odoo_18.0", 18, 0)
    repo = _make_target_repo(tmp_path, "18.0", version="0.3.1")
    js = repo / "my_module" / "static" / "src" / "widget.js"

    res = _run(repo, git_base, js)
    out = res.stdout + res.stderr

    assert "0.3" not in out, (
        "the addon's own version `0.3.1` must never be read as a series - `0.3` is a series no "
        f"checkout can declare, so the gate resolves nothing and skips itself. Output:\n{out}"
    )
    assert "target Odoo series: 18.0" in out, (
        "the series must come from evidence that IS the series (here the 18.0 branch), not from "
        f"the manifest version. Output:\n{out}"
    )
    assert "odoo_18.0" in out, (
        f"the 18.0 checkout must supply the eslint config. Output:\n{out}"
    )


def test_a_series_prefixed_manifest_alone_does_not_resolve_a_series(tmp_path):
    """Behaviour: a manifest `version` of `17.0.1.0.0` is NOT accepted as the series when nothing
    else declares one - the gate reports CANNOT-VERIFY and names the remedy.

    A manifest version is the addon's own, and a code-level upgrade leaves it unbumped: a module
    carrying `17.0.1.0.0` inside an 18.0 checkout is byte-identical on disk to one that really is
    17.0. Linting on that basis would run 17.0's oracle over 18.0 sources and report failures the
    real gate never raises - the same false FAIL a foreign checkout produces.

    Fails if the manifest is promoted back into a resolved series.
    """
    git_base = tmp_path / "git"
    git_base.mkdir()
    _make_odoo_checkout(git_base, "odoo_17.0", 17, 0)
    repo = _make_target_repo(tmp_path, "17.0", branch="feature/no-series-here")
    js = repo / "my_module" / "static" / "src" / "widget.js"

    res = _run(repo, git_base, js)
    out = res.stdout + res.stderr

    assert res.returncode == EXIT_CANNOT_VERIFY, (
        "a series-prefixed manifest is weak evidence, not a resolution; with no branch or "
        f"release.py declaring one the gate must refuse. Output:\n{out}"
    )
    assert "odoo_17.0/addons/web/tooling" not in out, (
        f"the gate must not lint against a series the manifest merely hints at. Output:\n{out}"
    )
    assert "ODOO_SERIES" in out, (
        "the refusal must name its remedy - pinning ODOO_SERIES is the one action that unblocks "
        f"the caller. Output:\n{out}"
    )
