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


@pytest.fixture(scope="module")
def media(tmp_path_factory):
    """The synthetic inputs (read-only for every test): a 2 s 1080p clip and a 3 s narration, built once."""
    if not HAS_FFMPEG:
        pytest.skip("ffmpeg/ffprobe not on PATH")
    tmp_path = tmp_path_factory.mktemp("media")
    clip, narr = tmp_path / "clip.mp4", tmp_path / "narr.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=1920x1080:rate=25:duration=2",
                    "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "2", "-pix_fmt", "yuv420p", str(clip)],
                   check=True, capture_output=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
                    "-ac", "1", "-ar", "48000", "-sample_fmt", "s16", str(narr)], check=True, capture_output=True)
    return clip, narr


@pytest.fixture(scope="module")
def fitted_narration(media, tmp_path_factory):
    """`fit` of the clip to the 3 s narration, run once: the scene several tests read, concat or measure."""
    clip, narr = media
    out = tmp_path_factory.mktemp("fitted") / "fitted.mp4"
    proc = _tool("fit", "--clip", str(clip), "--narration", str(narr), "--out", str(out), "--max-silence", "10")
    assert proc.returncode == 0, proc.stderr
    return out, _kv(proc.stdout)


@pytest.fixture(scope="module")
def short_fit(media, tmp_path_factory):
    """`fit` of the clip to a 0.4 s narration (speaks 0.5-0.9 s of the 2 s clip), run once:
    returns (short wav, fitted scene, `fit` stdout)."""
    clip, _ = media
    d = tmp_path_factory.mktemp("short")
    wav, out = d / "short.wav", d / "fitted.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=0.4",
                    "-ac", "1", "-ar", "48000", "-sample_fmt", "s16", str(wav)], check=True, capture_output=True)
    proc = _tool("fit", "--clip", str(clip), "--narration", str(wav), "--out", str(out), "--max-silence", "5")
    assert proc.returncode == 0, proc.stderr
    return wav, out, proc.stdout


@pytest.fixture(scope="module")
def tool_facts():
    """`verify-tools`, asked once."""
    if not HAS_FFMPEG:
        pytest.skip("ffmpeg/ffprobe not on PATH")
    return _kv(_tool("verify-tools").stdout)


def test_fit_holds_the_last_frame_to_the_narration_and_concat_passes_the_profile(fitted_narration, tmp_path):
    fitted, facts = fitted_narration
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


def test_fit_reports_a_scene_that_moves_longer_than_the_silence_limit_with_nobody_speaking(
        media, short_fit, tmp_path):
    clip, _ = media
    short, _fitted, ok_stdout = short_fit
    out = tmp_path / "fitted.mp4"
    over = _tool("fit", "--clip", str(clip), "--narration", str(short), "--out", str(out),
                 "--lead-in", "0.5", "--max-silence", "1.0")
    assert over.returncode == 4 and "SILENCE=over" in over.stdout, over.stdout + over.stderr
    assert abs(float(_kv(over.stdout)["SILENT_S"]) - 1.1) < 0.15  # 2 s clip - 0.5 lead-in - 0.4 narration
    assert out.exists()  # the file is still written so the author can watch the silent stretch
    assert _kv(ok_stdout)["SILENCE"] == "ok"  # the same scene under a limit it fits (5 s)


def test_verify_tools_reports_the_card_renderer_the_filters_and_the_font_coverage(tool_facts):
    kv = tool_facts
    assert kv["TITLE_CARD"] in ("drawtext", "libass", "none") and kv["FILTER_loudnorm"] in ("ok", "missing")
    assert kv["FONT_VI_COVERAGE"] in ("ok", "missing", "unknown") or kv["FONT"] == "none"
    assert kv["VERDICT"] in ("pass", "fail")


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe not on PATH")
def test_the_title_card_renders_with_whichever_text_filter_this_ffmpeg_has(tmp_path, tool_facts):
    out = tmp_path / "title.mp4"
    proc = subprocess.run([sys.executable, str(TOOL), "title", "--text", "Trợ lý AI của Viindoo", "--out", str(out),
                           "--seconds", "1"], capture_output=True, text=True)
    tools = tool_facts
    if tools["TITLE_CARD"] == "none":
        assert proc.returncode == 1 and "neither" in proc.stderr
        return
    assert proc.returncode == 0, proc.stderr
    assert _kv(proc.stdout)["RENDERED_WITH"] == tools["TITLE_CARD"] and out.stat().st_size > 1000
    assert not (tmp_path / "title.mp4.ass").exists() and not (tmp_path / "title.mp4.txt").exists()


def test_two_takes_at_different_levels_come_out_at_one_loudness(media, fitted_narration, tmp_path):
    """A retake recorded louder or softer than its neighbours is brought to the same level before
    the mix: the fitted clips of a loud and a soft narration measure within 2 LU of each other."""
    import re
    clip, narr = media
    soft = tmp_path / "soft.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(narr), "-af", "volume=-18dB", "-ac", "1", "-ar", "48000",
                    "-sample_fmt", "s16", str(soft)], check=True, capture_output=True)
    soft_out = tmp_path / "soft-fitted.mp4"
    proc = _tool("fit", "--clip", str(clip), "--narration", str(soft), "--out", str(soft_out), "--max-silence", "5")
    assert proc.returncode == 0, proc.stderr
    levels = []
    for out in (fitted_narration[0], soft_out):
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
def test_the_music_bed_rides_under_the_narration_and_the_audition_renders_dry_and_wet_samples(
        media, fitted_narration, tmp_path):
    _clip, narr = media
    fitted = fitted_narration[0]
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


