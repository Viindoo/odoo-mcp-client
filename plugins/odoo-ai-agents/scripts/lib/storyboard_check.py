#!/usr/bin/env python3
"""storyboard_check.py - validate, render and compile the storyboard of a narrated demo video.

Subcommands (stdlib only; every result is KEY=VALUE on stdout, exit 1 on a refusal):
  check       --storyboard SB.json
              Validates the whole plan. One `ERROR=<path>: <message>` line per problem, then
              `ERRORS=<n>` (exit 1). A clean plan prints OK=1, SCENES, LANGUAGES (csv; empty for
              a silent video, which also prints SILENT=1), ACTIONS (action objects in the scenes'
              click paths) and TEXT_ONLY_SCENES (csv of scene ids whose click path holds no
              action object). `languages: []` is a silent video: no narration, title or publish
              text is required and `language_switch` is optional.
  render      --storyboard SB.json --out plan.md
              Markdown of the plan for the human gate: scenes, click paths, the language switch
              (labels and actions, `{lang}`/`{lang_label}` left as placeholders; `Language switch:
              none` when absent), the wait indicators (`the web client's own` when none are
              declared), narration per language, must-see spans, focus boxes, the AI block (the key variable NAME only),
              music and publish. Prints OUT.
  scene-script --storyboard SB.json --lang xx_YY --scene ID --base-url URL --out script.json
              [--voice-wav W] [--takes-dir D] [--ui-user NAME]
              The script the recorder consumes for one scene in one language: only the action
              objects, `voice_in` carrying the wav; `language_switch` is passed through with
              `{lang}` substituted (the recorder runs it once per take, off camera). For a silent
              storyboard --lang names the locale the UI is recorded in (any xx_YY). Refused when the
              scene has no action object or `voice_in` lacks --voice-wav. Prints OUT.
  set-prompt  --storyboard SB.json --scene ID --lang xx_YY --prompt TEXT
              Records the owner's pick as `prompt_chosen[lang]`; refused unless it is one of
              `prompts[lang]`. Rewrites the file (indent 2). Prints OK=1.
  demo-data-script --storyboard SB.json --base-url URL --out script.json [--ui-user NAME]
              The script that seeds the demo data (`demo_data` actions, no video). Refused when
              `demo_data` is absent or empty. Prints OUT.

`language_labels` {locale: label} gives the text the UI shows for a language (a select menu lists
labels, not codes); `language_switch` and `demo_data` actions may use `{lang_label}` as well as
`{lang}`, and `scene-script` substitutes both. `check` refuses `{lang_label}` for a listed language
without a label, and a label for a language that is not listed.
`text` of fill and `value` of select are a string or a {locale: string} map with one entry per
listed language; `scene-script --lang X` writes the string for X.

Action objects carry `do` and: goto {url}; click/hover {selector}; fill {selector, text,
delay_ms?}; press {key}; scroll {selector}|{y}; select {selector, value}; wait_for {selector,
state: visible|hidden|ai_wait, timeout_s?}|{network_idle: true} (timeout_s, a number > 0, overrides
the 30 s default wait of a selector; ai_wait keeps 120 s); hold {seconds}; voice_in {}; expect_text
{selector, name}. There is no set_language action: the recorder switches the language before every
take from `language_switch`. How the recorder reaches the instance is not part of the plan;
scene-script and demo-data-script take an optional --ui-user NAME, written as `ui_user`.
A scene sets `allow_key_fields: true` to let a take show a key field.
Optional top-level pacing key `wait_squeeze_s` (number >= 0, default 1.0 when absent): the seconds
the assembler squeezes the rest of every wait into. `render` lists it with the other tunables and
`scene-script` carries it into the scene script as `wait_squeeze_s`.
"""
from __future__ import annotations

import argparse
import json
import re
import sys

VIDEO_TYPES = ("tutorial", "marketing")
WAIT_STATES = ("visible", "hidden", "ai_wait")
KEY_SCOPES = ("dedicated", "shared")
LOCALE_RE = re.compile(r"^[a-z]{2,3}_[A-Z]{2}$")
VIEWPORT = [1920, 1080]
FPS = 25

ACTION_KEYS = {
    "goto": ("url",), "click": ("selector",), "fill": ("selector", "text"), "press": ("key",),
    "hover": ("selector",), "scroll": (), "select": ("selector", "value"), "wait_for": (),
    "hold": ("seconds",), "voice_in": (), "expect_text": ("selector", "name"),
}


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


