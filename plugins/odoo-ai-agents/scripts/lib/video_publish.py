#!/usr/bin/env python3
"""video_publish.py - narrated assembly and publish-profile verification for demo videos (ffmpeg).

Subcommands (stdlib + ffmpeg/ffprobe on PATH):
  verify-tools [--font F]  what this machine can do (ffmpeg, the filters, title card via drawtext or
            libass, the font and its Vietnamese coverage) - run BEFORE recording; exit 1 on a gap.
  speedup   --clip scene.mp4 --events scene.events.json --out scene-paced.mp4 [--typing 3] [--travel 2]
            [--wait-keep 1] [--wait-squeeze 1.0] [--must-see "s,e;s,e"]   the dead time the recorder
            logged (typing, cursor travel, page loads, waits) plays faster; a wait keeps its first
            --wait-keep seconds at 1x and the rest is time-compressed into --wait-squeeze seconds so the
            viewer sees the indicator move fast (0 = cut it). Kinds hold, voice_in and voice_out stay 1x
            and are counted in SPANS. Any logged span overlapping a --must-see range plays at 1x in full
            (MUST_SEE_KEPT=n). A key_visible span means the take must not ship: prints
            KEY_VISIBLE=n, writes no output, exit 6. Everything else stays 1x.
  zoom      --clip scene.mp4 --focus x,y,w,h --from s --to s --out scene-zoomed.mp4 [--factor 1.6]
            a smooth punch-in on the area that matters (ease in, hold, ease out) at output resolution.
  audition  --narration a.wav [--narration b.wav ...] --out-dir D [--music bed.mp3]
            the same line per candidate voice, dry and with the music bed, for the owner to pick once.
  fit       --clip scene.mp4 [--narration scene.wav] --out scene-fitted.mp4 [--lead-in 0.5] [--max-hold 3]
            [--fade 0.3] [--max-silence 3.0] [--voice FILE@T ...]  The narration starts after the lead-in; when it
            outlasts the clip the last frame is held; a short fade closes the scene. Each --voice (repeatable)
            is another audio track (the page's spoken answer, the voice input) mixed in at T seconds on the
            output timeline, loudness-matched to the narration. Prints DURATION_S and VOICES=n.
            Without --narration (a silent clip) the video keeps its own length (no hold, no lead-in), the
            --fade still closes it, the output carries a silent AAC 48 kHz stereo track so every fitted
            clip has one audio layout, and NARRATION=none is printed.

List file (concat --list, sidecar --list): one ABSOLUTE path per line, in play order, blank lines
ignored. Not ffmpeg's own `file '...'` syntax - concat writes that itself. Both commands check the
list before any ffmpeg call and refuse a line that is not an existing file: `ERROR=list: <line>: not
a file` on stdout, exit 1.

Exit codes: 0 ok, 1 failure, 2 tool missing, 4 silence over the limit, 5 held frame over the limit,
6 a key field was shown on screen in the take (speedup).
  concat    --list clips.txt --out video.mp4  Concatenates fitted scenes (ffmpeg concat demuxer,
            re-encoded once) and applies two-pass loudnorm to the profile target. An input without an
            audio stream first gets a silent AAC 48 kHz stereo track of its length. When nothing is
            audible (measured loudness -inf) the second pass is skipped, the output keeps a plain AAC
            48 kHz stereo track and LOUDNESS=silent is printed.
  title     --text "..." --out card.mp4 --seconds 3 [--font ttf] [--size 1920x1080]
            A title card rendered from storyboard text (needs an ffmpeg with drawtext).
  verify    --video video.mp4 --profile youtube-1080p [--silent]  Reads ffprobe + ebur128 and prints one
            KEY=OK|FAIL line per rule; exit 1 on any FAIL. With --silent a deliverable with no signal at
            all (loudness -inf) passes LOUDNESS and TRUE_PEAK and SILENT=1 is printed; the audio stream
            rules (AAC, 48 kHz, stereo) still apply. Without it -inf fails.
  sidecar   --storyboard SB.json --lang xx_YY --list clips.txt --out-dir DIR [--narration-dir DIR]
            [--lead-in S]   --list is the file concat consumed; each chapter starts where the REAL
            durations (ffprobe) of the preceding entries end. An entry whose basename starts with
            `title` is the title card: not a chapter, but it counts in the offset. Writes <lang>.txt
            (title, description, chapters) and, only with --narration-dir (<scene id>.wav per scene),
            <lang>.srt (the scene's caption lines run from its chapter start plus --lead-in over the
            narration duration); otherwise prints CAPTIONS=none. Prints the paths and TOTAL_S.
  thumbnail --video video.mp4 --at 2.0 --out thumb.jpg  A 1280x720 JPEG under 2 MB. A missing or
            unreadable --video prints `ERROR=<path>: not a file` (exit 1).
  preview   --video video.mp4 --out preview.mp4 [--max-mb 10]  Same picture, higher CRF, under the cap.

Publish profile `youtube-1080p` (the only profile shipped): MP4 with faststart; H.264 High,
progressive, yuv420p, 1920x1080, constant frame rate equal to the recording rate, closed GOP of
half the frame rate, 2 B-frames, CRF 18 with maxrate 10M / bufsize 20M; AAC-LC 48 kHz stereo
384 kb/s; -14 LUFS integrated, true peak <= -1.0 dBTP (encoded at -1.5 for the margin).
Every parameter below is data; nothing in the storyboard is hardcoded here.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys

NARRATION_LUFS = -16   # integrated loudness every narration clip is brought to before the mix
NARRATION_TP = -1.5
SILENCE_SRC = "anullsrc=r=48000:cl=stereo"   # lavfi source of a silent stereo track

PROFILES = {
    "youtube-1080p": {
        "width": 1920, "height": 1080, "codec": "h264", "profile": "High", "pix_fmt": "yuv420p",
        "audio_codec": "aac", "sample_rate": 48000, "channels": 2, "audio_bitrate": "384k",
        "crf": 18, "maxrate": "10M", "bufsize": "20M", "bframes": 2,
        "lufs": -14.0, "true_peak": -1.5, "true_peak_max": -1.0, "lufs_tolerance": 1.0,
    },
}


def _run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, check=False, **kw)


def _need(tool):
    if not shutil.which(tool):
        print("x %s is missing - install ffmpeg (it ships ffprobe too)" % tool, file=sys.stderr)
        sys.exit(2)


def ffprobe(path):
    _need("ffprobe")
    proc = _run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams",
                 "-show_format", path])
    if proc.returncode != 0:
        print("x ffprobe failed: %s" % proc.stderr.strip()[-300:], file=sys.stderr)
        sys.exit(1)
    return json.loads(proc.stdout)


def duration_of(path):
    info = ffprobe(path)
    return float(info["format"].get("duration") or 0.0)


def frame_rate_of(path):
    for s in ffprobe(path)["streams"]:
        if s.get("codec_type") == "video":
            num, _, den = (s.get("r_frame_rate") or "0/1").partition("/")
            return float(num) / float(den or 1)
    return 0.0


def video_args(profile, fps):
    p = PROFILES[profile]
    gop = max(1, int(round(fps / 2.0)))
    return ["-c:v", "libx264", "-profile:v", p["profile"].lower(), "-pix_fmt", p["pix_fmt"],
            "-crf", str(p["crf"]), "-maxrate", p["maxrate"], "-bufsize", p["bufsize"],
            "-g", str(gop), "-keyint_min", str(gop), "-sc_threshold", "0", "-bf", str(p["bframes"]),
            "-coder", "1", "-r", "%g" % fps, "-vsync", "cfr", "-movflags", "+faststart"]


def audio_args(profile):
    p = PROFILES[profile]
    return ["-c:a", "aac", "-b:a", p["audio_bitrate"], "-ar", str(p["sample_rate"]),
            "-ac", str(p["channels"])]


def cmd_fit(args):
    _need("ffmpeg")
    clip_s = duration_of(args.clip)
    fps = frame_rate_of(args.clip) or 25.0
    if not args.narration:
        return _fit_silent(args, clip_s, fps)
    narration_s = duration_of(args.narration)
    total = max(clip_s, args.lead_in + narration_s + args.fade)
    hold = max(0.0, total - clip_s)
    if hold > args.max_hold:
        print("HOLD_S=%.3f" % hold)
        print("HOLD=over")
        print("x the last frame would freeze for %.1f s to fit the narration (limit %.1f s): shorten the "
              "narration or extend the footage - a frozen frame is what makes a video feel slow" % (hold, args.max_hold),
              file=sys.stderr)
        return 5
    # the part of the scene where the screen moves and nobody speaks (the lead-in is deliberate)
    silent = max(0.0, clip_s - args.lead_in - narration_s)
    vf = "tpad=stop_mode=clone:stop_duration=%.3f,fade=t=out:st=%.3f:d=%.3f" % (
        hold, max(0.0, total - args.fade), args.fade)
    # one integrated loudness per narration clip BEFORE the mix: a retake recorded on another day (or
    # another take of one line) sits at the same level as its neighbours; the final two-pass loudnorm
    # in concat then only evens the whole file
    af = "loudnorm=I=%s:TP=%s:LRA=11,aresample=48000,adelay=%d|%d,apad=whole_dur=%.3f" % (
        NARRATION_LUFS, NARRATION_TP, int(args.lead_in * 1000), int(args.lead_in * 1000), total)
    voices = []
    for spec in args.voice or []:
        path, sep, at = spec.rpartition("@")
        try:
            voices.append((path, float(at)))
            if not sep or not path:
                raise ValueError(spec)
        except ValueError:
            print("x --voice wants FILE@SECONDS, got %r" % spec, file=sys.stderr)
            return 1
    inputs = ["-i", args.clip, "-i", args.narration]
    fc = "[0:v]%s[v];" % vf
    if voices:
        fc += "[1:a]%s,aformat=channel_layouts=stereo[n]" % af
        for i, (path, at) in enumerate(voices, 2):
            ms = int(round(at * 1000))
            inputs += ["-i", path]
            # a voice track is levelled like the narration so neither drowns the other
            fc += (";[%d:a]loudnorm=I=%s:TP=%s:LRA=11,aresample=48000,adelay=%d|%d,"
                   "aformat=channel_layouts=stereo[x%d]" % (i, NARRATION_LUFS, NARRATION_TP, ms, ms, i))
        fc += ";[n]%samix=inputs=%d:duration=longest:dropout_transition=0:normalize=0,asetpts=N/SR/TB[a]" % (
            "".join("[x%d]" % i for i in range(2, 2 + len(voices))), len(voices) + 1)
    else:
        fc += "[1:a]%s[a]" % af
    cmd = ["ffmpeg", "-v", "error", "-y"] + inputs + [
           "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
           "-t", "%.3f" % total] + video_args(args.profile, fps) + audio_args(args.profile) + [args.out]
    proc = _run(cmd)
    if proc.returncode != 0:
        print("x ffmpeg fit failed: %s" % proc.stderr.strip()[-400:], file=sys.stderr)
        return 1
    print("OUT=%s" % args.out)
    print("DURATION_S=%.3f" % total)
    print("HOLD_S=%.3f" % hold)
    print("VOICES=%d" % len(voices))
    print("SILENT_S=%.3f" % silent)
    if silent > args.max_silence:
        print("SILENCE=over")
        print("x the screen moves for %.1f s with nobody speaking (limit %.1f s): say what it shows, "
              "or shorten the scene" % (silent, args.max_silence), file=sys.stderr)
        return 4
    print("SILENCE=ok")
    return 0


def _fit_silent(args, clip_s, fps):
    """A clip with no narration: its own length, the closing fade, a silent AAC track."""
    if args.voice:
        print("x --voice needs --narration", file=sys.stderr)
        return 1
    vf = "fade=t=out:st=%.3f:d=%.3f" % (max(0.0, clip_s - args.fade), args.fade)
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", args.clip, "-f", "lavfi", "-i", SILENCE_SRC,
           "-filter_complex", "[0:v]%s[v]" % vf, "-map", "[v]", "-map", "1:a",
           "-t", "%.3f" % clip_s] + video_args(args.profile, fps) + audio_args(args.profile) + [args.out]
    proc = _run(cmd)
    if proc.returncode != 0:
        print("x ffmpeg fit failed: %s" % proc.stderr.strip()[-400:], file=sys.stderr)
        return 1
    print("OUT=%s" % args.out)
    print("NARRATION=none")
    print("DURATION_S=%.3f" % clip_s)
    print("HOLD_S=0.000")
    print("VOICES=0")
    return 0


def _has_audio(path):
    return any(s.get("codec_type") == "audio" for s in ffprobe(path)["streams"])


def _is_silent(measured):
    try:
        return float(measured["input_i"]) == float("-inf")
    except (TypeError, ValueError, KeyError):
        return False


def loudnorm_measure(path, profile):
    p = PROFILES[profile]
    proc = _run(["ffmpeg", "-v", "info", "-i", path, "-af",
                 "loudnorm=I=%s:TP=%s:LRA=11:print_format=json" % (p["lufs"], p["true_peak"]),
                 "-f", "null", "-"])
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", proc.stderr, re.S)
    return json.loads(m.group(0)) if m else None


MUSIC_GAIN_DB = -18.0        # the bed under speech
DUCK = "sidechaincompress=threshold=0.03:ratio=8:attack=30:release=500:makeup=1"


def music_filter(duration_s, gain_db, fade_s=2.0):
    """ffmpeg filter_complex: the bed (input 1, looped) faded, ducked by the narration (input 0's
    audio) and mixed under it; the narration's own level is untouched."""
    return ("[1:a]aloop=loop=-1:size=2e9,atrim=0:%.3f,asetpts=N/SR/TB,volume=%gdB,"
            "afade=t=in:d=%g,afade=t=out:st=%.3f:d=%g[bed];"
            "[bed][0:a]%s[duck];[0:a][duck]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]"
            % (duration_s, gain_db, fade_s, max(0.0, duration_s - fade_s - 1.0), fade_s + 1.0, DUCK))


