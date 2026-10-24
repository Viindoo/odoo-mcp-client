#!/usr/bin/env python3
"""speech_client.py - text-to-speech and speech-to-text over the OpenAI audio API shape.

Reads `speech.toml` (speech_config.py). In `auth = "bearer"` mode the caller passes the value to
send as `Authorization: Bearer` - the odoo-media MCP server passes the plugin's configured option;
the CLI below reads the environment variable SPEECH_API_KEY for a human running it by hand. The
value is never printed, logged or written. Every HTTP call retries on 429 / 503 / a timeout with a
short backoff (a shared low-end gateway queues a second caller), and honours a cancel Event.

  tts    --text-file F --lang xx_YY --out clip.wav [--map MAP.json]
         POST <tts.base_url>/audio/speech with {model, input, voice, response_format}; the input
         is the text after the pronunciation map of its language; the reply is normalised to
         48 kHz 16-bit mono WAV with ffmpeg (engines differ: 24 kHz mp3 here, 48 kHz wav there);
         prints OUT=<path> DURATION_S=<seconds>.
  stt    --audio clip.wav --lang xx_YY [--words]
         POST <stt.base_url>/audio/transcriptions (multipart: file, model, language) and prints
         the transcript; --words asks verbose_json with word timestamps and prints JSON.
  voices GET <tts.voices_url> or <tts.base_url>/audio/voices; prints the JSON the server returns.
  probe  [--lang xx_YY] [--out-dir DIR]  one short sentence per configured language through tts,
         then through stt in the same language, and the word error rate between them: the round
         trip that catches a voice/language mismatch and a brand misread before a recording run.
         DIR defaults to <state root>/scratch/speech-probe (never the working directory).

Exit: 0 ok, 1 the endpoint refused or the configuration is invalid (reason on stderr, never the
value), 2 ffmpeg missing or the configuration file missing.
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
import paths  # noqa: E402

VALUE_ENV = "SPEECH_API_KEY"      # the CLI's source of the bearer value; the MCP server passes it in
RETRY_STATUS = (429, 503)
RETRY_BACKOFF_S = (2.0, 6.0, 18.0)

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


def _headers(table, value):
    headers = {"Content-Type": "application/json"}
    if table.get("auth", "bearer") == "bearer":
        if not value:
            raise SpeechError("the speech endpoint needs the configured value and none was supplied "
                              "(odoo-media: the plugin option speech_api_key; CLI: %s)" % VALUE_ENV, 3)
        headers["Authorization"] = "Bearer " + value
    return headers


def _cancelled(cancel):
    return cancel is not None and cancel.is_set()


def _post(url, headers, data, timeout=120, cancel=None):
    attempt = 0
    while True:
        if _cancelled(cancel):
            raise SpeechError("cancelled before %s" % url, 1)
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read(), resp.headers.get("Content-Type", "")
        except urllib.error.HTTPError as exc:
            body = exc.read()[:300].decode("utf-8", errors="replace")
            if exc.code in RETRY_STATUS and attempt < len(RETRY_BACKOFF_S):
                _backoff(attempt, cancel)
                attempt += 1
                continue
            raise SpeechError("%s answered %d: %s" % (url, exc.code, body), 1)
        except (urllib.error.URLError, OSError) as exc:
            if attempt < len(RETRY_BACKOFF_S) and "timed out" in str(exc).lower():
                _backoff(attempt, cancel)
                attempt += 1
                continue
            raise SpeechError("%s unreachable: %s" % (url, exc), 1)


def _backoff(attempt, cancel):
    delay = RETRY_BACKOFF_S[attempt]
    if cancel is not None:
        cancel.wait(delay)
    else:
        import time
        time.sleep(delay)


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


def tts(text, lang, out, pron_map=None, cfg=None, value=None, cancel=None, phonemes=False, speed=None, voice=None):
    """`speed` is the OpenAI speaking-rate factor (sent only when it differs from 1.0; an engine may
    ignore it - probe() measures that); `voice` overrides the recorded voice (an audition)."""
    cfg = cfg or _load()
    table = cfg["tts"]
    voice = voice or table["voices"].get(lang)
    if not voice:
        raise SpeechError("no voice recorded for %s - run /odoo-ai-agents:odoo-setup voice" % lang, 1)
    # the registry always applies (brands, vendors, acronyms confirmed once); the map adds terms
    entries = pronunciation.merge(pron_map or {}).get(lang) or []
    if entries:
        text = pronunciation.apply_map(text, entries, phonemes=phonemes)
    fmt = table.get("response_format", "wav")
    payload = {"model": table["model"], "input": text, "voice": voice, "response_format": fmt}
    if speed is not None and abs(float(speed) - 1.0) > 1e-6:
        payload["speed"] = float(speed)
    body = json.dumps(payload).encode("utf-8")
    raw, _ctype = _post(table["base_url"].rstrip("/") + "/audio/speech", _headers(table, value), body,
                        cancel=cancel)
    if not raw:
        raise SpeechError("the speech endpoint returned no audio", 1)
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    _normalise_wav(raw, out, fmt)
    return out, wav_duration(out)


def stt(audio, lang, cfg=None, value=None, cancel=None, words=False):
    """The transcript text; with words=True a dict {text, words: [{word, start, end}]} when the
    engine returns word timestamps (verbose_json), else {text, words: []}."""
    cfg = cfg or _load()
    table = cfg["stt"]
    boundary = "----odooai" + uuid.uuid4().hex
    with open(audio, "rb") as fh:
        payload = fh.read()
    parts = []
    fields = [("model", table["model"]), ("language", lang.split("_")[0]),
              ("response_format", "verbose_json" if words else "json")]
    if words:
        fields.append(("timestamp_granularities[]", "word"))
    for name, field in fields:
        parts.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n"
                      % (boundary, name, field)).encode("utf-8"))
    parts.append(("--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"%s\"\r\n"
                  "Content-Type: audio/wav\r\n\r\n" % (boundary, os.path.basename(audio))).encode("utf-8"))
    parts.append(payload)
    parts.append(("\r\n--%s--\r\n" % boundary).encode("utf-8"))
    headers = _headers(table, value)
    headers["Content-Type"] = "multipart/form-data; boundary=" + boundary
    raw, _ctype = _post(table["base_url"].rstrip("/") + "/audio/transcriptions", headers,
                        b"".join(parts), timeout=300, cancel=cancel)
    try:
        data = json.loads(raw.decode("utf-8"))
    except ValueError:
        text = raw.decode("utf-8", errors="replace").strip()
        return {"text": text, "words": []} if words else text
    text = (data.get("text") or "").strip()
    if not words:
        return text
    out = []
    for w in data.get("words") or []:
        if isinstance(w, dict) and "word" in w:
            out.append({"word": str(w.get("word")), "start": float(w.get("start") or 0.0),
                        "end": float(w.get("end") or 0.0)})
    return {"text": text, "words": out}


def _get_json(url, headers, timeout=60):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def voices(cfg=None, value=None, base_url=None):
    """The voice listing as the endpoint returns it; `base_url` overrides the configured one
    (the setup conversation lists voices before speech.toml exists)."""
    cfg = cfg or (None if base_url else _load())
    table = (cfg or {}).get("tts") or {"auth": "bearer" if value else "none"}
    base = (base_url or table["base_url"]).rstrip("/")
    url = (table.get("voices_url") if not base_url else None) or base + "/audio/voices"
    headers = _headers(table, value)
    headers.pop("Content-Type", None)
    try:
        return _get_json(url, headers)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise SpeechError("%s: %s" % (url, exc), 1)


def models(cfg=None, value=None, base_url=None):
    """The model ids the endpoint lists at GET <base>/models (OpenAI shape), [] when it has none."""
    cfg = cfg or (None if base_url else _load())
    table = (cfg or {}).get("tts") or {"auth": "bearer" if value else "none"}
    base = (base_url or table["base_url"]).rstrip("/")
    headers = _headers(table, value)
    headers.pop("Content-Type", None)
    try:
        data = _get_json(base + "/models", headers)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return []
        raise SpeechError("%s/models: HTTP %d" % (base, exc.code), 1)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise SpeechError("%s/models: %s" % (base, exc), 1)
    rows = data.get("data") if isinstance(data, dict) else data
    out = []
    for row in rows or []:
        mid = row.get("id") if isinstance(row, dict) else row
        if isinstance(mid, str) and mid.strip():
            out.append(mid.strip())
    return out


def _guess(ids, words):
    hits = [m for m in ids if any(w in m.lower() for w in words)]
    return hits[0] if len(hits) == 1 else ""


def probe_endpoint(base_url, timeout=5):
    """What an audio endpoint says about itself WITHOUT a value: reachable or not, open or
    expecting a value (401/403), and when open its models and voices.
    {"reachable": bool, "auth": "open"|"required"|"unknown", "models": [...], "voices": ...,
     "tts_model_guess": str, "stt_model_guess": str, "detail": str}"""
    base = base_url.rstrip("/")
    out = {"reachable": False, "auth": "unknown", "models": [], "voices": None,
           "tts_model_guess": "", "stt_model_guess": "", "detail": ""}
    status = None
    for path in ("/models", "/audio/voices"):
        try:
            data = _get_json(base + path, {}, timeout=timeout)
            out["reachable"] = True
            if path == "/models":
                rows = data.get("data") if isinstance(data, dict) else data
                out["models"] = [str(r.get("id") if isinstance(r, dict) else r) for r in (rows or [])
                                 if (r.get("id") if isinstance(r, dict) else r)]
            else:
                out["voices"] = data
        except urllib.error.HTTPError as exc:
            out["reachable"] = True
            status = exc.code if status is None or exc.code in (401, 403) else status
        except (urllib.error.URLError, OSError, ValueError) as exc:
            out["detail"] = "%s%s: %s" % (base, path, exc)
    if not out["reachable"]:
        return out
    if status in (401, 403):
        out["auth"] = "required"
    elif out["models"] or out["voices"] is not None:
        out["auth"] = "open"
    out["tts_model_guess"] = _guess(out["models"], ("tts", "speech"))
    out["stt_model_guess"] = _guess(out["models"], ("stt", "whisper", "transcri"))
    return out


PROBE_MAX_WER = 0.35   # a round trip through a low-end engine pair is noisy; a mismatch is far above


def probe_dir():
    return os.path.join(paths.state_root(), "scratch", "speech-probe")


def probe(lang=None, out_dir=None, value=None, cfg=None, cancel=None, speed=None):
    """Per language: synthesize the probe sentence, transcribe it in the same language, score the
    word error rate (tone-aware, narration_check.wer). A high rate means the voice does not speak
    that language or the endpoint is not what the configuration says. With `speed`, a second clip
    at that rate is rendered and `speed_honoured` says whether the engine changed the duration (a
    5 percent difference or more) - never assumed. Returns a list of dicts."""
    import narration_check
    cfg = cfg or _load()
    out_dir = out_dir or probe_dir()
    os.makedirs(out_dir, exist_ok=True)
    langs = [lang] if lang else sorted(cfg["tts"]["voices"])
    results = []
    for code in langs:
        sentence = PROBE_SENTENCES.get(code, DEFAULT_PROBE)
        clip = os.path.join(out_dir, "probe-%s.wav" % code)
        try:
            path, dur = tts(sentence, code, clip, cfg=cfg, value=value, cancel=cancel)
            heard = stt(path, code, cfg=cfg, value=value, cancel=cancel)
            rate = narration_check.wer(sentence, heard)
            entry = {"lang": code, "ok": True, "clip": path, "duration_s": round(dur, 2),
                     "sentence": sentence, "heard": heard, "wer": round(rate, 3),
                     "verdict": "pass" if rate <= PROBE_MAX_WER else "fail"}
            if speed is not None and abs(float(speed) - 1.0) > 1e-6:
                fast = os.path.join(out_dir, "probe-%s-x%g.wav" % (code, float(speed)))
                _p, fdur = tts(sentence, code, fast, cfg=cfg, value=value, cancel=cancel, speed=speed)
                expected = dur / float(speed)
                entry.update({"speed": float(speed), "duration_at_speed_s": round(fdur, 2),
                              "speed_honoured": abs(fdur - dur) >= 0.05 * dur and abs(fdur - expected) < abs(fdur - dur)})
            results.append(entry)
        except SpeechError as exc:
            results.append({"lang": code, "ok": False, "clip": clip, "duration_s": 0.0, "sentence": sentence,
                            "heard": "", "wer": 1.0, "verdict": "fail", "error": exc.args[0]})
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("tts")
    p.add_argument("--text-file", required=True)
    p.add_argument("--lang", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--map")
    p.add_argument("--speed", type=float)
    p.add_argument("--voice")
    p = sub.add_parser("stt")
    p.add_argument("--audio", required=True)
    p.add_argument("--lang", required=True)
    p.add_argument("--words", action="store_true")
    sub.add_parser("voices")
    p = sub.add_parser("probe")
    p.add_argument("--lang")
    p.add_argument("--out-dir")
    p.add_argument("--speed", type=float)
    args = parser.parse_args(argv)
    value = os.environ.get(VALUE_ENV) or None
    try:
        if args.cmd == "tts":
            with open(args.text_file, encoding="utf-8") as fh:
                text = fh.read()
            pron = None
            if args.map:
                with open(args.map, encoding="utf-8") as fh:
                    pron = json.load(fh)
            out, dur = tts(text, args.lang, args.out, pron, value=value, speed=args.speed, voice=args.voice)
            print("OUT=%s" % out)
            print("DURATION_S=%.2f" % dur)
            return 0
        if args.cmd == "stt":
            if args.words:
                print(json.dumps(stt(args.audio, args.lang, value=value, words=True), ensure_ascii=False))
            else:
                print(stt(args.audio, args.lang, value=value))
            return 0
        if args.cmd == "voices":
            print(json.dumps(voices(value=value), indent=2, ensure_ascii=False))
            return 0
        results = probe(args.lang, args.out_dir, value=value, speed=args.speed)
        for r in results:
            if r["ok"]:
                print("%s OUT=%s DURATION_S=%.2f WER=%.3f VERDICT=%s" % (
                    r["lang"], r["clip"], r["duration_s"], r["wer"], r["verdict"]))
            else:
                print("%s FAILED: %s" % (r["lang"], r["error"]), file=sys.stderr)
        return 1 if any(not r["ok"] or r["verdict"] == "fail" for r in results) else 0
    except SpeechError as exc:
        print("x " + exc.args[0], file=sys.stderr)
        return exc.args[1] if len(exc.args) > 1 else 1


if __name__ == "__main__":
    sys.exit(main())
