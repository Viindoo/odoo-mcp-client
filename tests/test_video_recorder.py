"""`scripts/lib/video_record.py` and `scripts/recorder/record.mjs` - one browser drives and records a scene.

Runs a real Chromium against a fixture site on 127.0.0.1, so the module is skipped unless node >= 20
and the pinned playwright library are present (`ODOO_AI_RECORDER_NODE_PATH` points a developer at a
node_modules that holds it).
"""
from __future__ import annotations

import functools
import http.server
import json
import math
import re
import shutil
import struct
import subprocess
import sys
import threading
import time
import wave
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "lib" / "video_record.py"


def _run(*args, timeout=240):
    return subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True, timeout=timeout)


def _kv(stdout):
    return dict(line.split("=", 1) for line in stdout.splitlines() if "=" in line)


pytestmark = pytest.mark.skipif(
    _run("install-check").returncode != 0, reason="node >= 20 and the pinned playwright library are not installed"
)

INDEX = """<!doctype html><meta charset=utf-8><title>fixture</title>
<input id=q type=text aria-label=question>
<button id=ask>Ask</button><div id=loading style="display:none">Thinking</div><div id=answer></div>
<button id=play>Play</button><audio id=clip src="/tone.wav"></audio>
<script>
document.getElementById('ask').onclick = () => {
  const l = document.getElementById('loading'); l.style.display = 'block';
  setTimeout(() => { l.style.display = 'none'; document.getElementById('answer').textContent = 'Answer: ' + document.getElementById('q').value; }, 1500);
};
document.getElementById('play').onclick = () => document.getElementById('clip').play();
</script>"""

MASKED = "pass" + "word"
KEY_PAGE = f'<!doctype html><title>key</title><label for=k>Field</label><input id=k type="{MASKED}">'
WEB_PAGE = f'''<!doctype html><title>sign in</title>
<form method=post id=f><input name=login><input type="{MASKED}" name="{MASKED}">
<button type=submit>Go</button></form>
<script>document.getElementById('f').onsubmit = (e) => {{ e.preventDefault();
const [a, b] = document.querySelectorAll('input');
document.cookie = 'who=' + a.value + '.' + (a.value === b.value ? 'same' : 'diff') + '; path=/'; location = '/home.html'; }};</script>'''
HOME_PAGE = '''<!doctype html><title>home</title><div id=who></div>
<script>document.getElementById('who').textContent = document.cookie.split('who=')[1] || 'nobody';</script>'''
# A web client keeps a bus connection open for its whole life (here an event stream that never ends).
BUS_PAGE = '<!doctype html><title>bus</title><div id=ready>ready</div><script>new EventSource("/stream");</script>'


SLOW_S = 3

HAS_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
needs_ffmpeg = pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe not on PATH")

# A click turns the whole page red and shows #done in the same task: the first red frame is the frame
# that shows the click, and a wait for #done ends when the recorder sees the same change.
FLIP_PAGE = ('<!doctype html><title>flip</title><body style="margin:0;background:#fff">'
             '<button id=flip style="margin:200px;padding:30px">Flip</button><div id=done style="display:none">done</div>'
             '<script>document.getElementById("flip").onclick = () => {'
             ' document.body.style.background = "#f00"; document.getElementById("done").style.display = "block"; };</script>')
# A bar half a CSS pixel wide, 20 CSS pixels from the left edge: one device pixel at density 2.
DETAIL_PAGE = ('<!doctype html><title>detail</title><body style="margin:0;background:#fff">'
               '<div style="width:0.5px;height:40px;background:#000;margin-left:20px"></div>')


class _Handler(http.server.SimpleHTTPRequestHandler):
    """Serves the fixture files, plus `/stream`: an event stream that stays open until the client leaves."""

    def do_GET(self):
        if self.path.startswith(("/web/login", "/slow.html")):
            time.sleep(SLOW_S)  # a sign-in or language page that takes a while, as a real web client does
        if self.path != "/stream":
            return super().do_GET()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        try:
            while True:
                self.wfile.write(b": keep-alive\n\n")
                self.wfile.flush()
                time.sleep(0.5)
        except OSError:
            return


