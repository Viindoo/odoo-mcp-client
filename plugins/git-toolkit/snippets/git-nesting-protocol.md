# Git Nesting Protocol (SSOT)

How git work runs below its caller: who may launch, how a result is collected, what a brief
carries.

## N0 - Launch and collect: the launch tool you hold decides

Read your own toolset before launching. The agent-launch tool you hold decides how a child's
result reaches you:

- **You hold none**: a dispatcher returns `NEEDS_CONTEXT` (N4); a leaf never launches (N2) and
  does its own scoped job. Never report a dispatch you could not make.
- **The tool has a `run_in_background` parameter**: launch every child whose result you need with
  `run_in_background: false` (the default is asynchronous); the call returns the result inside
  your turn. Independent children go in one message as several calls. Never end your turn while a
  child you launched runs: nothing wakes an agent that stopped, and its result goes to the main
  conversation instead.
- **The tool has no such parameter**: every launch returns a receipt. Launch, then end your turn;
  you are woken once per child as each completes. On every wake check which children are still
  outstanding. Never poll, never sleep for them, and never keep working in the same turn after
  the launch: a launcher that does not stop is never handed a result.

**An async receipt while you hold the parameter**: do not end your turn. Keep making tool calls -
a bounded wait, then a look at what arrived - until the completion notice reaches you, then read
the result.

**The main conversation** is notified of every completion. When a notice reaches it for a child a
dispatched agent launched, it does not act on that result: it resumes that agent by id so the
agent collects it.

A shell tool's flag of the same name decides nothing here. Always: never do a child's work while
it runs, never re-launch a running child, never end a turn with uncommitted work.

## N1 - Cold-spawn handoff (the default handoff mode)

Every dispatch is a stateless cold spawn: a self-contained brief in, a compact summary and a
findings-file path out. The worker rebuilds its picture from the brief and the findings files on
disk, so the handoff works at any caller depth.

- **A brief carries** the request and the expected result in business terms - what is wanted,
  which repository, worktree and branch, the outcome behind it, the constraints, what the caller
  needs back - plus the scoped target (paths, range, refs) and the chosen model. It never carries
  git or GitHub-CLI commands or flags: the receiving agent owns that know-how, and a command in a
  brief overrides it.
- **A return carries** a five-line summary and the absolute findings-file path, handed back once
  as the last act of the dispatch (`${CLAUDE_PLUGIN_ROOT}/snippets/completion-reporting.md`), to
  the launcher that collects it per N0.

## N2 - Depth guard (anti-runaway)

Only `git-pipeline-lead` can launch agents. The leaves - `git-surveyor`, `git-operator`,
`github-operator` - declare a `tools:` allowlist without the launch tool, so nesting stops at two
levels (lead -> leaf). A leaf does its one scoped job and returns.

## N3 - Per-phase model map (PHASED-PIPELINE)

The caller fixes the lead's tier at launch (`git-model-tiers.md` row 1); the lead assigns each
phase its model, and this table is the only copy:

| Phase | Worker | Model |
|---|---|---|
| P1 MAP - cluster files and line counts | `git-surveyor` x N, in parallel | haiku |
| P2 EVALUATE - read a scoped diff, assess conflict, risk, intent | `git-surveyor` per cluster | haiku (sonnet for a cluster flagged high-risk) |
| P3 STRATEGY - the safe execution plan and its sequencing | `git-pipeline-lead` itself | the lead's |
| P4 EXECUTE - apply with backup and per-batch verify | `git-operator` per cluster | sonnet (haiku for a conflict-free cherry-pick or merge cluster) |
| P5 VERIFY - tree identity, range-diff, no-loss proof | `git-surveyor` | sonnet |

Tier vocabulary and the single-delegate table: `${CLAUDE_PLUGIN_ROOT}/snippets/git-model-tiers.md`.
P3 and, when the plan changes a protected branch without a pull request, the human-confirm gate
are the lead's job, never a leaf's.

## N4 - Agent-unavailable fallback (dispatchers only)

A context whose job is to dispatch git work - the `git-ops` skill, a caller, `git-pipeline-lead`
- and that cannot launch agents returns `NEEDS_CONTEXT` ("needs a context that can launch git-ops
agents") and runs nothing itself, not even a bounded read. A leaf runs git under its own contract;
its missing launch tool is the N2 guard, not a gap to report.

## N5 - Brief contract (Git family delta)

On top of N1, a brief to a git-toolkit agent carries:

- **BASE ref and TARGET ref** whenever the op integrates, rebases or forward-ports: the ref the op
  starts from and the ref the change must land on. A bare "rebase this" is under-specified.
- **`confirmed: <verbatim human approval>`** for a push that moves or deletes a protected branch
  or a pull-request merge into one. Without it the agent stops at the human-confirm gate of
  `${CLAUDE_PLUGIN_ROOT}/snippets/git-safety-contract.md`. Every other rewrite needs no
  confirmation and runs under S1 and S6.
- **The commit convention is detected, never invented**: the agent resolves the actual one per
  `${CLAUDE_PLUGIN_ROOT}/snippets/commit-convention.md` C3; a preference the caller states is a
  hint.
- **What must not be touched**: the primary checkout (S9), any path or cluster outside the
  agent's assigned scope and, inside a phased pipeline, any step outside the P3-approved slice.

## N6 - Brief self-check

Before acting, an agent checks its brief:

- **A missing field with a safe, reversible default** (a TARGET the assigned scope makes
  unambiguous): proceed and state the assumption as the first line of the return.
- **A missing objective or done-condition, or a missing Git-family field with no safe default**
  (no BASE/TARGET for an integration or rewrite op, no `confirmed:` ahead of the gate, a commit
  convention that cannot be resolved): return `NEEDS_CONTEXT(<field>)`, or `BLOCKED(<field>)`
  when the gap is irreversible or large. Never guess, never invent a convention, never
  self-authorize the gated op.
- **A supplied commit message that does not match the detected convention, with no business
  outcome to rewrite it from**: return `NEEDS_CONTEXT(business-outcome)`.

`git-toolkit` depends on no other plugin: this file is the one home of the Git family's brief
delta and self-check.
