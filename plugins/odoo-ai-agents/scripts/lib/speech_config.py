#!/usr/bin/env python3
"""speech_config.py - the narration configuration for demo videos, vendor-neutral.

One `speech.toml` in the machine-global, never-committed state root (next to instances.toml):

  [tts]
  provider      = "<free label: openai | azure-openai | groq | localai | kokoro | speaches | ...>"
  base_url      = "https://.../v1"        # the audio API root; POST <base_url>/audio/speech
  model         = "<model id>"
  api_key_env   = "<NAME of the environment variable holding the key; never the key>"
  response_format = "wav"                # what the endpoint returns; the client normalises to WAV
  voices_url    = "<optional GET URL listing voices>"
  [tts.voices]
  vi_VN = "<voice id native to Vietnamese>"
  en_US = "<voice id native to English>"
  [stt]
  base_url      = "https://.../v1"        # POST <base_url>/audio/transcriptions
  model         = "<model id>"
  api_key_env   = "<NAME of the environment variable>"

The contract is the OpenAI audio API shape, which hosted vendors (OpenAI, Azure OpenAI, Groq,
Mistral in part) and self-hosted servers (LocalAI, Kokoro-FastAPI, Speaches, openedai-speech) all
speak; nothing here names one vendor as required. A voice is recorded under the language it is
native to - `record` refuses a voice entry whose language key is not a `xx_YY` locale, and the
same voice id under two languages (a voice reads a second language with an accent and mangles
names). The key never enters any file: `record` refuses a value in `api_key_env` that looks like
a key rather than a variable name.

Subcommands (stdlib only):
  check     exit 0 when speech.toml is valid AND every named key variable is set in this shell
            (self-hosted endpoints may set api_key_env = "" to mean no key); 1 otherwise with
            the remedy; 2 unreadable
  propose   prints KEY=VALUE facts: the provider shapes this file knows (PROVIDER_<n>=<label>
            <base_url shape> <needs voice?>), which known key variables are set (names only),
            FFMPEG and the filters the assembler needs, DECLARED
  record    --from-json FILE   validate and write (backup, atomic)
  show      print the configuration as JSON (api_key_env names only)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys

_LIB_DIR = os.path.dirname(os.path.abspath(__file__))
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
import config_merge  # noqa: E402
import docs_site_config  # noqa: E402  (TOML subset reader)
import paths  # noqa: E402

FILE_NAME = "speech.toml"
TTS_KEYS = ("provider", "base_url", "model", "api_key_env", "response_format", "voices_url")
STT_KEYS = ("provider", "base_url", "model", "api_key_env")
LOCALE_RE = re.compile(r"^[a-z]{2,3}_[A-Z]{2}$")
ENV_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,}$")
# OpenAI-audio-API shapes a setup can offer; labels only, no vendor is required.
PROVIDER_SHAPES = (
    ("openai", "https://api.openai.com/v1", "voice required", "OPENAI_API_KEY"),
    ("azure-openai", "https://<resource>.openai.azure.com/openai/v1", "voice required",
     "AZURE_OPENAI_API_KEY"),
    ("groq", "https://api.groq.com/openai/v1", "voice required", "GROQ_API_KEY"),
    ("localai", "http://localhost:8080/v1", "voice per backend", ""),
    ("kokoro-fastapi", "http://localhost:8880/v1", "voice required (voicepack)", ""),
    ("speaches", "http://localhost:8000/v1", "voice required", ""),
    ("openedai-speech", "http://localhost:8000/v1", "voice required", ""),
)
FFMPEG_FILTERS = ("loudnorm", "ebur128", "setpts", "drawtext", "aresample")


def speech_path():
    return os.path.join(paths.state_root(), FILE_NAME)


def _url_ok(value):
    return isinstance(value, str) and re.match(r"^https?://[^\s/]+", value.strip()) is not None


def _looks_like_a_key(value):
    v = value.strip()
    return len(v) > 24 and any(c.islower() for c in v) and any(c.isdigit() for c in v)


def validate(cfg):
    problems = []
    if not isinstance(cfg, dict):
        return ["the configuration is not a table"]
    for section in ("tts", "stt"):
        if section not in cfg or not isinstance(cfg[section], dict):
            problems.append("[%s] table missing" % section)
    if problems:
        return problems
    tts, stt = cfg["tts"], cfg["stt"]
    for key in tts:
        if key not in TTS_KEYS + ("voices",):
            problems.append("[tts] unknown key %r" % key)
    for key in stt:
        if key not in STT_KEYS:
            problems.append("[stt] unknown key %r" % key)
    for section, table in (("tts", tts), ("stt", stt)):
        if not _url_ok(table.get("base_url")):
            problems.append("[%s] base_url: an http(s) URL of the audio API root" % section)
        if not isinstance(table.get("model"), str) or not table["model"].strip():
            problems.append("[%s] model: a non-empty string" % section)
        env = table.get("api_key_env", "")
        if not isinstance(env, str):
            problems.append("[%s] api_key_env: the NAME of an environment variable" % section)
        elif env and (not ENV_NAME_RE.match(env) or _looks_like_a_key(env)):
            problems.append("[%s] api_key_env: an environment variable NAME such as OPENAI_API_KEY"
                            " - never the key itself" % section)
    if "voices_url" in tts and not _url_ok(tts["voices_url"]):
        problems.append("[tts] voices_url: an http(s) URL")
    voices = tts.get("voices")
    if not isinstance(voices, dict) or not voices:
        problems.append("[tts.voices] at least one language -> voice entry")
    else:
        seen = {}
        for lang, voice in voices.items():
            if not LOCALE_RE.match(str(lang)):
                problems.append("[tts.voices] %r: a locale such as vi_VN or en_US" % lang)
            if not isinstance(voice, str) or not voice.strip():
                problems.append("[tts.voices] %s: a non-empty voice id" % lang)
            elif voice in seen:
                problems.append("[tts.voices] voice %r is recorded for both %s and %s - a voice is "
                                "native to one language" % (voice, seen[voice], lang))
            else:
                seen[voice] = lang
    return problems


def render(cfg):
    q = config_merge._toml_basic_string
    out = ["[tts]"]
    for key in TTS_KEYS:
        if key in cfg["tts"]:
            out.append("%s = %s" % (key, q(str(cfg["tts"][key]))))
    out += ["", "[tts.voices]"]
    for lang in sorted(cfg["tts"]["voices"]):
        out.append("%s = %s" % (lang, q(str(cfg["tts"]["voices"][lang]))))
    out += ["", "[stt]"]
    for key in STT_KEYS:
        if key in cfg["stt"]:
            out.append("%s = %s" % (key, q(str(cfg["stt"][key]))))
    return "\n".join(out) + "\n"


def read_config(path=None):
    with open(path or speech_path(), encoding="utf-8") as fh:
        return docs_site_config._loads(fh.read())


def _load(path):
    try:
        return read_config(path), 0
    except FileNotFoundError:
        return None, 1
    except (OSError, ValueError) as exc:
        print("x %s could not be read: %s" % (path, exc), file=sys.stderr)
        return None, 2


def missing_env(cfg):
    names = {cfg["tts"].get("api_key_env", ""), cfg["stt"].get("api_key_env", "")} - {""}
    return sorted(n for n in names if not os.environ.get(n))


def cmd_check(args):
    path = speech_path()
    cfg, code = _load(path)
    if code == 1:
        print("x no speech configuration at %s - run /odoo-ai-agents:odoo-setup voice" % path,
              file=sys.stderr)
        return 1
    if code:
        return code
    problems = validate(cfg)
    for name in missing_env(cfg) if not problems else []:
        problems.append("environment variable %s is not set in this shell (export it; its value "
                        "is never written anywhere)" % name)
    for p in problems:
        print("x " + p, file=sys.stderr)
    if problems:
        return 1
    print("ok speech configuration: %s (voices: %s)" % (path, ", ".join(sorted(cfg["tts"]["voices"]))))
    return 0


def _emit(name, value):
    print("%s='%s'" % (name, str(value).replace("'", "'\\''")))


def ffmpeg_filters_missing():
    if not shutil.which("ffmpeg"):
        return list(FFMPEG_FILTERS)
    try:
        out = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True,
                             timeout=20, check=False).stdout
    except OSError:
        return list(FFMPEG_FILTERS)
    return [f for f in FFMPEG_FILTERS if " %s " % f not in out]


def cmd_propose(args):
    for i, (label, shape, voice, env) in enumerate(PROVIDER_SHAPES, 1):
        _emit("PROVIDER_%d" % i, "%s %s (%s)%s" % (label, shape, voice,
                                                   " key: " + env if env else " key: none"))
    _emit("KEY_ENV_SET", " ".join(env for _l, _s, _v, env in PROVIDER_SHAPES
                                  if env and os.environ.get(env)) or "none")
    _emit("FFMPEG", shutil.which("ffmpeg") or "missing")
    _emit("FFMPEG_FILTERS_MISSING", " ".join(ffmpeg_filters_missing()) or "none")
    _emit("FFPROBE", shutil.which("ffprobe") or "missing")
    cfg, code = _load(speech_path())
    _emit("DECLARED", 1 if code == 0 else 0)
    _emit("FACTS_TO_CONFIRM", "tts.provider tts.base_url tts.model tts.api_key_env tts.voices "
                              "stt.base_url stt.model stt.api_key_env")
    return 0


def cmd_record(args):
    with open(args.from_json, encoding="utf-8") as fh:
        cfg = json.load(fh)
    problems = validate(cfg)
    if problems:
        for p in problems:
            print("x " + p, file=sys.stderr)
        return 1
    path = speech_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with config_merge.locked_target(path):
        if os.path.exists(path):
            config_merge._backup(path)
        config_merge._atomic_replace(path, render(cfg))
    print("ok wrote %s" % path)
    return 0


def cmd_show(args):
    cfg, code = _load(speech_path())
    if code:
        if code == 1:
            print("x no speech configuration - run /odoo-ai-agents:odoo-setup voice", file=sys.stderr)
        return code
    print(json.dumps(cfg, indent=2, ensure_ascii=False))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    sub.add_parser("propose")
    p = sub.add_parser("record")
    p.add_argument("--from-json", required=True, dest="from_json")
    sub.add_parser("show")
    args = parser.parse_args(argv)
    return {"check": cmd_check, "propose": cmd_propose, "record": cmd_record,
            "show": cmd_show}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
