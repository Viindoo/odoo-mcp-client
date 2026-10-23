# Concurrency guard - the OOM envelope for agent fan-out (SSOT)

## Choosing Mode A vs Mode B

Use **Mode B** (model-weighted budget, per-worker ledger, disjoint-file partition) when the skill
fans out MORE THAN ONE worker that WRITES to a shared module/worktree: each worker owns a DISJOINT
file set and records it in the coordination ledger
(`${CLAUDE_PLUGIN_ROOT}/snippets/module-coordination-ledger.md`). Otherwise use **Mode A**.

## Mode A - subagent batching

Cap at **3 concurrent** subagent launches (or fork workers / parallel MCP legs);
for more work, batch in groups of <=3 (fire <=3, wait, fire the next <=3).

## Mode B - model-weighted budget (rolling-window / weighted-batch skills)

| model  | weight |
|--------|--------|
| haiku  | 1 |
| sonnet | 2 |
| opus   | 4 |
| fable  | 8 |

At most **8 weight-units** in flight at once => up to 8 haiku, 4 sonnet, 2 opus,
or exactly 1 fable (always exclusive). Mixing is allowed up to the budget (worst case 2 opus).

## Model-tier selection - the kind of reasoning drives the tier (SSOT)

Every launcher - the main agent, a skill, a spawner or node-owner agent - reads this section by
path before a launch and passes `model` explicitly. Pick the LOWEST tier whose row matches the
kind of reasoning the work needs: cheapest and fastest at the quality the row guarantees. Size is
never an input: module count, file count, line count and blast radius do not move a tier.

| tier | pick when the work is |
|------|-----------------------|
| **haiku** | mechanical, or a rule already stated: find and gather over code, OSM, git, GitHub, web; instance build, serve, test, log; CI polling; renames and list-driven deletions; mechanical documentation upkeep (recapturing the screenshots of existing pages, relabelling to a changed UI label or menu path, toctree wiring, filling translations that already exist, assembling an App Store page from supplied copy and existing captures, re-cutting an existing draft to another channel); recon; a build node whose design block passes the 5.1 checklist; review mode `R1`; acceptance mode `A1A2` when no Given needs a fixture built; comparing observed values with stated expected values |
| **sonnet** (default when unsure) | a rule must be inferred or judged: a build node that fails one 5.1 item; review `R2`; acceptance `A1A2` when a Given needs a fixture built (a multi-company database, a stubbed external service, device emulation, an upgrade database); debugging to a root cause; plan execution and coordination; translation; writing for a human reader; planning; composing new documentation or marketing copy; a landing page written from a catalog |
| **opus** | design (SRS and design session); any unit whose `business_function` is on the specialist list in `${CLAUDE_PLUGIN_ROOT}/snippets/business-taxonomy.md`; a node that meets 5.2; review `R3`; the one retry a tier up after an evidenced sonnet failure |
| **fable** | a design that changes an inheritance axis across two or more modules; never a default; always explicit human confirmation |

### 5.1 Haiku checklist for a build node

The architect fills it when writing `build_tier_hint`; the launcher checks presence only.
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

Read from the taxonomy and `recon.md`. Either holds:
(a) the node's `business_function` is on the specialist list; or
(b) the node has two or more `business_function` values AND recon records, for a method the node
changes, an override chain of at least `OVERRIDE_CHAIN_MIN` entries or at least `DEPENDENTS_MIN`
dependent modules.

`OVERRIDE_CHAIN_MIN = 3`, `DEPENDENTS_MIN = 5`.

### Escalation

On `BLOCKED`, a `NEEDS_JUDGEMENT` line, or a failed own gate: relaunch ONCE, one tier up, passing
the previous attempt's artifacts. Never two tiers at once.

Inside an approved scope the launcher chooses every tier itself, escalation included, and never
asks the human about a tier. `fable` alone needs the human's text confirmation
(`approve / skip / cancel`) before it launches; on `skip` the work stays at `opus`.

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
tier. A skill's frontmatter `model:` takes effect for the rest of the current turn once the skill
is invoked; a skill without it runs in the invoking context's model, so wrap a mechanical skill
invoked from an opus or fable context in a haiku or sonnet launch (reason d). `odoo-instance` is
the rule of its own: launch `odoo-instance-ops` at haiku, inline only in that skill's exceptions
(a)-(d).

## OSM session-pin race (`set_active_version` and `set_active_profile`)

Both pins are server-side state shared per MCP session, last-write-wins: a parent agent and the
subagents it dispatches share one session, so one actor's pin clobbers another's.

In every call, `odoo_version` carries a CONCRETE version and `profile_name` carries a concrete
profile. The sentinel `'auto'` and a bare omission are BOTH forbidden.
Call `set_active_version` (and `set_active_profile` where a tenant profile applies) once at
bootstrap as the reachability probe, and only then. Never rely on their ambient state afterwards. Multi-version and
multi-profile flows (migrations, cross-version diffs, cross-profile deployments) pass the
explicit concrete value per call - never the pin. A genuinely unknown version is a
`NEEDS_CONTEXT`, never a licence to pass `'auto'`.

## Odoo instance allocation (DB / port)

Under concurrency, never reuse the declared database or port for a MUTATION (tests, `init` / `update`, a throwaway
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
optionally +2 headed when a headed variant is also in play), RAM permitting**;
state-mutating (CRUD-heavy) drives stay <= 2 simultaneous regardless of family mix.
Exclusivity rule and close-before-done:
`${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T2.
