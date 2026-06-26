"""Behavior tests for scripts/verify-backend.sh - the pylint-odoo backend gate.

Protects the four behavior changes made for issue #117 (each is red without the
fix, green with it, per ETHOS #10):

  a. Whitelist isolation - when ENABLED_CODES is derived from a deployment quality
     module, the gate runs `--disable=all --enable=<whitelist>` so ONLY that
     whitelist runs (the rcfile's broad OCA defaults are NOT stacked on top).
  b. Comment-strip - codes the deployment intentionally commented out (e.g.
     `# 'C8105', ...`) are NOT re-enabled, and a `)` inside a comment cannot
     truncate the list.
  c. Version drift - unknown-option-value (W0012) is a WARN, never a BLOCK
     (it is OUR pylint-odoo version drift, not the developer's code), while a
     real finding alongside it still BLOCKs.
  d. B2 fail-closed - a quality module present but its whitelist underivable must
     NOT silently pass; the gate runs the full OCA config and emits a loud WARN
     ("could not derive ...") - never a clean GREEN with zero checks.

Hermetic: no real pylint/pylint-odoo. A fake tools venv (recording argv + emitting
canned findings) is injected via ODOO_AI_DIR; no PostgreSQL, no network, no Odoo.

Set VERIFY_BACKEND_SCRIPT=<path> to run these against a different script copy
(used to demonstrate red-before-green against the pre-fix original).
"""

import os
import subprocess
import textwrap
from pathlib import Path
from shutil import which

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = ROOT / "plugins" / "odoo-ai-agents"
SCRIPT = Path(
    os.environ.get(
        "VERIFY_BACKEND_SCRIPT",
        str(PLUGIN_ROOT / "scripts" / "verify-backend.sh"),
    )
)
SERIES = "18.0"

requires_bash = pytest.mark.skipif(which("bash") is None, reason="bash not available")


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

def _write_exec(path: Path, body: str) -> None:
    path.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8")
    path.chmod(0o755)


def _make_fake_toolchain(ai_dir: Path, argv_log: Path) -> None:
    """Create a fake isolated tools venv the gate will pick as PYLINT_BIN.

    bin/python  - answers the `import pylint_odoo` probe (exit 0).
    bin/pylint  - records every argv element (one per line) to argv_log, emits
                  $FAKE_PYLINT_OUT, and exits $FAKE_PYLINT_RC.
    """
    bindir = ai_dir / "tools" / f"pylint-{SERIES}" / "bin"
    bindir.mkdir(parents=True, exist_ok=True)
    _write_exec(bindir / "python", "exit 0\n")
    _write_exec(
        bindir / "pylint",
        textwrap.dedent(
            f"""\
            for a in "$@"; do printf '%s\\n' "$a" >> "{argv_log}"; done
            if [[ -n "${{FAKE_PYLINT_OUT:-}}" ]]; then printf '%s\\n' "$FAKE_PYLINT_OUT"; fi
            exit "${{FAKE_PYLINT_RC:-0}}"
            """
        ),
    )


def _make_quality_module(workdir: Path, enabled_codes_src: str) -> None:
    """Create a deployment quality module (test_pylint) holding ENABLED_CODES.

    No pylintrc inside it, so the gate must reach _derive_enabled_codes.
    """
    qm = workdir / "addons" / "test_pylint"
    qm.mkdir(parents=True, exist_ok=True)
    (qm / "constants.py").write_text(enabled_codes_src, encoding="utf-8")


def _target_py(workdir: Path) -> Path:
    """A trivial changed .py file to feed the gate (content is irrelevant - the
    fake pylint never reads it)."""
    f = workdir / "target.py"
    f.write_text("x = 1\n", encoding="utf-8")
    return f


