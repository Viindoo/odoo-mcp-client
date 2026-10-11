# Concurrency guard - the OOM envelope for agent fan-out (SSOT)

Root failure log: `unbounded-opus-fanout-oom` - unbounded OPUS fan-out crashed the
host. The guard has two modes; every fan-out skill references this file instead
of restating the numbers.

## Choosing Mode A vs Mode B (decision rule for a NEW fan-out skill)

Choose **Mode B** (per-worker ledger + disjoint-file partition) when the skill fans out MORE THAN
ONE worker that WRITE to a shared module/worktree - the model-weighted budget below, combined with
each worker owning a DISJOINT file set and the cross-run coordination ledger
(`${CLAUDE_PLUGIN_ROOT}/snippets/module-coordination-ledger.md`), is what keeps concurrent writers
from colliding. Otherwise use **Mode A**. Apply this rule first; the "Used by" lists under each
mode below are EXAMPLES of skills that already resolve to one side of the rule, not the definition.

## Mode A - subagent batching

Cap at **3 concurrent** subagent launches (or fork workers / parallel MCP legs);
for more work, batch in groups of <=3 (fire <=3, wait, fire the next <=3). None of Mode A's
current users fan out >1 worker writing a shared module/worktree.

## Mode B - model-weighted budget (rolling-window / weighted-batch skills)

| model  | weight |
|--------|--------|
| haiku  | 1 |
| sonnet | 2 |
| opus   | 4 |
| fable  | 8 |

At most **8 weight-units** in flight at once => up to 8 haiku, 4 sonnet, 2 opus,
or exactly 1 fable (always exclusive). Mixing is allowed up to the budget. Worst
case (2 opus) sits within budget.

If an OOM recurs under Mode B, lower BUDGET to 6 here (one place) - do not patch
individual skills.

## Model-tier selection - the kind of work drives the tier (SSOT)

Mode B caps how many run at once; THIS decides each launch's tier. Every launch - plugin agent or
built-in (Explore, general-purpose), from the main agent or any skill/agent - sets `model`
explicitly from the KIND of work and the judgement it needs. Context size is never a reason to
raise a tier or to split work (split only for parallelism, isolation or a clean caller context);
size, file/line/module count and blast radius alone never move a coding or analysis tier - the
DOMAIN's difficulty does (a plan is the exception: its length and breadth count - opus row).
Start at the lowest tier that fits; on BLOCKED, low confidence or a failed own gate, re-dispatch
ONCE one tier up.

| tier | pick when the work is |
|------|-----------------------|
| **haiku** | finding and gathering: lookup/search/listing over code, OSM (multi-tool is fine), git, GitHub, web; instance build/serve/test/log watching; mechanical edits, moves, lint fixes; code whose scope and business rules a design, plan or brief already states; scoping, classifying, validating; a verdict resting on OSM evidence |
| **sonnet** (default when unsure) | judgement: code whose rule must be inferred; root-cause debugging; review; analysis; synthesis (reports, research); coordination; git history rewrite, squash, conflict resolution; a small plan with a narrow blast radius; tests with a break-check; translation (it must read context - "Sun" the star or the day?); customer-facing content; the last safety gate before an irreversible step |
| **opus** | solution design; a long, complex plan; judgement or synthesis in a complex specialist, legal, accounting or regulatory domain (compliance-risk translation terms included); cross-cutting judgement across MULTIPLE hard domains AND many interacting modules together, e.g. a core create/write/unlink override many dependents rely on (`odoo-coding` § Phase 0 refines this row); the step after an evidenced sonnet failure |
| **fable** | ultra-complex, design-first, rare (Custom-XL subsystem, an inheritance axis changed across modules); ALWAYS explicit human confirmation, never a default |

