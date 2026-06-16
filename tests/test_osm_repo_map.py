"""Tests for plugins/odoo-ai-agents/scripts/lib/osm_repo_map.py.

All tests are CPU-only: no network, no I/O, no external dependencies.
"""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Module loading (mirror the pattern used in test_setup_instances.py)
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "lib"
OSM_REPO_MAP = LIB / "osm_repo_map.py"


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


osm = _load_module("osm_repo_map", OSM_REPO_MAP)


# ---------------------------------------------------------------------------
# normalize_remote
# ---------------------------------------------------------------------------

class TestNormalizeRemote:
    """normalize_remote unifies SSH and HTTPS URL forms to one canonical key."""

    CANONICAL = "github.com/acme/widget"

    ALL_FORMS = [
        "git@github.com:acme/widget.git",          # SCP SSH
        "ssh://git@github.com/acme/widget.git",    # SSH URL
        "https://github.com/acme/widget.git",      # HTTPS + .git
        "https://github.com/acme/widget",           # HTTPS no .git
        "https://github.com/acme/widget/",          # HTTPS trailing slash
    ]

    def test_osm_repo_map_normalizes_ssh_and_https_to_same_key(self):
        """All 5 URL forms must produce the identical canonical key."""
        for url in self.ALL_FORMS:
            result = osm.normalize_remote(url)
            assert result == self.CANONICAL, (
                f"normalize_remote({url!r}) returned {result!r}; "
                f"expected {self.CANONICAL!r}"
            )

    def test_normalize_remote_returns_none_for_unparseable_input(self):
        """An unparseable string must return None, not raise."""
        bad_inputs = [
            "",
            "not-a-url",
            "://missing-scheme",
            "just-a-word",
        ]
        for bad in bad_inputs:
            result = osm.normalize_remote(bad)
            assert result is None, (
                f"normalize_remote({bad!r}) returned {result!r}; expected None"
            )

    def test_normalize_remote_lowercases_host(self):
        """Host part must be lowercased in the returned key."""
        result = osm.normalize_remote("https://GitHub.COM/acme/widget")
        assert result is not None
        assert result.startswith("github.com/"), (
            f"Expected lowercase host; got {result!r}"
        )

    def test_normalize_remote_preserves_org_repo_case(self):
        """Org and repo case must be preserved."""
        result = osm.normalize_remote("https://github.com/Acme/Widget")
        assert result == "github.com/Acme/Widget"

    def test_normalize_remote_strips_trailing_git(self):
        """A trailing .git suffix must be removed."""
        with_git = osm.normalize_remote("https://github.com/acme/widget.git")
        without_git = osm.normalize_remote("https://github.com/acme/widget")
        assert with_git == without_git


# ---------------------------------------------------------------------------
# default_target_dir + build_clone_command
# ---------------------------------------------------------------------------

class TestBuildSshCloneCommand:
    """build_clone_command emits SSH argv with -b and --no-single-branch."""

    def test_osm_repo_map_builds_ssh_clone_command(self):
        """argv must contain -b, the branch, --no-single-branch, ssh_url, target_dir in order."""
        ssh_url = "git@github.com:acme/widget.git"
        branch = "17.0"
        target_dir = "widget"

        argv = osm.build_clone_command(ssh_url, branch, target_dir)

        assert argv[0] == "git"
        assert "-b" in argv
        b_idx = argv.index("-b")
        assert argv[b_idx + 1] == branch, "branch must follow -b"
        assert "--no-single-branch" in argv
        assert ssh_url in argv
        assert target_dir in argv
        # Order: git clone -b <branch> --no-single-branch <ssh_url> <target_dir>
        assert argv == ["git", "clone", "-b", branch, "--no-single-branch", ssh_url, target_dir]

    def test_default_target_dir_odoo_uses_major_version(self):
        """default_target_dir('odoo', '17.0') must return 'odoo17'."""
        assert osm.default_target_dir("odoo", "17.0") == "odoo17"

    def test_default_target_dir_other_repo_returns_verbatim(self):
        """default_target_dir for any repo other than 'odoo' returns the repo name unchanged."""
        assert osm.default_target_dir("widget", "17.0") == "widget"
        assert osm.default_target_dir("enterprise", "17.0") == "enterprise"
        assert osm.default_target_dir("my-addon", "16.0") == "my-addon"

    def test_default_target_dir_odoo_various_branches(self):
        """Major version extraction works for various branch formats."""
        assert osm.default_target_dir("odoo", "16.0") == "odoo16"
        assert osm.default_target_dir("odoo", "18.0") == "odoo18"


# ---------------------------------------------------------------------------
# CLI (__main__)
# ---------------------------------------------------------------------------

class TestCli:
    """CLI subcommands emit correct output and exit codes."""

    def _run(self, *args):
        return subprocess.run(
            [sys.executable, str(OSM_REPO_MAP), *args],
            capture_output=True,
            text=True,
        )

    def test_cli_normalize_prints_canonical_key(self):
        """normalize subcommand prints the canonical key for a valid URL."""
        result = self._run("normalize", "git@github.com:acme/widget.git")
        assert result.returncode == 0
        assert result.stdout.strip() == "github.com/acme/widget"

    def test_cli_normalize_exits_1_for_bad_url(self):
        """normalize subcommand exits with code 1 for an unparseable URL."""
        result = self._run("normalize", "not-a-url")
        assert result.returncode == 1

    def test_cli_target_dir_odoo(self):
        """target-dir subcommand returns odoo<major> for the odoo repo."""
        result = self._run("target-dir", "odoo", "17.0")
        assert result.returncode == 0
        assert result.stdout.strip() == "odoo17"

    def test_cli_clone_cmd_contains_no_single_branch(self):
        """clone-cmd subcommand emits a shell-quoted git clone with --no-single-branch."""
        result = self._run(
            "clone-cmd",
            "git@github.com:acme/widget.git",
            "17.0",
            "widget",
        )
        assert result.returncode == 0
        cmd = result.stdout.strip()
        assert "--no-single-branch" in cmd
        assert "-b" in cmd
        assert "17.0" in cmd
        assert "widget" in cmd