class Checker:
    """Collects every problem of one storyboard as `<path>: <message>` strings."""

    def __init__(self, sb):
        self.sb = sb
        self.errors = []
        self.actions = 0

    def err(self, path, msg):
        self.errors.append("%s: %s" % (path, msg))

    def _locale_map(self, value, path, langs, required):
        if value is None:
            if required and langs:
                self.err(path, "missing")
            return
        if not isinstance(value, dict):
            self.err(path, "must be an object keyed by locale")
            return
        if required:
            for lang in langs:
                v = value.get(lang)
                if not isinstance(v, str) or not v.strip():
                    self.err("%s.%s" % (path, lang), "missing")
        for lang, v in value.items():
            if lang not in langs:
                self.err("%s.%s" % (path, lang), "language not in `languages`")
            elif not isinstance(v, str):
                self.err("%s.%s" % (path, lang), "must be a string")

    def action(self, a, path, scene=None):
        if not isinstance(a, dict) or not isinstance(a.get("do"), str):
            self.err(path, "an action object needs a `do` string")
            return
        kind = a["do"]
        if kind == "set_language":
            self.err(path, "set_language is not an action - the recorder switches the language "
                           "before every take from language_switch")
            return
        if kind not in ACTION_KEYS:
            self.err(path, "unknown action `%s`" % kind)
            return
        for key in ACTION_KEYS[kind]:
            if isinstance(a.get(key), dict) and key in ("text", "value") and kind in ("fill", "select"):
                self._by_locale(a[key], "%s.%s" % (path, key))
            elif a.get(key) in (None, ""):
                self.err("%s.%s" % (path, key), "missing")
        if kind == "hold" and "seconds" in a and not (_is_num(a["seconds"]) and a["seconds"] > 0):
            self.err(path + ".seconds", "must be a number > 0")
        if kind == "scroll" and not a.get("selector") and not _is_num(a.get("y")):
            self.err(path, "scroll needs `selector` or `y`")
        if kind == "wait_for" and a.get("network_idle") is not True:
            if not a.get("selector"):
                self.err(path, "wait_for needs `selector` and `state`, or `network_idle: true`")
            elif a.get("state") not in WAIT_STATES:
                self.err(path + ".state", "must be one of %s" % ", ".join(WAIT_STATES))
        if kind == "wait_for" and "timeout_s" in a and not (_is_num(a["timeout_s"]) and a["timeout_s"] > 0):
            self.err(path + ".timeout_s", "must be a number > 0")
        if kind == "voice_in" and scene is not None:
            self._voice_in(scene, path)

    def _by_locale(self, value, path):
        langs = [x for x in (self.sb.get("languages") or []) if isinstance(x, str)]
        for lang in langs:
            if not isinstance(value.get(lang), str) or not value[lang]:
                self.err("%s.%s" % (path, lang), "missing")
        for lang in value:
            if lang not in langs:
                self.err("%s.%s" % (path, lang), "language not in `languages`")

    def _labels(self, sb, langs):
        labels = sb.get("language_labels")
        if labels is not None and not (isinstance(labels, dict)
                                       and all(isinstance(v, str) and v for v in labels.values())):
            self.err("language_labels", "must be an object {locale: label}")
            labels = None
        for lang in labels or {}:
            if lang not in langs:
                self.err("language_labels.%s" % lang, "language not in `languages`")
        for key in ("language_switch", "demo_data"):
            if any("{lang_label}" in json.dumps(a) for a in sb.get(key) or []):
                for lang in langs:
                    if not (labels or {}).get(lang):
                        self.err("language_labels.%s" % lang, "needed by %s" % key)

    def _voice_in(self, scene, path):
        vi = scene.get("voice_input") or {}
        pr = scene.get("prompts") or {}
        for lang in self.sb.get("languages") or []:
            if not isinstance(vi.get(lang), str) or not vi[lang].strip():
                self.err(path, "`voice_in` needs voice_input.%s" % lang)
            if not (isinstance(pr.get(lang), list) and pr[lang]):
                self.err(path, "`voice_in` needs non-empty prompts.%s" % lang)

    def run(self):
        sb = self.sb
        if not isinstance(sb.get("title"), str) or not sb["title"].strip():
            self.err("title", "missing")
        if sb.get("video_type") not in VIDEO_TYPES:
            self.err("video_type", "must be one of %s" % ", ".join(VIDEO_TYPES))
        langs = sb.get("languages")
        if not isinstance(langs, list) or not all(isinstance(x, str) for x in langs):
            self.err("languages", "must be a list of locales (empty for a silent video)")
            langs = []
        for i, lang in enumerate(langs):
            if not LOCALE_RE.match(lang):
                self.err("languages[%d]" % i, "`%s` is not a locale like xx_YY" % lang)
        for key in ("lead_in_s", "fade_s", "max_silence_s", "max_hold_s", "wait_squeeze_s", "speed"):
            if key in sb and not (_is_num(sb[key]) and sb[key] >= 0):
                self.err(key, "must be a number >= 0")
        if "shot_seconds" in sb:
            s = sb["shot_seconds"]
            if not (isinstance(s, list) and len(s) == 2 and all(_is_num(x) for x in s) and 0 < s[0] <= s[1]):
                self.err("shot_seconds", "must be [lo, hi] with 0 < lo <= hi")
        self._misc(sb, langs)
        self._labels(sb, langs)
        if len(langs) > 1 and not sb.get("language_switch"):
            self.err("language_switch", "required when `languages` has more than one entry")
        for key in ("language_switch", "demo_data"):
            for i, a in enumerate(sb.get(key) or []):
                self.action(a, "%s[%d]" % (key, i))
        self._ai(sb.get("ai"))
        self._scenes(sb, langs)
        pub = sb.get("publish")
        if not isinstance(pub, dict):
            if langs or pub is not None:
                self.err("publish", "missing" if pub is None else "must be an object keyed by locale")
        else:
            for lang in langs:
                p = pub.get(lang)
                for key in ("title", "description"):
                    if not isinstance(p, dict) or not isinstance(p.get(key), str) or not p[key].strip():
                        self.err("publish.%s.%s" % (lang, key), "missing")
        return self.errors

    def _misc(self, sb, langs):
        pron = sb.get("pronunciation")
        if pron is not None:
            if not isinstance(pron, dict):
                self.err("pronunciation", "must be an object keyed by locale")
            else:
                for lang, rows in pron.items():
                    if lang not in langs:
                        self.err("pronunciation.%s" % lang, "language not in `languages`")
                    for i, r in enumerate(rows if isinstance(rows, list) else []):
                        for key in ("written", "spoken"):
                            if not isinstance(r, dict) or not isinstance(r.get(key), str):
                                self.err("pronunciation.%s[%d].%s" % (lang, i, key), "missing")
        self._locale_map(sb.get("voice"), "voice", langs, False)
        music = sb.get("music")
        if music is not None:
            if not isinstance(music, dict) or not isinstance(music.get("on"), bool):
                self.err("music.on", "must be true or false")
            elif music["on"]:
                for key in ("file", "license"):
                    if not isinstance(music.get(key), str) or not music[key].strip():
                        self.err("music.%s" % key, "missing while music is on")
        self._selectors(sb.get("wait_selectors"), "wait_selectors")

    def _selectors(self, value, path):
        if value is not None and not (isinstance(value, list) and all(isinstance(x, str) and x for x in value)):
            self.err(path, "must be a list of CSS selectors")

    def _ai(self, ai):
        if ai is None:
            return
        if not isinstance(ai, dict):
            self.err("ai", "must be an object")
            return
        for key in ("requests_per_scene", "tokens_per_request", "takes", "trials_k"):
            if key in ai and not (isinstance(ai[key], int) and not isinstance(ai[key], bool) and ai[key] >= 0):
                self.err("ai.%s" % key, "must be a whole number >= 0")
        scope = ai.get("key_scope")
        if scope == "shared":
            self.err("ai.key_scope", "a shared key never drives a demo")
        elif scope not in KEY_SCOPES:
            self.err("ai.key_scope", "must be one of %s" % ", ".join(KEY_SCOPES))
        if not isinstance(ai.get("key_env"), str) or not ai["key_env"].strip():
            self.err("ai.key_env", "missing")

    def _scenes(self, sb, langs):
        scenes = sb.get("scenes")
        if not isinstance(scenes, list) or not scenes:
            self.err("scenes", "must be a non-empty list")
            return
        seen = set()
        for i, sc in enumerate(scenes):
            p = "scenes[%d]" % i
            if not isinstance(sc, dict):
                self.err(p, "must be an object")
                continue
            sid = sc.get("id")
            if not isinstance(sid, str) or not sid:
                self.err(p + ".id", "missing")
            elif sid in seen:
                self.err(p + ".id", "duplicate id `%s`" % sid)
            seen.add(sid)
            self._locale_map(sc.get("title"), p + ".title", langs, True)
            self._locale_map(sc.get("narration"), p + ".narration", langs, True)
            ts = sc.get("target_seconds")
            if not (_is_num(ts) and ts > 0):
                self.err(p + ".target_seconds", "must be a number > 0")
            cp = sc.get("click_path")
            if not isinstance(cp, list) or not cp:
                self.err(p + ".click_path", "must be a non-empty list")
                cp = []
            for j, item in enumerate(cp):
                if isinstance(item, str):
                    continue
                self.actions += 1
                self.action(item, "%s.click_path[%d]" % (p, j), sc)
            self._scene_extras(sc, p, langs, ts)

    def _scene_extras(self, sc, p, langs, ts):
        self._locale_map(sc.get("voice_input"), p + ".voice_input", langs, False)
        prompts = sc.get("prompts")
        if prompts is not None:
            if not isinstance(prompts, dict):
                self.err(p + ".prompts", "must be an object keyed by locale")
                prompts = {}
            for lang, lst in prompts.items():
                if lang not in langs:
                    self.err("%s.prompts.%s" % (p, lang), "language not in `languages`")
                if not (isinstance(lst, list) and all(isinstance(x, str) for x in lst)):
                    self.err("%s.prompts.%s" % (p, lang), "must be a list of strings")
        chosen = sc.get("prompt_chosen")
        if chosen is not None:
            if not isinstance(chosen, dict):
                self.err(p + ".prompt_chosen", "must be an object keyed by locale")
            else:
                for lang, v in chosen.items():
                    options = (prompts or {}).get(lang)
                    if not isinstance(options, list) or v not in options:
                        self.err("%s.prompt_chosen.%s" % (p, lang), "not one of prompts.%s" % lang)
        for j, span in enumerate(sc.get("must_see") or []):
            ok = (isinstance(span, list) and len(span) == 2 and all(_is_num(x) for x in span)
                  and span[0] < span[1])
            if not ok:
                self.err("%s.must_see[%d]" % (p, j), "must be [start_s, end_s] with start < end")
            elif _is_num(ts) and (span[0] < 0 or span[1] > ts):
                self.err("%s.must_see[%d]" % (p, j), "outside [0, target_seconds=%s]" % ts)
        for j, f in enumerate(sc.get("focus") or []):
            box = f.get("box") if isinstance(f, dict) else None
            if not (isinstance(box, list) and len(box) == 4 and all(_is_num(x) for x in box)):
                self.err("%s.focus[%d].box" % (p, j), "must be [x, y, w, h]")
            elif not (_is_num(f.get("from_s")) and _is_num(f.get("to_s")) and f["from_s"] < f["to_s"]):
                self.err("%s.focus[%d]" % (p, j), "needs from_s < to_s")
        self._selectors(sc.get("wait_selectors"), p + ".wait_selectors")
        if "allow_key_fields" in sc and not isinstance(sc["allow_key_fields"], bool):
            self.err(p + ".allow_key_fields", "must be true or false")


