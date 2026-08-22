"""Behavioral guard for scripts/lib/lint_toolchain.sh and its wiring into the odoo-bin launch.

THE INCIDENT: runbot rejected a branch on a `prettier/prettier` violation in a file that had just
been verified clean locally. Three stacked layers, all measured:

  1. Odoo's `test_eslint` resolves its binary with `tools.misc.find_in_path('eslint')` - a bare
     PATH lookup. On a stock Debian/Ubuntu box PATH yields the OS package, eslint 6.4.0 (2019).
  2. That version cannot PARSE a modern `web/tooling/_eslintrc.json`: it exits 2 with
     `Environment key "es2022" is unknown` before reading a single JS file. The test is
     `@skipIf(eslint is None)`, so a present-but-ancient binary does NOT skip - it FAILS, and
     renders the parse error as though it were a finding about the code. A developer can lose a
     day reading it that way.
  3. A repo can pin a correct eslint in its own package.json and still be linted by the OS binary,
     because nothing put the repo-local `node_modules/.bin` ahead of `/usr/bin`.

Business rules protected, NOT the implementation:

  - **Repo-local tooling wins over whatever the OS ships.** The venv bin and every repo-local
    node_modules/.bin go IN FRONT of the inherited PATH, or the gate keeps linting with 2019.
  - **The toolchain env never outlives one launch.** It is applied inside the launch subshell,
    like PGPASSWORD - a PATH change that leaked would silently re-point every later subprocess.
  - **No CSV field is ever dropped.** The first cut of this helper used `printf '%s'`, so `read`
    discarded the final field of every comma-separated list: the last addons entry was never
    scanned and a single-module list resolved to nothing. Silent, and it made the whole helper
    look like it worked.
  - **An unresolvable repo stays unresolved.** REPO_TO_CHECK_QUALITY takes ONE basename; when two
    addons entries both own a named module, guessing would lint the wrong tree. Unset keeps the
    lint test's own honest skip.
  - **The operator's own value is never overridden.**
  - **The log states what was exported, never that the gate is configured.** Some lint variants
    read .odoorc only and ignore the environment entirely.
  - **The wiring is reached.** A helper nothing calls protects nothing - this file asserts the
    launch sites actually call it, and that the script which never runs tests does NOT.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
LIB = PLUGIN / "scripts" / "lib" / "lint_toolchain.sh"
OPS = PLUGIN / "scripts" / "setup-steps" / "55-instance-ops.sh"
SPINUP = PLUGIN / "scripts" / "setup-steps" / "50-instance-spinup.sh"


def _sh(script, env=None):
    """Run a bash snippet with the lib sourced; return stdout."""
    full = f'set -u\n. "{LIB}"\n{script}\n'
    proc = subprocess.run(
        ["bash", "-c", full], capture_output=True, text=True, timeout=60,
        env={**os.environ, **(env or {})},
    )
    assert proc.returncode == 0, f"snippet failed rc={proc.returncode}: {proc.stderr[:400]}"
    return proc.stdout


@pytest.fixture
def tree(tmp_path):
    """Two addons repos under a SHARED PARENT, mirroring a real dev box:
    repoA is a git root with installed node tooling, repoB is a git root that pins the tooling but
    never installed it, and the shared parent itself carries a stray package.json + node_modules
    that belongs to no repo (this is the real-world shape that broke the first implementation)."""
    root = tmp_path / "git"
    (root / "repoA" / "modx").mkdir(parents=True)
    (root / "repoA" / ".git").mkdir()
    (root / "repoA" / "modx" / "__manifest__.py").write_text("{}")
    nb = root / "repoA" / "node_modules" / ".bin"
    nb.mkdir(parents=True)
    esl = nb / "eslint"
    esl.write_text("#!/bin/sh\necho v9\n")
    esl.chmod(0o755)

    (root / "repoB" / "mody").mkdir(parents=True)
    (root / "repoB" / ".git").mkdir()
    (root / "repoB" / "mody" / "__manifest__.py").write_text("{}")
    (root / "repoB" / "package.json").write_text('{"devDependencies":{"eslint":"8.0.0"}}')

    # The stray shared-parent install: package.json + node_modules, but NO .git.
    stray = root / "node_modules" / ".bin"
    stray.mkdir(parents=True)
    (stray / "eslint").write_text("#!/bin/sh\necho stray\n")
    (stray / "eslint").chmod(0o755)
    (root / "package.json").write_text('{"devDependencies":{"eslint":"6.0.0"}}')

    vbin = tmp_path / "venv" / "bin"
    vbin.mkdir(parents=True)
    py = vbin / "python3"
    py.write_text("#!/bin/sh\n")
    py.chmod(0o755)

    return {
        "py": str(py), "vbin": str(vbin),
        "csv": f"{root/'repoA'},{root/'repoB'}",
        "a": str(root / "repoA"), "b": str(root / "repoB"), "stray": str(root),
    }


def test_a_stray_node_modules_in_the_shared_parent_is_never_injected(tree):
    """MEASURED REGRESSION. The first implementation copied _find_odoo_bin's entry-then-parent
    search, which is correct for odoo-bin but wrong for node_modules: on the real machine it
    matched `$HOME/git/node_modules`, a stray install in the shared parent of every checkout, and
    resolved EVERY addons entry to that one directory. An unrelated eslint would then have been
    put ahead of PATH for all of them - the exact failure mode this helper exists to prevent,
    reintroduced by the fix. `.git` is the discriminator: the shared parent has a package.json but
    no `.git`, a real addons repo has `.git`."""
    out = _sh(f'lint_toolchain_path_prefix "{tree["py"]}" "{tree["csv"]}"')
    assert f'{tree["stray"]}/node_modules/.bin' not in out, (
        "a node_modules in the shared parent directory was injected - the parent step must "
        "require a git root, or one stray install hijacks every repo on the machine"
    )
    assert f'{tree["a"]}/node_modules/.bin' in out, "the genuine repo-local install must survive"


def test_the_stray_parent_is_not_named_as_an_uninstalled_repo(tree):
    """Same discriminator on the diagnostic side: naming the shared parent would send someone to
    run the package install in a directory that is not a repo at all."""
    out = _sh(f'lint_toolchain_diagnostics "{tree["csv"]}"')
    # Boundary-anchored on purpose: the shared parent is a PREFIX of every repo
    # path under it, so a bare substring check would also match the legitimate
    # `...=<parent>/repoB (` line and pass for the wrong reason.
    assert f'LINT_TOOLCHAIN_UNINSTALLED={tree["stray"]} ' not in out
    assert f'LINT_TOOLCHAIN_UNINSTALLED={tree["b"]} ' in out, (
        "the genuine pinned-but-uninstalled repo must still be reported"
    )


def test_silence_is_never_the_answer_when_no_repo_local_eslint_exists(tmp_path):
    """The dangerous state is the quiet one: no repo-local eslint means whatever PATH offers does
    the linting. The log must say so, and name the binary that will actually run."""
    repo = tmp_path / "plain"
    (repo / "mod").mkdir(parents=True)
    (repo / ".git").mkdir()
    out = _sh(f'lint_toolchain_diagnostics "{repo}"')
    assert "LINT_TOOLCHAIN_FALLBACK=" in out


def test_one_repo_root_shared_by_several_addons_entries_reports_once(tree):
    """A core checkout contributes both `<root>/addons` and `<root>/odoo/addons`; repeating the
    same line per entry buries the signal."""
    csv = f'{tree["a"]},{tree["a"]},{tree["a"]}'
    out = _sh(f'lint_toolchain_diagnostics "{csv}"')
    assert out.count("LINT_TOOLCHAIN_ESLINT=") == 1


def test_the_config_remedy_points_at_the_per_instance_conf_not_the_shared_default(tree):
    """50-instance-spinup.sh generates a per-instance odoo.conf under the state root precisely so
    instances cannot collide ("never the user's default odoo.conf"). Advising ~/.odoorc would undo
    that isolation by leaking one run's lint target into every instance on the host."""
    out = _sh(f'lint_toolchain_export "{tree["py"]}" "{tree["csv"]}" "modx"')
    assert "odoo.conf" in out, "must name the per-instance conf as the remedy"
    assert "never in the shared" in out and "~/.odoorc" in out, (
        "must explicitly warn AGAINST the shared default config"
    )


