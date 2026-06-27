<!-- SSOT snippet. The single home for the git-toolkit nesting model: cold-spawn handoff,
     the depth guard (only the pipeline lead spawns), leaf-no-spawn, the per-phase model map,
     and the Agent-unavailable fallback. Referenced via
     ${CLAUDE_PLUGIN_ROOT}/snippets/git-nesting-protocol.md. Edit here only. -->

# Git Nesting Protocol (SSOT)

The phased pipeline runs BELOW the caller so the caller's context stays pristine even for
thousand-file ops. This snippet defines how the nesting stays bounded and how it degrades when the
spawn tool is unavailable.

## N1 - Cold-spawn handoff (the only handoff mode here)

Every dispatch is a stateless COLD spawn via the Agent tool: a self-contained brief in, a compact
summary + a findings-file path out. The worker reconstructs its mental model from the brief plus the
findings files on disk - there is no warm team-resume. This is robust at ANY caller depth and needs
no team lead, so it works whether the caller is the main agent or itself a subagent.

- A brief carries: the exact intent, the safety contract pointer
  (`${CLAUDE_PLUGIN_ROOT}/snippets/git-safety-contract.md`), the scale pointer
  (`${CLAUDE_PLUGIN_ROOT}/snippets/git-scale-protocol.md`), the scoped target (paths/range/refs),
  and the chosen model.
- A return carries: a 5-line summary + the absolute findings-file path. Nothing else.

## N2 - Depth guard (anti-runaway)

ONLY `git-pipeline-lead` holds the subagent-spawning tool (the Agent tool). The three leaf agents -
`git-surveyor`, `git-operator`, `github-operator` - declare a `tools:` allowlist that EXCLUDES it,
so a leaf physically CANNOT spawn another agent. This caps nesting at two levels (lead -> leaf) and
makes a runaway spawn-storm impossible by construction.

- A leaf that "wants" to fan out CANNOT. It does its one scoped job and returns.
- Only the lead orchestrates a multi-worker pipeline.

## N3 - Per-phase model map (PHASED-PIPELINE)

The lead is opus. It assigns each phase its own model by cognitive load:

| Phase | Worker | Model | Why |
|---|---|---|---|
| P1 MAP | `git-surveyor` x N (parallel) | haiku | cheap mechanical `--name-only`/`--numstat` clustering |
| P2 EVALUATE | `git-surveyor` per cluster | sonnet | read a scoped diff, assess conflict/risk/intent |
| P3 STRATEGY | `git-pipeline-lead` (self) | opus | synthesize the safe execution plan + sequencing |
| P4 EXECUTE | `git-operator` per cluster | sonnet, opus for complex rewrite | apply with backup + per-batch verify |
| P5 VERIFY | `git-surveyor` | sonnet | tree-identity + range-diff + no-loss proof |

P3 strategy AND the human-confirm gate for destructive plans are the LEAD's job, never a leaf's.

## N4 - Agent-unavailable fallback

If the caller cannot cold-spawn (the Agent tool is absent in this context), DEGRADE - never fail
silently:

1. SINGLE-DELEGATE if a single leaf would suffice -> if no spawn, then
2. INLINE-with-contract: run the SAFE, BOUNDED-OUTPUT command directly, applying the safety
   contract inline, and keep the scale protocol (never read a huge diff inline).

Never substitute "always-delegate" for a missing spawn - every nested op here is a fresh cold spawn,
so there is no warm-resume to fall back to. Note the degraded tier in the return if it changed the
outcome.