def _die(msg):
    print("ERROR=%s" % msg)
    sys.exit(1)


def _load(path):
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        _die("%s: cannot read storyboard (%s)" % (path, exc))
    if not isinstance(data, dict):
        _die("%s: storyboard must be a JSON object" % path)
    return data


def _write_json(path, data):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def _find_scene(sb, sid):
    for sc in sb.get("scenes") or []:
        if isinstance(sc, dict) and sc.get("id") == sid:
            return sc
    _die("scene `%s` not found" % sid)


def _require_valid(sb):
    errors = Checker(sb).run()
    if errors:
        for e in errors:
            print("ERROR=" + e)
        print("ERRORS=%d" % len(errors))
        sys.exit(1)


def cmd_check(args):
    sb = _load(args.storyboard)
    chk = Checker(sb)
    errors = chk.run()
    for e in errors:
        print("ERROR=" + e)
    if errors:
        print("ERRORS=%d" % len(errors))
        return 1
    scenes = sb["scenes"]
    text_only = [s["id"] for s in scenes if not any(isinstance(i, dict) for i in s["click_path"])]
    print("OK=1")
    print("SCENES=%d" % len(scenes))
    print("LANGUAGES=%s" % ",".join(sb["languages"]))
    if not sb["languages"]:
        print("SILENT=1")
    print("ACTIONS=%d" % chk.actions)
    print("TEXT_ONLY_SCENES=%s" % ",".join(text_only))
    return 0


