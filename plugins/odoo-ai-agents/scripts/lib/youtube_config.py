#!/usr/bin/env python3
"""youtube_config.py - the YouTube channels a run publishes videos to, by purpose.

`youtube.toml` in the machine-global, never-committed state root holds ONE table per channel,
keyed by the PURPOSE the videos serve (free identifiers; `docs` and `marketing` are the two every
consumer in this plugin names):

  [channels.docs]
  slot             = "docs"        # which configured value holds this channel's refresh token:
                                   # docs | marketing | third (one channel per slot)
  channel          = "Acme Docs"   # a label for reports
  privacy          = "unlisted"    # default privacy of an upload: unlisted (default) | private
                                   # (never public: public is an explicit per-upload choice)
  playlist_id      = "PL..."       # optional
  default_language = "vi"          # optional BCP-47 default for title/description

  [channels.marketing]
  slot = "marketing"
  channel = "Acme"

At least ONE channel when YouTube is configured; two or three are optional (a second company
declares what it has; a run whose purpose has no channel keeps the video local and reports the
path). No credential value enters this file: the OAuth client id and secret and the three
refresh-token slots are the plugin's configured options (`youtube_client_id`,
`youtube_client_secret`, `youtube_refresh_token_docs|marketing|third`, Claude Code's own masked
dialog), which only the odoo-media MCP server receives; `record` refuses a value that looks like one.
A single `[youtube]` table written by an older plugin is read as `channels.docs` (slot docs) with a
notice and rewritten on the next `record`.

Subcommands (stdlib only):
  check   [--channel P]   exit 0 when youtube.toml is valid (and names P); 1 with the remedy;
                          2 unreadable. Whether the configured values are present is the
                          odoo-media `youtube_check` tool's job (it can also test them live).
  propose                 prints what the operator prepares on the Google side and the slots
  record  --channel P --from-json FILE   validate ONE channel table and merge it into the file
  remove  --channel P
  show                    prints the configuration as JSON
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
SLOTS = ("docs", "marketing", "third")
CHANNEL_KEYS = ("slot", "channel", "privacy", "playlist_id", "default_language")
PRIVACY = ("unlisted", "private", "public")
DEFAULT_PRIVACY = ("unlisted", "private")   # a channel DEFAULT is never public: public is said per upload, explicitly
PURPOSE_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
LANG_RE = re.compile(r"^[a-z]{2,3}(-[A-Za-z0-9]+)*$")
# the plugin options (plugin.json userConfig) the odoo-media server receives, per slot
OPTION_FOR_SLOT = {s: "youtube_refresh_token_%s" % s for s in SLOTS}
CLIENT_OPTIONS = ("youtube_client_id", "youtube_client_secret")
SCOPE = "https://www.googleapis.com/auth/youtube.force-ssl"
LEGACY_TABLE = "youtube"
LEGACY_ENV_KEYS = ("client_id_env", "client_secret_env", "refresh_token_env")


def youtube_path():
    return os.path.join(paths.state_root(), FILE_NAME)


def _looks_like_a_secret(value):
    v = value.strip()
    return len(v) > 40 and (any(c.islower() for c in v) and any(c.isdigit() for c in v)) and " " not in v


def migrate(cfg):
    """A single `[youtube]` table becomes `channels.docs`. Returns True when it did."""
    if not isinstance(cfg, dict) or not isinstance(cfg.get(LEGACY_TABLE), dict) or "channels" in cfg:
        return False
    old = cfg.pop(LEGACY_TABLE)
    table = {"slot": "docs"}
    for key in ("channel", "privacy", "playlist_id", "default_language"):
        if key in old:
            table[key] = old[key]
    cfg["channels"] = {"docs": table}
    return True


def validate(cfg):
    problems = []
    if not isinstance(cfg, dict) or not isinstance(cfg.get("channels"), dict):
        return ["[channels] table missing - at least one [channels.<purpose>] table"]
    channels = cfg["channels"]
    if not channels:
        return ["[channels] declares no channel - at least one [channels.<purpose>] table"]
    slots = {}
    for purpose, table in channels.items():
        if not PURPOSE_RE.match(str(purpose)):
            problems.append("[channels] %r: a purpose is a short lowercase identifier such as docs or marketing"
                            % purpose)
            continue
        problems.extend(validate_channel(purpose, table))
        slot = table.get("slot") if isinstance(table, dict) else None
        if slot in SLOTS:
            if slot in slots:
                problems.append("[channels.%s] slot %r is already used by channel %s - one channel per slot"
                                % (purpose, slot, slots[slot]))
            slots[slot] = purpose
    return problems


def validate_channel(purpose, table):
    problems = []
    if not isinstance(table, dict):
        return ["[channels.%s] is not a table" % purpose]
    for key in table:
        if key not in CHANNEL_KEYS:
            problems.append("[channels.%s] unknown key %r" % (purpose, key))
    slot = table.get("slot", purpose if purpose in SLOTS else None)
    if slot not in SLOTS:
        problems.append("[channels.%s] slot: one of %s (the configured value that holds this channel's "
                        "refresh token)" % (purpose, " | ".join(SLOTS)))
    if not isinstance(table.get("channel"), str) or not table["channel"].strip():
        problems.append("[channels.%s] channel: a non-empty label" % purpose)
    if table.get("privacy", "unlisted") not in DEFAULT_PRIVACY:
        problems.append("[channels.%s] privacy: one of %s (public is never a default - it is passed "
                        "explicitly per upload, where a human confirms it)" % (purpose, " | ".join(DEFAULT_PRIVACY)))
    if "playlist_id" in table and (not isinstance(table["playlist_id"], str) or not table["playlist_id"].strip()):
        problems.append("[channels.%s] playlist_id: a non-empty id" % purpose)
    if "default_language" in table and not LANG_RE.match(str(table["default_language"])):
        problems.append("[channels.%s] default_language: a BCP-47 tag such as vi or en-US" % purpose)
    for key, value in table.items():
        if isinstance(value, str) and _looks_like_a_secret(value):
            problems.append("[channels.%s] %s: this looks like a credential value - a configuration file "
                            "never holds one; the plugin's configuration dialog does" % (purpose, key))
    return problems


def normalize(cfg):
    """Fill the slot default (purpose == slot name)."""
    for purpose, table in (cfg.get("channels") or {}).items():
        if isinstance(table, dict) and "slot" not in table and purpose in SLOTS:
            table["slot"] = purpose
    return cfg


def render(cfg):
    q = config_merge._toml_basic_string
    out = []
    for purpose in sorted(cfg["channels"]):
        table = cfg["channels"][purpose]
        out.append("[channels.%s]" % purpose)
        for key in CHANNEL_KEYS:
            if key in table:
                out.append("%s = %s" % (key, q(str(table[key]))))
        out.append("")
    return "\n".join(out).rstrip("\n") + "\n"


def read_config(path=None):
    """The configuration, migrated and normalized. `cfg["_migrated"]` is True when the file still
    carries the single-table form."""
    with open(path or youtube_path(), encoding="utf-8") as fh:
        cfg = docs_site_config._loads(fh.read())
    migrated = migrate(cfg)
    normalize(cfg)
    if migrated:
        cfg["_migrated"] = True
    return cfg


def channel(cfg, purpose):
    """The channel table for `purpose`, or None."""
    table = (cfg.get("channels") or {}).get(purpose)
    return table if isinstance(table, dict) else None


def slot_option(table):
    """The plugin option name that holds this channel's refresh token."""
    return OPTION_FOR_SLOT[table["slot"]]


