<!-- SSOT snippet. The single source for the Continuation Contract that every skill/agent
     emits at the end of its output so run-harness can advance a drive-to-done run. Referenced
     via ${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md instead of pasting the block
     into every SKILL.md and agent file that emits a continuation contract - grep the plugin
     tree for the literal path `snippets/continuation-contract.md` to enumerate the current set
     (spans SKILL.md and agents/*.md; the set grows as skills/agents are added, so this comment
     states no count of its own). Full rationale + schema: docs/reference/workflow-harness.md §8. -->

# Continuation Contract (emit at the very end of your output)

After your normal output (the artifact/answer this step produces), append ONE fenced block
tagged `continuation`. It is a machine-readable handoff the `run-harness` reads to
decide what runs next. It does NOT replace or alter anything above it - it is purely additive.

````
```continuation
status: DONE | NEEDS_NEXT | BLOCKED | NEEDS_CONTEXT
concerns:                                   # OPTIONAL, DONE only: one line per caveat on an
                                             # otherwise-complete run - each names the dimension
                                             # and an evidence path (log/artifact/finding). [] or
                                             # omit when there is nothing to flag. See Rules below.
produced: [<real artifact path>, ...]      # files you actually wrote; [] for chat-only
next:                                       # [] when nothing to add; REQUIRED (>=1 entry) on
                                             # NEEDS_NEXT; DONE MAY also carry a low-confidence
                                             # (<0.5) advisory entry - the driver's "materialize
                                             # next[] -> dynamic node" step (workflow-harness.md
                                             # §8.1) reads next[] regardless of your own status
  - skill: <skill-or-workflow-name>
    reason: <why this is the next step>
    inputs: {<key>: <value>}                 # odoo_version, viindoo_profile are RESERVED - see Rules
    confidence: 0.0..1.0                     # <0.5 ⇒ driver surfaces it as a suggestion, not auto-run
blocked_reason: <non-null iff status in {BLOCKED, NEEDS_CONTEXT}>
```
````

`status` has exactly four values: `DONE`, `NEEDS_NEXT`, `BLOCKED`, `NEEDS_CONTEXT`.

`DONE_WITH_CONCERNS` is NOT one of them. To report a caveat on completed work, emit `status: DONE`
plus a `concerns:` list - one line per caveat, each naming the dimension and an evidence path. A
driver schedules `DONE` + `concerns` as DONE and surfaces the list. (ODOO-AI-ETHOS #10's
`DONE_WITH_CONCERNS` is a different field - a human-facing self-report, not this DAG signal.)

This is the ONE declaring file for `status` (`continuation_status`) and its `concerns:` qualifier;
every other file in this plugin that mentions either POINTS here rather than restating the values -
`${CLAUDE_PLUGIN_ROOT}/snippets/vocabulary.md` indexes it alongside the gate-reply sets and the
other overloaded terms.

Rules:
- **You only EMIT this - you never dispatch the next step yourself, with one narrow category
  exception.** Advancing ANOTHER agent's `next` is always the driver's (run-harness's) job. The
  exception: a front-door ORCHESTRATOR skill that drives its OWN bounded next/fix loop when it is
  NOT running as a run-harness node MAY self-dispatch its next spawner - its own instructions carry
  the exact condition and iteration bound for doing so. A leaf worker/agent NEVER self-dispatches.
  See `${CLAUDE_PLUGIN_ROOT}/snippets/worker-brief.md`.
- **Spawner completion barrier (distinct from the no-self-dispatch rule above).** If you launched
  any agent this turn, `status: DONE` is legal only when every child you launched returned
  DONE/BLOCKED; while a child runs you are not done. Full rule:
  `${CLAUDE_PLUGIN_ROOT}/snippets/spawner-completion-contract.md` R1/R2.
- `status: DONE` when the run's goal is met (add `concerns:` when a caveat remains worth
  flagging - never a fifth status value); `NEEDS_NEXT` when more work should follow (fill
  `next`); `BLOCKED` when you cannot proceed; `NEEDS_CONTEXT` when you need a human decision.
- **Teardown gate on every terminal status.** `DONE` (and `BLOCKED`/`NEEDS_CONTEXT`) is legal
  only after the resources this dispatch acquired are returned - browser pages/recordings you
  opened CLOSED, self-provisioned instance leases RELEASED (or explicitly handed off by
  name). Full rule: `${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T0-T4.
- **Completion report is three parts, always - not only in Agent Team mode.** ODOO-AI-ETHOS #10
  (Completion Status) is cited here ONLY for the general evidence-over-assertion principle it
  states for every domain - it is NOT the authority for the four-value `status` enum above, which
  this file declares in its own right and which diverges from ETHOS #10's own value set (see the
  `DONE_WITH_CONCERNS` note above). Your output, in order, is
  (a) a SHORT prose summary of what you did, (b) `produced` - the real artifact paths as your
  evidence, (c) this fenced `continuation` block. This holds whether your final message IS the
  report (no `SendMessage` in your toolset) or is pushed via `SendMessage` per
  `${CLAUDE_PLUGIN_ROOT}/snippets/agent-team-protocol.md` Ask 1, which reuses this exact 3-part
  shape rather than defining its own.
- `produced` is your evidence (ODOO-AI-ETHOS #10) - list the real paths you wrote.
- **"Waiting" is never a bare statement, and a technically-shaped `blocked_reason` is not
  automatically a real one.** `status` has no `waiting` value by design - a genuine pause IS
  `BLOCKED` or `NEEDS_CONTEXT`, with `blocked_reason` naming (a) what you are waiting on, (b) who
  or what can unblock it, and (c) what the caller should do next - AND each of (a)-(c) MUST cite a
  concrete, checkable referent from THIS turn's actual work (a specific file path, symbol/field/
  method name, error message, or tool-call result you already produced), never a generic
  paraphrase of the category ("missing information", "the coordinator", "more context", "additional
  detail"). **Decidability check (apply it):** if you could swap in a different module, task, or
  caller and the sentence would read equally true unchanged, it names nothing and fails this rule -
  a `blocked_reason` that could be copy-pasted verbatim into any OTHER agent's report on any OTHER
  module without becoming false is, by construction, ungrounded. Ending a turn on an unqualified
  "waiting"/"in progress"/"standing by" sentence with none of (a)-(c) named, a `blocked_reason` that
  fails the copy-paste check, or with no `continuation` block at all, is a protocol violation.
- Outside an active run this block is harmless - it just documents suggested next steps.
- Back-compat: a legacy `SUGGESTED_NEXT: <skill> (reason=…, target=…)` line is still read by
  the driver as a low-confidence `NEEDS_NEXT`; prefer the fenced block going forward. Superseded
  for `odoo-backend-coder`, `odoo-frontend-coder`, `odoo-code-reviewer`, and `odoo-instance-ops`:
  these four emit their conditional follow-up as an in-block `next:` entry instead - never both
  channels (the parser's back-compat branch only reads `SUGGESTED_NEXT` when `status` is empty,
  `parse-continuation.sh:46`, so a bare `SUGGESTED_NEXT:` line is silently dropped once the fenced
  block also sets a status).
- **Reserved `inputs` keys.** `inputs` stays free-form, but `odoo_version` (concrete series) and
  `viindoo_profile` are RESERVED: any `next:` hop into a code/test/review skill (`odoo-coding`,
  `odoo-code-review`, `odoo-test-writing`) MUST carry `odoo_version` in `inputs` so
  the version survives the handoff structurally, not by the next skill re-deriving it.