def _action_line(a):
    parts = [str(a.get("do", "?"))]
    for key in ("url", "selector"):
        if key in a:
            parts.append(str(a[key]))
    if "y" in a:
        parts.append("y=%s" % a["y"])
    for key in ("text", "value"):
        if key in a:
            parts.append('"%s"' % a[key])
    for key in ("key", "name", "state"):
        if key in a:
            parts.append(str(a[key]))
    if "seconds" in a:
        parts.append("%ss" % a["seconds"])
    if a.get("network_idle"):
        parts.append("network idle")
    return " ".join(parts)


def _cell(text):
    return str(text).replace("|", "\\|").replace("\n", " ")


def _squeeze(sb):
    """The seconds the assembler squeezes the rest of every wait into (default 1.0)."""
    return sb["wait_squeeze_s"] if "wait_squeeze_s" in sb else 1.0


def cmd_render(args):
    sb = _load(args.storyboard)
    langs = sb.get("languages") or []
    out = ["# %s" % sb.get("title", ""), "",
           "- Type: %s" % sb.get("video_type", ""),
           "- Languages: %s" % (", ".join(langs) if langs else "Silent video (no narration)"),
           "- wait_squeeze_s: %s" % _squeeze(sb),
           "", "## Scenes", "",
           "| Scene | Target (s) | Click path |", "|---|---|---|"]
    scenes = [s for s in sb.get("scenes") or [] if isinstance(s, dict)]
    for sc in scenes:
        steps = [i if isinstance(i, str) else _action_line(i) for i in sc.get("click_path") or []]
        out.append("| %s | %s | %s |" % (_cell(sc.get("id", "")), sc.get("target_seconds", ""),
                                          _cell("; ".join(steps))))
    switch = sb.get("language_switch") or []
    if switch:
        out += ["", "## Language switch", ""]
        out += ["- label %s: %s" % (k, v) for k, v in (sb.get("language_labels") or {}).items()]
        out += ["- " + _action_line(a) for a in switch if isinstance(a, dict)]
    else:
        out += ["", "Language switch: none"]
    waits = list(sb.get("wait_selectors") or [])
    for sc in scenes:
        waits += [w for w in sc.get("wait_selectors") or [] if w not in waits]
    out += ["", "Wait indicators: %s" % (", ".join(waits) if waits else "the web client's own")]
    for sc in scenes:
        out += ["", "### %s" % sc.get("id", "")]
        for lang in langs:
            title = (sc.get("title") or {}).get(lang, "")
            out += ["", "**%s** %s" % (lang, title), ""]
            out += ["> " + ln for ln in str((sc.get("narration") or {}).get(lang, "")).splitlines() or [""]]
        if sc.get("must_see"):
            out += ["", "Must see: " + ", ".join("%s-%ss" % (a, b) for a, b in sc["must_see"])]
        for f in sc.get("focus") or []:
            out.append("Focus box %s from %ss to %ss" % (f.get("box"), f.get("from_s"), f.get("to_s")))
    ai = sb.get("ai")
    if ai:
        out += ["", "## AI", ""]
        for key in ("requests_per_scene", "tokens_per_request", "takes", "trials_k", "key_scope"):
            if key in ai:
                out.append("- %s: %s" % (key, ai[key]))
        out.append("- key variable: %s" % ai.get("key_env", ""))
        if ai.get("quota_note"):
            out.append("- quota: %s" % ai["quota_note"])
    music = sb.get("music")
    if music:
        out += ["", "## Music", "", "- on: %s" % music.get("on")]
        for key in ("file", "license", "gain_db"):
            if key in music:
                out.append("- %s: %s" % (key, music[key]))
    out += ["", "## Publish", "", "- profile: %s" % sb.get("publish_profile", "youtube-1080p")]
    for lang, p in (sb.get("publish") or {}).items():
        out += ["", "**%s** %s" % (lang, (p or {}).get("title", "")), "", (p or {}).get("description", "")]
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")
    print("OUT=%s" % args.out)
    return 0