@pytest.fixture(scope="module")
def pace_clip(tmp_path_factory):
    """The one 6 s clip every pacing test cuts; nothing writes to it."""
    if not HAS_FFMPEG:
        pytest.skip("ffmpeg/ffprobe not on PATH")
    clip = tmp_path_factory.mktemp("pace") / "pace-clip.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=25:duration=6",
                    "-t", "6", "-pix_fmt", "yuv420p", str(clip)], check=True, capture_output=True)
    return clip


@pytest.fixture
def pace(tmp_path, pace_clip):
    """`_pace` bound to this test's directory and the shared clip."""
    def run(spans, *extra):
        return _pace(tmp_path, pace_clip, spans, *extra)
    return run


def _pace(tmp_path, clip, spans, *extra):
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
def test_a_long_wait_is_squeezed_into_the_squeeze_seconds_and_cut_when_the_squeeze_is_zero(pace):
    # 6 s clip, 4 s wait: 1 s kept + 3 s squeezed into 1 s + 2 s around it = 4 s; cut instead = 3 s
    proc, out = pace(WAIT, "--wait-keep", "1", "--wait-squeeze", "1")
    assert proc.returncode == 0, proc.stderr
    assert _length(out) == pytest.approx(4.0, abs=0.3)
    assert _kv(proc.stdout)["SPANS"] == "1"
    proc, out = pace(WAIT, "--wait-keep", "1", "--wait-squeeze", "0")
    assert proc.returncode == 0, proc.stderr
    assert _length(out) == pytest.approx(3.0, abs=0.3)


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe not on PATH")
def test_a_wait_inside_a_must_see_range_plays_in_full_and_is_counted(pace):
    proc, out = pace(WAIT, "--wait-keep", "1", "--wait-squeeze", "0", "--must-see", "2.0,3.0")
    assert proc.returncode == 0, proc.stderr
    assert _length(out) == pytest.approx(6.0, abs=0.3)
    assert _kv(proc.stdout)["MUST_SEE_KEPT"] == "1"


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe not on PATH")
def test_a_voice_span_is_kept_at_normal_speed_and_counted(pace):
    proc, out = pace([{"kind": "voice_out", "start": 1.0, "end": 4.0}])
    assert proc.returncode == 0, proc.stderr
    assert _length(out) == pytest.approx(6.0, abs=0.3)
    assert _kv(proc.stdout)["SPANS"] == "1"


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe not on PATH")
def test_a_take_that_showed_a_key_field_is_refused_and_writes_nothing(pace):
    proc, out = pace(WAIT + [{"kind": "key_visible", "start": 5.2, "end": 5.6}])
    assert proc.returncode == 6 and _kv(proc.stdout)["KEY_VISIBLE"] == "1"
    assert not out.exists()


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe not on PATH")
def test_a_voice_track_is_audible_at_its_offset_in_the_fitted_scene(media, short_fit, tmp_path):
    clip, _ = media
    short, plain, _ = short_fit  # speaks 0.5-0.9 s, so 1.1-1.9 s holds only the extra voice
    voice = tmp_path / "voice.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=880:duration=1.0",
                    "-ac", "1", "-ar", "48000", "-sample_fmt", "s16", str(voice)], check=True, capture_output=True)

    def window_db(out):
        import re
        err = subprocess.run(["ffmpeg", "-ss", "1.1", "-t", "0.8", "-i", str(out), "-af", "volumedetect", "-f", "null", "-"],
                             capture_output=True, text=True).stderr
        m = re.search(r"mean_volume: (-?[\d.]+|-inf) dB", err)
        assert m, err[-300:]
        return float(m.group(1)) if m.group(1) != "-inf" else -120.0

    mixed = tmp_path / "mixed.mp4"
    proc = _tool("fit", "--clip", str(clip), "--narration", str(short), "--max-silence", "5",
                 "--out", str(mixed), "--voice", "%s@1.0" % voice)
    assert proc.returncode == 0, proc.stderr
    assert _kv(proc.stdout)["VOICES"] == "1"
    assert window_db(plain) < -60.0 and window_db(mixed) > -40.0


# --------------------------------------------------------------------------- silent footage
@pytest.fixture(scope="module")
def silent(tmp_path_factory):
    """`silent(seconds)`: what the recorder writes - a picture and no audio stream at all. One file per
    length, built on first use and shared: no test writes to it."""
    if not HAS_FFMPEG:
        pytest.skip("ffmpeg/ffprobe not on PATH")
    made = {}

    def get(seconds=2):
        if seconds not in made:
            path = tmp_path_factory.mktemp("silent") / ("silent-%s.mp4" % seconds)
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                            "testsrc=size=1920x1080:rate=25:duration=%s" % seconds, "-t", str(seconds),
                            "-pix_fmt", "yuv420p", str(path)], check=True, capture_output=True)
            made[seconds] = path
        return made[seconds]
    return get


