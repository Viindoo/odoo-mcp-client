#!/usr/bin/env python3
"""video_publish.py - narrated assembly and publish-profile verification for demo videos (ffmpeg).

Subcommands (stdlib + ffmpeg/ffprobe on PATH):
  verify-tools [--font F]  what this machine can do (ffmpeg, the filters, title card via drawtext or
            libass, the font and its Vietnamese coverage) - run BEFORE recording; exit 1 on a gap.
  speedup   --clip scene.mp4 --events scene.events.json --out scene-paced.mp4 [--typing 3] [--travel 2]
            [--wait-keep 1] [--wait-squeeze 1.0] [--must-see "s,e;s,e"] [--trim-head]
            [--narration scene.wav [--lead-in 0.5] [--tail 0.5] [--hold-floor 0.5]]
            the dead time the recorder logged (typing, cursor travel, page loads, waits) plays faster; a
            wait keeps its first --wait-keep seconds at 1x and the rest is time-compressed into
            --wait-squeeze seconds so the viewer sees the indicator move fast (0 = cut it). Kinds
            voice_in and voice_out stay 1x and are counted in SPANS. Any logged span overlapping a
            --must-see range plays at 1x in full (MUST_SEE_KEPT=n). A key_visible span means the take
            must not ship: prints KEY_VISIBLE=n, writes no output, exit 6. Everything else stays 1x.
            --trim-head cuts the clip to its first rendered frame: the head is the run of load and wait
            spans at the start of the events log (each starting within 0.5 s of the previous one's end),
            never past the first --must-see range; prints HEAD_CUT_S. --narration (with --lead-in, the
            same value `fit` gets) shortens the `hold` spans so the paced scene ends --tail seconds after
            the narration; every hold keeps at least --hold-floor seconds and a hold inside a
            --must-see range is untouched; prints HOLD_CUT_S (0 when the scene is not longer than that).
  map-times --events-from A.events.json --events-to B.events.json --times "s,e;s,e"
            maps times written for the take of A onto the take of B (the same scene recorded in another
            language) by event boundaries: both logs hold the same sequence of event kinds, each boundary
            of A pairs with the same boundary of B and a time in between is interpolated linearly. Prints
            TIMES="s,e;s,e" (the mapped ranges, in the same format as --must-see) and ANCHORS=n; a pair
            of logs with different kind sequences prints ERROR=... and exits 1.
  zoom      --clip scene.mp4 --focus x,y,w,h --from s --to s --out scene-zoomed.mp4 [--factor 1.6]
            a smooth punch-in on the area that matters (ease in, hold, ease out), --focus in the clip's
            own pixels. The output has the clip's frame size, or - for a clip larger than the profile -
            the clip's size scaled to fit the profile, so the zoom reads the take's real pixels and the
            picture is resampled once.
  audition  --narration a.wav [--narration b.wav ...] --out-dir D [--music bed.mp3]
            the same line per candidate voice, dry and with the music bed, for the owner to pick once.
  tempo     --narration in.wav --out out.wav --factor 1.08  changes the narration's speed by a factor
            (0.5-2.0, pitch unchanged) for a speech engine that ignores the `speed` parameter. Prints
            FACTOR, DURATION_S (of the result) and IN_DURATION_S.
  fit       --clip scene.mp4 [--narration scene.wav] --out scene-fitted.mp4 [--lead-in 0.5] [--max-hold 3]
            [--fade 0.3] [--max-silence 3.0] [--voice FILE@T ...]  The clip is scaled to the profile's
            frame size (aspect kept, padded with black). The narration starts after the lead-in; when
            it outlasts the clip the last frame is held; a short fade closes the scene; the length is a
            whole number of video frames. Each --voice (repeatable) is another audio track (the page's
            spoken answer, the voice input) mixed in at T seconds on the output timeline,
            loudness-matched to the narration. The audio of the output has a continuous packet timeline
            (one AAC frame between consecutive packets) and as many samples as its duration says.
            Prints DURATION_S and VOICES=n. Without --narration (a silent clip) the video keeps its
            own length (no hold, no lead-in), the --fade still closes it, the output carries a silent
            AAC 48 kHz stereo track so every fitted clip has one audio layout, and NARRATION=none is
            printed.

List file (concat --list, sidecar --list): one ABSOLUTE path per line, in play order, blank lines
ignored. Not ffmpeg's own `file '...'` syntax - concat builds its own graph. Both commands check the
list before any ffmpeg call and refuse a line that is not an existing file: `ERROR=list: <line>: not
a file` on stdout, exit 1.

Exit codes: 0 ok, 1 failure, 2 tool missing, 4 silence over the limit, 5 held frame over the limit,
6 a key field was shown on screen in the take (speedup).
  concat    --list clips.txt --out video.mp4  Concatenates fitted scenes (ffmpeg concat filter: every
            clip is scaled to the profile's frame size, its audio is rebuilt on one gapless timeline
            and cut or padded to its video length; one encode) and applies two-pass loudnorm to the
            profile target. An input without an audio stream gets a silent track of its length. The
            output audio keeps a continuous packet timeline. When nothing is audible (measured
            loudness -inf) the second pass is skipped, the output keeps a plain AAC 48 kHz stereo
            track and LOUDNESS=silent is printed.
  title     --text "..." --out card.mp4 --seconds 3 [--font ttf] [--size 1920x1080]
            A title card rendered from storyboard text (needs an ffmpeg with drawtext).
  verify    --video video.mp4 --profile youtube-1080p [--silent]  Reads ffprobe + ebur128 and prints one
            KEY=OK|FAIL line per rule; exit 1 on any FAIL. AUDIO_PACKETS fails when a step between
            consecutive audio packets differs from one AAC frame (1024 samples) by more than 1 ms;
            AUDIO_SAMPLES fails when the decoded audio length differs from the audio stream's duration
            by more than two AAC frames (the encoder's priming offset is within that). With --silent
            a deliverable with no signal at all (loudness -inf) passes LOUDNESS and TRUE_PEAK and
            SILENT=1 is printed; the audio stream rules (AAC, 48 kHz, stereo) still apply. Without it
            -inf fails.
  sidecar   --storyboard SB.json --lang xx_YY --list clips.txt --out-dir DIR [--narration-dir DIR]
            [--lead-in S] [--link URL ...]   --list is the file concat consumed; each scene starts where
            the REAL durations (ffprobe) of the preceding entries end. An entry whose basename starts
            with `title` is the title card: not a scene, but it counts in the offset. Writes <lang>.txt:
            exactly what the video's description should show - the description text, a blank line, the
            chapter lines (when there are any), a blank line, then one line per --link (repeatable, in
            the order given) - and, only with --narration-dir (<scene id>.wav per scene), <lang>.srt
            (one cue per narration line; the first cue starts at its scene start plus --lead-in, a later
            cue starts where the narration clip's silences say its sentence starts - silencedetect, no
            network; when the number of spoken stretches is not the number of lines the scene's spoken
            span, the clip's duration, is split between the lines in proportion to their character
            counts and CAPTION_FALLBACK=<scene ids> names the scene; a cue lasts at least 0.5 s and cues
            never overlap); otherwise prints CAPTIONS=none. Chapters: the first is at 0:00 (the title
            card belongs to it), each lasts at least 10 s (a shorter scene joins the chapter before it)
            and there are at least 3 or none; times from one hour on read h:mm:ss. Prints the paths,
            TITLE=<the video title for the upload>, CHAPTERS=<count>, THUMBNAIL_AT_S=<the second of the
            frame to use as thumbnail: 3 s into the first scene> and TOTAL_S.
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
import math
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


def video_seconds(path):
    """The video stream's length, a whole number of frames; the container's length for a stream
    that states none."""
    info = ffprobe(path)
    for s in info["streams"]:
        if s.get("codec_type") != "video":
            continue
        num, _, den = (s.get("r_frame_rate") or "0/1").partition("/")
        fps = float(num) / float(den or 1)
        frames = s.get("nb_frames") or ""
        if frames.isdigit() and fps > 0:
            return int(frames) / fps
        try:
            seconds = float(s.get("duration"))
        except (TypeError, ValueError):
            seconds = float(info["format"].get("duration") or 0.0)
        return round(seconds * fps) / fps if fps > 0 else seconds
    return float(info["format"].get("duration") or 0.0)


def frame_size_of(path):
    for s in ffprobe(path)["streams"]:
        if s.get("codec_type") == "video":
            return int(s.get("width") or 0), int(s.get("height") or 0)
    return 0, 0


def whole_frames(seconds, fps):
    """`seconds` rounded up to a whole number of frames at `fps`."""
    return math.ceil(seconds * fps - 1e-6) / fps


def size_filter(profile):
    """The video filter that brings any frame size to the profile's: scaled to fit (aspect kept),
    padded with black, square pixels."""
    p = PROFILES[profile]
    w, h = p["width"], p["height"]
    return ("scale=%d:%d:force_original_aspect_ratio=decrease:force_divisible_by=2:flags=lanczos,"
            "pad=%d:%d:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1" % (w, h, w, h))


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
    clip_s = video_seconds(args.clip)
    fps = frame_rate_of(args.clip) or 25.0
    if not args.narration:
        return _fit_silent(args, clip_s, fps)
    narration_s = duration_of(args.narration)
    total = whole_frames(max(clip_s, args.lead_in + narration_s + args.fade), fps)
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
    vf = "%s,tpad=stop_mode=clone:stop_duration=%.6f,fade=t=out:st=%.6f:d=%.3f" % (
        size_filter(args.profile), hold, max(0.0, total - args.fade), args.fade)
    lead_ms = int(round(args.lead_in * 1000))
    # one integrated loudness per narration clip BEFORE the mix: a retake recorded on another day (or
    # another take of one line) sits at the same level as its neighbours; the final two-pass loudnorm
    # in concat then only evens the whole file. loudnorm leaves timestamp jumps in its output, so every
    # track gets a clean sample-counted timeline right after it (asetpts), before the delay is applied
    level = "loudnorm=I=%s:TP=%s:LRA=11,aresample=48000,asetpts=N/SR/TB" % (NARRATION_LUFS, NARRATION_TP)
    af = "%s,adelay=delays=%d:all=1,apad=whole_dur=%.6f" % (level, lead_ms, total)
    # the closing resample lays the audio on a gapless timeline from 0
    gapless = "aresample=async=1:first_pts=0"
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
            fc += (";[%d:a]%s,adelay=delays=%d:all=1,aformat=channel_layouts=stereo[x%d]"
                   % (i, level, ms, i))
        fc += ";[n]%samix=inputs=%d:duration=longest:dropout_transition=0:normalize=0,asetpts=N/SR/TB,%s[a]" % (
            "".join("[x%d]" % i for i in range(2, 2 + len(voices))), len(voices) + 1, gapless)
    else:
        fc += "[1:a]%s,%s[a]" % (af, gapless)
    cmd = ["ffmpeg", "-v", "error", "-y"] + inputs + [
           "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
           "-t", "%.6f" % total] + video_args(args.profile, fps) + audio_args(args.profile) + [args.out]
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
    vf = "%s,fade=t=out:st=%.6f:d=%.3f" % (size_filter(args.profile), max(0.0, clip_s - args.fade), args.fade)
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", args.clip, "-f", "lavfi", "-i", SILENCE_SRC,
           "-filter_complex", "[0:v]%s[v]" % vf, "-map", "[v]", "-map", "1:a",
           "-t", "%.6f" % clip_s] + video_args(args.profile, fps) + audio_args(args.profile) + [args.out]
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


def _concat_graph(clips, profile):
    """(ffmpeg input args, filter_complex) of the concat filter over `clips`: each clip's picture is
    brought to the profile's size on a timeline from 0, its audio is rebuilt on one gapless
    sample-counted timeline and cut or padded to the clip's video length; a clip with no audio
    stream is given a silent track of its length."""
    inputs, parts, joined = [], [], ""
    for c in clips:
        inputs += ["-i", c]
    next_input = len(clips)
    for i, c in enumerate(clips):
        seconds = video_seconds(c)
        if _has_audio(c):
            src = "%d:a" % i
        else:
            inputs += ["-f", "lavfi", "-i", SILENCE_SRC]
            src = "%d:a" % next_input
            next_input += 1
        parts.append("[%d:v]%s,setpts=PTS-STARTPTS[v%d]" % (i, size_filter(profile), i))
        parts.append("[%s]aresample=48000,asetpts=N/SR/TB,aformat=channel_layouts=stereo,"
                     "apad=whole_dur=%.6f,atrim=0:%.6f,asetpts=N/SR/TB[a%d]" % (src, seconds, seconds, i))
        joined += "[v%d][a%d]" % (i, i)
    parts.append("%sconcat=n=%d:v=1:a=1[v][a]" % (joined, len(clips)))
    return inputs, ";".join(parts)


def cmd_concat(args):
    _need("ffmpeg")
    clips = read_list(args.list)
    if clips is None:
        return 1
    if not clips:
        print("x no clips listed", file=sys.stderr)
        return 1
    fps = frame_rate_of(clips[0]) or 25.0
    raw = args.out + ".raw.mov"
    scratch = [raw]
    try:
        inputs, graph = _concat_graph(clips, args.profile)
        # one encode of the picture; the audio stays uncompressed until the final pass, so the
        # delivered AAC stream is encoded once
        proc = _run(["ffmpeg", "-v", "error", "-y"] + inputs + ["-filter_complex", graph, "-map", "[v]", "-map", "[a]"]
                    + video_args(args.profile, fps) + ["-c:a", "pcm_s16le", raw])
        if proc.returncode != 0:
            print("x concat failed: %s" % proc.stderr.strip()[-400:], file=sys.stderr)
            return 1
        if getattr(args, "music", None):
            bedded = args.out + ".bed.mkv"
            scratch.append(bedded)
            proc = add_music(raw, args.music, bedded, args.music_gain)
            if proc.returncode != 0:
                print("x music bed failed: %s" % proc.stderr.strip()[-400:], file=sys.stderr)
                return 1
            raw = bedded
            print("MUSIC=%s (%gdB under the narration, ducked)" % (os.path.basename(args.music), args.music_gain))
            print("MUSIC_LICENSE=%s" % (args.music_license or "UNSTATED - the report must state it"))
        measured = loudnorm_measure(raw, args.profile)
        p = PROFILES[args.profile]
        silent = _is_silent(measured)
        norm = "loudnorm=I=%s:TP=%s:LRA=11" % (p["lufs"], p["true_peak"])
        if measured and not silent:
            norm += (":measured_I=%s:measured_TP=%s:measured_LRA=%s:measured_thresh=%s:offset=%s"
                     ":linear=true" % (measured["input_i"], measured["input_tp"], measured["input_lra"],
                                       measured["input_thresh"], measured["target_offset"]))
        # loudnorm leaves timestamp jumps: the audio is laid on a gapless sample-counted timeline
        # from 0 after it
        tail = "aresample=48000,asetpts=N/SR/TB,aresample=async=1:first_pts=0"
        if silent:
            print("LOUDNESS=silent")   # nothing to normalise: no second loudnorm pass
            af = ["-af", tail]
        else:
            af = ["-af", "%s,%s" % (norm, tail)]
        proc = _run(["ffmpeg", "-v", "error", "-y", "-i", raw, "-c:v", "copy"] + af
                    + audio_args(args.profile) + ["-movflags", "+faststart", args.out])
        if proc.returncode != 0:
            print("x loudnorm pass failed: %s" % proc.stderr.strip()[-400:], file=sys.stderr)
            return 1
    finally:
        for f in scratch:
            if os.path.exists(f):
                os.unlink(f)
    print("OUT=%s" % args.out)
    print("DURATION_S=%.3f" % duration_of(args.out))
    return 0


# --------------------------------------------------------------------------- pacing
def _ease(expr):
    """smoothstep of a 0..1 expression, as ffmpeg expression text."""
    return "(%s)*(%s)*(3-2*(%s))" % (expr, expr, expr)


def zoom_output_size(width, height, profile):
    """The frame size a zoom renders at: the clip's own, or - for a clip larger than the profile -
    the clip's size scaled to fit the profile (aspect kept, even sides)."""
    p = PROFILES[profile]
    if width <= p["width"] and height <= p["height"]:
        return width, height
    k = min(p["width"] / float(width), p["height"] / float(height))
    return int(round(width * k / 2.0)) * 2, int(round(height * k / 2.0)) * 2


