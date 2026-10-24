#!/usr/bin/env python3
"""pronunciation.py - how a speech engine is made to say brands, vendors, models and acronyms.

Two layers, one rule: the REGISTRY (machine-global `<state root>/pronunciation.json`, recorded once
by `/odoo-ai-agents:odoo-setup voice` and confirmed by a human by ear) holds the terms every
narration must say the same way - the vendor's own brand, every AI vendor and model name the
products show (pronounced the ENGLISH way in every narration language), common acronyms. A
storyboard MAP may ADD terms for one video but never overrides a registered one (`merge`).

An entry is `{"written": "AI", "spoken": "ây ai", "kind": "respell"}` (kind `respell`, the
default, works with every engine; kind `phoneme` carries engine markup such as inline IPA and is
applied only when the caller says the engine accepts it). Matching is case-sensitive on whole
tokens with Unicode-aware boundaries: `AI -> ây ai` rewrites `AI`, `AI,`, `AI.`, `(AI)` and the
`AI` of `AI-first`, and leaves `ai`, `Ai`, `mai`, `AIRPORT` and `AI_x` alone. All-capital text
cannot be disambiguated and is left as it is. Two mapped terms that follow each other directly
("Viindoo AI") get a short pause between them (a comma, which every engine honours), so they
never merge into one word. Captions, title cards and descriptions always keep the written form -
only the text sent to the speech endpoint goes through this map.

Usage:
    python3 pronunciation.py apply --map MAP.json --lang vi_VN [--phonemes] [--no-registry] < text
    python3 pronunciation.py selfcheck --map MAP.json          # exit 1 on a wrong substitution
    python3 pronunciation.py merge --map MAP.json              # the registry + the map, as one map (JSON)
    python3 pronunciation.py registry list [--lang vi_VN]
    python3 pronunciation.py registry add --lang vi_VN --written Viindoo --spoken "Vinn đu"
                                          [--kind respell|phoneme] [--group brand|vendor|model|acronym]
                                          [--confirmed]
    python3 pronunciation.py registry confirm --lang vi_VN --written Viindoo
    python3 pronunciation.py registry remove --lang vi_VN --written Viindoo
    python3 pronunciation.py registry missing --map MAP.json --lang vi_VN --text FILE
        # terms of the text that look like proper nouns or acronyms and have no entry anywhere

MAP.json: {"vi_VN": [{"written": ..., "spoken": ..., "kind": ...}, ...], "en_US": [...]} with
optional `"_selfcheck": {"vi_VN": [{"in": ..., "out": ...}, ...]}` sample sentences.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata

_LIB_DIR = os.path.dirname(os.path.abspath(__file__))
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

REGISTRY_FILE = "pronunciation.json"
GROUPS = ("brand", "vendor", "model", "acronym", "other")
PAUSE = ", "          # the engine-neutral break between two mapped terms that touch
_WORD = re.compile(r"\w", re.UNICODE)
_ACRONYM = re.compile(r"\b[A-Z][A-Z0-9]{1,7}\b")
_PROPER = re.compile(r"\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b|\b[A-Z][a-z]{2,}\b")
_COMMON_START = {"The", "This", "That", "When", "Then", "Click", "Open", "Select", "Save", "Create", "Here",
                 "Now", "You", "It", "In", "On", "At", "To", "For", "And", "Or", "If", "Your", "Our", "We"}


def registry_path():
    import paths
    return os.path.join(paths.state_root(), REGISTRY_FILE)


def _all_caps(text):
    letters = [c for c in text if c.isalpha()]
    return len(letters) >= 12 and all(c.isupper() for c in letters)


def _entries(entries, phonemes):
    out = {}
    for entry in entries or []:
        written, spoken = entry.get("written", ""), entry.get("spoken", "")
        kind = entry.get("kind", "respell")
        if not written or not spoken or (kind == "phoneme" and not phonemes):
            continue
        out.setdefault(written, spoken)   # the first occurrence wins (the registry comes first)
    return out


def apply_map(text, entries, phonemes=False, pause=PAUSE):
    """Return the text with every whole-token `written` replaced by `spoken`; two replaced terms
    separated only by whitespace get `pause` between them."""
    table = _entries(entries, phonemes)
    if not table or _all_caps(text):
        return text
    alternation = "|".join(re.escape(w) for w in sorted(table, key=len, reverse=True))
    pattern = re.compile(r"(?<!\w)(?:%s)(?!\w)" % alternation, re.UNICODE)
    out, last_end, prev_replaced_end = [], 0, None
    for m in pattern.finditer(text):
        gap = text[last_end:m.start()]
        if prev_replaced_end == last_end and gap and gap.isspace():
            gap = pause
        out.append(gap)
        out.append(table[m.group(0)])
        last_end = m.end()
        prev_replaced_end = last_end
    out.append(text[last_end:])
    return unicodedata.normalize("NFC", "".join(out))


def selfcheck(spec):
    failures = []
    for lang, samples in (spec.get("_selfcheck") or {}).items():
        entries = spec.get(lang) or []
        for sample in samples:
            got = apply_map(sample["in"], entries)
            if got != sample["out"]:
                failures.append("%s: %r -> %r, expected %r" % (lang, sample["in"], got, sample["out"]))
    return failures


# ----------------------------------------------------------------------------- registry
def load_registry(path=None):
    path = path or registry_path()
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return {}
    return data if isinstance(data, dict) else {}


def save_registry(data, path=None):
    import config_merge
    path = path or registry_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with config_merge.locked_target(path):
        config_merge._atomic_replace(path, json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
    return path


def merge(spec, registry=None):
    """One map per language: registry entries first (they win), then the map's additions.
    `_selfcheck` samples of the map are kept."""
    registry = load_registry() if registry is None else registry
    out = {}
    langs = set(k for k in registry if not k.startswith("_")) | set(k for k in (spec or {}) if not k.startswith("_"))
    for lang in sorted(langs):
        reg = [dict(e) for e in registry.get(lang) or []]
        known = set(e.get("written") for e in reg)
        extra = [dict(e) for e in (spec or {}).get(lang) or [] if e.get("written") not in known]
        out[lang] = reg + extra
    if spec and spec.get("_selfcheck"):
        out["_selfcheck"] = spec["_selfcheck"]
    return out


def missing_terms(text, entries):
    """Capitalised words, CamelCase names and acronyms of the text with no entry: candidates for
    the registry, never a verdict (a human decides)."""
    known = set(e.get("written") for e in entries or [])
    found = []
    for m in list(_ACRONYM.finditer(text)) + list(_PROPER.finditer(text)):
        word = m.group(0)
        if word in known or word in _COMMON_START or word in found:
            continue
        # a sentence-initial common word is not a name: keep only words that also appear mid-sentence
        # or are acronyms / CamelCase
        if _ACRONYM.match(word) or any(c.isupper() for c in word[1:]) or re.search(r"[^.!?]\s+%s\b" % re.escape(word), text):
            found.append(word)
    return found


def _registry_cmd(args):
    data = load_registry(args.file)
    if args.rcmd == "list":
        langs = [args.lang] if args.lang else sorted(k for k in data if not k.startswith("_"))
        for lang in langs:
            for e in data.get(lang) or []:
                print("%s\t%s\t%s\t%s\t%s\t%s" % (lang, e.get("written"), e.get("spoken"), e.get("kind", "respell"),
                                                 e.get("group", "other"), "confirmed" if e.get("confirmed") else "unconfirmed"))
        return 0
    if args.rcmd == "add":
        if args.group not in GROUPS:
            print("x --group: one of %s" % " | ".join(GROUPS), file=sys.stderr)
            return 2
        entries = [e for e in data.get(args.lang) or [] if e.get("written") != args.written]
        entries.append({"written": args.written, "spoken": args.spoken, "kind": args.kind, "group": args.group,
                        "confirmed": bool(args.confirmed)})
        data[args.lang] = entries
        print("ok wrote %s (%s: %s -> %s, %s)" % (save_registry(data, args.file), args.lang, args.written, args.spoken,
                                                 "confirmed" if args.confirmed else "unconfirmed - confirm by ear"))
        return 0
    if args.rcmd == "confirm":
        hit = [e for e in data.get(args.lang) or [] if e.get("written") == args.written]
        if not hit:
            print("x no entry %s/%s" % (args.lang, args.written), file=sys.stderr)
            return 1
        hit[0]["confirmed"] = True
        save_registry(data, args.file)
        print("ok confirmed %s/%s" % (args.lang, args.written))
        return 0
    if args.rcmd == "remove":
        before = len(data.get(args.lang) or [])
        data[args.lang] = [e for e in data.get(args.lang) or [] if e.get("written") != args.written]
        if len(data[args.lang]) == before:
            print("x no entry %s/%s" % (args.lang, args.written), file=sys.stderr)
            return 1
        save_registry(data, args.file)
        print("ok removed %s/%s" % (args.lang, args.written))
        return 0
    if args.rcmd == "missing":
        spec = {}
        if args.map:
            with open(args.map, encoding="utf-8") as fh:
                spec = json.load(fh)
        with open(args.text, encoding="utf-8") as fh:
            text = fh.read()
        merged = merge(spec, data)
        for word in missing_terms(text, merged.get(args.lang) or []):
            print("MISSING=%s" % word)
        return 0
    return 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("apply")
    p.add_argument("--map", required=True)
    p.add_argument("--lang", required=True)
    p.add_argument("--phonemes", action="store_true")
    p.add_argument("--no-registry", action="store_true", dest="no_registry")
    p = sub.add_parser("selfcheck")
    p.add_argument("--map", required=True)
    p = sub.add_parser("merge")
    p.add_argument("--map", required=True)
    p.add_argument("--registry-file", dest="file")
    r = sub.add_parser("registry")
    rs = r.add_subparsers(dest="rcmd", required=True)
    for name in ("list", "add", "confirm", "remove", "missing"):
        q = rs.add_parser(name)
        q.add_argument("--lang", required=name != "list")
        q.add_argument("--registry-file", dest="file")
        if name in ("add", "confirm", "remove"):
            q.add_argument("--written", required=True)
        if name == "add":
            q.add_argument("--spoken", required=True)
            q.add_argument("--kind", default="respell", choices=("respell", "phoneme"))
            q.add_argument("--group", default="other")
            q.add_argument("--confirmed", action="store_true")
        if name == "missing":
            q.add_argument("--map")
            q.add_argument("--text", required=True)
    args = parser.parse_args(argv)
    if args.cmd == "registry":
        return _registry_cmd(args)
    with open(args.map, encoding="utf-8") as fh:
        spec = json.load(fh)
    if args.cmd == "merge":
        print(json.dumps(merge(spec, load_registry(args.file)), ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "apply":
        entries = (spec if args.no_registry else merge(spec)).get(args.lang) or []
        sys.stdout.write(apply_map(sys.stdin.read(), entries, args.phonemes))
        return 0
    failures = selfcheck(spec)
    for f in failures:
        print("x " + f, file=sys.stderr)
    if failures:
        return 1
    print("ok pronunciation map: %d language(s) checked" % len(spec.get("_selfcheck") or {}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