def _run(workdir: Path, ai_dir: Path, argv_log: Path, *,
         fake_out: str = "", fake_rc: int = 0,
         timeout: int = 60) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    # Deterministic config resolution - strip anything that would short-circuit it.
    for k in ("ODOO_PYLINTRC", "ODOO_SERIES", "VERIFY_BACKEND_BASE",
              "VERIFY_BACKEND_GIT_DIR"):
        env.pop(k, None)
    env["CLAUDE_PLUGIN_ROOT"] = str(PLUGIN_ROOT)   # real matrix + fallback pylintrc
    env["ODOO_AI_DIR"] = str(ai_dir)               # where the fake tools venv lives
    env["ODOO_GIT_BASE"] = str(workdir / "_empty_git")  # never scan the real ~/git
    (workdir / "_empty_git").mkdir(exist_ok=True)
    env["ARGV_LOG"] = str(argv_log)
    env["FAKE_PYLINT_OUT"] = fake_out
    env["FAKE_PYLINT_RC"] = str(fake_rc)
    cmd = ["bash", str(SCRIPT), "--series", SERIES, str(_target_py(workdir))]
    return subprocess.run(
        cmd, cwd=str(workdir), capture_output=True, text=True, env=env, timeout=timeout
    )


# ---------------------------------------------------------------------------
# a + b: whitelist isolation + comment-strip
# ---------------------------------------------------------------------------

@requires_bash
def test_whitelist_isolated_and_commented_codes_excluded(tmp_path):
    """Derived whitelist must run as `--disable=all --enable=<active codes>` and
    a commented-out code (even with a ')' in its comment) must NOT be enabled.

    Red without fix (a): no --disable=all -> OCA defaults stack on top.
    Red without fix (b): the ')' in the comment truncates the list AND the
                         commented C8105 is re-enabled.
    """
    workdir = tmp_path / "work"
    ai_dir = tmp_path / "ai"
    argv_log = tmp_path / "argv.log"
    workdir.mkdir()
    _make_fake_toolchain(ai_dir, argv_log)
    _make_quality_module(
        workdir,
        textwrap.dedent(
            """\
            ENABLED_CODES = [
                'C8107',
                # 'C8105',  # license-allowed (C8105) - intentionally disabled
                'C8108',
            ]
            """
        ),
    )

    res = _run(workdir, ai_dir, argv_log, fake_rc=0)
    assert res.returncode == 0, f"stdout={res.stdout}\nstderr={res.stderr}"

    argv = argv_log.read_text(encoding="utf-8")
    argv_lines = argv.splitlines()

    # (a) the whitelist is isolated.
    assert "--disable=all" in argv_lines, (
        f"Expected --disable=all so only the whitelist runs.\nargv:\n{argv}"
    )

    # (b) the --enable line carries the active codes and NOT the commented one.
    enable_lines = [l for l in argv_lines if l.startswith("--enable=")]
    assert len(enable_lines) == 1, f"Expected one --enable= arg.\nargv:\n{argv}"
    enable = enable_lines[0]
    assert "C8107" in enable, f"active C8107 must be enabled: {enable}"
    assert "C8108" in enable, (
        f"active C8108 must survive the comment's ')' (no premature truncation): {enable}"
    )
    # The commented-out code must appear nowhere in the pylint invocation.
    assert "C8105" not in argv, (
        f"commented-out C8105 must NOT be re-enabled anywhere.\nargv:\n{argv}"
    )


# ---------------------------------------------------------------------------
# c: version drift (unknown-option-value) is WARN, not BLOCK
# ---------------------------------------------------------------------------

@requires_bash
def test_unknown_option_value_is_warn_not_block(tmp_path):
    """A lone W0012(unknown-option-value) must WARN and PASS, never BLOCK.

    Red without fix (c): W0012 is counted as a finding -> BLOCK -> exit 1.
    """
    workdir = tmp_path / "work"
    ai_dir = tmp_path / "ai"
    argv_log = tmp_path / "argv.log"
    workdir.mkdir()
    _make_fake_toolchain(ai_dir, argv_log)
    _make_quality_module(workdir, "ENABLED_CODES = ['C8107']\n")

    drift = ("target.py:1: [W0012(unknown-option-value)] Unknown option value "
             "for '--enable', expected a valid pylint message and got 'drift-code'")
    res = _run(workdir, ai_dir, argv_log, fake_out=drift, fake_rc=4)

    assert res.returncode == 0, (
        f"unknown-option-value must not BLOCK.\nstdout={res.stdout}\nstderr={res.stderr}"
    )
    assert "BLOCK issues : 0" in res.stdout, f"Expected 0 BLOCKs.\nstdout:\n{res.stdout}"
    assert "RESULT: PASS" in res.stdout, res.stdout
    # The drift line is surfaced as a WARN, not a BLOCK.
    warn_lines = [l for l in res.stdout.splitlines()
                  if "[WARN ]" in l and "unknown-option-value" in l]
    assert warn_lines, f"unknown-option-value must be shown as [WARN ].\nstdout:\n{res.stdout}"
    assert "[BLOCK] " not in res.stdout or "unknown-option-value" not in (
        "\n".join(l for l in res.stdout.splitlines() if "[BLOCK]" in l)
    ), f"unknown-option-value must NOT be a BLOCK.\nstdout:\n{res.stdout}"