def add_music(src, music, out, gain_db=MUSIC_GAIN_DB):
    """`src` with the music bed mixed under its narration -> `out` (video copied)."""
    dur = duration_of(src)
    proc = _run(["ffmpeg", "-v", "error", "-y", "-i", src, "-stream_loop", "-1", "-i", music,
                 "-filter_complex", music_filter(dur, gain_db), "-map", "0:v", "-map", "[a]", "-c:v", "copy",
                 "-c:a", "pcm_s16le", "-t", "%.3f" % dur, out])
    return proc


def read_list(path):
    """The paths of a list file (one absolute path per line, blank lines ignored), or None after
    printing `ERROR=list: <line>: not a file` for the first line that is not an existing file."""
    with open(path, encoding="utf-8") as fh:
        lines = [line.strip() for line in fh if line.strip()]
    for line in lines:
        if not os.path.isabs(line) or not os.path.isfile(line):
            print("ERROR=list: %s: not a file" % line)
            return None
    return lines


def cmd_concat(args):
    _need("ffmpeg")
    clips = read_list(args.list)
    if clips is None:
        return 1
    if not clips:
        print("x no clips listed", file=sys.stderr)
        return 1
    fps = frame_rate_of(clips[0]) or 25.0
    listfile = args.out + ".concat.txt"
    raw = args.out + ".raw.mp4"
    padded = []
    try:
        inputs = []
        for i, c in enumerate(clips):
            if not _has_audio(c):
                # a silent clip gets a silent track of its length so every input has one audio layout
                tmp = "%s.pad%d%s" % (args.out, i, os.path.splitext(c)[1] or ".mp4")
                padded.append(tmp)
                pp = _run(["ffmpeg", "-v", "error", "-y", "-i", c, "-f", "lavfi", "-i", SILENCE_SRC,
                           "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-ar", "48000",
                           "-ac", "2", "-shortest", tmp])
                if pp.returncode != 0:
                    print("x adding a silent track to %s failed: %s" % (c, pp.stderr.strip()[-300:]),
                          file=sys.stderr)
                    return 1
                c = tmp
            inputs.append(c)
        with open(listfile, "w", encoding="utf-8") as fh:
            for c in inputs:
                fh.write("file '%s'\n" % os.path.abspath(c).replace("'", "'\\''"))
        proc = _run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", listfile]
                    + video_args(args.profile, fps) + audio_args(args.profile) + [raw])
        if proc.returncode != 0:
            print("x concat failed: %s" % proc.stderr.strip()[-400:], file=sys.stderr)
            return 1
        if getattr(args, "music", None):
            bedded = args.out + ".bed.mkv"
            proc = add_music(raw, args.music, bedded, args.music_gain)
            if proc.returncode != 0:
                print("x music bed failed: %s" % proc.stderr.strip()[-400:], file=sys.stderr)
                return 1
            os.replace(bedded, raw + ".mkv")
            raw = raw + ".mkv"
            print("MUSIC=%s (%gdB under the narration, ducked)" % (os.path.basename(args.music), args.music_gain))
            print("MUSIC_LICENSE=%s" % (args.music_license or "UNSTATED - the report must state it"))
        measured = loudnorm_measure(raw, args.profile)
        p = PROFILES[args.profile]
        silent = _is_silent(measured)
        af = ["-af", "loudnorm=I=%s:TP=%s:LRA=11" % (p["lufs"], p["true_peak"])]
        if measured and not silent:
            af[1] += (":measured_I=%s:measured_TP=%s:measured_LRA=%s:measured_thresh=%s:offset=%s"
                      ":linear=true" % (measured["input_i"], measured["input_tp"], measured["input_lra"],
                                        measured["input_thresh"], measured["target_offset"]))
        if silent:
            af = []   # nothing to normalise: no second loudnorm pass
            print("LOUDNESS=silent")
        proc = _run(["ffmpeg", "-v", "error", "-y", "-i", raw, "-c:v", "copy"] + af
                    + audio_args(args.profile) + ["-movflags", "+faststart", args.out])
        if proc.returncode != 0:
            print("x loudnorm pass failed: %s" % proc.stderr.strip()[-400:], file=sys.stderr)
            return 1
    finally:
        for f in [listfile, raw, args.out + ".raw.mp4", args.out + ".raw.mp4.mkv"] + padded:
            if os.path.exists(f):
                os.unlink(f)
    print("OUT=%s" % args.out)
    print("DURATION_S=%.3f" % duration_of(args.out))
    return 0


