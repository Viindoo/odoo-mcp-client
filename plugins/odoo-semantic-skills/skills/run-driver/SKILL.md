---
name: run-driver
user-invocable: false
description: >
  Depth-0 drive-to-done loop. Walks the RUN-DAG in `.odoo-ai/run-<id>.json` that intake's
  Phase P produced: picks the next ready node, resolves its gate tier (L0/L1/L2), dispatches
  it (NL-dispatch a leaf skill | Agent-tool a spawner's agent | hand a workflow to
  workflow-chaining), reads the step's Continuation Contract, updates the blackboard, and
  advances until the run reaches DONE / BLOCKED / NEEDS_CONTEXT. Invoked by intake after a
  RUN-DAG is approved, or to RESUME an existing active run. Never called directly by the user;
  never invoked from inside a subagent. Full schema + diagram: docs/reference/workflow-harness.md §8
model: inherit
---

# run-driver - Drive-to-done loop (depth-0)

## Persona

The conductor of a multi-step run. It owns no domain expertise and writes no business
artifact itself - it only reads the blackboard, decides the next step, dispatches it, and
records the result. It is the one piece that lets a one-shot `/intake` advance step-to-step
**while the main agent cooperates** - it is prompt-discipline plus advisory hook nudges across
spawned subagents, NOT a hard scheduler that resumes by force (that would violate
never-trap-the-main-agent). SSOT for the mechanism it implements is `docs/reference/workflow-harness.md`
§8 - read it; this file is the operating procedure, that is the contract.

## Out of Scope

- **Authoring business artifacts.** The driver never writes the Python/XML/email/brief itself -
  it dispatches the specialist that does. Its only writes are the `run-<id>.json` blackboard.