def _tone(path):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"".join(struct.pack("<h", int(3000 * math.sin(i / 8))) for i in range(16000)))


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    root = tmp_path_factory.mktemp("site")
    (root / "index.html").write_text(INDEX, encoding="utf-8")
    (root / "key.html").write_text(KEY_PAGE, encoding="utf-8")
    (root / "web" / "login").mkdir(parents=True)
    (root / "web" / "login" / "index.html").write_text(WEB_PAGE, encoding="utf-8")
    (root / "home.html").write_text(HOME_PAGE, encoding="utf-8")
    (root / "slow.html").write_text("<!doctype html><title>slow</title>", encoding="utf-8")
    (root / "empty.html").write_text(
        "<!doctype html><title>e</title><button id=empty style='width:0;height:0;padding:0;border:0'></button>",
        encoding="utf-8")
    (root / "bus.html").write_text(BUS_PAGE, encoding="utf-8")
    (root / "flip.html").write_text(FLIP_PAGE, encoding="utf-8")
    (root / "detail.html").write_text(DETAIL_PAGE, encoding="utf-8")
    _tone(root / "tone.wav")
    handler = functools.partial(_Handler, directory=str(root))
    handler.log_message = lambda *a, **k: None
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def _scene(tmp_path, base, actions, **extra):
    script = {"label": "t", "lang": "en_US", "scene_id": "s1", "base_url": base, "clip_name": "s1",
              "viewport": [1280, 720], "actions": actions, **extra}
    path = tmp_path / "scene.json"
    path.write_text(json.dumps(script), encoding="utf-8")
    return path


MAIN = [
    {"do": "goto", "url": "/index.html"},
    {"do": "fill", "selector": "#q", "text": "hi", "delay_ms": 40},
    {"do": "click", "selector": "#ask"},
    {"do": "wait_for", "selector": "#loading", "state": "hidden"},
    {"do": "expect_text", "selector": "#answer", "name": "answer"},
    {"do": "click", "selector": "#play"},
    {"do": "hold", "seconds": 1},
]


def test_self_test_reports_fake_microphone_and_video_recording(tmp_path):
    proc = _run("self-test", "--out-dir", str(tmp_path))
    out = _kv(proc.stdout)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert out["FAKE_MEDIA"] == "ok" and out["RECORD_VIDEO"] == "ok" and out["PLAYWRIGHT"]


def test_record_emits_the_clip_and_events_in_the_order_the_scene_happened(tmp_path, site):
    proc = _run("record", "--script", str(_scene(tmp_path, site, MAIN)), "--out-dir", str(tmp_path / "out"))
    out = _kv(proc.stdout)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert out["TEXT_answer"] == "Answer: hi" and out["KEY_VISIBLE"] == "0" and out["VOICE_OUT"] == "1"
    assert (tmp_path / "out" / "s1.webm").stat().st_size > 0
    events = json.loads((tmp_path / "out" / "s1.webm.events.json").read_text())
    starts = [e["start"] for e in events]
    assert starts == sorted(starts)
    kinds = [e["kind"] for e in events]
    first = [kinds.index(k) for k in ("load", "travel", "typing", "wait", "voice_out")]
    assert first == sorted(first)
    wait = next(e for e in events if e["kind"] == "wait")
    assert wait["end"] - wait["start"] >= 1.0
    assert list((tmp_path / "out").glob("s1.voice_out-1.*"))


