"""tools_youtube.py - publish to the YouTube channel of a PURPOSE (youtube_config.py channels).

  youtube_check    the channel's configuration, and with live=true one token refresh plus
                   channels.list(mine=true) (1 quota unit) - run it BEFORE a recording run
  youtube_upload   resumable upload + captions + thumbnail + playlist; dry_run plans only
  youtube_status   processing and privacy status of an uploaded video
The OAuth client values and the channel slot's refresh token are values.* (plugin options); an
access token is minted in memory per call. A `privacy: public` upload is the one outward-facing
call this server makes: the PermissionRequest hook leaves it to the human prompt.
"""

import os

from odoo_local import cli, protocol
from odoo_local.errors import ToolError

from . import values

_PURPOSE = {"type": "string", "pattern": "^[a-z][a-z0-9_-]{0,31}$",
            "description": "The channel purpose as youtube.toml declares it: docs (user guides, docs-site, App Store DEMO) or marketing (sales and marketing videos), or another purpose the operator declared."}

CHECK_IN = {"type": "object", "required": ["channel"],
            "properties": {"channel": _PURPOSE, "live": {"type": "boolean", "default": False,
                           "description": "Also refresh a token and read the channel title from Google (1 quota unit)."}},
            "additionalProperties": False}
CHECK_OUT = {
    "type": "object", "required": ["channel", "slot", "privacy", "values_present", "live"],
    "properties": {"channel": {"type": "string"}, "purpose": {"type": "string"}, "slot": {"type": "string"},
                   "privacy": {"type": "string"}, "playlist_id": {"type": ["string", "null"]},
                   "values_present": {"type": "boolean"}, "missing_options": {"type": "array", "items": {"type": "string"}},
                   "live": {"type": "boolean"}, "channel_id": {"type": ["string", "null"]},
                   "channel_title": {"type": ["string", "null"]}},
}
UPLOAD_IN = {
    "type": "object", "required": ["channel", "video", "title"],
    "properties": {
        "channel": _PURPOSE,
        "video": {"type": "string", "minLength": 1, "description": "Absolute path of the final MP4 (publish profile verified)."},
        "title": {"type": "string", "minLength": 1, "maxLength": 100},
        "description": {"type": "string", "description": "The description text (chapters included)."},
        "description_file": {"type": "string", "minLength": 1},
        "tags": {"type": "array", "items": {"type": "string"}},
        "language": {"type": "string", "description": "BCP-47 default language of title/description, e.g. vi; the channel's default when absent."},
        "privacy": {"type": "string", "enum": ["unlisted", "private", "public"], "description": "The channel's default when absent (unlisted until the docs are published)."},
        "category": {"type": "string", "default": "28"},
        "captions": {"type": "object", "description": "{locale: absolute path of an .srt}", "additionalProperties": {"type": "string"}},
        "thumbnail": {"type": "string", "description": "Absolute path of a JPEG under 2 MB."},
        "playlist": {"type": "string", "description": "Playlist id; the channel's default when absent."},
        "dry_run": {"type": "boolean", "default": False, "description": "Plan the requests, send nothing."},
    },
    "additionalProperties": False,
}
UPLOAD_OUT = {
    "type": "object", "required": ["channel", "privacy"],
    "properties": {"channel": {"type": "string"}, "dry_run": {"type": "boolean"}, "plan": {"type": "array", "items": {"type": "string"}},
                   "video_id": {"type": "string"}, "watch_url": {"type": "string"}, "embed_url": {"type": "string"},
                   "short_url": {"type": "string"}, "privacy": {"type": "string"},
                   "captions": {"type": "object", "additionalProperties": {"type": "string"}},
                   "thumbnail": {"type": ["string", "null"]}, "playlist": {"type": ["string", "null"]}},
}
STATUS_IN = {"type": "object", "required": ["channel", "video_id"],
             "properties": {"channel": _PURPOSE, "video_id": {"type": "string", "minLength": 1}}, "additionalProperties": False}
STATUS_OUT = {"type": "object", "required": ["upload_status", "privacy", "processing"],
              "properties": {"upload_status": {"type": ["string", "null"]}, "privacy": {"type": ["string", "null"]},
                             "processing": {"type": ["string", "null"]}}}


def _lib():
    return cli.load_lib("youtube_upload")


def _translate(exc):
    message = exc.args[0]
    code = exc.args[1] if len(exc.args) > 1 else 1
    if code == 3:
        return ToolError("VALUE_NOT_CONFIGURED", message)
    if code == 2 and "no channel for purpose" in message:
        return ToolError("YOUTUBE_CHANNEL_UNKNOWN", message)
    if code == 2:
        return ToolError("YOUTUBE_NOT_CONFIGURED", message)
    return ToolError("YOUTUBE_FAILED", message)