def _subst(value, lang, label=""):
    if isinstance(value, str):
        return value.replace("{lang}", lang).replace("{lang_label}", label)
    if isinstance(value, list):
        return [_subst(v, lang, label) for v in value]
    if isinstance(value, dict):
        return {k: _subst(v, lang, label) for k, v in value.items()}
    return value


def _label(sb, lang):
    return (sb.get("language_labels") or {}).get(lang, "")


def _resolve(value, lang):
    """An action with a {locale: string} `text`/`value` becomes the string for `lang`."""
    out = dict(value)
    for key in ("text", "value"):
        if out.get("do") in ("fill", "select") and isinstance(out.get(key), dict):
            out[key] = out[key].get(lang, "")
    return out


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-") or "video"


def _base_script(sb, lang, base_url, ui_user):
    return {
        "label": _slug(sb.get("title", "")),
        "lang": lang,
        "base_url": base_url,
        "viewport": list(VIEWPORT),
        "fps": FPS,
        "ui_user": ui_user or None,
        "language_switch": _subst(sb.get("language_switch") or [], lang, _label(sb, lang)),
    }


def cmd_scene_script(args):
    sb = _load(args.storyboard)
    _require_valid(sb)
    if sb["languages"]:
        if args.lang not in sb["languages"]:
            _die("language `%s` not in `languages`" % args.lang)
    elif not LOCALE_RE.match(args.lang):
        _die("--lang `%s` is not a locale like xx_YY" % args.lang)
    sc = _find_scene(sb, args.scene)
    if not any(isinstance(i, dict) for i in sc["click_path"]):
        _die("scene `%s` has no action object (text-only scene: nothing to record)" % args.scene)
    script = _base_script(sb, args.lang, args.base_url, args.ui_user)
    actions = []
    for item in sc["click_path"]:
        if not isinstance(item, dict):
            continue
        if item["do"] == "voice_in":
            if not args.voice_wav:
                _die("scene `%s` has `voice_in` and no --voice-wav" % args.scene)
            actions.append(dict(item, wav=args.voice_wav))
        else:
            actions.append(_resolve(item, args.lang))
    script.update({
        "scene_id": sc["id"],
        "wait_squeeze_s": _squeeze(sb),
        "wait_selectors": list(sb.get("wait_selectors") or []) + list(sc.get("wait_selectors") or []),
        "actions": actions,
        "voice_wav": args.voice_wav or None,
        "allow_key_fields": bool(sc.get("allow_key_fields", False)),
        "must_see": sc.get("must_see") or [],
        "out_dir": args.takes_dir or ".",
        "clip_name": "scene-%s" % sc["id"],
    })
    _write_json(args.out, script)
    print("OUT=%s" % args.out)
    return 0