# --------------------------------------------------------------------------- pacing
def _ease(expr):
    """smoothstep of a 0..1 expression, as ffmpeg expression text."""
    return "(%s)*(%s)*(3-2*(%s))" % (expr, expr, expr)


def cmd_zoom(args):
    """A smooth punch-in on the focus box between --from and --to (ease in, hold, ease out), rendered
    at the output resolution so text stays sharp; the rest of the clip is untouched. Captions and
    title cards are never zoomed - this runs on a scene clip only."""
    _need("ffmpeg")
    fps = frame_rate_of(args.clip) or 25.0
    info = ffprobe(args.clip)
    v = next((s for s in info["streams"] if s.get("codec_type") == "video"), {})
    W, H = int(v.get("width") or 1920), int(v.get("height") or 1080)
    fx, fy, fw, fh = [float(x) for x in args.focus.split(",")]
    z = max(1.0, min(float(args.factor), W / max(fw, 1.0), H / max(fh, 1.0)))
    seg_frames = max(1, int(round((args.to - args.frm) * fps)))
    ramp = max(1, int(round(args.ramp * fps)))
    ramp = min(ramp, max(1, seg_frames // 2))
    cx, cy = fx + fw / 2.0, fy + fh / 2.0
    # zoom level per output frame `on`: ease in over `ramp`, hold, ease out over the last `ramp`
    t_in = "min(on/%d,1)" % ramp
    t_out = "min((%d-on)/%d,1)" % (seg_frames, ramp)
    zexpr = "1+(%g-1)*min(%s,%s)" % (z, _ease(t_in), _ease(t_out))
    xexpr = "min(max(%g-(iw/zoom)/2,0),iw-iw/zoom)" % cx
    yexpr = "min(max(%g-(ih/zoom)/2,0),ih-ih/zoom)" % cy
    zp = "zoompan=z='%s':x='%s':y='%s':d=1:s=%dx%d:fps=%g" % (zexpr, xexpr, yexpr, W, H, fps)
    fc = ("[0:v]split=3[a][b][c];"
          "[a]trim=0:%(f).3f,setpts=PTS-STARTPTS[pre];"
          "[b]trim=%(f).3f:%(t).3f,setpts=PTS-STARTPTS,%(zp)s[mid];"
          "[c]trim=%(t).3f,setpts=PTS-STARTPTS[post];"
          "[pre][mid][post]concat=n=3:v=1:a=0[v]" % {"f": args.frm, "t": args.to, "zp": zp})
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", args.clip, "-filter_complex", fc, "-map", "[v]"]
    if any(s.get("codec_type") == "audio" for s in info["streams"]):
        cmd += ["-map", "0:a", "-c:a", "copy"]
    cmd += video_args(args.profile, fps) + [args.out]
    proc = _run(cmd)
    if proc.returncode != 0:
        print("x zoom failed: %s" % proc.stderr.strip()[-400:], file=sys.stderr)
        return 1
    print("OUT=%s" % args.out)
    print("ZOOM=%g over %.2f-%.2f s" % (z, args.frm, args.to))
    return 0


def _ranges(text):
    """`"s,e;s,e"` -> [(s, e), ...]."""
    out = []
    for part in (text or "").split(";"):
        if part.strip():
            lo, _, hi = part.partition(",")
            out.append((float(lo), float(hi)))
    return out


KEPT_KINDS = ("hold", "voice_in", "voice_out")   # logged for the report, always played at 1x


def cmd_speedup(args):
    """Compress the dead time the recorder logged: each event span of a kind named in --typing /
    --travel plays faster (typing, cursor travel, scrolling, a page load); a wait keeps its first
    --wait-keep seconds and squeezes the rest into --wait-squeeze seconds (0 = cut); everything else
    plays at 1x. The events file is the recorder's `<scene>.events.json`:
    [{"kind": "typing|wait|travel|load|hold|voice_in|voice_out|key_visible", "start": s, "end": s}].
    A key_visible span stops the run (exit 6, no output)."""
    _need("ffmpeg")
    with open(args.events, encoding="utf-8") as fh:
        events = sorted((e for e in json.load(fh) if isinstance(e, dict)), key=lambda e: float(e.get("start", 0)))
    shown = [e for e in events if e.get("kind") == "key_visible"]
    if shown:
        print("KEY_VISIBLE=%d" % len(shown))
        print("x a key field was shown on screen in this take (%d span%s): re-record it with the value masked"
              % (len(shown), "" if len(shown) == 1 else "s"), file=sys.stderr)
        return 6
    must_see = _ranges(args.must_see)
    total = duration_of(args.clip)
    factors = {"typing": args.typing, "travel": args.travel, "load": args.travel}
    spans, cursor, counted, protected = [], 0.0, 0, 0
    for e in events:
        s, en, kind = float(e.get("start", 0)), float(e.get("end", 0)), e.get("kind", "")
        if en <= s or s < cursor or en > total + 0.01:
            continue
        if kind in KEPT_KINDS:
            counted += 1
            continue
        if kind != "wait" and not (kind in factors and factors[kind] > 1.0):
            continue
        if any(s < hi and en > lo for lo, hi in must_see):
            protected += 1
            continue
        if kind == "wait":
            keep = min(args.wait_keep, en - s)
            if s > cursor:
                spans.append((cursor, s, 1.0))
            spans.append((s, s + keep, 1.0))
            rest = en - (s + keep)
            if rest > 0 and args.wait_squeeze > 0:
                target = min(args.wait_squeeze, rest)
                spans.append((s + keep, en, rest / target))
            elif rest > 0:
                spans.append((s + keep, en, 0.0))   # 0 = cut
        else:
            if s > cursor:
                spans.append((cursor, s, 1.0))
            spans.append((s, en, factors[kind]))
        cursor = en
    if cursor < total:
        spans.append((cursor, total, 1.0))
    kept = [sp for sp in spans if sp[2] > 0]
    if not kept:
        print("x nothing left after the cuts", file=sys.stderr)
        return 1
    parts = []
    for i, (s, en, f) in enumerate(kept):
        setpts = "setpts=(PTS-STARTPTS)/%g" % f if f != 1.0 else "setpts=PTS-STARTPTS"
        parts.append("[0:v]trim=%.3f:%.3f,%s[v%d]" % (s, en, setpts, i))
    fc = ";".join(parts) + ";" + "".join("[v%d]" % i for i in range(len(kept))) + "concat=n=%d:v=1:a=0[v]" % len(kept)
    fps = frame_rate_of(args.clip) or 25.0
    proc = _run(["ffmpeg", "-v", "error", "-y", "-i", args.clip, "-filter_complex", fc, "-map", "[v]", "-an"]
                + video_args(args.profile, fps) + [args.out])
    if proc.returncode != 0:
        print("x speedup failed: %s" % proc.stderr.strip()[-400:], file=sys.stderr)
        return 1
    new_total = duration_of(args.out)
    print("OUT=%s" % args.out)
    print("DURATION_S=%.3f" % new_total)
    print("SAVED_S=%.3f" % (total - new_total))
    print("SPANS=%d" % (len([sp for sp in spans if sp[2] != 1.0]) + counted))
    print("MUST_SEE_KEPT=%d" % protected)
    return 0


def cmd_audition(args):
    """The same spoken line as several candidate clips, each with and without the music bed, so the
    owner picks a voice and the music by ear once per project. Prints one line per sample."""
    _need("ffmpeg")
    os.makedirs(args.out_dir, exist_ok=True)
    for clip in args.narration:
        base = os.path.splitext(os.path.basename(clip))[0]
        dry = os.path.join(args.out_dir, base + ".dry.wav")
        proc = _run(["ffmpeg", "-v", "error", "-y", "-i", clip, "-af", "loudnorm=I=%s:TP=%s:LRA=11" % (NARRATION_LUFS, NARRATION_TP),
                     "-ar", "48000", "-ac", "2", dry])
        if proc.returncode != 0:
            print("x %s: %s" % (clip, proc.stderr.strip()[-200:]), file=sys.stderr)
            continue
        print("SAMPLE=%s voice=%s music=off" % (dry, base))
        if args.music:
            wet = os.path.join(args.out_dir, base + ".music.wav")
            dur = duration_of(dry)
            proc = _run(["ffmpeg", "-v", "error", "-y", "-i", dry, "-stream_loop", "-1", "-i", args.music,
                         "-filter_complex", music_filter(dur, args.music_gain), "-map", "[a]", "-t", "%.3f" % dur, wet])
            if proc.returncode == 0:
                print("SAMPLE=%s voice=%s music=on" % (wet, base))
    return 0


def have_filter(name):
    try:
        out = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True, timeout=20,
                             check=False).stdout
    except OSError:
        return False
    return " %s " % name in out


def _font(args):
    font = getattr(args, "font", None)
    if not font and shutil.which("fc-match"):
        font = _run(["fc-match", "-f", "%{file}", "sans-serif"]).stdout.strip() or None
    return font


def _ass_card(text, font_path, size):
    w, h = size.split("x")
    family = os.path.splitext(os.path.basename(font_path))[0] if font_path else "Sans"
    esc = text.replace("\\", "\\\\").replace("\n", "\\N")
    return ("[Script Info]\nScriptType: v4.00+\nPlayResX: %s\nPlayResY: %s\n\n[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, Underline, "
            "StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, "
            "MarginV, Encoding\nStyle: Title,%s,64,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,5,40,40,40,1\n\n"
            "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
            "Dialogue: 0,0:00:00.00,9:59:59.00,Title,,0,0,0,,%s\n") % (w, h, family, esc)


def cmd_title(args):
    _need("ffmpeg")
    font = _font(args)
    if not font:
        print("x no font - pass --font <ttf with Latin Extended coverage>", file=sys.stderr)
        return 2
    esc = lambda v: v.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")  # noqa: E731
    sidecar = None
    if have_filter("drawtext"):
        sidecar = args.out + ".txt"
        with open(sidecar, "w", encoding="utf-8") as fh:
            fh.write(args.text)
        vf = ("drawtext=fontfile=%s:textfile=%s:fontsize=64:fontcolor=white:x=(w-text_w)/2:"
              "y=(h-text_h)/2" % (esc(font), esc(sidecar)))
        how = "drawtext"
    elif have_filter("subtitles") or have_filter("ass"):
        # the static builds that lack drawtext carry libass: the card is an .ass subtitle over a plain colour
        sidecar = args.out + ".ass"
        with open(sidecar, "w", encoding="utf-8") as fh:
            fh.write(_ass_card(args.text, font, args.size))
        vf = "subtitles=%s:fontsdir=%s" % (esc(sidecar), esc(os.path.dirname(font)))
        how = "libass"
    else:
        print("x title card needs an ffmpeg with the drawtext or the subtitles (libass) filter; this build has "
              "neither - install the distro's ffmpeg package", file=sys.stderr)
        return 1
    try:
        proc = _run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
                     "-i", "color=c=0x1f1f1f:s=%s:r=%g:d=%s" % (args.size, args.fps, args.seconds),
                     "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-vf", vf, "-t", str(args.seconds)]
                    + video_args(args.profile, args.fps) + audio_args(args.profile) + [args.out])
    finally:
        if sidecar and os.path.exists(sidecar):
            os.unlink(sidecar)
    if proc.returncode != 0:
        print("x title card failed (%s): %s" % (how, proc.stderr.strip()[-300:]), file=sys.stderr)
        return 1
    print("OUT=%s" % args.out)
    print("RENDERED_WITH=%s" % how)
    return 0


