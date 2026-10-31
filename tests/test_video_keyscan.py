"""`scripts/lib/video_keyscan.py` - a demo-video output directory is scanned for leaked API keys and tokens."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "lib" / "video_keyscan.py"
PLANTED = "demo-key-value-with-no-known-shape"


def _scan(directory, *extra):
    env = {"DEMO_AI_KEY": PLANTED, "PATH": "/usr/bin:/bin"}
    return subprocess.run([sys.executable, str(TOOL), "scan", "--dir", str(directory), *extra],
                          capture_output=True, text=True, timeout=60, env=env)


def _hits(proc):
    return [line for line in proc.stdout.splitlines() if line.startswith("HIT=")]


def test_openai_shaped_key_is_a_hit_with_its_relative_path_and_line(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "notes.txt").write_text("ok\nkey sk-" + "a1B2c3D4e5" * 3 + "\n")
    proc = _scan(tmp_path)
    assert proc.returncode == 1 and _hits(proc) == ["HIT=sub/notes.txt:2"]
    assert "HITS=1" in proc.stdout and "sk-a1B2" not in proc.stdout


def test_bearer_header_is_a_hit(tmp_path):
    (tmp_path / "a.log").write_text("Authorization: Bearer " + "x" * 24 + "\n")
    assert _hits(_scan(tmp_path)) == ["HIT=a.log:1"]


def test_value_of_a_named_variable_is_a_hit_and_is_never_echoed(tmp_path):
    (tmp_path / "t.txt").write_text("the key is " + PLANTED + " done\n")
    proc = _scan(tmp_path, "--key-env", "DEMO_AI_KEY")
    assert proc.returncode == 1 and _hits(proc) == ["HIT=t.txt:1"]
    assert PLANTED not in proc.stdout + proc.stderr
    assert _scan(tmp_path).returncode == 0


def test_binary_files_and_short_placeholders_are_not_hits(tmp_path):
    (tmp_path / "clip.txt").write_bytes(b"\0\x01 sk-" + b"a" * 30)
    (tmp_path / "shot.png").write_bytes(b"sk-" + b"a" * 30)
    (tmp_path / "doc.md").write_text("Use sk-... or <KEY> as in the example.\nsk-short1234\n")
    proc = _scan(tmp_path)
    assert proc.returncode == 0 and "HITS=0" in proc.stdout and "FILES=1" in proc.stdout


def test_long_opaque_run_is_a_hit_but_ordinary_prose_is_not(tmp_path):
    (tmp_path / "a.json").write_text('{"v": "' + "ab12" * 12 + '"}\n')
    (tmp_path / "b.txt").write_text("A perfectly ordinary sentence about invoices.\n")
    assert _hits(_scan(tmp_path)) == ["HIT=a.json:1"]


def test_urls_and_absolute_paths_are_text_while_a_bare_hex_run_is_a_hit(tmp_path):
    url = "https://example.test/" + "a" * 49
    path = "/home/user/" + "b" * 59
    assert len(url) == 70 and len(path) == 70
    (tmp_path / "t.txt").write_text(url + "\n" + path + "\n")
    assert _scan(tmp_path).returncode == 0
    (tmp_path / "t.txt").write_text(url + "\n" + path + "\n" + "0123456789abcdef" * 2 + "01234567\n")
    assert _hits(_scan(tmp_path)) == ["HIT=t.txt:3"]
