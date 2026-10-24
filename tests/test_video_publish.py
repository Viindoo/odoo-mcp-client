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


def test_fit_reports_a_scene_that_moves_longer_than_the_silence_limit_with_nobody_speaking(media, tmp_path):
    clip, _ = media
    short = tmp_path / "short.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=0.4",
                    "-ac", "1", "-ar", "48000", "-sample_fmt", "s16", str(short)], check=True, capture_output=True)
    out = tmp_path / "fitted.mp4"
    base = [sys.executable, str(TOOL), "fit", "--clip", str(clip), "--narration", str(short),
            "--out", str(out), "--lead-in", "0.5"]
    over = subprocess.run(base + ["--max-silence", "1.0"], capture_output=True, text=True)
    assert over.returncode == 4 and "SILENCE=over" in over.stdout, over.stdout + over.stderr
    assert abs(float(_kv(over.stdout)["SILENT_S"]) - 1.1) < 0.15  # 2 s clip - 0.5 lead-in - 0.4 narration
    assert out.exists()  # the file is still written so the author can watch the silent stretch
    ok = subprocess.run(base + ["--max-silence", "3.0"], capture_output=True, text=True)
    assert ok.returncode == 0 and "SILENCE=ok" in ok.stdout


def test_verify_tools_reports_the_card_renderer_the_filters_and_the_font_coverage():
    if not HAS_FFMPEG:
        pytest.skip("ffmpeg/ffprobe not on PATH")
    proc = subprocess.run([sys.executable, str(TOOL), "verify-tools"], capture_output=True, text=True)
    kv = _kv(proc.stdout)
    assert kv["TITLE_CARD"] in ("drawtext", "libass", "none") and kv["FILTER_loudnorm"] in ("ok", "missing")
    assert kv["FONT_VI_COVERAGE"] in ("ok", "missing", "unknown") or kv["FONT"] == "none"
    assert kv["VERDICT"] in ("pass", "fail")


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe not on PATH")
def test_the_title_card_renders_with_whichever_text_filter_this_ffmpeg_has(tmp_path):
    out = tmp_path / "title.mp4"
    proc = subprocess.run([sys.executable, str(TOOL), "title", "--text", "Trợ lý AI của Viindoo", "--out", str(out),
                           "--seconds", "1"], capture_output=True, text=True)
    tools = _kv(subprocess.run([sys.executable, str(TOOL), "verify-tools"], capture_output=True, text=True).stdout)
    if tools["TITLE_CARD"] == "none":
        assert proc.returncode == 1 and "neither" in proc.stderr
        return
    assert proc.returncode == 0, proc.stderr
    assert _kv(proc.stdout)["RENDERED_WITH"] == tools["TITLE_CARD"] and out.stat().st_size > 1000
    assert not (tmp_path / "title.mp4.ass").exists() and not (tmp_path / "title.mp4.txt").exists()


