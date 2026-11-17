"""`module_requirements.py` decides whether a module's App Store page needs a Technical
requirements section: only when the module needs something Odoo's own installation does not bring."""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "lib"
SCRIPT = LIB / "module_requirements.py"
FACTS = LIB / "odoo_source_facts.py"

REQUIREMENTS = """\
# Odoo's own
Babel==2.9.1 ; python_version < '3.11'
python_dateutil>=2.8
python-ldap ; sys_platform != 'win32'
Pillow
PyYAML==6.0  # comment
lxml[html_clean]
-r other.txt
"""


def _checkout(tmp_path, requirements=REQUIREMENTS):
    root = tmp_path / "odoo"
    (root / "odoo").mkdir(parents=True)
    (root / "odoo" / "release.py").write_text("", encoding="utf-8")
    if requirements is not None:
        (root / "requirements.txt").write_text(requirements, encoding="utf-8")
    return root


def _module(tmp_path, external=None, descriptor="__manifest__.py"):
    mod = tmp_path / "addons" / "my_mod"
    mod.mkdir(parents=True)
    data = {"name": "My"}
    if external is not None:
        data["external_dependencies"] = external
    (mod / descriptor).write_text(repr(data), encoding="utf-8")
    return mod


def _run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True)


def _kv(out):
    return dict(line.split("=", 1) for line in out.splitlines() if "=" in line)


def test_only_the_python_packages_odoo_does_not_install_are_extra(tmp_path):
    root = _checkout(tmp_path)
    mod = _module(tmp_path, {"python": ["lxml", "zeep", "requests"]})
    res = _run(mod, "--odoo-root", root)
    assert res.returncode == 0
    assert _kv(res.stdout) == {"PYTHON_EXTRA": "zeep,requests", "BIN": "", "TECH_SECTION": "yes"}


@pytest.mark.parametrize("declared", ["ldap", "dateutil", "PIL", "yaml", "Pillow", "python_dateutil", "babel"])
def test_import_and_distribution_names_and_spellings_are_covered(tmp_path, declared):
    root = _checkout(tmp_path)
    mod = _module(tmp_path, {"python": [declared]})
    res = _run(mod, "--odoo-root", root)
    assert _kv(res.stdout) == {"PYTHON_EXTRA": "", "BIN": "", "TECH_SECTION": "no"}


def test_every_declared_bin_is_listed_and_opens_the_section(tmp_path):
    mod = _module(tmp_path, {"bin": ["wkhtmltopdf", "pdftotext"]})
    res = _run(mod)
    assert res.returncode == 0
    assert _kv(res.stdout) == {"PYTHON_EXTRA": "", "BIN": "wkhtmltopdf,pdftotext", "TECH_SECTION": "yes"}


def test_no_external_dependencies_means_no_section(tmp_path):
    res = _run(_module(tmp_path))
    assert res.returncode == 0
    assert _kv(res.stdout)["TECH_SECTION"] == "no"


def test_checkout_found_from_the_addons_path(tmp_path):
    root = _checkout(tmp_path)
    mod = _module(tmp_path, {"python": ["zeep"]})
    res = _run(mod, "--addons-path", root / "odoo")
    assert _kv(res.stdout)["PYTHON_EXTRA"] == "zeep"


def test_unreadable_checkout_requirements_are_refused_not_guessed(tmp_path):
    root = _checkout(tmp_path, None)
    mod = _module(tmp_path, {"python": ["zeep"]})
    res = _run(mod, "--odoo-root", root)
    assert res.returncode == 3 and "TECH_SECTION" not in res.stdout


def test_no_checkout_at_all_is_refused_when_python_is_declared(tmp_path):
    res = _run(_module(tmp_path, {"python": ["zeep"]}))
    assert res.returncode == 3


def test_the_oldest_descriptor_name_is_read(tmp_path):
    mod = _module(tmp_path, {"bin": ["x"]}, descriptor="__openerp__.py")
    assert _kv(_run(mod).stdout)["BIN"] == "x"


def test_an_unreadable_descriptor_is_a_usage_error(tmp_path):
    mod = tmp_path / "m"
    mod.mkdir()
    assert _run(mod).returncode == 2
    (mod / "__manifest__.py").write_text("{'name': [", encoding="utf-8")
    assert _run(mod).returncode == 2


def test_the_checkout_requirements_reader_normalises_every_line(tmp_path):
    root = _checkout(tmp_path)
    res = subprocess.run([sys.executable, str(FACTS), "python-requirements", str(root)],
                         capture_output=True, text=True)
    assert res.returncode == 0
    assert _kv(res.stdout)["PYTHON_REQUIREMENTS"] == "babel,python-dateutil,python-ldap,pillow,pyyaml,lxml"


def test_the_checkout_requirements_reader_refuses_when_unknown(tmp_path):
    root = _checkout(tmp_path, None)
    res = subprocess.run([sys.executable, str(FACTS), "python-requirements", str(root)],
                         capture_output=True, text=True)
    assert res.returncode == 3