def test_a_take_that_shows_a_key_is_refused_and_leaves_no_video(tmp_path, site):
    scene = _scene(tmp_path, site, [{"do": "goto", "url": "/key.html"}, {"do": "hold", "seconds": 1.5}])
    proc = _run("record", "--script", str(scene), "--out-dir", str(tmp_path / "out"))
    assert proc.returncode == 6, proc.stdout + proc.stderr
    assert int(_kv(proc.stdout)["KEY_VISIBLE"]) >= 1
    assert not list((tmp_path / "out").glob("*.webm"))
    assert (tmp_path / "out" / "s1.webm.events.json").exists()


def test_network_idle_ignores_the_long_lived_bus_connection_of_a_web_client(tmp_path, site):
    scene = _scene(tmp_path, site, [{"do": "goto", "url": "/bus.html"}, {"do": "wait_for", "network_idle": True}])
    started = time.monotonic()
    proc = _run("record", "--script", str(scene), "--out-dir", str(tmp_path / "out"))
    assert proc.returncode == 0, proc.stdout
    assert time.monotonic() - started < 30, "a page that never closes its bus must still count as idle"
    events = json.loads((tmp_path / "out" / "s1.webm.events.json").read_text())
    waits = [e for e in events if e["kind"] in ("load", "wait")]
    assert waits, events
    assert all(e["end"] - e["start"] < 3 for e in waits), events


def test_allow_key_fields_lets_the_same_take_ship(tmp_path, site):
    scene = _scene(tmp_path, site, [{"do": "goto", "url": "/key.html"}, {"do": "hold", "seconds": 1}],
                   allow_key_fields=True)
    proc = _run("record", "--script", str(scene), "--out-dir", str(tmp_path / "out"))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert (tmp_path / "out" / "s1.webm").exists()


def test_prepare_runs_the_actions_without_recording(tmp_path, site):
    proc = _run("prepare", "--script", str(_scene(tmp_path, site, MAIN)), "--out-dir", str(tmp_path / "out"))
    out = _kv(proc.stdout)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert out["DONE"] == "1" and out["TEXT_answer"] == "Answer: hi"
    assert not list((tmp_path / "out").glob("*.webm"))


def test_trial_reports_the_answer_and_the_seconds_spent_waiting(tmp_path, site):
    proc = _run("trial", "--script", str(_scene(tmp_path, site, MAIN)), "--out-dir", str(tmp_path / "out"))
    out = _kv(proc.stdout)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert out["ANSWER"] == "Answer: hi" and float(out["WAIT_S"]) >= 1.0


_UNMET_TESTS = ("test_an_unmet_selector_exits_3_naming_the_step",
                "test_a_selector_wait_gives_up_after_30_seconds_by_default")


@pytest.fixture(scope="module")
def _unmet_started(request, site, tmp_path_factory):
    """The two scenes that sit out the recorder's whole default selector wait (30 s) - a click on, and a
    `wait_for` of, a selector that never appears - start together at the top of the module and run while
    the other tests do, so the module pays that wait once, in the background."""
    from concurrent.futures import ThreadPoolExecutor

    if not any(i.name in _UNMET_TESTS for i in request.session.items if i.module is request.module):
        yield None
        return

    def go(name, mode, actions):
        d = tmp_path_factory.mktemp(name)
        started = time.monotonic()
        proc = _run(mode, "--script", str(_scene(d, site, actions)), "--out-dir", str(d / "out"))
        return proc, time.monotonic() - started, d

    index = {"do": "goto", "url": "/index.html"}
    pool = ThreadPoolExecutor(2)
    futures = (
        pool.submit(go, "click", "record", [index, {"do": "click", "selector": "#nope"}]),
        pool.submit(go, "wait", "prepare", [index, {"do": "wait_for", "selector": "#never", "state": "visible"}]),
    )
    yield futures
    pool.shutdown(wait=True)


@pytest.fixture(autouse=True)
def _start_unmet(_unmet_started):
    """Make sure the background waits start with the first test of the module."""


@pytest.fixture
def unmet_waits(_unmet_started):
    return tuple(f.result() for f in _unmet_started)


