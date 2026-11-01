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
    proc = subprocess.run([sys.executable, str(TOOL), "speedup", "--clip", str(clip), "--events", str(events), "--out", str(paced),
                           "--wait-squeeze", "0"],
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


def _pace(tmp_path, spans, *extra):
    clip = tmp_path / "pace-clip.mp4"
    if not clip.exists():
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=25:duration=6",
                        "-t", "6", "-pix_fmt", "yuv420p", str(clip)], check=True, capture_output=True)
    events = tmp_path / "pace.events.json"
    events.write_text(json.dumps(spans))
    out = tmp_path / "pace-out.mp4"
    out.unlink(missing_ok=True)
    proc = _tool("speedup", "--clip", str(clip), "--events", str(events), "--out", str(out), *extra)
    return proc, out


def _length(path):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                                capture_output=True, text=True).stdout)


WAIT = [{"kind": "wait", "start": 1.0, "end": 5.0}]


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe not on PATH")
def test_a_long_wait_is_squeezed_into_the_squeeze_seconds_and_cut_when_the_squeeze_is_zero(tmp_path):
    # 6 s clip, 4 s wait: 1 s kept + 3 s squeezed into 1 s + 2 s around it = 4 s; cut instead = 3 s
    proc, out = _pace(tmp_path, WAIT, "--wait-keep", "1", "--wait-squeeze", "1")
    assert proc.returncode == 0, proc.stderr
    assert _length(out) == pytest.approx(4.0, abs=0.3)
    assert _kv(proc.stdout)["SPANS"] == "1"
    proc, out = _pace(tmp_path, WAIT, "--wait-keep", "1", "--wait-squeeze", "0")
    assert proc.returncode == 0, proc.stderr
    assert _length(out) == pytest.approx(3.0, abs=0.3)


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe not on PATH")
def test_a_wait_inside_a_must_see_range_plays_in_full_and_is_counted(tmp_path):
    proc, out = _pace(tmp_path, WAIT, "--wait-keep", "1", "--wait-squeeze", "0", "--must-see", "2.0,3.0")
    assert proc.returncode == 0, proc.stderr
    assert _length(out) == pytest.approx(6.0, abs=0.3)
    assert _kv(proc.stdout)["MUST_SEE_KEPT"] == "1"


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe not on PATH")
def test_a_voice_span_is_kept_at_normal_speed_and_counted(tmp_path):
    proc, out = _pace(tmp_path, [{"kind": "voice_out", "start": 1.0, "end": 4.0}])
    assert proc.returncode == 0, proc.stderr
    assert _length(out) == pytest.approx(6.0, abs=0.3)
    assert _kv(proc.stdout)["SPANS"] == "1"


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe not on PATH")
def test_a_take_that_showed_a_key_field_is_refused_and_writes_nothing(tmp_path):
    proc, out = _pace(tmp_path, WAIT + [{"kind": "key_visible", "start": 5.2, "end": 5.6}])
    assert proc.returncode == 6 and _kv(proc.stdout)["KEY_VISIBLE"] == "1"
    assert not out.exists()


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe not on PATH")
def test_a_voice_track_is_audible_at_its_offset_in_the_fitted_scene(media, tmp_path):
    clip, _ = media
    short = tmp_path / "short.wav"  # speaks 0.5-0.9 s, so 1.1-1.9 s holds only the extra voice
    voice = tmp_path / "voice.wav"
    for path, hz, dur in ((short, 440, 0.4), (voice, 880, 1.0)):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=%d:duration=%s" % (hz, dur),
                        "-ac", "1", "-ar", "48000", "-sample_fmt", "s16", str(path)], check=True, capture_output=True)

    def window_db(out):
        import re
        err = subprocess.run(["ffmpeg", "-ss", "1.1", "-t", "0.8", "-i", str(out), "-af", "volumedetect", "-f", "null", "-"],
                             capture_output=True, text=True).stderr
        m = re.search(r"mean_volume: (-?[\d.]+|-inf) dB", err)
        assert m, err[-300:]
        return float(m.group(1)) if m.group(1) != "-inf" else -120.0

    plain, mixed = tmp_path / "plain.mp4", tmp_path / "mixed.mp4"
    base = ["fit", "--clip", str(clip), "--narration", str(short), "--max-silence", "5"]
    assert _tool(*base, "--out", str(plain)).returncode == 0
    proc = _tool(*base, "--out", str(mixed), "--voice", "%s@1.0" % voice)
    assert proc.returncode == 0, proc.stderr
    assert _kv(proc.stdout)["VOICES"] == "1"
    assert window_db(plain) < -60.0 and window_db(mixed) > -40.0


# --------------------------------------------------------------------------- silent footage
def _no_audio_clip(path, seconds=2):
    """What the recorder writes: a picture and no audio stream at all."""
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                    "testsrc=size=1920x1080:rate=25:duration=%s" % seconds, "-t", str(seconds),
                    "-pix_fmt", "yuv420p", str(path)], check=True, capture_output=True)
    return path


