<!-- SSOT snippet: what a document or marketing text that ships to the public may not contain.
     Read by odoo-doc-writer, odoo-doc-site-writer and odoo-marketer before they write. Edit here
     only; consumers point at ${CLAUDE_PLUGIN_ROOT}/snippets/public-docs-contract.md. -->

# Public docs contract

A module guide, an App Store page, a docs-site page and every marketing piece are published to
people outside the team. Before the file is returned, grep it for each item below; a hit is fixed
in the file, never reported as a finding and left.

| Never in a published text or image | Write instead |
|---|---|
| A local or absolute file path (`/home/...`, `C:\...`, a worktree, a state root, `${CLAUDE_PLUGIN_ROOT}`) | the menu path or UI label; for an image, the convention name of `module-doc-references.md` |
| A host, port or URL of a capture or test instance (`localhost:<port>`, an internal hostname, a database name) | nothing; a public product URL only when `POLICY` or the brief supplies it |
| Any value copied from a settings, environment or catalog file | nothing |
| An email address, plain, obfuscated (`[at]`, `(at)`) or behind `mailto:`, in text, alt or title | the pre-sales or support web page URL of the author profile (`author_profile_config.py show`); when the author insists on an address, an image rendered by `${CLAUDE_PLUGIN_ROOT}/scripts/lib/email_image.py` whose alt text is not the address |
| On a store page, an external link whose visible text hides its URL (the store renders external anchors as plain text) | the host and path as the link text, e.g. `support.acme-erp.com/tickets` |
| A real customer, partner, employee or company name that is not the demo company of the capture, and any price, contract, revenue or roadmap detail | an abstract example ("a manufacturer with ~150 staff") or the demo company |
| An issue, PR, ticket, failure-log or review-finding reference | nothing - the tracker holds it (`artifact-voice.md`) |
| A model, field, method or xmlid name in a text whose readers USE or BUY the product (end users, consultants, administrators, buyers) | the UI label, menu path or outcome. A text whose readers are developers (a technical guide, an API or extension reference, a developer page of a docs site) names models, fields, methods and xmlids: that is its content, and it is correct |
| A screenshot taken on a database that is not a demo-data build, or whose company name differs from the capture policy | a capture on the demo instance the caller provisioned, company name per `POLICY` or the demo default |
| An internal-only wording the site policy bans (`POLICY` `banned_terms`) | the public term |
| A narration of the document's own history: how the software behaved before a fix, what was corrected, why a section was rewritten ("previously", "after the fix", "now", "used to") | the behaviour as it is today, in the present tense; a change that matters to the reader is one line in the changelog section, dated, never in the body (`artifact-voice.md`) |
