"""tools_speech.py - narration speech through the configured OpenAI-audio-shaped endpoint.

  speech_synthesize   text -> 48 kHz mono WAV at `out` (speech_client.tts; the pronunciation map
                      of the language applied to the TEXT SENT ONLY, phoneme entries only when
                      `phonemes` says the engine accepts them)
  speech_transcribe   WAV -> transcript (speech_client.stt), word timestamps on request
  speech_voices       the voice listing the endpoint publishes, as it returns it
  speech_probe        per language: one sentence synthesized, transcribed in the same language and
                      scored - the round trip that catches a voice/language mismatch or an
                      endpoint that is not what the configuration says, BEFORE a recording run
All four are long-running (a shared low-end gateway queues a second caller; the client retries on
429/503 and watches the call's cancel event). The value the `bearer` mode sends is values.SPEECH.
"""

import os

from odoo_local import cli, protocol
from odoo_local.errors import ToolError

from . import values

_LANG = {"type": "string", "pattern": "^[a-z]{2,3}_[A-Z]{2}$", "description": "Locale such as vi_VN or en_US."}
_ABS = {"type": "string", "minLength": 1, "description": "Absolute path."}

SYNTHESIZE_IN = {
    "type": "object",
    "required": ["lang", "out"],
    "properties": {
        "text": {"type": "string", "description": "The narration text; one sentence per line (the engine pauses at a line break)."},
        "text_file": _ABS,
        "lang": _LANG,
        "out": {"type": "string", "minLength": 1, "description": "Absolute path of the WAV to write."},
        "pronunciation": {"type": "object", "description": "Pronunciation map {lang: [{written, spoken, kind}]} (pronunciation.py); applied to the text sent to the engine only."},
        "phonemes": {"type": "boolean", "default": False, "description": "True when the engine accepts the map's phoneme entries (inline IPA); else they are skipped."},
    },
    "additionalProperties": False,
}
SYNTHESIZE_OUT = {
    "type": "object", "required": ["out", "duration_s", "lang"],
    "properties": {"out": {"type": "string"}, "duration_s": {"type": "number"}, "lang": {"type": "string"}},
}
TRANSCRIBE_IN = {
    "type": "object", "required": ["audio", "lang"],
    "properties": {"audio": _ABS, "lang": _LANG,
                   "words": {"type": "boolean", "default": False, "description": "Also return word timestamps when the engine provides them."}},
    "additionalProperties": False,
}
TRANSCRIBE_OUT = {
    "type": "object", "required": ["text", "words"],
    "properties": {"text": {"type": "string"},
                   "words": {"type": "array", "items": {"type": "object", "properties": {
                       "word": {"type": "string"}, "start": {"type": "number"}, "end": {"type": "number"}}}}},
}
VOICES_OUT = {"type": "object", "required": ["voices"], "properties": {"voices": {"type": ["array", "object", "string", "null"]}}}
PROBE_IN = {"type": "object", "properties": {"lang": _LANG, "out_dir": _ABS}, "additionalProperties": False}
PROBE_OUT = {
    "type": "object", "required": ["ok", "results"],
    "properties": {"ok": {"type": "boolean"}, "results": {"type": "array", "items": {"type": "object"}}},
}


def _speech_client():
    return cli.load_lib("speech_client")


def _value(cfg, sc):
    """The bearer value when the configuration needs one, else None."""
    speech_config = cli.load_lib("speech_config")
    return values.require(values.SPEECH) if speech_config.needs_value(cfg) else None


def _config(sc):
    try:
        return sc._load()
    except sc.SpeechError as exc:
        raise _translate(exc)


def _translate(exc):
    message = exc.args[0]
    code = exc.args[1] if len(exc.args) > 1 else 1
    if code == 3:
        return ToolError("VALUE_NOT_CONFIGURED", message, {"option": values.OPTION[values.SPEECH]})
    if code == 2 and "ffmpeg" in message:
        return ToolError("FFMPEG_MISSING", message)
    if code == 2 or "no speech configuration" in message or "speech.toml invalid" in message:
        return ToolError("SPEECH_NOT_CONFIGURED", message)
    return ToolError("SPEECH_FAILED", message)