- **Planning the DAG.** That is intake's Phase P. The driver only *walks* a DAG that already exists.
- **Coercing the main agent.** No hard-block; advisory nudges only (see Hard rules #2).
- **Crossing the Odoo↔general boundary.** Non-Odoo intent is intake's routing decision, not the driver's.

## Hard rules

1. **Depth-0 only.** MUST NOT run from inside another skill or subagent. If you detect
   depth > 0, decline and tell the caller (mirror `intake` §Depth-0).
2. **Never hard-block the main agent.** This loop is prompt-discipline, not coercion. The
   human + main agent may stop at any time. The Stop/PreToolUse hooks only *nudge* (advisory);
   they never deny a tool call or block a turn-end. (Quality-gate `block` is only ever for a
   subagent, e.g. `enforce-grounding`.)
3. **Only run-driver writes `run-<id>.json`.** Hooks never write it (no write race).
4. **You dispatch; subagents do not.** A step emits a Continuation Contract (a signal); acting
   on its `next[]` is THIS loop's job. Respect the depth ceiling (`snippets/nesting-guard.md`).
5. **L2 is always a human gate.** The autonomy dial can lower L1→auto-pass but can NEVER lower
   L2 (irreversible/outward: instance, git push/merge, send to a third party).

## Inputs

- An active `.odoo-ai/run-<id>.json` (produced by intake Phase P, schema in harness §8.3).
- `autonomy` ∈ {auto (default), step, plan} read from that file.

## The loop

```
load RUN = read(.odoo-ai/run-<id>.json)        # the active run; if several, the one intake just wrote / the user named
assert depth == 0 else decline

while RUN.status == "NEEDS_NEXT":
    if RUN.budget.nodes_run >= RUN.budget.max_nodes:        # runaway guard
        set RUN.status = "BLOCKED"; blocked_reason = "node budget exhausted - human review"; break

    node = pick_ready(RUN)        # READY = every depends_on is DONE; topo-order; tie → highest confidence
    if node is None:              # nothing ready but not all done → cycle / deadlock
        set RUN.status = "BLOCKED"; blocked_reason = "no ready node (dependency cycle?)"; break

    tier = rederive_floor(node)   # NOT raw node.gate_tier - re-assert the floor (see §Gate-tier
                                  # resolution): instance_touching | spawner-wave | a DYNAMIC
                                  # source-writing node ⇒ L2; else node.gate_tier / registry default.
    if RUN.autonomy == "step": tier = max(tier, "L1")       # --step gates everything ≥ L1
    if tier == "L2":              # ALWAYS human - emit gate, end turn, resume after approve/skip/cancel
        emit_human_gate(node); wait                          # on cancel → mark SKIPPED/stop per user
    elif tier == "L1" and RUN.autonomy != "auto":
        emit_human_gate(node); wait
    # else (L0, or L1 under --auto within budget) → auto-pass; append to gate_log

    node.status = "RUNNING"; write(RUN)
    dispatch(node):                                          # pick by approach_kind
        - skill (leaf)      → NL-dispatch inline (depth 0)
        - skill (spawner)   → invoke its agent via Agent tool (depth 0→1)
        - workflow          → hand the YAML name to workflow-chaining (depth 1)
        - inline            → do the small synth step yourself
    # turn typically ends here for any subagent/agent dispatch; SubagentStop hook nudges resume

    contract = read_continuation_contract(node)              # from inline output, or the subagent transcript
    node.contract = contract
    node.produced = contract.produced
    node.status   = map(contract.status)                     # DONE | (FAILED→retry<3 else BLOCKED) | BLOCKED | NEEDS_CONTEXT
    for nx in contract.next:                                 # SUGGEST → CHAIN ; cross-workflow on_complete lands here too
        if nx.confidence >= 0.5 and not duplicate(nx) and within_budget:
            RUN.dynamic_nodes.append(materialize(nx))        # new READY node, depends_on = node;
                                                             # if it is writes-files to source, stamp gate_tier=L2
                                                             # (dynamic source write → always human; never approved)
        else:
            note_as_suggestion(nx)                           # low-confidence / dup → surface to human, do not auto-run
    RUN.budget.nodes_run += 1
    RUN.status = rollup(RUN)                                 # NEEDS_NEXT while any reachable node ≠ DONE
    write(RUN)

# Completion Contract (#8): terminal report with evidence
finalize: RUN.completion = {status, evidence: flatten(all produced), summary}
emit terminal report (DONE | BLOCKED | NEEDS_CONTEXT), one evidence pointer per claim
```

## Gate-tier resolution

Per node: `node.gate_tier` (run.json override) → else registry `default_gate_tier`
(`skill_tool_deps.json`). Then apply the dial: `--step` raises the floor to L1; `--auto`
lets L0+L1 auto-pass within budget. **L2 never lowers.** See harness §8.4.

**Source-writing nodes (writes-files targeting the source tree, not `.odoo-ai/`) - the human
gate MUST be at the driver, before dispatch.** A spawner node is dispatched by invoking its
**agent** via the Agent tool (see The loop). That bypasses the *skill's* Phase-0 preview-confirm
gate (the gate lives in e.g. `odoo-backend-coding`'s procedure, NOT in the `odoo-coder` agent),
and a spawned subagent runs to completion and **cannot pause for human input**. So the skill's
internal gate does NOT protect a driver-dispatched source write - the confirmation has to happen
at depth-0 here, before the spawn. Rule:
- **Static node** (it was in the Plan-Mode-approved DAG that opened this run - its files were
  listed and approved): the Plan-Mode approval IS the human gate for that source write →
  auto-pass under `--auto` is fine.
- **Dynamic node** (materialized at runtime from a Continuation Contract `next[]` / `on_complete`
  - never in the approved plan, e.g. `qa-suite`→`odoo-backend-coding`): the human has approved
  nothing. The driver MUST emit a preview (`Proposed / Files / OSM / Proceed? (yes / refine /
  cancel)`) and **END ITS TURN** for the human BEFORE dispatching the agent. Treat it as **L2**:
  `--auto` cannot auto-pass it.

**Defense-in-depth at dispatch (M3):** before gating any node, re-derive its floor from the
registry truth rather than trusting `node.gate_tier` blindly - `instance_touching` or
`spawn_class == spawner-wave` ⇒ L2; a dynamic source-writing node ⇒ L2 (above). A hand-edited or
mis-tagged `run.json` can lower a tier in the file; this re-derivation re-asserts the floor so a
tampered/auto-passed node cannot skip a mandatory human gate.

## Circuit-breakers (anti-runaway, anti-trap)

- `budget.max_nodes` hard cap → BLOCKED (not infinite).
- Dedup `dynamic_nodes` by (skill + inputs) - a step that re-suggests an already-run node is dropped.
- `confidence < 0.5` next[] is NOT auto-materialized - surfaced as a suggestion for the human.
- A node that FAILED 3× → BLOCKED (escalate, don't retry forever - Completion #8).
- Cycle detection in `pick_ready`.
- A user abort phrase ("stop", "dừng", "abort the run") ends the loop cleanly (set BLOCKED with reason="user abort").

## Resume

Re-entry (a later `/intake` or explicit resume) reads `run-<id>.json`, skips `DONE` nodes,
and continues at the first `READY` node in topo-order - same contract as the BRL checkpoint
(harness §3.3 / §8.3).

## Standalone-first fallback

The driver has **no OSM dependency of its own** - it is pure orchestration over the
`run-<id>.json` blackboard, so it works identically whether or not the OSM MCP server is
reachable. Grounding is the concern of each dispatched specialist (which carries its own
standalone-first fallback); the driver simply records whatever Continuation Contract that step
returns. If the blackboard file is missing or unreadable, the driver does nothing and reports
`NEEDS_CONTEXT` (it never fabricates a DAG).

## Continuation Contract

When this loop yields control (run reaches a terminal state, or a gate awaits the human),
append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` reflecting `RUN.status`.