def cmd_zoom(args):
    """A smooth punch-in on the focus box between --from and --to (ease in, hold, ease out). The
    zoom reads the take's own pixels and renders at the output size (the take's, or the profile's
    when the take is larger), so text stays sharp and the picture is resampled once; the rest of
    the clip is untouched. Captions and title cards are never zoomed - this runs on a scene clip
    only."""
    _need("ffmpeg")
    fps = frame_rate_of(args.clip) or 25.0
    info = ffprobe(args.clip)
    v = next((s for s in info["streams"] if s.get("codec_type") == "video"), {})
    W, H = int(v.get("width") or 1920), int(v.get("height") or 1080)
    OW, OH = zoom_output_size(W, H, args.profile)
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
    zp = "zoompan=z='%s':x='%s':y='%s':d=1:s=%dx%d:fps=%g" % (zexpr, xexpr, yexpr, OW, OH, fps)
    fit = "" if (OW, OH) == (W, H) else ",scale=%d:%d:flags=lanczos" % (OW, OH)
    fc = ("[0:v]split=3[a][b][c];"
          "[a]trim=0:%(f).3f,setpts=PTS-STARTPTS%(fit)s[pre];"
          "[b]trim=%(f).3f:%(t).3f,setpts=PTS-STARTPTS,%(zp)s[mid];"
          "[c]trim=%(t).3f,setpts=PTS-STARTPTS%(fit)s[post];"
          "[pre][mid][post]concat=n=3:v=1:a=0[v]" % {"f": args.frm, "t": args.to, "zp": zp, "fit": fit})
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
    print("SIZE=%dx%d" % (OW, OH))
    return 0


