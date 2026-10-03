<!-- Reference material for snippets/continuation-contract.md. This file is for humans and authors
     doing repo archaeology - it is never cited from any consumer-facing skill/agent/snippet body
     (see docs/authoring-skills-and-agents.md). Explanation and worked examples only; every
     decidable rule stays in the main file. -->

# Continuation Contract - rationale

## Why the 3-part report shape is stated once, here, and only pointed at elsewhere

A second file used to re-enumerate the 3-part shape (prose summary / produced / continuation block)
alongside a now-retired transport rule - a driftable copy of the same content. This file is the sole
declaring SSOT for the shape, and the shape is unconditional. How the report travels is not part of
the shape: it has exactly one home, spawner-completion-contract.md R3, so the shape and the
transport can change independently without either copy drifting.

## Why the `SUGGESTED_NEXT:` back-compat superseding matters

Before the fix, four agents (`odoo-backend-coder`, `odoo-frontend-coder`, `odoo-code-reviewer`,
`odoo-instance-ops`) emitted a bare `SUGGESTED_NEXT:` line for a conditional follow-up (a
UI-review suggestion, a code-agent handoff) ALONGSIDE the fenced `continuation` block. Because the
driver reads `SUGGESTED_NEXT` only while the fenced block's own `status` is empty, the suggestion
was silently dropped every time - the fenced block always set a status, so the bare line never
actually reached the driver. Moving the suggestion into the fenced
block's `next:` array closed that silent drop.
