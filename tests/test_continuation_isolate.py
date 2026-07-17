"""Behavioral guard for hooks/drive-continuation.sh (+ the sibling hooks/parse-continuation.sh
nudge) after Problem-3 namespacing: the run-state glob must resolve against the per-worktree
ISOLATE dir (`scripts/lib/resolve_project_dir.sh isolate`), not a bare project-relative
`./.odoo-ai/`, and a resolver refusal must degrade to the legacy path rather than ever crashing
or blocking a session.

Business rules protected, NOT the implementation:

  - **Per-worktree isolation (the C-1 regression fix).** Two linked worktrees of ONE repo, each
    running an independent drive-to-done run, must NOT see each other's `run-*.json`. A NAIVE
    migration off the old project-relative convention that pointed run-state at a single
    machine-global or repo-SHARE location (instead of the per-worktree ISOLATE dir) would put
    both worktrees' run files in the SAME directory, making `cnt == 2` in both worktrees ->
    the hook goes silent in BOTH (ambiguous, degrade-safe) instead of correctly nudging each
    worktree about its own run. This file asserts the correct, worktree-scoped outcome AND
    reproduces the naive-shared failure mode directly, so a regression back to a shared root
    fails this file for the right reason.
  - **Resilience.** A resolver refusal (non-git cwd with no `.odoo-ai-root` / `__manifest__.py`
    marker anywhere up the chain) or any resolver error must never crash the hook or block the
    session - it must silently fall back to the legacy `<proj>/.odoo-ai` path and keep behaving
    exactly as it did before Problem-3 namespacing.

Hermetic: every test runs against throwaway git repos/worktrees and a throwaway $ODOO_AI_HOME
under tmp_path - never the real $HOME, never this repo's own git state.

Run with: python3 -m pytest tests/test_continuation_isolate.py -v
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = ROOT / "plugins" / "odoo-ai-agents"
DRIVE_HOOK = PLUGIN_ROOT / "hooks" / "drive-continuation.sh"
PARSE_HOOK = PLUGIN_ROOT / "hooks" / "parse-continuation.sh"
RESOLVER = PLUGIN_ROOT / "scripts" / "lib" / "resolve_project_dir.sh"

pytestmark = pytest.mark.skipif(
    shutil.which("jq") is None or shutil.which("bash") is None or shutil.which("git") is None,
    reason="needs jq + bash + git; the hooks themselves degrade to a silent pass without jq/bash",
)

_GIT_ENV_EXTRA = {
    "GIT_AUTHOR_NAME": "test",
    "GIT_AUTHOR_EMAIL": "test@test.invalid",
    "GIT_COMMITTER_NAME": "test",
    "GIT_COMMITTER_EMAIL": "test@test.invalid",
    "GIT_CONFIG_NOSYSTEM": "1",
}


def _env(home: Path, **extra) -> dict:
    """A clean subprocess env: throwaway $ODOO_AI_HOME/$HOME, no override vars leaking in from
    the invoking shell, plugin root pinned - so every path is fully hermetic."""
    e = dict(os.environ)
    for var in ("ODOO_AI_HOME", "ODOO_AI_PROJECT_DIR", "ODOO_AI_WORKTREE_DIR", "ODOO_AI_INSTANCES"):
        e.pop(var, None)
    e["ODOO_AI_HOME"] = str(home)
    e["HOME"] = str(home)
    e["CLAUDE_PLUGIN_ROOT"] = str(PLUGIN_ROOT)
    e.update(_GIT_ENV_EXTRA)
    e.update(extra)
    return e


def _git(args, cwd: Path, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, env=env)


def _init_repo(path: Path, env: dict) -> None:
    path.mkdir(parents=True, exist_ok=True)
    assert _git(["init", "-q"], path, env).returncode == 0
    (path / "README.md").write_text("x", encoding="utf-8")
    assert _git(["add", "README.md"], path, env).returncode == 0
    r = _git(["commit", "-q", "-m", "init"], path, env)
    assert r.returncode == 0, r.stderr


def _add_worktree(repo: Path, wt_path: Path, env: dict) -> None:
    r = _git(["worktree", "add", "-q", str(wt_path)], repo, env)
    assert r.returncode == 0, r.stderr


def _resolve_isolate(cwd: Path, env: dict) -> str:
    r = subprocess.run(["bash", str(RESOLVER), "isolate"], cwd=cwd, capture_output=True,
                        text=True, env=env)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def _run_hook(hook: Path, cwd: Path, env: dict, transcript_lines=None, stop_hook_active=False):
    """Invoke a Stop/SubagentStop hook with a minimal stdin payload carrying `cwd`."""
    payload = {"cwd": str(cwd), "stop_hook_active": stop_hook_active}
    if transcript_lines is not None:
        tpath = cwd / "transcript.jsonl"
        tpath.write_text("\n".join(transcript_lines) + "\n", encoding="utf-8")
        payload["transcript_path"] = str(tpath)
    proc = subprocess.run(
        ["bash", str(hook)], input=json.dumps(payload), capture_output=True, text=True,
        timeout=30, env=env,
    )
    out = proc.stdout.strip()
    parsed = json.loads(out) if out else None
    return proc.returncode, parsed


def _needs_next(run_id: str, cursor: str = "nodeA") -> dict:
    return {"run_id": run_id, "status": "NEEDS_NEXT", "cursor": cursor}


def _cont_needs_next_text() -> str:
    body = "done.\n```continuation\nstatus: NEEDS_NEXT\nproduced: []\nnext: []\n```"
    return json.dumps({"role": "assistant", "content": [{"type": "text", "text": body}]})


# --------------------------------------------------------------------------- #
# Existence / static sanity
# --------------------------------------------------------------------------- #
def test_hooks_exist_and_parse():
    for h in (DRIVE_HOOK, PARSE_HOOK):
        assert h.exists(), f"hook not found at {h}"
        r = subprocess.run(["bash", "-n", str(h)], capture_output=True, text=True)
        assert r.returncode == 0, f"{h.name} failed bash -n: {r.stderr}"


# --------------------------------------------------------------------------- #
# Per-worktree ISOLATE scoping (the C-1 regression fix)
# --------------------------------------------------------------------------- #
def test_two_worktrees_each_yield_cnt_one_independently(tmp_path):
    """Two linked worktrees of ONE repo, each with its OWN NEEDS_NEXT run-*.json placed at its
    resolver-computed ISOLATE dir, must each nudge about ONLY their own run (cnt==1 per
    worktree) - never see, nor be confused by, the sibling worktree's run file."""
    home = tmp_path / "home"
    env = _env(home)
    repo = tmp_path / "repo"
    wt2 = tmp_path / "wt2"
    _init_repo(repo, env)
    _add_worktree(repo, wt2, env)

    isolate1 = Path(_resolve_isolate(repo, env))
    isolate2 = Path(_resolve_isolate(wt2, env))
    assert isolate1 != isolate2, "two linked worktrees must diverge on the ISOLATE dir"

    isolate1.mkdir(parents=True, exist_ok=True)
    isolate2.mkdir(parents=True, exist_ok=True)
    (isolate1 / "run-a.json").write_text(json.dumps(_needs_next("run-a")), encoding="utf-8")
    (isolate2 / "run-b.json").write_text(json.dumps(_needs_next("run-b")), encoding="utf-8")

    rc1, out1 = _run_hook(DRIVE_HOOK, repo, env)
    rc2, out2 = _run_hook(DRIVE_HOOK, wt2, env)

    assert rc1 == 0 and rc2 == 0
    assert out1 is not None and out1.get("continue") is True
    assert out2 is not None and out2.get("continue") is True
    assert "run-a" in out1["systemMessage"] and "run-b" not in out1["systemMessage"], (
        "worktree 1 must nudge about its OWN run only - a naive shared design would see both "
        "run files (cnt==2) and go silent instead"
    )
    assert "run-b" in out2["systemMessage"] and "run-a" not in out2["systemMessage"], (
        "worktree 2 must nudge about its OWN run only"
    )
    assert str(isolate1) in out1["systemMessage"]
    assert str(isolate2) in out2["systemMessage"]


