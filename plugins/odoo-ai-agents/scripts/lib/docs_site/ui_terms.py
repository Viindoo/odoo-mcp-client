#!/usr/bin/env python3
"""ui_terms.py - do the UI terms a translated page uses exist in Odoo, in that language?

  ODOO_DOC_PASSWORD=... ui_terms.py --url http://localhost:PORT --db D --login L --lang vi_VN
                                    --po file.po [--po file2.po ...] [--json]

Reads the msgstr of the given .po files and extracts UI-term candidates: the parts of a bold menu
path (`**Sales > Orders**`, split on the bold-path arrow, " > " or "-->"), `:guilabel:` text and the
parts of `:menuselection:`. Then asks a running instance (JSON-RPC: /web/session/authenticate,
/web/dataset/call_kw) for the names it shows in that language: ir.ui.menu name and complete_name,
ir.actions.act_window name, ir.module.module shortdesc of installed applications. Each term is
reported found (exact, else case-insensitive) or not found. Button labels and field labels are not
fetched (out of scope), so a term that is only a button or a field label reads "not found".

The password is read from the environment variable ODOO_DOC_PASSWORD only; it is never an argument and
never printed. Stdlib only, python3 >= 3.8.
Exit: 0 every term found, 1 at least one not found, 2 usage / connection / login / language not active.
"""
from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import re
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from docs_site import ARROW, emit, parse_po, read_text  # noqa: E402

PASSWORD_ENV = "ODOO_DOC_PASSWORD"
_SEPARATOR = re.compile(r"\s*(?:%s|-->|(?<=\s)>(?=\s))\s*" % ARROW)
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_GUILABEL = re.compile(r":guilabel:`([^`]+)`")
_MENUSELECTION = re.compile(r":menuselection:`([^`]+)`")
_HAS_SEPARATOR = re.compile(r"%s|-->|\s>\s" % ARROW)


class UiTermsError(Exception):
    pass


# --------------------------------------------------------------------------- extraction

def _clean(part):
    return re.sub(r"\s+", " ", part).strip()


def extract_terms(text):
    """[(term, kind, path)] from one msgstr; kind is "menu" or "guilabel", path the full menu path."""
    found = []
    for m in _BOLD.finditer(text):
        inner = m.group(1)
        if _HAS_SEPARATOR.search(inner):
            parts = [_clean(p) for p in _SEPARATOR.split(inner)]
            parts = [p for p in parts if p]
            path = " / ".join(parts)
            found.extend((p, "menu", path) for p in parts)
    for m in _MENUSELECTION.finditer(text):
        parts = [p for p in (_clean(x) for x in _SEPARATOR.split(m.group(1))) if p]
        path = " / ".join(parts)
        found.extend((p, "menu", path) for p in parts)
    for m in _GUILABEL.finditer(text):
        term = _clean(m.group(1))
        if term:
            found.append((term, "guilabel", None))
    return found


def terms_from_po(paths):
    """{term: {"term", "kinds": [...], "files": [...], "paths": [...]}} over the given .po files."""
    terms = {}
    for path in paths:
        text = read_text(path)
        if text is None:
            raise UiTermsError("po file not readable: %s" % path)
        for entry in parse_po(text):
            if entry["is_header"]:
                continue
            for item in entry["msgstrs"]:
                for term, kind, mpath in extract_terms(item["text"]):
                    row = terms.setdefault(term, {"term": term, "kinds": [], "files": [], "paths": []})
                    if kind not in row["kinds"]:
                        row["kinds"].append(kind)
                    ref = "%s:%d" % (os.path.basename(path), item["line"])
                    if ref not in row["files"]:
                        row["files"].append(ref)
                    if mpath and mpath not in row["paths"]:
                        row["paths"].append(mpath)
    return terms


# --------------------------------------------------------------------------- JSON-RPC

