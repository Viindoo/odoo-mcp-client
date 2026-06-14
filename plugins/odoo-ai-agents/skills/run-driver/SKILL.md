---
name: run-driver
user-invocable: false
description: >
  Depth-0 drive-to-done loop. Walks the RUN-DAG in `.odoo-ai/run-<id>.json` that intake's
  Phase P produced: picks the next ready node, resolves its gate tier (L0/L1/L2), dispatches
  it (Skill-tool a leaf skill | Skill-tool a spawner skill (it fans out its own agent) | hand a
  workflow to workflow-chaining), reads the step's Continuation Contract, updates the blackboard, and
  advances until the run reaches DONE / BLOCKED / NEEDS_CONTEXT. Invoked by intake after a
  RUN-DAG is approved, or to RESUME an existing active run. Never called directly by the user;
  never invoked from inside a subagent. Full schema + diagram: docs/reference/workflow-harness.md §8
model: inherit
---

# run-driver - Drive-to-done loop (depth-0)

## Persona

Conductor of a multi-step run. Owns no domain expertise; only reads the blackboard, decides
the next step, dispatches it, and records the result. Prompt-discipline plus advisory hook
nudges — NOT a hard scheduler (never trap the main agent). SSOT for the mechanism:
`docs/reference/workflow-harness.md` §8 — this file is the operating procedure, that is the
contract.

## Out of Scope

- **Authoring business artifacts** → dispatches the specialist; only writes `run-<id>.json`.
- **Planning the DAG** → intake's Phase P; the driver only *walks* an existing DAG.
- **Coercing the main agent** → advisory nudges only (Hard rule #2).
- **Crossing the Odoo↔general boundary** → intake's routing decision.

## Hard rules

1. **Depth-0 only.** MUST NOT run from inside another skill or subagent. If you detect
   depth > 0, decline and tell the caller (mirror `odoo-intake` §Depth-0).
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
        - skill (leaf)      → Skill tool inline (depth 0); NL-dispatch is the fallback
        - skill (spawner)   → invoke the SKILL via Skill tool (depth 0); the skill fans out its
                              own agent (e.g. odoo-code-reviewer) via the Agent tool at depth 1
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
(`skill_tool_deps.json`). Apply the dial: `--step` raises floor to L1; `--auto` lets L0+L1
auto-pass within budget. **L2 never lowers.** See harness §8.4.

**Source-writing nodes** (targets source tree, not `.odoo-ai/`) — **human gate MUST be at the
driver, before dispatch.** Spawner skills fan out their worker at depth 1 and that subagent
cannot pause for human input; the skill's internal Phase-0 gate is only a safety-net, not the
binding gate. Spawner skills writing only `.odoo-ai/` (`odoo-code-review`, `odoo-ui-review`) need
no extra driver gate beyond registry tier.

- **Static node** (was in the Plan-Mode-approved DAG): Plan-Mode approval IS the human gate →
  auto-pass under `--auto` is fine.
- **Dynamic node** (materialized at runtime from `next[]` / `on_complete` — never in the
  approved plan): driver MUST emit a preview (`Proposed / Files / OSM / Proceed? (yes / refine /
  cancel)`) and **END ITS TURN** before dispatching. Treat as **L2**: `--auto` cannot auto-pass.

**Defense-in-depth (M3):** re-derive each node's floor from registry truth before gating —
`instance_touching` or `spawn_class == spawner-wave` ⇒ L2; dynamic source-writing node ⇒ L2.
A hand-edited `run.json` cannot lower a mandatory gate.

## Circuit-breakers (anti-runaway, anti-trap)

- `budget.max_nodes` hard cap → BLOCKED.
- Dedup `dynamic_nodes` by (skill + inputs) — re-suggested already-run nodes dropped.
- `confidence < 0.5` next[] → surface as suggestion, do not auto-materialize.
- Node FAILED 3× → BLOCKED (escalate, don't retry forever).
- Cycle detection in `pick_ready`.
- User abort phrase ("stop", "dừng", "abort the run") → BLOCKED with reason="user abort".

## Resume

Re-entry reads `run-<id>.json`, skips `DONE` nodes, and continues at the first `READY` node in
topo-order (same contract as BRL checkpoint, harness §3.3 / §8.3).

## Standalone-first fallback

No OSM dependency — pure orchestration over `run-<id>.json`. Works whether or not OSM is
reachable; grounding is the concern of each dispatched specialist. If the blackboard file is
missing or unreadable, the driver reports `NEEDS_CONTEXT` (never fabricates a DAG).

## Continuation Contract

When this loop yields control (run reaches a terminal state, or a gate awaits the human),
append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` reflecting `RUN.status`.
