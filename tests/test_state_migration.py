"""Tests for the Tier-2 state-root migration helper (migrate_project_state.sh).

Business rules protected (Problem 3 - snippets/state-root-resolution.md, the
LOCKED two-axis ~/.odoo-ai/ state-root convention):
  - a SHARE-classified legacy subpath lands under the resolved SHARE dir; an
    ISOLATE-classified one lands under the resolved ISOLATE dir.
  - copy-not-clobber: a pre-existing Tier-2 target is left COMPLETELY
    untouched by a (re-)migration - never overwritten.
  - idempotent: re-running the migration after the legacy source changed does
    NOT re-copy (the first migrated copy wins, exactly like
    resolve_instances.sh's `_migrate_local_instances_to_global`).
  - Tier-1 subpaths (instances.toml, runtime/, logs/, i18n.json) are NEVER
    migrated by this helper - resolve_instances.sh already owns them, and
    re-migrating here would risk breaking the Tier-1 "always flat, never a
    project/worktree dir" invariant.
  - a log line is emitted on stdout for each subpath actually copied.
  - atomic + resumable: the copy for one subpath never writes directly to its
    final Tier-2 destination (it stages into a sibling temp dir and only
    renames into place on full success), so `[ -e dest ]` genuinely means
    "complete." A staging leftover from an interrupted PRIOR attempt (crash,
    SIGKILL, hook timeout) is NOT treated as "already migrated" - it is
    detected, removed, and the copy is retried to a full, correct result.

Hermetic: a temp $ODOO_AI_HOME + a temp git repo (own git-common-dir), so the
SHARE/ISOLATE repo-key resolves deterministically without touching the real
machine-global ~/.odoo-ai or this checkout's own git identity.
"""
import hashlib
import os
import subprocess
from pathlib import Path
from shutil import which

import pytest

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "lib" / "migrate_project_state.sh"

requires_bash = pytest.mark.skipif(which("bash") is None, reason="bash not available")
requires_git = pytest.mark.skipif(which("git") is None, reason="git not available")
pytestmark = [requires_bash, requires_git]


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def _init_repo(tmp_path: Path, name: str = "repo") -> Path:
    repo = tmp_path / name
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    return repo


def _hash12(path: Path) -> str:
    return hashlib.sha256(str(path).encode()).hexdigest()[:12]


def _git_common_dir(repo: Path) -> Path:
    out = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"],
        cwd=repo, capture_output=True, text=True, check=True,
    ).stdout.strip()
    p = Path(out)
    if not p.is_absolute():
        p = repo / p
    return p.resolve()


def _git_toplevel(repo: Path) -> Path:
    out = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=repo, capture_output=True, text=True, check=True,
    ).stdout.strip()
    return Path(out).resolve()


def _expected_dirs(repo: Path, home: Path) -> tuple[Path, Path]:
    """Independently compute the SHARE/ISOLATE dirs the resolver should pick,
    mirroring resolve_project_dir.sh's documented formula (never re-implementing
    the shipped resolver's logic - just its published, LOCKED hash inputs)."""
    repo_key = _hash12(_git_common_dir(repo))
    wt_key = _hash12(_git_toplevel(repo))
    share = home / ".odoo-ai" / "projects" / repo_key
    isolate = share / "worktrees" / wt_key
    return share, isolate


def _run_migration(repo: Path, home: Path) -> subprocess.CompletedProcess:
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    env["HOME"] = str(home)
    env["ODOO_AI_HOME"] = str(home / ".odoo-ai")
    return subprocess.run(
        ["bash", str(LIB), "run", str(repo)],
        capture_output=True, text=True, env=env, cwd=str(repo),
    )


# --------------------------------------------------------------------------- #
# tests
# --------------------------------------------------------------------------- #