VIETNAMESE_SAMPLE = "ăâđêôơưàảãáạằẳẵắặầẩẫấậèẻẽéẹềểễếệìỉĩíịòỏõóọồổỗốộờởỡớợùủũúụừửữứựỳỷỹýỵ"


def font_covers(font_path, sample=VIETNAMESE_SAMPLE):
    """Whether the font's charset (fc-query) holds every character of `sample`; None when fc-query
    is unavailable."""
    if not shutil.which("fc-query"):
        return None
    out = _run(["fc-query", "-f", "%{charset}", font_path]).stdout.strip()
    if not out:
        return False
    covered = set()
    for rng in out.split():
        lo, _, hi = rng.partition("-")
        try:
            a, b = int(lo, 16), int(hi or lo, 16)
        except ValueError:
            continue
        covered.update(range(a, b + 1))
    return all(ord(ch) in covered for ch in sample)


def cmd_verify_tools(args):
    """What this machine can do for a video run, BEFORE anything is recorded."""
    ok = True
    for tool in ("ffmpeg", "ffprobe"):
        path = shutil.which(tool)
        print("%s=%s" % (tool.upper(), path or "missing"))
        ok = ok and bool(path)
    if shutil.which("ffmpeg"):
        card = "drawtext" if have_filter("drawtext") else ("libass" if (have_filter("subtitles") or have_filter("ass")) else "none")
        print("TITLE_CARD=%s" % card)
        for f in ("loudnorm", "ebur128", "aresample", "tpad"):
            present = have_filter(f)
            print("FILTER_%s=%s" % (f, "ok" if present else "missing"))
            ok = ok and present
        if card == "none":
            print("REMEDY=install an ffmpeg build with drawtext or libass (the distro package has both)")
    font = _font(args)
    print("FONT=%s" % (font or "none"))
    if font:
        cov = font_covers(font)
        print("FONT_VI_COVERAGE=%s" % ("unknown" if cov is None else ("ok" if cov else "missing")))
        if cov is False:
            print("REMEDY=the font has no Vietnamese glyphs: record a font that has them as the author profile's font_file")
            ok = False
    print("VERDICT=%s" % ("pass" if ok else "fail"))
    return 0 if ok else 1


