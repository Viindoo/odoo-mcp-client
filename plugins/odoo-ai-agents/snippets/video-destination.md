<!-- SSOT snippet: where a video a run produced is published and embedded. Consumers point at
     ${CLAUDE_PLUGIN_ROOT}/snippets/video-destination.md; edit here only. -->

# Where a video goes

A video a run produced (`video-produce`, `odoo-demo-recording`) lives under
`<ISOLATE_DIR>/video/<label>/` for the run and is deleted when the run ends; what survives is the
URL in the artifact it illustrates. A video is embedded only on a page in its narration language
(a shared-source docs site: one video per site language; the source holds the source-language id,
the catalog entry of the embed holds the target-language id; the App Store page is English, so it
embeds the English one or none).

| The video illustrates | Published to | When | Embedded as |
|---|---|---|---|
| a code change (a feature, a fix, an upgrade, a forward-port that changes behaviour) | the pull request, through `git-toolkit:git-ops` with the request to attach the `preview` rendition (`video_publish.py preview`, under the repository plan's size cap) | with the PR, or as a comment once acceptance passed | the attachment alone in its own paragraph |
| documentation (the module guide, the App Store page, a docs-site page) or a standalone tutorial | the `docs` channel of `youtube.toml` (`/odoo-ai-agents:odoo-setup youtube`), odoo-media `youtube_check` then `youtube_upload`, the channel's privacy (`unlisted`; the plan's `publish-videos` node switches it to public once the PR that embeds it merged, or the owner does) | LAST: after acceptance passed and the i18n reconcile, before the docs commit that embeds it | App Store DEMO tab: the canonical `youtube.com/embed/<id>` iframe; docs-site page: the site's own video convention; module guide RST: a link to the watch URL |
| a sales or marketing video | the `marketing` channel, the same way | when the owner says | the marketing surface's own embed |

**Replacing a video** (re-voiced, re-cut): YouTube never replaces a file. Upload the new one,
update every page that embeds the old id (the report lists them), then - once the owner
confirms - make the old one private (`youtube_set_privacy`) or delete it (`youtube_delete`, after
`youtube_describe` showed its title). A published video goes `unlisted` -> `public` with
`youtube_set_privacy` when the docs that embed it go live, on the owner's word.

No channel for the purpose: the docs ship without the video, the file stays under the run directory
for the owner to publish, and the report names its path and `/odoo-ai-agents:odoo-setup youtube`;
a video is never committed into a repository, never published to another purpose's channel.
