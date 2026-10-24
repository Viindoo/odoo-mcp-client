#!/usr/bin/env python3
"""youtube_upload.py - publish a video to one of the configured YouTube channels.

YouTube Data API v3, resumable upload, to the channel of a PURPOSE (`youtube_config.py`:
`[channels.<purpose>]`). The OAuth client id, client secret and the channel's refresh token are
passed in by the caller - the odoo-media MCP server passes the plugin's configured options; the
CLI below reads the environment variables YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET and
YOUTUBE_REFRESH_TOKEN_<SLOT> for a human running it by hand. The access token lives in memory
for one call and nothing secret is printed, logged or written. Calls retry on 429 / 503 with a
short backoff and honour a cancel Event.

  upload --channel P --video V.mp4 --title T --description-file D.txt [--tags a,b] [--language vi]
         [--privacy unlisted|private|public] [--category 28] [--captions vi_VN=path.srt ...]
         [--thumbnail thumb.jpg] [--playlist PLAYLIST_ID] [--dry-run]
         Prints VIDEO_ID, WATCH_URL, EMBED_URL, SHORT_URL, PRIVACY and one CAPTION_<lang>=ok|failed
         line per caption file. --dry-run prints the request plan and sends nothing.
  status --channel P --video-id ID   prints the processing and privacy status.
  describe --channel P --video-id ID the video's title, channel and privacy (read before a change).
  set-privacy --channel P --video-id ID --privacy unlisted|private|public
         when the docs that embed it go live (-> public) or it is retired (-> private).
  delete --channel P --video-id ID --yes   removes a superseded video for good (a re-voiced
         video can only be re-uploaded); `describe` first, a human confirms, then --yes.
  check  --channel P [--live]        the configuration, and with --live ONE token refresh plus
         channels.list(mine=true): prints CHANNEL_ID and CHANNEL_TITLE, so a revoked or expired
         refresh token is caught before a recording run (1 quota unit).

Exit: 0 ok, 1 the API refused (reason on stderr, never a value), 2 missing configuration,
3 a needed value was not supplied.
Quota (per the API reference): one upload counts in a 100-per-day upload bucket; a caption insert
costs 400 units, a thumbnail set 50, a playlist insert 50 of the daily 10,000.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

_LIB_DIR = os.path.dirname(os.path.abspath(__file__))
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
import youtube_config  # noqa: E402

# ODOO_AI_GOOGLE_BASE replaces both Google hosts (a test double, or a corporate proxy that fronts them).
_GOOGLE_BASE = os.environ.get("ODOO_AI_GOOGLE_BASE", "").rstrip("/")
_API = _GOOGLE_BASE or "https://www.googleapis.com"
_OAUTH = _GOOGLE_BASE or "https://oauth2.googleapis.com"
TOKEN_URL = _OAUTH + "/token"
UPLOAD_URL = _API + "/upload/youtube/v3/videos"
CAPTIONS_URL = _API + "/upload/youtube/v3/captions"
THUMB_URL = _API + "/upload/youtube/v3/thumbnails/set"
PLAYLIST_URL = _API + "/youtube/v3/playlistItems"
VIDEOS_URL = _API + "/youtube/v3/videos"
CHANNELS_URL = _API + "/youtube/v3/channels"
CHUNK = 8 * 1024 * 1024  # a multiple of 256 KiB, as the resumable protocol requires
RETRY_STATUS = (429, 503)
RETRY_BACKOFF_S = (2.0, 6.0, 18.0)
# the CLI's sources of the values (the MCP server passes them in instead)
CLIENT_ID_ENV = "YOUTUBE_CLIENT_ID"
CLIENT_SECRET_ENV = "YOUTUBE_CLIENT_SECRET"
TOKEN_ENV = {s: "YOUTUBE_REFRESH_TOKEN_%s" % s.upper() for s in youtube_config.SLOTS}


class UploadError(Exception):
    pass


def channel_config(purpose, cfg=None):
    """The channel table of `purpose` (validated configuration), or UploadError 2."""
    if cfg is None:
        try:
            cfg = youtube_config.read_config()
        except FileNotFoundError:
            raise UploadError("no YouTube configuration - run /odoo-ai-agents:odoo-setup youtube", 2)
    problems = youtube_config.validate(cfg)
    if problems:
        raise UploadError("youtube.toml invalid: " + "; ".join(problems), 2)
    table = youtube_config.channel(cfg, purpose)
    if table is None:
        raise UploadError("no channel for purpose %r (declared: %s) - the video stays local unless "
                          "/odoo-ai-agents:odoo-setup youtube declares one" % (
                              purpose, ", ".join(sorted(cfg["channels"]))), 2)
    return table


def credentials_from_env(table):
    """The CLI's credentials for a channel, from the fixed environment variable names."""
    names = (CLIENT_ID_ENV, CLIENT_SECRET_ENV, TOKEN_ENV[table["slot"]])
    values = [os.environ.get(n) for n in names]
    missing = [n for n, v in zip(names, values) if not v]
    if missing:
        raise UploadError("value(s) not supplied: %s (the odoo-media server passes the plugin options; "
                          "a human running this CLI exports these names)" % ", ".join(missing), 3)
    return {"client_id": values[0], "client_secret": values[1], "refresh_token": values[2]}


