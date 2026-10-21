# Large-change pipeline (P1-P5) - deterministic recipe

The recipe `git-pipeline-lead` follows for a LARGE change (past the M2 trigger in
`${CLAUDE_PLUGIN_ROOT}/snippets/git-scale-protocol.md`): it runs these phases BELOW the caller.
This file is agent-facing - the lead cites it, no dispatcher does. The per-phase model map (every
phase tier) lives only in `${CLAUDE_PLUGIN_ROOT}/snippets/git-nesting-protocol.md` N3.

Each leaf brief the lead writes states the phase's request and expected result, never git commands
or flags: the leaf owns that know-how (the commands are in the recipes named below).

Findings live under `.git-toolkit/<run-slug>/` (gitignore it). Every dispatch is a cold spawn with
a self-contained brief; every return is a 5-line summary + a findings-file path.

## P1 - MAP (git-surveyor, parallel x N)

Goal: a file -> cluster map with per-cluster size, no diff content read. The surveyors take the
name/count views of `${CLAUDE_PLUGIN_ROOT}/snippets/git-scale-recipes.md` R1 (changed-file list and
+/- per file for sizing).

Cluster by top-level directory / module / package. Split the file list across N surveyors when it
is itself huge. Each surveyor writes `survey/map-<n>.md`; the lead merges into `clusters.md`
({cluster -> [files], loc}).

## P2 - EVALUATE (git-surveyor, parallel per cluster)

One surveyor per cluster, given ONLY that cluster's path; it reads the cluster's scoped diff (the
scoped read in R1), which is bounded to the cluster.

Each returns: conflict likelihood, risk, business intent of the cluster's change. Writes
`survey/eval-<cluster>.md`. The lead collects verdicts; never re-reads the per-cluster diffs.

## P3 - STRATEGY (lead)

The lead synthesizes one safe execution plan: sequencing across clusters, conflict strategy,
worktree isolation, backup points, and the commit convention to use (detect once, pass to every
operator). Write `plan.md`.

When P4 would push to a protected branch without a pull request (the human-confirm gate in
`${CLAUDE_PLUGIN_ROOT}/snippets/git-safety-contract.md`) and the lead's brief carries no
`confirmed:`, present the plan + what changes on the remote, STOP, wait for explicit confirmation.
This gate is the LEAD's, never a leaf's. Every other step runs under S1 + S6 without a human.

## P4 - EXECUTE (git-operator, per cluster)

Hand each operator one cluster + its plan slice. Worktree-isolate parallel operators: one worktree
per cluster, on its own NEW branch `<run>/<cluster>` cut from the explicit `<base-ref>`, created
with no upstream per S13 (S9 shows the form). An operator's first push of that branch names the
remote and sets the upstream.

Each operator: S1 backup + pre-op SHA, apply the cluster's change, resolve conflicts to intent,
per-batch S6 tree-identity verify, commit per the convention. Returns its result; the lead records
backup-branch names in `plan.md`.

## P5 - VERIFY (git-surveyor)

Prove no loss across the whole change with the S6 checks in
`${CLAUDE_PLUGIN_ROOT}/snippets/git-safety-contract.md`: the diff against the backup is empty for a
clean rewrite, `range-diff` shows per-commit survival, and the tree SHA matches the pre-op one.

For rewrites that INTENTIONALLY change content (drop/edit a commit), apply the S6 survival rule -
`git range-diff` (every intended commit present, none unintentionally dropped), not the empty-diff
invariant - per `${CLAUDE_PLUGIN_ROOT}/snippets/git-safety-contract.md` S6.

Write `verify.md` with PASS/FAIL. FAIL -> the lead does NOT report DONE: restore from backup,
re-plan or escalate BLOCKED.

## Return (lead -> caller)

Only the final compact block (see `git-pipeline-lead` output format). No phase narration, no diff
content reaches the caller.
