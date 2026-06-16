"""osm_repo_map.py - Pure-Python helpers for mapping git remotes to clone targets.

All functions are pure (no side effects, no I/O) so they are trivially testable.
Requires Python 3.9+ stdlib only.
"""

from __future__ import annotations

import shlex
import sys
from urllib.parse import urlparse


def normalize_remote(url: str) -> str | None:
    """Normalize any git remote URL to a canonical match key ``host/Org/repo``.

    Handled forms:
      - SCP-style SSH:  ``git@github.com:acme/widget.git``
      - SSH URL:        ``ssh://git@github.com/acme/widget.git``
      - HTTPS URL:      ``https://github.com/acme/widget.git``
      - HTTPS no .git:  ``https://github.com/acme/widget``
      - HTTPS trailing slash: ``https://github.com/acme/widget/``

    The returned key has a *lowercase* host but preserves Org/repo case and
    strips a trailing ``.git``.  Returns ``None`` for unparseable input.
    """
    if not url or not isinstance(url, str):
        return None

    url = url.strip()

    # --- SCP-style: git@host:Org/repo[.git] ---
    # Detect by the presence of ':' before any '/'
    colon_pos = url.find(":")
    slash_pos = url.find("/")
    if colon_pos != -1 and (slash_pos == -1 or colon_pos < slash_pos):
        # Could be SCP-style (no scheme) or a Windows path - guard against
        # scheme-like prefixes (e.g. "ssh://", "https://")
        if "://" not in url[:colon_pos + 3]:
            # SCP form: [user@]host:path
            host_part, _, path_part = url.partition(":")
            # Strip optional user
            host = host_part.split("@")[-1].lower()
            path_part = path_part.rstrip("/")
            if path_part.endswith(".git"):
                path_part = path_part[:-4]
            if "/" not in path_part:
                return None
            return f"{host}/{path_part}"

    # --- URL-style (ssh://, https://, git://, ...) ---
    try:
        parsed = urlparse(url)
    except Exception:
        return None

    if not parsed.scheme or not parsed.netloc:
        return None

    host = parsed.hostname
    if not host:
        return None
    host = host.lower()

    path = parsed.path.rstrip("/")
    if path.endswith(".git"):
        path = path[:-4]
    # Remove leading slash
    path = path.lstrip("/")

    if not path or "/" not in path:
        return None

    return f"{host}/{path}"


def default_target_dir(repo: str, branch: str) -> str:
    """Return the conventional local directory name for a cloned repo.

    For the repo named ``odoo`` the directory is ``odoo<major>`` where
    *major* is the integer part before the first ``.`` in *branch*
    (e.g. branch ``17.0`` -> major ``17`` -> ``odoo17``).

    For any other repo the repo name is returned verbatim.
    """
    if repo == "odoo":
        major = branch.split(".")[0]
        return f"odoo{major}"
    return repo


def build_clone_command(ssh_url: str, branch: str, target_dir: str) -> list[str]:
    """Return the argv list for ``git clone -b <branch> --no-single-branch <ssh_url> <target_dir>``.

    The caller is responsible for computing *target_dir* (use
    :func:`default_target_dir` for the conventional default).
    """
    return ["git", "clone", "-b", branch, "--no-single-branch", ssh_url, target_dir]


# ---------------------------------------------------------------------------
# __main__ CLI
# ---------------------------------------------------------------------------

def _usage() -> None:
    print(
        "Usage:\n"
        "  osm_repo_map.py normalize <url>\n"
        "  osm_repo_map.py target-dir <repo> <branch>\n"
        "  osm_repo_map.py clone-cmd <ssh_url> <branch> <target_dir>",
        file=sys.stderr,
    )


def main(argv: list[str] | None = None) -> int:
    args = (argv if argv is not None else sys.argv)[1:]
    if not args:
        _usage()
        return 2

    cmd = args[0]

    if cmd == "normalize":
        if len(args) != 2:
            _usage()
            return 2
        key = normalize_remote(args[1])
        if key is None:
            print("error: unparseable remote URL", file=sys.stderr)
            return 1
        print(key)
        return 0

    if cmd == "target-dir":
        if len(args) != 3:
            _usage()
            return 2
        print(default_target_dir(args[1], args[2]))
        return 0

    if cmd == "clone-cmd":
        if len(args) != 4:
            _usage()
            return 2
        argv_list = build_clone_command(args[1], args[2], args[3])
        print(shlex.join(argv_list))
        return 0

    print(f"error: unknown command {cmd!r}", file=sys.stderr)
    _usage()
    return 2


if __name__ == "__main__":
    sys.exit(main())
