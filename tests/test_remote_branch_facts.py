"""`scripts/lib/remote_branch_facts.py` - a series branch is confirmed on the remote before a clone
is proposed; a local bare repository stands in for the remote."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "lib" / "remote_branch_facts.py"
sys.path.insert(0, str(TOOL.parent))
import remote_branch_facts as rbf  # noqa: E402


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True,
                   env={"PATH": __import__("os").environ["PATH"], "HOME": str(cwd), "GIT_AUTHOR_NAME": "t",
                        "GIT_AUTHOR_EMAIL": "t@example.com", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"})


def test_present_and_absent_branches_are_told_apart_and_an_unreachable_remote_is_exit_2(tmp_path):
    bare = tmp_path / "remote.git"; bare.mkdir()
    _git(bare, "init", "--bare", "-b", "17.0")
    work = tmp_path / "work"; work.mkdir()
    _git(work, "init", "-b", "17.0"); (work / "f").write_text("x"); _git(work, "add", "f"); _git(work, "commit", "-m", "one")
    _git(work, "remote", "add", "origin", str(bare)); _git(work, "push", "origin", "17.0"); _git(work, "push", "origin", "17.0:18.0")
    proc = subprocess.run([sys.executable, str(TOOL), str(bare), "17.0", "18.0", "19.0"], capture_output=True, text=True)
    assert proc.returncode == 1
    assert "BRANCH_17.0=present" in proc.stdout and "BRANCH_18.0=present" in proc.stdout and "BRANCH_19.0=absent" in proc.stdout
    ok = subprocess.run([sys.executable, str(TOOL), str(bare), "17.0", "--json"], capture_output=True, text=True)
    assert ok.returncode == 0 and '"17.0": "present"' in ok.stdout
    gone = subprocess.run([sys.executable, str(TOOL), str(tmp_path / "nowhere.git"), "17.0", "--timeout", "5"], capture_output=True, text=True)
    assert gone.returncode == 2 and "REACHABLE=0" in gone.stdout


def test_credentials_never_appear_in_the_printed_remote():
    assert rbf.strip_credentials("https://user:s3cret@example.org/acme/repo.git") == "https://example.org/acme/repo.git"
    assert rbf.strip_credentials("git@github.com:acme/repo.git") == "git@github.com:acme/repo.git"


def test_an_option_like_or_command_transport_url_is_never_passed_to_git():
    assert rbf.remote_heads("--upload-pack=touch /tmp/pwned", timeout=5) is None
    assert rbf.remote_heads("ext::sh -c touch% /tmp/pwned", timeout=5) is None
