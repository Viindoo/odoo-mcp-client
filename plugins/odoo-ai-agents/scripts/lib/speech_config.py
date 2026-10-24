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
A configuration that spells `api_key_env = "<NAME>"` is read as `auth` (bearer when a name was
given, none when empty) and rewritten on the next `record`. Optional tables: `[tts.candidates]`
(locale -> voice ids to audition for a project) and `[tts.rate]` (`tutorial` / `marketing` ->
the speaking-rate factor sent as the OpenAI `speed` parameter; the probe measures whether the
engine honours it).

Subcommands (stdlib only):
  check     exit 0 when speech.toml is valid; 1 otherwise with the remedy; 2 unreadable. Whether the
            configured value is present is reported by the odoo-media `media_info` tool, not here.
  propose   prints KEY=VALUE facts: GATEWAY (ODOO_AI_SPEECH_BASE_URL when an operator exported
            one) first, then every local container or service that answers the OpenAI audio shape
            (docker ps published ports + the well-known local ports, probed once), then the
            provider shapes this file knows (PROVIDER_<n>=<label> <base_url shape> <needs voice?>
            auth: <mode>), FFMPEG, the filters the assembler needs and a REMEDY per missing one,
            DECLARED
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
VIDEO_TYPES = ("tutorial", "marketing")
DEFAULT_RATE = {"tutorial": 1.0, "marketing": 1.08}   # the OpenAI `speed` parameter, where the engine honours it
STT_KEYS = ("provider", "base_url", "model", "auth")
AUTH_MODES = ("bearer", "none")   # bearer: the configured value is sent as `Authorization: Bearer`
LEGACY_KEY = "api_key_env"        # an older configuration's key; read as auth, rewritten on record
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


def validate(cfg, complete=True):
    """Problems with the configuration. `complete=False` accepts an endpoint-only file (base_url
    and auth recorded, models and voices not chosen yet) - the stage the setup conversation records
    before the operator configures the value, so the value only ever travels to that endpoint."""
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
        if key not in TTS_KEYS + ("voices", "candidates", "rate"):
            problems.append("[tts] unknown key %r" % key)
    cands = tts.get("candidates")
    if cands is not None:
        if not isinstance(cands, dict):
            problems.append("[tts.candidates] a table: locale -> list of voice ids to audition")
        else:
            for lang, lst in cands.items():
                if not LOCALE_RE.match(str(lang)) or not isinstance(lst, list) or not all(isinstance(v, str) and v.strip() for v in lst):
                    problems.append("[tts.candidates] %s: a locale key and a list of voice ids" % lang)
    rate = tts.get("rate")
    if rate is not None:
        if not isinstance(rate, dict):
            problems.append("[tts.rate] a table: tutorial / marketing -> speed factor")
        else:
            for kind, v in rate.items():
                try:
                    ok = kind in VIDEO_TYPES and 0.5 <= float(v) <= 2.0
                except (TypeError, ValueError):
                    ok = False
                if not ok:
                    problems.append("[tts.rate] %s: one of %s with a factor between 0.5 and 2.0" % (kind, " | ".join(VIDEO_TYPES)))
    for key in stt:
        if key not in STT_KEYS:
            problems.append("[stt] unknown key %r" % key)
    for section, table in (("tts", tts), ("stt", stt)):
        if not _url_ok(table.get("base_url")):
            problems.append("[%s] base_url: an http(s) URL of the audio API root" % section)
        if complete and (not isinstance(table.get("model"), str) or not table["model"].strip()):
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
        if complete:
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
    voices = cfg["tts"].get("voices") or {}
    if voices:
        out += ["", "[tts.voices]"]
        for lang in sorted(voices):
            out.append("%s = %s" % (lang, q(str(voices[lang]))))
    cands = cfg["tts"].get("candidates") or {}
    if cands:
        out += ["", "[tts.candidates]"]
        for lang in sorted(cands):
            out.append("%s = [%s]" % (lang, ", ".join(q(str(v)) for v in cands[lang])))
    rate = cfg["tts"].get("rate") or {}
    if rate:
        out += ["", "[tts.rate]"]
        for kind in VIDEO_TYPES:
            if kind in rate:
                out.append("%s = %s" % (kind, q("%g" % float(rate[kind]))))   # a string: the subset reader has no floats
    out += ["", "[stt]"]
    for key in STT_KEYS:
        if key in cfg["stt"]:
            out.append("%s = %s" % (key, q(str(cfg["stt"][key]))))
    return "\n".join(out) + "\n"


