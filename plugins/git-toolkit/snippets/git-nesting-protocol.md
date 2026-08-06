<!-- SSOT snippet. The single home for the git-toolkit nesting model: cold-spawn handoff,
     the depth guard (only the pipeline lead spawns), leaf-no-spawn, the per-phase model map,
     the Agent-unavailable fallback, the Git family's brief delta, and the Brief self-check
     every git-toolkit agent runs. Referenced via
     ${CLAUDE_PLUGIN_ROOT}/snippets/git-nesting-protocol.md. Edit here only. -->

# Git Nesting Protocol (SSOT)

The phased pipeline runs BELOW the caller so the caller's context stays pristine even for
thousand-file ops. This snippet defines how the nesting stays bounded and how it degrades when the
spawn tool is unavailable.

**Before launching, read your own toolset.** If agent-launch capability is absent, do the work
yourself or return BLOCKED with the resumable state - never report a dispatch you could not make.
When the launch capability exposes a background/foreground switch, launch in the blocking mode when
you need the result - it returns inside your turn. When it does not, the launch is asynchronous:
launch, then end your turn to be resumed - never poll, never re-launch. Because a parked agent is
not resumed on every surface, never end a turn with uncommitted work.

## N1 - Cold-spawn handoff (the default handoff mode)

Every dispatch is a stateless COLD spawn by launching an agent: self-contained brief in, compact
summary + findings-file path out. The worker reconstructs its model from the brief plus the findings
files on disk - no warm team-resume. This is the DEFAULT and always-correct baseline: robust at ANY
caller depth and needing no team lead, so it works whether the caller is the main agent or itself a
subagent.

- A brief carries: the exact intent, the safety contract pointer
  (`${CLAUDE_PLUGIN_ROOT}/snippets/git-safety-contract.md`), the scale pointer
  (`${CLAUDE_PLUGIN_ROOT}/snippets/git-scale-protocol.md`), the scoped target (paths/range/refs),
  and the chosen model.
- A return carries: a 5-line summary + the absolute findings-file path. Nothing else.

A caller MAY instead spawn the agent as a NAMED TEAMMATE (Agent Team mode), where the agent persists
in the background and the lead waits on a message from it. That does NOT replace cold-spawn - it adds
one obligation on top: the agent additionally pushes a completion report to the lead as its terminal
action, per `${CLAUDE_PLUGIN_ROOT}/snippets/agent-team-reporting.md`. The cold-spawn guarantee
stands; team mode only changes how the worker's turn ENDS.

`git-pipeline-lead` ALWAYS cold-spawns its leaves and never spawns one as a named teammate, because
it is itself a subagent - a separate context, not the `main`-context lead - so a leaf's `to: "main"`
completion report would misdeliver to the top-level main context, past the pipeline lead, leaving it
stranded.

This is the same report-up-one-level principle stated universally elsewhere: a worker reports to its
direct launcher, never a grand-parent. The pipeline lead enforces it CONSERVATIVELY by refusing
named-teammate mode when nested, so a leaf's return is structurally addressed to its launcher
(cold-spawn has no address field to mis-set). The categorical rule here and the per-field `REPLY_TO`
rule used elsewhere are two implementations of one principle, not two policies.

## N2 - Depth guard (anti-runaway)

ONLY `git-pipeline-lead` holds agent-launch capability. The three leaf agents -
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

Tier vocabulary and the single-delegate op-class table: `${CLAUDE_PLUGIN_ROOT}/snippets/git-model-tiers.md`.

P3 strategy AND the human-confirm gate for destructive plans are the LEAD's job, never a leaf's.

## N4 - Agent-unavailable fallback

If the caller cannot cold-spawn (agent-launch capability is absent in this context), DEGRADE - never fail
silently:

1. SINGLE-DELEGATE if a single leaf would suffice -> if no spawn, then
2. INLINE-with-contract: run the SAFE, BOUNDED-OUTPUT command directly, applying the safety
   contract inline, and keep the scale protocol (never read a huge diff inline).

Never substitute "always-delegate" for a missing spawn - every nested op is a fresh cold spawn, so
there is no warm-resume to fall back to. Note the degraded tier in the return if it changed the
outcome.

## N5 - Brief contract (Git family delta)

Every brief a caller hands to a git-toolkit agent - leaf or lead - carries the Git family's own
required fields, on top of the cold-spawn contents already listed in N1:

- **BASE ref + TARGET ref.** The ref/branch the op starts from (BASE - e.g. the pre-op tip, the
  branch being integrated) and the ref/branch the change must land on (TARGET - e.g. the
  integration branch, the upstream branch, the PR base). Both are required whenever the op
  integrates, rebases, or forward-ports; a bare "rebase this" or "forward-port that" with no
  BASE/TARGET pair is under-specified.
- **Safety-gate flag for any destructive rewrite or force-push.** Interactive rebase, squash,
  split, amend, reset, `filter-repo`, and force-with-lease push all require the brief to state
  whether human confirmation was already obtained. Absent that flag, the agent MUST stop at the
  human-confirm gate in `${CLAUDE_PLUGIN_ROOT}/snippets/git-safety-contract.md` - it never
  self-authorizes a destructive op to compensate for a missing flag.
- **Detect the commit convention, do not invent one.** The brief may point at a project
  guideline, but the agent always resolves the ACTUAL convention per
  `${CLAUDE_PLUGIN_ROOT}/snippets/commit-convention.md` C3 (explicit guideline -> history
  inference -> repo-type). A caller-stated preference is a hint, never a license to skip
  detection or invent a format the repo does not use.
- **What must NOT be touched.** The primary/shared checkout (S9 worktree-always in
  `git-safety-contract.md` - every mutation runs in a dedicated worktree, never in-place); any
  path or cluster outside the agent's assigned scope; and, inside a phased pipeline, any step
  outside the P3-approved plan slice.

## N6 - Brief self-check

Every git-toolkit agent checks its inbound brief before acting, graduated by how recoverable the
gap is:

- **A missing field with a safe, reversible default** (e.g. TARGET left implicit when the
  assigned scope already makes it unambiguous) - PROCEED and state the assumption as the first
  line of the return.
- **A missing OBJECTIVE, a missing done-condition, or a missing load-bearing Git-family field with
  no safe default** (no BASE/TARGET for an integration or rewrite op, no safety-gate flag ahead of
  a destructive op, a commit convention that cannot be resolved) - STOP and return
  `NEEDS_CONTEXT(<field>)` (the caller can re-brief) or `BLOCKED(<field>)` (the gap is
  irreversible or large). Never silently guess, never invent a convention, and never
  self-authorize a destructive op to fill the gap.

This is the git-toolkit equivalent of a caller-side dispatch-brief schema. There is intentionally
no reference to `dispatch-brief.md` here - `git-toolkit` is a separate, dependency-free plugin
(see CLAUDE.md); this file is the SOLE home for both the Git family's brief delta (N5) and its
self-check (N6). Each of the 4 git-toolkit agents carries a short `## Brief self-check` body
section that points back at this file, never at `dispatch-brief.md`.