def _cancelled(cancel):
    return cancel is not None and cancel.is_set()


def _request(url, data=None, headers=None, method=None, timeout=120, cancel=None):
    attempt = 0
    while True:
        if _cancelled(cancel):
            raise UploadError("cancelled before %s" % url.split("?")[0], 1)
        req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, dict(resp.headers), resp.read()
        except urllib.error.HTTPError as exc:
            body = exc.read()[:400].decode("utf-8", errors="replace")
            if exc.code == 308:
                return 308, dict(exc.headers), b""
            if exc.code in RETRY_STATUS and attempt < len(RETRY_BACKOFF_S):
                _wait(RETRY_BACKOFF_S[attempt], cancel)
                attempt += 1
                continue
            raise UploadError("%s answered %d: %s" % (url.split("?")[0], exc.code, body), 1)
        except (urllib.error.URLError, OSError) as exc:
            raise UploadError("%s unreachable: %s" % (url.split("?")[0], exc), 1)


def _wait(delay, cancel):
    if cancel is not None:
        cancel.wait(delay)
    else:
        import time
        time.sleep(delay)


def access_token(creds, cancel=None):
    """One access token minted from the refresh token; lives in memory only."""
    form = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": creds["refresh_token"],
        "client_id": creds["client_id"],
        "client_secret": creds["client_secret"],
    }).encode("utf-8")
    _s, _h, body = _request(TOKEN_URL, form, {"Content-Type": "application/x-www-form-urlencoded"}, "POST",
                            cancel=cancel)
    token = json.loads(body.decode("utf-8")).get("access_token")
    if not token:
        raise UploadError("the token endpoint returned no access token", 1)
    return token


def my_channel(token, cancel=None):
    """{id, title} of the channel the token belongs to (channels.list mine=true, 1 unit)."""
    _s, _h, body = _request(CHANNELS_URL + "?part=snippet&mine=true", None, _auth(token), "GET", cancel=cancel)
    items = json.loads(body.decode("utf-8")).get("items") or []
    if not items:
        raise UploadError("the token belongs to an account with no YouTube channel", 1)
    return {"id": items[0].get("id", ""), "title": (items[0].get("snippet") or {}).get("title", "")}


def _auth(token, extra=None):
    h = {"Authorization": "Bearer " + token}
    h.update(extra or {})
    return h


def video_resource(title, description, tags, language, privacy, category):
    snippet = {"title": title[:100], "description": description[:5000], "categoryId": str(category)}
    if tags:
        snippet["tags"] = tags
    if language:
        snippet["defaultLanguage"] = language
    return {"snippet": snippet, "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False,
                                           "embeddable": True}}