def _ranges(text):
    """`"s,e;s,e"` -> [(s, e), ...]."""
    out = []
    for part in (text or "").split(";"):
        if part.strip():
            lo, _, hi = part.partition(",")
            out.append((float(lo), float(hi)))
    return out


KEPT_KINDS = ("hold", "voice_in", "voice_out")   # logged for the report, played at 1x (a hold may be shortened)
HEAD_KINDS = ("load", "wait")   # the spans of a take's head, before the first rendered frame
HEAD_GAP_S = 0.5                # a head span starts at most this long after the one before it ends


def _head_end(events, must_see):
    """When the take's first rendered frame shows: the end of the run of load / wait spans at the
    start of the sorted events (each starting within HEAD_GAP_S of the previous end), never past
    the first must-see range. 0.0 when the log does not start with such a run."""
    end = 0.0
    for e in events:
        if e.get("kind") not in HEAD_KINDS or float(e.get("start", 0)) - end > HEAD_GAP_S:
            break
        end = max(end, float(e.get("end", 0)))
    if must_see:
        end = min(end, min(lo for lo, _ in must_see))
    return end if end > 0.05 else 0.0


def _read_events(path):
    with open(path, encoding="utf-8") as fh:
        return sorted((e for e in json.load(fh) if isinstance(e, dict)), key=lambda e: float(e.get("start", 0)))


