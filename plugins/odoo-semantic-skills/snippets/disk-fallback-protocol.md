<!-- SSOT snippet. The single home for the "what do I do when OSM is unreachable" answer.
     Referenced (not copy-pasted) by every skill/agent whose Standalone-first fallback used
     to say "ask the user to paste / provide ...". Edit here only; consumers point at
     ${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md. Pairs with osm-first-contract.md. -->

# Disk-Fallback Protocol (three-tier grounding)

**Your consumer is another AI agent, not a human.** Every agent running this plugin has the
universal tools - `Read`, `Grep`, `Glob`, `Bash`, `WebFetch`/`WebSearch` - plus the OSM index
and the plugin's own `.odoo-ai/` files. When OSM (the `odoo-semantic` index) is unreachable,
**reading the source yourself is a legitimate grounding path, not a degraded one.** Asking a
human to paste data you can fetch is the worst possible fallback for an agent. Resolve every
input in this order and stop at the first hit. Do not build a step on any optional, non-default
integration (a live ERP/CRM MCP, an email connector) - those may be absent on another machine;
use them only as a bonus when present.

## Detecting "unreachable" (incl. hangs) - the circuit-breaker

"Unreachable" is **not** only a clean connection-refused. A tool call that **times out, hangs,
or returns a transport error** is a Tier-1 failure too - drop straight to Tier 2 and do not
re-wait on the stalled call. (A well-configured client caps the wait: the `odoo-semantic` entry
should carry `"timeout": 90000` (90 s) - see `docs/setup.md`. Default Claude Code
`MCP_TOOL_TIMEOUT` is ~28 h, i.e. effectively no cap, so a missing timeout is what turns a
server hang into an indefinite block.)

**Circuit-breaker:** after **2 consecutive OSM timeouts in a session**, treat OSM as down for
the **rest of the session** - skip all further OSM calls and go straight to Tier 2. This avoids
paying the ~90 s stall on every subsequent call against a server that is clearly not answering.
Tripping the breaker keeps you at `grounded: local-source` - it does **not** drop you to
`ungrounded` (that is Tier 3 only).

## Tier 1 - OSM-backed (gold standard)

The `odoo-semantic` index. `set_active_version` → `model_inspect` / `entity_lookup` /
`check_module_exists` / `find_examples` / `lookup_core_api`, etc. Use whenever reachable.

**Tier-1 MISS (reachable but the entity is not in the index).** OSM indexes Odoo core and
the configured repos/profiles - it does NOT index every customer-local addon. When OSM is
reachable but returns not-found/empty for a SPECIFIC module, model, or field that the
request says exists (typically a customer-local custom module), that is a MISS, not proof
of absence: keep using Tier 1 for everything it does cover, and drop to Tier 2 ONLY for the
missed entities - `Read`/`Grep` the local addons to get their fields, methods, manifest
`depends`, and views. Label the artifact `grounded: osm + local-source (hybrid)`. Never
conclude "module does not exist" from an index miss alone when a local repo is available to
check.

## Tier 2 - Disk- / live-grounded (use BEFORE ever asking a human)

When Tier 1 is unreachable - or for the specific entities a Tier-1 MISS could not cover -
self-serve from real sources you already have access to:

- **Local Odoo source** - discover modules with `Bash`: `find . -maxdepth 4 -name __manifest__.py`;
  `Read` each manifest for `version` / `depends` / `summary`; `Grep` model classes
  (`grep -rn "class .*models.Model" --include=*.py`), fields, method signatures, deprecated
  patterns (`@api.multi`, `_columns`, `osv.osv`, `web.Widget`), view/menu ids, SCSS tokens.
- **Official upstream** - `WebFetch` the raw source for the target version, e.g.
  `https://raw.githubusercontent.com/odoo/odoo/<version>/addons/<module>/__manifest__.py`,
  release notes, or `WebSearch` for public changelog / competitor / pricing pages.
- **Context + vault** - `Read .odoo-ai/context.md` for version/profile/instance; read vault
  notes (`Resources/Competitors/*`, `Sales/Customers/*`) instead of asking for them.

Label any artifact built this way `grounded: local-source (not OSM-indexed)` and lower
confidence one notch versus Tier 1 - it is **verified against real source**, just not the
index. This is NOT `ungrounded`.

## Tier 3 - Training-memory (last resort, must be flagged)

Only if Tiers 1 and 2 both fail (no index, no readable repo, no live instance, no network).
State `OSM unavailable - ungrounded` at the top of your output, lower confidence, and make the
caveat survive into the final artifact your orchestrator returns (per `osm-first-contract.md` §4).

## Asking a human

Escalate to the caller (`NEEDS_CONTEXT`) **only** for inputs that are genuinely unobtainable
by any tier above: secrets/credentials, or a business decision that no source encodes. Never
ask a human to re-supply code, field lists, manifests, module lists, changelogs, CRM data, or
email threads - those are Tier-2 fetches. If the repo/instance is truly inaccessible, say so
and return `BLOCKED(<reason>)` rather than soliciting a paste.
