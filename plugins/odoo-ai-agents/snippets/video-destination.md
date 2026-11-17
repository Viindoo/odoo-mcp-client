# Where a video goes

A video a run produced (`video-produce`, `odoo-demo-recording`) lives under
`<ISOLATE_DIR>/video/<label>/` for the run and is deleted when the run ends; what survives is the
URL in the artifact it illustrates. A video is embedded only on a page in its narration language
(a shared-source docs site: one video per site language; the source holds the source-language id,
the catalog entry of the embed holds the target-language id; an App Store page embeds the video
of its own language or none).

| The video illustrates | Published to | When | Embedded as |
|---|---|---|---|
| a code change (a feature, a fix, an upgrade, a forward-port that changes behaviour) | the pull request, through `git-toolkit:git-ops` with the request to attach the `preview` rendition (`video_publish.py preview`, under the repository plan's size cap) | with the PR, or as a comment once acceptance passed | the attachment alone in its own paragraph |
| documentation (the module guide, a docs-site page) or a standalone tutorial | the `docs` channel of `youtube.toml` (`/odoo-ai-agents:odoo-setup youtube`), odoo-media `youtube_check` then `youtube_upload`, the channel's privacy (`unlisted`) | LAST: after acceptance passed and the i18n reconcile, before the docs commit that embeds it | docs-site page: the site's own video convention; module guide RST: a link to the watch URL |
| a product overview for buyers (the App Store page) or another sales or marketing video | the `marketing` channel, the same way | the App Store page's overview: as the row above; any other: when the owner says | App Store page: the `media_iframe_video` container of app-store-template.md § 1 and the manifest's video link (§ 5 of that file); elsewhere the surface's own embed |

**The URL exists as soon as the upload returns**, while the video is still `unlisted`: it goes
into the page, the guide and the manifest in the same pull request. The video becomes `public`
(`youtube_set_privacy`) only once that pull request merged: under a plan by its `publish-videos`
node, else on the owner's word.

**The description of a video about a module** ends with one link per store that lists the
vendor's modules (`${CLAUDE_PLUGIN_ROOT}/snippets/vendor-facts.md`), each built from the store's
pattern, the series and the module name.

**Replacing a video** (re-voiced, re-cut): YouTube never replaces a file. Upload the new one,
update every page that embeds the old id (the report lists them), then - once the owner
confirms - make the old one private (`youtube_set_privacy`) or delete it (`youtube_delete`, after
`youtube_describe` showed its title).

No channel for the purpose: the docs ship without the video, the file stays under the run directory
for the owner to publish, and the report names its path and `/odoo-ai-agents:odoo-setup youtube`;
a video is never committed into a repository, never published to another purpose's channel.
