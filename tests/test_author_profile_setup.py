"""Behaviour tests for `scripts/setup-steps/65-author-profile.sh` and `author_profile_config.py`.

The profile is the one source of every published contact detail: a vendor's pre-sales and
support WEB PAGES, the manifest-only support address, and the address policy. `propose` reads
module descriptors and fills nothing in; `record` writes only a valid, operator-confirmed profile.
Everything runs on a throwaway state root (ODOO_AI_HOME).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
STEP = PLUGIN / "scripts" / "setup-steps" / "65-author-profile.sh"
LIB = PLUGIN / "scripts" / "lib" / "author_profile_config.py"

GOOD = {"vendor": "Acme ERP", "website": "https://acme-erp.com",
        "presales_url": "https://acme-erp.com/contact",
        "support_url": "https://support.acme-erp.com/tickets",
        "support_email": "support@acme-erp.com"}


@pytest.fixture()
def home(tmp_path):
    (tmp_path / "state").mkdir()
    return tmp_path / "state"


def _step(home, *args):
    return subprocess.run(["bash", str(STEP), *args], capture_output=True, text=True, timeout=60,
                          env={**os.environ, "ODOO_AI_HOME": str(home)})


def _record(home, profile):
    f = home / "p.json"
    f.write_text(json.dumps(profile), encoding="utf-8")
    return _step(home, "record", "--from-json", str(f))


def _facts(stdout):
    out = {}
    for line in stdout.splitlines():
        name, _, value = line.partition("=")
        out[name] = value.strip("'")
    return out


def test_describe_check_apply_follow_the_step_contract(home):
    assert "contact profile" in _step(home, "describe").stdout
    check = _step(home, "check")
    assert check.returncode == 1 and "odoo-setup author" in check.stderr
    apply = _step(home, "apply")
    assert apply.returncode == 1 and "propose" in apply.stdout
    assert not (home / "author-profile.toml").exists(), "apply must write nothing"


def test_propose_reads_the_manifests_and_derives_no_page(home, tmp_path):
    addons = tmp_path / "addons" / "mod_a"
    addons.mkdir(parents=True)
    (addons / "__manifest__.py").write_text(
        "{'name': 'A', 'author': 'Acme ERP', 'website': 'https://acme-erp.com', "
        "'support': 'support@acme-erp.com'}\n", encoding="utf-8")
    proc = _step(home, "propose", "--addons", str(tmp_path / "addons"))
    assert proc.returncode == 0, proc.stderr
    facts = _facts(proc.stdout)
    assert facts["VENDOR"] == "Acme ERP" and facts["WEBSITE"] == "https://acme-erp.com"
    assert facts["SUPPORT_EMAIL"] == "support@acme-erp.com" and facts["DECLARED"] == "0"
    assert "PRESALES_URL" not in facts and "SUPPORT_URL" not in facts
    assert not (home / "author-profile.toml").exists()


def test_record_then_show_and_check_round_trip(home):
    proc = _record(home, GOOD)
    assert proc.returncode == 0, proc.stderr
    shown = json.loads(_step(home, "show").stdout)
    assert shown == GOOD
    assert _step(home, "check").returncode == 0
    text = (home / "author-profile.toml").read_text(encoding="utf-8")
    assert text.startswith("[author]\n") and 'presales_url = "https://acme-erp.com/contact"' in text


@pytest.mark.parametrize("bad, word", [
    ({**GOOD, "presales_url": "mailto:sales@acme-erp.com"}, "presales_url"),
    ({**GOOD, "support_url": "http://support.acme-erp.com"}, "support_url"),
    ({**GOOD, "website": "https://localhost:8069"}, "website"),
    ({**GOOD, "support_email": "https://acme-erp.com/support"}, "support_email"),
    ({**GOOD, "address_policy": "sometimes"}, "address_policy"),
    ({**GOOD, "phone": "+84"}, "unknown key"),
    ({k: v for k, v in GOOD.items() if k != "vendor"}, "vendor"),
])
def test_record_refuses_an_address_in_a_url_field_and_every_other_invalid_profile(home, bad, word):
    proc = _record(home, bad)
    assert proc.returncode == 1, proc.stdout
    assert word in proc.stderr
    assert not (home / "author-profile.toml").exists()


def test_record_keeps_a_backup_of_the_previous_profile(home):
    assert _record(home, GOOD).returncode == 0
    assert _record(home, {**GOOD, "vendor": "Acme ERP Ltd"}).returncode == 0
    backups = [p for p in home.iterdir() if p.name.startswith("author-profile.toml.bak")]
    assert backups, sorted(p.name for p in home.iterdir())
    assert json.loads(_step(home, "show").stdout)["vendor"] == "Acme ERP Ltd"
