#!/usr/bin/env python3
"""pronunciation.py - apply a per-language pronunciation map to narration text, for TTS only.

A map is a list of entries `{"written": "AI", "spoken": "ây ai", "kind": "respell"}` (kind
`respell`, the default, works with every engine; kind `phoneme` carries engine markup and is
applied only when the caller says the engine supports it). Matching is case-sensitive on whole
tokens with Unicode-aware boundaries: `AI -> ây ai` rewrites `AI`, `AI,`, `AI.`, `(AI)` and the
`AI` of `AI-first`, and leaves `ai`, `Ai`, `mai`, `AIRPORT` and `AI_x` alone. All-capital text
cannot be disambiguated and is left as it is. Captions, title cards and descriptions always keep
the written form - only the text sent to the speech endpoint goes through this map.

Usage:
    python3 pronunciation.py apply --map MAP.json --lang vi_VN [--phonemes] < text
    python3 pronunciation.py selfcheck --map MAP.json          # exit 1 on a wrong substitution

MAP.json: {"vi_VN": [{"written": ..., "spoken": ..., "kind": ...}, ...], "en_US": [...]} with
optional `"_selfcheck": {"vi_VN": [{"in": ..., "out": ...}, ...]}` sample sentences.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata

_WORD = re.compile(r"\w", re.UNICODE)


def _is_word(ch):
    return bool(ch) and bool(_WORD.match(ch))


def _all_caps(text):
    letters = [c for c in text if c.isalpha()]
    return len(letters) >= 12 and all(c.isupper() for c in letters)


def apply_map(text, entries, phonemes=False):
    """Return the text with every whole-token `written` replaced by `spoken`."""
    if not entries or _all_caps(text):
        return text
    out = text
    for entry in sorted(entries, key=lambda e: -len(e.get("written", ""))):
        written, spoken = entry.get("written", ""), entry.get("spoken", "")
        kind = entry.get("kind", "respell")
        if not written or not spoken or (kind == "phoneme" and not phonemes):
            continue
        result, i, n = [], 0, len(written)
        while True:
            j = out.find(written, i)
            if j < 0:
                result.append(out[i:])
                break
            before = out[j - 1] if j > 0 else ""
            after = out[j + n] if j + n < len(out) else ""
            # a boundary is a non-word character; a hyphen counts as a boundary (AI-first)
            if (not _is_word(before)) and (not _is_word(after)):
                result.append(out[i:j])
                result.append(spoken)
            else:
                result.append(out[i:j + n])
            i = j + n
        out = "".join(result)
    return unicodedata.normalize("NFC", out)


def selfcheck(spec):
    failures = []
    for lang, samples in (spec.get("_selfcheck") or {}).items():
        entries = spec.get(lang) or []
        for sample in samples:
            got = apply_map(sample["in"], entries)
            if got != sample["out"]:
                failures.append("%s: %r -> %r, expected %r" % (lang, sample["in"], got, sample["out"]))
    return failures


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("apply")
    p.add_argument("--map", required=True)
    p.add_argument("--lang", required=True)
    p.add_argument("--phonemes", action="store_true")
    p = sub.add_parser("selfcheck")
    p.add_argument("--map", required=True)
    args = parser.parse_args(argv)
    with open(args.map, encoding="utf-8") as fh:
        spec = json.load(fh)
    if args.cmd == "apply":
        sys.stdout.write(apply_map(sys.stdin.read(), spec.get(args.lang) or [], args.phonemes))
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
