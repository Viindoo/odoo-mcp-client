"""Behavioral tests for the SessionStart ETHOS @import self-inject hook.

`hooks/ensure-ethos-import.sh` idempotently manages a sentinel-bounded block
inside the user's CLAUDE.md containing a single absolute @import line to the
plugin's ODOO-AI-ETHOS.md. Contract under test (behavior, not implementation):

  - appends the BEGIN/END sentinel block with the correct @import line;
  - creates CLAUDE.md when the file is missing;
  - idempotent: a second run leaves the file byte-identical;
  - self-heals: a stale/old path inside the block is replaced with the current one;
  - self-heals: a lone BEGIN (no END) is sanitized to a single well-formed block;
  - self-heals: inverted sentinels (END before BEGIN) produce a single well-formed block;
  - honours the ODOO_AI_NO_ETHOS_IMPORT=1 opt-out (no write at all);
  - preserves all user content outside the block;
  - emits the bridge additionalContext only on the first add, not on subsequent runs;
  - degrades gracefully when jq is absent (block still written, bridge to stderr).

Uses temp-tree technique: each test that needs an active ODOO-AI-ETHOS.md copies
the hook into a temp plugin-root dir containing a dummy file, so tests are fully
independent of the other agent's file.

Drives a throwaway CLAUDE.md via CLAUDE_CONFIG_DIR so the real ~/.claude/CLAUDE.md
is never touched. Stdlib-only (needs bash, python3, coreutils, awk, grep).
"""
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
HOOK = PLUGIN / "hooks" / "ensure-ethos-import.sh"

# Sentinel strings mirrored from the hook (fixed strings, not regex).
_BEGIN = "<!-- BEGIN odoo-ai-agents ETHOS import (managed by ensure-ethos-import.sh - do not edit inside) -->"
_END = "<!-- END odoo-ai-agents ETHOS import -->"


def _make_temp_plugin(tmp_path: Path, ethos_content: str = "# ETHOS dummy\nBoil the Ocean\n") -> Path:
    """Create a temporary plugin-root tree with a dummy ODOO-AI-ETHOS.md and the hook.

    Returns the path to the temp hook (ensure-ethos-import.sh inside the temp tree).
    """
    temp_plugin = tmp_path / "plugin_root"
    temp_plugin.mkdir(parents=True, exist_ok=True)
    (temp_plugin / "hooks").mkdir(exist_ok=True)
    # Place a dummy ODOO-AI-ETHOS.md at the plugin root.
    (temp_plugin / "ODOO-AI-ETHOS.md").write_text(ethos_content, encoding="utf-8")
    # Copy the real hook into the temp plugin's hooks dir so BASH_SOURCE resolves correctly.
    temp_hook = temp_plugin / "hooks" / "ensure-ethos-import.sh"
    shutil.copy2(str(HOOK), str(temp_hook))
    return temp_hook


