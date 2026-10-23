#!/usr/bin/env python3
"""youtube_upload.py - publish a documentation video to the configured YouTube channel.

YouTube Data API v3, resumable upload, from the configuration youtube_config.py reads. The OAuth
client id, secret and refresh token come from the environment variables the configuration NAMES
(scope youtube.force-ssl); the access token lives in memory for one run and nothing secret is
printed, logged or written.

  upload --video V.mp4 --title T --description-file D.txt [--tags a,b] [--language vi]
         [--privacy unlisted|private|public] [--category 28] [--captions vi_VN=path.srt ...]
         [--thumbnail thumb.jpg] [--playlist PLAYLIST_ID] [--dry-run]
         Prints VIDEO_ID, WATCH_URL, EMBED_URL, SHORT_URL, PRIVACY and one CAPTION_<lang>=ok|failed
         line per caption file. --dry-run prints the request plan (endpoints, parts, sizes) and
         sends nothing.
  status --video-id ID   prints the processing and privacy status.

Exit: 0 ok, 1 the API refused (reason on stderr, never a token), 2 missing configuration.
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

TOKEN_URL = "https://oauth2.googleapis.com/token"
UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
CAPTIONS_URL = "https://www.googleapis.com/upload/youtube/v3/captions"
THUMB_URL = "https://www.googleapis.com/upload/youtube/v3/thumbnails/set"
PLAYLIST_URL = "https://www.googleapis.com/youtube/v3/playlistItems"
VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
CHUNK = 8 * 1024 * 1024  # a multiple of 256 KiB, as the resumable protocol requires


class UploadError(Exception):
    pass


def _cfg():
    try:
        cfg = youtube_config.read_config()
    except FileNotFoundError:
        raise UploadError("no YouTube configuration - run /odoo-ai-agents:odoo-setup youtube", 2)
    problems = youtube_config.validate(cfg)
    if problems:
        raise UploadError("youtube.toml invalid: " + "; ".join(problems), 2)
    missing = youtube_config.missing_env(cfg)
    if missing:
        raise UploadError("environment variable(s) not set: " + ", ".join(missing), 2)
    return cfg["youtube"]


def _request(url, data=None, headers=None, method=None, timeout=120):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as exc:
        body = exc.read()[:400].decode("utf-8", errors="replace")
        if exc.code == 308:
            return 308, dict(exc.headers), b""
        raise UploadError("%s answered %d: %s" % (url.split("?")[0], exc.code, body), 1)
    except (urllib.error.URLError, OSError) as exc:
        raise UploadError("%s unreachable: %s" % (url.split("?")[0], exc), 1)


def access_token(cfg):
    y = cfg
    form = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": os.environ[y["refresh_token_env"]],
        "client_id": os.environ[y["client_id_env"]],
        "client_secret": os.environ[y["client_secret_env"]],
    }).encode("utf-8")
    _s, _h, body = _request(TOKEN_URL, form, {"Content-Type": "application/x-www-form-urlencoded"}, "POST")
    token = json.loads(body.decode("utf-8")).get("access_token")
    if not token:
        raise UploadError("the token endpoint returned no access token", 1)
    return token


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


def resumable_upload(token, path, resource):
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
                                       "PUT", timeout=600)
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
    lines.append("SECRETS=from environment variables %s, %s, %s (never printed)" % (
        cfg["client_id_env"], cfg["client_secret_env"], cfg["refresh_token_env"]))
    return lines


def cmd_upload(args):
    cfg = _cfg()
    with open(args.description_file, encoding="utf-8") as fh:
        description = fh.read()
    if args.dry_run:
        print("\n".join(plan(args, cfg)))
        return 0
    token = access_token(cfg)
    privacy = args.privacy or cfg.get("privacy", "unlisted")
    language = args.language or cfg.get("default_language")
    resource = video_resource(args.title, description, [t for t in (args.tags or "").split(",") if t],
                              language, privacy, args.category)
    video = resumable_upload(token, args.video, resource)
    video_id = video.get("id")
    if not video_id:
        raise UploadError("the upload returned no video id", 1)
    print("VIDEO_ID=%s" % video_id)
    for name, value in urls(video_id).items():
        print("%s=%s" % (name, value))
    print("PRIVACY=%s" % (video.get("status", {}).get("privacyStatus") or privacy))
    for item in args.captions or []:
        lang, _, path = item.partition("=")
        try:
            insert_caption(token, video_id, lang, path)
            print("CAPTION_%s=ok" % lang)
        except UploadError as exc:
            print("CAPTION_%s=failed (%s)" % (lang, exc.args[0]))
    if args.thumbnail:
        try:
            set_thumbnail(token, video_id, args.thumbnail)
            print("THUMBNAIL=ok")
        except UploadError as exc:
            print("THUMBNAIL=failed (%s)" % exc.args[0])
    playlist = args.playlist or cfg.get("playlist_id")
    if playlist:
        try:
            add_to_playlist(token, video_id, playlist)
            print("PLAYLIST=ok")
        except UploadError as exc:
            print("PLAYLIST=failed (%s)" % exc.args[0])
    return 0


def cmd_status(args):
    cfg = _cfg()
    token = access_token(cfg)
    _s, _h, body = _request(VIDEOS_URL + "?part=status,processingDetails&id=" + urllib.parse.quote(args.video_id),
                            None, _auth(token), "GET")
    items = json.loads(body.decode("utf-8")).get("items") or []
    if not items:
        raise UploadError("video %s not found" % args.video_id, 1)
    st = items[0].get("status", {})
    pr = items[0].get("processingDetails", {})
    print("UPLOAD_STATUS=%s" % st.get("uploadStatus"))
    print("PRIVACY=%s" % st.get("privacyStatus"))
    print("PROCESSING=%s" % pr.get("processingStatus"))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("upload")
    p.add_argument("--video", required=True); p.add_argument("--title", required=True)
    p.add_argument("--description-file", required=True, dest="description_file")
    p.add_argument("--tags"); p.add_argument("--language"); p.add_argument("--privacy", choices=youtube_config.PRIVACY)
    p.add_argument("--category", default="28"); p.add_argument("--captions", action="append")
    p.add_argument("--thumbnail"); p.add_argument("--playlist"); p.add_argument("--dry-run", action="store_true", dest="dry_run")
    p = sub.add_parser("status"); p.add_argument("--video-id", required=True, dest="video_id")
    args = parser.parse_args(argv)
    try:
        return {"upload": cmd_upload, "status": cmd_status}[args.cmd](args)
    except UploadError as exc:
        print("x " + exc.args[0], file=sys.stderr)
        return exc.args[1] if len(exc.args) > 1 else 1


if __name__ == "__main__":
    sys.exit(main())