def cmd_speedup(args):
    """Compress the dead time the recorder logged: each event span of a kind named in --typing /
    --travel plays faster (typing, cursor travel, scrolling, a page load); a wait keeps its first
    --wait-keep seconds and squeezes the rest into --wait-squeeze seconds (0 = cut); everything else
    plays at 1x. --trim-head first cuts the clip to its first rendered frame. With --narration the
    hold spans are shortened (never below --hold-floor) so the paced scene ends --tail seconds
    after the narration that starts at --lead-in. The events file is the recorder's
    `<scene>.events.json`:
    [{"kind": "typing|wait|travel|load|hold|voice_in|voice_out|key_visible", "start": s, "end": s}].
    A key_visible span stops the run (exit 6, no output)."""
    _need("ffmpeg")
    events = _read_events(args.events)
    shown = [e for e in events if e.get("kind") == "key_visible"]
    if shown:
        print("KEY_VISIBLE=%d" % len(shown))
        print("x a key field was shown on screen in this take (%d span%s): re-record it with the value masked"
              % (len(shown), "" if len(shown) == 1 else "s"), file=sys.stderr)
        return 6
    must_see = _ranges(args.must_see)
    total = duration_of(args.clip)
    target = None
    if args.narration:
        target = args.lead_in + duration_of(args.narration) + args.tail
    factors = {"typing": args.typing, "travel": args.travel, "load": args.travel}
    spans, holds, cursor, counted, protected = [], [], 0.0, 0, 0
    head = min(_head_end(events, must_see), total) if args.trim_head else 0.0
    if head > 0:
        spans.append((0.0, head, 0.0))   # 0 = cut
        cursor = head
    for e in events:
        s, en, kind = float(e.get("start", 0)), float(e.get("end", 0)), e.get("kind", "")
        if en <= s or s < cursor or en > total + 0.01:
            continue
        if kind in KEPT_KINDS:
            counted += 1
            if (kind == "hold" and target is not None and en - s > args.hold_floor
                    and not any(s < hi and en > lo for lo, hi in must_see)):
                if s > cursor:
                    spans.append((cursor, s, 1.0))
                holds.append(len(spans))
                spans.append((s, en, 1.0))
                cursor = en
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
                squeezed = min(args.wait_squeeze, rest)
                spans.append((s + keep, en, rest / squeezed))
            elif rest > 0:
                spans.append((s + keep, en, 0.0))   # 0 = cut
        else:
            if s > cursor:
                spans.append((cursor, s, 1.0))
            spans.append((s, en, factors[kind]))
        cursor = en
    if cursor < total:
        spans.append((cursor, total, 1.0))
    hold_cut = 0.0
    if target is not None and holds:
        excess = sum((en - s) / f for s, en, f in spans if f > 0) - target
        room = [spans[i][1] - spans[i][0] - args.hold_floor for i in holds]
        if excess > 0 and sum(room) > 0:
            take = min(excess, sum(room))
            for i, r in zip(holds, room):
                cut = take * r / sum(room)
                s, en, f = spans[i]
                spans[i] = (s, en - cut, 1.0)
                hold_cut += cut
    kept = [sp for sp in spans if sp[2] > 0 and sp[1] - sp[0] > 0.001]
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
    print("SPANS=%d" % (len([sp for sp in spans if sp[2] != 1.0 and sp[1] - sp[0] > 0.001]) + counted))
    print("MUST_SEE_KEPT=%d" % protected)
    print("HEAD_CUT_S=%.3f" % head)
    print("HOLD_CUT_S=%.3f" % hold_cut)
    return 0