def _run(hook: Path, cfg_dir: Path, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["CLAUDE_CONFIG_DIR"] = str(cfg_dir)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        ["bash", str(hook)],
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _read_md(cfg_dir: Path) -> str:
    return (cfg_dir / "CLAUDE.md").read_text(encoding="utf-8")


def _lines(cfg_dir: Path) -> list[str]:
    return _read_md(cfg_dir).splitlines()


def _assert_exactly_one_block(text: str) -> None:
    """Assert exactly one well-formed BEGIN/import/END block is present."""
    assert text.count(_BEGIN) == 1, f"expected exactly 1 BEGIN, got {text.count(_BEGIN)}"
    assert text.count(_END) == 1, f"expected exactly 1 END, got {text.count(_END)}"
    lines = text.splitlines()
    begin_idx = next((i for i, l in enumerate(lines) if l == _BEGIN), None)
    end_idx = next((i for i, l in enumerate(lines) if l == _END), None)
    import_idx = next((i for i, l in enumerate(lines) if re.match(r"^@/.*/ODOO-AI-ETHOS\.md$", l)), None)
    assert begin_idx is not None, "BEGIN not found"
    assert end_idx is not None, "END not found"
    assert import_idx is not None, "import line not found"
    assert begin_idx < import_idx < end_idx, (
        f"block structure wrong: BEGIN={begin_idx} import={import_idx} END={end_idx}"
    )


# ---------------------------------------------------------------------------
# Basic presence
# ---------------------------------------------------------------------------


def test_hook_file_present():
    assert HOOK.is_file(), f"missing hook: {HOOK}"


def test_block_added_on_first_run(tmp_path):
    hook = _make_temp_plugin(tmp_path)
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    (cfg / "CLAUDE.md").write_text("", encoding="utf-8")

    r = _run(hook, cfg)
    assert r.returncode == 0, f"hook must exit 0; stderr={r.stderr}"
    text = _read_md(cfg)
    assert _BEGIN in text, "BEGIN sentinel missing"
    assert _END in text, "END sentinel missing"
    assert re.search(r"^@/.*/ODOO-AI-ETHOS\.md$", text, re.MULTILINE), \
        "import line not found or not absolute"
    # Exactly one block (A6 strengthening).
    assert text.count(_BEGIN) == 1, "expected exactly one BEGIN block on first run"


def test_creates_claude_md_when_missing(tmp_path):
    hook = _make_temp_plugin(tmp_path)
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    # No CLAUDE.md at all.
    assert not (cfg / "CLAUDE.md").exists()

    r = _run(hook, cfg)
    assert r.returncode == 0, f"hook must exit 0; stderr={r.stderr}"
    assert (cfg / "CLAUDE.md").exists(), "CLAUDE.md not created"
    assert _BEGIN in _read_md(cfg)


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_idempotent_second_run_leaves_file_unchanged(tmp_path):
    hook = _make_temp_plugin(tmp_path)
    cfg = tmp_path / "cfg"
    cfg.mkdir()

    _run(hook, cfg)
    first_content = _read_md(cfg)

    r2 = _run(hook, cfg)
    assert r2.returncode == 0, f"second run must exit 0; stderr={r2.stderr}"
    assert _read_md(cfg) == first_content, "second run mutated the file (not idempotent)"


# ---------------------------------------------------------------------------
# Self-heal: stale path
# ---------------------------------------------------------------------------


def test_self_heal_stale_path(tmp_path):
    hook = _make_temp_plugin(tmp_path)
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    # Pre-seed with a block pointing to a wrong path.
    old_path = "/old/path/somewhere/ODOO-AI-ETHOS.md"
    seed = f"{_BEGIN}\n@{old_path}\n{_END}\n"
    (cfg / "CLAUDE.md").write_text(seed, encoding="utf-8")

    r = _run(hook, cfg)
    assert r.returncode == 0, f"hook must exit 0; stderr={r.stderr}"
    text = _read_md(cfg)

    # Exactly one well-formed block with the correct path.
    _assert_exactly_one_block(text)
    assert f"@{old_path}" not in text, "stale import line still present"
    assert re.search(r"^@/.*/ODOO-AI-ETHOS\.md$", text, re.MULTILINE), \
        "correct import line not found after self-heal"
    # No bridge on stale-path heal (A6 strengthening).
    assert r.stdout == "", f"stdout not empty on stale-heal run (spurious bridge?): {r.stdout!r}"

    # Idempotent: second run is byte-identical.
    after_first = _read_md(cfg)
    r2 = _run(hook, cfg)
    assert r2.returncode == 0
    assert _read_md(cfg) == after_first, "second run after stale-heal is not byte-identical"


# ---------------------------------------------------------------------------
# Self-heal: corruption cases (B1 / A5)
# ---------------------------------------------------------------------------


def test_self_heal_begin_only_no_end(tmp_path):
    """B1(a): BEGIN present but END absent -> lone BEGIN must be sanitized.

    This case triggers the MALFORMED path. User content outside the orphan
    sentinel must survive. After repair: exactly one well-formed block.
    Second run is byte-identical (idempotency after repair).
    """
    hook = _make_temp_plugin(tmp_path)
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    user_content = "# My personal config\n"
    # Lone BEGIN with some user content after it (simulates a partial write).
    seed = f"{user_content}{_BEGIN}\n# user wrote this thinking it was safe\n"
    (cfg / "CLAUDE.md").write_text(seed, encoding="utf-8")

    r = _run(hook, cfg)
    assert r.returncode == 0, f"hook must exit 0; stderr={r.stderr}"
    text = _read_md(cfg)

    # Exactly one well-formed block.
    _assert_exactly_one_block(text)
    # User content (the line before the orphan BEGIN) must survive.
    assert "# My personal config" in text, "user content lost after BEGIN-only sanitize"

    # Idempotent: second run is byte-identical.
    after_first = _read_md(cfg)
    r2 = _run(hook, cfg)
    assert r2.returncode == 0
    assert _read_md(cfg) == after_first, "second run after BEGIN-only repair is not byte-identical"


def test_self_heal_inverted_sentinels(tmp_path):
    """B1(b): END appears before BEGIN -> sanitize to exactly one well-formed block.

    User content before the inverted block must survive. File must not grow
    unboundedly on repeated runs (idempotency after repair).
    """
    hook = _make_temp_plugin(tmp_path)
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    user_line = "# Pre-existing user content"
    # END before BEGIN (inverted state).
    seed = f"{user_line}\n{_END}\nsome content\n{_BEGIN}\n"
    (cfg / "CLAUDE.md").write_text(seed, encoding="utf-8")

    r = _run(hook, cfg)
    assert r.returncode == 0, f"hook must exit 0; stderr={r.stderr}"
    text = _read_md(cfg)

    # Exactly one well-formed block.
    _assert_exactly_one_block(text)
    # Pre-existing user content must survive.
    assert user_line in text, "user content lost after inverted-sentinel sanitize"

    # Idempotent: second run is byte-identical (no unbounded growth).
    after_first = _read_md(cfg)
    r2 = _run(hook, cfg)
    assert r2.returncode == 0
    assert _read_md(cfg) == after_first, "second run after inverted-sentinel repair is not byte-identical"


# ---------------------------------------------------------------------------
# Opt-out (A1: dedicated var ODOO_AI_NO_ETHOS_IMPORT)
# ---------------------------------------------------------------------------


def test_opt_out_missing_claude_md_stays_missing(tmp_path):
    hook = _make_temp_plugin(tmp_path)
    cfg = tmp_path / "cfg"
    cfg.mkdir()

    r = _run(hook, cfg, {"ODOO_AI_NO_ETHOS_IMPORT": "1"})
    assert r.returncode == 0, f"opt-out must exit 0; stderr={r.stderr}"
    assert not (cfg / "CLAUDE.md").exists(), "opt-out must not create CLAUDE.md"


def test_opt_out_existing_file_byte_unchanged(tmp_path):
    hook = _make_temp_plugin(tmp_path)
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    before = "# My personal config\n"
    (cfg / "CLAUDE.md").write_text(before, encoding="utf-8")

    r = _run(hook, cfg, {"ODOO_AI_NO_ETHOS_IMPORT": "1"})
    assert r.returncode == 0, f"opt-out must exit 0; stderr={r.stderr}"
    assert _read_md(cfg) == before, "opt-out must not modify existing CLAUDE.md"


def test_old_auto_perms_var_does_not_suppress_ethos(tmp_path):
    """A1: ODOO_AI_NO_AUTO_PERMS=1 must NOT suppress ETHOS import.

    Opting out of browser permissions must not silently lose ETHOS loading.
    """
    hook = _make_temp_plugin(tmp_path)
    cfg = tmp_path / "cfg"
    cfg.mkdir()

    # ODOO_AI_NO_AUTO_PERMS=1 but no ODOO_AI_NO_ETHOS_IMPORT -> should still write block.
    r = _run(hook, cfg, {"ODOO_AI_NO_AUTO_PERMS": "1"})
    assert r.returncode == 0, f"hook must exit 0; stderr={r.stderr}"
    assert (cfg / "CLAUDE.md").exists(), "CLAUDE.md not created despite no ETHOS opt-out"
    assert _BEGIN in _read_md(cfg), "ETHOS block not written despite no ETHOS opt-out"


# ---------------------------------------------------------------------------
# Content preservation
# ---------------------------------------------------------------------------


def test_preserves_pre_existing_user_content(tmp_path):
    hook = _make_temp_plugin(tmp_path)
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    user_line = "# My personal config"
    other_import = "@/some/other/import.md"
    (cfg / "CLAUDE.md").write_text(f"{user_line}\n{other_import}\n", encoding="utf-8")

    r = _run(hook, cfg)
    assert r.returncode == 0, f"hook must exit 0; stderr={r.stderr}"
    text = _read_md(cfg)
    assert user_line in text, "pre-existing user line was lost"
    assert other_import in text, "pre-existing @import was lost"


# ---------------------------------------------------------------------------
# Import line shape
# ---------------------------------------------------------------------------


def test_import_line_matches_absolute_path_regex(tmp_path):
    hook = _make_temp_plugin(tmp_path)
    cfg = tmp_path / "cfg"
    cfg.mkdir()

    _run(hook, cfg)
    text = _read_md(cfg)
    assert re.search(r"^@/.*/ODOO-AI-ETHOS\.md$", text, re.MULTILINE), \
        "import line does not match expected pattern ^@/.*/ODOO-AI-ETHOS\\.md$"


# ---------------------------------------------------------------------------
# Sentinel structure
# ---------------------------------------------------------------------------


def test_sentinel_bounded_block_structure(tmp_path):
    hook = _make_temp_plugin(tmp_path)
    cfg = tmp_path / "cfg"
    cfg.mkdir()

    _run(hook, cfg)
    _assert_exactly_one_block(_read_md(cfg))


# ---------------------------------------------------------------------------
# Bridge: additionalContext only on first add (A6 strengthened)
# ---------------------------------------------------------------------------


def test_bridge_emitted_only_on_first_add(tmp_path):
    hook = _make_temp_plugin(tmp_path, ethos_content="# ETHOS content\nBoil the Ocean\n")
    cfg = tmp_path / "cfg"
    cfg.mkdir()

    # First run: bridge should appear on stdout (jq path) OR stderr (fallback).
    r1 = _run(hook, cfg)
    assert r1.returncode == 0
    first_output = r1.stdout + r1.stderr
    assert "ETHOS" in first_output or "Boil the Ocean" in first_output, \
        "bridge not emitted on first add"

    # Second run: stdout must be empty (no re-bridge); "Boil the Ocean" not in stdout or stderr
    # (only the one-line status echo is on stderr, not the full ETHOS content).
    r2 = _run(hook, cfg)
    assert r2.returncode == 0
    assert r2.stdout == "", f"stdout not empty on second run (re-bridge?): {r2.stdout!r}"
    assert "Boil the Ocean" not in r2.stdout, "bridge content re-emitted on stdout on second run"
    assert "Boil the Ocean" not in r2.stderr, "bridge content re-emitted on stderr on second run"


# ---------------------------------------------------------------------------
# jq-absent fallback
# ---------------------------------------------------------------------------


def test_jq_absent_block_still_written(tmp_path):
    hook = _make_temp_plugin(tmp_path)
    cfg = tmp_path / "cfg"
    cfg.mkdir()

    # Build a PATH that excludes jq but keeps standard tools.
    safe_bins = []
    for candidate in ["/bin", "/usr/bin", "/usr/local/bin"]:
        if Path(candidate).is_dir():
            safe_bins.append(candidate)
    no_jq_path = ":".join(safe_bins)

    r = _run(hook, cfg, {"PATH": no_jq_path})
    assert r.returncode == 0, f"hook must exit 0 without jq; stderr={r.stderr}"
    text = _read_md(cfg)
    assert _BEGIN in text, "BEGIN sentinel missing when jq absent"
    assert _END in text, "END sentinel missing when jq absent"
    assert re.search(r"^@/.*/ODOO-AI-ETHOS\.md$", text, re.MULTILINE), \
        "import line missing when jq absent"
