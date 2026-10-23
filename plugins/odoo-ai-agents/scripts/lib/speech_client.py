#!/usr/bin/env python3
"""speech_client.py - text-to-speech and speech-to-text over the OpenAI audio API shape.

Reads `speech.toml` (speech_config.py). The key comes from the environment variable the
configuration NAMES and is sent as `Authorization: Bearer`; it is never printed, logged or written.
Hosted vendors and self-hosted servers that speak this shape all work; a server that needs no key
leaves `api_key_env` empty.

  tts    --text-file F --lang xx_YY --out clip.wav [--map MAP.json]
         POST <tts.base_url>/audio/speech with {model, input, voice, response_format}; the input
         is the text after the pronunciation map of its language; the reply is normalised to
         48 kHz 16-bit mono WAV with ffmpeg; prints OUT=<path> DURATION_S=<seconds>.
  stt    --audio clip.wav --lang xx_YY
         POST <stt.base_url>/audio/transcriptions (multipart: file, model, language) and prints
         the transcript on stdout.
  voices GET <tts.voices_url> or <tts.base_url>/audio/voices; prints the JSON the server returns.
  probe  [--lang xx_YY]  one short sentence per configured language through tts; prints each
         clip's path and duration; exit 1 when a language fails.

Exit: 0 ok, 1 the endpoint refused or the configuration is invalid (reason on stderr, never the
key), 2 ffmpeg missing or the configuration file missing.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
import uuid
import wave

_LIB_DIR = os.path.dirname(os.path.abspath(__file__))
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
import pronunciation  # noqa: E402
import speech_config  # noqa: E402

PROBE_SENTENCES = {
    "vi_VN": "Xin chào, đây là bản thử giọng đọc cho video giới thiệu.",
    "en_US": "Hello, this is a narration voice check for the product video.",
}
DEFAULT_PROBE = "This is a narration voice check."


class SpeechError(Exception):
    pass


def _load():
    try:
        cfg = speech_config.read_config()
    except FileNotFoundError:
        raise SpeechError("no speech configuration - run /odoo-ai-agents:odoo-setup voice", 2)
    problems = speech_config.validate(cfg)
    if problems:
        raise SpeechError("speech.toml invalid: " + "; ".join(problems), 1)
    return cfg


def _headers(table):
    headers = {"Content-Type": "application/json"}
    env = table.get("api_key_env", "")
    if env:
        key = os.environ.get(env)
        if not key:
            raise SpeechError("environment variable %s is not set" % env, 1)
        headers["Authorization"] = "Bearer " + key
    return headers


def _post(url, headers, data, timeout=120):
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read(), resp.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        body = exc.read()[:300].decode("utf-8", errors="replace")
        raise SpeechError("%s answered %d: %s" % (url, exc.code, body), 1)
    except (urllib.error.URLError, OSError) as exc:
        raise SpeechError("%s unreachable: %s" % (url, exc), 1)


def _normalise_wav(raw, out, source_format):
    if not shutil.which("ffmpeg"):
        raise SpeechError("ffmpeg is missing - the clip cannot be normalised to 48 kHz WAV", 2)
    tmp = out + ".src." + (source_format or "bin")
    with open(tmp, "wb") as fh:
        fh.write(raw)
    try:
        proc = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", tmp, "-ac", "1", "-ar", "48000",
                               "-sample_fmt", "s16", out], capture_output=True, text=True, check=False)
    finally:
        os.unlink(tmp)
    if proc.returncode != 0:
        raise SpeechError("ffmpeg could not decode the speech reply: %s" % proc.stderr.strip()[-300:], 1)


def wav_duration(path):
    with wave.open(path, "rb") as wf:
        return wf.getnframes() / float(wf.getframerate() or 1)


def tts(text, lang, out, pron_map=None, cfg=None):
    cfg = cfg or _load()
    table = cfg["tts"]
    voice = table["voices"].get(lang)
    if not voice:
        raise SpeechError("no voice recorded for %s - run /odoo-ai-agents:odoo-setup voice" % lang, 1)
    if pron_map:
        text = pronunciation.apply_map(text, pron_map.get(lang) or [])
    fmt = table.get("response_format", "wav")
    body = json.dumps({"model": table["model"], "input": text, "voice": voice,
                       "response_format": fmt}).encode("utf-8")
    raw, _ctype = _post(table["base_url"].rstrip("/") + "/audio/speech", _headers(table), body)
    if not raw:
        raise SpeechError("the speech endpoint returned no audio", 1)
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    _normalise_wav(raw, out, fmt)
    return out, wav_duration(out)


def stt(audio, lang, cfg=None):
    cfg = cfg or _load()
    table = cfg["stt"]
    boundary = "----odooai" + uuid.uuid4().hex
    with open(audio, "rb") as fh:
        payload = fh.read()
    parts = []
    for name, value in (("model", table["model"]), ("language", lang.split("_")[0]),
                        ("response_format", "json")):
        parts.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n"
                      % (boundary, name, value)).encode("utf-8"))
    parts.append(("--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"%s\"\r\n"
                  "Content-Type: audio/wav\r\n\r\n" % (boundary, os.path.basename(audio))).encode("utf-8"))
    parts.append(payload)
    parts.append(("\r\n--%s--\r\n" % boundary).encode("utf-8"))
    headers = _headers(table)
    headers["Content-Type"] = "multipart/form-data; boundary=" + boundary
    raw, _ctype = _post(table["base_url"].rstrip("/") + "/audio/transcriptions", headers,
                        b"".join(parts), timeout=300)
    try:
        return json.loads(raw.decode("utf-8")).get("text", "").strip()
    except ValueError:
        return raw.decode("utf-8", errors="replace").strip()


def voices(cfg=None):
    cfg = cfg or _load()
    table = cfg["tts"]
    url = table.get("voices_url") or table["base_url"].rstrip("/") + "/audio/voices"
    headers = _headers(table)
    headers.pop("Content-Type", None)
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise SpeechError("%s: %s" % (url, exc), 1)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("tts")
    p.add_argument("--text-file", required=True)
    p.add_argument("--lang", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--map")
    p = sub.add_parser("stt")
    p.add_argument("--audio", required=True)
    p.add_argument("--lang", required=True)
    sub.add_parser("voices")
    p = sub.add_parser("probe")
    p.add_argument("--lang")
    p.add_argument("--out-dir", default=".")
    args = parser.parse_args(argv)
    try:
        if args.cmd == "tts":
            with open(args.text_file, encoding="utf-8") as fh:
                text = fh.read()
            pron = None
            if args.map:
                with open(args.map, encoding="utf-8") as fh:
                    pron = json.load(fh)
            out, dur = tts(text, args.lang, args.out, pron)
            print("OUT=%s" % out)
            print("DURATION_S=%.2f" % dur)
            return 0
        if args.cmd == "stt":
            print(stt(args.audio, args.lang))
            return 0
        if args.cmd == "voices":
            print(json.dumps(voices(), indent=2, ensure_ascii=False))
            return 0
        cfg = _load()
        langs = [args.lang] if args.lang else sorted(cfg["tts"]["voices"])
        failed = 0
        for lang in langs:
            out = os.path.join(args.out_dir, "probe-%s.wav" % lang)
            try:
                path, dur = tts(PROBE_SENTENCES.get(lang, DEFAULT_PROBE), lang, out, cfg=cfg)
                print("%s OUT=%s DURATION_S=%.2f" % (lang, path, dur))
            except SpeechError as exc:
                failed += 1
                print("%s FAILED: %s" % (lang, exc.args[0]), file=sys.stderr)
        return 1 if failed else 0
    except SpeechError as exc:
        print("x " + exc.args[0], file=sys.stderr)
        return exc.args[1] if len(exc.args) > 1 else 1


if __name__ == "__main__":
    sys.exit(main())