def _audio_stream(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
                          "stream=codec_name,sample_rate,channels", "-of", "json", str(path)],
                         capture_output=True, text=True, check=True).stdout
    streams = json.loads(out)["streams"]
    return streams[0] if streams else None


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe not on PATH")
def test_a_silent_clip_goes_through_fit_and_concat_with_a_title_card_and_verifies_as_silent(tmp_path):
    clip = _no_audio_clip(tmp_path / "scene.mp4")
    fitted = tmp_path / "fitted.mp4"
    fit = _tool("fit", "--clip", str(clip), "--out", str(fitted))
    assert fit.returncode == 0, fit.stderr
    facts = _kv(fit.stdout)
    assert facts["NARRATION"] == "none" and float(facts["DURATION_S"]) == pytest.approx(2.0, abs=0.1)
    assert float(facts["HOLD_S"]) == 0.0
    assert _audio_stream(fitted)["codec_name"] == "aac"
    card = tmp_path / "title.mp4"
    tools = _kv(_tool("verify-tools").stdout)
    if tools["TITLE_CARD"] == "none":
        pytest.skip("this ffmpeg cannot render a title card")
    assert _tool("title", "--text", "Demo", "--out", str(card), "--seconds", "1").returncode == 0
    (tmp_path / "list.txt").write_text("%s\n%s\n" % (card, fitted), encoding="utf-8")
    final = tmp_path / "final.mp4"
    cat = _tool("concat", "--list", str(tmp_path / "list.txt"), "--out", str(final))
    assert cat.returncode == 0, cat.stdout + cat.stderr
    audio = _audio_stream(final)
    assert (audio["codec_name"], audio["sample_rate"], audio["channels"]) == ("aac", "48000", 2)
    ok = _tool("verify", "--video", str(final), "--silent")
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert _kv(ok.stdout)["SILENT"] == "1" and "FAIL" not in ok.stdout
    plain = _tool("verify", "--video", str(final))
    assert plain.returncode == 1 and "LOUDNESS=FAIL" in plain.stdout


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe not on PATH")
def test_concat_of_a_clip_with_no_audio_stream_reports_silent_loudness_instead_of_failing(tmp_path):
    clip = _no_audio_clip(tmp_path / "scene.mp4")
    (tmp_path / "list.txt").write_text("%s\n" % clip, encoding="utf-8")
    final = tmp_path / "final.mp4"
    cat = _tool("concat", "--list", str(tmp_path / "list.txt"), "--out", str(final))
    assert cat.returncode == 0, cat.stdout + cat.stderr
    assert _kv(cat.stdout)["LOUDNESS"] == "silent"
    assert _audio_stream(final)["codec_name"] == "aac"


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe not on PATH")
def test_sidecar_places_chapters_at_the_real_offsets_and_writes_captions_only_with_a_narration_dir(tmp_path):
    card = _no_audio_clip(tmp_path / "title-card.mp4", 1)
    one = _no_audio_clip(tmp_path / "s1.mp4", 3)
    two = _no_audio_clip(tmp_path / "s2.mp4", 2)
    (tmp_path / "list.txt").write_text("%s\n\n%s\n%s\n" % (card, one, two), encoding="utf-8")
    sb = {"title": "Demo", "languages": ["vi_VN"], "lead_in_s": 0.5,
          "publish": {"vi_VN": {"title": "Trợ lý AI", "description": "Mô tả."}},
          "scenes": [{"id": "s1", "title": {"vi_VN": "Mở đầu"}, "narration": {"vi_VN": "Xin chào."}},
                     {"id": "s2", "title": {"vi_VN": "Tạo đơn"}, "narration": {"vi_VN": "Tạo một đơn hàng."}}]}
    (tmp_path / "sb.json").write_text(json.dumps(sb, ensure_ascii=False), encoding="utf-8")
    base = ["sidecar", "--storyboard", str(tmp_path / "sb.json"), "--lang", "vi_VN",
            "--list", str(tmp_path / "list.txt")]
    bare = _tool(*base, "--out-dir", str(tmp_path / "out1"))
    assert bare.returncode == 0, bare.stderr
    assert _kv(bare.stdout)["CAPTIONS"] == "none" and not (tmp_path / "out1" / "vi_VN.srt").exists()
    txt = (tmp_path / "out1" / "vi_VN.txt").read_text(encoding="utf-8")
    # the title card (1 s) is no chapter; it shifts the first chapter to 0:01 and the second to 0:04
    assert "0:01 Mở đầu" in txt and "0:04 Tạo đơn" in txt and "0:00" not in txt
    assert float(_kv(bare.stdout)["TOTAL_S"]) == pytest.approx(6.0, abs=0.3)
    narr = tmp_path / "narr"
    narr.mkdir()
    for sid in ("s1", "s2"):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1.5",
                        "-ac", "1", str(narr / ("%s.wav" % sid))], check=True, capture_output=True)
    full = _tool(*base, "--out-dir", str(tmp_path / "out2"), "--narration-dir", str(narr))
    assert full.returncode == 0, full.stderr
    srt = (tmp_path / "out2" / "vi_VN.srt").read_text(encoding="utf-8")
    assert "00:00:01,500 --> 00:00:02,800" in srt and "00:00:04,500 --> 00:00:05,800" in srt


