<!-- SSOT snippet. The single source for the Continuation Contract that every skill/agent
     emits at the end of its output so run-driver can advance a drive-to-done run. Referenced
     via ${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md instead of pasting the block
     into 31 SKILL.md + 4 agent files. Full rationale + schema: docs/reference/workflow-harness.md §8. -->

# Continuation Contract (emit at the very end of your output)

After your normal output (the artifact/answer this step produces), append ONE fenced block
tagged `continuation`. It is a machine-readable handoff the `run-driver` reads to
decide what runs next. It does NOT replace or alter anything above it - it is purely additive.

````
```continuation
status: DONE | NEEDS_NEXT | BLOCKED | NEEDS_CONTEXT
produced: [<real artifact path>, ...]      # files you actually wrote; [] for chat-only
next:                                       # [] unless status == NEEDS_NEXT
  - skill: <skill-or-workflow-name>
    reason: <why this is the next step>
    inputs: {<key>: <value>}
    confidence: 0.0..1.0                     # <0.5 ⇒ driver surfaces it as a suggestion, not auto-run
    risk_level: L0 | L1 | L2
blocked_reason: <non-null iff status in {BLOCKED, NEEDS_CONTEXT}>
```
````

Rules:
- **You only EMIT this - you never dispatch the next step yourself.** Advancing is the
  run-driver's job (a skill/agent emitting a contract must not self-dispatch the next spawner -
  that is the run-driver's job). See `${CLAUDE_PLUGIN_ROOT}/snippets/worker-brief.md`.
- `status: DONE` when the run's goal is met; `NEEDS_NEXT` when more work should follow (fill
  `next`); `BLOCKED` when you cannot proceed; `NEEDS_CONTEXT` when you need a human decision.
- `produced` is your evidence (Completion-status #8) - list the real paths you wrote.
- `risk_level`: L0 read-only/chat · L1 writes internal `.odoo-ai/` files · L2
  irreversible/outward (touches an instance, git push/merge, sends to a third party). When
  unsure, pick the higher tier.
- Outside an active run this block is harmless - it just documents suggested next steps.
- Back-compat: a legacy `SUGGESTED_NEXT: <skill> (reason=…, target=…)` line is still read by
  the driver as a low-confidence `NEEDS_NEXT`; prefer the fenced block going forward.
