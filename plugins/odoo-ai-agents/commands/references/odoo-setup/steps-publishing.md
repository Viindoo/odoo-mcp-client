# Publishing steps: docs site, author profile, voice, YouTube

Contents: 60-docs-site - 65-author-profile - 70-speech - 75-youtube. Each runs only via its own filter
(`docs-site`, `author`, `voice`, `youtube`), never in `all` or `instance`. Fork resolution for step 60 is in
`instance-cluster.md` § Fork resolution.

## Step notes

- **60-docs-site** *(runs only via `docs-site`; never in `all` or `instance`)* - Ask the operator for
  the path of a local clone of the docs repo. The operator has none: print `git clone <REMOTE>
  <directory beside the operator's other clones>` (`REMOTE` from the repo URL the operator names, or
  from `propose` on another clone), ask the operator to run it and re-run `docs-site`; never clone
  automatically. Then:
  1. Run `"$STEPS_DIR/60-docs-site.sh" propose --repo <path> [--key <id>]` (read-only). Read
     `REMOTE`, `FORK_STATUS`, `FORK_QUESTION`, `FORK_KNOWN_OWNERS`, `FORK_CANDIDATES`, `OTHER_REMOTES`, `SERIES`, `SERIES_<X_Y>_CLONES`,
     `SERIES_<X_Y>_INSTANCES`, `LANGUAGES` (`UNKNOWN` = the repo states none) and `DECLARED`.
     When `FORK_STATUS` is not `fork-remote-pushed`, follow **Fork resolution** before step 2.
  2. Show the facts. Put `FACTS_TO_CONFIRM` and `POLICY_FIELDS_TO_CONFIRM` to the operator with
     AskUserQuestion. Never fill a policy field yourself; leave an unanswered one unset; an empty
     list is a confirmed none. When `DECLARED=1`, offer `show --key <id>` values as defaults.
     Ask whether the docs repo has a forward-port bot; if yes, offer
     `FORWARD_PORT_BRANCH_PATTERN_CANDIDATE` (when non-empty, with its `..._EVIDENCE` branches) as
     the default of `forward_port_branch_pattern` (it must contain `{pr}` and `{series}` only); if
     no, leave it unset. Never record the candidate unconfirmed. Ask which code repositories the
     site documents and record them as `repos` (`owner/repo` or origin URL); never fill it from a guess.
  3. Write the confirmed row as one JSON object to a file under `<state root>/scratch/docs-site-setup/`, then run
     `"$STEPS_DIR/60-docs-site.sh" record --key <id> --from-json <file>` and remove the file after `record`. On a refusal, show stderr,
     correct the answer with the operator and re-run. `record` refuses a row without a `clone` on
     at least one series: offer the `--repo` path. `record` refuses an instance the catalog does not
     declare: route the operator to `/odoo-ai-agents:odoo-setup instance` first, then re-run
     `docs-site`. Never edit `docs-sites.toml` by hand.
  `check` / `show [--key <id>]` read the file; `apply` only advises.
- **65-author-profile** *(runs only via `author`; never in `all` or `instance`)* - The one
  source of every published contact detail. 1. Run `"$STEPS_DIR/65-author-profile.sh" propose
  --addons <the addons directory of the project>` (read-only): it prints `VENDOR`, `WEBSITE`
  and `SUPPORT_EMAIL` read from the module descriptors, and `FACTS_TO_CONFIRM`. 2. Put the
  facts to the operator with AskUserQuestion: confirm vendor and website; ask for the
  pre-sales page (`presales_url`) and the support or ticket page (`support_url`) - web pages,
  `https://`, never an address; the manifest-only `support_email`; `address_policy` (`never`,
  the default, or `image` when the vendor insists on showing an address, rendered as a PNG);
  optionally `font_file`. Never fill a page URL yourself; an unknown one stays unset and the
  page ships without that card. 3. Write the confirmed profile as JSON under
  `<state root>/scratch/author-profile-setup/`, run `"$STEPS_DIR/65-author-profile.sh" record
  --from-json <file>` and remove the file. A refusal names the field; correct it with the
  operator and re-run. `check` / `show` read the profile; `apply` only advises.