def _load(path):
    try:
        return read_config(path), 0
    except FileNotFoundError:
        return None, 1
    except (OSError, ValueError) as exc:
        print("x %s could not be read: %s" % (path, exc), file=sys.stderr)
        return None, 2


def _write(cfg):
    path = youtube_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    cfg = {"channels": cfg["channels"]}
    with config_merge.locked_target(path):
        if os.path.exists(path):
            config_merge._backup(path)
        config_merge._atomic_replace(path, render(cfg))
    return path


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
    if not problems and args.channel and not channel(cfg, args.channel):
        problems = ["no channel for purpose %r (declared: %s) - run /odoo-ai-agents:odoo-setup youtube"
                    % (args.channel, ", ".join(sorted(cfg["channels"])))]
    for p in problems:
        print("x " + p, file=sys.stderr)
    if problems:
        return 1
    if cfg.get("_migrated"):
        print("NOTICE=the file still holds the single-table form; the next record rewrites it as channels")
        print("UPGRADE=its variable names come from an earlier plugin version; the operator runs in their "
              "own terminal: python3 %s apply" % os.path.join(_LIB_DIR, "upgrade_values.py"))
    for purpose in sorted(cfg["channels"]):
        table = cfg["channels"][purpose]
        print("CHANNEL_%s=%s slot=%s privacy=%s option=%s" % (
            purpose, table["channel"], table["slot"], table.get("privacy", "unlisted"), slot_option(table)))
    print("ok YouTube configuration: %s (%d channel(s))" % (path, len(cfg["channels"])))
    return 0