def _audio_stream(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
                          "stream=codec_name,sample_rate,channels", "-of", "json", str(path)],
                         capture_output=True, text=True, check=True).stdout
    streams = json.loads(out)["streams"]
    return streams[0] if streams else None


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe not on PATH")
def test_a_silent_clip_goes_through_fit_and_concat_with_a_title_card_and_verifies_as_silent(tmp_path, silent, tool_facts):
    clip = silent()
    fitted = tmp_path / "fitted.mp4"
    fit = _tool("fit", "--clip", str(clip), "--out", str(fitted))
    assert fit.returncode == 0, fit.stderr
    facts = _kv(fit.stdout)
    assert facts["NARRATION"] == "none" and float(facts["DURATION_S"]) == pytest.approx(2.0, abs=0.1)
    assert float(facts["HOLD_S"]) == 0.0
    assert _audio_stream(fitted)["codec_name"] == "aac"
    card = tmp_path / "title.mp4"
    if tool_facts["TITLE_CARD"] == "none":
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
def test_concat_of_a_clip_with_no_audio_stream_reports_silent_loudness_instead_of_failing(tmp_path, silent):
    clip = silent()
    (tmp_path / "list.txt").write_text("%s\n" % clip, encoding="utf-8")
    final = tmp_path / "final.mp4"
    cat = _tool("concat", "--list", str(tmp_path / "list.txt"), "--out", str(final))
    assert cat.returncode == 0, cat.stdout + cat.stderr
    assert _kv(cat.stdout)["LOUDNESS"] == "silent"
    assert _audio_stream(final)["codec_name"] == "aac"


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe not on PATH")
def test_sidecar_places_scenes_at_the_real_offsets_and_writes_captions_only_with_a_narration_dir(tmp_path, silent):
    card = tmp_path / "title-card.mp4"  # the writer tells a title card by its name
    card.symlink_to(silent(1))
    one = silent(3)
    two = silent(2)
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
    facts = _kv(bare.stdout)
    assert facts["CAPTIONS"] == "none" and not (tmp_path / "out1" / "vi_VN.srt").exists()
    # a 6 s video cannot hold three chapters of 10 s: none are written, the description is the text alone
    assert (tmp_path / "out1" / "vi_VN.txt").read_text(encoding="utf-8") == "Mô tả.\n"
    assert facts["CHAPTERS"] == "0"
    assert facts["TITLE"] == "Trợ lý AI"
    assert float(facts["TOTAL_S"]) == pytest.approx(6.0, abs=0.3)
    # the title card (1 s) shifts the first scene to 1 s; the thumbnail frame is 3 s into it
    assert float(facts["THUMBNAIL_AT_S"]) == pytest.approx(4.0, abs=0.05)
    narr = tmp_path / "narr"
    narr.mkdir()
    for sid in ("s1", "s2"):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1.5",
                        "-ac", "1", str(narr / ("%s.wav" % sid))], check=True, capture_output=True)
    full = _tool(*base, "--out-dir", str(tmp_path / "out2"), "--narration-dir", str(narr))
    assert full.returncode == 0, full.stderr
    srt = (tmp_path / "out2" / "vi_VN.srt").read_text(encoding="utf-8")
    assert "00:00:01,500 --> 00:00:02,800" in srt and "00:00:04,500 --> 00:00:05,800" in srt
    assert "CAPTION_FALLBACK" not in _kv(full.stdout)   # one line per scene: nothing to detect


