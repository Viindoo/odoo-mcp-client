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
| A real customer, partner, employee or company name that is not the demo company of the capture, and any price, contract, revenue or roadmap detail | an abstract example ("a manufacturer with ~150 staff") or the demo company |
| An issue, PR, ticket, failure-log or review-finding reference | nothing - the tracker holds it (`artifact-voice.md`) |
| A model, field, method or xmlid name in a page for users or buyers | the UI label or outcome; a developer page of a docs site may name technical modules |
| A screenshot taken on a database that is not a demo-data build, or whose company name differs from the capture policy | a capture on the demo instance the caller provisioned, company name per `POLICY` or the demo default |
| An internal-only wording the site policy bans (`POLICY` `banned_terms`) | the public term |
