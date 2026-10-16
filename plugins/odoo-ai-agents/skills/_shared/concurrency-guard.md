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

## Model-tier selection - the kind of reasoning drives the tier (SSOT)

Every launch passes `model` explicitly. Pick the LOWEST tier whose row matches the kind of
reasoning the work needs. Size is never an input: module count, file count, line count and blast
radius do not move a tier.

| tier | pick when the work is |
|------|-----------------------|
| **haiku** | mechanical, or a rule already stated: find and gather over code, OSM, git, GitHub, web; instance build, serve, test, log; CI polling; renames and list-driven deletions; recon; a build node whose design block passes the 5.1 checklist; review mode `R1`; acceptance modes `A1`, `A2`; comparing observed values with stated expected values |
| **sonnet** (default when unsure) | a rule must be inferred or judged: a build node that fails one 5.1 item; review `R2`; debugging to a root cause; plan execution and coordination; translation; writing for a human reader; planning |
| **opus** | design (SRS and design session); any unit whose `business_function` is on the specialist list in `${CLAUDE_PLUGIN_ROOT}/snippets/business-taxonomy.md`; a node that meets 5.2; review `R3`; the one retry a tier up after an evidenced sonnet failure |
| **fable** | a design that changes an inheritance axis across two or more modules; never a default; always explicit human confirmation |

### 5.1 Haiku checklist for a build node

The architect fills it when writing `build_tier_hint`; the launcher checks presence, not quality.
All six present in the node's design block -> `haiku`. One missing -> `sonnet`. Node meets 5.2 ->
`opus`.

1. Every model touched is named and confirmed by OSM, or is a new model with `_name`, `_inherit`,
   `_description`.
2. Every new field has a name, a type, its relation target, `required`, and for a compute its
   `depends` and its rule written as condition -> value.
3. Every override names the method, the `super()` position, and its rule as condition -> outcome.
4. Every view change names the parent view xml_id and the xpath or anchor field.
5. The security groups for ACL rows and record rules are named.
6. Every acceptance criterion of the node has a comparable expected value.

### 5.2 Opus conditions for a node

Read from the taxonomy and `recon.md`, never judged. Either holds:
(a) the node's `business_function` is on the specialist list; or
(b) the node has two or more `business_function` values AND recon records, for a method the node
changes, an override chain of at least `OVERRIDE_CHAIN_MIN` entries or at least `DEPENDENTS_MIN`
dependent modules.

`OVERRIDE_CHAIN_MIN = 3`, `DEPENDENTS_MIN = 5` - edit the two numbers here only.

### Escalation

On `BLOCKED`, a `NEEDS_JUDGEMENT` line, or a failed own gate: relaunch ONCE, one tier up, passing
the previous attempt's artifacts. Never two tiers at once.

### Launch economics - every launcher (main, architect, coder) pays for a launch with its reason

Launch only when at least one holds, and write the letter into the worklog line for the launch:
(a) independence - a reviewer or tester must not share the author's context;
(b) real parallelism on disjoint file sets, each part verifiable by its own tests;
(c) the deliverable exceeds one agent's output budget;
(d) the work is tool-heavy and mechanical while this context runs at a higher tier;
(e) this context must stay clean for a later decision.
None holds -> do the work inline. Follow-up on something an existing agent did (fix a finding,
verify a fix, a second round, continue after a gate) goes to that agent with `SendMessage`, never
to a new launch; Explore and Plan agents cannot be resumed.

### Haiku-safe body rules

Every body that can run at haiku: each step has a true-or-false condition; a missing fact is
written as `UNKNOWN`, never guessed; every claim carries its evidence (an OSM result or
`file:line`); a step that needs judgement writes `NEEDS_JUDGEMENT` and stops; full output goes to
a file and the report returns the path plus a short summary; every OSM call passes a concrete
`odoo_version` and `profile_name`.

### Where a tier is chosen

The launch `model` parameter first, else the agent's frontmatter `model:`, else
`CLAUDE_CODE_SUBAGENT_MODEL`, else the caller's own model. An agent body never states its own
tier. A Skill runs in the invoking context's model: a mechanical skill invoked from an opus or
fable context is wrapped in a haiku or sonnet launch (reason d).

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