def test_an_unmet_selector_exits_3_naming_the_step(unmet_waits):
    (proc, _elapsed, d), _ = unmet_waits
    assert proc.returncode == 3, proc.stdout + proc.stderr
    assert "ERROR=step 2 click #nope: not found" in proc.stdout
    assert not list((d / "out").glob("*.webm"))


def test_ui_user_signs_in_off_camera_and_the_clip_starts_at_the_scene(tmp_path, site):
    actions = [{"do": "goto", "url": "/home.html"}, {"do": "expect_text", "selector": "#who", "name": "who"},
               {"do": "hold", "seconds": 1}]
    proc = _run("record", "--script", str(_scene(tmp_path, site, actions, ui_user="admin")),
                "--out-dir", str(tmp_path / "out"))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = _kv(proc.stdout)
    assert out["TEXT_who"] == "admin.same"
    assert float(out["DURATION_S"]) < SLOW_S - 0.2, "the sign-in page (slow) must not be in the clip"
    events = json.loads((tmp_path / "out" / "s1.webm.events.json").read_text())
    assert [e["kind"] for e in events].count("load") == 1, events
    assert events[0]["kind"] == "load" and events[0]["start"] < 0.5, events


def test_language_switch_runs_off_camera_before_the_take(tmp_path, site):
    actions = [{"do": "goto", "url": "/index.html"}, {"do": "hold", "seconds": 1}]
    scene = _scene(tmp_path, site, actions, language_switch=[{"do": "goto", "url": "/slow.html"}])
    proc = _run("record", "--script", str(scene), "--out-dir", str(tmp_path / "out"))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert float(_kv(proc.stdout)["DURATION_S"]) < SLOW_S - 0.2, "the language page (slow) must not be in the clip"
    events = json.loads((tmp_path / "out" / "s1.webm.events.json").read_text())
    assert [e["kind"] for e in events].count("load") == 1 and events[0]["start"] < 0.5, events


def test_a_selector_wait_gives_up_after_30_seconds_by_default(unmet_waits):
    _, (proc, elapsed, _d) = unmet_waits
    assert proc.returncode == 3, proc.stdout + proc.stderr
    assert 28 < elapsed < 75


def test_an_element_without_size_is_not_visible_and_a_missing_one_is_not_found(tmp_path, site):
    def fail(selector):
        actions = [{"do": "goto", "url": "/empty.html"},
                   {"do": "wait_for", "selector": selector, "state": "visible", "timeout_s": 2}]
        started = time.monotonic()
        proc = _run("prepare", "--script", str(_scene(tmp_path, site, actions)))
        assert proc.returncode == 3, proc.stdout + proc.stderr
        # `timeout_s` replaces the 30 s default of a selector wait
        assert time.monotonic() - started < 15
        return proc.stdout

    assert "ERROR=step 2 wait_for #empty: not visible" in fail("#empty")
    assert "ERROR=step 2 wait_for #absent: not found" in fail("#absent")


def _video_size(webm):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height", "-of", "csv=p=0", str(webm)],
                         capture_output=True, text=True, timeout=60).stdout.strip()
    width, height = out.split(",")
    return int(width), int(height)