# --------------------------------------------------------------------------- #
# PATH resolution
# --------------------------------------------------------------------------- #

def test_repo_local_tooling_is_put_ahead_of_the_os_binary(tree):
    """The whole point: the repo's own eslint must win the PATH lookup that find_in_path does."""
    out = _sh(f'lint_toolchain_path_prefix "{tree["py"]}" "{tree["csv"]}"')
    parts = out.split(":")
    assert parts[0] == tree["vbin"], "the venv bin must come first"
    assert f'{tree["a"]}/node_modules/.bin' in parts, "repo-local node bin must be on the prefix"


def test_the_last_csv_field_is_never_dropped(tree):
    """RED-BEFORE-GREEN regression guard for a real bug in this helper's first cut: `printf '%s'`
    left the final field without a newline and `while read` discarded it, so the LAST addons entry
    was never scanned. repoB is deliberately last and is the only one with the package.json pin."""
    out = _sh(f'lint_toolchain_diagnostics "{tree["csv"]}"')
    assert tree["b"] in out, (
        "the last CSV entry was not scanned - the split helper is dropping the final field again"
    )


def test_a_single_element_csv_still_resolves(tree):
    """The same dropped-field bug made a one-item list resolve to NOTHING, which is the shape a
    single-module dispatch always has."""
    out = _sh(f'lint_toolchain_repo_to_check "{tree["a"]}" "modx"')
    assert out.strip() == "repoA"