def migrate(cfg):
    """A configuration that spells `api_key_env = "<NAME>"` (empty = no key) is read as `auth`:
    bearer when a name was given, none when empty. Returns the sections migrated (for a notice)."""
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
    if migrate(cfg) and isinstance(cfg, dict):
        cfg["_migrated"] = True   # the file still names a variable; upgrade_values.py moves its value
    return cfg


def rate_for(cfg, video_type):
    """The speed factor for a video type: the configured one, else the default."""
    table = (cfg.get("tts") or {}).get("rate") or {}
    try:
        return float(table.get(video_type, DEFAULT_RATE.get(video_type, 1.0)))
    except (TypeError, ValueError):
        return 1.0


def candidates_for(cfg, lang):
    """Voices to audition for a language: the configured candidates, else the recorded voice alone."""
    tts = cfg.get("tts") or {}
    lst = (tts.get("candidates") or {}).get(lang) or []
    voice = (tts.get("voices") or {}).get(lang)
    out = [v for v in lst if v]
    if voice and voice not in out:
        out.insert(0, voice)
    return out


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
    if problems and not validate(cfg, complete=False):
        print("INCOMPLETE=%s" % " ".join(sorted(p.split(":")[0].strip("[] ").replace("] ", ".")
                                                 for p in problems)))
        print("ok endpoint declared in %s; models and voices not chosen yet - the odoo-media speech_voices "
              "tool lists them once the value is configured and the plugins reloaded" % path)
        return 1
    for p in problems:
        print("x " + p, file=sys.stderr)
    if problems:
        return 1
    print("ok speech configuration: %s (voices: %s)" % (path, ", ".join(sorted(cfg["tts"]["voices"]))))
    if cfg.get("_migrated"):
        print("UPGRADE=the file still names an environment variable from an earlier plugin version; "
              "the operator runs in their own terminal: python3 %s apply"
              % os.path.join(_LIB_DIR, "upgrade_values.py"))
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


LOCAL_PROBE_PORTS = (8080, 8880, 8000, 8100, 8300)   # the shapes above + two common container ports
FILTER_REMEDY = {
    "drawtext": "an ffmpeg build with libfreetype (the distro package); a static build without it renders "
                "the title card through libass instead when `subtitles` is present",
    "subtitles": "an ffmpeg build with libass (the distro package)",
}


def _answers_openai_audio(base, timeout=2.0):
    """The base URL when GET <base>/models or <base>/audio/voices answers HTTP 200 (or 401/403:
    reachable, wants a value), else None."""
    import urllib.error
    import urllib.request
    for path in ("/models", "/audio/voices"):
        try:
            with urllib.request.urlopen(base.rstrip("/") + path, timeout=timeout) as resp:
                if resp.status == 200:
                    return base
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                return base
        except (urllib.error.URLError, OSError, ValueError):
            continue
    return None


def discover_local(docker_cmd="docker", probe_ports=LOCAL_PROBE_PORTS):
    """[(name, base_url)] of local services that speak the OpenAI audio shape: every published
    port of a running container (`docker ps`) and the well-known local ports, each probed once."""
    found, seen = [], set()
    if shutil.which(docker_cmd):
        try:
            out = subprocess.run([docker_cmd, "ps", "--format", "{{.Names}} {{.Ports}}"], capture_output=True,
                                 text=True, timeout=15, check=False).stdout
        except (OSError, subprocess.TimeoutExpired):
            out = ""
        for line in out.splitlines():
            name, _, ports = line.partition(" ")
            for m in re.finditer(r"(?:0\.0\.0\.0|127\.0\.0\.1|\[::\]|):(\d+)->", ports):
                port = int(m.group(1))
                if port in seen:
                    continue
                seen.add(port)
                base = _answers_openai_audio("http://127.0.0.1:%d/v1" % port)
                if base:
                    found.append((name, base))
    for port in probe_ports:
        if port in seen:
            continue
        seen.add(port)
        base = _answers_openai_audio("http://127.0.0.1:%d/v1" % port)
        if base:
            found.append(("local:%d" % port, base))
    return found