def _cues(srt):
    """``[(start_s, end_s, text)]`` of an srt file."""
    def secs(stamp):
        h, m, rest = stamp.split(":")
        s, ms = rest.split(",")
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000

    out = []
    for block in srt.strip().split("\n\n"):
        lines = block.splitlines()
        start, end = lines[1].split(" --> ")
        out.append((secs(start), secs(end), "\n".join(lines[2:])))
    return out


def _sidecar_cues(tmp_path, narration, spoken=4.0):
    clip = _no_audio_clip(tmp_path / "s1.mp4", 6)
    (tmp_path / "list.txt").write_text("%s\n" % clip, encoding="utf-8")
    sb = {"title": "Demo", "languages": ["en_US"], "lead_in_s": 0.5,
          "publish": {"en_US": {"title": "T", "description": "D"}},
          "scenes": [{"id": "s1", "title": {"en_US": "One"}, "narration": {"en_US": narration}}]}
    (tmp_path / "sb.json").write_text(json.dumps(sb), encoding="utf-8")
    narr = tmp_path / "narr"
    narr.mkdir()
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=%s" % spoken,
                    "-ac", "1", str(narr / "s1.wav")], check=True, capture_output=True)
    proc = _tool("sidecar", "--storyboard", str(tmp_path / "sb.json"), "--lang", "en_US",
                 "--list", str(tmp_path / "list.txt"), "--out-dir", str(tmp_path / "out"),
                 "--narration-dir", str(narr))
    assert proc.returncode == 0, proc.stderr
    return _cues((tmp_path / "out" / "en_US.srt").read_text(encoding="utf-8"))


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe not on PATH")
def test_a_two_line_narration_yields_two_cues_that_split_the_spoken_span_by_characters(tmp_path):
    first, second = "Short line.", "A much longer second line of narration."
    cues = _sidecar_cues(tmp_path, first + "\n" + second, spoken=4.0)
    assert [c[2] for c in cues] == [first, second]
    (s1, e1, _), (s2, e2, _) = cues
    assert s1 == pytest.approx(0.5, abs=0.01)          # chapter start (0) plus the lead-in
    assert s2 == pytest.approx(e1, abs=0.01) and e1 <= s2   # contiguous, never overlapping
    share = len(first) / (len(first) + len(second))
    assert (e1 - s1) == pytest.approx(4.0 * share, abs=0.05)
    assert e2 == pytest.approx(0.5 + 4.0 - 0.2, abs=0.05)   # the last cue lifts 0.2 s early


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe not on PATH")
def test_a_one_line_narration_still_yields_one_cue_over_the_spoken_span(tmp_path):
    cues = _sidecar_cues(tmp_path, "Only one line here.", spoken=3.0)
    assert len(cues) == 1
    assert cues[0][0] == pytest.approx(0.5, abs=0.01) and cues[0][1] == pytest.approx(3.3, abs=0.05)


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe not on PATH")
def test_a_very_short_line_keeps_half_a_second_and_cues_still_do_not_overlap(tmp_path):
    cues = _sidecar_cues(tmp_path, "Hi.\nThis second line takes nearly all of the spoken time.", spoken=2.0)
    assert len(cues) == 2
    assert cues[0][1] - cues[0][0] >= 0.5 - 0.01
    assert cues[1][0] >= cues[0][1] - 0.001


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe not on PATH")
def test_concat_and_sidecar_refuse_a_list_line_that_is_not_an_existing_file_with_one_message(tmp_path):
    clip = _no_audio_clip(tmp_path / "title.mp4", 1)
    bad = "file '%s'" % clip   # ffmpeg's own syntax is not the list format
    (tmp_path / "list.txt").write_text("%s\n" % bad, encoding="utf-8")
    (tmp_path / "sb.json").write_text(json.dumps({"scenes": []}), encoding="utf-8")
    cat = _tool("concat", "--list", str(tmp_path / "list.txt"), "--out", str(tmp_path / "o.mp4"))
    side = _tool("sidecar", "--storyboard", str(tmp_path / "sb.json"), "--lang", "en_US",
                 "--list", str(tmp_path / "list.txt"), "--out-dir", str(tmp_path / "out"))
    expected = "ERROR=list: %s: not a file" % bad
    assert cat.returncode == 1 and expected in cat.stdout
    assert side.returncode == 1 and expected in side.stdout
    assert not (tmp_path / "o.mp4").exists()


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe not on PATH")
def test_thumbnail_of_a_missing_video_names_the_missing_file_not_the_size_cap(tmp_path):
    missing = tmp_path / "nope.mp4"
    proc = _tool("thumbnail", "--video", str(missing), "--out", str(tmp_path / "t.jpg"))
    assert proc.returncode == 1
    assert "ERROR=%s: not a file" % missing in proc.stdout and "2 MB" not in proc.stderr