A skill MAY add a domain table refining these rows (e.g. `odoo-coding` § Phase 0) but never
restates this section. **Where a model choice lives:** an agent reads its own body only AFTER it
was launched, so an agent body never says which model it runs at - the choice lives in its
frontmatter `model:` (default), here, or in the skill/agent that CALLS it (a spawner picks its
children's tier by pointing here). **Resolution order:** the launch `model` parameter, then the
agent's frontmatter `model:`, then `CLAUDE_CODE_SUBAGENT_MODEL`, then the caller's own model.

**Recon/scouting phase default (mechanism, not just a rule).** Launching a subagent with no
explicit `model` parameter does not fall back to a neutral default - it INHERITS THE CALLING
CONTEXT'S OWN MODEL, so in an opus session every unstated dispatch silently runs at opus: never
leave `model` unstated "to be safe" - silence is not neutral, it is a hidden opus default. A
recon/scouting phase (enumeration, grounding, collecting known facts: a codebase survey, a
commit-range triage, a scope/DAG map) is haiku by default, sonnet when it must judge, and MUST
state its tier at the dispatch site (`DISPATCH MODEL: haiku`, or a named agent whose frontmatter
resolves it) - never opus or fable by default. Escalating it to opus or fable needs
a stated justification tied to an opus/fable row above (e.g. "judgement in a regulatory domain" -
not "this recon covers many files").

**The same default binds a directly-invoked leaf skill.** A recon task MAY invoke a read-only leaf
skill via the Skill tool instead of dispatching a subagent. The Skill tool has no per-call `model`
parameter - it runs in the INVOKING context's model. If you are haiku/sonnet-tier, invoke it
directly; if you are opus/fable-tier, wrap the call in a dedicated haiku/sonnet subagent dispatch
(that subagent invokes the Skill tool) so the recon work runs at the cheap tier.

## OSM session-pin race (`set_active_version` and `set_active_profile`)

Both pins are server-side state shared per **(api_key_id, mcp_session_id)** - i.e. per MCP
session, last-write-wins. Two INDEPENDENT sessions never interfere with each other. The hazard
is MULTIPLE ACTORS inside ONE session: a parent agent and any subagent it dispatches share that
same session, so one actor's pin silently clobbers another's - confirmed empirically (a
dispatched subagent's `odoo_version='auto'` resolved to the parent's already-set pin, then the
subagent's own pin silently overrode the parent's - no error, no warning either way).

Rule for every agent and skill in this plugin, stated as a BAN so it is checkable: in every
example call and every instruction, `odoo_version` carries a CONCRETE version and
`profile_name` carries a concrete profile. The sentinel `'auto'` and a bare omission are BOTH
forbidden - not discouraged. This ban is a POLICY STRICTER than the server's own contract: the
server itself lets a single-actor session pass `'auto'` to reuse its own pin (ADR-0029) - that
is a legitimate server feature, not a defect, and this plugin is not working around a bug. The
ban exists because an agent can never prove at call time that it is the session's only actor: a
parent may dispatch a subagent at any moment after the pin, silently turning a single-actor
session into a multi-actor one. "`'auto'` is fine when you are alone" is therefore undecidable
from inside a single call; "always pass a concrete value" is decidable and costs nothing extra.
Still call `set_active_version` (and `set_active_profile` where a tenant profile applies) once
at bootstrap: they are the reachability probe and keep the server-side default sane, and that is
their ONLY sanctioned use. Never rely on their ambient state afterwards. Multi-version and
multi-profile flows (migrations, cross-version diffs, cross-profile deployments) pass the
explicit concrete value per call - never the pin. A genuinely unknown version is a
`NEEDS_CONTEXT`, never a licence to pass `'auto'`.

A `set_active_profile` clobber is authz-safe regardless of the above: the pinned profile is
re-validated at read time through a narrowing-only, fail-closed tenant check, so a clobber can
only narrow a view - never widen it or leak data - though it can still silently return a
narrower-than-intended result, which is reason enough to keep passing `profile_name` explicitly.

## Odoo instance allocation (DB / port)

The OSM rule above protects the static index; this protects LIVE instances. Under concurrency,
never reuse the declared database or port for a MUTATION (tests, `init` / `update`, a throwaway
server): another agent or session may hold it. Isolation comes from `lease_acquire` mode
`ephemeral` - a unique database and pooled ports owned by your `run_id`; mode `exclusive` gives up
isolation (say so in your report), and a read-only attach needs no lease. A refused acquire is
never a degrade: follow its error code's remedy. Protocol:
`${CLAUDE_PLUGIN_ROOT}/snippets/instance-resolution.md` § Allocate. `lease_release` (or
`lease_park`) what you acquired before your terminal status; ownership and the exits:
`${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T1/T3.

## Browser exclusivity (orthogonal)

Browser-driving agents (odoo-ui-debugger / odoo-ui-reviewer) are EXCLUSIVE-serial **per MCP
family** - never two drivers on the SAME family (chrome-devtools, playwright, pagecast; headed
and headless each count as their own family) at once. Distinct families MAY run in parallel, up
to the pool cap **`W` = the number of distinct browser server families available (2 headless;
optionally +2 headed when a headed variant is also in play), RAM permitting** -
state-mutating (CRUD-heavy) drives stay <= 2 simultaneous regardless of family mix. THIS file is
the SSOT for the `W` number; other files cite it here rather than restate it. Full rule
(exclusivity rationale + the RAM-guardrail note) + close-before-done:
`${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T2. This file governs OSM-only
fan-out and owns the `W` browser pool-cap number; it does not own the browser exclusivity rule's
rationale - that lives in T2.