def resumable_upload(token, path, resource, cancel=None):
    size = os.path.getsize(path)
    mime = mimetypes.guess_type(path)[0] or "video/mp4"
    init_url = UPLOAD_URL + "?uploadType=resumable&part=snippet,status"
    _s, headers, _b = _request(init_url, json.dumps(resource).encode("utf-8"),
                               _auth(token, {"Content-Type": "application/json; charset=UTF-8",
                                             "X-Upload-Content-Length": str(size),
                                             "X-Upload-Content-Type": mime}), "POST")
    session = headers.get("Location") or headers.get("location")
    if not session:
        raise UploadError("the upload session returned no Location header", 1)
    sent = 0
    with open(path, "rb") as fh:
        while sent < size:
            chunk = fh.read(CHUNK)
            last = sent + len(chunk) - 1
            status, h, body = _request(session, chunk, {"Content-Type": mime, "Content-Length": str(len(chunk)),
                                                        "Content-Range": "bytes %d-%d/%d" % (sent, last, size)},
                                       "PUT", timeout=600, cancel=cancel)
            if status == 308:
                rng = h.get("Range") or h.get("range") or ""
                sent = int(rng.split("-")[-1]) + 1 if rng else last + 1
                fh.seek(sent)
                continue
            if status in (200, 201):
                return json.loads(body.decode("utf-8"))
            raise UploadError("unexpected upload status %s" % status, 1)
    raise UploadError("upload ended without a video resource", 1)


def insert_caption(token, video_id, lang, path):
    name = lang.replace("_", "-")
    boundary = "odooai-caption"
    meta = json.dumps({"snippet": {"videoId": video_id, "language": name.split("-")[0], "name": name,
                                   "isDraft": False}}).encode("utf-8")
    with open(path, "rb") as fh:
        data = fh.read()
    body = (b"--" + boundary.encode() + b"\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n" + meta
            + b"\r\n--" + boundary.encode() + b"\r\nContent-Type: application/octet-stream\r\n\r\n" + data
            + b"\r\n--" + boundary.encode() + b"--\r\n")
    _request(CAPTIONS_URL + "?uploadType=multipart&part=snippet", body,
             _auth(token, {"Content-Type": "multipart/related; boundary=" + boundary}), "POST")


def set_thumbnail(token, video_id, path):
    mime = mimetypes.guess_type(path)[0] or "image/jpeg"
    with open(path, "rb") as fh:
        data = fh.read()
    _request(THUMB_URL + "?videoId=" + urllib.parse.quote(video_id), data,
             _auth(token, {"Content-Type": mime}), "POST")


def add_to_playlist(token, video_id, playlist_id):
    body = json.dumps({"snippet": {"playlistId": playlist_id,
                                   "resourceId": {"kind": "youtube#video", "videoId": video_id}}}).encode("utf-8")
    _request(PLAYLIST_URL + "?part=snippet", body, _auth(token, {"Content-Type": "application/json"}), "POST")


def urls(video_id):
    return {"WATCH_URL": "https://www.youtube.com/watch?v=" + video_id,
            "EMBED_URL": "https://www.youtube.com/embed/" + video_id,
            "SHORT_URL": "https://youtu.be/" + video_id}


def plan(args, cfg):
    privacy = args.privacy or cfg.get("privacy", "unlisted")
    lines = ["PLAN=dry-run",
             "UPLOAD=%s?uploadType=resumable&part=snippet,status (%d bytes, %s)" % (
                 UPLOAD_URL, os.path.getsize(args.video), mimetypes.guess_type(args.video)[0] or "video/mp4"),
             "PRIVACY=%s" % privacy, "TITLE=%s" % args.title[:100]]
    for item in args.captions or []:
        lang, _, path = item.partition("=")
        lines.append("CAPTION_%s=%s (%s)" % (lang, CAPTIONS_URL, os.path.basename(path)))
    if args.thumbnail:
        lines.append("THUMBNAIL=%s (%s)" % (THUMB_URL, os.path.basename(args.thumbnail)))
    playlist = args.playlist or cfg.get("playlist_id")
    if playlist:
        lines.append("PLAYLIST=%s (%s)" % (PLAYLIST_URL, playlist))
    lines.append("CHANNEL=%s (slot %s; the values come from the plugin options, never printed)" % (
        cfg["channel"], cfg["slot"]))
    return lines


