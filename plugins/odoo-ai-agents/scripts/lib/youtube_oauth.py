#!/usr/bin/env python3
"""youtube_oauth.py - obtain a YouTube refresh token for one channel and hand it to the plugin
configuration, run by the OPERATOR in their own terminal (never by an agent: the values pass
through this process only).

  consent --channel P --client-json FILE [--plugin-id odoo-ai-agents@<marketplace>] [--port N]
          [--no-open] [--out-json FILE]

OAuth 2.0 authorization code flow for a Desktop client with PKCE and a loopback redirect:
reads the client id and secret from the client JSON Google's console downloads, opens the consent
URL for the scope youtube.force-ssl (access_type=offline, prompt=consent so a refresh token is
issued), listens on 127.0.0.1:<port> for the redirect, exchanges the code, and reads the channel
title (channels.list mine=true). Then it stores the three values as the plugin's options -
`youtube_client_id`, `youtube_client_secret` and the channel's slot option
(`youtube_refresh_token_<slot>`, the slot from youtube.toml) - by piping them to
`claude plugin configure <id> --values-stdin` (Claude Code's own store, never argv, never
printed). Without a usable `claude` on PATH, or with --out-json, it writes them to FILE (mode
0600) for the operator to feed to that command and delete. Prints CHANNEL_TITLE, STORED=<option
names> or OUT_JSON=<path>, and the reminder to run /reload-plugins.

Exit: 0 ok, 1 Google refused, 2 bad input, 3 the store step failed (the values were not kept
anywhere; run again).
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import http.server
import json
import os
import secrets
import shutil
import subprocess
import sys
import threading
import urllib.parse
import urllib.request
import webbrowser

_LIB_DIR = os.path.dirname(os.path.abspath(__file__))
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
import youtube_config  # noqa: E402
import youtube_upload  # noqa: E402

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
PLUGIN_NAME = "odoo-ai-agents"


class ConsentError(Exception):
    pass


def read_client_json(path):
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    block = data.get("installed") or data.get("web") or {}
    cid, csec = block.get("client_id"), block.get("client_secret")
    if not cid or not csec:
        raise ConsentError("%s holds no installed/web client_id + client_secret" % path, 2)
    return cid, csec


def pkce_pair():
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(48)).rstrip(b"=").decode("ascii")
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
    return verifier, challenge


def consent_url(client_id, redirect_uri, challenge, state):
    query = urllib.parse.urlencode({
        "client_id": client_id, "redirect_uri": redirect_uri, "response_type": "code",
        "scope": youtube_config.SCOPE, "access_type": "offline", "prompt": "consent",
        "code_challenge": challenge, "code_challenge_method": "S256", "state": state,
    })
    return AUTH_URL + "?" + query


class _Redirect(http.server.BaseHTTPRequestHandler):
    state = ""
    result = {}
    done = threading.Event()

    def log_message(self, *_args):  # the request line carries the code; never log it
        pass

    def do_GET(self):
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if params.get("state", [""])[0] != self.state:
            self.send_response(400); self.end_headers(); self.wfile.write(b"state mismatch"); return
        if "error" in params:
            type(self).result = {"error": params["error"][0]}
        else:
            type(self).result = {"code": params.get("code", [""])[0]}
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"<html><body><p>Consent received. You can close this tab.</p></body></html>")
        self.done.set()


def wait_for_code(port, state, timeout_s):
    _Redirect.state = state
    _Redirect.result = {}
    _Redirect.done = threading.Event()
    server = http.server.HTTPServer(("127.0.0.1", port), _Redirect)
    server.allow_reuse_address = False
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        if not _Redirect.done.wait(timeout_s):
            raise ConsentError("no consent received within %d s" % timeout_s, 1)
    finally:
        server.shutdown()
    if "error" in _Redirect.result:
        raise ConsentError("Google refused: %s" % _Redirect.result["error"], 1)
    return _Redirect.result["code"]


def exchange(code, client_id, client_secret, verifier, redirect_uri):
    form = urllib.parse.urlencode({
        "code": code, "client_id": client_id, "client_secret": client_secret,
        "redirect_uri": redirect_uri, "grant_type": "authorization_code", "code_verifier": verifier,
    }).encode("utf-8")
    req = urllib.request.Request(youtube_upload.TOKEN_URL, data=form,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise ConsentError("the token endpoint answered %d: %s" % (
            exc.code, exc.read()[:200].decode("utf-8", "replace")), 1)
    refresh = data.get("refresh_token")
    if not refresh:
        raise ConsentError("no refresh token was issued (the consent screen must be In production and "
                           "the request carries prompt=consent); revoke the app's access in the Google "
                           "account and run again", 1)
    return refresh, data.get("access_token", "")


def plugin_id():
    """odoo-ai-agents@<marketplace> as `claude plugin list` reports it, or None."""
    if not shutil.which("claude"):
        return None
    try:
        out = subprocess.run(["claude", "plugin", "list", "--json"], capture_output=True, text=True,
                             timeout=60, check=False).stdout
        for entry in json.loads(out) if out.strip().startswith("[") else []:
            ident = entry.get("id") or entry.get("name") or ""
            if ident.split("@")[0] == PLUGIN_NAME:
                return ident if "@" in ident else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    return None


def store(values, ident):
    """Pipe the values to `claude plugin configure <id> --values-stdin`; nothing printed."""
    proc = subprocess.run(["claude", "plugin", "configure", ident, "--values-stdin"],
                          input=json.dumps(values), capture_output=True, text=True, timeout=120, check=False)
    if proc.returncode != 0:
        raise ConsentError("claude plugin configure failed (%d): %s" % (
            proc.returncode, (proc.stderr or proc.stdout).strip()[-300:]), 3)


def write_out_json(values, path):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(values, fh)


def cmd_consent(args):
    table = youtube_upload.channel_config(args.channel)
    option = youtube_config.slot_option(table)
    client_id, client_secret = read_client_json(args.client_json)
    verifier, challenge = pkce_pair()
    state = secrets.token_urlsafe(16)
    port = args.port or _free_port()
    redirect_uri = "http://127.0.0.1:%d/" % port
    url = consent_url(client_id, redirect_uri, challenge, state)
    print("CONSENT_URL=%s" % url)
    print("Sign in with the account that owns the channel '%s', then approve." % table["channel"])
    if not args.no_open:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    code = wait_for_code(port, state, args.timeout)
    refresh, access = exchange(code, client_id, client_secret, verifier, redirect_uri)
    try:
        mine = youtube_upload.my_channel(access) if access else {"id": "", "title": ""}
    except youtube_upload.UploadError as exc:
        mine = {"id": "", "title": "(not read: %s)" % exc.args[0]}
    print("CHANNEL_TITLE=%s" % mine["title"])
    print("CHANNEL_ID=%s" % mine["id"])
    values = {"youtube_client_id": client_id, "youtube_client_secret": client_secret, option: refresh}
    if args.out_json:
        write_out_json(values, args.out_json)
        print("OUT_JSON=%s (mode 0600; feed it to `claude plugin configure <plugin id> --values-stdin < %s`, "
              "then delete it)" % (args.out_json, args.out_json))
        return 0
    ident = args.plugin_id or plugin_id()
    if not ident:
        raise ConsentError("the plugin id could not be determined (claude not on PATH or the plugin is not "
                           "installed from a marketplace): run again with --plugin-id %s@<marketplace> or "
                           "--out-json FILE" % PLUGIN_NAME, 3)
    store(values, ident)
    print("STORED=%s" % " ".join(sorted(values)))
    print("Run /reload-plugins in Claude Code (or start a new session) so the odoo-media server receives it.")
    return 0


def _free_port():
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("consent")
    p.add_argument("--channel", required=True)
    p.add_argument("--client-json", required=True, dest="client_json")
    p.add_argument("--plugin-id", dest="plugin_id")
    p.add_argument("--port", type=int)
    p.add_argument("--timeout", type=int, default=600)
    p.add_argument("--no-open", action="store_true", dest="no_open")
    p.add_argument("--out-json", dest="out_json")
    args = parser.parse_args(argv)
    try:
        return cmd_consent(args)
    except (ConsentError, youtube_upload.UploadError) as exc:
        print("x " + exc.args[0], file=sys.stderr)
        return exc.args[1] if len(exc.args) > 1 else 1


if __name__ == "__main__":
    sys.exit(main())