def _map_time(t, anchors):
    """`t` mapped through the piecewise-linear map of `anchors` ((from, to) pairs sorted by from);
    outside the first and last anchor the offset of that anchor holds."""
    if t <= anchors[0][0]:
        return max(0.0, anchors[0][1] + (t - anchors[0][0]))
    if t >= anchors[-1][0]:
        return anchors[-1][1] + (t - anchors[-1][0])
    for (a0, b0), (a1, b1) in zip(anchors, anchors[1:]):
        if a0 <= t <= a1:
            return b0 if a1 == a0 else b0 + (b1 - b0) * (t - a0) / (a1 - a0)
    return t


def cmd_map_times(args):
    """Times written for the take of one language, mapped onto the take of another by event
    boundaries: the two logs hold the same sequence of event kinds, so the k-th boundary of one is
    the k-th boundary of the other."""
    ev_from, ev_to = _read_events(args.events_from), _read_events(args.events_to)
    kinds_from, kinds_to = [e.get("kind") for e in ev_from], [e.get("kind") for e in ev_to]
    if kinds_from != kinds_to:
        print("ERROR=event sequence differs: %d events (%s) against %d events (%s)"
              % (len(kinds_from), ",".join(map(str, kinds_from)), len(kinds_to), ",".join(map(str, kinds_to))))
        return 1
    pairs = []
    for a, b in zip(ev_from, ev_to):
        pairs.append((float(a.get("start", 0)), float(b.get("start", 0))))
        pairs.append((float(a.get("end", 0)), float(b.get("end", 0))))
    pairs.sort()
    anchors = []
    for a, b in pairs:
        b = max(b, anchors[-1][1]) if anchors else b   # the mapped time never runs backwards
        if anchors and anchors[-1][0] == a:
            anchors[-1] = (a, b)
        else:
            anchors.append((a, b))
    if not anchors:
        print("ERROR=no events to map by")
        return 1
    mapped = ["%.3f,%.3f" % (_map_time(lo, anchors), _map_time(hi, anchors)) for lo, hi in _ranges(args.times)]
    print("TIMES=%s" % ";".join(mapped))
    print("ANCHORS=%d" % len(anchors))
    return 0