def verify(video, profile, silent=False):
    p = PROFILES[profile]
    info = ffprobe(video)
    v = next((s for s in info["streams"] if s.get("codec_type") == "video"), {})
    a = next((s for s in info["streams"] if s.get("codec_type") == "audio"), {})
    results = []
    results.append(("CONTAINER_FASTSTART", _faststart(video)))
    results.append(("VIDEO_CODEC", v.get("codec_name") == p["codec"]))
    results.append(("VIDEO_PROFILE", (v.get("profile") or "") == p["profile"]))
    results.append(("PIX_FMT", v.get("pix_fmt") == p["pix_fmt"]))
    results.append(("SIZE", (v.get("width"), v.get("height")) == (p["width"], p["height"])))
    results.append(("PROGRESSIVE", (v.get("field_order") or "progressive") == "progressive"))
    results.append(("CONSTANT_FRAME_RATE", v.get("r_frame_rate") == v.get("avg_frame_rate")))
    results.append(("AUDIO_CODEC", a.get("codec_name") == p["audio_codec"]))
    results.append(("SAMPLE_RATE", str(a.get("sample_rate")) == str(p["sample_rate"])))
    results.append(("CHANNELS", a.get("channels") == p["channels"]))
    measured = loudnorm_measure(video, profile) if shutil.which("ffmpeg") else None
    if measured and silent and _is_silent(measured):
        results.append(("LOUDNESS", True))
        results.append(("TRUE_PEAK", True))
        results.append(("SILENT", True))
    elif measured:
        lufs = float(measured["input_i"])
        tp = float(measured["input_tp"])
        results.append(("LOUDNESS", abs(lufs - p["lufs"]) <= p["lufs_tolerance"]))
        results.append(("TRUE_PEAK", tp <= p["true_peak_max"]))
    else:
        results.append(("LOUDNESS", False))
        results.append(("TRUE_PEAK", False))
    return results