def test_absent_node_modules_contributes_nothing(tree):
    """A repo without installed tooling must not put a non-existent dir on PATH."""
    out = _sh(f'lint_toolchain_path_prefix "{tree["py"]}" "{tree["csv"]}"')
    assert f'{tree["b"]}/node_modules/.bin' not in out


# --------------------------------------------------------------------------- #
# repo resolution
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("modules,expected", [
    ("modx", "repoA"),
    ("mody", "repoB"),
    ("modx,mody", ""),   # two owning repos - genuine ambiguity
    ("nosuch", ""),
    ("", ""),
])
def test_repo_to_check_resolves_only_when_unambiguous(tree, modules, expected):
    out = _sh(f'lint_toolchain_repo_to_check "{tree["csv"]}" "{modules}"').strip()
    assert out == expected


def test_repo_to_check_returns_a_basename_not_a_path(tree):
    """The lint test matches with `adp.endswith(f"/{repo}")`. An absolute path matches nothing and
    the gate keeps skipping - so a path here would look configured and change nothing."""
    out = _sh(f'lint_toolchain_repo_to_check "{tree["csv"]}" "modx"').strip()
    assert out == "repoA" and "/" not in out


# --------------------------------------------------------------------------- #
# export semantics
# --------------------------------------------------------------------------- #

def test_export_does_not_leak_past_the_launch_subshell(tree):
    """Applied like PGPASSWORD: inside the launch subshell only. A leaked PATH would silently
    re-point every later subprocess in the run."""
    out = _sh(
        f'( lint_toolchain_export "{tree["py"]}" "{tree["csv"]}" "modx" >/dev/null\n'
        f'  echo "IN=$PATH" ) >/tmp/lt_in.$$\n'
        f'grep -q "{tree["vbin"]}" /tmp/lt_in.$$ && echo INSIDE_OK\n'
        f'case ":$PATH:" in *":{tree["vbin"]}:"*) echo LEAKED ;; *) echo OUTSIDE_CLEAN ;; esac\n'
        f'rm -f /tmp/lt_in.$$'
    )
    assert "INSIDE_OK" in out, "the prefix must be active inside the subshell"
    assert "OUTSIDE_CLEAN" in out and "LEAKED" not in out


def test_export_never_overrides_an_operator_set_value(tree):
    out = _sh(
        f'lint_toolchain_export "{tree["py"]}" "{tree["csv"]}" "modx" >/dev/null\n'
        f'echo "REPO=$REPO_TO_CHECK_QUALITY"',
        env={"REPO_TO_CHECK_QUALITY": "operator-choice"},
    )
    assert "REPO=operator-choice" in out


def test_the_log_line_states_what_was_exported_not_that_the_gate_works(tree):
    """Some lint variants read .odoorc only and ignore the environment entirely. Claiming the gate
    is configured would be the exact false-confidence this plugin keeps having to unlearn."""
    out = _sh(f'lint_toolchain_export "{tree["py"]}" "{tree["csv"]}" "modx"')
    assert "LINT_TOOLCHAIN_REPO=repoA" in out
    assert "odoo.conf" in out, "must name where a config-file-only variant reads it instead"


