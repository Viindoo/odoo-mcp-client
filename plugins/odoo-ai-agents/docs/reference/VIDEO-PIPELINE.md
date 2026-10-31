# Narrated demo videos - the scripts behind `odoo-produce-video` (human reference)

The `video-produce` workflow runs five phases (storyboard, record-scenes, narrate, assemble,
publish); the middle three run in the `odoo-video-producer` agent. Every script below is stdlib
Python (or Node for the recorder), prints `KEY=VALUE` lines, and documents its own flags in its
header docstring - that docstring is the CLI reference; this page is the map.

| Script (`scripts/lib/`) | Does | Exit codes |
|---|---|---|
| `storyboard_check.py` | `check` validates `storyboard.json` (schema: `skills/odoo-demo-recording/references/storyboard.md`); `render` writes the Markdown the plan gate shows; `scene-script` compiles one scene for one language into the recorder's script (`--base-url`, `--ui-user`, `--voice-wav`, `--takes-dir`); `set-prompt` records the trial's pick; `demo-data-script` compiles the seeding actions | 1 refused, with `ERROR=` lines |
| `video_record.py` | the recorder's wrapper: `record`, `prepare`, `trial`, `self-test`, `install-check`; resolves `<state root>/recorder/node_modules` (the Playwright library at the pin of `browser_mcp_servers.BROWSER_PLAYWRIGHT_VERSION`, installed by `odoo-setup browser`) and runs `scripts/recorder/record.mjs` with `NODE_PATH` | 2 not installed (`REMEDY=`), 3 a step found no target, 4 unusable script, 6 a key field was on screen (the video is deleted, the events file kept) |
| `scripts/recorder/record.mjs` | one Chromium reaches the instance as `ui_user` and runs `language_switch` off camera, then drives and records the scene at 1920x1080: cursor overlay and click ripple, wait indicators watched by a MutationObserver (the web client's own plus the storyboard's `wait_selectors`), network idle that ignores the web client's bus connection, the page's own audio saved as `voice_out`, a voice input through the fake microphone, a DOM scan for key fields; writes `<clip>.webm` and `<clip>.webm.events.json` (`typing | wait | load | travel | hold | voice_in | voice_out | key_visible`, seconds from the first frame) | as above |
| `video_budget.py` | `estimate` (requests x tokens x takes x languages + trials, from the storyboard `ai` block), `log` (one ledger line per trial or take), `check --margin` (exit 4 past the estimate), `keys` (refuses a shared or unset key, prints the variable NAME only) | 1 refused, 4 over budget |
| `video_keyscan.py` | `scan --dir` - every kept text file searched for key shapes and the exact value of the named environment variables; `HIT=<file>:<line>`, the value never echoed | 1 on a hit |
| `video_publish.py` | the ffmpeg assembler: `verify-tools`, `speedup` (`--typing`, `--travel`, `--wait-keep`, `--wait-squeeze`, `--must-see`), `zoom`, `fit` (`--narration` optional: without it a silent track, fades only; `--lead-in`, `--fade`, `--max-silence`, `--max-hold`, `--voice FILE@T`), `title`, `concat` (`--music`; a silent input gets a silent track, no loudness pass on silence), `verify` (the `youtube-1080p` profile by ffprobe and ebur128; `--silent` accepts a video with no signal), `sidecar` (`--list` the concat list: chapters from the real clip durations; `--narration-dir` adds the captions), `thumbnail`, `preview`, `audition` | 1 failed, 2 ffmpeg missing, 4 silence over the cap, 5 hold over the cap, 6 a key field in the events |
| `narration_check.py`, `pronunciation.py`, `speech_client.py` | the narration gates and the speech client; see `MEDIA-SERVER-API.md` | per docstring |

Layout under `<ISOLATE_DIR>/video/<label>/`: `storyboard.json`, `storyboard.md`, `scripts/`,
`takes/<lang>/`, `narration/<lang>/`, `assembly/<lang>/`, `deliverables/<lang>/`, `ledger.jsonl`,
`findings.md`. The publish phase deletes takes, narration and assembly; the run that owns the
label removes the rest when it ends.

Setup: `/odoo-ai-agents:odoo-setup browser` installs the recorder library next to the pinned
Chromium and runs `video_record.py self-test` (`FAKE_MEDIA=ok`, `RECORD_VIDEO=ok`);
`05-prereq-check.sh` reports the recorder as an optional item; `odoo-setup voice` and
`odoo-setup youtube` configure the speech endpoint and the channels.
