"""paths.py - Python parity resolver for Tier-2 project-scoped .odoo-ai/ state
(Problem 3 - namespaced ~/.odoo-ai/, two-axis root). Full policy:
snippets/state-root-resolution.md (SSOT for the classification tables and the
mandatory resolve-capture-substitute prose protocol).

Mirrors scripts/lib/resolve_project_dir.sh EXACTLY - shell/Python parity is a
stated INVARIANT (tested in tests/test_project_dir_resolution.py: both
resolvers must return the identical path for the same repo/worktree). Any
change to the algorithm here MUST be mirrored there, and vice versa.

Two axes under one machine-global root $ODOO_AI_HOME (default $HOME/.odoo-ai,
same convention as allocator.py's _home()):

    SHARE   - $ODOO_AI_HOME/projects/<repo-key>/
              <repo-key> = sha256(realpath(git rev-parse --git-common-dir))[:12]
              SAME for every linked worktree of one repo; DIFFERENT across
              separate repos.
    ISOLATE - $ODOO_AI_HOME/projects/<repo-key>/worktrees/<wt-key>/
              <wt-key> = sha256(realpath(git rev-parse --show-toplevel))[:12]
              DISTINCT per worktree (including the principal checkout).

Explicit overrides ($ODOO_AI_PROJECT_DIR for SHARE, $ODOO_AI_WORKTREE_DIR for
ISOLATE) are honored verbatim (still created, never re-hashed).

Non-git fallback (C-9): NEVER hash bare os.getcwd() (cwd-unstable). Walk UP
from the cwd to the nearest project marker and hash ITS realpath. Two marker
kinds, STRICT priority (C-2): `.odoo-ai-root` has GLOBAL priority - the walk
scans the WHOLE chain up to the filesystem root for it first; only when no
sentinel exists ANYWHERE does it fall back to the NEAREST `__manifest__.py`
dir. Real Odoo addons layouts nest a manifest under every module dir, so
"nearest marker of either kind" would mis-root from inside a module - the
sentinel exists precisely to override that. Outside git there is no separate
"worktree" concept, so the ISOLATE key degrades to the SAME marker key as the
SHARE key. Raises ProjectDirError (never silently keys on cwd) when NEITHER
marker is found.

CLI:
    python paths.py share      # prints the absolute SHARE dir
    python paths.py isolate    # prints the absolute ISOLATE dir
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys

__all__ = ["ProjectDirError", "share_dir", "isolate_dir"]


class ProjectDirError(RuntimeError):
    """Raised when neither git nor a project marker can resolve a project root -
    the caller must set $ODOO_AI_PROJECT_DIR / $ODOO_AI_WORKTREE_DIR explicitly
    rather than fall back to an unstable cwd-based key."""


# --------------------------------------------------------------------------- #
# internal helpers
# --------------------------------------------------------------------------- #
def _home() -> str:
    """${ODOO_AI_HOME:-$HOME/.odoo-ai}, trailing slashes fully normalised -
    mirrors allocator.py's `_home()` (same fix, same reason) and the shell
    convergence point (resolve_project_dir.sh's `_project_dir_home`,
    resolve_instances.sh's `_odoo_ai_global_instances`/`_odoo_ai_runtime_dir`) -
    all four are a stated PARITY INVARIANT. A doubled/tripled trailing slash on
    $ODOO_AI_HOME denotes the SAME directory as a single one (POSIX:
    "/a/b//" == "/a/b/" == "/a/b"), so it is collapsed HERE, at the source,
    exactly like share_dir/isolate_dir's override normalisation above - a bare
    `os.environ.get(...) or ...` (the prior form) left multi-slash input
    untouched, and `os.path.join` does not re-collapse it on every subsequent
    join, so an un-normalised $ODOO_AI_HOME with >=2 trailing slashes produced
    a DIFFERENT projects/<repo-key> string than resolve_project_dir.sh's
    (partially-stripping) shell chain - measured, see
    tests/test_project_dir_resolution.py's `odoo_ai_home` trailing-slash cases.
    An all-slashes $ODOO_AI_HOME (e.g. "/", "///") falls back to "/"."""
    override = os.environ.get("ODOO_AI_HOME")
    if override:
        return override.rstrip("/") or "/"
    return os.path.join(os.path.expanduser("~"), ".odoo-ai")


def _hash12(s: str) -> str:
    """First 12 hex chars of sha256(<raw bytes of s>) - no trailing newline,
    matching the shell resolver's `printf '%s' "$input" | sha256sum`."""
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]


def _git(args: list, cwd: str | None = None) -> str | None:
    """Run `git <args>` from `cwd` (default: the process cwd). Returns stripped
    stdout, or None on ANY failure (missing git binary, not a repo, ...) -
    mirrors the shell resolver's `2>/dev/null || fallback` swallow."""
    try:
        proc = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, check=False
        )
    except FileNotFoundError:
        return None
    if proc.returncode != 0:
        return None
    out = proc.stdout.strip()
    return out or None


