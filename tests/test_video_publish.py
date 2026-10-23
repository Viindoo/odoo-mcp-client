"""`scripts/lib/video_publish.py` - the publish profile is applied and verified from data.

The sidecar writer runs everywhere; the ffmpeg paths run only where ffmpeg and ffprobe exist and
build synthetic media (a 2 s test pattern and a 3 s tone), so the fitted scene holds its last
frame to the narration, the concatenated file passes every profile check, and a file that
breaks the profile fails it.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "lib" / "video_publish.py"
HAS_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def _tool(*args):
    return subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True, timeout=300)


def _kv(stdout):
    return dict(line.split("=", 1) for line in stdout.splitlines() if "=" in line)


def test_sidecar_writes_captions_timed_by_the_measured_durations_and_chapters(tmp_path):
    sb = {"title": "Demo", "languages": ["vi_VN"], "lead_in_s": 0.5,
          "publish": {"vi_VN": {"title": "Trợ lý AI", "description": "Mô tả."}},
          "scenes": [{"id": "s1", "title": {"vi_VN": "Mở đầu"}, "narration": {"vi_VN": "Xin chào."}},
                     {"id": "s2", "title": {"vi_VN": "Tạo đơn"}, "narration": {"vi_VN": "Tạo một đơn hàng."}}]}
    (tmp_path / "sb.json").write_text(json.dumps(sb, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "d.json").write_text(json.dumps({"s1": 4.0, "s2": 6.5}), encoding="utf-8")
    proc = _tool("sidecar", "--storyboard", str(tmp_path / "sb.json"), "--lang", "vi_VN",
                 "--durations", str(tmp_path / "d.json"), "--out-dir", str(tmp_path / "out"))
    assert proc.returncode == 0, proc.stderr
    srt = (tmp_path / "out" / "vi_VN.srt").read_text(encoding="utf-8")
    assert "00:00:00,500 --> 00:00:03,800" in srt and "00:00:04,500 --> 00:00:10,300" in srt
    txt = (tmp_path / "out" / "vi_VN.txt").read_text(encoding="utf-8")
    assert "TITLE: Trợ lý AI" in txt and "0:00 Mở đầu" in txt and "0:04 Tạo đơn" in txt
    assert _kv(proc.stdout)["TOTAL_S"] == "10.500"


@pytest.fixture()
def media(tmp_path):
    if not HAS_FFMPEG:
        pytest.skip("ffmpeg/ffprobe not on PATH")
    clip, narr = tmp_path / "clip.mp4", tmp_path / "narr.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=1920x1080:rate=25:duration=2",
                    "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "2", "-pix_fmt", "yuv420p", str(clip)],
                   check=True, capture_output=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
                    "-ac", "1", "-ar", "48000", "-sample_fmt", "s16", str(narr)], check=True, capture_output=True)
    return clip, narr


def test_fit_holds_the_last_frame_to_the_narration_and_concat_passes_the_profile(media, tmp_path):
    clip, narr = media
    fitted = tmp_path / "fitted.mp4"
    fit = _tool("fit", "--clip", str(clip), "--narration", str(narr), "--out", str(fitted))
    assert fit.returncode == 0, fit.stderr
    facts = _kv(fit.stdout)
    assert float(facts["DURATION_S"]) == pytest.approx(3.8, abs=0.05)  # 0.5 lead-in + 3 s + 0.3 fade
    assert float(facts["HOLD_S"]) == pytest.approx(1.8, abs=0.05)
    (tmp_path / "list.txt").write_text("%s\n%s\n" % (fitted, fitted), encoding="utf-8")
    final = tmp_path / "final.mp4"
    cat = _tool("concat", "--list", str(tmp_path / "list.txt"), "--out", str(final))
    assert cat.returncode == 0, cat.stderr
    ver = _tool("verify", "--video", str(final))
    assert ver.returncode == 0, ver.stdout + ver.stderr
    assert "FAIL" not in ver.stdout and "LOUDNESS=OK" in ver.stdout and "CONTAINER_FASTSTART=OK" in ver.stdout


def test_verify_fails_a_file_that_breaks_the_profile(media, tmp_path):
    clip, _narr = media  # 1920x1080 but yuv420p with silent stereo; shrink it to break SIZE
    small = tmp_path / "small.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(clip), "-vf", "scale=1280:720", "-c:a", "copy",
                    str(small)], check=True, capture_output=True)
    ver = _tool("verify", "--video", str(small))
    assert ver.returncode == 1
    assert "SIZE=FAIL" in ver.stdout