class Rpc(object):
    def __init__(self, base_url, timeout=60):
        self.base = base_url.rstrip("/")
        self.timeout = timeout
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.seq = 0

    def call(self, path, params):
        self.seq += 1
        body = json.dumps({"jsonrpc": "2.0", "method": "call", "params": params, "id": self.seq}).encode()
        req = urllib.request.Request(self.base + path, data=body,
                                     headers={"Content-Type": "application/json"})
        try:
            with self.opener.open(req, timeout=self.timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise UiTermsError("HTTP %s from %s" % (exc.code, path))
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise UiTermsError("cannot reach %s%s: %s" % (self.base, path, getattr(exc, "reason", exc)))
        if payload.get("error"):
            err = payload["error"]
            data = err.get("data") or {}
            raise UiTermsError("%s: %s" % (path, data.get("message") or err.get("message") or "error"))
        return payload.get("result")

    def authenticate(self, db, login, password):
        result = self.call("/web/session/authenticate", {"db": db, "login": login, "password": password})
        if not result or not result.get("uid"):
            raise UiTermsError("login refused for %r on database %r" % (login, db))

    def search_read(self, model, domain, fields, context):
        return self.call("/web/dataset/call_kw", {
            "model": model, "method": "search_read", "args": [domain],
            "kwargs": {"fields": fields, "context": context}}) or []


def fetch_catalog(rpc, lang):
    """The names the instance shows in `lang`: {"menu": [...], "menu_path": [...], "action": [...], "app": [...]}."""
    langs = rpc.search_read("res.lang", [["code", "=", lang]], ["code", "active"],
                            {"active_test": False})
    if not langs or not langs[0].get("active"):
        raise UiTermsError("language %s is not installed and active on this instance; load it first" % lang)
    ctx = {"lang": lang, "ir.ui.menu.full_list": True}
    menus = rpc.search_read("ir.ui.menu", [], ["name", "complete_name"], ctx)
    actions = rpc.search_read("ir.actions.act_window", [], ["name"], {"lang": lang})
    apps = rpc.search_read("ir.module.module", [["state", "=", "installed"], ["application", "=", True]],
                           ["shortdesc"], {"lang": lang})
    return {
        "ir.ui.menu.name": [m["name"] for m in menus if m.get("name")],
        "ir.ui.menu.complete_name": [m["complete_name"] for m in menus if m.get("complete_name")],
        "ir.actions.act_window.name": [a["name"] for a in actions if a.get("name")],
        "ir.module.module.shortdesc": [a["shortdesc"] for a in apps if a.get("shortdesc")],
    }


# --------------------------------------------------------------------------- matching

def match_terms(terms, catalog):
    """Result rows: each term found (exact, else case-insensitive) or not, with where it was found."""
    exact = {src: set(values) for src, values in catalog.items()}
    folded = {src: set(v.casefold() for v in values) for src, values in catalog.items()}
    paths_exact = exact.get("ir.ui.menu.complete_name", set())
    paths_folded = folded.get("ir.ui.menu.complete_name", set())
    rows = []
    for term in sorted(terms):
        row = dict(terms[term])
        hit_exact = sorted(src for src, values in exact.items()
                           if term in values and src != "ir.ui.menu.complete_name")
        hit_folded = sorted(src for src, values in folded.items()
                            if term.casefold() in values and src != "ir.ui.menu.complete_name")
        if hit_exact:
            row.update(found=True, match="exact", sources=hit_exact)
        elif hit_folded:
            row.update(found=True, match="case-insensitive", sources=hit_folded)
        else:
            row.update(found=False, match=None, sources=[])
        resolved = []
        for p in row["paths"]:
            ok = p in paths_exact or p.casefold() in paths_folded
            resolved.append({"path": p, "found": ok})
        row["path_resolution"] = resolved
        rows.append(row)
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description="Check translated UI terms against a live instance.")
    ap.add_argument("--url", required=True, help="http://localhost:PORT")
    ap.add_argument("--db", required=True)
    ap.add_argument("--login", required=True)
    ap.add_argument("--lang", required=True, help="Odoo language code, e.g. vi_VN")
    ap.add_argument("--po", action="append", required=True, help="a .po file; repeatable")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    password = os.environ.get(PASSWORD_ENV)
    if not password:
        sys.stderr.write("set %s in the environment (it is never taken as an argument)\n" % PASSWORD_ENV)
        return 2
    try:
        terms = terms_from_po(args.po)
        rpc = Rpc(args.url)
        rpc.authenticate(args.db, args.login, password)
        catalog = fetch_catalog(rpc, args.lang)
    except UiTermsError as exc:
        sys.stderr.write(str(exc).replace(password, "***") + "\n")
        return 2
    rows = match_terms(terms, catalog)
    missing = [r for r in rows if not r["found"]]
    report = {"ok": not missing, "lang": args.lang, "db": args.db, "po": args.po,
              "terms": rows, "found": len(rows) - len(missing), "not_found": len(missing)}
    lines = ["%d term(s): %d found, %d not found" % (len(rows), len(rows) - len(missing), len(missing))]
    for r in missing:
        lines.append("  NOT FOUND %r (%s) in %s" % (r["term"], "/".join(r["kinds"]), ", ".join(r["files"])))
    emit(report, args.json, lines)
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
