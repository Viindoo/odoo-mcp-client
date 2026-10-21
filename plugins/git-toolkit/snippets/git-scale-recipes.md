<!-- SSOT snippet. The single home for the command recipes behind the git scale protocol: the
     name/count views that come before any content read, the scoped read, and the huge-repo
     fetch strategies. AGENT-FACING: read by git-surveyor, git-operator and git-pipeline-lead,
     never by a dispatcher and never copied into a brief. The rules (never read a huge diff
     whole, the numeric trigger, cluster-then-delegate) live in git-scale-protocol.md. Referenced
     via ${CLAUDE_PLUGIN_ROOT}/snippets/git-scale-recipes.md. Edit here only. -->

# Git Scale Recipes (SSOT, agent-facing)

How the agents carry out `${CLAUDE_PLUGIN_ROOT}/snippets/git-scale-protocol.md`. Each command runs
as one plain call in the S12 shape of `${CLAUDE_PLUGIN_ROOT}/snippets/git-safety-contract.md`.

## R1 - Name/count view first (protocol M1)

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

## R2 - Cluster, then read per cluster (protocol M3)

1. The name-only list from R1 is the changed-file list.
2. Cluster files by directory / module / top-level package.
3. A worker reads only its cluster, through the scoped read in R1.

## R3 - Huge-repo fetch strategy (protocol M4)

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