def _faststart(path):
    """moov before mdat: the first top-level box after ftyp is moov."""
    with open(path, "rb") as fh:
        head = fh.read(64 * 1024)
    return head.find(b"moov") != -1 and (head.find(b"mdat") == -1 or head.find(b"moov") < head.find(b"mdat"))


def cmd_verify(args):
    results = verify(args.video, args.profile, getattr(args, "silent", False))
    bad = 0
    for name, ok in results:
        if name == "SILENT":
            print("SILENT=1")
            continue
        print("%s=%s" % (name, "OK" if ok else "FAIL"))
        bad += 0 if ok else 1
    return 1 if bad else 0


def _srt_time(seconds):
    ms = int(round(seconds * 1000))
    return "%02d:%02d:%02d,%03d" % (ms // 3600000, ms // 60000 % 60, ms // 1000 % 60, ms % 1000)


def _yt_time(seconds):
    s = int(seconds)
    return "%d:%02d" % (s // 60, s % 60)


def cmd_sidecar(args):
    _need("ffprobe")
    with open(args.storyboard, encoding="utf-8") as fh:
        sb = json.load(fh)
    paths = read_list(args.list)
    if paths is None:
        return 1
    os.makedirs(args.out_dir, exist_ok=True)
    lang = args.lang
    lead = args.lead_in if args.lead_in is not None else float(sb.get("lead_in_s", 0.5))
    scenes = sb.get("scenes", [])
    srt, chapters, t, n = [], [], 0.0, 0
    for path in paths:
        dur = duration_of(path)
        if os.path.basename(path).startswith("title") or n >= len(scenes):
            t += dur   # the title card is no chapter but shifts every chapter after it
            continue
        scene = scenes[n]
        sid = str(scene.get("id", n + 1))
        n += 1
        text = (scene.get("narration") or {}).get(lang, "")
        title = (scene.get("title") or {}).get(lang) or scene.get("title") or sid
        if isinstance(title, dict):
            title = title.get(lang, sid)
        if text and args.narration_dir:
            wav = os.path.join(args.narration_dir, "%s.wav" % sid)
            spoken = duration_of(wav) if os.path.exists(wav) else max(0.0, dur - lead)
            srt.append("%d\n%s --> %s\n%s\n" % (len(srt) + 1, _srt_time(t + lead),
                                                _srt_time(max(t + lead + 0.5, t + lead + spoken - 0.2)), text))
        chapters.append("%s %s" % (_yt_time(t), title))
        t += dur
    if args.narration_dir:
        srt_path = os.path.join(args.out_dir, "%s.srt" % lang)
        with open(srt_path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(srt))
    meta = sb.get("publish", {}).get(lang, {})
    txt_path = os.path.join(args.out_dir, "%s.txt" % lang)
    with open(txt_path, "w", encoding="utf-8") as fh:
        fh.write("TITLE: %s\n\n%s\n\nCHAPTERS:\n%s\n" % (meta.get("title", sb.get("title", "")),
                                                        meta.get("description", ""), "\n".join(chapters)))
    if args.narration_dir:
        print("SRT=%s" % srt_path)
    else:
        print("CAPTIONS=none")
    print("TXT=%s" % txt_path)
    print("TOTAL_S=%.3f" % t)
    return 0


def cmd_thumbnail(args):
    _need("ffmpeg")
    if not os.path.isfile(args.video) or not os.access(args.video, os.R_OK):
        print("ERROR=%s: not a file" % args.video)
        return 1
    extracted = False
    for q in (2, 4, 6, 8, 12):
        proc = _run(["ffmpeg", "-v", "error", "-y", "-ss", "%g" % args.at, "-i", args.video,
                     "-frames:v", "1", "-vf", "scale=1280:720", "-q:v", str(q), args.out])
        if proc.returncode == 0:
            extracted = True
            if os.path.getsize(args.out) <= 2 * 1024 * 1024:
                print("OUT=%s" % args.out)
                print("BYTES=%d" % os.path.getsize(args.out))
                return 0
    if extracted:
        print("x thumbnail could not be kept under 2 MB", file=sys.stderr)
    else:
        print("x ffmpeg could not extract a frame from %s at %g s" % (args.video, args.at), file=sys.stderr)
    return 1


def cmd_preview(args):
    _need("ffmpeg")
    fps = frame_rate_of(args.video) or 25.0
    for crf in (28, 32, 36, 40):
        v = [a if a != "18" else str(crf) for a in video_args(args.profile, fps)]
        proc = _run(["ffmpeg", "-v", "error", "-y", "-i", args.video] + v
                    + ["-c:a", "aac", "-b:a", "96k", "-ac", "2", "-ar", "48000", args.out])
        if proc.returncode == 0 and os.path.getsize(args.out) <= args.max_mb * 1024 * 1024:
            print("OUT=%s" % args.out)
            print("BYTES=%d" % os.path.getsize(args.out))
            print("CRF=%d" % crf)
            return 0
    print("x preview could not be kept under %s MB" % args.max_mb, file=sys.stderr)
    return 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("fit"); p.add_argument("--clip", required=True); p.add_argument("--narration")
    p.add_argument("--out", required=True); p.add_argument("--lead-in", type=float, default=0.5, dest="lead_in")
    p.add_argument("--max-silence", type=float, default=3.0, dest="max_silence")
    p.add_argument("--max-hold", type=float, default=3.0, dest="max_hold")
    p.add_argument("--fade", type=float, default=0.3); p.add_argument("--profile", default="youtube-1080p")
    p.add_argument("--voice", action="append", help="FILE@T: extra audio mixed in at T seconds of the output")
    p = sub.add_parser("concat"); p.add_argument("--list", required=True); p.add_argument("--out", required=True)
    p.add_argument("--profile", default="youtube-1080p")
    p.add_argument("--music", help="royalty-free bed, ducked under the narration"); p.add_argument("--music-gain", type=float, default=MUSIC_GAIN_DB, dest="music_gain")
    p.add_argument("--music-license", dest="music_license", help="the licence the report states")
    p = sub.add_parser("zoom"); p.add_argument("--clip", required=True); p.add_argument("--out", required=True)
    p.add_argument("--focus", required=True, help="x,y,w,h of the area that matters, in clip pixels")
    p.add_argument("--from", type=float, required=True, dest="frm"); p.add_argument("--to", type=float, required=True)
    p.add_argument("--factor", type=float, default=1.6); p.add_argument("--ramp", type=float, default=0.6); p.add_argument("--profile", default="youtube-1080p")
    p = sub.add_parser("speedup"); p.add_argument("--clip", required=True); p.add_argument("--events", required=True); p.add_argument("--out", required=True)
    p.add_argument("--typing", type=float, default=3.0); p.add_argument("--travel", type=float, default=2.0)
    p.add_argument("--wait-keep", type=float, default=1.0, dest="wait_keep"); p.add_argument("--profile", default="youtube-1080p")
    p.add_argument("--wait-squeeze", type=float, default=1.0, dest="wait_squeeze")
    p.add_argument("--must-see", dest="must_see", help='"s,e;s,e" ranges played at 1x in full')
    p = sub.add_parser("audition"); p.add_argument("--narration", action="append", required=True); p.add_argument("--out-dir", required=True, dest="out_dir")
    p.add_argument("--music"); p.add_argument("--music-gain", type=float, default=MUSIC_GAIN_DB, dest="music_gain")
    p = sub.add_parser("title"); p.add_argument("--text", required=True); p.add_argument("--out", required=True)
    p.add_argument("--seconds", type=float, default=3.0); p.add_argument("--font"); p.add_argument("--size", default="1920x1080")
    p.add_argument("--fps", type=float, default=25.0); p.add_argument("--profile", default="youtube-1080p")
    p = sub.add_parser("verify"); p.add_argument("--video", required=True); p.add_argument("--profile", default="youtube-1080p")
    p.add_argument("--silent", action="store_true", help="a deliverable with no signal (-inf) passes loudness")
    p = sub.add_parser("verify-tools"); p.add_argument("--font")
    p = sub.add_parser("sidecar"); p.add_argument("--storyboard", required=True); p.add_argument("--lang", required=True)
    p.add_argument("--list", required=True, help="the concat list file"); p.add_argument("--out-dir", required=True, dest="out_dir")
    p.add_argument("--narration-dir", dest="narration_dir", help="<scene id>.wav per scene; enables the .srt")
    p.add_argument("--lead-in", type=float, dest="lead_in", help="default: the storyboard lead_in_s or 0.5")
    p = sub.add_parser("thumbnail"); p.add_argument("--video", required=True); p.add_argument("--at", type=float, default=2.0)
    p.add_argument("--out", required=True)
    p = sub.add_parser("preview"); p.add_argument("--video", required=True); p.add_argument("--out", required=True)
    p.add_argument("--max-mb", type=float, default=10.0, dest="max_mb"); p.add_argument("--profile", default="youtube-1080p")
    args = parser.parse_args(argv)
    if args.cmd not in ("sidecar", "verify-tools", "audition") and getattr(args, "profile", "youtube-1080p") not in PROFILES:
        print("x unknown profile %s (known: %s)" % (args.profile, ", ".join(PROFILES)), file=sys.stderr)
        return 1
    return {"fit": cmd_fit, "concat": cmd_concat, "title": cmd_title, "verify": cmd_verify, "verify-tools": cmd_verify_tools,
            "zoom": cmd_zoom, "speedup": cmd_speedup, "audition": cmd_audition,
            "sidecar": cmd_sidecar, "thumbnail": cmd_thumbnail, "preview": cmd_preview}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