def test_share_and_isolate_subpaths_land_under_their_resolved_dirs(tmp_path):
    """A SHARE-classified legacy subpath (glossary.yml) lands under the resolved
    SHARE dir; an ISOLATE-classified one (worklog/<run>/) lands under the
    resolved ISOLATE dir - never the other way around, never left in place."""
    repo = _init_repo(tmp_path)
    home = tmp_path / "home"
    home.mkdir()

    (repo / ".odoo-ai" / "coordination" / "modules").mkdir(parents=True)
    (repo / ".odoo-ai" / "glossary.yml").write_text("term: my-project\n", encoding="utf-8")
    (repo / ".odoo-ai" / "worklog" / "run-abc").mkdir(parents=True)
    (repo / ".odoo-ai" / "worklog" / "run-abc" / "log.txt").write_text("step 1\n", encoding="utf-8")

    proc = _run_migration(repo, home)
    assert proc.returncode == 0, f"migration failed.\nstdout: {proc.stdout}\nstderr: {proc.stderr}"

    share_dir, isolate_dir = _expected_dirs(repo, home)

    share_target = share_dir / "glossary.yml"
    assert share_target.is_file(), (
        f"SHARE subpath glossary.yml must land under the resolved SHARE dir "
        f"{share_dir}; not found at {share_target}.\nstdout: {proc.stdout}"
    )
    assert share_target.read_text(encoding="utf-8") == "term: my-project\n"

    isolate_target = isolate_dir / "worklog" / "run-abc" / "log.txt"
    assert isolate_target.is_file(), (
        f"ISOLATE subpath worklog/run-abc/ must land under the resolved "
        f"ISOLATE dir {isolate_dir}; not found at {isolate_target}.\n"
        f"stdout: {proc.stdout}"
    )
    assert isolate_target.read_text(encoding="utf-8") == "step 1\n"

    # And never cross-classified (SHARE content must not appear under
    # ISOLATE, ISOLATE content must not appear under the bare SHARE dir).
    assert not (isolate_dir / "glossary.yml").exists()
    assert not (share_dir / "worklog").exists()


def test_copy_not_clobber_preserves_preexisting_target(tmp_path):
    """A Tier-2 target that already exists (e.g. from a previous, different
    migration or a hand-edit) is left COMPLETELY untouched - never overwritten
    by the legacy source's content."""
    repo = _init_repo(tmp_path)
    home = tmp_path / "home"
    home.mkdir()

    (repo / ".odoo-ai").mkdir()
    (repo / ".odoo-ai" / "glossary.yml").write_text("legacy content\n", encoding="utf-8")

    share_dir, _isolate_dir = _expected_dirs(repo, home)
    share_dir.mkdir(parents=True)
    (share_dir / "glossary.yml").write_text("pre-existing Tier-2 content\n", encoding="utf-8")

    proc = _run_migration(repo, home)
    assert proc.returncode == 0, f"migration failed.\nstdout: {proc.stdout}\nstderr: {proc.stderr}"

    assert (share_dir / "glossary.yml").read_text(encoding="utf-8") == "pre-existing Tier-2 content\n", (
        "a pre-existing Tier-2 target must never be clobbered by the legacy source"
    )
    # Log output must say so (skip, not migrate).
    assert "already exists" in proc.stdout or "skip" in proc.stdout.lower(), (
        f"expected a skip note in stdout.\nstdout: {proc.stdout}"
    )


def test_second_run_is_idempotent_noop(tmp_path):
    """Running the migration twice, with the legacy source CHANGED in between,
    must NOT re-copy - the first migrated copy wins (idempotent, matching
    resolve_instances.sh's `_migrate_local_instances_to_global` contract)."""
    repo = _init_repo(tmp_path)
    home = tmp_path / "home"
    home.mkdir()

    (repo / ".odoo-ai").mkdir()
    (repo / ".odoo-ai" / "glossary.yml").write_text("version 1\n", encoding="utf-8")

    proc1 = _run_migration(repo, home)
    assert proc1.returncode == 0, f"first run failed.\nstdout: {proc1.stdout}\nstderr: {proc1.stderr}"

    share_dir, _isolate_dir = _expected_dirs(repo, home)
    assert (share_dir / "glossary.yml").read_text(encoding="utf-8") == "version 1\n"

    # Mutate the legacy source - a true no-op second run must NOT pick this up.
    (repo / ".odoo-ai" / "glossary.yml").write_text("version 2 (should NOT be picked up)\n", encoding="utf-8")

    proc2 = _run_migration(repo, home)
    assert proc2.returncode == 0, f"second run failed.\nstdout: {proc2.stdout}\nstderr: {proc2.stderr}"
    assert (share_dir / "glossary.yml").read_text(encoding="utf-8") == "version 1\n", (
        "second run must be a no-op - it must NOT re-copy the (now-changed) legacy source"
    )