def _table(yu, purpose):
    try:
        return yu.channel_config(purpose)
    except yu.UploadError as exc:
        raise _translate(exc)


def _needed(table):
    return (values.YT_CLIENT_ID, values.YT_CLIENT_SECRET, values.YT_TOKEN[table["slot"]])


def _creds(table):
    names = _needed(table)
    missing = [values.OPTION[n] for n in names if not values.present(n)]
    if missing:
        raise ToolError("VALUE_NOT_CONFIGURED", "plugin option(s) not set: %s" % ", ".join(missing),
                        {"options": missing, "slot": table["slot"]})
    return {"client_id": values.require(names[0]), "client_secret": values.require(names[1]),
            "refresh_token": values.require(names[2])}


def register(registry, ctx):
    def check(args, ctx):
        yu = _lib()
        table = _table(yu, args["channel"])
        missing = [values.OPTION[n] for n in _needed(table) if not values.present(n)]
        out = {"channel": table["channel"], "purpose": args["channel"], "slot": table["slot"],
               "privacy": table.get("privacy", "unlisted"), "playlist_id": table.get("playlist_id"),
               "values_present": not missing, "missing_options": missing, "live": False,
               "channel_id": None, "channel_title": None}
        if args.get("live"):
            creds = _creds(table)
            try:
                mine = yu.my_channel(yu.access_token(creds, cancel=protocol.cancel_event()), cancel=protocol.cancel_event())
            except yu.UploadError as exc:
                raise _translate(exc)
            out.update({"live": True, "channel_id": mine["id"], "channel_title": mine["title"]})
        return out

    def upload(args, ctx):
        yu = _lib()
        table = _table(yu, args["channel"])
        if not os.path.isfile(args["video"]):
            raise ToolError("INVALID_ARGUMENTS", "arguments.video: %s is not a file" % args["video"])
        description = args.get("description")
        if description is None and args.get("description_file"):
            try:
                with open(args["description_file"], encoding="utf-8") as fh:
                    description = fh.read()
            except OSError as exc:
                raise ToolError("INVALID_ARGUMENTS", "arguments.description_file: %s" % exc)
        description = description or ""
        privacy = args.get("privacy") or table.get("privacy", "unlisted")
        if args.get("dry_run"):
            class _A(object):
                pass
            a = _A()
            a.video, a.title, a.privacy, a.thumbnail, a.playlist = args["video"], args["title"], privacy, args.get("thumbnail"), args.get("playlist")
            a.captions = ["%s=%s" % (k, v) for k, v in (args.get("captions") or {}).items()]
            return {"channel": args["channel"], "dry_run": True, "plan": yu.plan(a, table), "privacy": privacy}
        creds = _creds(table)
        try:
            result = yu.publish(table, creds, args["video"], args["title"], description, args.get("tags") or [],
                                args.get("language"), privacy, args.get("category", "28"), args.get("captions") or {},
                                args.get("thumbnail"), args.get("playlist"), cancel=protocol.cancel_event())
        except yu.UploadError as exc:
            raise _translate(exc)
        result["channel"] = args["channel"]
        result["dry_run"] = False
        return result

    def status(args, ctx):
        yu = _lib()
        table = _table(yu, args["channel"])
        try:
            return yu.video_status(_creds(table), args["video_id"], cancel=protocol.cancel_event())
        except yu.UploadError as exc:
            raise _translate(exc)

    registry.add(
        "youtube_check",
        "Report the YouTube channel declared for a purpose (docs | marketing | another the operator declared): "
        "its slot, default privacy, and whether every plugin option it needs is set; live=true also refreshes a "
        "token and reads the channel title from Google (1 quota unit) so a revoked or expired value is caught "
        "BEFORE a recording run. No channel for the purpose = the video stays local; the result names the setup "
        "command. Read-only.",
        CHECK_IN, CHECK_OUT, check, title="Check a YouTube channel", read_only=True, long_running=True)
    registry.add(
        "youtube_upload",
        "Publish a finished video to the channel of a purpose: resumable upload, then captions per language, "
        "thumbnail and playlist (each reported ok|failed, never failing the upload). Privacy defaults to the "
        "channel's (unlisted until the documentation that embeds it is published); a public upload is the one "
        "outward call here, so confirm it with the user first. dry_run=true plans the requests and sends "
        "nothing. Returns the watch, embed and short URLs the docs embed. Long-running.",
        UPLOAD_IN, UPLOAD_OUT, upload, title="Upload to YouTube", long_running=True, destructive=False)
    registry.add(
        "youtube_status",
        "Processing and privacy status of a video uploaded to the channel of a purpose. Read-only.",
        STATUS_IN, STATUS_OUT, status, title="YouTube video status", read_only=True, long_running=True)
