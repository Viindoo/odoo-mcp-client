"""registry.py - the odoo-media tool registry: media_info + the speech and YouTube groups."""

import shutil
import sys

from odoo_local import cli, protocol

from . import SERVER_NAME, tools_speech, tools_youtube, values

INSTRUCTIONS = (
    "odoo-media runs the two surfaces that need a value the operator configured through the plugin's "
    "options: narration speech (speech_synthesize / speech_transcribe / speech_voices / speech_probe over "
    "the OpenAI-audio-shaped endpoint of speech.toml) and YouTube publishing (youtube_check / "
    "youtube_upload / youtube_status to the channel of a purpose in youtube.toml). media_info says which "
    "options are set; a missing one is reported as VALUE_NOT_CONFIGURED with the option name - the operator "
    "fills it in the plugin's configuration dialog, never in the chat. The endpoints are shared, low-end "
    "services: call these tools one at a time. Every failure returns error.code plus a one-line "
    "error.remedy: follow the remedy."
)

INFO_OUT = {
    "type": "object",
    "required": ["name", "version", "python", "plugin_root", "options", "speech", "youtube", "ffmpeg", "tools"],
    "properties": {
        "name": {"type": "string"}, "version": {"type": "string"}, "protocol_version": {"type": ["string", "null"]},
        "python": {"type": "string"}, "plugin_root": {"type": "string"},
        "options": {"type": "object", "additionalProperties": {"type": "boolean"},
                    "description": "Per plugin option: whether this server received a value (never the value)."},
        "speech": {"type": "object"},
        "youtube": {"type": "object"},
        "ffmpeg": {"type": "object"},
        "tools": {"type": "array", "items": {"type": "string"}},
    },
}


def _speech_state():
    speech_config = cli.load_lib("speech_config")
    try:
        cfg = speech_config.read_config()
    except FileNotFoundError:
        return {"configured": False, "problems": ["no speech.toml - run /odoo-ai-agents:odoo-setup voice"]}
    except (OSError, ValueError) as exc:
        return {"configured": False, "problems": ["speech.toml unreadable: %s" % exc]}
    problems = speech_config.validate(cfg)
    return {"configured": not problems, "problems": problems,
            "needs_value": speech_config.needs_value(cfg) if not problems else None,
            "value_present": values.present(values.SPEECH),
            "languages": sorted((cfg.get("tts") or {}).get("voices") or {}) if not problems else [],
            "tts_base_url": (cfg.get("tts") or {}).get("base_url"), "stt_base_url": (cfg.get("stt") or {}).get("base_url")}


def _youtube_state():
    youtube_config = cli.load_lib("youtube_config")
    try:
        cfg = youtube_config.read_config()
    except FileNotFoundError:
        return {"configured": False, "channels": {}, "client_present": values.present(values.YT_CLIENT_ID) and values.present(values.YT_CLIENT_SECRET),
                "problems": ["no youtube.toml - the video stays local unless /odoo-ai-agents:odoo-setup youtube declares a channel"]}
    except (OSError, ValueError) as exc:
        return {"configured": False, "channels": {}, "client_present": False, "problems": ["youtube.toml unreadable: %s" % exc]}
    problems = youtube_config.validate(cfg)
    channels = {}
    if not problems:
        for purpose, table in cfg["channels"].items():
            channels[purpose] = {"channel": table["channel"], "slot": table["slot"], "privacy": table.get("privacy", "unlisted"),
                                 "value_present": values.present(values.YT_TOKEN[table["slot"]])}
    return {"configured": not problems, "problems": problems, "channels": channels,
            "client_present": values.present(values.YT_CLIENT_ID) and values.present(values.YT_CLIENT_SECRET),
            "migrated_from_single_table": bool(cfg.get("_migrated"))}


def _ffmpeg_state():
    speech_config = cli.load_lib("speech_config")
    return {"path": shutil.which("ffmpeg"), "ffprobe": shutil.which("ffprobe"),
            "filters_missing": speech_config.ffmpeg_filters_missing()}


def build_registry(ctx):
    registry = protocol.ToolRegistry()

    def media_info(args, ctx):
        return {
            "name": SERVER_NAME, "version": ctx.version, "protocol_version": ctx.protocol_version,
            "python": "%d.%d.%d" % sys.version_info[:3], "plugin_root": str(ctx.plugin_root),
            "options": values.presence(), "speech": _speech_state(), "youtube": _youtube_state(),
            "ffmpeg": _ffmpeg_state(), "tools": registry.names(),
        }

    registry.add(
        "media_info",
        "Report this odoo-media server's version and what it can do right now: which plugin options it received "
        "(true/false per option, never a value), whether speech.toml and youtube.toml are valid, the narration "
        "languages, the declared channels and their slots, and the ffmpeg filters the assembler needs. Call it "
        "first in a narration or publishing run; an option shown false is filled by the operator in the plugin's "
        "configuration dialog, then /reload-plugins. Read-only.",
        {"type": "object", "properties": {}, "additionalProperties": False}, INFO_OUT, media_info,
        title="odoo-media server info", read_only=True)
    tools_speech.register(registry, ctx)
    tools_youtube.register(registry, ctx)
    return registry