@pytest.fixture(scope="module")
def video_module():
    """video_publish.py imported as a module, for the rules that are pure functions."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("video_publish_under_test", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_chapters_start_at_zero_last_ten_seconds_and_come_in_threes_or_not_at_all(video_module):
    scenes = [(1.0, "A"), (13.0, "B"), (17.0, "C"), (28.0, "D"), (40.0, "E")]
    # title card 1 s, then A 12 s, B 4 s, C 11 s, D 12 s, E 3 s
    chapters = video_module._chapters(scenes, 43.0)
    assert [c[0] for c in chapters] == [0.0, 13.0, 28.0]          # first at 0:00; B, D open chapters; C, E join the one before
    assert [c[1] for c in chapters] == ["A", "B", "D"]
    starts = [c[0] for c in chapters] + [43.0]
    assert all(b - a >= 10 for a, b in zip(starts, starts[1:]))
    assert video_module._chapters(scenes, 25.0) == []             # fewer than three possible: none at all
    assert video_module._chapters([], 30.0) == []


def test_chapter_times_from_one_hour_on_read_h_mm_ss(video_module):
    assert video_module._yt_time(0) == "0:00"
    assert video_module._yt_time(599) == "9:59"
    assert video_module._yt_time(3599) == "59:59"
    assert video_module._yt_time(3600) == "1:00:00"
    assert video_module._yt_time(3725.9) == "1:02:05"


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe not on PATH")
def test_the_description_file_holds_the_text_then_the_chapters_then_the_links_and_no_header_lines(tmp_path, silent):
    card = tmp_path / "title-card.mp4"
    card.symlink_to(silent(1))
    clips = [silent(12), silent(4), silent(11), silent(12), silent(3)]
    (tmp_path / "list.txt").write_text("\n".join(str(c) for c in [card] + clips) + "\n", encoding="utf-8")
    sb = {"title": "Demo", "languages": ["en_US"],
          "publish": {"en_US": {"title": "The Video", "description": "What it shows."}},
          "scenes": [{"id": "s%d" % i, "title": {"en_US": name}} for i, name in enumerate("ABCDE", 1)]}
    (tmp_path / "sb.json").write_text(json.dumps(sb), encoding="utf-8")
    links = ["https://example.com/docs", "https://example.com/app"]
    proc = _tool("sidecar", "--storyboard", str(tmp_path / "sb.json"), "--lang", "en_US",
                 "--list", str(tmp_path / "list.txt"), "--out-dir", str(tmp_path / "out"),
                 "--link", links[0], "--link", links[1])
    assert proc.returncode == 0, proc.stderr
    facts = _kv(proc.stdout)
    txt = (tmp_path / "out" / "en_US.txt").read_text(encoding="utf-8")
    assert txt.split("\n\n") == ["What it shows.", "0:00 A\n0:13 B\n0:28 D", "\n".join(links) + "\n"]
    assert "TITLE" not in txt and "CHAPTERS" not in txt
    assert facts["TITLE"] == "The Video" and facts["CHAPTERS"] == "3"
    assert float(facts["THUMBNAIL_AT_S"]) == pytest.approx(4.0, abs=0.05)   # the first scene starts at 1 s
    # no chapters: the links follow the text directly
    short = tmp_path / "list2.txt"
    short.write_text("%s\n" % clips[1], encoding="utf-8")
    proc = _tool("sidecar", "--storyboard", str(tmp_path / "sb.json"), "--lang", "en_US", "--list", str(short),
                 "--out-dir", str(tmp_path / "out2"), "--link", links[0])
    assert proc.returncode == 0, proc.stderr
    assert (tmp_path / "out2" / "en_US.txt").read_text(encoding="utf-8").split("\n\n") == [
        "What it shows.", links[0] + "\n"]


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


def _sidecar_cues(tmp_path, silent, narration, spoken=4.0, wav_graph=None):
    """The cues and the KEY=VALUE facts `sidecar` gives one scene whose narration clip is a steady tone
    of `spoken` seconds, or what the lavfi graph `wav_graph` builds."""
    clip = silent(12)
    (tmp_path / "list.txt").write_text("%s\n" % clip, encoding="utf-8")
    sb = {"title": "Demo", "languages": ["en_US"], "lead_in_s": 0.5,
          "publish": {"en_US": {"title": "T", "description": "D"}},
          "scenes": [{"id": "s1", "title": {"en_US": "One"}, "narration": {"en_US": narration}}]}
    (tmp_path / "sb.json").write_text(json.dumps(sb), encoding="utf-8")
    narr = tmp_path / "narr"
    narr.mkdir()
    wav = str(narr / "s1.wav")
    if wav_graph:
        make = ["-filter_complex", wav_graph, "-map", "[a]"]
    else:
        make = ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=%s" % spoken]
    subprocess.run(["ffmpeg", "-v", "error", "-y"] + make + ["-ac", "1", wav], check=True, capture_output=True)
    proc = _tool("sidecar", "--storyboard", str(tmp_path / "sb.json"), "--lang", "en_US",
                 "--list", str(tmp_path / "list.txt"), "--out-dir", str(tmp_path / "out"),
                 "--narration-dir", str(narr))
    assert proc.returncode == 0, proc.stderr
    return _cues((tmp_path / "out" / "en_US.srt").read_text(encoding="utf-8")), _kv(proc.stdout)


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe not on PATH")
def test_a_two_line_narration_without_a_gap_splits_the_spoken_span_by_characters_and_names_the_scene(tmp_path, silent):
    first, second = "Short line.", "A much longer second line of narration."
    cues, facts = _sidecar_cues(tmp_path, silent, first + "\n" + second, spoken=4.0)
    assert facts["CAPTION_FALLBACK"] == "s1"    # no silence to find: the proportional split, and it says so
    assert [c[2] for c in cues] == [first, second]
    (s1, e1, _), (s2, e2, _) = cues
    assert s1 == pytest.approx(0.5, abs=0.01)          # chapter start (0) plus the lead-in
    assert s2 == pytest.approx(e1, abs=0.01) and e1 <= s2   # contiguous, never overlapping
    share = len(first) / (len(first) + len(second))
    assert (e1 - s1) == pytest.approx(4.0 * share, abs=0.05)
    assert e2 == pytest.approx(0.5 + 4.0 - 0.2, abs=0.05)   # the last cue lifts 0.2 s early


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe not on PATH")
def test_a_one_line_narration_still_yields_one_cue_over_the_spoken_span(tmp_path, silent):
    cues, facts = _sidecar_cues(tmp_path, silent, "Only one line here.", spoken=3.0)
    assert len(cues) == 1 and "CAPTION_FALLBACK" not in facts
    assert cues[0][0] == pytest.approx(0.5, abs=0.01) and cues[0][1] == pytest.approx(3.3, abs=0.05)


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe not on PATH")
def test_a_very_short_line_keeps_half_a_second_and_cues_still_do_not_overlap(tmp_path, silent):
    cues, _ = _sidecar_cues(tmp_path, silent, "Hi.\nThis second line takes nearly all of the spoken time.", spoken=2.0)
    assert len(cues) == 2
    assert cues[0][1] - cues[0][0] >= 0.5 - 0.01
    assert cues[1][0] >= cues[0][1] - 0.001


# three sentences: tone 0-1.2 s, silence, tone 1.8-3.3 s, silence, tone 3.8-4.8 s
SENTENCES_GRAPH = ("sine=frequency=440:sample_rate=48000:duration=1.2[t1];"
                   "anullsrc=r=48000:cl=mono,atrim=0:0.6[g1];"
                   "sine=frequency=330:sample_rate=48000:duration=1.5[t2];"
                   "anullsrc=r=48000:cl=mono,atrim=0:0.5[g2];"
                   "sine=frequency=550:sample_rate=48000:duration=1.0[t3];"
                   "[t1][g1][t2][g2][t3]concat=n=5:v=0:a=1[a]")
SENTENCE_STARTS = (0.0, 1.8, 3.8)


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe not on PATH")
def test_caption_cues_start_where_the_narration_clip_starts_each_sentence(tmp_path, silent):
    lines = "First sentence here.\nA second and a longer sentence.\nThird one."
    cues, facts = _sidecar_cues(tmp_path, silent, lines, wav_graph=SENTENCES_GRAPH)
    assert "CAPTION_FALLBACK" not in facts
    assert [c[2] for c in cues] == lines.splitlines()
    for (start, _end, _text), known in zip(cues, SENTENCE_STARTS):
        assert start == pytest.approx(0.5 + known, abs=0.1)   # the chapter starts at 0, the lead-in is 0.5 s
    assert all(b[0] >= a[1] - 0.001 for a, b in zip(cues, cues[1:]))


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe not on PATH")
def test_when_the_gaps_do_not_match_the_line_count_the_scene_keeps_the_proportional_split_and_is_named(tmp_path, silent):
    # two lines of text over a clip with three sentences
    cues, facts = _sidecar_cues(tmp_path, silent, "Short line.\nA much longer second line of narration.",
                                wav_graph=SENTENCES_GRAPH)
    assert facts["CAPTION_FALLBACK"] == "s1"
    share = len("Short line.") / (len("Short line.") + len("A much longer second line of narration."))
    assert (cues[0][1] - cues[0][0]) == pytest.approx(4.8 * share, abs=0.05)


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe not on PATH")
def test_concat_and_sidecar_refuse_a_list_line_that_is_not_an_existing_file_with_one_message(tmp_path, silent):
    clip = silent(1)
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


# --------------------------------------------------------------------------- audio timeline and frame size
AAC_FRAME_S = 1024 / 48000


def _probe_lines(path, entries, select):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", select, "-show_entries", entries,
                          "-of", "default=noprint_wrappers=1:nokey=1", str(path)], capture_output=True, text=True)
    return out.stdout.split()


def _audio_steps(path):
    """The step (s) between each pair of consecutive audio packets."""
    times = [float(x) for x in _probe_lines(path, "packet=pts_time", "a:0")]
    return [b - a for a, b in zip(times, times[1:])]


def _stream_seconds(path, select):
    return float(_probe_lines(path, "stream=duration", select)[0])


def _decoded_samples(path):
    import array
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:a:0", "-ac", "1", "-f", "s16le", "-"],
                         capture_output=True).stdout
    samples = array.array("h")
    samples.frombytes(raw[:len(raw) // 2 * 2])
    return samples


def _first_loud_s(path, level=2000):
    """When the decoded audio first rises above `level` (of 32768)."""
    samples = _decoded_samples(path)
    return next(i for i, v in enumerate(samples) if abs(v) > level) / 48000


def _assert_gapless(path, fps=25):
    """The audio packet timeline has one AAC frame between consecutive packets, the decoded audio is as
    long as the stream, and audio and video end within one video frame of each other."""
    steps = _audio_steps(path)
    assert len(steps) > 10
    assert max(abs(x - AAC_FRAME_S) for x in steps) <= 0.001, [round(x, 4) for x in steps if abs(x - AAC_FRAME_S) > 0.001]
    audio = _stream_seconds(path, "a:0")
    assert abs(len(_decoded_samples(path)) / 48000 - audio) <= AAC_FRAME_S
    assert abs(audio - _stream_seconds(path, "v:0")) <= 1.0 / fps


@pytest.fixture(scope="module")
def long_fit(tmp_path_factory):
    """A 6.5 s clip fitted to a 5.42 s narration, with and without an extra voice track, and fitted
    without narration: (plain, voiced, silent_fit)."""
    if not HAS_FFMPEG:
        pytest.skip("ffmpeg/ffprobe not on PATH")
    d = tmp_path_factory.mktemp("longfit")
    clip, narr, voice = d / "clip.mp4", d / "narr.wav", d / "voice.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=1920x1080:rate=25:duration=6.5",
                    "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "6.5", "-pix_fmt", "yuv420p", str(clip)],
                   check=True, capture_output=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=5.42",
                    "-ac", "1", "-ar", "48000", "-sample_fmt", "s16", str(narr)], check=True, capture_output=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=880:duration=1.0",
                    "-ac", "1", "-ar", "48000", "-sample_fmt", "s16", str(voice)], check=True, capture_output=True)
    plain, voiced, silent_fit = d / "plain.mp4", d / "voiced.mp4", d / "silent.mp4"
    for out, extra in ((plain, []), (voiced, ["--voice", "%s@4.0" % voice])):
        proc = _tool("fit", "--clip", str(clip), "--narration", str(narr), "--out", str(out), "--max-silence", "10", *extra)
        assert proc.returncode == 0, proc.stderr
    proc = _tool("fit", "--clip", str(clip), "--out", str(silent_fit))
    assert proc.returncode == 0, proc.stderr
    return plain, voiced, silent_fit


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe not on PATH")
@pytest.mark.parametrize("which", [0, 1, 2], ids=["narration", "narration-and-voice", "silent-clip"])
def test_a_fitted_scene_has_a_continuous_audio_timeline_and_the_narration_starts_at_the_lead_in(long_fit, which):
    fitted = long_fit[which]
    _assert_gapless(fitted)
    if which != 2:
        assert _first_loud_s(fitted) == pytest.approx(0.5, abs=0.06)   # the lead-in is 0.5 s


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe not on PATH")
def test_a_concatenated_deliverable_has_a_continuous_audio_timeline_and_passes_verify(long_fit, tmp_path):
    plain, voiced, silent_fit = long_fit
    (tmp_path / "list.txt").write_text("%s\n%s\n%s\n%s\n" % (plain, silent_fit, voiced, plain), encoding="utf-8")
    final = tmp_path / "final.mp4"
    cat = _tool("concat", "--list", str(tmp_path / "list.txt"), "--out", str(final))
    assert cat.returncode == 0, cat.stderr
    _assert_gapless(final)
    # the narration of the last scene starts 0.5 s after that scene starts (the three scenes before it set the offset)
    last_start = sum(_stream_seconds(c, "v:0") for c in (plain, silent_fit, voiced))
    tail = _decoded_samples(final)[int(round(last_start * 48000)):]
    assert next(i for i, v in enumerate(tail) if abs(v) > 2000) / 48000 == pytest.approx(0.5, abs=0.06)
    ver = _tool("verify", "--video", str(final))
    assert ver.returncode == 0, ver.stdout
    assert "AUDIO_PACKETS=OK" in ver.stdout and "AUDIO_SAMPLES=OK" in ver.stdout


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe not on PATH")
def test_verify_fails_an_audio_stream_with_holes_in_its_packet_timeline(long_fit, tmp_path):
    """A narration through single-pass loudnorm then adelay leaves a timestamp hole in front of the voice and
    another inside it: the decoded samples are all there but play out of step with the picture."""
    plain, _voiced, _silent = long_fit
    bad = tmp_path / "bad.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(plain.parent / "clip.mp4"), "-i", str(plain.parent / "narr.wav"),
                    "-filter_complex",
                    "[1:a]loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000,adelay=500|500,apad=whole_dur=6.5[a]",
                    "-map", "0:v", "-map", "[a]", "-t", "6.5", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                    "-ar", "48000", "-ac", "2", str(bad)], check=True, capture_output=True)
    assert max(abs(x - AAC_FRAME_S) for x in _audio_steps(bad)) > 0.05   # the file really has the hole
    ver = _tool("verify", "--video", str(bad))
    assert ver.returncode == 1
    facts = _kv(ver.stdout)
    assert facts["AUDIO_PACKETS"] == "FAIL" and facts["AUDIO_SAMPLES"] == "FAIL"
    good = _kv(_tool("verify", "--video", str(plain)).stdout)
    assert good["AUDIO_PACKETS"] == "OK" and good["AUDIO_SAMPLES"] == "OK"


def _luma_bytes(path, crop, at=0.5):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(at), "-i", str(path), "-frames:v", "1", "-vf",
                          "crop=%s,format=gray" % crop, "-f", "rawvideo", "-"], capture_output=True).stdout
    return list(raw)


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe not on PATH")
@pytest.mark.parametrize("size,padded", [("1280x800", True), ("2560x1440", False), ("640x360", False)])
def test_a_take_of_any_frame_size_is_fitted_to_the_profile_size_and_the_deliverable_verifies(
        media, tmp_path, size, padded):
    _clip, narr = media
    take = tmp_path / "take.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=white:size=%s:rate=25:duration=2" % size,
                    "-t", "2", "-pix_fmt", "yuv420p", str(take)], check=True, capture_output=True)
    fitted = tmp_path / "fitted.mp4"
    proc = _tool("fit", "--clip", str(take), "--narration", str(narr), "--out", str(fitted), "--max-silence", "10")
    assert proc.returncode == 0, proc.stderr
    assert _probe_lines(fitted, "stream=width,height", "v:0") == ["1920", "1080"]
    edge = _luma_bytes(fitted, "16:200:0:400")   # the left edge: black bars when the aspect differs, picture otherwise
    assert (max(edge) <= 20) == padded
    other = tmp_path / "other.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(fitted), "-c", "copy", str(other)], check=True, capture_output=True)
    (tmp_path / "list.txt").write_text("%s\n%s\n" % (fitted, other), encoding="utf-8")
    final = tmp_path / "final.mp4"
    cat = _tool("concat", "--list", str(tmp_path / "list.txt"), "--out", str(final))
    assert cat.returncode == 0, cat.stderr
    ver = _tool("verify", "--video", str(final))
    assert ver.returncode == 0, ver.stdout


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe not on PATH")
def test_a_zoom_on_a_take_larger_than_the_profile_renders_at_the_profile_size_from_the_takes_own_pixels(tmp_path):
    take = tmp_path / "take.mp4"   # one-pixel stripes: the only way to see them is to read the take's own pixels
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "nullsrc=s=3840x2160:r=10:d=1",
                    "-vf", "geq=lum='if(mod(X,2),235,16)':cb=128:cr=128", "-t", "1", "-pix_fmt", "yuv420p", "-crf", "10",
                    str(take)], check=True, capture_output=True)
    zoomed = tmp_path / "zoomed.mp4"
    proc = _tool("zoom", "--clip", str(take), "--focus", "960,540,1920,1080", "--from", "0.2", "--to", "0.9",
                 "--factor", "2", "--ramp", "0.1", "--out", str(zoomed))
    assert proc.returncode == 0, proc.stderr
    assert _kv(proc.stdout)["SIZE"] == "1920x1080"
    assert _probe_lines(zoomed, "stream=width,height", "v:0") == ["1920", "1080"]
    mid = _luma_bytes(zoomed, "400:200:760:440", at=0.55)
    mean = sum(mid) / len(mid)
    spread = (sum((v - mean) ** 2 for v in mid) / len(mid)) ** 0.5
    assert spread > 60, spread   # a picture shrunk before the zoom is flat grey here (spread under 30)


# --------------------------------------------------------------------------- pacing
@pytest.mark.parametrize("events,must_see,expected", [
    ([{"kind": "load", "start": 0.0, "end": 0.4}, {"kind": "wait", "start": 0.45, "end": 1.0},
      {"kind": "travel", "start": 1.5, "end": 2.0}], [], 1.0),                       # load and wait: the head ends with the wait
    ([{"kind": "load", "start": 0.0, "end": 0.4}, {"kind": "wait", "start": 3.0, "end": 4.0}], [], 0.4),   # a later wait is not the head
    ([{"kind": "travel", "start": 0.0, "end": 0.5}, {"kind": "load", "start": 0.6, "end": 1.0}], [], 0.0),  # starts on an action
    ([{"kind": "load", "start": 0.0, "end": 1.0}, {"kind": "wait", "start": 1.1, "end": 2.0}], [(0.5, 1.5)], 0.5),  # never into a must-see range
    ([], [], 0.0),
])
def test_the_head_of_a_take_ends_with_the_leading_run_of_load_and_wait_spans(video_module, events, must_see, expected):
    assert video_module._head_end(events, must_see) == pytest.approx(expected)


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe not on PATH")
def test_trim_head_cuts_the_clip_to_the_first_rendered_frame_and_reports_the_cut(pace):
    spans = [{"kind": "load", "start": 0.0, "end": 0.4}, {"kind": "wait", "start": 0.45, "end": 1.0}]
    kept, whole = pace(spans, "--travel", "1")
    assert kept.returncode == 0, kept.stderr
    assert float(_kv(kept.stdout)["HEAD_CUT_S"]) == 0.0 and _length(whole) == pytest.approx(6.0, abs=0.2)
    proc, out = pace(spans, "--travel", "1", "--trim-head")
    assert proc.returncode == 0, proc.stderr
    assert float(_kv(proc.stdout)["HEAD_CUT_S"]) == pytest.approx(1.0)
    assert _length(out) == pytest.approx(5.0, abs=0.2)


def _sine(path, seconds):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=%s" % seconds,
                    "-ac", "1", "-ar", "48000", "-sample_fmt", "s16", str(path)], check=True, capture_output=True)


HOLD = [{"kind": "hold", "start": 1.0, "end": 5.0}]


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe not on PATH")
def test_a_hold_is_shortened_so_the_scene_ends_half_a_second_after_the_narration(pace, tmp_path):
    narration = tmp_path / "n.wav"
    _sine(narration, 2.0)
    proc, out = pace(HOLD, "--narration", str(narration), "--lead-in", "0.5")
    assert proc.returncode == 0, proc.stderr
    facts = _kv(proc.stdout)
    assert _length(out) == pytest.approx(0.5 + 2.0 + 0.5, abs=0.15)     # lead-in + narration + tail
    assert float(facts["HOLD_CUT_S"]) == pytest.approx(3.0, abs=0.15)
    plain, out2 = pace(HOLD)                                            # no narration: a hold plays in full
    assert _length(out2) == pytest.approx(6.0, abs=0.2) and float(_kv(plain.stdout)["HOLD_CUT_S"]) == 0.0
    _sine(narration, 7.0)                                               # a narration longer than the footage: nothing to cut
    long_proc, out3 = pace(HOLD, "--narration", str(narration))
    assert float(_kv(long_proc.stdout)["HOLD_CUT_S"]) == 0.0 and _length(out3) == pytest.approx(6.0, abs=0.2)


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe not on PATH")
def test_a_hold_never_shrinks_below_the_floor_and_a_must_see_hold_is_untouched(pace, tmp_path):
    narration = tmp_path / "n.wav"
    _sine(narration, 0.2)
    proc, out = pace(HOLD, "--narration", str(narration), "--hold-floor", "0.8")
    assert proc.returncode == 0, proc.stderr
    assert float(_kv(proc.stdout)["HOLD_CUT_S"]) == pytest.approx(4.0 - 0.8, abs=0.1)   # the hold keeps its floor
    assert _length(out) == pytest.approx(6.0 - 3.2, abs=0.2)
    proc, out = pace(HOLD, "--narration", str(narration), "--must-see", "2.0,3.0")
    assert float(_kv(proc.stdout)["HOLD_CUT_S"]) == 0.0 and _length(out) == pytest.approx(6.0, abs=0.2)


def _events_file(tmp_path, name, spans):
    path = tmp_path / name
    path.write_text(json.dumps([{"kind": k, "start": s, "end": e} for k, s, e in spans]))
    return path


def test_times_of_one_take_map_onto_another_by_event_boundaries(tmp_path):
    a = _events_file(tmp_path, "a.json", [("load", 0.0, 1.0), ("typing", 2.0, 3.0), ("wait", 4.0, 6.0)])
    b = _events_file(tmp_path, "b.json", [("load", 0.0, 2.0), ("typing", 3.0, 5.0), ("wait", 6.0, 7.0)])
    proc = _tool("map-times", "--events-from", str(a), "--events-to", str(b), "--times", "0.5,1.0;2.5,3.0;5.0,6.0;7.0,8.0")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    facts = _kv(proc.stdout)
    mapped = [tuple(float(x) for x in r.split(",")) for r in facts["TIMES"].split(";")]
    # inside the load span 0-1 -> 0-2; the typing span 2-3 -> 3-5; the wait 4-6 -> 6-7; after the last event the offset holds
    assert mapped == [pytest.approx(r) for r in [(1.0, 2.0), (4.0, 5.0), (6.5, 7.0), (8.0, 9.0)]]
    assert facts["ANCHORS"] == "6"


def test_times_do_not_map_between_takes_whose_event_kinds_differ(tmp_path):
    a = _events_file(tmp_path, "a.json", [("load", 0.0, 1.0), ("typing", 2.0, 3.0)])
    b = _events_file(tmp_path, "b.json", [("load", 0.0, 1.0), ("wait", 2.0, 3.0)])
    proc = _tool("map-times", "--events-from", str(a), "--events-to", str(b), "--times", "0.5,1.0")
    assert proc.returncode == 1 and "ERROR" in _kv(proc.stdout) and "TIMES" not in _kv(proc.stdout)


# --------------------------------------------------------------------------- tempo
def _tone_hz(path):
    samples = _decoded_samples(path)
    crossings = sum(1 for a, b in zip(samples, samples[1:]) if a < 0 <= b)
    return crossings / (len(samples) / 48000)


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe not on PATH")
def test_tempo_speeds_the_narration_by_the_factor_keeps_the_pitch_and_prints_the_factor(media, tmp_path):
    _clip, narr = media   # a 3 s tone at 440 Hz
    out = tmp_path / "fast.wav"
    proc = _tool("tempo", "--narration", str(narr), "--out", str(out), "--factor", "1.08")
    assert proc.returncode == 0, proc.stderr
    facts = _kv(proc.stdout)
    assert float(facts["FACTOR"]) == 1.08
    assert float(facts["IN_DURATION_S"]) == pytest.approx(3.0, abs=0.01)
    assert float(facts["DURATION_S"]) == pytest.approx(3.0 / 1.08, abs=0.02)
    assert _tone_hz(out) == pytest.approx(440, abs=6)
    bad = _tool("tempo", "--narration", str(narr), "--out", str(tmp_path / "x.wav"), "--factor", "4")
    assert bad.returncode == 1 and not (tmp_path / "x.wav").exists()


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe not on PATH")
def test_clips_whose_audio_is_a_little_shorter_or_longer_than_their_picture_join_without_a_step(tmp_path):
    """Each join of AAC clips whose audio and video lengths differ by a fraction of a frame is where a
    packet step appears when the clips are joined as files."""
    video = tmp_path / "v.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=1920x1080:rate=25:duration=2",
                    "-pix_fmt", "yuv420p", str(video)], check=True, capture_output=True)
    clips = []
    for seconds in ("1.97", "2.03"):
        audio, muxed = tmp_path / ("a%s.m4a" % seconds), tmp_path / ("m%s.mp4" % seconds)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=300:sample_rate=48000:duration=" + seconds,
                        "-ac", "2", "-c:a", "aac", str(audio)], check=True, capture_output=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-i", str(audio), "-map", "0:v", "-map", "1:a",
                        "-c", "copy", str(muxed)], check=True, capture_output=True)
        clips.append(muxed)
    (tmp_path / "list.txt").write_text("\n".join(str(c) for c in clips + clips[:1]) + "\n", encoding="utf-8")
    final = tmp_path / "final.mp4"
    cat = _tool("concat", "--list", str(tmp_path / "list.txt"), "--out", str(final))
    assert cat.returncode == 0, cat.stderr
    _assert_gapless(final)
    assert float(_kv(cat.stdout)["DURATION_S"]) == pytest.approx(6.0, abs=0.04)
