<!-- SSOT snippet. The single home for the git scale protocol RULES: never read a huge diff into
     context, the numeric large-change trigger, cluster-then-delegate, the huge-repo strategy
     and the compact return. Outcomes only - the commands that carry them out live in a sibling
     snippet that only agents read. Referenced via
     ${CLAUDE_PLUGIN_ROOT}/snippets/git-scale-protocol.md. Edit here only. -->

# Git Scale Protocol (SSOT)

Git churn must happen in a delegated context so the caller stays clean; the fastest way to defeat
that is piping a 50k-line diff into a context window. Read SUMMARIES first, cluster, then delegate
per cluster - never the raw whole. The protocol exists for caller-context hygiene, parallelism and
the human gate; it is not a model capacity limit. The protocol states outcomes; the agents that
carry it out own the commands.

## M1 - Never read a huge diff into context

Start every large-change analysis with a NAME/COUNT view of the change - which files, how many
lines per file, added/modified/deleted - not the content. Content is read only per cluster, after
clustering. Choose deliberately between "changes since the branch point" and "the raw range" when
framing the comparison.

## M2 - Numeric large-change trigger

A change is LARGE - route it to the PHASED-PIPELINE (cold-spawn `git-pipeline-lead`), never one
leaf's single pass - when ANY of these holds:

- more than 500 files changed, OR
- more than 10,000 lines changed (added + deleted, summed over the files), OR
- a multi-commit history rewrite, OR
- a thousand-file backport / forward-port.

Below all thresholds: ONE leaf (`git-surveyor`, `git-operator` or `github-operator`) takes the op.
The threshold is on OUTPUT SIZE and RISK, not step count.

## M3 - Cluster, then delegate per cluster

1. Take the changed-file list.
2. Cluster files by directory / module / top-level package.
3. For each cluster: dispatch ONE worker with the cluster as its scope; it reads only its slice,
   writes a findings file, returns a compact summary + the file path.
4. Synthesize cluster findings centrally - never re-read the per-cluster diffs in the synthesizer.
5. NEVER load the full large diff into the caller's context at any tier: the diff is read by the
   delegated worker, one scoped cluster at a time, so the caller stays clean.

## M4 - Huge-repo fetch strategy

For repos too large to fully clone, the worker fetches a SUBSET (partial clone with a sparse
checkout of the needed paths), and handles large binaries through LFS, installing the LFS client
and pulling content before reading tracked binaries.

## M5 - Compact-return contract for scale workers

A worker dispatched on a cluster returns ONLY: a <=5 key-line summary + the absolute path to its
findings file. It does NOT echo diff hunks, file contents, or stack traces back to the caller. The
findings file carries detail; the return carries the gate-able conclusion.