def _marker_root(start_dir: str) -> str | None:
    """Walk UP from start_dir. `.odoo-ai-root` has GLOBAL priority over
    `__manifest__.py` (C-2, mirrors resolve_project_dir.sh's
    `_project_dir_marker_root`): scans the WHOLE chain for a sentinel first
    (returning the moment one is found); only if NO sentinel exists anywhere
    does it fall back to the NEAREST `__manifest__.py` dir recorded along the
    way. Returns None if the walk reaches the filesystem root with NEITHER
    marker found anywhere."""
    d = os.path.realpath(start_dir)
    nearest_manifest: str | None = None
    while True:
        if os.path.isfile(os.path.join(d, ".odoo-ai-root")):
            return d
        if nearest_manifest is None and os.path.isfile(os.path.join(d, "__manifest__.py")):
            nearest_manifest = d
        parent = os.path.dirname(d)
        if parent == d:
            return nearest_manifest
        d = parent


def _nongit_key(cwd: str | None = None) -> str | None:
    marker = _marker_root(cwd or os.getcwd())
    if marker is None:
        return None
    return _hash12(marker)


def _repo_key(cwd: str | None = None) -> str | None:
    common = _git(["rev-parse", "--git-common-dir"], cwd=cwd)
    if common is None:
        return _nongit_key(cwd)
    # `--git-common-dir` is CWD-RELATIVE from a main-checkout root/subdir (".git",
    # "../.git") and only absolute from some worktree layouts - anchor a relative
    # result on `cwd` (the directory git actually ran in), never on this process's
    # own os.getcwd(), which can differ once a caller passes an explicit `cwd`.
    if not os.path.isabs(common):
        common = os.path.join(cwd or os.getcwd(), common)
    return _hash12(os.path.realpath(common))


def _wt_key(cwd: str | None = None) -> str | None:
    top = _git(["rev-parse", "--show-toplevel"], cwd=cwd)
    if top is None:
        return _nongit_key(cwd)
    # --show-toplevel is documented-absolute, but anchor defensively for the
    # same reason as _repo_key above - keeps both helpers symmetric.
    if not os.path.isabs(top):
        top = os.path.join(cwd or os.getcwd(), top)
    return _hash12(os.path.realpath(top))


def _no_marker_message(var: str) -> str:
    return (
        "not inside a git repo and no project marker (__manifest__.py or "
        f".odoo-ai-root) found walking up from {os.getcwd()}. "
        f"Set ${var} to an explicit absolute path."
    )


# --------------------------------------------------------------------------- #
# public API
# --------------------------------------------------------------------------- #
def share_dir(root: str | None = None) -> str:
    """Return the absolute SHARE dir, creating it first. Honors an explicit
    $ODOO_AI_PROJECT_DIR override verbatim (still created, never re-hashed).

    `root` (optional): resolve as if the cwd were this directory. None = cwd,
    byte-identical to the pre-`root` behavior. Mirrors the shell's
    `resolve_project_dir.sh --root <abs-path> share`."""
    override = os.environ.get("ODOO_AI_PROJECT_DIR")
    if override:
        # Strip ALL trailing "/" (a doubled/tripled trailing slash denotes the
        # SAME directory as a single one - POSIX: "/a/b//" == "/a/b/" ==
        # "/a/b" - so the state-dir key must canonicalize all of them
        # identically); an all-slashes input (e.g. "/", "///") falls back to
        # "/". PARITY INVARIANT: resolve_project_dir.sh's
        # `_project_dir_rstrip_slashes` + `[ -n ] || override="/"` mirrors this
        # exactly - `${var%/}` alone strips only ONE and would diverge here.
        d = override.rstrip("/") or "/"
        os.makedirs(d, exist_ok=True)
        return d
    if root is not None and not os.path.isdir(root):
        raise ProjectDirError(f"resolve_project_dir: --root {root} is not a directory.")
    key = _repo_key(root)
    if key is None:
        raise ProjectDirError(_no_marker_message("ODOO_AI_PROJECT_DIR"))
    d = os.path.join(_home(), "projects", key)
    os.makedirs(d, exist_ok=True)
    return d


def isolate_dir(root: str | None = None) -> str:
    """Return the absolute ISOLATE dir, creating it first. Honors an explicit
    $ODOO_AI_WORKTREE_DIR override verbatim. When unset, resolves the SHARE dir
    first (so an $ODOO_AI_PROJECT_DIR override is respected for the SHARE half
    of the path too) and nests <SHARE>/worktrees/<wt-key>/ under it.

    `root` (optional): as in share_dir - forwarded to BOTH halves."""
    override = os.environ.get("ODOO_AI_WORKTREE_DIR")
    if override:
        # Same full-rstrip + all-slashes fallback as share_dir above (parity
        # invariant with resolve_project_dir.sh's `_project_dir_rstrip_slashes`).
        d = override.rstrip("/") or "/"
        os.makedirs(d, exist_ok=True)
        return d
    share = share_dir(root)
    key = _wt_key(root)
    if key is None:
        raise ProjectDirError(_no_marker_message("ODOO_AI_WORKTREE_DIR"))
    d = os.path.join(share, "worktrees", key)
    os.makedirs(d, exist_ok=True)
    return d


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _main(argv: list) -> int:
    root = None
    if argv[:1] == ["--root"]:
        if len(argv) < 2 or not argv[1]:
            print("paths.py: --root needs an absolute path", file=sys.stderr)
            return 2
        root, argv = argv[1], argv[2:]
    if len(argv) != 1 or argv[0] not in ("share", "isolate"):
        print("Usage: paths.py [--root <abs-path>] share|isolate", file=sys.stderr)
        return 2
    try:
        print(share_dir(root) if argv[0] == "share" else isolate_dir(root))
    except ProjectDirError as exc:
        print(f"paths.py: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
