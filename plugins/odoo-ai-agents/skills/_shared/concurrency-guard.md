# Concurrency guard - fan-out caps, model tier and effort (SSOT)

## Fan-out caps

- **Mode A** (the default): at most 3 subagents, fork workers or parallel MCP legs at once; more
  work goes in batches of 3.
- **Mode B**, for a skill that fans out more than one worker WRITING to a shared module or
  worktree: each worker owns a disjoint file set recorded in the coordination ledger
  (`${CLAUDE_PLUGIN_ROOT}/snippets/module-coordination-ledger.md`), and at most 8 weight units are
  in flight - haiku 1, sonnet 2, opus 4, fable 8 (always alone).

## Model-tier selection - the kind of reasoning drives the tier (SSOT)

Every launcher - the main agent, a skill, a spawner or node-owner agent - reads this section by
path before a launch and passes `model` and `effort` explicitly, for a plugin agent and for a
built-in one (Explore, general-purpose) alike. Pick the LOWEST tier whose row matches the
kind of reasoning the work needs. Size is never an input: module count, file count, line count and blast radius do not move a tier.

| tier | pick when the work is |
|------|-----------------------|
| **haiku** | mechanical, or a rule already stated: find and gather over code, OSM, git, GitHub, web; instance build, serve, test, log; CI polling; renames and list-driven deletions; mechanical documentation upkeep (recapturing existing screenshots, relabelling to a changed UI label or menu path, toctree wiring, filling translations that already exist, assembling an App Store page from supplied copy and captures, re-cutting a draft to another channel); recon; a build node whose design block passes the 5.1 checklist; review mode `R1`; acceptance mode `A1A2` when no Given needs a fixture built; comparing observed values with stated expected values |
| **sonnet** (default when unsure) | a rule must be inferred or judged: a build node that fails one 5.1 item; review `R2`; acceptance `A1A2` when a Given needs a fixture built (a multi-company database, a stubbed external service, device emulation, an upgrade database); debugging to a root cause; plan execution and coordination; translation; writing for a human reader; planning; composing new documentation or channel copy (blog, post, email, script) |
| **opus** | design (SRS and design session); any unit whose `business_function` is on the specialist list in `${CLAUDE_PLUGIN_ROOT}/snippets/business-taxonomy.md`; a node that meets 5.2; review `R3`; an App Store landing page or its copy (which claims to make, which to leave out); the one retry a tier up after an evidenced sonnet failure |
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

### Effort - the blast radius drives it

The tier is the kind of reasoning; the effort is how far the agent looks and how hard it checks
before it concludes. Size moves the effort, never the tier. Pick the LOWEST row that matches:

| effort | pick when |
|--------|-----------|
| `low` | mechanical work with its rule stated: find and gather, instance operations, polling, list-driven edits |
| `medium` | the default: a change inside one module and one business function, no recon flag |
| `high` | `recon.md` raised a flag (an inheritance-axis change, an override chain of at least `OVERRIDE_CHAIN_MIN`, at least `DEPENDENTS_MIN` dependents of one symbol, a `noupdate` data file in scope, a stored compute over a many-record relation); the change touches two or more modules or business functions; a design session; review `R2`; debugging to a root cause; writing an acceptance oracle |
| `xhigh` | a unit whose `business_function` is on the specialist list AND a recon flag; a design session whose request names a specialist business function; review `R3` |

`max` is the human's to ask for, never an agent's choice. A launcher with no recon (a debug, a
standalone review) reads the row from the module's business function and from whether the symptom
or the diff crosses modules. The architect writes the effort beside the tier in `build_tier_hint`,
the plan node carries it, the launcher passes it.

### Escalation

On `BLOCKED`, a `NEEDS_JUDGEMENT` line, or a failed own gate: relaunch ONCE, one tier up, passing
the previous attempt's artifacts. Never two tiers at once. A miss of breadth - a dependent module
not examined, a case a review or a test caught outside what the agent looked at - goes one effort
step up at the same tier instead, `xhigh` being the ceiling.

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

A body that can run at haiku: each step has a true-or-false condition; a missing fact is
`UNKNOWN`, never guessed; every claim carries its evidence (an OSM result or `file:line`); a step
that needs judgement writes `NEEDS_JUDGEMENT` and stops; full output goes to a file and the report
returns the path plus a short summary.

### Where a tier is chosen

The launch `model` parameter first, else the agent's frontmatter `model:`, else
`CLAUDE_CODE_SUBAGENT_MODEL`, else the caller's own model. An agent body never states its own
tier. Effort resolves the same way: the launch `effort` parameter, else the agent's frontmatter
`effort:`, else the default of the model it runs on - an agent on another model than its launcher
does not inherit the session's effort. A skill's frontmatter `model:` takes effect for the rest of the current turn once the skill
is invoked; a skill without it runs in the invoking context's model, so wrap a mechanical skill
invoked from an opus or fable context in a haiku or sonnet launch (reason d). `odoo-instance` is
the rule of its own: launch `odoo-instance-ops` at haiku, inline only in that skill's exceptions
(a)-(d).

## OSM session-pin race (`set_active_version` and `set_active_profile`)

Both pins are server-side state of one MCP session that a parent and its subagents share, last
write wins. So every call passes a CONCRETE `odoo_version` and `profile_name`: never `'auto'`,
never an omission, in multi-version and multi-profile flows too. `set_active_version` (and
`set_active_profile` for a tenant profile) is called once at bootstrap as the reachability probe
and never relied on afterwards. An unknown version is a `NEEDS_CONTEXT`.

## Odoo instance allocation (DB / port)

A mutation (tests, `init`, `update`, a throwaway server) never reuses the declared database or
port: another agent or session may hold it. `lease_acquire` mode `ephemeral` gives a database and
ports of your own; `exclusive` gives up isolation (say so in your report); a read-only attach
needs no lease. A refused acquire is not a degrade: follow the remedy of its error code. Protocol:
`${CLAUDE_PLUGIN_ROOT}/snippets/instance-resolution.md` § Allocate; release or park before your
terminal status: `${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T1/T3.

## Browser exclusivity

One driver per browser MCP family at a time (chrome-devtools, playwright, pagecast; headed and
headless count as separate families). Distinct families may run in parallel, RAM permitting, with
at most 2 state-mutating drives at once. Close-before-done:
`${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T2.
