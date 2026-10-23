"""`scripts/lib/email_image.py` - an address a vendor insists on ships as a PNG, never as text.

The renderer refuses anything that is not an address, keeps the address off the command line of
every subprocess it spawns, and names an alt text that is not the address. Rendering itself needs
Pillow or an ffmpeg with drawtext; without either the test for the rendered file is skipped and
the remedy is asserted instead.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "lib" / "email_image.py"


def _run(*args, home):
    return subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True,
                          timeout=60, env={"ODOO_AI_HOME": str(home), "PATH": __import__("os").environ["PATH"]})


def _has_renderer():
    try:
        import PIL  # noqa: F401
        return True
    except ImportError:
        pass
    if shutil.which("ffmpeg"):
        out = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True,
                             text=True, check=False).stdout
        return " drawtext " in out
    return False


def test_a_non_address_is_refused(tmp_path):
    proc = _run("--address", "not-an-address", "--out", str(tmp_path / "x.png"), home=tmp_path)
    assert proc.returncode == 1 and "not an email address" in proc.stderr
    assert not (tmp_path / "x.png").exists()


def test_the_rendered_file_is_a_png_and_the_alt_text_is_not_the_address(tmp_path):
    if not _has_renderer():
        proc = _run("--address", "sales@acme-erp.com", "--out", str(tmp_path / "m.png"), home=tmp_path)
        assert proc.returncode == 2 and ("pillow" in proc.stderr.lower() or "font" in proc.stderr)
        pytest.skip("no renderer on this machine")
    out = tmp_path / "m.png"
    proc = _run("--address", "sales@acme-erp.com", "--out", str(out), home=tmp_path)
    if proc.returncode == 2 and "font" in proc.stderr:
        pytest.skip("no font on this machine")
    assert proc.returncode == 0, proc.stderr
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    facts = dict(line.split("=", 1) for line in proc.stdout.splitlines())
    assert facts["PNG"] == str(out) and facts["ALT"] == "contact address"
    assert "sales@acme-erp.com" not in proc.stdout + proc.stderr
