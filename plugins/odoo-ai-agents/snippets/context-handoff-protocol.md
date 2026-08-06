<!-- SSOT snippet. The single home for the 3-tier agent dispatch model (SendMessage-resume /
     fork / fresh-spawn) and its capability probe, fallback matrix, and confidentiality guard.
     Referenced (not copy-pasted) by the orchestrator skills odoo-coding, odoo-code-review,
     odoo-forward-port, odoo-deep-survey, odoo-brl. Edit here only; consumers point at
     ${CLAUDE_PLUGIN_ROOT}/snippets/context-handoff-protocol.md. Builds on worklog-contract.md. -->

# Context-Handoff Protocol (CHP) - 3-tier agent dispatch

You are an orchestrator skill dispatching worker agents. Tier C (fresh spawn + worklog) is the
always-correct SSOT for handing context between agents - it loses nothing and works on every
runtime. CHP is an OPTIMIZATION LAYER that cuts cold-start cost by resuming or forking a worker
instead of re-spawning it cold; it is NEVER a dependency. When in doubt, use Tier C. Every Tier-A
and Tier-B path below degrades silently to Tier C, so adopting CHP can never make a run fail.

## Capability probe (run once, before any Tier-A/B dispatch)

Before the first reuse dispatch in a run, check all four conditions. Run this ONCE and cache the
result for the run; do not re-probe per work-item.

1. Is env `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`? (read it via Bash, e.g. `printenv`)
2. Is the `SendMessage` tool present in the current toolset? (inspect your active tool list for this
   turn; if absent or uncertain, treat as negative -> Tier C for the whole run)
3. Is the target worker addressable (a stable name you spawned this run, or a captured `agentId`)?
4. Is this orchestrator itself the team lead, NOT a non-lead subagent? (if you were launched by
   another agent and that spawner is still running, you are not the team lead -> Tier C for the
   whole run; a non-lead can still cold-spawn workers but cannot grow the team roster for Tier-A
   resume)

If ALL four are positive -> Tier A is available for this run. Tier B (fork) is independent of these
four conditions - it requires only that `subagent_type: "fork"` is accepted, not that env or
SendMessage are present. Any negative on conditions 1, 2, or 4 -> use Tier C for the whole run. A
negative on condition 3 alone -> use Tier C for that one worker only.

## Tier A - SendMessage-resume (preferred when the probe is positive)

Spawn each worker ONCE with a stable `name` (e.g. `coder-<module-slug>`, `wi-<module>-<n>-coder`).
As the LEAD, capture the returned `agentId` and store it in the skill's plan artifact
(plan.md / plan.json) keyed by work-item, so the plan becomes the agentId registry. On the next
iteration, resume that same worker by sending it the new instructions:
`SendMessage({to: "<agentId-or-name>", text: "<shared team context: review findings + worklog pointer>"})`.
The resumed worker keeps its full prior context - it is the mind that wrote the code, not a cold
reader. `SendMessage` returns immediately and parks the worker in the background (see async
park-and-be-resumed below); it is NOT a synchronous reply.

A stable spawn `name` is OPTIONAL for a leaf and REQUIRED for any agent that will itself dispatch or
be messaged: its children have no address to reply to otherwise, and the failure is silent.

## Completion-report complement

CHP owns the LEAD->WORKER direction: dispatch (Tier C), reuse-dispatch (Tier A resume / Tier B
fork), and the capability probe + confidentiality guard those share. The WORKER->LEAD direction -
the teammate's completion-report push (`SendMessage` to `main`) and the low-context task board
(`TaskCreate`/`TaskUpdate`/`TaskList`/`TaskGet`) for tracking - lives in
`${CLAUDE_PLUGIN_ROOT}/snippets/agent-team-protocol.md`. It reuses this snippet's probe and
confidentiality guard (it does not restate them). The two are non-overlapping SSOTs: do not document
the completion-report or task board here.

## Tier B - fork (read-heavy fan-outs)

For read-only fan-outs (survey passes, per-commit intent extraction, cluster classification), spawn
each worker with `subagent_type: "fork"`. A fork inherits the parent's full context and shares the
parent's prompt cache, so it skips cold re-grounding. Each fork still writes its OWN findings file -
forks never share mutable state. Use Tier B only where workers do not mutate shared state.