def test_tier1_subpaths_are_not_remigrated(tmp_path):
    """Tier-1 subpaths (instances.toml, runtime/, logs/, i18n.json) are NEVER
    migrated by this helper - resolve_instances.sh already owns them, and this
    helper must not create ANY Tier-2 copy of them."""
    repo = _init_repo(tmp_path)
    home = tmp_path / "home"
    home.mkdir()

    legacy = repo / ".odoo-ai"
    legacy.mkdir()
    (legacy / "instances.toml").write_text('[[instance]]\nseries = "17.0"\n', encoding="utf-8")
    (legacy / "i18n.json").write_text('{"default_languages": ["vi_VN"]}\n', encoding="utf-8")
    (legacy / "runtime").mkdir()
    (legacy / "runtime" / "leases.json").write_text("{}\n", encoding="utf-8")
    (legacy / "logs").mkdir()
    (legacy / "logs" / "foo.log").write_text("log line\n", encoding="utf-8")
    # A genuine Tier-2 subpath too, so we can tell "nothing was migrated at
    # all" (a bug) apart from "Tier-1 correctly excluded" (the real assertion).
    (legacy / "glossary.yml").write_text("term: proj\n", encoding="utf-8")

    proc = _run_migration(repo, home)
    assert proc.returncode == 0, f"migration failed.\nstdout: {proc.stdout}\nstderr: {proc.stderr}"

    share_dir, isolate_dir = _expected_dirs(repo, home)

    # The genuine Tier-2 subpath DID migrate (sanity: the helper actually ran).
    assert (share_dir / "glossary.yml").is_file(), (
        f"sanity check failed: glossary.yml should have migrated.\nstdout: {proc.stdout}"
    )

    # None of the Tier-1 names may appear anywhere under SHARE or ISOLATE.
    for root in (share_dir, isolate_dir):
        for tier1_name in ("instances.toml", "runtime", "logs", "i18n.json"):
            assert not (root / tier1_name).exists(), (
                f"Tier-1 subpath {tier1_name!r} must NEVER be migrated into "
                f"{root} - found at {root / tier1_name}"
            )

    # The legacy Tier-1 files themselves must be untouched (still present).
    assert (legacy / "instances.toml").exists()
    assert (legacy / "runtime" / "leases.json").exists()
    assert (legacy / "logs" / "foo.log").exists()
    assert (legacy / "i18n.json").exists()


def test_log_line_emitted_for_each_migrated_subpath(tmp_path):
    """Every subpath actually copied must produce a log line naming the
    legacy subpath, its Tier-2 destination, and the tier it was classified
    into - so a human/agent can audit what happened."""
    repo = _init_repo(tmp_path)
    home = tmp_path / "home"
    home.mkdir()

    (repo / ".odoo-ai").mkdir()
    (repo / ".odoo-ai" / "glossary.yml").write_text("term: proj\n", encoding="utf-8")
    (repo / ".odoo-ai" / "wave" / "impl").mkdir(parents=True)
    (repo / ".odoo-ai" / "wave" / "impl" / "log.txt").write_text("wave 1\n", encoding="utf-8")

    proc = _run_migration(repo, home)
    assert proc.returncode == 0, f"migration failed.\nstdout: {proc.stdout}\nstderr: {proc.stderr}"

    assert "Migrated .odoo-ai/glossary.yml" in proc.stdout and "(SHARE)" in proc.stdout, (
        f"expected a SHARE migration log line for glossary.yml.\nstdout: {proc.stdout}"
    )
    assert "Migrated .odoo-ai/wave" in proc.stdout and "(ISOLATE)" in proc.stdout, (
        f"expected an ISOLATE migration log line for wave/.\nstdout: {proc.stdout}"
    )