def cmd_tempo(args):
    """The narration clip played faster or slower by --factor, pitch unchanged (ffmpeg atempo)."""
    _need("ffmpeg")
    if not 0.5 <= args.factor <= 2.0:
        print("x --factor must be within 0.5 and 2.0, got %g" % args.factor, file=sys.stderr)
        return 1
    proc = _run(["ffmpeg", "-v", "error", "-y", "-i", args.narration, "-af", "atempo=%.6f" % args.factor, args.out])
    if proc.returncode != 0:
        print("x tempo failed: %s" % proc.stderr.strip()[-400:], file=sys.stderr)
        return 1
    print("OUT=%s" % args.out)
    print("FACTOR=%g" % args.factor)
    print("IN_DURATION_S=%.3f" % duration_of(args.narration))
    print("DURATION_S=%.3f" % duration_of(args.out))
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


AAC_FRAME = 1024                 # samples in one AAC packet
PACKET_STEP_TOLERANCE_S = 0.001  # a step between audio packets may differ from one frame by this
SAMPLE_TOLERANCE_FRAMES = 2      # decoded length vs stream duration: the priming offset and one frame


def audio_packet_times(path):
    """The presentation time (s) of every packet of the first audio stream."""
    _need("ffprobe")
    proc = _run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "packet=pts_time",
                 "-of", "default=noprint_wrappers=1:nokey=1", path])
    times = []
    for line in proc.stdout.split():
        try:
            times.append(float(line))
        except ValueError:
            pass
    return times


def audio_steps_regular(path, sample_rate):
    """Whether every step between consecutive audio packets is one AAC frame (the packet timeline
    has no hole and no overlap); the offset of the first packet (encoder priming) is ignored."""
    times = audio_packet_times(path)
    frame = AAC_FRAME / float(sample_rate)
    return len(times) > 0 and all(abs((b - a) - frame) <= PACKET_STEP_TOLERANCE_S
                                  for a, b in zip(times, times[1:]))