def test_an_uninstalled_pin_is_reported_rather_than_left_deceptive(tree):
    """repoB pins eslint but never installed it - the case where a repo LOOKS covered while the OS
    binary does the linting."""
    out = _sh(f'lint_toolchain_diagnostics "{tree["csv"]}"')
    assert "LINT_TOOLCHAIN_UNINSTALLED" in out and tree["b"] in out
    assert f'LINT_TOOLCHAIN_ESLINT={tree["a"]}/node_modules/.bin/eslint' in out


# --------------------------------------------------------------------------- #
# wiring - a helper nothing calls protects nothing
# --------------------------------------------------------------------------- #

def test_every_odoo_bin_launch_applies_the_toolchain():
    """The launch sites must actually call it, once per odoo-bin invocation that can run tests.
    The count is tied to the ulimit-scoped subshells, so a new verb added without the call goes
    red here instead of silently linting with the OS toolchain."""
    text = OPS.read_text(encoding="utf-8")
    assert "source \"$LIB_DIR/lint_toolchain.sh\"" in text, "55-instance-ops.sh must source the lib"
    launches = text.count('resource_limit_is_uncapped || ulimit -Sv')
    applies = text.count("lint_toolchain_export ")
    assert applies == launches, (
        f"{applies} toolchain applications for {launches} odoo-bin launch subshells - "
        "every launch that can run tests must apply it"
    )


def test_the_script_that_never_runs_tests_does_not_wire_it():
    """50-instance-spinup.sh passes no --test-enable, so no lint test ever runs on its path.
    Wiring it there would be a mechanism nothing reaches - this plugin's dominant defect class."""
    spin = SPINUP.read_text(encoding="utf-8")
    assert "--test-enable" not in spin, (
        "50-instance-spinup.sh now runs tests - the toolchain wiring decision must be revisited"
    )
    assert "lint_toolchain" not in spin


# --------------------------------------------------------------------------- #
# series resolution - the OTHER reason the lint gate never ran
# --------------------------------------------------------------------------- #

SERIES_SSOT = PLUGIN / "scripts" / "lib" / "odoo_series.py"
QUALITY_DOC = PLUGIN / "docs" / "reference" / "odoo-code-quality.md"


def test_series_ssot_infers_nothing_from_branch_topology():
    """MEASURED NEGATIVE RESULT, guarded so it is not "helpfully" undone.

    On a run-integration branch every detection step misses, and the three obvious rescues were
    measured on a real worktree and all fail: the upstream ref tracks the same run-integration
    branch; `--contains HEAD` matches no series branch; and ancestry matches SIX wrong series at
    once (series branches are forward-merged into each other) while missing the right one. An
    inference that is wrong six ways is worse than CANNOT-VERIFY, because it produces a confident
    lint run against the wrong series oracle. The SSOT resolves only from evidence that IS the
    series - keep it that way and make the caller pass ODOO_SERIES."""
    src = SERIES_SSOT.read_text(encoding="utf-8")
    # Strip comments: the file is allowed to EXPLAIN why these are rejected.
    code = "\n".join(
        line for line in src.splitlines() if not line.lstrip().startswith("#")
    )
    for banned in ("merge-base", "--contains", "@{u}", "rev-list --ancestry"):
        assert banned not in code, (
            f"odoo_series.py now infers a series from branch topology ({banned!r}) - "
            "measured to match six wrong series on a real forward-merged repo"
        )


def test_the_required_series_pin_is_documented_where_the_caller_reads_it():
    """The escape hatch existed all along and nobody used it, so the gate returned CANNOT-VERIFY
    on every pre-PR run - a gate that never runs. The invocation SSOT must say that this branch
    class REQUIRES the pin, not merely that a pin is possible."""
    doc = " ".join(QUALITY_DOC.read_text(encoding="utf-8").split())
    assert "ODOO_SERIES" in doc
    assert "run-integration" in doc, "must name the branch class where detection is designed to miss"
    assert "REQUIRED" in doc or "required" in doc, (
        "must state the pin is required for that class, not just available"
    )


def test_the_lib_is_source_only_and_executable_free():
    """Sourced helpers must have no top-level side effects: sourcing it must not alter PATH."""
    out = _sh('echo "SAME=$PATH"')
    assert out.startswith("SAME="), "sourcing the lib must not emit anything"
    before = os.environ["PATH"]
    assert out.strip() == f"SAME={before}", "sourcing the lib must not modify PATH"
