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
    risk_level: L0 | L1 | L2
blocked_reason: <non-null iff status in {BLOCKED, NEEDS_CONTEXT}>
```
````

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
  `${CLAUDE_PLUGIN_ROOT}/snippets/spawner-completion-contract.md` R1/R2. Different guarantee from
  'you never dispatch the next step yourself'; both hold.
- `status: DONE` when the run's goal is met; `NEEDS_NEXT` when more work should follow (fill
  `next`); `BLOCKED` when you cannot proceed; `NEEDS_CONTEXT` when you need a human decision.
- **Teardown gate on every terminal status.** `DONE` (and `BLOCKED`/`NEEDS_CONTEXT`) is legal
  only after the resources this dispatch acquired are returned - browser pages/recordings you
  opened CLOSED, self-provisioned instance leases RELEASED (or explicitly handed off by
  name). Full rule: `${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T0-T4.
- `produced` is your evidence (Completion-status #8) - list the real paths you wrote.
- `risk_level`: L0 read-only/chat · L1 writes internal state (Tier-2 SHARE/ISOLATE `.odoo-ai/`-rooted
  files, resolved per `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md` - never a
  project-relative `./.odoo-ai/`) · L2 irreversible/outward (touches an instance, git push/merge,
  sends to a third party). When unsure, pick the higher tier.
- Outside an active run this block is harmless - it just documents suggested next steps.
- Back-compat: a legacy `SUGGESTED_NEXT: <skill> (reason=…, target=…)` line is still read by
  the driver as a low-confidence `NEEDS_NEXT`; prefer the fenced block going forward. **Superseded
  for `odoo-backend-coder`, `odoo-frontend-coder`, `odoo-code-reviewer`, and `odoo-instance-ops`**
  (V-34): these four now emit their conditional follow-up (a UI-review suggestion, a code-agent
  handoff) as an in-block `next:` entry instead - a bare `SUGGESTED_NEXT:` line was silently
  dropped whenever the fenced block ALSO set a status (the parser's back-compat branch only reads
  `SUGGESTED_NEXT` when `status` is empty, `parse-continuation.sh:46`), and all four always emit a
  fenced block. Do not emit both channels for these four agents - the in-block `next:` is the only
  one the parser is guaranteed to see.
- **Reserved `inputs` keys.** `inputs` stays free-form, but `odoo_version` (concrete series) and
  `viindoo_profile` are RESERVED: any `next:` hop into a code/test/review skill (`odoo-coding`,
  `odoo-code-review`, `odoo-test-writing`) MUST carry `odoo_version` in `inputs` so
  the version survives the handoff structurally, not by the next skill re-deriving it.