def _emit(name, value):
    print("%s='%s'" % (name, str(value).replace("'", "'\\''")))


def cmd_propose(args):
    _emit("PREPARE_1", "a Google Cloud project with the YouTube Data API v3 enabled")
    _emit("PREPARE_2", "an OAuth 2.0 client of type Desktop app; download its client JSON")
    _emit("PREPARE_3", "the consent screen: audience External and status In production (Internal refuses a "
                       "brand-account channel; Testing expires the refresh token after 7 days); Publish "
                       "needs Branding filled in: app name, support contact, homepage, privacy policy URL, "
                       "and the authorized domain of those URLs; an unverified app is fine (Advanced > continue)")
    _emit("PREPARE_4", "one consent per channel account, on a machine with a browser: "
                       "75-youtube.sh consent --channel <purpose> --client-json <downloaded file> "
                       "(run by the operator in a terminal; it stores what it obtains in the plugin "
                       "configuration and prints nothing of it)")
    _emit("SCOPE", SCOPE)
    _emit("SLOTS", " ".join(SLOTS))
    _emit("CLIENT_OPTIONS", " ".join(CLIENT_OPTIONS))
    for slot in SLOTS:
        _emit("SLOT_OPTION_%s" % slot, OPTION_FOR_SLOT[slot])
    cfg, code = _load(youtube_path())
    _emit("DECLARED", 1 if code == 0 else 0)
    _emit("DECLARED_CHANNELS", " ".join(sorted(cfg["channels"])) if code == 0 else "")
    _emit("FACTS_TO_CONFIRM", "purpose channel slot privacy playlist_id default_language")
    _emit("RULE", "at least one channel; docs and marketing are the purposes this plugin's runs name; "
                  "a purpose without a channel keeps the video local")
    return 0


def cmd_record(args):
    with open(args.from_json, encoding="utf-8") as fh:
        table = json.load(fh)
    if isinstance(table, dict) and "channels" in table and not args.channel:
        cfg = normalize({"channels": table["channels"]})
    else:
        if not args.channel:
            print("x --channel <purpose> is required when FILE holds one channel table", file=sys.stderr)
            return 2
        existing, code = _load(youtube_path())
        cfg = existing if code == 0 else {"channels": {}}
        cfg = {"channels": dict(cfg.get("channels") or {})}
        cfg["channels"][args.channel] = table
        normalize(cfg)
    problems = validate(cfg)
    if problems:
        for p in problems:
            print("x " + p, file=sys.stderr)
        return 1
    print("ok wrote %s" % _write(cfg))
    return 0


def cmd_remove(args):
    cfg, code = _load(youtube_path())
    if code:
        return code or 1
    if not channel(cfg, args.channel):
        print("x no channel for purpose %r" % args.channel, file=sys.stderr)
        return 1
    del cfg["channels"][args.channel]
    print("ok wrote %s (%d channel(s) left)" % (_write(cfg), len(cfg["channels"])))
    return 0


def cmd_show(args):
    cfg, code = _load(youtube_path())
    if code:
        if code == 1:
            print("x no YouTube configuration - run /odoo-ai-agents:odoo-setup youtube", file=sys.stderr)
        return code
    print(json.dumps({"channels": cfg["channels"]}, indent=2, ensure_ascii=False))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("check"); p.add_argument("--channel")
    sub.add_parser("propose")
    p = sub.add_parser("record"); p.add_argument("--channel"); p.add_argument("--from-json", required=True, dest="from_json")
    p = sub.add_parser("remove"); p.add_argument("--channel", required=True)
    sub.add_parser("show")
    args = parser.parse_args(argv)
    return {"check": cmd_check, "propose": cmd_propose, "record": cmd_record, "remove": cmd_remove,
            "show": cmd_show}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
