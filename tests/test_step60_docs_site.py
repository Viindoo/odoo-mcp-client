"""Behaviour tests for `scripts/setup-steps/60-docs-site.sh`.

The step manages the machine-global, never-committed `docs-sites.toml` (state root, next to
instances.toml): one `[[site]]` row per product documentation repository, read by the
odoo-doc-site skill. `propose` derives what the repository states about itself and never fills the
policy; `record` writes only an operator-confirmed row and only a valid one.

Everything runs on throwaway state: a tmp state root (ODOO_AI_HOME), a tmp catalog
(ODOO_AI_INSTANCES) and a tmp git repository shaped like a docs repo. No network, no real config.
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
STEP = PLUGIN / "scripts" / "setup-steps" / "60-docs-site.sh"
GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}


def _sh(cwd, *args):
    subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True,
                   env={**os.environ, **GIT_ENV})


def _facts(stdout):
    out = {}
    for line in stdout.splitlines():
        name, _, value = line.partition("=")
        parts = shlex.split(value)
        out[name] = parts[0] if parts else ""
    return out


@pytest.fixture()
def machine(tmp_path):
    """A docs repo on branch 17.0 (origin acme, a fork the user pushed to, origin tracking refs for
    17.0 and 18.0, Makefile languages), a sibling clone of the same repo on 18.0, an unrelated
    sibling, and a catalog declaring a 17.0 and a profiled 18.0 instance."""
    work = tmp_path / "work"
    docs = work / "documentation"
    docs.mkdir(parents=True)
    _sh(docs, "git", "init", "-q", "-b", "17.0")
    (docs / "Makefile").write_text("LANGUAGES ?= en vi\n", encoding="utf-8")
    (docs / "conf.py").write_text("project = 'Docs'\n", encoding="utf-8")
    _sh(docs, "git", "add", ".")
    _sh(docs, "git", "commit", "-q", "-m", "init")
    _sh(docs, "git", "remote", "add", "origin", "https://token123@example.org/acme/documentation.git")
    _sh(docs, "git", "remote", "add", "fork", "https://example.org/alice/documentation.git")
    _sh(docs, "git", "remote", "add", "upstream", "https://example.org/other/documentation.git")
    bare = tmp_path / "alice-bare.git"
    _sh(tmp_path, "git", "init", "-q", "--bare", str(bare))
    _sh(docs, "git", "config", "remote.fork.pushurl", str(bare))
    _sh(docs, "git", "push", "-q", "fork", "HEAD:refs/heads/feat-x")
    _sh(docs, "git", "update-ref", "refs/remotes/origin/17.0", "HEAD")
    _sh(docs, "git", "update-ref", "refs/remotes/origin/18.0", "HEAD")
    _sh(docs, "git", "update-ref", "refs/remotes/origin/feature-x", "HEAD")

    sibling = work / "documentation-18"
    sibling.mkdir()
    _sh(sibling, "git", "init", "-q", "-b", "18.0")
    _sh(sibling, "git", "remote", "add", "origin", "git@example.org:acme/documentation.git")
    stranger = work / "other-project"
    stranger.mkdir()
    _sh(stranger, "git", "init", "-q", "-b", "18.0")
    _sh(stranger, "git", "remote", "add", "origin", "https://example.org/acme/something-else.git")

    home = tmp_path / "odoo-ai"
    home.mkdir()
    catalog = home / "instances.toml"
    catalog.write_text(
        '[[instance]]\nseries = "17.0"\naddons_path = ["/x"]\n\n'
        '[[instance]]\nseries = "18.0"\nprofile = "minimal"\naddons_path = ["/y"]\n',
        encoding="utf-8")
    return {"docs": docs, "sibling": sibling, "home": home, "catalog": catalog,
            "sites": home / "docs-sites.toml", "tmp": tmp_path}


def _run(machine, *args):
    env = {**os.environ, "ODOO_AI_HOME": str(machine["home"]),
           "ODOO_AI_INSTANCES": str(machine["catalog"]), "TEST_BACKUP_TS": "1700000000"}
    env.pop("CLAUDE_PLUGIN_ROOT", None)
    return subprocess.run([str(STEP), *args], capture_output=True, text=True, env=env, timeout=120)


def _row(machine, **overrides):
    """A complete, valid row for the fixture machine."""
    row = {
        "key": "docs", "remote": "https://example.org/acme/documentation.git", "fork_remote": "fork",
        "languages": ["en", "vi"], "audience": "business users of the product",
        "series": {
            "17.0": {"clone": str(machine["docs"]), "instance": "17.0", "extra_modules": ["theme_x"],
                     "module_bridge_patterns": ["bridge_{module}"]},
            "18.0": {"instance": "18.0:minimal"},
        },
        "policy": {
            "banned_terms": ["Foo"], "banned_terms_exempt_paths": ["content/developer/**"],
            "forbid_version_prose": True, "marketplace_url": "https://apps.example.org/{series}/{module}",
            "site_url_prefix": "https://docs.example.org/documentation/",
            "demo_company": {"en": "Acme Ltd", "vi": "Cong ty Acme"},
            "commit": "one-per-pr", "check_shot": "first-per-series", "semantic_classes": ["note"],
        },
    }
    row.update(overrides)
    return row


def _record(machine, row, key=None):
    f = machine["tmp"] / "row.json"
    f.write_text(json.dumps(row), encoding="utf-8")
    return _run(machine, "record", "--key", key or row["key"], "--from-json", str(f))


# ---------------------------------------------------------------- check

def test_check_fails_with_a_one_line_remedy_when_no_site_is_declared(machine):
    res = _run(machine, "check")
    assert res.returncode != 0
    assert not machine["sites"].exists()
    assert len(res.stderr.strip().splitlines()) == 1
    assert "odoo-setup docs-site" in res.stderr


def test_check_passes_once_a_complete_row_is_recorded(machine):
    assert _record(machine, _row(machine)).returncode == 0
    res = _run(machine, "check")
    assert res.returncode == 0, res.stdout + res.stderr


def test_check_names_what_an_incomplete_row_still_lacks(machine):
    row = _row(machine)
    del row["audience"]
    del row["policy"]["check_shot"]
    machine["sites"].write_text(
        '[[site]]\nkey = "docs"\nremote = "https://example.org/acme/documentation.git"\n'
        'fork_remote = "fork"\nlanguages = ["en"]\n[site.series."17.0"]\ninstance = "17.0"\n'
        '[site.policy]\nbanned_terms = []\nforbid_version_prose = false\ncommit = "per-area"\n',
        encoding="utf-8")
    res = _run(machine, "check")
    assert res.returncode != 0
    assert "audience" in res.stdout
    assert "check_shot" in res.stdout


def test_check_fails_when_the_capture_instance_left_the_catalog(machine):
    assert _record(machine, _row(machine)).returncode == 0
    machine["catalog"].write_text('[[instance]]\nseries = "17.0"\naddons_path = ["/x"]\n', encoding="utf-8")
    res = _run(machine, "check")
    assert res.returncode != 0
    assert "18.0:minimal" in res.stdout


def test_check_refuses_a_file_that_is_not_toml(machine):
    machine["sites"].write_text("[[site\nkey =\n", encoding="utf-8")
    res = _run(machine, "check")
    assert res.returncode == 2
    assert "docs-sites.toml" in res.stderr


# ---------------------------------------------------------------- propose

def test_propose_derives_the_repo_facts_and_asks_for_the_policy(machine):
    before = sorted(p.name for p in machine["home"].iterdir())
    res = _run(machine, "propose", "--repo", str(machine["docs"]))
    assert res.returncode == 0, res.stderr
    facts = _facts(res.stdout)
    assert facts["SITE_KEY"] == "documentation"
    assert facts["REMOTE"] == "https://example.org/acme/documentation.git"
    assert facts["SERIES"] == "17.0,18.0"
    assert facts["SERIES_BRANCHES_ON_ORIGIN"] == "17.0,18.0"
    assert facts["LANGUAGES"] == "en,vi"
    assert facts["SERIES_17_0_INSTANCES"] == "17.0"
    assert facts["SERIES_18_0_INSTANCES"] == "18.0:minimal"
    assert facts["SERIES_17_0_CLONES"] == str(machine["docs"].resolve())
    assert facts["SERIES_18_0_CLONES"] == str(machine["sibling"].resolve())
    to_confirm = facts["POLICY_FIELDS_TO_CONFIRM"].split(",")
    for field in ("audience", "repos", "banned_terms", "marketplace_url", "demo_company", "extra_modules"):
        assert field in to_confirm
    assert sorted(p.name for p in machine["home"].iterdir()) == before, "propose must write nothing"


def test_propose_offers_only_remotes_the_user_pushed_to_as_fork(machine):
    facts = _facts(_run(machine, "propose", "--repo", str(machine["docs"]), "--key", "mine").stdout)
    assert facts["SITE_KEY"] == "mine"
    assert facts["FORK_CANDIDATES"] == "fork"
    assert "upstream" in facts["OTHER_REMOTES"].split(",")


def test_propose_proposes_the_pushed_remote_as_fork_and_asks_nothing(machine):
    facts = _facts(_run(machine, "propose", "--repo", str(machine["docs"])).stdout)
    assert facts["FORK_STATUS"] == "fork-remote-pushed"
    assert facts["FORK_PUSHED_REMOTES"] == "fork=alice"
    assert "FORK_QUESTION" not in facts


def test_propose_asks_which_account_holds_the_fork_when_nothing_was_pushed(machine):
    _sh(machine["docs"], "git", "remote", "remove", "fork")
    res = _run(machine, "propose", "--repo", str(machine["docs"]))
    assert res.returncode == 0, res.stderr
    facts = _facts(res.stdout)
    assert facts["FORK_STATUS"] == "fork-remote-unpushed"
    assert facts["FORK_CANDIDATES"] == ""
    assert "acme/documentation" in facts["FORK_QUESTION"]
    assert "token123" not in res.stdout


def test_propose_offers_a_fork_owner_known_from_another_clone_of_the_catalog(machine):
    """The docs repo has no pushed fork; another clone in the catalog does (alice)."""
    other = machine["tmp"] / "work" / "addons"
    (other / "addons").mkdir(parents=True)
    _sh(other, "git", "init", "-q", "-b", "17.0")
    _sh(other, "git", "commit", "-q", "--allow-empty", "-m", "init")
    _sh(other, "git", "remote", "add", "origin", "https://example.org/acme/addons.git")
    _sh(other, "git", "remote", "add", "fork", "https://example.org/alice/addons.git")
    bare = machine["tmp"] / "alice-addons-bare.git"
    _sh(machine["tmp"], "git", "init", "-q", "--bare", str(bare))
    _sh(other, "git", "config", "remote.fork.pushurl", str(bare))
    _sh(other, "git", "push", "-q", "fork", "HEAD:refs/heads/feat-x")
    machine["catalog"].write_text(
        '[[instance]]\nseries = "17.0"\naddons_path = ["%s"]\n' % (other / "addons"), encoding="utf-8")
    _sh(machine["docs"], "git", "remote", "remove", "fork")
    facts = _facts(_run(machine, "propose", "--repo", str(machine["docs"])).stdout)
    assert facts["FORK_STATUS"] == "fork-remote-unpushed"
    assert facts["FORK_KNOWN_OWNERS"] == "alice"
    assert "acme/documentation" in facts["FORK_QUESTION"]


def test_propose_never_prints_a_credential_from_a_remote_url(machine):
    res = _run(machine, "propose", "--repo", str(machine["docs"]))
    assert "token123" not in res.stdout


def test_propose_refuses_a_directory_that_is_not_a_clone(machine):
    res = _run(machine, "propose", "--repo", str(machine["tmp"] / "nowhere"))
    assert res.returncode != 0
    assert "not inside a git clone" in res.stderr


# ---------------------------------------------------------------- record

def test_record_refuses_an_instance_the_catalog_does_not_declare(machine):
    row = _row(machine)
    row["series"]["17.0"]["instance"] = "17.0:ghost"
    res = _record(machine, row)
    assert res.returncode != 0
    assert "Traceback" not in res.stderr
    assert "17.0:ghost" in res.stderr and "not declared in the instance catalog" in res.stderr
    assert not machine["sites"].exists()


def test_record_refuses_an_instance_of_another_series(machine):
    row = _row(machine)
    row["series"]["17.0"]["instance"] = "18.0:minimal"
    res = _record(machine, row)
    assert res.returncode != 0
    assert not machine["sites"].exists()


@pytest.mark.parametrize("url", [
    "https://apps.example.org/{series}/modules",
    "https://apps.example.org/17.0/{module}",
    "https://apps.example.org/{series}/{module}/{other}",
    "apps.example.org/{series}/{module}",
])
def test_record_refuses_a_marketplace_pattern_that_cannot_be_filled(machine, url):
    row = _row(machine)
    row["policy"]["marketplace_url"] = url
    res = _record(machine, row)
    assert res.returncode != 0
    assert "marketplace_url" in res.stderr
    assert not machine["sites"].exists()


@pytest.mark.parametrize("where", ["site", "series", "policy"])
def test_record_refuses_an_unknown_key(machine, where):
    row = _row(machine)
    target = {"site": row, "series": row["series"]["17.0"], "policy": row["policy"]}[where]
    target["surprise"] = "x"
    res = _record(machine, row)
    assert res.returncode != 0
    assert "surprise" in res.stderr
    assert not machine["sites"].exists()


def test_record_refuses_a_remote_that_carries_a_password(machine):
    row = _row(machine, remote="https://alice:s3cret@example.org/acme/documentation.git")
    res = _record(machine, row)
    assert res.returncode != 0
    assert not machine["sites"].exists()


def test_record_refuses_a_row_whose_key_differs_from_the_requested_key(machine):
    res = _record(machine, _row(machine), key="other")
    assert res.returncode != 0
    assert not machine["sites"].exists()


def test_record_adds_a_row_without_touching_another_row_or_a_comment(machine):
    first = (
        "# machine notes - keep me\n"
        '[[site]]\nkey = "older"\nremote = "https://example.org/x/y.git"\nfork_remote = "me"\n'
        'languages = ["en"]  # inline comment\naudience = "a"\n'
        '[site.series."17.0"]\nclone = "%s"\ninstance = "17.0"\n' % machine["docs"] +
        "[site.policy]\nbanned_terms = []\nforbid_version_prose = false\n"
        'commit = "per-area"\ncheck_shot = "always"\n'
        "\n# trailing note\n")
    machine["sites"].write_text(first, encoding="utf-8")
    assert _record(machine, _row(machine)).returncode == 0
    text = machine["sites"].read_text(encoding="utf-8")
    assert text.startswith(first.rstrip("\n")), "the existing text must stay byte for byte"
    assert "# machine notes - keep me" in text and "# trailing note" in text and "# inline comment" in text
    parsed = tomllib.loads(text)
    assert [r["key"] for r in parsed["site"]] == ["older", "docs"]
    assert _run(machine, "check").returncode == 0


def test_record_replaces_the_row_of_the_same_key_and_leaves_the_others(machine):
    assert _record(machine, _row(machine)).returncode == 0
    assert _record(machine, _row(machine, key="second", audience="partners")).returncode == 0
    before = tomllib.loads(machine["sites"].read_text(encoding="utf-8"))["site"]
    changed = _row(machine, audience="everyone")
    assert _record(machine, changed).returncode == 0
    after = tomllib.loads(machine["sites"].read_text(encoding="utf-8"))["site"]
    assert [r["key"] for r in after] == ["docs", "second"]
    assert after[0]["audience"] == "everyone"
    assert after[1] == before[1]
    backups = list(machine["home"].glob("docs-sites.toml.bak.*"))
    assert backups, "an existing file must be backed up before it is rewritten"


def test_record_keeps_awkward_text_exactly(machine):
    row = _row(machine, audience='Readers of "the" product, C:\\docs \u2013 all')
    assert _record(machine, row).returncode == 0
    shown = json.loads(_run(machine, "show", "--key", "docs").stdout)
    assert shown["audience"] == row["audience"]


def test_record_writes_a_gitignore_so_the_state_root_is_never_committed(machine):
    assert _record(machine, _row(machine)).returncode == 0
    assert (machine["home"] / ".gitignore").read_text(encoding="utf-8").strip() == "*"


def test_record_is_atomic_when_the_existing_file_is_not_valid_toml(machine):
    machine["sites"].write_text("[[site\nbroken", encoding="utf-8")
    res = _record(machine, _row(machine))
    assert res.returncode == 2
    assert machine["sites"].read_text(encoding="utf-8") == "[[site\nbroken"


@pytest.mark.parametrize("pattern", ["bot/{series}/pr-{pr}", "fp-{pr}-{series}"])
def test_record_accepts_a_forward_port_branch_pattern_and_show_returns_it(machine, pattern):
    row = _row(machine)
    row["policy"]["forward_port_branch_pattern"] = pattern
    assert _record(machine, row).returncode == 0
    assert json.loads(_run(machine, "show", "--key", "docs").stdout)["policy"][
        "forward_port_branch_pattern"] == pattern
    assert _run(machine, "check").returncode == 0


def test_a_row_without_a_forward_port_pattern_is_complete(machine):
    row = _row(machine)
    assert "forward_port_branch_pattern" not in row["policy"]
    assert _record(machine, row).returncode == 0
    assert _run(machine, "check").returncode == 0


@pytest.mark.parametrize("pattern", [
    "bot/{series}/pr-1", "bot/pr-{pr}", "bot/{series}/{pr}/{other}", "bot/{series}/{pr}/{pr}", "", 7,
])
def test_record_refuses_a_forward_port_pattern_lacking_pr_or_series_or_with_others(machine, pattern):
    row = _row(machine)
    row["policy"]["forward_port_branch_pattern"] = pattern
    res = _record(machine, row)
    assert res.returncode != 0
    assert "forward_port_branch_pattern" in res.stderr
    assert not machine["sites"].exists()


def test_propose_offers_a_forward_port_pattern_seen_in_origin_branches_but_records_nothing(machine):
    for ref in ("bot/17.0/pr-101", "bot/18.0/pr-102", "bot/17.0/pr-103"):
        _sh(machine["docs"], "git", "update-ref", "refs/remotes/origin/" + ref, "HEAD")
    _sh(machine["docs"], "git", "update-ref", "refs/remotes/origin/fix-12-for-17.0", "HEAD")
    res = _run(machine, "propose", "--repo", str(machine["docs"]))
    facts = _facts(res.stdout)
    assert facts["FORWARD_PORT_BRANCH_PATTERN_CANDIDATE"] == "bot/{series}/pr-{pr}"
    assert facts["FORWARD_PORT_BRANCH_PATTERN_EVIDENCE"].startswith("bot/17.0/pr-101")
    assert "policy.forward_port_branch_pattern" in facts["FACTS_TO_CONFIRM"].split(",")
    assert "forward_port_branch_pattern" in facts["POLICY_FIELDS_TO_CONFIRM"].split(",")
    assert not machine["sites"].exists()


def test_propose_offers_no_forward_port_pattern_without_a_repeated_shape(machine):
    _sh(machine["docs"], "git", "update-ref", "refs/remotes/origin/fix-12-for-17.0", "HEAD")
    facts = _facts(_run(machine, "propose", "--repo", str(machine["docs"])).stdout)
    assert facts["FORWARD_PORT_BRANCH_PATTERN_CANDIDATE"] == ""


# ---------------------------------------------------------------- show / apply / describe

def test_show_returns_the_row_as_json_for_a_skill_to_read(machine):
    row = _row(machine)
    assert _record(machine, row).returncode == 0
    one = json.loads(_run(machine, "show", "--key", "docs").stdout)
    assert one == row
    every = json.loads(_run(machine, "show").stdout)
    assert every == [row]


def test_show_fails_for_an_undeclared_key_and_names_the_declared_ones(machine):
    assert _record(machine, _row(machine)).returncode == 0
    res = _run(machine, "show", "--key", "nope")
    assert res.returncode != 0
    assert "Traceback" not in res.stderr
    assert "no docs site with key 'nope'" in res.stderr and "declared: docs" in res.stderr


def test_apply_only_advises_and_writes_nothing(machine):
    res = _run(machine, "apply")
    assert res.returncode != 0
    assert "propose --repo" in res.stdout + res.stderr
    assert not machine["sites"].exists()


def test_describe_needs_no_state(machine):
    res = _run(machine, "describe")
    assert res.returncode == 0
    assert "docs site" in res.stdout


# ---------------------------------------------------------------- repos (the code repositories a site documents)

@pytest.mark.parametrize("repos", [
    ["acme/product"], ["https://example.org/acme/product.git", "git@example.org:acme/other.git"],
    ["ssh://git@example.org/acme/product.git"],
])
def test_record_accepts_the_code_repos_a_site_documents_and_show_returns_them(machine, repos):
    row = _row(machine, repos=repos)
    assert _record(machine, row).returncode == 0
    assert json.loads(_run(machine, "show", "--key", "docs").stdout)["repos"] == repos
    assert _run(machine, "check").returncode == 0


def test_a_row_without_repos_is_complete_and_show_has_no_repos(machine):
    assert _record(machine, _row(machine)).returncode == 0
    assert "repos" not in json.loads(_run(machine, "show", "--key", "docs").stdout)
    assert _run(machine, "check").returncode == 0


@pytest.mark.parametrize("repos", [
    [], "acme/product", [""], [7], ["two words"], ["not-a-repo"],
    ["https://user:secret@example.org/acme/product.git"], ["https://token123@example.org/acme/product.git"],
    ["acme/product", "acme/product"],
])
def test_record_refuses_repos_that_are_empty_malformed_repeated_or_carry_a_credential(machine, repos):
    res = _record(machine, _row(machine, repos=repos))
    assert res.returncode != 0
    assert "repos" in res.stderr
    assert not machine["sites"].exists()


def test_propose_asks_for_the_repos_and_never_fills_them(machine):
    facts = _facts(_run(machine, "propose", "--repo", str(machine["docs"])).stdout)
    assert "repos" in facts["POLICY_FIELDS_TO_CONFIRM"].split(",")
    assert not any(name.startswith("REPOS") for name in facts)


# ---------------------------------------------------------------- a row needs one clone (any series)

def test_record_refuses_a_row_where_no_series_declares_a_clone(machine):
    row = _row(machine)
    del row["series"]["17.0"]["clone"]
    res = _record(machine, row)
    assert res.returncode != 0
    assert "clone" in res.stderr
    assert not machine["sites"].exists()


def test_a_clone_on_any_one_series_is_enough_for_every_series(machine):
    row = _row(machine)
    row["series"]["18.0"]["clone"] = row["series"]["17.0"].pop("clone")
    assert _record(machine, row).returncode == 0
    assert _run(machine, "check").returncode == 0


def test_check_names_the_missing_clone_of_a_row_edited_by_hand(machine):
    assert _record(machine, _row(machine)).returncode == 0
    text = machine["sites"].read_text(encoding="utf-8")
    machine["sites"].write_text(
        "".join(l for l in text.splitlines(keepends=True) if not l.startswith("clone =")),
        encoding="utf-8")
    res = _run(machine, "check")
    assert res.returncode != 0
    assert "clone" in res.stdout


# ---------------------------------------------------------------- a python3 without tomllib

LIB = PLUGIN / "scripts" / "lib" / "docs_site_config.py"


def _run_no_tomllib(machine, *args):
    """docs_site_config.py as a python3 < 3.11 runs it: the import of tomllib fails."""
    boot = ("import runpy, sys; sys.modules['tomllib'] = None; sys.argv = sys.argv[1:]; "
            "runpy.run_path(sys.argv[0], run_name='__main__')")
    env = {**os.environ, "ODOO_AI_HOME": str(machine["home"]), "ODOO_AI_INSTANCES": str(machine["catalog"])}
    return subprocess.run([sys.executable, "-c", boot, str(LIB), *args], capture_output=True,
                          text=True, env=env, timeout=120)


def test_the_config_runs_without_tomllib_and_keeps_every_value_and_other_row(machine):
    other = _row(machine, key="second", audience='Readers of "the" product, C:\\docs \u2013 all')
    other["repos"] = ["acme/product"]
    other["policy"]["forward_port_branch_pattern"] = "bot/{series}/pr-{pr}"
    assert _record(machine, other).returncode == 0
    mine = _row(machine)
    f = machine["tmp"] / "mine.json"
    f.write_text(json.dumps(mine), encoding="utf-8")
    res = _run_no_tomllib(machine, "record", "--key", "docs", "--from-json", str(f))
    assert res.returncode == 0, res.stderr
    assert _run_no_tomllib(machine, "check").returncode == 0
    assert json.loads(_run_no_tomllib(machine, "show", "--key", "second").stdout) == other
    parsed = tomllib.loads(machine["sites"].read_text(encoding="utf-8"))["site"]
    assert [r["key"] for r in parsed] == ["second", "docs"]
    assert parsed[0] == other and parsed[1] == mine


def test_the_config_without_tomllib_refuses_toml_it_cannot_read_instead_of_misreading_it(machine):
    machine["sites"].write_text(
        '[[site]]\nkey = "docs"\nlanguages = ["en"\n', encoding="utf-8")
    res = _run_no_tomllib(machine, "check")
    assert res.returncode == 2
    assert "docs-sites.toml" in res.stderr
    machine["sites"].write_text('[[site]]\nkey = "docs"\nseries.x = 1\n', encoding="utf-8")
    assert _run_no_tomllib(machine, "show").returncode == 2
