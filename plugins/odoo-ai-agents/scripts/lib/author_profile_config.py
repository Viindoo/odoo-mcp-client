#!/usr/bin/env python3
"""author_profile_config.py - the vendor's public contact profile for published docs.

One `[author]` table in the machine-global, never-committed `author-profile.toml` (state root,
next to instances.toml). The doc writers read it instead of inventing or copying contact details:

  vendor          the vendor name as the store shows it (manifest `author`)
  website         the ORGANIZATION's site: scheme + host, at most a trailing slash (the bare
                  `website` of the manifests whose value is not a module page)
  module_page_url the pattern of a module's own page on the vendor site, with the placeholders
                  `{series}` and `{module}` (e.g. https://vendor.example/apps/modules/{series}/{module}),
                  generalised from the manifests by `propose`; braces are allowed HERE only
  module_page_url_alt  optional second pattern the manifests also use
  presales_url    the web page a prospect contacts sales through (a form or a page) - the
                  Pre-Sales card of the App Store page; absent -> that card is omitted
  support_url     the ticket or helpdesk page - the Technical Support card; absent -> omitted
  support_email   the manifest `support` key ONLY (the store shows it to purchasers after the
                  purchase); it never appears in a page or a guide
  address_policy  `never` (default): no address in any published text; `image`: an address the
                  vendor insists on is rendered by email_image.py and embedded as an image
  font_file       optional absolute path of a TTF/OTF with Latin Extended coverage, used by
                  email_image.py; absent -> fc-match picks one

Every URL is https://, public (no local or reserved host) and never an email. `record` writes
only an operator-confirmed profile; `propose` reads candidate values from module descriptors under
an addons directory (git READ only, no network) and never fills anything in.

Subcommands (stdlib only; tomllib when present, else the subset reader of docs_site_config):
  check     exit 0 when a profile exists and is valid, 1 when none (remedy on stderr), 2 unreadable
  propose   --addons DIR  prints KEY=VALUE candidates from the manifests: VENDOR, WEBSITE (the
            bare organization site), MODULE_PAGE_URL_<n> (each module-page pattern with its count),
            MANIFEST_WEBSITE_DRIFT (manifests whose page names another module), SUPPORT_EMAIL,
            DECLARED, FACTS_TO_CONFIRM; writes nothing
  record    --from-json FILE  validates and writes the profile (backup, atomic)
  show      prints the profile as JSON
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
from urllib.parse import urlsplit

_LIB_DIR = os.path.dirname(os.path.abspath(__file__))
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
import config_merge  # noqa: E402
import docs_site_config  # noqa: E402  (the TOML subset reader, one home)
import paths  # noqa: E402

FILE_NAME = "author-profile.toml"
KEYS = ("vendor", "website", "module_page_url", "module_page_url_alt", "presales_url", "support_url",
        "support_email", "address_policy", "font_file")
REQUIRED = ("vendor",)
URL_KEYS = ("website", "presales_url", "support_url")
PATTERN_KEYS = ("module_page_url", "module_page_url_alt")
PLACEHOLDERS = ("{series}", "{module}")
POLICIES = ("never", "image")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
_RESERVED = ("localhost", "local", "internal", "lan", "home.arpa", "test", "invalid", "example",
             "example.com", "example.org", "example.net")


def profile_path():
    return os.path.join(paths.state_root(), FILE_NAME)


def _url_problem(name, value):
    if not isinstance(value, str) or not value.strip():
        return "%s: a non-empty string" % name
    parts = urlsplit(value.strip())
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or not host:
        return "%s: an https:// URL (got %r)" % (name, value)
    if "@" in parts.netloc or _EMAIL.match(value.strip()):
        return "%s: a web page, never an address" % name
    if any(host == d or host.endswith("." + d) for d in _RESERVED) or "." not in host:
        return "%s: a public host, not %r" % (name, host)
    return None


def validate(profile):
    problems = []
    if not isinstance(profile, dict):
        return ["the profile is not a table"]
    for key in profile:
        if key not in KEYS:
            problems.append("unknown key %r (allowed: %s)" % (key, ", ".join(KEYS)))
    for key in REQUIRED:
        if not isinstance(profile.get(key), str) or not profile[key].strip():
            problems.append("%s: required, a non-empty string" % key)
    for key in URL_KEYS:
        if key in profile:
            p = _url_problem(key, profile[key])
            if p:
                problems.append(p)
            elif "{" in str(profile[key]) or "}" in str(profile[key]):
                problems.append("%s: a fixed page, no placeholder - a module-page pattern belongs in "
                                "module_page_url" % key)
            elif key == "website" and urlsplit(str(profile[key]).strip()).path.strip("/"):
                problems.append("website: the organization's site (scheme and host only) - a page path "
                                "belongs in presales_url, support_url or module_page_url")
    for key in PATTERN_KEYS:
        if key in profile:
            value = str(profile[key]).strip()
            probe = value
            for ph in PLACEHOLDERS:
                probe = probe.replace(ph, "x")
            p = _url_problem(key, probe)
            if p:
                problems.append(p)
            elif not all(ph in value for ph in PLACEHOLDERS):
                problems.append("%s: a pattern with both {series} and {module}" % key)
    if "support_email" in profile:
        v = profile["support_email"]
        if not isinstance(v, str) or not _EMAIL.match(v.strip()):
            problems.append("support_email: one address (manifest `support` only)")
    policy = profile.get("address_policy", "never")
    if policy not in POLICIES:
        problems.append("address_policy: one of %s" % " | ".join(POLICIES))
    if "font_file" in profile:
        v = profile["font_file"]
        if not isinstance(v, str) or not os.path.isabs(v) or not os.path.isfile(v):
            problems.append("font_file: an absolute path of an existing TTF/OTF file")
    return problems


def render(profile):
    out = ["[author]"]
    for key in KEYS:
        if key in profile:
            out.append("%s = %s" % (key, config_merge._toml_basic_string(str(profile[key]).strip())))
    return "\n".join(out) + "\n"


def read_profile(path):
    with open(path, encoding="utf-8") as fh:
        data = docs_site_config._loads(fh.read())
    author = data.get("author")
    if not isinstance(author, dict):
        raise ValueError("no [author] table")
    return author


def _load(path):
    try:
        return read_profile(path), 0
    except FileNotFoundError:
        return None, 1
    except (OSError, ValueError) as exc:
        print("x %s could not be read: %s" % (path, exc), file=sys.stderr)
        return None, 2


def cmd_check(args):
    path = profile_path()
    profile, code = _load(path)
    if code == 1:
        print("x no author profile at %s - run /odoo-ai-agents:odoo-setup author" % path,
              file=sys.stderr)
        return 1
    if code:
        return code
    problems = validate(profile)
    for p in problems:
        print("x " + p, file=sys.stderr)
    if problems:
        return 1
    print("ok author profile: %s" % path)
    return 0


def _manifests(addons):
    for dirpath, dirnames, filenames in os.walk(addons):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and d != "node_modules")
        for name in ("__manifest__.py", "__openerp__.py"):
            if name in filenames:
                yield os.path.join(dirpath, name)


def _manifest_values(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            tree = ast.parse(fh.read())
    except (OSError, SyntaxError):
        return {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            out = {}
            for k, v in zip(node.keys, node.values):
                if isinstance(k, ast.Constant) and isinstance(v, ast.Constant) \
                        and k.value in ("author", "website", "support") and isinstance(v.value, str):
                    out[k.value] = v.value.strip()
            return out
    return {}


def _emit(name, value):
    print("%s=%s" % (name, json.dumps(value) if not isinstance(value, str) else
                     "'" + value.replace("'", "'\\''") + "'"))


_MODULE_PAGE = re.compile(r"^(https?://[^/]+/.*?)(\d+\.\d+)/([A-Za-z0-9_]+)/?$")


def generalise_website(value, module=None):
    """A manifest `website`: ("site", "https://host") for a bare organization site, or
    ("pattern", "https://host/.../{series}/{module}") for a module page (the series and the last
    path segment replaced). Anything else is ("other", value)."""
    v = (value or "").strip()
    parts = urlsplit(v)
    if not parts.scheme or not parts.hostname:
        return "other", v
    if not parts.path.strip("/"):
        return "site", "%s://%s" % (parts.scheme, parts.netloc)
    m = _MODULE_PAGE.match(v)
    if m and (module is None or m.group(3) == module or True):
        return "pattern", "%s{series}/{module}" % m.group(1)
    return "other", v


def cmd_propose(args):
    counts = {"author": {}, "website": {}, "support": {}}
    sites, patterns, drift, total = {}, {}, 0, 0
    for m in _manifests(os.path.abspath(args.addons)):
        values = _manifest_values(m)
        for key, value in values.items():
            if value:
                counts[key][value] = counts[key].get(value, 0) + 1
        web = values.get("website")
        if web:
            total += 1
            kind, norm = generalise_website(web)
            if kind == "site":
                sites[norm] = sites.get(norm, 0) + 1
            elif kind == "pattern":
                patterns[norm] = patterns.get(norm, 0) + 1
                mm = _MODULE_PAGE.match(web.strip())
                if mm and mm.group(3) != os.path.basename(os.path.dirname(m)):
                    drift += 1
    def top(d):
        return max(d, key=d.get) if d else ""
    _emit("VENDOR", top(counts["author"]))
    _emit("WEBSITE", top(sites))
    for i, (pat, n) in enumerate(sorted(patterns.items(), key=lambda kv: -kv[1]), 1):
        _emit("MODULE_PAGE_URL_%d" % i, "%s %d" % (pat, n))
    _emit("MANIFEST_WEBSITE_DRIFT", drift)
    _emit("SUPPORT_EMAIL", top(counts["support"]))
    _emit("MANIFESTS_READ", sum(counts["author"].values()))
    profile, code = _load(profile_path())
    _emit("DECLARED", 1 if code == 0 else 0)
    _emit("FACTS_TO_CONFIRM", "vendor website module_page_url presales_url support_url support_email "
                              "address_policy font_file")
    _emit("NOTE", "website is the organization's site; module_page_url is the pattern of a module's page "
                  "({series}, {module}); presales_url and support_url are web pages the vendor states - "
                  "nothing here derives them")
    return 0


def cmd_record(args):
    with open(args.from_json, encoding="utf-8") as fh:
        profile = json.load(fh)
    problems = validate(profile)
    if problems:
        for p in problems:
            print("x " + p, file=sys.stderr)
        return 1
    path = profile_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with config_merge.locked_target(path):
        if os.path.exists(path):
            config_merge._backup(path)
        config_merge._atomic_replace(path, render(profile))
    print("ok wrote %s" % path)
    return 0


def cmd_show(args):
    profile, code = _load(profile_path())
    if code:
        if code == 1:
            print("x no author profile - run /odoo-ai-agents:odoo-setup author", file=sys.stderr)
        return code
    print(json.dumps(profile, indent=2, ensure_ascii=False))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    p = sub.add_parser("propose")
    p.add_argument("--addons", required=True)
    p = sub.add_parser("record")
    p.add_argument("--from-json", required=True, dest="from_json")
    sub.add_parser("show")
    args = parser.parse_args(argv)
    return {"check": cmd_check, "propose": cmd_propose, "record": cmd_record,
            "show": cmd_show}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
