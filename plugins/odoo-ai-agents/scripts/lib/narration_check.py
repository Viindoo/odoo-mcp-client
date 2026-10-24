#!/usr/bin/env python3
"""narration_check.py - does a narration clip say its script? Compare a transcript with the script.

Word error rate over NFC-normalised, case-folded tokens with punctuation removed and diacritics
KEPT (a tonal language changes meaning with the tone mark, so "ma" and "má" are different words
here), plus a slot check: every token listed in --slots (brand names, acronyms) must appear in the
transcript in some reading (the written form, or the spoken form of the pronunciation map when a
map is given). A transcript that cannot distinguish two readings of an acronym is reported, never
guessed.

The script's shape is checked first, with or without a transcript: a speech engine pauses at every
line break as at a sentence end, so a sentence that continues on the next line is read as two
broken halves. A non-empty line that ends without sentence-final punctuation while text follows it
is reported as a broken line and fails the check; the author rewrites the script as one sentence
(or more) per line. A sentence longer than --max-words (15 by default: spoken text carries one
idea per 8-15 words) is reported as SENTENCES_LONG and fails the check too - a long descriptive
sentence is what makes a narration sound like storytelling.

Usage:
    python3 narration_check.py --script S.txt [--transcript T.txt] [--slots "Viindoo,AI"]
                               [--map MAP.json --lang vi_VN] [--max-wer 0.15]
Prints LINES_BROKEN=<csv of line numbers|none> and, with a transcript, WER=<float>
SLOTS_MISSING=<csv|none>; VERDICT=<pass|fail|listen>; exit 0 pass, 1 fail, 3 listen (WER inside
the bound but a slot is ambiguous - a human listens to the clip).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata

_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)


_SENTENCE_END = re.compile(r'[.!?\u2026:;]["\u201d\u2019)\]]*\s*$')


def broken_lines(text):
    """1-based numbers of the lines where a sentence runs on to the next line."""
    lines = text.splitlines()
    broken = []
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        follows = any(later.strip() for later in lines[i + 1:])
        if follows and not _SENTENCE_END.search(line):
            broken.append(i + 1)
    return broken


_SENTENCE_SPLIT = re.compile(r'(?<=[.!?\u2026])\s+')


def long_sentences(text, max_words=15):
    """[(line no, word count, sentence)] of sentences longer than max_words - spoken text carries one
    idea per 8-15 words; a longer sentence is read as prose and sounds like storytelling."""
    out = []
    for no, line in enumerate(text.splitlines(), 1):
        for sentence in _SENTENCE_SPLIT.split(line.strip()):
            n = len(tokens(sentence))
            if n > max_words:
                out.append((no, n, sentence.strip()))
    return out


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
    parser.add_argument("--transcript")
    parser.add_argument("--slots", default="")
    parser.add_argument("--map")
    parser.add_argument("--lang")
    parser.add_argument("--max-wer", type=float, default=0.15)
    parser.add_argument("--max-words", type=int, default=15,
                        help="longest spoken sentence; 0 disables the check")
    args = parser.parse_args(argv)
    with open(args.script, encoding="utf-8") as fh:
        script = fh.read()
    broken = broken_lines(script)
    print("LINES_BROKEN=%s" % (",".join(str(n) for n in broken) or "none"))
    longs = long_sentences(script, args.max_words) if args.max_words else []
    print("SENTENCES_LONG=%s" % (",".join("%d:%dw" % (no, n) for no, n, _s in longs) or "none"))
    for no, n, s in longs:
        print("LONG=%d %d words: %s" % (no, n, s[:80]))
    if args.transcript is None:
        bad = bool(broken or longs)
        print("VERDICT=%s" % ("fail" if bad else "pass"))
        return 1 if bad else 0
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
    if rate > args.max_wer or missing or broken or longs:
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