@requires_bash
def test_real_finding_still_blocks_alongside_drift(tmp_path):
    """A real finding still BLOCKs even when a W0012 drift line is present - proves
    the W0012 filter is specific, not a blanket 'everything is now a warning'.

    Red without fix (c): both lines count as BLOCK (BLOCK=2, WARN=0).
    """
    workdir = tmp_path / "work"
    ai_dir = tmp_path / "ai"
    argv_log = tmp_path / "argv.log"
    workdir.mkdir()
    _make_fake_toolchain(ai_dir, argv_log)
    _make_quality_module(workdir, "ENABLED_CODES = ['C8107']\n")

    out = (
        "target.py:5: [C8107(manifest-required-author)] Missing required author key\n"
        "target.py:1: [W0012(unknown-option-value)] Unknown option value for "
        "'--enable', expected a valid pylint message and got 'drift-code'"
    )
    res = _run(workdir, ai_dir, argv_log, fake_out=out, fake_rc=16)

    assert res.returncode == 1, (
        f"a real finding must BLOCK (exit 1).\nstdout={res.stdout}\nstderr={res.stderr}"
    )
    assert "BLOCK issues : 1" in res.stdout, f"Expected exactly 1 BLOCK.\nstdout:\n{res.stdout}"
    assert "WARN  issues : 1" in res.stdout, f"Expected exactly 1 WARN.\nstdout:\n{res.stdout}"
    block_text = "\n".join(l for l in res.stdout.splitlines() if "[BLOCK]" in l)
    assert "manifest-required-author" in block_text, (
        f"the real finding must be the BLOCK.\nstdout:\n{res.stdout}"
    )
    assert "unknown-option-value" not in block_text, (
        f"the drift line must not be a BLOCK.\nstdout:\n{res.stdout}"
    )


# ---------------------------------------------------------------------------
# d (B2): empty-derive must fail-closed, never silently GREEN
# ---------------------------------------------------------------------------

@requires_bash
def test_empty_derive_fails_closed_not_silent_green(tmp_path):
    """A quality module present but with an underivable (all-commented) whitelist
    must NOT silently pass: no empty --disable=all, a loud 'could not derive' WARN,
    and the result is not a clean GREEN.

    Red without B2: empty derive falls back to OCA defaults silently -> a clean
    file reports 'PASS (clean)' with no derive-failure signal (false GREEN).
    """
    workdir = tmp_path / "work"
    ai_dir = tmp_path / "ai"
    argv_log = tmp_path / "argv.log"
    workdir.mkdir()
    _make_fake_toolchain(ai_dir, argv_log)
    _make_quality_module(
        workdir,
        textwrap.dedent(
            """\
            ENABLED_CODES = [
                # 'C8107',  # everything disabled - nothing derivable
                # 'C8108',
            ]
            """
        ),
    )

    # Fake pylint reports a perfectly clean run - so WITHOUT B2 this would be a
    # silent 'PASS (clean)'.
    res = _run(workdir, ai_dir, argv_log, fake_rc=0)

    assert "could not derive" in res.stdout, (
        f"empty-derive must surface a loud derive-failure WARN.\nstdout:\n{res.stdout}"
    )
    assert "RESULT: PASS (clean)" not in res.stdout, (
        f"empty-derive must NOT report a clean GREEN (false-GREEN guard).\nstdout:\n{res.stdout}"
    )
    # It must NOT have fabricated an empty whitelist (no --disable=all with no codes).
    argv = argv_log.read_text(encoding="utf-8") if argv_log.exists() else ""
    assert "--disable=all" not in argv.splitlines(), (
        f"must NOT prepend --disable=all when the whitelist is empty.\nargv:\n{argv}"
    )
    assert "WARN  issues : 0" not in res.stdout, (
        f"the derive-failure must count as a warning.\nstdout:\n{res.stdout}"
    )