def publish(table, creds, video, title, description, tags=(), language=None, privacy=None, category="28",
            captions=None, thumbnail=None, playlist=None, cancel=None):
    """Upload + captions + thumbnail + playlist for one channel table. Returns a result dict; the
    extras never fail the upload (their outcome is reported per item)."""
    token = access_token(creds, cancel=cancel)
    privacy = privacy or table.get("privacy", "unlisted")
    language = language or table.get("default_language")
    resource = video_resource(title, description, list(tags or []), language, privacy, category)
    resource_out = resumable_upload(token, video, resource, cancel=cancel)
    video_id = resource_out.get("id")
    if not video_id:
        raise UploadError("the upload returned no video id", 1)
    result = {"video_id": video_id, "privacy": resource_out.get("status", {}).get("privacyStatus") or privacy,
              "captions": {}, "thumbnail": None, "playlist": None}
    result.update({k.lower(): v for k, v in urls(video_id).items()})
    for lang, path in (captions or {}).items():
        try:
            insert_caption(token, video_id, lang, path)
            result["captions"][lang] = "ok"
        except UploadError as exc:
            result["captions"][lang] = "failed (%s)" % exc.args[0]
    if thumbnail:
        try:
            set_thumbnail(token, video_id, thumbnail)
            result["thumbnail"] = "ok"
        except UploadError as exc:
            result["thumbnail"] = "failed (%s)" % exc.args[0]
    playlist = playlist or table.get("playlist_id")
    if playlist:
        try:
            add_to_playlist(token, video_id, playlist)
            result["playlist"] = "ok"
        except UploadError as exc:
            result["playlist"] = "failed (%s)" % exc.args[0]
    return result


def video_details(creds, video_id, cancel=None):
    """{id, title, channel_id, channel_title, privacy} of a video, read before any change to it."""
    token = access_token(creds, cancel=cancel)
    _s, _h, body = _request(VIDEOS_URL + "?part=snippet,status&id=" + urllib.parse.quote(video_id), None,
                            _auth(token), "GET", cancel=cancel)
    items = json.loads(body.decode("utf-8")).get("items") or []
    if not items:
        raise UploadError("video %s not found (or not this channel's)" % video_id, 1)
    sn, st = items[0].get("snippet", {}), items[0].get("status", {})
    return {"id": items[0].get("id"), "title": sn.get("title", ""), "channel_id": sn.get("channelId", ""),
            "channel_title": sn.get("channelTitle", ""), "privacy": st.get("privacyStatus")}, token


def set_privacy(creds, video_id, privacy, cancel=None):
    """Change a video's privacy (unlisted -> public when the docs that embed it go live; -> private
    to retire it). Returns the details after the change."""
    details, token = video_details(creds, video_id, cancel=cancel)
    body = json.dumps({"id": video_id, "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False,
                                                  "embeddable": True}}).encode("utf-8")
    _request(VIDEOS_URL + "?part=status", body, _auth(token, {"Content-Type": "application/json"}), "PUT",
             cancel=cancel)
    details["privacy"] = privacy
    return details


def delete_video(creds, video_id, cancel=None):
    """Delete a video for good (a re-voiced video can only be re-uploaded: YouTube never replaces a
    file). Returns the details it had. Irreversible: the caller confirms with a human first."""
    details, token = video_details(creds, video_id, cancel=cancel)
    _request(VIDEOS_URL + "?id=" + urllib.parse.quote(video_id), None, _auth(token), "DELETE", cancel=cancel)
    return details


def video_status(creds, video_id, cancel=None):
    token = access_token(creds, cancel=cancel)
    _s, _h, body = _request(VIDEOS_URL + "?part=status,processingDetails&id=" + urllib.parse.quote(video_id),
                            None, _auth(token), "GET", cancel=cancel)
    items = json.loads(body.decode("utf-8")).get("items") or []
    if not items:
        raise UploadError("video %s not found" % video_id, 1)
    st = items[0].get("status", {})
    pr = items[0].get("processingDetails", {})
    return {"upload_status": st.get("uploadStatus"), "privacy": st.get("privacyStatus"),
            "processing": pr.get("processingStatus")}


