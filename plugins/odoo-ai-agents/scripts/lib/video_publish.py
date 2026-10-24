#!/usr/bin/env python3
"""video_publish.py - narrated assembly and publish-profile verification for demo videos (ffmpeg).

Subcommands (stdlib + ffmpeg/ffprobe on PATH):
  verify-tools [--font F]  what this machine can do (ffmpeg, the filters, title card via drawtext or
            libass, the font and its Vietnamese coverage) - run BEFORE recording; exit 1 on a gap.
  fit       --clip scene.mp4 --narration scene.wav --out scene-fitted.mp4 [--lead-in 0.5]
            [--fade 0.3] [--max-silence 3.0]  The narration starts after the lead-in; when it outlasts the clip the
            last frame is held; a short fade closes the scene. Prints DURATION_S.
  concat    --list clips.txt --out video.mp4  Concatenates fitted scenes (ffmpeg concat demuxer,
            re-encoded once) and applies two-pass loudnorm to the profile target.
  title     --text "..." --out card.mp4 --seconds 3 [--font ttf] [--size 1920x1080]
            A title card rendered from storyboard text (needs an ffmpeg with drawtext).
  verify    --video video.mp4 --profile youtube-1080p  Reads ffprobe + ebur128 and prints one
            KEY=OK|FAIL line per rule; exit 1 on any FAIL.
  sidecar   --storyboard SB.json --lang xx_YY --durations D.json --out-dir DIR
            Writes <lang>.srt (one cue per scene, timed by the measured durations), <lang>.txt
            (title, description, chapters at the real offsets) and prints the paths.
  thumbnail --video video.mp4 --at 2.0 --out thumb.jpg  A 1280x720 JPEG under 2 MB.
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
    narration_s = duration_of(args.narration)
    fps = frame_rate_of(args.clip) or 25.0
    total = max(clip_s, args.lead_in + narration_s + args.fade)
    hold = max(0.0, total - clip_s)
    # the part of the scene where the screen moves and nobody speaks (the lead-in is deliberate)
    silent = max(0.0, clip_s - args.lead_in - narration_s)
    vf = "tpad=stop_mode=clone:stop_duration=%.3f,fade=t=out:st=%.3f:d=%.3f" % (
        hold, max(0.0, total - args.fade), args.fade)
    # one integrated loudness per narration clip BEFORE the mix: a retake recorded on another day (or
    # another take of one line) sits at the same level as its neighbours; the final two-pass loudnorm
    # in concat then only evens the whole file
    af = "loudnorm=I=%s:TP=%s:LRA=11,aresample=48000,adelay=%d|%d,apad=whole_dur=%.3f" % (
        NARRATION_LUFS, NARRATION_TP, int(args.lead_in * 1000), int(args.lead_in * 1000), total)
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", args.clip, "-i", args.narration,
           "-filter_complex", "[0:v]%s[v];[1:a]%s[a]" % (vf, af), "-map", "[v]", "-map", "[a]",
           "-t", "%.3f" % total] + video_args(args.profile, fps) + audio_args(args.profile) + [args.out]
    proc = _run(cmd)
    if proc.returncode != 0:
        print("x ffmpeg fit failed: %s" % proc.stderr.strip()[-400:], file=sys.stderr)
        return 1
    print("OUT=%s" % args.out)
    print("DURATION_S=%.3f" % total)
    print("HOLD_S=%.3f" % hold)
    print("SILENT_S=%.3f" % silent)
    if silent > args.max_silence:
        print("SILENCE=over")
        print("x the screen moves for %.1f s with nobody speaking (limit %.1f s): say what it shows, "
              "or shorten the scene" % (silent, args.max_silence), file=sys.stderr)
        return 4
    print("SILENCE=ok")
    return 0


def loudnorm_measure(path, profile):
    p = PROFILES[profile]
    proc = _run(["ffmpeg", "-v", "info", "-i", path, "-af",
                 "loudnorm=I=%s:TP=%s:LRA=11:print_format=json" % (p["lufs"], p["true_peak"]),
                 "-f", "null", "-"])
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", proc.stderr, re.S)
    return json.loads(m.group(0)) if m else None


def cmd_concat(args):
    _need("ffmpeg")
    with open(args.list, encoding="utf-8") as fh:
        clips = [line.strip() for line in fh if line.strip() and not line.startswith("#")]
    if not clips:
        print("x no clips listed", file=sys.stderr)
        return 1
    fps = frame_rate_of(clips[0]) or 25.0
    listfile = args.out + ".concat.txt"
    with open(listfile, "w", encoding="utf-8") as fh:
        for c in clips:
            fh.write("file '%s'\n" % os.path.abspath(c).replace("'", "'\\''"))
    raw = args.out + ".raw.mp4"
    try:
        proc = _run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", listfile]
                    + video_args(args.profile, fps) + audio_args(args.profile) + [raw])
        if proc.returncode != 0:
            print("x concat failed: %s" % proc.stderr.strip()[-400:], file=sys.stderr)
            return 1
        measured = loudnorm_measure(raw, args.profile)
        p = PROFILES[args.profile]
        af = "loudnorm=I=%s:TP=%s:LRA=11" % (p["lufs"], p["true_peak"])
        if measured:
            af += (":measured_I=%s:measured_TP=%s:measured_LRA=%s:measured_thresh=%s:offset=%s"
                   ":linear=true" % (measured["input_i"], measured["input_tp"], measured["input_lra"],
                                     measured["input_thresh"], measured["target_offset"]))
        proc = _run(["ffmpeg", "-v", "error", "-y", "-i", raw, "-c:v", "copy", "-af", af]
                    + audio_args(args.profile) + ["-movflags", "+faststart", args.out])
        if proc.returncode != 0:
            print("x loudnorm pass failed: %s" % proc.stderr.strip()[-400:], file=sys.stderr)
            return 1
    finally:
        for f in (listfile, raw):
            if os.path.exists(f):
                os.unlink(f)
    print("OUT=%s" % args.out)
    print("DURATION_S=%.3f" % duration_of(args.out))
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


def verify(video, profile):
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
    if measured:
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
    results = verify(args.video, args.profile)
    bad = 0
    for name, ok in results:
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
    with open(args.storyboard, encoding="utf-8") as fh:
        sb = json.load(fh)
    with open(args.durations, encoding="utf-8") as fh:
        durations = json.load(fh)  # {"<scene id>": seconds}
    os.makedirs(args.out_dir, exist_ok=True)
    lang = args.lang
    srt, chapters, t = [], [], 0.0
    for i, scene in enumerate(sb.get("scenes", []), 1):
        sid = str(scene.get("id", i))
        dur = float(durations.get(sid, 0.0))
        text = (scene.get("narration") or {}).get(lang, "")
        title = (scene.get("title") or {}).get(lang) or scene.get("title") or sid
        if isinstance(title, dict):
            title = title.get(lang, sid)
        lead = float(sb.get("lead_in_s", 0.5))
        if text:
            srt.append("%d\n%s --> %s\n%s\n" % (len(srt) + 1, _srt_time(t + lead),
                                                _srt_time(max(t + lead + 0.5, t + dur - 0.2)), text))
        chapters.append("%s %s" % (_yt_time(t), title))
        t += dur
    srt_path = os.path.join(args.out_dir, "%s.srt" % lang)
    with open(srt_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(srt))
    meta = sb.get("publish", {}).get(lang, {})
    txt_path = os.path.join(args.out_dir, "%s.txt" % lang)
    with open(txt_path, "w", encoding="utf-8") as fh:
        fh.write("TITLE: %s\n\n%s\n\nCHAPTERS:\n%s\n" % (meta.get("title", sb.get("title", "")),
                                                        meta.get("description", ""), "\n".join(chapters)))
    print("SRT=%s" % srt_path)
    print("TXT=%s" % txt_path)
    print("TOTAL_S=%.3f" % t)
    return 0


def cmd_thumbnail(args):
    _need("ffmpeg")
    for q in (2, 4, 6, 8, 12):
        proc = _run(["ffmpeg", "-v", "error", "-y", "-ss", "%g" % args.at, "-i", args.video,
                     "-frames:v", "1", "-vf", "scale=1280:720", "-q:v", str(q), args.out])
        if proc.returncode == 0 and os.path.getsize(args.out) <= 2 * 1024 * 1024:
            print("OUT=%s" % args.out)
            print("BYTES=%d" % os.path.getsize(args.out))
            return 0
    print("x thumbnail could not be kept under 2 MB", file=sys.stderr)
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
    p = sub.add_parser("fit"); p.add_argument("--clip", required=True); p.add_argument("--narration", required=True)
    p.add_argument("--out", required=True); p.add_argument("--lead-in", type=float, default=0.5, dest="lead_in")
    p.add_argument("--max-silence", type=float, default=3.0, dest="max_silence")
    p.add_argument("--fade", type=float, default=0.3); p.add_argument("--profile", default="youtube-1080p")
    p = sub.add_parser("concat"); p.add_argument("--list", required=True); p.add_argument("--out", required=True)
    p.add_argument("--profile", default="youtube-1080p")
    p = sub.add_parser("title"); p.add_argument("--text", required=True); p.add_argument("--out", required=True)
    p.add_argument("--seconds", type=float, default=3.0); p.add_argument("--font"); p.add_argument("--size", default="1920x1080")
    p.add_argument("--fps", type=float, default=25.0); p.add_argument("--profile", default="youtube-1080p")
    p = sub.add_parser("verify"); p.add_argument("--video", required=True); p.add_argument("--profile", default="youtube-1080p")
    p = sub.add_parser("verify-tools"); p.add_argument("--font")
    p = sub.add_parser("sidecar"); p.add_argument("--storyboard", required=True); p.add_argument("--lang", required=True)
    p.add_argument("--durations", required=True); p.add_argument("--out-dir", required=True, dest="out_dir")
    p = sub.add_parser("thumbnail"); p.add_argument("--video", required=True); p.add_argument("--at", type=float, default=2.0)
    p.add_argument("--out", required=True)
    p = sub.add_parser("preview"); p.add_argument("--video", required=True); p.add_argument("--out", required=True)
    p.add_argument("--max-mb", type=float, default=10.0, dest="max_mb"); p.add_argument("--profile", default="youtube-1080p")
    args = parser.parse_args(argv)
    if args.cmd not in ("sidecar", "verify-tools") and getattr(args, "profile", "youtube-1080p") not in PROFILES:
        print("x unknown profile %s (known: %s)" % (args.profile, ", ".join(PROFILES)), file=sys.stderr)
        return 1
    return {"fit": cmd_fit, "concat": cmd_concat, "title": cmd_title, "verify": cmd_verify, "verify-tools": cmd_verify_tools,
            "sidecar": cmd_sidecar, "thumbnail": cmd_thumbnail, "preview": cmd_preview}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
