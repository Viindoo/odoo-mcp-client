# Continuation contract (the last block of your output)

After your normal output, append one fenced block tagged `continuation`. The plan runner (the main
agent) reads it to decide what runs next; a status or a next step written outside it reaches no
driver.

````
```continuation
status: DONE | NEEDS_NEXT | BLOCKED | NEEDS_CONTEXT
concerns:                     # optional, DONE only: one line per caveat - the dimension and an evidence path
produced: [<path you wrote>, ...]          # [] for chat-only work
next:                         # [] when nothing follows; at least one entry on NEEDS_NEXT
  - skill: <skill or workflow name>
    reason: <why this is next>
    inputs: {<key>: <value>}
    confidence: 0.0..1.0      # under 0.5 the runner offers it as a suggestion
blocked_reason: <required on BLOCKED and NEEDS_CONTEXT, else null>
```
````

- **Four statuses, declared here.** `DONE`: the goal is met; a caveat on finished work is `DONE`
  plus `concerns:`, never another value. `NEEDS_NEXT`: more work should follow; fill `next`.
  `BLOCKED`: you cannot proceed. `NEEDS_CONTEXT`: you need a fact or a decision only your caller or
  the human holds.
- **Your report is three parts, in order:** a short summary of what you did, `produced` (the real
  paths - your evidence), this block. It is delivered once
  (`${CLAUDE_PLUGIN_ROOT}/snippets/spawner-completion-contract.md` R3).
- **You emit `next`; the runner dispatches it.** A front-door skill that drives its own bounded
  loop outside a plan follows its own rule for dispatching its next step; a leaf never dispatches.
- **`DONE` has two preconditions:** every agent you launched returned a terminal status (same
  file, R1 and R2), and every resource this dispatch acquired is returned or handed off by name
  (`${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T0-T4). `BLOCKED` and
  `NEEDS_CONTEXT` owe the same teardown.
- **A non-`DONE` report lets its receiver decide without redoing your work.** `blocked_reason`
  names what you wait on, who or what can unblock it, and what the receiver should do next, each
  with a concrete referent from this turn's work (a file path, a symbol, an error message, a tool
  result). A sentence that would stay true for any other module or task names nothing. When a
  decision is needed, the summary gives the business context, the modules, the facts you verified,
  the options with their trade-offs and your recommendation. A decision your own role owns is
  taken, not returned.
- A turn never ends on "waiting" or "in progress" without this block.
- **Reserved `inputs` keys.** A `next` entry into `odoo-coding`, `odoo-code-review` or
  `odoo-test-writing` carries `odoo_version` (the concrete series) and, when known, `osm_profile`.