def test_interrupted_copy_leftover_is_retried_not_treated_as_migrated(tmp_path):
    """A crash/kill mid-copy (OOM, SessionStart's hook timeout, a concurrent
    same-worktree session) must never be indistinguishable from "fully
    migrated." Simulate the exact state such an interruption leaves behind -
    a staging temp dir at the destination's parent, matching the
    "<dest>.migrating.<pid>" pattern the atomic-copy fix uses, with NO final
    dest present (since the fix never writes the final dest directly) - and
    assert the NEXT run detects it as incomplete, removes it, and completes a
    full, correct copy rather than silently skipping (the pre-fix bug: the
    idempotency guard only tested existence of $dest, so a partial copy that
    happened to land AT $dest would have been treated as done forever)."""
    repo = _init_repo(tmp_path)
    home = tmp_path / "home"
    home.mkdir()

    (repo / ".odoo-ai").mkdir()
    (repo / ".odoo-ai" / "glossary.yml").write_text(
        "full legacy content that must survive the retry\n", encoding="utf-8"
    )

    share_dir, _isolate_dir = _expected_dirs(repo, home)
    share_dir.mkdir(parents=True)
    stale_tmp = share_dir / "glossary.yml.migrating.999999"
    stale_tmp.write_text("TRUNCATED partial cop", encoding="utf-8")

    final_dest = share_dir / "glossary.yml"
    assert not final_dest.exists(), (
        "sanity: an interrupted attempt must never have produced a final dest "
        "directly - only the staging leftover"
    )

    proc = _run_migration(repo, home)
    assert proc.returncode == 0, f"migration failed.\nstdout: {proc.stdout}\nstderr: {proc.stderr}"

    assert final_dest.is_file(), (
        "an interrupted prior copy (staging leftover only, no final dest) "
        f"must be retried to completion, not silently skipped.\n"
        f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
    )
    assert final_dest.read_text(encoding="utf-8") == "full legacy content that must survive the retry\n", (
        "the retried copy must be the FULL, correct content - not left as, "
        "or derived from, the stale partial"
    )
    assert not stale_tmp.exists(), "the stale staging leftover must be cleaned up, not left behind forever"

    combined = (proc.stdout + proc.stderr).lower()
    assert "partial" in combined or "interrupted" in combined or "retry" in combined or "retrying" in combined, (
        f"expected a one-line diagnostic noting the partial/interrupted retry.\n"
        f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
    )


def test_interrupted_directory_copy_leftover_is_retried_to_a_complete_tree(tmp_path):
    """Same contract as the file case, but for a DIRECTORY subpath (the more
    realistic crash scenario per the review: a large `coordination/` or
    `documentation/` tree mid-`cp -R`). A partial staging tree - missing one
    of two children, as a real SIGKILL mid-recursive-copy would leave - must
    be discarded wholesale and the subpath re-copied in full, not "completed"
    by assuming the partial tree was fine."""
    repo = _init_repo(tmp_path)
    home = tmp_path / "home"
    home.mkdir()

    legacy_coord = repo / ".odoo-ai" / "coordination" / "modules"
    (legacy_coord / "mod_a").mkdir(parents=True)
    (legacy_coord / "mod_b").mkdir(parents=True)
    (legacy_coord / "mod_a" / "wi.md").write_text("wi 1\n", encoding="utf-8")
    (legacy_coord / "mod_b" / "wi.md").write_text("wi 2\n", encoding="utf-8")

    share_dir, _isolate_dir = _expected_dirs(repo, home)
    share_dir.mkdir(parents=True)
    stale_tmp = share_dir / "coordination.migrating.888888"
    (stale_tmp / "modules" / "mod_a").mkdir(parents=True)
    (stale_tmp / "modules" / "mod_a" / "wi.md").write_text("PARTIAL wi 1 (trunc", encoding="utf-8")
    # mod_b was never reached before the simulated kill.

    proc = _run_migration(repo, home)
    assert proc.returncode == 0, f"migration failed.\nstdout: {proc.stdout}\nstderr: {proc.stderr}"

    final_coord = share_dir / "coordination"
    assert (final_coord / "modules" / "mod_a" / "wi.md").read_text(encoding="utf-8") == "wi 1\n"
    assert (final_coord / "modules" / "mod_b" / "wi.md").read_text(encoding="utf-8") == "wi 2\n", (
        "mod_b (missing from the partial staging tree) must be present in the "
        "retried, complete copy"
    )
    assert not stale_tmp.exists(), "the stale staging leftover must be cleaned up"


