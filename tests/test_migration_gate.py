"""Behavioural guard for scripts/lib/migration_gate.py - the version and migration rule gate.

Each test builds a base and a head addons tree with tiny modules and runs the gate as a
process, asserting on the KEY=VALUE output and the exit code.

Run with: python3 -m pytest tests/test_migration_gate.py -v
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GATE = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "lib" / "migration_gate.py"
SERIES = "99.0"


def module(tree, name, version, files=None):
    d = tree / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "__manifest__.py").write_text("{'name': '%s', 'version': '%s'}\n" % (name, version))
    for rel, content in (files or {}).items():
        p = d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)


def run(tmp_path, *extra):
    r = subprocess.run([sys.executable, str(GATE), "check", "--base", str(tmp_path / "base"),
                        "--head", str(tmp_path / "head"), "--series", SERIES, *extra],
                       capture_output=True, text=True)
    return r.returncode, r.stdout


def pair(tmp_path, base_version, head_version, head_files=None, base_files=None):
    module(tmp_path / "base", "m1", base_version, base_files)
    module(tmp_path / "head", "m1", head_version, head_files)


POST = {"migrations/99.0.1.0.4/post-migrate.py": "def migrate(cr, v):\n    pass\n"}


def test_clean_pr_passes(tmp_path):
    pair(tmp_path, "1.0.3", "1.0.4", POST)
    rc, out = run(tmp_path)
    assert rc == 0 and "MIGRATION_GATE=PASS" in out
    assert "BUMP=smallest" in out and "MIGRATION_DIRS_NEW=99.0.1.0.4" in out


def test_bump_of_two_fails(tmp_path):
    pair(tmp_path, "1.0.3", "1.0.5", {"migrations/99.0.1.0.5/post-migrate.py": "x = 1\n"})
    rc, out = run(tmp_path)
    assert rc == 1 and "BUMP=other" in out
    assert "FAIL_REASON=m1: version 1.0.3 -> 1.0.5 is not the smallest step" in out


def test_migration_without_bump_fails(tmp_path):
    pair(tmp_path, "1.0.3", "1.0.3", {"migrations/99.0.1.0.3/post-migrate.py": "x = 1\n"})
    rc, out = run(tmp_path)
    assert rc == 1 and "without a version bump" in out


def test_two_new_migration_folders_fail(tmp_path):
    files = dict(POST)
    files["migrations/99.0.1.0.3/post-migrate.py"] = "x = 1\n"
    pair(tmp_path, "1.0.3", "1.0.4", files)
    rc, out = run(tmp_path)
    assert rc == 1 and "2 new migration folders" in out


def test_short_folder_name_fails_unless_allowed(tmp_path):
    pair(tmp_path, "1.0.3", "1.0.4", {"migrations/1.0.4/post-migrate.py": "x = 1\n"})
    rc, out = run(tmp_path)
    assert rc == 1 and "uses the short form" in out
    rc, out = run(tmp_path, "--allow-short", "m1")
    assert rc == 0 and "MIGRATION_GATE=PASS" in out


def test_folder_for_another_version_fails(tmp_path):
    pair(tmp_path, "1.0.3", "1.0.4", {"migrations/99.0.1.0.9/post-migrate.py": "x = 1\n"})
    rc, out = run(tmp_path)
    assert rc == 1 and "does not match the bumped version" in out


def test_business_topic_file_fails(tmp_path):
    files = dict(POST)
    files["migrations/99.0.1.0.4/migrate_partner_tags.py"] = "x = 1\n"
    pair(tmp_path, "1.0.3", "1.0.4", files)
    rc, out = run(tmp_path)
    assert rc == 1 and "migrate_partner_tags.py" in out


def test_second_post_script_fails(tmp_path):
    files = dict(POST)
    files["migrations/99.0.1.0.4/post-migrate-2.py"] = "x = 1\n"
    pair(tmp_path, "1.0.3", "1.0.4", files)
    rc, out = run(tmp_path)
    assert rc == 1 and "post-migrate-2.py" in out


def test_modified_existing_migration_folder_fails(tmp_path):
    old = {"migrations/99.0.1.0.3/post-migrate.py": "x = 1\n"}
    head = dict(POST)
    head["migrations/99.0.1.0.3/post-migrate.py"] = "x = 2\n"
    pair(tmp_path, "1.0.3", "1.0.4", head, base_files=old)
    rc, out = run(tmp_path)
    assert rc == 1 and "existing migration folder 99.0.1.0.3 is modified" in out


def test_bump_without_migration_warns_and_passes(tmp_path):
    pair(tmp_path, "1.0.3", "1.0.4", {"models.py": "x = 1\n"})
    rc, out = run(tmp_path)
    assert rc == 0 and "MIGRATION_GATE=PASS" in out
    assert "WARN=m1: version bumped without a migration folder" in out


def test_new_module_migrations_fail_and_plain_new_module_passes(tmp_path):
    (tmp_path / "base").mkdir()
    module(tmp_path / "head", "fresh", "1.0.0", {"models.py": "x = 1\n"})
    rc, out = run(tmp_path)
    assert rc == 0 and "MIGRATION_GATE=PASS" in out
    module(tmp_path / "head", "fresh", "1.0.0",
           {"migrations/99.0.1.0.0/post-migrate.py": "x = 1\n"})
    rc, out = run(tmp_path)
    assert rc == 1 and "a new module ships a migrations/ folder" in out


def test_series_prefixed_version_warns(tmp_path):
    pair(tmp_path, "99.0.1.0.3", "99.0.1.0.4", POST)
    rc, out = run(tmp_path)
    assert rc == 0 and "WARN=m1: version carries the series prefix" in out
    assert "BUMP=smallest" in out


def test_modules_option_restricts_scope(tmp_path):
    pair(tmp_path, "1.0.3", "1.0.5", {"migrations/99.0.1.0.5/post-migrate.py": "x = 1\n"})
    module(tmp_path / "base", "m2", "1.0.0")
    module(tmp_path / "head", "m2", "1.0.0", {"models.py": "x = 1\n"})
    rc, out = run(tmp_path, "--modules", "m2")
    assert rc == 0 and "MODULE=m2" in out and "MODULE=m1" not in out
    rc, out = run(tmp_path)
    assert rc == 1 and "MODULE=m1" in out


def test_help_prints_the_full_docstring():
    r = subprocess.run([sys.executable, str(GATE), "--help"], capture_output=True, text=True)
    assert r.returncode == 0
    assert "Rules (within one pull request" in r.stdout


def test_two_part_version_bumps_only_to_dot_one_with_matching_folder(tmp_path):
    pair(tmp_path, "0.3", "0.3.1", {"migrations/99.0.0.3.1/post-migrate.py": "x = 1\n"})
    rc, out = run(tmp_path)
    assert rc == 0 and "MIGRATION_GATE=PASS" in out
    assert "BUMP=smallest" in out and "MIGRATION_DIRS_NEW=99.0.0.3.1" in out


def test_two_part_bump_without_migration_folder_warns_and_passes(tmp_path):
    pair(tmp_path, "0.3", "0.3.1", {"models.py": "x = 1\n"})
    rc, out = run(tmp_path)
    assert rc == 0 and "MIGRATION_GATE=PASS" in out and "BUMP=smallest" in out
    assert "WARN=m1: version bumped without a migration folder" in out


def test_two_part_minor_step_fails_naming_the_expected_dot_one(tmp_path):
    pair(tmp_path, "0.3", "0.4", {"models.py": "x = 1\n"})
    rc, out = run(tmp_path)
    assert rc == 1 and "BUMP=other" in out and "MIGRATION_GATE=FAIL" in out
    assert "is not the smallest step; expected 0.3.1" in out


def test_three_part_patch_step_is_the_smallest_bump(tmp_path):
    pair(tmp_path, "1.2.3", "1.2.4", {"models.py": "x = 1\n"})
    rc, out = run(tmp_path)
    assert rc == 0 and "BUMP=smallest" in out


def test_two_part_to_dot_zero_or_dot_two_fails(tmp_path):
    for head in ("0.3.0", "0.3.2"):
        pair(tmp_path, "0.3", head, {"models.py": "x = 1\n"})
        rc, out = run(tmp_path)
        assert rc == 1 and "BUMP=other" in out, head
        assert "expected 0.3.1" in out, head


def test_any_other_change_of_length_fails(tmp_path):
    for base, head in (("1.0.3", "1.0"), ("0.3", "0.3.1.1")):
        pair(tmp_path, base, head, {"models.py": "x = 1\n"})
        rc, out = run(tmp_path)
        assert rc == 1 and "BUMP=other" in out, (base, head)
