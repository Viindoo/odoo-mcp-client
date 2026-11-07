"""Setup step 40 writes its `.gitignore` only at the top of a git work tree, and step 05 narrows
its per-instance checks with --version / --profile. Throwaway state root, no network."""
from __future__ import annotations

import json
import os
import subprocess
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STEPS = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "setup-steps"


def _env(tmp_path, **extra):
    env = {k: v for k, v in os.environ.items() if not k.startswith("ODOO_AI_")}
    env.update({"HOME": str(tmp_path / "home"), "ODOO_AI_HOME": str(tmp_path / "state"),
                "ODOO_AI_INSTANCES": str(tmp_path / "instances.toml"), "ODOO_GIT_BASE": str(tmp_path / "git")})
    env.update(extra)
    return env


def _apply40(tmp_path, cwd):
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps([{"series": "17.0", "addons_path": ["/abs/core"], "http_port": 8139,
                                 "db_name": "odoo_17_0", "db_host": "localhost", "db_user": "odoo", "python": ""}]),
                    encoding="utf-8")
    return subprocess.run(["bash", str(STEPS / "40-instance-profile.sh"), "apply"], capture_output=True, text=True,
                          env=_env(tmp_path, ODOO_AI_PROFILE_SPEC=str(spec)), cwd=str(cwd), timeout=120)


def test_gitignore_is_written_at_the_work_tree_top_from_a_subdirectory(tmp_path):
    repo = tmp_path / "repo"; (repo / "sub" / "deep").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    proc = _apply40(tmp_path, repo / "sub" / "deep")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert (repo / ".gitignore").read_text() == ".odoo-ai/\n"
    assert not (repo / "sub" / "deep" / ".gitignore").exists()


def test_no_gitignore_is_written_outside_a_git_work_tree(tmp_path):
    plain = tmp_path / "plain"; plain.mkdir()
    proc = _apply40(tmp_path, plain)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert not (plain / ".gitignore").exists()


def _catalog(tmp_path):
    (tmp_path / "instances.toml").write_text(textwrap.dedent('''\
        [[instance]]
        series = "17.0"
        profile = "a"
        run_mode = "source"
        addons_path = ["/nonexistent/addons"]

        [[instance]]
        series = "17.0"
        profile = "b"
        run_mode = "source"
        addons_path = ["/nonexistent/addons"]

        [[instance]]
        series = "18.0"
        run_mode = "source"
        addons_path = ["/nonexistent/addons"]
        '''), encoding="utf-8")


def _prereq(tmp_path, *args):
    return subprocess.run(["bash", str(STEPS / "05-prereq-check.sh"), "apply", *args], capture_output=True, text=True,
                          env=_env(tmp_path, SETUP_FILTER="instance"), timeout=180)


def test_prereq_apply_checks_only_the_matching_rows_and_names_the_others_in_one_line(tmp_path):
    (tmp_path / "git").mkdir(); (tmp_path / "home").mkdir(); _catalog(tmp_path)
    out = _prereq(tmp_path, "--version", "17.0", "--profile", "a")
    text = out.stdout + out.stderr
    assert "venv for series 17.0" in text and "venv for series 18.0" not in text
    assert "for 17.0:a" in text and "for 17.0:b" not in text and "for 18.0" not in text
    skip = [l for l in text.splitlines() if "not checked" in l]
    assert len(skip) == 2                      # one line from the venv gate, one from the database report
    assert all("17.0:b" in l and "18.0" in l and l.count("other declared instance(s)") == 1 and " 2 other" in l for l in skip)


def test_prereq_without_flags_checks_every_row_and_prints_no_left_out_line(tmp_path):
    (tmp_path / "git").mkdir(); (tmp_path / "home").mkdir(); _catalog(tmp_path)
    out = _prereq(tmp_path)
    text = out.stdout + out.stderr
    assert "venv for series 17.0" in text and "venv for series 18.0" in text and "not checked" not in text