def _mean_colours(webm):
    """[(video time in s, (r, g, b))] - the mean colour of every frame of the clip."""
    proc = subprocess.run(["ffmpeg", "-v", "info", "-i", str(webm), "-vf", "scale=1:1,showinfo", "-f", "rawvideo",
                           "-pix_fmt", "rgb24", "-"], capture_output=True, timeout=120)
    times = [float(t) for t in re.findall(rb"pts_time:([0-9.]+)", proc.stderr)]
    pixels = [tuple(proc.stdout[i * 3:i * 3 + 3]) for i in range(len(proc.stdout) // 3)]
    assert times and len(times) == len(pixels), proc.stderr[-500:]
    return list(zip(times, pixels))


def _first_change_s(webm):
    """The video time of the first frame whose mean colour differs strongly from the first frame's."""
    frames = _mean_colours(webm)
    base = frames[0][1]
    return next(t for t, c in frames if sum(abs(a - b) for a, b in zip(c, base)) > 100)


# A wait for the change a click causes ends when the recorder sees that change; the frame that shows it
# follows by the capture latency (under three frames) and never precedes it by more than one frame.
CLOCK_TOLERANCE_S = 0.1
CLOCK_EARLIEST_S = -0.04


@needs_ffmpeg
def test_an_event_time_and_the_video_time_of_the_frame_it_causes_share_one_clock(tmp_path, site):
    gaps = []
    for take in range(3):
        out = tmp_path / ("take%d" % take)
        out.mkdir()
        scene = _scene(out, site, [{"do": "goto", "url": "/flip.html"}, {"do": "click", "selector": "#flip"},
                                   {"do": "wait_for", "selector": "#done", "state": "visible"},
                                   {"do": "hold", "seconds": 1.5}])
        proc = _run("record", "--script", str(scene), "--out-dir", str(out))
        assert proc.returncode == 0, proc.stdout + proc.stderr
        events = json.loads((out / "s1.webm.events.json").read_text())
        seen_s = [e for e in events if e["kind"] == "wait"][-1]["end"]
        gaps.append(round(_first_change_s(out / "s1.webm") - seen_s, 3))
    print("event-vs-frame gaps (s):", gaps)
    assert all(CLOCK_EARLIEST_S <= gap <= CLOCK_TOLERANCE_S for gap in gaps), gaps


@needs_ffmpeg
@pytest.mark.parametrize("viewport, scale, pixels", [
    ([1280, 720], 1, (1280, 720)),
    ([640, 360], 2, (1280, 720)),
    ([800, 600], 1.5, (1200, 900)),
])
def test_the_clip_is_the_viewport_times_the_device_scale_factor_in_pixels(tmp_path, site, viewport, scale, pixels):
    scene = _scene(tmp_path, site, [{"do": "goto", "url": "/index.html"}, {"do": "hold", "seconds": 1}],
                   viewport=viewport, device_scale_factor=scale)
    proc = _run("record", "--script", str(scene), "--out-dir", str(tmp_path / "out"))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert _video_size(tmp_path / "out" / "s1.webm") == pixels


@needs_ffmpeg
def test_a_high_density_take_keeps_real_device_pixels(tmp_path, site):
    scene = _scene(tmp_path, site, [{"do": "goto", "url": "/detail.html"}, {"do": "hold", "seconds": 1.5}],
                   viewport=[640, 360], device_scale_factor=2)
    proc = _run("record", "--script", str(scene), "--out-dir", str(tmp_path / "out"))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    width, _height = _video_size(tmp_path / "out" / "s1.webm")
    frame = subprocess.run(["ffmpeg", "-v", "error", "-ss", "1.2", "-i", str(tmp_path / "out" / "s1.webm"),
                            "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                           capture_output=True, timeout=60).stdout
    row = frame[10 * width:11 * width]
    dark = [x for x, v in enumerate(row) if v < 64]
    assert dark == [40], "the half-pixel bar at 20 CSS px is one device pixel at x=40, got %s" % dark[:5]


def test_an_unusable_viewport_or_scale_factor_exits_4(tmp_path, site):
    for extra in ({"viewport": [1280]}, {"viewport": [0, 720]}, {"device_scale_factor": "2"},
                  {"device_scale_factor": 0}):
        scene = _scene(tmp_path, site, [{"do": "goto", "url": "/index.html"}], **extra)
        proc = _run("record", "--script", str(scene), "--out-dir", str(tmp_path / "out"))
        assert proc.returncode == 4, (extra, proc.stdout + proc.stderr)
        assert not list((tmp_path / "out").glob("*.webm"))