def test_two_takes_at_different_levels_come_out_at_one_loudness(media, tmp_path):
    """A retake recorded louder or softer than its neighbours is brought to the same level before
    the mix: the fitted clips of a loud and a soft narration measure within 2 LU of each other."""
    import re
    clip, narr = media
    soft = tmp_path / "soft.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(narr), "-af", "volume=-18dB", "-ac", "1", "-ar", "48000",
                    "-sample_fmt", "s16", str(soft)], check=True, capture_output=True)
    levels = []
    for wav in (narr, soft):
        out = tmp_path / ("%s-fitted.mp4" % wav.stem)
        proc = subprocess.run([sys.executable, str(TOOL), "fit", "--clip", str(clip), "--narration", str(wav),
                               "--out", str(out), "--max-silence", "5"], capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr
        measured = subprocess.run(["ffmpeg", "-i", str(out), "-af", "ebur128", "-f", "null", "-"],
                                  capture_output=True, text=True).stderr
        m = re.search(r"Integrated loudness:\s+I:\s+(-?\d+\.\d) LUFS", measured)
        assert m, measured[-600:]
        levels.append(float(m.group(1)))
    assert abs(levels[0] - levels[1]) < 2.0, levels


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe not on PATH")
def test_pacing_compresses_logged_dead_time_zooms_on_the_focus_and_caps_the_held_frame(tmp_path):
    clip = tmp_path / "clip.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=25:duration=6",
                    "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "6", "-pix_fmt", "yuv420p", str(clip)],
                   check=True, capture_output=True)
    events = tmp_path / "ev.json"
    events.write_text(json.dumps([{"kind": "typing", "start": 1.0, "end": 3.0}, {"kind": "wait", "start": 4.0, "end": 5.5}]))
    paced = tmp_path / "paced.mp4"
    proc = subprocess.run([sys.executable, str(TOOL), "speedup", "--clip", str(clip), "--events", str(events), "--out", str(paced)],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    kv = _kv(proc.stdout)
    # 2 s typing at 3x saves 1.33 s, a 1.5 s wait keeps 1 s: about 1.8 s saved of 6
    assert 1.6 <= float(kv["SAVED_S"]) <= 2.1 and kv["SPANS"] == "2"
    zoomed = tmp_path / "zoomed.mp4"
    proc = subprocess.run([sys.executable, str(TOOL), "zoom", "--clip", str(clip), "--focus", "600,300,300,150", "--from", "1",
                           "--to", "3", "--out", str(zoomed)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    size = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,duration",
                           "-of", "csv=p=0", str(zoomed)], capture_output=True, text=True).stdout.strip().split(",")
    assert size[0] == "1280" and size[1] == "720" and abs(float(size[2]) - 6.0) < 0.2
    long_narr = tmp_path / "long.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=12", "-ac", "1", "-ar", "48000",
                    "-sample_fmt", "s16", str(long_narr)], check=True, capture_output=True)
    proc = subprocess.run([sys.executable, str(TOOL), "fit", "--clip", str(clip), "--narration", str(long_narr), "--out",
                           str(tmp_path / "f.mp4"), "--max-silence", "10", "--max-hold", "3"], capture_output=True, text=True)
    assert proc.returncode == 5 and "HOLD=over" in proc.stdout and "freeze" in proc.stderr


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe not on PATH")
def test_the_music_bed_rides_under_the_narration_and_the_audition_renders_dry_and_wet_samples(media, tmp_path):
    clip, narr = media
    fitted = tmp_path / "fitted.mp4"
    assert subprocess.run([sys.executable, str(TOOL), "fit", "--clip", str(clip), "--narration", str(narr), "--out", str(fitted),
                           "--max-silence", "10"], capture_output=True, text=True).returncode == 0
    bed = tmp_path / "bed.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=220:duration=2", "-ac", "2", "-ar", "48000", str(bed)],
                   check=True, capture_output=True)
    lst = tmp_path / "list.txt"; lst.write_text("%s\n" % fitted)
    out = tmp_path / "final.mp4"
    proc = subprocess.run([sys.executable, str(TOOL), "concat", "--list", str(lst), "--out", str(out), "--music", str(bed),
                           "--music-license", "CC0 test tone"], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    kv = _kv(proc.stdout)
    assert kv["MUSIC_LICENSE"] == "CC0 test tone" and abs(float(kv["DURATION_S"]) - 3.8) < 0.3  # lead-in + narration + fade
    # the bed is audible in the lead-in (0-0.5 s), where no narration plays: the stream is not silent there
    level = subprocess.run(["ffmpeg", "-i", str(out), "-t", "0.4", "-af", "volumedetect", "-f", "null", "-"],
                           capture_output=True, text=True).stderr
    import re
    m = re.search(r"mean_volume: (-?\d+\.\d) dB", level)
    assert m and float(m.group(1)) > -60.0, level[-300:]
    proc = subprocess.run([sys.executable, str(TOOL), "audition", "--narration", str(narr), "--out-dir", str(tmp_path / "aud"),
                           "--music", str(bed)], capture_output=True, text=True)
    assert proc.returncode == 0 and "music=off" in proc.stdout and "music=on" in proc.stdout
    assert (tmp_path / "aud" / "narr.dry.wav").exists() and (tmp_path / "aud" / "narr.music.wav").exists()
