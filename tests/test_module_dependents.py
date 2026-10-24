"""`module_dependents.py` answers "which modules extend this one" from the manifests on disk - the
source of the App Store page's EXTENSIONS cards - never from memory."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "lib" / "module_dependents.py"


def _addon(base: Path, name, depends, author="Acme", manifest="__manifest__.py", **extra):
    d = base / name
    d.mkdir(parents=True)
    data = {"name": extra.pop("display", name.replace("_", " ").title()), "depends": depends, "author": author}
    data.update(extra)
    (d / manifest).write_text(repr(data), encoding="utf-8")
    return d


def _world(tmp_path):
    own = tmp_path / "own"
    other = tmp_path / "other"
    _addon(own, "viin_sale", ["sale"], summary="Sell more,  faster")
    _addon(own, "viin_sale_discount", ["viin_sale", "account"], display="Sales Discounts",
           summary="Approve discounts without the back-and-forth")
    _addon(own, "viin_sale_portal", ["viin_sale"], display="Customer Portal for Sales", installable=False)
    _addon(own, "viin_sale_loyalty", ["viin_sale"], display="Loyalty", application=True, manifest="__openerp__.py")
    _addon(other, "third_party_bridge", ["viin_sale"], author="Someone Else")
    _addon(other, "unrelated", ["sale"])
    (other / "broken").mkdir()
    (other / "broken" / "__manifest__.py").write_text("{'name': 'Broken', 'depends': [", encoding="utf-8")
    return own, other


def _run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True)


def test_lists_every_module_whose_manifest_depends_on_the_one_asked_sorted_by_display_name(tmp_path):
    own, other = _world(tmp_path)
    proc = _run("viin_sale", "--addons-path", "%s,%s" % (own, other), "--json")
    assert proc.returncode == 0, proc.stderr
    rows = json.loads(proc.stdout)
    assert [r["technical_name"] for r in rows] == ["viin_sale_portal", "viin_sale_loyalty", "viin_sale_discount",
                                                   "third_party_bridge"]
    discount = rows[2]
    assert discount["name"] == "Sales Discounts" and discount["summary"] == "Approve discounts without the back-and-forth"
    assert discount["installable"] is True and discount["application"] is False
    assert rows[1]["application"] is True            # an __openerp__.py manifest counts too
    assert rows[0]["installable"] is False
    assert "broken" in proc.stderr and "x " in proc.stderr   # the unparsable manifest is named, not fatal


def test_author_filter_keeps_only_the_vendors_own_extensions(tmp_path):
    own, other = _world(tmp_path)
    proc = _run("viin_sale", "--addons-path", "%s,%s" % (own, other), "--author", " acme ")
    assert proc.returncode == 0, proc.stderr
    names = [line.split()[0] for line in proc.stdout.splitlines() if line.startswith("DEPENDENT=")]
    assert names == ["DEPENDENT=viin_sale_portal", "DEPENDENT=viin_sale_loyalty", "DEPENDENT=viin_sale_discount"]
    assert "third_party_bridge" not in proc.stdout


def test_a_module_nobody_extends_is_an_empty_answer_not_an_error(tmp_path):
    own, other = _world(tmp_path)
    proc = _run("viin_sale_loyalty", "--addons-path", str(own))
    assert proc.returncode == 0 and proc.stdout.strip() == "DEPENDENTS=none"


def test_the_module_itself_and_a_missing_directory_are_ignored(tmp_path):
    own, _ = _world(tmp_path)
    proc = _run("viin_sale", "--addons-path", "%s,%s" % (own, tmp_path / "nowhere"), "--json")
    assert proc.returncode == 0, proc.stderr
    assert "viin_sale" not in [r["technical_name"] for r in json.loads(proc.stdout)]