def decoded_audio_samples(path):
    """The number of samples the first audio stream decodes to (counted, never held in memory)."""
    _need("ffmpeg")
    proc = subprocess.Popen(["ffmpeg", "-v", "error", "-i", path, "-map", "0:a:0", "-ac", "1", "-f", "s16le", "-"],
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    size = 0
    while True:
        chunk = proc.stdout.read(1 << 20)
        if not chunk:
            break
        size += len(chunk)
    proc.wait()
    return size // 2


def audio_samples_match(path, stream, info, sample_rate):
    """Whether the decoded audio is as long as the audio stream says, within the encoder's priming
    offset and one frame."""
    try:
        seconds = float(stream.get("duration"))
    except (TypeError, ValueError):
        seconds = float(info["format"].get("duration") or 0.0)
    decoded = decoded_audio_samples(path) / float(sample_rate)
    return abs(decoded - seconds) <= SAMPLE_TOLERANCE_FRAMES * AAC_FRAME / float(sample_rate)


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
    results.append(("AUDIO_PACKETS", bool(a) and audio_steps_regular(video, p["sample_rate"])))
    results.append(("AUDIO_SAMPLES", bool(a) and audio_samples_match(video, a, info, p["sample_rate"])))
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
    if s >= 3600:
        return "%d:%02d:%02d" % (s // 3600, s // 60 % 60, s % 60)
    return "%d:%02d" % (s // 60, s % 60)


MIN_CUE_S = 0.5   # a caption cue never stays on screen shorter than this
CUE_TAIL_S = 0.2  # the last cue of a scene lifts this early so it does not touch the next scene's
SENTENCE_SILENCE_DB = -35   # below this level the narration clip is silent
SENTENCE_GAP_S = 0.25       # a silence at least this long separates two sentences
MIN_SPEECH_S = 0.05         # a sound shorter than this is no sentence
MIN_CHAPTER_S = 10          # YouTube ignores a chapter list with a shorter chapter
MIN_CHAPTERS = 3            # ... and one with fewer chapters
THUMBNAIL_OFFSET_S = 3.0    # the thumbnail frame is this far into the first scene


def _speech_stretches(wav):
    """``[(start, end)]`` of the spoken stretches of a narration clip, between its silences
    (ffmpeg silencedetect, local); None when ffmpeg cannot read the clip."""
    proc = _run(["ffmpeg", "-v", "info", "-i", wav, "-af",
                 "silencedetect=noise=%ddB:d=%g" % (SENTENCE_SILENCE_DB, SENTENCE_GAP_S), "-f", "null", "-"])
    if proc.returncode != 0:
        return None
    total = duration_of(wav)
    silences, opened = [], None
    for line in proc.stderr.splitlines():
        m = re.search(r"silence_start: (-?[\d.]+)", line)
        if m:
            opened = max(0.0, float(m.group(1)))
        m = re.search(r"silence_end: (-?[\d.]+)", line)
        if m and opened is not None:
            silences.append((opened, float(m.group(1))))
            opened = None
    if opened is not None:
        silences.append((opened, total))
    stretches, pos = [], 0.0
    for lo, hi in silences:
        if lo - pos > MIN_SPEECH_S:
            stretches.append((pos, lo))
        pos = max(pos, hi)
    if total - pos > MIN_SPEECH_S:
        stretches.append((pos, total))
    return stretches


def _caption_cues(text, start, spoken, onsets=None):
    """One ``(start, end, line)`` per non-blank narration line.

    With ``onsets`` (the offset in the narration clip where each line starts, one per line) the
    first cue starts at ``start`` and each later cue at ``start`` plus its onset; without them the
    spoken span is split between the lines in proportion to their character counts. Each cue
    starts where the previous one ends, none is shorter than ``MIN_CUE_S`` and none overlaps.
    """
    lines = [ln.strip() for ln in str(text).splitlines() if ln.strip()]
    total = sum(len(ln) for ln in lines)
    cues, cursor = [], start
    for i, ln in enumerate(lines):
        if onsets is not None:
            nxt = start + onsets[i + 1] if i + 1 < len(lines) else start + spoken
            end = max(cursor + MIN_CUE_S, nxt)
        else:
            end = cursor + max(MIN_CUE_S, spoken * len(ln) / total)
        if i == len(lines) - 1:
            end = max(cursor + MIN_CUE_S, end - CUE_TAIL_S)
        cues.append((cursor, end, ln))
        cursor = end
    return cues


def _chapters(scenes, total):
    """``[(start, title)]`` for the video description from ``scenes`` (``(start, title)`` per
    scene, in play order): the first chapter is at 0 (a title card before the first scene belongs
    to it), a scene that would make a chapter shorter than MIN_CHAPTER_S joins the chapter before
    it, and fewer than MIN_CHAPTERS chapters means none."""
    if not scenes:
        return []
    chosen = [(0.0, scenes[0][1])]
    for start, title in scenes[1:]:
        if int(start) - int(chosen[-1][0]) >= MIN_CHAPTER_S and int(total) - int(start) >= MIN_CHAPTER_S:
            chosen.append((start, title))
    return chosen if len(chosen) >= MIN_CHAPTERS else []


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
    srt, starts, fallback, t, n = [], [], [], 0.0, 0
    for path in paths:
        dur = duration_of(path)
        if os.path.basename(path).startswith("title") or n >= len(scenes):
            t += dur   # the title card is no scene but shifts every scene after it
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
            lines = [ln for ln in str(text).splitlines() if ln.strip()]
            onsets = None
            if len(lines) > 1:
                stretches = _speech_stretches(wav) if os.path.exists(wav) else None
                if stretches is not None and len(stretches) == len(lines):
                    onsets = [lo for lo, _ in stretches]
                else:
                    fallback.append(sid)
            for start, end, line in _caption_cues(text, t + lead, spoken, onsets):
                srt.append("%d\n%s --> %s\n%s\n" % (len(srt) + 1, _srt_time(start), _srt_time(end), line))
        starts.append((t, title))
        t += dur
    chapters = _chapters(starts, t)
    if args.narration_dir:
        srt_path = os.path.join(args.out_dir, "%s.srt" % lang)
        with open(srt_path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(srt))
    meta = sb.get("publish", {}).get(lang, {})
    title = " ".join(str(meta.get("title", sb.get("title", ""))).split())
    blocks = [str(meta.get("description", "")).strip(),
              "\n".join("%s %s" % (_yt_time(start), name) for start, name in chapters),
              "\n".join(args.link or [])]
    txt_path = os.path.join(args.out_dir, "%s.txt" % lang)
    with open(txt_path, "w", encoding="utf-8") as fh:
        fh.write("\n\n".join(b for b in blocks if b) + "\n")
    if args.narration_dir:
        print("SRT=%s" % srt_path)
    else:
        print("CAPTIONS=none")
    print("TXT=%s" % txt_path)
    print("TITLE=%s" % title)
    print("CHAPTERS=%d" % len(chapters))
    first = starts[0][0] if starts else 0.0
    print("THUMBNAIL_AT_S=%.3f" % min(first + THUMBNAIL_OFFSET_S, max(0.0, t - 0.5)))
    print("TOTAL_S=%.3f" % t)
    if fallback:
        print("CAPTION_FALLBACK=%s" % ",".join(fallback))
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
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
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
    p.add_argument("--trim-head", action="store_true", dest="trim_head", help="cut the clip to its first rendered frame")
    p.add_argument("--narration", help="the scene's narration clip: hold spans are shortened to end --tail after it")
    p.add_argument("--lead-in", type=float, default=0.5, dest="lead_in", help="where the narration starts (as in fit)")
    p.add_argument("--tail", type=float, default=0.5, help="seconds the scene runs after the narration ends")
    p.add_argument("--hold-floor", type=float, default=0.5, dest="hold_floor", help="a hold is never shortened below this")
    p = sub.add_parser("map-times"); p.add_argument("--events-from", required=True, dest="events_from")
    p.add_argument("--events-to", required=True, dest="events_to"); p.add_argument("--times", required=True, help='"s,e;s,e"')
    p = sub.add_parser("tempo"); p.add_argument("--narration", required=True); p.add_argument("--out", required=True)
    p.add_argument("--factor", type=float, required=True, help="speed factor, 0.5-2.0 (1.08 = 8%% faster), pitch unchanged")
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
    p.add_argument("--link", action="append", default=[], help="a URL line closing the description (repeatable, in order)")
    p = sub.add_parser("thumbnail"); p.add_argument("--video", required=True); p.add_argument("--at", type=float, default=2.0)
    p.add_argument("--out", required=True)
    p = sub.add_parser("preview"); p.add_argument("--video", required=True); p.add_argument("--out", required=True)
    p.add_argument("--max-mb", type=float, default=10.0, dest="max_mb"); p.add_argument("--profile", default="youtube-1080p")
    args = parser.parse_args(argv)
    if args.cmd not in ("sidecar", "verify-tools", "audition", "map-times", "tempo") and getattr(args, "profile", "youtube-1080p") not in PROFILES:
        print("x unknown profile %s (known: %s)" % (args.profile, ", ".join(PROFILES)), file=sys.stderr)
        return 1
    return {"fit": cmd_fit, "concat": cmd_concat, "title": cmd_title, "verify": cmd_verify, "verify-tools": cmd_verify_tools,
            "zoom": cmd_zoom, "speedup": cmd_speedup, "audition": cmd_audition,
            "map-times": cmd_map_times, "tempo": cmd_tempo,
            "sidecar": cmd_sidecar, "thumbnail": cmd_thumbnail, "preview": cmd_preview}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
