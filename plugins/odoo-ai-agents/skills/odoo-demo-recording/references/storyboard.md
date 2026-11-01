# Storyboard - the plan of a narrated demo video

`storyboard.json` under `<ISOLATE_DIR>/video/<label>/`; validated by
`${CLAUDE_PLUGIN_ROOT}/scripts/lib/storyboard_check.py check` (its docstring is the CLI
reference). Every tunable lives here; nothing is hardcoded later.

## Top level

| Key | Value |
|---|---|
| `title`, `video_type` | the video's title; `tutorial` or `marketing` |
| `languages` | locales `xx_YY`, one recording each with the UI in that language; empty = a silent video, one recording in the instance's locale, no narration |
| `lead_in_s`, `fade_s`, `max_silence_s`, `max_hold_s`, `shot_seconds` | 0.5, 0.3, 3.0, 3.0, `[lo, hi]` (marketing 2-4, tutorial 3-8) |
| `publish_profile` | `youtube-1080p` |
| `pronunciation` | `{lang: [{written, spoken, kind}]}` - adds to the machine registry, never overrides it |
| `voice` | `{locale: voice id}` - the audition's pick, else the voice the speech configuration names for the locale |
| `speed` | one rate for the whole video: the video type's rate when the probe said the engine honours it, else 1.0 |
| `wait_squeeze_s` | seconds the assembler squeezes the rest of every wait into after its first second (1.0); raise it when a scene's narration outruns its footage, instead of re-recording |
| `music` | `{on, file, license, gain_db}`; marketing on, tutorial off unless asked; file and licence from the author profile |
| `wait_selectors` | selectors of wait indicators beside the web client's own |
| `language_switch` | actions that switch the UI language, with `{lang}` where the locale goes and `{lang_label}` where the UI shows a language by name; the recorder runs them as `ui_user` before every take, off camera; required for more than one language |
| `language_labels` | `{locale: label}` - the name the UI shows for each language; required by `{lang_label}` |
| `demo_data` | actions that seed the scratch database through the UI: fictitious names, noise archived, rankings without ties |
| `ai` | `{requests_per_scene, tokens_per_request, takes, trials_k, key_env, key_scope, quota_note}` - present only for a scene that calls an AI; `key_scope: shared` is refused |
| `scenes`, `publish` | below; `{lang: {title, description}}` |

## Scene

| Key | Value |
|---|---|
| `id`, `title` | unique id; `{lang: text}` |
| `click_path` | action objects (below); a human string beside them is a note, a scene with no action is not recordable |
| `target_seconds` | the shot's length |
| `narration` | `{lang: spoken text}` - 8-15 words per sentence, one sentence per line; absent on a silent storyboard |
| `voice_input` | `{lang: text}` the fake microphone speaks (a `voice_in` action needs it for every language) |
| `prompts`, `prompt_chosen` | `{lang: [candidates]}`; the pick after the trials, one of the candidates |
| `focus` | `[{box: [x, y, w, h], from_s, to_s}]` - the area the assembler punches in on |
| `must_see` | `[[start_s, end_s]]` inside the target - never compressed |
| `allow_key_fields` | `false`: a take that shows a key field is refused |

## Actions (`do`)

Selectors are Playwright selectors (CSS, `text=`, `>>` chains). `goto {url}` · `click {selector}` ·
`fill {selector, text, delay_ms}` · `press {key}` · `hover {selector}` · `scroll {selector | y}` ·
`select {selector, value}` (a native `<select>` only; `text` and `value` are a string or a
`{locale: string}` map - a record's name is translated in a translated UI, and a name the UI does
not find makes the first autocomplete entry the quick-create, so the take saves a new record
instead of the demo one) · `wait_for {selector, state: visible | hidden |
ai_wait, timeout_s}` or `{network_idle: true}` (`ai_wait` = an indicator shows, then hides and the
network is idle; a selector wait gives up after 30 s unless `timeout_s` says otherwise, `ai_wait`
after 120 s) · `hold {seconds}` · `voice_in {}` · `expect_text {selector, name}` (prints
`TEXT_<name>=`; one per scene that computes a figure, so the take proves it in every language).

The recorder writes `<clip>.webm.events.json` beside each take: `[{kind, start, end}]` with
`typing | wait | load | travel | hold | voice_in | voice_out | key_visible`, seconds from the
first frame; the assembler compresses typing (3x), waits (first second kept, the rest squeezed
into `wait_squeeze_s`), travel and loads (2x), keeps `must_see`, and refuses a take with
`key_visible`. The recorder
reaches the instance as the handle's `ui_user` and runs `language_switch` before the first frame;
the storyboard says nothing about accounts.
