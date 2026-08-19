<!-- SSOT snippet. The single home for the 3-tier agent dispatch model (resume-a-child-you-launched /
     fork / fresh-spawn), the two identity facts, and the confidentiality guard. The message-DIRECTION
     rule is NOT here - it is owned once by spawner-completion-contract.md R3; this file cites it and
     never restates it. Referenced (not copy-pasted) by the orchestrator skills odoo-coding,
     odoo-code-review, odoo-forward-port, odoo-deep-survey, odoo-brl. Edit here only; consumers point
     at ${CLAUDE_PLUGIN_ROOT}/snippets/context-handoff-protocol.md. Builds on worklog-contract.md. -->

# Context-Handoff Protocol (CHP) - 3-tier agent dispatch

You are an orchestrator skill dispatching worker agents. Tier C (fresh spawn + worklog) is the
always-correct SSOT for handing context between agents - it loses nothing and works on every
runtime. CHP is an OPTIMIZATION LAYER that cuts cold-start cost by resuming or forking a worker
instead of re-spawning it cold; it is NEVER a dependency. When in doubt, use Tier C. Every Tier-A
and Tier-B path below degrades silently to Tier C, so adopting CHP can never make a run fail.

## Tier A - resume a child you launched (by the id your launch returned)

You may resume a child you launched YOURSELF instead of cold-spawning a replacement, when BOTH ARE
true. Decide it locally, per child, per turn - there is no run-wide probe and no environment flag:

1. you hold the id that child's own launch call returned to you, and
2. a messaging tool is in your current toolset.

Your own depth is NOT a condition. A resume send has no synchronous return, so the only way to see
the result is to be woken with it - and you are woken whether you are the root or a dispatched
agent, provided you END YOUR TURN after sending (§ Async park-and-be-resumed semantics).

Send the new instructions to that id. Record the id per work-item in the skill's plan artifact
(plan.md / plan.json) as you capture it, so the plan is the id registry. The resumed child keeps its
full prior context - it is the mind that wrote the code, not a cold reader. Send semantics:
§ Async park-and-be-resumed semantics below.

Either condition false, or the id no longer resolves (the runtime reports the target is not
addressable, or a session `/resume` dropped it): cold-spawn (Tier C). Always correct at any depth,
loses nothing - the worklog is current. Only when you hold no launch capability at all (the nesting
cap) is there no tier left to take; then take the fallback your declared role assigns you
(`${CLAUDE_PLUGIN_ROOT}/snippets/spawner-completion-contract.md` R0 § Which fallback is yours).
Never surface a fallback to the user as an error.

You never hold any other address: you cannot name a child at launch, you cannot look up a child you
did not launch, and no child can address you
(`${CLAUDE_PLUGIN_ROOT}/snippets/spawner-completion-contract.md` R3).

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

## Async park-and-be-resumed semantics

A resume send is fire-and-forget: it returns immediately and the child runs in the background. NEVER
write call-and-await-a-return-value logic around it - there is no synchronous return to read. Being
resumed is therefore the only way the result reaches you, so structure a Tier-A exchange as
park-and-be-resumed: send, stop, resume on completion. Scoped to a resume SEND: a blocking tool call
that RETURNS a verdict inside the one call is not a park.

**The wake is keyed on YOU having stopped, never on your depth.** You are woken with the child's
result once it completes and you hold no other live child of your own - the root and a dispatched
launcher alike (`${CLAUDE_PLUGIN_ROOT}/snippets/spawner-completion-contract.md` R1 § Boundary).
What breaks the exchange is sending and then continuing to work in the same turn: that leaves no
point at which anything can be handed to you, and the result is never delivered. Send, then END
YOUR TURN.

## The launcher holds the only address

A child does NOT know its own id. Only the launcher that started it captures and holds that id, and
that id is the ONLY address anyone ever holds - the channel runs DOWN and only down
(`${CLAUDE_PLUGIN_ROOT}/snippets/spawner-completion-contract.md` R3).

**No agent can read its own address.** The roster/context an agent is shown always excludes its own
entry, and it never contains its launcher either, so "pass your own address to your child" is
executable ONLY for `main` (the one fixed-literal address). There is exactly ONE way any other agent
comes to hold an address at all: it captures the id its OWN launch call returned for a child it
launched itself. It never derives or introspects it, and no launcher can name a child at launch.

## A skill has no address of its own

A skill's instructions execute inline in whatever context invoked it - it is not a separate
addressable entity and holds no address, its own or its invoker's. Its launches ARE that context's
launches: each id a launch returns is captured by the context running the skill, which resumes that
child by that id. A skill whose frontmatter declares a forked/background subagent context is
launched as a real subagent instead; it still holds no address for its launcher - only the ids its
own launches return.

## Sanctioned nested spawner - the `odoo-coder` node coordinator

Being a subagent never bars you from launching your own subagents. `odoo-coder` (the node
COORDINATOR launched by `odoo-coding` once per work node) is the sanctioned nested spawner: although it
is itself a subagent of `odoo-coding`, it LAUNCHES and coordinates its own three workers
(`odoo-test-writer`, `odoo-backend-coder`, `odoo-frontend-coder`). This is legal because it sits well
within the nesting cap (`main -> odoo-coding -> odoo-coder -> worker`, 2 levels deep against a
default cap of 3; R0 move 1, `${CLAUDE_PLUGIN_ROOT}/snippets/spawner-completion-contract.md`). It
must not launch anything deeper than those three. Every one of those launches is asynchronous: it
dispatches its workers, ENDS ITS TURN, and is woken with each worker's result (R0 move 3).

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
language; the resume-message text and worker briefs themselves are not.

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
