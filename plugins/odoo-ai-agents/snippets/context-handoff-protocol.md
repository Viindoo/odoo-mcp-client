<!-- SSOT snippet. The single home for the 3-tier agent dispatch model (SendMessage-resume /
     fork / fresh-spawn) and its capability probe, fallback matrix, and confidentiality guard.
     Referenced (not copy-pasted) by the orchestrator skills odoo-coding, odoo-code-review, wave,
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
   another agent via the Agent tool and that spawner is still running, you are not the team lead ->
   Tier C for the whole run; a non-lead can still cold-spawn workers via Agent but cannot grow the
   team roster for Tier-A resume)

If ALL four are positive -> Tier A is available for this run. Tier B (fork) is independent of these
four conditions - it requires only that `subagent_type: "fork"` is accepted, not that env or
SendMessage are present. Any negative on conditions 1, 2, or 4 -> use Tier C for the whole run. A
negative on condition 3 alone -> use Tier C for that one worker only.

## Tier A - SendMessage-resume (preferred when the probe is positive)

Spawn each worker ONCE with a stable `name` (e.g. `coder-<module-slug>`, `wi-<slug>-<id>-coder`).
As the LEAD, capture the returned `agentId` and store it in the skill's plan artifact
(plan.md / plan.json) keyed by work-item, so the plan becomes the agentId registry. On the next
iteration, resume that same worker by sending it the new instructions:
`SendMessage({to: "<agentId-or-name>", text: "<shared team context: review findings + worklog pointer>"})`.
The resumed worker keeps its full prior context - it is the mind that wrote the code, not a cold
reader. `SendMessage` returns immediately and parks the worker in the background (see async
park-and-be-resumed below); it is NOT a synchronous reply.

## Tier B - fork (read-heavy fan-outs)

For read-only fan-outs (survey passes, per-commit intent extraction, cluster classification), spawn
each worker with `subagent_type: "fork"`. A fork inherits the parent's full context and shares the
parent's prompt cache, so it skips cold re-grounding. Each fork still writes its OWN findings file -
forks never share mutable state. Use Tier B only where workers do not mutate shared state.

## Tier C - fresh spawn + worklog (always-correct fallback)

The baseline and current behavior: dispatch a fresh worker via the Agent tool with a written brief,
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
Structure every Tier-A exchange as park-and-be-resumed: send, stop, resume on reply.

## Lead is the address authority

A worker does NOT know its own `agentId`. Only the lead that spawned it captures and holds that id.
A two-way exchange therefore closes ONLY if the lead embeds the worker's reply-to id in the prompt it
sends. Workers MUST NOT self-address or assume an id; if a worker needs to reply to a specific peer,
the lead supplies that address explicitly in the brief.

## No nested teams = roster only

"No nested teams" constrains TEAM MEMBERSHIP only: only the lead adds or removes teammates from the
roster. It does NOT stop a non-lead agent from cold-spawning its own subagents via the Agent tool. So
a non-lead orchestrator can still dispatch fresh workers (Tier C) - it simply cannot grow the team
roster for Tier-A resume, which is why probe condition 4 routes non-lead orchestrators to Tier C.

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

Worktree lifecycle (creation, removal, topology changes) is owned exclusively by **git-operator**
(S9 invariant - SSOT in git-toolkit `snippets/git-safety-contract.md`). Tier-A workers do NOT
create or tear down their own worktree - they receive a pre-created worktree path from the
orchestrator, which delegates any worktree mutation to git-operator before dispatching the worker.

However, the shell cwd is NOT guaranteed to be restored across a Tier-A resume. On resume,
immediately `cd` to the assigned worktree path before any Bash command. Put this instruction in
the worker's brief so it holds whether or not the runtime restores cwd.
