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

## Model-tier selection - complexity drives the tier (SSOT)

Mode B caps how many run at once; THIS decides which tier each work-item gets.
Every skill/agent that dispatches a subagent sets the launch `model` from the
dispatched work's complexity - the agent's frontmatter `model:` is only a default
that the dispatcher overrides per launch. Pick by the REASONING DEPTH the work
needs, never by wall-clock time.

| tier | pick when the work is | examples |
|------|-----------------------|----------|
| **haiku** | mechanical, low-reasoning, fully bounded - a recipe with no judgement | one field/label/CSV row; copy a known pattern; collect/format already-known facts; a single small file |
| **sonnet** (default) | medium reasoning, balanced - and the ambiguous-case default | normal computed/onchange/constraint; one override; a bounded analysis cluster; anything you cannot confidently place |
| **opus** | heavy reasoning - cross-cutting judgement across MULTIPLE hard domains AND entangled with many interacting modules, together, never size/blast-radius alone (`odoo-coding` § Phase 0 refines this row; do not escalate on size/file-count/blast-radius by itself) | core create/write/unlink override whose correctness spans many dependents; cross-model / multi-company logic spanning modules; cross-cluster synthesis |
| **fable** | ultra-complex, design-first - rare top band (~2x opus); ALWAYS needs explicit human confirmation | Custom-XL whole-subsystem build; change an inheritance axis across modules |

Principle: haiku is fast but only earns its speed on mechanical work; opus is
strong but slow and expensive on small work; sonnet balances the two and is the
default when unsure; fable is never a default. Between two tiers, pick the lower
unless the work needs cross-context reasoning - then pick the higher. A skill MAY
add a domain-specific tier table that refines these rows (e.g. `odoo-coding`
§ Phase 0) but MUST NOT restate the principle - reference this section.

**Recon/scouting phase default (mechanism, not just a rule).** Launching a subagent with no
explicit `model` parameter does not fall back to some neutral default - it INHERITS THE CALLING
CONTEXT'S OWN MODEL. In an opus-tier session this silently turns every unstated dispatch into an
opus dispatch regardless of the work's actual reasoning depth, which is why a dispatch site must
never leave `model` unstated "to be safe" - silence is not neutral, it is a hidden opus default. A
recon/scouting phase - enumeration, grounding, or collecting already-known facts about current
state (a codebase survey, a commit-range triage, a scope/DAG map) - is haiku/sonnet-tier work per
the table above and MUST state its tier explicitly at the dispatch site (inline, e.g. `Model:
sonnet` / `DISPATCH MODEL: sonnet`, or by naming a specific agent whose own frontmatter default
already resolves it) - never opus or fable by default, and never left unstated. Escalating a
recon/scouting dispatch to opus or fable requires a stated justification tied to one of the
table's own opus/fable rows above (e.g. "cross-cutting synthesis across N unresolved hot-spots" -
not "this recon covers a lot of files").

**The same default binds a directly-invoked leaf skill, not just a subagent dispatch.** A
recon/scouting task MAY be done by invoking a read-only leaf skill directly via the Skill tool
instead of dispatching a subagent (a skill name is not an agentType). The Skill tool carries no
per-call `model` parameter - it always executes in the INVOKING context's own model, with no lever
to lower it. This is the inheritance defect above, through a second door: in an opus/fable-tier
orchestrating context, a direct Skill-tool call to a recon-depth leaf skill silently runs that work
at opus/fable, exactly the outcome this whole clause exists to prevent. Decision rule for the agent
taking this path (decidable, not a judgement call): if you are ALREADY haiku/sonnet-tier, invoke the
leaf skill directly - no wrapper needed. If you are opus/fable-tier, do NOT invoke it directly -
wrap the call inside a dedicated haiku/sonnet subagent dispatch (that subagent invokes the Skill
tool internally) so the recon-depth work runs at the cheap tier instead of silently inheriting
yours.

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

The OSM rule above protects the static index; this protects LIVE instances. Under
concurrency, never reuse the declared `db_name`/`http_port` for a MUTATION - tests
(`--test-enable`), `-i`/`-u`, a throwaway server: another agent or session may hold it.
Acquire an isolated lease: `scripts/lib/allocator.py acquire --mode ephemeral --run-id
<id>` (a unique DB name + ports owned by that run) or `--mode exclusive` (single-holder
lease on a declared DB); a read-only attach stays lease-free. The returned port NUMBERS are
version-agnostic - map them to CLI flags via `cli_help`. Exit **6, 7, 8 or 9** is a
REFUSAL, never a degrade: handle all four, and say so when you trade isolation away for
`--mode exclusive` - which `8`/`9` gate too, so it is no way past them. Exit codes (§6.6), protocol, GC/stale rules:
`${CLAUDE_PLUGIN_ROOT}/docs/reference/INSTANCE-ALLOCATION.md` and
`${CLAUDE_PLUGIN_ROOT}/snippets/instance-resolution.md` § Allocate. Release the lease token before your
terminal status - that imperative and the release mechanics belong to
`${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T1/T3, not to this file.

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