def _text(args):
    if args.get("text") is not None:
        return args["text"]
    path = args.get("text_file")
    if not path:
        raise ToolError("INVALID_ARGUMENTS", "arguments: one of text or text_file is required")
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError as exc:
        raise ToolError("INVALID_ARGUMENTS", "arguments.text_file: %s" % exc)


def register(registry, ctx):
    def synthesize(args, ctx):
        sc = _speech_client()
        cfg = _config(sc)
        text = _text(args)
        try:
            out, dur = sc.tts(text, args["lang"], args["out"], args.get("pronunciation"), cfg=cfg,
                              value=_value(cfg, sc), cancel=protocol.cancel_event(), phonemes=args.get("phonemes", False))
        except sc.SpeechError as exc:
            raise _translate(exc)
        return {"out": out, "duration_s": round(dur, 3), "lang": args["lang"]}

    def transcribe(args, ctx):
        sc = _speech_client()
        cfg = _config(sc)
        if not os.path.isfile(args["audio"]):
            raise ToolError("INVALID_ARGUMENTS", "arguments.audio: %s is not a file" % args["audio"])
        try:
            res = sc.stt(args["audio"], args["lang"], cfg=cfg, value=_value(cfg, sc),
                         cancel=protocol.cancel_event(), words=True)
        except sc.SpeechError as exc:
            raise _translate(exc)
        return {"text": res["text"], "words": res["words"] if args.get("words") else []}

    def voices(args, ctx):
        sc = _speech_client()
        cfg = _config(sc)
        try:
            return {"voices": sc.voices(cfg=cfg, value=_value(cfg, sc))}
        except sc.SpeechError as exc:
            raise _translate(exc)

    def probe(args, ctx):
        sc = _speech_client()
        cfg = _config(sc)
        results = sc.probe(args.get("lang"), args.get("out_dir"), value=_value(cfg, sc), cfg=cfg,
                           cancel=protocol.cancel_event())
        return {"ok": all(r["ok"] and r["verdict"] == "pass" for r in results), "results": results}

    registry.add(
        "speech_synthesize",
        "Synthesize narration text in one language through the configured speech endpoint and write a "
        "48 kHz mono WAV. One sentence per line in the text (the engine pauses at a line break). Pass the "
        "storyboard's pronunciation map so brands and acronyms are respelled for the engine only; set "
        "phonemes=true only when media_info / the configuration says the engine accepts inline IPA. "
        "Long-running; the endpoint is a shared low-end service, so call it one clip at a time.",
        SYNTHESIZE_IN, SYNTHESIZE_OUT, synthesize, title="Synthesize narration", long_running=True, idempotent=True)
    registry.add(
        "speech_transcribe",
        "Transcribe a WAV in the given language through the configured speech-to-text endpoint; with "
        "words=true also the word timestamps when the engine provides them. Use it with "
        "narration_check.py to verify a narration clip says its script. Long-running.",
        TRANSCRIBE_IN, TRANSCRIBE_OUT, transcribe, title="Transcribe a clip", read_only=True, long_running=True)
    registry.add(
        "speech_voices",
        "List the voices the configured speech endpoint publishes (as the endpoint returns them; a gateway "
        "that publishes none answers an error). Read-only.",
        {"type": "object", "properties": {}, "additionalProperties": False}, VOICES_OUT, voices,
        title="List voices", read_only=True, long_running=True)
    registry.add(
        "speech_probe",
        "Round-trip check per configured language (or one `lang`): synthesize one sentence, transcribe it "
        "in the same language, score the word error rate. verdict=fail means the voice does not speak that "
        "language, the endpoint is not what the configuration says, or the value is wrong - fix the setup "
        "before any recording run. Clips land under <state root>/scratch/speech-probe. Long-running.",
        PROBE_IN, PROBE_OUT, probe, title="Probe the speech setup", read_only=True, long_running=True)