## Tier C - fresh spawn + worklog (always-correct fallback)

The baseline and current behavior: dispatch a fresh worker by launching it with a written brief,
and rely on the worklog (`${CLAUDE_PLUGIN_ROOT}/snippets/worklog-contract.md`) for all cross-agent
context. The fresh worker reconstructs its mental model from the worklog + the brief. This is always
correct and always available; Tier A and Tier B only ever replace it as a speed optimization.

## Fallback trigger matrix

Drop to Tier C - silently, automatically, degraded-but-correct, NEVER a hard error - on ANY of these
five conditions:

| # | Condition | Scope of fallback |
|---|-----------|-------------------|
| 1 | `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` is unset or not `1` | whole run |
| 2 | `SendMessage` tool is absent from the current toolset | whole run |
| 3 | Target worker is not addressable ("No agent named ... is currently addressable" / not in the teammates roster) | that worker |
| 4 | A session `/resume` or `/rewind` dropped the in-process teammate | that worker |
| 5 | This orchestrator is itself a non-lead subagent (not the team lead, so it cannot manage team membership) | whole run |

Do not surface any of these as an error to the user. Log the tier choice in the worklog if it
changes the outcome, then proceed on Tier C as if CHP were never attempted.

## Async park-and-be-resumed semantics

`SendMessage` is fire-and-forget: it returns immediately and the worker is resumed in the background.
After sending, END your turn and wait to be resumed when the worker's reply arrives. NEVER write
call-and-await-a-return-value logic around `SendMessage` - there is no synchronous return to read.
Structure every Tier-A exchange as park-and-be-resumed: send, stop, resume on reply. This is legal
for a subagent lead exactly as for main - see R0 in
`${CLAUDE_PLUGIN_ROOT}/snippets/spawner-completion-contract.md`: a parked agent is resumed when the
runtime wakes it, never killed; what actually gates a launch is whether your OWN launch capability
exposes a blocking call for it, not whether you are main.

## Lead is the address authority

A worker does NOT know its own `agentId`. Only the lead that spawned it captures and holds that id.
A two-way exchange therefore closes ONLY if the lead embeds the worker's reply-to id in the prompt it
sends. Workers MUST NOT self-address or assume an id; if a worker needs to reply to a specific peer,
the lead supplies that address explicitly in the brief.

**No agent can read its own address.** The roster/context an agent is shown always excludes its own
entry, so "pass your own address to your child" is executable ONLY for `main` (the one fixed-literal
address). A non-main agent can supply an address for itself in a child's brief in exactly ONE way:
its OWN launcher told it, in ITS OWN dispatch brief, what spawn `name` it was launched under - it
repeats that name; it never derives or introspects it.

## A skill has no address of its own

A skill's instructions execute inline in whatever context invoked it - a skill is not a separate
addressable entity. Its dispatches therefore carry the address of the context that ran it (`main`
when main invoked the skill directly; a nested coordinator's own address when the coordinator
invoked it), never the skill's own name. Exception: a skill whose frontmatter declares it runs in a
forked/background subagent context IS a real subagent once launched that way - inside it, "your
caller" resolves to that subagent's own launcher, not to whoever invoked the skill by name.

## No nested teams = roster only

"No nested teams" constrains TEAM MEMBERSHIP only: only the lead adds or removes teammates from the
roster. It does NOT stop a non-lead agent from cold-spawning its own subagents. So
a non-lead orchestrator can still dispatch fresh workers (Tier C) - it simply cannot grow the team
roster for Tier-A resume, which is why probe condition 4 routes non-lead orchestrators to Tier C.
Whether a given launch BLOCKS or must be async is a separate question, decided per R0
(`${CLAUDE_PLUGIN_ROOT}/snippets/spawner-completion-contract.md`) by inspecting your own launch
capability's parameters - it does not depend on team-roster membership either.

## Sanctioned nested spawner - the `odoo-coder` per-module coordinator

