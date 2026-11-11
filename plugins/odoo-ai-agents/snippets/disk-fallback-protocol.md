# Disk-fallback protocol (three-tier grounding)

When the Odoo Semantic index (OSM) cannot answer, read the source yourself: that is a legitimate
grounding path, and asking a human to paste data you can fetch is not. Resolve every input in this
order and stop at the first hit. Never build a step on an optional integration (a live ERP or CRM
MCP, an email connector) that another machine may lack; use one only as a bonus.

## Tier 1 - OSM

Use it whenever it is reachable.

**Unreachable** covers a refusal, a timeout, a hang and a transport error alike: drop to Tier 2
and do not wait on the stalled call. After two consecutive OSM timeouts in a session, treat OSM as
down for the rest of it. That keeps you at `grounded: local-source`, not `ungrounded`.

**A miss is not absence.** OSM indexes Odoo core and the configured repos, not every local addon.
A not-found for a specific module, model or field the request says exists: keep OSM for what it
covers, read the local source for the missed entity, and label `grounded: hybrid`. Never conclude
"does not exist" from an index miss while a local repo is readable.

## Tier 2 - the source, before any question to a human

- **Local Odoo source**: the module descriptors (`__manifest__.py`, and `__openerp__.py` on the
  series that use it) for version, `depends` and summary; the model classes, fields, method
  signatures, views, menus and SCSS tokens by search.
- **Official upstream**: the raw source of the target series, release notes, or a public page, by
  web fetch or search.
- **The declared instance catalog** for series, profile, addons path and instance
  (`${CLAUDE_PLUGIN_ROOT}/snippets/project-facts-resolution.md` rung 2), and, when the caller set
  `$ODOO_AI_VAULT_HOME` (an optional pointer to a private notes vault with no assumed layout), a
  note there matching the entity's name. Unset or nothing found: skip it silently.

Label the result `grounded: local-source - not OSM-indexed`, one notch of confidence below Tier 1:
it is verified against real source.

## Tier 3 - memory, flagged

Only when there is no index, no readable repo, no live instance and no network. State
`grounded: ungrounded - OSM unavailable` at the top, lower the confidence, and carry the caveat
into the final artifact.

## Asking a human

`NEEDS_CONTEXT` only for what no tier can supply: a business decision no source encodes. Never ask
for code, field lists, manifests, module lists, changelogs, CRM data or email threads. A repo or
instance that is truly inaccessible is `BLOCKED(<reason>)`, not a request to paste.
