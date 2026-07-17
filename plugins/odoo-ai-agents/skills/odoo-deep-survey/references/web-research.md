<!-- SSOT for the deep-survey Phase W (web research) procedure. The orchestrator (opus, main
     context) reads this and INLINES the relevant parts into each dispatched web-research fork
     worker (leaf subagents cannot resolve ${CLAUDE_PLUGIN_ROOT}). Phase W is CONDITIONAL (fires
     only on an external-dimension sub-question) and BOUNDED. This is reconnaissance, NOT the
     built-in `deep-research` skill - do NOT dispatch or depend on that heavy workflow. -->

# Deep-Survey Phase W - bounded web reconnaissance

Phase W is a LIGHT, conditional external-evidence pass. It is reconnaissance, not exhaustive
research: a small broad `WebSearch` sweep followed by a bounded number of targeted `WebFetch`
of the top reputable sources. It reuses the SAME fork-worker fan-out machinery as Phases 1-3;
it does NOT invoke or depend on the built-in `deep-research` skill (that is a heavy,
token-costly loop-until-dry / N-vote harness - out of scope here).

## Trigger (conditional-on-intent)

Run Phase W **only if** the Bootstrap decomposition produced at least one sub-question with an
EXTERNAL dimension - i.e. the answer lives outside the codebase/OSM index:

- a third-party library / external API the code integrates with;
- a standard / regulation / spec the behavior must conform to;
- an ecosystem or version-landscape question ("what does the OCA/community do", "which versions
  support X");
- a "how do others solve X" comparison.

For a PURE in-codebase / OSM survey (no external sub-question), Phase W is **SKIPPED entirely**
- consistent with the skill's evidence-triggered escalation discipline. State the skip.

## Bound (hard cap - state it in the run)

Phase W is explicitly capped. It is NOT loop-until-dry, NOT an N-vote adversarial harness, NOT
unbounded fan-out:

- **Broad sweep:** at most ONE haiku fork worker per external sub-question, each running a small
  `WebSearch` (a few queries), capped at **<= 4 web workers per survey**.
- **Targeted fetch:** each worker does `WebFetch` on at most the **top 3 reputable sources** for
  its sub-question - authoritative tier first, reputable tier only to fill gaps.
- **No escalation loop.** One broad -> targeted pass per sub-question, then stop and record. A
  still-open external question becomes an `open_questions` row, not another web wave.

## Source-credibility ladder

Rank every source before trusting it; a finding's tier travels with it into `web_findings`.

- **Authoritative** (load-bearing): `github.com/odoo/odoo` source, `odoo.com/documentation`, the
  OSM index itself, `github.com/OCA` repos, official Odoo release notes / runbot. For a named
  third-party dependency, that library's OWN official docs are authoritative for the library.
- **Reputable** (usable, prefer corroboration): well-known Odoo blogs, Cybrosys articles,
  accepted answers on the official Odoo forum, established community docs.
- **Low-trust** (corroboration-only, NEVER load-bearing): random forums, unattributed blogs,
  AI-generated content, SEO content farms. A low-trust source may only echo a claim already made
  by an authoritative/reputable source - it can never be the sole basis for a finding.

## Light corroboration

Prefer **>= 2 reputable-or-better sources** for any web claim that will inform the plan. A single
reputable source is allowed but the claim is marked `UNVERIFIED`. An authoritative source stands
on its own (`VERIFIED`). Low-trust sources never raise a claim above `UNVERIFIED`.

## HARD rule - web is SUBORDINATE to OSM/source

A web claim about how ODOO behaves is subordinate to OSM and the Odoo source. **If a web source
and OSM/source disagree about Odoo behavior, OSM/source WINS** - drop the web claim, or keep it
only as a flagged discrepancy noting that OSM/source contradicts it. Web evidence is
load-bearing ONLY for genuinely external facts (a third-party library's API, a regulation's
text) that OSM does not index. Never let a blog override `model_inspect`.

## Recording

Every web finding carries **source-tier + URL + fetch-date**. Workers write findings to
`<SHARE_DIR>/survey/<slug>-<date>/phaseW/<NN>-<subquestion>.md` (resolve `<SHARE_DIR>` once per
`${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`; substitute the captured absolute path -
never write the placeholder or a bare `.odoo-ai/` into a Read/Write/Edit) + one worklog entry each. At
synthesis they aggregate into the `web_findings` section of `synthesis.md`
(`references/synthesis-schema.md`) as rows:
`claim | source-tier | URL | corroborating-source | VERIFIED/UNVERIFIED`.