def test_naive_shared_design_would_go_silent_ambiguous(tmp_path):
    """Direct reproduction of the failure mode the ISOLATE fix prevents: if run-state were
    written to a SINGLE shared location for two worktrees (a naive migration off the old
    project-relative convention onto a repo-SHARE-style root instead of per-worktree ISOLATE),
    both run files land in ONE directory and the hook sees cnt==2 -> silent (no nudge, by the
    documented degrade-safe "ambiguous which to name" rule). This is the regression the two-axis
    ISOLATE convention exists to avoid, reproduced explicitly rather than only implied."""
    home = tmp_path / "home"
    env = _env(home)
    repo = tmp_path / "repo"
    wt2 = tmp_path / "wt2"
    _init_repo(repo, env)
    _add_worktree(repo, wt2, env)

    shared_dir = tmp_path / "naive-shared-run-state"
    shared_dir.mkdir(parents=True, exist_ok=True)
    (shared_dir / "run-a.json").write_text(json.dumps(_needs_next("run-a")), encoding="utf-8")
    (shared_dir / "run-b.json").write_text(json.dumps(_needs_next("run-b")), encoding="utf-8")

    # Force BOTH worktrees' resolver output to the SAME dir via the documented
    # ODOO_AI_WORKTREE_DIR override - this simulates exactly what a naive "always resolve to one
    # shared root" implementation would produce, without touching the (locked) resolver itself.
    naive_env = _env(home, ODOO_AI_WORKTREE_DIR=str(shared_dir))

    rc1, out1 = _run_hook(DRIVE_HOOK, repo, naive_env)
    rc2, out2 = _run_hook(DRIVE_HOOK, wt2, naive_env)

    assert rc1 == 0 and rc2 == 0, "ambiguity must degrade to a silent pass, never crash"
    assert out1 is None, "cnt==2 in a naively-shared dir must go silent, not nudge either run"
    assert out2 is None, "cnt==2 in a naively-shared dir must go silent, not nudge either run"