def test_no_legacy_dir_is_a_fast_noop(tmp_path):
    """No legacy .odoo-ai/ at all: the migration must be a clean no-op (exit 0,
    no Tier-2 dir created) - not an error, and not a silent full-tree scan."""
    repo = _init_repo(tmp_path)
    home = tmp_path / "home"
    home.mkdir()

    proc = _run_migration(repo, home)
    assert proc.returncode == 0, f"migration failed.\nstdout: {proc.stdout}\nstderr: {proc.stderr}"
    assert not (home / ".odoo-ai" / "projects").exists(), (
        "no legacy .odoo-ai/ means nothing to migrate - no Tier-2 project dir "
        "should be created at all"
    )


def test_unrecognized_top_level_entry_is_left_in_place_not_migrated(tmp_path):
    """A top-level legacy entry that is in NEITHER the SHARE nor the ISOLATE
    table (here a stale `context.md`, a name neither table claims)
    must be left exactly where it is - never copied into either resolved
    Tier-2 dir, never deleted, never guessed into a tier "to be safe"
    (state-root-resolution.md "The rule"). This is the live `unknown` outcome
    `_tier2_classify_top()` falls through to for any unrecognized name."""
    repo = _init_repo(tmp_path)
    home = tmp_path / "home"
    home.mkdir()

    legacy = repo / ".odoo-ai"
    legacy.mkdir()
    (legacy / "context.md").write_text("id: stale-legacy-artifact\n", encoding="utf-8")
    # A genuine SHARE subpath alongside it, so we can tell "the helper ran but
    # correctly excluded the unknown entry" apart from "nothing ran at all".
    (legacy / "glossary.yml").write_text("term: proj\n", encoding="utf-8")

    proc = _run_migration(repo, home)
    assert proc.returncode == 0, f"migration failed.\nstdout: {proc.stdout}\nstderr: {proc.stderr}"

    share_dir, isolate_dir = _expected_dirs(repo, home)

    # Sanity: the helper did run and DID migrate the recognized SHARE sibling.
    assert (share_dir / "glossary.yml").is_file(), (
        f"sanity check failed: glossary.yml should have migrated.\nstdout: {proc.stdout}"
    )

    # The unrecognized entry must never appear under either resolved Tier-2 dir.
    assert not (share_dir / "context.md").exists(), (
        f"unrecognized top-level entry context.md must NOT be migrated into SHARE "
        f"{share_dir}.\nstdout: {proc.stdout}"
    )
    assert not (isolate_dir / "context.md").exists(), (
        f"unrecognized top-level entry context.md must NOT be migrated into ISOLATE "
        f"{isolate_dir}.\nstdout: {proc.stdout}"
    )

    # The legacy file itself must be untouched - left in place, not deleted.
    assert (legacy / "context.md").is_file(), (
        "an unrecognized top-level entry must be left in place at its legacy path"
    )
    assert (legacy / "context.md").read_text(encoding="utf-8") == "id: stale-legacy-artifact\n", (
        "an unrecognized top-level entry must be left byte-for-byte untouched"
    )

    combined = (proc.stdout + proc.stderr).lower()
    assert "unrecognized" in combined or "unknown" in combined, (
        f"expected a diagnostic naming the unrecognized entry.\n"
        f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
    )


# --------------------------------------------------------------------------- #
# visual/ split (CS-C5 - visual/current/<slug>/ moved to ISOLATE)
#
# The file exercised no `visual/` case at all before these two tests (grep for
# "visual" returned zero hits) - the 2-arm top-level split (share/isolate) was
# completely unguarded for visual/'s own nested SHARE-vs-ISOLATE rule.
# --------------------------------------------------------------------------- #

