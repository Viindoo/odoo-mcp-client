# i18n phase detail

Contents: P0 language resolution; Release the export instance; Dispatch brief extras.

## P0 language resolution

**P0 - Scope [haiku].** Resolve the target language list by precedence (highest first),
then echo which source was used:

1. Explicit languages in the request/args.
2. Machine-global registry: read `${ODOO_AI_HOME:-$HOME/.odoo-ai}/i18n.json` and use its
   `default_languages` array if present and non-empty.
3. Infer from existing `<lang>.po` filenames in each module's `i18n/` directory
   (`<module>/i18n/<lang>.po`); skip this tier when no `i18n/` dir exists. A stem is either the
   full language code or Odoo's export name, the language's ISO code: resolve an ISO-code stem to
   its language code before passing it to a build.
4. Query the confirmed instance: `res.lang` records with `active = True` (codes).

**No tier 5 - the target language is a REQUIRED input with NO built-in default.**
Never treat `en_US` as a *target* language or as a stand-in for an unresolved target. When tiers
1-4 ALL resolve empty:

- **Standalone** (a human asked directly, not as a dispatched pipeline step): return
  `status: NEEDS_CONTEXT` naming the missing field (`target language`).
- **Mandated** (a caller dispatched you as a required step, `${CLAUDE_PLUGIN_ROOT}/snippets/i18n-mandate-contract.md`):
  record `i18n: not-applicable (no target language resolvable from tiers 1-4)` (escape E3), return
  that verbatim to the caller, and translate nothing.

A caller SHOULD pass explicit `TARGET LANGUAGES` when it has them; when it has none, tiers 2-4 still
run against whatever IS available.

**`en_US` is mandatory, independent of the tiers above.** After resolving the target languages, set
`activation_languages = {"en_US"} union target_languages`. `en_US` is ALWAYS loaded into the DB
alongside every target language (recipe KT3) - none of the tiers above can produce it (Odoo ships no
`en_US.po`), so add it here. It governs the DB-activation set - the export build's `languages` and
the `languages_loaded` its `INSTANCE_HANDLE` must show - ONLY; no `en_US.po` is exported or merged.

Echo the resolved language list (target languages + the `activation_languages` set) AND the source tier
that produced it in the scope summary.

## Release the export instance

**Release the export instance [MANDATORY, after the last P4 reload].** When THIS skill provisioned
the P2 build (standalone, or `SELF_PROVISION`), you are the run-level owner of the lease
(`${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T1): once every P3 leaf has returned
and the last per-language reload is done, call
`mcp__plugin_odoo-ai-agents_odoo-local__lease_release` with its `lease_token` and `run_id` - or
`lease_park` when the user or a named next step still wants that database. A brief that carries
`HAND_ON: <skill>` (the caller's documentation step, `${CLAUDE_PLUGIN_ROOT}/snippets/docs-after-change.md`
§ One capture instance per build shape) keeps the lease running instead: return its `INSTANCE_HANDLE` and
`BUILD_SHAPE` in the Continuation Contract's `next.inputs` and release nothing; the caller owns it
from there. An `INSTANCE_HANDLE` your caller forwarded DOWN to you is never yours to release or
park.

## Dispatch brief extras

Also carry, verbatim, the P2 build the artifacts came from: `INSTANCE_HANDLE` (the SAME handle for
every leaf of the run) plus `BUILD_SHAPE: demo=on, languages=<activation set>,
skip_auto_install=<bool>`. A leaf that receives a `BUILD_SHAPE` with `demo` anything but `on`, or
that cannot corroborate demo records for a module whose manifest declares `demo` files, returns
BLOCKED rather than reconciling.

Pick the leaf's model per `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § Model-tier
selection, its effort per § Effort, and pass both as launch parameters. When a module in the leaf's scope has a `business_function` on the specialist list of
`${CLAUDE_PLUGIN_ROOT}/snippets/business-taxonomy.md` (read from its manifest `category`), state the
function in the brief.