# --------------------------------------------------------------------------- #
# Resolver-refuse fallback (CRITICAL RESILIENCE - never crash, never block)
# --------------------------------------------------------------------------- #
def test_resolver_refusal_falls_back_to_legacy_path_without_crashing(tmp_path):
    """A non-git cwd with NO project marker anywhere up the chain (no `.odoo-ai-root`, no
    `__manifest__.py`) makes the resolver refuse (non-zero exit, no stdout). The hook must not
    propagate that failure - it must silently fall back to the legacy `<proj>/.odoo-ai` path and
    keep working exactly as it did before Problem-3 namespacing."""
    home = tmp_path / "home"
    env = _env(home)
    proj = tmp_path / "no-marker-project"
    proj.mkdir(parents=True)

    # Sanity: the resolver itself really does refuse here (no git, no marker).
    r = subprocess.run(["bash", str(RESOLVER), "isolate"], cwd=proj, capture_output=True,
                        text=True, env=env)
    assert r.returncode != 0 and not r.stdout.strip(), (
        "test precondition: resolver must actually refuse for this fixture to be meaningful"
    )

    legacy_dir = proj / ".odoo-ai"
    legacy_dir.mkdir(parents=True)
    (legacy_dir / "run-x.json").write_text(json.dumps(_needs_next("run-x")), encoding="utf-8")

    rc, out = _run_hook(DRIVE_HOOK, proj, env)
    assert rc == 0, "a resolver refusal must never crash or non-zero-exit the hook"
    assert out is not None and out.get("continue") is True
    assert "run-x" in out["systemMessage"]
    assert str(legacy_dir) in out["systemMessage"], "must fall back to the legacy project path"


def test_missing_plugin_root_falls_back_without_crashing(tmp_path):
    """CLAUDE_PLUGIN_ROOT unset (resolver script unreachable) is a second, independent failure
    mode the hook must also degrade past cleanly."""
    home = tmp_path / "home"
    env = _env(home)
    del env["CLAUDE_PLUGIN_ROOT"]
    proj = tmp_path / "proj-no-plugin-root"
    proj.mkdir(parents=True)
    legacy_dir = proj / ".odoo-ai"
    legacy_dir.mkdir(parents=True)
    (legacy_dir / "run-y.json").write_text(json.dumps(_needs_next("run-y")), encoding="utf-8")

    rc, out = _run_hook(DRIVE_HOOK, proj, env)
    assert rc == 0
    assert out is not None and "run-y" in out["systemMessage"]


# --------------------------------------------------------------------------- #
# parse-continuation.sh - same resolve+fallback pattern, sibling hook
# --------------------------------------------------------------------------- #
def test_parse_continuation_names_the_resolved_isolate_dir(tmp_path):
    home = tmp_path / "home"
    env = _env(home)
    repo = tmp_path / "repo"
    _init_repo(repo, env)
    isolate = Path(_resolve_isolate(repo, env))

    rc, out = _run_hook(PARSE_HOOK, repo, env, transcript_lines=[_cont_needs_next_text()])
    assert rc == 0
    assert out is not None and out.get("continue") is True
    assert str(isolate) in out["systemMessage"]


def test_parse_continuation_resolver_refusal_falls_back_without_crashing(tmp_path):
    home = tmp_path / "home"
    env = _env(home)
    proj = tmp_path / "no-marker-project-parse"
    proj.mkdir(parents=True)

    rc, out = _run_hook(PARSE_HOOK, proj, env, transcript_lines=[_cont_needs_next_text()])
    assert rc == 0, "a resolver refusal must never crash or non-zero-exit the hook"
    assert out is not None and out.get("continue") is True
    assert str(proj / ".odoo-ai") in out["systemMessage"]
