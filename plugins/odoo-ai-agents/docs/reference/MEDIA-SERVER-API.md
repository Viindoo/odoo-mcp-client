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
| `media_info` | version, options present (true/false), `speech.toml` / `youtube.toml` state, languages, channels and slots, ffmpeg filters missing, the last upgrade pass (`upgrade`: version, moved, missing, connection) | no |
| `speech_synthesize` | text (one sentence per line) + lang + out [+ pronunciation map, phonemes, `speed` (the video type's rate), `voice` (an audition candidate)] -> 48 kHz mono WAV, duration | yes |
| `speech_transcribe` | WAV + lang [+ words] -> transcript [+ word timestamps] | yes |
| `speech_voices` | the recorded endpoint's voice listing as returned (`null` when the endpoint publishes none), plus its model ids and a TTS / STT model guess; an endpoint-only `speech.toml` (`70-speech.sh record --endpoint-only`) is enough, and the value only ever goes to that recorded endpoint | yes |
| `speech_probe` | per language: one sentence synthesized, transcribed back, word error rate, `verdict` pass/fail; with `speed`, whether the engine honoured it (`speed_honoured`, measured by duration); clips under `<state root>/scratch/speech-probe` | yes |
| `youtube_check` | channel of a purpose: slot, privacy, options present; `live` = one access refresh + `channels.list(mine)` -> channel id and title | yes |
| `youtube_upload` | resumable upload + captions + thumbnail + playlist; `dry_run` plans; returns watch/embed/short URLs | yes |
| `youtube_describe` | title, channel and privacy of a video (read before a change) | yes |
| `youtube_set_privacy` | unlisted -> public when the docs go live; -> private to retire a video | yes |
| `youtube_delete` | delete a superseded video; runs only when the given title matches; the human prompt always applies | yes |
| `youtube_status` | upload / privacy / processing status of a video | yes |

Every call retries once per backoff step on HTTP 429 / 503 (a shared low-end gateway queues a
second caller) and stops at the call's cancel event. Calls are meant to run one at a time.

## Error codes (`scripts/mcp/odoo_local/errors.py` SERVER_CODES, shared table)

`VALUE_NOT_CONFIGURED`, `SPEECH_NOT_CONFIGURED`, `SPEECH_FAILED`, `FFMPEG_MISSING`,
`YOUTUBE_NOT_CONFIGURED`, `YOUTUBE_CHANNEL_UNKNOWN`, `YOUTUBE_FAILED`, plus the frame's
`INVALID_ARGUMENTS` / `INTERNAL` / `PYTHON_TOO_OLD`. Each carries a one-line remedy.

## Permissions

`hooks/auto-approve-local.sh` auto-allows every odoo-media tool except `youtube_upload` or
`youtube_set_privacy` with `privacy: public` (the outward publication) and `youtube_delete`
(irreversible), which fall through to the human prompt. A channel's DEFAULT privacy is never `public` (`youtube_config`
refuses it), so a public upload is always the explicit argument the hook sees.

## Configuration files (state root, never committed)

- `speech.toml` (`scripts/lib/speech_config.py`): `[tts]` provider, base_url, model, `auth`
  (`bearer` | `none`), response_format, voices_url; `[tts.voices]` locale -> voice (one voice, one
  language); `[stt]` base_url, model, auth.
- `youtube.toml` (`scripts/lib/youtube_config.py`): `[channels.<purpose>]` slot, channel, privacy,
  playlist_id, default_language; at least one channel; one channel per slot. A single `[youtube]`
  table from an older plugin is read as `channels.docs` and rewritten on the next `record`.

## Upgrade pass at start (`scripts/mcp/odoo_media/upgrade.py`)

Claude Code runs no plugin code at install, update or reload; the stdio server is what starts again
at `/reload-plugins`. So this server, in a daemon thread that never delays serving, compares the
plugin version with `<state root>/state/upgrade.json` and runs once per version: `upgrade_values.apply`
(the values an earlier `speech.toml` / `youtube.toml` named by environment variable move into the
plugin's options through `claude plugin configure --values-stdin`; the files are rewritten; the
moved values are applied to this process so the tools work at once), then the sibling plugin's
`scripts/migrate_connection.py apply` (found through Claude Code's installed-plugins record; the
stand-alone `odoo-semantic` registration moves into `odoo-semantic-mcp`'s options and is removed).
When the installed odoo-semantic-mcp ships no migration yet (a machine that updated this plugin first),
that half is marked `pending` in the stamp and runs at the first start after the sibling is updated;
the values half is not repeated. The stamp holds the report without any value; `upgrade-notice.txt`
is shown once by the session-start readiness hook. A `--plugin-dir` checkout has no marketplace id and the pass does nothing; a failed
configure call leaves no stamp, so the next start retries; two servers are serialized by a lock.
`ODOO_MEDIA_PLUGIN_ID` is the test seam that stands in for a marketplace path.

## Human-run commands

- `75-youtube.sh consent --channel <purpose> --client-json <file>` (`scripts/lib/youtube_oauth.py`):
  loopback OAuth with PKCE for the Desktop client, scope `youtube.force-ssl`, `prompt=consent`;
  stores the client values and the channel's slot value through `claude plugin configure
  --values-stdin` (or `--out-json FILE`, mode 0600, for the operator to feed and delete).
- `scripts/lib/upgrade_values.py plan|apply` and `odoo-semantic-mcp/scripts/migrate_connection.py plan|apply`:
  the upgrade pass as a command, for an operator whose session did not run it (an option is only
  ever written through `claude plugin configure --values-stdin`, never printed).
- The `speech_client.py` / `youtube_upload.py` CLIs read the same values from the environment of
  the human who runs them (the names are in each script's header); an agent uses the tools.