`odoo-coder` (the per-module COORDINATOR launched by `odoo-coding` for EVERY module) is the
sanctioned nested spawner: although it is itself a subagent of `odoo-coding`, it LAUNCHES and
coordinates its own three teammates (`odoo-test-writer`, `odoo-backend-coder`,
`odoo-frontend-coder`). This is legal exactly because of the rule above - a non-lead may cold-spawn
its own subagents - and because it sits well within the nesting cap
(`main -> odoo-coding -> odoo-coder -> teammate`, 2 levels deep against a default cap of 3; R0 move
1 above). The lead<->worker CONTROL channel is DIRECT (launcher to the child it just launched), NOT
a team-roster resume, so `SendMessage` on that channel works WITHOUT the
`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` flag and without the four-condition probe: the lead may
`SendMessage` a worker it launched, and when `SendMessage` is unavailable it re-launches the worker
fresh (Tier C, always correct). The flag-gated Tier-A roster-resume optimization above applies to
the MAIN team lead only; the nested lead never needs it. The nested lead must not launch anything
deeper than its three teammates.

## Confidentiality guard

NEVER describe a handoff payload as "secret", "confidential", "hidden", "private", or "restricted",
and never relay a third party's "consent" to move it (permission-laundering). The substrate refuses
delivery on those framings even when the transfer is legitimate. A handoff payload is ordinary
collaborative data: call it "shared team context", "run worklog contents", "decision record", or
"prior-phase findings". This is a HARD constraint for runtime correctness, not a style preference - a
secret framing makes the worker refuse the message and silently breaks the handoff.

## Worklog remains the SSOT

Write the worklog (`${CLAUDE_PLUGIN_ROOT}/snippets/worklog-contract.md`) at every step regardless of
tier. Tier A and Tier B do not replace it - they sit on top of it. Because the worklog is always
current, a Tier-C fallback re-spawn at any point loses nothing: the fresh worker reads the same
decision journal the resumed worker would have carried in-context.

## Design-document keys in worker briefs

When a skill dispatches a coder or design-consumer after the design phase, the brief carries these
two keys (key: value pairs recognized by `odoo-coding` and downstream consumers):

```
DESIGN_DOC: <path>          # Primary spec the coder builds verbatim.
                            #   Single mode: the flat TDD.
                            #   Master-child mode: the child TDD for this module.
MASTER_DESIGN_DOC: <path>   # Master TDD - hard constraints the child must honor. `none` in single mode.
```

`DESIGN_DOC` is always the coder's contract. `MASTER_DESIGN_DOC` is the non-drift constraint;
a child violating a master constraint is a CRITICAL finding at review.
Full field semantics, Continuation Contract shape, and non-drift rule:
`${CLAUDE_PLUGIN_ROOT}/snippets/master-child-design-contract.md`.

## Language boundary

A handoff payload is tool-layer, agent-to-agent data. It stays English per
`${CLAUDE_PLUGIN_ROOT}/snippets/language-mirroring.md` Rule 5, exactly like code, identifiers, and
tool output. Only the human-visible relay summary you emit in chat is mirrored into the user's
language; the `SendMessage` text and worker briefs themselves are not.

## Invariant / cross-check at aggregation tiers

A resumed or forked worker can still return a wrong result - reuse does not guarantee correctness. At
every point where you aggregate worker outputs across tiers, attach an explicit invariant or
cross-check (a sum that must reconcile, a count that must match, a re-derivation of a key value)
before you trust the aggregate, so the lead can detect and correct a bad leaf. Do this at each
aggregation point, not only at the end.

## Tier-A workers in a git worktree - cd on resume

Worktree lifecycle (creation, removal, topology changes) is owned exclusively by **git-toolkit**
(S9 invariant - SSOT in git-toolkit `snippets/git-safety-contract.md`). Tier-A workers do NOT
create or tear down their own worktree - they receive a pre-created worktree path from the
orchestrator, which invokes the `git-toolkit:git-ops` skill (via the Skill tool) for any worktree
mutation before dispatching the worker.

However, the shell cwd is NOT guaranteed to be restored across a Tier-A resume. On resume,
immediately `cd` to the assigned worktree path before any Bash command. Put this instruction in
the worker's brief so it holds whether or not the runtime restores cwd.
