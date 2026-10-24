#!/usr/bin/env python3
"""speech_config.py - the narration configuration for demo videos, vendor-neutral.

One `speech.toml` in the machine-global, never-committed state root (next to instances.toml):

  [tts]
  provider      = "<free label: gateway | openai | azure-openai | groq | localai | kokoro | speaches | ...>"
  base_url      = "https://.../v1"        # the audio API root; POST <base_url>/audio/speech
  model         = "<model id>"
  auth          = "bearer"               # bearer: the configured value is sent as Authorization; none: no header
  response_format = "wav"                # what the endpoint returns; the client normalises to 48 kHz WAV
  voices_url    = "<optional GET URL listing voices>"
  [tts.voices]
  vi_VN = "<voice id native to Vietnamese>"
  en_US = "<voice id native to English>"
  [stt]
  base_url      = "https://.../v1"        # POST <base_url>/audio/transcriptions
  model         = "<model id>"
  auth          = "bearer"

The contract is the OpenAI audio API shape, which hosted vendors (OpenAI, Azure OpenAI, Groq,
Mistral in part), company gateways and self-hosted servers (LocalAI, Kokoro-FastAPI, Speaches,
openedai-speech) all speak; nothing here names one vendor as required. A voice is recorded under
the language it is native to - `record` refuses a voice entry whose language key is not a `xx_YY`
locale, and the same voice id under two languages (a voice reads a second language with an accent
and mangles names). No credential value enters this file: the value the `bearer` mode sends is the
plugin's configured `speech_api_key` option (Claude Code's own masked dialog, stored by Claude
Code), which only the odoo-media MCP server receives; `record` refuses a value that looks like one.
A configuration written by 8.1.0 (`api_key_env = "<NAME>"`) is read as `auth` (bearer when a name
was given, none when empty) and rewritten on the next `record`.

Subcommands (stdlib only):
  check     exit 0 when speech.toml is valid; 1 otherwise with the remedy; 2 unreadable. Whether the
            configured value is present is reported by the odoo-media `media_info` tool, not here.
  propose   prints KEY=VALUE facts: the provider shapes this file knows (PROVIDER_<n>=<label>
            <base_url shape> <needs voice?> auth: <mode>), GATEWAY (ODOO_AI_SPEECH_BASE_URL when
            an operator exported one), FFMPEG and the filters the assembler needs, DECLARED
  record    --from-json FILE   validate and write (backup, atomic)
  show      print the configuration as JSON
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
TTS_KEYS = ("provider", "base_url", "model", "auth", "response_format", "voices_url")
STT_KEYS = ("provider", "base_url", "model", "auth")
AUTH_MODES = ("bearer", "none")   # bearer: the configured value is sent as `Authorization: Bearer`
LEGACY_KEY = "api_key_env"        # 8.1.0 spelled the variable NAME here; read as auth=bearer, rewritten on record
LOCALE_RE = re.compile(r"^[a-z]{2,3}_[A-Z]{2}$")
ENV_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,}$")
# OpenAI-audio-API shapes a setup can offer; labels only, no vendor is required.
PROVIDER_SHAPES = (
    ("gateway", "https://<your gateway>/v1", "voice per engine", "bearer"),
    ("openai", "https://api.openai.com/v1", "voice required", "bearer"),
    ("azure-openai", "https://<resource>.openai.azure.com/openai/v1", "voice required", "bearer"),
    ("groq", "https://api.groq.com/openai/v1", "voice required", "bearer"),
    ("localai", "http://localhost:8080/v1", "voice per backend", "none"),
    ("kokoro-fastapi", "http://localhost:8880/v1", "voice required (voicepack)", "none"),
    ("speaches", "http://localhost:8000/v1", "voice required", "none"),
    ("openedai-speech", "http://localhost:8000/v1", "voice required", "none"),
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
        auth = table.get("auth", "bearer")
        if auth not in AUTH_MODES:
            problems.append("[%s] auth: one of %s" % (section, " | ".join(AUTH_MODES)))
        for key, value in table.items():
            if isinstance(value, str) and _looks_like_a_key(value) and key != "base_url":
                problems.append("[%s] %s: this looks like a credential value - a configuration file "
                                "never holds one; the plugin's configuration dialog does" % (section, key))
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


def migrate(cfg):
    """8.1.0 wrote `api_key_env = "<NAME>"` (empty = no key). It is read as `auth`: bearer when a
    name was given, none when empty. Returns the keys that were migrated (for a notice)."""
    migrated = []
    if not isinstance(cfg, dict):
        return migrated
    for section in ("tts", "stt"):
        table = cfg.get(section)
        if isinstance(table, dict) and LEGACY_KEY in table:
            name = table.pop(LEGACY_KEY)
            table.setdefault("auth", "bearer" if (isinstance(name, str) and name.strip()) else "none")
            migrated.append(section)
    return migrated


def read_config(path=None):
    with open(path or speech_path(), encoding="utf-8") as fh:
        cfg = docs_site_config._loads(fh.read())
    migrate(cfg)
    return cfg


def needs_value(cfg):
    """True when any section authenticates with the configured value."""
    return any((cfg.get(s) or {}).get("auth", "bearer") == "bearer" for s in ("tts", "stt"))


def _load(path):
    try:
        return read_config(path), 0
    except FileNotFoundError:
        return None, 1
    except (OSError, ValueError) as exc:
        print("x %s could not be read: %s" % (path, exc), file=sys.stderr)
        return None, 2


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
    for p in problems:
        print("x " + p, file=sys.stderr)
    if problems:
        return 1
    print("ok speech configuration: %s (voices: %s)" % (path, ", ".join(sorted(cfg["tts"]["voices"]))))
    print("AUTH=%s" % ("bearer (the value comes from the plugin configuration; the odoo-media "
                       "media_info tool reports whether it is set)" if needs_value(cfg) else "none"))
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
    for i, (label, shape, voice, auth) in enumerate(PROVIDER_SHAPES, 1):
        _emit("PROVIDER_%d" % i, "%s %s (%s) auth: %s" % (label, shape, voice, auth))
    gateway = os.environ.get("ODOO_AI_SPEECH_BASE_URL", "").strip()
    _emit("GATEWAY", gateway or "none")
    _emit("FFMPEG", shutil.which("ffmpeg") or "missing")
    _emit("FFMPEG_FILTERS_MISSING", " ".join(ffmpeg_filters_missing()) or "none")
    _emit("FFPROBE", shutil.which("ffprobe") or "missing")
    cfg, code = _load(speech_path())
    _emit("DECLARED", 1 if code == 0 else 0)
    _emit("FACTS_TO_CONFIRM", "tts.provider tts.base_url tts.model tts.auth tts.voices "
                              "stt.base_url stt.model stt.auth")
    _emit("VALUE_SOURCE", "the plugin configuration dialog (never a file, never the chat)")
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