def cmd_propose(args):
    gateway = os.environ.get("ODOO_AI_SPEECH_BASE_URL", "").strip()
    _emit("GATEWAY", gateway or "none")
    n = 0
    if gateway:
        n += 1
        _emit("PROVIDER_%d" % n, "gateway %s (voice per engine) auth: bearer - exported by the operator" % gateway)
    for name, base in discover_local():
        n += 1
        _emit("PROVIDER_%d" % n, "%s %s (local container or service answering the OpenAI audio shape) auth: none"
              % (name, base))
    for label, shape, voice, auth in PROVIDER_SHAPES:
        if label == "gateway" and gateway:
            continue
        n += 1
        _emit("PROVIDER_%d" % n, "%s %s (%s) auth: %s" % (label, shape, voice, auth))
    _emit("FFMPEG", shutil.which("ffmpeg") or "missing")
    missing = ffmpeg_filters_missing()
    _emit("FFMPEG_FILTERS_MISSING", " ".join(missing) or "none")
    for f in missing:
        _emit("REMEDY_%s" % f, FILTER_REMEDY.get(f, "an ffmpeg build with the %s filter (the distro package)" % f))
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
    if "tts" in cfg and isinstance(cfg["tts"], dict):
        cfg["tts"].setdefault("voices", {})
    problems = validate(cfg, complete=not args.endpoint_only)
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


def cmd_probe_endpoint(args):
    """What the endpoint at --base-url says about itself, without any value (the setup
    conversation runs it before anything is recorded)."""
    speech_client = _load_client()
    info = speech_client.probe_endpoint(args.base_url)
    _emit("REACHABLE", 1 if info["reachable"] else 0)
    _emit("AUTH", info["auth"])
    _emit("MODELS", " ".join(info["models"]) or "none")
    voices = info["voices"]
    names = []
    if isinstance(voices, dict):
        names = [str(v) for v in (voices.get("voices") or voices.get("data") or [])]
    elif isinstance(voices, list):
        names = [str(v.get("id") or v.get("name")) if isinstance(v, dict) else str(v) for v in voices]
    _emit("VOICES", " ".join(n for n in names if n) or "none")
    _emit("TTS_MODEL_GUESS", info["tts_model_guess"] or "none")
    _emit("STT_MODEL_GUESS", info["stt_model_guess"] or "none")
    if info["detail"]:
        _emit("DETAIL", info["detail"])
    if not info["reachable"]:
        return 1
    if info["auth"] == "required":
        _emit("NEXT", "the endpoint expects a value: record it first (record --endpoint-only), the operator "
                      "fills the plugin option titled 'Speech endpoint key' (/plugin > odoo-ai-agents > "
                      "Configure), then /reload-plugins, then the odoo-media speech_voices tool lists its "
                      "models and voices (the value only ever goes to the recorded endpoint)")
    return 0


def _load_client():
    import importlib.util
    spec = importlib.util.spec_from_file_location("speech_client", os.path.join(_LIB_DIR, "speech_client.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
    p.add_argument("--endpoint-only", action="store_true", dest="endpoint_only",
                   help="record base_url and auth only (models and voices come from the endpoint later)")
    sub.add_parser("show")
    p = sub.add_parser("probe-endpoint")
    p.add_argument("--base-url", required=True, dest="base_url")
    args = parser.parse_args(argv)
    return {"check": cmd_check, "propose": cmd_propose, "record": cmd_record,
            "show": cmd_show, "probe-endpoint": cmd_probe_endpoint}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