def cmd_upload(args):
    table = channel_config(args.channel)
    with open(args.description_file, encoding="utf-8") as fh:
        description = fh.read()
    if args.dry_run:
        print("\n".join(plan(args, table)))
        return 0
    creds = credentials_from_env(table)
    captions = {}
    for item in args.captions or []:
        lang, _, path = item.partition("=")
        captions[lang] = path
    result = publish(table, creds, args.video, args.title, description,
                     [t for t in (args.tags or "").split(",") if t], args.language, args.privacy, args.category,
                     captions, args.thumbnail, args.playlist)
    print("VIDEO_ID=%s" % result["video_id"])
    for name in ("watch_url", "embed_url", "short_url"):
        print("%s=%s" % (name.upper(), result[name]))
    print("PRIVACY=%s" % result["privacy"])
    for lang, outcome in result["captions"].items():
        print("CAPTION_%s=%s" % (lang, outcome))
    if result["thumbnail"]:
        print("THUMBNAIL=%s" % result["thumbnail"])
    if result["playlist"]:
        print("PLAYLIST=%s" % result["playlist"])
    return 0


def cmd_status(args):
    table = channel_config(args.channel)
    st = video_status(credentials_from_env(table), args.video_id)
    print("UPLOAD_STATUS=%s" % st["upload_status"])
    print("PRIVACY=%s" % st["privacy"])
    print("PROCESSING=%s" % st["processing"])
    return 0


def cmd_describe(args):
    table = channel_config(args.channel)
    d, _t = video_details(credentials_from_env(table), args.video_id)
    for k in ("id", "title", "channel_id", "channel_title", "privacy"):
        print("%s=%s" % (k.upper(), d[k]))
    return 0


def cmd_set_privacy(args):
    table = channel_config(args.channel)
    d = set_privacy(credentials_from_env(table), args.video_id, args.privacy)
    print("VIDEO_ID=%s\nTITLE=%s\nPRIVACY=%s" % (d["id"], d["title"], d["privacy"]))
    return 0


def cmd_delete(args):
    table = channel_config(args.channel)
    if not args.yes:
        print("x delete is irreversible: re-run with --yes after confirming the title with `describe`", file=sys.stderr)
        return 2
    d = delete_video(credentials_from_env(table), args.video_id)
    print("DELETED=%s (%s)" % (d["id"], d["title"]))
    return 0


def cmd_check(args):
    table = channel_config(args.channel)
    print("CHANNEL=%s slot=%s privacy=%s" % (table["channel"], table["slot"], table.get("privacy", "unlisted")))
    if not args.live:
        print("ok configuration (pass --live to test the values against Google)")
        return 0
    creds = credentials_from_env(table)
    mine = my_channel(access_token(creds))
    print("CHANNEL_ID=%s" % mine["id"])
    print("CHANNEL_TITLE=%s" % mine["title"])
    print("ok live")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("upload")
    p.add_argument("--channel", required=True)
    p.add_argument("--video", required=True); p.add_argument("--title", required=True)
    p.add_argument("--description-file", required=True, dest="description_file")
    p.add_argument("--tags"); p.add_argument("--language"); p.add_argument("--privacy", choices=youtube_config.PRIVACY)
    p.add_argument("--category", default="28"); p.add_argument("--captions", action="append")
    p.add_argument("--thumbnail"); p.add_argument("--playlist"); p.add_argument("--dry-run", action="store_true", dest="dry_run")
    p = sub.add_parser("status"); p.add_argument("--channel", required=True)
    p.add_argument("--video-id", required=True, dest="video_id")
    p = sub.add_parser("check"); p.add_argument("--channel", required=True); p.add_argument("--live", action="store_true")
    p = sub.add_parser("describe"); p.add_argument("--channel", required=True); p.add_argument("--video-id", required=True, dest="video_id")
    p = sub.add_parser("set-privacy"); p.add_argument("--channel", required=True); p.add_argument("--video-id", required=True, dest="video_id")
    p.add_argument("--privacy", required=True, choices=youtube_config.PRIVACY)
    p = sub.add_parser("delete"); p.add_argument("--channel", required=True); p.add_argument("--video-id", required=True, dest="video_id")
    p.add_argument("--yes", action="store_true")
    args = parser.parse_args(argv)
    try:
        return {"upload": cmd_upload, "status": cmd_status, "check": cmd_check, "describe": cmd_describe,
                "set-privacy": cmd_set_privacy, "delete": cmd_delete}[args.cmd](args)
    except UploadError as exc:
        print("x " + exc.args[0], file=sys.stderr)
        return exc.args[1] if len(exc.args) > 1 else 1


if __name__ == "__main__":
    sys.exit(main())
