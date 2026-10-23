#!/usr/bin/env python3
"""youtube_config.py - where a run publishes a documentation video, vendor-agnostic in shape.

One `[youtube]` table in the machine-global, never-committed `youtube.toml` (state root):

  channel            a label for the channel the OAuth user uploads to (for reports only)
  client_id_env      NAME of the environment variable holding the OAuth client id
  client_secret_env  NAME of the variable holding the OAuth client secret
  refresh_token_env  NAME of the variable holding the user's refresh token (scope
                     youtube.force-ssl: it covers the upload, the captions and the playlist)
  privacy            default privacy of an upload: unlisted (default) | private | public
  playlist_id        optional playlist every documentation video is added to
  default_language   optional BCP-47 default for title/description, e.g. "vi"

No secret enters any file: the three *_env keys name variables; `record` refuses a value that
looks like a key or token; `check` verifies the variables are set in this shell. The upload itself
is youtube_upload.py (YouTube Data API v3, resumable upload).

Subcommands (stdlib only):
  check     exit 0 when youtube.toml is valid AND the named variables are set; 1 with the remedy;
            2 unreadable
  propose   prints what the operator prepares (a Google Cloud project with the YouTube Data API
            enabled, an OAuth client of type Desktop, a refresh token with the upload scope
            obtained once on a machine with a browser), which variables are already set (names
            only), DECLARED
  record    --from-json FILE
  show      prints the configuration as JSON
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

_LIB_DIR = os.path.dirname(os.path.abspath(__file__))
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
import config_merge  # noqa: E402
import docs_site_config  # noqa: E402
import paths  # noqa: E402

FILE_NAME = "youtube.toml"
KEYS = ("channel", "client_id_env", "client_secret_env", "refresh_token_env", "privacy",
        "playlist_id", "default_language")
ENV_KEYS = ("client_id_env", "client_secret_env", "refresh_token_env")
PRIVACY = ("unlisted", "private", "public")
ENV_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,}$")
DEFAULT_ENV = {"client_id_env": "YOUTUBE_CLIENT_ID", "client_secret_env": "YOUTUBE_CLIENT_SECRET",
               "refresh_token_env": "YOUTUBE_REFRESH_TOKEN"}


def youtube_path():
    return os.path.join(paths.state_root(), FILE_NAME)


def _looks_like_a_secret(value):
    v = value.strip()
    return len(v) > 24 and (any(c.islower() for c in v) or "-" in v or "/" in v)


def validate(cfg):
    problems = []
    if not isinstance(cfg, dict) or not isinstance(cfg.get("youtube"), dict):
        return ["[youtube] table missing"]
    y = cfg["youtube"]
    for key in y:
        if key not in KEYS:
            problems.append("[youtube] unknown key %r" % key)
    if not isinstance(y.get("channel"), str) or not y["channel"].strip():
        problems.append("[youtube] channel: a non-empty label")
    for key in ENV_KEYS:
        v = y.get(key, "")
        if not isinstance(v, str) or not ENV_NAME_RE.match(v) or _looks_like_a_secret(v):
            problems.append("[youtube] %s: the NAME of an environment variable such as %s - never the "
                            "value" % (key, DEFAULT_ENV[key]))
    if y.get("privacy", "unlisted") not in PRIVACY:
        problems.append("[youtube] privacy: one of %s" % " | ".join(PRIVACY))
    if "playlist_id" in y and (not isinstance(y["playlist_id"], str) or not y["playlist_id"].strip()):
        problems.append("[youtube] playlist_id: a non-empty id")
    if "default_language" in y and not re.match(r"^[a-z]{2,3}(-[A-Za-z0-9]+)*$", str(y["default_language"])):
        problems.append("[youtube] default_language: a BCP-47 tag such as vi or en-US")
    return problems


def render(cfg):
    q = config_merge._toml_basic_string
    out = ["[youtube]"]
    for key in KEYS:
        if key in cfg["youtube"]:
            out.append("%s = %s" % (key, q(str(cfg["youtube"][key]))))
    return "\n".join(out) + "\n"


def read_config(path=None):
    with open(path or youtube_path(), encoding="utf-8") as fh:
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
    return sorted(n for n in (cfg["youtube"][k] for k in ENV_KEYS) if not os.environ.get(n))


def cmd_check(args):
    path = youtube_path()
    cfg, code = _load(path)
    if code == 1:
        print("x no YouTube configuration at %s - run /odoo-ai-agents:odoo-setup youtube" % path,
              file=sys.stderr)
        return 1
    if code:
        return code
    problems = validate(cfg)
    if not problems:
        problems = ["environment variable %s is not set in this shell" % n for n in missing_env(cfg)]
    for p in problems:
        print("x " + p, file=sys.stderr)
    if problems:
        return 1
    print("ok YouTube configuration: %s (privacy %s)" % (path, cfg["youtube"].get("privacy", "unlisted")))
    return 0


def _emit(name, value):
    print("%s='%s'" % (name, str(value).replace("'", "'\\''")))


def cmd_propose(args):
    _emit("PREPARE_1", "a Google Cloud project with the YouTube Data API v3 enabled")
    _emit("PREPARE_2", "an OAuth 2.0 client of type Desktop app (client id + client secret)")
    _emit("PREPARE_3", "a refresh token for the channel's Google account with the scope "
                       "https://www.googleapis.com/auth/youtube.force-ssl (upload + captions + "
                       "playlist), obtained once through the desktop (loopback) consent flow on a "
                       "machine with a browser")
    _emit("PREPARE_4", "the consent screen published (In production), else Google expires the "
                       "refresh token after 7 days; one test upload confirms the project is not "
                       "locked to private")
    _emit("KEY_ENV_SET", " ".join(n for n in DEFAULT_ENV.values() if os.environ.get(n)) or "none")
    cfg, code = _load(youtube_path())
    _emit("DECLARED", 1 if code == 0 else 0)
    _emit("FACTS_TO_CONFIRM", "channel client_id_env client_secret_env refresh_token_env privacy "
                              "playlist_id default_language")
    return 0


def cmd_record(args):
    with open(args.from_json, encoding="utf-8") as fh:
        cfg = json.load(fh)
    problems = validate(cfg)
    if problems:
        for p in problems:
            print("x " + p, file=sys.stderr)
        return 1
    path = youtube_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with config_merge.locked_target(path):
        if os.path.exists(path):
            config_merge._backup(path)
        config_merge._atomic_replace(path, render(cfg))
    print("ok wrote %s" % path)
    return 0


def cmd_show(args):
    cfg, code = _load(youtube_path())
    if code:
        if code == 1:
            print("x no YouTube configuration - run /odoo-ai-agents:odoo-setup youtube", file=sys.stderr)
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
