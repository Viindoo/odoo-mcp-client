# Large-change pipeline (P1-P5) - deterministic recipe

The PHASED-PIPELINE recipe for a LARGE change (>500 files OR >10k LOC OR a multi-commit rewrite OR a
thousand-file backport, per `${CLAUDE_PLUGIN_ROOT}/snippets/git-scale-protocol.md` M2). Cold-spawn
`git-pipeline-lead` (opus); it runs these phases BELOW the caller. The per-phase model map lives in
`${CLAUDE_PLUGIN_ROOT}/snippets/git-nesting-protocol.md` N3.

Findings live under `.git-toolkit/<run-slug>/` (gitignore it). Every dispatch is a cold spawn with
a self-contained brief; every return is a 5-line summary + a findings-file path.

## P1 - MAP (git-surveyor @ haiku, parallel x N)

Goal: a file -> cluster map with per-cluster size, no diff content read.

```bash
git diff --name-only <range>     # full changed-file list
git diff --numstat <range>       # +/- per file for cluster sizing
```

Cluster by top-level directory / module / package. Split the file list across N surveyors when it
is itself huge. Each surveyor writes `survey/map-<n>.md`; the lead merges into `clusters.md`
({cluster -> [files], loc}).

## P2 - EVALUATE (git-surveyor @ sonnet, parallel per cluster)

One surveyor per cluster, given ONLY that cluster's path:

```bash
git diff -- <cluster-path>       # scoped content - safe, bounded to the cluster
```

Each returns: conflict likelihood, risk, business intent of the cluster's change. Writes
`survey/eval-<cluster>.md`. The lead collects verdicts; never re-reads the per-cluster diffs.

## P3 - STRATEGY + HUMAN-CONFIRM (lead, opus)

The lead synthesizes one safe execution plan: sequencing across clusters, conflict strategy,
worktree isolation, backup points, and the commit convention to use (detect once, pass to every
operator). Write `plan.md`.

Then the HUMAN-CONFIRM gate for any destructive step (the 8-item list in
`${CLAUDE_PLUGIN_ROOT}/snippets/git-safety-contract.md`): present the plan + what is irreversible,
STOP, wait for explicit confirmation. This gate is the LEAD's, never a leaf's.

## P4 - EXECUTE (git-operator @ sonnet, opus for complex rewrite, per cluster)

Hand each operator one cluster + its plan slice. Worktree-isolate parallel operators:

```bash
git worktree add -b <run>/<cluster> <path>/<cluster> <base-ref>
```

Each operator: S1 backup + pre-op SHA, apply the cluster's change, resolve conflicts to intent,
per-batch S6 tree-identity verify, commit per the convention. Returns its result; the lead records
backup-branch names in `plan.md`.

## P5 - VERIFY (git-surveyor @ sonnet)

Prove no loss across the whole change:

```bash
git diff <backup>..HEAD                       # MUST be empty for a clean rewrite
git range-diff <old-base>..<old-tip> <new-base>..<new-tip>   # per-commit survival
git rev-parse HEAD^{tree}                      # compare to pre-op tree SHA
```

For rewrites that INTENTIONALLY change content (drop/edit a commit), apply the S6 survival rule -
`git range-diff` (every intended commit present, none unintentionally dropped), not the empty-diff
invariant - per `${CLAUDE_PLUGIN_ROOT}/snippets/git-safety-contract.md` S6.

Write `verify.md` with PASS/FAIL. FAIL -> the lead does NOT report DONE: restore from backup,
re-plan or escalate BLOCKED.

## Return (lead -> caller)

Only the final compact block (see `git-pipeline-lead` output format). No phase narration, no diff
content reaches the caller.
