# odoo-media MCP server - tool reference

`odoo-media` is the plugin's second local stdio MCP server (`scripts/mcp/odoo_media_server.py`,
package `scripts/mcp/odoo_media/`), registered in `.mcp.json` next to `odoo-local` and listed in
`scripts/lib/plugin_mcp_servers.py` `LOCAL_SERVERS`. It carries the two surfaces that need a value
the operator configured through the plugin's options: narration speech and YouTube publishing.
Agents call its tools as `mcp__plugin_odoo-ai-agents_odoo-media__<tool>`.

## Why a server

Claude Code substitutes a plugin's `userConfig` options (`plugin.json`; `sensitive: true` = masked
dialog, stored by Claude Code) only into a plugin MCP server's `env` / `headers` and into exec-form
hooks. A script an agent runs through Bash never sees them, a skill sees a placeholder. So every
call that sends such a value runs inside this server; the libraries (`scripts/lib/speech_client.py`,
`youtube_upload.py`) take the value from their caller and keep a CLI for a human who exports it.

## Options

The options and the environment names the server receives them under are declared in exactly two
places and nowhere else: `.claude-plugin/plugin.json` (`userConfig`: one option for the speech
endpoint, two for the Google OAuth client, one per YouTube slot `docs` / `marketing` / `third`)
and `.mcp.json` (the `odoo-media` server's `env` block). `scripts/mcp/odoo_media/values.py` maps
the names back to the option titles for `media_info` and for `VALUE_NOT_CONFIGURED`.

An option that was never set reaches the server as the literal `${user_config...}` text and
counts as absent. `media_info` reports presence per option (booleans); a tool that needs an absent
one returns `VALUE_NOT_CONFIGURED` with the option name. The operator fills it in
`/plugin` > odoo-ai-agents > Configure (or `claude plugin configure odoo-ai-agents@<marketplace>
--values-stdin` in their terminal) and runs `/reload-plugins`; `75-youtube.sh consent` stores the
YouTube ones itself.

## Tools

| Tool | Does | Long-running |
|---|---|---|
| `media_info` | version, options present (true/false), `speech.toml` / `youtube.toml` state, languages, channels and slots, ffmpeg filters missing | no |
| `speech_synthesize` | text (one sentence per line) + lang + out [+ pronunciation map, phonemes] -> 48 kHz mono WAV, duration | yes |
| `speech_transcribe` | WAV + lang [+ words] -> transcript [+ word timestamps] | yes |
| `speech_voices` | the endpoint's voice listing as returned | yes |
| `speech_probe` | per language: one sentence synthesized, transcribed back, word error rate, `verdict` pass/fail; clips under `<state root>/scratch/speech-probe` | yes |
| `youtube_check` | channel of a purpose: slot, privacy, options present; `live` = one access refresh + `channels.list(mine)` -> channel id and title | yes |
| `youtube_upload` | resumable upload + captions + thumbnail + playlist; `dry_run` plans; returns watch/embed/short URLs | yes |
| `youtube_status` | upload / privacy / processing status of a video | yes |

Every call retries once per backoff step on HTTP 429 / 503 (a shared low-end gateway queues a
second caller) and stops at the call's cancel event. Calls are meant to run one at a time.

## Error codes (`scripts/mcp/odoo_local/errors.py` SERVER_CODES, shared table)

`VALUE_NOT_CONFIGURED`, `SPEECH_NOT_CONFIGURED`, `SPEECH_FAILED`, `FFMPEG_MISSING`,
`YOUTUBE_NOT_CONFIGURED`, `YOUTUBE_CHANNEL_UNKNOWN`, `YOUTUBE_FAILED`, plus the frame's
`INVALID_ARGUMENTS` / `INTERNAL` / `PYTHON_TOO_OLD`. Each carries a one-line remedy.

## Permissions

`hooks/auto-approve-local.sh` auto-allows every odoo-media tool except `youtube_upload` with
`privacy: public` (and not `dry_run`), which falls through to the human prompt - the one outward
publication this server makes. A channel's DEFAULT privacy is never `public` (`youtube_config`
refuses it), so a public upload is always the explicit argument the hook sees.

## Configuration files (state root, never committed)

- `speech.toml` (`scripts/lib/speech_config.py`): `[tts]` provider, base_url, model, `auth`
  (`bearer` | `none`), response_format, voices_url; `[tts.voices]` locale -> voice (one voice, one
  language); `[stt]` base_url, model, auth.
- `youtube.toml` (`scripts/lib/youtube_config.py`): `[channels.<purpose>]` slot, channel, privacy,
  playlist_id, default_language; at least one channel; one channel per slot. A single `[youtube]`
  table from an older plugin is read as `channels.docs` and rewritten on the next `record`.

## Human-run commands

- `75-youtube.sh consent --channel <purpose> --client-json <file>` (`scripts/lib/youtube_oauth.py`):
  loopback OAuth with PKCE for the Desktop client, scope `youtube.force-ssl`, `prompt=consent`;
  stores the client values and the channel's slot value through `claude plugin configure
  --values-stdin` (or `--out-json FILE`, mode 0600, for the operator to feed and delete).
- The `speech_client.py` / `youtube_upload.py` CLIs read the same values from the environment of
  the human who runs them (the names are in each script's header); an agent uses the tools.
