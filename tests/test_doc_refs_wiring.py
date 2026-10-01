"""Wiring guard for the module-doc reference rule and its deterministic gate.

Behaviour protected:

- `snippets/module-doc-references.md` is the ONE place that states the cross-module store-link
  form; every other prose file points at it, so the form cannot drift into two spellings.
- The gate command in that SSOT runs the real `scripts/lib/doc_refs_check.py` with flags the
  script actually accepts, under the plugin interpreter `python3`, and takes `--series` as the
  resolved series (never a literal version).
- Every writer of module docs (both doc writers) and the skill that commits them run that gate,
  each passing the series it resolved - a writer that skips the gate ships links the store cannot
  serve.
- `snippets/venv-resolution.md` (the interpreter SSOT) carries the reverse rule: plugin scripts run
  with the plugin `python3`, never with an Odoo venv python.

Texts are whitespace-normalized before matching so a soft line wrap cannot hide a phrase.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
SSOT_REL = "snippets/module-doc-references.md"
SSOT = PLUGIN / SSOT_REL
GATE = PLUGIN / "scripts" / "lib" / "doc_refs_check.py"
VENV_SSOT = PLUGIN / "snippets" / "venv-resolution.md"

GATE_RUNNERS = [
    PLUGIN / "agents" / "odoo-user-doc-writer.md",
    PLUGIN / "agents" / "odoo-marketing-writer.md",
    PLUGIN / "skills" / "odoo-doc-illustration" / "SKILL.md",
]

PROSE_SUFFIXES = {".md", ".yaml", ".yml", ".json", ".sh"}


def _norm(text: str) -> str:
    return " ".join(text.split())


def _read(path: Path) -> str:
    assert path.is_file(), f"missing: {path}"
    return _norm(path.read_text(encoding="utf-8"))


def _prose_files() -> list[Path]:
    return sorted(
        p for p in PLUGIN.rglob("*")
        if p.is_file() and p.suffix in PROSE_SUFFIXES
        and not p.name.upper().startswith("CHANGELOG")
        and "/evals/" not in "/" + p.relative_to(PLUGIN).as_posix()
    )


# --------------------------------------------------------------------------- #
# Matchers (+ proof they can fail)
# --------------------------------------------------------------------------- #
STORE_FORM_RE = re.compile(r"/apps/modules/")
GATE_CMD_RE = re.compile(r'python3 "\$\{CLAUDE_PLUGIN_ROOT\}/scripts/lib/doc_refs_check\.py"([^`]*)')
LITERAL_SERIES_RE = re.compile(r"--series[`\s=]*\d")
# `--series` bound to a resolved value: "`--series` = the Step 0 version", "= M's resolved series".
RESOLVED_SERIES_RE = re.compile(r"--series`?\s*=\s*[^.;)]{0,40}?(?:resolved|Step 0)", re.I)
GATE_POINTER = "module-doc-references.md` § Reference gate"


def test_matchers_can_fail():
    assert LITERAL_SERIES_RE.search("run with `--series 17.0`")
    assert LITERAL_SERIES_RE.search("--series=16.0")
    assert not LITERAL_SERIES_RE.search("--series <resolved series>")
    assert RESOLVED_SERIES_RE.search("(`--series` = the Step 0 version)")
    assert RESOLVED_SERIES_RE.search("`--series` = M's resolved series")
    assert not RESOLVED_SERIES_RE.search("`--series` = 17.0")
    assert GATE_CMD_RE.search('python3 "${CLAUDE_PLUGIN_ROOT}/scripts/lib/doc_refs_check.py" --series x')
    assert not GATE_CMD_RE.search('/opt/venv/bin/python scripts/lib/doc_refs_check.py --series x')


# --------------------------------------------------------------------------- #
# SSOT shape
# --------------------------------------------------------------------------- #
def test_ssot_is_the_only_prose_stating_the_store_link_form():
    files = _prose_files()
    assert len(files) > 200, "prose scan is vacuous"
    stating = sorted(
        p.relative_to(PLUGIN).as_posix() for p in files
        if STORE_FORM_RE.search(p.read_text(encoding="utf-8", errors="replace"))
    )
    assert stating == [SSOT_REL], (
        f"only {SSOT_REL} may state the /apps/modules/ link form; others point at it: {stating}"
    )


def test_ssot_gate_command_matches_the_real_script_cli():
    text = _read(SSOT)
    m = GATE_CMD_RE.search(text)
    assert m, f"{SSOT_REL} must give the gate command run with the plugin interpreter python3"
    assert GATE.is_file(), f"gate script missing: {GATE}"
    flags = set(re.findall(r"--[a-z][a-z-]+", m.group(1)))
    assert {"--module-root", "--series"} <= flags, f"gate command lacks required flags: {flags}"
    help_out = subprocess.run(
        [sys.executable, str(GATE), "--help"], capture_output=True, text=True, timeout=30
    ).stdout
    unknown = [f for f in flags if f not in help_out]
    assert not unknown, f"SSOT gate command passes flags the script does not accept: {unknown}"
    assert "--series <resolved series>" in text, "the SSOT must take --series from the resolved series"
    assert not LITERAL_SERIES_RE.search(text), "the SSOT must never spell a literal --series value"


def test_ssot_states_the_three_exit_outcomes():
    text = _read(SSOT)
    for outcome in ("Exit 0", "Exit 1", "Exit 2"):
        assert outcome in text, f"{SSOT_REL} must tell the runner what {outcome} means"
    assert "NEEDS_CONTEXT" in text


# --------------------------------------------------------------------------- #
# Consumers run the gate with the resolved series
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("path", GATE_RUNNERS, ids=lambda p: p.relative_to(PLUGIN).as_posix())
def test_doc_writers_and_skill_run_the_gate_with_the_resolved_series(path: Path):
    text = _read(path)
    rel = path.relative_to(PLUGIN).as_posix()
    assert GATE_POINTER in text, f"{rel} must run the reference gate ({GATE_POINTER})"
    assert RESOLVED_SERIES_RE.search(text), f"{rel} must pass --series from the series it resolved"
    assert not LITERAL_SERIES_RE.search(text), f"{rel} must never pass a literal --series value"


def test_no_prose_passes_a_literal_series_to_the_gate():
    offenders = [
        p.relative_to(PLUGIN).as_posix() for p in _prose_files()
        if LITERAL_SERIES_RE.search(_norm(p.read_text(encoding="utf-8", errors="replace")))
        and "doc_refs_check" in p.read_text(encoding="utf-8", errors="replace")
    ]
    assert not offenders, f"literal --series value next to the gate: {offenders}"


# --------------------------------------------------------------------------- #
# Interpreter split
# --------------------------------------------------------------------------- #
def test_venv_ssot_carries_the_plugin_interpreter_rule():
    text = _read(VENV_SSOT)
    assert "Run plugin scripts (`${CLAUDE_PLUGIN_ROOT}/scripts/...`) with the plugin interpreter `python3`" in text
    assert "never with an Odoo venv python" in text
    assert "run Odoo, tests and migrations only with the venv python resolved here" in text