def test_visual_children_split_share_and_isolate_by_full_subpath(tmp_path):
    """`visual/` is classified by the FULL subpath, never the top-level name
    alone (state-root-resolution.md "Note the split inside visual/"):
    `baselines/` and `doc/` land under SHARE; every other immediate child
    (e.g. `screenshots/`) lands under ISOLATE. Asserts where BYTES end up,
    not what a doc says."""
    repo = _init_repo(tmp_path)
    home = tmp_path / "home"
    home.mkdir()

    legacy_visual = repo / ".odoo-ai" / "visual"
    (legacy_visual / "baselines" / "baseline").mkdir(parents=True)
    (legacy_visual / "baselines" / "baseline" / "a.png").write_text("baseline-a", encoding="utf-8")
    (legacy_visual / "baselines" / "storageState-x.json").write_text("{}\n", encoding="utf-8")
    (legacy_visual / "doc").mkdir(parents=True)
    (legacy_visual / "doc" / "b.png").write_text("doc-b", encoding="utf-8")
    (legacy_visual / "screenshots" / "s").mkdir(parents=True)
    (legacy_visual / "screenshots" / "s" / "c.png").write_text("screenshot-c", encoding="utf-8")

    proc = _run_migration(repo, home)
    assert proc.returncode == 0, f"migration failed.\nstdout: {proc.stdout}\nstderr: {proc.stderr}"

    share_dir, isolate_dir = _expected_dirs(repo, home)

    assert (share_dir / "visual" / "baselines" / "baseline" / "a.png").read_text(encoding="utf-8") == "baseline-a", (
        f"visual/baselines/baseline/ must land under SHARE.\nstdout: {proc.stdout}"
    )
    assert (share_dir / "visual" / "baselines" / "storageState-x.json").read_text(encoding="utf-8") == "{}\n", (
        f"visual/baselines/storageState-*.json must land under SHARE.\nstdout: {proc.stdout}"
    )
    assert (share_dir / "visual" / "doc" / "b.png").read_text(encoding="utf-8") == "doc-b", (
        f"visual/doc/ must land under SHARE.\nstdout: {proc.stdout}"
    )
    assert (isolate_dir / "visual" / "screenshots" / "s" / "c.png").read_text(encoding="utf-8") == "screenshot-c", (
        f"visual/screenshots/ (not baselines/ or doc/) must land under ISOLATE.\nstdout: {proc.stdout}"
    )
    # Never cross-classified.
    assert not (isolate_dir / "visual" / "baselines").exists()
    assert not (isolate_dir / "visual" / "doc").exists()
    assert not (share_dir / "visual" / "screenshots").exists()


def test_legacy_baselines_current_is_discarded_not_migrated_to_share(tmp_path):
    """A legacy `visual/baselines/current/` (the pre-fix, SHARE-tier, cross-run
    location a visual-regression run's comparison set used to be written to)
    is a PER-RUN artifact with no run slug recoverable from the flat legacy
    layout - it must be DISCARDED, not copied wholesale into SHARE along with
    the rest of `baselines/`. Red today: the un-split `baselines | doc)` arm
    copies `baselines` wholesale, so the nested `current/` rides along into
    SHARE."""
    repo = _init_repo(tmp_path)
    home = tmp_path / "home"
    home.mkdir()

    legacy_current = repo / ".odoo-ai" / "visual" / "baselines" / "current"
    legacy_current.mkdir(parents=True)
    (legacy_current / "home-1280.png").write_text("stale-comparison-set", encoding="utf-8")

    proc = _run_migration(repo, home)
    assert proc.returncode == 0, f"migration failed.\nstdout: {proc.stdout}\nstderr: {proc.stderr}"

    share_dir, isolate_dir = _expected_dirs(repo, home)

    assert not (share_dir / "visual" / "baselines" / "current").exists(), (
        f"legacy visual/baselines/current/ must NOT be migrated into SHARE.\n"
        f"stdout: {proc.stdout}"
    )
    assert not (isolate_dir / "visual" / "current").exists(), (
        "legacy visual/baselines/current/ has no recoverable run slug - it must "
        "be discarded, not guessed into an ISOLATE per-slug path either.\n"
        f"stdout: {proc.stdout}"
    )
    assert "Discarded" in proc.stdout and "baselines/current" in proc.stdout, (
        f"expected a printed line naming the discarded legacy comparison set.\n"
        f"stdout: {proc.stdout}"
    )