- **70-speech** *(runs only via `voice`; never in `all` or `instance`)* - Narration for demo
  videos, vendor-neutral: any endpoint that speaks the OpenAI audio API (`POST
  <base_url>/audio/speech`, optional `GET <base_url>/audio/voices`) for text-to-speech, and
  `POST <base_url>/audio/transcriptions` for the speech-to-text check. The operator never types
  a model id, a voice id or an auth mode: the endpoint states them. 1. Run
  `"$STEPS_DIR/70-speech.sh" propose` (read-only): it lists what it found - a gateway the
  operator exported as `ODOO_AI_SPEECH_BASE_URL`, local containers or services answering the
  audio shape - the provider shapes it knows, and whether `ffmpeg` has the filters the assembler
  needs. 2. ONE closed question: "Where does the narration voice come from?" with what `propose`
  found as the first choices, then "my company's gateway - I give its URL", "a hosted vendor
  with an OpenAI-compatible audio API - I give its URL", and "none for now (demo videos stay
  silent)". A URL is the one free-text answer. 3. Run
  `"$STEPS_DIR/70-speech.sh" probe-endpoint --base-url <URL>` (read-only, no value): it says
  whether the endpoint answers, whether it is open or expects a value (`AUTH=open|required`),
  and, when open, its models and voices. `AUTH=required`: record the endpoint first
  (`"$STEPS_DIR/70-speech.sh" record --endpoint-only --from-json <file>` with the TTS and STT
  `base_url` and `auth` only - the value will only ever travel to this recorded endpoint), tell
  the operator to open `/plugin`, choose `odoo-ai-agents`, Configure, fill in "Speech endpoint
  key" (never through the chat), then `/reload-plugins`; then the odoo-media `speech_voices`
  tool lists the models and, when the endpoint publishes a listing, the voices. 4. Decide from
  the listing, show it in the plan: the TTS model (the one id that names speech or tts; several
  -> one closed question from the list), the STT model (the id that names transcription, stt or
  whisper; same rule), one voice per narration language - the languages the docs-site and i18n
  registries declare, never asked again - from the voices the endpoint tags for that language,
  else ONE closed question per language from the list (a voice is native to one language; a
  mismatch is refused). `voices` null (the endpoint publishes no listing, as many gateways do):
  the voice ids come from the endpoint's own documentation - ONE closed question per language
  naming the ids the operator reads there - and `speech_probe` in step 5 is what confirms them.
  5. Write the confirmed
  configuration as JSON under `<state root>/scratch/speech-setup/`, run
  `"$STEPS_DIR/70-speech.sh" record --from-json <file>` and remove the file; then call the
  odoo-media `speech_probe` tool (one short sentence per language, synthesized and transcribed
  back: `verdict` `pass` per language, else the voice or the endpoint is wrong) and let the
  operator listen to the clips it names. `check` validates the file only; `apply` only advises. **Upgrading from an earlier version:** when `check` prints `UPGRADE=`,
  the file still names an environment variable; hand the operator the command on that line
  (their own terminal, or this chat with a leading `!`; never yours) - it moves the value into
  the plugin configuration and rewrites the file - then `/reload-plugins`, and step 3 is done.
- **75-youtube** *(runs only via `youtube`; never in `all` or `instance`)* - The channels videos
  are published to, by purpose. 1. Run `"$STEPS_DIR/75-youtube.sh" propose` (read-only): it
  prints what the operator prepares on the Google side (a Cloud project with the YouTube Data
  API enabled, a Desktop-type OAuth client and its downloaded client JSON, the consent screen
  External and In production with Branding filled in) and the slots. 2. Ask the operator ONE
  closed question: which channels they publish to - `docs` (user guides, the docs site, the App
  Store page's video block; at least this one), `marketing` (sales and marketing videos), a third purpose
  of theirs - then, per chosen channel, its label (the channel's handle or name, free text).
  Nothing else is asked: the default privacy is `unlisted` (a decision the plan states; public is
  said per upload); a playlist id and a default language are never asked at setup - a playlist
  is added later with `odoo-setup youtube` (its id is the `list=` value of the playlist's URL in
  YouTube Studio), and every upload states its own language. A purpose without a channel keeps
  its videos local. 3. Per channel, write the confirmed table as JSON under `<state root>/scratch/youtube-setup/`,
  run `"$STEPS_DIR/75-youtube.sh" record --channel <purpose> --from-json <file>` and remove the
  file. 4. Per channel, give the operator the one command THEY run in their own terminal, on a
  machine with a browser: `"$STEPS_DIR/75-youtube.sh" consent --channel <purpose> --client-json
  <downloaded client JSON>` - it completes the consent for the account that owns the channel and
  stores what it obtains in the plugin configuration itself, printing nothing of it; then
  `/reload-plugins`. The operator runs it in a terminal, or types it in this chat with a leading
  `!` (it then runs on their machine, outside the agent); the agent never runs it. 5. Call the odoo-media `youtube_check` tool
  (channel = purpose, `live` true): the channel title comes back from Google, or the result names
  the option still missing. `check` validates the file only; `apply` only advises. **Upgrading
  from an earlier version:** when `check` prints `UPGRADE=`, hand the operator the command on
  that line (their own terminal, or this chat with a leading `!`; never yours) - it moves the
  values into the plugin configuration and rewrites the file as channels - then
  `/reload-plugins`, then step 5.
