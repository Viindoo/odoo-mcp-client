"""`catalog_review.py` reads the whole instance registry and names every anomaly with its fix,
so the setup plan shows them to the operator instead of a step stumbling on one later."""
import json
import os
import stat
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "lib" / "catalog_review.py"


def _venv(path: Path, ok=True):
    (path / "bin").mkdir(parents=True)
    (path / "pyvenv.cfg").write_text("home = /usr/bin\n")
    py = path / "bin" / "python"
    py.write_text("#!/usr/bin/env bash\nexit 0\n")
    if ok:
        py.chmod(py.stat().st_mode | stat.S_IXUSR)
    return py


def _catalog(tmp_path):
    good = tmp_path / "addons17"
    good.mkdir()
    shared = _venv(tmp_path / "venvs" / "19.0")
    dead_py = _venv(tmp_path / "venvs" / "16.0", ok=False)
    toml = tmp_path / "instances.toml"
    toml.write_text(textwrap.dedent('''\
        # the venv of 17.0 used to live at /nonexistent/old-venv
        [[instance]]
        series = "17.0"
        profile = "std"
        instance_key = "17.0:std"
        addons_path = ["%(good)s"]
        python = "%(shared)s"

        [[instance]]
        series = "19.0"
        profile = "std"
        instance_key = "19.0:std"
        addons_path = ["%(good)s"]
        python = "%(shared)s"

        [[instance]]
        series = "19.0"
        profile = "internal"
        instance_key = "19.0:internal"
        addons_path = ["%(good)s", "%(gone)s"]
        python = "%(shared)s"

        [[instance]]
        series = "16.0"
        instance_key = "16.0"
        addons_path = ["%(good)s"]
        python = "%(dead)s"

        [[instance]]
        series = "15.0"
        instance_key = "15.0"
        addons_path = ["%(good)s"]
        python = ""

        [[instance]]
        series = "17.0"
        profile = "std"
        instance_key = "17.0:std"
        addons_path = ["%(good)s"]
        python = ""
        ''' % {"good": good, "shared": shared, "gone": tmp_path / "gone", "dead": dead_py}))
    return toml


def _run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True)


def test_review_names_every_anomaly_with_its_fix(tmp_path):
    toml = _catalog(tmp_path)
    proc = _run("review", str(toml), "--json")
    assert proc.returncode == 0, proc.stderr
    findings = json.loads(proc.stdout)
    kinds = sorted((f["kind"], f.get("row") or " ".join(f.get("rows", []))) for f in findings)
    assert ("DUPLICATE_ROW", "17.0:std") in kinds
    assert ("SHARED_VENV", "17.0:std 19.0:std 19.0:internal") in kinds
    assert ("DEAD_ADDONS_PATH", "19.0:internal") in kinds
    assert ("DEAD_PYTHON", "16.0") in kinds
    assert ("NO_PYTHON", "15.0") in kinds
    assert any(f["kind"] == "STALE_COMMENT" and "/nonexistent/old-venv" in f["detail"] for f in findings)
    assert all(f["fix"] for f in findings)
    text = _run("review", str(toml)).stdout
    assert "FINDINGS=%d" % len(findings) in text and "FINDING=SHARED_VENV rows=17.0:std 19.0:std 19.0:internal" in text


def test_a_clean_registry_has_no_findings_and_a_missing_one_is_not_an_error(tmp_path):
    good = tmp_path / "addons"
    good.mkdir()
    py = _venv(tmp_path / "venv")
    toml = tmp_path / "instances.toml"
    toml.write_text('[[instance]]\nseries = "17.0"\naddons_path = ["%s"]\npython = "%s"\n' % (good, py))
    assert _run("review", str(toml)).stdout.strip() == "FINDINGS=0"
    assert _run("review", str(tmp_path / "absent.toml")).stdout.strip() == "FINDINGS=0"


def test_dedupe_drops_the_later_copy_keeps_everything_else_byte_for_byte_and_backs_up(tmp_path):
    toml = _catalog(tmp_path)
    before = toml.read_text()
    proc = _run("dedupe", str(toml))
    assert proc.returncode == 0, proc.stderr
    assert "DROPPED=17.0:std" in proc.stdout and "KEPT=5" in proc.stdout
    after = toml.read_text()
    assert after.count("[[instance]]") == 5 and after.count('instance_key = "17.0:std"') == 1
    assert after.startswith("# the venv of 17.0 used to live")            # comments and the first rows untouched
    assert 'python = ""\n' in after and '"15.0"' in after                   # the unrelated empty-python row stays
    backups = list(tmp_path.glob("instances.toml.bak.*"))
    assert len(backups) == 1 and backups[0].read_text() == before
    assert _run("dedupe", str(toml)).stdout.strip() == "KEPT=5"           # idempotent
    findings = json.loads(_run("review", str(toml), "--json").stdout)
    assert not any(f["kind"] == "DUPLICATE_ROW" for f in findings)
