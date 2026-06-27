<!-- SSOT snippet. The single home for the git scale protocol: never read a huge diff into
     context, the numeric large-change trigger, cluster-then-delegate, and the huge-repo
     fetch strategies (sparse/partial-clone/LFS). Referenced via
     ${CLAUDE_PLUGIN_ROOT}/snippets/git-scale-protocol.md. Edit here only. -->

# Git Scale Protocol (SSOT)

Git churn must happen in a delegated context so the caller stays clean; the fastest way to defeat
that is piping a 50k-line diff into a context window. Read SUMMARIES first, cluster, then delegate
per cluster - never the raw whole.

## M1 - Never read a huge diff into context

Start every large-change analysis with a NAME/COUNT view, not the content:

```bash
git diff --name-only <range>     # file list only - use FIRST
git diff --name-status <range>   # M / A / D per file
git diff --numstat <range>       # +/- counts per file
git diff --stat <range>          # human summary - good for a PR overview
git diff -- path/to/cluster/     # scoped content read, AFTER clustering
```

Three-dot `<base>...<head>` gives changes since the branch point; two-dot `<base>..<head>` gives
the raw range. Pick deliberately.

## M2 - Numeric large-change trigger

A change is LARGE - route it to the PHASED-PIPELINE (cold-spawn `git-pipeline-lead`), never an
inline read - when ANY of these holds:

- more than 500 files changed, OR
- more than 10,000 lines changed (sum of `--numstat` adds+deletes), OR
- a multi-commit history rewrite, OR
- a thousand-file backport / forward-port.

Below all thresholds and low-risk: SINGLE-DELEGATE one leaf, or INLINE if bounded-output. The
threshold is on OUTPUT SIZE and RISK, not step count.

## M3 - Cluster, then delegate per cluster

1. `git diff --name-only` -> the changed-file list.
2. Cluster files by directory / module / top-level package.
3. For each cluster: dispatch ONE worker with a SCOPED diff (`git diff -- <cluster-path>`); it
   reads only its slice, writes a findings file, returns a compact summary + the file path.
4. Synthesize cluster findings centrally - never re-read the per-cluster diffs in the synthesizer.
5. NEVER load the full large diff in one context window at any tier.

## M4 - Huge-repo fetch strategy

For repos too large to fully clone, fetch a SUBSET:

```bash
git clone --filter=blob:none --sparse <url>        # partial clone - skip blobs
git sparse-checkout set path/to/mod1 path/to/mod2  # cone mode - fastest
git sparse-checkout list
git sparse-checkout disable
```

For large binaries, use LFS:

```bash
git lfs track "*.psd" "*.zip"
git lfs ls-files
git lfs pull
git lfs migrate import --include="*.bin"
```

A plain `git clone` without an LFS client yields pointer files, not content - install the client or
`git lfs pull` before reading tracked binaries.

## M5 - Compact-return contract for scale workers

A worker dispatched on a cluster returns ONLY: a <=5 key-line summary + the absolute path to its
findings file. It does NOT echo diff hunks, file contents, or stack traces back to the caller. The
findings file carries detail; the return carries the gate-able conclusion.
