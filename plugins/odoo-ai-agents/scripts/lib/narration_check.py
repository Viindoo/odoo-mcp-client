#!/usr/bin/env python3
"""narration_check.py - does a narration clip say its script? Compare a transcript with the script.

Word error rate over NFC-normalised, case-folded tokens with punctuation removed and diacritics
KEPT (a tonal language changes meaning with the tone mark, so "ma" and "má" are different words
here), plus a slot check: every token listed in --slots (brand names, acronyms) must appear in the
transcript in some reading (the written form, or the spoken form of the pronunciation map when a
map is given). A transcript that cannot distinguish two readings of an acronym is reported, never
guessed.

Usage:
    python3 narration_check.py --script S.txt --transcript T.txt [--slots "Viindoo,AI"]
                               [--map MAP.json --lang vi_VN] [--max-wer 0.15]
Prints WER=<float> SLOTS_MISSING=<csv|none> VERDICT=<pass|fail|listen>; exit 0 pass, 1 fail,
3 listen (WER inside the bound but a slot is ambiguous - a human listens to the clip).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata

_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)


def tokens(text):
    text = unicodedata.normalize("NFC", text).casefold()
    return [t for t in _PUNCT.sub(" ", text).split() if t]


def wer(reference, hypothesis):
    r, h = tokens(reference), tokens(hypothesis)
    if not r:
        return 0.0 if not h else 1.0
    prev = list(range(len(h) + 1))
    for i, rt in enumerate(r, 1):
        cur = [i]
        for j, ht in enumerate(h, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (rt != ht)))
        prev = cur
    return prev[-1] / float(len(r))


def slot_status(slots, transcript, pron_entries):
    """missing, ambiguous: a slot is present when its written or spoken form appears."""
    text = " " + " ".join(tokens(transcript)) + " "
    spoken = {e["written"]: e["spoken"] for e in (pron_entries or []) if e.get("written")}

    def present(form):
        seq = " ".join(tokens(form))
        return bool(seq) and (" " + seq + " ") in text

    missing, ambiguous = [], []
    for slot in slots:
        spoken_hit = slot in spoken and present(spoken[slot])
        written_hit = present(slot)
        if spoken_hit or (written_hit and not slot.isupper()):
            continue
        if written_hit:
            # an acronym: the lowercase transcript token may be the acronym or an ordinary word
            # (vi "ai" = who), and an engine may have read it letter by letter - a human listens
            ambiguous.append(slot)
        else:
            missing.append(slot)
    return missing, ambiguous


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--script", required=True)
    parser.add_argument("--transcript", required=True)
    parser.add_argument("--slots", default="")
    parser.add_argument("--map")
    parser.add_argument("--lang")
    parser.add_argument("--max-wer", type=float, default=0.15)
    args = parser.parse_args(argv)
    with open(args.script, encoding="utf-8") as fh:
        script = fh.read()
    with open(args.transcript, encoding="utf-8") as fh:
        transcript = fh.read()
    pron = None
    if args.map and args.lang:
        with open(args.map, encoding="utf-8") as fh:
            pron = json.load(fh).get(args.lang)
    rate = wer(script, transcript)
    slots = [s.strip() for s in args.slots.split(",") if s.strip()]
    missing, ambiguous = slot_status(slots, transcript, pron)
    verdict = "pass"
    code = 0
    if rate > args.max_wer or missing:
        verdict, code = "fail", 1
    elif ambiguous:
        verdict, code = "listen", 3
    print("WER=%.3f" % rate)
    print("SLOTS_MISSING=%s" % (",".join(missing) or "none"))
    print("SLOTS_AMBIGUOUS=%s" % (",".join(ambiguous) or "none"))
    print("VERDICT=%s" % verdict)
    return code


if __name__ == "__main__":
    sys.exit(main())