def cmd_set_prompt(args):
    sb = _load(args.storyboard)
    sc = _find_scene(sb, args.scene)
    options = (sc.get("prompts") or {}).get(args.lang)
    if not isinstance(options, list) or args.prompt not in options:
        _die("prompt is not one of scenes[%s].prompts.%s" % (args.scene, args.lang))
    sc.setdefault("prompt_chosen", {})[args.lang] = args.prompt
    _write_json(args.storyboard, sb)
    print("OK=1")
    return 0


def cmd_demo_data(args):
    sb = _load(args.storyboard)
    _require_valid(sb)
    data = sb.get("demo_data")
    if not data:
        _die("`demo_data` is absent or empty")
    lang = (sb["languages"] or ["en_US"])[0]
    script = _base_script(sb, lang, args.base_url, args.ui_user)
    script.update({
        "scene_id": None,
        "wait_selectors": list(sb.get("wait_selectors") or []),
        "actions": [_resolve(a, lang) for a in _subst(data, lang, _label(sb, lang))],
        "voice_wav": None,
        "allow_key_fields": False,
        "must_see": [],
        "out_dir": ".",
        "clip_name": "prepare",
    })
    _write_json(args.out, script)
    print("OUT=%s" % args.out)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, fn, *opts):
        p = sub.add_parser(name)
        p.add_argument("--storyboard", required=True)
        for opt, required in opts:
            p.add_argument(opt, required=required)
        p.set_defaults(fn=fn)

    add("check", cmd_check)
    add("render", cmd_render, ("--out", True))
    add("scene-script", cmd_scene_script, ("--lang", True), ("--scene", True), ("--base-url", True),
        ("--out", True), ("--voice-wav", False), ("--takes-dir", False), ("--ui-user", False))
    add("set-prompt", cmd_set_prompt, ("--scene", True), ("--lang", True), ("--prompt", True))
    add("demo-data-script", cmd_demo_data, ("--base-url", True), ("--out", True), ("--ui-user", False))
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
